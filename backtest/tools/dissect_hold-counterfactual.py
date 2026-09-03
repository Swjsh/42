"""
D4 hold-counterfactual dissection (2026-09-03, read-only, cached-data-only).

Reconstructs minute/sub-minute premium for SPY 0DTE 770C / 768C / 772C from three
sources -- real quote-tape NBBO (FACT), real fills (FACT), and a disclosed
Black-Scholes proxy calibrated to the nearest real quote (APPROXIMATE) -- then
prices the eight losing legs of today's wave 1 (770C/772C) and wave 2 (768C/770C)
under five counterfactual hold rules.

Read-only on automation/state/**, analysis/quote-tape/**, journal/**.
Writes only to analysis/deep-research/2026-09-03-money/ and this script.
No network calls. Cached ledger data only.
"""
import json
import math
from collections import defaultdict

CORE_DECISIONS = "automation/state/core-decisions.jsonl"
QUOTE_TAPE = "analysis/quote-tape/2026-09-03.jsonl"
KEY_LEVELS = "automation/state/key-levels.json"
DATE = "2026-09-03"
CUTOFF = "11:39:59"   # analysis stamp is 11:40 ET; last fully-observed minute is 11:39

# ---------------------------------------------------------------- load raw ticks
def load_core_rows():
    rows = []
    with open(CORE_DECISIONS, encoding="utf-8") as f:
        for l in f:
            if f'"date": "{DATE}"' in l:
                rows.append(json.loads(l))
    rows.sort(key=lambda r: r["ts_et"])
    return rows

core_rows = load_core_rows()

# minute -> spy, vix  (first-seen per minute; both accounts merged, safe read first)
spy_tape = {}
vix_tape = {}
for r in core_rows:
    t = r["ts_et"][11:16]
    if t not in spy_tape:
        spy_tape[t] = r["spy"]
        vix_tape[t] = r["vix"]

minutes_sorted = sorted(spy_tape.keys())
minutes_sorted = [m for m in minutes_sorted if m <= CUTOFF[:5]]

# verified 5m-close formula: last_closed_5m_close(t) = spy_tape[ floor((t-1)/5)*5 + 1 ]
def minute_to_int(m):
    hh, mm = m.split(":")
    return int(hh) * 60 + int(mm)

def int_to_minute(x):
    return f"{x // 60:02d}:{x % 60:02d}"

def last_closed_5m_close(t_minute):
    x = minute_to_int(t_minute)
    m0 = ((x - 1) // 5) * 5
    anchor = m0 + 1
    key = int_to_minute(anchor)
    # walk backward to nearest available minute if exact key missing
    while key not in spy_tape and anchor > minute_to_int("09:30"):
        anchor -= 1
        key = int_to_minute(anchor)
    return spy_tape.get(key)

# cross-check against engine-reported values (ground truth) wherever exit_pass exists
verify_errs = []
for r in core_rows:
    ep = r.get("exit_pass")
    if ep and ep[0].get("last_closed_5m_close") is not None:
        t = r["ts_et"][11:16]
        got = last_closed_5m_close(t)
        want = ep[0]["last_closed_5m_close"]
        if got is not None and abs(got - want) > 1e-9:
            verify_errs.append((t, got, want))

# ------------------------------------------------------------ load quote tape
def load_quote_rows():
    rows = []
    with open(QUOTE_TAPE, encoding="utf-8") as f:
        for l in f:
            rows.append(json.loads(l))
    rows.sort(key=lambda r: r["ts_et"])
    return rows

qt_rows = load_quote_rows()
by_symbol = defaultdict(list)
for r in qt_rows:
    t = r["ts_et"][11:19]
    if t <= CUTOFF:
        by_symbol[r["symbol"]].append({"t": t, "bid": r["bid"], "ask": r["ask"], "mid": r["mid"]})

for sym in by_symbol:
    by_symbol[sym].sort(key=lambda x: x["t"])

# ------------------------------------------------------------ key levels
with open(KEY_LEVELS, encoding="utf-8") as f:
    kl = json.load(f)
levels_by_price = {round(l["price"], 2): l for l in kl["levels"] if "price" in l}

def zone_floor(trigger_level):
    lvl = levels_by_price.get(round(trigger_level, 2))
    zw = lvl["zone_width"] if lvl and "zone_width" in lvl else None
    return (trigger_level - zw) if zw is not None else None, zw

# ------------------------------------------------------------ Black-Scholes
def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bs_call(S, K, T, sigma):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * norm_cdf(d2)

def implied_vol(target, S, K, T, lo=0.01, hi=6.0, iters=60):
    if target <= max(S - K, 0.0) + 1e-6:
        return lo
    flo, fhi = bs_call(S, K, T, lo) - target, bs_call(S, K, T, hi) - target
    if flo > 0:
        return lo
    if fhi < 0:
        return hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        fm = bs_call(S, K, T, mid) - target
        if abs(fm) < 1e-6:
            return mid
        if fm > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)

