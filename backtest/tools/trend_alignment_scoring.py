"""trend_alignment_scoring.py -- Phase 1 SCORING RUN (context-enrichment program, 2026-07-14).

Executes the frozen pre-registration (analysis/recommendations/
prereg-trend-alignment-correlation-2026-07-14.json) EXACTLY -- no re-picks. Split out of
trend_alignment_correlation_study.py (which owns the fetch/cache/population-loader
infrastructure + the no-look-ahead slicing boundary) to keep files small (coding-style: many
small files). Nothing here re-derives alignment math or re-implements a population loader --
every population/alignment call goes through trend_alignment_correlation_study's already-
tested functions.

THREE POPULATIONS, replayed/scored per the pre-reg:
  P1 (MODELED) -- ribbon_ride_strike_exit_ab.py's load_cohort()/fetch_entry_and_bars() +
      structure_stop_study.replay_structure_aware(), UNMODIFIED, at strike=OTM-2 (so=2),
      shape=SS-B, fill-bar convention '>' (old_semantics=False, PRIMARY). A second, independent
      call to ab.replay_cell() with the identical arguments is used ONLY as a self-consistency
      check (same n, same total pnl) -- proof this module didn't silently drift from the
      certified replay path.
  P2 (MEASURED) -- automation/state/fills-ledger.jsonl, option-only fills, grouped into
      episodes via exit_shape_parity_study.reconstruct_positions() UNMODIFIED. Attribution is
      read from each position's ENTRY fill (pre-reg convention). Still-open positions
      (closed_qty < entry_qty) excluded by construction.
  P3 (MODELED alignment / MEASURED j_pnl) -- trend_alignment_correlation_study.load_p3_population()
      (verbatim ssb_certification_study.J_ANCHOR_TRADES), j_pnl as the outcome label.

STATISTICS (see pre-reg `statistics`/`nulls`/`kill_criteria_and_confidence_bar` for the full
spec this module implements verbatim): Spearman rank correlation (bucket vs mean pnl) as
primary; a seed=1407, n=1000, alpha=0.10 two-sided shuffle-null of the (episode -> signed_score)
label assignment; monotonic-ish check (<=1 adjacent-bucket inversion); drop-top-3-per-bucket
robustness; chronological first/second-half sign-consistency; a secondary aligned-vs-fighting
Welch t-test (disclosed only, never overrides the Spearman verdict); top-3-episode
concentration (OP-20); win/loss x aligned/fighting/neutral contingency.

ANALYSIS ONLY -- reads local caches + on-disk state, writes only to analysis/recommendations/.
Places no orders, edits no live params/config.

Run: backtest/.venv/Scripts/python.exe backtest/tools/trend_alignment_scoring.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "backtest", REPO / "backtest" / "tools", REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scipy import stats as _sps  # noqa: E402

import trend_alignment_correlation_study as tas  # noqa: E402
from et_clock import et_now as _et_now           # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / "trend-alignment-correlation.json"
OUT_MD = REPO / "analysis" / "recommendations" / "trend-alignment-correlation.md"

# ---- frozen pre-reg constants (no-repick clause -- these are copied FROM the frozen file,
# never invented here; see prereg-trend-alignment-correlation-2026-07-14.json) ----
SHUFFLE_SEED = 1407
SHUFFLE_N = 1000
SHUFFLE_ALPHA = 0.10          # two-sided 90% interval
EVIDENCE_FLOOR_N = 15         # OP-16 advisory floor
CONTROL_STRIKE_SO = 2         # OTM-2 (matches ab.CONTROL_STRIKE / CONTROL_STRIKE_SO)

OCC_RE = re.compile(r"^[A-Z]+\d{6}([CP])\d{8}$")


def log(msg: str) -> None:
    print(f"[trend-alignment-scoring] {msg}", flush=True)


# ===============================================================================================
# P1 -- SS-B replay on the OTM-2 canonical cohort (MODELED), + self-consistency check against
# ribbon_ride_strike_exit_ab.replay_cell()'s own aggregate (proves no silent drift).
# ===============================================================================================
def score_p1() -> dict:
    import ribbon_ride_strike_exit_ab as ab
    import structure_stop_study as sss

    daily_df = tas.fetch_historical_bars("daily")
    hourly_df = tas.fetch_historical_bars("hourly")
    m15_df = tas.fetch_historical_bars("m15")

    prepped, _spy_full, _spy_by_date = ab.load_cohort()
    shape = ab.SS_B_SHAPE

    trades: list[dict] = []
    n_no_bars = 0
    for s in prepped:
        fetched = ab.fetch_entry_and_bars(float(s["entry_spot"]), s["side"], s["date_obj"],
                                          s["entry_ts_obj"], CONTROL_STRIKE_SO, old_semantics=False)
        if fetched is None:
            n_no_bars += 1
            continue
        entry_premium, norm_bars = fetched
        r = sss.replay_structure_aware(entry_premium, s["side"], ab.QTY, norm_bars,
                                       s["ss_time"], shape, ab.TIME_STOP_LAYER)
        alignment = tas.alignment_for_decision(daily_df, hourly_df, m15_df, s["entry_ts_obj"])
        av = tas.alignment_vs_side(alignment, s["direction"])
        trades.append({
            "date": s["date"], "entry_ts": s["entry_ts"], "direction": s["direction"],
            "pnl": round(r["pnl"], 2), "signed_score": av["signed_score"],
            "raw_score": av["raw_score"], "aligned": av["aligned"], "fighting": av["fighting"],
            "degraded": av["degraded"],
            "is_oos": "OOS" if s["date_obj"] >= ab.OOS_BOUNDARY else "IS",
        })

    # Self-consistency check: an independent call to the certified replay_cell() must produce
    # the SAME n and the SAME total pnl (proves this loop didn't silently diverge from the
    # single source of truth for the SS-B replay math).
    ref_trades, ref_n_no_bars = ab.replay_cell(prepped, CONTROL_STRIKE_SO, shape, True,
                                               old_semantics=False)
    my_total = round(sum(t["pnl"] for t in trades), 2)
    ref_total = round(sum(t["pnl"] for t in ref_trades), 2)
    self_check_passed = (n_no_bars == ref_n_no_bars and len(trades) == len(ref_trades)
                         and abs(my_total - ref_total) < 0.01)
    if not self_check_passed:
        raise AssertionError(
            f"P1 self-consistency check FAILED -- my(n={len(trades)},no_bars={n_no_bars},"
            f"total={my_total}) vs replay_cell(n={len(ref_trades)},no_bars={ref_n_no_bars},"
            f"total={ref_total}). Refusing to score on a diverged replay.")

    log(f"P1: {len(trades)} trades scored (of {len(prepped)} signals, {n_no_bars} no-OPRA-"
        f"coverage skips); self-check PASSED (ref_total={ref_total})")
    return {"trades": trades, "n_no_bars": n_no_bars, "n_total_signals": len(prepped),
            "self_check": {"passed": True, "ref_total_pnl": ref_total, "my_total_pnl": my_total}}


# ===============================================================================================
# P2 -- real fills (MEASURED). Option-only, closed positions only, attribution from entry fill.
# ===============================================================================================
def score_p2() -> dict:
    import exit_shape_parity_study as esps

    ledger_f = REPO / "automation" / "state" / "fills-ledger.jsonl"
    all_fills = []
    with ledger_f.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_fills.append(json.loads(line))

    option_fills = [f for f in all_fills if f.get("is_option") and not f.get("is_crypto")]
    positions = esps.reconstruct_positions(option_fills)

    buy_attr: dict[tuple, str] = {}
    for f in option_fills:
        if f["side"] == "buy":
            buy_attr.setdefault((f["arm"], f["symbol"], f["ts_utc"]), f["attribution"])

    daily_df = tas.fetch_historical_bars("daily")
    hourly_df = tas.fetch_historical_bars("hourly")
    m15_df = tas.fetch_historical_bars("m15")

    episodes: list[dict] = []
    n_still_open = 0
    n_symbol_unparseable = 0
    for p in positions:
        closed_qty = sum(ef["qty"] for ef in p["exit_fills"])
        if closed_qty < p["entry_qty"] - 1e-6:
            n_still_open += 1
            continue
        m = OCC_RE.match(p["symbol"])
        if not m:
            n_symbol_unparseable += 1
            continue
        side = m.group(1)
        direction = tas.side_from_option_char(side)
        attribution = buy_attr.get((p["arm"], p["symbol"], p["entry_ts_utc"]), "unknown")
        alignment = tas.alignment_for_decision(daily_df, hourly_df, m15_df, p["entry_ts_utc"])
        av = tas.alignment_vs_side(alignment, direction)
        episodes.append({
            "arm": p["arm"], "symbol": p["symbol"], "date": p["date_et"],
            "entry_ts_utc": p["entry_ts_utc"], "direction": direction,
            "pnl": round(p["actual_exit_pnl"], 2), "attribution": attribution,
            "signed_score": av["signed_score"], "raw_score": av["raw_score"],
            "aligned": av["aligned"], "fighting": av["fighting"], "degraded": av["degraded"],
        })

    engine_eps = [e for e in episodes if e["attribution"] == "engine"]
    manual_eps = [e for e in episodes if e["attribution"] == "manual"]
    unknown_eps = [e for e in episodes if e["attribution"] not in ("engine", "manual")]
    log(f"P2: {len(positions)} option-only positions ({n_still_open} still-open excluded, "
        f"{n_symbol_unparseable} unparseable-symbol excluded) -> {len(episodes)} closed "
        f"episodes: {len(engine_eps)} engine, {len(manual_eps)} manual, {len(unknown_eps)} "
        f"unknown-attribution")
    return {"episodes_all": episodes, "engine": engine_eps, "manual": manual_eps,
            "unknown_attribution": unknown_eps, "n_still_open_excluded": n_still_open,
            "n_symbol_unparseable_excluded": n_symbol_unparseable,
            "n_positions_total": len(positions)}


# ===============================================================================================
# P3 -- J's OP-16 anchor trades (n=7). Alignment MODELED at real entry_time_et; outcome = j_pnl
# (MEASURED, J's own real dollars).
# ===============================================================================================
def score_p3() -> dict:
    daily_df = tas.fetch_historical_bars("daily")
    hourly_df = tas.fetch_historical_bars("hourly")
    m15_df = tas.fetch_historical_bars("m15")

    trades = tas.load_p3_population()
    episodes = []
    for t in trades:
        entry_ts = f"{t['date']}T{t['entry_time_et']}"
        direction = tas.side_from_option_char(t["side"])
        alignment = tas.alignment_for_decision(daily_df, hourly_df, m15_df, entry_ts)
        av = tas.alignment_vs_side(alignment, direction)
        episodes.append({
            "date": t["date"], "side": t["side"], "strike": t["strike"], "qty": t["qty"],
            "entry_time_et": t["entry_time_et"], "direction": direction, "role": t["role"],
            "pnl": t["j_pnl"], "signed_score": av["signed_score"], "raw_score": av["raw_score"],
            "aligned": av["aligned"], "fighting": av["fighting"], "degraded": av["degraded"],
        })
    log(f"P3: {len(episodes)} J anchor trades scored (n=7 BY CONSTRUCTION -- always "
        f"INCONCLUSIVE on its own, corroboration/context only)")
    return {"episodes": episodes}


# ===============================================================================================
# STATISTICS -- Spearman + shuffle-null + monotonic-ish + drop-top-3 + halves + t-test +
# concentration + win/loss contingency. Pure functions, no I/O.
# ===============================================================================================
def spearman(signed_scores: list[int], pnls: list[float]) -> dict | None:
    if len(signed_scores) < 2 or len(set(signed_scores)) < 2:
        return None
    rho, pval = _sps.spearmanr(signed_scores, pnls)
    if rho != rho:  # NaN (degenerate input)
        return None
    return {"rho": float(rho), "pvalue": float(pval)}


def shuffle_null_interval(signed_scores: list[int], pnls: list[float], *,
                          seed: int = SHUFFLE_SEED, n: int = SHUFFLE_N,
                          alpha: float = SHUFFLE_ALPHA) -> dict:
    """Shuffle the (episode -> signed_score) LABEL assignment, holding pnls fixed -- the exact
    pre-reg convention (nulls.shuffle_null). Returns the empirical two-sided (1-alpha) interval
    of the Spearman rho across `n` shuffles."""
    if len(pnls) < 3:
        return {"n_valid_draws": 0, "interval_90pct": [None, None]}
    rng = random.Random(seed)
    draws = []
    scores = list(signed_scores)
    for _ in range(n):
        rng.shuffle(scores)
        rho, _p = _sps.spearmanr(scores, pnls)
        if rho == rho:
            draws.append(float(rho))
    if not draws:
        return {"n_valid_draws": 0, "interval_90pct": [None, None]}
    draws.sort()
    lo_i = int(len(draws) * (alpha / 2))
    hi_i = min(int(len(draws) * (1 - alpha / 2)), len(draws) - 1)
    return {"n_valid_draws": len(draws), "interval_90pct": [draws[lo_i], draws[hi_i]]}


def beats_null(spearman_result: dict | None, null_result: dict) -> bool:
    """Positive AND outside the shuffle-null's two-sided interval (condition_1's test, reused
    for condition_3's post-drop re-check)."""
    if not spearman_result or spearman_result["rho"] is None:
        return False
    lo, hi = null_result["interval_90pct"]
    if lo is None:
        return False
    rho = spearman_result["rho"]
    return rho > 0 and (rho < lo or rho > hi)


