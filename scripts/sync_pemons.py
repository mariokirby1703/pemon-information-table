"""Unattended discovery and rotating metadata refresh; never removes entries."""
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


def discover(full=False):
    found = {}
    previous = set()
    stalled_pages = 0
    for page in range(5000 if full else 5):
        print(f"Reading platformer demon list, page {page + 1}...", flush=True)
        response = builder._post(
            f"{builder.BASE}/getGJLevels21.php",
            data={"secret": builder.SECRET, "type": "0" if full else "11",
                  "str": "", "diff": "-2", "len": "5", "star": "1",
                  "page": str(page), "gameVersion": "22", "binaryVersion": "45"},
            headers=builder.HEADERS,
        )
        response.raise_for_status()
        raw = response.text.strip()
        if raw == "-1" and page > 0:
            break
        if "#" not in raw:
            raise RuntimeError(f"Invalid discovery response on page {page}: {raw[:80]!r}")
        rows = [builder._kv_block(row) for row in raw.split("#", 1)[0].split("|") if row]
        if not rows:
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
            if row.get("15") == "5" and row.get("17") == "1" and int(row.get("18", 0)) == 10:
                found[row["1"]] = raw
    else:
        if full:
            raise RuntimeError("Discovery exceeded page limit")
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
    for level_id, raw in discovered.items():
        row = next(builder._kv_block(item) for item in raw.split("#", 1)[0].split("|")
                   if builder._kv_block(item).get("1") == level_id)
        # Ignore volatile likes/downloads: a new level version or changed metadata
        # triggers the expensive download, even if the level is old.
        keys = ("2", "5", "6", "9", "12", "15", "17", "18", "19", "31", "35", "37", "42", "43", "45", "46", "47", "52", "53", "57")
        fingerprints[level_id] = [row.get(key) for key in keys]
        previous = state.get("fingerprints", {}).get(level_id)
        old = by_id.get(level_id)
        difficulty = f"{builder._demon_name(int(row.get('43', 0)))} Demon"
        rating = {1: "Epic", 2: "Legendary", 3: "Mythic"}.get(int(row.get("42", 0)),
                     "Featured" if int(row.get("19", 0)) > 0 else "Rated")
        if (previous is not None and previous != fingerprints[level_id]) or (
            old and (old.get("difficulty") != difficulty or old.get("rating") != rating)
        ):
            changed.append(level_id)
    selected = set([*changed, *[value for value in ids if value not in by_id], *batch])
    if batch_size == 0:
        print(f"Rating watch: {len(new_ids)} newly discovered, {len(changed)} changed, "
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
    result = sorted(by_id.values(), key=lambda entry: entry["number"])
    if result != existing:
        builder.save_data(builder.OUTPUT_FILE, result)
    id_text = "\n".join(ids) + "\n"
    if builder.INPUT_FILE.read_text(encoding="utf-8") != id_text:
        builder.INPUT_FILE.write_text(id_text, encoding="utf-8")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"next_level_id": next_level_id, "fingerprints": fingerprints}))
    print(f"Checked {len(selected)} levels; added {added}, updated {updated}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=20)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--all", action="store_true", help="Fully refresh every existing entry, newest first")
    modes.add_argument("--watch", action="store_true", help="Scan all rated platformer demons and download only new/changed levels")
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
    if args.all:
        # A complete daily pass must always start at the newest entry.
        args.batch_size = sys.maxsize
        if STATE.exists():
            state = json.loads(STATE.read_text())
            state["next_level_id"] = None
            STATE.write_text(json.dumps(state))
    try:
        sync(args.batch_size)
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
