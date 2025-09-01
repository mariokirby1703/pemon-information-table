import requests
import json
import os
import base64

from collections import deque
import time

INPUT_FILE = "pemon_ids.txt"
OUTPUT_FILE = "pemons.json"

# ===================== Safe, configurable Rate Limiter + resilient _post =====================
import os
import time
import random
from collections import deque
from threading import Lock
import requests
from requests.exceptions import ConnectionError, ReadTimeout, ChunkedEncodingError
from urllib3.exceptions import ProtocolError

# ---- Easy knobs (per ENV überschreibbar) ----
# Mindestabstand zwischen zwei Requests (Sekunden, Anti-Burst)
MIN_INTERVAL = float(os.getenv("RL_MIN_INTERVAL", "5.5"))
# Fenster-Limits (Fenster_in_Sekunden, max_Requests): z.B. 10 pro Minute, 100 pro 10 Min
# ENV-Format: RL_WINDOWS="60:10,600:100"
_windows_env = os.getenv("RL_WINDOWS")
if _windows_env:
    WINDOWS = []
    for part in _windows_env.split(","):
        w, c = part.split(":")
        WINDOWS.append((int(w.strip()), int(c.strip())))
else:
    WINDOWS = [(60, 10), (600, 100)]

# Retry- und Jitter-Settings
RETRY_MAX = int(os.getenv("RL_RETRY_MAX", "5"))           # max. Versuche pro Request
BACKOFF_BASE = float(os.getenv("RL_BACKOFF_BASE", "1.5")) # Basis für Exponential-Backoff
BACKOFF_CAP = float(os.getenv("RL_BACKOFF_CAP", "30"))    # max. Wartezeit zwischen Retries
JITTER_MIN = float(os.getenv("RL_JITTER_MIN", "0.2"))
JITTER_MAX = float(os.getenv("RL_JITTER_MAX", "0.8"))

# Requests-Session Pool (Komfort)
POOL_CONNECTIONS = int(os.getenv("RL_POOL_CONNECTIONS", "8"))
POOL_MAXSIZE    = int(os.getenv("RL_POOL_MAXSIZE", "8"))

class RateLimiter:
    """
    Konfigurierbarer Anti-Burst Limiter:
      - min_interval: Mindestabstand zwischen zwei Calls
      - windows: Liste[(dauer_s, max_calls)] als gleitende Fenster
    Thread-sicher & monotonic (robust gg. Uhrsprünge).
    """
    def __init__(self, min_interval: float, windows: list[tuple[int, int]]):
        self.min_interval = float(min_interval)
        self.windows = sorted([(int(w), int(c)) for w, c in windows], key=lambda x: x[0])
        self._lock = Lock()
        self._last_call = None
        self._buckets = {w: deque() for w, _ in self.windows}

    def _prune(self, now: float):
        for w, dq in self._buckets.items():
            while dq and now - dq[0] >= w:
                dq.popleft()

    def _time_until_allowed(self, now: float) -> float:
        sleep_for = 0.0
        if self._last_call is not None:
            gap = self.min_interval - (now - self._last_call)
            if gap > sleep_for:
                sleep_for = gap
        for w, max_calls in self.windows:
            dq = self._buckets[w]
            if len(dq) >= max_calls:
                wait_w = w - (now - dq[0])
                if wait_w > sleep_for:
                    sleep_for = wait_w
        return max(0.0, sleep_for)

    def wait(self):
        while True:
            now = time.monotonic()
            with self._lock:
                self._prune(now)
                sleep_for = self._time_until_allowed(now)
                if sleep_for <= 0:
                    now = time.monotonic()
                    self._prune(now)
                    for w in self._buckets:
                        self._buckets[w].append(now)
                    self._last_call = now
                    return
            time.sleep(sleep_for)

# Globaler Limiter
rate_limiter = RateLimiter(min_interval=MIN_INTERVAL, windows=WINDOWS)

# Wiederverwendete Session mit moderatem Pooling
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=POOL_CONNECTIONS,
    pool_maxsize=POOL_MAXSIZE,
    max_retries=0  # wir machen unsere eigenen Retries
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