CLOSE_MIN = minute_to_int("16:00")

def T_years(t_minute):
    mins_to_close = max(CLOSE_MIN - minute_to_int(t_minute), 0.5)
    return mins_to_close / (390.0 * 252.0)

# --------------------------------------------------- build per-symbol premium path
# merged timeline: real quote-tape entries where available (native ~20s cadence),
# else one synthetic BS-proxy entry per minute using a calibration scale k such that
# sigma_used(t) = k * VIX(t)/100, with k solved once per gap from the last real quote
# immediately preceding the gap (implied_vol / (VIX/100) at that instant), held
# constant through the gap. Reports the calibration error at the minute real quotes
# resume, where that happens within the analysis window.

def build_symbol_path(symbol, strike, entry_minute):
    real = by_symbol.get(symbol, [])
    real = [q for q in real if q["t"] >= entry_minute + ":00"]
    # index real quotes by minute for quick lookup / gap detection
    real_minutes = sorted(set(q["t"][:5] for q in real))
    all_minutes = [m for m in minutes_sorted if m >= entry_minute]

    path = []  # list of dicts: t, bid, ask, mid, source
    for q in real:
        path.append({"t": q["t"], "bid": q["bid"], "ask": q["ask"], "mid": q["mid"], "source": "FACT_quote"})

    have_minutes = set(real_minutes)
    gap_minutes = [m for m in all_minutes if m not in have_minutes]

    # group gap minutes into contiguous runs
    runs = []
    cur = []
    for m in all_minutes:
        if m in have_minutes:
            if cur:
                runs.append(cur); cur = []
        else:
            cur.append(m)
    if cur:
        runs.append(cur)

    calib_log = []
    for run in runs:
        start = run[0]
        start_idx = minutes_sorted.index(start)
        # anchor_before: last real quote strictly before this run (by minute)
        anchor_minute = None
        for m in reversed(minutes_sorted[:start_idx]):
            if m in have_minutes:
                anchor_minute = m
                break
        # anchor_after: first real quote strictly after this run (two-point calibration
        # when the gap is bounded on both sides -- far more accurate than single-point
        # forward extrapolation, which a naive constant-implied-vol decay model gets
        # badly wrong for a near-the-money 0DTE contract; see calibration_error_pct log)
        end_idx = minute_to_int(run[-1])
        next_minute_key = int_to_minute(end_idx + 1)
        anchor_after_minute = next_minute_key if next_minute_key in have_minutes else None

        iv0 = iv1 = None
        S0 = vix0 = None
        if anchor_minute is not None:
            anchor_quotes = [q for q in real if q["t"][:5] == anchor_minute]
            anchor_mid = anchor_quotes[-1]["mid"]
            S0 = spy_tape[anchor_minute]
            vix0 = vix_tape[anchor_minute]
            iv0 = implied_vol(anchor_mid, S0, strike, T_years(anchor_minute))
        if anchor_after_minute is not None:
            after_quotes = [q for q in real if q["t"][:5] == anchor_after_minute]
            after_mid = after_quotes[0]["mid"]
            S1 = spy_tape[anchor_after_minute]
            vix1 = vix_tape[anchor_after_minute]
            iv1 = implied_vol(after_mid, S1, strike, T_years(anchor_after_minute))

        bounded = iv0 is not None and iv1 is not None
        if bounded:
            t0i, t1i = minute_to_int(anchor_minute), minute_to_int(anchor_after_minute)
            anchor_src = (f"TWO-POINT calibration: real quote at {anchor_minute} (mid {anchor_mid}, "
                          f"implied_vol {iv0:.4f}) .. real quote at {anchor_after_minute} "
                          f"(mid {after_mid}, implied_vol {iv1:.4f}); sigma linearly time-interpolated "
                          f"between the two -- exact at both boundaries by construction")
        elif iv0 is not None:
            k = iv0 / (vix0 / 100.0)
            anchor_src = (f"SINGLE-POINT (open-ended gap, no later real quote in window): anchored to "
                          f"real quote at {anchor_minute} (mid {anchor_mid}), implied_vol {iv0:.4f}, "
                          f"VIX {vix0:.2f} -> k={k:.4f}, sigma(t)=k*VIX(t)/100 held forward")
        else:
            k = 1.0
            anchor_src = "no prior real quote -- k=1.0 (sigma=VIX/100) fallback"

        for m in run:
            S = spy_tape[m]
            vix = vix_tape[m]
            if bounded:
                frac = (minute_to_int(m) - t0i) / float(t1i - t0i)
                sigma = max(iv0 + frac * (iv1 - iv0), 0.005)
            elif iv0 is not None:
                sigma = max(k * vix / 100.0, 0.01)
            else:
                sigma = max(k * vix / 100.0, 0.01)
            price = bs_call(S, strike, T_years(m), sigma)
            path.append({"t": m + ":30", "bid": price, "ask": price, "mid": price,
                         "source": "APPROX_bs_2pt" if bounded else "APPROX_bs_1pt",
                         "sigma": sigma, "calib": anchor_src})

        if bounded:
            # diagnostic only: what a naive single-anchor (sigma=k*VIX/100 held flat)
            # forward extrapolation would have produced at the gap end, for comparison
            k_naive = iv0 / (vix0 / 100.0)
            sigma_naive_end = max(k_naive * vix_tape[run[-1]] / 100.0, 0.01)
            naive_proxy_end = bs_call(spy_tape[run[-1]], strike, T_years(run[-1]), sigma_naive_end)
            naive_err_pct = (naive_proxy_end - after_mid) / after_mid * 100.0
            calib_log.append({
                "gap": f"{run[0]}-{run[-1]}", "anchor": anchor_src,
                "proxy_at_gap_end": "N/A (exact at boundary by construction)",
                "real_at_resume": after_mid, "resume_minute": anchor_after_minute,
                "calibration_error_pct": 0.0,
                "method": "two-point (bounded) -- used for pricing",
                "diagnostic_naive_single_point_error_pct": round(naive_err_pct, 2),
                "diagnostic_note": "if a naive single-anchor constant-k-vs-VIX extrapolation had been used instead (as in the trailing open-ended gaps), it would have missed the real resumption price by this much -- shows the single-point method's reliability is poor for a near-the-money 0DTE contract several points from spot",
            })
        else:
            calib_log.append({
                "gap": f"{run[0]}-{run[-1]}", "anchor": anchor_src,
                "proxy_at_gap_end": None, "real_at_resume": None, "resume_minute": None,
                "calibration_error_pct": "UNMEASURED (no later real quote in analysis window -- gap still open at data cutoff 11:39 ET)",
                "method": "single-point forward extrapolation (open-ended)",
            })

    path.sort(key=lambda x: x["t"])
    return path, calib_log

