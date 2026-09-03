#!/usr/bin/env python
"""pdt_blocked_counterfactual.py -- runner for the FROZEN prereg
analysis/recommendations/prereg-pdt-blocked-counterfactual-2026-08-11.json
(rule_id PDT-BLOCKED-COUNTERFACTUAL-2026-08-11, status FROZEN_BEFORE_RUNNER since 2026-08-11).

QUESTION (from the prereg, verbatim intent): on PAPER accounts the engine self-imposes the
live PDT rule (3 day-trades / 5 business days under $25k). Did that self-imposed constraint
COST money or SAVE money? MEASUREMENT ONLY -- this script ships nothing and arms nothing.

POPULATION: every status == RISK_DENY_PDT row in automation/state/core-decisions.jsonl that
carries a symbol, deduped to unique (account, symbol, date) intents, keyed by the FIRST
chronological attempt (the engine retries the same blocked intent roughly once a minute while
the setup stays valid; the first attempt is the moment the trigger fired and the entry would
genuinely have been placed -- qty/premium are read from THAT row, matching the prereg's "LOGGED
qty and premium"). Re-derived fresh from the ledger every run -- see load_population().

METHOD: price each blocked intent through the REAL exit_manager via
backtest/tools/multileg_exit_walk.py (calibration v5: fill_mode="extreme", slippage=$0.01,
SPY union feed for last_closed_5m_close so structure/ribbon exits can fire). Exit shape =
that account's config, resolved deterministically from doctrine + git history (see
"SHAPE RESOLUTION" below) -- never re-picked after seeing any P&L number.

SHAPE RESOLUTION (decided from written history BEFORE this script priced a single intent):
  ribbon_ride's exit shape changed exactly once inside the study window. Commit 933bd651
  ("feat(exit): SS-B structure-stop live, both lanes, flag-ON (STOP-B ship 1)"), dated
  2026-07-09, shipped structure_stop_enabled=true + a new ExitShape (catastrophe cap -50%,
  TP1 +100% sell 66%, trailing runner 15% off HWM, arm +5%). `git show 933bd651~1:automation/
  state/fleet/strategies.py` recovers the PRIOR literal: ExitShape(premium_stop_pct=-0.20,
  tp1_premium_pct=1.5, tp1_qty_fraction=0.8, profit_lock_mode="fixed") -- premium-mode only,
  structure_stop_enabled did not exist yet.
    date < 2026-07-09  -> PRE_STOPB_SHAPE (git-recovered literal above), stop_mode="premium"
    date >= 2026-07-09 -> current strategies.by_name("ribbon_ride").exit.to_dict(), with the
                          pre_tp1_* ladder/floor/trail knobs forced OFF (they postdate this
                          window -- pre_tp1_ladder shipped 2026-08-10, AFTER the last intent
                          in this population, 2026-08-07; same precedent already used by the
                          sibling harness backtest/tools/harness_fidelity_anchor.py for the
                          identical reason).
  tp1_qty_fraction is read from the STRATEGY body (0.667), not CLAUDE.md's per-account table
  (0.8 safe / 0.667 bold) -- CLAUDE.md's own account-context section says "TP1 IS NOT A
  PER-ACCOUNT SETTING -- it comes from the STRATEGY (ribbon_ride hardcodes +100%/sell-66%;
  per-arm overrides exist) ... Read the arm's exit-state.json for live truth, never this
  table." No historical per-date exit-state.json snapshot exists to check per-arm overrides
  against, so the STRATEGY body (the thing CLAUDE.md says to trust over its own table, and the
  literal object heartbeat_core._execute's non-isolated-setup branch registers verbatim via
  `_shape = strategies.by_name("ribbon_ride").exit.to_dict()`) is used for BOTH accounts. This
  is disclosed as a DEVIATION from a literal reading of "per-arm 0.8/0.667", not a silent
  substitution.
  Structure vs premium is resolved PER INTENT: structure only if (a) date >= 2026-07-09 AND
  (b) the ledger row itself logged a resolvable trigger_level (trigger_level_exact, or the
  side-appropriate bull_reclaim_level_raw / bear_rejection_level_raw). Absent either condition
  -> premium mode, which is exactly exit_manager.ExitState.from_entry's own null-trigger_level
  fallback (automation/state/fleet/exit_manager.py) -- not a guess invented for this study.
  core-decisions.jsonl did not carry trigger_level_exact at all before the field was added to
  its schema; every 2026-07-08 intent (the day before STOP-B shipped) predates BOTH the field
  and the feature, so premium mode there is doctrine-correct, not a data gap being papered over.

HARNESS VALIDATION (mandatory before trusting any gate number, tonight's standing rule after
a sibling null study's verdict had to be WITHHELD on a 79.3%-agreement walker): replay a sample
of the SAME accounts' ACTUAL PLACED trades from the SAME window through the identical harness
configuration and compare the sign of the replay P&L against the broker-realized `pnl_dollars`
in analysis/trades-enriched.jsonl. Per-row RECORDED stop_mode/trigger_level are used when
present (exit_manager.py's from_entry resolves premium mode whenever no trigger_level exists --
~27% of the real population genuinely ran premium, so assuming structure for all of them would
overstate this harness's own fidelity). Below 85% sign agreement, the counterfactual's gates
are still computed and reported, but the overall verdict is WITHHELD_HARNESS_UNRELIABLE.

EXPLICITLY FORBIDDEN (prereg, verbatim): dropping losing days; re-picking the exit shape after
seeing results; converting a pass into a live-money change (PDT is a real regulatory rule for
live accounts under $25k and is NOT being questioned there).

KNOWN LIMITATION, restated prominently per the prereg (NOT resolved by this script): this is a
NAIVE counterfactual. Taking a blocked trade would have shifted the rolling PDT window and
could have blocked a DIFFERENT later trade. This measures the marginal value of the blocked
intents in ISOLATION, not a full sequential re-simulation. A positive result licenses a forward
trial, never a direct ship. n=18 is below the advisory n>=20 bar -- a pass is SUGGESTIVE, not
sufficient on its own.

$0, deterministic, no network (OPRA bar caches + SPY union feed are pre-fetched on disk; if any
required cache is missing this script reports an honest gap rather than fetching or estimating).
"""
from __future__ import annotations

import glob as _glob
import json
import re
import statistics as stt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/lib", "backtest/tools", "automation/state/fleet", "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import argparse  # noqa: E402
import pandas as pd  # noqa: E402

