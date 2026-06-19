"""Watcher orchestrator — runs all watchers per-bar, logs observations.

Called by:
  - heartbeat (live, market hours): per-tick watcher pass alongside main engine
  - backtest replay: post-hoc on historical bars to populate observation history
  - scheduled task (Sunday): batch-replay over recent days for source-of-truth list

Observation log: automation/state/watcher-observations.jsonl  (append-only)
Per-day summary:  automation/state/watcher-summary.json       (overwritten daily)

Observation row schema:
  {
    "observed_at": "ISO timestamp",
    "bar_timestamp_et": "ISO timestamp",
    "watcher_name": "orb_watcher" | "bullish_watcher" | "pinfade_watcher",
    "setup_name": "ORB_BREAK_LONG" | ...,
    "direction": "long" | "short" | "neutral",
    "entry_price": float,
    "stop_price": float,
    "tp1_price": float,
    "runner_price": float | null,
    "confidence": "low" | "medium" | "high",
    "reason": str,
    "triggers_fired": [str],
    "metadata": {...},
    "would_be_outcome": null,    # filled in by replay scorer once bars after entry exist
    "would_be_pnl_dollars": null
  }
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from . import WatcherSignal
from .orb_watcher import detect_orb_break
from .bullish_watcher import detect_bullish_setup
from .pinfade_watcher import detect_pinfade
from .sniper_watcher import detect_sniper_setup
from .vwap_watcher import detect_vwap_setup
from .opening_drive_fade_watcher import detect_opening_drive_fade_setup
from .v14_enhanced_watcher import detect_v14_enhanced_setup
from .premarket_fail_fade_watcher import detect_premarket_fail_fade_setup
from .shotgun_scalper_watcher import detect_shotgun_scalper_setup
from .tbr_high_vol_watcher import detect_tbr_high_vol_setup
from .bearish_reversal_at_level_watcher import detect_bearish_reversal_at_level
from .level_break_first_strike_watcher import detect_lbfs_setup
from .named_level_wick_bounce_watcher import detect_nlwb_setup
from .double_bottom_morning_low_vol_watcher import detect_db_morning_low_vol_setup
from .momentum_acceleration_highvol_watcher import detect_momentum_accel_highvol_setup
from .double_bottom_base_quiet_watcher import detect_db_base_quiet_setup
from .hs_near_named_level_watcher import detect_hs_near_named_setup
from .hs_watcher import detect_hs_setup
from .fbw_morning_mid_watcher import detect_fbw_morning_mid_setup
from .close_ceiling_fade_watcher import detect_close_ceiling_fade_setup
from .floor_hold_bounce_watcher import detect_floor_hold_bounce_setup
from .rsi_divergence_watcher import detect_rsi_divergence_bull
from .bearish_rejection_morning_watcher import detect_bearish_rejection_morning
from .orb15_watcher import detect_orb15_break  # Reddit ORB-15 adoption 2026-06-14
from .erl_irl_watcher import detect_erl_irl_setup  # Reddit ERL->IRL adoption 2026-06-14
from .named_level_second_test_watcher import detect_named_level_second_test_setup  # 2026-06-18
from .stairstep_continuation_watcher import detect_stairstep_continuation_setup  # 2026-06-18
from ..filters import BarContext

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO.parent
STATE_DIR = ROOT / "automation" / "state"
OBS_LOG = STATE_DIR / "watcher-observations.jsonl"
SUMMARY = STATE_DIR / "watcher-summary.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)


# Per-day dedup state (resets each new day)
_dedup_state: dict[tuple[str, str, str], str] = {}  # (date, watcher, setup_direction) -> best_confidence
_dedup_date: Optional[str] = None

CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def run_all_watchers(
    bar: pd.Series,
    day_bars: pd.DataFrame,
    bar_idx_in_day: int,
    vol_baseline_20: float,
    ctx: BarContext,
    vix_now: float,
    multi_day_rth: Optional[pd.DataFrame] = None,
    ribbon_state_dict: Optional[dict] = None,
) -> list[WatcherSignal]:
    """Run every watcher on the current bar; return all triggered signals.

    Deduplicates same-watcher+setup+direction signals within a day, keeping
    only the FIRST occurrence at each confidence tier. So if ORB_BREAK_LONG
    fires at 10:20 medium then again at 10:25 medium, only 10:20 logs.
    But if 10:20 medium then 10:25 HIGH (upgraded confidence), the 10:25
    upgrade DOES log.
    """
    global _dedup_state, _dedup_date

    bar_date_str = bar["timestamp_et"].date().isoformat() if hasattr(bar["timestamp_et"], "date") else "?"
    if _dedup_date != bar_date_str:
        _dedup_state = {}
        _dedup_date = bar_date_str

    raw_signals: list[WatcherSignal] = []
    orb = detect_orb_break(bar, day_bars, bar_idx_in_day, vol_baseline_20)
    if orb is not None:
        # 16-month finding (2026-05-10): ORB MEDIUM-conf is the sweet spot.
        # Low=$+96/68 fires (noise). Medium=$+589/86 fires. High=$-198/9 fires (consensus trap).
        # Suppress non-medium confidences to keep only the +EV slice.
        if orb.confidence == "medium":
            raw_signals.append(orb)

    # ORB-15 added 2026-06-14 (WATCH-ONLY, Reddit r/FuturesTradingNQ adoption).
    # 15-min opening range (09:30-09:45 ET) vs the deployed 30-min ORB. Self-contained
    # watcher (own state) so the deployed orb_watcher is untouched. Long-only, retest mode.
    # VALIDATION (2026-06-14, 16-mo SPY-space): break exp=-$0.75, retest exp=-$2.37 — net
    # negative; real-fills +$30/trade N=9 Q2-2026 only. DO NOT promote (OP-21 + Rule 9).
    # Spec: strategy/candidates/2026-06-14-reddit-orb15-and-erl-irl-fvg-adoption.md
    try:
        orb15 = detect_orb15_break(bar, day_bars, bar_idx_in_day, vol_baseline_20)
        if orb15 is not None:
            raw_signals.append(orb15)
    except Exception as _e_orb15:
        sys.stderr.write(f"orb15_watcher exception: {type(_e_orb15).__name__}: {_e_orb15}\n")

    bull = detect_bullish_setup(ctx)
    if bull is not None:
        # Bullish: medium-conf is break-even, low+high are net negative.
        # Keep medium-only for observation/learning until 3+ live wins (OP 21).
        if bull.confidence == "medium":
            raw_signals.append(bull)
    ribbon_stack = ctx.ribbon_now.stack if ctx.ribbon_now else None
    # PIN-FADE DISABLED 2026-05-10 (16-month verdict): 1/53 wins = 1.9% WR, -$7,900 net.
    # Classifier identifies pre-breakout chop as fade setup. Needs ground-up rebuild.
    # Re-enable only after grader truthfully models iron-condor theta capture.
    _PINFADE_ENABLED = False
    if _PINFADE_ENABLED:
        pf = detect_pinfade(bar, day_bars, vix_now, ribbon_stack)
        if pf is not None:
            raw_signals.append(pf)

    # === WATCH-ONLY shipped 2026-05-13 (4 new strategies, OP 21 promotion path) ===
    # All run on every bar; signals dedup-merged below.
    # v14_enhanced (ctx only — same data as production v14)
    # NOTE T63 (fire #22 2026-05-14): silent excepts replaced with stderr logging
    # so silent-failure mode 3 can no longer hide a watcher exception. Per OP 25,
    # silent failure is the only true failure. The try/except still prevents one
    # broken watcher from killing the live loop, but EVERY caught exception is
    # surfaced to stderr (visible in Gamma_WatcherLive scheduled-task output).
    try:
        v14e = detect_v14_enhanced_setup(ctx)
        if v14e is not None:
            raw_signals.append(v14e)
    except Exception as _e_v14e:
        sys.stderr.write(f"v14_enhanced_watcher exception: {type(_e_v14e).__name__}: {_e_v14e}\n")

    # BEARISH_REVERSAL_AT_LEVEL added 2026-05-19 (WATCH-ONLY, OP-21 historical gate PASS).
    # Countertrend puts setup: BULL ribbon day + SPY up >=$3 + ★★★ level rejection + vol >=2×.
    # Fires only after 11:00 ET. Historical: 3/3 wins (75% WR on 4 signals). Live: 0/3.
    # Uses ctx only — same data path as v14e, no multi_day_rth dependency.
    try:
        bral = detect_bearish_reversal_at_level(ctx)
        if bral is not None:
            raw_signals.append(bral)
    except Exception as _e_bral:
        sys.stderr.write(f"bearish_reversal_at_level_watcher exception: {type(_e_bral).__name__}: {_e_bral}\n")

    # LEVEL_BREAK_FIRST_STRIKE added 2026-05-19 (WATCH-ONLY, OP-21 VIX-gated).
    # Fires on MIXED-ribbon days when SPY closes >=20c below a named level + vol >=1.5x.
    # VIX<20 variant: 43.3% WR (n=30) — NO EDGE, observe-only.
    # VIX>=20 variant: 100% WR (n=4) — the ratifiable route (gate: N>=15 across >=2 regimes).
    try:
        lbfs = detect_lbfs_setup(ctx)
        if lbfs is not None:
            raw_signals.append(lbfs)
    except Exception as _e_lbfs:
        sys.stderr.write(f"level_break_first_strike_watcher exception: {type(_e_lbfs).__name__}: {_e_lbfs}\n")

    # NAMED_LEVEL_WICK_BOUNCE added 2026-05-20 (WATCH-ONLY, OP-21 historical gate PASS).
    # Fires when SPY 5m bar wicks >=8c below a named support level but closes ABOVE it.
    # Motivated by the 2026-05-19 12:35 ET missed entry: bounce off pre-market low 734.56.
    # Historical: N=157 (PDL proxy), WR=71.3%, zero fires on J loser days (structural guard).
    # Live gate: 0/3 — DO NOT promote until 3+ live J confirmations + real-fills OOS pass.
    # MUTUALLY EXCLUSIVE with LBFS: NLWB close > level, LBFS close < level — cannot co-fire.
    try:
        nlwb = detect_nlwb_setup(ctx)
        if nlwb is not None:
            raw_signals.append(nlwb)
    except Exception as _e_nlwb:
        sys.stderr.write(f"named_level_wick_bounce_watcher exception: {type(_e_nlwb).__name__}: {_e_nlwb}\n")

    # DOUBLE_BOTTOM_MORNING_LOW_VOL added 2026-05-20 (WATCH-ONLY, real-fills FAVORABLE).
    # MORNING 09:35-11:30 ET + VIX<20 + conf<0.60 (pathological band) + NOT_NEAR_NAMED.
    # Real-fills: WR=67.9% (N=109), +$828, FAVORABLE +5.9pp vs proxy. WATCH_STABLE.
    # Live gate: 0/3. Uses ctx.prior_bars sliding window for double_bottom_detector.
    try:
        db_morning = detect_db_morning_low_vol_setup(ctx)
        if db_morning is not None:
            raw_signals.append(db_morning)
    except Exception as _e_dbm:
        sys.stderr.write(f"double_bottom_morning_low_vol_watcher exception: {type(_e_dbm).__name__}: {_e_dbm}\n")

    # MOMENTUM_ACCELERATION_HIGHVOL added 2026-05-20 (WATCH-ONLY, WATCH_FRAGILE).
    # VIX>=20 + ribbon ALIGNED + momentum_acceleration fires. Full RTH 09:35-15:55 ET.
    # Real-fills: WR=42.9% DEGRADED (VIX[20-25) drag). VIX>=25 subset: WR=54.5%, N=11.
    # Live gate: 0/3. Uses ctx.prior_bars sliding window for momentum_acceleration detector.
    try:
        ma_highvol = detect_momentum_accel_highvol_setup(ctx)
        if ma_highvol is not None:
            raw_signals.append(ma_highvol)
    except Exception as _e_mahv:
        sys.stderr.write(f"momentum_accel_highvol_watcher exception: {type(_e_mahv).__name__}: {_e_mahv}\n")

    # DOUBLE_BOTTOM_BASE_QUIET added 2026-05-20 (WATCH-ONLY, real-fills FAVORABLE).
    # Full RTH 09:35-15:55 ET + VIX<20 + conf<0.60 (LOW tier) + NOT_NEAR_NAMED.
    # conf=LOW gate excludes pathological 0.60-0.70 band (OOS WR=46.8%).
    # Real-fills: WR=63.9% (N=122), +$1,755, FAVORABLE +4.4pp vs proxy. WATCH_STABLE.
    # Live gate: 0/3. Most robust watcher (walk-forward STABLE +1.2pp OOS improvement).
    try:
        db_base = detect_db_base_quiet_setup(ctx)
        if db_base is not None:
            raw_signals.append(db_base)
    except Exception as _e_dbb:
        sys.stderr.write(f"double_bottom_base_quiet_watcher exception: {type(_e_dbb).__name__}: {_e_dbb}\n")

    # HEAD_AND_SHOULDERS_NEAR_NAMED_LEVEL — WATCH_FRAGILE (16-month WR=50.0%, NO EDGE).
    # Proximity filter HURT H&S at full scale. Superseded by hs_watcher (no proximity).
    # Kept for observation-only accumulation. No promotion path.
    try:
        hs_near = detect_hs_near_named_setup(ctx)
        if hs_near is not None:
            raw_signals.append(hs_near)
    except Exception as _e_hs:
        sys.stderr.write(f"hs_near_named_level_watcher exception: {type(_e_hs).__name__}: {_e_hs}\n")

    # HEAD_AND_SHOULDERS_BEAR added 2026-05-20 (WATCH_STABLE per OP-21).
    # No proximity filter — fires on ALL H&S tops. Entry 09:40-12:00 ET (morning only).
    # OP-21: historical ✓ walk-forward ✓ real-fills ✓ (WR=73.7% N=19, PnL=+$346).
    # VIX>=25: 80% WR. VIX 15-20: 87.5% WR. Only remaining gate: live 0/3.
    try:
        hs_bear = detect_hs_setup(ctx)
        if hs_bear is not None:
            raw_signals.append(hs_bear)
    except Exception as _e_hs2:
        sys.stderr.write(f"hs_watcher exception: {type(_e_hs2).__name__}: {_e_hs2}\n")

    # CLOSE_CEILING_DISTRIBUTION_FADE added 2026-05-20 evening (WATCH-ONLY, live-accumulation only).
    # L59 pattern: N>=3 consecutive bars testing ★★+ ceiling without closing above →
    # fake breakout bar → buy puts. Historical backtest impossible (no key-levels archive).
    # Reads today's key-levels.json for ★★+ resistance/carry/broken_to_resistance levels.
    # Entry: 09:45-14:30 ET. premium_stop=-0.99 (chart-stop only per L51/L55).
    # Promotion: N>=20 live obs WR>=50% → real-fills → 3 live J wins.
    try:
        ccf = detect_close_ceiling_fade_setup(ctx)
        if ccf is not None:
            raw_signals.append(ccf)
    except Exception as _e_ccf:
        sys.stderr.write(f"close_ceiling_fade_watcher exception: {type(_e_ccf).__name__}: {_e_ccf}\n")

    # FLOOR_HOLD_DISTRIBUTION_BOUNCE added 2026-05-20 evening (WATCH-ONLY, live-accumulation only).
    # Bullish analog of L59 close-ceiling: N>=3 bars wicking to ★★+ support without closing below
    # → fake breakdown bar → buy calls. Wyckoff spring pattern. Historical backtest impossible
    # (no key-levels archive). Reads today's key-levels.json for {"support","carry"} stars>=2.
    # Entry: 09:45-14:30 ET. premium_stop=-0.99 (chart-stop only per L51/L55).
    # Promotion: N>=20 live obs WR>=50% → real-fills → 3 live J wins.
    try:
        fhb = detect_floor_hold_bounce_setup(ctx)
        if fhb is not None:
            raw_signals.append(fhb)
    except Exception as _e_fhb:
        sys.stderr.write(f"floor_hold_bounce_watcher exception: {type(_e_fhb).__name__}: {_e_fhb}\n")

    # NAMED_LEVEL_SECOND_TEST added 2026-06-18 (WATCH-ONLY, OP-21 live-accumulation only).
    # HIGHER-LOW (support → long) / LOWER-HIGH (resistance → short) SECOND test of a named
    # ★★+ level: a first test bounced earlier in the session, then a second test forms a
    # higher low / lower high. DISTINCT from NLWB (single-bar wick reclaim) — this is a
    # two-touch structural sequence. Reads today's key-levels.json (role OR type, stars>=2).
    # Entry 09:45-14:30 ET, cooldown 30m. chart-stop only (L51/L55). high conf w/ vol>=1.1x.
    # Motivating case: 2026-06-18 PML 743.35 (09:45 test#1 → 11:45 +$0.50 higher low → 746.40).
    # Promotion: N>=20 obs WR>=50% → real-fills → 3 live J wins.
    try:
        nlst = detect_named_level_second_test_setup(ctx)
        if nlst is not None:
            raw_signals.append(nlst)
    except Exception as _e_nlst:
        sys.stderr.write(f"named_level_second_test_watcher exception: {type(_e_nlst).__name__}: {_e_nlst}\n")

    # STAIRSTEP_CONTINUATION added 2026-06-18 (WATCH-ONLY, OP-21 n=1 paper observation).
    # Broken named ★★+ level with >=3 strict retests forming LOWER HIGHS (descending → short)
    # or HIGHER LOWS (ascending → long), confirming bar closes on the broken side + correct
    # color. Detects break via role (broken_to_resistance/_support) OR intraday close past the
    # level. Entry 09:45-15:00 ET, cooldown 30m. chart-stop only (L51/L55).
    # Motivating case: 2026-05-07 LH-LH-LH at 735.40 (736.12→735.61→735.41) → -$5.65.
    # Promotion: N>=20 obs WR>=50% → real-fills → 3 live J wins.
    try:
        stair = detect_stairstep_continuation_setup(ctx)
        if stair is not None:
            raw_signals.append(stair)
    except Exception as _e_stair:
        sys.stderr.write(f"stairstep_continuation_watcher exception: {type(_e_stair).__name__}: {_e_stair}\n")

    # RSI_DIVERGENCE_BULL added 2026-05-21 (WATCH-ONLY, Stage-1 scan N=42 WR=81%).
    # Bullish RSI divergence: price LL while RSI makes HL → momentum exhaustion signal.
    # VIX MODERATE (15-20): WR=85.2% N=27. OOS PASS (ratio=0.867). Fails in April trend months.
    # No J anchor coverage → COMPLEMENTARY SIGNAL ONLY (exit enhancer / filter role).
    # Promotion: N>=15 live obs, WR>=70%, >=8 distinct dates, real-fills check.
    try:
        rsi_div = detect_rsi_divergence_bull(ctx)
        if rsi_div is not None:
            raw_signals.append(rsi_div)
    except Exception as _e_rsid:
        sys.stderr.write(f"rsi_divergence_watcher exception: {type(_e_rsid).__name__}: {_e_rsid}\n")

    # BEARISH_REJECTION_MORNING added 2026-05-24 (WATCH-ONLY, 0/3 live obs).
    # J's 4/29 +$342 and 5/04 +$730 morning BEAR entries — ribbon FLIPS to BEAR at named level.
    # Pattern: 09:35-10:55 ET, ribbon=BEAR (flip, not countertrend), level rejection >=15c,
    # vol >=1.5×. DISTINCT from BEARISH_REVERSAL (which is 11:00+ and requires ribbon=BULL).
    # Anchor coverage: 4/29 10:25 +$342, 5/04 10:27 +$730. Both bars_after_trigger=0, at_close.
    # DO NOT promote until 3+ live J confirmations + OP-21 real-fills gate + J ratification.
    try:
        brm = detect_bearish_rejection_morning(ctx)
        if brm is not None:
            raw_signals.append(brm)
    except Exception as _e_brm:
        sys.stderr.write(f"bearish_rejection_morning_watcher exception: {type(_e_brm).__name__}: {_e_brm}\n")

    # ERL->IRL added 2026-06-14 (WATCH-ONLY, Reddit ICT adoption). Liquidity sweep of a
    # named level -> Fair Value Gap displacement -> retrace-into-gap entry -> target next
    # external level. Intraday-compressed, ITM-2 + chart-stop (premium_stop=-0.99 per
    # L51/L55/L74). VIX logged not gated. ctx-based (prior_bars + levels_active).
    # VALIDATION (2026-06-14): SPY-space WR 69% BUT real-fills FAIL — ATM exp=-$25,
    # ITM2 exp=-$59 (Q2-2026); R:R mismatch (chart-stop below swept low). DO NOT promote;
    # needs exit redesign. Spec: strategy/candidates/2026-06-14-reddit-orb15-and-erl-irl-fvg-adoption.md
    try:
        erl = detect_erl_irl_setup(ctx)
        if erl is not None:
            raw_signals.append(erl)
    except Exception as _e_erl:
        sys.stderr.write(f"erl_irl_watcher exception: {type(_e_erl).__name__}: {_e_erl}\n")

    # FAILED_BREAKDOWN_WICK_MORNING_MID added 2026-05-20 (WATCH-ONLY, OP-21 0/3 live obs).
    # failed_breakdown_wick | conf=MID [0.65,0.80) | MORNING 09:35-11:30 ET | vix=ANY.
    # Real-fills PASS: WR=74.3% N=35, P&L=+$455. Walk-forward STABLE (OOS=78.9%>train=68.8%).
    # All 4 OP-21 gates passed. Pending: 3 live J observations before promotion.
    # Uses ctx.prior_bars sliding window — no multi_day_rth dependency. chart-stop only (L55).
    try:
        fbw_mid = detect_fbw_morning_mid_setup(ctx)
        if fbw_mid is not None:
            raw_signals.append(fbw_mid)
    except Exception as _e_fbw:
        sys.stderr.write(f"fbw_morning_mid_watcher exception: {type(_e_fbw).__name__}: {_e_fbw}\n")

    # SHOTGUN_SCALPER added 2026-05-15 (WATCH-ONLY). Three live-trigger tiers:
    # T1 open-bar rejection, T2 named-level reject, T3 trendline break+retest.
    # Single-exit doctrine, no runner. Promotion path per OP 21.
    try:
        sgs = detect_shotgun_scalper_setup(
            bar=bar,
            day_bars=day_bars,
            bar_idx_in_day=bar_idx_in_day,
            ribbon_state_dict=ribbon_state_dict,
            vix_now=vix_now,
        )
        if sgs is not None:
            raw_signals.append(sgs)
    except Exception as _e_sgs:
        sys.stderr.write(f"shotgun_scalper_watcher exception: {type(_e_sgs).__name__}: {_e_sgs}\n")

    # TBR_HIGH_VOL watcher (2026-05-24): dedicated stream for high-volume TBR signals only.
    # Emits watcher_name="tbr_high_vol_watcher", setup_name="TBR_HIGH_VOL".
    # Graded with shotgun_grader.py (single-exit doctrine). WATCH-ONLY.
    try:
        tbr_hv = detect_tbr_high_vol_setup(
            bar=bar,
            day_bars=day_bars,
            bar_idx_in_day=bar_idx_in_day,
            ribbon_state_dict=ribbon_state_dict,
            vix_now=vix_now,
        )
        if tbr_hv is not None:
            raw_signals.append(tbr_hv)
    except Exception as _e_tbr:
        sys.stderr.write(f"tbr_high_vol_watcher exception: {type(_e_tbr).__name__}: {_e_tbr}\n")

    # SNIPER + VWAP + ODF + PFF need multi_day_rth. T62 (fire #22): invariant log-warn
    # when multi_day_rth is None/empty for a live call so silent-failure mode 1
    # becomes visible. Replay callers (e.g., backtest pipeline) intentionally pass
    # multi_day_rth=None and that's fine — they fire the live-only-watcher subset.
    if multi_day_rth is not None and not multi_day_rth.empty:
        # Find bar's index within multi_day_rth (it should be the latest matching ts)
        try:
            matching = multi_day_rth.index[multi_day_rth["timestamp_et"] == bar["timestamp_et"]]
            bar_idx_full = int(matching[-1]) if len(matching) > 0 else -1
        except Exception as _e_match:
            sys.stderr.write(f"multi_day_rth timestamp lookup failed: {type(_e_match).__name__}: {_e_match}\n")
            bar_idx_full = -1

        if bar_idx_full < 0:
            # T62: this branch should be rare in live mode. Diagnose timestamp mismatch
            # (tz-aware vs tz-naive, dtype=object after concat per CLAUDE.md L31).
            sys.stderr.write(
                f"multi_day_rth timestamp NOT MATCHED for bar {bar.get('timestamp_et')!r} "
                f"(multi_day_rth tz={getattr(multi_day_rth['timestamp_et'].dtype, 'tz', None)}, "
                f"bar tz={getattr(bar.get('timestamp_et'), 'tz', None)}). "
                f"Silent-skip of sniper/odf/vwap/pff this bar.\n"
            )

        if bar_idx_full >= 0:
            # SNIPER RETIRED 2026-05-14 per J directive: "if SNIPER is already
            # inside another strat better it can be retired we dont need
            # redundancy we need accuracy and development". v14_enhanced covers
            # the same level-break + ribbon-flip family with better real-fills
            # metrics ($36K wide vs SNIPER's $14K best). Per OP-22 retirement
            # principle. Wrapper file `sniper_watcher.py` preserved for historical
            # reference + the standalone `lib/sniper_detector.py` stays in tree
            # (used by t48_sniper_513_diag.py for offline analysis).
            # try:
            #     snp = detect_sniper_setup(bar, bar_idx_full, multi_day_rth)
            #     if snp is not None:
            #         raw_signals.append(snp)
            # except Exception as _e_snp:
            #     sys.stderr.write(f"sniper_watcher exception: {type(_e_snp).__name__}: {_e_snp}\n")

            try:
                odf = detect_opening_drive_fade_setup(bar, bar_idx_full, multi_day_rth)
                if odf is not None:
                    raw_signals.append(odf)
            except Exception as _e_odf:
                sys.stderr.write(f"opening_drive_fade_watcher exception: {type(_e_odf).__name__}: {_e_odf}\n")

            try:
                vw = detect_vwap_setup(bar, bar_idx_full, multi_day_rth, ribbon_state_dict)
                if vw is not None:
                    raw_signals.append(vw)
            except Exception as _e_vw:
                sys.stderr.write(f"vwap_watcher exception: {type(_e_vw).__name__}: {_e_vw}\n")

            # PREMARKET_FAIL_FADE — extracted from J's 2026-05-13 09:30 trade.
            # First 3 RTH bars only; needs multi-day history for prior-day-high
            # fallback level when bias file is missing premarket resistance.
            try:
                pff = detect_premarket_fail_fade_setup(bar, bar_idx_full, multi_day_rth)
                if pff is not None:
                    raw_signals.append(pff)
            except Exception as _e_pff:
                sys.stderr.write(f"premarket_fail_fade_watcher exception: {type(_e_pff).__name__}: {_e_pff}\n")
    else:
        # T62: live caller passing no multi_day_rth = silent skip of 4 watchers.
        # Replay callers MAY do this intentionally. Live mode (watcher_live.py)
        # should ALWAYS pass multi_day_rth=rth. If we see this in live mode, it
        # means the wiring broke. Detect: heuristic — bar's timestamp is within
        # the last hour and ctx is fully populated.
        try:
            _bts = bar.get("timestamp_et") if isinstance(bar, pd.Series) else None
            _now = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))  # ET
            if _bts is not None and hasattr(_bts, "to_pydatetime"):
                _bts_py = _bts.to_pydatetime()
                if _bts_py.tzinfo is None:
                    _bts_py = _bts_py.replace(tzinfo=dt.timezone(dt.timedelta(hours=-4)))
                _age_sec = (_now - _bts_py).total_seconds()
                if 0 <= _age_sec <= 3600 and ctx is not None:
                    sys.stderr.write(
                        f"WARNING T62: multi_day_rth None/empty in apparent live call "
                        f"(bar age {_age_sec:.0f}s). Skipping sniper/odf/vwap/pff. "
                        f"Replay callers can ignore this.\n"
                    )
        except Exception:
            pass  # T62 invariant check is best-effort; never break the loop

    # Dedup per-day: emit only NEW (watcher, setup, direction) combos OR confidence upgrades
    emitted = []
    for s in raw_signals:
        key = (bar_date_str, s.watcher_name, f"{s.setup_name}_{s.direction}")
        prior_conf = _dedup_state.get(key)
        if prior_conf is None:
            _dedup_state[key] = s.confidence
            emitted.append(s)
        elif CONF_RANK[s.confidence] > CONF_RANK[prior_conf]:
            _dedup_state[key] = s.confidence
            emitted.append(s)
        # else: same or lower confidence, suppress
    return emitted


def log_observation(signal: WatcherSignal, bar_timestamp_et) -> None:
    """Append a single observation to the JSONL log."""
    row = {
        "observed_at": dt.datetime.now().isoformat(),
        "bar_timestamp_et": bar_timestamp_et.isoformat() if hasattr(bar_timestamp_et, "isoformat") else str(bar_timestamp_et),
        "watcher_name": signal.watcher_name,
        "setup_name": signal.setup_name,
        "direction": signal.direction,
        "entry_price": signal.entry_price,
        "stop_price": signal.stop_price,
        "tp1_price": signal.tp1_price,
        "runner_price": signal.runner_price,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "triggers_fired": signal.triggers_fired,
        "metadata": signal.metadata,
        "would_be_outcome": None,        # filled by replay scorer
        "would_be_pnl_dollars": None,
    }
    with OBS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def grade_observation(obs: dict, future_bars: pd.DataFrame) -> dict:
    """Score a watcher observation with proper TP1+runner partial accounting.

    Mimics the orchestrator's TP1+RUNNER doctrine:
      - 50% qty exits at TP1 (locked profit)
      - 50% qty rides as runner with stop moved to BE
      - If runner hits target = full target capture
      - If runner BE-stops = TP1 partial profit only
      - If full stop hits before TP1 = full loss
    """
    if obs.get("would_be_outcome") is not None:
        return obs

    direction = obs["direction"]
    entry = obs["entry_price"]
    stop = obs["stop_price"]
    tp1 = obs["tp1_price"]
    runner = obs["runner_price"]

    if future_bars.empty:
        return obs

    outcome = "open"
    tp1_filled = False
    pnl_dollars = 0.0   # in $ for 1 SPY contract (SPY price * 100)

    for _, b in future_bars.iterrows():
        bar_high = float(b["high"])
        bar_low = float(b["low"])

        if direction == "long":
            # Stop check (BE if tp1 already filled, else original)
            if not tp1_filled and bar_low <= stop:
                outcome = "stopped"
                pnl_dollars = (stop - entry) * 100   # full size loss
                break
            if tp1_filled and bar_low <= entry:
                outcome = "tp1_then_be_stop"
                # TP1 50% locked at tp1 price; runner 50% exited at BE (entry)
                pnl_dollars = ((tp1 - entry) * 0.5 + 0.0) * 100   # only TP1 partial wins
                break
            # Runner check
            if runner is not None and bar_high >= runner:
                outcome = "runner_hit"
                if tp1_filled:
                    pnl_dollars = ((tp1 - entry) * 0.5 + (runner - entry) * 0.5) * 100
                else:
                    pnl_dollars = (runner - entry) * 100   # full size at runner
                break
            # TP1 check (lock partial, move stop to BE, keep runner alive)
            if not tp1_filled and bar_high >= tp1:
                tp1_filled = True
                stop = entry  # BE
        elif direction == "short":
            if not tp1_filled and bar_high >= stop:
                outcome = "stopped"
                pnl_dollars = (entry - stop) * 100
                break
            if tp1_filled and bar_high >= entry:
                outcome = "tp1_then_be_stop"
                pnl_dollars = ((entry - tp1) * 0.5 + 0.0) * 100
                break
            if runner is not None and bar_low <= runner:
                outcome = "runner_hit"
                if tp1_filled:
                    pnl_dollars = ((entry - tp1) * 0.5 + (entry - runner) * 0.5) * 100
                else:
                    pnl_dollars = (entry - runner) * 100
                break
            if not tp1_filled and bar_low <= tp1:
                tp1_filled = True
                stop = entry
        elif direction == "neutral":
            # PIN-FADE: profit if SPY stays within range, loss if breaks
            # FIX 2026-05-10: original grader had no "pinned" win path → 0 wins in 53 fires.
            # Iron condor sells premium; profit = full premium collected if expiring in range.
            # Approximate: nominal premium = $50 collected per condor.
            # If SPY stays in range until end of grading window OR through next 12 bars (1h)
            # whichever first, treat as "pinned" win = +$50.
            # If breaks either side = lose net premium minus collected = -$150 (conservative).
            if bar_high >= stop:
                outcome = "broken_high"
                pnl_dollars = -150.0
                break
            other_boundary = tp1 - (stop - tp1)
            if bar_low <= other_boundary:
                outcome = "broken_low"
                pnl_dollars = -150.0
                break

    if outcome == "open" and tp1_filled:
        # End of window with TP1 filled but runner still open — treat as TP1-only
        outcome = "tp1_partial_open"
        pnl_dollars = ((tp1 - entry) if direction == "long" else (entry - tp1)) * 0.5 * 100
    elif outcome == "open" and direction == "neutral":
        # PIN-FADE that didn't break — won via theta decay (premium collected)
        outcome = "pinned"
        pnl_dollars = 50.0   # nominal premium collected on iron condor

    obs["would_be_outcome"] = outcome
    obs["would_be_pnl_dollars"] = round(pnl_dollars, 2)
    obs["tp1_filled"] = tp1_filled
    return obs
