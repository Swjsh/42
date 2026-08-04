"""fleet_arm_replay.py -- fleet-arm-faithful strike-tier + exit-P&L replay harness.

THE GAP THIS CLOSES (2026-08-02): this repo had no tool that could answer "what would arm X
look like at strike tier Y" with both (a) that arm's OWN true gated population and (b) a real
exit-P&L layer. The two existing candidates each had exactly one half:

  - `backtest/replay_fleet_arms.py` HAS the population fidelity (per-arm `gate_override`
    injected as min_triggers, direction_lock, ELITE/confluence requirement, min_confidence-
    benched-by-design) but explicitly scopes strike/qty OUT ("a separate parity check, not
    the gate" -- its own docstring) and has NO exit layer -- it only proves entry TIMING
    parity against run_backtest's raw (uniformly wrong-shaped) dollar_pnl.
  - `backtest/tools/bold_fullhist_replay.py` HAS the real exit layer (`exit_manager_walk`
    driving the REAL `automation/state/fleet/exit_manager.py#plan_exit_actions`) but
    hardcodes CORE BOLD's own gate profile (`aggressive/params.json`'s `min_triggers=1`, no
    confluence requirement, `require_bearish_fill_bar=True`) inside `bold_base_live()` --
    running it for a fleet arm would silently misrepresent that arm's population (the exact
    OP-16 sim-accuracy gap the 2026-08-02 fleet-strike-tier-atm audit correctly refused to
    paper over: "risky-1's TIGHT gate ... nor risky-3's LOOSE gate ... is modeled").

This module REUSES both rather than forking either:
  ENTRY/POPULATION layer: `replay_fleet_arms._arm_base_params` (SAFE-vs-BOLD base-params
    routing, identical to `fleet_executor._base_params_for`) + `replay_fleet_arms.
    _is_elite_triggers` (the v13b ELITE mirror) for the post-filters `run_backtest` cannot
    express (direction_lock, require_confluence_or_sequence/min_setup_quality==EXCELLENT,
    min_confidence-benched-by-design) -- imported and called, not copy-pasted.
  EXIT layer: `lib.exit_manager_walk.walk_exit_manager` driving the REAL exit_manager core,
    exactly as `bold_fullhist_replay.replay_population` / `engine_fullhist_replay.main` do --
    same ribbon-lookup/no-lookahead-alignment primitives, imported from
    `engine_fullhist_replay` (`build_ribbon_lookup`, `ribbon_tick_df_for`, `naive_dt`), not
    copy-pasted.

ONE RECONCILIATION WORTH NAMING EXPLICITLY (the strike-tier injection): `replay_fleet_arms.
_arm_run_backtest_params` deliberately does NOT touch strike (its docstring: "strike_tier_
table / position_sizing_tiers do NOT affect entry timing -- they are sizing-only"). This
module needs the OPPOSITE -- strike tier IS the whole point, taken as an INPUT -- so it
does not reuse that function verbatim. Instead it reuses a DIFFERENT existing, generic
mechanism already in `lib.orchestrator._params_to_kwargs`: pass a `v15_strike_offset_per_
tier` list (schema = `crypto.lib.strike_selection.StrikeTier`'s own fields) plus
`account_equity`, and `_params_to_kwargs` resolves the correct bracket AND applies the
live-to-sim sign negation itself (`crypto/lib/strike_selection.py` convention:
positive=ITM/negative=OTM; `simulator_real.py` convention: inverted -- this is the EXACT
trap `bold_fullhist_replay.py`'s docstring calls finding #2, `_live_to_sim_strike_offset`,
re-implemented there as a Bold-specific one-tier function; `_params_to_kwargs` already does
the same negation generically for a WHOLE table, which is what a multi-arm/multi-table tool
needs). Verified equivalent by `test_fleet_arm_replay.py::test_strike_injection_matches_
bold_fullhist_replays_manual_negation`.

SIZING: `run_backtest`'s own internal qty is a structural no-op (bold_fullhist_replay.py's
finding #1: `backtest/lib/simulator.py`'s `DEFAULT_QTY=3` already satisfies the per-trade-cap
scaling's own floor, so every `TradeFill.qty` is 3 regardless of account). Raw `TradeFill.
qty` is therefore NEVER used here. Qty is re-derived via the REAL live sizing chain, imported
and called (not reimplemented): `fleet_executor._qty_for` (the account's own
`position_sizing_tiers` table) then `fleet_executor._apply_full_send_min_sizing` (the
FULL-SEND arm-level clamp to `min_contracts`, keyed off `gate_override.full_send` -- applies
regardless of which lane an entry logically came from, exactly mirroring live `plan_all`).
`_apply_recency_min_sizing` is DELIBERATELY NOT applied by default (`apply_recency_clamp`
input, default False) -- it depends on `automation/state/recency-confirmation.json`'s
CURRENT point-in-time verdict, which has no historical time series; applying today's
snapshot across 18 months of history would silently misrepresent every other day. Disclosed,
not silently on.

EXIT SHAPE: `fleet_executor._exit_shape_dict` (registry shape + the arm's own
`params_patch.exit_patch` shallow-merge, schema-validated) -- imported and called, exactly
the function `fleet_executor.plan_all` itself uses for every live ENTER plan.

ENTRY+1 / no-lookahead: inherited for free from `walk_exit_manager` itself (its own
docstring: "a freshly-registered position's FIRST managed tick is the row strictly AFTER its
entry timestamp, never the entry row itself") -- not re-implemented here.

SYNTHETIC PRICING -- disclosed AND excluded, never blended (same convention `backtest/tools/
ladder_fullhist_replay.py` already established, reused verbatim rather than re-litigated):
any gated trade whose resolved contract has no cached OPRA bar (`backtest/data/options/
{symbol}.csv`) gets a Black-Scholes SYNTHETIC entry premium computed via `lib.pricing.
black_scholes` (participation-rate visibility only) and is EXCLUDED from every P&L/WR
aggregate -- there is still no validated mechanism anywhere in this codebase for walking a
full BS-synthetic bar series through `walk_exit_manager`'s TP1/stop/trail decisions (a single
point price cannot drive them), and C1 doctrine ("real-fills is the only WR authority") plus
this precedent both argue against inventing one under time pressure. Reported per row
(`is_synthetic`/`synthetic_entry_premium`) and in aggregate (`n_excluded_synthetic_priced`).

STRUCTURE-VETO ENTRY-LAYER GAP -- INHERITED, NOT NEW: `structure_veto_enabled` (params.json
key, Safe=True/Bold=absent-false) is consumed by `backtest/lib/engine/engine_cli.py`'s
`decide_payload`, NOT by `orchestrator.run_backtest` -- no kwarg exists to model it at the
entry layer here. `replay_fleet_arms.py` DOES model this (its own structure-veto post-filter,
built 2026-07-18) but only by replaying `decide_payload` bar-by-bar over its own narrow
8-DAY fixture window -- expensive per-bar payload construction that neither
`bold_fullhist_replay.py` nor `engine_fullhist_replay.py` pays across 18 months of history
either (both disclose the identical gap in their own docstrings: "Same gap Safe's own
engine_fullhist_replay.py has"). This module inherits that SAME accepted, precedented
full-history tradeoff rather than building a third structure-veto replay implementation --
a genuinely counter-structure entry can survive into this tool's population that the live
brain would have SKIP_STRUCTURE_VETO'd. Disclosed via `n_structure_veto_modeled: False` on
every output.

SCOPE: RIDE_THE_RIBBON family only (`BEARISH_REJECTION_RIDE_THE_RIBBON` /
`BULLISH_RECLAIM_RIDE_THE_RIBBON`) -- the two setups `orchestrator.run_backtest` models.
Matches `engine_fullhist_replay.py` / `bold_fullhist_replay.py`'s own identical disclosed
scope; `vwap_continuation` and the other extra-setups have no full-history entry-detection
harness in this repo yet on ANY of these three tools.

ANCHOR VALIDATION (OP-16 sim-accuracy gate, task requirement): validates against each arm's
OWN real historical fills, auto-mined (not hand-transcribed) from `automation/state/
fills-ledger.jsonl` via FIFO round-trip reconstruction (`mine_real_arm_fills` below) --
`attribution=='engine'` rows only (never J's manual fills). As of 2026-08-02: safe-3 n=21,
risky-1 n=18, risky-3 n=30 closed round trips, 2026-06-29..2026-07-31. Same pass criterion as
`bold_fullhist_replay.run_anchor_validation`: same win/loss SIGN and within
max($60, 30% of |real|) tolerance -- not exact-cent parity (resting-order-fill
approximation, see `exit_manager_walk.py`'s own FILL-PRICE CONVENTION docstring).
**If ANY arm's anchor pass rate is below ANCHOR_PASS_THRESHOLD, every scorecard this module
writes for that arm is labeled `"UNVALIDATED"` at the top level AND in the markdown banner --
never silently trusted just because the tool ran without an exception.**

A REAL BUG THIS ANCHOR PASS CAUGHT (2026-08-02, disclosed rather than quietly fixed and
forgotten): the first draft's FIFO reconciler tracked one accumulator per SYMBOL for its
WHOLE leg history -- since OCC symbols are date-scoped but NOT round-trip-scoped (the same
contract can be bought, fully sold, and bought again later the same day), a real risky-3
same-day re-entry on SPY260708P00741000 got blended into one fictional qty=10 anchor at a
weighted-average entry premium that never existed as a real fill, replaying to +$605 against
a real -$80. The aggregate FIFO net P&L still summed correctly ($-80 either way), which is
exactly why this class of bug survives a quick eyeball of totals -- caught only because a
PER-ANCHOR pass/fail check flagged the specific row, not because the headline number looked
wrong. Fixed by flushing and resetting the accumulator the instant a position's open_qty
returns to zero. Pass rate went 60-67% (buggy) -> 79-84% (fixed) across the three arms.

REMAINING ANCHOR MISSES (disclosed, not hidden): a residual ~15-20% still miss tolerance,
concentrated on a handful of specific contract/dates that recur across MULTIPLE arms (e.g.
2026-07-09 SPY260709C00750000 fails identically on all three) -- consistent with a SHARED,
NAMEABLE cause rather than random noise: this tool (like `bold_fullhist_replay.py` and
`engine_fullhist_replay.py` before it) applies ONE current exit shape uniformly across the
ENTIRE historical window. `strategies.py#RIBBON_RIDE.exit` itself changed shape 2026-07-09
(the SS-B structure-stop ship) and again 2026-07-20 (per-arm `exit_patch` differentiation
began existing AT ALL that date) -- a trade dated BEFORE either change is replayed under an
exit shape that was not actually live that day. This is a PRE-EXISTING, ACCEPTED limitation
of the whole fullhist-replay family (neither parent tool models point-in-time exit-shape
history either), not something newly introduced here; flagged as real follow-up work (a
point-in-time exit-shape resolver keyed on accounts.json's git history), not built tonight.

ATM-TIER LIMITATION (task requirement, stated plainly, not buried): NO real ATM fleet fills
exist yet for ANY of these three arms as of this build (2026-08-02) -- `bold_core` shipped
2026-07-31 23:13 MT after close, and Sat/Sun are non-trading. Every ATM-tier cell this tool
can currently produce is THEREFORE UN-ANCHORABLE -- it is a `strike_tiers` counterfactual
run against a population/exit layer anchored at the arm's PRE-ATM strikes, not proof the ATM
NUMBERS themselves reproduce reality. Every ATM-tier scorecard says so explicitly
(`anchor_covers_this_strike_tier: False`).

Run: backtest/.venv/Scripts/python.exe backtest/tools/fleet_arm_replay.py --arm risky-1
     backtest/.venv/Scripts/python.exe backtest/tools/fleet_arm_replay.py --arm risky-1 --strike-tiers bold_core
     backtest/.venv/Scripts/python.exe backtest/tools/fleet_arm_replay.py --anchor-only --arm safe-3
     backtest/.venv/Scripts/python.exe backtest/tools/fleet_arm_replay.py --all-arms
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]           # backtest/
ROOT = REPO.parent                                     # repo root
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
CRYPTO_LIB = ROOT / "crypto" / "lib"
for _p in (str(ROOT), str(REPO), str(REPO / "tools"), str(FLEET_DIR), str(CRYPTO_LIB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import replay_fleet_arms as rfa            # noqa: E402 -- population/gate reuse
import engine_fullhist_replay as efr        # noqa: E402 -- ribbon/alignment/matcher reuse
import fleet_executor as fx                 # noqa: E402 -- sizing/exit-shape reuse
import fills_fifo as _fills_fifo            # noqa: E402 -- the ONE FIFO round-trip miner (extracted 2026-08-04)
import strategies as fleet_strategies       # noqa: E402  -- automation/state/fleet/strategies.py
import strike_selection as ss               # noqa: E402  -- crypto/lib/strike_selection.py
from lib.orchestrator import run_backtest, _params_to_kwargs  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager            # noqa: E402
from lib.option_pricing_real import load_contract_bars, option_symbol  # noqa: E402
from lib.pricing import black_scholes, time_to_expiry_years, vix_to_iv  # noqa: E402
from lib.et_frame import parse_timestamp_et, FRAME_WALL_V1, FRAME_ET_V2  # noqa: E402

DATA = REPO / "data"
# Full-history population window -- SAME merged files bold_fullhist_replay.py /
# engine_fullhist_replay.py use, apples-to-apples with those two scorecards.
SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 22)

# Anchor window -- a MORE RECENT file than the merged full-history pair (anchors are real
# fills through 2026-07-31; matches bold_fullhist_replay.run_anchor_validation's own choice
# of a separate, fresher SPY file for exactly this reason).
ANCHOR_SPY_FILE = DATA / "spy_5m_2026-05-19_2026-07-31.csv"

TIME_STOP_ET = dt.time(15, 40)  # matches every base params file's time_stop_et="15:40"

ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
FILLS_LEDGER_PATH = ROOT / "automation" / "state" / "fills-ledger.jsonl"

ANCHOR_TOLERANCE_PCT = 0.30
ANCHOR_TOLERANCE_DOLLARS = 60.0   # matches bold_fullhist_replay.py's own tolerance exactly
# 0.70 matches this repo's own walk-forward gate bar (OP-16: "WF >= 0.70"), reused here for
# consistency rather than inventing a new threshold. Live-verified 2026-08-02 (post FIFO-bug
# fix): safe-3 81% (22/27), risky-1 79% (19/24), risky-3 84% (32/38) -- all three clear it.
ANCHOR_PASS_THRESHOLD = 0.70      # below this fraction of anchors passing -> UNVALIDATED banner

OUT_DIR = ROOT / "analysis" / "recommendations"

_NAMED_TABLES = {
    "safe": ss.V15_SAFE_TIERS,
    "bold": ss.V15_BOLD_TIERS,
    "bold_core": ss.V15_BOLD_CORE_TIERS,
    "probe": fx.PROBE_STRIKE_TIERS,
}

# LIVE-VERIFIED EQUITY (2026-08-02, setup/scripts/accounts_status.py re-run fresh this
# session -- cross-checked against analysis/recommendations/fleet-strike-tier-atm-2026-08-02.
# md's own live-verify, exact match, zero drift since it's a paper account and Sat/Sun are
# non-trading). USED AS THE DEFAULT (not accounts.json's frozen `starting_equity`) because
# $2,000.00 -- the frozen grid value -- sits EXACTLY ON the bold_core/V15_BOLD_TIERS tier
# boundary (`equity_min=2000.0` is the START of the OTM-2 bracket, not the END of the ATM
# one -- pick_tier's own `t.equity_min <= equity < t.equity_max` semantics), so defaulting to
# the frozen value would silently price every risky-1/risky-3 report at OTM-2 instead of the
# ATM tier that is the entire subject of tonight's audit. Matches this tool family's own
# established precedent of a hardcoded LIVE-VERIFIED equity constant (bold_fullhist_replay.
# py's BOLD_LIVE_EQUITY), not a new convention. A caller can always override via `equity=`.
LIVE_EQUITY_2026_08_02 = {"safe-3": 1967.81, "risky-1": 1756.87, "risky-3": 2121.61}


def log(msg: str) -> None:
    print(f"[fleet-arm-replay] {msg}", flush=True)


def resolve_strike_tiers(name_or_table) -> tuple:
    """String name ('safe'/'bold'/'bold_core'/'probe') -> the matching StrikeTier tuple;
    an already-built Sequence[StrikeTier] passes through unchanged (so a study can hand in
    a bespoke table, e.g. to test a hypothetical tier ladder nobody has shipped yet)."""
    if isinstance(name_or_table, str):
        key = name_or_table.lower()
        if key not in _NAMED_TABLES:
            raise ValueError(f"unknown strike tier table name {name_or_table!r} -- "
                              f"known: {sorted(_NAMED_TABLES)}, or pass a StrikeTier sequence")
        return _NAMED_TABLES[key]
    return tuple(name_or_table)


def _accounts() -> dict:
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


def _arm(accounts: dict, arm_id: str) -> dict:
    for a in accounts["arms"]:
        if a.get("id") == arm_id:
            return a
    raise KeyError(arm_id)


# =====================================================================================
# CONFIG -- the INPUT surface (task requirement: "ARM + gate_override + strike tier table +
# sizing + exit shape as INPUTS"). Every field defaults to the arm's OWN accounts.json
# config when not overridden, so `ArmReplayConfig.for_arm("risky-1")` alone reproduces the
# arm exactly as configured; any field can be swapped for a counterfactual study without
# touching accounts.json or any other live file.
# =====================================================================================
@dataclasses.dataclass(frozen=True)
class ArmReplayConfig:
    arm_id: str
    gate_override: dict                     # {} => ungated (no min_triggers/confluence bar)
    direction_lock: Optional[str]           # "PUT_ONLY" | "CALL_ONLY" | None
    strike_tiers: tuple                     # resolved StrikeTier tuple (task's "strike tier table")
    equity: float                           # drives BOTH the strike bracket and position_sizing_tiers
    exit_patch: dict                        # shallow-merged over the strategy's registry ExitShape
    min_contracts: int                      # the FULL-SEND / floor clamp target
    full_send: bool                         # arm-level flag (NOT lane-specific -- mirrors _apply_full_send_min_sizing)
    apply_recency_clamp: bool = False       # deliberately default-off, see module docstring
    structure_stop_enabled: bool = False    # from the arm's OWN base params, not guessed
    strike_tiers_label: str = "custom"      # for report legibility only

    @classmethod
    def for_arm(cls, arm_id: str, accounts: Optional[dict] = None, **overrides) -> "ArmReplayConfig":
        """Build a config that reproduces `arm_id` exactly as accounts.json has it TODAY,
        with any field in `overrides` replacing the arm's own value. This is the ONE
        constructor call this module expects external callers to use.

        EQUITY DEFAULT: LIVE_EQUITY_2026_08_02 when this arm has an entry there, else the
        arm's frozen accounts.json `starting_equity` (disclosed via the fallback itself never
        raising) -- see LIVE_EQUITY_2026_08_02's own comment for why the frozen $2,000 value
        is actively wrong to default to for risky-1/risky-3 specifically."""
        accounts = accounts or _accounts()
        arm = _arm(accounts, arm_id)
        base_params = rfa._arm_base_params(arm)  # SAFE-vs-BOLD routing, reused verbatim
        g = dict(arm.get("gate_override") or {})
        patch = arm.get("params_patch") or {}
        exit_patch = dict(patch.get("exit_patch") or {})
        table_name = arm.get("strike_tier_table") or patch.get("strike_tier_table")
        if not table_name:
            table_name = "safe" if str(arm_id).startswith("safe") else "bold"
        default_equity = LIVE_EQUITY_2026_08_02.get(arm_id, float(arm.get("starting_equity") or 2000.0))
        kw = dict(
            arm_id=arm_id,
            gate_override=g,
            direction_lock=arm.get("direction_lock"),
            strike_tiers=resolve_strike_tiers(table_name),
            equity=float(default_equity),
            exit_patch=exit_patch,
            min_contracts=int(base_params.get("min_contracts", 3)),
            full_send=bool(g.get("full_send")),
            # structure_stop_enabled is read directly from the arm's OWN base params, NOT
            # derived from structure_veto_enabled -- two DIFFERENT keys (see module
            # docstring's STRUCTURE-VETO section). The exit layer's stop_mode="structure"
            # activation gate is params.json's own `structure_stop_enabled`, independent of
            # the entry-layer veto this tool does not model.
            structure_stop_enabled=bool(base_params.get("structure_stop_enabled", False)),
            strike_tiers_label=str(table_name),
        )
        if "strike_tiers" in overrides and isinstance(overrides["strike_tiers"], str):
            overrides = {**overrides, "strike_tiers": resolve_strike_tiers(overrides["strike_tiers"]),
                        "strike_tiers_label": overrides["strike_tiers"]}
        kw.update(overrides)
        # re-derive full_send from a caller-supplied gate_override override (a counterfactual
        # "what if this gate_override didn't have full_send" must actually change the clamp)
        if "gate_override" in overrides and "full_send" not in overrides:
            kw["full_send"] = bool(overrides["gate_override"].get("full_send"))
        return cls(**kw)

    def effective_arm(self) -> dict:
        """A synthetic arm-shaped mapping carrying THIS config's values (not accounts.json's
        on-disk ones) -- threaded into every reused fleet_executor helper so a counterfactual
        gate_override/exit_patch/full_send actually changes what those helpers compute,
        instead of silently reading the disk default underneath an override."""
        return {
            "id": self.arm_id,
            "gate_override": {**self.gate_override, "full_send": self.full_send} if self.full_send
                              else {k: v for k, v in self.gate_override.items() if k != "full_send"},
            "direction_lock": self.direction_lock,
            "params_patch": {"exit_patch": self.exit_patch} if self.exit_patch else {},
        }


# =====================================================================================
# POPULATION layer -- reuses replay_fleet_arms's SAFE/BOLD base-params routing + ELITE
# mirror; the ONE new piece is strike-tier injection via _params_to_kwargs's generic
# v15_strike_offset_per_tier + account_equity mechanism (see module docstring).
# =====================================================================================
def _run_backtest_params(config: ArmReplayConfig, accounts: dict) -> dict:
    arm = _arm(accounts, config.arm_id)
    p = rfa._arm_base_params(arm)  # deep copy, SAFE or BOLD base -- reused, not reimplemented
    mt = config.gate_override.get("min_triggers")
    if mt is not None:
        p["filter_10_min_triggers_bear"] = int(mt)
        p["filter_10_min_triggers_bull"] = int(mt)
    p["v15_strike_offset_per_tier"] = [dataclasses.asdict(t) for t in config.strike_tiers]
    return p


def gated_population(
    config: ArmReplayConfig, spy: pd.DataFrame, vix: pd.DataFrame,
    start: dt.date, end: dt.date, accounts: Optional[dict] = None,
) -> tuple[list, list[str], bool]:
    """This arm's TRUE gated population over [start, end] at config.strike_tiers/equity.

    Mirrors replay_fleet_arms._ground_truth_trades's post-filter cascade EXACTLY (direction_
    lock -> ELITE/confluence requirement -> min_confidence-benched-by-design), reusing its
    `_is_elite_triggers` rather than re-deriving the ELITE definition a second time. The ONE
    divergence from that function (documented, not silent): strike tier is injected here
    (via v15_strike_offset_per_tier, see module docstring) because THIS tool's whole purpose
    is strike-tier counterfactuals, whereas replay_fleet_arms.py deliberately scopes strike
    out of its own entry-timing-only fidelity check.

    Returns (trades, notes, benched_by_confidence) -- same 3-tuple shape (minus the raw
    BacktestResult, which callers here don't need) as _ground_truth_trades's own return."""
    accounts = accounts or _accounts()
    arm = _arm(accounts, config.arm_id)
    p = _run_backtest_params(config, accounts)
    kw = _params_to_kwargs(p, account_equity=config.equity)
    # use_real_fills=True is NOT expressible via the params-overrides dict (_params_to_kwargs
    # has no mapping for it -- confirmed by reading the function) and run_backtest's own
    # default is False (backtest/lib/orchestrator.py:477) -- every hand-built BASE dict in
    # this codebase's fullhist-replay family sets it explicitly for exactly this reason
    # (elite_bear_level_reject_gate_ab.SAFE_BASE, bold_fullhist_replay.bold_base_live both do
    # this as their literal first line). Passed as an explicit kwarg, not through `kw`, since
    # replay_fleet_arms.py's own population path (entry-TIMING fidelity only, never reads
    # entry_premium/dollar_pnl) does not need and does not set this -- a real divergence from
    # what this module reuses from it, documented here rather than silently inherited.
    res = run_backtest(spy, vix, start_date=start, end_date=end, use_real_fills=True, **kw)
    trades = list(res.trades)
    notes: list[str] = [f"v15_strike_offset_per_tier injected @ equity=${config.equity:,.2f} "
                        f"-> resolved sim strike_offset={kw.get('strike_offset')} "
                        f"(table={config.strike_tiers_label})"]

    dl = config.direction_lock
    if dl == "PUT_ONLY":
        trades = [t for t in trades if getattr(t, "side", "P") == "P"]
        notes.append("direction_lock=PUT_ONLY -> keep P only")
    elif dl == "CALL_ONLY":
        trades = [t for t in trades if getattr(t, "side", "C") == "C"]
        notes.append("direction_lock=CALL_ONLY -> keep C only")

    g = config.gate_override
    if g.get("require_confluence_or_sequence") or str(g.get("min_setup_quality", "")).upper() == "EXCELLENT":
        trades = [t for t in trades if rfa._is_elite_triggers(getattr(t, "triggers_fired", []))]
        notes.append("require ELITE (confluence/sequence) -> keep ELITE only")

    benched_by_confidence = False
    if g.get("min_confidence") is not None:
        trades = []
        benched_by_confidence = True
        notes.append(f"min_confidence={g['min_confidence']} on confidence-less signal -> "
                     "benched by design (population EMPTY) -- same finding replay_fleet_arms.py made")

    return trades, notes, benched_by_confidence


# =====================================================================================
# SIZING + EXIT SHAPE -- reused verbatim from fleet_executor, never reimplemented.
# =====================================================================================
def resolve_qty(config: ArmReplayConfig, elite: bool, base_params: dict) -> Optional[int]:
    eff = config.effective_arm()
    tiers = base_params.get("position_sizing_tiers")
    qty = fx._qty_for(tiers, config.equity, elite)
    if qty is None:
        return None
    qty, _note = fx._apply_full_send_min_sizing(qty, eff, {"min_contracts": config.min_contracts})
    if config.apply_recency_clamp:
        qty, _note2 = fx._apply_recency_min_sizing(
            qty, fleet_strategies.RIBBON_RIDE.name,
            {"recency_min_size_enabled": True, "min_contracts": config.min_contracts})
    return qty


def resolve_exit_shape(config: ArmReplayConfig) -> dict:
    """ribbon_ride's registry shape + this config's exit_patch -- reuses
    fleet_executor._exit_shape_dict (schema-validated merge), the SAME function
    fleet_executor.plan_all calls for every live ENTER plan. Scope: ribbon_ride only, see
    module docstring's SCOPE section."""
    return fx._exit_shape_dict(fleet_strategies.RIBBON_RIDE, config.effective_arm())


# =====================================================================================
# SYNTHETIC fallback (disclosed, excluded -- ladder_fullhist_replay.py's precedent, reused).
# =====================================================================================
def _synthetic_entry_premium(spot: float, strike: int, side: str, vix_now: float,
                             entry_time_et: dt.datetime) -> float:
    is_call = side == "C"
    iv = vix_to_iv(vix_now)
    tte = time_to_expiry_years(entry_time_et)
    price, _delta = black_scholes(spot, strike, iv, tte, is_call=is_call)
    return round(max(price, 0.01), 4)


# =====================================================================================
# MAIN WALK -- entry (gated population, correctly-tiered strike) + exit (real
# exit_manager_walk) in one pass. Mirrors bold_fullhist_replay.replay_population's shape.
# =====================================================================================
def replay_arm(
    config: ArmReplayConfig, spy: pd.DataFrame, vix: pd.DataFrame, ribbon_lookup: pd.DataFrame,
    start: dt.date, end: dt.date, accounts: Optional[dict] = None,
) -> dict:
    accounts = accounts or _accounts()
    arm = _arm(accounts, config.arm_id)
    base_params = rfa._arm_base_params(arm)
    exit_shape = resolve_exit_shape(config)

    t0 = time.time()
    trades, notes, benched = gated_population(config, spy, vix, start, end, accounts)
    entry_elapsed = time.time() - t0
    log(f"[{config.arm_id} @ {config.strike_tiers_label}] population: {len(trades)} gated entries "
        f"({entry_elapsed:.1f}s) benched_by_confidence={benched}")

    rows: list[dict] = []
    n_no_opra = 0
    n_synthetic = 0
    t1 = time.time()
    for t in trades:
        edate = efr.naive_dt(t.entry_time_et).date()
        # STRIKE: re-derived from THIS config's own tier table (never the raw TradeFill.strike
        # -- run_backtest already priced it correctly here because config.strike_tiers was
        # injected into the SAME run_backtest call via v15_strike_offset_per_tier, so t.strike
        # IS the config's strike; re-deriving would be redundant, not a second source of truth
        # -- kept as t.strike deliberately, ONE computation, not two that could drift).
        strike = int(t.strike)
        symbol = option_symbol(edate, strike, t.side)
        opt_df = load_contract_bars(symbol)
        day_spy = spy.loc[spy["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            continue
        entry_time_et = efr.naive_dt(t.entry_time_et)
        elite = rfa._is_elite_triggers(getattr(t, "triggers_fired", []))
        qty = resolve_qty(config, elite, base_params)
        if qty is None:
            continue
        trigger_level = float(t.rejection_level) if getattr(t, "rejection_level", None) else None
        tier_label = fleet_strategies_tier(getattr(t, "triggers_fired", []))

        if opt_df is None:
            n_no_opra += 1
            vix_same_day = vix.loc[vix["timestamp_et"].dt.date == edate]
            vix_at_or_before = vix_same_day.loc[vix_same_day["timestamp_et"] <= pd.Timestamp(entry_time_et)]
            vix_now = float(vix_at_or_before.iloc[-1]["close"]) if not vix_at_or_before.empty else 18.0
            # spot = the day's SPY bar at-or-before entry_time_et (TradeFill carries no .spot
            # field -- confirmed by reading simulator's TradeFill dataclass; re-derive from
            # day_spy instead of guessing at an attribute that doesn't exist).
            spot_bars = day_spy.loc[day_spy["timestamp_et"] <= pd.Timestamp(entry_time_et)]
            spot_now = float(spot_bars.iloc[-1]["close"]) if not spot_bars.empty else float(strike)
            synth = _synthetic_entry_premium(spot_now, strike, t.side, vix_now, entry_time_et)
            n_synthetic += 1
            rows.append({
                "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
                "setup": t.setup, "side": t.side, "tier": tier_label, "symbol": symbol,
                "qty": qty, "triggers": list(getattr(t, "triggers_fired", []) or []),
                "trigger_level": trigger_level, "is_synthetic": True,
                "synthetic_entry_premium": synth, "dollar_pnl": None, "exit_reason": None,
                "excluded_from_headline": True, "exclude_reason": "no_opra_cache_synthetic_disclosed_only",
            })
            continue

        entry_premium = float(t.entry_premium)
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=entry_time_et, entry_premium=entry_premium,
            qty=qty, exit_shape=exit_shape, structure_stop_enabled=config.structure_stop_enabled,
            trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        rows.append({
            "date": edate.isoformat(), "entry_time_et": entry_time_et.isoformat(),
            "setup": t.setup, "side": t.side, "tier": tier_label, "symbol": symbol,
            "qty": qty, "entry_premium": round(entry_premium, 4),
            "triggers": list(getattr(t, "triggers_fired", []) or []), "trigger_level": trigger_level,
            "is_synthetic": False, "synthetic_entry_premium": None,
            "dollar_pnl": res.dollar_pnl, "exit_reason": res.exit_reason,
            "resolved_stop_mode": res.stop_mode, "hold_minutes": res.hold_minutes,
            "n_ticks_walked": res.n_ticks_walked, "resolved": res.resolved,
            "excluded_from_headline": False, "exclude_reason": None,
        })
    exit_elapsed = time.time() - t1
    n_real = sum(1 for r in rows if not r["excluded_from_headline"])
    log(f"[{config.arm_id} @ {config.strike_tiers_label}] exit re-derivation done "
        f"({exit_elapsed:.1f}s) -- n_real_fills={n_real} n_synthetic_disclosed={n_synthetic}")

    return {
        "arm_id": config.arm_id, "strike_tiers_label": config.strike_tiers_label,
        "equity": config.equity, "gate_override": config.gate_override,
        "direction_lock": config.direction_lock, "min_contracts": config.min_contracts,
        "full_send": config.full_send, "exit_shape": exit_shape,
        "structure_stop_enabled": config.structure_stop_enabled,
        "n_structure_veto_modeled": False,  # see module docstring
        "rows": rows,
        "n_raw_gated_entries": len(trades), "n_excluded_synthetic_priced": n_synthetic,
        "n_excluded_no_spy_day": sum(1 for t in trades
                                     if spy.loc[spy["timestamp_et"].dt.date == efr.naive_dt(t.entry_time_et).date()].empty),
        "benched_by_confidence": benched,
        "population_notes": notes,
        "entry_layer_seconds": round(entry_elapsed, 1), "exit_layer_seconds": round(exit_elapsed, 1),
    }


def fleet_strategies_tier(triggers) -> str:
    """Same tier convention every study in this codebase uses (see
    elite_bear_level_reject_gate_ab.classify_tier's own docstring citing this list) --
    imported indirectly via rfa is unnecessary since classify_tier lives in
    elite_bear_level_reject_gate_ab, not replay_fleet_arms; call it directly."""
    import elite_bear_level_reject_gate_ab as eb  # local import: only needed here, avoids
    return eb.classify_tier(triggers)              # a module-level name collision with `eb` unused elsewhere


# =====================================================================================
# ANCHOR VALIDATION -- auto-mined REAL fills (not hand-transcribed) via FIFO reconstruction.
# =====================================================================================
def mine_real_arm_fills(arm_id: str, ledger_path: Path = FILLS_LEDGER_PATH) -> list[dict]:
    """FIFO-reconstruct CLOSED round trips for `arm_id` from fills-ledger.jsonl,
    `attribution=='engine'` rows only (never J's manual fills -- same discipline
    bold_fullhist_replay.ANCHOR_FILLS's own hand-mining used, here automated and exhaustive
    instead of a hand-picked sample). Returns bold_fullhist_replay.ANCHOR_FILLS-shaped
    dicts: date/symbol/side/entry_ts_et/entry_premium/exit_ts_et/exit_premium/qty/real_pnl.

    BODY EXTRACTED VERBATIM (2026-08-04) to `automation/state/fleet/fills_fifo.py` so the
    stdlib-only weekly divergence instrument (`setup/scripts/full_send_vs_gated.py`) shares
    the SAME implementation instead of drifting a second FIFO copy (C14). The same-day
    re-entry flush fix (2026-08-02: one risky-3 anchor blended to +$605 vs real -$80 --
    see the git history of THIS file for the full narrative) lives there now; this
    re-export keeps every existing caller and test (`test_fleet_arm_replay.py`) exercising
    that one body through the original name + signature."""
    return _fills_fifo.mine_real_arm_fills(arm_id, ledger_path=ledger_path)


def _load_arm_trigger_levels(arm_id: str) -> dict:
    """Best-effort trigger_level recovery from the per-arm decisions.jsonl (mostly-null in
    practice for fleet arms -- see module note; fail-open to premium-stop-only, exactly like
    bold_fullhist_replay._load_trigger_levels_from_decisions does for core-Bold's own
    ledger)."""
    path = FLEET_DIR / arm_id / "decisions.jsonl"
    if not path.exists():
        return {}
    out: dict = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            tl = row.get("trigger_level")
            sym = (row.get("placement") or {}).get("symbol")
            ts = row.get("ts_et")
            if tl is not None and sym and ts:
                out[(sym, ts[:16])] = float(tl)  # minute-resolution match
    except OSError:
        return {}
    return out


def run_anchor_validation(config: ArmReplayConfig, spy_df: pd.DataFrame,
                          ribbon_lookup: pd.DataFrame) -> dict:
    """Replays each of this arm's REAL fills (mine_real_arm_fills) through the SAME
    exit_shape/structure_stop_enabled this config resolves for the counterfactual runs --
    i.e. the anchor validates the EXIT-LAYER + SIZING fidelity (known real entry premium/
    qty/time, nothing re-detected), same discipline as bold_fullhist_replay.
    run_anchor_validation."""
    fills = mine_real_arm_fills(config.arm_id)
    exit_shape = resolve_exit_shape(config)
    trigger_levels = _load_arm_trigger_levels(config.arm_id)
    rows = []
    n_pass = 0
    for a in fills:
        symbol = a["symbol"]
        opt_df = load_contract_bars(symbol)
        if opt_df is None or a["entry_premium"] is None:
            rows.append({**a, "replay_status": "NO_OPRA_CACHE_OR_NO_ENTRY_PREMIUM"})
            continue
        edate = dt.date.fromisoformat(a["date"])
        day_spy = spy_df.loc[spy_df["timestamp_et"].dt.date == edate].reset_index(drop=True)
        if day_spy.empty:
            rows.append({**a, "replay_status": "NO_SPY_DAY"})
            continue
        entry_time_et = dt.datetime.fromisoformat(a["entry_ts_et"])
        rtd = efr.ribbon_tick_df_for(opt_df, ribbon_lookup)
        trigger_level = trigger_levels.get((symbol, a["entry_ts_et"][:16]))
        res = walk_exit_manager(
            symbol=symbol, side=a["side"], entry_time_et=entry_time_et,
            entry_premium=a["entry_premium"], qty=a["qty"], exit_shape=exit_shape,
            structure_stop_enabled=config.structure_stop_enabled, trigger_level=trigger_level,
            strategy="ribbon_ride", time_stop_et=TIME_STOP_ET, opt_df=opt_df,
            ribbon_tick_df=rtd, five_min_spy_df=day_spy,
        )
        real_pnl = a["real_pnl"]
        replay_pnl = res.dollar_pnl
        same_sign = (real_pnl > 0) == (replay_pnl > 0) or (real_pnl == 0 and replay_pnl == 0)
        tol = max(ANCHOR_TOLERANCE_DOLLARS, abs(real_pnl) * ANCHOR_TOLERANCE_PCT)
        within_tol = abs(replay_pnl - real_pnl) <= tol
        row_pass = same_sign and within_tol
        n_pass += int(row_pass)
        rows.append({
            **a, "trigger_level_used": trigger_level, "replay_pnl": replay_pnl,
            "replay_exit_reason": res.exit_reason, "replay_hold_minutes": res.hold_minutes,
            "same_sign": same_sign, "tolerance_dollars": round(tol, 2),
            "within_tolerance": within_tol, "anchor_pass": row_pass, "replay_status": "OK",
        })
    n_anchors = len(fills)
    pass_rate = (n_pass / n_anchors) if n_anchors else 0.0
    return {
        "arm_id": config.arm_id, "n_anchors": n_anchors, "n_pass": n_pass,
        "pass_rate": round(pass_rate, 4), "all_pass": (n_anchors > 0 and n_pass == n_anchors),
        "unvalidated": (n_anchors == 0 or pass_rate < ANCHOR_PASS_THRESHOLD),
        "unvalidated_threshold": ANCHOR_PASS_THRESHOLD,
        "tolerance_note": (f"pass = same win/loss sign AND |replay-real| <= "
                            f"max(${ANCHOR_TOLERANCE_DOLLARS}, {ANCHOR_TOLERANCE_PCT:.0%} of "
                            f"|real|) -- same convention as bold_fullhist_replay.py's own "
                            f"anchor gate; exact-cent parity not expected (resting-order-fill "
                            f"approximation, see exit_manager_walk.py's FILL-PRICE CONVENTION)."),
        "rows": rows,
    }


# =====================================================================================
# SCORECARD -- JSON + markdown, UNVALIDATED banner is load-bearing (task requirement).
# =====================================================================================
def _headline(rows: list[dict]) -> dict:
    real = [r for r in rows if not r["excluded_from_headline"]]
    if not real:
        return {"total_pnl": 0.0, "n_trades": 0, "win_rate": None, "avg_pnl_per_trade": None}
    df = pd.DataFrame(real)
    df["dollar_pnl"] = df["dollar_pnl"].astype(float)
    total = round(df["dollar_pnl"].sum(), 2)
    n = len(df)
    wr = round((df["dollar_pnl"] > 0).mean(), 4)
    return {"total_pnl": total, "n_trades": n, "win_rate": wr, "avg_pnl_per_trade": round(total / n, 2)}


def write_scorecard(replay_out: dict, anchor_out: dict, config: ArmReplayConfig,
                    window: tuple[dt.date, dt.date], out_stub: str) -> None:
    unvalidated = anchor_out["unvalidated"]
    anchor_covers_strike_tier = (anchor_out["n_anchors"] > 0
                                 and config.strike_tiers_label != "probe"
                                 and _tier_predates_or_matches_anchor_history(config))
    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "verdict_label": "UNVALIDATED" if unvalidated else "ANCHOR-VALIDATED",
        "unvalidated_reason": (
            None if not unvalidated else
            (f"{anchor_out['n_pass']}/{anchor_out['n_anchors']} real fills reproduce within "
             f"tolerance ({anchor_out['pass_rate']:.0%} < {ANCHOR_PASS_THRESHOLD:.0%} threshold)"
             if anchor_out["n_anchors"] > 0 else "zero real fills available to anchor against")
        ),
        "anchor_covers_this_strike_tier": anchor_covers_strike_tier,
        "atm_tier_limitation": (
            "NO real fills exist yet at ANY ATM-priced tier for this arm as of this build "
            "(bold_core shipped 2026-07-31 23:13 MT after close; weekend is non-trading) -- "
            "this cell's population/exit fidelity is anchored against this arm's OLDER "
            "(pre-ATM) real fills, NOT proof the ATM numbers themselves reproduce reality."
            if not anchor_covers_strike_tier and config.strike_tiers_label in ("bold_core",) else None
        ),
        "window": {"start": window[0].isoformat(), "end": window[1].isoformat()},
        "config": {
            "arm_id": config.arm_id, "gate_override": config.gate_override,
            "direction_lock": config.direction_lock,
            "strike_tiers_label": config.strike_tiers_label,
            "strike_tiers": [dataclasses.asdict(t) for t in config.strike_tiers],
            "equity": config.equity, "exit_patch": config.exit_patch,
            "min_contracts": config.min_contracts, "full_send": config.full_send,
            "apply_recency_clamp": config.apply_recency_clamp,
            "structure_stop_enabled": config.structure_stop_enabled,
        },
        "anchor_validation": anchor_out,
        "population": {
            "n_raw_gated_entries": replay_out["n_raw_gated_entries"],
            "n_excluded_synthetic_priced": replay_out["n_excluded_synthetic_priced"],
            "n_excluded_no_spy_day": replay_out["n_excluded_no_spy_day"],
            "benched_by_confidence": replay_out["benched_by_confidence"],
            "notes": replay_out["population_notes"],
            "n_structure_veto_modeled": replay_out["n_structure_veto_modeled"],
        },
        "headline": _headline(replay_out["rows"]),
        "runtime_seconds": {"entry": replay_out["entry_layer_seconds"],
                            "exit": replay_out["exit_layer_seconds"]},
        "trades": replay_out["rows"],
    }
    out_json = OUT_DIR / f"{out_stub}.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {out_json}")
    write_markdown(out, OUT_DIR / f"{out_stub}.md")
    h = out["headline"]
    log(f"HEADLINE [{config.arm_id}@{config.strike_tiers_label}] verdict={out['verdict_label']} "
        f"total_pnl=${h['total_pnl']:+.2f} n_trades={h['n_trades']} WR={h.get('win_rate')} "
        f"anchor={anchor_out['n_pass']}/{anchor_out['n_anchors']}")



# The strike table each fleet_rest arm ACTUALLY traded real fills under, before the
# 2026-08-01 bold_core extension (commit 43bb979d) -- NOT an id-prefix guess. safe-3 is
# "bold" here deliberately: it has used strike_tier_table='bold' since the 2026-06-25 grid
# rebuild (its own params_patch doc: "to fit the $600 notional cap at $2K equity"), so a
# naive "safe arms historically used V15_SAFE_TIERS" assumption would be WRONG for it
# specifically and would falsely report its (unchanged) real fills as "not covering" its
# own (also unchanged) current tier. risky-1/risky-3 were "bold" (id-prefix default) before
# 43bb979d repointed them to "bold_core" -- this dict is the pre-ship truth for all three.
PRE_BOLD_CORE_HISTORICAL_TABLE = {
    "safe-3": ss.V15_BOLD_TIERS, "risky-1": ss.V15_BOLD_TIERS, "risky-3": ss.V15_BOLD_TIERS,
}


def _tier_predates_or_matches_anchor_history(config: ArmReplayConfig) -> bool:
    """True iff every real fill this arm has ever logged was ALREADY priced under a table
    that agrees with config.strike_tiers at config.equity (i.e. the anchor's own strikes
    are direct evidence for THIS cell, not just the exit-layer mechanics in general).
    Compares config's resolved offset at config.equity against PRE_BOLD_CORE_HISTORICAL_
    TABLE's offset at the same equity (the table every real fill so far was actually priced
    under) -- False (not covered) whenever they disagree, e.g. any 'bold_core'/'probe' cell
    in the ATM bracket. Falls back to a bold/safe id-prefix guess only for an arm this dict
    doesn't name (future-proofing, disclosed via the fallback itself never raising)."""
    fallback_table = PRE_BOLD_CORE_HISTORICAL_TABLE.get(
        config.arm_id, ss.V15_SAFE_TIERS if config.arm_id.startswith("safe") else ss.V15_BOLD_TIERS)
    this_offset = ss.pick_tier(config.equity, config.strike_tiers).strike_offset
    historical_offset = ss.pick_tier(config.equity, fallback_table).strike_offset
    return this_offset == historical_offset


def write_markdown(out: dict, path: Path) -> None:
    cfg = out["config"]
    a = out["anchor_validation"]
    h = out["headline"]
    banner = (
        f"# {out['verdict_label']} -- fleet arm replay: {cfg['arm_id']} @ {cfg['strike_tiers_label']}"
    )
    L = [banner, ""]
    if out["verdict_label"] == "UNVALIDATED":
        L += [
            f"> **UNVALIDATED. {out['unvalidated_reason']}.** Every number below is a model "
            "output, not a confirmed-against-reality result. Treat as directional only.",
            "",
        ]
    if out.get("atm_tier_limitation"):
        L += [f"> **ATM-TIER LIMITATION:** {out['atm_tier_limitation']}", ""]
    L += [
        f"Generated {out['generated_at']}. Runner: `backtest/tools/fleet_arm_replay.py`.",
        f"Window: {out['window']['start']} .. {out['window']['end']}.",
        "",
        "## Config (all INPUTS -- every field overridable)",
        "",
        f"- arm_id: `{cfg['arm_id']}`",
        f"- gate_override: `{cfg['gate_override']}`",
        f"- direction_lock: `{cfg['direction_lock']}`",
        f"- strike_tiers: `{cfg['strike_tiers_label']}` = {cfg['strike_tiers']}",
        f"- equity: ${cfg['equity']:,.2f}",
        f"- exit_patch: `{cfg['exit_patch']}`",
        f"- min_contracts: {cfg['min_contracts']} | full_send: {cfg['full_send']}",
        f"- structure_stop_enabled: {cfg['structure_stop_enabled']} | "
        f"structure_veto entry-layer modeled: {out['population']['n_structure_veto_modeled']} "
        "(inherited disclosed gap, see module docstring)",
        "",
        "## Anchor validation (OP-16 sim-accuracy gate)",
        "",
        f"**{a['n_pass']}/{a['n_anchors']} real {cfg['arm_id']} engine fills reproduce within "
        f"tolerance ({a['pass_rate']:.0%}). ALL PASS: {a['all_pass']}.**",
        "",
        f"> {a['tolerance_note']}",
        "",
        "| Date | Symbol | Real P&L | Replay P&L | Same sign | Within tol | PASS |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in a["rows"]:
        if r.get("replay_status") != "OK":
            L.append(f"| {r['date']} | {r['symbol']} | ${r.get('real_pnl', 0):+.2f} | -- | -- | -- | "
                     f"**{r['replay_status']}** |")
            continue
        L.append(f"| {r['date']} | {r['symbol']} | ${r['real_pnl']:+.2f} | ${r['replay_pnl']:+.2f} | "
                 f"{r['same_sign']} | {r['within_tolerance']} | {'PASS' if r['anchor_pass'] else 'FAIL'} |")
    L += [
        "",
        "## Population",
        "",
        f"- Raw gated entries: {out['population']['n_raw_gated_entries']}",
        f"- Excluded, synthetic-priced (disclosed, never blended into P&L): "
        f"{out['population']['n_excluded_synthetic_priced']}",
        f"- Excluded, no SPY day: {out['population']['n_excluded_no_spy_day']}",
        f"- Benched by confidence (design-level, not a data gap): {out['population']['benched_by_confidence']}",
        "",
        "Notes:",
    ] + [f"- {n}" for n in out["population"]["notes"]] + [
        "",
        "## Headline (real fills only -- synthetic-priced trades excluded)",
        "",
        f"| Total P&L | N trades | WR | Avg/trade |",
        f"|---|---|---|---|",
        f"| ${h['total_pnl']:+,.2f} | {h['n_trades']} | {h.get('win_rate')} | "
        f"${h.get('avg_pnl_per_trade', 0) or 0:+.2f} |",
        "",
        "---",
        f"_Source: `backtest/tools/fleet_arm_replay.py`. Raw JSON with full trade log: "
        f"see the sibling `.json` file next to this report._",
    ]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    log(f"wrote {path}")


# =====================================================================================
# CLI
# =====================================================================================
def _load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """DST FRAME CORRECTNESS (a real bug caught building this tool, not a style choice --
    read `backtest/lib/et_frame.py`'s module docstring in full before ever touching this
    function again): the SPY master CSVs AND the OPRA option cache both store timestamps
    with a FIXED -04:00 offset year-round (a known writer bug, `DST-FRAME-AUDIT-2026-07-02`)
    -- the UTC instant is correct, only the label is wrong for EST months. Because SPY and
    OPRA SHARE that same fixed-offset storage, a `wall-v1` parse (naive strip, no DST
    correction) of BOTH keeps them mutually aligned; converting SPY to genuine DST-aware
    `America/New_York` time WITHOUT also reinterpreting the OPRA cache the same way would
    silently shift every EST-month (Nov-Mar) trade by up to 1 hour relative to its own
    option bars -- exactly the "NEVER join a naive et-v2 series against a naive wall-v1
    series" trap et_frame.py's docstring names explicitly. `bold_fullhist_replay.py` /
    `engine_fullhist_replay.py`'s own plain `pd.to_datetime(spy_df["timestamp_et"])` calls
    (no utc=True) are IS `wall-v1` by construction -- reused here via the canonical helper
    instead of a bespoke parse, but the CONVENTION is identical, not a new choice.

    VIX is the ONE frame that must NOT use wall-v1: its writer uses REAL tz_convert + %z
    (et_frame.py: "The VIX master is NOT affected"), so its offsets genuinely vary by DST --
    a plain pd.to_datetime() on it produces a mixed-offset column pandas cannot even build a
    `.dt` accessor on (the crash that caught this whole issue while building this tool).
    VIX shares no timestamp storage with the option cache, so DST-correcting it in isolation
    introduces no cross-frame misalignment."""
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)
    spy_df["timestamp_et"] = parse_timestamp_et(spy_df["timestamp_et"], frame=FRAME_WALL_V1)
    vix_df["timestamp_et"] = parse_timestamp_et(vix_df["timestamp_et"], frame=FRAME_ET_V2)
    ribbon_lookup = efr.build_ribbon_lookup(spy_df)
    return spy_df, vix_df, ribbon_lookup


def _load_anchor_spy() -> pd.DataFrame:
    """SPY, wall-v1 (see _load_data's docstring) -- a DELIBERATE DEVIATION from
    `bold_fullhist_replay.run_anchor_validation`'s own anchor-SPY loader, which uses
    et-v2-style parsing (utc=True -> tz_convert -> tz_localize(None)). That choice is
    HARMLESS there only because every one of its 7 anchor dates falls in EDT months
    (2026-06-26..2026-07-28, where wall-v1 and et-v2 coincide exactly --
    `test_et_frame_guards.py::test_summer_day_identical_across_frames` pins this) -- it
    would silently misalign against the OPRA cache the moment an anchor fell in an EST
    month. This tool's own anchor windows (2026-06-29..2026-07-31, all three arms) are
    ALSO EDT-only today, so the two choices produce byte-identical output right now, but
    wall-v1 is used here so this function stays correct if a future arm's anchor set ever
    extends into winter -- reused via the canonical `et_frame` helper rather than
    hand-rolled, so this deviation is a one-argument diff, not a second implementation."""
    df = pd.read_csv(ANCHOR_SPY_FILE)
    return df.assign(timestamp_et=parse_timestamp_et(df["timestamp_et"], frame=FRAME_WALL_V1))


def run_one(arm_id: str, *, strike_tiers: Optional[str] = None, anchor_only: bool = False,
           skip_population: bool = False, out_stub: Optional[str] = None,
           **config_overrides) -> dict:
    accounts = _accounts()
    overrides = dict(config_overrides)
    if strike_tiers:
        overrides["strike_tiers"] = strike_tiers
    config = ArmReplayConfig.for_arm(arm_id, accounts, **overrides)

    anchor_spy = _load_anchor_spy()
    anchor_ribbon = efr.build_ribbon_lookup(anchor_spy)
    log(f"running anchor validation for {arm_id} ({len(mine_real_arm_fills(arm_id))} real fills mined)")
    anchor_out = run_anchor_validation(config, anchor_spy, anchor_ribbon)
    if anchor_only:
        print(json.dumps(anchor_out, indent=2, default=str))
        return anchor_out

    stub = out_stub or f"fleet-arm-replay-{arm_id}-{config.strike_tiers_label}-2026-08-02"
    if skip_population:
        write_scorecard({"rows": [], "n_raw_gated_entries": 0, "n_excluded_synthetic_priced": 0,
                         "n_excluded_no_spy_day": 0, "benched_by_confidence": False,
                         "population_notes": ["--skip-population"], "n_structure_veto_modeled": False,
                         "entry_layer_seconds": 0.0, "exit_layer_seconds": 0.0},
                        anchor_out, config, (FULL_START, FULL_END), stub)
        return anchor_out

    spy_df, vix_df, ribbon_lookup = _load_data()
    replay_out = replay_arm(config, spy_df, vix_df, ribbon_lookup, FULL_START, FULL_END, accounts)
    write_scorecard(replay_out, anchor_out, config, (FULL_START, FULL_END), stub)
    return replay_out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="risky-1", help="arm id (safe-3 / risky-1 / risky-3 / ...)")
    ap.add_argument("--strike-tiers", default=None,
                    help="named table (safe/bold/bold_core/probe) -- default: the arm's own accounts.json table")
    ap.add_argument("--equity", type=float, default=None)
    ap.add_argument("--anchor-only", action="store_true")
    ap.add_argument("--skip-population", action="store_true")
    ap.add_argument("--all-arms", action="store_true",
                    help="run safe-3, risky-1, risky-3 each at their OWN configured strike tier")
    args = ap.parse_args()

    if args.all_arms:
        for arm_id in ("safe-3", "risky-1", "risky-3"):
            run_one(arm_id, anchor_only=args.anchor_only, skip_population=args.skip_population)
        return 0

    overrides = {}
    if args.equity is not None:
        overrides["equity"] = args.equity
    run_one(args.arm, strike_tiers=args.strike_tiers, anchor_only=args.anchor_only,
           skip_population=args.skip_population, **overrides)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
