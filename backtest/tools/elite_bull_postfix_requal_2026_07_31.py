"""elite_bull_postfix_requal_2026_07_31.py -- POST-FIX requalification of block_elite_bull.

Executes the FROZEN pre-registration analysis/recommendations/elite-bull-requal-prereg-2026-07-31.json
(frozen 2026-07-31 16:46:41 EDT, BEFORE any fetch/replay). Read that file first -- population,
dedupe, exclusions E1/E2/E3/F1, replay method, qty cells, and the verdict rule are all frozen there.

Method lineage: identical replay pipeline to backtest/tools/bull_elite_atm_decision_log_mining.py
(the 2026-07-22 requalification's decision-log-mining arm): mine core-decisions.jsonl
SKIP_ELITE_BULL_LEVEL_RECLAIM rows, dedupe at 5-min gaps, ATM strike, real-OPRA entry premium at
the first cached bar >= signal tick, exit re-walked through the REAL production exit_manager
(backtest/lib/exit_manager_walk.py#walk_exit_manager) at the live core registry-CONTROL shape
(strategies.RIBBON_RIDE -- heartbeat_core.py:1983-1985 registers core entries under exactly this),
structure stop enabled, trigger_level from the logged trigger_level_exact, time stop 15:50,
entry+1 strict-'>' exit eligibility per ENTRY-BAR-CONVENTION-RULING-2026-07-25.md.

New vs the 07-22 tool (all frozen in the prereg):
  * window = corrected-feed era only (2026-07-28..2026-07-31);
  * BOTH accounts mined (bold's gate has never been revalidated -- 07-22 doc names it the gap);
  * E2 exclusion: trigger_bar_et on a PRIOR day = stale open echo (field exists post-fix only);
  * E3 exclusion: first tick >= 15:00 ET = untradeable under entry_no_trade_after_et regardless
    of the gate (replayed for information as 'late_cluster', never graded);
  * sequential-hold PRIMARY cohort: the core holds one position at a time, so events falling
    inside a prior replay's holding window are consumed, not independent trials;
  * qty cells 10 (07-22 comparability) and 3 (min-size, Rule-6 floor -- verdict PRIMARY);
  * fleet real-fill reconciliation from automation/state/fills-ledger.jsonl (FIFO round trips,
    mapped to blocked clusters within +/-15 min).

Data: 100% real OPRA. Post-fix contracts were not cached at prereg freeze; `--fetch` backfills
them through backtest/tools/expand_opra_cache.py's fetch_contract_bars/write_cache (same auth
path, same CSV schema). DISCOVERED AT RUN TIME (2026-07-31): the /v1beta1/options/bars endpoint
now 403s ("OPRA agreement is not signed") on BOTH mcp keys -- it worked 2026-07-23
(_fetch_late_entry_contracts_2026_07_23.py) so the agreement state changed between then and now.
The /v1beta1/options/trades endpoint still returns raw OPRA trade prints (probed 200), so the
fetch falls back to aggregating REAL trade prints into 5-min OHLCV bars client-side (identical
semantics to the bars endpoint: open/high/low/close from prints in time order, volume=sum size,
vwap=sum(p*s)/sum(s)) and writes the SAME cache CSV schema. Disclosed caveat: official bars may
exclude certain trade-condition codes that a raw aggregation keeps; effect on 5-min OHLC of a
liquid SPY 0DTE contract is negligible but nonzero. The replay itself only reads the local
cache; any still-missing contract is dropped and counted in n_missing_bars, never imputed.

Run (backtest venv):
    backtest/.venv/Scripts/python.exe backtest/tools/elite_bull_postfix_requal_2026_07_31.py --fetch
    backtest/.venv/Scripts/python.exe backtest/tools/elite_bull_postfix_requal_2026_07_31.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
PREREG = REPO / "analysis" / "recommendations" / "elite-bull-requal-prereg-2026-07-31.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "elite-bull-requal-2026-07-31.json"
SPY_5M_MASTER = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-31.csv"

WINDOW_START = dt.date(2026, 7, 28)   # first corrected-feed session (compiler v2 shipped 07-27 evening)
WINDOW_END = dt.date(2026, 7, 31)
DEDUPE_GAP_MINUTES = 5
ENTRY_CEILING_ET = dt.time(15, 0)     # entry_no_trade_after_et, both params files (read 2026-07-31)
TIME_STOP_ET = dt.time(15, 50)
STRIKE_OFFSET_ATM = 0
QTY_CELLS = (10, 3)                   # 10 = 07-22 comparability; 3 = min-size (verdict PRIMARY)
FLEET_ARMS = ("safe-3", "risky-1", "risky-3")
MAP_WINDOW_MIN = 15.0


# ------------------------------------------------------------------------------------------ #
# pure helpers (guard-tested in backtest/tests/test_elite_bull_postfix_requal_2026_07_31.py)
# ------------------------------------------------------------------------------------------ #
def dedupe_into_events(rows: list[dict], gap_minutes: float = DEDUPE_GAP_MINUTES) -> list[dict]:
    """Cluster consecutive skip ticks <= gap_minutes apart into one event (07-22 precedent)."""
    if not rows:
        return []
    ordered = sorted(rows, key=lambda r: r["ts_et"])
    groups: list[list[dict]] = [[ordered[0]]]
    for prev, row in zip(ordered, ordered[1:]):
        gap_min = (dt.datetime.fromisoformat(row["ts_et"])
                   - dt.datetime.fromisoformat(prev["ts_et"])).total_seconds() / 60.0
        if gap_min <= gap_minutes:
            groups[-1].append(row)
        else:
            groups.append([row])
    return [{"entry_row": g[0], "n_ticks": len(g), "first_ts": g[0]["ts_et"]} for g in groups]


def classify_exclusion(event: dict, other_account_rows: list[dict]) -> tuple[str, str]:
    """Frozen exclusion ladder: E1 stale echo -> E2 prior-day trigger bar -> E3 late -> F1 flag.

    Returns (status, reason) where status in {"E1","E2","E3","F1","KEPT"}.
    """
    row = event["entry_row"]
    ts = dt.datetime.fromisoformat(row["ts_et"])
    for other in other_account_rows:
        ots = other.get("ts_et")
        if not ots:
            continue
        if (abs((dt.datetime.fromisoformat(ots) - ts).total_seconds()) <= 90
                and other.get("action") == "SKIP_STALE_TRIGGER"):
            return "E1", f"cross-account SKIP_STALE_TRIGGER at {ots}"
    trig = row.get("trigger_bar_et")
    if trig:
        trig_date = dt.datetime.fromisoformat(trig).date()
        if trig_date < ts.date():
            return "E2", f"trigger bar {trig} is a prior-day echo"
    if ts.time() >= ENTRY_CEILING_ET:
        return "E3", "first tick >= 15:00 ET entry ceiling (SKIP_LATE_ENTRY even if unblocked)"
    if dt.time(9, 35) <= ts.time() < dt.time(9, 41):
        return "F1", "open-adjacent (09:35-09:41) -- kept, flagged elevated_stale_risk"
    return "KEPT", ""


def merge_cross_account(safe_events: list[dict], bold_events: list[dict],
                        gap_minutes: float = DEDUPE_GAP_MINUTES) -> int:
    """Headline distinct-setup count: safe+bold events within gap_minutes are ONE setup."""
    all_ts = sorted(dt.datetime.fromisoformat(e["first_ts"]) for e in safe_events + bold_events)
    if not all_ts:
        return 0
    n = 1
    for prev, cur in zip(all_ts, all_ts[1:]):
        if (cur - prev).total_seconds() / 60.0 > gap_minutes:
            n += 1
    return n


def sequential_hold(replays: list[dict]) -> list[dict]:
    """PRIMARY cohort filter: the core holds ONE position at a time. An event whose entry ts
    is <= the previous kept replay's exit time is consumed by the open position -> dropped."""
    kept: list[dict] = []
    current_exit: Optional[dt.datetime] = None
    for r in sorted(replays, key=lambda x: x["entry_ts_et"]):
        entry = dt.datetime.fromisoformat(r["entry_ts_et"])
        if current_exit is not None and entry <= current_exit:
            continue
        kept.append(r)
        if r.get("exit_time_et"):
            current_exit = dt.datetime.fromisoformat(r["exit_time_et"])
        else:
            current_exit = None
    return kept


