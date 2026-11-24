"""Run one lightweight Platformer Demon sync per Berlin day and push data."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import json
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".sync-state"
CHECKOUT = RUNTIME / "checkout"
RATED_FILES = ["src/assets/pemons.json", "src/assets/pemon_ids.txt"]
UNRATED_FILES = ["src/assets/unrated-pemons.json", "src/assets/unrated-pemon-ids.txt"]
DATA_FILES = RATED_FILES + UNRATED_FILES

def dataset_options(dataset):
    if dataset == "rated":
        return ["--rated-only"], RATED_FILES
    if dataset == "unrated":
        return ["--unrated-only"], UNRATED_FILES
    if dataset == "both":
        return [], DATA_FILES
    raise ValueError(f"Unknown dataset: {dataset}")
SUCCESS_STATE = RUNTIME / "last-success.json"


def berlin_today():
    return datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()


def already_synced_today(today=None):
    """Only successful sync-and-push runs count towards the daily limit."""
    today = today or berlin_today()
    if not SUCCESS_STATE.exists():
        return False
    data = json.loads(SUCCESS_STATE.read_text(encoding="utf-8"))
    return data.get("date") == today


def record_success(today=None):
    today = today or berlin_today()
    RUNTIME.mkdir(exist_ok=True)
    temporary = SUCCESS_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"date": today}) + "\n", encoding="utf-8")
    os.replace(temporary, SUCCESS_STATE)



@contextmanager
def exclusive_run():
    """Keep the fast watcher and daily full sync from touching the same checkout."""
    lock_path = RUNTIME / "sync.lock"
    with lock_path.open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                print("Another Pemon sync is running; skipping overlapping run.", flush=True)
                yield False
                return
            try:
                yield True
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Another Pemon sync is running; skipping overlapping run.", flush=True)
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)



def run(*args, cwd=CHECKOUT, capture=False):
    result = subprocess.run(args, cwd=cwd, check=True, text=True,
                            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE if capture else sys.stdout,
                            stderr=sys.stderr)
    return result.stdout.strip() if capture else ""


def main(check_only=False, full=False, dataset='both'):
    dataset_args, data_files = dataset_options(dataset)
    os.environ.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", RL_MIN_INTERVAL="5", PYTHONUTF8="1")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is not installed or not on PATH")
    RUNTIME.mkdir(exist_ok=True)
    remote = run(git, "remote", "get-url", "origin", cwd=ROOT, capture=True)
    if not CHECKOUT.exists():
        run(git, "clone", "--branch", "main", "--single-branch", remote, str(CHECKOUT), cwd=ROOT)
    if run(git, "status", "--porcelain", capture=True):
        raise RuntimeError(f"The automation checkout has uncommitted files. Review {CHECKOUT} before retrying.")
    # Update a stale checkout before checking push access. Rebase also keeps an
    # earlier committed data update whose push failed without discarding it.
    run(git, "pull", "--rebase", "origin", "main")
    run(git, "push", "--dry-run" if check_only else "--porcelain", "origin", "HEAD:main")
    if check_only:
        print("Preflight passed: checkout clean and GitHub push access available.", flush=True)
        return
    print(f"Sync scope: {dataset} ({'full' if full else 'watch'} mode)", flush=True)
    run(sys.executable, "-u", str(ROOT / "scripts/sync_pemons.py"),
        "--all" if full else "--watch", "--data-root", str(CHECKOUT),
        *dataset_args, cwd=ROOT)
    run(git, "add", "--", *data_files)
    diff = subprocess.run([git, "diff", "--cached", "--quiet"], cwd=CHECKOUT,
                          stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr)
    if diff.returncode == 0:
        print("No data changes; no commit needed.", flush=True)
        return
    if diff.returncode != 1:
        raise RuntimeError("Could not inspect staged data changes")
    name = run(git, "config", "user.name", cwd=ROOT, capture=True)
    email = run(git, "config", "user.email", cwd=ROOT, capture=True)
    run(git, "-c", f"user.name={name}", "-c", f"user.email={email}",
        "commit", "-m", "chore: daily platformer demon data sync")
    run(git, "pull", "--rebase", "origin", "main")
    run(git, "push", "origin", "HEAD:main")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check Git access only")
    parser.add_argument("--all", action="store_true", help="Download all entries in selected scope")
    parser.add_argument("--force", action="store_true", help="Bypass daily limit")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--rated-only", dest="dataset", action="store_const", const="rated")
    scope.add_argument("--unrated-only", dest="dataset", action="store_const", const="unrated")
    parser.set_defaults(dataset="both")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    RUNTIME.mkdir(exist_ok=True)
    check = args.check
    full = args.all
    force = args.force
    dataset = args.dataset
    logfile = RUNTIME / ("preflight.log" if check else "daily-sync.log")
    with logfile.open("a", encoding="utf-8", buffering=1) as log, redirect_stdout(log), redirect_stderr(log):
        # Pass real file handles to children; Windows scheduled tasks may have
        # invalid console handles, so changing CRT descriptors with dup2 fails.
        print(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---", flush=True)
        try:
            with exclusive_run() as acquired:
                if acquired:
                    if not check and not force and dataset == "both" and already_synced_today():
                        print("Today's Pemon sync already succeeded; skipping.", flush=True)
                    else:
                        main(check_only=check, full=full, dataset=dataset)
                        if not check and dataset == "both":
                            record_success()
                            print(f"Daily sync completed for {berlin_today()}.", flush=True)
                        elif not check:
                            print(f"{dataset.capitalize()}-only sync completed for {berlin_today()}; daily marker unchanged.", flush=True)
        except Exception:
            import traceback
            traceback.print_exc()
            raise SystemExit(1)
