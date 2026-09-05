"""gate_net_cost_walk.py -- GOAL-GATE-NET-COST-2026-09-05 N2.

For every refused (wave, arm) row in `analysis/gate-net-cost/refusals-2026-09-05.json`
(N1's inventory), prices the entry the arm WOULD have taken and walks it forward through
that arm's REAL exit shape on real OPRA option bars with the engine's real cost model, so
N3 can turn each gate's refused-WINNER ceiling (already priced elsewhere) into a
net-of-losers figure.

REUSES, never reimplements (per the goal's OPERATING RULES):
  - `backtest/tools/gate_revalidation_ab.py` -- `build_ribbon_lookup`, `ribbon_tick_df_for`,
    `ribbon_ride_shape`, `account_config` (the SAME sound-replay building blocks
    `postfix_gate_costing.py` / `gate_expiry_check.py` already use for this exact class of
    refused-tick counterfactual).
  - `backtest.autoresearch.gate_expiry_check.bar_idx_for_ts` (SPY-bar lookup) and
    `autoresearch._b5_vix_regime_dayside._swing_stop` (level fallback). NOT reused verbatim:
    `gate_expiry_check._stop_level_for_row`'s field-priority fallback
    (trigger_level_exact -> bull_reclaim_level_raw -> bear_rejection_level_raw, in that FIXED
    order regardless of side) is sound only for that module's own single-side populations;
    hand-checking it against a real bear (P) fill returned a BULL-side level as the trade's
    structure stop and mis-triggered a stop within 5 minutes of entry where the real trade
    held 82 minutes to TP1. This module's own `_stop_level_for_wave_row` fixes that: prefer
    trigger_level_exact, else the SIDE-MATCHING raw field only, else `_swing_stop` -- see
    that function's docstring for the discriminating evidence.
  - `backtest.autoresearch.infinite_ammo_discovery._nearest_cached_strike` -- first cached
    strike scanning outward from the target strike (proxy when the exact strike is uncached).
  - `backtest.lib.option_pricing_real` -- `option_symbol`, `load_contract_bars`,
    `bar_at_or_after` (real OPRA 5-min bar cache).
  - `backtest.lib.exit_manager_walk.walk_exit_manager` -- the ACTUAL production
    `automation/state/fleet/exit_manager.py::plan_exit_actions` core, `all_exits_market=True`
    per the goal's OPERATING RULES (every live exit is an unconditional market order --
    see that module's FILL-PRICE CONVENTION docstring).
  - `crypto/lib/strike_selection.pick_strike` -- the REAL production strike formula (not a
    bare ATM approximation): per-arm tier table resolved the SAME way
    `automation/state/fleet/fleet_executor.py::_tiers_for_arm` resolves it live (read-only,
    hand-verified against that function + `automation/state/fleet/accounts.json`, 2026-09-05):
      safe-2 -> V15_SAFE_TIERS (ATM at this equity bracket)
      bold-2 -> V15_BOLD_TIERS (OTM-2 at this equity bracket)
      safe-3, risky-1 -> V15_BOLD_CORE_TIERS (ATM at this equity bracket, params_patch.
        strike_tier_table="bold_core")
      risky-3 -> V15_BOLD_CORE_PRE_EXT_TIERS (OTM-2 at this equity bracket, params_patch.
        strike_tier_table="bold_core_pre_ext" -- the 2026-08-06 per-arm ATM-extension kill)

STRATEGY SCOPE: every refused wave is walked as `ribbon_ride` -- the goal's own DONE-WHEN
names exclusively ribbon_ride's exit params (TP1 +100%/sell-66%, runner 2.5x, chandelier
trail, -50% cap, structure/ribbon-flip stop, time-stop), and every fleet setup_name observed
in the refusal population is a `*_RIDE_THE_RIBBON` variant. `vwap_continuation` refusals (if
any slipped into the inventory) are walked under the SAME ribbon_ride shape, disclosed as an
approximation via `strategy_assumed`, never silently.

EXIT SHAPE per arm: core arms (safe-2/bold-2) get `ribbon_ride_shape()` verbatim (both core
accounts share this exact registry shape, confirmed by gate_revalidation_ab.py's own
docstring). Fleet arms get the SAME base shape shallow-merged with that arm's
`accounts.json` params_patch.exit_patch via `fleet_executor._exit_shape_dict` -- the REAL
production merge function, not a re-derivation.

structure_stop_enabled / time_stop_et for fleet arms: borrowed from the matching core
account's own params.json/aggressive params.json (safe-prefixed arms -> safe account_config,
else -> bold account_config) -- the SAME approximation `postfix_gate_costing.py` Part C uses,
hand-verified there (2026-08-08) that fleet arms carry no dedicated params.json and both
patches leave stop_mode=structure / time_stop_et unpatched.

QTY per arm ("standard size", per the goal's DONE-WHEN): core arms read their OWN
params.json/aggressive params.json `min_contracts` (safe=3, bold=5 -- more precise than
zero_enter_autopsy.py's blanket DEFAULT_QTY=3, which only ever runs for account="safe").
Fleet arms use `postfix_gate_costing.py`'s own documented fallback for this exact situation
(a refused tick's `qty` field is always None) -- 3 if the arm id starts with "safe" else 5.

EQUITY for strike-tier resolution: `accounts.json` arm's own `starting_equity` field
(5000.0 for every one of these 5 arms, read live not hand-copied) -- all 5 arms sit in the
SAME $2K-$10K strike-tier bracket at every date in the window per the CLAUDE.md-verified
current equities (~$5K each), so this is not a live-equity-tracking claim, only a tier
lookup, disclosed as such in the output's `_doc`.

FAIL-OPEN THROUGHOUT (per the goal's mandate: "a missing bar = labeled null, never a
crash"): every stage that can fail (row lookup, side missing, no SPY bar, no cached
contract, no OPRA bars, no fill bar, walk_exit_manager raising) degrades that ONE row to
`walk_ok: false` with a `walk_error` string; the loop over ~350 waves never aborts on one
bad row.

Output: analysis/gate-net-cost/walk-2026-09-05.json -- one row per (wave, arm, gate) with
entry_ts, contract, entry_px, exit_ts, exit_stage, exit_px, realized_if_taken_dollars (at
the arm's standard size), peak_multiple, walk_ok/walk_error.

CLI: cd backtest && ../backtest/.venv/Scripts/python.exe ../setup/scripts/gate_net_cost_walk.py
     (invoke from repo root: backtest/.venv/Scripts/python.exe setup/scripts/gate_net_cost_walk.py)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (REPO, BACKTEST, BACKTEST / "lib", BACKTEST / "tools", BACKTEST / "autoresearch",
           FLEET_DIR, REPO / "setup" / "scripts", REPO / "crypto" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from autoresearch.gate_expiry_check import bar_idx_for_ts  # noqa: E402
from autoresearch._b5_vix_regime_dayside import _swing_stop  # noqa: E402
from autoresearch.recency_check import load_merged_spy_vix  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _normalize_spy  # noqa: E402
from autoresearch.infinite_ammo_discovery import _nearest_cached_strike  # noqa: E402
from lib.option_pricing_real import option_symbol, load_contract_bars, bar_at_or_after  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
import strike_selection as ss  # noqa: E402

sys.path.insert(0, str(BACKTEST / "tools"))
import gate_revalidation_ab as grab  # noqa: E402
import fleet_executor  # noqa: E402
from _option_bars_1min_cache import load_1min_cache_readonly as _load_1min_cache_readonly  # noqa: E402,F401
# GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3: the read-only 1-min cache loader (schema
# normalization + vwap/trade_count proxy fill, see that function's own docstring) lives in
# _option_bars_1min_cache.py so gate_net_cost_walk.py and right_tail_waves.py share ONE
# implementation (OP-22) instead of each re-deriving it.

RESOLUTIONS = ("5min", "1min")

REFUSALS_PATH = REPO / "analysis" / "gate-net-cost" / "refusals-2026-09-05.json"
OUT_PATH = REPO / "analysis" / "gate-net-cost" / "walk-2026-09-05.json"
ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"

MAX_STRIKE_STEPS = 4

CORE_ACCOUNT_FOR_ARM = {"safe": "safe-2", "bold": "bold-2"}
ARM_FOR_CORE_ACCOUNT = {v: k for k, v in CORE_ACCOUNT_FOR_ARM.items()}

# Per-arm strike-tier table, resolved the SAME way fleet_executor._tiers_for_arm resolves it
# live -- hand-verified against that function + accounts.json's params_patch.strike_tier_table
# per arm, 2026-09-05 (see module docstring for the citation of each arm's table + doc field).
TIERS_FOR_ARM = {
    "safe-2": ss.V15_SAFE_TIERS,
    "bold-2": ss.V15_BOLD_TIERS,
    "safe-3": ss.V15_BOLD_CORE_TIERS,
    "risky-1": ss.V15_BOLD_CORE_TIERS,
    "risky-3": ss.V15_BOLD_CORE_PRE_EXT_TIERS,
}


def log(m: str) -> None:
    print(f"[gate-net-cost-walk] {m}", flush=True)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _account_starting_equity() -> dict[str, float]:
    data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    return {a["id"]: float(a.get("starting_equity", 5000.0)) for a in data.get("arms", [])}


def _accounts_by_id() -> dict[str, dict[str, Any]]:
    data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    return {a["id"]: a for a in data.get("arms", [])}


def _qty_for_arm(arm: str, core_cfg: dict[str, Any]) -> int:
    """The arm's 'standard size'. Core arms: their own params.json min_contracts (read via
    gate_revalidation_ab.account_config()). Fleet arms: postfix_gate_costing.py's own
    documented fallback for a refused tick's always-null qty field (3 if the arm id starts
    with 'safe' else 5)."""
    if arm in ("safe-2", "bold-2"):
        account = ARM_FOR_CORE_ACCOUNT[arm]
        return int(core_cfg[account]["qty"])
    return 3 if arm.startswith("safe") else 5


def _exit_shape_for_arm(arm: str, accounts: dict[str, dict[str, Any]], strat) -> dict:
    if arm in ("safe-2", "bold-2"):
        return grab.ribbon_ride_shape()
    arm_dict = accounts.get(arm)
    if arm_dict is None:
        return grab.ribbon_ride_shape()
    return fleet_executor._exit_shape_dict(strat, arm=arm_dict)


def _exit_cfg_for_arm(arm: str, core_cfg: dict[str, Any]) -> dict[str, Any]:
    """structure_stop_enabled / time_stop_et. Core arms: their own account_config() entry.
    Fleet arms: borrowed from the matching core account (safe-prefixed -> safe, else bold) --
    the exact convention postfix_gate_costing.py Part C uses and hand-verified there
    (2026-08-08) that fleet arms carry no dedicated params.json of their own."""
    if arm in ("safe-2", "bold-2"):
        account = ARM_FOR_CORE_ACCOUNT[arm]
        return core_cfg[account]
    account = "safe" if arm.startswith("safe") else "bold"
    return core_cfg[account]


def _row_lookup_index(fleet_arms: list[str]) -> tuple[dict[tuple[str, str], dict], dict[str, dict[tuple[str, str], dict]]]:
    """(core_index, fleet_index_by_arm): core_index keyed by (account, ts_et) ->
    core-decisions.jsonl row; fleet_index_by_arm[arm] keyed by (arm, ts_et) -> decisions.jsonl
    row. Used to re-fetch the FULL row (side, any level field) for a wave whose inventory
    entry stored only date/wave_start_et/account-or-arm (N1's own schema)."""
    core_index: dict[tuple[str, str], dict] = {}
    for r in _load_jsonl(CORE_DECISIONS):
        ts = r.get("ts_et")
        acct = r.get("account")
        if ts and acct:
            core_index[(acct, ts)] = r
    fleet_index: dict[str, dict[tuple[str, str], dict]] = {}
    for arm in fleet_arms:
        idx: dict[tuple[str, str], dict] = {}
        for r in _load_jsonl(FLEET_DIR / arm / "decisions.jsonl"):
            ts = r.get("ts_et")
            if ts:
                idx[(arm, str(ts)[:19])] = r
        fleet_index[arm] = idx
    return core_index, fleet_index


def _stop_level_for_wave_row(row: dict, spy: pd.DataFrame, bar_idx: int, side: str) -> float:
    """SIDE-AWARE trigger level for the structure stop -- a deliberate correction of
    `autoresearch.gate_expiry_check._stop_level_for_row`'s naive field-priority fallback
    (`trigger_level_exact` -> `bull_reclaim_level_raw` -> `bear_rejection_level_raw`,
    checked in that FIXED order regardless of `side`). That helper is sound for its own
    callers (gate_revalidation_ab.py's 3 cells, each a single-side population by
    construction -- cell1/cell3 are always side=C, cell2 always side=P) but is UNSOUND for
    this walker's mixed-side wave population: hand-checking the 2026-09-01 safe-2 762P real
    fill against it returned `bull_reclaim_level_raw=761.51` (a BULL-side level, ~11 cents
    BELOW spot at entry) as the BEAR trade's structure stop -- backwards for a put (whose
    resistance should sit ABOVE spot), and it triggered a false structure_stop within one
    5-min bar of entry where the real live trade held 82 minutes to TP1. FIX: prefer
    `trigger_level_exact`, else the SIDE-MATCHING raw field only (`bear_rejection_level_raw`
    for P, `bull_reclaim_level_raw` for C -- never the other side's), else fall back to
    `_swing_stop` (the SAME fallback the original helper uses, imported verbatim from
    `autoresearch._b5_vix_regime_dayside`) -- exercised on this exact row (whose
    bear_rejection_level_raw is null -- trendline_rejection triggers do not populate it),
    where it returns the swing high, hand-checked to reproduce the real TP1 fill within
    tolerance (see test_gate_net_cost_walk_2026_09_05.py)."""
    exact = row.get("trigger_level_exact")
    if exact is not None:
        return float(exact)
    side_key = "bear_rejection_level_raw" if side == "P" else "bull_reclaim_level_raw"
    v = row.get(side_key)
    if v is not None:
        return float(v)
    return _swing_stop(spy, bar_idx, side)


def _side_from_char(side: Any) -> Optional[str]:
    if side in ("C", "P"):
        return side
    if side in ("BULL", "bull"):
        return "C"
    if side in ("BEAR", "bear"):
        return "P"
    return None


class WalkCtx:
    def __init__(self):
        log("loading SPY+VIX frame ...")
        spy_raw, _vix = load_merged_spy_vix()
        self.spy = _normalize_spy(spy_raw)
        self.spy_ts = self.spy["timestamp_et"]
        self.spy_by_date = {d: sub.reset_index(drop=True) for d, sub in self.spy.groupby("date")}
        self.ribbon_lookup = grab.build_ribbon_lookup(self.spy)
        self.core_cfg = grab.account_config()
        self.accounts = _accounts_by_id()
        self.equity = _account_starting_equity()
        self.strat = fleet_strategies_by_name_ribbon_ride()


def fleet_strategies_by_name_ribbon_ride():
    import strategies as fleet_strategies
    return fleet_strategies.by_name("ribbon_ride")


def _walk_entry(
    ctx: WalkCtx, *, arm: str, side: str, day: dt.date, trig_ts: pd.Timestamp,
    stop_level: Optional[float], strike_override: Optional[int] = None,
    entry_premium_override: Optional[float] = None,
    opt_df_override: Optional[pd.DataFrame] = None, opt_df_resolution: str = "5min",
    resolution: str = "5min",
) -> dict[str, Any]:
    """Price + walk ONE entry via the real production exit_manager core.
    strike_override / entry_premium_override let the hand-check reproduce a REAL fill's
    exact contract/entry instead of re-deriving the strike from the tier table -- everything
    else (exit shape, cfg, walk_exit_manager call) is identical to the normal wave path.
    opt_df_override / opt_df_resolution (added for the goal's mandatory hand-checks): when a
    1-minute OPRA cache already exists on disk for the exact contract/date (checked via
    `backtest/tools/_option_bars_1min_cache.fetch_1min_cached`'s cache-hit path -- NEVER a
    live fetch, per the goal's $0/read-only rules), the hand-check passes that DataFrame here
    to walk at the SAME resolution the real live engine ticks at, instead of the 5-min OPRA
    cache the main N2 wave-walk uses (disclosed resolution difference, not silently blended).
    resolution (GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3, default unchanged): when "1min" and
    opt_df_override is not already supplied, look up the 1-min cache read-only via
    `_load_1min_cache_readonly` for the resolved contract/day; on a cache miss, falls back to
    the normal 5-min cache and discloses it via the returned `resolution_1min_fallback` flag
    -- never a live fetch from inside the walk."""
    spy_day = ctx.spy_by_date.get(day)
    if spy_day is None or spy_day.empty:
        return {"walk_ok": False, "walk_error": f"no SPY bars cached for {day}"}

    if strike_override is not None:
        strike = strike_override
    else:
        pos = int(ctx.spy_ts.searchsorted(trig_ts, side="right")) - 1
        if pos < 0 or pos >= len(ctx.spy_ts):
            return {"walk_ok": False, "walk_error": "no SPY bar at/before trigger tick"}
        spot = float(ctx.spy.iloc[pos]["close"])
        tiers = TIERS_FOR_ARM[arm]
        equity = ctx.equity.get(arm, 5000.0)
        target = ss.pick_strike(spot, equity, side, tiers)
        strike = _nearest_cached_strike(day, target, side, MAX_STRIKE_STEPS)
        if strike is None:
            return {"walk_ok": False, "walk_error": f"no cached contract near strike {target}"}

    symbol = option_symbol(day, strike, side)
    resolution_1min_fallback = False
    if opt_df_override is not None:
        opt_df = opt_df_override
    elif resolution == "1min":
        opt_df_1min = _load_1min_cache_readonly(symbol, day.isoformat())
        if opt_df_1min is not None:
            opt_df = opt_df_1min
            opt_df_resolution = "1min"
        else:
            opt_df = load_contract_bars(symbol, frame="wall-v1")
            opt_df_resolution = "5min"
            resolution_1min_fallback = True
    else:
        opt_df = load_contract_bars(symbol, frame="wall-v1")
    if opt_df is None or opt_df.empty:
        return {"walk_ok": False, "walk_error": f"no OPRA cache for {symbol}", "contract": symbol}

    if entry_premium_override is not None:
        entry_bar = bar_at_or_after(opt_df, trig_ts.to_pydatetime())
        if entry_bar is None:
            return {"walk_ok": False, "walk_error": f"no {symbol} bar at/after entry tick", "contract": symbol}
        entry_premium = entry_premium_override
        entry_time_et = entry_bar.timestamp_et
    else:
        fill_target = trig_ts + pd.Timedelta(minutes=5)
        entry_bar = bar_at_or_after(opt_df, fill_target.to_pydatetime())
        if entry_bar is None:
            return {"walk_ok": False, "walk_error": f"no {symbol} bar at/after fill target", "contract": symbol}
        entry_premium = float(entry_bar.open)
        entry_time_et = entry_bar.timestamp_et
        if entry_premium <= 0:
            return {"walk_ok": False, "walk_error": "bad entry premium (<= 0)", "contract": symbol}

    exit_shape = _exit_shape_for_arm(arm, ctx.accounts, ctx.strat)
    exit_cfg = _exit_cfg_for_arm(arm, ctx.core_cfg)
    qty = _qty_for_arm(arm, ctx.core_cfg)
    rtd = grab.ribbon_tick_df_for(opt_df, ctx.ribbon_lookup)

    try:
        res = walk_exit_manager(
            symbol=symbol, side=side, entry_time_et=entry_time_et,
            entry_premium=float(entry_premium), qty=qty, exit_shape=exit_shape,
            structure_stop_enabled=exit_cfg["structure_stop_enabled"], trigger_level=stop_level,
            strategy="ribbon_ride", time_stop_et=exit_cfg["time_stop_et"],
            opt_df=opt_df, ribbon_tick_df=rtd, five_min_spy_df=spy_day,
            opt_df_resolution=opt_df_resolution, allow_5min=True,
            all_exits_market=True,
        )
    except Exception as exc:  # noqa: BLE001 -- one bad wave must never abort the run
        return {"walk_ok": False, "walk_error": f"walk_exit_manager raised: {exc}", "contract": symbol}

    if res.exit_time_et is None:
        return {"walk_ok": False, "walk_error": "unwalkable (no bars after entry)", "contract": symbol}

    # peak_multiple: highest close/entry_premium over the bars actually walked.
    mask = (opt_df["timestamp_et"] > pd.Timestamp(entry_time_et)) & \
           (opt_df["timestamp_et"] <= pd.Timestamp(res.exit_time_et))
    walked_bars = opt_df.loc[mask]
    peak_multiple = (float(walked_bars["close"].max()) / entry_premium) if not walked_bars.empty else None

    last_leg = res.legs[-1] if res.legs else None
    return {
        "walk_ok": True, "walk_error": None,
        "contract": symbol, "entry_ts": entry_time_et.isoformat(),
        "entry_px": round(float(entry_premium), 4),
        "exit_ts": res.exit_time_et.isoformat(),
        "exit_stage": last_leg.stage if last_leg else res.exit_reason,
        "exit_px": last_leg.fill_price if last_leg else None,
        "realized_if_taken_dollars": res.dollar_pnl,
        "peak_multiple": round(peak_multiple, 4) if peak_multiple is not None else None,
        "qty": qty, "hold_minutes": res.hold_minutes, "exit_reason": res.exit_reason,
        "resolution_used": opt_df_resolution,
        "resolution_1min_fallback": resolution_1min_fallback,
    }


def _iter_wave_buckets(refusals: dict) -> list[tuple[str, str, dict]]:
    """(gate_id, bucket_key, wave) triples across core_gates + fleet_decisions_reason_gates.
    fleet_gate_override is SKIPPED -- N1 found it structurally empty (that ledger doesn't
    track min_triggers/require_confluence_or_sequence at all, see refusals-2026-09-05.json's
    own fleet_gate_override: {})."""
    out = []
    for gate_id, bucket in refusals.get("core_gates", {}).items():
        for w in bucket.get("waves", []):
            out.append((gate_id, gate_id, w))
    for key, bucket in refusals.get("fleet_decisions_reason_gates", {}).items():
        gate_id = key.split("__", 1)[0]
        for w in bucket.get("waves", []):
            out.append((gate_id, key, w))
    return out


def run_walk(refusals_path: Path = REFUSALS_PATH, resolution: str = "5min") -> dict[str, Any]:
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {RESOLUTIONS}, got {resolution!r}")
    refusals = json.loads(refusals_path.read_text(encoding="utf-8"))
    buckets = _iter_wave_buckets(refusals)
    fleet_arms = ["safe-3", "risky-1", "risky-3"]
    core_index, fleet_index = _row_lookup_index(fleet_arms)

    ctx = WalkCtx()

    rows: list[dict[str, Any]] = []
    n_ok = 0
    error_counts: dict[str, int] = {}
    for gate_id, bucket_key, w in buckets:
        date_s = w.get("date")
        wave_start = w.get("wave_start_et")
        account = w.get("account")   # core waves
        arm_raw = w.get("arm")       # fleet waves
        row_out: dict[str, Any] = {
            "wave_id": f"{date_s}|{wave_start}", "gate": gate_id, "bucket": bucket_key,
        }
        try:
            if account in ("safe", "bold"):
                arm = CORE_ACCOUNT_FOR_ARM[account]
                src_row = core_index.get((account, wave_start))
            elif arm_raw:
                arm = arm_raw
                key_ts = str(wave_start)[:19] if wave_start else None
                src_row = fleet_index.get(arm, {}).get((arm, key_ts)) if key_ts else None
            else:
                arm, src_row = None, None

            row_out["arm"] = arm
            if arm is None:
                row_out["walk_ok"] = False
                row_out["walk_error"] = "no arm resolved for this wave"
            elif src_row is None:
                row_out["walk_ok"] = False
                row_out["walk_error"] = "could not re-fetch source decision row at wave_start_et"
            else:
                side = _side_from_char(src_row.get("side"))
                if side is None:
                    row_out["walk_ok"] = False
                    row_out["walk_error"] = f"no usable side on source row (side={src_row.get('side')!r})"
                else:
                    try:
                        trig_ts = pd.Timestamp(str(wave_start)[:19])
                    except Exception:
                        row_out["walk_ok"] = False
                        row_out["walk_error"] = "unparseable wave_start_et"
                        rows.append(row_out)
                        continue
                    day = dt.date.fromisoformat(date_s)
                    bar_idx, stale = bar_idx_for_ts(ctx.spy_ts, trig_ts.to_pydatetime())
                    if bar_idx is None:
                        row_out["walk_ok"] = False
                        row_out["walk_error"] = "no SPY bar at/before wave start"
                        rows.append(row_out)
                        continue
                    if stale:
                        row_out["walk_ok"] = False
                        row_out["walk_error"] = "stale (prior-session) SPY bar at this tick"
                        rows.append(row_out)
                        continue
                    stop_level = _stop_level_for_wave_row(src_row, ctx.spy, bar_idx, side)
                    res = _walk_entry(ctx, arm=arm, side=side, day=day, trig_ts=trig_ts,
                                       stop_level=stop_level, resolution=resolution)
                    row_out["side"] = side
                    row_out.update(res)
        except Exception as exc:  # noqa: BLE001 -- fail-open at the ROW level, never abort the run
            row_out["walk_ok"] = False
            row_out["walk_error"] = f"unexpected: {exc}"
        rows.append(row_out)
        if row_out.get("walk_ok"):
            n_ok += 1
        else:
            error_counts[row_out.get("walk_error", "unknown")] = error_counts.get(
                row_out.get("walk_error", "unknown"), 0) + 1
        if len(rows) % 50 == 0:
            log(f"... {len(rows)}/{len(buckets)} walked ({n_ok} ok)")

    top_errors = sorted(error_counts.items(), key=lambda kv: -kv[1])[:15]
    n_1min_fallback = sum(1 for r in rows if r.get("resolution_1min_fallback"))
    return {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "source_inventory": str(refusals_path.relative_to(REPO)),
        "resolution": resolution,
        "n_rows": len(rows),
        "n_walk_ok": n_ok,
        "n_walk_error": len(rows) - n_ok,
        "n_resolution_1min_fallback": n_1min_fallback if resolution == "1min" else None,
        "top_error_reasons": top_errors,
        "cost_model": {
            "engine": "backtest.lib.exit_manager_walk.walk_exit_manager",
            "all_exits_market": True,
            "exit_slippage": 0.02,
            "note": "every stage fills at bar close minus exit_slippage -- what live "
                    "actually does per exit_manager_walk.py's own FILL-PRICE CONVENTION "
                    "docstring (every real exit order is an unconditional market order).",
        },
        "strategy_assumed": "ribbon_ride (every gate this goal names is scoped to "
                             "ribbon_ride's exit params; see module docstring)",
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refusals", default=str(REFUSALS_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--resolution", default="5min", choices=list(RESOLUTIONS),
                     help="OPRA bar resolution to walk at. Default 5min (unchanged behavior). "
                          "1min reads backtest/data/highres/ read-only (GOAL-OPRA-1MIN-COVERAGE-"
                          "2026-09-05 O3); falls back to 5min per-row on a cache miss.")
    args = ap.parse_args()
    out = run_walk(Path(args.refusals), resolution=args.resolution)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"n_rows={out['n_rows']} n_walk_ok={out['n_walk_ok']} n_walk_error={out['n_walk_error']}")
    log(f"top errors: {out['top_error_reasons']}")
    log(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