def fifo_round_trips(fills: list[dict]) -> list[dict]:
    """Realized round-trip episodes per (arm, symbol, date): flat->flat = one trade.

    Each fill: {arm, symbol, date_et, ts_et, side, qty, price}. Returns episodes with
    entry_ts_et, exit_ts_et, qty, pnl (option multiplier 100)."""
    episodes: list[dict] = []
    by_key: dict = {}
    for f in sorted(fills, key=lambda x: x["ts_et"]):
        by_key.setdefault((f["arm"], f["symbol"], f["date_et"]), []).append(f)
    for (arm, symbol, date_et), rows in sorted(by_key.items()):
        pos = 0.0
        cost = 0.0        # open-position cost basis ($)
        proceeds = 0.0
        entry_ts = None
        for f in rows:
            qty = float(f["qty"])
            if f["side"] == "buy":
                if pos == 0:
                    entry_ts, cost, proceeds = f["ts_et"], 0.0, 0.0
                pos += qty
                cost += qty * float(f["price"]) * 100.0
            else:
                pos -= qty
                proceeds += qty * float(f["price"]) * 100.0
                if pos <= 0:
                    episodes.append({
                        "arm": arm, "symbol": symbol, "date": date_et,
                        "entry_ts_et": entry_ts, "exit_ts_et": f["ts_et"],
                        "pnl": round(proceeds - cost, 2),
                    })
                    pos, cost, proceeds, entry_ts = 0.0, 0.0, 0.0, None
        if pos > 0:  # unresolved open position -- disclose, never silently drop
            episodes.append({"arm": arm, "symbol": symbol, "date": date_et,
                             "entry_ts_et": entry_ts, "exit_ts_et": None,
                             "pnl": None, "unresolved_open_qty": pos})
    return episodes


