"""
D3 -- LOSS-SIZE: were the losers too big? Read-only scratch analysis.
Writes analysis/deep-research/2026-09-03-money/dissect-loss-size.{md,json}

Inputs (all cached/local, no network, no broker calls):
  analysis/pain-ledger/mae-mfe.json          -- 394 scored engine round trips
  automation/state/fills-ledger.jsonl        -- today's fills (READ-ONLY)
  automation/state/core-decisions.jsonl      -- per-minute SPY/VIX tape (READ-ONLY)
  automation/state/fleet/<arm>/decisions.jsonl -- per-tick equity (READ-ONLY)
  analysis/journal/calendar-data.json        -- daily net P&L per account (fee-adjusted)
  analysis/quote-tape/2026-09-03.jsonl       -- today's option NBBO tape (READ-ONLY)
  automation/state/key-levels.json + key-levels-history/2026-09-03/0930.json -- zone widths
  backtest/data/spy_sip_cache/spy_1m_*.json  -- historical SPY 1-min bars
  backtest/data/highres/SPY*C*_1m_*.csv      -- historical option 1-min bars
"""
import json, math, random, statistics, re, glob
from collections import defaultdict, Counter
from datetime import datetime, timedelta

random.seed(20260903)
REPO = "C:/Users/jackw/Desktop/42"

def rp(*parts):
    return "/".join([REPO] + list(parts))

# ===========================================================================
# 1. LOAD & PREP
# ===========================================================================
with open(rp("analysis", "pain-ledger", "mae-mfe.json"), encoding="utf-8") as f:
    LEDGER = json.load(f)
ALL_TRADES = LEDGER["trades"]
SINCE = "2026-08-06"
TRADES = [t for t in ALL_TRADES if t["date"] >= SINCE]

for t in TRADES:
    notional = t["entry_price"] * t["qty"] * 100.0
    t["_notional"] = notional
    t["_exit_pct"] = (t["realized_pnl"] / notional) if notional else 0.0

LOSERS = [t for t in TRADES if t["outcome"] == "loser"]

# ---------------------------------------------------------------------------
# 1a. Equity by arm+date
# ---------------------------------------------------------------------------
def fleet_equity_by_date(arm):
    path = rp("automation", "state", "fleet", arm, "decisions.jsonl")
    first_eq, last_eq = {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("ts_et")
            eq = r.get("equity")
            if not ts or eq is None:
                continue
            date = ts[:10]
            if date not in first_eq:
                first_eq[date] = eq
            last_eq[date] = eq
    return first_eq, last_eq

equity_by_arm_date = {}
equity_source_note = {}
for arm in ["risky-1", "risky-3", "safe-3"]:
    first_eq, last_eq = fleet_equity_by_date(arm)
    equity_by_arm_date[arm] = dict(first_eq)
    equity_source_note[arm] = "fleet decisions.jsonl, first equity row per ET date (direct, ground truth)"
    if arm == "risky-3":
        # outage: decisions.jsonl goes dark after 2026-08-28 (per memory:
        # project_quiet_hold_eats_nightly_tasks_2026_09_02). Forward-fill SOD
        # equity for later dates via cumulative realized_pnl from mae-mfe.json
        # trades for this arm, anchored at the last known real equity value.
        dates_known = sorted(first_eq.keys())
        last_known_date = dates_known[-1] if dates_known else None
        last_known_eq = last_eq.get(last_known_date) if last_known_date else None
        equity_source_note["risky-3"] += (
            f" -- OUTAGE: file stops {last_known_date} 15:54 ET (confirmed via tail read). "
            f"Dates after {last_known_date} forward-filled from cumulative realized_pnl "
            f"(mae-mfe.json, arm==risky-3) anchored at last known equity ${last_known_eq}. "
            "APPROXIMATE for those dates; disclosed per row."
        )
        if last_known_date and last_known_eq is not None:
            rt_after = sorted(
                [t for t in ALL_TRADES if t["arm"] == "risky-3" and t["date"] > last_known_date],
                key=lambda t: t["date"],
            )
            running = last_known_eq
            by_date_pnl = defaultdict(float)
            for t in rt_after:
                by_date_pnl[t["date"]] += t["realized_pnl"]
            for d in sorted(by_date_pnl.keys()):
                equity_by_arm_date["risky-3"][d] = running  # SOD equity for date d
                running += by_date_pnl[d]

# safe-2 / bold-2: no equity field in core-decisions.jsonl -- reconstruct
# backward from the 2026-09-03 SOD anchor (HARD CONSTRAINTS) via
# calendar-data.json's fee-adjusted daily net P&L. Valid because 0DTE closes
# flat every day (no overnight equity change), so SOD(d_next) = SOD(d) + pnl_net(d).
with open(rp("analysis", "journal", "calendar-data.json"), encoding="utf-8") as f:
    CAL = json.load(f)

ANCHOR_SOD_09_03 = {"safe-2": 5653.81, "bold-2": 5593.52, "safe-3": 5639.10, "risky-1": 6149.12}

for arm in ["safe-2", "bold-2"]:
    days = CAL["views"][arm]["days"]
    dates_sorted = sorted(days.keys())
    eq = {}
    running = ANCHOR_SOD_09_03[arm]
    eq[dates_sorted[-1]] = running  # 09-03 SOD = given anchor
    for d in reversed(dates_sorted[:-1]):
        # SOD(d) = SOD(d_next_in_view) - pnl_net(d_next_in_view)... walk correctly:
        pass
    # correct backward walk: iterate from last to first, next_date's SOD known
    for i in range(len(dates_sorted) - 1, 0, -1):
        d_next = dates_sorted[i]
        d_cur = dates_sorted[i - 1]
        pnl_next = days[d_next]["pnl_net"]
        eq[d_cur] = eq[d_next] - pnl_next
    equity_by_arm_date[arm] = eq
    equity_source_note[arm] = (
        "RECONSTRUCTED: backward walk from 2026-09-03 SOD anchor (HARD CONSTRAINTS) using "
        "analysis/journal/calendar-data.json daily pnl_net (fee-adjusted); valid because 0DTE "
        "closes flat every session (no overnight equity carry). Gaps (no-trade dates) contribute "
        "$0 and are skipped; SOD equity for a gap date equals the prior trading date's close. "
        "Cross-check: reconstructed 09-03 SOD used the given anchor directly, not derived."
    )

def sod_equity(arm, date):
    d = equity_by_arm_date.get(arm, {})
    if date in d:
        return d[date], "exact"
    # fallback: nearest known date on/before
    known = sorted(k for k in d.keys() if k <= date)
    if known:
        return d[known[-1]], "carried_fwd_from_" + known[-1]
    known_after = sorted(k for k in d.keys() if k > date)
    if known_after:
        return d[known_after[0]], "carried_back_from_" + known_after[0]
    return None, "no_data"

# annotate trades with equity + pct_of_equity
for t in TRADES:
    eq, eq_flag = sod_equity(t["arm"], t["date"])
    t["_sod_equity"] = eq
    t["_eq_flag"] = eq_flag
    t["_pct_equity"] = (t["realized_pnl"] / eq * 100.0) if eq else None

print("=== 1. DATA LOADED ===")
print(f"n trades since {SINCE}: {len(TRADES)}, n losers: {len(LOSERS)}")
print("equity coverage:", Counter(t["_eq_flag"] for t in TRADES))

# ===========================================================================
# 2. LOSS DISTRIBUTION -- three units, per arm + book-wide
# ===========================================================================
def pctile(sorted_vals, p):
    if not sorted_vals:
        return None
    n = len(sorted_vals)
    idx = p / 100.0 * (n - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])

