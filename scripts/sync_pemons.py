"""Unattended rated and unrated discovery, metadata refresh and promotion."""
import argparse
from datetime import datetime
import importlib.util
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("builder", ROOT / "src/assets/pemon-create.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
STATE = ROOT / ".sync-state/cursor.json"


def refresh_batch(ids, state, batch_size):
    """Start with the latest table additions; resume older entries next run."""
    newest_first = list(reversed(ids))
    # Watch mode deliberately skips the rolling metadata refresh without
    # advancing its cursor. Newly rated and changed levels are still checked.
    if batch_size == 0:
        return [], state.get("next_level_id")
    if not newest_first:
        return [], None
    next_id = state.get("next_level_id")
    start = newest_first.index(next_id) if next_id in newest_first else 0
    batch = newest_first[start:start + batch_size]
    end = start + len(batch)
    return batch, newest_first[end] if end < len(newest_first) else None


def creator_names_from_search(raw):
    """Return verified creator names keyed by stable GD player ID.

    getGJLevels21 supplies a separate creators section containing records
    formatted as playerID:username:accountID. A rename only affects the
    display name, not that numeric player ID. Skip missing/invalid records.
    """
    parts = raw.split("#", 2)
    if len(parts) < 2:
        return {}
    names = {}
    for chunk in parts[1].split("|"):
        fields = chunk.split(":")
        if len(fields) < 2 or not fields[0].isdigit():
            continue
        name = builder._valid_creator_name(fields[1].strip())
        if name:
            names[fields[0]] = name
    return names


def discover(full=False, hyped=False):
    found = {}
    previous = set()
    stalled_pages = 0
    for page in range(5000 if full else 5):
        print(f"Reading {'hyped unrated' if hyped else 'rated'} platformer demon list, page {page + 1}...", flush=True)
        response = builder._post(
            f"{builder.BASE}/getGJLevels21.php",
            data={"secret": builder.SECRET, "type": "31" if hyped else ("0" if full else "11"),
                  "str": "", "diff": "-2", "len": "5",
                  **({"noStar": "1", "hypeSecret": "1"} if hyped else {"star": "1"}),
                  "page": str(page), "gameVersion": "22", "binaryVersion": "51" if hyped else "45"},
            headers=builder.HEADERS,
        )
        response.raise_for_status()
        raw = response.text.strip()
        if raw == "-1" and page > 0 and not hyped:
            break
        if "#" not in raw:
            raise RuntimeError(f"Invalid discovery response on page {page}: {raw[:80]!r}")
        rows = [builder._kv_block(row) for row in raw.split("#", 1)[0].split("|") if row]
        if not rows:
            if hyped and not (page == 0 and raw.split("#")[3:4] == ["0:0:10"]):
                raise RuntimeError("Unexpected empty hyped page; preserving previous data")
            break
        if any(not row.get("1", "").isdigit() for row in rows):
            raise RuntimeError("Discovery returned an invalid level ID")
        ids = {row["1"] for row in rows}
        # Search order is live, not a snapshot: moving levels can overlap page
        # boundaries. Deduplicate these; only fail if pagination stops progressing.
        stalled_pages = stalled_pages + 1 if not ids - previous else 0
        if stalled_pages >= 3:
            raise RuntimeError("Discovery pagination made no progress for three pages; refusing incomplete scan")
        overlap = len(ids & previous)
        if overlap:
            print(f"Ignoring {overlap} overlapping level(s) on page {page + 1}.", flush=True)
        previous.update(ids)
        for row in rows:
            if hyped:
                # The Demon filter on a sent/hyped query describes the search
                # category, not necessarily the level's awarded Demon flag.
                # Verify the real awarded moon count using the download endpoint.
                print(f"Hyped candidate {row['1']} {row.get('2', '')!r}: "
                      f"len={row.get('15')!r}, demon={row.get('17')!r}, "
                      f"stars={row.get('18')!r}, difficulty={row.get('9')!r}, "
                      f"requested={row.get('39')!r}, demonCode={row.get('43')!r}", flush=True)
                if row.get("15") == "5":
                    found[row["1"]] = raw
            elif row.get("15") == "5" and row.get("17") == "1" and int(row.get("18") or 0) == 10:
                found[row["1"]] = raw
        if hyped:
            # Use explicit page information when provided, rather than requesting
            # one extra page that may return an ambiguous -1.
            parts = raw.split("#")
            info = parts[3].split(":") if len(parts) > 3 else []
            if len(info) == 3 and all(value.isdigit() for value in info):
                total, offset, size = map(int, info)
                if size > 0 and offset + size >= total:
                    break
    else:
        if full:
            raise RuntimeError("Discovery exceeded page limit")
    if hyped:
        print(f"Hyped search returned {len(previous)} unique levels; "
              f"{len(found)} platformer candidates.", flush=True)
        if previous and not found:
            raise RuntimeError("Hyped search returned no platformers; check filter response above")
    return found


def sync(batch_size=20):
    existing = builder.load_existing_data(builder.OUTPUT_FILE)
    by_id = {str(entry["ID"]): entry for entry in existing}
    ids = list(dict.fromkeys(builder.INPUT_FILE.read_text(encoding="utf-8").split()))
    if any(not value.isdigit() for value in ids):
        raise ValueError("pemon_ids.txt contains invalid IDs")
    ids.extend(value for value in by_id if value not in ids)
    discovered = discover(True)
    new_ids = sorted(set(discovered) - set(ids), key=int)
    ids.extend(new_ids)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    batch, next_level_id = refresh_batch(ids, state, batch_size)
    fingerprints = {}
    changed = []
    creator_updates = {}
    creators_cache = {}
    for level_id, raw in discovered.items():
        row = next(builder._kv_block(item) for item in raw.split("#", 1)[0].split("|")
                   if builder._kv_block(item).get("1") == level_id)
        # Ignore volatile likes/downloads: a new level version or changed metadata
        # triggers the expensive download, even if the level is old.
        keys = ("2", "5", "6", "9", "12", "15", "17", "18", "19", "31", "35", "37", "42", "43", "45", "46", "47", "52", "53", "57")
        fingerprints[level_id] = [row.get(key) for key in keys]
        previous = state.get("fingerprints", {}).get(level_id)
        old = by_id.get(level_id)
        # One creator block per search page can cover several levels. Reuse it
        # and compare usernames using their stable player IDs, not old names.
        if old is not None:
            if raw not in creators_cache:
                creators_cache[raw] = creator_names_from_search(raw)
            live_creator = creators_cache[raw].get(row.get("6", ""))
            if live_creator and live_creator != old.get("creator"):
                creator_updates[level_id] = live_creator
        difficulty = f"{builder._demon_name(int(row.get('43', 0)))} Demon"
        rating = {1: "Epic", 2: "Legendary", 3: "Mythic"}.get(int(row.get("42", 0)),
                     "Featured" if int(row.get("19", 0)) > 0 else "Rated")
        if (previous is not None and previous != fingerprints[level_id]) or (
            old and (old.get("difficulty") != difficulty or old.get("rating") != rating)
        ):
            changed.append(level_id)
    selected = set([*changed, *[value for value in ids if value not in by_id], *batch])
    if batch_size == 0:
        print(f"Rating watch: {len(new_ids)} newly discovered, {len(changed)} metadata changes, "
              f"{len(creator_updates)} creator rename(s), "
              f"{len(selected)} level(s) to download.", flush=True)
    today = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y")
    positions = {value: index + 1 for index, value in enumerate(ids)}
    selected = sorted(selected, key=positions.get, reverse=True)
    updated = added = 0
    for level_id in selected:
        print(f"Checking level {level_id} ({positions[level_id]})...", flush=True)
        kv = builder._fetch_download(int(level_id))
        if kv.get("1") != level_id or not kv.get("2") or "15" not in kv or "17" not in kv:
            raise RuntimeError(f"Invalid metadata for {level_id}; no files written")
        old = by_id.get(level_id)
        if not old and not (kv["15"] == "5" and kv["17"] == "1" and kv.get("18") == "10"):
            raise RuntimeError(f"New level {level_id} is no longer a rated platformer demon")
        if level_id in discovered:
            builder.levels21_cache[level_id] = discovered[level_id]
        fresh = builder.get_level_data_gd(level_id, positions[level_id], True, downloaded=kv)
        if not fresh or not fresh.get("creator"):
            raise RuntimeError(f"Incomplete metadata for {level_id}; no files written")
        if old:
            entry = builder.merge_entries(old, fresh)
            updated += entry != old
        else:
            fresh["rateDate"] = today
            entry = builder.sanitize_entry(fresh)
            added += 1
        by_id[level_id] = entry

    # Names come from the authenticated level-search response, so a
    # username-only change needs no expensive level download. Apply after
    # all downloads succeeded, preserving every other JSON field.
    renamed = 0
    for level_id, name in creator_updates.items():
        entry = by_id[level_id]
        if entry.get("creator") != name:
            print(f"Creator renamed for level {level_id}: "
                  f"{entry.get('creator', '')!r} -> {name!r}", flush=True)
            by_id[level_id] = {**entry, "creator": name}
            renamed += 1
    result = sorted(by_id.values(), key=lambda entry: entry["number"])
    if result != existing:
        builder.save_data(builder.OUTPUT_FILE, result)
    id_text = "\n".join(ids) + "\n"
    if builder.INPUT_FILE.read_text(encoding="utf-8") != id_text:
        builder.INPUT_FILE.write_text(id_text, encoding="utf-8")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"next_level_id": next_level_id, "fingerprints": fingerprints}))
    print(f"Checked {len(selected)} levels; added {added}, updated {updated}, renamed {renamed}.")


