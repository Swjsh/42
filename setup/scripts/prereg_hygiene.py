"""Prereg hygiene monitor (B3-monitors, 2026-09-01).

THE GAP THIS CLOSES: pre-registrations (`analysis/recommendations/*prereg*.json`) are
frozen commitments -- a design + pass/fail criterion written BEFORE any outcome is
computed, per the Karpathy eval-first doctrine (OP-11). Nothing previously checked
whether a filed prereg (a) still parses, (b) has gone stale sitting FROZEN/NOT RUN long
past its useful window, or (c) is an ORPHAN -- nothing in the live code even references
it any more, so its "kill criteria" or "arming plan" can never fire. All three are
silent-rot signatures this instrument makes visible.

For every `analysis/recommendations/*prereg*.json`:
  1. Parse it. A malformed file (bad JSON) is reported by name + the parse error --
     never silently skipped.
  2. Read a status/verdict-like field: prefers the `status` key; falls back to the
     first key whose name contains "verdict" (sorted for determinism); `None` if
     neither exists.
  3. Compute age in days from (in priority order): `frozen_at_et`/`frozen_at` field,
     else a trailing `-YYYY-MM-DD` date embedded in the filename, else the file's own
     mtime (flagged in the record as `age_source: "mtime_fallback"` since that is a
     weaker signal -- mtime moves on any touch, not just authoring).
  4. Orphan check: ripgrep (falling back to a pure-Python walk if `rg` is unavailable)
     for the file's stem across setup/, backtest/, automation/ -- ZERO references means
     nothing in the live pipeline can act on this prereg's kill/arm criteria.

Flags a prereg when ALL THREE hold: status text matches FROZEN/NOT RUN/NOT SHIPPED,
age > 14 days, AND it is an orphan. This is the "committed, went stale, nothing can
even act on it" triple -- any one alone is normal (a same-day FROZEN prereg with no
references yet is expected; an old prereg a script still greps for is fine).

Writes analysis/recommendations/prereg-hygiene.json every run (always, for a stable
read surface). Appends ONE consolidated '### BROKEN: prereg-hygiene <ts>' block to
automation/overnight/STATUS.md ONLY when the flagged-file SET changed since the last
run (dedupe -- OP-25 "compound, don't accumulate"; a nightly re-fire of an unchanged
flag set must never spam STATUS.md).

Fail-open throughout: any read/parse error on a NON-prereg input (STATUS.md missing,
prior hygiene json missing/corrupt) degrades gracefully rather than crashing. Pure
stdlib + optional `rg` subprocess. $0 cost.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# OP-27 L41 / C8: this script is scheduled (Gamma_PreregHygiene, 16:58 ET nightly) and
# shells out to ripgrep. Without CREATE_NO_WINDOW that flashes a conhost window on J's
# desktop every night -- the exact popup class that is J's standing #1 priority. Same
# constant/spelling as guard_runner_full.py:59. Guard: test_window_leak_compliance.py
# ::test_no_py_subprocess_missing_creationflags, which caught this.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

REPO = Path(__file__).resolve().parents[2]
RECS_DIR = REPO / "analysis" / "recommendations"
OUT_FILE = RECS_DIR / "prereg-hygiene.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
SEARCH_DIRS = ["setup", "backtest", "automation"]
# EXCLUDED from the orphan-reference scan: this monitor's OWN output. Without this
# exclusion, flagging a prereg writes its filename into STATUS.md (under automation/,
# a SEARCH_DIRS root) -- the next run's scan then finds that mention and reports the
# prereg as "referenced", permanently suppressing the flag after its first firing. A
# real self-inflicted false-negative loop, caught in this task's own live dry run.
EXCLUDE_PATHS = {STATUS_MD.resolve()}

STALE_STATUS_RE = re.compile(r"FROZEN|NOT RUN|NOT SHIPPED", re.IGNORECASE)
FILENAME_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\.json)?$")
AGE_DAYS_THRESHOLD = 14

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now  # noqa: E402
except Exception:  # noqa: BLE001 -- never let a clock import wedge this monitor
    def et_now(now_utc=None):  # type: ignore
        return datetime.now(timezone.utc)


def _et_ts() -> str:
    try:
        return et_now().strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_field(data: dict) -> Optional[str]:
    if "status" in data and isinstance(data["status"], str):
        return data["status"]
    verdict_keys = sorted(k for k in data if "verdict" in k.lower())
    for k in verdict_keys:
        v = data[k]
        if isinstance(v, str):
            return v
        if v is not None:
            return json.dumps(v)[:200]
    return None


def _age_days(path: Path, data: dict) -> tuple[float, str]:
    for key in ("frozen_at_et", "frozen_at"):
        raw = data.get(key)
        if isinstance(raw, str) and raw[:10].count("-") == 2:
            try:
                dt = datetime.strptime(raw[:10], "%Y-%m-%d")
                age = (datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds() / 86400.0
                return age, key
            except ValueError:
                pass
    m = FILENAME_DATE_RE.search(path.stem)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d")
            age = (datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds() / 86400.0
            return age, "filename_date"
        except ValueError:
            pass
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None)
        age = (datetime.now(timezone.utc).replace(tzinfo=None) - mtime).total_seconds() / 86400.0
        return age, "mtime_fallback"
    except OSError:
        return 0.0, "unknown"


# Text-like source/doc extensions this monitor scans for stem references. Excludes data
# ledgers (.jsonl) and any huge state files -- SKIP_OVER_BYTES below is the real guard for
# those, but narrowing extensions first avoids opening the biggest offenders at all.
_SCAN_EXTS = {".py", ".ps1", ".md", ".json", ".vbs", ".txt"}
# Skip any single file bigger than this -- the point is finding CODE/DOC references to a
# prereg filename, never re-deriving results from a multi-hundred-MB data ledger. A prereg
# genuinely referenced only from inside a huge ledger would still be "not referenced by any
# live CODE PATH", which is the actual thing this monitor is checking for.
_SKIP_OVER_BYTES = 2_000_000


def _referenced_stems(stems: list[str]) -> Optional[set]:
    """ONE ripgrep pass over setup/, backtest/, automation/ for ALL prereg stems at once
    (multi -e patterns) -- returns the subset of `stems` that appear at least once.
    Tried first because it is dramatically faster than a Python walk when available.
    Returns None if `rg` itself is unavailable/erroring (e.g. native Windows Python's
    subprocess PATH does not include the Git-Bash-only `rg` this box has) -- callers then
    fall back to `_referenced_stems_python`, a single combined tree walk."""
    if not stems:
        return set()
    args = ["rg", "--fixed-strings", "-o", "--no-filename", "--no-line-number"]
    for p in EXCLUDE_PATHS:
        args += ["--glob", f"!{p.relative_to(REPO).as_posix()}"]
    for s in stems:
        args += ["-e", s]
    args += SEARCH_DIRS
    try:
        result = subprocess.run(
            args, cwd=str(REPO), capture_output=True, text=True, timeout=60,
            creationflags=NO_WINDOW,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode not in (0, 1):  # 0=matches, 1=no matches at all -- both fine
        return None
    hits = set(line.strip() for line in result.stdout.splitlines() if line.strip())
    return {s for s in stems if s in hits}


def _results_index() -> tuple[dict, dict]:
    """One pass over every *.json in RECS_DIR (a bounded recommendations directory, not
    a data ledger) building two lookup maps so a prereg can be matched to an existing
    result file even when its OWN status field never got updated after the run:

    - by_rule_id: rule_id string -> result filename (for result files that self-label
      with the same rule_id the prereg carries)
    - by_registration: prereg filename -> result filename (for result files that name
      the exact prereg they ran via a `registration` field, the older convention)

    Confirmed live 2026-09-02: 5 real preregs (recency-qty-clamp, ladder-vwap,
    pdt-blocked-counterfactual via rule_id; expected-move-gate, morning-gate via
    registration) already have a completed sibling result sitting on disk while their
    OWN `status` field still reads a FROZEN/never-run value -- the PDT one was
    RE-RUN from scratch this same night before the duplication was caught, burning
    real Sonnet compute on an answer that already existed. This is the fix."""
    by_rule_id: dict[str, list[str]] = {}
    by_registration: dict[str, list[str]] = {}
    for f in RECS_DIR.glob("*.json"):
        if f.resolve() == OUT_FILE.resolve():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        rid = data.get("rule_id")
        if isinstance(rid, str) and rid:
            by_rule_id.setdefault(rid, []).append(f.name)
        reg = data.get("registration")
        if isinstance(reg, str) and reg:
            by_registration.setdefault(Path(reg).name, []).append(f.name)
    return by_rule_id, by_registration


def _matching_result_file(prereg_path: Path, data: dict, by_rule_id: dict, by_registration: dict) -> Optional[str]:
    """Best-effort: does this prereg already have a completed result sitting on disk?
    Tries, in order: rule_id match, registration-field match (a result naming this
    exact prereg filename), then the filename heuristic observed across every real
    example found live (strip a leading 'prereg-', append '-results.json'). Every
    branch excludes a self-match -- a prereg carrying its own rule_id (with no
    separate result file) must never be reported as "has a matching result"."""
    own = prereg_path.name
    rid = data.get("rule_id")
    if isinstance(rid, str) and rid in by_rule_id:
        others = [n for n in by_rule_id[rid] if n != own]
        if others:
            return others[0]
    reg_hits = [n for n in by_registration.get(own, []) if n != own]
    if reg_hits:
        return reg_hits[0]
    stem = prereg_path.stem
    bare = stem[len("prereg-"):] if stem.startswith("prereg-") else stem
    candidate = RECS_DIR / f"{bare}-results.json"
    if candidate.exists() and candidate.name != own:
        return candidate.name
    return None


def _referenced_stems_python(stems: list[str]) -> set:
    """Fallback for when `rg` is unavailable: ONE combined tree walk (not one walk per
    stem -- that was measured at multi-minute runtime against this repo's tree) checking
    every stem against every scanned file's content in a single read pass."""
    found: set = set()
    remaining = set(stems)
    for d in SEARCH_DIRS:
        base = REPO / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not remaining:
                return found
            if not p.is_file() or p.suffix not in _SCAN_EXTS:
                continue
            if p.resolve() in EXCLUDE_PATHS:
                continue
            try:
                if p.stat().st_size > _SKIP_OVER_BYTES:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            hit_now = {s for s in remaining if s in text}
            if hit_now:
                found |= hit_now
                remaining -= hit_now
    return found


def scan() -> dict:
    files = sorted(RECS_DIR.glob("*prereg*.json"))
    malformed = []
    parsed: list[tuple[Path, dict]] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError) as e:
            malformed.append({"file": f.name, "error": str(e)})
            continue
        if not isinstance(data, dict):
            malformed.append({"file": f.name, "error": "top-level JSON is not an object"})
            continue
        parsed.append((f, data))

    all_stems = [f.stem for f, _ in parsed]
    referenced = _referenced_stems(all_stems)
    if referenced is None:
        referenced = _referenced_stems_python(all_stems)
    by_rule_id, by_registration = _results_index()

    entries = []
    flagged = []
    has_results_count = 0
    for f, data in parsed:
        status = _status_field(data)
        age_days, age_source = _age_days(f, data)
        orphan = f.stem not in referenced
        result_file = _matching_result_file(f, data, by_rule_id, by_registration)
        has_results = result_file is not None
        if has_results:
            has_results_count += 1
        entry = {
            "file": f.name,
            "status": status,
            "age_days": round(age_days, 1),
            "age_source": age_source,
            "orphan": orphan,
            "has_results_file": has_results,
            "result_file": result_file,
        }
        entries.append(entry)
        is_stale_status = bool(status and STALE_STATUS_RE.search(status))
        # A prereg with a matched result file was demonstrably RUN, regardless of what
        # its own stale status text says -- never flag it as "FROZEN/NOT RUN". This is
        # the fix for the class caught live 2026-09-02: 3 preregs sat FROZEN-labelled
        # with a completed verdict already on disk, and one (PDT counterfactual) was
        # actually RE-RUN from scratch the same night before the duplication was found.
        if is_stale_status and age_days > AGE_DAYS_THRESHOLD and orphan and not has_results:
            flagged.append({**entry, "reason": "FROZEN/NOT RUN + age>14d + orphan"})
    # Reconciliation candidates: a prereg whose OWN status text still reads as never-run
    # even though a result file matched -- these are exactly the entries whose status
    # field is stale bookkeeping, surfaced so the next adjudication pass doesn't have
    # to re-discover this by hand (or worse, re-run the study) the way tonight did.
    stale_status_but_has_results = [
        {"file": e["file"], "status": e["status"], "result_file": e["result_file"]}
        for e in entries
        if e["has_results_file"] and bool(e["status"] and STALE_STATUS_RE.search(e["status"]))
    ]
    return {
        "generated_at_et": _et_ts(),
        "n_total": len(files),
        "n_parsed": len(entries),
        "n_malformed": len(malformed),
        "malformed": malformed,
        "n_flagged": len(flagged),
        "flagged": flagged,
        "n_has_results_file": has_results_count,
        "stale_status_but_has_results": stale_status_but_has_results,
        "entries": entries,
    }