def map_fill_to_cluster(entry_ts: str, clusters: list[dict],
                        window_min: float = MAP_WINDOW_MIN) -> Optional[str]:
    """Nearest blocked-cluster first_ts within +/-window_min minutes, else None."""
    ts = dt.datetime.fromisoformat(entry_ts)
    best, best_gap = None, None
    for c in clusters:
        cts = dt.datetime.fromisoformat(c["first_ts"])
        gap = abs((ts - cts).total_seconds()) / 60.0
        if gap <= window_min and (best_gap is None or gap < best_gap):
            best, best_gap = c["first_ts"], gap
    return best


def drop_top1(pnls: list[float]) -> tuple[float, bool]:
    if not pnls:
        return 0.0, False
    winners = [p for p in pnls if p > 0]
    if not winners:
        total = sum(pnls)
        return round(total, 2), total > 0
    remainder = sum(pnls) - max(winners)
    return round(remainder, 2), remainder > 0


def cohort_stats(replays: list[dict]) -> dict:
    pnls = [r["pnl"] for r in replays]
    n = len(pnls)
    total = round(sum(pnls), 2)
    wins = sum(1 for p in pnls if p > 0)
    remainder, remainder_pos = drop_top1(pnls)
    by_day: dict = {}
    for r in replays:
        by_day[r["date"]] = round(by_day.get(r["date"], 0.0) + r["pnl"], 2)
    return {"n": n, "win_rate": round(wins / n, 4) if n else 0.0, "total_pnl": total,
            "expectancy_per_trade": round(total / n, 2) if n else 0.0,
            "drop_top1_remainder": remainder, "drop_top1_positive": remainder_pos,
            "by_day_pnl": by_day,
            "trades": sorted(replays, key=lambda r: r["entry_ts_et"])}


