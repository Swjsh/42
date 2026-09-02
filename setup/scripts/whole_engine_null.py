"""whole_engine_null.py -- THE WHOLE-ENGINE NULL STUDY RUNNER.

Implements analysis/recommendations/prereg-whole-engine-null-2026-09-01.json EXACTLY where
feasible; any deviation from the frozen design is recorded in the output JSON's `deviations`
list, never silently substituted. See that file for the frozen question, populations, nulls,
metrics, pass criterion, and kill nails -- this module does not restate them in prose, it
grades them mechanically.

WHY THIS EXISTS: R10 (FABLE-FULL-AUDIT-2026-09-01) found that every null in this repo is
FEATURE-level (does gate X help within trades the engine already took) -- no ENGINE-level
null (does the WHOLE thing beat a long-beta strategy) has ever been run, despite a measured
+0.232 book-day-P&L correlation with SPY's own open->close return. This is that null, built
once, run once, honestly reported.

ANALYSIS ONLY. Reads trades-enriched.jsonl, SPY 5m bars, and (read-only) the RIBBON_RIDE
ExitShape from automation/state/fleet/strategies.py -- never edits any trading-path file
(CONFIG FREEZE safe by construction; no import of heartbeat_core/filters/risk_gate/
fleet_executor/params.json for anything other than the frozen ExitShape constant, which is
a dataclass literal, not a mutable file this freeze covers). Writes only under
analysis/whole-engine-null/. Places no order, reads Alpaca market-data endpoints only
(historical option bars -- not OPRA-gated, see refused_setup_ledger.py's fetch_bars
docstring for the verified mechanism this module reuses).

RESUMABLE + CACHED: every fetched 1-minute option-bar series is cached to
analysis/whole-engine-null/bars-cache/<contract>.json (checked first; falls back to the
already-large backtest/data/highres/<contract>_1m_<date>.csv cache built by
refused_setup_ledger.py before hitting the network at all -- $0 marginal cost for anything
already fetched by that ledger's daily fire). A killed/interrupted run loses no completed
fetch; re-running picks up where it left off.

Run:
    backtest/.venv/Scripts/python.exe setup/scripts/whole_engine_null.py [--date YYYY-MM-DD]
        [--resamples N] [--seed N] [--fetch-budget-s N] [--skip-fetch]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
SETUP_SCRIPTS = REPO / "setup" / "scripts"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(FLEET_DIR), str(SETUP_SCRIPTS), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402 -- automation/state/fleet/strategies.py (READ ONLY)
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
import refused_setup_ledger as refusals  # noqa: E402 -- fetch_bars() reuse
from et_clock import et_now  # noqa: E402
import go_live_gate as glg  # noqa: E402 -- fee_ex_cat() A1 cost model reuse

PREREG = REPO / "analysis" / "recommendations" / "prereg-whole-engine-null-2026-09-01.json"
TRADES_ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"
SPY_5M_FILE = BACKTEST / "data" / "spy_5m_2026-05-19_2026-09-01.csv"
HIGHRES_DIR = BACKTEST / "data" / "highres"

OUT_DIR = REPO / "analysis" / "whole-engine-null"
BARS_CACHE_DIR = OUT_DIR / "bars-cache"

ACTIVE_ARMS = ("safe-2", "bold-2", "safe-3", "risky-1")   # prereg's P1 arm set, verbatim
P1_START = "2026-08-11"
P2_START = "2026-09-01"

TIME_STOP_ET = dt.time(15, 40)          # prereg's stated "15:40 time stop"
ENTRY_WINDOW_START = dt.time(9, 35)
ENTRY_WINDOW_END = dt.time(15, 0)
STRATEGY_NAME = "ribbon_ride"

DEFAULT_RESAMPLES = 300                 # prereg's own disclosed fallback if 1000 is too slow
FETCH_BUDGET_S_DEFAULT = 480.0          # wall-clock cap on NEW network fetches this run
SIGN_AGREEMENT_MIN = 0.85               # V9 validate-the-validator bar (fable-judgment
                                         # 02-VALIDATION V9). Written into the prereg as the
                                         # dated addendum `addendum_2026_09_01_validator_fidelity`:
                                         # the walker must reproduce the engine's OWN realized
                                         # P&L signs on >= 85% of P1 entries, or the verdict is
                                         # WITHHELD. A PASS/FAIL from an unfaithful walker is a
                                         # statement about the harness, not the engine.

COST_SLIP_CENTS = glg.COST_MODEL_EXIT_SLIPPAGE_CENTS  # 2c/contract, A1's model, reused verbatim


def log(msg: str) -> None:
    print(f"[whole-engine-null] {msg}", flush=True)


# ============================================================================================ #
# 0. FROZEN DESIGN (loaded, never edited by this module)
# ============================================================================================ #
def load_prereg() -> dict:
    return json.loads(PREREG.read_text(encoding="utf-8"))


# ============================================================================================ #
# 1. ENGINE TRADES + POPULATIONS
# ============================================================================================ #
def load_engine_rows() -> list[dict]:
    """Every row in trades-enriched.jsonl with attribution=='engine' (the row this study
    scores), skipping the leading `_meta` summary line."""
    out = []
    with open(TRADES_ENRICHED, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("_meta"):
                continue
            if row.get("attribution") == "engine":
                out.append(row)
    return out


def build_populations(rows: list[dict]) -> dict[str, list[dict]]:
    p1 = [r for r in rows if r["date"] >= P1_START and r["arm"] in ACTIVE_ARMS]
    p2 = [r for r in rows if r["date"] >= P2_START and r["arm"] in ACTIVE_ARMS]
    return {"P1_post_ladder": p1, "P2_frozen_window": p2}


def group_by_day(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["date"], []).append(r)
    for d in out:
        out[d].sort(key=lambda r: r["entry_ts_et"])
    return out


# ============================================================================================ #
# 2. SPY 5-MINUTE BARS (spot for strike selection, structure_stop closes, day open/close)
# ============================================================================================ #
def load_spy_5m() -> pd.DataFrame:
    """Wall-clock ET, tz-naive, DST-correct -- via a real tz convert+strip (NEVER a bare
    string-offset strip, which et_frame.py's own module docstring documents as silently
    WRONG for EST months on this exact file family)."""
    df = pd.read_csv(SPY_5M_FILE)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(timestamp_et=ts.dt.tz_localize(None))
    df["date"] = df["timestamp_et"].dt.strftime("%Y-%m-%d")
    df["time"] = df["timestamp_et"].dt.strftime("%H:%M")
    return df.sort_values("timestamp_et").reset_index(drop=True)


def day_frame(spy5: pd.DataFrame, date: str) -> pd.DataFrame:
    return spy5.loc[spy5["date"] == date].reset_index(drop=True)


def daily_open_close(spy5: pd.DataFrame, date: str) -> Optional[tuple[float, float]]:
    """RTH open->close: first bar at/after 09:30, last bar at/before 16:00."""
    d = day_frame(spy5, date)
    rth = d.loc[(d["time"] >= "09:30") & (d["time"] <= "16:00")]
    if rth.empty:
        return None
    return float(rth.iloc[0]["open"]), float(rth.iloc[-1]["close"])


def spy_down_days(spy5: pd.DataFrame, dates: list[str]) -> set[str]:
    out = set()
    for d in dates:
        oc = daily_open_close(spy5, d)
        if oc and (oc[1] - oc[0]) < 0:
            out.add(d)
    return out


def entry_grid(date: str) -> list[str]:
    """5-minute entry-minute grid, 09:35..15:00 inclusive -- the discretization DEVIATION
    from the prereg's literal '1-minute uniform' (see `deviations` in the output; SPY 1m
    bars are not cached anywhere in this repo, only 5m -- the prereg itself names '1m/5m' as
    an acceptable spot source)."""
    out = []
    t = dt.datetime.combine(dt.date.today(), ENTRY_WINDOW_START)
    end = dt.datetime.combine(dt.date.today(), ENTRY_WINDOW_END)
    while t <= end:
        out.append(t.strftime("%H:%M"))
        t += dt.timedelta(minutes=5)
    return out


def spot_at(spy5: pd.DataFrame, date: str, time_str: str) -> Optional[float]:
    d = day_frame(spy5, date)
    row = d.loc[d["time"] == time_str]
    if row.empty:
        # nearest bar at/before, then at/after -- a genuinely missing 5-min print (thin tape,
        # early close) should not silently kill an entire resample.
        before = d.loc[d["time"] <= time_str]
        if not before.empty:
            return float(before.iloc[-1]["open"])
        after = d.loc[d["time"] >= time_str]
        return float(after.iloc[0]["open"]) if not after.empty else None
    return float(row.iloc[0]["open"])


def atm_strike(spot: float) -> int:
    """ATM strike the v15 core would use (fills-verified 2026-07-11: ATM). Matches
    refused_setup_ledger._strike verbatim."""
    return int(round(float(spot)))


def occ_symbol(date: str, side: str, strike: int) -> str:
    y, m, d = date.split("-")
    cp = "P" if side == "P" else "C"
    return f"SPY{y[2:]}{m}{d}{cp}{strike * 1000:08d}"


# ============================================================================================ #
# 3. 1-MINUTE OPTION BARS -- cache-first, network fallback, resumable
# ============================================================================================ #
class FetchBudget:
    """Wall-clock cap on NEW network fetches this run. Cache hits are always free and never
    count against it -- a resumed run that already cached everything it needs does zero
    network work regardless of the budget."""

    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + seconds if seconds > 0 else None
        self.n_fetched = 0
        self.n_cache_hit = 0
        self.n_highres_hit = 0
        self.n_failed = 0

    def exhausted(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline


def _cache_path(contract: str) -> Path:
    return BARS_CACHE_DIR / f"{contract}.json"


def get_1m_bars(contract: str, date: str, budget: FetchBudget) -> Optional[pd.DataFrame]:
    """Cache priority: our own analysis/whole-engine-null/bars-cache/<contract>.json ->
    backtest/data/highres/<contract>_1m_<date>.csv (refused_setup_ledger's pre-existing
    cache, built at $0 marginal cost by that daily fire) -> network fetch via
    refused_setup_ledger.fetch_bars (same mechanism, same rate-limit backoff via its
    multi-credential fallback). Returns None -- an honest null, never a fabricated price --
    when no bars exist and none can be fetched within budget."""
    cp = _cache_path(contract)
    if cp.exists():
        budget.n_cache_hit += 1
        rows = json.loads(cp.read_text(encoding="utf-8"))
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["timestamp_et"] = pd.to_datetime(date + " " + df["t"])
        return df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})[
            ["timestamp_et", "open", "high", "low", "close"]
        ]

    hr = HIGHRES_DIR / f"{contract}_1m_{date}.csv"
    if not hr.exists():
        if budget.exhausted():
            return None
        ok = refusals.fetch_bars(contract, date)
        budget.n_fetched += 1
        if not ok:
            budget.n_failed += 1
            BARS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cp.write_text("[]", encoding="utf-8")  # cache the miss -- never re-hit a dead contract
            return None
    else:
        budget.n_highres_hit += 1

    bars = refusals._load_highres(contract, date)
    if not bars:
        BARS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cp.write_text("[]", encoding="utf-8")
        return None
    rows = [{"t": t, "o": o, "h": h, "l": lo, "c": c} for (t, o, h, lo, c) in bars]
    BARS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(rows), encoding="utf-8")
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(date + " " + df["t"])
    return df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})[
        ["timestamp_et", "open", "high", "low", "close"]
    ]


# ============================================================================================ #
# 4. THE EXIT WALK -- production RIBBON_RIDE shape, real exit_manager core, every population
# ============================================================================================ #
RIBBON_SHAPE = fleet_strategies.RIBBON_RIDE.exit.to_dict()


def walk_one(*, symbol: str, side: str, date: str, entry_time_et: dt.datetime,
             entry_premium: float, qty: int, trigger_level: Optional[float],
             spy5: pd.DataFrame, budget: FetchBudget) -> Optional[dict]:
    """One position, walked through the REAL exit_manager core with the production
    RIBBON_RIDE ExitShape. Returns None (honest null) when no option bars exist for the
    contract on this day -- never a fabricated fill."""
    opt_df = get_1m_bars(symbol, date, budget)
    if opt_df is None or opt_df.empty:
        return None
    dspy = day_frame(spy5, date)
    if dspy.empty:
        return None
    result = walk_exit_manager(
        symbol=symbol, side=side, entry_time_et=entry_time_et, entry_premium=entry_premium,
        qty=int(qty), exit_shape=RIBBON_SHAPE, structure_stop_enabled=True,
        trigger_level=trigger_level, strategy=STRATEGY_NAME, time_stop_et=TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=dspy,
    )
    if not result.resolved and result.exit_reason == "no_bars_after_entry":
        return None
    exit_qty = int(qty)
    exit_avg = entry_premium + (result.dollar_pnl / (exit_qty * 100.0)) if exit_qty else entry_premium
    return {"dollar_pnl": result.dollar_pnl, "qty": exit_qty, "exit_avg_px": round(exit_avg, 4),
            "exit_reason": result.exit_reason, "hold_minutes": result.hold_minutes,
            "n_legs": len(result.legs)}


def cost_adjust(trade: dict) -> float:
    """A1's exact cost model (setup/scripts/go_live_gate.py#fee_ex_cat), plus the SAME
    2c/contract exit slippage -- applied ONCE per trade against its realized exit_avg_px,
    matching go_live_gate's row-level convention (that model already treats a possibly
    multi-leg flat_to_flat row as one fee event, not one per leg)."""
    fee = glg.fee_ex_cat(trade["qty"], trade["exit_avg_px"])
    slip = (COST_SLIP_CENTS / 100.0) * trade["qty"]
    return trade["dollar_pnl"] - fee - slip


# ============================================================================================ #
# 5. V9 -- VALIDATE THE VALIDATOR: replay the engine's OWN entries, check sign agreement
# ============================================================================================ #
def _proxy_trigger_level(row: dict) -> Optional[float]:
    """Reconstructs the SPY chart level the live structure-stop actually keyed on, for rows
    where trades-enriched.jsonl's own `trigger_level` field is null (94/121 P1 rows,
    verified this build -- the enrichment pipeline never carried it through even though
    `stop_mode`:"structure" IS recorded per-row). Uses ctx_extras' nearest_level_{above,
    below}_dist, which the SAME decision tick recorded as the live distance-to-level: a bear
    (put) entry rejects a level ABOVE spot -> trigger ~= strike + nearest_level_above_dist; a
    bull (call) entry reclaims a level BELOW spot -> trigger ~= strike - nearest_level_below_dist.
    DISCLOSED APPROXIMATION (see `deviations`): this is a reconstruction, not the recorded
    level itself -- V9's harness-reliability read is reported net of this caveat."""
    lvl = row.get("trigger_level")
    if lvl is not None:
        return float(lvl)
    extras = row.get("ctx_extras") or {}
    strike = row.get("strike")
    if strike is None:
        return None
    if row.get("right") == "P":
        d = extras.get("nearest_level_above_dist")
        return float(strike) + float(d) if d is not None else None
    d = extras.get("nearest_level_below_dist")
    return float(strike) - float(d) if d is not None else None