# ---------------------------------------------------------------- leg engine
def simulate_rule(path, entry_price, qty, rule, zone_floor_val=None, trigger_level=None,
                   runner_mode="chandelier", tp1_frac=0.8):
    """Return dict describing exit(s), P&L, and MAE along the held path."""
    mult = 100
    mae_dollars = 0.0
    mae_pct_prem = 0.0
    running_min = entry_price

    def upd_mae(px):
        nonlocal mae_dollars, mae_pct_prem, running_min
        if px < running_min:
            running_min = px
        dd = (entry_price - running_min) * qty * mult
        if dd > mae_dollars:
            mae_dollars = dd
            mae_pct_prem = (entry_price - running_min) / entry_price * 100.0

    if rule == "zone_edge_break":
        for pt in path:
            t5 = pt["t"][:5]
            c5 = last_closed_5m_close(t5) if t5 in spy_tape else None
            upd_mae(pt["bid"])
            if c5 is not None and zone_floor_val is not None and c5 < zone_floor_val:
                exit_px = pt["bid"]
                pnl = (exit_px - entry_price) * qty * mult
                return {"resolved": True, "exit_t": pt["t"], "exit_px": round(exit_px, 4),
                        "trigger_5m_close": c5, "pnl": round(pnl, 2),
                        "mae_dollars": round(mae_dollars, 2), "mae_pct_of_premium": round(mae_pct_prem, 2),
                        "source": pt["source"]}
        last = path[-1]
        mtm = (last["bid"] - entry_price) * qty * mult
        return {"resolved": False, "note": "no 5m close breached zone floor by cutoff", "mtm_at_cutoff": round(mtm, 2),
                "mtm_t": last["t"], "mtm_px": round(last["bid"], 4),
                "mae_dollars": round(mae_dollars, 2), "mae_pct_of_premium": round(mae_pct_prem, 2)}

    if rule in ("cap_50", "cap_70"):
        thresh = entry_price * (0.5 if rule == "cap_50" else 0.30)
        for pt in path:
            upd_mae(pt["bid"])
            if pt["bid"] <= thresh:
                exit_px = pt["bid"]
                pnl = (exit_px - entry_price) * qty * mult
                return {"resolved": True, "exit_t": pt["t"], "exit_px": round(exit_px, 4),
                        "pnl": round(pnl, 2), "mae_dollars": round(mae_dollars, 2),
                        "mae_pct_of_premium": round(mae_pct_prem, 2), "source": pt["source"]}
        last = path[-1]
        mtm = (last["bid"] - entry_price) * qty * mult
        return {"resolved": False, "note": "cap never touched by cutoff", "mtm_at_cutoff": round(mtm, 2),
                "mtm_t": last["t"], "mtm_px": round(last["bid"], 4),
                "mae_dollars": round(mae_dollars, 2), "mae_pct_of_premium": round(mae_pct_prem, 2)}

    if rule == "tp1_runner":
        tp1_thresh = entry_price * 2.0
        tp1_hit = None
        for pt in path:
            upd_mae(pt["bid"])
            if pt["bid"] >= tp1_thresh:
                tp1_hit = pt
                break
        if tp1_hit is None:
            last = path[-1]
            mtm = (last["bid"] - entry_price) * qty * mult
            return {"resolved": False, "note": "TP1 (+100%) never reached by cutoff", "mtm_at_cutoff": round(mtm, 2),
                    "mtm_t": last["t"], "mtm_px": round(last["bid"], 4),
                    "mae_dollars": round(mae_dollars, 2), "mae_pct_of_premium": round(mae_pct_prem, 2)}
        tp1_qty = round(qty * tp1_frac, 3)
        runner_qty = qty - tp1_qty
        tp1_pnl = (tp1_hit["bid"] - entry_price) * tp1_qty * mult
        # runner phase
        hwm = tp1_hit["bid"]
        runner_exit = None
        idx0 = path.index(tp1_hit)
        for pt in path[idx0 + 1:]:
            upd_mae(pt["bid"])
            if runner_mode == "chandelier":
                if pt["bid"] > hwm:
                    hwm = pt["bid"]
                if pt["bid"] <= hwm * 0.85:
                    runner_exit = pt
                    break
            else:  # breakeven stop, bold/risky style, no trail
                if pt["bid"] <= entry_price:
                    runner_exit = pt
                    break
        if runner_exit is not None:
            runner_pnl = (runner_exit["bid"] - entry_price) * runner_qty * mult
            total = tp1_pnl + runner_pnl
            return {"resolved": True, "tp1_t": tp1_hit["t"], "tp1_px": round(tp1_hit["bid"], 4),
                    "tp1_qty": tp1_qty, "tp1_pnl": round(tp1_pnl, 2),
                    "runner_exit_t": runner_exit["t"], "runner_exit_px": round(runner_exit["bid"], 4),
                    "runner_qty": runner_qty, "runner_pnl": round(runner_pnl, 2),
                    "pnl": round(total, 2), "mae_dollars": round(mae_dollars, 2),
                    "mae_pct_of_premium": round(mae_pct_prem, 2), "runner_mode": runner_mode}
        else:
            last = path[-1]
            runner_mtm = (last["bid"] - entry_price) * runner_qty * mult
            total_mtm = tp1_pnl + runner_mtm
            return {"resolved": "partial", "tp1_t": tp1_hit["t"], "tp1_px": round(tp1_hit["bid"], 4),
                    "tp1_qty": tp1_qty, "tp1_pnl": round(tp1_pnl, 2),
                    "note": "runner still open at cutoff", "runner_mtm": round(runner_mtm, 2),
                    "mtm_t": last["t"], "mtm_px": round(last["bid"], 4),
                    "pnl_realized_plus_mtm": round(total_mtm, 2),
                    "mae_dollars": round(mae_dollars, 2), "mae_pct_of_premium": round(mae_pct_prem, 2),
                    "runner_mode": runner_mode}

    if rule == "hold_1520":
        for pt in path:
            upd_mae(pt["bid"])
        last = path[-1]
        mtm = (last["bid"] - entry_price) * qty * mult
        return {"resolved": False, "note": "PENDING -- 15:20 ET not yet reached; unrealized mark-to-market as of data cutoff",
                "mtm_at_cutoff": round(mtm, 2), "mtm_t": last["t"], "mtm_px": round(last["bid"], 4),
                "mae_dollars": round(mae_dollars, 2), "mae_pct_of_premium": round(mae_pct_prem, 2)}

    raise ValueError(rule)