import strategies as st  # noqa: E402
from lib.option_pricing_real import load_contract_bars  # noqa: E402
from multileg_exit_walk import walk  # noqa: E402
from walker_magnitude_fidelity import (  # noqa: E402 -- WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY
    magnitude_fidelity as _shared_magnitude_fidelity,
    evaluate_magnitude_fidelity,
    stage_decomposition,
)
# WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK (2026-09-03): the alternate walker this
# harness can be pointed at (see --walker below). Bare imports -- backtest/lib and
# automation/state/fleet are already on sys.path (see loop above).
from exit_manager_walk import walk_exit_manager, _reframe_series, FRAME_WALL_V1  # noqa: E402
from exit_manager import TIME_STOP_ET  # noqa: E402
# WALKER-PDT-ANCHOR-FIDELITY-INPUTS (2026-09-03) step 2: REUSE whole_engine_null's
# build_ribbon_tick_df instead of forking a copy -- "setup/scripts" is on sys.path (see loop
# above), same directory this file itself lives in.
import whole_engine_null as wen  # noqa: E402
# step 3: the SAME REST/disk-cache path V9's own get_1m_bars ultimately wraps, for fetching
# 1-minute option bars for this anchor's contracts (network+disk-cache cost, never estimated).
from _option_bars_1min_cache import fetch_1min_cached  # noqa: E402

PREREG_PATH = REPO / "analysis/recommendations/prereg-pdt-blocked-counterfactual-2026-08-11.json"
CORE_LEDGER = REPO / "automation/state/core-decisions.jsonl"
TRADES_ENRICHED = REPO / "analysis/trades-enriched.jsonl"
OUT_JSON = REPO / "analysis/recommendations/pdt-blocked-counterfactual-2026-09-02.json"
OUT_MD = REPO / "analysis/recommendations/pdt-blocked-counterfactual-2026-09-02.md"
# WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK (2026-09-03) RESEARCH variant output -- a
# SEPARATE path so the published 2026-09-02 (multileg) artifact is never overwritten by a
# --walker exit_manager run.
OUT_JSON_EXIT_MGR = REPO / "analysis/recommendations/pdt-blocked-counterfactual-2026-09-03-exit-manager-walk.json"
OUT_MD_EXIT_MGR = REPO / "analysis/recommendations/pdt-blocked-counterfactual-2026-09-03-exit-manager-walk.md"

WALKERS = ("multileg", "exit_manager")

ACCT2ARM = {"safe": "safe-2", "bold": "bold-2"}
# WALKER-PDT-ANCHOR-FIDELITY-INPUTS (2026-09-03) step 2: reverse of ACCT2ARM -- maps
# trades-enriched.jsonl's "arm" field ("safe-2"/"bold-2") back to core-decisions.jsonl's own
# "account" convention ("safe"/"bold"), the key build_ribbon_tick_df's per-tick ribbon read
# needs (see whole_engine_null._core_account_for_arm for the same convention).
ARM2ACCOUNT = {v: k for k, v in ACCT2ARM.items()}
STOP_B_SHIP_DATE = "2026-07-09"          # commit 933bd651, git-verified (see module docstring)
STUDY_WINDOW_START = "2026-07-08"
STUDY_WINDOW_END = "2026-08-07"
HARNESS_SIGN_AGREEMENT_BAR = 0.85         # tonight's standing rule
PER_TRADE_RISK_CAP_PCT = {"safe": 0.30, "bold": 0.50}  # CLAUDE.md Rule 6

# git show 933bd651~1:automation/state/fleet/strategies.py -- the exact PRE-STOP-B literal.
PRE_STOPB_SHAPE = {
    "premium_stop_pct": -0.20, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.8,
    "profit_lock_mode": "fixed", "stop_mode": "premium",
    # dataclass defaults the pre-STOP-B 4-arg literal did not override:
    "runner_target_pct": 2.5, "trail_pct": 0.125, "profit_lock_arm_pct": 0.05,
    "catastrophe_stop_pct": -0.50,
}


# --- SHAPE RESOLUTION (pure, date-keyed -- see module docstring) -------------------------
def canonical_shape(date: str) -> dict:
    """The exit shape ribbon_ride ran on `date`, decided from doctrine/git history alone."""
    if date < STOP_B_SHIP_DATE:
        return dict(PRE_STOPB_SHAPE)
    strat = st.by_name("ribbon_ride")
    base = strat.exit.to_dict() if strat else dict(PRE_STOPB_SHAPE)
    shape = dict(base)
    shape.update(pre_tp1_be_floor_arm_pct=None, pre_tp1_floor_pct=None, pre_tp1_ladder=None,
                 pre_tp1_trail_arm_pct=None, pre_tp1_trail_pct=None)
    return shape


def resolve_trigger_level(date: str, trigger_level) -> float:
    """0.0 -> premium mode inside multileg_exit_walk.walk() (it sets
    structure_stop_enabled=bool(trigger_level) internally); a non-zero value -> structure mode
    IS attempted (still gated by the shape's own stop_mode=="structure" declaration)."""
    if date < STOP_B_SHIP_DATE or trigger_level is None:
        return 0.0
    try:
        v = float(trigger_level)
    except (TypeError, ValueError):
        return 0.0
    return v if v > 0 else 0.0


# --- WALKER SWITCH (WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK, 2026-09-03) -----------
def _five_min_spy_df_for_date(date: str, spy_map: dict) -> pd.DataFrame:
    """{"HH:MM": close} (spy_by_day()'s per-day shape) -> the timestamp_et/close DataFrame
    `exit_manager_walk.walk_exit_manager` requires for `five_min_spy_df`. An empty/missing
    day returns an empty-but-correctly-columned frame (`last_closed_bar_close_at` then
    returns None -- structure/ribbon exits cannot fire, same disclosed limitation the
    no-SPY-feed branch in main() already carries for the multileg walker)."""
    day_map = (spy_map or {}).get(date) or {}
    rows = sorted(day_map.items())
    if not rows:
        return pd.DataFrame({"timestamp_et": pd.Series([], dtype="datetime64[ns]"),
                             "close": pd.Series([], dtype=float)})
    return pd.DataFrame({
        "timestamp_et": [pd.Timestamp(f"{date} {t}") for t, _ in rows],
        "close": [float(c) for _, c in rows],
    })