HYPED_KEYS = ("2", "5", "6", "9", "12", "15", "17", "18", "19", "31", "35",
              "37", "42", "43", "45", "46", "47", "52", "53", "57")


def read_unrated_ids():
    path = builder.OUTPUT_FILE.with_name("unrated-pemon-ids.txt")
    ids = list(dict.fromkeys(path.read_text(encoding="utf-8-sig").split())) if path.exists() else []
    if any(not value.isdigit() for value in ids):
        raise ValueError("unrated-pemon-ids.txt must contain numeric level IDs")
    return ids


def prepare_unrated(full=False, promotions=None):
    """Track all previously discovered and manually added IDs, even outside Hyped."""
    output = builder.OUTPUT_FILE.with_name("unrated-pemons.json")
    state_path = STATE.with_name("unrated-cursor.json")
    existing = builder.load_existing_data(output)
    old_by_id = {str(entry["ID"]): entry for entry in existing}
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    previous = state.get("fingerprints", {})
    discovered = discover(full=True, hyped=True)
    rated_ids = {str(entry["ID"]) for entry in builder.load_existing_data(builder.OUTPUT_FILE)}
    ids = list(dict.fromkeys([*read_unrated_ids(), *old_by_id, *discovered]))
    today = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y")
    result, fingerprints = [], {}
    downloaded = 0
    for level_id in ids:
        if level_id in rated_ids:
            print(f"Removing already known rated level {level_id} from unrated list.", flush=True)
            continue
        raw = discovered.get(level_id)
        row = next((builder._kv_block(item) for item in raw.split("#", 1)[0].split("|")
                    if builder._kv_block(item).get("1") == level_id), {}) if raw else {}
        fingerprint = [row.get(key) for key in HYPED_KEYS] if raw else None
        old = old_by_id.get(level_id)
        number = len(result) + 1
        # Levels outside Hyped must be checked directly: leaving the tab is
        # not proof of a rating. Manual IDs are included in this same path.
        if full or not raw or old is None or previous.get(level_id) != fingerprint:
            source = "hyped" if raw else "tracked/manual"
            print(f"Checking {source} platformer demon {level_id}...", flush=True)
            kv = builder._fetch_download(int(level_id))
            downloaded += 1
            if kv.get("1") != level_id or not kv.get("2") or "15" not in kv or "18" not in kv:
                raise RuntimeError(f"Invalid metadata for {level_id}; preserving previous data and IDs")
            moons = int(kv.get("18") or 0)
            print(f"Unrated check {level_id}: len={kv.get('15')!r}, "
                  f"demon={kv.get('17')!r}, stars={moons}", flush=True)
            if kv["15"] != "5":
                print(f"Skipping {level_id}: not a platformer.", flush=True)
                continue
            if moons != 0:
                if moons == 10 and kv.get("17") == "1":
                    if promotions is not None:
                        # An ID search is preferable to a potentially stale
                        # Hyped response when a level has just been rated.
                        builder.levels21_cache.pop(level_id, None)
                        fresh = builder.get_level_data_gd(level_id, number, True, downloaded=kv)
                        if not fresh or not fresh.get("creator"):
                            raise RuntimeError(f"Incomplete promotion metadata for {level_id}")
                        entry = builder.merge_entries(old, fresh) if old else builder.sanitize_entry(fresh)
                        entry["rateDate"] = today
                        entry.pop("firstSeen", None)
                        promotions[level_id] = entry
                    print(f"Promoting {level_id}: now a rated platformer demon.", flush=True)
                else:
                    print(f"Removing {level_id}: rated, but not a platformer demon.", flush=True)
                continue
            if raw:
                builder.levels21_cache[level_id] = raw
            else:
                builder.levels21_cache.pop(level_id, None)
            fresh = builder.get_level_data_gd(level_id, number, True, downloaded=kv)
            if not fresh or not fresh.get("creator"):
                raise RuntimeError(f"Incomplete unrated metadata for {level_id}")
            entry = builder.merge_entries(old, fresh) if old else builder.sanitize_entry(fresh)
        else:
            entry = dict(old)
        name = creator_names_from_search(raw).get(row.get("6", "")) if raw else None
        if name:
            entry["creator"] = name
        entry.update(number=number, difficulty="Demon", rating="Unrated", rateDate="",
                     firstSeen=(old or {}).get("firstSeen") or today)
        result.append(entry)
        fingerprints[level_id] = fingerprint
    print(f"Unrated watch: {len(result)} tracked unrated platformer demons, "
          f"{downloaded} level downloads.", flush=True)
    return result, fingerprints


