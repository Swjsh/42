"""historical_replay.py -- TASK C1 (2026-08-28), scoped per A1's NO-GO verdict on a full
signal+exit historical replay (see analysis/deep-research/ ... A1 finding, reproduced in this
module's own summary output at run time).

WHAT THIS IS: an EXIT-LAYER-ONLY replay over REAL, ALREADY-KNOWN engine signals -- never a
reconstructed signal. A1 found two hard blockers to reconstructing NEW historical entries via
run_backtest's auto-detector: (1) PARITY-GAP-1 -- the auto-detector's level set is confirmed
divergent from live's actual key-levels.json pipeline outside ~16-18 spot-check dates, and the
one candidate fix tested came back HARMFUL; (2) the 233-date highres option cache is a
demand-driven "verify known trades" cache (83.2% single-sided strike coverage), not systematic
strike-range coverage, so a genuinely NEW candidate entry's strike would usually have no priced
option data anyway. Both blockers are specific to RECONSTRUCTING a signal that did not really
fire. They do NOT apply to a REAL, already-filled engine trade: its exact strike is available
by construction (the option-bar caches were largely built to price exactly these trades), and
its entry time/price/side are the REAL BROKER FILL, not a level-detector's guess.

WHAT THIS THEREFORE CANNOT DO: multiply the sample. The population of "historically-detected
signals with option data" is capped at the trades that already happened -- this tool re-walks
the SAME ~346 known engine trades (382 engine-attributed round trips in trades-enriched.jsonl,
less 36 with no matched setup) through the REAL exit_manager core, on REAL 1-minute option
bars, under an explicit exit-cost sweep, and checks whether that walk reproduces what the
account actually realized. It is a FIDELITY + COST-SENSITIVITY instrument, not a new-evidence
generator. This is stated plainly per the task's own instruction: "If A1 said the signal layer
cannot be made faithful, DO NOT force it -- instead build the largest defensible subset ...
and say plainly what it can and cannot establish. A faithful smaller thing beats an unfaithful
bigger one."

WHAT IT REUSES, NOT REBUILDS (OP-22):
  - backtest/lib/exit_manager_walk.py#walk_exit_manager -- ticks the REAL production
    automation/state/fleet/exit_manager.py plan_exit_actions core over cached bars. Proven
    6/6 fidelity vs live fills on 2026-07-17 (backtest/tools/exit_manager_replay.py).
  - automation/state/fleet/strategies.py + fleet_executor.py#_exit_shape_dict /
    #_params_for -- the REAL per-arm exit-shape resolution (base strategy exit shape +
    accounts.json params_patch.exit_patch overlay), so a fleet arm's disclosed exit-parameter
    A/B (risky-3 structure/trail 0.20, risky-1 tp1 0.5, etc.) is honored exactly as live
    resolves it, not approximated.
  - backtest/lib/ribbon.py#compute_ribbon -- the fingerprinted Saty Pivot Ribbon (13/20/48 EMA)
    live's own ribbon_stack reads.
  - setup/scripts/lib/scorecard_guards.py -- day-level bootstrap CI / P(PF<=1), ex-best-day
    sign-flip, signal-cluster n, BH-FDR. Applied here across the 4 swept cost scenarios (one
    sweep, one FDR correction) exactly as the module's own contract requires.

EXIT-COST MODEL: exit_manager_walk.py's own docstring discloses a confirmed, unfixed bug --
6 of 9 exit stages (TP1/catastrophe-stop/profit-lock/runner/trail/be_stop) fill EXACTLY at the
triggered premium level with ZERO slippage by DEFAULT, even though every live exit (all 9
stages) is an unconditional MARKET order that pays the spread. This replay does NOT use that
default. It uses the module's own documented "STEP 1 TREATMENT ARM" (all_exits_market=True --
every stage fills at bar-open minus a swept slippage, matching what live actually does
mechanically) and sweeps exit_slippage = $0.00 / $0.50 / $1.00 / $2.00 per contract (per-share
= per-contract/100). A costless replay is not decision-relevant per the task's own instruction.

FIDELITY CHECK: for every trade actually walked, replay_dollar_pnl (per cost scenario) is
compared against the REAL realized pnl_dollars from analysis/trades-enriched.jsonl (FIFO-
reconciled, real broker fills). The aggregate delta at each cost scenario is the headline
fidelity number -- if the replay cannot reproduce the real forward period within a stated
tolerance, that is reported prominently, not buried, per the task's explicit instruction.

ANTI-SELF-DECEPTION (per /fable-too-good, run BEFORE reporting any strongly-positive number):
  - Look-ahead: entries are REAL fills (never reconstructed), and walk_exit_manager itself only
    ever walks bars strictly AFTER entry_time_et (see that module's `after = ...` gate) --
    checked, not assumed.
  - Survivorship in option-date caching: A1 already flagged the highres cache as demand-driven.
    This script discloses (a) how many of the 346 candidate trades have NO option-bar coverage
    at all (walked=0), and (b) whether the walked subset's live P&L differs systematically from
    the skipped subset's live P&L (a coverage-selection artifact would show up as a mean/sum
    skew between the two groups) -- both computed and reported, never assumed away.
  - Strike availability bias: not applicable in the way it is for signal reconstruction -- every
    walked trade uses the EXACT real strike traded, by construction.
  - Entry-bar convention / post-entry info: walk_exit_manager's own entry-bar gate (see above)
    is the enforcement; this script does not additionally slice or filter bars, so there is no
    second, script-level place look-ahead could sneak in.

Run: backtest/.venv/Scripts/python.exe backtest/tools/historical_replay.py [--limit N] [--no-fetch]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time as _time_mod
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
SETUP_SCRIPTS_LIB = REPO / "setup" / "scripts" / "lib"  # scorecard_guards.py lives here --
# added SEPARATELY (bare, not dotted) because setup/scripts/lib and backtest/lib are BOTH
# named "lib": whichever package sys.path resolves first wins the "lib." dotted namespace,
# so scorecard_guards is imported bare (`import scorecard_guards`) off its own directory
# instead of colliding with backtest.lib.
for _p in (REPO, BACKTEST, BACKTEST / "lib", BACKTEST / "tools", FLEET_DIR, SETUP_SCRIPTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402 -- automation/state/fleet/strategies.py
import fleet_executor as fx  # noqa: E402 -- automation/state/fleet/fleet_executor.py
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from scorecard_guards import (  # noqa: E402 -- bare import, see SETUP_SCRIPTS_LIB note above
    day_level_bootstrap, ex_best_day, signal_cluster_n, benjamini_hochberg,
)
from _option_bars_1min_cache import fetch_1min_cached  # noqa: E402

TRADES_ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
ACCOUNTS_JSON = FLEET_DIR / "accounts.json"
SPY_SIP_DIR = BACKTEST / "data" / "spy_sip_cache"
HIGHRES_DIR = BACKTEST / "data" / "highres"
OPRA_1M_DIR = BACKTEST / "data" / "opra_1m_cache"

OUT_DIR = REPO / "analysis" / "historical-replay"
LEDGER_PATH = OUT_DIR / "ledger.jsonl"
SUMMARY_PATH = OUT_DIR / "summary.json"

# Real per-contract exit slippage sweep (dollars). Applied via all_exits_market=True so it
# hits ALL 9 exit stages, correcting exit_manager_walk's own disclosed zero-slippage bug on
# 6 of 9 -- see module docstring EXIT-COST MODEL.
COST_SCENARIOS = [0.00, 0.50, 1.00, 2.00]

# Ribbon warmup buffer: the fast/pivot/slow EMA (13/20/48 periods, ribbon.py) needs continuity
# across days to match live's continuously-running ribbon (live never resets it). alpha for the
# 48-period EMA is 2/49=0.0408; after ~150 5-min bars (~2 trading days) the SMA seed's residual
# influence is < e^(-0.0408*150) = 0.2% -- ~40 trading days of buffer is generous, not tuned.
RIBBON_WARMUP_START = "2026-04-15"
FORWARD_WINDOW_START = "2026-06-26"
FORWARD_WINDOW_END = "2026-08-28"

TRIGGER_LEVEL_MATCH_TOL_S = 600.0  # same-signal-instance tolerance (matches exit_manager_
                                    # replay.py's own ground-truth match window)

_ARM_IDS = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3", "safe-1")


def log(msg: str) -> None:
    print(f"[historical-replay] {msg}", flush=True)


# --------------------------------------------------------------------------------------- #
# LOAD: real, already-known engine trades (the ONLY signal source this tool uses)
# --------------------------------------------------------------------------------------- #

def load_engine_trades() -> tuple[list[dict], int]:
    """Every attribution=='engine' round trip in trades-enriched.jsonl with a matched setup
    (setup is required to resolve an exit_shape -- see module docstring). Returns
    (trades, n_dropped_no_setup)."""
    rows = []
    with TRADES_ENRICHED.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("_meta"):
                continue
            rows.append(r)
    engine = [r for r in rows if r.get("attribution") == "engine"]
    dropped = [r for r in engine if not r.get("setup")]
    kept = [r for r in engine if r.get("setup")]
    return kept, len(dropped)


def resolve_strategy(setup_name: str):
    up = str(setup_name).strip().upper()
    for strat in fleet_strategies.REGISTRY:
        if any(up == s.upper() for s in strat.entry_setups):
            return strat
    return None


def load_accounts() -> dict:
    accounts = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    return {a["id"]: a for a in accounts.get("arms", []) if a.get("id") in _ARM_IDS}


def load_core_trigger_lookup() -> dict:
    """{(date_str, side): [(ts_dt, trigger_level_exact), ...] sorted by ts} from
    core-decisions.jsonl. build_shared_signal.py's own docstring (verified this session,
    line ~154-157) states fleet arms' trigger_level_exact is DERIVED FROM core-decisions.jsonl's
    "trigger_level_exact (ground truth from the winning side's ...)" -- so every arm's real
    trigger level for a given signal instance traces back to THIS file, not a per-arm log.
    Every row with a non-null trigger_level_exact is indexed regardless of action (PLACED,
    SKIP_*, etc.) -- the level describes the signal instance at that tick, not just placements,
    and we need the nearest one in time to each REAL trade's entry, any arm."""
    lookup: dict = {}
    n_rows = 0
    with CORE_DECISIONS.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            tl = r.get("trigger_level_exact")
            side = r.get("side")
            ts = r.get("ts_et")
            if tl is None or side not in ("P", "C") or not ts:
                continue
            try:
                ts_dt = dt.datetime.fromisoformat(str(ts))
            except ValueError:
                continue
            date_str = ts_dt.strftime("%Y-%m-%d")
            lookup.setdefault((date_str, side), []).append((ts_dt, float(tl)))
            n_rows += 1
    for k in lookup:
        lookup[k].sort(key=lambda t: t[0])
    log(f"trigger_level lookup: {n_rows} core-decisions rows w/ trigger_level_exact, "
        f"{len(lookup)} (date,side) buckets")
    return lookup


