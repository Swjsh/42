"""Run the production engine for BOTH accounts (Gamma-Safe + Gamma-Risky) over a
window, with each account's real v15.2 params engaged (per OP-16 sim-accuracy gate).

WHY THIS EXISTS
---------------
`run.py` runs ONE config and — critically — leaves profit_lock_mode="fixed" (OFF)
because it never passes params_overrides. v15.2 production uses TRAILING chandelier
profit-lock (params.json v15_profit_lock_mode=trailing, arm +5%, trail 20%). So a
bare `run.py --real-fills` is effectively v14 exits, not v15. This driver injects
each account's params via the canonical params_overrides path (the same translation
the live heartbeat mirror uses) so "what would have happened" is faithful.

ACCOUNT CONFIGS (documented intent, honored here):
  Safe  : ATM strike (offset 0), TP1 +30%, trailing PL, equity from --safe-equity
  Bold  : ITM-2 strike (offset -2), TP1 +75%, trailing PL, equity from --bold-equity
  Both  : BEARISH_REJECTION_RIDE_THE_RIBBON only (OP-16 scope lock; BULLISH_RECLAIM
          is DRAFT and not mapped by _params_to_kwargs anyway).

DISCLOSURE (OP-20): premium_stop_pct = params.json -0.08 (symmetric). CLAUDE.md's
v15 "asymmetric bear -20%" is NOT wired into params.json/backtest — that is a
live↔backtest drift, flagged separately, NOT silently patched (Rule 9).

GUARDRAILS: engine-benefit analysis infra (OP-22). Reads params*.json, never
writes them. Never places orders. Writes only to analysis/backtests/.

USAGE
-----
    python tools/run_dual_account.py \
        --start 2026-05-19 --end 2026-05-29 \
        --safe-equity 747.11 --bold-equity 1535.83 \
        --label-prefix missed_week
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
from pathlib import Path

import pandas as pd

# Import the proven formatting + run helpers from run.py (DRY — identical output schema).
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.orchestrator import run_backtest  # noqa: E402
from lib.repro import compute_run_id, write_registry_entry  # noqa: E402
import run as runmod  # noqa: E402  (backtest/run.py)

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data"
ANALYSIS_DIR = REPO.parent / "analysis" / "backtests"
STATE = REPO.parent / "automation" / "state"


def _load_params() -> dict:
    return json.loads((STATE / "params.json").read_text(encoding="utf-8"))


def _account_overrides(base: dict, overlay_path: Path) -> dict:
    """Merge params.json (base) + an account params file, then resolve the
    strike-selection conflict in favour of the account's DOCUMENTED static
    offset (strip the per-tier table so _params_to_kwargs uses strike_offset_itm).

    NOTE (2026-06-18): the old flat overlays params_safe.json / params_bold.json
    were retired (*.retired-2026-06-18). Live sources are params.json (Safe) and
    aggressive/params.json (Bold). Bold's file is now a FULL params file rather
    than a thin overlay, but the merge (base.update(overlay non-_ keys)) is
    overlay-wins, so passing the full file as the overlay yields the Bold config
    correctly."""
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    merged = copy.deepcopy(base)
    merged.update({k: v for k, v in overlay.items() if not k.startswith("_")})
    # Honour the account's static ATM/ITM intent over the inherited per-tier table.
    merged.pop("v15_strike_offset_per_tier", None)
    return merged


def _locate_csvs(start: str, end: str) -> tuple[Path, Path]:
    for cs, ce in [(start, end), ("2025-01-01", "2026-05-07")]:
        sp = DATA_DIR / f"spy_5m_{cs}_{ce}.csv"
        vp = DATA_DIR / f"vix_5m_{cs}_{ce}.csv"
        if sp.exists() and vp.exists():
            return sp, vp
    raise SystemExit(f"No SPY/VIX csv covers {start}..{end} in {DATA_DIR}")


def _run_account(name: str, overrides: dict, equity: float, args,
                 spy: pd.DataFrame, vix: pd.DataFrame,
                 spy_path: Path, vix_path: Path) -> dict:
    label = f"{args.label_prefix}_{name}"
    result = run_backtest(
        spy, vix,
        start_date=dt.date.fromisoformat(args.start),
        end_date=dt.date.fromisoformat(args.end),
        use_real_fills=True,
        initial_equity=equity,
        params_overrides=overrides,
    )
    out_dir = ANALYSIS_DIR / label
    out_dir.mkdir(parents=True, exist_ok=True)

    # trades.csv (reuse run.py row formatter)
    if result.trades:
        pd.DataFrame([runmod._trade_to_csv_row(t) for t in result.trades]).to_csv(
            out_dir / "trades.csv", index=False)
    else:
        (out_dir / "trades.csv").write_text(
            "date,time_entry,time_exit,setup,contract,strike,qty,entry_px,exit_px,dollar_pnl,exit_reason\n")
    if result.decisions:
        pd.DataFrame([runmod._decision_to_csv_row(d) for d in result.decisions]).to_csv(
            out_dir / "decisions.csv", index=False)

    # summary.md (reuse run.py builder). It reads args.label/start/end/disable_filters/real_fills.
    class _A:  # minimal shim for _compute_summary
        pass
    a = _A()
    a.label = label
    a.start = args.start
    a.end = args.end
    a.disable_filters = []
    a.real_fills = True
    (out_dir / "summary.md").write_text(
        runmod._compute_summary(result.trades, result.decisions, a), encoding="utf-8")

    identity = compute_run_id(spy_path, vix_path)
    total = sum(t.dollar_pnl for t in result.trades)
    nw = sum(1 for t in result.trades if t.dollar_pnl > 0)
    (out_dir / "metadata.json").write_text(json.dumps({
        "label": label, "account": name, "initial_equity": equity,
        "start": args.start, "end": args.end,
        "run_id": identity.run_id, "run_at": dt.datetime.now().isoformat(),
        "trades_fired": len(result.trades), "total_pnl": round(total, 2),
        "winners": nw, "effective_overrides": runmod and {
            "premium_stop_pct": overrides.get("premium_stop_pct"),
            "tp1_premium_pct": overrides.get("tp1_premium_pct"),
            "tp1_qty_fraction": overrides.get("tp1_qty_fraction"),
            "strike_offset_itm": overrides.get("strike_offset_itm"),
            "v15_profit_lock_mode": overrides.get("v15_profit_lock_mode"),
            "v15_profit_lock_threshold_pct": overrides.get("v15_profit_lock_threshold_pct"),
            "v15_profit_lock_trail_pct": overrides.get("v15_profit_lock_trail_pct"),
        },
    }, indent=2))

    # Per-trade + per-day rollup for console.
    per_day: dict[str, float] = {}
    rows = []
    for t in result.trades:
        d = t.entry_time_et.date().isoformat()
        per_day[d] = per_day.get(d, 0.0) + t.dollar_pnl
        rows.append({
            "date": d,
            "entry": t.entry_time_et.strftime("%H:%M"),
            "strike": t.strike,
            "qty": t.qty,
            "entry_px": round(t.entry_premium, 2),
            "pnl": round(t.dollar_pnl, 0),
            "exit": t.exit_reason.value if t.exit_reason else "",
        })
    return {"label": label, "n": len(result.trades), "winners": nw,
            "total": round(total, 2), "per_day": per_day, "rows": rows,
            "out_dir": str(out_dir)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--safe-equity", type=float, default=747.11)
    ap.add_argument("--bold-equity", type=float, default=1535.83)
    ap.add_argument("--label-prefix", default="dual")
    args = ap.parse_args(argv)

    base = _load_params()
    spy_path, vix_path = _locate_csvs(args.start, args.end)
    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)
    spy = spy[(spy["timestamp_et"] >= args.start) & (spy["timestamp_et"] < f"{args.end}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= args.start) & (vix["timestamp_et"] < f"{args.end}T23:59:59")].reset_index(drop=True)

    # Live param sources (the flat params_safe/params_bold overlays were retired
    # 2026-06-18): Safe = params.json, Bold = aggressive/params.json.
    safe_ov = _account_overrides(base, STATE / "params.json")
    bold_ov = _account_overrides(base, STATE / "aggressive" / "params.json")

    print(f"Dual-account run {args.start}..{args.end}  (SPY {len(spy)} / VIX {len(vix)} bars)")
    print(f"  Safe: ATM(off={safe_ov.get('strike_offset_itm')}) TP1 {safe_ov.get('tp1_premium_pct')} "
          f"PL {safe_ov.get('v15_profit_lock_mode')}/{safe_ov.get('v15_profit_lock_trail_pct')} eq ${args.safe_equity}")
    print(f"  Bold: ITM(off={bold_ov.get('strike_offset_itm')}) TP1 {bold_ov.get('tp1_premium_pct')} "
          f"PL {bold_ov.get('v15_profit_lock_mode')}/{bold_ov.get('v15_profit_lock_trail_pct')} eq ${args.bold_equity}")

    safe = _run_account("safe", safe_ov, args.safe_equity, args, spy, vix, spy_path, vix_path)
    bold = _run_account("bold", bold_ov, args.bold_equity, args, spy, vix, spy_path, vix_path)

    for acct in (safe, bold):
        print(f"\n=== {acct['label']} :: {acct['n']} trades, {acct['winners']} W, "
              f"total ${acct['total']} ===")
        for r in acct["rows"]:
            print(f"  {r['date']} {r['entry']} {r['strike']}P x{r['qty']} @${r['entry_px']:.2f} "
                  f"-> ${r['pnl']:+.0f}  {r['exit']}")
        print("  per-day: " + ", ".join(f"{d}:${v:+.0f}" for d, v in sorted(acct["per_day"].items())))

    # Combined JSON for downstream synthesis.
    combined = {"start": args.start, "end": args.end, "safe": safe, "bold": bold}
    (ANALYSIS_DIR / f"{args.label_prefix}_dual_summary.json").write_text(
        json.dumps(combined, indent=2))
    print(f"\nWrote {ANALYSIS_DIR / (args.label_prefix + '_dual_summary.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