def _walk_via_exit_manager(fill: dict, shape: dict, bars, *, trigger_level: float = 0.0,
                           spy_map: Optional[dict] = None, exit_slippage: float = 0.01) -> dict:
    """Adapter: prices ONE fill through `backtest/lib/exit_manager_walk.walk_exit_manager`
    (ticks the LIVE exit_manager.plan_exit_actions decision core, per bar) instead of
    `multileg_exit_walk.walk`, returning the SAME {"pnl","legs","n_legs","mfe_pct"} /
    {"error"} contract `walk()` returns so callers do not need to branch on which walker ran.
    Filed under WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK: exit_manager_walk clears the
    magnitude criterion on the V9 anchor (ratio 0.645) where multileg_exit_walk cannot without
    a 1-min-native rewrite (see WALKER-MARKET-STAGE-FILL-ROOT-FIX's negative result,
    automation/overnight/queue.md:2550).

    `trigger_level` is passed through UNCONVERTED (0.0 stays 0.0, never coerced to None) and
    `structure_stop_enabled=bool(trigger_level)` -- the EXACT convention multileg_exit_walk.walk
    already uses (`em.ExitState.from_entry(..., structure_stop_enabled=bool(trigger_level))`),
    so both walkers resolve premium-vs-structure mode identically for the same intent.

    KNOWN STRUCTURAL DEVIATION from multileg's calibration v5, disclosed not papered over:
    multileg applies `slippage` to EVERY leg, limit-style stages included; exit_manager_walk
    applies `exit_slippage` ONLY to its 3 market-style stages (time_stop/ribbon_flip/
    structure_stop) -- tp1/premium_stop/profit_lock_floor/trail/be_stop/runner_target fill at
    the exact triggered level with zero slippage (see that module's FILL-PRICE CONVENTION
    note -- its own docstring already flags this as unfixed-on-purpose, not something this
    adapter should silently work around).

    `ribbon_tick_df` (WALKER-PDT-ANCHOR-FIDELITY-INPUTS step 2, 2026-09-03): when `fill`
    carries an "account" key ("safe"|"bold", core-decisions.jsonl's own convention -- see
    ARM2ACCOUNT), builds a REAL per-tick ribbon series via
    `whole_engine_null.build_ribbon_tick_df` (imported, not copied) reindexed onto THIS bars
    frame's own timestamps -- the SAME mechanism V9's `ribbon_account` kwarg already uses, so
    ribbon_flip exits are reachable here too, not structurally dead. `bars`' timestamp column
    is frame-normalized to wall-v1 first (`_reframe_series`) so it merges cleanly against the
    (tz-naive) ribbon series regardless of whether `bars` came from `load_contract_bars`
    (raw tz-aware) or `_option_bars_1min_cache.fetch_1min_cached` (already tz-naive) --
    `walk_exit_manager` itself reframes `opt_df` internally the same way (default
    frame="wall-v1"), so this is the SAME normalization, not a second independent one. A fill
    with no "account" key (any caller predating this fold, or a caller genuinely lacking one)
    keeps `ribbon_tick_df=None` -- backward-compatible default, not a silent behavior change
    for those callers.

    `mfe_pct` is reported as None (not fabricated): walk_exit_manager does not expose a
    per-tick high-water-mark, and this field is non-load-bearing for G1-G4 (fabricating an
    approximation from leg fill prices alone would be a WORSE number than an honest gap).

    `walked_stage` (WALKER-PDT-ANCHOR-FIDELITY-INPUTS step 1, 2026-09-03): the FULL
    "+"-joined leg-stage sequence (e.g. "tp1+trail"), not just the last leg -- matches
    `recorded_stage`'s own already-compound convention so `stage_decomposition` compares
    like-for-like (see that function's docstring; the old last-leg-only value inflated the
    PDT anchor's disagree count via a first-token mismatch that was never a real event
    disagreement -- WALKER-STAGE-DISAGREE-RESIDUAL-2026-09-03.md Finding 0)."""
    entry = float(fill["entry_premium"])
    qty = int(fill["qty"])
    sym = fill["symbol"]
    side = "P" if "P00" in sym else "C"
    entry_time_et = pd.Timestamp(f"{fill['date']} {fill['entry_time']}")
    five_min_spy_df = _five_min_spy_df_for_date(fill["date"], spy_map or {})
    account = fill.get("account")
    ribbon_tick_df = None
    if account:
        reframed = bars.assign(timestamp_et=_reframe_series(bars["timestamp_et"], FRAME_WALL_V1))
        ribbon_tick_df = wen.build_ribbon_tick_df(reframed, fill["date"], account)
    try:
        result = walk_exit_manager(
            symbol=sym, side=side, entry_time_et=entry_time_et, entry_premium=entry, qty=qty,
            exit_shape=shape, structure_stop_enabled=bool(trigger_level),
            trigger_level=trigger_level, strategy=str(fill.get("strategy", "RIBBON")),
            time_stop_et=TIME_STOP_ET, opt_df=bars, ribbon_tick_df=ribbon_tick_df,
            five_min_spy_df=five_min_spy_df, exit_slippage=exit_slippage,
        )
    except Exception as exc:  # noqa: BLE001 -- mirror walk()'s own error-as-data contract
        return {"error": f"{type(exc).__name__}: {exc}", "pnl": 0.0, "legs": []}
    if not result.resolved and result.exit_reason == "no_bars_after_entry":
        return {"error": "no bars at/after entry", "pnl": 0.0, "legs": []}
    legs = [{"t": leg.ts_et.strftime("%H:%M"), "stage": leg.stage, "qty": leg.qty,
            "px": leg.fill_price, "pnl": leg.leg_pnl} for leg in result.legs]
    return {"pnl": result.dollar_pnl, "legs": legs, "n_legs": len(legs), "mfe_pct": None,
           "walked_stage": ("+".join(leg["stage"] for leg in legs) if legs else result.exit_reason)}


def _price_via_walker(walker: str, fill: dict, shape: dict, bars, *, trigger_level: float,
                      spy_map: dict, exit_slippage: Optional[float] = None) -> dict:
    """Dispatch point. `walker="multileg"` (the default everywhere in this file) makes the
    EXACT SAME call multileg_exit_walk.walk() always got -- byte-identical to the published
    2026-09-02 run; `walker="exit_manager"` is the WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-
    WALK research path.

    `exit_slippage` (WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION, 2026-09-03): additive override,
    `None` (default) means "use `_walk_via_exit_manager`'s own default (0.01)" -- byte-identical
    for every existing caller that never passes this. Only meaningful for `walker="exit_manager"`
    -- the multileg walker's own `slippage=0.01` kwarg above is untouched by this parameter
    (multileg already applies slippage to every leg, not just market-style stages; there is no
    market-stages-only asymmetry to ablate on that walker)."""
    if walker == "exit_manager":
        kwargs = {} if exit_slippage is None else {"exit_slippage": exit_slippage}
        return _walk_via_exit_manager(fill, shape, bars, trigger_level=trigger_level,
                                      spy_map=spy_map, **kwargs)
    return walk(fill, shape, bars, trigger_level=trigger_level, fill_mode="extreme",
               spy_closes=spy_map.get(fill["date"]), slippage=0.01)


