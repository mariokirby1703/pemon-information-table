import json
import os
import random
import re
import time
from collections import deque
from threading import Lock

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, ReadTimeout
from urllib3.exceptions import ProtocolError

INPUT_FILE = "demon_ids.txt"
OUTPUT_FILE = "demons.json"

BASE = "http://www.boomlings.com/database"
SECRET = "Wmfd2893gb7"
HEADERS = {
    "User-Agent": "",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "*/*",
    "Connection": "close",
}

LENGTH_MAP = {
    0: "Tiny",
    1: "Short",
    2: "Medium",
    3: "Long",
    4: "XL",
    5: "Platformer",
}

NON_DEMON_DIFF = {
    10: "Easy",
    20: "Normal",
    30: "Hard",
    40: "Harder",
    50: "Insane",
}

DEMON_NAME = {
    3: "Easy",
    4: "Medium",
    0: "Hard",
    5: "Insane",
    6: "Extreme",
}

# Official song index from GD-Server key 12 (0-based) -> (song name, artist)
OFFICIAL_SONGS = {
    0: ("Stereo Madness", "ForeverBound"),
    1: ("Back on Track", "DJVI"),
    2: ("Polargeist", "Step"),
    3: ("Dry Out", "DJVI"),
    4: ("Base After Base", "DJVI"),
    5: ("Cant Let Go", "DJVI"),
    6: ("Jumper", "Waterflame"),
    7: ("Time Machine", "Waterflame"),
    8: ("Cycles", "DJVI"),
    9: ("xStep", "DJVI"),
    10: ("Clutterfunk", "Waterflame"),
    11: ("Theory of Everything", "DJ-Nate"),
    12: ("Electroman Adventures", "Waterflame"),
    13: ("Clubstep", "DJ-Nate"),
    14: ("Electrodynamix", "DJ-Nate"),
    15: ("Hexagon Force", "Waterflame"),
    16: ("Blast Processing", "Waterflame"),
    17: ("Theory of Everything 2", "DJ-Nate"),
    18: ("Geometrical Dominator", "Waterflame"),
    19: ("Deadlocked", "F-777"),
    20: ("Fingerdash", "MDK"),
    21: ("Dash", "MDK"),
}

MIN_INTERVAL = float(os.getenv("RL_MIN_INTERVAL", "3"))
WINDOWS = [(10, 6), (60, 30)]
RETRY_MAX = int(os.getenv("RL_RETRY_MAX", "5"))
BACKOFF_BASE = float(os.getenv("RL_BACKOFF_BASE", "1.5"))
BACKOFF_CAP = float(os.getenv("RL_BACKOFF_CAP", "30"))
JITTER_MIN = float(os.getenv("RL_JITTER_MIN", "0.05"))
JITTER_MAX = float(os.getenv("RL_JITTER_MAX", "0.15"))
POOL_CONNECTIONS = int(os.getenv("RL_POOL_CONNECTIONS", "8"))
POOL_MAXSIZE = int(os.getenv("RL_POOL_MAXSIZE", "8"))

_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=POOL_CONNECTIONS, pool_maxsize=POOL_MAXSIZE, max_retries=0)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

levels21_cache: dict[str, str] = {}
account_name_cache: dict[int, str] = {}
user_name_cache: dict[int, str] = {}
song_cache: dict[int, dict] = {}
player_name_cache: dict[int, str] = {}


class RateLimiter:
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


def _respect_retry_after(resp) -> float:
    retry_after = resp.headers.get("Retry-After")
    if not retry_after:
        return 0.0
    try:
        return max(0.0, float(retry_after))
    except Exception:
        return 30.0


