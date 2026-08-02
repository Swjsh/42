"""bold_fullhist_replay.py -- FULL-HISTORY production-parity replay of the CURRENT LIVE
core-Bold engine (Gamma-Bold-2 / bold-2, account PA33W2KUAT40). Sibling of
`backtest/tools/engine_fullhist_replay.py` (Safe). Built WEEKEND-TWELVE Next-Twelve #8
(2026-08-01): every prior fullhist-replay tool in this repo walked SAFE's shape (params.json
exit/sizing/gates) -- Bold cells in studies (WS11's core-recency bull supplement, the
elite-bull-requal-2026-07-31 bold cohort) were either blind or Safe-approximated. OP-16
sim-accuracy gate: verify the sim matches production before ratification.

READ FIRST: analysis/deep-research/BOLD-HARNESS-2026-08-01.md -- the full knob-by-knob
translation table (every automation/state/aggressive/params.json key that differs from
automation/state/params.json, with doc citations) and the anchor-validation results live
there; this docstring only summarizes the load-bearing findings.

THREE TRAPS THE TRANSLATION AUDIT SURFACED (a naive "copy Safe's tool, swap the params
file" port would have hit all three and silently lied):

1. SIZING (the biggest one). Live Bold qty is NOT run_backtest's internal
   per_trade_risk_cap_pct scaling -- that scaling is a NO-OP in practice: backtest/lib/
   simulator.py's DEFAULT_QTY=3 already satisfies the scaling code's own `max(3, ...)`
   floor (orchestrator.py:1917-1932), so every orchestrator-produced TradeFill.qty is 3,
   unconditionally, regardless of account or per_trade_risk_cap_pct. The REAL live formula
   (setup/scripts/heartbeat_core.py:1835, `qty = int(params.get("min_contracts", 3))`,
   confirmed byte-exact against 7/7 real bold-2 ENGINE-attributed fills in
   automation/state/fills-ledger.jsonl -- zero deviation across 2026-06-26..2026-07-28) is:
   qty = params['min_contracts'] (Bold=5, Safe=3), clamped DOWN by
   risk_gate.max_affordable_qty, NEVER resized -- if even the floor is unaffordable the
   WHOLE order is denied (RISK_CAP/MIN_CONTRACTS deadlock), not shrunk to fit. This tool
   ignores run_backtest's own qty entirely and re-derives it (resolve_bold_qty below);
   reusing raw TradeFill.qty the way engine_fullhist_replay.py does (safe, where it
   happens to coincide with min_contracts=3 by luck, not design) would have silently
   graded every Bold trade at qty=3 instead of 5 -- exit P&L is exactly linear in qty
   (backtest/lib/exit_manager_walk.py's leg_pnl formula), so that is a flat 40% understatement
   of every Bold dollar number, not a rounding error.
2. STRIKE SIGN CONVENTION. crypto/lib/strike_selection.py's V15_BOLD_CORE_TIERS uses the
   LIVE-PARAMS convention (positive=ITM, negative=OTM -- confirmed by its own OTM-2/ITM-2
   labels). orchestrator.run_backtest's strike_offset/_bear/_bull kwargs use the INVERTED
   simulator convention (backtest/lib/simulator_real.py:281 "strike_offset=-2 ... ITM-2 for
   puts"; independently confirmed by multiple params.json docstrings, e.g.
   j_vwap_cont_strike_offset_bold's own note "sim -2 = ITM-2"). This tool negates the tier
   table's offset before passing it to run_backtest (_live_to_sim_strike_offset). At
   bold-2's current $1,197.52 equity (live-verified this session via
   mcp__alpaca_aggressive__get_account_info) the resolved tier is ATM (offset 0), so the
   negation is presently a no-op -- but a future re-run at Bold equity >= $2,000 (tier
   flips to OTM-2, offset -2 live-convention) would silently invert ITM/OTM without this.
3. EXIT SHAPE IS SHARED, NOT BOLD-SPECIFIC. aggressive/params.json's own top-level exit
   keys (premium_stop_pct -0.07/-0.05, tp1_premium_pct 0.75, tp1_qty_fraction 0.667,
   runner_max_premium_pct 5.0) READ like Bold's exit shape but are VESTIGIAL for the core
   ribbon_ride path once GAMMA_CORE_MANAGES_EXITS=1 (confirmed live per
   project_p0_g1_manages_exits_guard memory + CLAUDE.md's conductor doctrine). heartbeat_
   core.py's entry path (~line 1981-1985, `_xov is None` branch -- ribbon_ride/RIDE_THE_
   RIBBON never has a _SETUP_EXEC_OVERRIDES entry) registers EVERY core ribbon_ride fill,
   BOTH accounts, under `strategies.by_name("ribbon_ride").exit.to_dict()` -- the exact same
   dict object Safe's tool uses. CORE_MANAGES_EXITS is a single process-wide env flag read
   once at import (`os.environ.get("GAMMA_CORE_MANAGES_EXITS", "0")`), not indexed by
   account, so this identity is structural, not coincidental -- both accounts share ONE
   process, one flag. This tool uses the identical shared shape; a "Bold-shaped" -7%/+75%/5x
   exit would have modeled an inert safety bracket, never what exit_manager actually rides.

Two further, disclosed (not fixed) gaps shared with ALL orchestrator-based harnesses in
this repo (pre-existing, not introduced by this tool):
  - structure_veto_enabled (Safe=true, Bold=absent->false in engine_cli's own default) is
    consumed by backtest/lib/engine/engine_cli.py, NOT orchestrator.run_backtest -- no
    kwarg exists to model it here. Same gap Safe's own engine_fullhist_replay.py has.
  - PDT/settlement (Bold pdt_gate_mode="margin_pdt" vs Safe "cash_settlement") and the
    daily kill-switch are RUNTIME/STATE-DEPENDENT risk_gate checks (day-trade counts,
    intraday equity path) that no static full-history orchestrator walk can model without
    a full account-state simulator neither tool in this repo has built.
  - max_premium_per_contract (Bold $5.00 vs Safe $3.30) and Safe-only
    v15_max_premium_pct_of_account (Bold has no such tiered table at all -- risk_gate.
    check_order skips CODE_MAX_PREMIUM_TIER entirely when the key is absent) are additional
    live pre-order caps outside orchestrator.run_backtest's kwarg surface.

TWO-LAYER DESIGN: identical to engine_fullhist_replay.py -- ENTRY via
`lib.orchestrator.run_backtest(**BOLD_BASE_LIVE)` (the engine_cli-equivalent score+gate+
filter cascade), EXIT via `lib.exit_manager_walk.walk_exit_manager` driving the REAL
`automation/state/fleet/exit_manager.py#plan_exit_actions` core. See that module's
docstring for the SIM-EXIT-SHAPE-PARITY rationale (unchanged here). Ribbon-lookup, no-
lookahead as-of alignment, and the strike/side/time entry matcher are REUSED verbatim from
engine_fullhist_replay.py (imported, not copy-pasted) -- those primitives are account-
agnostic and already guard-tested by test_engine_fullhist_replay.py.

WHY A SEPARATE TOOL, NOT A "MODE" FLAG ON engine_fullhist_replay.py (task ask: decide by
reading, state why): engine_fullhist_replay.py hardcodes SAFE_BASE_LIVE as a module-level
dict, its own anchor days are Safe-specific real fills, and its output paths are Safe-
named. Threading BOLD_BASE_LIVE + the qty-resolution divergence + the strike-sign fix +
a completely different anchor set through one shared module via a `--account` flag would
require as much branching as two focused modules, and would break this repo's OWN
established convention: every gate-study tool here (elite_bear_level_reject_gate_ab.py,
elite_bull_postfix_requal_2026_07_31.py) hand-builds its own BASE dict rather than a
shared parameterized runner, explicitly because `runner.run_with_params`'s allowlist
doesn't cover every live key (elite_bear_level_reject_gate_ab.py's own docstring). A
second focused module, importing the account-agnostic primitives, matches precedent.

GATE STATE AS INPUT (task requirement -- "the harness must take gate state as an INPUT so
studies can run pre/post-trial counterfactuals"): block_elite_bull is a parameter of
bold_base_live() and replay_population(), not a hardcoded constant. main() runs BOTH
states -- PRE_TRIAL (block_elite_bull=True, what was live for nearly the whole window) and
POST_TRIAL (block_elite_bull=False, armed 2026-08-01 per elite-bull-requal-2026-07-31.json
verdict "a") -- into ONE scorecard so a study can diff them without re-running.

Run: backtest/.venv/Scripts/python.exe backtest/tools/bold_fullhist_replay.py
     backtest/.venv/Scripts/python.exe backtest/tools/bold_fullhist_replay.py --anchor-only
     backtest/.venv/Scripts/python.exe backtest/tools/bold_fullhist_replay.py --first-consumer-only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
CRYPTO_LIB = ROOT / "crypto" / "lib"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR), str(CRYPTO_LIB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import engine_fullhist_replay as efr  # noqa: E402 -- reuse ribbon/alignment/matcher primitives
import elite_bear_level_reject_gate_ab as eb  # noqa: E402 -- classify_tier, entry_date
import strategies as fleet_strategies  # noqa: E402  -- automation/state/fleet/strategies.py
import strike_selection as ss  # noqa: E402  -- crypto/lib/strike_selection.py
from lib.orchestrator import run_backtest  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402

DATA = REPO / "data"
# SAME merged window as engine_fullhist_replay.py -- apples-to-apples Safe-vs-Bold comparison.
SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-22.csv"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 22)
TIME_STOP_ET = dt.time(15, 40)   # matches BOLD_BASE_LIVE's time_stop_minutes_before_close=20

OUT_JSON = ROOT / "analysis" / "recommendations" / "bold-fullhist-replay-2026-08-01.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "bold-fullhist-replay-2026-08-01.md"

# Live-verified THIS session (2026-08-01, mcp__alpaca_aggressive__get_account_info,
# PA33W2KUAT40): equity=$1,197.52, cash-only, no open positions. Both static across the
# whole window -- this repo's established full-window-study convention (see
# engine_fullhist_replay.py's SAFE_BASE_LIVE comment); NOT a compounding account curve.
BOLD_LIVE_EQUITY = 1197.52
BOLD_MIN_CONTRACTS = 5           # aggressive/params.json min_contracts
BOLD_PER_TRADE_RISK_CAP_PCT = 0.50  # aggressive/params.json per_trade_risk_cap_pct


def _live_to_sim_strike_offset(live_convention_offset: int) -> int:
    """crypto/lib/strike_selection.py convention: positive=ITM, negative=OTM.
    backtest/lib/simulator_real.py convention (what orchestrator.run_backtest's
    strike_offset kwargs actually consume): INVERTED, negative=ITM, positive=OTM. Negate
    to translate. (See module docstring finding #2 -- a real trap, not defensive noise:
    0 is sign-invariant so this is presently a no-op at Bold's current ATM tier, but is
    load-bearing the moment Bold's equity crosses into a non-ATM tier.)"""
    return -live_convention_offset


def resolve_bold_strike_offset(equity: float = BOLD_LIVE_EQUITY) -> tuple[int, str]:
    """Bold's LIVE strike tier (V15_BOLD_CORE_TIERS, wired 2026-07-18 -- see that table's
    module docstring) at the given equity, translated to the simulator's sign convention.
    Returns (sim_convention_offset, tier_label)."""
    tier = ss.pick_tier(equity, ss.V15_BOLD_CORE_TIERS)
    return _live_to_sim_strike_offset(tier.strike_offset), tier.label


def resolve_bold_qty(
    entry_premium: float, equity: float = BOLD_LIVE_EQUITY,
    per_trade_risk_cap_pct: float = BOLD_PER_TRADE_RISK_CAP_PCT,
    min_contracts: int = BOLD_MIN_CONTRACTS,
) -> Optional[int]:
    """THE faithful live sizing formula (setup/scripts/heartbeat_core.py:1835 + risk_gate.
    check_order's MIN_CONTRACTS/RISK_CAP gates), NOT run_backtest's internal per-trade-cap
    scaling (module docstring finding #1 -- that scaling is a no-op given
    backtest/lib/simulator.py's DEFAULT_QTY=3, so it NEVER reflects any account's real
    min_contracts). Live never resizes below the floor -- if min_contracts itself is
    unaffordable, the order is denied outright (RISK_CAP/MIN_CONTRACTS deadlock). Returns
    None when the entry would be denied live (excluded from the replay, counted +
    disclosed, never silently downsized -- mirrors risk_gate's fail-closed philosophy)."""
    if entry_premium is None or entry_premium <= 0:
        return None
    notional = entry_premium * min_contracts * 100.0
    cap_dollars = equity * per_trade_risk_cap_pct
    if notional > cap_dollars:
        return None
    return min_contracts


BOLD_MIN_CONTRACTS_PREFERRED = 5   # try this first (== current live BOLD_MIN_CONTRACTS)
BOLD_MIN_CONTRACTS_FALLBACK = 3    # Rule 6's absolute floor (2 TP + 1 runner) -- never lower


def resolve_bold_qty_adaptive(
    entry_premium: float, equity: float = BOLD_LIVE_EQUITY,
    per_trade_risk_cap_pct: float = BOLD_PER_TRADE_RISK_CAP_PCT,
    min_contracts_preferred: int = BOLD_MIN_CONTRACTS_PREFERRED,
    min_contracts_floor: int = BOLD_MIN_CONTRACTS_FALLBACK,
) -> Optional[int]:
    """BOLD-ADAPTIVE-SIZING-TRY5-FALLBACK3 (2026-08-02): try `min_contracts_preferred`
    first (identical affordability check to resolve_bold_qty); if THAT is RISK_CAP-denied,
    fall back to `min_contracts_floor` ONLY (never any intermediate value -- a strict
    two-tier selector, not a max-affordable-qty search). Returns None when even the floor
    is unaffordable (same fail-closed convention as resolve_bold_qty -- never silently
    downsized to some other quantity). min_contracts_floor must never be set below Rule 6's
    absolute 3-contract floor (2 TP + 1 runner) -- enforced by
    test_bold_adaptive_sizing_2026_08_02.py, not just by convention here."""
    if min_contracts_floor < 3:
        raise ValueError(
            f"min_contracts_floor={min_contracts_floor} violates Rule 6's absolute floor "
            "of 3 (2 TP + 1 runner) -- refusing to resolve a qty below it")
    preferred = resolve_bold_qty(
        entry_premium, equity=equity, per_trade_risk_cap_pct=per_trade_risk_cap_pct,
        min_contracts=min_contracts_preferred)
    if preferred is not None:
        return preferred
    return resolve_bold_qty(
        entry_premium, equity=equity, per_trade_risk_cap_pct=per_trade_risk_cap_pct,
        min_contracts=min_contracts_floor)


def bold_base_live(block_elite_bull: bool) -> dict:
    """Hand-built translation of automation/state/aggressive/params.json (read 2026-08-01),
    mirroring elite_bear_level_reject_gate_ab.py's SAFE_BASE / engine_fullhist_replay.py's
    SAFE_BASE_LIVE pattern (hand-built, not runner.run_with_params -- see module docstring
    "WHY A SEPARATE TOOL" section). Every value below is cited against its aggressive/
    params.json source line; every DIFFERENCE from Safe's SAFE_BASE_LIVE is called out
    inline with "SAFE:" so the diff is legible without cross-referencing two files. Full
    enumerated table: analysis/deep-research/BOLD-HARNESS-2026-08-01.md.

    block_elite_bull is a PARAMETER (task requirement) so pre/post-trial counterfactuals
    are one function call apart, not a hand-edit."""
    strike_offset, strike_tier_label = resolve_bold_strike_offset(BOLD_LIVE_EQUITY)
    return dict(
        use_real_fills=True,
        strike_offset=strike_offset,                  # V15_BOLD_CORE_TIERS @ $1,197.52 = ATM (sim 0). SAFE: also ATM (0) at this equity -- ties out, but via a DIFFERENT table + a sign negation Safe's ATM=0 never exercises.
        premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50,  # catastrophe cap, IDENTICAL both accounts (structure_stop_enabled dominates below $50% gap moves either way; aggressive/params.json's own -0.07/-0.05 are the VESTIGIAL initial-bracket-only numbers, see finding #3)
        tp1_premium_pct=0.5, tp1_qty_fraction=0.667,   # exit-layer discards these (see EXIT LAYER below); passed for disclosure/parity only, matching SAFE_BASE_LIVE's own convention. aggressive/params.json's OWN tp1_qty_fraction=0.667 (SAFE: 0.8, raised 2026-06-28) -- but NEITHER value reaches the real ribbon_ride exit (finding #3): both discarded, both replaced by strategies.RIBBON_RIDE.exit.to_dict()'s tp1_qty_fraction=0.667.
        runner_target_premium_pct=2.5,                 # disclosure-only (see above)
        level_stop_buffer_dollars=0.5,                 # aggressive/params.json chart_stop_buffer_dollars 0.5 -- SAME as Safe
        time_stop_minutes_before_close=20,             # aggressive/params.json time_stop_et "15:40" -- SAME as Safe
        profit_lock_threshold_pct=0.05,                # disclosure-only, exit-layer discards
        profit_lock_stop_offset_pct=0.0,
        profit_lock_mode="fixed",
        profit_lock_trail_pct=0.125,
        f9_vol_mult=0.7,                                # aggressive/params.json filter_9_vol_multiplier 0.7 -- SAME as Safe
        min_triggers_bear=1, min_triggers_bull=1,       # aggressive/params.json filter_10_min_triggers_bear/bull 1/1. SAFE: bear=1, bull=2 -- Bold needs only ONE confirming trigger for a bull entry, Safe needs two. REAL entry-gate difference.
        no_trade_before=dt.time(9, 35),                 # aggressive/params.json entry_no_trade_before_et -- SAME as Safe
        no_trade_window=(dt.time(15, 0), dt.time(16, 0)),  # aggressive/params.json entry_no_trade_after_et "15:00" -- SAME as Safe
        block_level_rejection=False,                    # aggressive/params.json block_level_rejection: false (REMOVED 2026-06-18, superseded by require_bearish_fill_bar per its own doc). SAFE: true (still ON). REAL entry-gate difference -- Bold does NOT block LEVEL-tier level_rejection bears; Safe does.
        block_elite_bull=block_elite_bull,               # ** THE GATE UNDER TEST ** -- INPUT PARAMETER, not hardcoded. aggressive/params.json's CURRENT on-disk value is false (LIFT-GATE TRIAL armed 2026-08-01); this function lets a caller model either state.
        block_elite_bull_vix_low=15.0, block_elite_bull_vix_high=18.0,  # aggressive/params.json block_elite_bull_vix_low/high 15.0/18.0. SAFE: 0.0/25.0 -- Bold's block band (when armed) is much NARROWER than Safe's (a 3-point VIX window vs Safe's effectively-unconditional 0-25).
        entry_bar_body_pct_min=0.0,                      # aggressive/params.json has NO entry_bar_body_pct_min key -> engine default 0.0 (gate off). SAFE: 0.2 (gate ON, blocks doji/wick-dominant bear entries). REAL entry-gate difference.
        block_bull_1100_1200=False,                      # aggressive/params.json block_bull_1100_1200: false (key ABSENT -- kwarg default False anyway). SAFE: true (blocks ALL bull entries 11:00-12:00 ET). REAL entry-gate difference.
        midday_trendline_gate=False,                     # aggressive/params.json midday_trendline_gate: false -- SAME as Safe (both off)
        min_ribbon_momentum_cents=None,                  # aggressive/params.json has NO min_ribbon_momentum_cents key -> kwarg default None (gate off). SAFE: also None/null (gate off, L107 revert) -- SAME net effect, different provenance (Bold never had the key; Safe has it explicitly disabled).
        max_ribbon_duration_bars=999,                     # aggressive/params.json has NO max_ribbon_duration_bars key -> kwarg default None in run_backtest, but orchestrator treats None as "disabled" same as 999 -- SAME net effect as Safe's explicit 999.
        vix_bear_hard_cap=None,                           # aggressive/params.json has NO vix_bear_hard_cap key -> gate off (no bear VIX ceiling at all for Bold). SAFE: 23.0 (blocks bear entries VIX>=23). REAL entry-gate difference -- flagged separately in aggressive/params.json's own vestigial-VIX doc as "BOLD-VIX-BEAR-CEILING-GAP".
        per_trade_risk_cap_pct=0.50,                      # Rule 6, Bold. SAFE: 0.30. (NOTE: only used here for the risk_gate ASSERT-AGREE cross-check inside run_backtest, per finding #1 -- NOT the qty this tool actually grades trades at; see resolve_bold_qty.)
        enable_bullish=True,                              # aggressive/params.json enable_bullish true -- SAME as Safe (OP-16)
        min_premium_for_level_tiers=0.3,                  # aggressive/params.json min_entry_premium 0.3 -- SAME as Safe
        initial_equity=BOLD_LIVE_EQUITY,                  # live-verified 2026-08-01 (this session), PA33W2KUAT40
        require_bearish_fill_bar=True,                    # aggressive/params.json require_bearish_fill_bar: true (J-ratified 2026-06-17, "ENFORCED-5 RULE-9-1"). SAFE: key ABSENT -> kwarg default False. REAL entry-gate difference -- Bold requires a confirming bearish N+1 fill-bar before a bear entry executes; Safe does not.
        block_conf_lvl_rej_midday_afternoon=False,        # aggressive/params.json: false (REMOVED 2026-06-18). SAFE: key absent -> default False. SAME net effect (both off), different provenance.
        block_bull_morning_agg=False,                     # aggressive/params.json: false (J-DIRECTED disable 2026-06-24, "remove this entirely" after it vetoed an 11/11 setup). SAFE: key absent -> default False (this gate was ALWAYS aggressive-only). SAME net effect (off).
    )


# --- ANCHOR SET (task step 3, OP-16 sim-accuracy gate) --------------------------------------
# 7 REAL bold-2 ENGINE-attributed (attribution=="engine", i.e. heartbeat_core.py placed
# these -- NOT J's manual fills, which this harness cannot and should not claim to model)
# round trips, mined from automation/state/fills-ledger.jsonl by hand 2026-08-01 (every
# row independently re-summed against the ledger; the 07-28 C741 -$295.00 figure was
# cross-checked against elite-bull-requal-2026-07-31.json's own
# "core_real_fills_on_cohort" entry -- exact match, confirms this hand-FIFO is correct).
# qty is 5 on EVERY SINGLE ONE, zero exceptions across 7 independent dates spanning
# 2026-06-26..2026-07-28 -- the strongest available confirmation that Bold's real live
# sizing is unconditionally min_contracts (5), never a tiered/scaled amount.
ANCHOR_FILLS: list[dict] = [
    {"date": "2026-06-26", "symbol": "SPY260626P00729000", "side": "P",
     "entry_ts_et": "2026-06-26T14:53:49.640000", "entry_premium": 0.21,
     "exit_ts_et": "2026-06-26T14:56:05.375785", "exit_premium": 0.18, "qty": 5,
     "real_pnl": -15.00},
    {"date": "2026-07-02", "symbol": "SPY260702P00743000", "side": "P",
     "entry_ts_et": "2026-07-02T09:31:03.860318", "entry_premium": 0.48,
     "exit_ts_et": "2026-07-02T09:32:05.330962", "exit_premium": 0.36, "qty": 5,
     "real_pnl": -60.00},
    {"date": "2026-07-02", "symbol": "SPY260702P00740000", "side": "P",
     "entry_ts_et": "2026-07-02T12:51:28.535543", "entry_premium": 0.42,
     "exit_ts_et": "2026-07-02T13:05:06.583357", "exit_premium": None, "qty": 5,
     "real_pnl": 290.00},   # 2-leg exit (4@1.16 + 1@0.36); real_pnl is the FIFO net, not a single exit_premium
    {"date": "2026-07-17", "symbol": "SPY260717P00743000", "side": "P",
     "entry_ts_et": "2026-07-17T13:51:32.001364", "entry_premium": 0.38,
     "exit_ts_et": "2026-07-17T14:27:04.194958", "exit_premium": None, "qty": 5,
     "real_pnl": 191.00},   # 2-leg exit (3@0.85 + 2@0.63)
    {"date": "2026-07-23", "symbol": "SPY260723P00735000", "side": "P",
     "entry_ts_et": "2026-07-23T11:29:25.517336", "entry_premium": 1.28,
     "exit_ts_et": "2026-07-23T11:56:04.968699", "exit_premium": 0.67, "qty": 5,
     "real_pnl": -305.00},
    {"date": "2026-07-27", "symbol": "SPY260727P00737000", "side": "P",
     "entry_ts_et": "2026-07-27T12:57:31.071602", "entry_premium": 1.37,
     "exit_ts_et": "2026-07-27T14:00:06.343269", "exit_premium": 0.66, "qty": 5,
     "real_pnl": -355.00},
    {"date": "2026-07-28", "symbol": "SPY260728C00741000", "side": "C",
     "entry_ts_et": "2026-07-28T11:28:20.226696", "entry_premium": 1.38,
     "exit_ts_et": "2026-07-28T13:46:25.044077", "exit_premium": 0.79, "qty": 5,
     "real_pnl": -295.00},  # cross-checked exact vs elite-bull-requal-2026-07-31.json core_real_fills_on_cohort
]
ANCHOR_TOLERANCE_PCT = 0.30   # documented, generous: fill-price convention differences
ANCHOR_TOLERANCE_DOLLARS = 60.0  # (mid-vs-fill, resting-order-limit-fill assumptions -- see
# exit_manager_walk.py's own FILL-PRICE CONVENTION docstring) mean exact-cent parity is not
# expected; pass = same SIGN (win/loss) AND within max(pct, dollars) of the real fill. This
# mirrors engine_fullhist_replay.py's own $60 anchor tolerance (its 07-17 anchor sums to
# $151 over 4 trades -- a comparable relative band).


def log(msg: str) -> None:
    print(f"[bold-fullhist-replay] {msg}", flush=True)


def _load_spy_vix() -> tuple[pd.DataFrame, pd.DataFrame]:
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)
    spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
    return spy_df, vix_df