def bucket_table(episodes: list[dict], *, score_key: str = "signed_score",
                 pnl_key: str = "pnl") -> list[dict]:
    buckets: dict[int, list[float]] = defaultdict(list)
    for e in episodes:
        buckets[e[score_key]].append(e[pnl_key])
    table = []
    for b in range(-3, 4):
        vals = buckets.get(b, [])
        table.append({
            "bucket": b, "n": len(vals),
            "mean_pnl": round(sum(vals) / len(vals), 2) if vals else None,
            "total_pnl": round(sum(vals), 2) if vals else 0.0,
        })
    return table


def monotonic_ish(table: list[dict]) -> dict:
    """<=1 adjacent-bucket inversion across the present buckets' mean-pnl series (pre-reg
    condition_2). A bucket with n=0 (mean_pnl=None) is skipped, not treated as a break."""
    present = [(row["bucket"], row["mean_pnl"]) for row in table if row["mean_pnl"] is not None]
    if len(present) < 3:
        return {"verdict": "INSUFFICIENT_BUCKETS", "n_present_buckets": len(present),
                "n_inversions": None, "bucket_means_in_order": [v for _, v in present]}
    vals = [v for _, v in present]
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    inversions = 0
    prev_sign = None
    for d in diffs:
        sign = 1 if d > 0 else (-1 if d < 0 else 0)
        if sign == 0:
            continue
        if prev_sign is not None and sign != prev_sign:
            inversions += 1
        prev_sign = sign
    return {"verdict": "PASS" if inversions <= 1 else "FAIL", "n_present_buckets": len(present),
            "n_inversions": inversions, "bucket_means_in_order": vals}