def _respect_retry_after(resp) -> float:
    """Liest Retry-After (Sekunden oder HTTP-Date) und gibt Sekunden zurück (oder 0)."""
    ra = resp.headers.get("Retry-After")
    if not ra:
        return 0.0
    try:
        # Sekunden?
        return max(0.0, float(ra))
    except Exception:
        # Datumsformat – grob 30s fallback
        return 30.0

def _post(url, data, headers, timeout=30):
    """
    Robuster POST:
      - Limiter + kleiner Jitter vor jedem Versuch
      - Retries bei Verbindungsabbrüchen, ReadTimeout, ChunkedEncoding, 429, 5xx
      - 403: einmal lange Pause, dann aufgeben (Cloudflare/Block)
    """
    attempt = 0
    while True:
        attempt += 1

        # Pacing (Limiter) + kleiner Zufallsjitter, um regelmäßige Muster zu brechen
        rate_limiter.wait()
        time.sleep(random.uniform(JITTER_MIN, JITTER_MAX))

        try:
            resp = _session.post(url, data=data, headers=headers, timeout=timeout)
        except (ConnectionError, ProtocolError, ReadTimeout, ChunkedEncodingError):
            if attempt >= RETRY_MAX:
                raise
            sleep_for = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            # leichter Jitter obendrauf
            sleep_for += random.uniform(JITTER_MIN, JITTER_MAX)
            time.sleep(sleep_for)
            continue

        # HTTP-Status prüfen
        status = resp.status_code

        # 2xx/3xx -> fertig
        if 200 <= status < 400:
            return resp

        # 429 Too Many Requests → Retry-After respektieren
        if status == 429:
            if attempt >= RETRY_MAX:
                return resp  # gib zurück, damit der Aufrufer entscheiden kann
            wait_ra = _respect_retry_after(resp)
            wait_ra = wait_ra if wait_ra > 0 else min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            wait_ra += random.uniform(JITTER_MIN, JITTER_MAX)
            time.sleep(wait_ra)
            continue

        # 5xx -> exponentieller Backoff
        if 500 <= status < 600:
            if attempt >= RETRY_MAX:
                return resp
            sleep_for = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
            sleep_for += random.uniform(JITTER_MIN, JITTER_MAX)
            time.sleep(sleep_for)
            continue

        # 403 (oft Cloudflare) -> einmal längere Pause, dann aufgeben
        if status == 403:
            if attempt >= min(RETRY_MAX, 2):
                return resp
            time.sleep(60.0 + random.uniform(0.5, 1.5))
            continue

        # andere Fehler -> ohne Retry zurückgeben
        return resp
# ===================== /Rate Limiter Block =====================

# ===================== Boomlings API =====================
BASE = "http://www.boomlings.com/database"
SECRET = "Wmfd2893gb7"
HEADERS = {
    "User-Agent": "",  # leer lassen – hilft gegen Cloudflare-Blocks
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "*/*",
    "Connection": "close",
}

def _kv_block(text: str) -> dict:
    """Wandelt 'k:v:k:v:...' in dict. Schneidet alles nach dem ersten '#' ab."""
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

def _length_name(code: int) -> str:
    # 0 Tiny, 1 Short, 2 Medium, 3 Long, 4 XL, 5 Platformer
    return {0: "Tiny", 1: "Short", 2: "Medium", 3: "Long", 4: "XL", 5: "Plat"}.get(code, "N/A")

def _non_demon_diff(numer: int) -> str:
    return {
        10: "Easy",
        20: "Normal",
        30: "Hard",
        40: "Harder",
        50: "Insane",
    }.get(numer, "N/A")

def _demon_name(code: int) -> str:
    # 3 Easy, 4 Medium, 0 Hard, 5 Insane, 6 Extreme
    return {3: "Easy", 4: "Medium", 0: "Hard", 5: "Insane", 6: "Extreme"}.get(code, "Unknown")

