"""bear_f8_sign_costing.py -- SIGN-ONLY costing of blocker 8 (bear VIX floor) refusals.

Born 2026-09-03 from `BEAR-F8-VIX-FLOOR-COSTING-REPLAY`'s SCOPE RAISED note
(`automation/overnight/queue.md`, Fable, 03:57 ET): the item's original ask -- a full-dollar
`postfix_gate_costing.py` replay -- is blocked on `WALKER-MARKET-STAGE-FILL-ROOT-FIX` (that
replay prices exits with `exit_manager_walk`, whose magnitude fidelity is under repair). This
tool answers a narrower, walker-free question instead: does SPY itself move further in the
refused population's favour than in the entered population's favour, using ONLY spot price?

NO option pricing. NO walker (`exit_manager_walk`, `simulate_trade_real`, or any pricing/replay
module) is imported or called anywhere in this file -- verified by
`backtest/tests/test_bear_f8_sign_costing.py::test_no_walker_or_option_pricing_import`.
SPY 5-minute bars only (`backtest/data/spy_5m_2026-05-19_2026-09-02.csv` -- no 1-minute SPY file
exists anywhere in `backtest/data/`; this is a disclosed fallback, not a silent substitution).

Full pre-registered rule (written BEFORE this tool computed anything): see
`analysis/recommendations/bear-f8-vix-floor-sign-costing-2026-09-03.md`. This module is a
read-only report generator -- it never edits `filters.py`, `params.json`, or any live gate, and
it is NOT a ship proposal (10-30 shape-menu input only).

Run: backtest/.venv/Scripts/python.exe backtest/tools/bear_f8_sign_costing.py
     [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                            # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CORE_DECISIONS = ROOT / "automation" / "state" / "core-decisions.jsonl"
TRADES_ENRICHED = ROOT / "analysis" / "trades-enriched.jsonl"
SPY_5M = REPO / "data" / "spy_5m_2026-05-19_2026-09-02.csv"

WINDOW_START = dt.date(2026, 8, 5)
WINDOW_END = dt.date(2026, 9, 1)
EVENT_CLUSTER_GAP_MINUTES = 15
ENTER_JOIN_TOLERANCE_S = 120
BOOTSTRAP_SEED = 1337
BOOTSTRAP_N = 2000
VIX_FLOOR = 17.30
VIX_STRAT_SPLIT = 15.5

CORE_ARMS = ("safe-2", "bold-2")
ARM_TO_ACCOUNT = {"safe-2": "safe", "bold-2": "bold"}


# ============================================================ loading -- core-decisions.jsonl

def load_core_decisions(path: Path) -> list[dict]:
    """Fail-open line reader. No filtering here -- callers slice by date/armed/account."""
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_trades_enriched(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("_meta"):
                continue
            rows.append(r)
    return rows


# ============================================================ clustering (identical convention
# to postfix_gate_costing.cluster_events / gate_expiry_check.cluster_events -- reimplemented
# locally so this file has zero import surface on the walker-adjacent modules).

def cluster_events(rows: list[dict], gap_minutes: int = EVENT_CLUSTER_GAP_MINUTES) -> list[dict]:
    """Fold consecutive rows (already filtered) into one event per gap_minutes-separated
    cluster, keeping the FIRST row (earliest ts) of each cluster as the tradeable signal."""
    rows_sorted = sorted(rows, key=lambda r: r["ts_et"])
    events: list[dict] = []
    last_ts: dt.datetime | None = None
    for r in rows_sorted:
        try:
            ts = dt.datetime.fromisoformat(r["ts_et"])
        except (ValueError, TypeError):
            continue
        if last_ts is None or (ts - last_ts).total_seconds() > gap_minutes * 60:
            events.append(r)
        last_ts = ts
    return events


# ============================================================ Population R -- refused episodes

def build_population_r(rows: list[dict]) -> list[dict]:
    """Sole-blocker-8 bear HOLD rows, armed, pooled across BOTH accounts (see .md rationale:
    safe/bold fire the same signal within seconds and cluster identically pooled or per-account
    -- pooling avoids double-counting the same market moment as two episodes)."""
    sub = [
        r for r in rows
        if r.get("armed") is True
        and WINDOW_START.isoformat() <= r.get("ts_et", "")[:10] <= WINDOW_END.isoformat()
        and r.get("verdict") == "HOLD"
        and (r.get("bear_blockers") or []) == [8]
    ]
    events = cluster_events(sub)
    out = []
    for ev in events:
        out.append({
            "ts_et": ev["ts_et"],
            "entry_price": ev.get("spy"),
            "vix": ev.get("vix"),
            "account_first_tick": ev.get("account"),
        })
    return out


# ============================================================ ENTER_BEAR join (core-decisions
# spot price, NOT option premium -- trades-enriched carries no SPY spot field)

def join_enter_bear(account: str, target_ts: dt.datetime, enter_rows_by_account: dict) -> dict | None:
    """Closest core-decisions ENTER_BEAR row for `account` at-or-before `target_ts`, within
    ENTER_JOIN_TOLERANCE_S seconds. Returns None if nothing qualifies (caller drops + discloses)."""
    candidates = enter_rows_by_account.get(account, [])
    best = None
    best_dt = None
    for r in candidates:
        try:
            ts = dt.datetime.fromisoformat(r["ts_et"])
        except (ValueError, TypeError):
            continue
        delta = (target_ts - ts).total_seconds()
        if 0 <= delta <= ENTER_JOIN_TOLERANCE_S:
            if best_dt is None or delta < best_dt:
                best, best_dt = r, delta
    return best


def build_enter_bear_index(rows: list[dict]) -> dict:
    idx: dict[str, list[dict]] = {"safe": [], "bold": []}
    for r in rows:
        if r.get("account") in idx and str(r.get("verdict", "")).startswith("ENTER_BEAR"):
            idx[r["account"]].append(r)
    return idx


# ============================================================ Population E -- entered trades +
# full-history walk-parameter trips (both derived the same way, different date filters)

def build_bear_trips(trades: list[dict], enter_idx: dict, *, window_only: bool) -> tuple[list[dict], int]:
    """Core-arm (safe-2/bold-2) engine put trips, joined to their core-decisions ENTER_BEAR spot
    tick. Returns (trips, n_dropped_no_join)."""
    out, dropped = [], 0
    for t in trades:
        if t.get("right") != "P":
            continue
        if t.get("attribution") != "engine":
            continue
        if t.get("unbalanced"):
            continue
        if t.get("arm") not in CORE_ARMS:
            continue
        date = t.get("date", "")
        if window_only and not (WINDOW_START.isoformat() <= date <= WINDOW_END.isoformat()):
            continue
        entry_ts_raw = t.get("entry_ts_et")
        hold_min = t.get("hold_min")
        if not entry_ts_raw or hold_min is None:
            dropped += 1
            continue
        try:
            entry_ts = dt.datetime.fromisoformat(entry_ts_raw)
        except ValueError:
            dropped += 1
            continue
        account = ARM_TO_ACCOUNT[t["arm"]]
        matched = join_enter_bear(account, entry_ts, enter_idx)
        if matched is None:
            dropped += 1
            continue
        out.append({
            "ts_et": matched["ts_et"],
            "entry_price": matched.get("spy"),
            "vix": matched.get("vix"),
            "hold_min": hold_min,
            "arm": t["arm"],
            "date": date,
        })
    return out, dropped


# ============================================================ SPY 5m bar walk

def load_spy_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def window_bars(spy: pd.DataFrame, entry_ts: dt.datetime, hold_min: float) -> pd.DataFrame:
    end_ts = entry_ts + dt.timedelta(minutes=hold_min)
    # start from the bar covering/at-or-before entry_ts (so a <5min hold still gets >=1 bar)
    before = spy[spy["ts"] <= entry_ts]
    start_idx = before.index[-1] if len(before) else (spy.index[0] if len(spy) else None)
    if start_idx is None:
        return spy.iloc[0:0]
    sub = spy.loc[start_idx:]
    sub = sub[sub["ts"] <= end_ts]
    if sub.empty:
        # hold shorter than the bar's own span -- still give the single covering bar
        sub = spy.loc[[start_idx]]
    return sub


def mfe_mae_points(spy: pd.DataFrame, entry_ts: dt.datetime, entry_price: float, hold_min: float) -> tuple[float, float] | None:
    """(MFE, MAE) in SPY points for a PUT position over [entry_ts, entry_ts+hold_min]."""
    bars = window_bars(spy, entry_ts, hold_min)
    if bars.empty or entry_price is None:
        return None
    mfe = entry_price - float(bars["low"].min())    # favourable = SPY falls
    mae = float(bars["high"].max()) - entry_price   # adverse = SPY rises
    return mfe, mae


def walk_outcome(spy: pd.DataFrame, entry_ts: dt.datetime, entry_price: float,
                  median_hold: float, fav_price: float, adv_price: float) -> str | None:
    """FAVOURABLE / ADVERSE / FLAT per the frozen rule. None if no bars available."""
    bars = window_bars(spy, entry_ts, median_hold)
    if bars.empty or entry_price is None:
        return None
    for _, bar in bars.iterrows():
        touched_fav = bar["low"] <= fav_price
        touched_adv = bar["high"] >= adv_price
        if touched_fav and touched_adv:
            return "ADVERSE"   # pre-registered conservative tie-break, same-bar ambiguity
        if touched_fav:
            return "FAVOURABLE"
        if touched_adv:
            return "ADVERSE"
    return "FLAT"


# ============================================================ bootstrap

def session_clustered_bootstrap_ci(entries: list[dict], outcome_key: str, target: str,
                                     seed: int = BOOTSTRAP_SEED, n_boot: int = BOOTSTRAP_N) -> tuple[float, float, float]:
    """Resample TRADING DAYS (sessions) with replacement; per resample, pool all entries whose
    session was drawn and compute the FAVOURABLE-rate (or whichever `target` outcome) across
    them. Returns (point_estimate, ci_lower_2.5, ci_upper_97.5). Point estimate is the
    un-resampled rate over all entries (not the bootstrap mean)."""
    if not entries:
        return (float("nan"), float("nan"), float("nan"))
    by_session: dict[str, list[dict]] = {}
    for e in entries:
        sess = e["ts_et"][:10]
        by_session.setdefault(sess, []).append(e)
    sessions = sorted(by_session)
    point = sum(1 for e in entries if e[outcome_key] == target) / len(entries)
    rng = np.random.default_rng(seed)
    n_sessions = len(sessions)
    rates = []
    for _ in range(n_boot):
        picked = rng.choice(sessions, size=n_sessions, replace=True)
        pool = []
        for s in picked:
            pool.extend(by_session[s])
        if not pool:
            continue
        rates.append(sum(1 for e in pool if e[outcome_key] == target) / len(pool))
    if not rates:
        return (point, float("nan"), float("nan"))
    lo, hi = np.percentile(rates, [2.5, 97.5])
    return (point, float(lo), float(hi))


def session_clustered_diff_ci(r_entries: list[dict], e_entries: list[dict], outcome_key: str,
                                target: str, seed: int = BOOTSTRAP_SEED, n_boot: int = BOOTSTRAP_N) -> tuple[float, float, float]:
    """Bootstrap CI on (R favourable rate - E favourable rate), resampling the UNION of session
    dates once per iteration and applying the same drawn sessions to both populations."""
    r_by_session: dict[str, list[dict]] = {}
    for e in r_entries:
        r_by_session.setdefault(e["ts_et"][:10], []).append(e)
    e_by_session: dict[str, list[dict]] = {}
    for e in e_entries:
        e_by_session.setdefault(e["ts_et"][:10], []).append(e)
    all_sessions = sorted(set(r_by_session) | set(e_by_session))
    if not all_sessions:
        return (float("nan"), float("nan"), float("nan"))
    r_point = (sum(1 for e in r_entries if e[outcome_key] == target) / len(r_entries)) if r_entries else float("nan")
    e_point = (sum(1 for e in e_entries if e[outcome_key] == target) / len(e_entries)) if e_entries else float("nan")
    point = r_point - e_point
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        picked = rng.choice(all_sessions, size=len(all_sessions), replace=True)
        r_pool, e_pool = [], []
        for s in picked:
            r_pool.extend(r_by_session.get(s, []))
            e_pool.extend(e_by_session.get(s, []))
        if not r_pool or not e_pool:
            continue
        r_rate = sum(1 for e in r_pool if e[outcome_key] == target) / len(r_pool)
        e_rate = sum(1 for e in e_pool if e[outcome_key] == target) / len(e_pool)
        diffs.append(r_rate - e_rate)
    if not diffs:
        return (point, float("nan"), float("nan"))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return (point, float(lo), float(hi))


# ============================================================ main

def outcome_pct(entries: list[dict], outcome_key: str) -> dict:
    n = len(entries)
    if n == 0:
        return {"n": 0, "favourable_pct": None, "adverse_pct": None, "flat_pct": None}
    c = {"FAVOURABLE": 0, "ADVERSE": 0, "FLAT": 0}
    for e in entries:
        c[e[outcome_key]] += 1
    return {
        "n": n,
        "favourable_pct": round(100 * c["FAVOURABLE"] / n, 1),
        "adverse_pct": round(100 * c["ADVERSE"] / n, 1),
        "flat_pct": round(100 * c["FLAT"] / n, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "analysis" / "recommendations" / "bear-f8-vix-floor-sign-costing-2026-09-03.json"))
    args = ap.parse_args()

    print("[bear-f8-sign] loading core-decisions + trades-enriched + SPY 5m bars ...", flush=True)
    core_rows = load_core_decisions(CORE_DECISIONS)
    trades = load_trades_enriched(TRADES_ENRICHED)
    spy = load_spy_bars(SPY_5M)
    enter_idx = build_enter_bear_index(core_rows)

    # ---- Population R --------------------------------------------------------------
    pop_r = build_population_r(core_rows)
    print(f"[bear-f8-sign] Population R episodes: {len(pop_r)}", flush=True)

    # ---- walk-parameter trips (full history, core arms) -----------------------------
    walk_trips, walk_dropped = build_bear_trips(trades, enter_idx, window_only=False)
    print(f"[bear-f8-sign] walk-parameter trips: {len(walk_trips)} (dropped {walk_dropped} unjoined)", flush=True)

    mfe_list, mae_list, hold_list = [], [], []
    for t in walk_trips:
        entry_ts = dt.datetime.fromisoformat(t["ts_et"])
        res = mfe_mae_points(spy, entry_ts, t["entry_price"], t["hold_min"])
        if res is None:
            continue
        mfe, mae = res
        mfe_list.append(mfe)
        mae_list.append(mae)
        hold_list.append(t["hold_min"])

    median_hold = statistics.median(hold_list)
    median_mfe = statistics.median(mfe_list)
    median_mae = statistics.median(mae_list)
    print(f"[bear-f8-sign] walk params: n={len(hold_list)} median_hold={median_hold:.2f}min "
          f"median_MFE={median_mfe:.3f}pts median_MAE={median_mae:.3f}pts", flush=True)

    # ---- Population E (same window) --------------------------------------------------
    pop_e, e_dropped = build_bear_trips(trades, enter_idx, window_only=True)
    print(f"[bear-f8-sign] Population E trades: {len(pop_e)} (dropped {e_dropped} unjoined)", flush=True)

    # ---- walk both populations forward -------------------------------------------
    def walk_all(entries: list[dict]) -> list[dict]:
        out = []
        for e in entries:
            entry_ts = dt.datetime.fromisoformat(e["ts_et"])
            entry_price = e["entry_price"]
            if entry_price is None:
                continue
            fav_price = entry_price - median_mfe
            adv_price = entry_price + median_mae
            outcome = walk_outcome(spy, entry_ts, entry_price, median_hold, fav_price, adv_price)
            if outcome is None:
                continue
            rec = dict(e)
            rec["outcome"] = outcome
            out.append(rec)
        return out

    r_walked = walk_all(pop_r)
    e_walked = walk_all(pop_e)

    r_stats = outcome_pct(r_walked, "outcome")
    e_stats = outcome_pct(e_walked, "outcome")

    r_point, r_lo, r_hi = session_clustered_bootstrap_ci(r_walked, "outcome", "FAVOURABLE")
    e_point, e_lo, e_hi = session_clustered_bootstrap_ci(e_walked, "outcome", "FAVOURABLE")
    diff_point, diff_lo, diff_hi = session_clustered_diff_ci(r_walked, e_walked, "outcome", "FAVOURABLE")

    # ---- VIX stratification of R ----------------------------------------------------
    r_low_vix = [e for e in r_walked if (e.get("vix") or 0) < VIX_STRAT_SPLIT]
    r_high_vix = [e for e in r_walked if (e.get("vix") or 0) >= VIX_STRAT_SPLIT]
    vix_strat = {
        f"vix_lt_{VIX_STRAT_SPLIT}": outcome_pct(r_low_vix, "outcome"),
        f"vix_{VIX_STRAT_SPLIT}_to_{VIX_FLOOR}": outcome_pct(r_high_vix, "outcome"),
    }

    # ---- verdict ----------------------------------------------------------------------
    if r_lo == r_lo and r_lo > e_point:  # nan-safe
        verdict = "F8_COSTS_EDGE"
    elif r_hi == r_hi and r_hi < e_point:
        verdict = "F8_EARNS_ITS_KEEP"
    else:
        verdict = "INCONCLUSIVE"

    result = {
        "generated_at_note": "sign-only, no option pricing, no walker -- see .md pre-registration",
        "window": f"{WINDOW_START}..{WINDOW_END}",
        "spy_bar_source": SPY_5M.name,
        "spy_bar_granularity": "5min (no 1-min SPY file exists in backtest/data/ -- disclosed fallback)",
        "walk_params": {
            "n_trips": len(hold_list),
            "n_dropped_unjoined": walk_dropped,
            "median_hold_min": round(median_hold, 2),
            "median_mfe_pts": round(median_mfe, 3),
            "median_mae_pts": round(median_mae, 3),
        },
        "population_r": {
            "label": "refused (sole blocker-8 bear episodes)",
            "n_raw_episodes": len(pop_r),
            "n_walked": len(r_walked),
            **r_stats,
            "favourable_rate_point": round(r_point, 4) if r_point == r_point else None,
            "favourable_rate_ci95": [round(r_lo, 4) if r_lo == r_lo else None,
                                       round(r_hi, 4) if r_hi == r_hi else None],
        },
        "population_e": {
            "label": "entered (actual bear entries, safe-2/bold-2, same window)",
            "n_raw_trades": len(pop_e),
            "n_dropped_unjoined": e_dropped,
            "n_walked": len(e_walked),
            **e_stats,
            "favourable_rate_point": round(e_point, 4) if e_point == e_point else None,
            "favourable_rate_ci95": [round(e_lo, 4) if e_lo == e_lo else None,
                                       round(e_hi, 4) if e_hi == e_hi else None],
        },
        "r_minus_e_favourable_rate": {
            "point": round(diff_point, 4) if diff_point == diff_point else None,
            "ci95": [round(diff_lo, 4) if diff_lo == diff_lo else None,
                     round(diff_hi, 4) if diff_hi == diff_hi else None],
        },
        "vix_stratification_of_r": vix_strat,
        "verdict": verdict,
        "verdict_vocab": ["F8_COSTS_EDGE", "F8_EARNS_ITS_KEEP", "INCONCLUSIVE"],
        "bootstrap": {"seed": BOOTSTRAP_SEED, "n_boot": BOOTSTRAP_N, "resample_unit": "trading_day_session"},
        "scope_note": "10-30 shape-menu input, NOT a ship proposal. No option pricing, no walker.",
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[bear-f8-sign] wrote {out_path}", flush=True)
    print(json.dumps({k: v for k, v in result.items() if k not in ("walk_params",)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