# --- POPULATION (re-derived fresh from the ledger every run) -----------------------------
def load_population(ledger_path: Path = CORE_LEDGER) -> tuple[list[dict], dict]:
    attempts: list[dict] = []
    with open(ledger_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "RISK_DENY_PDT" not in line:  # cheap prefilter, ledger is large
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            ex = row.get("exec") or {}
            if ex.get("status") != "RISK_DENY_PDT":
                continue
            sym = ex.get("symbol")
            if not sym:
                continue
            attempts.append({
                "ts_et": row.get("ts_et"), "account": row.get("account"), "symbol": sym,
                "qty": ex.get("qty"), "premium": ex.get("premium"), "reason": ex.get("reason"),
                "side": row.get("side"), "setup": row.get("setup"),
                "trigger_level_exact": row.get("trigger_level_exact"),
                "bear_rejection_level_raw": row.get("bear_rejection_level_raw"),
                "bull_reclaim_level_raw": row.get("bull_reclaim_level_raw"),
            })

    uniq: dict[tuple, list[dict]] = {}
    for a in attempts:
        date = (a["ts_et"] or "")[:10]
        key = (a["account"], a["symbol"], date)
        uniq.setdefault(key, []).append(a)

    intents: list[dict] = []
    for (account, symbol, date), rows in sorted(uniq.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1])):
        rows_sorted = sorted(rows, key=lambda r: r["ts_et"] or "")
        first = rows_sorted[0]
        side = first.get("side") or ("P" if "P00" in symbol else "C")
        trig = first.get("trigger_level_exact")
        if trig is None:
            trig = first.get("bull_reclaim_level_raw") if side == "C" else first.get("bear_rejection_level_raw")
        equity = None
        m = re.search(r"equity\s*\$([\d,]+)", first.get("reason") or "")
        if m:
            equity = float(m.group(1).replace(",", ""))
        intents.append({
            "account": account, "arm": ACCT2ARM.get(account, account), "symbol": symbol,
            "date": date, "entry_time": (first["ts_et"] or "")[11:], "side": side,
            "qty": int(first["qty"]), "entry_premium": float(first["premium"]),
            "setup": first.get("setup"), "n_attempts": len(rows_sorted),
            "trigger_level": trig, "equity_at_block": equity,
        })
    counts = {
        "n_attempts_top_level": len(attempts),
        "n_unique_intents": len(intents),
        "date_range": [intents[0]["date"], intents[-1]["date"]] if intents else None,
        "n_days": len({i["date"] for i in intents}),
    }
    return intents, counts


# --- PRICING ------------------------------------------------------------------------------
def spy_by_day() -> dict:
    """{date: {"HH:MM": closed 5m SPY close}} -- union of every spy_5m_*.csv cache, same
    de-dup/normalize logic as backtest/tools/harness_fidelity_anchor.py#spy_by_day (kept as an
    independent copy here rather than importing that module, since this script must stand alone
    even if that sibling tool is later removed)."""
    frames = []
    for fpath in _glob.glob(str(REPO / "backtest/data/spy_5m_*.csv")):
        try:
            d = pd.read_csv(fpath)
            ts = pd.to_datetime(d["timestamp_et"], format="mixed")
            ts = ts.dt.tz_convert("America/New_York") if ts.dt.tz is not None \
                else ts.dt.tz_localize("America/New_York")
            d["ts"] = ts
            frames.append(d)
        except Exception:  # noqa: BLE001
            continue
    if not frames:
        return {}
    best = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts"]).sort_values("ts")
    out: dict = {}
    for day, g in best.groupby(best["ts"].dt.strftime("%Y-%m-%d")):
        out[day] = dict(zip(g["ts"].dt.strftime("%H:%M"), g["close"].astype(float)))
    return out


def price_intent(intent: dict, bars: pd.DataFrame, spy_map: dict,
                 walker: str = "multileg", exit_slippage: Optional[float] = None) -> dict:
    shape = canonical_shape(intent["date"])
    trig = resolve_trigger_level(intent["date"], intent["trigger_level"])
    fill = {"entry_premium": intent["entry_premium"], "qty": intent["qty"],
            "symbol": intent["symbol"], "date": intent["date"],
            "entry_time": intent["entry_time"], "strategy": intent.get("setup") or "RIBBON",
            "account": intent.get("account")}
    return _price_via_walker(walker, fill, shape, bars, trigger_level=trig, spy_map=spy_map,
                             exit_slippage=exit_slippage)


def run_counterfactual(intents: list[dict], spy_map: dict,
                       walker: str = "multileg") -> tuple[list[dict], list[str]]:
    priced: list[dict] = []
    deviations: list[str] = []
    for it in intents:
        if it["date"] >= STOP_B_SHIP_DATE and not it.get("trigger_level"):
            deviations.append(
                f"{it['symbol']} ({it['date']}, {it['account']}): post-STOP-B date but the "
                f"ledger row logged no resolvable trigger_level -- ran PREMIUM mode as a "
                f"genuine data gap (schema/telemetry miss), not a policy choice. Priced "
                f"anyway (disclosed here, not hidden).")
        bars = load_contract_bars(it["symbol"])
        if bars is None or bars.empty:
            deviations.append(f"NO CACHED BARS for {it['symbol']} ({it['date']}) -- intent "
                               f"excluded, not estimated/substituted.")
            continue
        res = price_intent(it, bars, spy_map, walker=walker)
        if "error" in res:
            deviations.append(f"walk() error on {it['symbol']} ({it['date']}): {res['error']} "
                               f"-- intent excluded, not estimated/substituted.")
            continue
        cap_pct = PER_TRADE_RISK_CAP_PCT.get(it["account"])
        notional = it["entry_premium"] * it["qty"] * 100.0
        capital_flag = None
        if it.get("equity_at_block") and cap_pct:
            cap_dollars = it["equity_at_block"] * cap_pct
            if notional > cap_dollars:
                capital_flag = (f"notional ${notional:,.0f} > {cap_pct:.0%} risk cap "
                                 f"${cap_dollars:,.0f} at equity ${it['equity_at_block']:,.0f}")
        priced.append({**it, "pnl": res["pnl"], "n_legs": res.get("n_legs", 0),
                       "legs": res.get("legs", []), "mfe_pct": res.get("mfe_pct"),
                       "notional": round(notional, 2), "capital_flag": capital_flag})
    return priced, deviations


