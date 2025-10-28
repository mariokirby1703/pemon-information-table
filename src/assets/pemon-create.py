#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pemons builder: fetch Geometry Dash level metadata either via GDBrowser
or directly from the official GD (Boomlings) endpoints.

- Source choice at startup (GDBrowser or GD-Server).
- Flexible selection: ranges by position (number), "last N", or explicit IDs via "id:".
- Merges into OUTPUT_FILE with conservative rules (objects cap, songID states).
- Robust rate limiting & retry/backoff for Boomlings.
- 'showcase' field is removed everywhere (added/updated/skipped and legacy).

ENV (optional):
  RL_MIN_INTERVAL, RL_RETRY_MAX, RL_BACKOFF_BASE, RL_BACKOFF_CAP,
  RL_JITTER_MIN, RL_JITTER_MAX, RL_POOL_CONNECTIONS, RL_POOL_MAXSIZE
"""

import os
import re
import json
import time
import base64
import random
import requests
from collections import deque
from threading import Lock
from requests.exceptions import ConnectionError, ReadTimeout, ChunkedEncodingError
from urllib3.exceptions import ProtocolError

# ===================== Config =====================
INPUT_FILE = "pemon_ids.txt"
OUTPUT_FILE = "pemons.json"

# ===================== Rate Limiter (20 req/min) + robust POST =====================
MIN_INTERVAL = float(os.getenv("RL_MIN_INTERVAL", "3"))  # ~20/min
# Max 4 in 10s (sanft), max 20 in 60s (Zielrate)
WINDOWS = [(10, 4), (60, 20)]

RETRY_MAX = int(os.getenv("RL_RETRY_MAX", "5"))
BACKOFF_BASE = float(os.getenv("RL_BACKOFF_BASE", "1.5"))
BACKOFF_CAP = float(os.getenv("RL_BACKOFF_CAP", "30"))
JITTER_MIN = float(os.getenv("RL_JITTER_MIN", "0.05"))
JITTER_MAX = float(os.getenv("RL_JITTER_MAX", "0.15"))

# ===================== Telemetry & Caches =====================
stats = {
    "creator_from_21": 0,
    "creator_from_account": 0,
    "creator_from_user": 0,
    "creator_from_gdb": 0,
    "creator_missing": 0,
    "song_from_21": 0,
    "song_from_api": 0,
    "song_missing": 0,
}
levels21_cache: dict[str, str] = {}
account_name_cache: dict[int, str] = {}
user_name_cache: dict[int, str] = {}
song_cache: dict[int, dict] = {}

POOL_CONNECTIONS = int(os.getenv("RL_POOL_CONNECTIONS", "8"))
POOL_MAXSIZE    = int(os.getenv("RL_POOL_MAXSIZE", "8"))

class RateLimiter:
    """Token-bucket style limiter supporting multiple sliding windows."""
    def __init__(self, min_interval: float, windows: list[tuple[int, int]]):
        self.min_interval = float(min_interval)
        self.windows = sorted([(int(w), int(c)) for w, c in windows], key=lambda x: x[0])
        self._lock = Lock()
        self._last = None
        self._buckets = {w: deque() for w, _ in self.windows}

    def _prune(self, now: float):
        for w, dq in self._buckets.items():
            while dq and now - dq[0] >= w:
                dq.popleft()

    def wait(self):
        while True:
            now = time.monotonic()
            with self._lock:
                self._prune(now)
                wait = 0.0
                if self._last is not None:
                    wait = max(wait, self.min_interval - (now - self._last))
                for w, max_calls in self.windows:
                    dq = self._buckets[w]
                    if len(dq) >= max_calls:
                        wait = max(wait, w - (now - dq[0]))
                if wait <= 0:
                    now = time.monotonic()
                    self._prune(now)
                    for w in self._buckets:
                        self._buckets[w].append(now)
                    self._last = now
                    return
            time.sleep(wait)

rate_limiter = RateLimiter(MIN_INTERVAL, WINDOWS)

_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=POOL_CONNECTIONS, pool_maxsize=POOL_MAXSIZE, max_retries=0)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

def _respect_retry_after(resp) -> float:
    ra = resp.headers.get("Retry-After")
    if not ra:
        return 0.0
    try:
        return max(0.0, float(ra))
    except Exception:
        return 30.0

def _post(url, data, headers, timeout=30):
    """Robust POST with limiter + retries for Boomlings endpoints."""
    attempt = 0
    while True:
        attempt += 1
        rate_limiter.wait()
        time.sleep(random.uniform(JITTER_MIN, JITTER_MAX))
        try:
            resp = _session.post(url, data=data, headers=headers, timeout=timeout)
        except (ConnectionError, ProtocolError, ReadTimeout, ChunkedEncodingError):
            if attempt >= RETRY_MAX:
                raise
            backoff = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            time.sleep(backoff + random.uniform(JITTER_MIN, JITTER_MAX))
            continue

        s = resp.status_code
        if 200 <= s < 400:
            return resp
        if s == 429:
            if attempt >= RETRY_MAX:
                return resp
            wait = _respect_retry_after(resp) or min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            time.sleep(wait + random.uniform(JITTER_MIN, JITTER_MAX))
            continue
        if 500 <= s < 600:
            if attempt >= RETRY_MAX:
                return resp
            backoff = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            time.sleep(backoff + random.uniform(JITTER_MIN, JITTER_MAX))
            continue
        if s == 403:
            if attempt >= min(RETRY_MAX, 2):
                return resp
            time.sleep(60.0 + random.uniform(0.5, 1.5))
            continue
        return resp

# ===================== Boomlings API Helpers =====================
BASE = "http://www.boomlings.com/database"
SECRET = "Wmfd2893gb7"
HEADERS = {
    "User-Agent": "",  # leave empty
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "*/*",
    "Connection": "close",
}

def _kv_block(text: str) -> dict:
    """Parse colon-separated k:v blocks used by many Boomlings endpoints."""
    if "#" in text:
        text = text.split("#", 1)[0]
    parts = text.strip().split(":")
    out = {}
    for i in range(0, len(parts) - 1, 2):
        k, v = parts[i], parts[i + 1]
        if k:
            out.setdefault(k, v)
    return out

def _kv_tilde(text: str) -> dict:
    parts = text.strip().split("~|~")
    out = {}
    for i in range(0, len(parts) - 1, 2):
        k, v = parts[i], parts[i + 1]
        if k:
            out[k] = v
    return out

def _to_int(s, default=0):
    try:
        return int(s)
    except Exception:
        return default

def _b64_text(s: str) -> str:
    """Base64 decode with fallback for URL-safe variants."""
    if not s:
        return ""
    try:
        return base64.b64decode(s.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        s2 = s.replace("-", "+").replace("_", "/")
        pad = (-len(s2)) % 4
        try:
            return base64.b64decode(s2 + "=" * pad).decode("utf-8", errors="replace")
        except Exception:
            return ""

def _non_demon_diff(numer: int) -> str:
    return {10: "Easy", 20: "Normal", 30: "Hard", 40: "Harder", 50: "Insane"}.get(numer, "N/A")

def _demon_name(code: int) -> str:
    return {3: "Easy", 4: "Medium", 0: "Hard", 5: "Insane", 6: "Extreme"}.get(code, "Unknown")

# --- Boomlings fetchers & parsers ---
def _fetch_download(level_id: int) -> dict:
    url = f"{BASE}/downloadGJLevel22.php"
    r = _post(url, data={"levelID": str(level_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code == 403:
        raise RuntimeError("403/Cloudflare (download).")
    r.raise_for_status()
    txt = r.text.strip()
    if not txt or txt == "-1":
        raise RuntimeError(f"Level {level_id} not found / error: {txt!r}")
    return _kv_block(txt)

def _fetch_levels21_raw(level_id: int) -> str:
    url = f"{BASE}/getGJLevels21.php"
    r = _post(url, data={"levelID": str(level_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code == 403:
        raise RuntimeError("403/Cloudflare (getGJLevels21).")
    r.raise_for_status()
    return r.text.strip()

def _parse_creators_map_from_levels21(raw: str) -> dict[int, str]:
    """Parse creators section defensively: map any numeric token to the following non-numeric token."""
    result = {}
    parts = raw.split("#")
    if len(parts) < 2:
        return result
    creators = parts[1]
    for chunk in creators.split("|"):
        if not chunk:
            continue
        tokens = chunk.split(":")
        for i in range(len(tokens) - 1):
            if tokens[i].isdigit() and not tokens[i + 1].isdigit():
                try:
                    result[int(tokens[i])] = tokens[i + 1]
                except Exception:
                    pass
    return result

def _kv_tilde_song_to_dict(text: str) -> dict:
    kv = _kv_tilde(text)
    return {
        "id": _to_int(kv.get("1", "0")),
        "name": kv.get("2", ""),
        "artist": kv.get("4", ""),
        "size": kv.get("5", ""),
        "url": kv.get("10", "-"),
    }

def _fetch_username_by_account_id(account_id: int) -> str:
    if not account_id:
        return ""
    url = f"{BASE}/getGJUserInfo20.php"
    r = _post(url, data={"targetAccountID": str(account_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return ""
    txt = r.text.strip()
    if not txt or txt == "-1":
        return ""
    kv = _kv_block(txt)
    return kv.get("2", "") or ""

def _fetch_username_by_user_id(user_id: int) -> str:
    if not user_id:
        return ""
    url = f"{BASE}/getGJUserInfo20.php"
    r = _post(url, data={"targetUserID": str(user_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return ""
    txt = r.text.strip()
    if not txt or txt == "-1":
        return ""
    kv = _kv_block(txt)
    return kv.get("2", "") or ""

def _fetch_song(song_id: int) -> dict:
    if not song_id:
        return {}
    url = f"{BASE}/getGJSongInfo.php"
    r = _post(url, data={"songID": str(song_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code != 200 or r.text.strip() == "-1":
        return {}
    return _kv_tilde_song_to_dict(r.text.strip())

def _fallback_creator_from_gdbrowser(level_id: str) -> str:
    try:
        r = requests.get(f"https://gdbrowser.com/api/level/{level_id}", timeout=15)
        if r.status_code == 200:
            j = r.json()
            return j.get("author", "") or ""
    except Exception:
        pass
    return ""

def _extract_song_meta_from_levels21(raw21: str, custom_song_id: int) -> dict:
    """Liest Song-Name/Artist aus dem Songs-Block von getGJLevels21."""
    if not raw21 or not custom_song_id:
        return {}
    try:
        parts = raw21.split("#")
        if len(parts) < 3:
            return {}
        songs = parts[2]
        recs = re.split(r":~1~\|~", songs)
        if recs:
            if not recs[0].startswith("1~|~"):
                idx = recs[0].find("1~|~")
                if idx != -1:
                    recs[0] = recs[0][idx:]
            if recs[0] and not recs[0].startswith("1~|~"):
                recs[0] = "1~|~" + recs[0]
        for rec in recs:
            if not rec.strip():
                continue
            fields = rec.split("~|~")
            d = {}
            for i in range(0, len(fields) - 1, 2):
                d[fields[i]] = fields[i + 1]
            sid = _to_int(d.get("1", "0"))
            if sid and sid == custom_song_id:
                return {"name": d.get("2", ""), "artist": d.get("4", "")}
    except Exception:
        return {}
    return {}

# ===================== Fetchers =====================
def get_level_data_gdbrowser(level_id: str, number: int, skip_warnings: bool = False):
    """Fetch via GDBrowser JSON API (unchanged)."""
    url = f"https://gdbrowser.com/api/level/{level_id}"
    try:
        resp = requests.get(url, timeout=30)
    except Exception:
        print(f"[!] Network error fetching level {level_id} from GDBrowser.")
        return None

    if resp.status_code != 200:
        print(f"[!] Failed to fetch level {level_id} from GDBrowser (HTTP {resp.status_code})")
        return None

    try:
        data = resp.json()
    except Exception:
        print(f"[!] Invalid JSON for level {level_id} from GDBrowser.")
        return None

    cp = int(data.get("cp", 0))
    rating_map = {1: "Rated", 2: "Featured", 3: "Epic", 4: "Legendary", 5: "Mythic"}
    rating = rating_map.get(cp, "")

    official = int(data.get("officialSong", 0)) != 0
    song_name = data.get("songName", "") or ""
    song_author = data.get("songAuthor", "") or ""
    song_id_val = "OFFICIAL" if official else int(data.get("songID", 0)) if str(data.get("songID", "0")).isdigit() else ""

    level_info = {
        "number": number,
        "level": data.get("name", "") or "",
        "creator": data.get("author", "") or "",
        "ID": int(data.get("id", 0)),
        "difficulty": data.get("difficulty", "") or "",
        "rating": rating,
        "userCoins": int(data.get("coins", 0)),
        "estimatedTime": None,
        "objects": int(data.get("objects", 0)),
        "checkpoints": None,
        "twop": bool(data.get("twoPlayer", False)),
        "primarySong": song_name,
        "artist": song_author,
        "songID": song_id_val,
        "songs": None,
        "SFX": None,
        "rateDate": ""
        # showcase removed
    }

    if level_info["objects"] == 65535 and not skip_warnings:
        print(f"[!] Warning: Level {level_id} has 65535 objects — may be higher (GD limit).")

    return level_info

def _resolve_creator_name(level_id: str, user_id: int, account_id: int, raw21: str) -> str:
    """Bevorzugt creators-map aus raw21, danach Account/User mit Cache, zuletzt GDB."""
    # 1) creators-map aus raw21
    if raw21:
        try:
            cmap = _parse_creators_map_from_levels21(raw21)
            for k in (account_id, user_id):
                if k and k in cmap and cmap[k]:
                    stats["creator_from_21"] += 1
                    return cmap[k]
        except Exception:
            pass
    # 2) AccountID / UserID mit Memoization
    if account_id:
        if account_id not in account_name_cache:
            account_name_cache[account_id] = _fetch_username_by_account_id(account_id) or ""
        if account_name_cache[account_id]:
            stats["creator_from_account"] += 1
            return account_name_cache[account_id]
    if user_id:
        if user_id not in user_name_cache:
            user_name_cache[user_id] = _fetch_username_by_user_id(user_id) or ""
        if user_name_cache[user_id]:
            stats["creator_from_user"] += 1
            return user_name_cache[user_id]
    # 3) Fallback GDBrowser
    name = _fallback_creator_from_gdbrowser(level_id)
    if name:
        stats["creator_from_gdb"] += 1
    else:
        stats["creator_missing"] += 1
    return name

def get_level_data_gd(level_id: str, number: int, skip_warnings: bool = False):
    """Fetch directly from Boomlings endpoints and map to our output schema."""
    try:
        kv = _fetch_download(int(level_id))
    except Exception as e:
        print(f"[!] Boomlings fetch failed for level {level_id}: {e}")
        return None

    # Core fields from downloadGJLevel22.php
    name = kv.get("2", "") or ""
    user_id     = _to_int(kv.get("6", "0"))
    account_id  = _to_int(kv.get("49", "0"))  # present on many levels

    demon_flag      = kv.get("17", "0") == "1"
    stars           = _to_int(kv.get("18", "0"))
    feature_score   = _to_int(kv.get("19", "0"))
    two_player      = kv.get("31", "0") == "1"
    custom_song_id  = _to_int(kv.get("35", "0"))
    coins           = _to_int(kv.get("37", "0"))
    epic_code       = _to_int(kv.get("42", "0"))
    demon_code      = _to_int(kv.get("43", "0"))
    objects         = _to_int(kv.get("45", "0"))
    editorA         = _to_int(kv.get("46", "0"))
    editorB         = _to_int(kv.get("47", "0"))
    official_song_i = _to_int(kv.get("12", "0"))
    k52_raw         = kv.get("k52", "") or kv.get("52", "")
    k53_raw         = kv.get("k53", "") or kv.get("53", "")
    k57_frames      = _to_int(kv.get("57", kv.get("k57", "0")), 0)

    level_id_int = _to_int(kv.get("1", str(level_id)))

    # Einmaliges Laden von getGJLevels21 (Cache-Hit bevorzugt)
    raw21 = levels21_cache.get(level_id)
    if raw21 is None:
        try:
            raw21 = _fetch_levels21_raw(int(level_id))
        except Exception:
            raw21 = ""
        levels21_cache[level_id] = raw21

    # Difficulty text
    if demon_flag or demon_code in (0, 3, 4, 5, 6):
        difficulty_text = f"{_demon_name(demon_code)} Demon"
    else:
        difficulty_text = _non_demon_diff(_to_int(kv.get("9", "0")))

    # Rating text
    if epic_code == 0:
        rating = "Featured" if feature_score >= 1 else ("Rated" if stars > 0 else "")
    else:
        rating = {1: "Epic", 2: "Legendary", 3: "Mythic"}.get(epic_code, "")

    # Resolve creator (nutzt raw21 bevorzugt)
    creator_name = _resolve_creator_name(level_id, user_id, account_id, raw21)

    # Song fields
    official_song_flag = (official_song_i != 0)
    song_id_out = "OFFICIAL" if official_song_flag else (custom_song_id if custom_song_id > 0 else "")
    primary_song = ""
    artist = ""

    # Custom/NONG: erst aus raw21, dann Song-API (mit Cache)
    if not official_song_flag and custom_song_id:
        # 1) Aus raw21 ziehen
        song_meta = _extract_song_meta_from_levels21(raw21, custom_song_id)
        if song_meta:
            primary_song = song_meta.get("name", "") or ""
            artist = song_meta.get("artist", "") or ""
            if primary_song and artist:
                stats["song_from_21"] += 1
        # 2) Fallback: getGJSongInfo (mit Cache)
        if (not primary_song or not artist):
            sm = song_cache.get(custom_song_id)
            if sm is None:
                sm = _fetch_song(custom_song_id)
                song_cache[custom_song_id] = sm
            if sm:
                if sm.get("name"):
                    primary_song = primary_song or sm.get("name", "") or ""
                if sm.get("artist"):
                    artist = artist or sm.get("artist", "") or ""
            if primary_song and artist:
                stats["song_from_api"] += 1
        if not primary_song or not artist:
            stats["song_missing"] += 1

    # estimatedTime in **seconds**
    estimated_seconds = int(round(k57_frames / 240.0)) if k57_frames > 0 else None
    estimated_time_seconds = estimated_seconds if isinstance(estimated_seconds, int) and estimated_seconds > 0 else None

    # songs (k52) + SFX (k53) counts
    songs_count = 0
    sfx_count = 0
    if k52_raw:
        songs_count = len([x.strip() for x in k52_raw.split(",") if x.strip()])
    if k53_raw:
        first_part = k53_raw.split("#", 1)[0]
        sfx_count = len([x.strip() for x in first_part.split(",") if x.strip()])

    level_info = {
        "number": number,
        "level": name,
        "creator": creator_name or "",
        "ID": level_id_int,
        "difficulty": difficulty_text,
        "rating": rating,
        "userCoins": coins,
        "estimatedTime": estimated_time_seconds,  # seconds or None
        "objects": objects,
        "checkpoints": None,
        "twop": two_player,
        "primarySong": primary_song,
        "artist": artist,
        "songID": song_id_out,   # "" means do not overwrite on merge
        "songs": songs_count if songs_count > 0 else None,
        "SFX": sfx_count if sfx_count > 0 else None,
        "rateDate": ""
        # showcase removed
    }

    if level_info["objects"] == 65535 and not skip_warnings:
        print(f"[!] Warning: Level {level_id} has 65535 objects — may be higher (GD limit).")

    return level_info

# Unified facade
def get_level_data(level_id: str, number: int, source: str, skip_warnings: bool = False):
    if source == "gd":
        return get_level_data_gd(level_id, number, skip_warnings=skip_warnings)
    else:
        return get_level_data_gdbrowser(level_id, number, skip_warnings=skip_warnings)

# ===================== Merge helpers =====================
def load_existing_data(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def entries_differ(existing, new):
    for key in new:
        if key == "number":
            continue
        if key == "objects":
            old_val = existing.get("objects", 0)
            new_val = new.get("objects", 0)
            if new_val == 0 or (new_val == 65535 and old_val > 65535):
                continue
            if old_val != new_val:
                return True
        elif existing.get("songID") == "NONG" and key in ["primarySong", "artist", "songID"]:
            continue
        elif existing.get("songID") == "UNKNOWN":
            if key == "songID":
                continue
            elif key in ["primarySong", "artist"]:
                if existing.get(key) != "":
                    return True
                continue
        else:
            old_val = existing.get(key)
            new_val = new.get(key)
            if new_val in [None, ""] and old_val not in [None, ""]:
                continue
            if old_val != new_val:
                return True
    return False

def merge_entries(existing, new):
    merged = existing.copy()
    for key, value in new.items():
        if key not in existing:
            merged[key] = value
        elif key == "objects":
            old_val = existing.get("objects", 0)
            if value == 0 or (value == 65535 and old_val > 65535):
                continue
            merged[key] = value
        elif existing.get("songID") == "NONG" and key in ["primarySong", "artist", "songID"]:
            continue
        elif existing.get("songID") == "UNKNOWN":
            if key == "songID":
                continue
            elif key in ["primarySong", "artist"]:
                merged[key] = ""
        elif value is None or value == "":
            continue
        else:
            merged[key] = value

    # strip deprecated fields on merge
    merged.pop("showcase", None)
    return merged

def sanitize_entry(entry: dict) -> dict:
    """Remove deprecated/unused fields before writing to result."""
    if entry is None:
        return entry
    entry.pop("showcase", None)
    return entry

# ===================== Selection parsing =====================
def _parse_positions_spec(spec: str, total: int) -> list[int]:
    """Parse a comma-separated list of 1-based positions and ranges (e.g., '1-5,10,20-25')."""
    indices: set[int] = set()
    tokens = [t.strip() for t in spec.split(",") if t.strip()]
    for tok in tokens:
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", tok)
        if m:
            a = int(m.group(1))
            b = int(m.group(2))
            if a > b:
                a, b = b, a
            a = max(1, min(a, total))
            b = max(1, min(b, total))
            for i in range(a, b + 1):
                indices.add(i)
        elif tok.isdigit():
            i = int(tok)
            if 1 <= i <= total:
                indices.add(i)
    return sorted(indices)

def _parse_id_spec(spec: str, all_ids: list[str]) -> list[str]:
    """Parse 'id: ...' list; supports single IDs and numeric ranges. Keeps order as in all_ids."""
    id_set: set[str] = set()
    body = spec.split(":", 1)[1] if ":" in spec else spec
    tokens = [t.strip() for t in body.split(",") if t.strip()]
    for tok in tokens:
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", tok)
        if m:
            a = int(m.group(1)); b = int(m.group(2))
            if a > b:
                a, b = b, a
            # generate numeric strings in range, then filter by membership
            for x in range(a, b + 1):
                s = str(x)
                if s in all_ids:
                    id_set.add(s)
        elif tok.isdigit():
            if tok in all_ids:
                id_set.add(tok)
    # preserve original order from file
    return [lvl_id for lvl_id in all_ids if lvl_id in id_set]

def select_level_ids(selection: str, all_ids: list[str]) -> list[str]:
    """Return ordered list of selected level IDs, based on selection string."""
    sel = (selection or "").strip()
    if not sel:
        return all_ids[:]  # all

    low = sel.lower()
    if low.startswith("last "):
        n_str = low.split(" ", 1)[1].strip()
        if n_str.isdigit():
            n = int(n_str)
            return all_ids[-n:] if n > 0 else []
        # fall through to positions parsing if malformed

    if low.startswith("id:"):
        ids = _parse_id_spec(sel, all_ids)
        return ids

    # default: treat as positions/ranges by "number" (line index in pemon_ids.txt)
    total = len(all_ids)
    pos_list = _parse_positions_spec(sel, total)
    if not pos_list:
        return all_ids[:]
    # map 1-based positions to IDs
    return [all_ids[i - 1] for i in pos_list]

# ===================== Main =====================
def main():
    # Source selection
    print("Quelle wählen:")
    print("  [1] GDBrowser (einfach, JSON-API)")
    print("  [2] GD-Server (Boomlings, robust, rate-limited)")
    choice = input("Deine Wahl (1/2, Enter=1): ").strip()
    source = "gd" if choice == "2" else "gdbrowser"

    # Read all IDs from file
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        all_ids = [line.strip() for line in f if line.strip().isdigit()]

    # Optional selection
    print("\n🔢 Welche Levels sollen verarbeitet werden?")
    print("   Beispiele (Positionen = 'number' Spalte):  1-30   |   600-650   |   1,5,9-12,100")
    print("   Letzte N:  last 50")
    print("   IDs direkt:  id: 12345, 67890, 100000-100100")
    selection_input = input("   Eingabe (leer = alle): ").strip()

    # Compute selection (ordered)
    level_ids = select_level_ids(selection_input, all_ids)

    # Build number mapping (the 'number' is the line index in the full file)
    id_to_line = {level_id: idx + 1 for idx, level_id in enumerate(all_ids)}

    existing_data = load_existing_data(OUTPUT_FILE)
    existing_dict = {str(entry.get("ID")): entry for entry in existing_data if isinstance(entry, dict)}

    added_count = 0
    updated_count = 0
    skipped_count = 0

    print(f"\n📦 Verarbeite {len(level_ids)} von {len(all_ids)} Levels über '{'GDBrowser' if source=='gdbrowser' else 'GD-Server'}'...\n")

    result_data_dict: dict[str, dict] = {}
    processed_ids: set[str] = set()

    for level_id in level_ids:
        if level_id in processed_ids:
            continue
        processed_ids.add(level_id)

        number = id_to_line.get(level_id, 0)
        old_entry = existing_dict.get(level_id)
        new_entry = get_level_data(level_id, number, source, skip_warnings=bool(old_entry))

        if not new_entry:
            if old_entry:
                print(f"[~] Skipped level {level_id}")
                entry = old_entry.copy()
                entry["number"] = number
                entry = sanitize_entry(entry)
                result_data_dict[level_id] = entry
                skipped_count += 1
            continue

        if not old_entry:
            print(f"[+] Added level {level_id}: {new_entry['level']} by {new_entry['creator']}")
            entry = sanitize_entry(new_entry)
            result_data_dict[level_id] = entry
            added_count += 1
        elif entries_differ(old_entry, new_entry):
            print(f"[~] Updated level {level_id}: {new_entry['level']} (changes detected)")
            merged = merge_entries(old_entry, new_entry)
            merged["number"] = number
            merged = sanitize_entry(merged)
            result_data_dict[level_id] = merged
            updated_count += 1
        else:
            entry = old_entry.copy()
            entry["number"] = number
            entry = sanitize_entry(entry)
            result_data_dict[level_id] = entry
            skipped_count += 1

    # Keep entries not touched in this run (also sanitize)
    for old_id, old_entry in existing_dict.items():
        if old_id not in processed_ids:
            entry = sanitize_entry(old_entry.copy())
            result_data_dict[old_id] = entry

    result_data = sorted(result_data_dict.values(), key=lambda x: x.get("number", 0))
    save_data(OUTPUT_FILE, result_data)

    print("\n===== Summary =====")
    print(f"Total levels processed: {len(level_ids)}")
    print(f"🆕 Added:   {added_count}")
    print(f"🔄 Updated: {updated_count}")
    print(f"✅ Skipped: {skipped_count}")
    print(f"📄 Output saved to: {OUTPUT_FILE}")
    # Telemetry
    print("\n----- Telemetry -----")
    print(f"Creator via levels21:   {stats['creator_from_21']}")
    print(f"Creator via accountID:  {stats['creator_from_account']}")
    print(f"Creator via userID:     {stats['creator_from_user']}")
    print(f"Creator via GDBrowser:  {stats['creator_from_gdb']}")
    print(f"Creator missing:        {stats['creator_missing']}")
    print(f"Song via levels21:      {stats['song_from_21']}")
    print(f"Song via getGJSongInfo: {stats['song_from_api']}")
    print(f"Song missing fields:    {stats['song_missing']}")

if __name__ == "__main__":
    main()