def grade_verdict(primary_total: float, primary_n: int, fleet_net: float) -> str:
    """FROZEN verdict rule (prereg 'verdict_rule_frozen'). Returns 'a' | 'b' | 'c'."""
    if primary_n == 0:
        return "b"
    if primary_total > 0 and fleet_net > 0:
        return "a"
    if primary_total < 0 and fleet_net < 0:
        return "c"
    return "b"


# ------------------------------------------------------------------------------------------ #
# mining + replay (impure shell)
# ------------------------------------------------------------------------------------------ #
def load_core_rows() -> list[dict]:
    rows = []
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ts = r.get("ts_et", "")
            if WINDOW_START.isoformat() <= ts[:10] <= WINDOW_END.isoformat():
                rows.append(r)
    return rows


def mine_account(rows: list[dict], account: str) -> dict:
    skips = [r for r in rows if r.get("account") == account
             and r.get("action") == "SKIP_ELITE_BULL_LEVEL_RECLAIM"]
    other = [r for r in rows if r.get("account") != account]
    events = dedupe_into_events(skips)
    kept, flagged, excluded = [], [], []
    for ev in events:
        status, reason = classify_exclusion(ev, other)
        ev = {**ev, "exclusion_status": status, "exclusion_reason": reason}
        if status in ("E1", "E2", "E3"):
            excluded.append(ev)
        elif status == "F1":
            flagged.append(ev)
            kept.append({**ev, "elevated_stale_risk": True})
        else:
            kept.append(ev)
    return {"n_raw_ticks": len(skips), "n_events": len(events), "kept": kept,
            "flagged": flagged, "excluded": excluded}


def contracts_needed(events: list[dict]) -> list[tuple[dt.date, int]]:
    out = set()
    for ev in events:
        row = ev["entry_row"]
        d = dt.date.fromisoformat(row["ts_et"][:10])
        out.add((d, int(round(float(row["spy"]))) + STRIKE_OFFSET_ATM))
    return sorted(out)