def dist_summary(vals):
    if not vals:
        return None
    sv = sorted(vals)
    return {
        "n": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "stdev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
        "min": sv[0],
        "p10": pctile(sv, 10),
        "p25": pctile(sv, 25),
        "p75": pctile(sv, 75),
        "p90": pctile(sv, 90),
        "p95": pctile(sv, 95),
        "max": sv[-1],
    }

def bootstrap_ci_mean(values, n_resamples=3000):
    if not values:
        return (None, None, None)
    n = len(values)
    boots = []
    for _ in range(n_resamples):
        sample = [values[random.randrange(n)] for _ in range(n)]
        boots.append(statistics.mean(sample))
    boots.sort()
    lo = boots[int(0.025 * n_resamples)]
    hi = boots[int(0.975 * n_resamples) - 1]
    return (statistics.mean(values), lo, hi)

ARMS = sorted({t["arm"] for t in LOSERS})
loss_dist_by_arm = {}
for arm in ARMS:
    arm_losers = [t for t in LOSERS if t["arm"] == arm]
    dollars = [t["realized_pnl"] for t in arm_losers]
    pct_prem = [t["_exit_pct"] * 100.0 for t in arm_losers]
    pct_eq = [t["_pct_equity"] for t in arm_losers if t["_pct_equity"] is not None]
    ci_d = bootstrap_ci_mean(dollars)
    ci_pp = bootstrap_ci_mean(pct_prem)
    ci_pe = bootstrap_ci_mean(pct_eq)
    loss_dist_by_arm[arm] = {
        "n": len(arm_losers),
        "dollars": dist_summary(dollars),
        "dollars_mean_ci": {"point": ci_d[0], "lo": ci_d[1], "hi": ci_d[2]},
        "pct_premium": dist_summary(pct_prem),
        "pct_premium_mean_ci": {"point": ci_pp[0], "lo": ci_pp[1], "hi": ci_pp[2]},
        "pct_equity": dist_summary(pct_eq),
        "pct_equity_mean_ci": {"point": ci_pe[0], "lo": ci_pe[1], "hi": ci_pe[2]},
    }

book_dollars = [t["realized_pnl"] for t in LOSERS]
book_pct_prem = [t["_exit_pct"] * 100.0 for t in LOSERS]
book_pct_eq = [t["_pct_equity"] for t in LOSERS if t["_pct_equity"] is not None]
loss_dist_book = {
    "n": len(LOSERS),
    "dollars": dist_summary(book_dollars),
    "pct_premium": dist_summary(book_pct_prem),
    "pct_equity": dist_summary(book_pct_eq),
}

print("\n=== 2. LOSS DISTRIBUTION SINCE 2026-08-06 ===")
print("BOOK n=%d  $ mean=%.2f median=%.2f p90=%.2f  |  premium%% mean=%.1f median=%.1f  |  equity%% mean=%.3f median=%.3f" % (
    loss_dist_book["n"], loss_dist_book["dollars"]["mean"], loss_dist_book["dollars"]["median"], loss_dist_book["dollars"]["p90"],
    loss_dist_book["pct_premium"]["mean"], loss_dist_book["pct_premium"]["median"],
    loss_dist_book["pct_equity"]["mean"], loss_dist_book["pct_equity"]["median"],
))
for arm in ARMS:
    d = loss_dist_by_arm[arm]
    print("%-10s n=%3d  $ mean=%8.2f median=%8.2f p90=%8.2f  |  prem%% mean=%6.1f median=%6.1f  |  eq%% mean=%6.3f median=%6.3f" % (
        arm, d["n"], d["dollars"]["mean"], d["dollars"]["median"], d["dollars"]["p90"],
        d["pct_premium"]["mean"], d["pct_premium"]["median"],
        d["pct_equity"]["mean"], d["pct_equity"]["median"],
    ))

# ===========================================================================
# 3. TODAY'S 8 LOSING LEGS -- placed on the PRIOR (before 09-03) loss distribution
# ===========================================================================
TODAY = "2026-09-03"
# Reconstructed directly from fills-ledger.jsonl (verified against
# analysis/journal/calendar-data.json trades for safe-2 -- exact match).
TODAY_LOSING_LEGS = [
    # (arm, symbol, wave, buy_ts, buy_qty, buy_px, sell_ts, sell_qty, sell_px)
    ("bold-2",  "770903C772", "wave1", "09:42:06", 5, 0.37, "09:58:04", 5, 0.20),
    ("safe-3",  "770903C770", "wave1", "09:42:06", 5, 1.11, "10:01:06", 5, 0.57),
    ("risky-1", "770903C770", "wave1", "09:42:08", 5, 1.08, "10:02:07", 5, 0.52),
    ("safe-2",  "770903C770", "wave1", "09:41:04", 3, 0.98, "10:03:03", 3, 0.50),
    ("bold-2",  "770903C770", "wave2", "10:16:08", 5, 0.48, "10:36:05", 5, 0.34),
    ("safe-2",  "770903C768", "wave2", "10:16:25", 3, 1.40, "10:36:04", 3, 1.18),
    ("safe-3",  "770903C768", "wave2", "10:17:07", 5, 1.31, "10:37:06", 5, 1.18),
    ("risky-1", "770903C768", "wave2", "10:17:09", 5, 1.31, "10:37:07", 5, 1.18),
]

