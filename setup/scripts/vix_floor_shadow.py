"""vix_floor_shadow.py -- VIX-FLOOR-SHADOW evaluation (pre-registered
analysis/recommendations/VIX-FLOOR-SHADOW-PREREG-2026-08-27.md).

SHADOW / ANALYSIS ONLY. Never imports or edits params*.json, heartbeat_core.py,
filters.py, or any live-order path. Reads automation/state/core-decisions.jsonl
(read-only) and writes ONLY to analysis/recommendations/vix-floor-shadow-*.

Reuses the ratified exit-parity machinery instead of re-implementing it:
  - automation/state/fleet/exit_manager.py (ExitState, plan_exit_actions) -- the
    ACTUAL live pure decision core.
  - backtest/tools/exit_shape_parity_study.py -- fetch_option_bars / creds probe /
    _et_hhmm_to_utc (PARITY-GAP-2 iteration-6 machinery, 6/6 fidelity).
  - backtest/tools/alpaca_bars.py#fetch_spy_5m_sip -- real SPY 5-min SIP bars for
    the structure-stop check (same feed the live actuator's structure mode uses).
  - automation/state/fleet/strategies.py#RIBBON_RIDE.exit -- the LIVE ribbon_ride
    exit shape, used byte-identical (dataclasses.asdict, no field re-typed).

Run via the backtest venv interpreter (exempt from the 5-min reaper, L41):
  backtest/.venv/Scripts/python.exe setup/scripts/vix_floor_shadow.py [--today]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time as _time_mod
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts",
           REPO / "backtest" / "tools", REPO / "crypto" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from exit_manager import ExitState, plan_exit_actions, TIME_STOP_ET  # noqa: E402
from strategies import RIBBON_RIDE  # noqa: E402
from strike_selection import atm_strike  # noqa: E402
from spread_executor import occ_symbol  # noqa: E402
from exit_shape_parity_study import (  # noqa: E402
    fetch_option_bars, _live_data_creds, _et_hhmm_to_utc,
)
from alpaca_bars import fetch_spy_5m_sip  # noqa: E402

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER_PATH = OUT_DIR / "vix-floor-shadow-ledger.jsonl"
SUMMARY_PATH = OUT_DIR / "vix-floor-shadow-summary.json"
PREREG_PATH = OUT_DIR / "VIX-FLOOR-SHADOW-PREREG-2026-08-27.md"

IS_OOS_SPLIT_DATE = "2026-08-14"  # fixed in the prereg, IS < split <= OOS
QTY = 3  # Safe-tier minimum (CLAUDE.md rule 6: 2 TP + 1 runner)
TICK = 0.01  # 1-cent slippage against the trader on entry

RIBBON_RIDE_SHAPE: dict = asdict(RIBBON_RIDE.exit)


# --- population -------------------------------------------------------------------------

def load_population(path: Path = CORE_DECISIONS,
                     since_date: "str | None" = None) -> list[dict]:
    """Rows where bear_blockers == [8] exactly. No look-ahead: only fields that
    existed at the signal tick are read (C6)."""
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("bear_blockers") != [8]:
                continue
            if r.get("account") not in ("safe", "bold"):
                continue
            if since_date is not None and str(r.get("ts_et", ""))[:10] < since_date:
                continue
            out.append(r)
    out.sort(key=lambda r: (r.get("account", ""), r.get("ts_et", "")))
    return out


# One-open-position-at-a-time collapse is implemented inline inside
# select_and_walk() below (per-account sequential walk) -- it cannot be a pure
# pass over the row list because each entry's hold length is only known after
# that entry's own exit walk runs.


# --- contract construction ---------------------------------------------------------------

def _expiry_yymmdd(date_et: str) -> str:
    y, m, d = date_et.split("-")
    return f"{y[2:]}{m}{d}"


def build_shadow_contract(row: dict) -> "str | None":
    spot = row.get("spy")
    if not spot:
        return None
    strike = atm_strike(float(spot))  # V15_SAFE_TIERS offset=0 at $2K-$10K, both accounts
    return occ_symbol("P", float(strike), _expiry_yymmdd(str(row["ts_et"])[:10]))


# --- entry timing -----------------------------------------------------------------------

def _next_minute_iso_et(ts_et: str) -> str:
    t = dt.datetime.fromisoformat(ts_et)
    nxt = (t.replace(second=0, microsecond=0) + dt.timedelta(minutes=1))
    return nxt.isoformat()


def find_entry_bar(option_bars: list[dict], entry_hhmm: str, date_et: str) -> "dict | None":
    """First 1-min option bar at/after the next-minute entry time."""
    start_utc = f"{date_et}T{_et_hhmm_to_utc(date_et, entry_hhmm)}"
    for b in option_bars:
        if b["t"] >= start_utc:
            return b
    return None


def spy_5m_bars_for_date(date_et: str, cache: dict) -> list[dict]:
    if date_et in cache:
        return cache[date_et]
    d = dt.date.fromisoformat(date_et)
    try:
        df = fetch_spy_5m_sip(d, d, include_premarket=True)
    except Exception as exc:  # noqa: BLE001 -- fail open per fetch_spy_5m_sip contract
        print(f"[vix_floor_shadow] spy 5m fetch failed {date_et}: {exc}", file=sys.stderr)
        cache[date_et] = []
        return []
    bars = []
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            # timestamp_et is a string "2026-06-01 04:00:00-04:00" (real per-row
            # DST offset, alpaca_bars.fetch_spy_5m_sip's own format) -- parse then
            # convert to UTC for a "t"/"c" dict matching fetch_option_bars' bars.
            ts = dt.datetime.fromisoformat(str(r["timestamp_et"]))
            ts_utc = ts.astimezone(dt.timezone.utc)
            bars.append({"t": ts_utc.isoformat().replace("+00:00", "Z"),
                        "c": float(r["close"])})
    cache[date_et] = bars
    return bars


# --- the walk (mirrors exit_shape_parity_study.replay_position, structure mode) ----------

def walk_shadow_trade(row: dict, option_bars: list[dict], spy_5m: list[dict]) -> dict:
    date_et = str(row["ts_et"])[:10]
    entry_hhmm = _next_minute_iso_et(row["ts_et"])[11:16]
    entry_bar = find_entry_bar(option_bars, entry_hhmm, date_et)
    if entry_bar is None:
        return {"excluded": True, "exclude_reason": "no_opra_bar_at_or_after_entry_minute"}

    entry_price = round(float(entry_bar["o"]) + TICK, 4)
    trigger_level = row.get("bear_rejection_level_raw")
    if trigger_level is None:
        return {"excluded": True, "exclude_reason": "no_trigger_level"}

    state = ExitState.from_entry(
        symbol=build_shadow_contract(row) or "UNKNOWN", side="P",
        entry_premium=entry_price, qty=QTY, exit_shape=RIBBON_RIDE_SHAPE,
        strategy="ribbon_ride_shadow", trigger_level=float(trigger_level),
        structure_stop_enabled=True,
    )
    relevant = [b for b in option_bars if b["t"] >= entry_bar["t"]]
    open_qty = QTY
    realized = 0.0
    exits: list[dict] = []
    last_ts = entry_bar["t"]
    for b in relevant:
        bar_dt_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        now_et = (bar_dt_utc - dt.timedelta(hours=4)).time()  # EDT offset, same convention
        closed5 = _last_closed_5m_close(spy_5m, b["t"]) if state.stop_mode == "structure" else None
        decision = plan_exit_actions(
            state, best_premium=b["h"], worst_premium=b["l"], open_qty=open_qty,
            now_et=now_et, ribbon_flip_back=False, time_stop_et=TIME_STOP_ET,
            last_closed_5m_close=closed5,
        )
        for action in decision.actions:
            if action.kind in ("SELL_PARTIAL", "SELL_ALL"):
                if action.stage == "tp1":
                    fill = entry_price * (1.0 + state.tp1_premium_pct)
                elif action.stage == "runner_target":
                    fill = entry_price * (1.0 + state.runner_target_pct)
                elif action.stage in ("premium_stop", "profit_lock_floor", "trail", "be_stop"):
                    # Read the ACTUAL level off exit_manager's own reason string -- never
                    # recompute from premium_stop_pct, which is only the static catastrophe
                    # cap and does not reflect ladder/trail ratchets (see _reason_level).
                    lvl = _reason_level(action.reason)
                    fill = lvl if lvl is not None else entry_price * (1.0 + state.premium_stop_pct)
                else:  # time_stop / structure_stop -- market-style, fill at this bar's close
                    fill = b["c"]
                realized += (fill - entry_price) * action.qty * 100
                open_qty -= action.qty
                exits.append({"stage": action.stage, "qty": action.qty,
                             "fill_price": round(fill, 4), "ts_utc": b["t"]})
        state = decision.state
        last_ts = b["t"]
        if open_qty <= 0:
            break

    return {"excluded": False, "entry_price": entry_price, "entry_ts_utc": entry_bar["t"],
            "exit_ts_utc": last_ts, "exits": exits, "pnl": round(realized, 2),
            "final_open_qty": open_qty, "stop_mode": state.stop_mode}


_REASON_LEVEL_RE = re.compile(r"@\s*([0-9]+\.?[0-9]*)")


def _reason_level(reason: "str | None") -> "float | None":
    """Extract the actual price level exit_manager.py's `reason` string carries
    (e.g. "premium_stop @ 4.65", "profit_lock_floor @ 5.02"). SINGLE SOURCE OF
    TRUTH fix: the "premium_stop" stage label is REUSED by exit_manager.py for
    any pre-TP1 hard-exit whose runner_stop was ratcheted up by the ladder
    rungs / dynamic trail (see exit_manager.py:548-571) -- only the profit-lock
    "full"-scope and pre_tp1_be_floor_arm_pct paths relabel it "profit_lock_
    floor"; the ladder/trail-ratcheted case stays labeled "premium_stop" even
    though the level is nowhere near the static catastrophe_stop_pct. An
    earlier version of this script recomputed fill = entry*(1+premium_stop_pct)
    for every "premium_stop"-stage action, which silently priced winning,
    ladder-ratcheted exits (e.g. +30% locked-in floor) as if they'd hit the
    static -50% cap -- caught by the Step-4 hand-verification bar walk
    (2026-08-27), which showed the option premium never dipped below the
    supposed catastrophe level on the bar that "triggered" it."""
    m = _REASON_LEVEL_RE.search(reason or "")
    return float(m.group(1)) if m else None


def _last_closed_5m_close(spy_5m_bars: list[dict], bar_ts_utc: str):
    try:
        ts = dt.datetime.fromisoformat(str(bar_ts_utc).replace("Z", "+00:00"))
    except ValueError:
        return None
    best_t, best_c = None, None
    for b in spy_5m_bars or []:
        try:
            bt = dt.datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00"))
            close = float(b["c"])
        except (KeyError, TypeError, ValueError):
            continue
        if bt + dt.timedelta(minutes=5) <= ts and (best_t is None or bt > best_t):
            best_t, best_c = bt, close
    return best_c


# --- selection with one-position-at-a-time replication ------------------------------------

def select_and_walk(rows: list[dict]) -> list[dict]:
    """Per account, sort by ts_et, walk sequentially. A row becomes an entry
    only if no shadow position is currently open for that account (tracked by
    comparing ts_et to the previous shadow trade's exit ts_et, converted back
    to ET for comparison). Later rows during the hold are SKIPPED and counted.
    """
    by_acct: dict = {}
    for r in rows:
        by_acct.setdefault(r["account"], []).append(r)

    option_bar_cache: dict = {}
    spy_5m_cache: dict = {}
    trades: list[dict] = []
    skipped_during_hold = 0
    raw_n = len(rows)

    for account, acct_rows in by_acct.items():
        acct_rows = sorted(acct_rows, key=lambda r: r["ts_et"])
        open_until_utc = None  # exit_ts_utc of the currently open shadow position
        for row in acct_rows:
            date_et = str(row["ts_et"])[:10]
            if open_until_utc is not None:
                # compare in UTC: signal ts_et (naive ET) -> approx UTC by +4h (EDT)
                sig_dt = dt.datetime.fromisoformat(row["ts_et"])
                sig_utc = sig_dt + dt.timedelta(hours=4)
                sig_utc_iso = sig_utc.isoformat() + "Z"
                if sig_utc_iso <= open_until_utc:
                    skipped_during_hold += 1
                    continue
                open_until_utc = None

            contract = build_shadow_contract(row)
            if contract is None:
                trades.append({**_base_row(row, contract), "excluded": True,
                              "exclude_reason": "no_spot_price"})
                continue

            key = (contract, date_et)
            if key not in option_bar_cache:
                option_bar_cache[key] = fetch_option_bars(contract, date_et)
                _time_mod.sleep(0.15)
            bars = option_bar_cache[key]
            if not bars:
                trades.append({**_base_row(row, contract), "excluded": True,
                              "exclude_reason": "no_opra_bars_for_contract"})
                continue

            spy5 = spy_5m_bars_for_date(date_et, spy_5m_cache)
            walked = walk_shadow_trade(row, bars, spy5)
            trade = {**_base_row(row, contract), **walked}
            trades.append(trade)
            if not walked.get("excluded") and walked.get("exit_ts_utc"):
                open_until_utc = walked["exit_ts_utc"]

    for t in trades:
        t["raw_population_n"] = raw_n
        t["skipped_during_hold_n"] = skipped_during_hold
    return trades


def _base_row(row: dict, contract: "str | None") -> dict:
    return {
        "signal_ts_et": row["ts_et"], "account": row["account"], "date_et": str(row["ts_et"])[:10],
        "contract": contract, "spy_at_signal": row.get("spy"), "vix_at_signal": row.get("vix"),
        "bear_score": row.get("bear_score"), "bear_triggers_raw": row.get("bear_triggers_raw"),
        "trigger_level": row.get("bear_rejection_level_raw"), "qty": QTY,
    }


# --- summary ------------------------------------------------------------------------------

def _profit_factor(pnls: list[float]) -> "float | None":
    gains = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    if losses == 0:
        return None if gains == 0 else float("inf")
    return round(gains / losses, 3)


def summarize(trades: list[dict]) -> dict:
    valid = [t for t in trades if not t.get("excluded")]
    excluded = [t for t in trades if t.get("excluded")]
    exclude_reasons: dict = {}
    for t in excluded:
        exclude_reasons[t.get("exclude_reason", "unknown")] = (
            exclude_reasons.get(t.get("exclude_reason", "unknown"), 0) + 1)

    pnls = [t["pnl"] for t in valid]
    wins = [p for p in pnls if p > 0]
    is_trades = [t for t in valid if t["date_et"] < IS_OOS_SPLIT_DATE]
    oos_trades = [t for t in valid if t["date_et"] >= IS_OOS_SPLIT_DATE]

    by_day: dict = {}
    for t in valid:
        by_day.setdefault(t["date_et"], []).append(t["pnl"])
    per_day = {d: {"n": len(v), "pnl": round(sum(v), 2)} for d, v in sorted(by_day.items())}
    total_pnl = round(sum(pnls), 2)
    max_day_share = None
    if valid and total_pnl != 0:
        max_day_pnl = max((abs(v["pnl"]) for v in per_day.values()), default=0.0)
        max_day_share = round(max_day_pnl / abs(total_pnl), 3) if total_pnl else None

    is_pf = _profit_factor([t["pnl"] for t in is_trades])
    oos_pf = _profit_factor([t["pnl"] for t in oos_trades])
    n_gate = len(valid) >= 15
    oos_positive_gate = (oos_pf is not None and oos_pf > 1.0) if oos_trades else False
    # WF stability: OOS PF within 0.70x of IS PF (both directions), guards against IS-only edge
    wf_gate = None
    if is_pf not in (None, float("inf")) and oos_pf not in (None, float("inf")) and is_pf > 0:
        wf_gate = (oos_pf / is_pf) >= 0.70
    sub_window_stable = (max_day_share is not None and max_day_share <= 0.50)

    verdict = "NOT_PROMOTED"
    if n_gate and oos_positive_gate and wf_gate and sub_window_stable:
        verdict = "PROMOTABLE_CANDIDATE"

    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "prereg": str(PREREG_PATH.relative_to(REPO)),
        "population": {
            "raw_bear_blockers_eq_8_rows": trades[0]["raw_population_n"] if trades else 0,
            "skipped_during_hold": trades[0]["skipped_during_hold_n"] if trades else 0,
            "shadow_entries_attempted": len(trades),
            "n_valid": len(valid), "n_excluded": len(excluded),
            "exclude_reasons": exclude_reasons,
        },
        "totals": {
            "n": len(valid), "win_rate": round(len(wins) / len(valid), 3) if valid else None,
            "total_pnl": total_pnl, "profit_factor": _profit_factor(pnls),
            "avg_pnl": round(total_pnl / len(valid), 2) if valid else None,
        },
        "is_oos_split_date": IS_OOS_SPLIT_DATE,
        "is": {"n": len(is_trades), "pnl": round(sum(t["pnl"] for t in is_trades), 2),
              "profit_factor": is_pf},
        "oos": {"n": len(oos_trades), "pnl": round(sum(t["pnl"] for t in oos_trades), 2),
               "profit_factor": oos_pf},
        "per_day": per_day,
        "max_single_day_pnl_share_of_total": max_day_share,
        "gates": {
            "n_gte_15": n_gate, "oos_pf_gt_1": oos_positive_gate,
            "wf_stability_gte_0.70": wf_gate, "sub_window_stable_max_day_lte_0.50": sub_window_stable,
            "anchor_no_regression": "N/A_shadow_only_never_pooled_with_real_bear_cohort",
        },
        "verdict": verdict,
        "disclosures": [
            "Selection is on entry-time information only (C6 no look-ahead).",
            "Synthetic fills are mechanism evidence, not P&L truth -- no real order was placed.",
            "August 2026 VIX regime concentration (14-16 band) -- speaks only to that regime.",
            "This population is a DIFFERENT setup shape than the real trendline-bypass bear "
            "cohort and is never pooled with it.",
        ],
        "schedule_hint": (
            "backtest/.venv/Scripts/python.exe setup/scripts/vix_floor_shadow.py --today "
            "(suggested daily, e.g. 16:10 ET after EOD flatten; NOT registered by this build -- "
            "see prereg Step 3)."
        ),
    }


# --- main -----------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true",
                    help="append mode: only process today's ET date, merge into existing ledger")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    since_date = None
    existing_ledger: list[dict] = []
    if args.today:
        from et_clock import et_now  # noqa: E402
        since_date = et_now().date().isoformat()
        if LEDGER_PATH.exists():
            with LEDGER_PATH.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        existing_ledger.append(json.loads(line))
            existing_ledger = [r for r in existing_ledger if r.get("date_et") != since_date]

    rows = load_population(since_date=since_date)
    print(f"[vix_floor_shadow] {len(rows)} bear_blockers==[8] rows"
         f"{' (today only)' if args.today else ''}")

    trades = select_and_walk(rows)
    all_trades = existing_ledger + trades if args.today else trades

    with LEDGER_PATH.open("w", encoding="utf-8") as fh:
        for t in all_trades:
            fh.write(json.dumps(t) + "\n")

    summary = summarize(all_trades)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary["totals"], indent=2))
    print(json.dumps(summary["gates"], indent=2))
    print("verdict:", summary["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