def _post(url, data, timeout=30):
    attempt = 0
    while True:
        attempt += 1
        rate_limiter.wait()
        time.sleep(random.uniform(JITTER_MIN, JITTER_MAX))
        try:
            resp = _session.post(url, data=data, headers=HEADERS, timeout=timeout)
        except (ConnectionError, ProtocolError, ReadTimeout, ChunkedEncodingError):
            if attempt >= RETRY_MAX:
                raise
            backoff = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            time.sleep(backoff + random.uniform(JITTER_MIN, JITTER_MAX))
            continue

        status = resp.status_code
        if 200 <= status < 400:
            return resp
        if status == 429:
            if attempt >= RETRY_MAX:
                return resp
            wait = _respect_retry_after(resp) or min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            time.sleep(wait + random.uniform(JITTER_MIN, JITTER_MAX))
            continue
        if 500 <= status < 600:
            if attempt >= RETRY_MAX:
                return resp
            backoff = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            time.sleep(backoff + random.uniform(JITTER_MIN, JITTER_MAX))
            continue
        if status == 403:
            if attempt >= min(RETRY_MAX, 2):
                return resp
            time.sleep(60.0 + random.uniform(0.5, 1.5))
            continue
        return resp


def _kv_block(text: str) -> dict:
    if "#" in text:
        text = text.split("#", 1)[0]
    parts = text.strip().split(":")
    out = {}
    for i in range(0, len(parts) - 1, 2):
        key, value = parts[i], parts[i + 1]
        if key:
            out.setdefault(key, value)
    return out


def _kv_tilde(text: str) -> dict:
    parts = text.strip().split("~|~")
    out = {}
    for i in range(0, len(parts) - 1, 2):
        key, value = parts[i], parts[i + 1]
        if key:
            out[key] = value
    return out


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _fetch_download(level_id: int) -> dict:
    url = f"{BASE}/downloadGJLevel22.php"
    response = _post(url, data={"levelID": str(level_id), "secret": SECRET}, timeout=30)
    if response.status_code == 403:
        raise RuntimeError("403/Cloudflare (download).")
    response.raise_for_status()
    text = response.text.strip()
    if not text or text == "-1":
        raise RuntimeError(f"Level {level_id} not found / error: {text!r}")
    return _kv_block(text)


def _fetch_levels21_raw(level_id: int) -> str:
    url = f"{BASE}/getGJLevels21.php"
    response = _post(url, data={"levelID": str(level_id), "secret": SECRET}, timeout=30)
    if response.status_code == 403:
        raise RuntimeError("403/Cloudflare (getGJLevels21).")
    response.raise_for_status()
    return response.text.strip()


def _fetch_levels21_search_raw(level_name: str) -> str:
    url = f"{BASE}/getGJLevels21.php"
    response = _post(url, data={"type": "0", "str": level_name, "secret": SECRET}, timeout=30)
    if response.status_code == 403:
        raise RuntimeError("403/Cloudflare (getGJLevels21 search).")
    response.raise_for_status()
    return response.text.strip()


def _fetch_username_by_account_id(account_id: int) -> str:
    if not account_id:
        return ""
    url = f"{BASE}/getGJUserInfo20.php"
    response = _post(url, data={"targetAccountID": str(account_id), "secret": SECRET}, timeout=30)
    if response.status_code != 200:
        return ""
    text = response.text.strip()
    if not text or text == "-1":
        return ""
    kv = _kv_block(text)
    return kv.get("2", "") or ""


def _fetch_username_by_user_id(user_id: int) -> str:
    if not user_id:
        return ""
    url = f"{BASE}/getGJUserInfo20.php"
    response = _post(url, data={"targetUserID": str(user_id), "secret": SECRET}, timeout=30)
    if response.status_code != 200:
        return ""
    text = response.text.strip()
    if not text or text == "-1":
        return ""
    kv = _kv_block(text)
    return kv.get("2", "") or ""


def _fetch_song(song_id: int) -> dict:
    if not song_id:
        return {}
    url = f"{BASE}/getGJSongInfo.php"
    response = _post(url, data={"songID": str(song_id), "secret": SECRET}, timeout=30)
    if response.status_code != 200:
        return {}
    text = response.text.strip()
    if not text or text == "-1":
        return {}
    kv = _kv_tilde(text)
    return {
        "id": _to_int(kv.get("1", "0")),
        "name": kv.get("2", ""),
        "artist": kv.get("4", ""),
    }


