"""multi_scanner_run.py -- run all 5 multi-symbol candidate scanners once, print + persist.

Entry point for multi/lib/scanners.py (read that module's docstring first for the full
"select, never gate" framing and the no-predictive-value disclosure -- both apply here too).

WHAT THIS SCRIPT DOES, nothing more:
  1. Reads automation/state/multi/params.json's `scanners` + `universe` blocks (READ ONLY --
     this script never writes that file; it and multi/lib/creds.py are owned elsewhere).
  2. Resolves this lane's existing paper-account credentials via multi.lib.creds (by
     reference -- never copies or prints a secret; a resolved key is only ever passed to
     scanners.py's HTTP layer as an auth header).
  3. Runs movers / most_actives / gap / news, then composite, via
     scanners.run_all_scanners().
  4. Prints a readable table to stdout and writes the full structured result to
     automation/state/multi/scanner-{YYYY-MM-DD}.json (atomic tmp+replace write).
  5. Exits non-zero ONLY on TOTAL failure -- every one of the 5 scanners came back
     ok=False (network errors, or every one disabled/empty-universe). A scanner that ran
     fine and simply found nothing is NOT a failure; its ok=True, candidates=() row makes
     that visible in both the table and the JSON, distinguishable from an errored one by the
     `error` field and the exit code stays 0.

Run:
    backtest/.venv/Scripts/python.exe setup/scripts/multi_scanner_run.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi.lib import creds  # noqa: E402
from multi.lib import scanners as sc  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 -- best-effort console encoding fix on Windows only
    pass

OUT_DIR = REPO / "automation" / "state" / "multi"


# ------------------------------------------------------------------------------------------
# Output write
# ------------------------------------------------------------------------------------------

def build_snapshot(results: dict[str, sc.ScannerResult], as_of_et: str, account_source: str) -> dict:
    return {
        "_doc": "Multi-symbol scanner snapshot. SELECTION/WATCHLIST OUTPUT ONLY -- never a "
                "trade gate. See multi/lib/scanners.py module docstring (L199 reference) and "
                "the no-predictive-value disclosure before wiring this anywhere.",
        "as_of_et": as_of_et,
        "credential_source": account_source,
        "scanners": {name: sc.scanner_result_to_dict(r) for name, r in results.items()},
    }


def write_snapshot(snapshot: dict, out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = snapshot["as_of_et"][:10]
    out_path = out_dir / f"scanner-{date_str}.json"
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    return out_path


# ------------------------------------------------------------------------------------------
# Readable table
# ------------------------------------------------------------------------------------------

def _status_str(r: sc.ScannerResult) -> str:
    if r.ok and r.error:
        return "OK*"    # ran, but with a partial-failure note (e.g. most_actives half-failed)
    return "OK" if r.ok else "ERROR"


def print_summary_table(results: dict[str, sc.ScannerResult]) -> None:
    print(f"{'scanner':<14}{'status':<8}{'raw':>6}{'kept':>6}  note")
    print("-" * 70)
    for name, r in results.items():
        note = r.error or ""
        print(f"{name:<14}{_status_str(r):<8}{r.raw_count:>6}{len(r.candidates):>6}  {note}")
    print()


def print_movers_table(r: sc.ScannerResult, limit: int = 10) -> None:
    if not r.candidates:
        return
    print(f"-- movers (top {min(limit, len(r.candidates))} of {len(r.candidates)}) --")
    for c in r.candidates[:limit]:
        print(f"  {c.symbol:<8} {c.direction:<7} {c.percent_change:>8.2f}%  price={c.price}")
    print()


def print_gap_table(r: sc.ScannerResult, limit: int = 10) -> None:
    if not r.candidates:
        return
    print(f"-- gap (top {min(limit, len(r.candidates))} of {len(r.candidates)}, by relative volume) --")
    for c in r.candidates[:limit]:
        rv = f"{c.relative_volume:.1f}x" if c.relative_volume is not None else "n/a"
        print(f"  {c.symbol:<8} gap={c.gap_pct:>7.2f}%  rel_vol={rv:<8} "
              f"prior_close={c.prior_close}  current={c.current_price}")
    print()


def print_news_table(r: sc.ScannerResult, limit: int = 10) -> None:
    if not r.candidates:
        return
    print(f"-- news (top {min(limit, len(r.candidates))} of {len(r.candidates)}) --")
    for n in r.candidates[:limit]:
        syms = ",".join(n.symbols) if n.symbols else "(untagged)"
        age = f"{n.age_hours:.1f}h" if n.age_hours is not None else "?"
        print(f"  [{n.category:<10}] {syms:<14} age={age:<6} {n.headline[:80]}")
    print()


def print_composite_table(r: sc.ScannerResult, limit: int = 15) -> None:
    if not r.candidates:
        return
    print(f"-- composite (top {min(limit, len(r.candidates))} of {len(r.candidates)}, by signal_count) --")
    for row in r.candidates[:limit]:
        fired = []
        if row.get("movers"):
            fired.append("movers")
        if row.get("most_actives"):
            fired.append("most_actives")
        if row.get("gap"):
            fired.append("gap")
        if row.get("news"):
            fired.append("news")
        print(f"  {row['symbol']:<8} signal_count={row['signal_count']}  fired=[{','.join(fired)}]")
    print()


# ------------------------------------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------------------------------------

def main() -> int:
    params = creds.load_params()
    try:
        c = creds.resolve(params)
    except creds.CredError as e:
        print(f"multi_scanner_run: FAILED -- cannot resolve credentials: {e}", file=sys.stderr)
        return 1

    now_et = sc.et_now()
    results = sc.run_all_scanners(params, c.key, c.secret, now_et=now_et)

    print(f"multi_scanner_run -- {now_et.isoformat()} -- credential_source={c.source}\n")
    print_summary_table(results)
    print_movers_table(results["movers"])
    print_gap_table(results["gap"])
    print_news_table(results["news"])
    print_composite_table(results["composite"])

    snapshot = build_snapshot(results, as_of_et=now_et.isoformat(), account_source=c.source)
    out_path = write_snapshot(snapshot)
    print(f"wrote {out_path}")

    if all(not r.ok for r in results.values()):
        print("multi_scanner_run: TOTAL FAILURE -- every scanner came back ok=False.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