def publish_promotions(promotions):
    """Append verified promotions to rated data before removing unrated copies."""
    if not promotions:
        return
    existing = builder.load_existing_data(builder.OUTPUT_FILE)
    by_id = {str(entry["ID"]): entry for entry in existing}
    ids = list(dict.fromkeys(builder.INPUT_FILE.read_text(encoding="utf-8-sig").split()))
    if any(not value.isdigit() for value in ids):
        raise ValueError("pemon_ids.txt contains invalid IDs")
    ids.extend(value for value in by_id if value not in ids)
    added = 0
    for level_id, entry in promotions.items():
        if level_id not in ids:
            ids.append(level_id)
        if level_id in by_id:
            # The normal rated scan may already have inserted this level.
            # Keep the rated record and its assigned number/date.
            continue
        by_id[level_id] = {**entry, "number": ids.index(level_id) + 1}
        added += 1
    if added:
        builder.save_data(builder.OUTPUT_FILE, sorted(by_id.values(), key=lambda entry: entry["number"]))
    id_text = "".join(f"{level_id}\n" for level_id in ids)
    if builder.INPUT_FILE.read_text(encoding="utf-8") != id_text:
        builder.INPUT_FILE.write_text(id_text, encoding="utf-8")
    print(f"Promotion: {added} level(s) added to rated data.", flush=True)