def _fetch_username_by_player_id(player_id: int) -> str:
    if not player_id:
        return ""
    url = f"{BASE}/getGJUsers20.php"
    response = _post(url, data={"str": str(player_id), "secret": SECRET}, timeout=30)
    if response.status_code != 200:
        return ""
    text = response.text.strip()
    if not text or text == "-1":
        return ""
    for chunk in text.split("|"):
        if not chunk:
            continue
        kv = _kv_block(chunk)
        if kv.get("2", "").isdigit() and int(kv.get("2", "0")) == player_id:
            return kv.get("1", "") or ""
    return ""


def _parse_creators_map_from_levels21(raw: str) -> dict[int, str]:
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


def _extract_song_meta_from_levels21(raw21: str, custom_song_id: int) -> dict:
    if not raw21 or not custom_song_id:
        return {}
    try:
        parts = raw21.split("#")
        if len(parts) < 3:
            return {}
        songs = parts[2]
        records = songs.split(":~1~|~")
        if records:
            if not records[0].startswith("1~|~"):
                idx = records[0].find("1~|~")
                if idx != -1:
                    records[0] = records[0][idx:]
            if records[0] and not records[0].startswith("1~|~"):
                records[0] = "1~|~" + records[0]
        for record in records:
            if not record.strip():
                continue
            fields = record.split("~|~")
            data = {}
            for i in range(0, len(fields) - 1, 2):
                data[fields[i]] = fields[i + 1]
            song_id = _to_int(data.get("1", "0"))
            if song_id == custom_song_id:
                return {"name": data.get("2", ""), "artist": data.get("4", "")}
    except Exception:
        return {}
    return {}


def _resolve_creator_name(user_id: int, account_id: int, raw21: str, level_name: str) -> str:
    if raw21:
        try:
            creators_map = _parse_creators_map_from_levels21(raw21)
            for candidate in (account_id, user_id):
                if candidate and candidate in creators_map and creators_map[candidate]:
                    return creators_map[candidate]
        except Exception:
            pass

    if account_id:
        if account_id not in account_name_cache:
            account_name_cache[account_id] = _fetch_username_by_account_id(account_id) or ""
        if account_name_cache[account_id]:
            return account_name_cache[account_id]

    if user_id:
        if user_id not in player_name_cache:
            player_name_cache[user_id] = _fetch_username_by_player_id(user_id) or ""
        if player_name_cache[user_id]:
            return player_name_cache[user_id]
        if user_id not in user_name_cache:
            user_name_cache[user_id] = _fetch_username_by_user_id(user_id) or ""
        if user_name_cache[user_id]:
            return user_name_cache[user_id]

    if level_name:
        try:
            raw_search = _fetch_levels21_search_raw(level_name)
            search_map = _parse_creators_map_from_levels21(raw_search)
            for candidate in (account_id, user_id):
                if candidate and candidate in search_map and search_map[candidate]:
                    return search_map[candidate]
        except Exception:
            pass

    return ""


def _difficulty_text(kv: dict) -> str:
    demon_flag = kv.get("17", "0") == "1"
    demon_code = _to_int(kv.get("43", "0"))
    if demon_flag or demon_code in (0, 3, 4, 5, 6):
        return f"{DEMON_NAME.get(demon_code, 'Unknown')} Demon"
    return NON_DEMON_DIFF.get(_to_int(kv.get("9", "0")), "N/A")


def _rating_text(kv: dict) -> str:
    stars = _to_int(kv.get("18", "0"))
    feature_score = _to_int(kv.get("19", "0"))
    epic_code = _to_int(kv.get("42", "0"))
    if epic_code == 0:
        return "Featured" if feature_score >= 1 else ("Rated" if stars > 0 else "")
    return {1: "Epic", 2: "Legendary", 3: "Mythic"}.get(epic_code, "")