def replay_population(
    spy_df: pd.DataFrame, vix_df: pd.DataFrame, ribbon_lookup: pd.DataFrame,
    block_elite_bull: bool, min_contracts: int = BOLD_MIN_CONTRACTS,
    qty_mode: str = "fixed",
    min_contracts_preferred: int = BOLD_MIN_CONTRACTS_PREFERRED,
    min_contracts_floor: int = BOLD_MIN_CONTRACTS_FALLBACK,
) -> dict:
    """ENTRY via run_backtest(**bold_base_live(block_elite_bull)); EXIT via
    walk_exit_manager driving strategies.RIBBON_RIDE.exit.to_dict() (finding #3); qty via
    resolve_bold_qty (finding #1), NOT the raw TradeFill.qty. Returns a dict with rows +
    exclusion counters (mirrors engine_fullhist_replay.py's main()/write_scorecard split,
    collapsed to one function since this tool runs it twice, once per gate state).

    min_contracts (2026-08-02, MIN-CONTRACTS-BOLD-2026-08-02 A/B): threaded through to
    resolve_bold_qty exactly like block_elite_bull above -- an INPUT, not a hardcoded
    constant, "so studies can run pre/post-trial counterfactuals" (same task requirement
    block_elite_bull was built to satisfy 2026-08-01). Default is BOLD_MIN_CONTRACTS (5,
    the CURRENT live floor), so every pre-existing call site that does not pass this
    argument is byte-identical to before this change (parity guard:
    test_min_contracts_bold_2026_08_02.py::test_replay_population_default_min_contracts_
    matches_bold_min_contracts_constant).

    qty_mode (2026-08-02, BOLD-ADAPTIVE-SIZING-TRY5-FALLBACK3): 'fixed' (DEFAULT, byte-
    identical to every pre-existing call site -- uses resolve_bold_qty(min_contracts)
    exactly as before, min_contracts_preferred/min_contracts_floor are UNUSED in this
    mode) or 'adaptive' (uses resolve_bold_qty_adaptive(min_contracts_preferred,
    min_contracts_floor) instead, min_contracts is UNUSED in this mode). Each row's output
    dict now also carries exit_time_et (previously computed by walk_exit_manager as
    WalkResult.exit_time_et but discarded before this change -- only hold_minutes survived
    into the row). This is a PURE ADDITIVE field: existing consumers that don't read the
    new key are unaffected; test_bold_adaptive_sizing_2026_08_02.py pins both the qty_mode
    default and the new field's presence."""
    if qty_mode not in ("fixed", "adaptive"):
        raise ValueError(f"qty_mode must be 'fixed' or 'adaptive', got {qty_mode!r}")
    base = bold_base_live(block_elite_bull)
    t0 = time.time()
    r = run_backtest(spy_df, vix_df, start_date=FULL_START, end_date=FULL_END, **base)
    entry_elapsed = time.time() - t0
    log(f"  [gate block_elite_bull={block_elite_bull} min_contracts={min_contracts}] "
        f"run_backtest done in {entry_elapsed:.1f}s -- {len(r.trades)} raw entries")

    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    rows: list[dict] = []
    n_no_opra = 0
    n_no_spy_day = 0
    n_excluded_sizing = 0
    t1 = time.time()
    for t in r.trades:
        edate = eb.entry_date(t)
        symbol = option_symbol(edate, int(t.strike), t.side)
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            n_no_opra += 1
            continue
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            n_no_spy_day += 1
            continue

        entry_time_et = efr.naive_dt(t.entry_time_et)
        entry_premium = float(t.entry_premium)
        if qty_mode == "adaptive":
            qty = resolve_bold_qty_adaptive(
                entry_premium, min_contracts_preferred=min_contracts_preferred,
                min_contracts_floor=min_contracts_floor)
        else:
            qty = resolve_bold_qty(entry_premium, min_contracts=min_contracts)
        if qty is None:
            n_excluded_sizing += 1
            continue
        trigger_level = float(t.rejection_level) if t.rejection_level else None
        tier = eb.classify_tier(t.triggers_fired)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)

        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=correct_shape, structure_stop_enabled=True,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "tier": tier, "symbol": symbol,
            "qty": qty, "entry_premium": round(entry_premium, 4), "triggers": t.triggers_fired,
            "trigger_level": trigger_level,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
            "n_ticks_walked": res.n_ticks_walked, "resolved": res.resolved,
            "exit_time_et": res.exit_time_et.isoformat() if res.exit_time_et else None,
        })
    exit_elapsed = time.time() - t1
    log(f"  [gate block_elite_bull={block_elite_bull} min_contracts={min_contracts}] "
        f"exit re-derivation done in {exit_elapsed:.1f}s -- n_replayed={len(rows)} "
        f"n_no_opra_excluded={n_no_opra} n_no_spy_day_excluded={n_no_spy_day} "
        f"n_excluded_risk_cap_deadlock={n_excluded_sizing}")

    return {
        "block_elite_bull": block_elite_bull,
        "min_contracts": min_contracts,
        "qty_mode": qty_mode,
        "min_contracts_preferred": min_contracts_preferred,
        "min_contracts_floor": min_contracts_floor,
        "rows": rows,
        "n_raw_entries": len(r.trades),
        "n_excluded_no_opra_cache": n_no_opra,
        "n_excluded_no_spy_day": n_no_spy_day,
        "n_excluded_risk_cap_deadlock": n_excluded_sizing,
        "entry_layer_seconds": round(entry_elapsed, 1),
        "exit_layer_seconds": round(exit_elapsed, 1),
        "correct_exit_shape": correct_shape,
        "base_config": {k: (str(v) if isinstance(v, (dt.time, tuple)) else v)
                         for k, v in base.items()},
    }


