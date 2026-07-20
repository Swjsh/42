"""Data-loss recovery pass 2 (2026-07-14 stash-drop incident): splice-merge append-only logs.

For each target file:
    merged = stash_version (232a161, full state at 07:15 MT) + bytes appended since the
             07:15 tree-wipe (current content minus the pre-stash HEAD prefix, 05339e3)

core.autocrlf=true on this repo: git blobs (base/stash, via `git show`) are LF-only; the
Windows working tree is CRLF. The prefix/tail comparison is done on LF-normalized copies
so a pure line-ending difference is never mistaken for content divergence (verified
empirically pre-fix: 6/6 sampled "MANUAL_FLAG" files were byte-identical after \r\n->\n
normalization -- zero real divergence). The merged file is written back out as CRLF to
match the existing on-disk convention.

Only merges when current content is a clean append-extension of the pre-stash HEAD
version (LF-normalized prefix check) -- anything rewritten since the wipe is flagged
MANUAL, never touched. Atomic os.replace + re-read retry guards against racing 24/7
writers. Idempotent: once merged, current startswith stash (LF-normalized) and re-runs
log ALREADY_MERGED.

Run AFTER 15:55 ET (SPY engine last tick) on incident day; safe any time after.
"""
import os
import subprocess
import sys
import time

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

MAIN = r"C:/Users/jackw/Desktop/42"
BASE = "05339e3"
STASH = "232a161"
LOG_PATH = os.path.join(MAIN, "automation/state/recovered/splice-log-2026-07-14.txt")

TARGETS = [
    # engine decision ledgers (post-close mandatory)
    "automation/state/core-decisions.jsonl",
    "automation/state/fleet/risky-1/decisions.jsonl",
    "automation/state/fleet/risky-3/decisions.jsonl",
    "automation/state/fleet/safe-3/decisions.jsonl",
    # trade journals of record
    "journal/trades.csv",
    "journal/trades-aggressive.csv",
    # diverged append-only logs (writer appended post-wipe)
    "analysis/backtests/data-versions.jsonl",
    "analysis/prospector/ideas-ledger.jsonl",
    "analysis/trendlines/trendline-log.jsonl",
    "automation/state/conductor-proposals.jsonl",
    "automation/state/cook-queue.jsonl",
    "automation/state/crypto-twin/decisions.jsonl",
    "automation/state/crypto-twin/journal.jsonl",
    "automation/state/crypto-twin/soak-log.jsonl",
    "automation/state/discord-outbox.jsonl",
    "automation/state/manager-log.jsonl",
    "automation/state/minimax-calls.jsonl",
    "automation/state/swarm-calls.jsonl",
    "automation/state/watcher-live-diag.jsonl",
    "automation/state/watcher-observations.jsonl",
    "backtest/autoresearch/_state/overnight_grinder/keepers.jsonl",
    "backtest/autoresearch/_state/overnight_grinder/results.jsonl",
    "backtest/autoresearch/_state/shotgun_scalper_stage3/rejections.jsonl",
    "backtest/autoresearch/_state/shotgun_scalper_stage4/rejections.jsonl",
    "strategy/candidates/_review-log.jsonl",
    "strategy/candidates/_skill-inbox/_correction-queue.jsonl",
]


def git_blob(commit, path):
    r = subprocess.run(
        ["git", "-C", MAIN, "show", f"{commit}:{path}"],
        capture_output=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    return r.stdout if r.returncode == 0 else None


def to_lf(b):
    return b.replace(b"\r\n", b"\n")


def log(lines, msg):
    print(msg)
    lines.append(msg)


def splice_one(path, lines):
    full = os.path.join(MAIN, path)
    stash = git_blob(STASH, path)
    if stash is None:
        log(lines, f"SKIP_NO_STASH_BLOB {path}")
        return
    base = git_blob(BASE, path) or b""
    stash_lf, base_lf = to_lf(stash), to_lf(base)
    for attempt in range(5):
        try:
            with open(full, "rb") as fh:
                cur = fh.read()
        except FileNotFoundError:
            cur = b""
        cur_lf = to_lf(cur)
        if cur_lf.startswith(stash_lf):
            log(lines, f"ALREADY_MERGED {path} ({len(cur)} bytes)")
            return
        if not cur_lf.startswith(base_lf):
            log(lines, f"MANUAL_FLAG {path} (current is not a clean append of pre-stash HEAD, even LF-normalized)")
            return
        tail_lf = cur_lf[len(base_lf):]
        merged_lf = stash_lf + tail_lf
        merged = merged_lf.replace(b"\n", b"\r\n")  # match on-disk CRLF convention (core.autocrlf=true)
        tmp = full + ".splice-tmp"
        with open(tmp, "wb") as fh:
            fh.write(merged)
        with open(full, "rb") as fh:
            cur2 = fh.read()
        if to_lf(cur2) != cur_lf:
            os.remove(tmp)
            time.sleep(1.5)
            continue  # writer raced us between read and replace; retry
        os.replace(tmp, full)
        log(
            lines,
            f"MERGED {path} base={len(base)}b stash={len(stash)}b "
            f"tail={len(tail_lf)}b(lf) -> {len(merged)}b",
        )
        return
    log(lines, f"RETRY_EXHAUSTED {path} (writer too hot; rerun later)")


def main():
    lines = [f"# splice run {time.strftime('%Y-%m-%d %H:%M:%S')} local"]
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    for path in TARGETS:
        try:
            splice_one(path, lines)
        except Exception as exc:  # never let one file abort the batch
            log(lines, f"ERROR {path}: {exc!r}")
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    flagged = [ln for ln in lines if not ln.startswith(("MERGED", "ALREADY_MERGED", "#"))]
    print(f"\nDONE: {len(lines) - 1} targets, {len(flagged)} flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
