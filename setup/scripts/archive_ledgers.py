#!/usr/bin/env python
"""archive_ledgers.py -- DURABLE, OFF-VOLUME, CHECKSUMMED CUSTODY of the irreplaceable book.

WHY THIS EXISTS (2026-08-19, data-custody emergency)
====================================================
The pre-August trading book exists in exactly ONE place: automation/state/fills-ledger.jsonl.
Alpaca's paper API has DELETED its own copy -- verified live this session: a FILL query for
2026-06-25..2026-08-03 returns ZERO rows, while the identical query from 2026-08-03 returns
rows immediately (so it is deletion, not a broken query). 22 of our 35 trading days, 137 of
303 round trips, and -$1,664 of the -$1,805 gross rest on that single file and nothing else.

That file was found with THREE independent protections missing at once:
  1. NOT tracked by git          (`git ls-files` -> no such path)
  2. NOT covered by .gitignore   (`git check-ignore` -> no match)
     => it is an UNTRACKED, UNIGNORED file, so `git clean -fd automation/state/` deletes it.
        Verified: `git clean -nd` prints "Would remove automation/state/fills-ledger.jsonl".
  3. NOT in ledger_archive.py's SOURCES -- the existing daily archive never copied it, and
     that archive prunes at 30 days anyway (its oldest surviving dir is 2026-07-20).

This module is the custody tier the other one is not: OFF-VOLUME, CHECKSUMMED, PERMANENT.

DESIGN
======
* CONTENT-ADDRESSED STORE (git's own idea). Every file's bytes are sha256'd; the blob is
  stored gzipped at blobs/<aa>/<sha256>.gz. The NAME IS THE CHECKSUM, so silent bit-rot is
  detectable by construction -- you cannot corrupt a blob without its name ceasing to match
  its content. Unchanged files cost ZERO additional bytes on later days (dedupe for free),
  which is what makes "keep every daily snapshot forever" affordable for a 68 MB decision log.
* APPEND-ONLY. Blobs are written once and never rewritten or deleted. Every capture ever run
  appends one line to captures.jsonl. A re-run on the same day cannot destroy an earlier
  capture's data -- the earlier manifest's blobs are all still referenced and still present.
* POINT-IN-TIME CONSISTENCY. Live files are being APPENDED TO while this runs. Each source is
  read into memory ONCE; that exact byte string is what gets hashed AND what gets stored. We
  never hash one read and store another, so a concurrent append can only ever truncate the
  snapshot to an earlier honest prefix -- it can never produce a manifest whose checksum
  disagrees with its blob.
* VERIFY BY READING BACK. After writing, every blob is re-read FROM DISK, decompressed, and
  re-hashed; the fills ledger is additionally re-parsed and its FIFO P&L recomputed from the
  ARCHIVED copy. An archive nobody has read back is not a backup.
* SECRETS NEVER ENTER THE ARCHIVE. .mcp.json / secrets.json / *.pem / *.key / .alpaca-keys are
  hard-denied by _assert_not_secret() -- an archive on a second volume is a second place for a
  credential to leak from. A deny-list hit is a CRASH, never a skip.

WHERE IT LIVES, AND WHY (the deliberate choice)
===============================================
Primary: D:\\GammaArchive  -- a DIFFERENT PHYSICAL VOLUME from the repo.
  C: is 930.7 GB with only ~54.8 GB free and holds the repo itself. An archive that lives
  beside the thing it protects is not a backup: the same `git clean -xfd`, the same `rm`, the
  same C: failure, the same ransomware pass takes both copies at once. D: is a Fixed NTFS
  volume, 931.4 GB with 847.8 GB free, already J's backup drive (D:\\SwjshAK-Backups). At the
  measured gzipped incremental this stores centuries of book history in free space that
  already exists. Storage was never the constraint -- colocation was.
Fallback: <repo>/automation/archive/custody -- used ONLY if the primary is unreachable, and
  it is reported LOUDLY as status=DEGRADED with the reason. It is NOT a silent fallback: a
  same-volume copy still beats no copy, but the report must never call it healthy.
Override: set GAMMA_ARCHIVE_ROOT to relocate (e.g. to an external/offsite mount).

REMAINING GAP, STATED PLAINLY: D: and C: are two disks in ONE machine. This protects against
accidental deletion, git accidents, and single-disk failure. It does NOT protect against
fire/theft/ransomware taking the whole box. Offsite replication is the next tier and is NOT
implemented here (it needs a destination J chooses).

USAGE
  python setup/scripts/archive_ledgers.py                   # capture + verify (the daily fire)
  python setup/scripts/archive_ledgers.py --restore-drill    # capture, then prove a rebuild
  python setup/scripts/archive_ledgers.py --restore-drill --deep   # ...via the REAL builder
  python setup/scripts/archive_ledgers.py --restore <date> --dest <dir>   # materialize a day
  python setup/scripts/archive_ledgers.py --status           # read the last integrity report
  python setup/scripts/archive_ledgers.py --strict           # nonzero exit on DEGRADED/FAILED

Exit code is 0 by default even on trouble (OP-25/C7 fail-open: never crash the scheduled
task), but the outcome is ALWAYS printed and ALWAYS written to integrity-report.json. Use
--strict from guards/CI where a nonzero exit is wanted.

Scheduled via Gamma_LedgerCustody (install-ledger-custody.ps1).
Guard: backtest/tests/test_archive_ledgers.py
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------- paths (C9: anchor to __file__)
REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = Path(__file__).resolve().parent
for _p in (_SCRIPTS, REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now, et_today_str  # noqa: E402
import fills_fifo  # noqa: E402

PRIMARY_ROOT = Path(r"D:\GammaArchive")
FALLBACK_ROOT = REPO / "automation" / "archive" / "custody"

SCHEMA = 1

# The 5 arms whose real fills constitute the book. safe-1 is EXCLUDED from the P&L
# semantics for the same reason trade_matrix_build.py excludes it: retired 2026-07-11,
# its broker account was reassigned to safe-2, so counting it double-counts one account.
# (Its ROWS are still archived -- exclusion is a reporting choice, never a custody choice.)
ACTIVE_ARMS = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")

# THE file this whole module exists for. Its absence is a FAILED run, not a skip.
CRITICAL = "automation/state/fills-ledger.jsonl"

# Repo-relative source specs. A spec containing '*' is a glob; a spec without one is a
# literal path. Missing literals are recorded in `missing[]` with a reason -- never
# defaulted, never silently dropped (an absent file is REPORTED absent).
SOURCE_SPECS: tuple[str, ...] = (
    # -- the irreplaceable book ------------------------------------------------
    "automation/state/fills-ledger.jsonl",
    "automation/state/order-intents.jsonl",      # concurrent lane; archived once it exists
    # -- decision provenance (what the engine saw when it fired) ---------------
    "automation/state/core-decisions.jsonl",
    "automation/state/fleet/decisions/*.jsonl",
    "automation/state/fleet/*/decisions.jsonl",
    # -- per-arm exit / risk state --------------------------------------------
    "automation/state/fleet/*/exit-state.json",
    "automation/state/fleet/*/circuit-breaker.json",
    "automation/state/fleet/*/settlement-ledger.json",
    "automation/state/fleet/*/entry-claim.json",
    "automation/state/fleet/*/flat-streak.json",
    "automation/state/fleet/accounts.json",
    # -- levels history --------------------------------------------------------
    "automation/state/key-levels.json",
    "journal/key-levels-archive/*",
    # -- journals + the canonical derived table --------------------------------
    "journal/trades.csv",
    "journal/trades-aggressive.csv",
    "analysis/recommendations/trade-matrix.json",
    # -- option bars that make MAE/MFE reproducible offline --------------------
    "backtest/data/opra_1m_cache/*",
)

# Hard deny-list. A match is a CRASH, not a skip: the whole point of a second volume is
# that it must never become a second place a credential can leak from.
SECRET_MARKERS = (
    ".mcp.json", "secrets.json", ".alpaca-keys", ".openrouter.key",
    ".discord-config.json", ".heartbeat-api-key",
)
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


class SecretInArchiveError(RuntimeError):
    """Raised when a source path looks like a credential. Never caught, never downgraded."""


def _assert_not_secret(rel: str) -> None:
    low = rel.lower()
    name = low.rsplit("/", 1)[-1]
    for marker in SECRET_MARKERS:
        if marker in name:
            raise SecretInArchiveError(f"refusing to archive credential-bearing path: {rel}")
    for suf in SECRET_SUFFIXES:
        if name.endswith(suf):
            raise SecretInArchiveError(f"refusing to archive credential-bearing path: {rel}")


# ---------------------------------------------------------------- archive root selection
def resolve_archive_root(explicit: Optional[str] = None) -> tuple[Path, str, str]:
    """Return (root, status, reason). status is HEALTHY (off-volume) or DEGRADED (same volume).

    NEVER silently falls back: a fallback always carries status=DEGRADED plus the OS error
    that caused it, so the integrity report can never describe a same-volume copy as healthy.
    """
    candidate = Path(explicit or os.environ.get("GAMMA_ARCHIVE_ROOT") or PRIMARY_ROOT)
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        FALLBACK_ROOT.mkdir(parents=True, exist_ok=True)
        return (FALLBACK_ROOT, "DEGRADED",
                f"primary archive root {candidate} unwritable ({exc}); fell back to "
                f"{FALLBACK_ROOT}, which is ON THE SAME VOLUME AS THE REPO and therefore "
                f"does NOT protect against repo-level deletion or C: failure")
    same_volume = str(candidate.resolve().drive).upper() == str(REPO.resolve().drive).upper()
    if same_volume:
        return (candidate, "DEGRADED",
                f"archive root {candidate} is on the SAME VOLUME as the repo ({REPO.drive}) -- "
                f"a single disk failure or `git clean -xfd` can take both copies")
    return (candidate, "HEALTHY",
            f"off-volume archive root {candidate} (repo lives on {REPO.drive})")


# ---------------------------------------------------------------- source resolution
def resolve_sources(repo: Path, specs: Optional[Iterable[str]] = None) -> tuple[list[str], list[dict]]:
    """Expand `specs` to (present_rel_paths_sorted, missing_records).

    Globs that match nothing are recorded as missing with reason 'glob matched nothing' --
    an empty glob is information, not a no-op to swallow.

    `specs` defaults to the MODULE-LEVEL SOURCE_SPECS read at CALL time, deliberately not
    as a default argument value: a default would freeze the tuple at import time, so a
    guard that patches SOURCE_SPECS to prove this function reacts to it would silently
    keep testing the original list and pass for the wrong reason (caught in RED-proofing,
    2026-08-19 -- the exact shape of a guard that can never go red).
    """
    if specs is None:
        specs = SOURCE_SPECS
    present: set[str] = set()
    missing: list[dict] = []
    for spec in specs:
        if "*" in spec:
            hits = [p for p in repo.glob(spec) if p.is_file()]
            if not hits:
                missing.append({"spec": spec, "reason": "glob matched nothing"})
                continue
            for p in hits:
                present.add(p.relative_to(repo).as_posix())
        else:
            p = repo / spec
            if p.is_file():
                present.add(spec)
            else:
                missing.append({"spec": spec, "reason": "not found"})
    for rel in present:
        _assert_not_secret(rel)
    return sorted(present), missing


# ---------------------------------------------------------------- blob store
def blob_rel(sha: str) -> str:
    return f"blobs/{sha[:2]}/{sha}.gz"


def write_blob(root: Path, sha: str, data: bytes) -> tuple[str, bool]:
    """Store `data` at its content address. Returns (blob_rel, newly_written).

    Idempotent AND append-only: if the blob already exists its bytes are by definition the
    same content (the name IS the hash), so we never rewrite it. Written via a temp file +
    atomic replace so an interrupted run can never leave a half-written blob at a name that
    claims to be a complete one.
    """
    rel = blob_rel(sha)
    dest = root / rel
    if dest.exists():
        return rel, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + f".tmp{os.getpid()}")
    # mtime=0 -> byte-deterministic output for identical input (nice-to-have, not relied on).
    tmp.write_bytes(gzip.compress(data, compresslevel=6, mtime=0))
    os.replace(tmp, dest)
    return rel, True


def read_blob(root: Path, sha: str) -> bytes:
    return gzip.decompress((root / blob_rel(sha)).read_bytes())


# ---------------------------------------------------------------- semantics
def ledger_semantics(ledger_path: Path) -> dict:
    """FIFO round-trip count + gross P&L per active arm, computed from `ledger_path`.

    Delegates to automation/state/fleet/fills_fifo.py -- the ONE FIFO implementation in the
    repo (C14: never a second copy that can drift from the first).
    """
    per_arm: dict[str, dict] = {}
    total_trips = 0
    total_gross = 0.0
    for arm in ACTIVE_ARMS:
        trips = fills_fifo.mine_real_arm_fills(arm, ledger_path)
        gross = round(sum(float(t["real_pnl"]) for t in trips), 2)
        per_arm[arm] = {"round_trips": len(trips), "gross": gross}
        total_trips += len(trips)
        total_gross += gross
    return {
        "arms_counted": list(ACTIVE_ARMS),
        "excluded_arms": ["safe-1"],
        "round_trips": total_trips,
        "gross_pnl": round(total_gross, 2),
        "per_arm": per_arm,
    }


# ---------------------------------------------------------------- capture
def capture(repo: Path, root: Path, *, today: str, now_iso: str) -> dict:
    """Read every source ONCE, hash those exact bytes, store them, return the manifest."""
    present, missing = resolve_sources(repo)
    files: list[dict] = []
    errors: list[dict] = []
    new_blobs = 0
    total_bytes = 0

    for rel in present:
        src = repo / rel
        try:
            data = src.read_bytes()            # ONE read -- this byte string IS the snapshot
        except OSError as exc:
            errors.append({"rel": rel, "error": str(exc)})
            continue
        sha = hashlib.sha256(data).hexdigest()
        try:
            brel, is_new = write_blob(root, sha, data)
        except OSError as exc:
            errors.append({"rel": rel, "error": f"blob write failed: {exc}"})
            continue
        new_blobs += int(is_new)
        total_bytes += len(data)
        files.append({
            "rel": rel,
            "sha256": sha,
            "bytes": len(data),
            "lines": data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0),
            "blob": brel,
            "src_mtime_utc": datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
        })

    critical_ok = any(f["rel"] == CRITICAL for f in files)
    return {
        "schema": SCHEMA,
        "snapshot_date_et": today,
        "captured_at_et": now_iso,
        "repo_root": str(repo),
        "archive_root": str(root),
        "critical_source": CRITICAL,
        "critical_present": critical_ok,
        "file_count": len(files),
        "total_source_bytes": total_bytes,
        "new_blobs_written": new_blobs,
        "files": files,
        "missing": missing,
        "errors": errors,
    }


# ---------------------------------------------------------------- verify (read it back)
def verify_manifest(root: Path, manifest: dict, *, repo: Optional[Path] = None) -> dict:
    """Re-read EVERY blob from disk, decompress, re-hash, and compare to the manifest.

    Then re-parse the archived fills ledger and recompute its FIFO P&L from the ARCHIVED
    bytes -- if `repo` is given, that result is also compared against the same computation
    run on the LIVE file, so a semantic drift is caught, not just a byte drift.
    """
    checked = 0
    bad: list[dict] = []
    for f in manifest["files"]:
        try:
            data = read_blob(root, f["sha256"])
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            bad.append({"rel": f["rel"], "problem": f"blob unreadable: {exc}"})
            continue
        checked += 1
        actual = hashlib.sha256(data).hexdigest()
        if actual != f["sha256"]:
            bad.append({"rel": f["rel"], "problem": "SHA MISMATCH (corruption)",
                        "expected": f["sha256"], "actual": actual})
        elif len(data) != f["bytes"]:
            bad.append({"rel": f["rel"], "problem": "size mismatch",
                        "expected": f["bytes"], "actual": len(data)})

    out: dict[str, Any] = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "blobs_checked": checked,
        "blobs_expected": len(manifest["files"]),
        "corruption": bad,
    }

    entry = next((f for f in manifest["files"] if f["rel"] == CRITICAL), None)
    if entry is None:
        out["semantics"] = {"status": "MISSING",
                            "reason": f"{CRITICAL} absent from this snapshot"}
        out["status"] = "FAILED"
        return out

    # If the critical blob is already known unreadable/corrupt, say so plainly -- do NOT
    # attempt the semantic re-read, which would raise out of a verification routine whose
    # entire job is to REPORT corruption rather than die on it.
    if any(c["rel"] == CRITICAL for c in bad):
        out["semantics"] = {
            "status": "UNREADABLE",
            "reason": f"{CRITICAL} blob failed byte-level verification; "
                      f"P&L cannot be recomputed from a corrupt archive copy",
        }
        out["status"] = "FAILED"
        return out

    try:
        with tempfile.TemporaryDirectory(prefix="gamma-verify-") as td:
            mat = Path(td) / "fills-ledger.jsonl"
            mat.write_bytes(read_blob(root, entry["sha256"]))
            archived = ledger_semantics(mat)
    except (OSError, EOFError, gzip.BadGzipFile, ValueError) as exc:
        out["semantics"] = {"status": "UNREADABLE",
                            "reason": f"could not re-read {CRITICAL} from archive: {exc}"}
        out["status"] = "FAILED"
        return out
    archived["rows"] = entry["lines"]
    sem: dict[str, Any] = {"from_archive": archived}

    if repo is not None:
        live_path = repo / CRITICAL
        if live_path.is_file():
            live = ledger_semantics(live_path)
            sem["from_live"] = live
            # The live file may have grown since capture (mid-session appends). A snapshot
            # that is a PREFIX of live is correct; a snapshot that DISAGREES is corruption.
            sem["agrees_with_live"] = (
                archived["round_trips"] == live["round_trips"]
                and abs(archived["gross_pnl"] - live["gross_pnl"]) < 0.005
            )
            sem["note"] = ("live may have grown since capture -- a prefix snapshot is correct; "
                           "only a snapshot that cannot be re-read or re-parsed is a failure")
        else:
            sem["from_live"] = None
            sem["note"] = "live file not present to compare against"
    out["semantics"] = sem
    out["status"] = "FAILED" if bad else "OK"
    return out


# ---------------------------------------------------------------- restore
def latest_snapshot(root: Path) -> Optional[str]:
    snaps = root / "snapshots"
    if not snaps.is_dir():
        return None
    days = sorted(p.name for p in snaps.iterdir()
                  if p.is_dir() and (p / "manifest.json").is_file())
    return days[-1] if days else None


def load_manifest(root: Path, date_str: str) -> dict:
    return json.loads((root / "snapshots" / date_str / "manifest.json").read_text(encoding="utf-8"))


def restore(root: Path, date_str: str, dest: Path, *, only: Optional[set[str]] = None) -> dict:
    """Materialize a snapshot's files under `dest`, preserving repo-relative layout.

    Every restored file is re-hashed after decompression; a mismatch is an itemized failure,
    never a silent partial restore.
    """
    manifest = load_manifest(root, date_str)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    failed: list[dict] = []
    for f in manifest["files"]:
        if only is not None and f["rel"] not in only:
            continue
        try:
            data = read_blob(root, f["sha256"])
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            failed.append({"rel": f["rel"], "error": str(exc)})
            continue
        if hashlib.sha256(data).hexdigest() != f["sha256"]:
            failed.append({"rel": f["rel"], "error": "sha mismatch on restore"})
            continue
        target = dest / f["rel"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(f["rel"])
    return {"snapshot": date_str, "dest": str(dest), "restored": len(written),
            "failed": failed, "files": written}


# ---------------------------------------------------------------- the restore drill
# Code is NOT archived here on purpose: it lives in git and on the public GitHub remote, so
# it is recoverable by definition. The drill therefore proves the honest claim -- "archived
# DATA + git-recoverable CODE rebuilds the book" -- and copies the code in explicitly so it
# is obvious which half came from where.
DRILL_CODE = (
    "setup/scripts/trade_matrix_build.py",
    "setup/scripts/cost_model.py",
    "setup/scripts/et_clock.py",
    "automation/state/fleet/fills_fifo.py",
)


def restore_drill(root: Path, repo: Path, *, deep: bool = False,
                  date_str: Optional[str] = None) -> dict:
    """Rebuild the book FROM THE ARCHIVE and compare against the live canonical table.

    Shallow: FIFO round-trip count + gross P&L from the restored fills ledger.
    Deep (--deep): additionally runs the REAL trade_matrix_build.py inside the restore tree
    (its REPO is Path(__file__).parents[2], so copying it into the tree repoints every input
    at archived data) and compares row_count + totals.gross.
    """
    date_str = date_str or latest_snapshot(root)
    if date_str is None:
        return {"status": "FAILED", "reason": "no snapshot in archive to restore from"}

    result: dict[str, Any] = {"snapshot": date_str, "deep": deep}
    with tempfile.TemporaryDirectory(prefix="gamma-restore-drill-") as td:
        tree = Path(td) / "restored-repo"
        rest = restore(root, date_str, tree)
        result["restore"] = {"restored": rest["restored"], "failed": rest["failed"]}
        if rest["failed"]:
            result["status"] = "FAILED"
            result["reason"] = "restore reported failed files"
            return result

        ledger = tree / CRITICAL
        if not ledger.is_file():
            result["status"] = "FAILED"
            result["reason"] = f"{CRITICAL} not present in restored tree"
            return result
        result["rebuilt_from_archive"] = ledger_semantics(ledger)

        # The comparison anchor: the LIVE canonical table (never a hardcoded constant --
        # the book grows, and a frozen number would silently rot into a false pass).
        tm = repo / "analysis" / "recommendations" / "trade-matrix.json"
        if tm.is_file():
            live_tm = json.loads(tm.read_text(encoding="utf-8"))
            result["live_canonical"] = {"row_count": live_tm["row_count"],
                                        "gross": live_tm["totals"]["gross"]}
        else:
            result["live_canonical"] = None

        if deep:
            missing_code = None
            for rel in DRILL_CODE:
                src = repo / rel
                if not src.is_file():
                    missing_code = rel
                    break
                tgt = tree / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, tgt)
            if missing_code:
                result["deep_build"] = {"status": "FAILED",
                                        "reason": f"missing code {missing_code}"}
            else:
                out_json = Path(td) / "rebuilt-trade-matrix.json"
                proc = subprocess.run(
                    [sys.executable, str(tree / "setup/scripts/trade_matrix_build.py"),
                     "--no-fetch", "--no-broker", "--out", str(out_json)],
                    capture_output=True, text=True, timeout=600,
                )
                if proc.returncode != 0 or not out_json.is_file():
                    result["deep_build"] = {"status": "FAILED", "rc": proc.returncode,
                                            "stderr": proc.stderr[-1500:]}
                else:
                    rebuilt = json.loads(out_json.read_text(encoding="utf-8"))
                    result["deep_build"] = {
                        "status": "OK",
                        "row_count": rebuilt["row_count"],
                        "gross": rebuilt["totals"]["gross"],
                        "net": rebuilt["totals"]["net"],
                        "trading_days": rebuilt["trading_days"],
                        "crosscheck_vs_fills_fifo": rebuilt["crosscheck_vs_fills_fifo"]["status"],
                        "path_coverage": rebuilt["path_coverage"],
                    }

    # ---- verdict -------------------------------------------------------------
    checks: list[dict] = []
    lc = result.get("live_canonical")
    rb = result["rebuilt_from_archive"]
    if lc:
        checks.append({"check": "fifo_round_trips_vs_canonical",
                       "expected": lc["row_count"], "actual": rb["round_trips"],
                       "pass": rb["round_trips"] == lc["row_count"]})
        checks.append({"check": "fifo_gross_vs_canonical",
                       "expected": lc["gross"], "actual": rb["gross_pnl"],
                       "pass": abs(rb["gross_pnl"] - lc["gross"]) < 0.005})
    db = result.get("deep_build")
    if db and db.get("status") == "OK" and lc:
        checks.append({"check": "rebuilt_matrix_row_count",
                       "expected": lc["row_count"], "actual": db["row_count"],
                       "pass": db["row_count"] == lc["row_count"]})
        checks.append({"check": "rebuilt_matrix_gross",
                       "expected": lc["gross"], "actual": db["gross"],
                       "pass": abs(db["gross"] - lc["gross"]) < 0.005})
    elif db and db.get("status") != "OK":
        checks.append({"check": "deep_build_ran", "expected": "OK",
                       "actual": db.get("status"), "pass": False})
    result["checks"] = checks
    if not checks:
        result["status"] = "INCONCLUSIVE"
        result["reason"] = "no canonical trade-matrix.json to compare against"
    else:
        result["status"] = "PASS" if all(c["pass"] for c in checks) else "FAILED"
    return result


# ---------------------------------------------------------------- report
def write_integrity_report(root: Path, payload: dict) -> Path:
    p = root / "integrity-report.json"
    p.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return p


def _append_capture_log(root: Path, record: dict) -> None:
    """Append-only audit trail of every capture ever run (tiny, never rewritten)."""
    with (root / "captures.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


REPO_STATUS = "automation/state/archive-custody-status.json"


def _write_repo_status(repo: Path, payload: dict) -> None:
    """Mirror a ONE-SCREEN summary back into the repo.

    The real report lives on D:, which no other session (or dashboard, or health check)
    is going to reach for. A custody archive whose health is only visible on the backup
    volume is invisible exactly when someone needs to notice it went stale -- so the
    status, not the data, comes home to the shared surface.
    """
    d = payload.get("restore_drill") or {}
    summary = {
        "_doc": "Status ONLY -- the archive itself lives at archive_root. "
                "Written by setup/scripts/archive_ledgers.py.",
        "status": payload["status"],
        "archive_root": payload["archive_root"],
        "archive_root_status": payload["archive_root_status"],
        "snapshot_date_et": payload["snapshot_date_et"],
        "captured_at_et": payload["captured_at_et"],
        "files_archived": payload["files_archived"],
        "source_bytes": payload["source_bytes"],
        "snapshots_retained": payload["snapshot_count"],
        "critical_present": payload["critical_present"],
        "blobs_verified": payload["verify"]["blobs_checked"],
        "corruption_count": len(payload["verify"]["corruption"]),
        "restore_drill_status": d.get("status"),
        "restore_drill_checks": d.get("checks"),
    }
    try:
        out = repo / REPO_STATUS
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    except OSError as exc:
        print(f"[archive] WARN could not write {REPO_STATUS}: {exc}")


README = r"""# Gamma durable archive