def get_level_data(level_id, number, skip_warnings=False):
    try:
        kv = _fetch_download(int(level_id))
    except Exception as exc:
        print(f"[!] GD-Server fetch failed for level {level_id}: {exc}")
        return None

    raw21 = levels21_cache.get(str(level_id))
    if raw21 is None:
        try:
            raw21 = _fetch_levels21_raw(int(level_id))
        except Exception:
            raw21 = ""
        levels21_cache[str(level_id)] = raw21

    user_id = _to_int(kv.get("6", "0"))
    account_id = _to_int(kv.get("49", kv.get("41", "0")))
    level_name = kv.get("2", "") or ""
    creator_name = _resolve_creator_name(user_id, account_id, raw21, level_name) or "-"

    official_song_idx = _to_int(kv.get("12", "0"))
    custom_song_id = _to_int(kv.get("35", "0"))
    song_id_out = "OFFICIAL" if official_song_idx != 0 else (custom_song_id if custom_song_id > 0 else "")
    primary_song = ""
    artist = ""

    if official_song_idx > 0:
        primary_song, artist = OFFICIAL_SONGS.get(official_song_idx, ("", ""))
    elif custom_song_id > 0:
        song_meta = _extract_song_meta_from_levels21(raw21, custom_song_id)
        if song_meta:
            primary_song = song_meta.get("name", "") or ""
            artist = song_meta.get("artist", "") or ""
        if not primary_song or not artist:
            cached_song = song_cache.get(custom_song_id)
            if cached_song is None:
                cached_song = _fetch_song(custom_song_id)
                song_cache[custom_song_id] = cached_song
            if cached_song:
                primary_song = primary_song or cached_song.get("name", "") or ""
                artist = artist or cached_song.get("artist", "") or ""

    level_info = {
        "number": number,
        "level": level_name,
        "creator": creator_name,
        "ID": _to_int(kv.get("1", str(level_id))),
        "difficulty": _difficulty_text(kv),
        "rating": _rating_text(kv),
        "userCoins": _to_int(kv.get("37", "0")),
        "length": LENGTH_MAP.get(_to_int(kv.get("15", "0")), ""),
        "objects": _to_int(kv.get("45", "0")),
        "twop": kv.get("31", "0") == "1",
        "primarySong": primary_song,
        "artist": artist,
        "songID": song_id_out,
    }

    if level_info["creator"] == "-" and not skip_warnings:
        print(f"[i] Info: Level {level_id} creator unresolved on GD-Server.")

    if level_info["objects"] == 0 and not skip_warnings:
        print(f"[i] Info: Level {level_id} objects=0 on GD-Server response.")

    if level_info["objects"] == 65535 and not skip_warnings:
        print(f"[!] Warning: Level {level_id} has 65535 objects - may be higher (GD limit).")

    return level_info