def drop_top3_per_bucket(episodes: list[dict], *, score_key: str = "signed_score",
                         pnl_key: str = "pnl") -> list[dict]:
    by_bucket: dict[int, list[dict]] = defaultdict(list)
    for e in episodes:
        by_bucket[e[score_key]].append(e)
    kept: list[dict] = []
    for group in by_bucket.values():
        ordered = sorted(group, key=lambda e: e[pnl_key], reverse=True)
        kept.extend(ordered[3:])  # drop the top 3 P&L episodes IN THIS BUCKET
    return kept


def chronological_halves(episodes: list[dict], *, date_key: str = "date") -> tuple[list, list]:
    ordered = sorted(episodes, key=lambda e: e[date_key])
    mid = len(ordered) // 2
    return ordered[:mid], ordered[mid:]


def sign_of(spearman_result: dict | None) -> bool | None:
    if not spearman_result or spearman_result["rho"] is None:
        return None
    return spearman_result["rho"] > 0


def aligned_vs_fighting_ttest(episodes: list[dict], *, score_key: str = "signed_score",
                              pnl_key: str = "pnl") -> dict:
    aligned = [e[pnl_key] for e in episodes if e[score_key] >= 1]
    fighting = [e[pnl_key] for e in episodes if e[score_key] <= -1]
    if len(aligned) < 2 or len(fighting) < 2:
        return {"verdict": "INSUFFICIENT_N", "n_aligned": len(aligned), "n_fighting": len(fighting)}
    t_stat, p_val = _sps.ttest_ind(aligned, fighting, equal_var=False)
    return {"n_aligned": len(aligned), "n_fighting": len(fighting),
            "mean_aligned": round(sum(aligned) / len(aligned), 2),
            "mean_fighting": round(sum(fighting) / len(fighting), 2),
            "t_stat": float(t_stat), "p_value": float(p_val)}