def resolve_trigger_level(lookup: dict, date_str: str, side: str,
                           entry_dt: dt.datetime) -> Optional[float]:
    candidates = lookup.get((date_str, side)) or []
    best, best_gap = None, None
    for ts_dt, level in candidates:
        gap = abs((ts_dt - entry_dt).total_seconds())
        if gap <= TRIGGER_LEVEL_MATCH_TOL_S and (best_gap is None or gap < best_gap):
            best, best_gap = level, gap
    return best


# --------------------------------------------------------------------------------------- #
# SPY 5-min continuous ribbon (built ONCE, spans the warmup buffer through the window end)
# --------------------------------------------------------------------------------------- #

def _load_spy_1min_day(date_str: str) -> Optional[pd.DataFrame]:
    p = SPY_SIP_DIR / f"spy_1m_{date_str}.json"
    if not p.exists():
        return None
    try:
        bars = json.loads(p.read_text(encoding="utf-8")).get("bars", [])
    except (OSError, json.JSONDecodeError):
        return None
    if not bars:
        return None
    df = pd.DataFrame(bars).rename(columns={"t": "timestamp_et", "o": "open", "h": "high",
                                              "l": "low", "c": "close", "v": "volume"})
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])  # already-naive ET wall clock
    rth = df[(df["timestamp_et"].dt.time >= dt.time(9, 30))
             & (df["timestamp_et"].dt.time < dt.time(16, 0))]
    return rth.reset_index(drop=True)