def run_v9(p1_rows: list[dict], spy5: pd.DataFrame, budget: FetchBudget) -> dict:
    compared, sign_agree, biases, skipped = [], 0, [], 0
    for row in p1_rows:
        entry_time = pd.Timestamp(row["entry_ts_et"]).to_pydatetime()
        trig = _proxy_trigger_level(row)
        walked = walk_one(symbol=row["symbol"], side=row["right"], date=row["date"],
                          entry_time_et=entry_time, entry_premium=float(row["entry_px"]),
                          qty=int(row["qty"]), trigger_level=trig, spy5=spy5, budget=budget)
        if walked is None:
            skipped += 1
            continue
        real_pnl = float(row["pnl_dollars"])
        walked_pnl = walked["dollar_pnl"]

        def sgn(x: float) -> int:
            return 0 if abs(x) < 1e-9 else (1 if x > 0 else -1)

        agree = sgn(real_pnl) == sgn(walked_pnl)
        sign_agree += int(agree)
        compared.append({"symbol": row["symbol"], "date": row["date"], "real_pnl": real_pnl,
                          "walked_pnl": walked_pnl, "sign_agree": agree,
                          "had_real_trigger_level": row.get("trigger_level") is not None})
        biases.append(walked_pnl - real_pnl)
    n = len(compared)
    rate = (sign_agree / n) if n else 0.0
    mean_bias = (sum(biases) / n) if n else 0.0
    return {
        "n_p1_rows": len(p1_rows), "n_compared": n, "n_skipped_no_bars": skipped,
        "n_sign_agree": sign_agree, "sign_agreement_rate": round(rate, 4),
        "mean_bias_dollars": round(mean_bias, 2),
        "harness_reliable": rate >= SIGN_AGREEMENT_MIN,
        "min_bar_for_reliable": SIGN_AGREEMENT_MIN,
        "n_rows_with_real_trigger_level": sum(1 for r in p1_rows if r.get("trigger_level") is not None),
        "detail": compared,
    }