# ---------------------------------------------------------------- the 8 legs
LEGS = [
    dict(name="safe-2 wave1 770C", symbol="SPY260903C00770000", strike=770.0, arm="safe-2",
         entry_minute="09:41", entry_price=0.98, qty=3, trigger_level=769.36,
         real_exit_t="10:03:03", real_exit_px=0.50, equity=5653.81, tp1_frac=0.8, runner_mode="chandelier"),
    dict(name="safe-3 wave1 770C", symbol="SPY260903C00770000", strike=770.0, arm="safe-3",
         entry_minute="09:42", entry_price=1.11, qty=5, trigger_level=769.36,
         real_exit_t="10:01:06", real_exit_px=0.57, equity=5639.10, tp1_frac=0.8, runner_mode="chandelier"),
    dict(name="risky-1 wave1 770C", symbol="SPY260903C00770000", strike=770.0, arm="risky-1",
         entry_minute="09:42", entry_price=1.08, qty=5, trigger_level=769.36,
         real_exit_t="10:02:07", real_exit_px=0.52, equity=6149.12, tp1_frac=0.667, runner_mode="breakeven"),
    dict(name="bold-2 wave1 772C", symbol="SPY260903C00772000", strike=772.0, arm="bold-2",
         entry_minute="09:42", entry_price=0.37, qty=5, trigger_level=769.36,
         real_exit_t="09:58:04", real_exit_px=0.20, equity=5593.52, tp1_frac=0.667, runner_mode="breakeven"),
    dict(name="safe-2 wave2 768C", symbol="SPY260903C00768000", strike=768.0, arm="safe-2",
         entry_minute="10:16", entry_price=1.40, qty=3, trigger_level=768.00,
         real_exit_t="10:36:04", real_exit_px=1.18, equity=5653.81, tp1_frac=0.8, runner_mode="chandelier"),
    dict(name="safe-3 wave2 768C", symbol="SPY260903C00768000", strike=768.0, arm="safe-3",
         entry_minute="10:17", entry_price=1.31, qty=5, trigger_level=768.00,
         real_exit_t="10:37:06", real_exit_px=1.18, equity=5639.10, tp1_frac=0.8, runner_mode="chandelier"),
    dict(name="risky-1 wave2 768C", symbol="SPY260903C00768000", strike=768.0, arm="risky-1",
         entry_minute="10:17", entry_price=1.31, qty=5, trigger_level=768.00,
         real_exit_t="10:37:07", real_exit_px=1.18, equity=6149.12, tp1_frac=0.667, runner_mode="breakeven"),
    dict(name="bold-2 wave2 770C", symbol="SPY260903C00770000", strike=770.0, arm="bold-2",
         entry_minute="10:16", entry_price=0.48, qty=5, trigger_level=768.00,
         real_exit_t="10:36:05", real_exit_px=0.34, equity=5593.52, tp1_frac=0.667, runner_mode="breakeven"),
]