today_legs = []
for arm, sym, wave, bts, bq, bpx, sts, sq, spx in TODAY_LOSING_LEGS:
    dollars = round((spx - bpx) * bq * 100.0, 2)
    pct_prem = (spx / bpx - 1.0) * 100.0
    eq, eq_flag = sod_equity(arm, TODAY)
    pct_eq = (dollars / eq * 100.0) if eq else None
    today_legs.append({
        "arm": arm, "symbol": sym, "wave": wave,
        "buy_ts_et": bts, "buy_qty": bq, "buy_px": bpx,
        "sell_ts_et": sts, "sell_qty": sq, "sell_px": spx,
        "dollars": dollars, "pct_premium": pct_prem,
        "sod_equity": eq, "pct_equity": pct_eq,
    })

TOTAL_TODAY_LOSS = sum(l["dollars"] for l in today_legs)
print("\n=== 3. TODAY'S 8 LOSING LEGS ===")
print(f"Total: ${TOTAL_TODAY_LOSS:.2f} across {len(today_legs)} legs")

def percentile_rank(value, population):
    # population = list of realized losses (negative numbers), value negative.
    # SEVERITY percentile: 100 = the single most severe (most negative) loss
    # in the population, 0 = the mildest. i.e. "Nth percentile" = worse than
    # N% of the comparison population. Mid-rank on ties.
    if not population:
        return None
    n = len(population)
    less_severe = sum(1 for x in population if x > value)
    equal = sum(1 for x in population if x == value)
    return 100.0 * (less_severe + 0.5 * equal) / n

for leg in today_legs:
    arm = leg["arm"]
    prior_arm_losers = [t for t in LOSERS if t["arm"] == arm and t["date"] < TODAY]
    prior_book_losers = [t for t in LOSERS if t["date"] < TODAY]
    d_pop = [t["realized_pnl"] for t in prior_arm_losers]
    pp_pop = [t["_exit_pct"] * 100.0 for t in prior_arm_losers]
    pe_pop = [t["_pct_equity"] for t in prior_arm_losers if t["_pct_equity"] is not None]
    d_pop_book = [t["realized_pnl"] for t in prior_book_losers]

    leg["arm_prior_n"] = len(prior_arm_losers)
    leg["pctile_dollars_in_arm"] = percentile_rank(leg["dollars"], d_pop)
    leg["pctile_pct_premium_in_arm"] = percentile_rank(leg["pct_premium"], pp_pop)
    leg["pctile_pct_equity_in_arm"] = percentile_rank(leg["pct_equity"], pe_pop) if leg["pct_equity"] is not None else None
    leg["pctile_dollars_in_book"] = percentile_rank(leg["dollars"], d_pop_book)

    print(f"{arm:9s} {leg['wave']:5s} ${leg['dollars']:7.2f} ({leg['pct_premium']:6.1f}% prem, {leg['pct_equity']:.3f}% eq)  "
          f"-> arm pctile: $={leg['pctile_dollars_in_arm']:.0f} prem%={leg['pctile_pct_premium_in_arm']:.0f} eq%={leg['pctile_pct_equity_in_arm']:.0f}  "
          f"(n_prior={leg['arm_prior_n']})  book$ pctile={leg['pctile_dollars_in_book']:.0f}")

# ===========================================================================
# 4. MECHANISM -- delta / SPY-points translation of the -50% cap
# ===========================================================================