# --- GATES (pure functions -- guard-tested on synthetic inputs) ---------------------------
def day_pnls_from_priced(priced: list[dict]) -> dict:
    out: dict = {}
    for p in priced:
        out[p["date"]] = out.get(p["date"], 0.0) + p["pnl"]
    return out


def compute_gates(day_pnls: dict) -> dict:
    """G1-G4 exactly as defined in the frozen prereg. Pure -- no I/O, no P&L computation of
    its own. day_pnls: {date: net $ for that day}."""
    net_total = sum(day_pnls.values()) if day_pnls else 0.0
    profitable_days = sum(1 for v in day_pnls.values() if v > 0)
    losing_days = sum(1 for v in day_pnls.values() if v < 0)
    best_day_name = max(day_pnls, key=day_pnls.get) if day_pnls else None
    best_day_pnl = day_pnls.get(best_day_name, 0.0) if best_day_name else 0.0

    g1 = net_total > 0
    g2 = profitable_days > losing_days
    g3 = (net_total - best_day_pnl) >= 0
    if net_total > 0:
        g4_pct = best_day_pnl / net_total
        g4 = best_day_pnl <= 0.6 * net_total
    else:
        g4_pct = None
        g4 = False  # "60% of a POSITIVE net" is undefined when net isn't positive -> can't pass

    return {
        "G1_net_positive": {"pass": g1, "net_total": round(net_total, 2)},
        "G2_day_balance": {"pass": g2, "profitable_days": profitable_days,
                           "losing_days": losing_days, "flat_days": len(day_pnls) - profitable_days - losing_days},
        "G3_drop_best": {"pass": g3, "net_minus_best_day": round(net_total - best_day_pnl, 2),
                         "best_day": best_day_name, "best_day_pnl": round(best_day_pnl, 2)},
        "G4_not_concentrated": {"pass": g4, "best_day_pct_of_net": (round(g4_pct, 4) if g4_pct is not None else None),
                                "note": None if net_total > 0 else "net not positive -- 'X% of a positive net' is undefined, gate cannot pass"},
        "all_pass": bool(g1 and g2 and g3 and g4),
        "n_days": len(day_pnls),
    }


