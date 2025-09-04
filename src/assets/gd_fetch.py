#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Usage:
  python gd_level_min.py <level_id>
"""

import sys, json, base64, requests, re
from datetime import timedelta
from urllib.parse import unquote

BASE = "http://www.boomlings.com/database"
SECRET = "Wmfd2893gb7"
HEADERS = {
    "User-Agent": "",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "*/*",
    "Connection": "close",
}

LEN_MAP = {0:"Tiny", 1:"Small", 2:"Medium", 3:"Long", 4:"XL", 5:"Platformer"}
DEMON_MAP = {3:"Easy Demon", 4:"Medium Demon", 0:"Hard Demon", 5:"Insane Demon", 6:"Extreme Demon"}
RATING_MAP = {1:"Epic", 2:"Legendary", 3:"Mythic"}  # 0 wird unten per Logik (key19) aufgelöst

session = requests.Session()
session.trust_env = False

def _kv(text: str) -> dict:
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

def _b64txt(s: str) -> str:
    if not s:
        return ""
    try:
        return base64.b64decode(s.encode()).decode("utf-8", "replace")
    except Exception:
        s2 = s.replace("-", "+").replace("_", "/")
        pad = (-len(s2)) % 4
        try:
            return base64.b64decode(s2 + "=" * pad).decode("utf-8", "replace")
        except Exception:
            return ""

def _post(url: str, data: dict) -> str:
    r = session.post(url, data=data, headers=HEADERS, timeout=30)
    r.raise_for_status()
    t = r.text.strip()
    if t == "-1":
        raise RuntimeError("Server returned -1 (not found / error).")
    tl = t.lower()
    if ("<html" in tl or "<!doctype html" in tl) and "cloudflare" in tl:
        raise RuntimeError("Cloudflare block detected.")
    return t

def _fmt_hms(total_seconds: int) -> str:
    if total_seconds < 0:
        total_seconds = 0
    td = timedelta(seconds=int(total_seconds))
    hours = td.seconds // 3600 + td.days * 24
    minutes = (td.seconds % 3600) // 60
    seconds = td.seconds % 60
    return f"{hours}:{minutes:02d}:{seconds:02d}"

def _get_creator(player_id: int, level_name_hint: str = "") -> tuple[str, int]:
    try:
        r = session.post(f"{BASE}/getGJUsers20.php",
                         data={"str": str(player_id), "secret": SECRET},
                         headers=HEADERS, timeout=30)
        r.raise_for_status()
        t = r.text.strip()
        if t and t != "-1" and "cloudflare" not in t.lower():
            for chunk in t.split("|"):
                if not chunk:
                    continue
                kvu = _kv(chunk)
                if kvu.get("2", "").isdigit() and int(kvu["2"]) == player_id:
                    name = kvu.get("1", "") or ""
                    acc_id = int(kvu.get("16", "0")) if kvu.get("16", "0").isdigit() else 0
                    if name:
                        return name, acc_id
    except Exception:
        pass

    if level_name_hint:
        try:
            r = session.post(f"{BASE}/getGJLevels21.php",
                             data={"type": "0", "str": level_name_hint, "secret": SECRET},
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            t = r.text.strip()
            if t and t != "-1" and "cloudflare" not in t.lower():
                parts = t.split("#")
                if len(parts) >= 2:
                    creators_part = parts[1]
                    for chunk in creators_part.split("|"):
                        if not chunk:
                            continue
                        cols = chunk.split(":")
                        if len(cols) >= 2 and cols[0].isdigit() and int(cols[0]) == player_id:
                            name = cols[1]
                            acc_id = int(cols[2]) if len(cols) >= 3 and cols[2].isdigit() else 0
                            if name:
                                return name, acc_id
        except Exception:
            pass
    return "", 0

def _parse_song_map_from_levels21(raw: str) -> dict[int, dict]:
    songs = {}
    parts = raw.split("#")
    if len(parts) < 3:
        return songs
    blob = parts[2]
    for m in re.finditer(r'(?:(?<=^)|(?<=:))1~\|~(.*?)(?=(?:(?<=:))1~\|~|\Z)', blob, re.S):
        seg = "1~|~" + m.group(1)
        f = seg.split("~|~")
        d = {}
        for i in range(0, len(f) - 1, 2):
            d[f[i]] = f[i + 1]
        sid = d.get("1", "")
        if sid.isdigit():
            sid = int(sid)
            songs[sid] = {
                "songID": sid,
                "name": d.get("2", ""),
                "artist": d.get("4", ""),
                "size": d.get("5", ""),
                "downloadURL": unquote(d.get("10", "-") or "-"),
            }
    return songs

def _get_song_primary_and_artist(level_name: str, official_idx: int, custom_id: int, level_id_for_fallback: int) -> tuple[str, str]:
    if official_idx != 0 or custom_id <= 0:
        return "", ""
    try:
        r = session.post(f"{BASE}/getGJSongInfo.php",
                         data={"songID": str(custom_id), "secret": SECRET},
                         headers=HEADERS, timeout=30)
        r.raise_for_status()
        t = r.text.strip()
        if t and t != "-1" and "cloudflare" not in t.lower():
            k = _kv_tilde(t)
            sid = int(k.get("1", "0")) if k.get("1", "").isdigit() else 0
            if sid > 0:
                return k.get("2", "") or "", k.get("4", "") or ""
    except Exception:
        pass
    try:
        r = session.post(f"{BASE}/getGJLevels21.php",
                         data={"levelID": str(level_id_for_fallback), "secret": SECRET},
                         headers=HEADERS, timeout=30)
        r.raise_for_status()
        t = r.text.strip()
        if t and t != "-1" and "cloudflare" not in t.lower():
            songs_map = _parse_song_map_from_levels21(t)
            if custom_id in songs_map:
                m = songs_map[custom_id]
                return m.get("name", "") or "", m.get("artist", "") or ""
    except Exception:
        pass
    if level_name:
        try:
            r = session.post(f"{BASE}/getGJLevels21.php",
                             data={"type": "0", "str": level_name, "secret": SECRET},
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            t = r.text.strip()
            if t and t != "-1" and "cloudflare" not in t.lower():
                songs_map = _parse_song_map_from_levels21(t)
                if custom_id in songs_map:
                    m = songs_map[custom_id]
                    return m.get("name", "") or "", m.get("artist", "") or ""
        except Exception:
            pass
    return "", ""

def main():
    if len(sys.argv) < 2:
        print("Usage: python gd_level_min.py <level_id>", file=sys.stderr)
        sys.exit(1)

    level_id = int(sys.argv[1])

    raw = _post(f"{BASE}/downloadGJLevel22.php", {"levelID": str(level_id), "secret": SECRET})
    kv = _kv(raw)

    def geti(key, default=0):
        try:
            return int(kv.get(str(key), str(default)))
        except Exception:
            return default

    levelID        = geti(1)
    levelName      = kv.get("2", "")
    description    = _b64txt(kv.get("3", ""))
    downloads      = geti(10)
    officialSong   = geti(12)
    likes_raw      = geti(14)
    length_code    = geti(15)
    awardedStars   = geti(18)
    feature_score  = geti(19)     # <- neu für rated/featured Unterscheidung
    twoPlayer      = kv.get("31", "0") == "1"
    customSongID   = geti(35)
    coins          = geti(37)
    rating_code    = geti(42)     # 0/1/2/3
    demon_code     = geti(43)
    objects        = geti(45)
    editorTimeA    = geti(46)
    editorTimeB    = geti(47)
    playerID       = geti(6)
    accountID      = geti(41)
    k52_raw        = kv.get("k52", "") or kv.get("52", "")
    k53_raw        = kv.get("k53", "") or kv.get("53", "")
    k57_frames     = geti(57) if "57" in kv or "k57" in kv else geti("k57")

    likes = abs(likes_raw)
    length = LEN_MAP.get(length_code, f"unknown({length_code})")
    demonDifficulty = DEMON_MAP.get(demon_code, f"unknown({demon_code})")

    # --- Rating-Logik ---
    # Wenn key42 == 0: nutze key19 → 0 = rated, >=1 = featured
    # Sonst (key42 in 1..3): epic/legendary/mythic laut Map
    if rating_code == 0:
        rating = "Featured" if feature_score >= 1 else "Rated"
    else:
        rating = RATING_MAP.get(rating_code, f"unknown({rating_code})")

    editor_total_seconds = max(0, editorTimeA + editorTimeB)
    editorTime = _fmt_hms(editor_total_seconds)

    key_52 = len([x.strip() for x in k52_raw.split(",") if x.strip()]) if k52_raw else 0
    if k53_raw:
        first_part = k53_raw.split("#", 1)[0]
        key_53 = len([x.strip() for x in first_part.split(",") if x.strip()])
    else:
        key_53 = 0

    key_57 = _fmt_hms(int(round(k57_frames / 240.0)) if isinstance(k57_frames, int) else 0)

    creator_name, account_id_resolved = _get_creator(playerID, level_name_hint=levelName)
    if not accountID and account_id_resolved:
        accountID = account_id_resolved

    primarySong, artistName = _get_song_primary_and_artist(levelName, officialSong, customSongID, levelID)

    out = {
        "levelName": levelName,
        "creator": creator_name,
        "levelID": levelID,
        "demonDifficulty": demonDifficulty,
        "rating": rating,
        "coins": coins,
        "estimatedTime": key_57,
        "objects": objects,
        "twoPlayer": twoPlayer,
        "primarySong": primarySong,
        "artist": artistName,
        "customSongID": customSongID,
        "songs": key_52,
        "SFXs": key_53,
        "description": description,
        "downloads": downloads,
        "editorTime": editorTime,
        "officialSong": officialSong,
        "likes": likes,
        "length": length,
        "awardedStars": awardedStars
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