# ---- 4a. Today's SPY + VIX per-minute tape (core-decisions.jsonl, account=='safe') ----
spy_by_ts_today = {}
vix_by_ts_today = {}
with open(rp("automation", "state", "core-decisions.jsonl"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        ts = r.get("ts_et", "")
        if not ts.startswith(TODAY) or r.get("account") != "safe":
            continue
        if r.get("spy") is not None:
            spy_by_ts_today[ts[11:16]] = r["spy"]
        if r.get("vix") is not None:
            vix_by_ts_today[ts[11:16]] = r["vix"]

def spy_at(hhmm):
    return spy_by_ts_today.get(hhmm)

def vix_at(hhmm):
    return vix_by_ts_today.get(hhmm)

# ---- 4b. Black-Scholes delta proxy (disclosed APPROXIMATE per task's documented proxy method) ----
def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bs_call_delta(S, K, sigma, T_years, r=0.0):
    if T_years <= 0 or sigma <= 0:
        return 1.0 if S > K else (0.0 if S < K else 0.5)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T_years) / (sigma * math.sqrt(T_years))
    return norm_cdf(d1)

def minutes_to_close(hhmm):
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    mins_now = h * 60 + m
    mins_close = 16 * 60
    return max(mins_close - mins_now, 1)

def t_years_intraday(hhmm):
    # trading-minutes-in-a-year convention: 390 min/day * 252 days/yr
    return minutes_to_close(hhmm) / (390.0 * 252.0)

# ---- 4c. Empirical delta from TODAY's quote tape vs SPY tape ----
qt_rows = []
with open(rp("analysis", "quote-tape", "2026-09-03.jsonl"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        qt_rows.append(json.loads(line))

def quote_series(symbol, arm=None):
    rows = [r for r in qt_rows if r["symbol"] == symbol and (arm is None or r["arm"] == arm)]
    rows.sort(key=lambda r: r["ts_et"])
    out = []
    for r in rows:
        hhmm = r["ts_et"][11:16]
        spy = spy_at(hhmm)
        if spy is not None:
            out.append((r["ts_et"], hhmm, r["mid"], spy))
    return out

def empirical_delta(symbol, arm, t_start, t_end):
    """OLS slope of option-mid vs SPY over [t_start,t_end] (HH:MM strings)."""
    series = [row for row in quote_series(symbol, arm) if t_start <= row[1] <= t_end]
    # dedupe by (hhmm) keeping first
    seen = {}
    for ts, hhmm, mid, spy in series:
        if hhmm not in seen:
            seen[hhmm] = (mid, spy)
    pts = sorted(seen.items())
    if len(pts) < 3:
        return None, len(pts), pts
    xs = [spy for _, (mid, spy) in pts]
    ys = [mid for _, (mid, spy) in pts]
    n = len(xs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    slope = (num / den) if den else None
    return slope, n, pts

print("\n=== 4. MECHANISM: delta / SPY-points translation ===")
print("-- 4c. Empirical delta from today's quote-tape vs SPY tape --")
wave1_delta, w1n, w1pts = empirical_delta("SPY260903C00770000", "safe-2", "09:41", "10:03")
print(f"wave1 770C (safe-2 tape) OLS slope (d(mid)/d(SPY)): {wave1_delta} (n={w1n} distinct minutes)")
print("  raw points:", w1pts)
wave2_delta, w2n, w2pts = empirical_delta("SPY260903C00768000", "safe-2", "10:16", "10:37")
print(f"wave2 768C (safe-2 tape) OLS slope: {wave2_delta} (n={w2n})")
print("  raw points:", w2pts)

print("\n  CAVEAT: today's core-decisions 'spy' field is a 5-min-bar-close series")
print("  repeated across the per-minute log (confirmed: 5 consecutive identical")
print("  values e.g. 769.79 at 09:46-09:50) while option mid genuinely moves")
print("  0.705-1.125 within that same repeated-SPY window -- the OLS slope above")
print("  is NOT a valid delta measurement, it is dominated by real intra-bar SPY")
print("  moves the coarse tape cannot see (plus bid/ask bounce). Disclosed as")
print("  UNRELIABLE; BS proxy + historical 1-min regression are the trusted reads.")

# ---- 4d. BS delta at each leg's entry tick ----
print("\n-- 4d. BS delta at entry (r=0, sigma=VIX/100, T=intraday convention) --")
for arm, sym, wave, bts, bq, bpx, sts, sq, spx in TODAY_LOSING_LEGS:
    strike = float(sym.split("C")[1]) if "C" in sym else float(sym.split("P")[1])
    hhmm = bts[:5]
    S = spy_at(hhmm)
    V = vix_at(hhmm)
    if S is None or V is None:
        print(f"  {arm} {wave} {sym}: no spot/vix at {hhmm}")
        continue
    T = t_years_intraday(hhmm)
    delta = bs_call_delta(S, strike, V / 100.0, T)
    spy_pts_for_cap = 0.5 * bpx / delta if delta > 0 else None
    print(f"  {arm:9s} {wave:5s} K={strike:.0f} entry {hhmm} S={S:.2f} VIX={V:.2f} T_yr={T:.5f}  "
          f"BS_delta={delta:.3f}  -> -50%cap implies SPY move of {spy_pts_for_cap:.3f} pts")

# ---- 4e. Decompose: how much of the collapse does BS (delta+theta, using the
#      tape-visible SPY move) explain, vs an unexplained residual (intra-bar
#      SPY move invisible at 5-min resolution, and/or IV change)? ----
def bs_call_price(S, K, sigma, T_years, r=0.0):
    if T_years <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T_years) / (sigma * math.sqrt(T_years))
    d2 = d1 - sigma * math.sqrt(T_years)
    return S * norm_cdf(d1) - K * math.exp(-r * T_years) * norm_cdf(d2)

print("\n-- 4e. BS decomposition: delta+theta (tape-visible SPY move) vs unexplained residual --")
decomp_rows = []
for arm, sym, wave, bts, bq, bpx, sts, sq, spx in TODAY_LOSING_LEGS:
    strike = float(sym.split("C")[1]) if "C" in sym else float(sym.split("P")[1])
    hhmm_b, hhmm_s = bts[:5], sts[:5]
    S_b, S_s = spy_at(hhmm_b), spy_at(hhmm_s)
    V_b, V_s = vix_at(hhmm_b), vix_at(hhmm_s)
    if None in (S_b, S_s, V_b, V_s):
        continue
    T_b, T_s = t_years_intraday(hhmm_b), t_years_intraday(hhmm_s)
    bs_entry = bs_call_price(S_b, strike, V_b / 100.0, T_b)
    bs_exit_tapevisible = bs_call_price(S_s, strike, V_b / 100.0, T_s)  # sigma held at entry VIX
    explained = bs_exit_tapevisible - bs_entry  # $ per share, from tape-visible S move + theta
    actual_move = spx - bpx
    residual = actual_move - explained
    decomp_rows.append({
        "arm": arm, "wave": wave, "symbol": sym,
        "bs_price_at_entry": bs_entry, "real_entry_px": bpx,
        "spy_move_tape_pts": S_s - S_b,
        "bs_explained_move": explained, "actual_move": actual_move,
        "residual_unexplained": residual,
        "pct_of_move_explained_by_tape_delta_theta": (explained / actual_move * 100.0) if actual_move else None,
    })
    print(f"  {arm:9s} {wave:5s} SPYtape_move={S_s-S_b:+.3f}pt  BS_entry_px={bs_entry:.3f} (real={bpx:.2f})  "
          f"BS_explained_Dpremium={explained:+.3f}  actual_Dpremium={actual_move:+.3f}  "
          f"residual(unexplained)={residual:+.3f}  explained%={(explained/actual_move*100 if actual_move else float('nan')):.0f}%")

# ---- 4f. VIX/100 badly overprices 0DTE (BS_entry_px >> real entry premium above) --
#      solve implied sigma from the REAL entry premium instead (bisection),
#      then recompute delta at that implied sigma -- a much better-calibrated read.
def implied_vol_call(real_price, S, K, T_years, r=0.0, lo=0.001, hi=3.0, iters=60):
    if real_price <= max(S - K, 0.0):
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        px = bs_call_price(S, K, mid, T_years, r)
        if px > real_price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0

print("\n-- 4f. Implied vol (from real entry premium) vs VIX, and re-derived delta --")
iv_rows = []
for arm, sym, wave, bts, bq, bpx, sts, sq, spx in TODAY_LOSING_LEGS:
    strike = float(sym.split("C")[1]) if "C" in sym else float(sym.split("P")[1])
    hhmm = bts[:5]
    S = spy_at(hhmm)
    V = vix_at(hhmm)
    if S is None or V is None:
        continue
    T = t_years_intraday(hhmm)
    iv = implied_vol_call(bpx, S, strike, T)
    if iv is None:
        print(f"  {arm} {wave}: entry premium {bpx} <= intrinsic, cannot invert")
        continue
    delta_iv = bs_call_delta(S, strike, iv, T)
    spy_pts_cap_iv = 0.5 * bpx / delta_iv if delta_iv > 0 else None
    iv_rows.append({"arm": arm, "wave": wave, "symbol": sym, "implied_vol_pct": iv * 100,
                     "vix_pct": V, "delta_implied": delta_iv, "spy_pts_for_cap_implied": spy_pts_cap_iv})
    print(f"  {arm:9s} {wave:5s} K={strike:.0f}  implied_vol={iv*100:5.1f}%  (VIX={V:.1f}%)  "
          f"delta_iv={delta_iv:.3f}  -> -50%cap implies SPY move of {spy_pts_cap_iv:.3f} pts")

# ---- 4g. Historical empirical delta: near-ATM calls, cached 1-min option bars
#      vs cached SPY 1-min bars, window 09:40-10:20, dates since 2026-08-06 ----
print("\n-- 4g. Historical empirical delta (cached 1-min bars, 09:40-10:20, since 08-06) --")

def load_spy_1m(date):
    path = rp("backtest", "data", "spy_sip_cache", f"spy_1m_{date}.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return {}
    out = {}
    for b in d["bars"]:
        hhmm = b["t"][11:16]
        out[hhmm] = b["c"]
    return out

def load_option_1m(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 6:
                continue
            ts = parts[0]
            hhmm = ts[11:16]
            close = float(parts[4])
            out[hhmm] = close
    return out

highres_call_files = glob.glob(rp("backtest", "data", "highres", "SPY26*C*_1m_2026-*.csv"))
by_date_files = defaultdict(list)
for fpath in highres_call_files:
    m = re.search(r"SPY26(\d{2})(\d{2})(\d{2})C(\d{8})_1m_(\d{4}-\d{2}-\d{2})\.csv", os.path.basename(fpath) if False else fpath)
    m = re.search(r"SPY(\d{6})C(\d{8})_1m_(\d{4}-\d{2}-\d{2})\.csv", fpath)
    if not m:
        continue
    strike = int(m.group(2)) / 1000.0
    date = m.group(3)
    if date < SINCE:
        continue
    by_date_files[date].append((strike, fpath))

hist_deltas = []
for date in sorted(by_date_files.keys()):
    spy1m = load_spy_1m(date)
    if not spy1m:
        continue
    s0940 = spy1m.get("09:40")
    if s0940 is None:
        continue
    # nearest-strike call file to spot at 09:40 (near-ATM)
    strikes_files = by_date_files[date]
    nearest = min(strikes_files, key=lambda sf: abs(sf[0] - s0940))
    strike, fpath = nearest
    if abs(strike - s0940) > 3.0:
        continue  # not near-ATM enough
    opt1m = load_option_1m(fpath)
    pts = []
    for hhmm in sorted(opt1m.keys()):
        if "09:40" <= hhmm <= "10:20" and hhmm in spy1m:
            pts.append((spy1m[hhmm], opt1m[hhmm]))
    if len(pts) < 10:
        continue
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(xs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        continue
    slope = num / den
    r2_num = num * num
    r2_den = den * sum((y - my) ** 2 for y in ys)
    r2 = (r2_num / r2_den) if r2_den else None
    hist_deltas.append({"date": date, "strike": strike, "spot_0940": s0940,
                         "n_pts": n, "delta_slope": slope, "r2": r2})
    print(f"  {date}  K={strike:.0f} (spot@09:40={s0940:.2f}, {strike-s0940:+.2f} OTM)  "
          f"n={n}  delta_slope={slope:.3f}  R2={r2:.3f}" if r2 is not None else
          f"  {date}  K={strike:.0f}  n={n}  delta_slope={slope:.3f}")

if hist_deltas:
    slopes = [h["delta_slope"] for h in hist_deltas]
    print(f"\n  n_days={len(slopes)}  mean_delta={statistics.mean(slopes):.3f}  "
          f"median_delta={statistics.median(slopes):.3f}  stdev={statistics.stdev(slopes) if len(slopes)>1 else 0:.3f}")

# ---- 4h. Clean decomposition using IMPLIED vol (calibrated to real entry price):
#      actual move = theta_effect + tape_visible_delta_effect + residual
#      (residual = real intra-bar SPY move invisible at 5-min resolution +
#       IV change over the hold + fill/spread noise -- cannot be separated
#       further without tick SPY data, which this task does not permit fetching)
print("\n-- 4h. Clean decomposition (implied-vol calibrated): theta vs tape-delta vs residual --")
decomp2 = []
for arm, sym, wave, bts, bq, bpx, sts, sq, spx in TODAY_LOSING_LEGS:
    strike = float(sym.split("C")[1]) if "C" in sym else float(sym.split("P")[1])
    hhmm_b, hhmm_s = bts[:5], sts[:5]
    S_b, S_s = spy_at(hhmm_b), spy_at(hhmm_s)
    if None in (S_b, S_s):
        continue
    T_b, T_s = t_years_intraday(hhmm_b), t_years_intraday(hhmm_s)
    iv = implied_vol_call(bpx, S_b, strike, T_b)
    if iv is None:
        continue
    theta_only_px = bs_call_price(S_b, strike, iv, T_s)       # spot fixed, time advances
    tape_px = bs_call_price(S_s, strike, iv, T_s)              # tape SPY move + time
    theta_effect = theta_only_px - bpx
    delta_effect = tape_px - theta_only_px
    residual = spx - tape_px
    actual_move = spx - bpx
    decomp2.append({
        "arm": arm, "wave": wave, "symbol": sym, "implied_vol_pct": iv * 100,
        "theta_effect": theta_effect, "tape_delta_effect": delta_effect,
        "residual": residual, "actual_move": actual_move,
    })
    print(f"  {arm:9s} {wave:5s}  theta={theta_effect:+.3f}  tape_delta={delta_effect:+.3f}  "
          f"residual={residual:+.3f}  |  actual={actual_move:+.3f}  "
          f"(theta {theta_effect/actual_move*100:.0f}% / tape_delta {delta_effect/actual_move*100:.0f}% / "
          f"residual {residual/actual_move*100:.0f}%)")

if decomp2:
    tot_theta = sum(d["theta_effect"] for d in decomp2)
    tot_delta = sum(d["tape_delta_effect"] for d in decomp2)
    tot_resid = sum(d["residual"] for d in decomp2)
    tot_actual = sum(d["actual_move"] for d in decomp2)
    print(f"\n  POOLED (n={len(decomp2)}): theta={tot_theta:+.3f} ({tot_theta/tot_actual*100:.0f}%)  "
          f"tape_delta={tot_delta:+.3f} ({tot_delta/tot_actual*100:.0f}%)  "
          f"residual={tot_resid:+.3f} ({tot_resid/tot_actual*100:.0f}%)  actual={tot_actual:+.3f}")

# ===========================================================================
# 4i. Typical 10-minute SPY noise (first hour), from cached 1-min bars, since 08-06
# ===========================================================================
print("\n-- 4i. Typical 10-min SPY range (09:30-10:30), 1-min bars, since 08-06 --")
spy_cache_dates = sorted(
    re.search(r"spy_1m_(\d{4}-\d{2}-\d{2})\.json", f).group(1)
    for f in glob.glob(rp("backtest", "data", "spy_sip_cache", "spy_1m_2026-*.json"))
    if re.search(r"spy_1m_(\d{4}-\d{2}-\d{2})\.json", f).group(1) >= SINCE
)
ten_min_ranges = []
for date in spy_cache_dates:
    bars = load_spy_1m(date)
    # rebuild ordered list restricted to 09:30-10:30
    ordered = sorted([(hhmm, px) for hhmm, px in bars.items() if "09:30" <= hhmm <= "10:30"])
    if len(ordered) < 10:
        continue
    prices = [p for _, p in ordered]
    for i in range(len(prices) - 9):
        window = prices[i:i + 10]
        rng = max(window) - min(window)
        ten_min_ranges.append(rng)

if ten_min_ranges:
    ten_min_ranges_sorted = sorted(ten_min_ranges)
    print(f"  n_windows={len(ten_min_ranges)} across {len(spy_cache_dates)} days")
    print(f"  mean={statistics.mean(ten_min_ranges):.3f}  median={statistics.median(ten_min_ranges):.3f}  "
          f"p25={pctile(ten_min_ranges_sorted,25):.3f}  p75={pctile(ten_min_ranges_sorted,75):.3f}  "
          f"p90={pctile(ten_min_ranges_sorted,90):.3f}  max={ten_min_ranges_sorted[-1]:.3f}")

# 5-min bar ATR-14-style: average true range of 5m bars in first hour
print("\n-- 4i-b. 5-min bar range (09:30-10:30), since 08-06 --")
five_min_ranges = []
for date in spy_cache_dates:
    path = rp("backtest", "data", "spy_sip_cache", f"spy_5m_{date}.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        continue
    for b in d["bars"]:
        hhmm = b["t"][11:16]
        if "09:30" <= hhmm <= "10:30":
            five_min_ranges.append(b["h"] - b["l"])

if five_min_ranges:
    fsorted = sorted(five_min_ranges)
    print(f"  n_bars={len(five_min_ranges)}  mean_range={statistics.mean(five_min_ranges):.3f}  "
          f"median={statistics.median(five_min_ranges):.3f}  p75={pctile(fsorted,75):.3f}  p90={pctile(fsorted,90):.3f}")

# today's actual: wave1 09:41-10:03 (22min), wave2 10:16-10:37 (21min), from the
# 5-min-repeated tape (best available -- likely UNDERSTATES real intraminute range)
print("\n-- 4i-c. TODAY's actual tape-visible range during wave1 / wave2 holds (likely understated) --")
w1_prices = [spy_by_ts_today[h] for h in spy_by_ts_today if "09:41" <= h <= "10:03"]
w2_prices = [spy_by_ts_today[h] for h in spy_by_ts_today if "10:16" <= h <= "10:37"]
print(f"  wave1 (09:41-10:03): min={min(w1_prices):.2f} max={max(w1_prices):.2f} range={max(w1_prices)-min(w1_prices):.3f} net={w1_prices[-1]-w1_prices[0]:+.3f}")
print(f"  wave2 (10:16-10:37): min={min(w2_prices):.2f} max={max(w2_prices):.2f} range={max(w2_prices)-min(w2_prices):.3f} net={w2_prices[-1]-w2_prices[0]:+.3f}")

# ===========================================================================
# 5. ALTERNATIVE (i): smaller size + wider premium stop, same $ risk
#    (min 3 contracts = TP1 2 + runner 1, per Rule 6)
# ===========================================================================
print("\n=== 5. ALTERNATIVE (i): smaller size + wider cap (-70%/-80%), same $ risk ===")

CURRENT_50_COHORT = [t for t in TRADES if t["stop"]["premium_stop_pct"] == -0.5]
FLOOR = 3
REDUCIBLE = [t for t in CURRENT_50_COHORT if t["qty"] > FLOOR]
AT_FLOOR = [t for t in CURRENT_50_COHORT if t["qty"] <= FLOOR]
print(f"current -50% cohort since {SINCE}: n={len(CURRENT_50_COHORT)}  "
      f"reducible (qty>{FLOOR}): n={len(REDUCIBLE)}  already-at-floor (qty<={FLOOR}): n={len(AT_FLOOR)}")
print(f"  -> alternative (i) has NO room on {len(AT_FLOOR)}/{len(CURRENT_50_COHORT)} "
      f"({len(AT_FLOOR)/len(CURRENT_50_COHORT)*100:.0f}%) of this cohort's trades without "
      f"accepting MORE $ risk than today (they're already at the rule-6 floor). "
      f"Every one of today's wave1/wave2 safe-2 legs (qty=3) is in this floor cohort.")

def classify_stage2(t):
    if t["outcome"] == "scratch":
        return "scratch"
    if t["outcome"] == "winner":
        return "winner"
    # loser
    if t["_exit_pct"] <= -0.45:
        return "cap_hit"
    return "structure_or_time_loss"

for t in REDUCIBLE:
    t["_stage2"] = classify_stage2(t)

stage2_counts = Counter(t["_stage2"] for t in REDUCIBLE)
print("  REDUCIBLE population by stage:", dict(stage2_counts))

def counterfactual_alt_i(t, cap_c, floor=FLOOR):
    """cap_c: positive fraction e.g. 0.70 or 0.80. Returns (pnl, note)."""
    scale = floor / t["qty"]
    if t["_stage2"] == "cap_hit":
        # RIGHT-CENSORED: real trade stopped observing bars once it hit -50%.
        # We do NOT know what a -70%/-80% cap would have done. Conservative/
        # neutral assumption: dollar-per-contract outcome unchanged, scaled
        # only by size. Explicitly flagged, not a modeled counterfactual.
        return t["realized_pnl"] * scale, "UNKNOWN_censored_size_only"
    # winner / structure_or_time_loss: real window is uncensored past -50%
    # (by construction -- these never hit the real cap), so mae_pct reflects
    # the true worst point reached before the REAL exit. Valid, non-look-ahead
    # counterfactual test (same logic as H8's tightening sweep, applied wider).
    if t.get("mae_before_first_exit") and t["mae_pct"] <= -cap_c:
        notional_new = t["entry_price"] * floor * 100.0
        return notional_new * (-cap_c), "would_have_capped_wider"
    return t["realized_pnl"] * scale, "unaffected_size_only"

for cap_c in [0.70, 0.80]:
    rows = [(t, *counterfactual_alt_i(t, cap_c)) for t in REDUCIBLE]
    total_actual = sum(t["realized_pnl"] for t in REDUCIBLE)
    total_cf = sum(pnl for _, pnl, _ in rows)
    total_at_floor_actual = sum(t["realized_pnl"] * (FLOOR / t["qty"]) for t in REDUCIBLE)  # size-only baseline
    n_censored = sum(1 for _, _, note in rows if note == "UNKNOWN_censored_size_only")
    n_wider_cap_hit = sum(1 for _, _, note in rows if note == "would_have_capped_wider")
    cf_vals = [pnl for _, pnl, _ in rows]
    ci = bootstrap_ci_mean(cf_vals)
    total_ci_lo = ci[1] * len(cf_vals) if ci[1] is not None else None
    total_ci_hi = ci[2] * len(cf_vals) if ci[2] is not None else None
    print(f"\n  -- candidate cap -{cap_c*100:.0f}% at floor-{FLOOR} sizing --")
    print(f"     n={len(REDUCIBLE)}  n_censored(cap_hit, size-only assumption)={n_censored}  "
          f"n_newly_capped_wider(non-cap-hit trades that breach -{cap_c*100:.0f}%)={n_wider_cap_hit}")
    print(f"     TOTAL $ actual (full size)      = {total_actual:+.2f}")
    print(f"     TOTAL $ size-only (floor-3, same -50% cap) = {total_at_floor_actual:+.2f}")
    print(f"     TOTAL $ size-only + wider cap where computable = {total_cf:+.2f}  "
          f"95% CI [{total_ci_lo:+.2f}, {total_ci_hi:+.2f}]" if total_ci_lo is not None else "")

    # by arm
    by_arm_cf = defaultdict(list)
    for t, pnl, note in rows:
        by_arm_cf[t["arm"]].append(pnl)
    print("     by arm (size-only+wider-cap-where-computable):",
          {a: round(sum(v), 2) for a, v in sorted(by_arm_cf.items())})

    # 4 named winning days
    for wd in ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]:
        day_rows = [(t, pnl) for t, pnl, note in rows if t["date"] == wd]
        if not day_rows:
            continue
        day_actual = sum(t["realized_pnl"] for t, _ in day_rows)
        day_cf = sum(pnl for _, pnl in day_rows)
        print(f"     {wd}: n={len(day_rows)} actual={day_actual:+.2f} -> alt(i)={day_cf:+.2f}  delta={day_cf-day_actual:+.2f}")

    # drop-best-day (drop the date with the largest positive contribution to total_cf)
    by_date_cf = defaultdict(float)
    for t, pnl, note in rows:
        by_date_cf[t["date"]] += pnl
    if by_date_cf:
        best_date = max(by_date_cf, key=by_date_cf.get)
        total_cf_dropbest = total_cf - by_date_cf[best_date]
        print(f"     drop-best-day ({best_date}, contributed {by_date_cf[best_date]:+.2f}): "
              f"total_cf without it = {total_cf_dropbest:+.2f}")

print("\n  -- sanity check: qty by stage in REDUCIBLE population (does bigger size correlate with cap_hit?) --")
for stage in ["winner", "structure_or_time_loss", "cap_hit", "scratch"]:
    qtys = [t["qty"] for t in REDUCIBLE if t["_stage2"] == stage]
    if qtys:
        print(f"     {stage:24s} n={len(qtys):3d}  mean_qty={statistics.mean(qtys):.2f}  median_qty={statistics.median(qtys):.1f}  qty_dist={dict(Counter(qtys))}")

# ===========================================================================
# 6. ALTERNATIVE (ii): same size, zone-edge chart stop primary, cap as backstop
# ===========================================================================
print("\n=== 6. ALTERNATIVE (ii): zone-edge chart stop as primary (cap = backstop only) ===")
print("""
  BLOCKED for a full historical walker sweep: this repo's own ledger does not
  persist the zone_width actually in force at each historical trigger (this is
  the exact F3 gap named in this morning's SYNTHESIS.md -- "the true zone width
  in force on past triggers" -- not resolved here, not fabricated).
  What IS computable: (a) today's worked example with REAL zone widths + REAL
  SPY path (section 4), and (b) a population-level, disclosed-APPROXIMATE
  bound using the historically-measured delta (0.501, n=19 days, section 4g)
  to translate each historical loser's %-loss into an implied SPY-point move,
  bucketed against the two zone widths actually observed today (0.384, 0.80).
""")

DELTA_HIST = 0.501  # from 4g, n=19 days, R2 0.77-0.99
ZONE_NARROW = 0.384  # intraday-marker levels (PMH/PML/prior-day)
ZONE_WIDE = 0.80     # shelf levels

bucket_counts = Counter()
implied_moves = []
for t in LOSERS:
    implied_move = abs(t["_exit_pct"]) * t["entry_price"] / DELTA_HIST
    implied_moves.append(implied_move)
    if implied_move < ZONE_NARROW:
        bucket_counts["inside_narrow_zone_0.384"] += 1
    elif implied_move < ZONE_WIDE:
        bucket_counts["between_narrow_and_wide_zone"] += 1
    else:
        bucket_counts["exceeds_wide_zone_0.80"] += 1

n_loss = len(LOSERS)
print(f"  ALL {n_loss} losers since {SINCE}, delta-implied SPY move at exit vs today's two observed zone widths:")
for k in ["inside_narrow_zone_0.384", "between_narrow_and_wide_zone", "exceeds_wide_zone_0.80"]:
    c = bucket_counts[k]
    print(f"    {k:32s} n={c:3d}  ({c/n_loss*100:.0f}%)")
print(f"  median implied SPY move at exit = {statistics.median(implied_moves):.3f} pts  "
      f"(vs zone widths 0.384-0.80 in force today)")

# same, restricted to cap_hit trades only (the direct comparator to today's wave1)
CAP_HIT_POP = [t for t in CURRENT_50_COHORT if t["outcome"] == "loser" and t["_exit_pct"] <= -0.45]
bucket_counts_caphit = Counter()
for t in CAP_HIT_POP:
    implied_move = abs(t["_exit_pct"]) * t["entry_price"] / DELTA_HIST
    if implied_move < ZONE_NARROW:
        bucket_counts_caphit["inside_narrow_zone_0.384"] += 1
    elif implied_move < ZONE_WIDE:
        bucket_counts_caphit["between_narrow_and_wide_zone"] += 1
    else:
        bucket_counts_caphit["exceeds_wide_zone_0.80"] += 1
print(f"\n  CAP-HIT-ONLY subset (current -50% cohort, n={len(CAP_HIT_POP)}):")
for k in ["inside_narrow_zone_0.384", "between_narrow_and_wide_zone", "exceeds_wide_zone_0.80"]:
    c = bucket_counts_caphit[k]
    print(f"    {k:32s} n={c:3d}  ({c/len(CAP_HIT_POP)*100:.0f}%)" if CAP_HIT_POP else "")

# ===========================================================================
# 7. WRITE JSON companion
# ===========================================================================
out = {
    "meta": {
        "stamp_et": "2026-09-03T11:40",
        "slug": "loss-size",
        "question": "D3 -- were the losers too big?",
        "since_date": SINCE,
        "n_trades_since": len(TRADES),
        "n_losers_since": len(LOSERS),
        "equity_source_notes": equity_source_note,
    },
    "loss_distribution": {
        "book": loss_dist_book,
        "by_arm": loss_dist_by_arm,
    },
    "today_losing_legs": today_legs,
    "today_total_loss": TOTAL_TODAY_LOSS,
    "mechanism": {
        "bs_delta_at_entry_vix_sigma": "see stdout -- VIX-sigma badly overprices (BS_entry_px >> real), rejected as primary",
        "implied_vol_rows": iv_rows,
        "bs_decomposition_theta_delta_residual": decomp2,
        "pooled_decomposition": {
            "theta_pct": (tot_theta / tot_actual * 100) if decomp2 else None,
            "tape_delta_pct": (tot_delta / tot_actual * 100) if decomp2 else None,
            "residual_pct": (tot_resid / tot_actual * 100) if decomp2 else None,
        },
        "historical_delta_empirical": {
            "n_days": len(hist_deltas), "mean": statistics.mean([h["delta_slope"] for h in hist_deltas]) if hist_deltas else None,
            "median": statistics.median([h["delta_slope"] for h in hist_deltas]) if hist_deltas else None,
            "rows": hist_deltas,
        },
        "ten_min_spy_range_first_hour": {
            "n_windows": len(ten_min_ranges), "mean": statistics.mean(ten_min_ranges) if ten_min_ranges else None,
            "median": statistics.median(ten_min_ranges) if ten_min_ranges else None,
            "p25": pctile(sorted(ten_min_ranges), 25) if ten_min_ranges else None,
            "p90": pctile(sorted(ten_min_ranges), 90) if ten_min_ranges else None,
        },
        "today_actual_ranges": {
            "wave1": {"min": min(w1_prices), "max": max(w1_prices), "range": max(w1_prices)-min(w1_prices), "net": w1_prices[-1]-w1_prices[0]},
            "wave2": {"min": min(w2_prices), "max": max(w2_prices), "range": max(w2_prices)-min(w2_prices), "net": w2_prices[-1]-w2_prices[0]},
        },
        "zone_widths_observed_today": {"769.36_shelf": 0.8, "768.00_intraday_pmh": 0.384, "767.58_shelf": 0.8},
        "population_cap_vs_zone_bucketing": {
            "all_losers": dict(bucket_counts),
            "cap_hit_only": dict(bucket_counts_caphit),
            "delta_used": DELTA_HIST,
        },
    },
    "alternative_i_smaller_size_wider_cap": {
        "cohort_n": len(CURRENT_50_COHORT), "reducible_n": len(REDUCIBLE), "at_floor_n": len(AT_FLOOR),
        "reducible_stage_counts": dict(stage2_counts),
    },
}
with open(rp("analysis", "deep-research", "2026-09-03-money", "dissect-loss-size.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)
print("\n=== JSON written ===")
