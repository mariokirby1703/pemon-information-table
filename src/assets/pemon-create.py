#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pemons builder: fetch Geometry Dash level metadata either via GDBrowser
or directly from the official GD (Boomlings) endpoints.

- Prompts at startup to choose the data source.
- Respects an optional "limit" of how many last IDs from INPUT_FILE to process.
- Merges into OUTPUT_FILE with conservative rules (objects cap, songID states).
- Robust rate limiting & retry/backoff for Boomlings.

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

# ===================== Rate Limiter (6 req/min) + robust POST =====================
MIN_INTERVAL = float(os.getenv("RL_MIN_INTERVAL", "10.5"))  # ~6/min
WINDOWS = [(60, 6)]  # 6 per 60s

RETRY_MAX = int(os.getenv("RL_RETRY_MAX", "5"))
BACKOFF_BASE = float(os.getenv("RL_BACKOFF_BASE", "1.5"))
BACKOFF_CAP = float(os.getenv("RL_BACKOFF_CAP", "30"))
JITTER_MIN = float(os.getenv("RL_JITTER_MIN", "0.2"))
JITTER_MAX = float(os.getenv("RL_JITTER_MAX", "0.8"))

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

def _parse_levels21_maps(raw: str):
    """
    returns:
      creators_by_playerid: { playerID:int -> username:str }
      songs_by_id:         { songID:int -> {name, artist, size, url} }
    """
    creators_by_playerid = {}
    songs_by_id = {}
    parts = raw.split("#")

    # creators map
    if len(parts) >= 2:
        creators = parts[1]
        for chunk in creators.split("|"):
            if not chunk:
                continue
            cols = chunk.split(":")
            if len(cols) >= 2 and cols[0].isdigit():
                creators_by_playerid[int(cols[0])] = cols[1]

    # songs map
    if len(parts) >= 3:
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
                k = fields[i].strip()
                v = fields[i + 1]
                d[k] = v
            sid = _to_int(d.get("1", "0"))
            if sid:
                songs_by_id[sid] = {
                    "name": d.get("2", ""),
                    "artist": d.get("4", ""),
                    "size": d.get("5", ""),
                    "url": d.get("10", "-"),
                }
    return creators_by_playerid, songs_by_id

def _fetch_username_fallback_by_userid(player_id: int) -> str:
    """Fallback: getGJUserInfo20.php (sometimes targetUserID or targetAccountID works)."""
    url = f"{BASE}/getGJUserInfo20.php"
    for field in ("targetUserID", "targetAccountID"):
        r = _post(url, data={field: str(player_id), "secret": SECRET}, headers=HEADERS, timeout=30)
        if r.status_code == 200 and r.text.strip() and r.text.strip() != "-1":
            kv = _kv_block(r.text.strip())
            name = kv.get("2", "")
            if name:
                return name
    return ""

