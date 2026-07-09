"""exit_shape_parity_study.py -- T6, HANDOFF-2026-07-09-TRUTH-AND-EXITS, WS2 (the money question).

Replays every REAL fleet round-trip since 2026-06-25 (fleet_rest arms: safe-1, safe-3, risky-1,
risky-3; engine-attributed; options only) under 4 candidate exit shapes, using the ACTUAL
`plan_exit_actions` state machine from automation/state/fleet/exit_manager.py (the same pure
decision core the live actuator runs) driven by REAL Alpaca 1-min option bars
(/v1beta1/options/bars -- confirmed real OPRA trade data, not synthetic).

SCOPE / DISCLOSED LIMITATION: this replay tests the PREMIUM- and TIME-based components of each
shape only (premium stop, TP1 partial, runner profit-lock, runner target, 15:50 time stop).
`ribbon_flip_back` is always False here -- chart-stop / ribbon-flip invalidation is NOT
reconstructed (that needs full live ribbon/structure state, not just option premium bars), so
candidate (b)'s "chart-stop" component collapses to its -50% catastrophe cap in this study. This
is disclosed, not silently dropped -- see the report's "what this does NOT model" section.

Fill-price assumption for each stage (consistent across all 4 shapes, so the comparison is
apples-to-apples even though it is a simplification of real slippage): TP1/runner-target fill
AT the triggering level; premium-stop/runner-stop fill AT the stop level; time-stop fills at
that bar's close. No entry/exit-path files are touched -- this writes only to analysis/.

Usage: backtest/.venv/Scripts/python.exe backtest/tools/exit_shape_parity_study.py
"""
from __future__ import annotations

import json
import sys
import time as _time_mod
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, time as dtime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import fleet_broker as fb  # noqa: E402
from et_clock import et_now  # noqa: E402
from exit_manager import ExitState, plan_exit_actions, TIME_STOP_ET  # noqa: E402

STATE = REPO / "automation" / "state"
LEDGER = STATE / "fills-ledger.jsonl"
OUT_DIR = REPO / "analysis" / "exit-parity"
FLEET_REST_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")
OPTIONS_HOST = "https://data.alpaca.markets"

# --- the 4 candidate shapes (HANDOFF T6) --------------------------------------------------
SHAPES = {
    "actual_ribbon_ride": {
        "premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
        "profit_lock_mode": "fixed",
    },
    "v15_3_safe_ratified": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 0.30, "tp1_qty_fraction": 0.8,
        "profit_lock_mode": "fixed",  # chart-stop NOT modeled here -- see module docstring
    },
    "j_style_scalp": {
        "premium_stop_pct": -0.50, "tp1_premium_pct": 0.50, "tp1_qty_fraction": 0.8,
        "profit_lock_mode": "trailing",
    },
    "no_trail_hold_to_time_stop": {
        # No TP1 (set absurdly high so it never fires), no premium stop except catastrophe
        # cap, no runner logic -- just ride to the 15:50 time stop or the -50% cap.
        "premium_stop_pct": -0.50, "tp1_premium_pct": 999.0, "tp1_qty_fraction": 1.0,
        "profit_lock_mode": "fixed",
    },
}


def load_fleet_engine_fills(ledger_path: Path = LEDGER) -> list[dict]:
    if not ledger_path.exists():
        return []
    out = []
    with ledger_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("arm") in FLEET_REST_ARMS and r.get("attribution") == "engine"
                    and not r.get("is_crypto") and r.get("is_option")):
                out.append(r)
    return out


