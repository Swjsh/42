"""sampling_gap_ledger.py -- quantifies the SAMPLING-GAP component of stop-type exit
giveback across the full engine fill history (runner-leg investigation, sub-problem A,
overnight 2026-08-02).

WHY THIS EXISTS. The 2026-07-31 winner autopsy decomposed one runner leg's $0.230/contract
giveback into four components: HWM-sampling (0.020), the mechanical trail band (0.138, the
exit shape WORKING AS DESIGNED), a sampling gap at the firing tick (0.052 -- the floor sat at
$0.552, the engine's next look already saw $0.50), and fill slippage (0.020). This script
generalizes component 3 (and, separately, component 4) across every stop-type exit in the
book's real-fills history, so "the engine set a stop and didn't look again for N minutes" can
be answered in aggregate dollars instead of n=1.

SCOPE -- deliberately narrow. Only the `worst_premium <= runner_stop` exit family is in scope:
stage in {premium_stop, profit_lock_floor, trail, be_stop} (see exit_manager.py's pre-TP1
branch (a2) and post-TP1 branch -- both compare worst_premium against a threshold named
`runner_stop` in the logged exit_pass row, confirmed by reading the source this session).
EXCLUDED: tp1 / runner_target (upside best_premium>=level -- late observation does not have
the same one-directional cost; a late look can just as easily catch a HIGHER best), time_stop
(not a threshold breach), ribbon_flip (binary state flip, no premium threshold), structure_stop
(the threshold is a SPY price level compared against a closed 5m bar, not a premium value --
the logged `runner_stop` field on those rows is the STANDING catastrophe cap, not the level
that actually fired, so computing a "gap" from it would measure the wrong mechanism entirely;
flagged and counted separately, never computed). This script changes NO exit rule and places
NO order -- it is pure measurement over already-logged ticks and already-settled broker fills.

DEFINITIONS (per exit event):
  threshold       = the logged `runner_stop` value on the tick that fired the SELL (the exact
                     price the engine's own rule compared worst_premium against).
  observed        = the logged `worst_premium` (bid) on that same tick.
  sampling_gap    = max(0, threshold - observed)   -- how far the bid had ALREADY fallen below
                     the floor by the time the engine looked. This is the cadence cost: zero
                     for a same-tick precise breach, positive whenever price gapped through the
                     floor between two observations.
  slippage        = fill_price - observed          -- SIGNED. The gap between the quote the
                     decision was made on and the actual market-order fill a few seconds later.
                     Can be negative (fill better than the observed bid) -- reported both signed
                     (mean) and loss-only (clipped at 0, for a conservative "cost" figure).

CADENCE GROUPS -- empirically measured from ts_et deltas between consecutive logged ticks per
arm/account, NOT assumed from doctrine text:
  fleet arms (safe-1, safe-3, risky-1, risky-3) -- ticked by Gamma_FleetExecutor, 3-minute
    cadence for their ENTIRE history in this dataset (2026-06-21 through 2026-07-31/08-01).
    Gamma_FleetExecutor's cadence was tightened 3min->1min by commit 87620376 (Sat 2026-08-01
    14:58 MT), verified LIVE via `Get-ScheduledTask -TaskName Gamma_FleetExecutor` this session
    (Interval=PT1M, StartBoundary 2026-08-01) -- but the market has not been open since that
    change shipped (Sat/Sun), so there is zero live 1-minute fleet data yet.
  core accounts (safe, bold) via heartbeat_core -- 1-minute cadence for this ENTIRE dataset
    (heartbeat_core has never run on any other cadence). Used here as the empirical proxy for
    "what does this exact mechanism cost at 1-minute cadence", since it is the same
    exit_manager.plan_exit_actions core, the same exit_actuator.manage_tick wiring, and the
    same real-OPRA-bid sampling problem -- just ticked 3x more often, for real, for 40 days.

OUTPUT: analysis/pain-ledger/sampling-gap.json + a console summary. Read-only over decisions
logs and fills-ledger; writes nothing except its own output file. No params/strategy/exit-rule
file is touched by this script.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
CORE_LEDGER = ROOT / "automation" / "state" / "core-decisions.jsonl"
FILLS_LEDGER = ROOT / "automation" / "state" / "fills-ledger.jsonl"
OUT_PATH = ROOT / "analysis" / "pain-ledger" / "sampling-gap.json"

STOP_TYPE_STAGES = {"premium_stop", "profit_lock_floor", "trail", "be_stop"}
EXCLUDED_STAGES_NOTED = {"structure_stop", "tp1", "runner_target", "time_stop", "ribbon_flip"}

FLEET_ARMS = ["safe-1", "safe-3", "risky-1", "risky-3"]
CORE_ACCOUNTS = ["safe", "bold"]


def _load_fills() -> dict:
    """order_id -> fill row (real broker fills only)."""
    out = {}
    if not FILLS_LEDGER.exists():
        return out
    with FILLS_LEDGER.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            oid = d.get("order_id")
            if oid:
                out[oid] = d
    return out


def _parse_ts(ts: str):
    try:
        # ts_et strings carry an offset in decisions.jsonl (…-04:00); core-decisions.jsonl
        # sometimes omits it -- both handled by fromisoformat on py>=3.11 fallback below.
        return datetime.fromisoformat(ts)
    except ValueError:
        try:
            return datetime.fromisoformat(ts + "-04:00")
        except ValueError:
            return None


def _empirical_cadence_seconds(ticks_sorted: list) -> dict:
    """Median/mean gap between consecutive logged ticks (any row, not just exit_pass) --
    the ground-truth observation cadence, measured, not assumed."""
    deltas = []
    for a, b in zip(ticks_sorted, ticks_sorted[1:]):
        ta, tb = _parse_ts(a), _parse_ts(b)
        if ta is None or tb is None:
            continue
        gap = (tb - ta).total_seconds()
        if 0 < gap < 3600:  # drop overnight/cross-session gaps
            deltas.append(gap)
    if not deltas:
        return {"n": 0, "median_s": None, "mean_s": None}
    return {
        "n": len(deltas),
        "median_s": round(statistics.median(deltas), 1),
        "mean_s": round(statistics.mean(deltas), 1),
    }


def score_event(threshold: float, observed: float, fill_price: float, qty: float) -> dict:
    """PURE scoring core (mirrors this codebase's decision-core/actuator split -- see
    exit_manager.py vs exit_actuator.py). Given the threshold that fired, the worst_premium
    the engine observed on that tick, and the real fill price, returns the dollar
    decomposition. No I/O, no rounding surprises hidden inside main().

    sampling_gap is clamped to >= 0 by construction (max(0, ...)): a threshold that was NOT
    yet breached at observation time (observed > threshold -- e.g. a same-tick precise stop)
    contributes zero, never a negative 'gain'. slippage is left SIGNED (fill can be better OR
    worse than the observed quote); slippage_loss is the >=0 clamp of the unfavorable side
    only, so a favorable fill can never net against and hide an unfavorable one elsewhere.
    """
    sampling_gap_per_ct = max(0.0, threshold - observed)
    slippage_signed_per_ct = fill_price - observed
    slippage_loss_per_ct = max(0.0, -slippage_signed_per_ct)
    qty = qty or 0
    return {
        "sampling_gap_per_ct": round(sampling_gap_per_ct, 4),
        "sampling_gap_dollars": round(sampling_gap_per_ct * qty * 100, 2),
        "slippage_signed_per_ct": round(slippage_signed_per_ct, 4),
        "slippage_signed_dollars": round(slippage_signed_per_ct * qty * 100, 2),
        "slippage_loss_dollars": round(slippage_loss_per_ct * qty * 100, 2),
    }


def _collect_exit_events(rows: list, source: str, id_field: str, id_value: str) -> list:
    """Walk one arm/account's tick stream, emit one record per SELL_ALL/SELL_PARTIAL action
    whose stage is in the worst<=threshold family. Also returns the raw ts list for cadence."""
    events = []
    for row in rows:
        for ep in (row.get("exit_pass") or []):
            for act in (ep.get("actions") or []):
                stage = act.get("stage")
                kind = act.get("kind")
                if kind not in ("SELL_ALL", "SELL_PARTIAL"):
                    continue
                if stage not in STOP_TYPE_STAGES and stage not in EXCLUDED_STAGES_NOTED:
                    continue  # unknown stage -- neither measured nor silently counted as excluded-noted
                broker = act.get("broker") or {}
                order_id = broker.get("id")
                placed = bool(act.get("placed"))
                events.append({
                    "source": source,
                    id_field: id_value,
                    "ts_et": row.get("ts_et"),
                    "symbol": ep.get("symbol"),
                    "stage": stage,
                    "in_scope": stage in STOP_TYPE_STAGES,
                    "qty": act.get("qty"),
                    "threshold": ep.get("runner_stop"),
                    "observed_worst": ep.get("worst_premium"),
                    "observed_best": ep.get("best_premium"),
                    "placed": placed,
                    "order_id": order_id,
                })
    return events


def main() -> dict:
    fills = _load_fills()

    all_events = []
    cadence_by_group = {}

    for arm in FLEET_ARMS:
        p = FLEET_DIR / arm / "decisions.jsonl"
        if not p.exists():
            continue
        rows = []
        ts_list = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(d)
                if d.get("ts_et"):
                    ts_list.append(d["ts_et"])
        ts_list.sort()
        cadence_by_group[f"arm:{arm}"] = _empirical_cadence_seconds(ts_list)
        all_events.extend(_collect_exit_events(rows, "fleet", "arm", arm))

    core_rows_by_account = {a: [] for a in CORE_ACCOUNTS}
    if CORE_LEDGER.exists():
        with CORE_LEDGER.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                acct = d.get("account")
                if acct in core_rows_by_account:
                    core_rows_by_account[acct].append(d)
    for acct, rows in core_rows_by_account.items():
        ts_list = sorted(r["ts_et"] for r in rows if r.get("ts_et"))
        cadence_by_group[f"core:{acct}"] = _empirical_cadence_seconds(ts_list)
        all_events.extend(_collect_exit_events(rows, "core", "account", acct))

    # Join fills, compute dollar components.
    n_no_fill = 0
    n_not_placed = 0
    n_excluded_structure_family = 0
    scored = []
    for ev in all_events:
        if not ev["in_scope"]:
            n_excluded_structure_family += 1
            continue
        if not ev["placed"]:
            n_not_placed += 1
            continue
        oid = ev["order_id"]
        fill = fills.get(oid) if oid else None
        if fill is None or fill.get("price") is None:
            n_no_fill += 1
            continue
        threshold = ev["threshold"]
        observed = ev["observed_worst"]
        qty = ev["qty"] or 0
        fill_price = fill["price"]
        if threshold is None or observed is None:
            n_no_fill += 1
            continue
        rec = {
            "source": ev["source"],
            "arm_or_account": ev.get("arm") or ev.get("account"),
            "ts_et": ev["ts_et"],
            "symbol": ev["symbol"],
            "stage": ev["stage"],
            "qty": qty,
            "threshold": threshold,
            "observed_worst": observed,
            "fill_price": fill_price,
            **score_event(threshold, observed, fill_price, qty),
        }
        scored.append(rec)

    def _agg(recs: list) -> dict:
        if not recs:
            return {"n": 0}
        gaps = [r["sampling_gap_dollars"] for r in recs]
        n_breached = sum(1 for r in recs if r["sampling_gap_per_ct"] > 0)
        return {
            "n": len(recs),
            "n_with_sampling_gap": n_breached,
            "breach_rate": round(n_breached / len(recs), 4),
            "sampling_gap_dollars_total": round(sum(gaps), 2),
            "sampling_gap_dollars_median_per_exit": round(statistics.median(gaps), 4),
            "sampling_gap_dollars_mean_per_exit": round(statistics.mean(gaps), 4),
            "slippage_signed_dollars_total": round(sum(r["slippage_signed_dollars"] for r in recs), 2),
            "slippage_loss_dollars_total": round(sum(r["slippage_loss_dollars"] for r in recs), 2),
        }

    fleet_recs = [r for r in scored if r["source"] == "fleet"]
    core_recs = [r for r in scored if r["source"] == "core"]

    by_stage = {}
    for stage in sorted(STOP_TYPE_STAGES):
        by_stage[stage] = _agg([r for r in scored if r["stage"] == stage])

    by_arm = {}
    for arm in FLEET_ARMS + CORE_ACCOUNTS:
        by_arm[arm] = _agg([r for r in scored if r["arm_or_account"] == arm])

    result = {
        "_meta": {
            "generated_at_et": datetime.now().isoformat(),
            "builder": "setup/scripts/sampling_gap_ledger.py",
            "descriptive_only": True,
            "scope_note": "Only stage in {premium_stop, profit_lock_floor, trail, be_stop} "
                           "(the worst_premium<=runner_stop family) is scored. structure_stop / "
                           "tp1 / runner_target / time_stop / ribbon_flip are counted, never "
                           "scored, for the reasons in the module docstring.",
            "fleet_cadence_fix": {
                "commit": "87620376",
                "committed_local": "2026-08-01T14:58:52-06:00",
                "verified_live_this_session": True,
                "verification": "Get-ScheduledTask -TaskName Gamma_FleetExecutor -> "
                                 "Triggers[0].Repetition.Interval == 'PT1M', StartBoundary "
                                 "2026-08-01T07:31:00-06:00",
                "note": "No trading day has occurred under the new cadence yet (shipped "
                        "Saturday; market closed Sat/Sun). All fleet rows in this ledger are "
                        "pre-fix (3-minute).",
            },
        },
        "counts": {
            "total_stop_type_actions_seen": len(all_events) - n_excluded_structure_family,
            "excluded_not_stop_type_family": n_excluded_structure_family,
            "excluded_not_placed_or_watch_mode": n_not_placed,
            "excluded_no_matching_fill": n_no_fill,
            "scored": len(scored),
        },
        "empirical_cadence_seconds_by_group": cadence_by_group,
        "headline": {
            "fleet_3min_legacy": _agg(fleet_recs),
            "core_1min_always": _agg(core_recs),
        },
        "by_stage": by_stage,
        "by_arm_or_account": by_arm,
        "all_scored_events": scored,
    }
    return result


if __name__ == "__main__":
    result = main()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("=== SAMPLING GAP LEDGER ===")
    print(f"scored {result['counts']['scored']} stop-type exits "
          f"(excluded: {result['counts']['excluded_not_stop_type_family']} non-stop-type, "
          f"{result['counts']['excluded_not_placed_or_watch_mode']} not-placed/WATCH, "
          f"{result['counts']['excluded_no_matching_fill']} no-fill-match)")
    print()
    print("empirical cadence (median seconds between logged ticks):")
    for k, v in result["empirical_cadence_seconds_by_group"].items():
        print(f"  {k}: median={v.get('median_s')}s  n={v.get('n')}")
    print()
    print("FLEET (3-min, legacy, entire history to date):", json.dumps(result["headline"]["fleet_3min_legacy"], indent=2))
    print()
    print("CORE (1-min, entire history):", json.dumps(result["headline"]["core_1min_always"], indent=2))
    print()
    print("by stage:")
    for k, v in result["by_stage"].items():
        print(f"  {k}: {v}")
    print()
    print(f"written -> {OUT_PATH}")
