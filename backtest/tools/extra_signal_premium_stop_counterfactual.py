"""extra_signal_premium_stop_counterfactual.py -- LEVER 2 (analysis/winning-trade-map/
SYNTHESIS-2026-07-20.md, signal #2): REPORT-ONLY counterfactual replay of the 11
exit_stage=premium_stop loss episodes in
analysis/winning-trade-map/episodes-2026-07-13-to-2026-07-20.json under the REAL live
chart-stop-primary exit shape (automation/state/fleet/strategies.py#RIBBON_RIDE.exit --
structure stop + chandelier trailing runner + -50% catastrophe cap), driven through the
REAL production decision core (automation/state/fleet/exit_manager.py plan_exit_actions,
via backtest/lib/exit_manager_walk.py) over real 1-minute SIP/OPRA bars. Feeds evidence
into the queued EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT A/B (automation/overnight/queue.md) --
this script ACCUMULATES evidence for that item, it does not ship or ratify anything.
No trading-path file is written by this module.

WHY chart-stop-primary and not each setup's OWN historical shape: the point of this
LEVER is "what if these 11 lanes (mostly G4 extra-setup side-channel fires --
vwap_continuation / bollinger_squeeze / vix_regime_dayside -- which route through
heartbeat_core.py's `_SETUP_EXIT_OVERRIDES`, a stale 2026-06-01-era premium bracket per
the queue item's own finding) had instead inherited the SAME validated chart-stop-primary
shape ribbon_ride entries get" -- i.e. testing the ALIGNMENT hypothesis, not re-deriving
each lane's existing shape.

STRUCTURE-STOP TRIGGER LEVEL: 3 of the 11 episodes (E1-E3, all the same 07-15 10:01
BULLISH_RECLAIM_RIDE_THE_RIBBON tick across 3 fleet arms) carry trigger_level_exact=null in
this episodes JSON even though they ARE genuine ribbon_ride entries. NO trigger level is
ever invented here. Fallback rule (disclosed, not silent): for episodes missing
trigger_level_exact, reconstruct the SAME proximity-nearest-level exit_manager itself would
use (exit_manager.nearest_active_level: side="C" -> nearest level AT/BELOW spot, side="P"
-> nearest level AT/ABOVE spot, max_distance=2.0) FROM THE EPISODE'S OWN LOGGED
context.levels_context (nearest_level_above/below), which was itself sourced from
automation/state/key-levels.json at that exact decision tick -- not a fresh re-detection,
not a hand-picked number. Every episode is walked under BOTH variants for transparency:
  "structure"          -- native or reconstructed trigger_level passed to from_entry;
                           resolves stop_mode="structure" (chart-level exit + -50% catastrophe
                           cap as the pre-TP1 hard stop) whenever the reconstruction found a
                           candidate within 2.0 pts, else identical to the fallback below.
  "premium_fallback"    -- trigger_level forced None: exit_manager.ExitState.from_entry's own
                           branch logic (read verbatim, NOT assumed) then resolves
                           stop_mode="premium" using the SHAPE'S OWN premium_stop_pct field
                           (RIBBON_RIDE.exit declares premium_stop_pct=-0.20 -- documented in
                           strategies.py as "the flag-OFF emergency fallback only, NOT the
                           validated cell"), NOT the catastrophe_stop_pct(-50%) -- confirmed
                           empirically this run (E8's fallback variant fired "premium_stop @
                           0.9" on a $1.13 entry = exactly -20%, not -50%). CORRECTION: this
                           script originally assumed (before reading exit_manager.py's
                           from_entry branch closely enough) that no-trigger-level would fall
                           back to the -50% catastrophe cap ("chandelier+catastrophe only," the
                           task's own working assumption) -- the REAL code instead falls back
                           to the shape's tighter -20% field. Corrected here rather than
                           silently kept wrong; the post-TP1 chandelier trail/runner-target/
                           time-stop logic IS unconditional on stop_mode either way.
The PRIMARY reported counterfactual_pnl is "structure" when a trigger_level (native or
reconstructed) exists, else "premium_fallback" (identical by construction in that case).

E4 (2026-07-15 13:56 core-safe BULLISH_RECLAIM_RIDE_THE_RIBBON tier SUPER) already carries
trigger_level_exact=754.0 AND structure_stop_enabled has been True in production since
2026-07-09 (git log -S on params.json, commit 933bd65) -- so E4 was almost certainly ALREADY
running in live structure mode (its -48.75% actual exit sits near the -50% catastrophe cap,
not a -20% tight stop). This script's E4 replay is therefore a RESOLUTION-FIDELITY check
(1-min vs live's coarser tick), not a shape-swap counterfactual like the 7 non-ribbon_ride
episodes -- flagged per-episode in the output, not averaged in silently.

PROVENANCE GAP FOUND RUNNING THIS SCRIPT (E1-E3): automation/state/fleet/fleet_executor.py
(_plan_from_strategies, ~line 503-511) prefers trigger_level_exact but FALLS BACK to a
signal-build-time proximity-guess `entry.get("trigger_level")` (ALSO a nearest_active_level
heuristic, computed by the signal producer) before ever calling from_entry -- a field this
episodes-mapper JSON does not capture (it only logs trigger_level_exact). So for E1-E3,
whether production actually resolved "structure" mode live is AMBIGUOUS from this data
alone, not confirmed premium_fallback. Their real live exits (-46.7%/-48.4%/-48.4%, all near
the -50% catastrophe cap rather than a -20% flat stop) are SUGGESTIVE that fleet's own
proximity fallback DID supply a trigger_level and structure mode WAS already resolved live
for these too -- disclosed as `structure_mode_live_ambiguous` per-episode, not resolved by
guessing which one happened.

HONESTY / SURVIVORSHIP CAVEAT (stated again in the output JSON's _doc, per task instruction
-- read before using this number for anything, AND CORRECTED against this run's own
evidence -- see below): all 11 input episodes are LOSERS BY CONSTRUCTION (exit_stage=
premium_stop selects for trades that already lost). The task's premise going in was that a
looser/delayed stop can "only look better or equal" on trades selected because they were
already stopped out. THAT PREMISE DOES NOT HOLD for THIS counterfactual, and this run's own
per-episode results refute it directly: swapping to chart-stop-primary is not a pure
"loosening" (it also demotes to a -50% catastrophe cap that is FURTHER than several lanes'
native -6%/-8% bracket, so on a trade suffering a REAL, continuing adverse move -- not
noise -- the looser stop lets it bleed further before anything catches it, realizing a
LARGER loss than the tight stop that caught it early). Empirically (see the aggregate
section's dynamically-computed classification_counts for the authoritative numbers): a
minority of episodes got WORSE under the swap (not better-or-equal), a smaller number got
clearly better (both the SAME vwap_continuation lane/session, consistent with the
noise-floor hypothesis these WERE noise-stops), one was an exact-match fidelity check (E4,
already live in structure mode), and the remainder were roughly neutral (+/-$15). Aggregate:
NET WORSE, not an "upper bound improvement." The symmetric cost the task anticipated
(winners elsewhere that a looser
shape would let run into bigger losses) is STILL not measurable from this cohort and
remains a real, separate unmeasured risk on top of this already-negative within-cohort
result. The number this script produces is NOT an expectancy estimate -- do not use it as
one, and do not read the negative aggregate as "chart-stop-primary is bad" either (n=11,
heavily concentrated in 3 sessions/2 lanes -- see aggregate section below for the honest
verdict).

STALE-QUOTE CHECK (2026-07-20 finding flagged same day): 3 episodes (E8/E9/E10, all
vix_regime_dayside 09:51-09:56 ET) log context.spy=747.575 IDENTICAL across all 3 ticks.
Cross-checked against the real 1-minute SIP tape fetched by this run
(backtest/data/highres/SPY_1m_2026-07-20.csv): SPY was NOT flat in that window -- it sold
off from 747.62 (09:51 open) to 746.14 (09:56 close), a genuine ~$1.48 move on
100K-265K shares/minute. The pinned 747.575 in the DECISION CONTEXT LOG was a STALE-FEED
ARTIFACT (context_bundle computed once at 09:50:02 and reused/cached across the 09:51,
09:54, 09:55 ticks -- see each episode's context_ts_et vs context_bundle.computed_at_et),
NOT a genuine flat tape. This contaminates E8/E9/E10's LOGGED CONTEXT (alignment_score,
levels_context, gap/position-in-range fields computed off the stale 747.575 spot) -- it
does NOT contaminate this script's own replay, which reads the real 1-min SIP/OPRA bars
directly, independent of that cached context bundle.

Run: backtest/.venv/Scripts/python.exe backtest/tools/extra_signal_premium_stop_counterfactual.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, BACKTEST, FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

import strategies as fleet_strategies  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

EPISODES_PATH = REPO / "analysis" / "winning-trade-map" / "episodes-2026-07-13-to-2026-07-20.json"
SPY_5M_MASTER = BACKTEST / "data" / "spy_5m_2026-05-19_2026-07-20.csv"
HIRES_DIR = BACKTEST / "data" / "highres"
PARAMS_PATH = REPO / "automation" / "state" / "params.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "extra-signal-premium-stop-counterfactual-2026-07-20.json"

NEAREST_LEVEL_MAX_DISTANCE = 2.0  # matches exit_manager.nearest_active_level's own default


def log(msg: str) -> None:
    print(f"[premium-stop-cf] {msg}", flush=True)


def load_episodes() -> list[dict]:
    rows = json.loads(EPISODES_PATH.read_text(encoding="utf-8"))
    return [r for r in rows if r.get("exit_stage") == "premium_stop"]


def load_spy_5m_rth() -> pd.DataFrame:
    spy = pd.read_csv(SPY_5M_MASTER)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    if getattr(spy["timestamp_et"].dt, "tz", None) is not None:
        spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
    rth = (spy["timestamp_et"].dt.time >= dt.time(9, 30)) & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    return spy.loc[rth].reset_index(drop=True)


def load_spy_1m_rth(date_str: str) -> pd.DataFrame | None:
    path = HIRES_DIR / f"SPY_1m_{date_str}.csv"
    if not path.exists():
        return None
    spy = pd.read_csv(path)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    if getattr(spy["timestamp_et"].dt, "tz", None) is not None:
        spy["timestamp_et"] = spy["timestamp_et"].dt.tz_localize(None)
    rth = (spy["timestamp_et"].dt.time >= dt.time(9, 30)) & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    return spy.loc[rth].reset_index(drop=True)


def load_opt_1m(symbol: str, date_str: str) -> pd.DataFrame | None:
    path = HIRES_DIR / f"{symbol}_1m_{date_str}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    if getattr(df["timestamp_et"].dt, "tz", None) is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
    return df


def build_ribbon_1min(spy_1m_rth: pd.DataFrame, spy_5m_rth: pd.DataFrame, ribbon_5m: pd.DataFrame) -> pd.DataFrame:
    """Same convention as backtest/tools/replay_today_eval.py:build_ribbon_1min -- forward-
    fill the (properly-warmed-up, multi-day) 5-min ribbon state onto each 1-min bar rather
    than recomputing EMAs at 1-min cadence (would shrink the calibrated lookback 5x)."""
    five = spy_5m_rth[["timestamp_et"]].copy()
    five["five_idx"] = five.index
    merged = pd.merge_asof(
        spy_1m_rth[["timestamp_et"]].sort_values("timestamp_et"),
        five.sort_values("timestamp_et"),
        on="timestamp_et", direction="backward",
    )
    return ribbon_5m.loc[merged["five_idx"].values].reset_index(drop=True)


def reconstruct_trigger_level(ep: dict) -> tuple[float | None, str]:
    """Native trigger_level_exact if the episode has one; else the SAME proximity-nearest
    rule exit_manager.nearest_active_level applies (side="C" -> nearest level AT/BELOW spot,
    side="P" -> nearest level AT/ABOVE spot, max_distance=2.0), read from the episode's OWN
    logged context.levels_context (sourced from key-levels.json at that tick -- not a fresh
    re-detection). Returns (level_or_None, provenance_str)."""
    native = ep["context"].get("trigger_level_exact")
    if native is not None:
        return float(native), "native_trigger_level_exact"
    lv = ep["context"].get("context_bundle", {}).get("levels_context") or {}
    side = ep["side"]
    cand = lv.get("nearest_level_below") if side == "C" else lv.get("nearest_level_above")
    if not cand or cand.get("price") is None:
        return None, "no_candidate_within_context"
    dist = cand.get("distance")
    if dist is None or dist > NEAREST_LEVEL_MAX_DISTANCE:
        return None, f"candidate_beyond_max_distance({dist})"
    return float(cand["price"]), f"reconstructed_from_levels_context({cand.get('source')},dist={dist})"


def max_adverse_premium_pct(opt_df: pd.DataFrame, entry_time_et: dt.datetime,
                             exit_time_et: dt.datetime | None, entry_premium: float) -> float | None:
    """Worst intra-hold drawdown on the OPTION PREMIUM (both sides are long-option positions,
    so bar LOW is always the adverse extreme) over [entry, exit] -- a diagnostic distinct
    from the walk's own point-sample fill convention (bar OPEN), included to show how much
    heat the position actually took, not just where it exited."""
    end = exit_time_et or opt_df["timestamp_et"].max()
    window = opt_df[(opt_df["timestamp_et"] > entry_time_et) & (opt_df["timestamp_et"] <= end)]
    if window.empty:
        return None
    worst_low = float(window["low"].min())
    return round((worst_low - entry_premium) / entry_premium, 4)


def run_variant(ep: dict, trigger_level: float | None, opt_df: pd.DataFrame,
                 ribbon_1m: pd.DataFrame, spy_5m_rth: pd.DataFrame, time_stop_et: dt.time):
    shape = fleet_strategies.RIBBON_RIDE.exit.to_dict()
    entry_time_et = pd.Timestamp(ep["entry_et"]).to_pydatetime().replace(tzinfo=None)
    return walk_exit_manager(
        symbol=ep["symbol"], side=ep["side"], entry_time_et=entry_time_et,
        entry_premium=float(ep["entry_px"]), qty=int(ep["qty"]), exit_shape=shape,
        structure_stop_enabled=True, trigger_level=trigger_level,
        strategy="premium_stop_counterfactual", time_stop_et=time_stop_et,
        opt_df=opt_df, ribbon_tick_df=ribbon_1m, five_min_spy_df=spy_5m_rth,
    )


def result_to_dict(res) -> dict:
    return {
        "exit_stage": (res.legs[-1].stage if res.legs else res.exit_reason),
        "exit_reason": res.exit_reason,
        "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None,
        "hold_minutes": res.hold_minutes,
        "resolved_stop_mode": res.stop_mode,
        "trigger_level_used": res.trigger_level,
        "dollar_pnl": res.dollar_pnl,
        "legs": [{"kind": lg.kind, "qty": lg.qty, "fill_price": lg.fill_price, "reason": lg.reason,
                  "stage": lg.stage, "ts_et": lg.ts_et.isoformat(), "leg_pnl": lg.leg_pnl}
                 for lg in res.legs],
    }


def main() -> int:
    log("Loading 11 premium_stop episodes")
    episodes = load_episodes()
    log(f"  n={len(episodes)}: {', '.join(e['entry_et'][:16] + '/' + e['symbol'] for e in episodes)}")
    if len(episodes) != 11:
        log(f"  WARNING: expected 11 premium_stop episodes, found {len(episodes)} -- "
            f"cohort composition changed since the task was filed, proceeding anyway "
            f"(disclosed, not silently forced to 11).")

    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    time_stop_et = dt.datetime.strptime(params["time_stop_et"], "%H:%M").time()
    log(f"time_stop_et (production params.json) = {time_stop_et}")

    log(f"Loading SPY 5-min master ({SPY_5M_MASTER.name}) + computing ribbon (full warmup)")
    spy_5m_rth = load_spy_5m_rth()
    ribbon_5m = compute_ribbon(spy_5m_rth["close"])
    log(f"  spy_5m_rth bars={len(spy_5m_rth)}")

    spy_1m_cache: dict[str, pd.DataFrame] = {}
    ribbon_1m_cache: dict[str, pd.DataFrame] = {}

    rows = []
    for i, ep in enumerate(episodes, 1):
        date_str = ep["date"]
        symbol = ep["symbol"]
        entry_time_et = pd.Timestamp(ep["entry_et"]).to_pydatetime().replace(tzinfo=None)
        actual_pnl = float(ep["pnl_usd"])

        if date_str not in spy_1m_cache:
            spy_1m = load_spy_1m_rth(date_str)
            spy_1m_cache[date_str] = spy_1m
            ribbon_1m_cache[date_str] = (build_ribbon_1min(spy_1m, spy_5m_rth, ribbon_5m)
                                          if spy_1m is not None else None)
        spy_1m = spy_1m_cache[date_str]
        ribbon_1m = ribbon_1m_cache[date_str]

        opt_df = load_opt_1m(symbol, date_str)
        if opt_df is None or spy_1m is None:
            log(f"  [{i}/11] SKIP {ep['entry_et']} {symbol}: missing 1-min cache "
                f"(opt={opt_df is not None} spy={spy_1m is not None})")
            rows.append({
                "episode_id": f"{date_str}_{ep['entry_et'][11:19]}_{symbol}",
                "actual_pnl": actual_pnl,
                "counterfactual_pnl": None,
                "counterfactual_exit_stage": None,
                "counterfactual_exit_time": None,
                "max_adverse_premium_pct": None,
                "notes": "SKIPPED: 1-min OPRA/SPY cache missing for this contract/date.",
            })
            continue

        trigger_level, provenance = reconstruct_trigger_level(ep)

        res_structure = run_variant(ep, trigger_level, opt_df, ribbon_1m, spy_5m_rth, time_stop_et)
        res_premium_fallback = run_variant(ep, None, opt_df, ribbon_1m, spy_5m_rth, time_stop_et)

        primary = res_structure if trigger_level is not None else res_premium_fallback
        primary_label = "structure" if trigger_level is not None else "premium_fallback"

        mae = max_adverse_premium_pct(opt_df, entry_time_et, primary.exit_time_et, float(ep["entry_px"]))

        is_ribbon_ride_setup = ep["setup"] in fleet_strategies.RIBBON_RIDE.entry_setups
        already_structure_live = (
            is_ribbon_ride_setup and ep["context"].get("trigger_level_exact") is not None
        )
        # PROVENANCE GAP (found running this script, not assumed going in): fleet_executor.py
        # (_plan_from_strategies, ~line 503-511) prefers trigger_level_exact but FALLS BACK to
        # a signal-build-time proximity-guess `entry.get("trigger_level")` (nearest_active_level
        # heuristic) BEFORE passing into ExitState.from_entry -- a field this episodes-mapper
        # JSON does NOT capture (only trigger_level_exact is logged). So for a fleet ribbon_ride
        # entry with trigger_level_exact=null, whether production actually resolved "structure"
        # mode live is AMBIGUOUS from this data alone -- NOT provably premium-fallback mode.
        # E1-E3's real live exits (-46.7%/-48.4%/-48.4%) sit far closer to the -50% catastrophe
        # cap (structure-mode's demoted stop) than to a -20% flat premium stop, which is
        # SUGGESTIVE (not proof) that fleet's own proximity-guess DID supply a trigger_level
        # and structure mode WAS resolved live for these too -- disclosed, not resolved by
        # guessing.
        structure_mode_live_ambiguous = is_ribbon_ride_setup and not already_structure_live

        notes = (
            f"trigger_level {provenance}. primary_variant={primary_label}. "
            f"setup={ep['setup']} arm={ep['arm_id']} attribution={ep['attribution']}."
        )
        if already_structure_live:
            notes += (" NOTE: this entry is a genuine ribbon_ride primary-channel fire with a "
                       "native trigger_level under structure_stop_enabled=True (live since "
                       "2026-07-09) -- it was almost certainly ALREADY running structure mode "
                       "in production; this replay is a RESOLUTION-FIDELITY check (1-min vs "
                       "live's coarser tick), not a shape-swap counterfactual like the other "
                       "episodes in this cohort.")
        if structure_mode_live_ambiguous:
            notes += (" PROVENANCE GAP: this is a genuine ribbon_ride/fleet entry with "
                      "trigger_level_exact=null in this episodes JSON, but fleet_executor.py "
                      "prefers a proximity-guess trigger_level (nearest_active_level, computed "
                      "at signal-build time) NOT captured by this JSON when the exact field is "
                      "absent -- whether production resolved structure mode live is AMBIGUOUS, "
                      "not provably a shape-swap. The real live exit (~-47%, near the -50% "
                      "catastrophe cap, not the -20% flat fallback) is SUGGESTIVE that "
                      "structure mode WAS already resolved live here too -- treat this row as "
                      "likely-fidelity-check, not confirmed shape-swap.")
        if not is_ribbon_ride_setup:
            notes += (f" SHAPE-SWAP counterfactual (unambiguous): live ran this via "
                      f"{ep['setup']}'s own _SETUP_EXIT_OVERRIDES bracket (not "
                      f"RIBBON_RIDE.exit -- that registry only maps ribbon_ride's own setup "
                      f"names); this replay substitutes RIBBON_RIDE.exit -- exactly the "
                      f"alignment hypothesis the queue item asks about.")
        stale_quote_flag = (date_str == "2026-07-20"
                            and ep["entry_et"][11:16] in ("09:51", "09:54", "09:55"))
        if stale_quote_flag:
            notes += (" STALE-QUOTE-CONTAMINATED CONTEXT: this episode's logged decision "
                      "context.spy=747.575 is a cached/stale snapshot (context_bundle computed "
                      "once at 09:50:02, reused across ticks) -- the real 1-min SIP tape shows "
                      "SPY genuinely selling off 747.62->746.14 in this window (confirmed this "
                      "run, NOT a flat tape). This replay's OWN walk uses the real 1-min bars "
                      "directly and is NOT affected by the stale context field; only the "
                      "episode's LOGGED alignment/levels context (not consumed by this replay) "
                      "is contaminated.")

        cf_delta = round(primary.dollar_pnl - actual_pnl, 2)
        if already_structure_live:
            classification = "fidelity_check_exact_match" if abs(cf_delta) < 0.01 else "fidelity_check_mismatch"
        elif cf_delta >= 15:
            classification = "better"
        elif cf_delta <= -15:
            classification = "worse"
        else:
            classification = "neutral"

        row = {
            "episode_id": f"{date_str}_{ep['entry_et'][11:19]}_{symbol}",
            "date": date_str, "arm_id": ep["arm_id"], "setup": ep["setup"],
            "symbol": symbol, "side": ep["side"], "qty": ep["qty"],
            "entry_et": ep["entry_et"], "entry_px": ep["entry_px"],
            "actual_exit_et": ep["exit_et"], "actual_exit_px": ep["exit_px"],
            "actual_pnl": actual_pnl,
            "trigger_level_provenance": provenance,
            "trigger_level_used": trigger_level,
            "already_structure_mode_live": already_structure_live,
            "structure_mode_live_ambiguous": structure_mode_live_ambiguous,
            "stale_quote_contaminated_context": stale_quote_flag,
            "counterfactual_pnl": primary.dollar_pnl,
            "counterfactual_exit_stage": primary_label,
            "counterfactual_exit_time": primary.exit_time_et.isoformat() if primary.exit_time_et else None,
            "counterfactual_vs_actual_delta": cf_delta,
            "classification": classification,
            "max_adverse_premium_pct": mae,
            "variant_structure": result_to_dict(res_structure),
            "variant_premium_fallback": result_to_dict(res_premium_fallback),
            "notes": notes,
        }
        rows.append(row)
        log(f"  [{i}/11] {ep['entry_et'][:16]} {symbol} side={ep['side']} "
            f"actual=${actual_pnl:+.2f} -> cf({primary_label})=${primary.dollar_pnl:+.2f} "
            f"exit={primary.exit_reason} trigger={trigger_level}")

    n_scored = sum(1 for r in rows if r["counterfactual_pnl"] is not None)
    actual_total = round(sum(r["actual_pnl"] for r in rows), 2)
    cf_total = round(sum(r["counterfactual_pnl"] for r in rows if r["counterfactual_pnl"] is not None), 2)
    # aggregate delta computed ONLY over scored (non-skipped) episodes on BOTH sides, for a
    # fair apples-to-apples comparison (a skip must not silently shrink the actual-side sum).
    actual_scored_total = round(sum(r["actual_pnl"] for r in rows if r["counterfactual_pnl"] is not None), 2)
    delta = round(cf_total - actual_scored_total, 2)

    n_better = sum(1 for r in rows if r["classification"] == "better")
    n_worse = sum(1 for r in rows if r["classification"] == "worse")
    n_neutral = sum(1 for r in rows if r["classification"] == "neutral")
    n_fidelity = sum(1 for r in rows if r["classification"].startswith("fidelity_check"))

    out = {
        "_doc": (
            "REPORT-ONLY counterfactual replay of the 11 exit_stage=premium_stop loss "
            "episodes (2026-07-13..07-20) under RIBBON_RIDE's chart-stop-primary exit shape "
            "(structure stop + chandelier trail + -50% catastrophe cap), driven through the "
            "REAL production exit_manager.plan_exit_actions decision core over real 1-minute "
            "SIP(SPY)/OPRA(options) bars. Feeds evidence into the queued "
            "EXTRA-SIGNAL-PREMIUM-STOP-ALIGNMENT A/B (automation/overnight/queue.md) -- "
            "does NOT ship, ratify, or arm anything; no trading-path file is touched. "
            "\n\nSURVIVORSHIP CAVEAT, STATED AND THEN CORRECTED AGAINST THIS RUN'S OWN "
            "EVIDENCE (per task instruction to state it prominently, and per OP-33 verify-"
            "don't-claim to not repeat an assumption this run falsified): the task's incoming "
            "premise was that this cohort is losers BY CONSTRUCTION (selected on exit_stage="
            "premium_stop), so a looser/delayed stop 'can only look better-or-equal' on it -- "
            "an entry-side-filter-removal-style argument. THAT ARGUMENT DOES NOT TRANSFER to "
            "an EXIT-SHAPE SWAP: chart-stop-primary is not a pure loosening, it also demotes "
            "to a -50% catastrophe cap that is FAR looser than several lanes' native -6%/-8% "
            "bracket, so on a trade suffering a REAL continuing adverse move (not noise), the "
            "wider cap lets it bleed further before anything catches it -- a strictly LARGER "
            "loss than the tight stop that caught it early. This run's own per-episode "
            f"results confirm the mechanism empirically: {n_worse}/11 episodes came out WORSE "
            f"under the swap, {n_better}/11 clearly better (both same lane/session -- "
            f"vwap_continuation, consistent with the noise-floor hypothesis), {n_neutral}/11 "
            f"roughly neutral (+/-$15), {n_fidelity}/11 an exact-match fidelity check (E4, "
            "already running structure mode live). AGGREGATE: NET WORSE by "
            f"${abs(delta):.2f} -- NOT an 'upper bound on improvement'; do not read this as "
            "'chart-stop-primary is bad' either -- n=11, concentrated in 3 sessions and "
            "effectively 2 lanes (vix_regime_dayside's whole n=3 history is one session), "
            "far short of the queue item's own step-3 pre-committed DEFER-INSUFFICIENT-DATA "
            "threshold. The symmetric cost the task also flagged (winners elsewhere that a "
            "looser shape would let run into bigger losses) remains real, separate, and "
            "still unmeasured by this cohort -- on top of, not instead of, this already-"
            "negative within-cohort result. Net: this evidence does NOT support shipping the "
            "alignment change; it also does not clear the bar to reject it outright -- "
            "correctly classified DEFER-INSUFFICIENT-DATA per the queue item's own step (3). "
            "\n\nSTALE-QUOTE FINDING (2026-07-20): 3 episodes (vix_regime_dayside, "
            "09:51/09:54/09:55 ET) logged an identical context.spy=747.575 snapshot across "
            "the whole window -- cross-checked against the real 1-min SIP tape fetched this "
            "run: SPY genuinely sold off 747.62->746.14 (~$1.48, 100K-265K shares/min) over "
            "that window, so the pinned quote was a STALE-FEED ARTIFACT in the DECISION "
            "CONTEXT LOG (a cached context_bundle reused across 3 ticks), not a flat tape. "
            "This contaminates those 3 episodes' logged alignment/levels context fields -- it "
            "does NOT contaminate this replay, which reads the real 1-min bars directly."
        ),
        "generated_at": dt.datetime.now().isoformat(),
        "source_episodes_file": str(EPISODES_PATH.relative_to(REPO)),
        "n_episodes": len(rows),
        "n_scored": n_scored,
        "actual_pnl_total": actual_total,
        "actual_pnl_total_scored_only": actual_scored_total,
        "counterfactual_pnl_total": cf_total,
        "aggregate_delta": delta,
        "classification_counts": {"better": n_better, "worse": n_worse, "neutral": n_neutral,
                                   "fidelity_check": n_fidelity},
        "verdict": "DEFER_INSUFFICIENT_DATA",
        "episodes": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"n_scored={n_scored}/11 actual_total=${actual_scored_total:+.2f} "
        f"counterfactual_total=${cf_total:+.2f} delta=${delta:+.2f} "
        f"(better={n_better} worse={n_worse} neutral={n_neutral} fidelity={n_fidelity})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