# --- HARNESS VALIDATION (validate the validator, before trusting any gate) ---------------
def load_anchor_sample(window_start: str = STUDY_WINDOW_START,
                       window_end: str = STUDY_WINDOW_END) -> list[dict]:
    rows: list[dict] = []
    with open(TRADES_ENRICHED, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("_meta"):
                continue
            if r.get("arm") not in ("safe-2", "bold-2"):
                continue
            if not (window_start <= r["date"] <= window_end):
                continue
            if r.get("attribution") != "engine":
                continue
            if r.get("pnl_dollars") is None or r.get("entry_px") is None or not r.get("qty"):
                continue
            rows.append(r)
    return rows


def anchor_trigger_level(row: dict) -> float:
    """Honors the row's OWN recorded stop_mode when present (tonight's instruction) instead
    of assuming structure; falls back to the date rule only when stop_mode is unrecorded."""
    mode = row.get("stop_mode")
    trig = row.get("trigger_level")
    if mode == "structure":
        return float(trig) if trig is not None else 0.0
    if mode == "premium":
        return 0.0
    return resolve_trigger_level(row["date"], trig)


def _load_anchor_bars(sym: str, date: str, bar_resolution: str, cache: dict):
    """5-min (default, BYTE-IDENTICAL to every prior call: `load_contract_bars(sym)`, keyed by
    symbol alone) or 1-min (WALKER-PDT-ANCHOR-FIDELITY-INPUTS step 3, 2026-09-03: REAL Alpaca
    1-min option bars via `_option_bars_1min_cache.fetch_1min_cached`, a genuine network+disk-
    cache fetch, keyed by (symbol,date) -- a 0DTE contract trades exactly one date, but the
    tuple key is the honest cache contract regardless). Returns None on any fetch failure
    (never estimated/substituted) -- caller counts it in `skipped_no_bars`."""
    cache_key = sym if bar_resolution == "5min" else (sym, date)
    if cache_key not in cache:
        try:
            if bar_resolution == "1min":
                bars_1m, _source = fetch_1min_cached(sym, date)
                cache[cache_key] = bars_1m
            else:
                cache[cache_key] = load_contract_bars(sym)
        except Exception:  # noqa: BLE001
            cache[cache_key] = None
    return cache[cache_key]


def harness_validation(walker: str = "multileg", bar_resolution: str = "5min",
                       exit_slippage: Optional[float] = None) -> dict:
    """`walker` (WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK, 2026-09-03): "multileg"
    (default) is BYTE-IDENTICAL to every prior call of this function -- same `walk()` call,
    same arguments, same order. "exit_manager" routes the SAME 43-row anchor (same
    load_anchor_sample/canonical_shape/anchor_trigger_level resolution -- each row's OWN
    RECORDED stop_mode is honoured identically either way) through
    `exit_manager_walk.walk_exit_manager` instead.

    `bar_resolution` (WALKER-PDT-ANCHOR-FIDELITY-INPUTS step 3, 2026-09-03): "5min" (default,
    byte-identical -- see `_load_anchor_bars`) or "1min" (real fetch/cache of 1-minute option
    bars for this anchor's distinct (symbol,date) pairs). Orthogonal to `walker` -- either
    walker can be asked to walk on either resolution, though only "exit_manager" is what this
    queue item's own criterion is scored against.

    `exit_slippage` (WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION, 2026-09-03): additive override
    forwarded to `_price_via_walker`/`_walk_via_exit_manager`. `None` (default) is byte-
    identical to every prior call (uses that adapter's own 0.01 default); only has an effect
    when `walker="exit_manager"`."""
    rows = load_anchor_sample()
    spy_map = spy_by_day()
    cache: dict = {}
    results: list[dict] = []
    skipped_no_bars = 0
    for r in rows:
        sym = r["symbol"]
        bars = _load_anchor_bars(sym, r["date"], bar_resolution, cache)
        if bars is None or bars.empty:
            skipped_no_bars += 1
            continue
        shape = canonical_shape(r["date"])
        mode = r.get("stop_mode")
        if mode in ("structure", "premium"):
            shape = dict(shape)
            shape["stop_mode"] = mode
        trig = anchor_trigger_level(r)
        fill = {"entry_premium": r["entry_px"], "qty": int(r["qty"]), "symbol": sym,
                "date": r["date"], "entry_time": r["entry_ts_et"][11:19], "strategy": "RIBBON",
                "account": ARM2ACCOUNT.get(r["arm"])}
        res = _price_via_walker(walker, fill, shape, bars, trigger_level=trig, spy_map=spy_map,
                                exit_slippage=exit_slippage)
        if "error" in res:
            continue
        actual = float(r["pnl_dollars"])
        replay = res["pnl"]
        walked_stage = (res.get("walked_stage") if "walked_stage" in res
                        else ("+".join(leg["stage"] for leg in res["legs"]) if res.get("legs") else None))
        results.append({
            "date": r["date"], "arm": r["arm"], "symbol": sym, "stop_mode": mode,
            "actual": actual, "replay": replay, "err": round(replay - actual, 2),
            "sign_ok": (actual > 0) == (replay > 0) or abs(replay - actual) < 1e-9,
            "recorded_stage": r.get("exit_reason"), "walked_stage": walked_stage,
        })
    n = len(results)
    if n == 0:
        return {"n": 0, "sign_agreement": None, "skipped_no_bars": skipped_no_bars,
                "note": "no anchor rows could be replayed"}
    sign_ok = sum(1 for r in results if r["sign_ok"])
    errs = [r["err"] for r in results]
    # MAGNITUDE FIDELITY (2026-09-03, WALKER-MAGNITUDE-BIAS-VS-SIGN-FIDELITY). This IS the
    # study whose own anchor run first surfaced the gap: 95.35% sign agreement on this exact
    # anchor shape while replaying -$2,201.60 against an actual -$538.00 (~4x aggregate-
    # negative). `magnitude_fidelity_verdict` is a SECOND, INDEPENDENT read reported alongside
    # `harness_reliable` below -- it does NOT feed that gate. `harness_reliable` stays keyed to
    # sign_agreement >= HARNESS_SIGN_AGREEMENT_BAR exactly as before this fold.
    mag = _shared_magnitude_fidelity([(r["actual"], r["replay"]) for r in results])
    # STAGE DECOMPOSITION (WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK): localizes a
    # magnitude defect to "picked the wrong event" (stage disagreement) vs "priced the right
    # event wrong" (stage agreement, pure pricing/fill-convention gap) -- the diagnostic the
    # queue item asks for when the anchor FAILS the magnitude criterion.
    stagedecomp = stage_decomposition(results, real_key="actual", walk_key="replay",
                                      recorded_stage_key="recorded_stage",
                                      walked_stage_key="walked_stage")
    return {
        "walker": walker,
        "exit_slippage_requested": exit_slippage,  # None -> adapter's own default (0.01)
        "n": n, "skipped_no_bars": skipped_no_bars,
        "sign_agreement": round(sign_ok / n, 4),
        "actual_total": round(sum(r["actual"] for r in results), 2),
        "replay_total": round(sum(r["replay"] for r in results), 2),
        "median_abs_error": round(stt.median([abs(e) for e in errs]), 2),
        "magnitude_fidelity": mag,
        "magnitude_fidelity_verdict": evaluate_magnitude_fidelity(mag),
        "stage_decomposition": stagedecomp,
        "rows": results,
    }


def exit_manager_magnitude_gate(hv: dict) -> bool:
    """Pure gate: may the exit_manager-walker counterfactual's own G1-G4 verdict be trusted?
    Only True on an explicit PASS from evaluate_magnitude_fidelity -- FAIL and INSUFFICIENT
    (below the n floor, or an undivideable ratio) both withhold."""
    return hv.get("magnitude_fidelity_verdict") == "PASS"


# --- ORCHESTRATION --------------------------------------------------------------------
def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--walker", choices=WALKERS, default="multileg",
                    help="pricing walker. 'multileg' (default) is BYTE-IDENTICAL to the "
                         "published 2026-09-02 run (multileg_exit_walk.walk). "
                         "'exit_manager' is the WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK "
                         "research variant (backtest/lib/exit_manager_walk.walk_exit_manager) "
                         "-- gated on its own anchor clearing walker_magnitude_fidelity's "
                         "PASS criterion before any G1-G4 number is trusted, and writes to "
                         "*-exit-manager-walk.{json,md} instead of the published artifact.")
    ap.add_argument("--bars", choices=("5min", "1min"), default="5min",
                    help="anchor bar resolution for harness_validation only "
                         "(WALKER-PDT-ANCHOR-FIDELITY-INPUTS step 3). '5min' (default) is "
                         "BYTE-IDENTICAL to every prior run (option_pricing_real."
                         "load_contract_bars). '1min' fetches/caches real Alpaca 1-min option "
                         "bars for this anchor's contracts -- a genuine network+disk-cache "
                         "cost, single-reader OPRA cache. Does NOT affect the blocked-cohort "
                         "pricing pass (run_counterfactual) or G1-G4 -- anchor-only.")
    ap.add_argument("--exit-slippage", default=None,
                    help="WALKER-EXIT-SLIPPAGE-ASYMMETRY-ABLATION (2026-09-03): override the "
                         "exit_manager walker's exit_slippage $ constant (applied only to its "
                         "3 market-style stages -- time_stop/ribbon_flip/structure_stop; see "
                         "exit_manager_walk.py's FILL-PRICE CONVENTION note). Omit (default) "
                         "for byte-identical behavior (_walk_via_exit_manager's own 0.01 "
                         "default). A float (e.g. '0' or '0.02') sets it directly. The literal "
                         "string 'live' resolves it from the exit-side of the fill-latency "
                         "instrument (analysis/pain-ledger/latency.json) -- FAILS LOUDLY "
                         "(non-zero exit, no silent fallback) if that instrument carries no "
                         "dollar-denominated exit-slippage field, rather than guessing. No "
                         "effect on --walker multileg (disclosed, not silently ignored).")
    return ap.parse_args(argv)