def _prior_flagged_set() -> Optional[set]:
    if not OUT_FILE.exists():
        return None
    try:
        prior = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        return {row["file"] for row in prior.get("flagged", [])}
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None


def _append_status_block(report: dict) -> bool:
    """Append a consolidated BROKEN block to STATUS.md. Returns True if it wrote."""
    ts = report["generated_at_et"]
    lines = [f"### BROKEN: prereg-hygiene {ts}"]
    if report["malformed"]:
        named = ", ".join(m["file"] for m in report["malformed"][:6])
        lines.append(f"- {len(report['malformed'])} MALFORMED prereg file(s): {named}")
    if report["flagged"]:
        lines.append(
            f"- {report['n_flagged']} prereg(s) FROZEN/NOT RUN + age>{AGE_DAYS_THRESHOLD}d + "
            f"orphan (nothing references them):"
        )
        for row in report["flagged"][:10]:
            lines.append(
                f"  - {row['file']} (age {row['age_days']}d via {row['age_source']}, "
                f"status={row['status']!r})"
            )
    block = "\n".join(lines) + "\n"
    try:
        with STATUS_MD.open("a", encoding="utf-8") as fh:
            fh.write("\n" + block)
        return True
    except OSError:
        return False


def main() -> int:
    report = scan()
    prior_set = _prior_flagged_set()
    current_set = {row["file"] for row in report["flagged"]}
    changed = prior_set is None or prior_set != current_set
    try:
        OUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError as e:  # noqa: BLE001 -- never crash on a write failure, just say so
        print(f"WARN: could not write {OUT_FILE}: {e}")
        return 1
    if (report["flagged"] or report["malformed"]) and changed:
        wrote = _append_status_block(report)
        print(f"prereg_hygiene: flagged-set CHANGED, STATUS.md block written={wrote}")
    else:
        print("prereg_hygiene: no change to flagged set (or nothing to flag) -- no STATUS.md append")
    print(f"prereg_hygiene: {report['n_total']} files, {report['n_malformed']} malformed, "
          f"{report['n_flagged']} flagged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