def reconstruct_positions(fills: list[dict]) -> list[dict]:
    """Group raw fills into logical POSITIONS per (arm, symbol): all leading BUY fills before
    the first SELL = one entry (qty-weighted avg price, ts = first buy), all subsequent SELLs
    close it down (possibly in >1 leg -- TP1 partial + runner). A fresh BUY after the position
    is fully closed (open_qty back to 0) starts a NEW position (same-day re-entry, e.g. the
    07-08 741P AM + midday legs). PURE."""
    from collections import defaultdict
    by_key: dict = defaultdict(list)
    for f in fills:
        by_key[(f["arm"], f["symbol"])].append(f)

    positions = []
    for (arm, symbol), group in by_key.items():
        group.sort(key=lambda x: x["ts_utc"])
        pos = None  # {"entry_qty","entry_notional","entry_ts_utc","exit_fills":[]}
        open_qty = 0.0
        for f in group:
            if f["side"] == "buy":
                if open_qty <= 1e-9:
                    if pos is not None:
                        positions.append(pos)
                    pos = {"arm": arm, "symbol": symbol, "entry_qty": 0.0, "entry_notional": 0.0,
                          "entry_ts_utc": f["ts_utc"], "date_et": f["date_et"], "exit_fills": []}
                pos["entry_qty"] += f["qty"]
                pos["entry_notional"] += f["qty"] * f["price"]
                open_qty += f["qty"]
            else:  # sell
                if pos is None:
                    continue  # sell with no tracked entry (shouldn't happen for engine fills)
                pos["exit_fills"].append(f)
                open_qty -= f["qty"]
        if pos is not None:
            positions.append(pos)
    for p in positions:
        p["entry_price"] = round(p["entry_notional"] / p["entry_qty"], 4) if p["entry_qty"] else 0.0
        p["actual_exit_pnl"] = sum((ef["price"] - p["entry_price"]) * ef["qty"] * 100
                                   for ef in p["exit_fills"])
    return positions


def fetch_option_bars(symbol: str, date_et: str, start_hhmm: str = "09:29") -> list[dict]:
    """1-min option bars for `symbol` from start_hhmm ET on date_et through 16:05 ET (covers
    the 15:50 time stop with margin). REAL Alpaca OPRA data (confirmed live, not synthetic).
    Fail-open -> []."""
    creds_all = fb.load_creds()
    creds = creds_all.get("safe-1")  # any account's key works for market data
    if not creds:
        return []
    y, m, d = date_et.split("-")
    start = f"{date_et}T{_et_hhmm_to_utc(date_et, start_hhmm)}"
    end = f"{date_et}T{_et_hhmm_to_utc(date_et, '16:05')}"
    url = (f"{OPTIONS_HOST}/v1beta1/options/bars?symbols={symbol}&timeframe=1Min"
           f"&start={start}&end={end}&limit=1000")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        print(f"[exit_shape_parity_study] bar fetch error {symbol} {date_et}: {exc}", file=sys.stderr)
        return []
    bars = (data.get("bars") or {}).get(symbol) or []
    return bars


def _et_hhmm_to_utc(date_et: str, hhmm: str) -> str:
    """'2026-07-08','09:29' -> '13:29:00Z' (EDT, -4h; this rig trades only in EDT months)."""
    hh, mm = hhmm.split(":")
    utc_hh = (int(hh) + 4) % 24
    day_overflow = (int(hh) + 4) >= 24
    if day_overflow:
        # not expected for our 09:29-16:05 ET window (always same UTC day), guard anyway
        return f"{hhmm}:00Z"
    return f"{utc_hh:02d}:{mm}:00Z"