def load_existing_data(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_data(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_partial_output(existing_dict, result_data_dict, processed_ids):
    snapshot_dict = dict(result_data_dict)
    for old_id, old_entry in existing_dict.items():
        if old_id not in processed_ids:
            snapshot_dict[old_id] = old_entry
    result_data = sorted(snapshot_dict.values(), key=lambda x: x.get("number", 0))
    save_data(OUTPUT_FILE, result_data)


def _parse_positions_spec(spec: str, total: int) -> list[int]:
    indices: set[int] = set()
    tokens = [t.strip() for t in spec.split(",") if t.strip()]
    for token in tokens:
        match = re.match(r"^(\d+)\s*-\s*(\d+)$", token)
        if match:
            a = int(match.group(1))
            b = int(match.group(2))
            if a > b:
                a, b = b, a
            a = max(1, min(a, total))
            b = max(1, min(b, total))
            for i in range(a, b + 1):
                indices.add(i)
        elif token.isdigit():
            i = int(token)
            if 1 <= i <= total:
                indices.add(i)
    return sorted(indices)


def _parse_id_spec(spec: str, all_ids: list[str]) -> list[str]:
    id_set: set[str] = set()
    body = spec.split(":", 1)[1] if ":" in spec else spec
    tokens = [t.strip() for t in body.split(",") if t.strip()]
    for token in tokens:
        match = re.match(r"^(\d+)\s*-\s*(\d+)$", token)
        if match:
            a = int(match.group(1))
            b = int(match.group(2))
            if a > b:
                a, b = b, a
            for x in range(a, b + 1):
                s = str(x)
                if s in all_ids:
                    id_set.add(s)
        elif token.isdigit() and token in all_ids:
            id_set.add(token)
    return [lvl_id for lvl_id in all_ids if lvl_id in id_set]


def select_level_ids(selection: str, all_ids: list[str]) -> list[str]:
    sel = (selection or "").strip()
    if not sel:
        return all_ids[:]

    low = sel.lower()

    # Backward-compatible: plain number means "last N"
    if sel.isdigit():
        n = int(sel)
        return all_ids[-n:] if n > 0 else []

    if low.startswith("last "):
        n_str = low.split(" ", 1)[1].strip()
        if n_str.isdigit():
            n = int(n_str)
            return all_ids[-n:] if n > 0 else []

    if low.startswith("id:"):
        return _parse_id_spec(sel, all_ids)

    total = len(all_ids)
    pos_list = _parse_positions_spec(sel, total)
    if not pos_list:
        return all_ids[:]
    return [all_ids[i - 1] for i in pos_list]


def entries_differ(existing, new):
    for key in new:
        if key == "number":
            continue

        if key == "creator":
            new_creator = new.get("creator")
            old_creator = existing.get("creator")
            if new_creator == "-" and old_creator not in [None, "", "-"]:
                continue
            if old_creator != new_creator:
                return True
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

        elif key == "creator":
            old_creator = existing.get("creator")
            if value == "-" and old_creator not in [None, "", "-"]:
                continue
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


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        all_ids = [line.strip() for line in f if line.strip().isdigit()]

    id_to_line = {level_id: idx + 1 for idx, level_id in enumerate(all_ids)}

    print("Which levels should be processed?")
    print("  Examples by line-number: 1-500   |   501-1000   |   1,5,9-12")
    print("  Last N: 500  or  last 500")
    print("  Direct IDs: id: 12556,13519")
    selection_input = input("Selection (empty = all): ").strip()
    level_ids = select_level_ids(selection_input, all_ids)

    autosave_input = input("Auto-save every N processed levels? (default 50, 0 = off): ").strip()
    if autosave_input == "":
        autosave_every = 50
    elif autosave_input.isdigit():
        autosave_every = int(autosave_input)
    else:
        autosave_every = 50

    existing_data = load_existing_data(OUTPUT_FILE)
    existing_dict = {str(entry["ID"]): entry for entry in existing_data}

    added_count = 0
    updated_count = 0
    skipped_count = 0

    result_data_dict = {}
    processed_ids = set()
    interrupted = False

    print(f"Processing {len(level_ids)} of {len(all_ids)} levels via GD-Server...\n")

    try:
        for level_id in level_ids:
            if level_id in processed_ids:
                continue
            processed_ids.add(level_id)

            number = id_to_line[level_id]
            old_entry = existing_dict.get(level_id)
            new_entry = get_level_data(level_id, number, skip_warnings=bool(old_entry))

            if not new_entry:
                if old_entry:
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

            if autosave_every > 0 and len(processed_ids) % autosave_every == 0:
                save_partial_output(existing_dict, result_data_dict, processed_ids)
                print(f"[i] Auto-saved progress at {len(processed_ids)} processed levels.")
    except KeyboardInterrupt:
        interrupted = True
        print("\n[!] Interrupted by user (Ctrl+C). Saving partial progress...")
    finally:
        save_partial_output(existing_dict, result_data_dict, processed_ids)

    print("\n===== Summary =====")
    print(f"Total levels targeted:  {len(level_ids)}")
    print(f"Total levels processed: {len(processed_ids)}")
    print(f"Added:   {added_count}")
    print(f"Updated: {updated_count}")
    print(f"Skipped: {skipped_count}")
    if interrupted:
        print("Run status: interrupted, partial progress saved.")
    else:
        print("Run status: completed.")
    print(f"Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