RULES = ["zone_edge_break", "cap_50", "cap_70", "tp1_runner", "hold_1520"]

results = {}
paths_cache = {}
calib_logs = {}

for leg in LEGS:
    key = (leg["symbol"], leg["entry_minute"], leg["entry_price"])
    if key not in paths_cache:
        path, clog = build_symbol_path(leg["symbol"], leg["strike"], leg["entry_minute"])
        paths_cache[key] = path
        calib_logs[key] = clog
    path = paths_cache[key]
    zf, zw = zone_floor(leg["trigger_level"])
    leg_out = {"zone_floor": zf, "zone_width": zw, "real_pnl": round((leg["real_exit_px"] - leg["entry_price"]) * leg["qty"] * 100, 2)}
    for rule in RULES:
        leg_out[rule] = simulate_rule(path, leg["entry_price"], leg["qty"], rule,
                                       zone_floor_val=zf, trigger_level=leg["trigger_level"],
                                       runner_mode=leg["runner_mode"], tp1_frac=leg["tp1_frac"])
    results[leg["name"]] = leg_out

# ---------------------------------------------------------------- wave-1 mechanics check
# how far below zone floor 768.56 was SPY when the -50% cap fired at 10:01-10:03?
zf_wave1, zw_wave1 = zone_floor(769.36)
mech = {
    "zone_floor_wave1": zf_wave1,
    "zone_width_wave1": zw_wave1,
    "spy_at_cap_fires": {m: spy_tape.get(m) for m in ["10:01", "10:02", "10:03"]},
    "distance_below_zone_floor": {m: round(zf_wave1 - spy_tape[m], 4) if spy_tape.get(m) is not None and spy_tape[m] < zf_wave1 else
                                   round(spy_tape[m] - zf_wave1, 4) if spy_tape.get(m) is not None else None
                                   for m in ["10:01", "10:02", "10:03"]},
    "5m_closes_wave1_holding_period": {m: last_closed_5m_close(m) for m in
                                        ["09:41","09:46","09:51","09:56","10:01","10:06","10:11","10:16"]},
    "did_5m_close_breach_zone_floor_768_56_before_1003": None,
}
breach_before = [m for m in ["09:41","09:46","09:51","09:56","10:01"]
                 if last_closed_5m_close(m) is not None and last_closed_5m_close(m) < zf_wave1]