def build_continuous_spy_5min(start: str, end: str) -> pd.DataFrame:
    """RTH-only 1-min SPY across every cached trading date in [start, end], resampled 5-min
    (open=first/high=max/low=min/close=last, empty inter-day/weekend bins dropped -- mirrors
    orchestrator.py's own 15-min resample convention), then ribbon-tagged ONCE on the full
    continuous series so EMA state carries across days exactly like live's continuously-running
    ribbon (never reset per-trade-day -- see module docstring RIBBON_WARMUP_START rationale)."""
    all_files = sorted(SPY_SIP_DIR.glob("spy_1m_*.json"))
    frames = []
    n_days = 0
    for p in all_files:
        date_str = p.stem.replace("spy_1m_", "")
        if not (start <= date_str <= end):
            continue
        day = _load_spy_1min_day(date_str)
        if day is not None and not day.empty:
            frames.append(day)
            n_days += 1
    if not frames:
        raise RuntimeError(f"no spy_sip_cache data in [{start},{end}]")
    spy_1m = pd.concat(frames, ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    idx = spy_1m.set_index("timestamp_et")
    five = idx.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna().reset_index()
    ribbon = compute_ribbon(five["close"])
    five = pd.concat([five, ribbon[["fast", "pivot", "slow", "spread_cents", "stack"]]], axis=1)
    log(f"continuous SPY 5-min ribbon: {n_days} cached trading days -> {len(five)} 5-min bars "
        f"[{start}..{end}]")
    return five


def ribbon_1min_for(opt_df: pd.DataFrame, spy_5m: pd.DataFrame) -> pd.DataFrame:
    """Per-1-min-option-bar ribbon stack = the most-recently-CLOSED 5-min bar's stack,
    forward-filled via merge_asof(direction='backward') -- same convention as
    replay_today_eval.build_ribbon_1min, applied directly against the option bars' own
    timestamps instead of an intermediate SPY-1min frame."""
    left = opt_df[["timestamp_et"]].copy().sort_values("timestamp_et")
    right = spy_5m[["timestamp_et", "stack"]].sort_values("timestamp_et")
    merged = pd.merge_asof(left, right, on="timestamp_et", direction="backward")
    return merged.reset_index(drop=True)


# --------------------------------------------------------------------------------------- #
# Option bars: highres cache -> opra_1m_cache -> live REST fetch (read-only, fail-open)
# --------------------------------------------------------------------------------------- #

def _load_opra_1m_cache(symbol: str, date_str: str) -> Optional[pd.DataFrame]:
    p = OPRA_1M_DIR / f"{symbol}_{date_str}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if df.empty:
        return None
    ts = pd.to_datetime(df["t"], utc=True)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df["timestamp_et"] = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return df[["timestamp_et", "open", "high", "low", "close", "volume"]].sort_values(
        "timestamp_et").reset_index(drop=True)


def _load_highres(symbol: str, date_str: str) -> Optional[pd.DataFrame]:
    """The highres/ cache is NOT one uniform schema (found running this over the full
    population, not assumed): most files carry a `timestamp_et` column already tz-labeled
    at a fixed ET offset (e.g. "2026-07-15T09:30:00-04:00"); a minority (2 of 1,069 unique
    symbols, e.g. SPY260805C00776000) instead carry a bare `timestamp` column of raw UTC "Z"
    instants (mirrors the tolerance ladder_rung_replay_2026_08_07.py already had to add for
    the same reason). Both are normalized to naive ET wall-clock via
    `tz_convert("America/New_York")` (DST-correct, not a fixed -4 assumption) + tz strip."""
    p = HIGHRES_DIR / f"{symbol}_1m_{date_str}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if df.empty:
        return None
    if "timestamp_et" not in df.columns and "timestamp" in df.columns:
        df = df.rename(columns={"timestamp": "timestamp_et"})
    if "timestamp_et" not in df.columns:
        return None
    ts = pd.to_datetime(df["timestamp_et"])
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.assign(timestamp_et=ts)
    keep = [c for c in ("timestamp_et", "open", "high", "low", "close", "volume") if c in df.columns]
    return df[keep].sort_values("timestamp_et").reset_index(drop=True)


def option_bars_for(symbol: str, date_str: str, allow_fetch: bool) -> tuple[Optional[pd.DataFrame], str]:
    df = _load_highres(symbol, date_str)
    if df is not None:
        return df, "highres_cache"
    df = _load_opra_1m_cache(symbol, date_str)
    if df is not None:
        return df, "opra_1m_cache"
    if not allow_fetch:
        return None, "no_data_fetch_disabled"
    try:
        df, source = fetch_1min_cached(symbol, date_str)
    except Exception as exc:  # noqa: BLE001 -- read-only REST fetch must never abort the run
        log(f"  fetch error {symbol} {date_str}: {exc}")
        return None, "fetch_error"
    if df is None or df.empty:
        return None, "no_data"
    return df, f"rest_{source}"


# --------------------------------------------------------------------------------------- #
# Main replay
# --------------------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap n trades walked (debug)")
    ap.add_argument("--no-fetch", action="store_true", help="disable live REST fallback fetch")
    args = ap.parse_args()

    log("loading real engine trades (trades-enriched.jsonl) -- the ONLY signal source")
    trades, n_dropped_no_setup = load_engine_trades()
    if args.limit:
        trades = trades[: args.limit]
    log(f"{len(trades)} candidate trades (attribution=engine, setup known); "
        f"{n_dropped_no_setup} dropped (ctx_matched=false, no setup -> no exit_shape derivable)")

    accounts = load_accounts()
    trigger_lookup = load_core_trigger_lookup()
    spy_5m = build_continuous_spy_5min(RIBBON_WARMUP_START, FORWARD_WINDOW_END)

    opt_cache: dict = {}
    ribbon_cache: dict = {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger_fh = LEDGER_PATH.open("w", encoding="utf-8")

    n_walked_trades = 0
    n_skipped_no_data = 0
    skipped_rows: list[dict] = []
    per_scenario_rows: dict = {c: [] for c in COST_SCENARIOS}
    n_stop_mode_divergent = 0
    n_stop_mode_scored = 0

    t0 = _time_mod.time()
    for i, t in enumerate(trades):
        symbol = t["symbol"]
        date_str = t["date"]
        side = t["right"]
        arm = t["arm"]
        setup = t["setup"]
        entry_dt = dt.datetime.fromisoformat(t["entry_ts_et"])
        entry_px = float(t["entry_px"])
        qty = int(t["qty"])
        live_pnl = float(t["pnl_dollars"])
        live_exit_reason = t.get("exit_reason")
        live_stop_mode = t.get("stop_mode")

        cache_key = (symbol, date_str)
        if cache_key not in opt_cache:
            opt_cache[cache_key] = option_bars_for(symbol, date_str, allow_fetch=not args.no_fetch)
        opt_df, opt_source = opt_cache[cache_key]

        if opt_df is None:
            n_skipped_no_data += 1
            skipped_rows.append({"date": date_str, "arm": arm, "symbol": symbol,
                                  "live_pnl": live_pnl, "reason": opt_source})
            continue

        strat = resolve_strategy(setup)
        if strat is None:
            n_skipped_no_data += 1
            skipped_rows.append({"date": date_str, "arm": arm, "symbol": symbol,
                                  "live_pnl": live_pnl, "reason": "unresolved_strategy"})
            continue

        arm_dict = accounts.get(arm)
        exit_shape = fx._exit_shape_dict(strat, arm_dict)  # noqa: SLF001 -- reused prod resolver
        params = fx._params_for(arm_dict) if arm_dict is not None else {}  # noqa: SLF001
        structure_stop_enabled = bool(params.get("structure_stop_enabled", False))
        time_stop_str = params.get("time_stop_et", "15:50")
        hh, mm = str(time_stop_str).split(":")
        time_stop_et = dt.time(int(hh), int(mm))

        trigger_level = resolve_trigger_level(trigger_lookup, date_str, side, entry_dt)

        if cache_key not in ribbon_cache:
            ribbon_cache[cache_key] = ribbon_1min_for(opt_df, spy_5m)
        ribbon_1m = ribbon_cache[cache_key]

        n_walked_trades += 1
        resolved_structure_this_trade = None
        for cost in COST_SCENARIOS:
            slippage_per_share = cost / 100.0
            res = walk_exit_manager(
                symbol=symbol, side=side, entry_time_et=entry_dt, entry_premium=entry_px,
                qty=qty, exit_shape=exit_shape, structure_stop_enabled=structure_stop_enabled,
                trigger_level=trigger_level, strategy=setup, time_stop_et=time_stop_et,
                opt_df=opt_df, ribbon_tick_df=ribbon_1m, five_min_spy_df=spy_5m,
                opt_df_resolution="1min", allow_5min=True, frame="wall-v1",
                exit_slippage=slippage_per_share, all_exits_market=True,
            )
            resolved_structure_this_trade = res.stop_mode
            row = {
                "date": date_str, "arm": arm, "symbol": symbol, "side": side, "setup": setup,
                "qty": qty, "entry_ts_et": entry_dt.isoformat(), "entry_premium": entry_px,
                "cost_per_contract": cost, "option_bar_source": opt_source,
                "trigger_level": trigger_level, "resolved_stop_mode": res.stop_mode,
                "live_stop_mode": live_stop_mode,
                "exit_reason": res.exit_reason, "live_exit_reason": live_exit_reason,
                "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None,
                "hold_minutes": res.hold_minutes, "n_ticks_walked": res.n_ticks_walked,
                "replay_dollar_pnl": res.dollar_pnl, "live_dollar_pnl": live_pnl,
                "delta_vs_live": round(res.dollar_pnl - live_pnl, 2),
                "n_legs": len(res.legs),
            }
            ledger_fh.write(json.dumps(row, default=str) + "\n")
            per_scenario_rows[cost].append(row)

        if live_stop_mode in ("structure", "premium") and resolved_structure_this_trade in ("structure", "premium"):
            n_stop_mode_scored += 1
            if resolved_structure_this_trade != live_stop_mode:
                n_stop_mode_divergent += 1

        if (i + 1) % 50 == 0:
            log(f"  ... {i+1}/{len(trades)} trades processed ({_time_mod.time()-t0:.1f}s)")

    ledger_fh.close()
    log(f"walk complete: {n_walked_trades} trades walked, {n_skipped_no_data} skipped "
        f"(no option data / unresolved strategy), in {_time_mod.time()-t0:.1f}s")

    # ----------------------------------------------------------------------------------- #
    # Guards + fidelity check, per cost scenario
    # ----------------------------------------------------------------------------------- #
    scenario_summaries = {}
    pvals_for_fdr = {}
    for cost in COST_SCENARIOS:
        rows = per_scenario_rows[cost]
        day_trade_pnls: dict = {}
        day_pnls: dict = {}
        entries_for_cluster = []
        replay_total = 0.0
        live_total = 0.0
        for r in rows:
            d = r["date"]
            day_trade_pnls.setdefault(d, []).append(r["replay_dollar_pnl"])
            day_pnls[d] = day_pnls.get(d, 0.0) + r["replay_dollar_pnl"]
            entries_for_cluster.append({"date": d, "entry_ts_et": r["entry_ts_et"], "sym": r["symbol"]})
            replay_total += r["replay_dollar_pnl"]
            live_total += r["live_dollar_pnl"]
        boot = day_level_bootstrap(day_trade_pnls)
        ex_best = ex_best_day(day_pnls)
        cluster = signal_cluster_n(entries_for_cluster)
        cell_id = f"cost_{cost:.2f}"
        pvals_for_fdr[cell_id] = boot["p_pnl_le_0"]
        replay_total = round(replay_total, 2)
        live_total = round(live_total, 2)
        delta = round(replay_total - live_total, 2)
        tol = round(max(400.0, abs(live_total) * 0.15), 2)
        scenario_summaries[cell_id] = {
            "cost_per_contract": cost,
            "n_trades": len(rows),
            "n_days": boot["n_days"],
            "replay_total_pnl": replay_total,
            "live_total_pnl": live_total,
            "delta_vs_live": delta,
            "fidelity_tolerance_abs": tol,
            "within_fidelity_tolerance": bool(abs(delta) <= tol),
            "bootstrap": boot,
            "ex_best_day": ex_best,
            "signal_cluster": cluster,
        }

    fdr = benjamini_hochberg(pvals_for_fdr, q=0.10)

    # Coverage / survivorship disclosure
    skipped_live_sum = round(sum(r["live_pnl"] for r in skipped_rows), 2)
    skipped_live_mean = round(skipped_live_sum / len(skipped_rows), 2) if skipped_rows else None
    walked_live_sum = round(sum(t2["live_dollar_pnl"] for t2 in per_scenario_rows[COST_SCENARIOS[0]]), 2)
    n_walked_unique = len(per_scenario_rows[COST_SCENARIOS[0]])
    walked_live_mean = round(walked_live_sum / n_walked_unique, 2) if n_walked_unique else None

    summary = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "scope_note": (
            "EXIT-LAYER-ONLY replay over REAL already-known engine trades (never a "
            "reconstructed signal), per A1's NO-GO verdict on full signal+exit replay. "
            "Does NOT multiply the evidence sample -- population is capped at trades that "
            "already happened. See module docstring for full disclosure."
        ),
        "forward_window": [FORWARD_WINDOW_START, FORWARD_WINDOW_END],
        "n_candidate_trades": len(trades),
        "n_dropped_no_setup": n_dropped_no_setup,
        "n_walked_trades": n_walked_trades,
        "n_skipped_no_option_data_or_strategy": n_skipped_no_data,
        "coverage_pct": round(100.0 * n_walked_trades / len(trades), 2) if trades else None,
        "survivorship_check": {
            "skipped_trades_n": len(skipped_rows),
            "skipped_trades_live_pnl_sum": skipped_live_sum,
            "skipped_trades_live_pnl_mean": skipped_live_mean,
            "walked_trades_live_pnl_sum": walked_live_sum,
            "walked_trades_live_pnl_mean": walked_live_mean,
            "doc": (
                "If skipped-trade mean/sum diverges sharply from walked-trade mean/sum, the "
                "walked subset is NOT representative and any 'the replay says X' claim must "
                "be scoped to 'the covered subset says X', not the full population."
            ),
        },
        "stop_mode_fidelity": {
            "n_scored": n_stop_mode_scored,
            "n_divergent_from_live_recorded_stop_mode": n_stop_mode_divergent,
            "divergent_pct": (round(100.0 * n_stop_mode_divergent / n_stop_mode_scored, 2)
                               if n_stop_mode_scored else None),
            "doc": (
                "A trade's replay-resolved stop_mode (structure vs premium) can diverge from "
                "trades-enriched.jsonl's recorded live stop_mode when this script's "
                "trigger_level reconstruction (core-decisions.jsonl trigger_level_exact, "
                f"nearest match within {TRIGGER_LEVEL_MATCH_TOL_S:.0f}s) misses the real level "
                "that was actually live at entry, or when the CURRENT structure_stop_enabled "
                "flag read from live params does not match what was armed at that historical "
                "date (flag toggles are not versioned by date in this replay). A trade that "
                "resolves to 'premium' in the replay but was 'structure' live uses a DIFFERENT "
                "stop mechanism than what actually happened -- this count is the direct measure "
                "of how often that happens."
            ),
        },
        "cost_scenarios": scenario_summaries,
        "fdr_across_cost_scenarios": fdr,
        "anti_self_deception": {
            "look_ahead": (
                "walk_exit_manager only walks bars with timestamp_et > entry_ts (its own "
                "internal gate) -- checked via source read, not assumed. Entries are REAL "
                "broker fills (entry_ts_et/entry_px straight from trades-enriched.jsonl's "
                "FIFO-reconciled ledger), never a reconstructed signal."
            ),
            "survivorship_in_option_date_caching": (
                "See survivorship_check above -- computed, not assumed away."
            ),
            "strike_availability_bias": (
                "N/A in the signal-reconstruction sense -- every walked trade uses the EXACT "
                "real strike/contract traded, by construction."
            ),
            "entry_bar_convention": (
                "entry_time_et = real broker fill timestamp (microsecond-precision, from "
                "trades-enriched.jsonl). No 'next bar open' approximation is used anywhere in "
                "this script; walk_exit_manager's own after-entry gate does the slicing."
            ),
        },
        "disclosure_for_any_future_citation": (
            "This result is a FIDELITY/COST-SENSITIVITY check on the exit layer of "
            f"{n_walked_trades} ALREADY-KNOWN real engine trades ({FORWARD_WINDOW_START}.."
            f"{FORWARD_WINDOW_END}), NOT new backtest evidence and NOT a larger sample than "
            "the live forward record. It must never be cited as 'N historical trades support "
            "going live' -- N here is the same trades already counted in the forward record. "
            "It may be cited only as: (a) whether the exit_manager_walk mechanism reproduces "
            "real fills at each cost assumption, and (b) how sensitive realized P&L is to "
            "exit-side slippage. trigger_level and structure_stop_enabled are RECONSTRUCTED "
            "(not read from a per-trade historical snapshot) -- see stop_mode_fidelity above "
            "for the measured divergence rate."
        ),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log(f"wrote {LEDGER_PATH}")
    log(f"wrote {SUMMARY_PATH}")
    for cost in COST_SCENARIOS:
        s = scenario_summaries[f"cost_{cost:.2f}"]
        log(f"  cost=${cost:.2f}/ctr: replay=${s['replay_total_pnl']:+.2f} "
            f"live=${s['live_total_pnl']:+.2f} delta=${s['delta_vs_live']:+.2f} "
            f"within_tol={s['within_fidelity_tolerance']} "
            f"pf_ci=[{s['bootstrap']['pf_ci_low']},{s['bootstrap']['pf_ci_high']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