def remove_rated_from_unrated():
    """Rated-only scans need not query Hyped, but must remove promoted duplicates.
    Keep pending manual IDs that have not yet been downloaded.
    """
    output = builder.OUTPUT_FILE.with_name("unrated-pemons.json")
    ids_path = builder.OUTPUT_FILE.with_name("unrated-pemon-ids.txt")
    if not output.exists() and not ids_path.exists():
        return
    rated = {str(entry["ID"]) for entry in builder.load_existing_data(builder.OUTPUT_FILE)}
    existing = builder.load_existing_data(output)
    result = [dict(entry, number=index) for index, entry in enumerate(
        (entry for entry in existing if str(entry["ID"]) not in rated), 1)]
    ids = [value for value in read_unrated_ids() if value not in rated]
    if result != existing:
        builder.save_data(output, result)
    id_text = "".join(f"{value}\n" for value in ids)
    if ids_path.exists() and ids_path.read_text(encoding="utf-8-sig") != id_text:
        ids_path.write_text(id_text, encoding="utf-8")
    if len(result) != len(existing):
        print(f"Removed {len(existing) - len(result)} newly rated level(s) from unrated data.", flush=True)


def save_unrated(prepared):
    """Publish only the successful snapshot, excluding already rated IDs."""
    result, fingerprints = prepared
    rated = {str(entry["ID"]) for entry in builder.load_existing_data(builder.OUTPUT_FILE)}
    result = [entry for entry in result if str(entry["ID"]) not in rated]
    for number, entry in enumerate(result, 1):
        entry["number"] = number
    output = builder.OUTPUT_FILE.with_name("unrated-pemons.json")
    ids = builder.OUTPUT_FILE.with_name("unrated-pemon-ids.txt")
    if not output.exists() or builder.load_existing_data(output) != result:
        builder.save_data(output, result)
    id_text = "".join(f'{entry["ID"]}\n' for entry in result)
    if not ids.exists() or ids.read_text(encoding="utf-8") != id_text:
        ids.write_text(id_text, encoding="utf-8")
    state_path = STATE.with_name("unrated-cursor.json")
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps({"fingerprints": {
        str(entry["ID"]): fingerprints[str(entry["ID"])] for entry in result
    }}), encoding="utf-8")


