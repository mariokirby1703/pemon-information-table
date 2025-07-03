import requests
import json
import os

INPUT_FILE = "pemon_ids.txt"
OUTPUT_FILE = "pemons.json"

def get_level_data(level_id, number, skip_warnings=False):
    url = f"https://gdbrowser.com/api/level/{level_id}"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"[!] Failed to fetch level {level_id}")
        return None
    data = response.json()

    cp = int(data.get("cp", 0))
    rating_map = {
        1: "Rated",
        2: "Featured",
        3: "Epic",
        4: "Legendary",
        5: "Mythic"
    }
    rating = rating_map.get(cp, "")

    official = int(data.get("officialSong", 0)) != 0
    song_name = data.get("songName", "")

    level_info = {
        "number": number,
        "level": data.get("name", ""),
        "creator": data.get("author", ""),
        "ID": int(data.get("id", 0)),
        "difficulty": data.get("difficulty", ""),
        "rating": rating,
        "userCoins": data.get("coins", 0),
        "estimatedTime": None,
        "objects": int(data.get("objects", 0)),
        "checkpoints": None,
        "twop": data.get("twoPlayer", False),
        "primarySong": song_name,
        "artist": data.get("songAuthor", ""),
        "songID": "OFFICIAL" if official else int(data.get("songID", 0)),
        "songs": None,
        "SFX": None,
        "rateDate": "",
        "showcase": ""
    }

    if level_info["objects"] == 65535 and not skip_warnings:
        print(f"[!] Warning: Level {level_id} has 65535 objects — may be higher (GD limit).")

    return level_info

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
        elif key in ["primarySong", "artist", "songID"] and existing.get("songID") == "NONG":
            continue
        elif key in ["primarySong", "artist"] and existing.get("songID") == "UNKNOWN":
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
        elif key in ["primarySong", "artist", "songID"] and existing.get("songID") == "NONG":
            continue
        elif existing.get("songID") == "UNKNOWN" and key in ["primarySong", "artist"]:
            merged[key] = ""
            continue
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

    level_ids = all_ids[-limit:] if limit else all_ids

    existing_data = load_existing_data(OUTPUT_FILE)
    existing_dict = {str(entry["ID"]): entry for entry in existing_data}

    added_count = 0
    updated_count = 0
    skipped_count = 0

    result_data = []
    processed_ids = set()

    print(f"📦 Verarbeite {len(level_ids)} von {len(all_ids)} Levels...\n")

    for index, level_id in enumerate(level_ids, start=1):
        if level_id in processed_ids:
            continue
        processed_ids.add(level_id)

        old_entry = existing_dict.get(level_id)
        new_entry = get_level_data(level_id, index, skip_warnings=bool(old_entry))

        if not new_entry:
            continue

        if not old_entry:
            print(f"[+] Added level {level_id}: {new_entry['level']} by {new_entry['creator']}")
            result_data.append(new_entry)
            added_count += 1
        elif entries_differ(old_entry, new_entry):
            print(f"[~] Updated level {level_id}: {new_entry['level']} (changes detected)")
            merged = merge_entries(old_entry, new_entry)
            result_data.append(merged)
            updated_count += 1
        else:
            old_entry["number"] = index
            result_data.append(old_entry)
            skipped_count += 1

    # Füge alte, nicht verarbeitete Einträge wieder hinzu
    for old_id, old_entry in existing_dict.items():
        if old_id not in processed_ids:
            result_data.append(old_entry)

    result_data.sort(key=lambda x: x["number"])
    save_data(OUTPUT_FILE, result_data)

    print("\n===== Summary =====")
    print(f"Total levels processed: {len(level_ids)}")
    print(f"🆕 Added:   {added_count}")
    print(f"🔄 Updated: {updated_count}")
    print(f"✅ Skipped: {skipped_count}")
    print(f"📄 Output saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