def concentration_top3(episodes: list[dict], *, pnl_key: str = "pnl") -> float | None:
    total = sum(e[pnl_key] for e in episodes)
    if not total:
        return None
    top3 = sum(sorted((e[pnl_key] for e in episodes), reverse=True)[:3])
    return round(top3 / total, 3)


def win_loss_contingency(episodes: list[dict], *, score_key: str = "signed_score",
                         pnl_key: str = "pnl") -> dict:
    cells = {"aligned_win": 0, "aligned_loss": 0, "neutral_win": 0, "neutral_loss": 0,
             "fighting_win": 0, "fighting_loss": 0}
    for e in episodes:
        is_win = e[pnl_key] > 0
        s = e[score_key]
        bucket = "aligned" if s > 0 else ("fighting" if s < 0 else "neutral")
        cells[f"{bucket}_{'win' if is_win else 'loss'}"] += 1
    n_win = sum(1 for e in episodes if e[pnl_key] > 0)
    n_loss = len(episodes) - n_win
    return {
        "contingency": cells, "n_win": n_win, "n_loss": n_loss,
        "pct_losers_fighting_trend": round(100 * cells["fighting_loss"] / n_loss, 1) if n_loss else None,
        "pct_winners_aligned_with_trend": round(100 * cells["aligned_win"] / n_win, 1) if n_win else None,
    }


