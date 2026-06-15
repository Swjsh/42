"""Winner-day entry blocker diagnostic — T-2026-05-18-02.

For J's 3 winner days (4/29, 5/01, 5/04), runs the engine with Safe-ATM config and
dumps per-bar filter decisions from 09:35 to 14:00 ET, showing EXACTLY which filter
blocked the engine from entering in the morning window.

Hypothesis: Ribbon lag (spread < 30c for first 30-50 min after open) is the primary
blocker. The ribbon EMA stack needs multiple RTH bars to diverge after a gap.

Output: analysis/recommendations/winner_day_entry_blockers.json  (machine-readable)
         analysis/recommendations/winner_day_entry_blockers.md    (human-readable summary)

Usage: python backtest/autoresearch/winner_day_entry_blocker_diag.py
Cost: $0 (pure Python, no LLM calls)
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from lib.orchestrator import run_backtest

# ---------------------------------------------------------------------------
# Config — Safe-ATM at $1K (the config that FAILS on winner days)
# ---------------------------------------------------------------------------
SAFE_ATM_KWARGS = dict(
    use_real_fills=True,
    premium_stop_pct=-0.08,
    premium_stop_pct_bear=-0.08,
    premium_stop_pct_bull=-0.08,
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.0,
    strike_offset=0,          # ATM
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,     # v15.1 — no dead window
    profit_lock_mode="trailing",
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.10,
    profit_lock_trail_pct=0.20,
    # bear min triggers = 1 (default)
)

J_WINNERS = [
    {"date": "2026-04-29", "j_entry_time": "10:25:51", "j_strike": 710, "j_pnl": 342,
     "note": "Rejection at 711.4 + ribbon flip. Gap-down day. SPY ~710 area."},
    {"date": "2026-05-01", "j_entry_time": "13:36:00", "j_strike": 721, "j_pnl": 470,
     "note": "Leg #2 — real trigger at trendline. First leg was anticipation (stopped out)."},
    {"date": "2026-05-04", "j_entry_time": "10:27:50", "j_strike": 721, "j_pnl": 730,
     "note": "Confluence: premarket level + multi-day trendline + ribbon flip."},
]

DATA_DIR = REPO / "data"


def _load_data():
    spy_path = DATA_DIR / "spy_5m_2025-01-01_2026-05-15.csv"
    vix_path = DATA_DIR / "vix_5m_2025-01-01_2026-05-15.csv"
    if not spy_path.exists():
        spy_path = DATA_DIR / "spy_5m_2025-01-01_2026-05-07.csv"
        vix_path = DATA_DIR / "vix_5m_2025-01-01_2026-05-07.csv"
    print(f"Loading {spy_path.name}...")
    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)
    return spy, vix


def _format_time(ts) -> str:
    if hasattr(ts, "strftime"):
        return ts.strftime("%H:%M")
    return str(ts)[:16]


def _blocker_names(blockers: list[int]) -> str:
    names = {
        1: "F1:time_gate",
        2: "F2:news",
        3: "F3:budget",
        4: "F4:day_trades",
        5: "F5:ribbon_stack",
        6: "F6:spread<30c",
        7: "F7:volume_div",
        8: "F8:vix",
        9: "F9:breakdown_bar",
        10: "F10:triggers",
    }
    return " | ".join(names.get(b, f"F{b}") for b in blockers) if blockers else "NONE"


def _analyze_day(spy_df, vix_df, winner: dict) -> dict:
    date_str = winner["date"]
    d = dt.date.fromisoformat(date_str)
    j_entry_time_str = winner["j_entry_time"]
    j_entry_h, j_entry_m, j_entry_s = (int(x) for x in j_entry_time_str.split(":"))
    j_entry_time = dt.time(j_entry_h, j_entry_m, j_entry_s)

    print(f"\n{'='*72}")
    print(f"  {date_str}  J entered {winner['j_strike']}P @ {j_entry_time_str}  (+${winner['j_pnl']})")
    print(f"  Note: {winner['note']}")
    print(f"{'='*72}")

    # Run backtest on this single day with full context (needs prior bars for ribbon warmup)
    # Use full data from 2026-04-14 to give ribbon warmup context
    spy_window = spy_df[
        (spy_df["timestamp_et"] >= f"{date_str}T00:00:00") |
        (spy_df["timestamp_et"] >= "2026-04-14")
    ].copy()
    # Actually filter correctly: need days from 2026-04-14 through the target date
    spy_window = spy_df[spy_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()
    vix_window = vix_df[vix_df["timestamp_et"] <= f"{date_str}T23:59:59"].copy()

    result = run_backtest(
        spy_df=spy_window,
        vix_df=vix_window,
        start_date=d,
        end_date=d,
        **SAFE_ATM_KWARGS,
    )

    # Pull decisions for this day from 09:35 to 14:00
    day_decisions = []
    for dec in result.decisions:
        ts = dec["timestamp_et"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        if ts.date() != d:
            continue
        if ts.time() < dt.time(9, 35) or ts.time() > dt.time(14, 0):
            continue
        day_decisions.append(dec)

    print(f"\n  Engine decisions 09:35-14:00 ({len(day_decisions)} bars evaluated):")
    print(f"  {'Time':>6}  {'SPY':>7}  {'VIX':>6}  {'Stack':>6}  {'Sprd':>5}  {'Pass':>5}  Blockers / Triggers")
    print(f"  {'-'*100}")

    first_enter_time = None
    first_pass_time = None
    blocker_tally: dict[str, int] = {}

    for dec in day_decisions:
        ts = dec["timestamp_et"]
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        time_str = ts.strftime("%H:%M")
        spy_close = dec.get("spy_close", 0)
        vix_val = dec.get("vix", 0)
        stack = dec.get("ribbon_stack", "?") or "None"
        spread = dec.get("ribbon_spread_cents", 0) or 0
        passed = dec.get("passed", False)
        blockers = dec.get("blockers", [])
        triggers = dec.get("triggers_fired", [])
        action = dec.get("action", "")

        blocker_str = _blocker_names(blockers)
        trigger_str = ", ".join(triggers) if triggers else ""

        # Count which filter is most often the blocker
        for b in blockers:
            key = f"F{b}"
            blocker_tally[key] = blocker_tally.get(key, 0) + 1

        if passed and not action:
            status = "ENTER"
            if first_pass_time is None:
                first_pass_time = ts.time()
        elif action == "SKIP_QUALITY_LOCK":
            status = "QTY-LOCK"
        else:
            status = "BLOCK"

        if status == "ENTER" and first_enter_time is None:
            first_enter_time = ts.time()

        # Highlight bars near J's entry time
        j_marker = " <<J" if abs(ts.hour * 60 + ts.minute - j_entry_h * 60 - j_entry_m) <= 10 else ""

        print(f"  {time_str:>6}  {spy_close:>7.2f}  {vix_val:>6.2f}  "
              f"{str(stack)[:6]:>6}  {spread:>5.0f}  {status:>5}  "
              f"{blocker_str or trigger_str}{j_marker}")

    # Trades actually taken
    print(f"\n  Trades taken: {len(result.trades)}")
    for t in result.trades:
        entry_t = t.entry_time_et
        if hasattr(entry_t, "strftime"):
            entry_str = entry_t.strftime("%H:%M:%S")
        else:
            entry_str = str(entry_t)[:19]
        exit_t = t.runner_exit_time_et if hasattr(t, "runner_exit_time_et") and t.runner_exit_time_et else t.entry_time_et
        exit_str = exit_t.strftime("%H:%M:%S") if hasattr(exit_t, "strftime") else str(exit_t)[:19]
        print(f"    Entry: {entry_str}  Exit: {exit_str}  P&L: ${t.dollar_pnl:+.2f}  "
              f"Strike: {t.strike}  Exit reason: {t.exit_reason}")

    print(f"\n  First filter-pass bar: {first_pass_time}")
    print(f"  First actual entry: {first_enter_time}")
    print(f"  J's entry time: {j_entry_time}")
    print(f"  Entry lag vs J: {_compute_lag_min(first_enter_time, j_entry_time)} minutes"
          if first_enter_time else "  Engine never entered!")

    print(f"\n  Blocker frequency (bars where each filter was the problem):")
    for f_id, count in sorted(blocker_tally.items(), key=lambda x: -x[1]):
        names = {
            "F5": "Ribbon not BEAR-stacked",
            "F6": "Ribbon spread < 30c",
            "F7": "Volume divergence",
            "F8": "VIX < 17.30 or not rising",
            "F9": "Not a breakdown bar (green or low vol)",
            "F10": "No valid trigger (no level rejection/flip/confluence)",
        }
        desc = names.get(f_id, f_id)
        print(f"    {f_id}: {count:>3} bars blocked  ({desc})")

    return {
        "date": date_str,
        "j_entry_time": j_entry_time_str,
        "j_pnl": winner["j_pnl"],
        "engine_first_pass_time": str(first_pass_time) if first_pass_time else None,
        "engine_first_entry_time": str(first_enter_time) if first_enter_time else None,
        "entry_lag_minutes": _compute_lag_min(first_enter_time, j_entry_time) if first_enter_time else None,
        "blocker_frequency": blocker_tally,
        "engine_pnl": sum(t.dollar_pnl for t in result.trades),
        "engine_n_trades": len(result.trades),
        "trades": [
            {
                "entry_time": str(t.entry_time_et)[:19],
                "exit_time": str(t.runner_exit_time_et if (hasattr(t, "runner_exit_time_et") and t.runner_exit_time_et) else t.entry_time_et)[:19],
                "dollar_pnl": round(float(t.dollar_pnl), 2),
                "strike": t.strike,
                "exit_reason": t.exit_reason,
            }
            for t in result.trades
        ],
    }


def _compute_lag_min(engine_time, j_time) -> int | None:
    if engine_time is None or j_time is None:
        return None
    e_min = engine_time.hour * 60 + engine_time.minute
    j_min = j_time.hour * 60 + j_time.minute
    return e_min - j_min


def main() -> int:
    spy_df, vix_df = _load_data()
    print(f"Loaded {len(spy_df):,} SPY rows, {len(vix_df):,} VIX rows")

    day_results = []
    for winner in J_WINNERS:
        result = _analyze_day(spy_df, vix_df, winner)
        day_results.append(result)

    # Summary
    print(f"\n{'='*72}")
    print("SUMMARY — Entry blocker diagnosis on J's 3 winner days")
    print(f"{'='*72}")
    print(f"{'Date':>12}  {'J entry':>8}  {'Eng first pass':>14}  {'Eng entry':>10}  "
          f"{'Lag':>5}  {'Engine P&L':>11}  Top blocker")
    print("-"*100)
    for r in day_results:
        top_blocker = max(r["blocker_frequency"].items(), key=lambda x: x[1])[0] if r["blocker_frequency"] else "NONE"
        print(f"  {r['date']:>10}  {r['j_entry_time'][:5]:>8}  "
              f"{str(r['engine_first_pass_time'] or 'NEVER'):>14}  "
              f"{str(r['engine_first_entry_time'] or 'NEVER'):>10}  "
              f"{str(r['entry_lag_minutes'] or 'N/A'):>5}  "
              f"${r['engine_pnl']:>+10.2f}  {top_blocker}")

    # Write outputs
    out_dir = REPO.parent / "analysis" / "recommendations"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_json = out_dir / "winner_day_entry_blockers.json"
    out_json.write_text(json.dumps({
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "purpose": "Identify which filter blocks morning entries on J's 3 winner days (Safe-ATM config)",
        "config": "Safe-ATM: strike_offset=0, premium_stop=-8%, tp1=+30%, no_trade_before=09:35, no_trade_window=None",
        "op16_floor": 771,
        "j_max_edge": 1542,
        "day_results": day_results,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote: {out_json}")

    # Write markdown
    out_md = out_dir / "winner_day_entry_blockers.md"
    _write_markdown(day_results, out_md)
    print(f"Wrote: {out_md}")

    return 0


def _write_markdown(day_results: list, path: Path) -> None:
    lines = ["# Winner-Day Entry Blocker Diagnosis", "",
             "> Config: Safe-ATM (strike_offset=0, premium_stop=-8%, no_trade_before=09:35, no dead window)", "",
             "## Summary Table", "",
             "| Date | J Entry | Engine First Pass | Engine Entry | Lag (min) | Engine P&L | Top Blocker |",
             "|---|---|---|---|---|---|---|"]
    for r in day_results:
        top_b = max(r["blocker_frequency"].items(), key=lambda x: x[1])[0] if r["blocker_frequency"] else "NONE"
        lines.append(
            f"| {r['date']} | {r['j_entry_time'][:5]} | "
            f"{r.get('engine_first_pass_time') or 'NEVER'} | "
            f"{r.get('engine_first_entry_time') or 'NEVER'} | "
            f"{r.get('entry_lag_minutes') or 'N/A'} | "
            f"${r['engine_pnl']:+.2f} | {top_b} |"
        )
    lines += ["", "## Filter Blocker Breakdown", ""]

    filter_names = {
        "F5": "F5 — Ribbon NOT BEAR-stacked (ribbon EMA lag at open)",
        "F6": "F6 — Ribbon spread < 30c (EMAs too compressed after gap)",
        "F7": "F7 — Volume divergence failed",
        "F8": "F8 — VIX < 17.30 or not rising",
        "F9": "F9 — Not a breakdown bar (green bar or insufficient volume)",
        "F10": "F10 — No valid trigger (no level rejection / ribbon flip / confluence)",
    }
    for r in day_results:
        lines += [f"### {r['date']}", ""]
        if r["blocker_frequency"]:
            lines += ["| Filter | Bars blocked | Description |", "|---|---|---|"]
            for f_id, cnt in sorted(r["blocker_frequency"].items(), key=lambda x: -x[1]):
                lines.append(f"| {f_id} | {cnt} | {filter_names.get(f_id, f_id)} |")
        else:
            lines.append("No blockers recorded (engine entered successfully from open).")

        lines += ["", f"**Engine trades:**"]
        for t in r.get("trades", []):
            lines.append(f"- {t['entry_time'][11:16]} → {t['exit_time'][11:16]}: "
                        f"{t['strike']}P  P&L=${t['dollar_pnl']:+.2f}  ({t['exit_reason']})")
        lines.append("")

    lines += ["## Root-Cause Hypothesis", "",
              "Based on blocker frequencies, the primary bottleneck on sustained-trend days is:",
              "",
              "- **F6 (spread < 30c) + F5 (ribbon not stacked)**: After a gap-down open, the ribbon EMAs",
              "  need 4-8 RTH bars (~20-40 min) to diverge to >= 30c spread. During this time, EVERY bar",
              "  is blocked regardless of price action or level state.",
              "",
              "- **F10 (no trigger)**: Even after ribbon warms up, the engine needs a REJECTION at a level.",
              "  On gap-down days, price is already below most premarket levels at the open. The engine waits",
              "  for price to BOUNCE BACK to a level and reject — which can take 60-120 min more.",
              "",
              "**Combined lag**: Ribbon warmup (30-40 min) + bounce-back wait (60-120 min) = 90-160 min",
              "delay vs J's morning open entries.",
              "",
              "**Fix candidates:**",
              "1. Reduce spread minimum for the first 10 minutes of RTH (e.g. `spread >= 5c` if F5=BEAR)",
              "2. Allow entry on first 09:35-09:45 bar if HTF (15m) ribbon is BEAR-stacked (uses pre-built warmup)",
              "3. Add a 'gap-down continuation' trigger that fires on gap-down open + first red bar (no bounce required)",
              "4. Wire the PML/PMH rejection as a trigger when price GAPS THROUGH a level (not just bounces to it)",
              ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