def replay_position(position: dict, bars: list[dict], shape: dict) -> dict:
    """Replay ONE position under ONE candidate shape against REAL 1-min option bars, using
    the ACTUAL live exit_manager.plan_exit_actions decision core. Returns pnl + exit trace."""
    entry_ts = position["entry_ts_utc"]
    relevant_bars = [b for b in bars if b["t"] >= entry_ts]
    if not relevant_bars:
        return {"pnl": None, "reason": "no bars at/after entry", "exits": []}

    qty = int(position["entry_qty"])
    if qty < 1:
        return {"pnl": None, "reason": "qty<1", "exits": []}
    state = ExitState.from_entry(symbol=position["symbol"], side="P", entry_premium=position["entry_price"],
                                 qty=qty, exit_shape=shape, strategy="replay")
    open_qty = qty
    realized = 0.0
    exits = []
    stopped_out = False
    stop_bar_idx = None
    for i, bar in enumerate(relevant_bars):
        bar_dt_utc = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
        now_et_dt = et_now(bar_dt_utc)
        now_et = now_et_dt.time()
        decision = plan_exit_actions(state, best_premium=bar["h"], worst_premium=bar["l"],
                                     open_qty=open_qty, now_et=now_et, ribbon_flip_back=False,
                                     time_stop_et=TIME_STOP_ET)
        for action in decision.actions:
            if action.kind in ("SELL_PARTIAL", "SELL_ALL"):
                if action.stage == "tp1":
                    fill_price = position["entry_price"] * (1.0 + state.tp1_premium_pct)
                elif action.stage == "runner_target":
                    fill_price = position["entry_price"] * (1.0 + state.runner_target_pct)
                elif action.stage in ("premium_stop", "trail", "be_stop"):
                    fill_price = state.runner_stop_premium if action.stage != "premium_stop" else (
                        position["entry_price"] * (1.0 + state.premium_stop_pct))
                    if action.stage in ("trail", "be_stop"):
                        fill_price = decision.state.runner_stop_premium
                    if action.stage == "premium_stop":
                        stopped_out = True
                        stop_bar_idx = i
                else:  # time_stop
                    fill_price = bar["c"]
                pnl_leg = (fill_price - position["entry_price"]) * action.qty * 100
                realized += pnl_leg
                open_qty -= action.qty
                exits.append({"stage": action.stage, "qty": action.qty,
                             "fill_price": round(fill_price, 4), "ts_utc": bar["t"]})
        state = decision.state
        if open_qty <= 0:
            break

    thesis_paid_after_stop = None
    if stopped_out and stop_bar_idx is not None:
        later_bars = relevant_bars[stop_bar_idx + 1:]
        thesis_paid_after_stop = any(b["h"] >= position["entry_price"] for b in later_bars)

    return {"pnl": round(realized, 2), "exits": exits, "final_open_qty": open_qty,
            "stopped_out": stopped_out, "thesis_paid_after_stop": thesis_paid_after_stop}


def main() -> int:
    fills = load_fleet_engine_fills()
    positions = reconstruct_positions(fills)
    print(f"[exit_shape_parity_study] {len(positions)} reconstructed positions from "
          f"{len(fills)} engine fleet fills")

    bar_cache: dict = {}
    results: dict = {shape_name: [] for shape_name in SHAPES}
    for pos in positions:
        key = (pos["symbol"], pos["date_et"])
        if key not in bar_cache:
            bar_cache[key] = fetch_option_bars(pos["symbol"], pos["date_et"])
            _time_mod.sleep(0.15)  # be polite to the data API
        bars = bar_cache[key]
        for shape_name, shape in SHAPES.items():
            r = replay_position(pos, bars, shape)
            r["arm"] = pos["arm"]; r["symbol"] = pos["symbol"]; r["date_et"] = pos["date_et"]
            r["entry_price"] = pos["entry_price"]; r["qty"] = pos["entry_qty"]
            r["actual_exit_pnl"] = round(pos["actual_exit_pnl"], 2)
            results[shape_name].append(r)

    summary = {}
    for shape_name, rows in results.items():
        valid = [r for r in rows if r["pnl"] is not None]
        wins = [r for r in valid if r["pnl"] > 0]
        total_pnl = round(sum(r["pnl"] for r in valid), 2)
        surrendered = [r for r in valid if r.get("stopped_out") and r.get("thesis_paid_after_stop")]
        summary[shape_name] = {
            "n_positions": len(rows), "n_valid": len(valid), "n_no_data": len(rows) - len(valid),
            "total_pnl": total_pnl,
            "win_rate": round(len(wins) / len(valid), 3) if valid else None,
            "n_stopped_out": sum(1 for r in valid if r.get("stopped_out")),
            "n_stopped_then_thesis_paid": len(surrendered),
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "exit-shape-parity-2026-07-08.json").write_text(
        json.dumps({"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "n_positions": len(positions), "summary": summary, "results": results},
                   indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