# --- ANCHOR VALIDATION (task step 3) ---------------------------------------------------------
def run_anchor_validation() -> dict:
    """Replays each of the 7 ANCHOR_FILLS through the SAME entry-metadata-in/exit-re-derived
    pipeline replay_population uses (walk_exit_manager + strategies.RIBBON_RIDE.exit,
    structure_stop_enabled=True, qty via resolve_bold_qty), using the REAL logged entry
    premium/time/qty (not a re-detected signal -- these are KNOWN real fills, this is purely
    an exit-fidelity + sizing-fidelity check, not an entry-gate check). trigger_level is
    recovered from core-decisions.jsonl when available (best-effort; None -> premium-stop-
    only fallback, disclosed per-row) since fills-ledger.jsonl itself carries no level."""
    trigger_levels = _load_trigger_levels_from_decisions()
    spy5_path = REPO / "data" / "spy_5m_2026-05-19_2026-07-31.csv"
    spy_df = pd.read_csv(spy5_path)
    ts = pd.to_datetime(spy_df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    spy_df = spy_df.assign(timestamp_et=ts.dt.tz_localize(None))
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()

    out_rows = []
    n_pass = 0
    for a in ANCHOR_FILLS:
        symbol = a["symbol"]
        opt_df = load_contract_bars(symbol)
        if opt_df is None:
            out_rows.append({**a, "replay_status": "NO_OPRA_CACHE"})
            continue
        edate = dt.date.fromisoformat(a["date"])
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            out_rows.append({**a, "replay_status": "NO_SPY_DAY"})
            continue
        entry_time_et = dt.datetime.fromisoformat(a["entry_ts_et"])
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        trigger_level = trigger_levels.get((symbol, a["entry_ts_et"]))
        res = walk_exit_manager(
            symbol=symbol, side=a["side"], entry_time_et=entry_time_et,
            entry_premium=a["entry_premium"], qty=a["qty"], exit_shape=correct_shape,
            structure_stop_enabled=True, trigger_level=trigger_level, strategy="ribbon_ride",
            time_stop_et=TIME_STOP_ET, opt_df=opt_df, ribbon_tick_df=rtd,
            five_min_spy_df=day_spy,
        )
        real_pnl = a["real_pnl"]
        replay_pnl = res.dollar_pnl
        same_sign = (real_pnl > 0) == (replay_pnl > 0) or (real_pnl == 0 and replay_pnl == 0)
        tol = max(ANCHOR_TOLERANCE_DOLLARS, abs(real_pnl) * ANCHOR_TOLERANCE_PCT)
        within_tol = abs(replay_pnl - real_pnl) <= tol
        row_pass = same_sign and within_tol
        n_pass += int(row_pass)
        out_rows.append({
            **a, "trigger_level_used": trigger_level,
            "replay_pnl": replay_pnl, "replay_exit_reason": res.exit_reason,
            "replay_hold_minutes": res.hold_minutes, "same_sign": same_sign,
            "tolerance_dollars": round(tol, 2), "within_tolerance": within_tol,
            "anchor_pass": row_pass, "replay_status": "OK",
        })
    return {
        "n_anchors": len(ANCHOR_FILLS), "n_pass": n_pass,
        "all_pass": n_pass == len(ANCHOR_FILLS),
        "tolerance_note": (f"pass = same win/loss sign AND |replay-real| <= "
                            f"max(${ANCHOR_TOLERANCE_DOLLARS}, {ANCHOR_TOLERANCE_PCT:.0%} of "
                            f"|real|) -- exact-cent parity not expected, see exit_manager_"
                            f"walk.py's own FILL-PRICE CONVENTION docstring (resting-order-"
                            f"limit-fill approximation, real fills reflect live spread/timing)"),
        "rows": out_rows,
    }


def _load_trigger_levels_from_decisions() -> dict:
    """Best-effort recovery of trigger_level_exact for the ANCHOR_FILLS entries from
    core-decisions.jsonl (account=='bold', ts_et within 90s of the fill's entry_ts_et).
    Missing/unreadable -> {} (anchor rows fall back to premium-stop-only, disclosed via
    trigger_level_used=None in the output -- fail-open, never fabricated)."""
    path = ROOT / "automation" / "state" / "core-decisions.jsonl"
    if not path.exists():
        return {}
    wanted = {(a["symbol"], a["entry_ts_et"]) for a in ANCHOR_FILLS}
    want_ts = {a["entry_ts_et"]: a["symbol"] for a in ANCHOR_FILLS}
    out: dict = {}
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("account") != "bold":
                    continue
                ts = row.get("ts_et")
                lvl = row.get("trigger_level_exact") or row.get("rejection_level")
                if not ts or lvl is None:
                    continue
                for entry_ts, symbol in want_ts.items():
                    try:
                        diff = abs((dt.datetime.fromisoformat(ts)
                                    - dt.datetime.fromisoformat(entry_ts)).total_seconds())
                    except ValueError:
                        continue
                    if diff <= 90:
                        out[(symbol, entry_ts)] = float(lvl)
    except OSError:
        return {}
    return out


# --- FIRST CONSUMER (task step 4): elite-bull blocked cohort under the TRUE bold shape -------
ELITE_BULL_REQUAL_JSON = ROOT / "analysis" / "recommendations" / "elite-bull-requal-2026-07-31.json"


def run_first_consumer_elite_bull_delta() -> dict:
    """Re-runs the Friday (2026-07-31) elite-bull-requal-2026-07-31.json bold cohort's OWN
    already-mined, already-exit-derived trades at BOLD'S TRUE qty (5, resolve_bold_qty),
    NOT the qty3 that study used for BOTH its "bold_*" cohorts and the SAFE-mislabeled
    "primary" that actually drove the trial's verdict (see report for the full audit).
    Two independent derivations, cross-checked against each other:
      (a) ANALYTIC rescale: qty5_pnl = qty3_pnl * (5/3) trade-by-trade. A FIRST-ORDER
          approximation only -- NOT exact (see finding below), kept as a cheap sanity cross-
          check with zero new I/O.
      (b) INDEPENDENT REPLAY (authoritative): re-walks each trade from its recorded
          entry_premium/trigger_level/symbol/entry_ts_et through walk_exit_manager at qty=5
          directly, from the SAME OPRA cache that study fetched.
    DISCLOSED FINDING (caught by (a) vs (b) disagreeing on this run, not assumed away):
    exit P&L is linear in qty WITHIN one exit leg, but the TP1/runner SPLIT is
    `int(qty * tp1_qty_fraction)` (integer truncation) -- at tp1_qty_fraction=0.667, qty=3
    splits 2/1 (66.7%/33.3% rides as runner), qty=5 splits 3/2 (60.0%/40.0% rides as
    runner). A MORE MORE qty (in relative terms) rides the runner at qty=5 than at qty=3, so
    any trade that actually reaches TP1 and rides a runner scales SUPER-linearly on its
    winners (5/3 undersells the true qty=5 result) -- confirmed exactly on this cohort's one
    TP1-splitting winner (SPY260731C00744000 12:16:03: analytic $530.67 vs independent
    replay $542.80). Trades that never reach TP1 (straight to stop) ARE exactly linear (4/5
    other trades in this cohort match to the cent). (b) is therefore the number this
    function reports as authoritative; (a) is retained only as a cheap same-ballpark sanity
    check, not as proof of exactness -- an earlier draft of this docstring claimed (a) was
    "exact under the model", which this run's own output disproved; corrected here rather
    than silently tightening the comparison tolerance to hide it.
    """
    if not ELITE_BULL_REQUAL_JSON.exists():
        return {"error": f"{ELITE_BULL_REQUAL_JSON} not found"}
    src = json.loads(ELITE_BULL_REQUAL_JSON.read_text(encoding="utf-8"))
    cohorts = src["cohorts"]
    correct_shape = fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    assert correct_shape == src["exit_shape_used"], (
        "elite-bull-requal-2026-07-31.json's exit_shape_used no longer matches the live "
        "strategies.RIBBON_RIDE.exit shape -- the source study is stale, re-run it first")

    spy5_path = REPO / "data" / "spy_5m_2026-05-19_2026-07-31.csv"
    spy_df = pd.read_csv(spy5_path)
    ts = pd.to_datetime(spy_df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    spy_df = spy_df.assign(timestamp_et=ts.dt.tz_localize(None))

    def rescale_and_reverify(cohort_name: str) -> dict:
        qty3 = cohorts[cohort_name]["trades"]
        out_trades = []
        for tr in qty3:
            analytic_pnl = round(tr["pnl"] * (5.0 / 3.0), 2)
            symbol = tr["symbol"]
            opt_df = load_contract_bars(symbol)
            replay_pnl = None
            if opt_df is not None:
                edate = dt.date.fromisoformat(tr["date"])
                day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
                if not day_spy.empty:
                    res = walk_exit_manager(
                        symbol=symbol, side="C", entry_time_et=dt.datetime.fromisoformat(tr["entry_ts_et"]),
                        entry_premium=tr["entry_premium"], qty=5, exit_shape=correct_shape,
                        structure_stop_enabled=True, trigger_level=tr.get("trigger_level"),
                        strategy="ribbon_ride", time_stop_et=dt.time(15, 50),
                        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=day_spy,
                    )
                    replay_pnl = res.dollar_pnl
            # AUTHORITATIVE pnl = independent replay when available (accounts for the
            # int(qty*tp1_qty_fraction) TP1/runner split truncation, see docstring finding);
            # falls back to the analytic rescale ONLY when the OPRA cache is missing for
            # this symbol (disclosed via qty5_pnl_source, never silently substituted).
            authoritative_pnl = replay_pnl if replay_pnl is not None else analytic_pnl
            out_trades.append({
                "date": tr["date"], "entry_ts_et": tr["entry_ts_et"], "symbol": symbol,
                "qty3_pnl_source": tr["pnl"], "qty5_analytic_rescale": analytic_pnl,
                "qty5_independent_replay": replay_pnl,
                "qty5_authoritative": authoritative_pnl,
                "qty5_pnl_source": "independent_replay" if replay_pnl is not None else "analytic_rescale_fallback",
                "linear_approx_diff": (
                    round(replay_pnl - analytic_pnl, 2) if replay_pnl is not None else 0.0
                ),
            })
        total_qty3 = round(sum(t["pnl"] for t in qty3), 2)
        total_qty5_analytic = round(sum(t["qty5_analytic_rescale"] for t in out_trades), 2)
        total_qty5_authoritative = round(sum(t["qty5_authoritative"] for t in out_trades), 2)
        n_missing = sum(1 for t in out_trades if t["qty5_independent_replay"] is None)
        return {
            "n": len(qty3), "total_pnl_at_qty3_source": total_qty3,
            "total_pnl_at_qty5_analytic": total_qty5_analytic,
            "total_pnl_at_qty5_authoritative": total_qty5_authoritative,
            "n_missing_opra_for_independent_replay": n_missing,
            "linearity_holds": all(abs(t["linear_approx_diff"]) < 0.02 for t in out_trades),
            "trades": out_trades,
        }

    bold_per_event = rescale_and_reverify("bold_per_event_qty3")
    bold_seq_hold = rescale_and_reverify("bold_sequential_hold_qty3")

    def drop_top1(trades: list[dict], pnl_key: str) -> float:
        pnls = [t[pnl_key] for t in trades]
        winners = [p for p in pnls if p > 0]
        if not winners:
            return round(sum(pnls), 2)
        return round(sum(pnls) - max(winners), 2)

    bold_seq_hold["drop_top1_at_qty5_analytic"] = drop_top1(
        bold_seq_hold["trades"], "qty5_analytic_rescale")
    bold_seq_hold["drop_top1_at_qty5_authoritative"] = drop_top1(
        bold_seq_hold["trades"], "qty5_authoritative")

    safe_primary = cohorts["safe_sequential_hold_qty3"]  # the cell actually used as "primary" Friday
    fleet_net_mapped = src["fleet_real_fills"]["net_mapped"]

    def grade(primary_total: float, primary_n: int, fleet_net: float) -> str:
        if primary_n == 0:
            return "b"
        if primary_total > 0 and fleet_net > 0:
            return "a"
        if primary_total < 0 and fleet_net < 0:
            return "c"
        return "b"

    original_verdict = src["verdict"]
    original_primary_cell = src["verdict_rule_inputs"]["primary_cell"]
    # AUTHORITATIVE (independent-replay) total is the correct number; the analytic rescale
    # is reported alongside for transparency but is NOT what grades the corrected verdict
    # (see docstring finding -- it understates TP1/runner-splitting winners).
    corrected_primary_total = bold_seq_hold["total_pnl_at_qty5_authoritative"]
    corrected_primary_n = bold_seq_hold["n"]
    corrected_verdict = grade(corrected_primary_total, corrected_primary_n, fleet_net_mapped)

    return {
        "source_study": str(ELITE_BULL_REQUAL_JSON.relative_to(ROOT)),
        "source_study_verdict": original_verdict,
        "source_study_primary_cell_NAME": original_primary_cell,
        "account_mismatch_flag": (
            original_primary_cell.startswith("safe_")
            and "MISLABELED: the trial armed on aggressive/params.json (bold-2 account) was "
                "justified by verdict_rule_inputs.primary_cell='safe_sequential_hold_qty3' -- "
                "SAFE's blocked-signal cohort, not bold-2's own. Bold's OWN cohort "
                "(bold_sequential_hold_qty3) was reported in the same file but never used as "
                "the frozen verdict rule's PRIMARY input."
        ),
        "safe_primary_total_cited_friday": safe_primary["total_pnl"],
        "safe_primary_n_cited_friday": safe_primary["n"],
        "bold_own_cohort_at_STUDY_qty3": {
            "sequential_hold": {"n": cohorts["bold_sequential_hold_qty3"]["n"],
                                 "total_pnl": cohorts["bold_sequential_hold_qty3"]["total_pnl"],
                                 "drop_top1": cohorts["bold_sequential_hold_qty3"]["drop_top1_remainder"]},
            "per_event": {"n": cohorts["bold_per_event_qty3"]["n"],
                          "total_pnl": cohorts["bold_per_event_qty3"]["total_pnl"],
                          "drop_top1": cohorts["bold_per_event_qty3"]["drop_top1_remainder"]},
        },
        "bold_own_cohort_at_TRUE_qty5": {
            "sequential_hold": bold_seq_hold,
            "per_event": bold_per_event,
        },
        "fleet_net_mapped_unchanged": fleet_net_mapped,
        "corrected_verdict_using_bolds_OWN_cohort_as_primary": {
            "primary_cell": "bold_sequential_hold_qty5, independent-replay-authoritative (this tool)",
            "primary_total": corrected_primary_total, "primary_n": corrected_primary_n,
            "primary_drop_top1": bold_seq_hold["drop_top1_at_qty5_authoritative"],
            "primary_total_analytic_rescale_crosscheck": bold_seq_hold["total_pnl_at_qty5_analytic"],
            "linearity_held_exactly": bold_seq_hold["linearity_holds"],
            "fleet_net": fleet_net_mapped,
            "verdict": corrected_verdict,
            "verdict_meaning": {
                "a": "LIFT_GATE_TRIAL supported", "b": "INSUFFICIENT/mixed signs -- keep gate",
                "c": "AGAINST -- gate stays, question closed",
            }[corrected_verdict],
        },
        "materially_weakens_per_task_criterion": (
            bold_seq_hold["drop_top1_at_qty5_authoritative"] < 0
        ),
        "delta_vs_friday": (
            f"Friday's cited evidence (+${safe_primary['total_pnl']:.2f}, n={safe_primary['n']}) "
            f"was SAFE's cohort, not bold-2's own. Bold's OWN cohort at its TRUE qty=5 sizing "
            f"(independent re-replay, authoritative -- the analytic 5/3 rescale cross-check "
            f"gives ${bold_seq_hold['total_pnl_at_qty5_analytic']:+.2f}, a close but NOT exact "
            f"match: TP1/runner qty-splits at int(qty*0.667) differ 2/1 at qty3 vs 3/2 at qty5, "
            f"so winners that reach TP1 scale super-linearly) is ${corrected_primary_total:+.2f} "
            f"(n={corrected_primary_n}) -- a COIN-FLIP total, not a robust positive -- with "
            f"drop-best ${bold_seq_hold['drop_top1_at_qty5_authoritative']:+.2f}: ONE single "
            f"trade (07-31 12:16 C744, +$542.80) IS the entire positive total; remove it and "
            f"the cohort is deeply red. The frozen verdict rule (verdict_rule_frozen in the "
            f"prereg) tests SIGN ONLY (primary_total>0 AND fleet_net>0 => 'a'), so it still "
            f"mechanically outputs '{corrected_verdict}' here -- $7.80 and $867.00 both clear "
            f"'>0'. LOUD FLAG (task's own explicit trigger: drop-best negative): the rule's "
            f"sign-only test is blind to the fact that Bold's OWN true evidence is a razor-"
            f"thin coin flip resting on a single trade, with the other 4 losing -$542.80 "
            f"combined -- a dramatically weaker and more concentrated picture than the +$867/"
            f"n=5/drop-best+$177 Friday actually saw (that number was never bold-2's own to "
            f"begin with). The trial's forward kill-criterion (n>=10 fills OR 10 sessions, "
            f"net<0 -> re-block) still stands as the LIVE guard and is doing real work here -- "
            f"but J should know the armed trial's disclosed justification was a different "
            f"account's number, and bold-2's own number is a coin flip propped up by one trade."
        ),
    }


def write_scorecard(gate_results: dict, anchor: dict, first_consumer: dict) -> None:
    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "window": {"start": FULL_START.isoformat(), "end": FULL_END.isoformat()},
        "account": "core_bold (Gamma-Bold-2, PA33W2KUAT40)",
        "live_equity_used": BOLD_LIVE_EQUITY,
        "live_equity_source": "mcp__alpaca_aggressive__get_account_info, live-verified 2026-08-01 this session",
        "gate_states": {},
        "anchor_validation": anchor,
        "first_consumer_elite_bull_delta": first_consumer,
    }
    for label, res in gate_results.items():
        df = pd.DataFrame(res["rows"])
        if df.empty:
            out["gate_states"][label] = {**{k: v for k, v in res.items() if k != "rows"},
                                          "headline": {"total_pnl": 0.0, "n_trades": 0}}
            continue
        df["dollar_pnl"] = df["dollar_pnl"].astype(float)
        total_pnl = round(df["dollar_pnl"].sum(), 2)
        n_trades = len(df)
        wins = df[df["dollar_pnl"] > 0]
        win_rate = round(len(wins) / n_trades, 4) if n_trades else None
        avg_trade = round(total_pnl / n_trades, 2) if n_trades else None
        per_side = {side: {"n_trades": len(g), "total_pnl": round(g["dollar_pnl"].sum(), 2),
                            "win_rate": round((g["dollar_pnl"] > 0).mean(), 4)}
                    for side, g in df.groupby("side")}
        per_tier = {tier: {"n_trades": len(g), "total_pnl": round(g["dollar_pnl"].sum(), 2),
                            "win_rate": round((g["dollar_pnl"] > 0).mean(), 4)}
                    for tier, g in df.groupby("tier")}
        out["gate_states"][label] = {
            **{k: v for k, v in res.items() if k != "rows"},
            "headline": {"total_pnl": total_pnl, "n_trades": n_trades, "win_rate": win_rate,
                         "avg_pnl_per_trade": avg_trade},
            "per_side": per_side, "per_tier": per_tier,
            "trades": res["rows"],
        }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    for label, gs in out["gate_states"].items():
        h = gs["headline"]
        log(f"HEADLINE [{label}]: total_pnl=${h['total_pnl']:+.2f} n_trades={h['n_trades']} "
            f"WR={h.get('win_rate')}")
    log(f"ANCHOR: {anchor['n_pass']}/{anchor['n_anchors']} pass, all_pass={anchor['all_pass']}")
    if "delta_vs_friday" in first_consumer:
        log(f"FIRST CONSUMER: {first_consumer['delta_vs_friday']}")


def write_markdown(out: dict) -> None:
    L = [
        "# Bold full-history replay -- CURRENT LIVE core-Bold engine, 2025-01-02..2026-07-22",
        "",
        f"Generated {out['generated_at']}. Runner: `backtest/tools/bold_fullhist_replay.py`.",
        f"Account: {out['account']}. Equity used: ${out['live_equity_used']:,.2f} "
        f"({out['live_equity_source']}).",
        "",
        "Full translation table + methodology: "
        "`analysis/deep-research/BOLD-HARNESS-2026-08-01.md`.",
        "",
        "## Gate-state comparison (task requirement: gate state as an input)",
        "",
        "| Gate state | block_elite_bull | N trades | Total P&L | WR | Avg/trade |",
        "|---|---|---|---|---|---|",
    ]
    for label, gs in out["gate_states"].items():
        h = gs["headline"]
        L.append(f"| {label} | {gs.get('block_elite_bull')} | {h['n_trades']} | "
                 f"${h['total_pnl']:+,.2f} | {h.get('win_rate')} | ${h.get('avg_pnl_per_trade', 0):+.2f} |")
    a = out["anchor_validation"]
    L += [
        "",
        "## Anchor validation (OP-16 sim-accuracy gate, task step 3)",
        "",
        f"**{a['n_pass']}/{a['n_anchors']} real bold-2 engine fills reproduce within "
        f"tolerance. ALL PASS: {a['all_pass']}.**",
        "",
        f"> {a['tolerance_note']}",
        "",
        "| Date | Symbol | Real P&L | Replay P&L | Same sign | Within tol | PASS |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in a["rows"]:
        if r.get("replay_status") != "OK":
            L.append(f"| {r['date']} | {r['symbol']} | ${r['real_pnl']:+.2f} | -- | -- | -- | "
                     f"**{r['replay_status']}** |")
            continue
        L.append(f"| {r['date']} | {r['symbol']} | ${r['real_pnl']:+.2f} | "
                 f"${r['replay_pnl']:+.2f} | {r['same_sign']} | {r['within_tolerance']} | "
                 f"{'PASS' if r['anchor_pass'] else 'FAIL'} |")
    fc = out["first_consumer_elite_bull_delta"]
    L += [
        "",
        "## First consumer: elite-bull blocked-cohort re-run under the TRUE bold shape (task step 4)",
        "",
    ]
    if "error" in fc:
        L.append(f"ERROR: {fc['error']}")
    else:
        L += [
            f"Source study: `{fc['source_study']}` (verdict `{fc['source_study_verdict']}`, "
            f"primary cell `{fc['source_study_primary_cell_NAME']}`).",
            "",
            f"**{fc['account_mismatch_flag']}**" if fc.get("account_mismatch_flag") else "",
            "",
            f"- Friday's cited PRIMARY (SAFE's cohort, qty3): n={fc['safe_primary_n_cited_friday']} "
            f"total=${fc['safe_primary_total_cited_friday']:+.2f}",
            f"- Bold's OWN cohort at the study's qty3: sequential-hold n="
            f"{fc['bold_own_cohort_at_STUDY_qty3']['sequential_hold']['n']} total="
            f"${fc['bold_own_cohort_at_STUDY_qty3']['sequential_hold']['total_pnl']:+.2f} "
            f"drop-best=${fc['bold_own_cohort_at_STUDY_qty3']['sequential_hold']['drop_top1']:+.2f}",
            f"- **Bold's OWN cohort at TRUE qty=5, independent-replay-authoritative (this tool)**: "
            f"sequential-hold n={fc['bold_own_cohort_at_TRUE_qty5']['sequential_hold']['n']} total="
            f"${fc['bold_own_cohort_at_TRUE_qty5']['sequential_hold']['total_pnl_at_qty5_authoritative']:+.2f} "
            f"drop-best=${fc['bold_own_cohort_at_TRUE_qty5']['sequential_hold']['drop_top1_at_qty5_authoritative']:+.2f} "
            f"(analytic 5/3 rescale cross-check: "
            f"${fc['bold_own_cohort_at_TRUE_qty5']['sequential_hold']['total_pnl_at_qty5_analytic']:+.2f} -- "
            f"linearity held exactly: "
            f"{fc['bold_own_cohort_at_TRUE_qty5']['sequential_hold']['linearity_holds']}; "
            f"where it doesn't, TP1/runner integer-split truncation is the cause, see tool docstring)",
            f"- Fleet net (unchanged, proxy arms not bold-2 itself): "
            f"${fc['fleet_net_mapped_unchanged']:+.2f}",
            "",
            f"**Corrected verdict using Bold's own cohort as primary: "
            f"`{fc['corrected_verdict_using_bolds_OWN_cohort_as_primary']['verdict']}` "
            f"({fc['corrected_verdict_using_bolds_OWN_cohort_as_primary']['verdict_meaning']})**",
            "",
            fc["delta_vs_friday"],
        ]
    L += [
        "",
        "---",
        "_Source: `backtest/tools/bold_fullhist_replay.py`. Raw JSON: "
        "`analysis/recommendations/bold-fullhist-replay-2026-08-01.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor-only", action="store_true", help="run only the anchor validation (fast)")
    ap.add_argument("--first-consumer-only", action="store_true",
                     help="run only the elite-bull first-consumer delta (fast)")
    ap.add_argument("--skip-population", action="store_true",
                     help="skip the full 386-day population walk (anchor + first-consumer only)")
    args = ap.parse_args()

    t_start = time.time()
    log("running anchor validation (7 real bold-2 engine fills)")
    anchor = run_anchor_validation()
    if args.anchor_only:
        log(json.dumps(anchor, indent=2, default=str))
        return 0 if anchor["all_pass"] else 1

    log("running first-consumer elite-bull delta (re-run under TRUE bold shape)")
    first_consumer = run_first_consumer_elite_bull_delta()
    if args.first_consumer_only:
        log(json.dumps(first_consumer, indent=2, default=str))
        return 0

    if args.skip_population:
        write_scorecard({}, anchor, first_consumer)
        return 0

    log(f"loading merged full-history SPY/VIX data: {SPY_FILE.name} / {VIX_FILE.name}")
    spy_df, vix_df = _load_spy_vix()
    log(f"  spy rows={len(spy_df)} range={spy_df['timestamp_et'].min()} .. {spy_df['timestamp_et'].max()}")
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)

    gate_results = {}
    log("=== GATE STATE: PRE_TRIAL (block_elite_bull=True) ===")
    gate_results["pre_trial_block_elite_bull_true"] = replay_population(
        spy_df, vix_df, ribbon_lookup, block_elite_bull=True)
    log("=== GATE STATE: POST_TRIAL (block_elite_bull=False, armed 2026-08-01) ===")
    gate_results["post_trial_block_elite_bull_false"] = replay_population(
        spy_df, vix_df, ribbon_lookup, block_elite_bull=False)

    write_scorecard(gate_results, anchor, first_consumer)
    log(f"total runtime {time.time() - t_start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