Content-addressed, checksummed, append-only custody of Project Gamma's irreplaceable
trading state. Written by `setup/scripts/archive_ledgers.py` (repo: Swjsh/42).

    blobs/<aa>/<sha256>.gz      immutable, gzipped; THE FILENAME IS THE SHA256 OF THE
                                UNCOMPRESSED CONTENT, so corruption is detectable
    snapshots/<YYYY-MM-DD>/manifest.json   that day's file list -> sha256 + size + lines
    snapshots/<YYYY-MM-DD>/verify.json     read-back proof for that day
    captures.jsonl              one append-only line per capture ever run
    integrity-report.json       latest run's status

## Restore without the repo

    python archive_ledgers.py --restore 2026-08-20 --dest C:\restored

Or by hand, with nothing but a Python REPL:

    import gzip, json, pathlib
    m = json.load(open('snapshots/2026-08-20/manifest.json'))
    for f in m['files']:
        blob = pathlib.Path('blobs')/f['sha256'][:2]/(f['sha256']+'.gz')
        out  = pathlib.Path('restored')/f['rel']
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(gzip.decompress(blob.read_bytes()))

The format is deliberately boring: gzip + sha256 + JSON, all stdlib. A crisis is the
wrong time to need a bespoke tool.

NO CREDENTIALS ARE STORED HERE. `.mcp.json`, `secrets.json`, `*.pem`, `*.key` and
friends are hard-denied by the writer.
"""


# ---------------------------------------------------------------- main
def run_capture(*, repo: Path = REPO, explicit_root: Optional[str] = None,
                drill: bool = False, deep: bool = False) -> dict:
    root, root_status, root_reason = resolve_archive_root(explicit_root)
    (root / "README.md").write_text(README, encoding="utf-8")

    today = et_today_str()
    now_iso = et_now().isoformat(timespec="seconds")

    manifest = capture(repo, root, today=today, now_iso=now_iso)
    snap_dir = root / "snapshots" / today
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    verify = verify_manifest(root, manifest, repo=repo)
    (snap_dir / "verify.json").write_text(json.dumps(verify, indent=1), encoding="utf-8")

    if not manifest["critical_present"] or verify["status"] != "OK" or manifest["errors"]:
        status = "FAILED"
    else:
        status = root_status  # HEALTHY, or DEGRADED when the archive is same-volume

    payload: dict[str, Any] = {
        "status": status,
        "archive_root": str(root),
        "archive_root_status": root_status,
        "archive_root_reason": root_reason,
        "snapshot_date_et": today,
        "captured_at_et": now_iso,
        "files_archived": manifest["file_count"],
        "source_bytes": manifest["total_source_bytes"],
        "new_blobs_written": manifest["new_blobs_written"],
        "critical_present": manifest["critical_present"],
        "missing": manifest["missing"],
        "errors": manifest["errors"],
        "verify": verify,
        "snapshot_count": (len(list((root / "snapshots").iterdir()))
                           if (root / "snapshots").is_dir() else 0),
        "retention": "PERMANENT -- snapshots are never pruned; unchanged files cost 0 extra bytes",
    }
    if drill:
        payload["restore_drill"] = restore_drill(root, repo, deep=deep)
        if payload["restore_drill"]["status"] != "PASS":
            payload["status"] = "FAILED"

    write_integrity_report(root, payload)
    _write_repo_status(repo, payload)
    _append_capture_log(root, {
        "captured_at_et": now_iso, "snapshot_date_et": today, "status": payload["status"],
        "files": manifest["file_count"], "new_blobs": manifest["new_blobs_written"],
        "source_bytes": manifest["total_source_bytes"],
        "critical_present": manifest["critical_present"],
    })
    return payload


def _print(payload: dict) -> None:
    print(f"[archive] status={payload['status']}  root={payload['archive_root']} "
          f"({payload['archive_root_status']})")
    print(f"[archive] {payload['archive_root_reason']}")
    print(f"[archive] snapshot {payload['snapshot_date_et']}: {payload['files_archived']} files, "
          f"{payload['source_bytes']:,} source bytes, {payload['new_blobs_written']} new blobs, "
          f"{payload['snapshot_count']} snapshots retained")
    v = payload["verify"]
    print(f"[verify ] read back {v['blobs_checked']}/{v['blobs_expected']} blobs, "
          f"corruption={len(v['corruption'])}")
    sem = v.get("semantics", {})
    fa = sem.get("from_archive")
    if fa:
        print(f"[verify ] archived ledger re-parsed: {fa['rows']} rows -> "
              f"{fa['round_trips']} round trips, gross ${fa['gross_pnl']:,.2f}"
              + (f"  (agrees with live: {sem.get('agrees_with_live')})"
                 if "agrees_with_live" in sem else ""))
    if not payload["critical_present"]:
        print(f"[archive] !! CRITICAL SOURCE MISSING: {CRITICAL} -- the book was NOT archived")
    for m in payload["missing"]:
        print(f"[archive] MISSING {m['spec']} ({m['reason']})")
    for e in payload["errors"]:
        print(f"[archive] ERROR {e}")
    for c in v["corruption"]:
        print(f"[verify ] CORRUPTION {c}")
    d = payload.get("restore_drill")
    if d:
        print(f"[drill  ] status={d['status']} snapshot={d.get('snapshot')} deep={d.get('deep')}")
        rb = d.get("rebuilt_from_archive")
        if rb:
            print(f"[drill  ] FIFO from archive: {rb['round_trips']} round trips, "
                  f"gross ${rb['gross_pnl']:,.2f}")
        db = d.get("deep_build")
        if db and db.get("status") == "OK":
            print(f"[drill  ] rebuilt matrix: {db['row_count']} rows, gross ${db['gross']:,.2f}, "
                  f"net ${db['net']:,.2f}, {db['trading_days']} days, "
                  f"crosscheck={db['crosscheck_vs_fills_fifo']}")
        elif db:
            print(f"[drill  ] deep build FAILED: {db}")
        for c in d.get("checks", []):
            flag = "PASS" if c["pass"] else "FAIL"
            print(f"[drill  ] {flag} {c['check']}: expected {c['expected']} got {c['actual']}")
        if d.get("reason"):
            print(f"[drill  ] reason: {d['reason']}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Durable checksummed archive of Gamma's book.")
    ap.add_argument("--root", help="archive root override (default D:\\GammaArchive)")
    ap.add_argument("--restore-drill", action="store_true", help="capture, then prove a rebuild")
    ap.add_argument("--deep", action="store_true", help="drill via the real trade_matrix_build")
    ap.add_argument("--restore", metavar="DATE", help="materialize a snapshot (YYYY-MM-DD)")
    ap.add_argument("--dest", help="destination dir for --restore")
    ap.add_argument("--status", action="store_true", help="print the last integrity report")
    ap.add_argument("--strict", action="store_true", help="exit nonzero on DEGRADED/FAILED")
    args = ap.parse_args(argv)

    try:
        if args.restore:
            root, _, _ = resolve_archive_root(args.root)
            if not args.dest:
                print("ERROR --restore requires --dest")
                return 2
            res = restore(root, args.restore, Path(args.dest))
            print(f"[restore] snapshot={res['snapshot']} -> {res['dest']}: "
                  f"{res['restored']} files, {len(res['failed'])} failed")
            for f in res["failed"]:
                print(f"[restore] FAILED {f}")
            return 1 if res["failed"] else 0

        if args.status:
            root, _, _ = resolve_archive_root(args.root)
            p = root / "integrity-report.json"
            if not p.is_file():
                print(f"no integrity report at {p} -- archive has never run")
                return 1
            payload = json.loads(p.read_text(encoding="utf-8"))
            _print(payload)
            return 1 if (args.strict and payload["status"] != "HEALTHY") else 0

        payload = run_capture(repo=REPO, explicit_root=args.root,
                              drill=args.restore_drill, deep=args.deep)
        _print(payload)
        if args.strict and payload["status"] != "HEALTHY":
            return 1
        return 0
    except SecretInArchiveError:
        raise  # never swallow: a credential nearly entered the archive
    except Exception as exc:  # noqa: BLE001 -- fail-open per OP-25/C7, but NEVER silently
        print(f"[archive] ERROR archive_ledgers.main() failed: {exc!r}")
        return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