def sync_datasets(batch_size, full=False, dataset="both"):
    if dataset not in ("both", "rated", "unrated"):
        raise ValueError(f"Unknown dataset: {dataset}")
    promotions = {}
    prepared = prepare_unrated(full=full, promotions=promotions) if dataset != "rated" else None
    if dataset != "unrated":
        if full and STATE.exists():
            state = json.loads(STATE.read_text())
            state["next_level_id"] = None
            STATE.write_text(json.dumps(state))
        sync(sys.maxsize if full else batch_size)
    if prepared is not None:
        publish_promotions(promotions)
        save_unrated(prepared)
    else:
        remove_rated_from_unrated()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=20)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--all", action="store_true", help="Fully refresh every existing entry, newest first")
    modes.add_argument("--watch", action="store_true", help="Scan rated platformer demons; sync creator names and download only new/changed levels")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--rated-only", dest="dataset", action="store_const", const="rated")
    scope.add_argument("--unrated-only", dest="dataset", action="store_const", const="unrated")
    parser.set_defaults(dataset="both")
    parser.add_argument("--data-root", type=Path, help="Separate checkout containing src/assets")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if args.data_root:
        asset_dir = args.data_root.resolve() / "src" / "assets"
        builder.INPUT_FILE = asset_dir / "pemon_ids.txt"
        builder.OUTPUT_FILE = asset_dir / "pemons.json"
    if args.watch:
        args.batch_size = 0
    try:
        sync_datasets(args.batch_size, full=args.all, dataset=args.dataset)
    except builder.requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 403:
            print(
                "GD server denied this runner's request (HTTP 403). No data was written. "
                "This is an access denial, not a confirmed rate limit. "
                "If GitHub-hosted runners remain blocked, configure an authorized "
                "self-hosted runner using the PEMON_RUNNER repository variable; see README.md.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        raise