mech["did_5m_close_breach_zone_floor_768_56_before_1003"] = breach_before if breach_before else "NO -- never breached (min 5m close in window was {:.3f} at {})".format(
    min(last_closed_5m_close(m) for m in ["09:41","09:46","09:51","09:56","10:01"]),
    min(["09:41","09:46","09:51","09:56","10:01"], key=lambda m: last_closed_5m_close(m))
)

# ---------------------------------------------------------------- dump
out = {
    "verify_5m_close_formula_against_engine_ground_truth": {
        "n_ground_truth_points_checked": sum(1 for r in core_rows if r.get("exit_pass") and r["exit_pass"][0].get("last_closed_5m_close") is not None),
        "mismatches": verify_errs,
    },
    "wave1_mechanics": mech,
    "legs": results,
    "calibration_logs": {f"{k[0]}@{k[1]}": v for k, v in calib_logs.items()},
    "spy_vix_tape_minutes": len(minutes_sorted),
}

with open("C:/Users/jackw/AppData/Local/Temp/claude/C--Users-jackw-Desktop-42/b6eea006-22c7-498b-a0c1-23c79c635f20/scratchpad/hold_counterfactual_output.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)

print("DONE. verify mismatches:", len(verify_errs))
print(json.dumps(mech, indent=2, default=str))