def fetch_bars_via_trades(symbol: str, trade_date: dt.date, key: str, secret: str) -> list[dict]:
    """REAL OPRA trade prints -> 5-min OHLCV bars (fallback for the 403-gated bars endpoint).

    Same output schema as expand_opra_cache.fetch_contract_bars (timestamp_et fixed -04:00,
    open/high/low/close/volume/vwap/trade_count). Paginated; RTH window 13:30-21:00 UTC."""
    from urllib.error import HTTPError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    trades: list[tuple[dt.datetime, float, float]] = []  # (ts_utc, price, size)
    page_token = None
    while True:
        params = {"symbols": symbol, "start": f"{trade_date.isoformat()}T13:30:00Z",
                  "end": f"{trade_date.isoformat()}T21:00:00Z", "limit": 10000}
        if page_token:
            params["page_token"] = page_token
        url = "https://data.alpaca.markets/v1beta1/options/trades?" + urlencode(params)
        req = Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        payload = None
        for attempt in range(5):  # burst throttling shows up as transient 403/429 -- back off
            try:
                with urlopen(req, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except HTTPError as e:
                if e.code in (403, 429) and attempt < 4:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                raise
        assert payload is not None
        for t in payload.get("trades", {}).get(symbol, []) or []:
            ts = dt.datetime.fromisoformat(t["t"].replace("Z", "+00:00"))
            trades.append((ts, float(t["p"]), float(t["s"])))
        page_token = payload.get("next_page_token")
        if not page_token:
            break
        time.sleep(0.2)
    if not trades:
        return []
    trades.sort(key=lambda x: x[0])
    buckets: dict = {}
    for ts, p, s in trades:
        ts_et = ts.replace(tzinfo=None) - dt.timedelta(hours=4)
        bucket = ts_et.replace(minute=(ts_et.minute // 5) * 5, second=0, microsecond=0)
        b = buckets.setdefault(bucket, {"o": p, "h": p, "l": p, "c": p, "v": 0.0,
                                        "pv": 0.0, "n": 0})
        b["h"] = max(b["h"], p)
        b["l"] = min(b["l"], p)
        b["c"] = p
        b["v"] += s
        b["pv"] += p * s
        b["n"] += 1
    rows = []
    for bucket in sorted(buckets):
        b = buckets[bucket]
        rows.append({"timestamp_et": bucket.strftime("%Y-%m-%dT%H:%M:%S-04:00"),
                     "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
                     "volume": b["v"], "vwap": round(b["pv"] / b["v"], 4) if b["v"] else b["c"],
                     "trade_count": b["n"]})
    return rows


def fetch_missing(contract_keys: list[tuple[dt.date, int]]) -> dict:
    from urllib.error import HTTPError
    from expand_opra_cache import (already_cached, fetch_contract_bars, option_symbol,
                                   write_cache, write_empty_sentinel)
    from _alpaca_creds import resolve_alpaca_creds
    creds = resolve_alpaca_creds()
    fetched, fetched_via_trades, empty, cached = [], [], [], []
    for d, strike in contract_keys:
        sym = option_symbol(d, strike, "C")
        if already_cached(sym):
            cached.append(sym)
            continue
        bars, via_trades = [], False
        try:
            bars = fetch_contract_bars(sym, d, creds.key, creds.secret)
        except HTTPError as e:
            if e.code != 403:
                raise
            bars = fetch_bars_via_trades(sym, d, creds.key, creds.secret)
            via_trades = True
        if bars:
            write_cache(sym, bars)
            (fetched_via_trades if via_trades else fetched).append(sym)
        else:
            write_empty_sentinel(sym)
            empty.append(sym)
        time.sleep(0.35)
    return {"fetched_bars_endpoint": fetched, "fetched_via_trades_agg": fetched_via_trades,
            "empty": empty, "already_cached": cached}


_SPY5_CACHE: Optional[pd.DataFrame] = None


def spy_5m() -> pd.DataFrame:
    global _SPY5_CACHE
    if _SPY5_CACHE is None:
        df = pd.read_csv(SPY_5M_MASTER)
        ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
        df = df.assign(timestamp_et=ts.dt.tz_localize(None))
        df["date"] = df["timestamp_et"].dt.date
        _SPY5_CACHE = df
    return _SPY5_CACHE


def replay_event(ev: dict, qty: int, exit_shape: dict) -> Optional[dict]:
    from lib.option_pricing_real import load_contract_bars, option_symbol
    from lib.exit_manager_walk import walk_exit_manager
    row = ev["entry_row"]
    ts_et = dt.datetime.fromisoformat(row["ts_et"])
    date = ts_et.date()
    strike = int(round(float(row["spy"]))) + STRIKE_OFFSET_ATM
    symbol = option_symbol(date, strike, "C")
    opt_df = load_contract_bars(symbol)
    if opt_df is None or opt_df.empty:
        return None
    ts_col = pd.to_datetime(opt_df["timestamp_et"])
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_localize(None)
    opt_df = opt_df.assign(timestamp_et=ts_col)
    after = opt_df[opt_df["timestamp_et"] >= ts_et]
    if after.empty:
        return None
    entry_premium = float(after.iloc[0]["open"])
    if entry_premium <= 0:
        return None
    five_min = spy_5m()
    day = five_min[five_min["date"] == date]
    if day.empty:
        return None
    res = walk_exit_manager(
        symbol=symbol, side="C", entry_time_et=ts_et, entry_premium=entry_premium,
        qty=qty, exit_shape=exit_shape, structure_stop_enabled=True,
        trigger_level=row.get("trigger_level_exact"), strategy="ribbon_ride",
        time_stop_et=TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=day,
    )
    return {"date": date.isoformat(), "entry_ts_et": ts_et.isoformat(), "strike": strike,
            "symbol": symbol, "entry_premium": round(entry_premium, 4),
            "trigger_level": row.get("trigger_level_exact"), "qty": qty,
            "pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None,
            "structure_fired": any(leg.stage == "structure_stop" for leg in res.legs),
            "elevated_stale_risk": bool(ev.get("elevated_stale_risk"))}


def load_fleet_fills() -> list[dict]:
    fills = []
    with FILLS_LEDGER.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not r.get("is_option"):
                continue
            if not (WINDOW_START.isoformat() <= r.get("date_et", "") <= WINDOW_END.isoformat()):
                continue
            sym = r.get("symbol", "")
            if len(sym) < 12 or sym[9] != "C":   # SPYyymmddC######## -- calls only
                continue
            fills.append({"arm": r["arm"], "symbol": sym, "date_et": r["date_et"],
                          "ts_et": r["ts_et"], "side": r["side"], "qty": r["qty"],
                          "price": r["price"]})
    return fills


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="backfill missing OPRA contracts first")
    args = ap.parse_args()

    import strategies as strat_mod
    exit_shape = strat_mod.RIBBON_RIDE.exit.to_dict()

    rows = load_core_rows()
    mining = {acct: mine_account(rows, acct) for acct in ("safe", "bold")}
    distinct_setups = merge_cross_account(
        [e for e in mining["safe"]["kept"]], [e for e in mining["bold"]["kept"]])

    all_events = (mining["safe"]["kept"] + mining["bold"]["kept"]
                  + [e for a in mining.values() for e in a["excluded"] if e["exclusion_status"] == "E3"])
    needed = contracts_needed(all_events)
    fetch_report = fetch_missing(needed) if args.fetch else {"skipped": "run with --fetch"}
    print(f"[requal] contracts needed={len(needed)} fetch={json.dumps(fetch_report)[:300]}", flush=True)

    cohorts: dict = {}
    for acct in ("safe", "bold"):
        for qty in QTY_CELLS:
            replays, missing = [], 0
            for ev in mining[acct]["kept"]:
                r = replay_event(ev, qty, exit_shape)
                if r is None:
                    missing += 1
                else:
                    replays.append(r)
            seq = sequential_hold(replays)
            cohorts[f"{acct}_per_event_qty{qty}"] = {**cohort_stats(replays), "n_missing_bars": missing}
            cohorts[f"{acct}_sequential_hold_qty{qty}"] = {**cohort_stats(seq), "n_missing_bars": missing}
            conservative = [r for r in seq if not r.get("elevated_stale_risk")]
            cohorts[f"{acct}_sequential_hold_conservative_qty{qty}"] = cohort_stats(conservative)

    # late cluster: E3-excluded events, replayed for information only (never graded)
    late_replays = []
    for acct in ("safe", "bold"):
        for ev in [e for e in mining[acct]["excluded"] if e["exclusion_status"] == "E3"]:
            r = replay_event(ev, 3, exit_shape)
            if r is not None:
                late_replays.append({**r, "account": acct})
    cohorts["late_cluster_UNTRADEABLE_qty3"] = cohort_stats(late_replays) if late_replays else {"n": 0}

    # fleet real fills
    fills = load_fleet_fills()
    fleet_fills = [f for f in fills if f["arm"] in FLEET_ARMS]
    episodes = fifo_round_trips(fleet_fills)
    safe_clusters = [{"first_ts": e["first_ts"]} for e in mining["safe"]["kept"]
                     + [x for x in mining["safe"]["excluded"] if x["exclusion_status"] == "E3"]]
    for ep in episodes:
        ep["mapped_blocked_cluster"] = (map_fill_to_cluster(ep["entry_ts_et"], safe_clusters)
                                        if ep["entry_ts_et"] else None)
    mapped = [e for e in episodes if e["mapped_blocked_cluster"] and e["pnl"] is not None]
    fleet_net_mapped = round(sum(e["pnl"] for e in mapped), 2)
    fleet_net_all = round(sum(e["pnl"] for e in episodes if e["pnl"] is not None), 2)

    # core real fills on cohort signals (gate not binding, e.g. bold VIX outside band)
    core_calls = fifo_round_trips([f for f in fills if f["arm"] in ("safe-2", "bold-2")])

    primary = cohorts["safe_sequential_hold_qty3"]
    verdict_letter = grade_verdict(primary["total_pnl"], primary["n"], fleet_net_mapped)

    out = {
        "_doc": "block_elite_bull POST-FIX (corrected level feed) requalification. Executed "
                "against the frozen prereg elite-bull-requal-prereg-2026-07-31.json. All cells "
                "reported. Real OPRA only; missing contracts dropped + counted, never imputed.",
        "generated_at": dt.datetime.now().isoformat(),
        "window": [WINDOW_START.isoformat(), WINDOW_END.isoformat()],
        "exit_shape_used": exit_shape,
        "mining": {acct: {"n_raw_ticks": m["n_raw_ticks"], "n_events": m["n_events"],
                          "n_kept": len(m["kept"]),
                          "excluded": [{"first_ts": e["first_ts"],
                                        "status": e["exclusion_status"],
                                        "reason": e["exclusion_reason"]} for e in m["excluded"]]}
                   for acct, m in mining.items()},
        "distinct_setups_cross_account": distinct_setups,
        "contracts": {"needed": [[d.isoformat(), s] for d, s in needed], "fetch": fetch_report},
        "data_provenance": {
            "SPY260728C00740000": "Alpaca /options/trades OPRA prints, aggregated to 5-min client-side",
            "SPY260728C00742000": "Alpaca /options/trades OPRA prints, aggregated to 5-min client-side",
            "SPY260729C00737000": "Alpaca /options/trades OPRA prints, aggregated to 5-min client-side",
            "SPY260729C00742000": "Alpaca /options/trades OPRA prints, aggregated to 5-min client-side",
            "SPY260729C00743000": "Alpaca /options/trades OPRA prints, aggregated to 5-min client-side",
            "SPY260731C00744000": "TradingView OPRA_DLY 5-min bars (Alpaca options-data 403'd "
                                  "'OPRA agreement is not signed' mid-fetch); cross-validated vs "
                                  "real fleet fill prints on C746 (3/3 fills inside bar ranges)",
            "SPY260731C00745000": "TradingView OPRA_DLY 5-min bars (same as C744)",
            "SPY260731C00746000": "TradingView OPRA_DLY 5-min bars (same as C744; the cross-validated contract)",
            "SPY260731C00748000": "TradingView OPRA_DLY 5-min bars (same as C744)",
            "note": "ALL sources are real OPRA prints -- no synthetic/BS pricing anywhere. "
                    "The Alpaca /options/bars endpoint 403s ('OPRA agreement is not signed') on "
                    "both mcp keys as of 2026-07-31 evening; it worked 2026-07-23. Standing repair "
                    "needed for future backfills (J dashboard action or trades-agg migration).",
        },
        "cohorts": cohorts,
        "fleet_real_fills": {"episodes": episodes, "net_mapped": fleet_net_mapped,
                             "net_all_calls": fleet_net_all,
                             "arms": list(FLEET_ARMS), "map_window_min": MAP_WINDOW_MIN},
        "core_real_fills_on_cohort": core_calls,
        "old_era_evidence_cited": {
            "raw_real_fills_since_ssb": {"n": 24, "wr": 0.0, "total": -885.0,
                                         "source": "bull-requalification-2026-07-22.md item 3"},
            "decision_log_mining_atm": {"n": 30, "total": 665.60, "drop_top1": -1420.80,
                                        "wr": 0.167,
                                        "source": "bull-elite-atm-decision-log-mining-2026-07-22.json"},
            "backtest_detection_atm": {"n": 9, "total": -1720.50,
                                       "source": "bull-requalification-2026-07-22.json"},
            "otm2_ssb_2026_07_10": {"n": 28, "total": -3873.60, "wr": 0.286,
                                    "source": "block-elite-bull-ssb-revalidation.json"},
        },
        "verdict_rule_inputs": {"primary_cell": "safe_sequential_hold_qty3",
                                "primary_total": primary["total_pnl"], "primary_n": primary["n"],
                                "fleet_net_mapped": fleet_net_mapped},
        "verdict": verdict_letter,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[requal] wrote {OUT_JSON}", flush=True)
    print(f"[requal] PRIMARY safe_seq_qty3: n={primary['n']} total=${primary['total_pnl']} "
          f"wr={primary['win_rate']} | fleet_net_mapped=${fleet_net_mapped} "
          f"| verdict={verdict_letter}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