# ============================================================================================ #
# 6. N_a -- RANDOM ENTRY, SAME EXIT MACHINERY
# ============================================================================================ #
def run_null_a(day_rows: dict[str, list[dict]], spy5: pd.DataFrame, resamples: int,
               seed: int, budget: FetchBudget) -> dict:
    rng = random.Random(seed)
    grid = None
    per_day_totals: dict[str, list[float]] = {}
    per_day_totals_cost: dict[str, list[float]] = {}
    n_draws_no_bars = 0
    for date, rows in day_rows.items():
        grid = entry_grid(date)
        day_pnls, day_pnls_cost = [], []
        for _r in range(resamples):
            total, total_cost = 0.0, 0.0
            for entry in rows:
                minute = rng.choice(grid)
                spot = spot_at(spy5, date, minute)
                if spot is None:
                    continue
                strike = atm_strike(spot)
                side = entry["right"]
                symbol = occ_symbol(date, side, strike)
                entry_dt = dt.datetime.strptime(f"{date} {minute}", "%Y-%m-%d %H:%M")
                bars = get_1m_bars(symbol, date, budget)
                if bars is None or bars.empty:
                    n_draws_no_bars += 1
                    continue
                at_or_after = bars.loc[bars["timestamp_et"] >= entry_dt]
                if at_or_after.empty:
                    n_draws_no_bars += 1
                    continue
                entry_px = float(at_or_after.iloc[0]["open"])
                if entry_px <= 0:
                    continue
                walked = walk_one(symbol=symbol, side=side, date=date,
                                  entry_time_et=entry_dt, entry_premium=entry_px,
                                  qty=int(entry["qty"]), trigger_level=float(strike),
                                  spy5=spy5, budget=budget)
                if walked is None:
                    n_draws_no_bars += 1
                    continue
                total += walked["dollar_pnl"]
                total_cost += cost_adjust(walked)
            day_pnls.append(round(total, 2))
            day_pnls_cost.append(round(total_cost, 2))
        per_day_totals[date] = day_pnls
        per_day_totals_cost[date] = day_pnls_cost

    n_common = min((len(v) for v in per_day_totals.values()), default=0)
    combined = [sum(per_day_totals[d][i] for d in per_day_totals) for i in range(n_common)]
    combined_cost = [sum(per_day_totals_cost[d][i] for d in per_day_totals_cost) for i in range(n_common)]
    return {
        "resamples_requested": resamples, "resamples_realized": n_common,
        "n_draws_no_bars_honest_null": n_draws_no_bars,
        "per_day_totals": per_day_totals, "combined_totals_as_traded": combined,
        "combined_totals_cost_adjusted": combined_cost,
    }


