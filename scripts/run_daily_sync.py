"""Run the daily local sync in an isolated checkout, then commit and push data."""
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".sync-state"
CHECKOUT = RUNTIME / "checkout"
DATA_FILES = ["src/assets/pemons.json", "src/assets/pemon_ids.txt"]


def run(*args, cwd=CHECKOUT, capture=False):
    result = subprocess.run(args, cwd=cwd, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ""


def main(check_only=False):
    os.environ.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", RL_MIN_INTERVAL="5")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is not installed or not on PATH")
    RUNTIME.mkdir(exist_ok=True)
    remote = run(git, "remote", "get-url", "origin", cwd=ROOT, capture=True)
    if not CHECKOUT.exists():
        run(git, "clone", "--branch", "main", "--single-branch", remote, str(CHECKOUT), cwd=ROOT)
    if run(git, "status", "--porcelain", capture=True):
        raise RuntimeError(f"The automation checkout has uncommitted files. Review {CHECKOUT} before retrying.")
    # Deliver an earlier committed update before starting another download pass.
    run(git, "push", "--dry-run" if check_only else "--porcelain", "origin", "HEAD:main")
    run(git, "pull", "--ff-only", "origin", "main")
    if check_only:
        print("Preflight passed: checkout clean and GitHub push access available.", flush=True)
        return
    run(sys.executable, "-u", str(ROOT / "scripts/sync_pemons.py"), "--all", "--data-root", str(CHECKOUT), cwd=ROOT)
    run(git, "add", "--", *DATA_FILES)
    diff = subprocess.run([git, "diff", "--cached", "--quiet"], cwd=CHECKOUT)
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


if __name__ == "__main__":
    RUNTIME.mkdir(exist_ok=True)
    logfile = RUNTIME / ("preflight.log" if "--check" in sys.argv else "daily-sync.log")
    with logfile.open("a", encoding="utf-8", buffering=1) as log:
        # Native Git output and child Python output go into the same log.
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        print(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---", flush=True)
        try:
            main(check_only="--check" in sys.argv)
        except Exception:
            import traceback
            traceback.print_exc()
            raise SystemExit(1)