def _fetch_download(level_id: int) -> dict:
    """downloadGJLevel22.php → Primärquelle für Leveldaten (einzelnes Level)."""
    url = f"{BASE}/downloadGJLevel22.php"
    r = _post(url, data={"levelID": str(level_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code == 403:
        raise RuntimeError("403/Cloudflare-Block. Private IP nutzen, langsam anfragen, User-Agent leer lassen.")
    r.raise_for_status()
    txt = r.text.strip()
    if not txt or txt == "-1":
        raise RuntimeError(f"Level {level_id} nicht gefunden oder Serverfehler: {txt!r}")
    return _kv_block(txt)

def _fetch_levels_meta(level_id: int) -> str:
    """
    getGJLevels21.php mit levelID – enthält nach dem ersten '#'
    eine Creator-Mapping-Liste 'playerID:username:accountID|...'.
    Wir geben den Rohtext zurück und parsen nur die Creator-Liste.
    """
    url = f"{BASE}/getGJLevels21.php"
    r = _post(url, data={"levelID": str(level_id), "secret": SECRET}, headers=HEADERS, timeout=30)
    if r.status_code == 403:
        raise RuntimeError("403/Cloudflare-Block bei getGJLevels21.php.")
    r.raise_for_status()
    return r.text.strip()

def _parse_creator_from_levels21(raw: str, player_id: int) -> str:
    """
    Rohantwort: <level(s)>#<creatorMap>#<songs>...
    creatorMap: 'playerID:username:accountID|playerID:username:accountID|...'
    """
    if "#" not in raw:
        return ""
    parts = raw.split("#")
    if len(parts) < 2:
        return ""
    creators = parts[1]
    for chunk in creators.split("|"):
        if not chunk:
            continue
        cols = chunk.split(":")
        if len(cols) >= 2:
            try:
                pid = int(cols[0])
            except Exception:
                continue
            if pid == player_id:
                return cols[1]
    return ""

def _fetch_song(song_id: int) -> dict:
    """getGJSongInfo.php – liefert Name/Artist/Size/URL, wenn Custom Song."""
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
        "artist_id": _to_int(kv.get("3", "0")),
        "artist": kv.get("4", ""),
        "size": kv.get("5", ""),          # z. B. "5.36MB"
        "url": kv.get("10", "-"),
    }

# ===================== Deine ursprüngliche Logik – jetzt Boomlings-basiert =====================
def get_level_data(level_id, number, skip_warnings=False):
    try:
        kv = _fetch_download(int(level_id))
    except Exception as e:
        print(f"[!] Failed to fetch level {level_id}: {e}")
        return None

    # --- Felder gemäß 2.2 (aus downloadGJLevel22.php) ---
    name = kv.get("2", "")
    desc = _b64_text(kv.get("3", ""))  # (Beschreibung wird nicht ausgegeben, nur als Referenz verfügbar)
    version = _to_int(kv.get("5", "0"))
    player_id = _to_int(kv.get("6", "0"))

    downloads = _to_int(kv.get("10", "0"))
    game_version_raw = _to_int(kv.get("13", "0"))  # 22 => "2.2"
    likes = _to_int(kv.get("14", "0"))

    length_code = _to_int(kv.get("15", "0"))
    length_name = _length_name(length_code)   # wird nicht in dein JSON geschrieben, nur intern
    platformer = length_code == 5

    demon_flag = kv.get("17", "0") == "1"
    stars = _to_int(kv.get("18", "0"))

    feature_score = _to_int(kv.get("19", "0"))  # >0 = featured
    copied_id = _to_int(kv.get("30", "0"))
    two_player = kv.get("31", "0") == "1"

    custom_song_id = _to_int(kv.get("35", "0"))
    coins = _to_int(kv.get("37", "0"))
    verified_coins = kv.get("38", "0") == "1"
    stars_requested = _to_int(kv.get("39", "0"))
    ldm = kv.get("40", "0") == "1"
    epic_code = _to_int(kv.get("42", "0"))  # 0 none, 1 epic, 2 legendary, 3 mythic
    demon_code = _to_int(kv.get("43", "0"))  # demon subtype
    objects = _to_int(kv.get("45", "0"))

    # Difficulty-Text
    if demon_flag or demon_code in (0, 3, 4, 5, 6):
        difficulty_text = f"{_demon_name(demon_code)} Demon"
    else:
        difficulty_text = _non_demon_diff(_to_int(kv.get("9", "0")))

    # Rating (wie dein altes cp→Text Mapping)
    # cp 1=Rated, 2=Featured, 3=Epic, 4=Legendary, 5=Mythic
    if epic_code in (1, 2, 3):
        cp = 2 + epic_code
    elif feature_score > 0:
        cp = 2
    elif stars > 0:
        cp = 1
    else:
        cp = 0
    rating_map = {1: "Rated", 2: "Featured", 3: "Epic", 4: "Legendary", 5: "Mythic"}
    rating = rating_map.get(cp, "")

    # Creator-Name über getGJLevels21.php auflösen
    creator = ""
    try:
        raw_meta = _fetch_levels_meta(int(level_id))
        creator = _parse_creator_from_levels21(raw_meta, player_id) or ""
    except Exception:
        creator = ""

    # Song-Infos (custom oder official)
    official_song = _to_int(kv.get("12", "0")) != 0
    song_name = ""
    song_author = ""
    song_id_out = "OFFICIAL" if official_song else 0
    if not official_song and custom_song_id:
        song_meta = _fetch_song(custom_song_id)
        song_name = song_meta.get("name", "")
        song_author = song_meta.get("artist", "")
        song_id_out = custom_song_id

    # Gewohnte Struktur
    level_info = {
        "number": number,
        "level": name,
        "creator": creator,
        "ID": _to_int(kv.get("1", "0")),
        "difficulty": difficulty_text,
        "rating": rating,
        "userCoins": coins,
        "estimatedTime": None,
        "objects": objects,
        "checkpoints": None,
        "twop": two_player,
        "primarySong": song_name,
        "artist": song_author,
        "songID": song_id_out if not official_song else "OFFICIAL",
        "songs": None,
        "SFX": None,
        "rateDate": "",
        "showcase": ""
    }

    if level_info["objects"] == 65535 and not skip_warnings:
        print(f"[!] Warning: Level {level_id} has 65535 objects — may be higher (GD limit).")

    return level_info

# ===================== Rest wie gehabt =====================
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
                continue  # ignorieren
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
            continue  # Behalte NONG-Songs komplett

        elif existing.get("songID") == "UNKNOWN":
            if key == "songID":
                continue  # songID bleibt "UNKNOWN"
            elif key in ["primarySong", "artist"]:
                merged[key] = ""  # explizit leer setzen

        elif value is None or value == "":
            continue

        else:
            merged[key] = value
    return merged

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        all_ids = [line.strip() for line in f if line.strip().isdigit()]

    # Eingabe: Wie viele Level sollen verarbeitet werden?
    limit_input = input("🔢 Wie viele der letzten Level möchtest du verarbeiten? (Leer = alle): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else None

    # Mapping: ID → Zeilennummer (1-basiert)
    id_to_line = {level_id: idx + 1 for idx, level_id in enumerate(all_ids)}

    # Nur die letzten N IDs bearbeiten (aber mit richtiger Zeilenposition)
    level_ids = all_ids[-limit:] if limit else all_ids

    existing_data = load_existing_data(OUTPUT_FILE)
    existing_dict = {str(entry["ID"]): entry for entry in existing_data}

    added_count = 0
    updated_count = 0
    skipped_count = 0

    result_data_dict = {}  # Key = ID, Value = final merged entry
    processed_ids = set()

    print(f"📦 Verarbeite {len(level_ids)} von {len(all_ids)} Levels...\n")

    for level_id in level_ids:
        if level_id in processed_ids:
            continue
        processed_ids.add(level_id)

        number = id_to_line[level_id]  # echte Zeilennummer verwenden
        old_entry = existing_dict.get(level_id)
        new_entry = get_level_data(level_id, number, skip_warnings=bool(old_entry))

        if not new_entry:
            if old_entry:
                print(f"[~] Skipped level {level_id}")
                result_data_dict[level_id] = old_entry  # bestehenden Eintrag sichern
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
            print(f"[~] Skipped level {level_id}")
            old_entry["number"] = number
            result_data_dict[level_id] = old_entry
            skipped_count += 1

    # Füge alle anderen (nicht aktualisierten) alten Einträge hinzu
    for old_id, old_entry in existing_dict.items():
        if old_id not in processed_ids:
            result_data_dict[old_id] = old_entry

    # Sortiere nach number-Feld
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