def _resolve_exit_slippage_arg(raw: Optional[str]) -> Optional[float]:
    """CLI value -> float | None. `None`/unset -> None (byte-identical default, see
    harness_validation's own docstring). `"live"` looks up a dollar-denominated exit-slippage
    field on the fill-latency instrument (analysis/pain-ledger/latency.json) -- that file (as
    of 2026-09-03) is a PIPELINE-TIMING instrument (seconds between order stages, entry fills
    only, scoped to arms safe-3/risky-1/risky-3) with no such field at all, so this raises
    LOUDLY rather than silently treating 'live' as 0 or as the default -- per OP no-silent-
    fallback discipline. Anything else parses as a float, letting a bad value fail with
    Python's own ValueError rather than a swallowed default."""
    if raw is None:
        return None
    if raw.strip().lower() == "live":
        latency_path = REPO / "analysis" / "pain-ledger" / "latency.json"
        doc = json.loads(latency_path.read_text(encoding="utf-8")) if latency_path.exists() else {}
        rows = doc.get("rows") or []
        candidate_keys = [k for k in (rows[0].keys() if rows else [])
                          if "exit" in k.lower() and "slip" in k.lower()]
        if not candidate_keys:
            raise SystemExit(
                f"--exit-slippage live: {latency_path.relative_to(REPO)} has no "
                f"exit-slippage $ field (it measures pipeline TIME latency in seconds, entry "
                f"fills only, scope_arms={doc.get('scope_arms')} -- not safe-2/bold-2, the PDT "
                f"anchor's own arms, and not a price/dollar quantity at all). Not resolvable; "
                f"skip 'live' or supply a numeric override.")
        raise SystemExit(  # unreachable today (candidate_keys is always empty) -- kept honest
            f"--exit-slippage live: found candidate field(s) {candidate_keys} but no reader "
            f"was ever wired for them (none existed when this flag was built) -- refusing to "
            f"guess at a dollar value from an unread field.")
    return float(raw)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    walker = args.walker
    bar_resolution = args.bars
    exit_slippage = _resolve_exit_slippage_arg(args.exit_slippage)
    out_json = OUT_JSON if walker == "multileg" else OUT_JSON_EXIT_MGR
    out_md = OUT_MD if walker == "multileg" else OUT_MD_EXIT_MGR
    deviations: list[str] = []
    if exit_slippage is not None and walker == "multileg":
        print("  NOTE: --exit-slippage has no effect on --walker multileg (its own "
              "slippage=0.01 applies to every leg already, not just market-style stages) -- "
              "disclosed, not silently ignored.")

    if not PREREG_PATH.exists():
        print(f"FATAL: prereg not found at {PREREG_PATH}")
        return 1
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    if prereg.get("status") != "FROZEN_BEFORE_RUNNER":
        deviations.append(f"prereg status is {prereg.get('status')!r}, not "
                           f"FROZEN_BEFORE_RUNNER -- proceeding anyway, disclosed.")

    intents, counts = load_population()
    print(f"=== POPULATION (re-derived from {CORE_LEDGER.relative_to(REPO)}) ===")
    print(f"  RISK_DENY_PDT attempts (top-level exec.status): {counts['n_attempts_top_level']}")
    print(f"  unique (account,symbol,date) intents:           {counts['n_unique_intents']}")
    print(f"  date range: {counts['date_range']}  n_days={counts['n_days']}")
    if (counts["n_attempts_top_level"], counts["n_unique_intents"]) != (68, 18):
        deviations.append(
            f"prereg claimed 68 attempts -> 18 unique intents; this run found "
            f"{counts['n_attempts_top_level']} -> {counts['n_unique_intents']} "
            f"(ledger has grown/changed since 2026-08-11 -- reported as found, not forced).")
    else:
        print("  MATCHES prereg's original count (68 -> 18) exactly.")

    print(f"\n=== VALIDATE THE VALIDATOR (harness fidelity vs broker truth) -- "
          f"walker={walker} bars={bar_resolution} exit_slippage={exit_slippage} ===")
    hv = harness_validation(walker=walker, bar_resolution=bar_resolution,
                            exit_slippage=exit_slippage)
    if hv.get("sign_agreement") is not None:
        print(f"  n={hv['n']} anchor positions (safe-2/bold-2, {STUDY_WINDOW_START}..{STUDY_WINDOW_END}, engine-attributed)")
        print(f"  sign agreement: {hv['sign_agreement']*100:.1f}%  (bar: {HARNESS_SIGN_AGREEMENT_BAR*100:.0f}%)")
        print(f"  actual total ${hv['actual_total']:+,.0f}  replay total ${hv['replay_total']:+,.0f}  "
              f"median abs err ${hv['median_abs_error']:,.0f}")
        print(f"  MAGNITUDE fidelity verdict: {hv['magnitude_fidelity_verdict']}  "
              f"(aggregate_ratio={hv['magnitude_fidelity'].get('aggregate_ratio')}, "
              f"reported alongside sign agreement, does NOT gate harness_reliable below)")
    else:
        print(f"  COULD NOT VALIDATE: {hv.get('note')}")
    harness_reliable = (hv.get("sign_agreement") is not None
                        and hv["sign_agreement"] >= HARNESS_SIGN_AGREEMENT_BAR)

    if walker == "exit_manager" and not exit_manager_magnitude_gate(hv):
        # WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK: "only if the anchor PASSES the
        # magnitude criterion, re-run the counterfactual's frozen gates ... if the anchor
        # FAILS, stop there and report why (per-stage decomposition)". No cohort pricing, no
        # G1-G4, no output file -- the published 2026-09-02 artifact is untouched either way.
        print(f"\n=== STOPPED: exit_manager anchor did NOT pass the magnitude criterion "
              f"(verdict={hv['magnitude_fidelity_verdict']}) ===")
        print("  Per-stage decomposition (stage_agree = walker picked the SAME final exit "
              "event the broker recorded, so the residual is a pricing/fill-convention gap; "
              "stage_disagree = the walker picked a DIFFERENT event entirely, a structural "
              "gap):")
        sd = hv.get("stage_decomposition") or {}
        print(f"    stage_agree:    {sd.get('stage_agree')}")
        print(f"    stage_disagree: {sd.get('stage_disagree')}")
        print(f"    disagree_share_of_total_abs_error: {sd.get('disagree_share_of_total_abs_error')}")
        print("  No cohort pricing/gates/output file was produced -- not trustworthy enough "
              "to compute the counterfactual verdict on. Fix the walker or the anchor before "
              "re-running.")
        return 0

    print("\n=== PRICING the blocked cohort (calibration v5) ===")
    spy_map = spy_by_day()
    if not spy_map:
        deviations.append("NO SPY union feed cached -- structure/ribbon exits cannot fire for "
                          "ANY intent (silent premium-mode-equivalent walk). Disclosed, not "
                          "hidden.")
    priced, price_deviations = run_counterfactual(intents, spy_map, walker=walker)
    deviations.extend(price_deviations)
    print(f"  priced {len(priced)}/{len(intents)} intents "
          f"({len(intents) - len(priced)} excluded -- see deviations)")

    day_pnls = day_pnls_from_priced(priced)
    gates = compute_gates(day_pnls)
    print("\n=== GATES ===")
    for k in ("G1_net_positive", "G2_day_balance", "G3_drop_best", "G4_not_concentrated"):
        print(f"  {k}: {gates[k]}")
    print(f"  ALL PASS: {gates['all_pass']}")

    if not priced:
        verdict = "WITHHELD_NO_PRICEABLE_POPULATION"
    elif not harness_reliable:
        verdict = "WITHHELD_HARNESS_UNRELIABLE"
    elif gates["all_pass"]:
        verdict = "PASS_PROPOSE_FORWARD_TRIAL"
    else:
        verdict = "FAIL_PDT_STAYS_AS_IS"

    print(f"\n=== VERDICT: {verdict} ===")
    if verdict == "WITHHELD_HARNESS_UNRELIABLE":
        print("  Gates were computed and are reported below, but the harness that produced "
              "them has not been shown reliable enough to trust the number. What would need "
              "fixing: raise sign agreement (investigate the specific mismatches in "
              "hv['rows']) before this verdict can be un-withheld.")

    capital_flags = [p for p in priced if p.get("capital_flag")]

    out = {
        "rule_id": prereg.get("rule_id"),
        "prereg_path": str(PREREG_PATH.relative_to(REPO)),
        "run_at_note": "generated by setup/scripts/pdt_blocked_counterfactual.py",
        "walker": walker,
        "anchor_bar_resolution": bar_resolution,
        "harness_deviation_disclosed": (
            None if walker == "multileg" else
            "Prereg's contract names multileg_exit_walk by construction (walk_exit_manager did "
            "not exist when it was frozen). This run used --walker exit_manager instead, per "
            "WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK (automation/overnight/queue.md) -- "
            "the anchor cleared walker_magnitude_fidelity's PASS criterion first (see "
            "harness_validation.magnitude_fidelity_verdict below) before this cohort's gates "
            "were trusted. The published 2026-09-02 multileg artifact is untouched by this run."),
        "calibration": {"fill_mode": "extreme", "slippage": 0.01, "spy_feed": "union of backtest/data/spy_5m_*.csv"},
        "population": {**counts, "intents": [
            {k: v for k, v in it.items() if k not in ("trigger_level_exact",)} for it in intents]},
        "harness_validation": hv,
        "harness_reliable": harness_reliable,
        "priced": priced,
        "day_pnls": {k: round(v, 2) for k, v in sorted(day_pnls.items())},
        "gates": gates,
        "verdict": verdict,
        "capital_non_binding_flags": capital_flags,
        "known_limitations_stated_before_running": prereg.get("known_limitations_stated_before_running"),
        "explicitly_forbidden": prereg.get("explicitly_forbidden"),
        "deviations": deviations,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out_json}")

    md = _render_md(out, out_json_name=out_json.name)
    out_md.write_text(md, encoding="utf-8")
    print(f"wrote {out_md}")
    return 0