def population_stats_block(episodes: list[dict], *, date_key: str = "date") -> dict:
    """One population's full stats bundle -- bucket table, spearman, null, monotonic, t-test,
    concentration, contingency. Reused for every P1/P2/P3 slice this run reports."""
    scores = [e["signed_score"] for e in episodes]
    pnls = [e["pnl"] for e in episodes]
    table = bucket_table(episodes)
    sp = spearman(scores, pnls)
    null = shuffle_null_interval(scores, pnls)
    return {
        "n": len(episodes),
        "bucket_table": table,
        "spearman": sp,
        "shuffle_null": null,
        "beats_null": beats_null(sp, null),
        "monotonic_ish": monotonic_ish(table),
        "aligned_vs_fighting_ttest": aligned_vs_fighting_ttest(episodes),
        "concentration_top3_pct_of_total": concentration_top3(episodes),
        "win_loss_contingency": win_loss_contingency(episodes),
        "evidence_floor_met": len(episodes) >= EVIDENCE_FLOOR_N,
    }


# ===============================================================================================
# ORCHESTRATION -- run all 3 populations, evaluate the frozen kill-criteria ladder, write output.
# ===============================================================================================
def run_score() -> dict:
    prereg = json.loads(tas.PREREG_F.read_text(encoding="utf-8"))
    if prereg.get("status") != "FROZEN_PENDING_RUN":
        log(f"WARNING: pre-reg status is {prereg.get('status')!r}, expected "
            f"'FROZEN_PENDING_RUN' -- scoring anyway, but this is worth a look.")

    log("=== P1 (MODELED, SS-B @ OTM-2, n=250 canonical cohort) ===")
    p1 = score_p1()
    log("=== P2 (MEASURED, real fills) ===")
    p2 = score_p2()
    log("=== P3 (J anchor, n=7) ===")
    p3 = score_p3()

    p1_all = p1["trades"]
    p1_is = [t for t in p1_all if t["is_oos"] == "IS"]
    p1_oos = [t for t in p1_all if t["is_oos"] == "OOS"]

    p1_full_stats = population_stats_block(p1_all)
    p1_is_stats = population_stats_block(p1_is)
    p1_oos_stats = population_stats_block(p1_oos)

    # ---- condition 1: P1 OOS positive AND beats shuffle-null ----
    cond1 = p1_oos_stats["beats_null"]

    # ---- condition 2: monotonic-ish ----
    cond2 = p1_oos_stats["monotonic_ish"]["verdict"] == "PASS"

    # ---- condition 3: drop-top-3-per-bucket -- sign AND null-beating status unchanged ----
    p1_oos_dropped = drop_top3_per_bucket(p1_oos)
    dropped_scores = [t["signed_score"] for t in p1_oos_dropped]
    dropped_pnls = [t["pnl"] for t in p1_oos_dropped]
    dropped_sp = spearman(dropped_scores, dropped_pnls)
    dropped_null = shuffle_null_interval(dropped_scores, dropped_pnls)
    dropped_beats_null = beats_null(dropped_sp, dropped_null)
    cond3 = (sign_of(dropped_sp) == sign_of(p1_oos_stats["spearman"])
            and dropped_beats_null == cond1)

    # ---- condition 4: chronological halves, same sign ----
    first_half, second_half = chronological_halves(p1_oos)
    sp_first = spearman([t["signed_score"] for t in first_half], [t["pnl"] for t in first_half])
    sp_second = spearman([t["signed_score"] for t in second_half], [t["pnl"] for t in second_half])
    sign_first, sign_second = sign_of(sp_first), sign_of(sp_second)
    cond4 = sign_first is not None and sign_first == sign_second

    n_p1_oos = len(p1_oos)
    if n_p1_oos < EVIDENCE_FLOOR_N:
        p1_verdict = "INCONCLUSIVE_UNDERPOWERED"
    else:
        p1_verdict = "SUPPORTED" if (cond1 and cond2 and cond3 and cond4) else "KILL"

    # ---- P2 (engine-attributed, MEASURED) -- corroboration only ----
    p2_engine_stats = population_stats_block(p2["engine"])
    p2_manual_stats = population_stats_block(p2["manual"]) if p2["manual"] else None
    cond5 = (sign_of(p2_engine_stats["spearman"]) is not None
            and sign_of(p1_oos_stats["spearman"]) is not None
            and sign_of(p2_engine_stats["spearman"]) == sign_of(p1_oos_stats["spearman"]))

    if p1_verdict == "SUPPORTED":
        overall_verdict = "SUPPORTED" if cond5 else "MIXED_INCONCLUSIVE"
    else:
        overall_verdict = p1_verdict

    # ---- P3 (context/corroboration ONLY -- never counted toward pass/fail) ----
    p3_stats = population_stats_block(p3["episodes"])

    # ---- pooled cross-population sign check (informational, per primary_metric.statement) ----
    pooled_signs = {
        "p1_oos_sign": sign_of(p1_oos_stats["spearman"]),
        "p2_engine_sign": sign_of(p2_engine_stats["spearman"]),
        "p3_sign": sign_of(p3_stats["spearman"]),
    }
    non_null_signs = [v for v in pooled_signs.values() if v is not None]
    pooled_signs["all_agree"] = bool(non_null_signs) and len(set(non_null_signs)) == 1

    result = {
        "_doc": "Phase 1 SCORING RUN output. Frozen pre-reg: " + tas.PREREG_F.name
               + ". MEASURED = real broker fills. MODELED = SS-B replay on real OPRA bars "
               "(P1) or alignment reconstructed for a real J fill whose j_pnl is MEASURED "
               "(P3). No-repick clause applies -- this run reflects the FROZEN spec exactly.",
        "scored_at_et": _et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "hypothesis": prereg["hypothesis"],
        "populations": {
            "P1_full": {"label": "MODELED", "n": len(p1_all), "window": "2025-01-01..2026-06-18",
                       "stats": p1_full_stats},
            "P1_IS": {"label": "MODELED", "n": len(p1_is), "window": "date < 2026-01-01",
                     "stats": p1_is_stats},
            "P1_OOS": {"label": "MODELED", "n": len(p1_oos), "window": "date >= 2026-01-01",
                      "stats": p1_oos_stats,
                      "self_check": p1["self_check"], "n_no_opra_coverage_skipped": p1["n_no_bars"]},
            "P2_engine": {"label": "MEASURED", "n": len(p2["engine"]), "stats": p2_engine_stats,
                         "n_still_open_excluded": p2["n_still_open_excluded"]},
            "P2_manual": {"label": "MEASURED", "n": len(p2["manual"]),
                         "stats": p2_manual_stats,
                         "note": "reported separately, NEVER pooled into engine expectancy per pre-reg"},
            "P3_j_anchor": {"label": "MODELED alignment / MEASURED j_pnl", "n": len(p3["episodes"]),
                           "stats": p3_stats, "episodes": p3["episodes"],
                           "note": "n=7 BY CONSTRUCTION always INCONCLUSIVE standalone -- "
                                   "corroboration/context only, never counted toward pass/fail"},
        },
        "kill_criteria": {
            "condition_1_p1_oos_positive_correlation": cond1,
            "condition_2_monotonic_ish": cond2,
            "condition_3_survives_drop_top_3": {
                "passed": cond3, "dropped_n": len(p1_oos_dropped),
                "dropped_spearman": dropped_sp, "dropped_beats_null": dropped_beats_null,
            },
            "condition_4_both_halves_same_sign": {
                "passed": cond4, "first_half_n": len(first_half), "second_half_n": len(second_half),
                "first_half_spearman": sp_first, "second_half_spearman": sp_second,
            },
            "condition_5_p2_corroborates": {
                "passed": cond5, "p2_engine_n": len(p2["engine"]),
                "p2_engine_evidence_floor_met": p2_engine_stats["evidence_floor_met"],
            },
        },
        "p1_verdict": p1_verdict,
        "overall_verdict": overall_verdict,
        "pooled_cross_population_sign_check": pooled_signs,
        "p2_attribution_breakdown": {
            "engine": len(p2["engine"]), "manual": len(p2["manual"]),
            "unknown_attribution": len(p2["unknown_attribution"]),
            "n_positions_total": p2["n_positions_total"],
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")

    OUT_MD.write_text(render_md(result), encoding="utf-8")
    log(f"wrote {OUT_MD}")

    log(f"P1 verdict: {p1_verdict} | OVERALL verdict: {overall_verdict}")
    return result


# ===============================================================================================
# MARKDOWN REPORT
# ===============================================================================================
def _fmt_rho(sp: dict | None) -> str:
    if not sp or sp["rho"] is None:
        return "n/a (degenerate)"
    return f"rho={sp['rho']:.3f}, p={sp['pvalue']:.3f}"


def _fmt_bucket_table(table: list[dict]) -> str:
    lines = ["| bucket | n | mean pnl | total pnl |", "|---|---|---|---|"]
    for row in table:
        mp = f"${row['mean_pnl']:.2f}" if row["mean_pnl"] is not None else "-"
        lines.append(f"| {row['bucket']:+d} | {row['n']} | {mp} | ${row['total_pnl']:.2f} |")
    return "\n".join(lines)


def render_md(r: dict) -> str:
    p1oos = r["populations"]["P1_OOS"]
    p1full = r["populations"]["P1_full"]
    p2e = r["populations"]["P2_engine"]
    p2m = r["populations"]["P2_manual"]
    p3 = r["populations"]["P3_j_anchor"]
    kc = r["kill_criteria"]

    lines = [
        "# Trend-Alignment Correlation Study -- Phase 1 Results",
        "",
        f"Scored: {r['scored_at_et']} ET. Frozen pre-reg: "
        "`analysis/recommendations/prereg-trend-alignment-correlation-2026-07-14.json` "
        "(no re-picks after freeze).",
        "",
        f"## VERDICT: {r['overall_verdict']}",
        "",
        f"P1 (own verdict): **{r['p1_verdict']}**. Overall (P1 AND P2-corroboration): "
        f"**{r['overall_verdict']}**.",
        "",
        "A KILL/INCONCLUSIVE result here is a publishable, informative outcome per this "
        "program's own discipline -- it does NOT get re-run or re-picked. A KILL means Phase "
        "0's context-bundle tag stays LOGGED-ONLY (or is retired), never promoted to a gate/"
        "veto/sizing input.",
        "",
        "## Hypothesis (frozen)",
        "",
        r["hypothesis"],
        "",
        "## P1 -- canonical ribbon_ride cohort, SS-B replay (MODELED, real OPRA bars)",
        "",
        f"n_total_signals={p1full['n']}, OOS (date>=2026-01-01) n={p1oos['n']}, "
        f"no-OPRA-coverage skips={p1oos.get('n_no_opra_coverage_skipped')}. "
        f"Self-check vs `replay_cell()`: **{'PASSED' if p1oos['self_check']['passed'] else 'FAILED'}** "
        f"(ref_total_pnl=${p1oos['self_check']['ref_total_pnl']:.2f}).",
        "",
        "### P1 OOS expectancy-by-alignment-bucket",
        "",
        _fmt_bucket_table(p1oos["stats"]["bucket_table"]),
        "",
        f"Spearman (bucket vs mean-pnl): {_fmt_rho(p1oos['stats']['spearman'])}. "
        f"Shuffle-null 90% interval (seed={SHUFFLE_SEED}, n={SHUFFLE_N} draws, "
        f"alpha={SHUFFLE_ALPHA}): {p1oos['stats']['shuffle_null']['interval_90pct']}. "
        f"Beats null: **{p1oos['stats']['beats_null']}**.",
        "",
        f"Monotonic-ish (<=1 adjacent-bucket inversion): "
        f"**{p1oos['stats']['monotonic_ish']['verdict']}** "
        f"({p1oos['stats']['monotonic_ish']['n_inversions']} inversions across "
        f"{p1oos['stats']['monotonic_ish']['n_present_buckets']} present buckets).",
        "",
        f"Aligned-vs-fighting t-test (secondary, disclosed only): "
        f"{p1oos['stats']['aligned_vs_fighting_ttest']}",
        "",
        f"Top-3-episode concentration: "
        f"{p1oos['stats']['concentration_top3_pct_of_total']} of total P&L (OP-20 disclosure).",
        "",
        f"Win/loss x aligned/fighting contingency: "
        f"{p1oos['stats']['win_loss_contingency']['contingency']}. "
        f"% losers fighting trend: {p1oos['stats']['win_loss_contingency']['pct_losers_fighting_trend']}. "
        f"% winners aligned with trend: {p1oos['stats']['win_loss_contingency']['pct_winners_aligned_with_trend']}.",
        "",
        "### P1 full-window (IS+OOS combined, for reference -- IS/OOS split is the primary read)",
        "",
        _fmt_bucket_table(p1full["stats"]["bucket_table"]),
        "",
        "## Kill-criteria ladder (P1's own SUPPORTED/KILL verdict)",
        "",
        f"1. OOS positive + beats shuffle-null: **{kc['condition_1_p1_oos_positive_correlation']}**",
        f"2. Monotonic-ish: **{kc['condition_2_monotonic_ish']}**",
        f"3. Survives drop-top-3-per-bucket: **{kc['condition_3_survives_drop_top_3']['passed']}** "
        f"(post-drop n={kc['condition_3_survives_drop_top_3']['dropped_n']}, "
        f"{_fmt_rho(kc['condition_3_survives_drop_top_3']['dropped_spearman'])})",
        f"4. Both chronological halves same sign: "
        f"**{kc['condition_4_both_halves_same_sign']['passed']}** "
        f"(first half n={kc['condition_4_both_halves_same_sign']['first_half_n']} "
        f"{_fmt_rho(kc['condition_4_both_halves_same_sign']['first_half_spearman'])}, "
        f"second half n={kc['condition_4_both_halves_same_sign']['second_half_n']} "
        f"{_fmt_rho(kc['condition_4_both_halves_same_sign']['second_half_spearman'])})",
        f"5. P2 (real fills) corroborates sign: "
        f"**{kc['condition_5_p2_corroborates']['passed']}** "
        f"(P2 engine n={kc['condition_5_p2_corroborates']['p2_engine_n']}, "
        f"evidence floor met={kc['condition_5_p2_corroborates']['p2_engine_evidence_floor_met']})",
        "",
        "## P2 -- real engine fills (MEASURED)",
        "",
        f"n={p2e['n']} engine-attributed closed episodes ({r['p2_attribution_breakdown']}), "
        f"{p2e['n_still_open_excluded']} still-open excluded by construction.",
        "",
        "### P2 engine expectancy-by-alignment-bucket",
        "",
        _fmt_bucket_table(p2e["stats"]["bucket_table"]),
        "",
        f"Spearman: {_fmt_rho(p2e['stats']['spearman'])}. Beats null: {p2e['stats']['beats_null']} "
        f"(n={p2e['n']}, evidence floor n>=15 met: {p2e['stats']['evidence_floor_met']} -- "
        f"P2's job is DIRECTIONAL corroboration, not an independent statistical pass/fail).",
        "",
        f"Win/loss contingency: {p2e['stats']['win_loss_contingency']['contingency']}. "
        f"% losers fighting trend: {p2e['stats']['win_loss_contingency']['pct_losers_fighting_trend']}. "
        f"% winners aligned: {p2e['stats']['win_loss_contingency']['pct_winners_aligned_with_trend']}.",
        "",
    ]
    if p2m and p2m["n"]:
        lines += [
            f"### P2 manual (n={p2m['n']}, reported separately, NEVER pooled into engine expectancy)",
            "",
            _fmt_bucket_table(p2m["stats"]["bucket_table"]),
            "",
        ]
    lines += [
        "## P3 -- J's OP-16 anchor trades (n=7, corroboration/context ONLY, never counted "
        "toward pass/fail)",
        "",
        "| date | role | side | j_pnl | signed_score | aligned | fighting |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in p3["episodes"]:
        lines.append(f"| {e['date']} | {e['role']} | {e['side']} | ${e['pnl']:.2f} | "
                    f"{e['signed_score']:+d} | {e['aligned']} | {e['fighting']} |")
    lines += [
        "",
        f"Spearman (n=7, always INCONCLUSIVE per evidence floor): {_fmt_rho(p3['stats']['spearman'])}.",
        "",
        "## Pooled cross-population sign check (informational only -- see pre-reg primary_metric)",
        "",
        f"{r['pooled_cross_population_sign_check']}",
        "",
        "## Honesty notes",
        "",
        "- P1 is a MODELED replay (SS-B exit shape on real OPRA bars), not a live fill -- "
        "absolute dollars are QTY=10 research-scale, not account-size absolute.",
        "- P2 is MEASURED (real broker fills) but n~113 spans multiple arms/risk-tiers pooled "
        "together per the pre-reg's population definition; not stratified by arm here.",
        "- P3's alignment reconstruction is MODELED (no live context-bundle existed at those "
        "April/May 2026 trade times) even though j_pnl itself is MEASURED.",
        "- This pre-reg's scope ends at 'does it correlate' -- a SUPPORTED verdict does NOT "
        "itself change any live behavior (OP-0 #1 / OP-16 eval-first gate). It only qualifies "
        "a separately pre-registered Phase 2 proposal for HOW the tag would be consumed.",
        "- **Build-time observation (disclosed, not a re-pick):** buckets 0/+2/-2 are EMPTY in "
        "every population's table above. Root cause verified directly (sampled 60 P1 alignment "
        "reads): `analyze_structure`'s per-timeframe classifier essentially never returns "
        "'range'/'unknown' on SPY daily/hourly/15m history in this window -- every timeframe "
        "read was 'uptrend' or 'downtrend', never a 0-vote. `alignment_score` is therefore "
        "structurally odd-valued ({-3,-1,+1,+3}), not the full [-3,+3] the pre-reg's bucket "
        "range anticipated. This does not change any scoring/kill-criteria logic (all bucket "
        "math already handles n=0 buckets correctly) -- disclosed because it means this study's "
        "effective resolution is 4 buckets, not 7, a fact worth carrying into any Phase 2 design.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(0 if run_score() else 1)
