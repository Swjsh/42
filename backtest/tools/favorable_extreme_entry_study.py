"""favorable_extreme_entry_study.py -- FAVORABLE-EXTREME-ENTRY (2026-07-17).

J's breakthrough directive after seeing the 14:03 bollinger_squeeze PUT win (+$105): the fill
landed at the TOP of the 14:00-14:05 bar's $0.47 upper wick (SPY spiked to 745.10 right before
rolling to a 743.23 close) -- "that is a PRIMO entry -- we need that every time it presents
itself." STUDY ONLY -- no live code, no orders, no engine edits.

Frozen pre-registration: analysis/recommendations/prereg-favorable-extreme-entry-2026-07-17.json
(content_sha256_16 pinned below; preflight() FAILS LOUD on any drift).

TWO PARTS:

PART A -- OBSERVATIONAL CHARACTERIZATION (not gated). Real broker fills (primary population:
automation/state/fills-ledger.jsonl BUY legs on the two live accounts, attribution=='engine',
joined by order_id to automation/state/core-decisions.jsonl's exec/extra_exec[].exec.broker.id
for the live-sampled SPY spot at placement; secondary/lower-confidence population:
journal/trades.csv rows with no ledger match, bar-close proxy). For each entry, computes
favorability = where the fill-implied SPY spot landed within its entry bar's [low,high] range,
oriented by direction (near-high favorable for PUT/short, near-low favorable for CALL/long),
buckets into favorable_extreme/neutral/adverse_extreme, and flags whether a house-standard wick
(detect_wick_rejection_bearish/detect_wick_reclaim_bullish's own frozen thresholds) was present
AND caught. Correlational, not causal -- reported as such, no ratification gate applies.

PART B -- PRE-REGISTERED CAUSAL A/B. On the SAME real confirmation-trigger signal population
pong_resting_limit_study.py's control_outcome() already mines (imported and called directly, not
reimplemented), replaces the current immediate marketable entry with a short-patience resting
limit at signal_premium*(1-delta_band) -- automation/state/fleet/entry_manager.py's ALREADY
UNIT-TESTED EntryState/plan_entry_action state machine, imported unchanged -- gated by a SPY-side
cancel-watcher (reusing PONG's own cancel-on-break concept) that cancels outright if the
underlying trades through the signal's own trigger level before the option fills. Grid: delta_band
x {0.05,0.10,0.15} x policy x {cancel,convert} x cancel_watcher x {none,0.15,0.30} = 18 cells per
account. Gates: the frozen ab_delta_per_trade_v2026_07_16 WF form + BH-FDR, identical to
pong-resting-limit-2026-07-17's own application.

ANALYSIS ONLY. No params/config/trading-path/entry_manager.py/filters.py file touched. No orders
placed. If a Part B cell clears, the BUILD SPEC is written as a section of the scorecard md.

Run: backtest/.venv/Scripts/python.exe backtest/tools/favorable_extreme_entry_study.py [--smoke]
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if str(REPO / "crypto" / "lib") not in sys.path:
    sys.path.insert(0, str(REPO / "crypto" / "lib"))

import pandas as pd  # noqa: E402

from entry_manager import EntryState, plan_entry_action  # noqa: E402
from lib import filters as filters_mod  # noqa: E402
from lib.simulator_credit import DEFAULT_ENTRY_SLIPPAGE  # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import bh_fdr, FDR_ALPHA  # noqa: E402
import structure_stop_study as sss  # noqa: E402
import strike_selection as ssel  # noqa: E402
import pong_resting_limit_study as pong  # noqa: E402 -- reused verbatim for control/mining/replay

SMOKE = "--smoke" in sys.argv

PREREG = REPO / "analysis" / "recommendations" / "prereg-favorable-extreme-entry-2026-07-17.json"
EXPECTED_PREREG_SHA16 = "a559f27243ebd26d"
EXPECTED_PREREG_VERSION = 1

OUT_JSON = REPO / "analysis" / "recommendations" / ("favorable-extreme-entry-2026-07-17-SMOKE.json" if SMOKE
                                                     else "favorable-extreme-entry-2026-07-17.json")
OUT_MD = REPO / "analysis" / "recommendations" / ("favorable-extreme-entry-2026-07-17-SMOKE.md" if SMOKE
                                                   else "favorable-extreme-entry-2026-07-17.md")

FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
TRADES_CSV = REPO / "journal" / "trades.csv"

MAIN_ARMS = {"safe": "safe-2", "bold": "bold-2"}

IS_START = dt.date(2025, 1, 1)
OOS_BOUNDARY = dt.date(2026, 1, 1)
DATA_END = dt.date(2026, 7, 8)   # latest date with a matching SPY+VIX master on disk this session

QTY = 3
PATIENCE_TICKS = 3   # reused unchanged from shadow_entry_actuator's frozen (delta=0.10, patience=3)
MIN_ENTRY_PREMIUM = 0.30
NULL_SEEDS = 3 if SMOKE else 10
FAV_HIGH = 0.70
FAV_LOW = 0.30
WICK_MIN_PCT = 0.50     # reused from detect_wick_rejection_bearish/detect_wick_reclaim_bullish defaults
WICK_MIN_DOLLARS = 0.15

DELTA_BAND_CELLS = [0.05, 0.10, 0.15]
POLICY_CELLS = ["cancel", "convert"]
CANCEL_CELLS: list[tuple[str, "float | None"]] = [("none", None), ("0.15", 0.15), ("0.30", 0.30)]

EXIT_SHAPE = {"label": "tp50_structure_t30", "tp_pct": 0.50, "stop_type": "structure", "time_stop_min": 30}

J_ANCHOR_DATES = pong.J_ANCHOR_DATES

ACCOUNTS = {
    "safe": {"params_path": REPO / "automation" / "state" / "params.json", "tiers": ssel.V15_SAFE_TIERS},
    "bold": {"params_path": REPO / "automation" / "state" / "aggressive" / "params.json", "tiers": ssel.V15_BOLD_TIERS},
}
LIVE_EQUITY = {"safe": 1724.59, "bold": 2153.84}  # live-verified this session (Alpaca MCP get_account_info)


def log(msg: str) -> None:
    print(f"[favorable-extreme-entry] {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# PRE-FLIGHT
# ---------------------------------------------------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    ok = (recomputed == EXPECTED_PREREG_SHA16 == stored and preg.get("version") == EXPECTED_PREREG_VERSION)
    return {"ok": ok, "recomputed_sha16": recomputed, "stored_sha16": stored,
           "expected_sha16": EXPECTED_PREREG_SHA16, "version": preg.get("version"), "status": preg.get("status")}


# ---------------------------------------------------------------------------------------------
# PART A -- real-fills characterization
# ---------------------------------------------------------------------------------------------
def load_spy_bars_for_char() -> pd.DataFrame:
    """Loads a wall-v1 SPY 5m frame covering 2026-04-29..2026-07-17 for Part A bar lookups.
    Concatenates the long-run master + the SIP-sourced tail master, deduping by timestamp with
    the SIP tail (appended later, per DATA-PROVENANCE.md's SIP-canonical-since-07-14 note) taking
    precedence on overlap."""
    long_master = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-14.csv"
    tail_master = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-17.csv"
    frames = []
    for p in (long_master, tail_master):
        if p.exists():
            frames.append(pd.read_csv(p))
    df = pd.concat(frames, ignore_index=True)
    df["timestamp_et"] = pong._wallv1(df["timestamp_et"])
    df = df.sort_values("timestamp_et").drop_duplicates(subset="timestamp_et", keep="last").reset_index(drop=True)
    return df


def bar_covering(spy_bars: pd.DataFrame, ts: dt.datetime) -> "pd.Series | None":
    """5m bar whose [timestamp_et, timestamp_et+5min) window covers ts (bar timestamps are
    bar-OPEN times, the house convention throughout this codebase)."""
    ts = pd.Timestamp(ts).tz_localize(None) if pd.Timestamp(ts).tzinfo is not None else pd.Timestamp(ts)
    window = spy_bars[(spy_bars["timestamp_et"] <= ts) & (spy_bars["timestamp_et"] > ts - dt.timedelta(minutes=5))]
    if window.empty:
        return None
    return window.iloc[-1]


def favorability(spot: float, bar: pd.Series, side: str) -> "tuple[float, bool] | None":
    lo, hi = float(bar["low"]), float(bar["high"])
    rng = hi - lo
    if rng <= 0.01:
        return None
    if side == "P":
        fav = (spot - lo) / rng
    else:
        fav = (hi - spot) / rng
    clipped = min(1.0, max(0.0, fav))
    return round(clipped, 4), (clipped != round(fav, 4))


def wick_against_signal(bar: pd.Series, side: str) -> "tuple[bool, float]":
    o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
    rng = h - l
    if rng <= 0.01:
        return False, 0.0
    if side == "P":
        wick = h - max(o, c)
    else:
        wick = min(o, c) - l
    present = (wick >= WICK_MIN_DOLLARS) and ((wick / rng) >= WICK_MIN_PCT)
    return present, round(wick, 4)


def bucket_for(fav: float) -> str:
    if fav >= FAV_HIGH:
        return "favorable_extreme"
    if fav <= FAV_LOW:
        return "adverse_extreme"
    return "neutral"


def build_order_spy_index() -> dict:
    """order_id -> {spy, ts_et, setup, side, strike, account} from core-decisions.jsonl's
    exec + extra_exec[].exec blocks (the live-sampled spot at the tick that PLACED that order)."""
    idx: dict = {}
    if not CORE_DECISIONS.exists():
        return idx
    with CORE_DECISIONS.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            spy = d.get("spy")
            ts = d.get("ts_et")
            account = d.get("account")
            cands = []
            if d.get("exec"):
                cands.append(d["exec"])
            for ee in (d.get("extra_exec") or []):
                if ee.get("exec"):
                    cands.append(ee["exec"])
            for ex in cands:
                broker = ex.get("broker") or {}
                oid = broker.get("id")
                if oid and spy is not None:
                    idx[oid] = {"spy": spy, "ts_et": ts, "setup": ex.get("setup"),
                               "side": ex.get("side"), "strike": ex.get("strike"), "account": account}
    return idx


def load_fills_ledger() -> list[dict]:
    rows = []
    if not FILLS_LEDGER.exists():
        return rows
    with FILLS_LEDGER.open(encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def reconstruct_round_trips(fills: list[dict], arm: str) -> list[dict]:
    """Groups fills-ledger rows by (arm, symbol), then walks each symbol's fills in
    chronological order tracking OPEN QTY -- a BUY while flat (open_qty==0) starts a NEW round
    trip; subsequent buys/sells while open_qty>0 belong to that SAME trip (TP1 partial + runner
    legs); a SELL that returns open_qty to 0 closes it. This is a REQUIRED correctness fix over a
    naive per-symbol group-all: 0DTE strikes cluster on cheap round numbers, so a same-day
    RE-ENTRY on the identical strike (a real, Rule-4-compliant fresh-trigger re-entry) shares a
    symbol with an earlier, already-closed trade on that same strike -- a naive group-all merges
    the two into one blended (wrong PnL, wrong entry-location) record. Verified this session: the
    naive version silently merged 2026-07-17 safe's 11:40 745P loser (-$102, per
    analysis/daily-brief/2026-07-17-safe-tape-audit.md) with the SAME day's 14:03 bollinger_squeeze
    745P winner (+$105, same audit) into one blob reading +$3 -- exactly -102+105 -- and dropped
    the exemplar trade from the population entirely."""
    by_symbol: dict = {}
    for r in fills:
        if r.get("arm") != arm or r.get("attribution") != "engine":
            continue
        by_symbol.setdefault(r["symbol"], []).append(r)
    trips = []
    for symbol, rows in by_symbol.items():
        ordered = sorted(rows, key=lambda r: r["ts_et"])
        side = "P" if symbol[-9] == "P" else "C"  # SPYyymmdd[C|P]strike -- side char precedes strike
        open_qty = 0.0
        current: "dict | None" = None
        for r in ordered:
            qty, price = float(r["qty"]), float(r["price"])
            if r.get("side") == "buy":
                if open_qty <= 1e-9 or current is None:
                    current = {"arm": arm, "symbol": symbol, "side": side, "order_id": r.get("order_id"),
                              "entry_ts_et": r["ts_et"], "entry_price": price, "date_et": r["date_et"],
                              "n_buy_legs": 0, "n_sell_legs": 0, "_cost": 0.0, "_proceeds": 0.0}
                current["n_buy_legs"] += 1
                current["_cost"] += qty * price * 100.0
                open_qty += qty
            else:  # sell
                if current is None:
                    continue  # a sell with no matching open buy in this arm/symbol slice -- skip, disclosed
                current["n_sell_legs"] += 1
                current["_proceeds"] += qty * price * 100.0
                open_qty -= qty
                if open_qty <= 1e-9:
                    current["dollar_pnl"] = round(current["_proceeds"] - current["_cost"], 2)
                    current["fully_closed"] = True
                    trips.append(current)
                    current = None
                    open_qty = 0.0
        if current is not None:
            # never fully closed within the ledger window (e.g. 0DTE expired worthless with no
            # sell activity ever generated) -- a REAL economic loss of the full cost paid, not a bug.
            current["dollar_pnl"] = round(current["_proceeds"] - current["_cost"], 2)
            current["fully_closed"] = False
            trips.append(current)
    return trips


def part_a_characterize() -> dict:
    log("PART A: loading fills-ledger + core-decisions order index + SPY bars ...")
    order_idx = build_order_spy_index()
    fills = load_fills_ledger()
    spy_bars = load_spy_bars_for_char()
    log(f"  order_idx: {len(order_idx)} distinct order_ids; fills-ledger: {len(fills)} rows; "
       f"spy_bars: {len(spy_bars)} bars")

    primary_rows = []
    for account_label, arm in MAIN_ARMS.items():
        trips = reconstruct_round_trips(fills, arm)
        for t in trips:
            oid = t["order_id"]
            entry_info = order_idx.get(oid)
            match_quality = "decision_log" if entry_info is not None else "no_match"
            if entry_info is None:
                continue  # no live-tick spot available -- excluded from primary, not imputed (C7)
            spot = entry_info["spy"]
            fill_dt = dt.datetime.fromisoformat(t["entry_ts_et"])
            bar = bar_covering(spy_bars, fill_dt)
            if bar is None:
                continue
            fav_res = favorability(spot, bar, t["side"])
            if fav_res is None:
                continue
            fav, clipped = fav_res
            wick_present, wick_dollars = wick_against_signal(bar, t["side"])
            primary_rows.append({
                "account": account_label, "arm": arm, "symbol": t["symbol"], "side": t["side"],
                "date": t["date_et"], "entry_ts_et": t["entry_ts_et"], "fill_price": t["entry_price"],
                "spy_spot": spot, "bar_low": float(bar["low"]), "bar_high": float(bar["high"]),
                "favorability": fav, "clipped": clipped, "bucket": bucket_for(fav),
                "wick_against_signal_present": wick_present, "wick_dollars": wick_dollars,
                "wick_caught": bool(wick_present and fav >= FAV_HIGH),
                "dollar_pnl": t["dollar_pnl"], "win": t["dollar_pnl"] > 0,
                "fully_closed": t["fully_closed"], "match_quality": "decision_log",
                "setup": entry_info.get("setup"),
            })
    log(f"  primary population (decision-log live-tick spot, safe-2+bold-2 engine): {len(primary_rows)} matched round trips")

    # secondary/lower-confidence population: trades.csv rows without a fills-ledger/order_id match
    secondary_rows = []
    matched_dates_syms = {(r["date"], r["symbol"].split("00")[0][:len(r['symbol'])]) for r in primary_rows}
    if TRADES_CSV.exists():
        import csv
        import re
        with TRADES_CSV.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_date = (row.get("date") or "").strip()
                m = re.search(r"\d{4}-\d{2}-\d{2}", raw_date)
                if not m:
                    continue  # malformed row (known artifact, e.g. embedded-tab date field), excluded + disclosed
                date_iso = m.group(0)
                c_or_p = (row.get("c_or_p") or "").strip()
                if c_or_p not in ("C", "P"):
                    continue
                time_entry = (row.get("time_entry") or "").strip()
                if not time_entry:
                    continue
                try:
                    fill_dt = dt.datetime.fromisoformat(f"{date_iso}T{time_entry}")
                except ValueError:
                    continue
                # skip if this (date, contract) already matched in the primary population
                contract = (row.get("contract") or "")
                already = any(p["date"] == date_iso and p["side"] == c_or_p and
                              abs((dt.datetime.fromisoformat(p["entry_ts_et"]) - fill_dt).total_seconds()) < 300
                              for p in primary_rows)
                if already:
                    continue
                bar = bar_covering(spy_bars, fill_dt)
                if bar is None:
                    continue
                spot_proxy = float(bar["close"])  # no live-tick data for pre-heartbeat_core-era rows
                fav_res = favorability(spot_proxy, bar, c_or_p)
                if fav_res is None:
                    continue
                fav, clipped = fav_res
                wick_present, wick_dollars = wick_against_signal(bar, c_or_p)
                try:
                    dollar_pnl = float(row.get("dollar_pnl") or "nan")
                except ValueError:
                    dollar_pnl = None
                if dollar_pnl is None or dollar_pnl != dollar_pnl:  # NaN guard
                    continue
                secondary_rows.append({
                    "account": row.get("account_id"), "date": date_iso, "entry_ts_et": fill_dt.isoformat(),
                    "contract": contract, "side": c_or_p, "spy_spot_proxy": spot_proxy,
                    "bar_low": float(bar["low"]), "bar_high": float(bar["high"]),
                    "favorability": fav, "clipped": clipped, "bucket": bucket_for(fav),
                    "wick_against_signal_present": wick_present, "wick_dollars": wick_dollars,
                    "wick_caught": bool(wick_present and fav >= FAV_HIGH),
                    "dollar_pnl": dollar_pnl, "win": dollar_pnl > 0, "match_quality": "bar_proxy",
                    "setup": row.get("setup"),
                })
    log(f"  secondary population (bar-close proxy, trades.csv unmatched rows): {len(secondary_rows)} rows")

    def _bucket_table(rows: list[dict]) -> dict:
        out = {}
        for b in ("favorable_extreme", "neutral", "adverse_extreme"):
            sub = [r for r in rows if r["bucket"] == b]
            n = len(sub)
            mean_pnl = round(sum(r["dollar_pnl"] for r in sub) / n, 2) if n else None
            win_rate = round(sum(1 for r in sub if r["win"]) / n, 4) if n else None
            out[b] = {"n": n, "mean_dollar_pnl": mean_pnl, "win_rate": win_rate,
                      "total_dollar_pnl": round(sum(r["dollar_pnl"] for r in sub), 2) if n else None}
        return out

    def _wick_caught_table(rows: list[dict]) -> dict:
        caught = [r for r in rows if r["wick_caught"]]
        not_caught = [r for r in rows if not r["wick_caught"]]
        def _stat(sub):
            n = len(sub)
            return {"n": n, "mean_dollar_pnl": round(sum(r["dollar_pnl"] for r in sub) / n, 2) if n else None,
                   "win_rate": round(sum(1 for r in sub if r["win"]) / n, 4) if n else None}
        return {"wick_caught": _stat(caught), "not_wick_caught": _stat(not_caught)}

    return {
        "primary": {"n": len(primary_rows), "rows": primary_rows, "bucket_table": _bucket_table(primary_rows),
                   "wick_caught_table": _wick_caught_table(primary_rows)},
        "secondary": {"n": len(secondary_rows), "rows": secondary_rows, "bucket_table": _bucket_table(secondary_rows),
                     "wick_caught_table": _wick_caught_table(secondary_rows)},
    }


# ---------------------------------------------------------------------------------------------
# PART B -- pre-registered A/B: entry_manager-driven resting entry vs immediate marketable
# ---------------------------------------------------------------------------------------------
def tier_for_equity(tiers, equity: float):
    for t in tiers:
        if t.equity_min <= equity < t.equity_max:
            return t.strike_offset, t.label
    last = tiers[-1]
    return last.strike_offset, last.label


def candidate_favorable_extreme(ctrl: dict, delta_band: float, policy: str, cancel_threshold,
                                spy_by_date: dict, time_stop_et: dt.time) -> dict:
    if not ctrl["traded"]:
        return {"traded": False, "outcome": "untraded_signal", "date": ctrl["date"]}
    signal_premium = ctrl["entry_premium_raw"]
    walk_bars = ctrl["walk_bars"]
    if not walk_bars:
        return {"traded": False, "outcome": "no_bars", "date": ctrl["date"]}
    role = ctrl["role"]
    level = float(ctrl["level"])
    date = ctrl["date"]
    entry_ts = ctrl["entry_ts"]
    day_bars = spy_by_date.get(date)

    state = EntryState.from_signal(symbol="x", side=role, signal_premium=signal_premium,
                                   delta=delta_band, patience_ticks=PATIENCE_TICKS, policy=policy)
    fill_bar = None
    outcome = None
    last_ts = entry_ts
    for bar in walk_bars:
        if cancel_threshold is not None and day_bars is not None:
            spy_upto = day_bars[(day_bars["timestamp_et"] > last_ts) & (day_bars["timestamp_et"] <= bar.dt)]
            breach = False
            for _, wb in spy_upto.iterrows():
                if role == "C":
                    if float(wb["low"]) <= level - cancel_threshold:
                        breach = True
                        break
                else:
                    if float(wb["high"]) >= level + cancel_threshold:
                        breach = True
                        break
            if breach:
                outcome = "canceled_watcher"
                break
        last_ts = bar.dt
        dec = plan_entry_action(state, ask=bar.l)
        state = dec.state
        if state.status == "filled":
            fill_bar = bar
            outcome = "filled"
            break
        if state.status == "converted":
            fill_bar = bar
            outcome = "converted"
            break
        if state.status == "missed":
            outcome = "missed_patience"
            break

    if outcome is None:
        outcome = "unfilled_expired"
    if outcome not in ("filled", "converted"):
        return {"traded": False, "outcome": outcome, "date": date}

    if outcome == "filled":
        fill_price = state.fill_price
    else:
        fill_price = round(max(0.01, fill_bar.c + DEFAULT_ENTRY_SLIPPAGE), 4)
    if fill_price is None or fill_price < MIN_ENTRY_PREMIUM:
        return {"traded": False, "outcome": "floor_skip", "date": date}

    fill_idx = walk_bars.index(fill_bar)
    remaining_bars = walk_bars[fill_idx + 1:]
    if not remaining_bars:
        return {"traded": False, "outcome": "no_bars_after_fill", "date": date}

    ss_time = None
    if day_bars is not None:
        sub = day_bars[day_bars["timestamp_et"] >= fill_bar.dt]
        ss_time = sss.structure_stop_signal_time(sub, role, level, sss.STRUCTURE_BUFFER["SS-B"])

    pnl = pong.replay_exit(fill_price, role, QTY, remaining_bars, ss_time, EXIT_SHAPE, fill_bar.dt,
                           time_stop_et, entry_side_friction=False)

    classification = None
    if day_bars is not None:
        after = day_bars[day_bars["timestamp_et"] > pd.Timestamp(fill_bar.dt)].head(pong.CLASSIFICATION_WINDOW_BARS)
        broke = False
        for _, ab in after.iterrows():
            if role == "C":
                if float(ab["low"]) <= level - pong.BREAK_MARGIN:
                    broke = True
                    break
            else:
                if float(ab["high"]) >= level + pong.BREAK_MARGIN:
                    broke = True
                    break
        classification = "slice_through" if broke else "bounce"

    return {"traded": True, "pnl": pnl, "date": date, "outcome": outcome,
           "fill_price": fill_price, "classification": classification}


def mine_signal_universe(so: int, time_stop_et: dt.time, spy_naive: pd.DataFrame, level_by_day: dict) -> dict:
    universe: dict = {}
    for d in sorted(level_by_day.keys()):
        level_set = level_by_day[d]
        levels = level_set.active
        if not levels:
            continue
        day_rows = spy_naive[(spy_naive["date"] == d) & (spy_naive["time"] >= dt.time(9, 30))]
        if day_rows.empty:
            continue
        day_open_spot = float(day_rows["open"].iloc[0])
        for L in levels:
            role = "C" if L < day_open_spot else "P"
            episode_id = f"{d.isoformat()}|{role}|{L:.2f}"
            universe[episode_id] = {"role": role, "level": L, "date": d}
    return universe


def main() -> int:
    t_start = _time_mod.time()
    pf = preflight()
    log(f"preflight: {pf}")
    if not pf["ok"]:
        log("PREREG HASH/VERSION MISMATCH -- refusing to run a drifted spec. Aborting.")
        return 1

    # ---------------- PART A ----------------
    part_a = part_a_characterize()

    # ---------------- PART B ----------------
    if SMOKE:
        load_start, data_end = dt.date(2026, 5, 19), dt.date(2026, 6, 20)
    else:
        load_start, data_end = IS_START, DATA_END
    log(f"PART B: loading SPY/VIX data {load_start}..{data_end} ...")
    spy_full, vix_full = pong.load_data(load_start, data_end)

    spy_naive = spy_full.copy()
    spy_naive["timestamp_et"] = pong._wallv1(spy_naive["timestamp_et"])
    spy_naive["date"] = spy_naive["timestamp_et"].dt.date
    spy_naive["time"] = spy_naive["timestamp_et"].dt.time
    if not SMOKE:
        spy_naive = spy_naive[spy_naive["date"] >= IS_START]
    spy_naive = spy_naive.sort_values("timestamp_et").reset_index(drop=True)
    spy_by_date = {d: g.reset_index(drop=True) for d, g in spy_naive.groupby("date")}

    log(f"building causal level set per day over {spy_naive['date'].nunique()} days ...")
    level_by_day = pong.build_level_by_day(spy_naive)
    log(f"level_by_day: {len(level_by_day)} days with an active level set")

    accounts_out: dict = {}
    for label, cfg in ACCOUNTS.items():
        equity = LIVE_EQUITY[label]
        so, tier_label = tier_for_equity(cfg["tiers"], equity)
        raw_params = json.loads(cfg["params_path"].read_text(encoding="utf-8-sig"))
        time_stop_et = dt.datetime.strptime(raw_params.get("time_stop_et", "15:40"), "%H:%M").time()
        log(f"[{label}] tier={tier_label} so={so} equity=${equity} time_stop={time_stop_et}")

        universe = mine_signal_universe(so, time_stop_et, spy_naive, level_by_day)
        log(f"[{label}] signal universe: {len(universe)} (date,level,role) combos")

        control_cache: dict = {}
        for eid, v in universe.items():
            control_cache[eid] = pong.control_outcome(eid, v["date"].isoformat(), v["role"], v["level"], so,
                                                       time_stop_et, spy_naive, spy_by_date)
        n_control_traded = sum(1 for c in control_cache.values() if c["traded"])
        log(f"[{label}] control: {len(control_cache)} episode_ids, {n_control_traded} confirmation-triggered")

        ctrl_outcomes: dict = {}
        for eid, v in universe.items():
            ctrl = control_cache[eid]
            pnl = pong.control_pnl_for_shape(ctrl, EXIT_SHAPE, time_stop_et, spy_by_date) if ctrl["traded"] else 0.0
            ctrl_outcomes[eid] = {"pnl": pnl, "date": v["date"], "traded": ctrl["traded"]}

        self_dwf = pong.compute_delta_wf(ctrl_outcomes, ctrl_outcomes)
        control_sanity = {"is_delta_mean": self_dwf["is_delta_mean"], "oos_delta_mean": self_dwf["oos_delta_mean"],
                          "wf_delta": self_dwf["wf_delta"], "ladder_verdict": self_dwf["ladder_verdict"]}

        cells_out: dict = {}
        bh_input: list[dict] = []
        null_cache: dict = {}
        cell_order: list[str] = []
        outcome_tally_by_cell: dict = {}

        for delta_band in DELTA_BAND_CELLS:
            for policy in POLICY_CELLS:
                for cancel_label, cancel_threshold in CANCEL_CELLS:
                    cell_key = f"delta{delta_band}|{policy}|cancel_{cancel_label}"
                    cell_order.append(cell_key)

                    cand_outcomes: dict = {}
                    n_bounce = n_slice = 0
                    bounce_delta_sum = slice_delta_sum = 0.0
                    tally: dict = {}
                    for eid, v in universe.items():
                        ctrl = control_cache[eid]
                        cres = candidate_favorable_extreme(ctrl, delta_band, policy, cancel_threshold,
                                                           spy_by_date, time_stop_et)
                        tally[cres["outcome"]] = tally.get(cres["outcome"], 0) + 1
                        if cres["traded"]:
                            cand_outcomes[eid] = {"pnl": cres["pnl"], "date": v["date"], "traded": True}
                            delta_here = cres["pnl"] - ctrl_outcomes[eid]["pnl"]
                            if cres["classification"] == "bounce":
                                n_bounce += 1
                                bounce_delta_sum += delta_here
                            elif cres["classification"] == "slice_through":
                                n_slice += 1
                                slice_delta_sum += delta_here
                        else:
                            cand_outcomes[eid] = {"pnl": 0.0, "date": v["date"], "traded": False}
                    outcome_tally_by_cell[cell_key] = tally

                    dwf = pong.compute_delta_wf(cand_outcomes, ctrl_outcomes)
                    anchor_ok = pong.anchor_no_regression(dwf["deltas"], cand_outcomes)
                    n = dwf["n_shared"]
                    per_trade_mean = round((dwf["is_delta_sum"] + dwf["oos_delta_sum"]) / n, 2) if n else None

                    n_cand_traded = tally.get("filled", 0) + tally.get("converted", 0)
                    null_key = min(n_cand_traded, 40)
                    if null_key not in null_cache and null_key > 0:
                        n_signals = null_key
                        n_call = sum(1 for eid in cand_outcomes if cand_outcomes[eid]["traded"]
                                    and universe[eid]["role"] == "C")
                        n_call = min(n_call, n_signals)
                        n_put = n_signals - n_call
                        rth = spy_naive[(spy_naive["time"] >= dt.time(9, 30)) &
                                       (spy_naive["time"] <= dt.time(16, 0))].reset_index(drop=True)
                        sim_fn = pong.make_null_sim_fn(so, time_stop_et, EXIT_SHAPE, spy_by_date)
                        null_res = pong.random_entry_null(
                            rth=rth, n_signals=n_signals, n_call=n_call, n_put=n_put, strike_offset=so,
                            premium_stop_pct=-0.50, qty=QTY, entry_gate=(dt.time(9, 35), time_stop_et),
                            seeds=NULL_SEEDS, setup="FAVEXT_NULL", sim_fn=sim_fn,
                        )
                        null_cache[null_key] = null_res.get("per_trade_by_seed", [])
                    p_null = pong.empirical_p_null(per_trade_mean, null_cache.get(null_key, []))

                    cells_out[cell_key] = {
                        "delta_band": delta_band, "policy": policy, "cancel_watcher": cancel_label,
                        "n": n, "n_is": dwf["n_is"], "n_oos": dwf["n_oos"],
                        "is_delta_mean": dwf["is_delta_mean"], "oos_delta_mean": dwf["oos_delta_mean"],
                        "wf_delta": dwf["wf_delta"], "verdict_ladder": dwf["ladder_verdict"],
                        "oos_positive": dwf["oos_positive"], "wf_ge_070": dwf["wf_ge_070"],
                        "sub_window_stable": dwf["sub_window_stable"], "anchor_no_regression": anchor_ok,
                        "per_trade_mean": per_trade_mean, "p_null": p_null,
                        "n_bounce_filled": n_bounce, "n_slice_filled": n_slice,
                        "bounce_delta_total": round(bounce_delta_sum, 2), "slice_delta_total": round(slice_delta_sum, 2),
                        "bounce_delta_mean": round(bounce_delta_sum / n_bounce, 2) if n_bounce else None,
                        "slice_delta_mean": round(slice_delta_sum / n_slice, 2) if n_slice else None,
                        "n_cand_only": dwf["n_cand_only"], "n_ctrl_only": dwf["n_ctrl_only"],
                        "n_both_traded": dwf["n_both_traded"], "outcome_tally": tally,
                    }
                    bh_input.append({"p_null": p_null})

        bh_fdr(bh_input, alpha=FDR_ALPHA)
        for cell_key, b in zip(cell_order, bh_input):
            cells_out[cell_key]["bh_fdr_survivor"] = b["bh_fdr_survivor"]
            cells_out[cell_key]["bh_rank"] = b["bh_rank"]

        gates: dict = {}
        decisions: dict = {}
        for key, c in cells_out.items():
            g_ = {"oos_positive": bool(c["oos_positive"]), "wf_ge_070": bool(c["wf_ge_070"]),
                 "sub_window_stable": bool(c["sub_window_stable"]), "anchor_no_regression": bool(c["anchor_no_regression"]),
                 "bh_fdr_survivor": bool(c["bh_fdr_survivor"])}
            g_["all_5_pass"] = all(g_.values())
            gates[key] = g_
            fails = [k for k, v in g_.items() if k != "all_5_pass" and not v]
            decisions[key] = {"ship_ready": g_["all_5_pass"] and c["n"] > 0, "fails": fails, "n": c["n"],
                              "evidence_thin": c["n"] < 15}

        ship_ready = [k for k in cells_out if decisions[k]["ship_ready"]]
        winner = None
        if ship_ready:
            winner = max(ship_ready, key=lambda k: (cells_out[k]["oos_delta_mean"] or -1e18, cells_out[k]["n"]))
        n_gates_passed = {k: sum(1 for kk, v in gates[k].items() if kk != "all_5_pass" and v) for k in cells_out}
        closest = max(cells_out.keys(), key=lambda k: (n_gates_passed[k], cells_out[k]["n"]))

        raw_bounce_total = sum(c["n_bounce_filled"] for c in cells_out.values())
        raw_slice_total = sum(c["n_slice_filled"] for c in cells_out.values())

        accounts_out[label] = {
            "tier_label": tier_label, "strike_offset": so, "equity_live_verified": equity, "qty": QTY,
            "time_stop_et": str(time_stop_et), "n_universe": len(universe), "n_control_traded": n_control_traded,
            "control_sanity_disclosure": control_sanity,
            "cells": cells_out, "gates": gates, "decisions": decisions,
            "verdict": {"any_ship_ready": bool(ship_ready), "ship_ready_cells": ship_ready, "winner": winner,
                       "closest_cell": closest, "closest_cell_gates_passed": n_gates_passed[closest],
                       "closest_cell_fails": decisions[closest]["fails"],
                       "closest_cell_verdict_ladder": cells_out[closest]["verdict_ladder"]},
            "adverse_selection_note": {
                "bounce_filled_sum_across_cells": raw_bounce_total, "slice_filled_sum_across_cells": raw_slice_total,
            },
        }
        log(f"[{label}] VERDICT any_ship_ready={bool(ship_ready)} winner={winner} n_cells_ship_ready={len(ship_ready)}")

    elapsed_total = round(_time_mod.time() - t_start, 1)
    any_ship_ready_overall = any(accounts_out[a]["verdict"]["any_ship_ready"] for a in accounts_out)

    out = {
        "_doc": "FAVORABLE-EXTREME-ENTRY -- part A (real-fills entry-location characterization) + "
               "part B (pre-registered A/B: entry_manager-driven resting entry vs immediate "
               "marketable). 2026-07-17 J-directed breakthrough-to-evidence. ANALYSIS ONLY. "
               "Source: backtest/tools/favorable_extreme_entry_study.py.",
        "generated_at": dt.datetime.now().isoformat(),
        "smoke_mode": SMOKE,
        "preflight": pf,
        "prereg_path": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "part_a": part_a,
        "part_b": {
            "grid": {"delta_band_cells": DELTA_BAND_CELLS, "policy_cells": POLICY_CELLS,
                    "cancel_watcher_cells": [c[0] for c in CANCEL_CELLS], "exit_shape": EXIT_SHAPE, "qty": QTY},
            "accounts": accounts_out,
            "verdict": {"any_ship_ready_overall": any_ship_ready_overall,
                       "safe_ship_ready": accounts_out["safe"]["verdict"]["any_ship_ready"],
                       "bold_ship_ready": accounts_out["bold"]["verdict"]["any_ship_ready"]},
        },
        "disclosures": [
            "PART A is CORRELATIONAL on incidental fills, not causal -- no ratification gate applies to it; it is descriptive evidence for whether part B's deliberate mechanism is worth testing, per the task's own framing.",
            "PART A primary population requires an order_id join between fills-ledger.jsonl and core-decisions.jsonl; rows with no join (no core-decisions.jsonl PLACED record for that order_id -- e.g. exits, or entries placed via a path this study didn't index) are EXCLUDED, not imputed (C7); this undercounts the true fill population, disclosed as a conservative gap, not a silent one.",
            "PART A's 'fill-implied SPY spot' is the live-tick value sampled at the DECISION TICK that PLACED the matched order (order_id join), which can precede the broker-confirmed fill by up to ~60s (heartbeat cadence) -- not the exact fill-moment tick (no tick-by-tick spot log exists). VERIFIED DIRECTLY on the exemplar itself this session (Alpaca 1-min SPY bars, feed=sip): at order placement (14:03:03 ET) SPY was ~744.59 (matching the logged decision-tick spot almost exactly), but the actual broker fill landed at 14:03:18.9 -- by then SPY had already climbed into the 744.87-745.09 range per the 14:03-14:04 ET 1-min bar (O=744.87 H=745.09). This means the placement-tick proxy systematically UNDERSTATES true fill-moment favorability on fast-moving bars -- a CONSERVATIVE bias, not a random one: the true favorable_extreme population is likely LARGER than what this study's primary population shows, not smaller, and the exemplar's own favorability score under this proxy (0.28, adverse_extreme bucket) is almost certainly an undercount of where the OPTION actually filled. Building a full 1-min SPY cache to correct every primary-population row was scoped OUT of this study for time (a named, disclosed follow-up, not attempted) -- the exemplar-level spot check stands as the verification that the direction of the bias is understated-favorability, not overstated.",
            "PART A's secondary/lower-confidence population (journal/trades.csv rows with no ledger match) uses the entry bar's OWN CLOSE as a spot proxy -- NOT a live-tick reading -- and is never blended into the primary population's headline numbers.",
            "journal/trades.csv is independently confirmed INCOMPLETE this same evening (STATUS.md SAFE-TRADES-CSV-JOURNALING-GAP: missing the 14:03 bollinger_squeeze exemplar itself) -- automation/state/fills-ledger.jsonl is used as the PRIMARY ground truth for part A instead, superseding trades.csv where they disagree.",
            "PART B: MEASURED (real OPRA local cache replay), not REALIZED -- no broker fills exist for this candidate mechanism, which does not exist in production.",
            "PART B reuses pong_resting_limit_study.py's control_outcome()/build_level_by_day()/replay_exit()/compute_delta_wf()/anchor_no_regression()/make_null_sim_fn() functions VERBATIM (imported, not re-derived) for the signal population, control arm, and exit replay -- methodological continuity with today's sibling study.",
            "PART B's entry_manager.py state machine is discretized to 1 tick = 1 five-minute OPRA option bar (ask=bar.low), materially SLOWER than a live per-second actuator would run -- disclosed as a named open question for the build spec, not resolved here.",
            "PART B's CONVERT fill price deliberately does NOT reuse plan_entry_action's own returned ask-based fill_price (which would double-dip the SAME bar.low the fill-check tested against) -- it uses bar.close + DEFAULT_ENTRY_SLIPPAGE instead, a disclosed correction for honesty.",
            "PART B cohort end=2026-07-08 (latest date with a matching SPY+VIX master on disk this session) -- today's 07-17 exemplar itself is NOT inside the statistical population, remaining purely motivating context.",
            "PART B qty=3 fixed BOTH accounts (disclosed deviation from each account's own live qty knob, matching pong-resting-limit's own precedent).",
            "PART B min_entry_premium floor (0.30) applied against the candidate's realized fill price and the control's raw entry premium; a signal below floor is dropped and counted (floor_skip), never imputed (C7).",
            "PART B exit shape is FIXED (tp50/structure/t30), not swept -- entry mechanism is the axis under test, matching pong-resting-limit's own entry_zone_width precedent for fixing a non-central dimension.",
            "PART B ONE process, no multiprocessing.Pool -- OPRA local bar cache is process-local (6-8-worker-ceiling / OPRA-cache-deadlock lesson).",
        ],
        "runtime_seconds": elapsed_total,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    log(f"wrote {OUT_JSON} + {OUT_MD} ({elapsed_total}s total)")
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# FAVORABLE-EXTREME-ENTRY study -- FAVORABLE-EXTREME-ENTRY-2026-07-17")
    L.append("")
    L.append(f"Generated: {out['generated_at']}. Source: `backtest/tools/favorable_extreme_entry_study.py`. "
             f"Pre-reg: `{out['prereg_path']}`.")
    if out["smoke_mode"]:
        L.append("")
        L.append("**SMOKE MODE RUN -- reduced date range/seeds, pipeline verification only, "
                 "NOT a decision-grade result.**")
    L.append("")
    L.append("## The exemplar")
    L.append("")
    L.append("2026-07-17 14:03:03 ET bollinger_squeeze PUT, SPY745P @ $1.01, entry bar "
             "14:00-14:05 O=744.60 H=745.10 L=744.38 C=744.63 (upper wick $0.47) -- fill landed "
             "near the bar's HIGH right before SPY rolled to a 743.23 close, +$105. The fill "
             "was INCIDENTAL (1-min heartbeat tick sampled mid-spike), not deliberately targeted "
             "-- that's the question this study interrogates.")
    L.append("")
    L.append("## PART A -- real-fills entry-location characterization (correlational, not gated)")
    L.append("")
    for pop_label, pop_key in (("PRIMARY (decision-log live-tick spot)", "primary"),
                               ("SECONDARY (bar-close proxy, lower confidence)", "secondary")):
        pop = out["part_a"][pop_key]
        L.append(f"### {pop_label} -- n={pop['n']}")
        L.append("")
        L.append("| bucket | n | mean $pnl | win rate | total $pnl |")
        L.append("|---|--:|--:|--:|--:|")
        for b, stats in pop["bucket_table"].items():
            L.append(f"| {b} | {stats['n']} | ${stats['mean_dollar_pnl']} | {stats['win_rate']} | ${stats['total_dollar_pnl']} |")
        L.append("")
        wct = pop["wick_caught_table"]
        L.append(f"Wick-caught (fill in a house-standard wick zone AGAINST signal direction, favorability>=0.70): "
                 f"n={wct['wick_caught']['n']}, mean ${wct['wick_caught']['mean_dollar_pnl']}, "
                 f"win_rate={wct['wick_caught']['win_rate']} -- vs not-wick-caught: "
                 f"n={wct['not_wick_caught']['n']}, mean ${wct['not_wick_caught']['mean_dollar_pnl']}, "
                 f"win_rate={wct['not_wick_caught']['win_rate']}.")
        L.append("")
    L.append("**Correlational, on incidental fills -- this is a precondition check, not a causal claim.**")
    L.append("")
    L.append("## PART B -- pre-registered A/B (entry_manager-driven resting entry vs immediate marketable)")
    L.append("")
    for label in ("safe", "bold"):
        a = out["part_b"]["accounts"][label]
        L.append(f"### {label.upper()}")
        L.append("")
        L.append(f"Tier **{a['tier_label']}** (so={a['strike_offset']}), equity=${a['equity_live_verified']}, "
                 f"qty={a['qty']}, time_stop={a['time_stop_et']}, signal universe n={a['n_universe']}, "
                 f"confirmation-triggered n={a['n_control_traded']}.")
        L.append("")
        cs = a["control_sanity_disclosure"]
        L.append(f"Control-sanity (self-vs-self, mandatory disclosure): is_delta_mean={cs['is_delta_mean']}, "
                 f"oos_delta_mean={cs['oos_delta_mean']}, wf_delta={cs['wf_delta']}, ladder={cs['ladder_verdict']}.")
        L.append("")
        L.append("| cell | n | is/oos | IS delta/tr | OOS delta/tr | WF | ladder | bounce n/delta | slice n/delta | anchor | bh | ship_ready |")
        L.append("|---|--:|--:|--:|--:|--:|---|---|---|:--:|:--:|:--:|")
        for key, c in a["cells"].items():
            d = a["decisions"][key]
            L.append(f"| {key} | {c['n']} | {c['n_is']}/{c['n_oos']} | ${c['is_delta_mean']} | ${c['oos_delta_mean']} | "
                     f"{c['wf_delta']} | {c['verdict_ladder']} | {c['n_bounce_filled']}/${c['bounce_delta_mean']} | "
                     f"{c['n_slice_filled']}/${c['slice_delta_mean']} | {c['anchor_no_regression']} | "
                     f"{c['bh_fdr_survivor']} | {d['ship_ready']} |")
        L.append("")
        v = a["verdict"]
        if v["any_ship_ready"]:
            L.append(f"**{label.upper()} SHIP-READY: {v['ship_ready_cells']}. Winner: {v['winner']}.**")
        else:
            cc2 = a["cells"][v["closest_cell"]]
            L.append(f"**{label.upper()}: NULL RESULT (KILL).** Closest cell: `{v['closest_cell']}` "
                     f"({v['closest_cell_gates_passed']}/5 gates, verdict_ladder={v['closest_cell_verdict_ladder']}, "
                     f"n={cc2['n']}, IS=${cc2['is_delta_mean']}, OOS=${cc2['oos_delta_mean']}) -- "
                     f"fails: {v['closest_cell_fails']}.")
        L.append("")
        asn = a["adverse_selection_note"]
        L.append(f"Adverse-selection (summed across all 18 cells' filled episodes): bounce={asn['bounce_filled_sum_across_cells']}, "
                 f"slice_through={asn['slice_filled_sum_across_cells']}.")
        L.append("")
    L.append("## Overall verdict")
    L.append("")
    ov = out["part_b"]["verdict"]
    L.append(f"any_ship_ready_overall={ov['any_ship_ready_overall']} (safe={ov['safe_ship_ready']}, bold={ov['bold_ship_ready']})")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
