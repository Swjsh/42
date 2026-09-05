"""zero_enter_autopsy.py -- GOAL-ZERO-ENTER-DAYS-2026-09-03 Z3.

Read-only, $0, deterministic autopsy for a frozen-window trading day graded
SAT_OUT_GATED or regressing by conductor_outcome._grade_zero_enter_day. Writes
analysis/zero-enter/ZERO-ENTER-<date>.json: a per-bar table (which blocker
fired at which 5-min bar, SPY price, would-have-entered flag) plus a
day-level summary (thesis, dominant blocker, and the day's own thesis payoff
priced net of realistic costs).

NEVER touches a FROZEN_TRADING_PATH file (params.json, aggressive/params.json,
fleet/accounts.json, fleet/strategies.py, fleet/exit_manager.py,
fleet/fleet_executor.py, fleet/build_shared_signal.py, backtest/lib/filters.py,
backtest/lib/risk_gate.py, setup/scripts/heartbeat_core.py) -- this script only
READS from all of them (filters.py's vol_baseline_20bar/buyer_pressure_bar_v11
for blocker-10 reconstruction, simulator_real.py's cost-model constants for
pricing). Fail-open throughout: a missing thesis file, missing option cache,
or unreadable ledger degrades to a labeled null, never a crash.

Building blocks REUSED, not reimplemented (per the goal's OPERATING RULES):
  - conductor_outcome._grade_zero_enter_day / _decisions_for_day -- day grade.
  - backtest.lib.filters.vol_baseline_20bar / buyer_pressure_bar_v11 -- the
    real blocker-10 mechanism, for blocker_detail reconstruction (mirrors
    backtest/tools/f10_volume_reproduce.py's proven import pattern).
  - backtest.lib.simulator_real.DEFAULT_ENTRY_SLIPPAGE / DEFAULT_EXIT_SLIPPAGE
    -- the backtest engine's own cost model (never a hand-rolled number).
  - backtest.lib.option_pricing_real -- real OPRA option bar cache + symbol
    builder, for the counterfactual thesis payoff.

CLI: python setup/scripts/zero_enter_autopsy.py --date 2026-09-02
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (REPO, BACKTEST, BACKTEST / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import conductor_outcome as co  # noqa: E402
from lib.filters import vol_baseline_20bar, buyer_pressure_bar_v11  # noqa: E402
from lib.simulator_real import DEFAULT_ENTRY_SLIPPAGE, DEFAULT_EXIT_SLIPPAGE  # noqa: E402
from lib.simulator import TIME_STOP_ET, DEFAULT_QTY  # noqa: E402
from lib.option_pricing_real import (  # noqa: E402
    option_symbol, load_contract_bars, bar_at_or_after, bar_containing,
)
from lib.et_frame import parse_timestamp_et, FRAME_ET_V2  # noqa: E402

try:
    import pandas as pd
except ImportError:  # pragma: no cover -- pandas is a hard dependency of the venv this runs in
    pd = None

SCORE_THRESHOLD = co.ZERO_ENTER_SCORE_THRESHOLD
OUT_DIR = REPO / "analysis" / "zero-enter"
SIP_SIP_DIR = BACKTEST / "data" / "spy_sip_cache"


def _decisions_for_day_account(day: str, account: str) -> list[dict[str, Any]]:
    """core-decisions.jsonl rows for one account/day, chronological order."""
    rows = [
        r for r in co._decisions_for_day(day, co.DECISIONS_FILE)
        if r.get("account") == account
    ]
    return list(reversed(rows))  # _decisions_for_day comes back newest-first


def _dedup_by_bar(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """RTH (09:35-16:00) rows deduped to unique 5-min bars by trigger_bar_et,
    last occurrence kept -- the exact method SIP-VOLMULT-2026-09-02.md used
    (core_decisions_unique_bar_check), pinned by test_zero_enter_autopsy.py."""
    by_bar: dict[str, dict[str, Any]] = {}
    for r in rows:
        ts = str(r.get("ts_et", "") or "")
        if len(ts) < 16 or not ("09:35" <= ts[11:16] < "16:00"):
            continue
        tb = r.get("trigger_bar_et")
        if not tb:
            continue
        by_bar[tb] = r
    return by_bar


def _thesis_side_for_day(rows: list[dict[str, Any]]) -> tuple[str, str]:
    """(dominant_ribbon, thesis_side) -- the ribbon direction that held for a
    majority of the day's RTH ticks. Validated against SIP-VOLMULT-2026-09-02
    (dominant BULL ribbon -> bull-side blocker count reproduces the
    published 57/77 f10-blocked figure exactly; the alternative
    "whichever side scored higher per-bar" tried and rejected -- gave 50/77)."""
    counts = Counter(r.get("ribbon") for r in rows if r.get("ribbon"))
    dominant = counts.most_common(1)[0][0] if counts else "UNKNOWN"
    side = "bull" if dominant == "BULL" else "bear"
    return dominant, side


def _reconstruct_blocker10_detail(target_date: str, bar_et: str) -> str | None:
    """Best-effort reconstruction of the f10 (buyer_pressure_bar_v11) mechanism
    for one bar, using the REAL filter functions against the cached SIP 5-min
    series (mirrors f10_volume_reproduce.py's proven pattern). Returns None
    (fail-open, labeled) when the SIP cache does not cover this date."""
    if pd is None:
        return None
    try:
        avail = sorted(p.stem.replace("spy_5m_", "") for p in SIP_SIP_DIR.glob("spy_5m_*.json"))
    except OSError:
        return None
    warmup = [d for d in avail if d < target_date][-3:]
    all_dates = warmup + ([target_date] if target_date in avail else [])
    if target_date not in avail:
        return None
    frames = []
    for d in all_dates:
        p = SIP_SIP_DIR / f"spy_5m_{d}.json"
        try:
            bars = json.loads(p.read_text(encoding="utf-8")).get("bars", [])
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            continue
        if not bars:
            continue
        df = pd.DataFrame(bars).rename(
            columns={"t": "timestamp_et", "o": "open", "h": "high", "l": "low",
                     "c": "close", "v": "volume"}
        )
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
        frames.append(df[["timestamp_et", "open", "high", "low", "close", "volume"]])
    if not frames:
        return None
    full = pd.concat(frames, ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    target_ts = pd.Timestamp(bar_et)
    if target_ts.tzinfo is not None:
        target_ts = target_ts.tz_localize(None)
    match = full.index[full["timestamp_et"] == target_ts]
    if len(match) == 0:
        return None
    idx = int(match[0])
    baseline = vol_baseline_20bar(full, idx)
    bar = full.iloc[idx]
    ratio = (float(bar["volume"]) / baseline) if baseline > 0 else None
    return (
        f"vol_baseline_20={baseline:.0f}, bar.volume={int(bar['volume'])}, "
        f"ratio={ratio:.3f}" if ratio is not None else
        f"vol_baseline_20={baseline:.0f}, bar.volume={int(bar['volume'])}"
    )


def _load_thesis(day: str) -> str | None:
    """Premarket/journal thesis text -- best-effort. journal/<day>.md's
    human-authored section (before the generated GAMMA-EOD block), or None."""
    p = REPO / "journal" / f"{day}.md"
    try:
        text = p.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    head = text.split("<!-- GAMMA-EOD:BEGIN")[0].strip()
    return head or None


def _price_thesis_payoff(
    day: str, thesis_side: str, entry_bar_et: str | None, entry_spy: float | None,
) -> dict[str, Any]:
    """Price the day's own thesis (thesis_side, entered at entry_bar_et) net of
    the backtest engine's real cost model (DEFAULT_ENTRY_SLIPPAGE/
    DEFAULT_EXIT_SLIPPAGE from simulator_real.py -- never hand-rolled), using
    real OPRA option bars. Exits at the engine's TIME_STOP_ET close. Degrades
    to a labeled null when no qualifying entry bar existed that day or no
    OPRA cache covers the contract (fail-open, never a crash)."""
    if entry_bar_et is None or entry_spy is None:
        return {
            "computed": False,
            "reason": "no bar this day scored >= threshold with zero blockers on the "
                      "thesis side -- nothing to counterfactually price",
            "payoff_usd": None,
        }
    trade_date = dt.date.fromisoformat(day)
    strike = int(round(entry_spy))  # ATM, per V15_SAFE_TIERS core-Safe convention
    side_char = "C" if thesis_side == "bull" else "P"
    symbol = option_symbol(trade_date, strike, side_char)
    df = load_contract_bars(symbol)
    if df is not None and not df.empty:
        # normalize to a tz-naive ET wall-clock frame (mirrors simulator_real.py's
        # own call-site convention -- see option_pricing_real.load_contract_bars'
        # docstring's FRAME DISCLOSURE) so bar_at_or_after can compare against
        # the naive datetimes this script builds from core-decisions.jsonl's
        # own tz-naive ts_et strings.
        df = df.copy()
        df["timestamp_et"] = parse_timestamp_et(df["timestamp_et"], FRAME_ET_V2)
    if df is None or df.empty:
        return {
            "computed": False,
            "reason": f"no OPRA option cache for {symbol} -- cannot price this day's "
                      f"counterfactual (fail-open null, not a fabricated number)",
            "payoff_usd": None,
            "symbol": symbol,
        }
    entry_dt = dt.datetime.fromisoformat(entry_bar_et.replace("Z", "")).replace(tzinfo=None)
    entry_bar = bar_at_or_after(df, entry_dt)
    if entry_bar is None:
        return {
            "computed": False,
            "reason": f"no {symbol} option bar at/after entry time {entry_bar_et}",
            "payoff_usd": None,
            "symbol": symbol,
        }
    exit_dt = dt.datetime.combine(trade_date, TIME_STOP_ET)
    exit_bar = bar_containing(df, exit_dt) or bar_at_or_after(df, entry_dt)
    if exit_bar is None:
        return {
            "computed": False,
            "reason": f"no {symbol} option bar at the {TIME_STOP_ET} time-stop",
            "payoff_usd": None,
            "symbol": symbol,
        }
    entry_premium = entry_bar.open + DEFAULT_ENTRY_SLIPPAGE
    exit_premium = max(0.0, exit_bar.close - DEFAULT_EXIT_SLIPPAGE)
    qty = DEFAULT_QTY
    payoff = (exit_premium - entry_premium) * qty * 100.0
    return {
        "computed": True,
        "symbol": symbol,
        "strike": strike,
        "side": side_char,
        "entry_bar_et": entry_bar.timestamp_et.isoformat(),
        "entry_premium_net_of_slippage": round(entry_premium, 4),
        "exit_bar_et": exit_bar.timestamp_et.isoformat(),
        "exit_premium_net_of_slippage": round(exit_premium, 4),
        "qty": qty,
        "cost_model": {
            "entry_slippage": DEFAULT_ENTRY_SLIPPAGE,
            "exit_slippage": DEFAULT_EXIT_SLIPPAGE,
            "commission": 0.0,
            "source": "backtest.lib.simulator_real.DEFAULT_ENTRY_SLIPPAGE/"
                      "DEFAULT_EXIT_SLIPPAGE (Alpaca paper = $0 commission)",
        },
        "payoff_usd": round(payoff, 2),
    }


def run_autopsy(day: str, *, account: str = "safe") -> dict[str, Any]:
    """Build the full ZERO-ENTER-<day>.json payload for one trading day.
    Never raises -- any internal failure degrades a field to a labeled null."""
    grade = co._grade_zero_enter_day(day)
    all_rows = _decisions_for_day_account(day, account)
    dominant_ribbon, thesis_side = _thesis_side_for_day(all_rows)
    by_bar = _dedup_by_bar(all_rows)

    bar_rows = []
    blocker_counter: Counter = Counter()
    first_would_have_entered: tuple[str, float] | None = None
    for tb in sorted(by_bar.keys()):
        r = by_bar[tb]
        bear_s = r.get("bear_score", 0) or 0
        bull_s = r.get("bull_score", 0) or 0
        side_score = bear_s if thesis_side == "bear" else bull_s
        side_blockers = (r.get("bear_blockers") if thesis_side == "bear"
                          else r.get("bull_blockers")) or []
        would_have_entered = bool(side_score >= SCORE_THRESHOLD and not side_blockers)
        if would_have_entered and first_would_have_entered is None:
            first_would_have_entered = (tb, float(r.get("spy")) if r.get("spy") is not None else None)
        dominant_blocker = side_blockers[0] if side_blockers else None
        blocker_detail = None
        if dominant_blocker == 10:
            blocker_detail = _reconstruct_blocker10_detail(day, tb)
        # Day-level aggregate counts EVERY blocker present on this bar's side
        # (not just the first-listed one) -- matches the Z2 hand-fill's own
        # method (and SIP-VOLMULT-2026-09-02.md's blocker-10 membership
        # check), so a blocker that co-occurs with others still gets full
        # credit for how many bars it fired on.
        for b in side_blockers:
            blocker_counter[b] += 1
        bar_rows.append({
            "ts_et": tb,
            "bar_close": r.get("spy"),
            "dominant_blocker": dominant_blocker,
            "blocker_detail": blocker_detail,
            "bear_score": bear_s,
            "bull_score": bull_s,
            "would_have_entered": would_have_entered,
        })

    entry_bar_et, entry_spy = (first_would_have_entered if first_would_have_entered
                                else (None, None))
    payoff = _price_thesis_payoff(day, thesis_side, entry_bar_et, entry_spy)

    dominant_blocker_day, dominant_count = (
        blocker_counter.most_common(1)[0] if blocker_counter else (None, 0)
    )

    day_summary = {
        "trading_day": day,
        "account": account,
        "thesis_verbatim": _load_thesis(day),
        "thesis_direction": dominant_ribbon,
        "thesis_payoff_if_taken_net_of_costs": payoff,
        "dominant_blocker_day": dominant_blocker_day,
        "blocker_fire_count": dominant_count,
        "n_bars": len(bar_rows),
        "grade": (grade or {}).get("grade"),
        "grade_reason": (grade or {}).get("reason"),
    }
    return {
        "_doc": "zero_enter_autopsy.py output -- per-bar counterfactual table + day summary. "
                "Read-only autopsy, never a gate change. Schema matches "
                "analysis/zero-enter/ZERO-ENTER-2026-09-02.json (Z2, hand-validated).",
        "schema_version": 1,
        "bars": bar_rows,
        "day_summary": day_summary,
    }


def _default_date() -> str:
    """Today's ET date (never Bash/system-local TZ -- this box runs Mountain,
    per CLAUDE.md's Ohio->Colorado rule). Used when --date is omitted, e.g. by
    the scheduled-task fire (install-zero-enter-autopsy.ps1)."""
    from et_clock import et_today_str
    return et_today_str()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None,
                     help="Trading date YYYY-MM-DD. Defaults to today (ET) when omitted.")
    ap.add_argument("--account", default="safe")
    ap.add_argument("--out", default=None, help="Override output path.")
    args = ap.parse_args()
    date_arg = args.date or _default_date()

    result = run_autopsy(date_arg, account=args.account)
    out_path = Path(args.out) if args.out else OUT_DIR / f"ZERO-ENTER-{date_arg}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    ds = result["day_summary"]
    print(f"[zero-enter-autopsy] {date_arg}: grade={ds['grade']} n_bars={ds['n_bars']} "
          f"dominant_blocker={ds['dominant_blocker_day']} ({ds['blocker_fire_count']}x) "
          f"payoff_computed={ds['thesis_payoff_if_taken_net_of_costs']['computed']}")
    print(f"[zero-enter-autopsy] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