def _fetch_song(song_id: int) -> dict:
    if not song_id:
        return {}
    url = f"{BASE}/getGJSongInfo.php"
    r = _post(url, data={"songID": str(song_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code != 200 or r.text.strip() == "-1":
        return {}
    kv = _kv_block(r.text.strip())
    return {
        "id": _to_int(kv.get("1", "0")),
        "name": kv.get("2", ""),
        "artist": kv.get("4", ""),
        "size": kv.get("5", ""),
        "url": kv.get("10", "-"),
    }

# ===================== Fetchers =====================
def get_level_data_gdbrowser(level_id: str, number: int, skip_warnings: bool = False):
    """Fetch via GDBrowser JSON API."""
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
        "rateDate": "",
        "showcase": ""
    }

    if level_info["objects"] == 65535 and not skip_warnings:
        print(f"[!] Warning: Level {level_id} has 65535 objects — may be higher (GD limit).")

    return level_info

def get_level_data_gd(level_id: str, number: int, skip_warnings: bool = False):
    """Fetch directly from Boomlings endpoints and map to our output schema."""
    try:
        kv = _fetch_download(int(level_id))
    except Exception as e:
        print(f"[!] Boomlings fetch failed for level {level_id}: {e}")
        return None

    # Core fields from downloadGJLevel22.php
    name = kv.get("2", "") or ""
    player_id = _to_int(kv.get("6", "0"))

    length_code = _to_int(kv.get("15", "0"))
    demon_flag = kv.get("17", "0") == "1"
    stars = _to_int(kv.get("18", "0"))
    feature_score = _to_int(kv.get("19", "0"))
    copied_id = _to_int(kv.get("30", "0"))
    two_player = kv.get("31", "0") == "1"
    custom_song_id = _to_int(kv.get("35", "0"))
    coins = _to_int(kv.get("37", "0"))
    verified_coins = kv.get("38", "0") == "1"
    stars_requested = _to_int(kv.get("39", "0"))
    epic_code = _to_int(kv.get("42", "0"))
    demon_code = _to_int(kv.get("43", "0"))
    objects = _to_int(kv.get("45", "0"))
    level_id_int = _to_int(kv.get("1", str(level_id)))

    # Difficulty text similar to GDBrowser
    if demon_flag or demon_code in (0, 3, 4, 5, 6):
        difficulty_text = f"{_demon_name(demon_code)} Demon"
    else:
        # Non-demon difficulty uses a numeric tier found in another field; fall back to 'N/A'
        difficulty_text = _non_demon_diff(_to_int(kv.get("9", "0")))

    # Rating text (cp-ish)
    if epic_code in (1, 2, 3):
        cp = 2 + epic_code  # Epic->3, Legendary->4, Mythic->5
    elif feature_score > 0:
        cp = 2
    elif stars > 0:
        cp = 1
    else:
        cp = 0
    rating_map = {1: "Rated", 2: "Featured", 3: "Epic", 4: "Legendary", 5: "Mythic"}
    rating = rating_map.get(cp, "")

    # From getGJLevels21 maps
    creator_name = None
    song_meta_from_map = None
    try:
        raw21 = _fetch_levels21_raw(int(level_id))
        creators_map, songs_map = _parse_levels21_maps(raw21)
        if player_id in creators_map:
            creator_name = creators_map[player_id]
        if custom_song_id and custom_song_id in songs_map:
            song_meta_from_map = songs_map[custom_song_id]
    except Exception:
        pass

    # Creator fallback via getGJUserInfo20
    if not creator_name:
        try:
            creator_name = _fetch_username_fallback_by_userid(player_id) or None
        except Exception:
            creator_name = None

    # Song fields
    official_song_flag = (_to_int(kv.get("12", "0")) != 0)

    # songID: never write 0, keep "" instead
    if official_song_flag:
        song_id_out = "OFFICIAL"
    else:
        song_id_out = custom_song_id if custom_song_id > 0 else ""

    primary_song = None
    artist = None

    # Prefer metadata from map (no extra request)
    if song_meta_from_map:
        primary_song = song_meta_from_map.get("name") or None
        artist = song_meta_from_map.get("artist") or None

    # Fallback to getGJSongInfo for custom songs
    if (primary_song is None or artist is None) and (not official_song_flag) and custom_song_id:
        sm = _fetch_song(custom_song_id)
        if sm:
            primary_song = primary_song or (sm.get("name") or None)
            artist = artist or (sm.get("artist") or None)

    level_info = {
        "number": number,
        "level": name,
        "creator": creator_name or "",
        "ID": level_id_int,
        "difficulty": difficulty_text,
        "rating": rating,
        "userCoins": coins,
        "estimatedTime": None,
        "objects": objects,
        "checkpoints": None,
        "twop": two_player,
        "primarySong": (primary_song or ""),
        "artist": (artist or ""),
        "songID": song_id_out,   # "" means do not overwrite on merge
        "songs": None,
        "SFX": None,
        "rateDate": "",
        "showcase": ""
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

def find_entry_by_id(entries, level_id):
    for entry in entries:
        if str(entry.get("ID")) == str(level_id):
            return entry
    return None

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
                # Keep these empty when songID is UNKNOWN
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
    return merged

# ===================== Main =====================
def main():
    # Source selection
    print("Quelle wählen:")
    print("  [1] GDBrowser (einfach, JSON-API)")
    print("  [2] GD-Server (Boomlings, robust, rate-limited)")
    choice = input("Deine Wahl (1/2, Enter=1): ").strip()
    source = "gd" if choice == "2" else "gdbrowser"

    # Optional limit
    limit_input = input("🔢 Wie viele der letzten Level möchtest du verarbeiten? (Leer = alle): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else None

    # Read IDs
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        all_ids = [line.strip() for line in f if line.strip().isdigit()]

    id_to_line = {level_id: idx + 1 for idx, level_id in enumerate(all_ids)}
    level_ids = all_ids[-limit:] if limit else all_ids

    existing_data = load_existing_data(OUTPUT_FILE)
    existing_dict = {str(entry["ID"]): entry for entry in existing_data}

    added_count = 0
    updated_count = 0
    skipped_count = 0

    result_data_dict = {}
    processed_ids = set()

    print(f"📦 Verarbeite {len(level_ids)} von {len(all_ids)} Levels über '{'GDBrowser' if source=='gdbrowser' else 'GD-Server'}'...\n")

    for level_id in level_ids:
        if level_id in processed_ids:
            continue
        processed_ids.add(level_id)

        number = id_to_line[level_id]
        old_entry = existing_dict.get(level_id)
        new_entry = get_level_data(level_id, number, source, skip_warnings=bool(old_entry))

        if not new_entry:
            if old_entry:
                print(f"[~] Skipped level {level_id}")
                result_data_dict[level_id] = old_entry
                skipped_count += 1
            continue

        if not old_entry:
            print(f"[+] Added level {level_id}: {new_entry['level']} by {new_entry['creator']}")
            result_data_dict[level_id] = new_entry
            added_count += 1
        elif entries_differ(old_entry, new_entry):
            print(f"[~] Updated level {level_id}: {new_entry['level']} (changes detected)")
            merged = merge_entries(old_entry, new_entry)
            merged["number"] = number
            result_data_dict[level_id] = merged
            updated_count += 1
        else:
            old_entry["number"] = number
            result_data_dict[level_id] = old_entry
            skipped_count += 1

    # Keep entries not touched in this run
    for old_id, old_entry in existing_dict.items():
        if old_id not in processed_ids:
            result_data_dict[old_id] = old_entry

    result_data = sorted(result_data_dict.values(), key=lambda x: x.get("number", 0))
    save_data(OUTPUT_FILE, result_data)

    print("\n===== Summary =====")
    print(f"Total levels processed: {len(level_ids)}")
    print(f"🆕 Added:   {added_count}")
    print(f"🔄 Updated: {updated_count}")
    print(f"✅ Skipped: {skipped_count}")
    print(f"📄 Output saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
