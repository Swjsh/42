"""RSI-EXTENSION-BLOCK-ELITE-BULL — pre-registered probe of J's 2026-07-21 dojo ruling.

Context (queue RSI-EXTENSION-BLOCK-ELITE-BULL, J RULING from dojo session
2026-07-21-225649): on the live 12:21 SKIP_ELITE_BULL_LEVEL_RECLAIM exhibit J said
"12:21 needs to not happen -- the move is already happening, we didn't bounce off
a key level. If that's an entry the same logic should apply to the 11:15 candle,
and 11:15 would have been a great entry."

This is a DIFFERENT question from the already-CLOSED "bull-unblock" thread
(CLAUDE.md project memory: block_elite_bull KEEP, net -$241 on its removed
cohort -- do not re-mine wholesale unblock). J is NOT asking to remove the gate;
he is asking whether a QUALITY CONDITION on top of the existing block can let a
fresh, non-extended reclaim (11:15-shaped) through while keeping an extended,
already-moved reclaim (12:21-shaped) blocked. This probe tests that discriminator
against the REAL removed-by-block_elite_bull cohort, not J's one anecdote.

PRE-REGISTERED HYPOTHESIS (frozen before running, per J's own tape read):
    An ELITE bull level_reclaim should stay BLOCKED when, at the entry bar:
      (a) RSI(14) >= X  AND no reset below Y occurred in the trailing N bars
          (i.e. the move has been extended/one-directional, no fresh pullback), OR
      (b) close is >= Z dollars above the session low (already ran, no fresh entry)
    "Should PASS" (quality-conditioned exemption from block_elite_bull) is the
    complement: RSI reset recently (fresh bounce) and/or entry is close to the low.

Grid (small, pre-registered, NOT hand-picked post-hoc):
    X (RSI ext threshold)  in {65, 68, 70}
    Y (reset threshold)    in {50, 55}
    N (reset lookback bars) in {6, 10}   (30min / 50min on 5m bars)
    Z (dollars above session low, independent univariate check) in {3, 4, 5}

Method: run the REAL engine twice (BASE=block_elite_bull=True production,
UNBLOCK=False) over the widened real-fills window; the ADDED bull cohort is
exactly what the gate removes today (same methodology as bull_unblock_replay_probe,
SLICE 1, which found n=7/WR14.3%/-$241 over 05-21..06-30). This probe widens the
window to the latest OPRA-cached date and asks: within that removed cohort, does
the RSI-extension discriminator separate the winners from the losers? If a
would-PASS subset is net-positive while the would-stay-BLOCKED subset absorbs the
losses, the quality-conditioned exemption is worth proposing. If n is too small to
say anything (expected -- the whole cohort is n~7-15), the honest answer is
INCONCLUSIVE, same as every other bull-frontier probe on this data volume.

RSI computed independently from SPY 5m closes (Wilder alpha=1/14, ewm equivalent,
continuous across the window -- matches crypto/lib/indicators.py's Wilder
convention, TV Pine ta.rsi cross-validated formula) -- NOT read from the engine
(no RSI wired into filters.py today; this probe is exactly the evidence-gathering
step before any such wiring would be considered).

Read-only on production state. No Alpaca calls. No params edits. $0 (cached fills).
Rail-4 CLEAR: research tool + JSON result; touches NO params/orders/filters/
heartbeat/CLAUDE. Pre-reg-then-A/B, per J's own ruling requirement -- ships this
probe + result, NOT a params change (any live wiring needs its own A/B gate).
"""
import sys, os, json, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
from lib.orchestrator import run_backtest
from autoresearch.probe_stats import (
    significance, day_concentration, concentration_flag, slippage_sweep,
    summarize_trades,
)
from autoresearch.bull_unblock_replay_probe import (
    classify_verdict, _key, _date, ANCHOR_DATES,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Widened window: same start as SLICE 1, extended to the latest date with a
# confirmed real-OPRA options cache (verified this fire: backtest/data/options/
# newest contract files are SPY260717*, i.e. 2026-07-17 is the last fully-cached
# trading day -- 07-21/07-22 (this week, incl. the dojo exhibit date) are NOT yet
# option-cached, so real_fills can't price them; SPY-level RSI is still computed
# from the full 07-22 bar file for the reset/session-low math on the priced cohort).
SPY = "data/spy_5m_2026-05-19_2026-07-17.csv"
VIX = "data/vix_5m_2026-05-19_2026-07-17.csv"
START = dt.date(2026, 5, 21)
END = dt.date(2026, 7, 17)

RSI_LENGTH = 14
X_GRID = (65.0, 68.0, 70.0)     # RSI extension threshold
Y_GRID = (50.0, 55.0)           # reset-below threshold
N_GRID = (6, 10)                # trailing bars checked for a reset
Z_GRID = (3.0, 4.0, 5.0)        # dollars above session low (univariate check)


def _bull_cfg(block_elite_bull: bool) -> dict:
    p = json.load(open(os.path.join(REPO, "automation", "state", "params.json")))
    return dict(
        use_real_fills=True,
        no_trade_before=dt.time(9, 35),
        enable_bullish=True,
        block_elite_bull=block_elite_bull,
        block_elite_bull_vix_low=float(p.get("block_elite_bull_vix_low", 0.0)),
        block_elite_bull_vix_high=float(p.get("block_elite_bull_vix_high", 25.0)),
        block_bull_1100_1200=bool(p.get("block_bull_1100_1200", True)),
        block_level_rejection=bool(p.get("block_level_rejection", True)),
        min_triggers_bull=int(p.get("filter_10_min_triggers_bull", 2)),
        strike_offset=-2,
        per_trade_risk_cap_pct=0.30,
        initial_equity=1763.0,
    )


def _wilder_rsi(closes: pd.Series, length: int = RSI_LENGTH) -> pd.Series:
    """Wilder RSI, ewm(alpha=1/length) equivalent -- matches crypto/lib/indicators.py
    convention and TV Pine ta.rsi. Continuous across the window (no per-day reset;
    RSI is a rolling momentum oscillator, not session-anchored like VWAP)."""
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss==0 with avg_gain>0 => RSI=100 (Wilder convention); avg_loss==0 and
    # avg_gain==0 (flat) => RSI=50 (neutral, avoids a NaN/inf artifact).
    rsi = rsi.where(avg_loss != 0.0, avg_gain.apply(lambda g: 100.0 if g > 0 else 50.0))
    return rsi


def _bar_index_at_or_before(spy_df: pd.DataFrame, ts: pd.Timestamp) -> int | None:
    """Index of the last bar whose timestamp_et <= ts (entry bar itself)."""
    idx = spy_df.index[spy_df["timestamp_et"] <= ts]
    return int(idx[-1]) if len(idx) else None


def _session_low_so_far(spy_df: pd.DataFrame, day: dt.date, bar_idx: int) -> float | None:
    day_mask = spy_df["timestamp_et"].dt.date == day
    day_idx = spy_df.index[day_mask & (spy_df.index <= bar_idx)]
    if not len(day_idx):
        return None
    return float(spy_df.loc[day_idx, "low"].min())


def _rsi_features(spy_df: pd.DataFrame, rsi: pd.Series, entry_ts: pd.Timestamp,
                   entry_spot: float, entry_day: dt.date) -> dict | None:
    bar_idx = _bar_index_at_or_before(spy_df, entry_ts)
    if bar_idx is None or pd.isna(rsi.loc[bar_idx]):
        return None
    rsi_at_entry = float(rsi.loc[bar_idx])
    day_mask = spy_df["timestamp_et"].dt.date == entry_day
    day_start_idx = spy_df.index[day_mask].min()
    lo_idx = max(int(day_start_idx), bar_idx - max(N_GRID))
    trail = rsi.loc[lo_idx:bar_idx - 1] if bar_idx > lo_idx else pd.Series([], dtype=float)
    session_low = _session_low_so_far(spy_df, entry_day, bar_idx)
    dollars_above_low = (entry_spot - session_low) if session_low is not None else None
    # per-N minimum RSI in the trailing window (for the reset test at each N)
    min_rsi_by_n = {}
    for n in N_GRID:
        w_lo = max(int(day_start_idx), bar_idx - n)
        window = rsi.loc[w_lo:bar_idx - 1] if bar_idx > w_lo else pd.Series([], dtype=float)
        min_rsi_by_n[n] = float(window.min()) if len(window) and not window.isna().all() else None
    return {
        "rsi_at_entry": round(rsi_at_entry, 1),
        "dollars_above_session_low": round(dollars_above_low, 2) if dollars_above_low is not None else None,
        "min_rsi_by_n": min_rsi_by_n,
    }


def _would_block_a(feat: dict, x: float, y: float, n: int) -> bool:
    """Condition (a): RSI extended (>=X) with no reset (<=Y) in trailing N bars."""
    min_rsi = feat["min_rsi_by_n"].get(n)
    had_reset = (min_rsi is not None) and (min_rsi <= y)
    return feat["rsi_at_entry"] >= x and not had_reset


def _would_block_b(feat: dict, z: float) -> bool:
    """Condition (b): entry is Z+ dollars above the session low (already ran)."""
    d = feat.get("dollars_above_session_low")
    return d is not None and d >= z


def _bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg FDR. Returns per-test significance flags at level q."""
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    thresh = [ (k + 1) / m * q for k in range(m) ]
    sig = [False] * m
    max_k = -1
    for rank, i in enumerate(order):
        if pvals[i] <= thresh[rank]:
            max_k = rank
    for rank, i in enumerate(order):
        sig[i] = rank <= max_k
    return sig


def _welch_p_two_sample(a: list[float], b: list[float]) -> float:
    """Two-sample Welch t-test p-value (approx via normal CDF, no scipy dep)."""
    import math
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 1.0
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = (va / na + vb / nb) ** 0.5
    if se == 0:
        return 1.0
    t = (ma - mb) / se
    # normal approx to two-sided p-value (conservative enough for n<30 disclosure)
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / (2 ** 0.5))))
    return max(0.0, min(1.0, p))


def _score_cohort(name: str, trades: list) -> dict:
    if not trades:
        return {"n": 0, "note": "empty cohort"}
    pnls = [t.dollar_pnl for t in trades]
    rows = [{"dollar_pnl": t.dollar_pnl, "qty": getattr(t, "qty", 1) or 1} for t in trades]
    by_day: dict = {}
    for t in trades:
        by_day[str(_date(t))] = by_day.get(str(_date(t)), 0.0) + t.dollar_pnl
    conc = day_concentration(by_day)
    return {
        "summary": summarize_trades(pnls),
        "significance": significance(len(trades)),
        "day_concentration": conc,
        "concentration_flag": concentration_flag(conc.get("top3_day_pct_of_net")),
        "slippage": slippage_sweep(rows),
    }


def main():
    spy = pd.read_csv(os.path.join(REPO, "backtest", SPY))
    vix = pd.read_csv(os.path.join(REPO, "backtest", VIX))
    spy_full = spy.copy()
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"]).dt.tz_localize(None)
    rsi = _wilder_rsi(spy_full["close"])

    print("=" * 72)
    print("RSI-EXTENSION-BLOCK-ELITE-BULL — pre-registered probe (J dojo ruling 2026-07-21)")
    print(f"window {START}..{END}  (use_real_fills=True)")
    print("=" * 72)

    r_base = run_backtest(spy, vix, start_date=START, end_date=END, **_bull_cfg(True))
    r_unbl = run_backtest(spy, vix, start_date=START, end_date=END, **_bull_cfg(False))

    base_keys = {_key(t) for t in r_base.trades}
    added = [t for t in r_unbl.trades if _key(t) not in base_keys]
    added_bulls = [t for t in added if t.side == "C"]
    print(f"\nremoved-by-block_elite_bull cohort: n={len(added_bulls)} "
          f"(widened window vs SLICE 1's n=7 on 05-21..06-30)")

    # --- feature extraction (RSI at entry, reset windows, dollars-above-low) ---
    feats = []
    for t in added_bulls:
        ts = pd.Timestamp(t.entry_time_et)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        f = _rsi_features(spy_full, rsi, ts, float(t.entry_spot), ts.date())
        feats.append((t, f))
    missing = [t for t, f in feats if f is None]
    feats = [(t, f) for t, f in feats if f is not None]
    if missing:
        print(f"WARNING: {len(missing)} trades had no RSI feature (insufficient warmup/data) -- excluded")

    for t, f in sorted(feats, key=lambda tf: _date(tf[0])):
        wl = "WIN" if t.dollar_pnl > 0 else ("EVEN" if t.dollar_pnl == 0 else "LOSS")
        print(f"  {_date(t)} strike={float(t.strike):.0f} pnl={t.dollar_pnl:+7.1f} {wl:4s}  "
              f"rsi={f['rsi_at_entry']:5.1f}  $abovelow={f['dollars_above_session_low']}")

    # --- pre-registered grid: condition (a) RSI-extension + no-reset ---------
    grid_results_a = []
    pvals_a = []
    for x in X_GRID:
        for y in Y_GRID:
            for n in N_GRID:
                blocked = [t for t, f in feats if _would_block_a(f, x, y, n)]
                kept = [t for t, f in feats if not _would_block_a(f, x, y, n)]
                blocked_pnls = [t.dollar_pnl for t in blocked]
                kept_pnls = [t.dollar_pnl for t in kept]
                p = _welch_p_two_sample(blocked_pnls, kept_pnls) if blocked and kept else 1.0
                pvals_a.append(p)
                grid_results_a.append({
                    "X": x, "Y": y, "N": n,
                    "would_stay_blocked": _score_cohort("blocked", blocked),
                    "would_pass": _score_cohort("kept", kept),
                    "p_value_raw": round(p, 4),
                })
    sig_a = _bh_fdr(pvals_a, q=0.10)
    for r, s in zip(grid_results_a, sig_a):
        r["bh_fdr_significant_q10"] = bool(s)

    # --- condition (b) dollars-above-session-low univariate check -----------
    grid_results_b = []
    pvals_b = []
    for z in Z_GRID:
        blocked = [t for t, f in feats if _would_block_b(f, z)]
        kept = [t for t, f in feats if not _would_block_b(f, z)]
        blocked_pnls = [t.dollar_pnl for t in blocked]
        kept_pnls = [t.dollar_pnl for t in kept]
        p = _welch_p_two_sample(blocked_pnls, kept_pnls) if blocked and kept else 1.0
        pvals_b.append(p)
        grid_results_b.append({
            "Z": z,
            "would_stay_blocked": _score_cohort("blocked", blocked),
            "would_pass": _score_cohort("kept", kept),
            "p_value_raw": round(p, 4),
        })
    sig_b = _bh_fdr(pvals_b, q=0.10)
    for r, s in zip(grid_results_b, sig_b):
        r["bh_fdr_significant_q10"] = bool(s)

    n_total = len(feats)
    n_sufficient = n_total >= 10
    any_bh_sig = any(r["bh_fdr_significant_q10"] for r in grid_results_a + grid_results_b)

    if n_total == 0:
        verdict = "NO_TRADES_TO_SCORE"
    elif not n_sufficient:
        verdict = "INCONCLUSIVE_SAMPLE_TOO_SMALL"
    elif any_bh_sig:
        verdict = "DISCRIMINATOR_SEPARATES_COHORTS_BH_FDR_SIGNIFICANT"
    else:
        verdict = "NO_DISCRIMINATOR_SEPARATION_FOUND"

    print(f"\n--- VERDICT: {verdict} (n={n_total}, sufficient={n_sufficient}, "
          f"any BH-FDR q=0.10 hit={any_bh_sig}) ---")
    if not n_sufficient:
        print("  Same statistical-power ceiling as every prior bull-frontier probe on this "
              "window (n<10) -- an honest null, not a negative finding about the mechanism.")

    # J's own two named exhibits, if they land in a priced window (they may not --
    # 07-21 is outside the option-cache window; reported for completeness only).
    exhibit_note = (
        "J's 11:15/12:21 2026-07-21 exhibits are OUTSIDE this probe's option-cache "
        "window (options cached only through 2026-07-17) -- cannot be individually "
        "priced/scored here; this probe answers the GENERAL discriminator question "
        "on the full removed-by-block_elite_bull population instead of the single "
        "anecdote, per OP-16's 'general population, not one-off exception' discipline."
    )
    print(f"\nNOTE: {exhibit_note}")

    anchor_added = [t for t, f in feats if _date(t) in ANCHOR_DATES]
    anchor_ok = not anchor_added

    out = {
        "probe": "rsi_extension_block_probe",
        "queue_id": "RSI-EXTENSION-BLOCK-ELITE-BULL",
        "generated_at": dt.datetime.now().isoformat(),
        "window": [str(START), str(END)],
        "real_fills": True,
        "removed_by_block_elite_bull_cohort_n": len(added_bulls),
        "feature_extraction_n": n_total,
        "excluded_missing_features_n": len(missing),
        "pre_registered_grid": {
            "X_rsi_extension": list(X_GRID), "Y_reset_below": list(Y_GRID),
            "N_reset_lookback_bars": list(N_GRID), "Z_dollars_above_low": list(Z_GRID),
        },
        "condition_a_rsi_no_reset": grid_results_a,
        "condition_b_dollars_above_low": grid_results_b,
        "anchor_no_regression": anchor_ok,
        "exhibit_note": exhibit_note,
        "verdict": verdict,
        "trades": [
            {"date": str(_date(t)), "strike": float(t.strike), "pnl": round(t.dollar_pnl, 2),
             "rsi_at_entry": f["rsi_at_entry"],
             "dollars_above_session_low": f["dollars_above_session_low"]}
            for t, f in sorted(feats, key=lambda tf: _date(tf[0]))
        ],
    }
    outp = os.path.join(REPO, "analysis", "recommendations",
                        "rsi-extension-block-elite-bull-2026-07-22.json")
    json.dump(out, open(outp, "w"), indent=2)
    print(f"\n[written] {outp}")
    return out


if __name__ == "__main__":
    main()