def _render_md(out: dict, out_json_name: str = OUT_JSON.name) -> str:
    g = out["gates"]
    hv = out["harness_validation"]
    lines = [
        f"# PDT-BLOCKED-COUNTERFACTUAL-2026-08-11 -- runner result ({out_json_name})",
        "",
        f"**Verdict: {out['verdict']}**",
        "",
        "## Naive-counterfactual limitation (restated prominently, per the frozen prereg)",
        "",
        "> Taking a blocked trade would have shifted the rolling PDT window and could have "
        "blocked a DIFFERENT later trade. This measures the marginal value of the blocked "
        "intents in ISOLATION, not a full sequential re-simulation. **A positive result "
        "licenses a forward trial, never a direct ship.** n=18 is below the advisory n>=20 "
        "bar -- a pass is SUGGESTIVE, not sufficient on its own. PDT stays exactly as-is for "
        "live accounts under $25k regardless of this result -- that is a real regulatory "
        "rule and is NOT being questioned here.",
        "",
        "## Population (re-derived from core-decisions.jsonl, not copied from the prereg)",
        "",
        f"- RISK_DENY_PDT attempts: **{out['population']['n_attempts_top_level']}**",
        f"- unique (account,symbol,date) intents: **{out['population']['n_unique_intents']}**",
        f"- date range: {out['population']['date_range']}, {out['population']['n_days']} days",
        "",
        "## Harness validation (validate the validator)",
        "",
    ]
    if hv.get("sign_agreement") is not None:
        lines += [
            f"- n = {hv['n']} anchor positions (safe-2/bold-2, engine-attributed, "
            f"{STUDY_WINDOW_START}..{STUDY_WINDOW_END})",
            f"- **sign agreement: {hv['sign_agreement']*100:.1f}%** "
            f"(bar: {HARNESS_SIGN_AGREEMENT_BAR*100:.0f}%) "
            f"-> {'RELIABLE' if out['harness_reliable'] else 'NOT RELIABLE'}",
            f"- actual total ${hv['actual_total']:+,.0f} vs replay total ${hv['replay_total']:+,.0f}, "
            f"median abs error ${hv['median_abs_error']:,.0f}",
        ]
    else:
        lines.append(f"- COULD NOT VALIDATE: {hv.get('note')}")
    lines += [
        "",
        "## Gates",
        "",
        "| Gate | Pass | Detail |",
        "|---|---|---|",
        f"| G1 net_positive | {g['G1_net_positive']['pass']} | net_total = ${g['G1_net_positive']['net_total']:+,.2f} |",
        f"| G2 day_balance | {g['G2_day_balance']['pass']} | {g['G2_day_balance']['profitable_days']} profitable vs {g['G2_day_balance']['losing_days']} losing days |",
        f"| G3 drop_best | {g['G3_drop_best']['pass']} | net - best_day = ${g['G3_drop_best']['net_minus_best_day']:+,.2f} (best day {g['G3_drop_best']['best_day']}: ${g['G3_drop_best']['best_day_pnl']:+,.2f}) |",
        f"| G4 not_concentrated | {g['G4_not_concentrated']['pass']} | best day = {g['G4_not_concentrated']['best_day_pct_of_net']} of net |",
        f"| **ALL PASS** | **{g['all_pass']}** | |",
        "",
        f"Days priced: {g['n_days']}",
        "",
        "## Deviations from the frozen design",
        "",
    ]
    if out["deviations"]:
        lines += [f"- {d}" for d in out["deviations"]]
    else:
        lines.append("- none")
    if out["capital_non_binding_flags"]:
        lines += ["", "## Capital-non-binding assumption violated for:", ""]
        for c in out["capital_non_binding_flags"]:
            lines.append(f"- {c['account']} {c['symbol']} {c['date']}: {c['capital_flag']}")
    lines += [
        "",
        "## Per-intent detail",
        "",
        "| Date | Account | Symbol | Qty | Entry | PnL | Legs |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in out["priced"]:
        lines.append(f"| {p['date']} | {p['account']} | {p['symbol']} | {p['qty']} | "
                     f"${p['entry_premium']:.2f} | ${p['pnl']:+,.2f} | {p['n_legs']} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