def percentile(values: list[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


# ============================================================================================ #
# 7. N_b -- BUY & HOLD ATM, 09:35 -> 15:40, call / put (bias-directed: skipped, see deviations)
# ============================================================================================ #
def median_entry_notional(rows: list[dict]) -> float:
    notionals = [float(r["entry_px"]) * float(r["qty"]) * 100.0 for r in rows]
    if not notionals:
        return 500.0
    s = sorted(notionals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def run_null_b(day_rows: dict[str, list[dict]], spy5: pd.DataFrame, median_notional: float,
               budget: FetchBudget) -> dict:
    per_side: dict[str, list[dict]] = {"C": [], "P": []}
    for date in day_rows:
        spot = spot_at(spy5, date, "09:35")
        if spot is None:
            continue
        strike = atm_strike(spot)
        for side in ("C", "P"):
            symbol = occ_symbol(date, side, strike)
            bars = get_1m_bars(symbol, date, budget)
            if bars is None or bars.empty:
                continue
            entry_dt = dt.datetime.strptime(f"{date} 09:35", "%Y-%m-%d %H:%M")
            exit_dt = dt.datetime.strptime(f"{date} 15:40", "%Y-%m-%d %H:%M")
            entry_rows = bars.loc[bars["timestamp_et"] >= entry_dt]
            exit_rows = bars.loc[bars["timestamp_et"] <= exit_dt]
            if entry_rows.empty or exit_rows.empty:
                continue
            entry_px = float(entry_rows.iloc[0]["open"])
            exit_px = float(exit_rows.iloc[-1]["close"])
            if entry_px <= 0:
                continue
            qty = max(1, round(median_notional / (entry_px * 100.0)))
            pnl = (exit_px - entry_px) * qty * 100.0
            per_side[side].append({"date": date, "strike": strike, "qty": qty,
                                    "entry_px": entry_px, "exit_px": exit_px,
                                    "pnl_dollars": round(pnl, 2)})
    out = {}
    for side, label in (("C", "call"), ("P", "put")):
        trades = per_side[side]
        out[f"n_b_{label}"] = {
            "n_days": len(trades), "total_pnl": round(sum(t["pnl_dollars"] for t in trades), 2),
            "trades": trades,
        }
    out["n_b_bias_directed"] = {
        "status": "SKIPPED",
        "reason": ("today-bias.json has no historical archive covering P1 (only 2 stray "
                   "snapshots exist repo-wide, both pre-P1: analysis/level-quality/"
                   "snapshots/2026-06-{16,19}/today-bias.json). Prereg explicitly allows "
                   "'else skip and disclose' for this leg."),
    }
    return out


# ============================================================================================ #
# 8. N_c -- OPPOSITE DIRECTION: the engine's exact entries, side flipped, same strike/machinery
# ============================================================================================ #
def run_null_c(p1_rows: list[dict], spy5: pd.DataFrame, budget: FetchBudget) -> dict:
    trades = []
    for row in p1_rows:
        flip_side = "P" if row["right"] == "C" else "C"
        symbol = occ_symbol(row["date"], flip_side, int(row["strike"]))
        entry_time = pd.Timestamp(row["entry_ts_et"]).to_pydatetime()
        bars = get_1m_bars(symbol, row["date"], budget)
        if bars is None or bars.empty:
            continue
        at_or_after = bars.loc[bars["timestamp_et"] >= entry_time]
        if at_or_after.empty:
            continue
        entry_px = float(at_or_after.iloc[0]["open"])
        if entry_px <= 0:
            continue
        trig = _proxy_trigger_level(row)
        walked = walk_one(symbol=symbol, side=flip_side, date=row["date"],
                          entry_time_et=entry_time, entry_premium=entry_px,
                          qty=int(row["qty"]), trigger_level=trig, spy5=spy5, budget=budget)
        if walked is None:
            continue
        trades.append({"date": row["date"], "orig_symbol": row["symbol"], "flip_symbol": symbol,
                       "orig_side": row["right"], "flip_side": flip_side,
                       "dollar_pnl": walked["dollar_pnl"]})
    total = sum(t["dollar_pnl"] for t in trades)
    return {"n_trades": len(trades), "n_p1_rows": len(p1_rows), "total_pnl": round(total, 2),
            "trades": trades}


# ============================================================================================ #
# 9. PASS CRITERION -- mechanical, from the prereg's frozen text, nothing hand-tuned here
# ============================================================================================ #
def evaluate_pass_criterion(*, engine_total: float, engine_total_cost: float,
                            na_totals: list[float], na_totals_cost: list[float],
                            nb_call_total: float, engine_p3_total: float,
                            na_p3_totals: list[float], nc_total: float,
                            p2_n_days: int) -> dict:
    na_p95 = percentile(na_totals, 95)
    na_p5 = percentile(na_totals, 5)
    na_p25 = percentile(na_totals, 25)
    na_p75 = percentile(na_totals, 75)
    na_iqr = (na_p75 - na_p25) if (na_p75 is not None and na_p25 is not None) else None

    na_p3_p75 = percentile(na_p3_totals, 75)
    na_p3_median = percentile(na_p3_totals, 50)

    check1 = (na_p95 is not None) and (engine_total > na_p95)
    check2 = (na_iqr is not None) and (engine_total > (nb_call_total + na_iqr))
    check3 = (engine_p3_total >= 0) or (na_p3_p75 is not None and engine_p3_total > na_p3_p75)
    check4 = nc_total <= 0

    nails = {
        "BETA": engine_total <= nb_call_total,
        "NULL_DOMINATED": (na_p5 is not None and na_p95 is not None
                          and na_p5 <= engine_total <= na_p95),
        "REGIME_BOUND": nc_total > 0,
        "DOWN_DAY_BLIND": (engine_p3_total < 0
                          and (na_p3_median is not None and engine_p3_total < na_p3_median)),
        "UNPOWERED": p2_n_days < 20,
    }

    checks = {
        "check1_engine_gt_na_p95": check1,
        "check2_engine_gt_nb_call_plus_na_iqr": check2,
        "check3_p3_nonneg_or_gt_na_p3_p75": check3,
        "check4_nc_le_0": check4,
    }
    all_pass = all(checks.values())
    named_fails = [name for name, hit in nails.items()
                  if hit and name != "UNPOWERED"]
    if all_pass:
        verdict = "PASS"
    else:
        verdict = "FAIL"
        if not named_fails:
            failing = [k for k, v in checks.items() if not v]
            named_fails = [f"unnamed_nail:{','.join(failing)}"]
    return {
        "checks": checks, "all_checks_pass": all_pass, "verdict": verdict,
        "named_fails": named_fails, "kill_nails": nails,
        "na_percentiles": {"p5": na_p5, "p25": na_p25, "p75": na_p75, "p95": na_p95,
                          "iqr": na_iqr},
        "na_p3_percentiles": {"median": na_p3_median, "p75": na_p3_p75},
        "inputs": {"engine_total": engine_total, "engine_total_cost_adjusted": engine_total_cost,
                  "nb_call_total": nb_call_total, "engine_p3_total": engine_p3_total,
                  "nc_total": nc_total},
    }


# ============================================================================================ #
# 10. MAIN
# ============================================================================================ #
WITHHELD_VERDICT = "WITHHELD_HARNESS_UNRELIABLE"


def finalize_verdict(mechanical_verdict: str, harness_reliable: bool) -> str:
    """The ONE place the reported verdict is decided.

    mechanical_verdict is the frozen pass criterion's own PASS/FAIL. It is reported as the
    study verdict only when the exit walker has been shown faithful to the engine's own real
    fills (V9 sign agreement >= SIGN_AGREEMENT_MIN). Otherwise the verdict is withheld --
    the numbers are still published, labeled as describing the harness, not the engine.
    Never raises; unknown inputs withhold (fail-closed on certification).
    """
    if harness_reliable is True and mechanical_verdict in ("PASS", "FAIL"):
        return mechanical_verdict
    return WITHHELD_VERDICT


def run(date: str, resamples: int, seed: int, fetch_budget_s: float, skip_fetch: bool) -> dict:
    t0 = time.monotonic()
    prereg = load_prereg()
    deviations: list[str] = []

    rows = load_engine_rows()
    pops = build_populations(rows)
    p1_rows, p2_rows = pops["P1_post_ladder"], pops["P2_frozen_window"]
    p1_by_day = group_by_day(p1_rows)
    p1_days = sorted(p1_by_day)

    spy5 = load_spy_5m()
    down_days = spy_down_days(spy5, p1_days)
    p3_rows = [r for r in p1_rows if r["date"] in down_days]
    p3_by_day = group_by_day(p3_rows)

    deviations.append(
        "Entry-minute resampling uses the 5-minute SPY grid (09:35..15:00, 66 points), not a "
        "true 1-minute-uniform draw -- no SPY 1-minute bar cache exists anywhere in this repo "
        "(only 5-minute); the prereg itself names 'SPY 1m/5m' as an acceptable spot source."
    )
    deviations.append(
        "N_a / N_c structure-stop trigger_level has no chart level to key on for a random "
        "entry, so N_a uses the entry's own ATM strike as the proxy level; N_c (and V9, for "
        "the 94/121 P1 rows whose recorded trigger_level is null) reconstruct it from "
        "ctx_extras' nearest_level_{above,below}_dist relative to strike. Both are disclosed "
        "approximations of the real chart level the live engine actually used, not the "
        "recorded value itself."
    )
    deviations.append(
        "N_b bias-directed leg SKIPPED: today-bias.json has no historical archive covering "
        "P1 (only 2 pre-P1 snapshots exist repo-wide). Prereg explicitly allows 'skip and "
        "disclose' here."
    )

    budget = FetchBudget(0.0 if skip_fetch else fetch_budget_s)

    log(f"P1: {len(p1_rows)} trades / {len(p1_days)} days. P2: {len(p2_rows)} trades. "
        f"P3 (SPY-down subset of P1): {len(p3_rows)} trades / {len(p3_by_day)} days.")

    log("V9 -- validating the validator (replaying the engine's OWN entries)...")
    v9 = run_v9(p1_rows, spy5, budget)
    log(f"V9: {v9['n_compared']} compared, sign agreement {v9['sign_agreement_rate']:.1%} "
        f"(bar={SIGN_AGREEMENT_MIN:.0%}), mean bias ${v9['mean_bias_dollars']:+.2f}, "
        f"{v9['n_skipped_no_bars']} skipped (no bars).")
    harness_reliable = v9["harness_reliable"]
    if not harness_reliable:
        deviations.append(
            f"V9 sign agreement {v9['sign_agreement_rate']:.1%} < {SIGN_AGREEMENT_MIN:.0%} bar "
            "-- per the prereg's addendum_2026_09_01_validator_fidelity the overall verdict is "
            "WITHHELD (HARNESS_UNRELIABLE). The mechanical pass-criterion sub-checks are still "
            "computed and published as mechanical_verdict, but they describe the walker, not the "
            "engine, until the walker's fidelity clears the bar. See v9_harness_validation."
        )

    log(f"N_a -- {resamples} resamples/day over {len(p1_days)} P1 days...")
    na = run_null_a(p1_by_day, spy5, resamples, seed, budget)
    log(f"N_a: {na['resamples_realized']}/{resamples} resamples fully realized; "
        f"{na['n_draws_no_bars_honest_null']} draws had no bars.")

    log("N_a on P3 (down-day subset)...")
    na_p3 = run_null_a(p3_by_day, spy5, resamples, seed + 1, budget) if p3_by_day else {
        "resamples_requested": resamples, "resamples_realized": 0,
        "combined_totals_as_traded": [], "combined_totals_cost_adjusted": [],
        "n_draws_no_bars_honest_null": 0, "per_day_totals": {}, "per_day_totals_cost": {},
    }

    log("N_b -- buy & hold ATM call/put, 09:35 -> 15:40...")
    median_notional = median_entry_notional(p1_rows)
    nb = run_null_b(p1_by_day, spy5, median_notional, budget)
    log(f"N_b: call total ${nb['n_b_call']['total_pnl']:+.2f} over {nb['n_b_call']['n_days']} "
        f"days; put total ${nb['n_b_put']['total_pnl']:+.2f} over {nb['n_b_put']['n_days']} days.")

    log("N_c -- opposite direction, engine's exact entries, side flipped...")
    nc = run_null_c(p1_rows, spy5, budget)
    log(f"N_c: {nc['n_trades']}/{nc['n_p1_rows']} flipped, total ${nc['total_pnl']:+.2f}.")

    engine_total_p1 = round(sum(float(r["pnl_dollars"]) for r in p1_rows), 2)
    arm_day_counts: dict[tuple, int] = {}
    for r in p1_rows:
        key = (r["arm"], r["date"])
        arm_day_counts[key] = arm_day_counts.get(key, 0) + 1
    engine_total_p1_cost = round(sum(
        glg.cost_adjusted_pnl(r, arm_day_counts, COST_SLIP_CENTS) for r in p1_rows), 2)
    engine_p3_total = round(sum(float(r["pnl_dollars"]) for r in p3_rows), 2)

    pass_eval = evaluate_pass_criterion(
        engine_total=engine_total_p1, engine_total_cost=engine_total_p1_cost,
        na_totals=na["combined_totals_as_traded"], na_totals_cost=na["combined_totals_cost_adjusted"],
        nb_call_total=nb["n_b_call"]["total_pnl"], engine_p3_total=engine_p3_total,
        na_p3_totals=na_p3["combined_totals_as_traded"], nc_total=nc["total_pnl"],
        p2_n_days=len(set(r["date"] for r in p2_rows)),
    )

    # VERDICT GATING (2026-09-01, orchestrator, reversing the same-night FIXER pass): the
    # pass criterion is evaluated exactly as frozen (`pass_eval["verdict"]`, published as
    # `mechanical_verdict`). Whether that verdict may be REPORTED as the study's verdict is
    # governed by the validator-fidelity precondition written into the prereg as
    # `addendum_2026_09_01_validator_fidelity`: below SIGN_AGREEMENT_MIN the overall verdict
    # is WITHHELD_HARNESS_UNRELIABLE. This is doctrine (02-VALIDATION V9), not a new knob --
    # a harness that reproduces the engine's own fills on only 79% of trades cannot certify
    # the engine either way. finalize_verdict() is the single point of truth for this.

    elapsed = round(time.monotonic() - t0, 1)
    if resamples < 1000:
        deviations.append(
            f"N_a ran at {resamples} resamples/day, not the prereg's default 1000 (session "
            "wall-clock budget) -- the prereg's own text pre-authorizes this exact fallback "
            "('if too slow, 300 and disclose'). Re-run with --resamples 1000 for the full "
            "design; every fetched contract is cached, so a re-run only pays for NEW draws."
        )

    doc = {
        "_meta": {
            "date": date, "generated_at_et": et_now().isoformat(timespec="seconds"),
            "builder": "setup/scripts/whole_engine_null.py",
            "prereg": "analysis/recommendations/prereg-whole-engine-null-2026-09-01.json",
            "shadow_only": "MEASUREMENT ONLY -- never places, arms, or edits a gate/params file.",
            "elapsed_s": elapsed,
            "fetch_stats": {"cache_hit": budget.n_cache_hit, "highres_hit": budget.n_highres_hit,
                           "network_fetched": budget.n_fetched, "network_failed": budget.n_failed},
        },
        "populations": {
            "P1_post_ladder": {"n_trades": len(p1_rows), "n_days": len(p1_days),
                              "days": p1_days, "total_pnl": engine_total_p1,
                              "total_pnl_cost_adjusted": engine_total_p1_cost},
            "P2_frozen_window": {"n_trades": len(p2_rows),
                                "n_days": len(set(r["date"] for r in p2_rows)),
                                "days": sorted(set(r["date"] for r in p2_rows)),
                                "total_pnl": round(sum(float(r["pnl_dollars"]) for r in p2_rows), 2)},
            "P3_spy_down_days": {"n_trades": len(p3_rows), "n_days": len(p3_by_day),
                                "days": sorted(p3_by_day), "total_pnl": engine_p3_total},
        },
        "v9_harness_validation": v9,
        "harness_reliable": harness_reliable,
        "n_a_random_entry_same_exit": {k: v for k, v in na.items() if k != "per_day_totals"
                                       and k != "per_day_totals_cost"},
        "n_a_on_p3": {k: v for k, v in na_p3.items() if k not in ("per_day_totals", "per_day_totals_cost")},
        "n_b_buy_and_hold_atm": nb,
        "n_c_opposite_direction": nc,
        "pass_criterion": pass_eval,
        "mechanical_verdict": pass_eval["verdict"],
        "overall_verdict": finalize_verdict(pass_eval["verdict"], harness_reliable),
        "deviations": deviations,
        "look_ahead_guards_note": prereg["look_ahead_guards"],
    }
    return doc


def write_outputs(doc: dict, date: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{date}.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    (OUT_DIR / "latest.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")

    pc = doc["pass_criterion"]
    lines = [
        f"# Whole-Engine Null Study -- {date}",
        "",
        f"**Verdict: {doc['overall_verdict']}**"
        + (f" -- {', '.join(pc.get('named_fails', []))}" if doc['overall_verdict'] == "FAIL" else ""),
        "",
        f"Mechanical pass-criterion result (frozen text, describes the walker until V9 clears): "
        f"**{doc['mechanical_verdict']}**",
        f"V9 validate-the-validator gate (prereg addendum_2026_09_01_validator_fidelity): "
        f"harness_reliable={doc['harness_reliable']} "
        f"(sign agreement {doc['v9_harness_validation']['sign_agreement_rate']:.1%}, "
        f"n={doc['v9_harness_validation']['n_compared']}, "
        f"bar={SIGN_AGREEMENT_MIN:.0%}) -- below the bar the verdict above is WITHHELD.",
        "",
        "## P1 (post-ladder, >=2026-08-11)",
        f"- engine trades: {doc['populations']['P1_post_ladder']['n_trades']} over "
        f"{doc['populations']['P1_post_ladder']['n_days']} days",
        f"- engine total P&L: ${doc['populations']['P1_post_ladder']['total_pnl']:+.2f} "
        f"(cost-adjusted ${doc['populations']['P1_post_ladder']['total_pnl_cost_adjusted']:+.2f})",
        f"- N_a 95th pctile: {pc['na_percentiles']['p95']}",
        f"- N_a IQR: {pc['na_percentiles']['iqr']}",
        f"- N_b call total: ${doc['n_b_buy_and_hold_atm']['n_b_call']['total_pnl']:+.2f}",
        f"- N_b put total: ${doc['n_b_buy_and_hold_atm']['n_b_put']['total_pnl']:+.2f}",
        f"- N_c (opposite direction) total: ${doc['n_c_opposite_direction']['total_pnl']:+.2f}",
        "",
        "## P3 (SPY-down-day subset of P1)",
        f"- trades: {doc['populations']['P3_spy_down_days']['n_trades']} over "
        f"{doc['populations']['P3_spy_down_days']['n_days']} days, "
        f"total P&L ${doc['populations']['P3_spy_down_days']['total_pnl']:+.2f}",
        "",
        "## Pass criterion (mechanical, frozen)",
    ]
    for name, val in pc["checks"].items():
        lines.append(f"- {name}: {'PASS' if val else 'FAIL'}")
    lines += ["", "## Kill nails"]
    for name, hit in pc["kill_nails"].items():
        lines.append(f"- {name}: {'TRIGGERED' if hit else 'clear'}")
    lines += ["", "## Deviations from the frozen design"]
    for d in doc["deviations"]:
        lines.append(f"- {d}")
    (OUT_DIR / f"{date}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    p1_total = doc['populations']['P1_post_ladder']['total_pnl']
    if doc["overall_verdict"] == WITHHELD_VERDICT:
        summary = (f"WHOLE-ENGINE-NULL {date}: WITHHELD (harness unreliable -- V9 sign agreement "
                  f"{doc['v9_harness_validation']['sign_agreement_rate']:.1%} < {SIGN_AGREEMENT_MIN:.0%}). "
                  f"Mechanical sub-checks read {doc['mechanical_verdict']} on the raw numbers "
                  f"(engine P1 ${p1_total:+.2f}, N_a p95 {pc['na_percentiles']['p95']}, "
                  f"N_c ${doc['n_c_opposite_direction']['total_pnl']:+.2f}) but describe the walker, "
                  "not the engine, until the walker is fixed.")
    elif doc["overall_verdict"] == "PASS":
        summary = (f"WHOLE-ENGINE-NULL {date}: PASS -- engine P1 ${p1_total:+.2f} "
                  f"beats N_a p95 ({pc['na_percentiles']['p95']}), N_b call, P3, and N_c <= 0.")
    else:
        summary = (f"WHOLE-ENGINE-NULL {date}: FAIL -- {', '.join(pc.get('named_fails', []))}. "
                  f"engine P1 ${p1_total:+.2f}, "
                  f"N_a p95 {pc['na_percentiles']['p95']}, N_c ${doc['n_c_opposite_direction']['total_pnl']:+.2f}.")
    (OUT_DIR / "summary-line.txt").write_text(summary + "\n", encoding="utf-8")
    log(summary)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None)
    ap.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fetch-budget-s", type=float, default=FETCH_BUDGET_S_DEFAULT)
    ap.add_argument("--skip-fetch", action="store_true",
                    help="cache-only: never hit the network, honest-null any missing contract")
    a = ap.parse_args()
    date = a.date or et_now().date().isoformat()
    doc = run(date, a.resamples, a.seed, a.fetch_budget_s, a.skip_fetch)
    write_outputs(doc, date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
