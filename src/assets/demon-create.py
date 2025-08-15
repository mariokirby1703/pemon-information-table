import requests
import json
import os

INPUT_FILE = "demon_ids.txt"
OUTPUT_FILE = "demons.json"

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
        "creator": data.get("author", ""),  # kann auch "-" sein, das übernehmen wir für neue Einträge unverändert
        "ID": int(data.get("id", 0)),
        "difficulty": data.get("difficulty", ""),
        "rating": rating,
        "userCoins": data.get("coins", 0),
        "length": data.get("length", ""),
        "objects": int(data.get("objects", 0)),
        "twop": data.get("twoPlayer", False),
        "primarySong": song_name,
        "artist": data.get("songAuthor", ""),
        "songID": "OFFICIAL" if official else int(data.get("songID", 0))
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

        # Sonderfall: Creator
        # Wenn API "-" liefert, aber bestehender Creator ein sinnvoller Wert ist, gilt das nicht als Änderung.
        if key == "creator":
            new_creator = new.get("creator")
            old_creator = existing.get("creator")
            if new_creator == "-" and old_creator not in [None, "", "-"]:
                continue  # beibehalten, keine Änderung melden
            # In allen anderen Fällen normal vergleichen (z.B. altes "" -> neues "-" oder richtiger Name)
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
                continue  # ignorieren
            elif key in ["primarySong", "artist"]:
                # songID bleibt UNKNOWN → diese sollen leer sein → keine Änderung
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

        # Sonderfall: Creator
        elif key == "creator":
            old_creator = existing.get("creator")
            # Wenn neuer Wert "-" ist und wir bereits einen sinnvollen alten Wert haben, behalten wir den alten.
            if value == "-" and old_creator not in [None, "", "-"]:
                continue
            # Sonst übernehmen (inkl. Fällen: alt leer -> neu "-", alt leer -> neu richtiger Name, etc.)
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
                result_data_dict[level_id] = old_entry  # bestehenden Eintrag sichern
                skipped_count += 1
            continue

        if not old_entry:
            print(f"[+] Added level {level_id}: {new_entry['level']} by {new_entry['creator']}")
            result_data_dict[level_id] = new_entry  # neuer Eintrag, creator bleibt ggf. "-"
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
