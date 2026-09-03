"""gate_expiry_check.py -- THE GATE-EXPIRY INSTRUMENT (J directive 2026-07-31, verbatim:
"the same thing that worked on day three hundred and seventy two ago is not gonna work on
day one hundred and sixty two ago").

THE GAP THIS CLOSES: every armed veto/gate in this engine (backtest/lib/engine/gates.py's
GATE_ORDER, structure_veto_enabled, the free-model veto, fleet per-arm patches) was validated
ONCE against a scorecard and then blocks forever with NO re-validation clock. Concrete case:
block_elite_bull was revalidated 2026-07-10 (SS-B exit shape, KEEP -- "SS-B ~6.9x worse
without it") under a level feed that was later found broken, then kept blocking on that STALE
verdict through 2026-07-31 -- 111 fires same session on a maxed 11/11 bull setup, while the
fleet_rest arms (which structurally never inherit GATE_ORDER at all, per GATE-PROVENANCE-
CENSUS-2026-07-09) took the identical setup and made real money. Nothing noticed the evidence
had gone stale. This script is that notice.

WHAT IT REUSES BYTE-FOR-BIT (per the directive: "reuse recency_check.py's rolling-window
pattern and its N floor -- do not reinvent it"):
  - autoresearch.recency_check: RECENCY_LOOKBACK_TRADING_DAYS, CONFIRM_N_FLOOR, QTY_BY_ACCOUNT,
    read_cache_last_date, load_merged_spy_vix, resolve_window, window_metrics -- imported
    directly, never copy-pasted.
  - the real-OPRA-fills sim path: lib.simulator_real.simulate_trade_real (the SAME call
    recency_check.py's simulate_set uses), autoresearch.infinite_ammo_discovery's
    _strike_from_spot / _nearest_cached_strike, autoresearch._edgehunt_vwap_continuation's
    _normalize_spy / _align_vix, lib.ribbon.compute_ribbon, autoresearch._b5_vix_regime_dayside's
    _swing_stop (fallback stop level when a decision row carries no trigger level).

WHAT IT MEASURES, PER GATE: mines automation/state/core-decisions.jsonl for every row where
`verdict` equals the gate's SKIP action and `armed` is True (excludes the off-hours diagnostic/
gym-harness calls the 2026-07-09/07-10 audits found polluting fire counts), within the RECENT
window (same rolling N-trading-day window recency_check.py uses). Consecutive same-gate fires
within EVENT_CLUSTER_GAP_MINUTES are folded into ONE tradeable event (matches the
elite-bull-requal-2026-07-31.json map_window_min convention) -- a signal held for 20 minutes is
one refused trade, not four. Each event's located SPY 5m bar is checked against its OWN date;
a bar from a DIFFERENT session than the decision's timestamp is dropped as a stale-bar echo
(the exact contamination class GATE-PROVENANCE-SWEEP-2026-07-10 found and never wired a fix
for -- this miner avoids it by construction). Each surviving event is replayed forward through
the REAL OPRA option cache (ATM strike, same premium-stop convention recency_check uses) to
get its real realized P&L, then aggregated into a per-gate recent-window expectancy.

VERDICT (per gate, per the SAME CONFIRM/YELLOW/RED shape recency_check.py uses, but inverted
semantics -- here RED means the gate itself is the problem):
  RED     = the REFUSED cohort's recent-window expectancy is POSITIVE and n >= floor
            -> this gate is COSTING money right now; its evidence needs a fresh look.
  YELLOW  = refused cohort positive but n < floor -- watch, not yet actionable.
  GREEN   = refused cohort negative (still justified) OR the gate hasn't fired recently.
  Combined with evidence_age (last_revalidated vs the registry's revalidation_interval_days):
  a gate whose evidence has aged past its interval AND has no recent-window read gets flagged
  STALE_UNVERIFIED (distinct from RED -- it might be fine, nobody has checked).

NEVER BLOCKS, NEVER KILLS, NEVER AUTO-DISARMS ANYTHING. This is a REPORT. Arming/disarming a
gate stays a human/ratification decision (OP-16); this script's only side effects are writing
automation/state/gate-registry-status.json and, on a NEW transition into RED, one loud line
under automation/overnight/STATUS.md "## Known broken" -- byte-for-byte the same
transition-only, no-respam pattern as setup/guard_runner_slow.py::_flag_status_md. Fail-open
throughout (OP-25): a mining failure for one gate never aborts the others; the whole script
always exits 0.

SOUNDNESS FIX (self-caught incident, 2026-08-08 evening, same session that shipped the bug):
this instrument's forward-replay layer used to be `lib.simulator_real.simulate_trade_real`,
which carries two independently-documented, dated defects -- exit-shape divergence from the
REAL production exit_manager (2026-07-17 FRAME AUDIT) and same-bar/intrabar look-ahead in its
profit-lock ratchet (BACKTESTING-PLAYBOOK.md 2.12). Every EV figure this script ever wrote was
computed through that unsound path and had propagated into automation/state/gate-registry-
status.json, setup/scripts/gate_recency_report.py's weekly digest, and
markdown/doctrine/GATE-RECENCY-DOCTRINE.md's worked example -- an OP-33 (verify, don't claim)
violation. `evaluate_gate_pnl` now replays every armed gate's refused cohort through
`backtest/lib/exit_manager_walk.walk_exit_manager` (the ACTUAL production
`exit_manager.plan_exit_actions` core) instead -- the exact sound path
`analysis/recommendations/GATE-REVALIDATION-RESULTS-2026-08-08.md` /
`backtest/tools/gate_revalidation_ab.py` proved out the same night. This module's own
mining/attribution layer (`load_decision_rows`, `cluster_events`, `bar_idx_for_ts`,
`_stop_level_for_row`) was independently audited SOUND and is UNCHANGED -- only the
forward-replay call inside `evaluate_gate_pnl` moved. Every EV record `evaluate_gate_pnl`
produces now carries `replay_engine`/`replay_soundness` provenance stamps so a future reader
never mistakes a recomputed number for the old unsound one again. `simulate_event` (the old
simulate_trade_real-backed replay) is kept, UNCHANGED, purely because
`backtest/tools/postfix_gate_costing.py` imports it directly -- it is no longer called from
anywhere in this file's own flow; postfix_gate_costing.py's own use of the unsound path is a
separate, out-of-scope finding (flagged, not fixed, here).

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/gate_expiry_check.py
     [--lookback N] [--floor N] [--gate GATE_ID]
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, copied verbatim from
# setup/guard_runner_slow.py per the gate-expiry-instrument build directive) =======
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: a script launched wscript->run_exe_hidden.vbs->
# backtest-venv-pythonw with NO relay layer was caught flashing a WindowsTerminal
# window on a real Start-ScheduledTask fire within 45s. This script is launched via
# that exact chain (Gamma_GateExpiryCheck) and prints heavily (per-gate status
# lines), so it inherits the same risk without this guard.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "gate-expiry-check.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "gate-expiry-check.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch.recency_check import (  # noqa: E402
    RECENCY_LOOKBACK_TRADING_DAYS,
    CONFIRM_N_FLOOR,
    load_merged_spy_vix,
    resolve_window,
    window_metrics,
)
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    _nearest_cached_strike,
    _strike_from_spot,
)
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402
from autoresearch._b5_vix_regime_dayside import _swing_stop  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.concentration import drop_top_n  # noqa: E402

REGISTRY = ROOT / "automation" / "state" / "gate-registry.json"
OUT_JSON = ROOT / "automation" / "state" / "gate-registry-status.json"
STATUS_MD = ROOT / "automation" / "overnight" / "STATUS.md"
CORE_DECISIONS = ROOT / "automation" / "state" / "core-decisions.jsonl"
TRADES_ENRICHED = ROOT / "analysis" / "trades-enriched.jsonl"

# sim convention shared with recency_check.py / the harnesses (NEG=ITM, POS=OTM offset; 0=ATM)
PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4
STRIKE_OFFSET_ATM = 0

# consecutive same-gate fires within this many minutes are ONE tradeable event, not N.
EVENT_CLUSTER_GAP_MINUTES = 15

# concentration term (2026-08-23, see costing_verdict docstring): a refused cohort's positive
# mean must survive dropping its top-N winning trades before it can earn a bare actionable RED.
# 3 matches the G-battery's own drop_top3 methodology (gate_revalidation_ab.py::drop_top_n),
# so this instrument's smoke-alarm threshold and the ratifying battery's pass bar agree.
CONCENTRATION_DROP_TOP_N = 3

# categories this checker deliberately does NOT run a costing verdict against (disclosed,
# not silently skipped -- see check_gate()).
_NOT_MEASURED_CATEGORIES = {
    "safety_doctrine": "doctrine/regulatory gate (J's Rule 4/5/6/7), not a statistical edge -- excluded by design",
    "fleet_config": "fleet-scoped; not yet wired to this checker's core-decisions.jsonl miner (future extension)",
}


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def load_decision_rows(path: Path, since: dt.date) -> list[dict]:
    """Tail-read core-decisions.jsonl, keeping rows dated >= `since`. Fail-open per line."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            ts = r.get("ts_et")
            if not ts or len(ts) < 10:
                continue
            try:
                d = dt.date.fromisoformat(ts[:10])
            except ValueError:
                continue
            if d < since:
                continue
            rows.append(r)
    return rows


def cluster_events(rows: list[dict], gap_minutes: int) -> list[dict]:
    """Fold consecutive fires (already filtered to one account+gate) into one event per
    gap_minutes-separated cluster, keeping the cluster's FIRST row (earliest ts) as the
    tradeable signal -- matches elite-bull-requal-2026-07-31.json's map_window_min convention."""
    rows_sorted = sorted(rows, key=lambda r: r["ts_et"])
    events: list[dict] = []
    last_ts: dt.datetime | None = None
    for r in rows_sorted:
        try:
            ts = dt.datetime.fromisoformat(r["ts_et"])
        except ValueError:
            continue
        if last_ts is None or (ts - last_ts).total_seconds() > gap_minutes * 60:
            events.append(r)
        last_ts = ts
    return events


def bar_idx_for_ts(spy_ts: pd.Series, ts: dt.datetime) -> tuple[int | None, bool]:
    """Locate the last SPY 5m bar at-or-before `ts`. Returns (idx, is_stale) -- is_stale=True
    when the located bar's OWN date differs from ts's date (a prior-session phantom bar per
    the GATE-PROVENANCE-SWEEP-2026-07-10 finding: GATE_ORDER can fire on a carried-over bar
    before heartbeat_core's own stale-trigger-bar guard ever runs)."""
    pos = int(spy_ts.searchsorted(pd.Timestamp(ts), side="right")) - 1
    if pos < 0 or pos >= len(spy_ts):
        return None, True
    bar_ts = spy_ts.iloc[pos]
    return pos, (bar_ts.date() != ts.date())


def _stop_level_for_row(row: dict, spy: pd.DataFrame, bar_idx: int, side: str) -> float:
    for key in ("trigger_level_exact", "bull_reclaim_level_raw", "bear_rejection_level_raw"):
        v = row.get(key)
        if v is not None:
            return float(v)
    return _swing_stop(spy, bar_idx, side)


# ============================================================ SOUND forward-replay (2026-08-08
# soundness fix -- see module docstring). ====================================================
_SOUND_REPLAY_MODULE = None   # lazy-import cache, populated on first real use
_REPLAY_CTX_CACHE: dict = {}  # id(spy) -> (spy_by_date, ribbon_lookup), memoized per run


def _sound_replay_module():
    """Lazily import backtest/tools/gate_revalidation_ab.py -- the GATE-REVALIDATION-2026-08-08
    soundness fix -- and cache the module object. DEFERRED ON PURPOSE (function-scope, not a
    module-level import): gate_revalidation_ab.py itself imports THIS module's mining/
    attribution layer (load_decision_rows, cluster_events, bar_idx_for_ts, _stop_level_for_row)
    at ITS OWN module-load time, so a module-level import here would be circular. By the time
    this function is first CALLED, this module has already finished loading, so Python simply
    resolves the already-complete module object -- no circularity. Reused, not reimplemented:
    this is the exact replay approach GATE-REVALIDATION-RESULTS-2026-08-08.md proved sound
    (walk_exit_manager, the production exit_manager.plan_exit_actions core)."""
    global _SOUND_REPLAY_MODULE
    if _SOUND_REPLAY_MODULE is None:
        tools_dir = str(REPO / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import gate_revalidation_ab as _grab  # noqa: PLC0415 -- intentionally deferred, see above
        _SOUND_REPLAY_MODULE = _grab
    return _SOUND_REPLAY_MODULE


def _replay_context(spy: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """(spy_by_date, ribbon_lookup) for the sound replay path, memoized per spy DataFrame
    identity -- main() loads spy ONCE and reuses it across every gate this run; recomputing
    the ribbon + date groupby per-gate would repeat the same work ~20x for nothing."""
    key = id(spy)
    if key not in _REPLAY_CTX_CACHE:
        grab = _sound_replay_module()
        spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
        ribbon_lookup = grab.build_ribbon_lookup(spy)
        _REPLAY_CTX_CACHE[key] = (spy_by_date, ribbon_lookup)
    return _REPLAY_CTX_CACHE[key]


def simulate_event(row: dict, spy: pd.DataFrame, ribbon: pd.DataFrame, spy_ts: pd.Series,
                    qty: int, gate_id: str) -> dict:
    """Replay one refused signal forward through the REAL OPRA cache. Never raises -- every
    failure mode returns a tagged status dict so the caller can count it honestly instead of
    silently dropping it."""
    try:
        ts = dt.datetime.fromisoformat(row["ts_et"])
    except (KeyError, ValueError):
        return {"status": "bad_ts"}
    bar_idx, stale = bar_idx_for_ts(spy_ts, ts)
    if bar_idx is None:
        return {"status": "no_bar", "ts_et": row.get("ts_et")}
    if stale:
        return {"status": "stale_dropped", "ts_et": row.get("ts_et")}
    side = row.get("side")
    if side not in ("C", "P"):
        return {"status": "no_side", "ts_et": row.get("ts_et")}
    bar = spy.iloc[bar_idx]
    spot = float(bar["close"])
    d = bar["date"]
    atm = _strike_from_spot(spot)
    strike = _nearest_cached_strike(d, atm, side, MAX_STRIKE_STEPS)
    if strike is None:
        return {"status": "no_contract", "ts_et": row.get("ts_et")}
    stop_level = _stop_level_for_row(row, spy, bar_idx, side)
    try:
        fill = simulate_trade_real(
            entry_bar_idx=bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=stop_level, triggers_fired=row.get("triggers") or [gate_id],
            side=side, qty=qty, setup=gate_id, strike_override=strike,
            premium_stop_pct=PREMIUM_STOP_PCT,
        )
    except Exception as exc:  # noqa: BLE001 -- one bad row must never abort the gate's measurement
        return {"status": "sim_error", "ts_et": row.get("ts_et"), "error": str(exc)}
    if fill is None or fill.dollar_pnl is None:
        return {"status": "sim_none", "ts_et": row.get("ts_et")}
    return {
        "status": "ok",
        "date": str(d),
        "pnl": round(float(fill.dollar_pnl), 2),
        "entry_premium": round(float(fill.entry_premium), 4),
        "exit": fill.exit_reason.name if fill.exit_reason else "NONE",
        "ts_et": row.get("ts_et"),
    }


def costing_verdict(m: dict, floor: int) -> tuple[str, str]:
    """RED = the refused cohort would have EARNED money recently (gate is costing). Mirror of
    recency_check.verdict_for's shape, INVERTED semantics (see module docstring).

    CONCENTRATION TERM (added 2026-08-23, J directive, OP-25 self-correction): this used to be
    a NAIVE MEAN ONLY check -- n>=floor AND mean>0 => bare RED, no drop-topN, no OOS split, no
    BH-FDR, no bootstrap null. Two independent full G-battery revalidations this same weekend
    proved that wrong BOTH times it fired: structure_veto_enabled (naive: n=10, +$2.15/tr =>
    RED; battery: n=15, mean +$7.43/tr, drop_top3=-$588.00, BH-FDR p=0.836 => NOT-UNBLOCK-
    ELIGIBLE -- see analysis/recommendations/gate-revalidation-structure_veto-2026-08-23-
    extended.json) and require_bearish_fill_bar (naive: n=34, +$46.15/tr => RED; battery: n=57,
    mean +$23.11/tr, drop_top3=-$958.00, BH-FDR p=0.5374, bootstrap-null p=0.3311 => NOT-
    UNBLOCK-ELIGIBLE -- gate-revalidation-bearish_fill_bar-2026-08-23-extended.json). In both
    cases a handful of outlier winners carried the whole positive mean. A bare actionable RED
    can no longer be emitted for a cohort like that: `m["drop_top3"]` (the refused cohort's
    per-trade P&L total AFTER dropping its top-3 winning trades -- see
    backtest/tools/gate_revalidation_ab.py::drop_top_n, REUSED here, never reimplemented) must
    be POSITIVE for the mean-positive/over-floor read to earn a bare RED. Missing/unknown
    concentration data (m has no "drop_top3" key) is treated as UNPROVEN, never as an automatic
    pass -- this check fails CLOSED, exactly the class of silent-pass bug that produced both
    false alarms. A concentration-carried cohort downgrades to NAIVE_RED_CONCENTRATED, labeled
    "NAIVE-RED (battery required)" in its reason -- explicitly NOT actionable on its own; it
    can never again be misread as a finished finding. A cohort that DOES survive drop-top3
    keeps RED, but its reason now also says a full G-battery is still the ratifying instrument
    before any params.json flip -- this checker was never meant to be the final word, only the
    smoke alarm that says "go run the battery."
    """
    n = m.get("n", 0)
    if n == 0:
        return "INSUFFICIENT_DATA", "no refused signals survived mining in the recent window"
    exp = m.get("exp_per_trade")
    if exp is not None and exp > 0:
        if n >= floor:
            drop_top3 = m.get("drop_top3")
            n_dropped = m.get("n_dropped_for_drop_top3", CONCENTRATION_DROP_TOP_N)
            if drop_top3 is None or drop_top3 <= 0:
                concentration_note = (
                    f"drop-top{n_dropped}=${drop_top3}" if drop_top3 is not None
                    else "drop-topN concentration UNKNOWN (no per-trade P&L supplied to costing_verdict)"
                )
                return (
                    "NAIVE_RED_CONCENTRATED",
                    f"NAIVE-RED (battery required): refused cohort reads +${exp}/tr, n={n} >= "
                    f"floor {floor}, but {concentration_note} -- the positive mean does NOT "
                    f"survive dropping its top {n_dropped} winning trade(s), so this naive read "
                    f"is NOT actionable on its own. A full G-battery (OOS split + BH-FDR + "
                    f"bootstrap null vs random entry -- backtest/tools/gate_revalidation_ab.py) "
                    f"must ratify before this gate is treated as costing money."
                )
            return (
                "RED",
                f"refused cohort would have EARNED ${exp}/tr, n={n} >= floor {floor} -- COSTING "
                f"money AND survives drop-top{n_dropped} (${drop_top3}). A full G-battery is "
                f"still the ratifying instrument before any params.json flip -- this is the "
                f"smoke alarm, not the verdict."
            )
        return "YELLOW", f"refused cohort positive (${exp}/tr) but n={n} < floor {floor} -- watch, not yet actionable"
    return "GREEN", f"refused cohort would have LOST ${exp}/tr, n={n} -- still justified on recent data"


def evaluate_gate_pnl(gate: dict, spy: pd.DataFrame, ribbon: pd.DataFrame, spy_ts: pd.Series,
                       recent_start: dt.date, recent_end: dt.date, floor: int) -> dict:
    """SOUND as of 2026-08-08 (see module docstring): forward-replay now runs every armed
    gate's refused cohort through backtest/lib/exit_manager_walk.walk_exit_manager (the
    production exit_manager.plan_exit_actions core) via a lazy import of
    backtest/tools/gate_revalidation_ab.py's replay_row/account_config/build_ribbon_lookup --
    NOT lib.simulator_real.simulate_trade_real. `ribbon` is accepted-but-unused: retained ONLY
    so this function's call signature (and check_gate's positional call into it) stays
    byte-identical, since backtest/tests/test_gate_expiry_check.py monkeypatches this whole
    function with a 7-positional-arg fake in several places."""
    skip_action = gate.get("skip_action")
    if not skip_action or skip_action in ("n/a",) or "not a" in (skip_action or ""):
        return {"verdict": "NOT_MEASURED", "reason": "gate has no single SKIP_* action to mine"}
    accounts_armed = gate.get("accounts_armed", {}) or {}
    if not any(accounts_armed.get(a) for a in ("safe", "bold")):
        return {"verdict": "INERT", "reason": "not armed on either account -- nothing to measure"}

    grab = _sound_replay_module()
    spy_by_date, ribbon_lookup = _replay_context(spy)
    account_cfg = grab.account_config()

    by_account: dict[str, dict] = {}
    all_ok_rows: list[dict] = []
    for account in ("safe", "bold"):
        if not accounts_armed.get(account):
            continue
        rows = [
            r for r in load_decision_rows(CORE_DECISIONS, recent_start)
            if r.get("account") == account and r.get("verdict") == skip_action and r.get("armed") is True
        ]
        events = cluster_events(rows, EVENT_CLUSTER_GAP_MINUTES)
        cfg = account_cfg[account]
        sim_results = [
            grab.replay_row(ev, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                             ribbon_lookup=ribbon_lookup, cfg=cfg)
            for ev in events
        ]
        ok_rows = [r for r in sim_results if r["status"] == "ok"]
        status_counts: dict[str, int] = {}
        for r in sim_results:
            status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
        metrics = window_metrics(ok_rows, recent_start, recent_end) if ok_rows else {"n": 0}
        by_account[account] = {
            "n_raw_fires": len(rows),
            "n_events": len(events),
            "status_counts": status_counts,
            **metrics,
        }
        all_ok_rows.extend(ok_rows)

    combined = window_metrics(all_ok_rows, recent_start, recent_end) if all_ok_rows else {"n": 0}
    if all_ok_rows:
        # CONCENTRATION TERM (2026-08-23, see costing_verdict docstring): drop-top1 and
        # drop-top3 on the refused cohort's own per-trade P&L, via the shared
        # backtest/lib/concentration.py::drop_top_n helper (2026-08-23 fold -- this used to
        # call backtest/tools/gate_revalidation_ab.py's own drop_top_n through the
        # already-lazily-imported `grab`; now BOTH this instrument and
        # core_strategy_recency.py's direction_verdict call the ONE shared implementation so
        # there is no third copy of this math. Identical algorithm/rounding -- this refactor
        # is behavior-preserving, pinned by test_gate_expiry_naive_red_guard_2026_08_23.py
        # staying green unchanged). drop_top3 is what gates costing_verdict's actionability;
        # drop_top1 is carried for visibility only.
        records = [(str(r.get("date")), float(r["pnl"])) for r in all_ok_rows]
        drop_top1, n_dropped_1 = drop_top_n(records, 1)
        drop_top3, n_dropped_3 = drop_top_n(records, CONCENTRATION_DROP_TOP_N)
        combined = {
            **combined,
            "drop_top1": drop_top1, "n_dropped_for_drop_top1": n_dropped_1,
            "drop_top3": drop_top3, "n_dropped_for_drop_top3": n_dropped_3,
        }
    verdict, reason = costing_verdict(combined, floor)
    return {
        "by_account": by_account, "combined": combined, "verdict": verdict, "reason": reason,
        # PROVENANCE STAMP (2026-08-08 soundness fix, OP-33): every EV record this function
        # produces -- including n=0 INSUFFICIENT_DATA reads, which still ran the sound replay
        # and found nothing -- carries these two fields so a future reader can never mistake
        # a freshly-computed number for the retired simulate_trade_real-backed one. Rows this
        # function never reaches (NOT_MEASURED/INERT above, or ERROR from check_gate's own
        # try/except wrapper, or category=="core_strategy" which routes to the SEPARATE
        # real-broker-fills instrument core_strategy_recency.py and never calls this function
        # at all) carry no EV number and are deliberately left unstamped -- stamping them
        # "walk_exit_manager"/"sound" would be a FALSE provenance claim, not a true one.
        "replay_engine": "walk_exit_manager",
        "replay_soundness": "sound",
    }


def evidence_age_days(gate: dict, today: dt.date) -> int | None:
    lr = gate.get("last_revalidated")
    if not isinstance(lr, str) or len(lr) < 10 or lr[:10].count("-") != 2:
        return None
    try:
        d = dt.date.fromisoformat(lr[:10])
    except ValueError:
        return None
    return (today - d).days


def check_gate(gate: dict, spy: pd.DataFrame, ribbon: pd.DataFrame, spy_ts: pd.Series,
                recent_start: dt.date, recent_end: dt.date, floor: int, today: dt.date) -> dict:
    age = evidence_age_days(gate, today)
    interval = gate.get("revalidation_interval_days")
    evidence_stale = bool(interval and age is not None and age > interval)

    category = gate.get("category")
    if category == "core_strategy":
        # WS11 (2026-08-01): the CORE RIDE_THE_RIBBON strategy's own recency rows
        # (core_strategy_bear / core_strategy_bull). Not a refusal gate -- there is no
        # SKIP verdict to mine -- so the category routes to the sibling instrument
        # (real-broker-fills authority + disclosed Safe-shape replay supplement).
        # SEMANTICS NOTE: RED here means the strategy ITSELF is losing on recent real
        # fills, not "a gate is costing money" -- both mean look-now on this surface.
        # Fail-open like every other row: an eval failure degrades to ERROR, never
        # sinks the other gates.
        try:
            from autoresearch import core_strategy_recency as _csr
            pnl_check = _csr.evaluate_for_registry(gate, floor=floor)
        except Exception as exc:  # noqa: BLE001
            pnl_check = {"verdict": "ERROR", "reason": f"core-strategy recency eval failed: {exc}"}
    elif category in _NOT_MEASURED_CATEGORIES:
        pnl_check = {"verdict": "NOT_MEASURED", "reason": _NOT_MEASURED_CATEGORIES[category]}
    else:
        try:
            pnl_check = evaluate_gate_pnl(gate, spy, ribbon, spy_ts, recent_start, recent_end, floor)
        except Exception as exc:  # noqa: BLE001 -- one gate's failure must never sink the run (OP-25 fail-open)
            pnl_check = {"verdict": "ERROR", "reason": f"mining failed: {exc}"}

    pv = pnl_check["verdict"]
    if pv == "RED":
        overall = "RED"
    elif pv == "NAIVE_RED_CONCENTRATED":
        # 2026-08-23 concentration term: measured, found concentration-carried -- distinct from
        # STALE_UNVERIFIED (which means "never checked"). Deliberately NEVER "RED": this is the
        # exact field compute_newly_red/flag_status_md gate on (r["overall"] == "RED") to decide
        # whether to scream in STATUS.md's "## Known broken" -- a concentration-carried naive
        # read must never trip that alarm again.
        overall = "NAIVE_RED_CONCENTRATED"
    elif pv in ("GREEN_CONCENTRATED", "RED_CONCENTRATED"):
        # 2026-08-23, 3rd instance of the same defect (core_strategy_recency.py's
        # direction_verdict): a category=="core_strategy" row can now report a
        # concentration-carried GREEN or RED (see core_strategy_recency.py docstring --
        # the bull "+$2.45/tr GREEN" that was actually 2 days out of 31 trades). Both pass
        # straight through, distinct from plain "GREEN"/"RED" and from NAIVE_RED_CONCENTRATED
        # (a different instrument's vocabulary) -- and, critically, distinct from the literal
        # string "RED" that compute_newly_red/flag_status_md key off, so a concentration-
        # carried core-strategy verdict never trips the STATUS.md "## Known broken" alarm
        # in either direction.
        overall = pv
    elif pv == "ERROR":
        overall = "ERROR"
    elif evidence_stale and pv in ("INSUFFICIENT_DATA", "INERT", "NOT_MEASURED"):
        overall = "STALE_UNVERIFIED"
    elif pv == "YELLOW":
        overall = "YELLOW"
    else:
        overall = "GREEN"

    return {
        "id": gate["id"],
        "category": category,
        "evidence_age_days": age,
        "revalidation_interval_days": interval,
        "evidence_stale": evidence_stale,
        "pnl_check": pnl_check,
        "overall": overall,
    }


# ============================================================ SOLE-BLOCKER MINER (queue item
# GATE-EXPIRY-SOLE-BLOCKER-MINER, built 2026-09-03): extends this nightly instrument's
# refusal-costing clock from the SKIP-verdict gates above to the 11-filter bull/bear checklist,
# which refuses via HOLD rows carrying per-door blocker lists (bear_blockers/bull_blockers),
# not a SKIP_* action -- so it had NO clock at all before this (see
# analysis/recommendations/vix-bear-floor-postfix-quantification-2026-08-04.json's
# "standing_watch_condition": "queue item filed to extend the nightly gate-expiry instrument
# with this sole-blocker miner so the watch is mechanical, not remembered").
#
# MINING: reuses backtest/tools/postfix_gate_costing.py's DOORS map + sole_blocker_rows()
# selector byte-for-bit (lazy-imported below via _postfix_module(), mirroring
# _sound_replay_module()'s pattern -- postfix_gate_costing.py imports FROM this module at ITS
# OWN load time, so a module-level import here would be circular). A HOLD row counts for filter
# N iff its door's blocker list is EXACTLY [N] (C15: multi-blocker rows are cascade cohorts, no
# single filter may claim them).
#
# COSTING: this build deliberately does NOT forward-replay through the OPRA option cache /
# walk_exit_manager tonight (the cache was held by a parallel builder's exit-walk replay work
# at build time) -- every cell this miner emits is stamped `"costing": "NOT_REPLAYED"`. In place
# of a dollar EV it reports a cheap DIRECTIONAL proxy: the day's own P1 outcome (the next REAL
# entry taken that trading day, same door/side, from analysis/trades-enriched.jsonl) --
#   WIN  -> "cost_money"  (a same-direction real trade won; the refused signal plausibly would
#                          have too)
#   LOSS -> "saved_money" (a same-direction real trade lost; the refusal plausibly was correct)
#   none found that day/side -> "unknown"
# This is WEAKER evidence than evaluate_gate_pnl's $ replay above (one proxy trade standing in
# for the refused signal's own counterfactual walk, not a forward simulation of THAT signal) and
# must never be read as a dollar figure. A full replay (postfix_gate_costing.py --start/--end,
# or a future extension of this file once the OPRA cache is free) remains the ratifying
# instrument -- exactly as costing_verdict's RED reason already says for the SKIP gates above.
# ==============================================================================================

# Flagship watches named by the queue item -- folded into the SAME gate-result shape
# (id/overall/pnl_check) as every other row in `results` so compute_newly_red/flag_status_md
# flag them with byte-identical transition-only, no-respam semantics. door, filter id.
SOLE_BLOCKER_FLAGSHIPS = {
    "filter-8-bear-sole": ("bear", 8),   # VIX floor -- post-fix count expected 0
    "filter-10-bull-sole": ("bull", 10),  # buyer pressure -- bull-f10-buyer-pressure-prereg-2026-08-04.json
}

_POSTFIX_MODULE = None  # lazy-import cache, mirrors _SOUND_REPLAY_MODULE above


def _postfix_module():
    """Lazily import backtest/tools/postfix_gate_costing.py -- DEFERRED ON PURPOSE (function-
    scope, not module-level): that module imports THIS module's mining layer (CORE_DECISIONS,
    EVENT_CLUSTER_GAP_MINUTES, cluster_events, load_decision_rows) at ITS OWN module-load time,
    so a module-level import here would be circular. By the time this function is first
    CALLED, this module has already finished loading -- Python simply resolves the
    already-complete module object, no circularity."""
    global _POSTFIX_MODULE
    if _POSTFIX_MODULE is None:
        tools_dir = str(REPO / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import postfix_gate_costing as _pgc  # noqa: PLC0415 -- intentionally deferred, see above
        _POSTFIX_MODULE = _pgc
    return _POSTFIX_MODULE


def load_p1_outcomes_by_day(path: Path = TRADES_ENRICHED) -> dict[tuple[str, str], list[dict]]:
    """(date, side) -> real fills that day on that side, sorted by entry_ts_et. side is 'C'/'P'
    (trades-enriched.jsonl's own `right` field). Fail-open per line, matches
    load_decision_rows' own tolerance -- a malformed row must never abort the whole miner."""
    out: dict[tuple[str, str], list[dict]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            date, side, ts = r.get("date"), r.get("right"), r.get("entry_ts_et")
            if not date or side not in ("C", "P") or not ts:
                continue
            out.setdefault((date, side), []).append(r)
    for key, rows in out.items():
        rows.sort(key=lambda r: r["entry_ts_et"])
    return out


def p1_outcome_for_event(ev: dict, p1_by_day: dict[tuple[str, str], list[dict]], side: str) -> tuple[str, float | None]:
    """('WIN'|'LOSS'|'NONE', pnl_dollars_or_None) for the day's next real P1 entry (same
    door/side) at-or-after the refused event's own timestamp; if none fired after it that day,
    fall back to the day's last same-side fill (still the day's own outcome, just before the
    refusal instead of after); NONE if no same-side real fill exists that day at all."""
    ts = ev.get("ts_et", "")
    date = ts[:10]
    candidates = p1_by_day.get((date, side), [])
    if not candidates:
        return "NONE", None
    after = [c for c in candidates if c["entry_ts_et"] >= ts]
    chosen = after[0] if after else candidates[-1]
    pnl = chosen.get("pnl_dollars")
    if pnl is None:
        return "NONE", None
    return ("WIN" if pnl > 0 else "LOSS"), round(float(pnl), 2)


def sole_blocker_events(rows_hold: list[dict], door: str, filt: int) -> list[dict]:
    """HOLD rows (one account's worth, verdict=='HOLD') exact-sole-blocked on `filt` for
    `door`, clustered into tradeable events via this module's own cluster_events -- the
    IDENTICAL 15-min folding the SKIP gates above use."""
    grab = _postfix_module()
    bkey, side, lvl_key = grab.DOORS[door]
    sub = []
    for r in grab.sole_blocker_rows(rows_hold, bkey, filt):
        ev = dict(r)
        ev["side"] = side
        if r.get(lvl_key) is not None:
            ev["trigger_level_exact"] = r[lvl_key]
        sub.append(ev)
    return cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)


def sole_blocker_rows_all_accounts(holds_by_account: dict[str, list[dict]], door: str,
                                    filt: int) -> list[dict]:
    """Raw (pre-cluster) sole-blocked-on-`filt` HOLD rows for `door`, combined across BOTH
    accounts (row copies, same shape sole_blocker_events produces per-account) -- feeds the
    cross-account `episodes_distinct` clustering below. GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-COUNT
    (2026-09-03): the SAME refused market moment produces one HOLD row per account (identical
    gate logic, identical market data -- only qty differs), so accounts must be combined and
    re-clustered TOGETHER, never counted per-account and then summed."""
    grab = _postfix_module()
    bkey, side, lvl_key = grab.DOORS[door]
    sub = []
    for holds in holds_by_account.values():
        for r in grab.sole_blocker_rows(holds, bkey, filt):
            ev = dict(r)
            ev["side"] = side
            if r.get(lvl_key) is not None:
                ev["trigger_level_exact"] = r[lvl_key]
            sub.append(ev)
    return sub


def mine_sole_blockers(recent_start: dt.date, recent_end: dt.date,
                        p1_by_day: dict | None = None,
                        filters: range = range(1, 12)) -> dict[str, dict]:
    """Per door x filter x account, over [recent_start, recent_end]: sole-blocker event counts
    + the NOT_REPLAYED directional read (see module-section docstring above). Called twice by
    main() below -- once for the single most-recent session, once for the rolling 20-session
    window -- by passing recent_start==recent_end for the former.

    GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-COUNT (2026-09-03, filed from the first live run's bear
    sole-[8] 106-events/14-sessions read): safe and bold run the IDENTICAL bull/bear checklist
    against the SAME market data, so a refused moment mechanically produces one HOLD row per
    account -- verified live: bear_filter8_safe and bear_filter8_bold both read exactly 53
    events over the same rolling window, byte-identical. Summing the two per-account
    `n_events` (what the flagship watches used to do) double-counts every such episode. Each
    emitted cell below now also carries `events_raw` (== the pre-existing per-account
    `n_events`, unchanged) plus the cross-account-deduped `episodes_distinct` (+ its own
    cost/saved/unknown split) computed ONCE per door+filter and duplicated onto every matching
    account cell -- additive, nothing removed."""
    grab = _postfix_module()
    if p1_by_day is None:
        p1_by_day = load_p1_outcomes_by_day()
    rows = [
        r for r in load_decision_rows(CORE_DECISIONS, recent_start)
        if r.get("ts_et", "")[:10] <= recent_end.isoformat() and r.get("armed") is True
    ]
    out: dict[str, dict] = {}
    for door in grab.DOORS:
        side = grab.DOORS[door][1]
        holds_by_account = {
            account: [r for r in rows if r.get("account") == account and r.get("verdict") == "HOLD"]
            for account in ("safe", "bold")
        }
        for filt in filters:
            per_account_events = {
                account: sole_blocker_events(holds_by_account[account], door, filt)
                for account in ("safe", "bold")
            }
            if not any(per_account_events.values()):
                continue

            distinct_raw = sole_blocker_rows_all_accounts(holds_by_account, door, filt)
            distinct_events = cluster_events(distinct_raw, EVENT_CLUSTER_GAP_MINUTES)
            dcost = dsaved = dunknown = 0
            for ev in distinct_events:
                read, _pnl = p1_outcome_for_event(ev, p1_by_day, side)
                if read == "WIN":
                    dcost += 1
                elif read == "LOSS":
                    dsaved += 1
                else:
                    dunknown += 1

            for account in ("safe", "bold"):
                events = per_account_events[account]
                if not events:
                    continue
                cost = saved = unknown = 0
                for ev in events:
                    read, _pnl = p1_outcome_for_event(ev, p1_by_day, side)
                    if read == "WIN":
                        cost += 1
                    elif read == "LOSS":
                        saved += 1
                    else:
                        unknown += 1
                key = f"{door}_filter{filt}_{account}"
                out[key] = {
                    "n_events": len(events), "n_cost_money": cost, "n_saved_money": saved,
                    "n_unknown": unknown, "costing": "NOT_REPLAYED",
                    # additive -- GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-COUNT (2026-09-03)
                    "events_raw": len(events),
                    "episodes_distinct": len(distinct_events),
                    "n_cost_money_distinct": dcost,
                    "n_saved_money_distinct": dsaved,
                    "n_unknown_distinct": dunknown,
                }
    return out


def sole_blocker_top5(sole_blocker_report: dict[str, dict]) -> dict[str, list[dict]]:
    """Per door, the top-5 filter ids by summed n_events across both accounts -- the
    human-readable rollup the queue item's report asks for."""
    by_door_filter: dict[tuple[str, int], int] = {}
    for key, cell in sole_blocker_report.items():
        door, rest = key.split("_filter", 1)
        filt_str, _account = rest.split("_", 1)
        dk = (door, int(filt_str))
        by_door_filter[dk] = by_door_filter.get(dk, 0) + cell["n_events"]
    out: dict[str, list[dict]] = {}
    for door in {d for d, _f in by_door_filter}:
        ranked = sorted(
            ((f, n) for (d, f), n in by_door_filter.items() if d == door),
            key=lambda t: -t[1],
        )[:5]
        out[door] = [{"filter": f, "n_events": n} for f, n in ranked]
    return out


def sole_blocker_flagship_results(sole_blocker_report: dict[str, dict], floor: int) -> dict[str, dict]:
    """The two named watches (bear sole-[8] VIX floor, bull sole-[10] buyer pressure) folded
    into a gate-result-shaped dict (id/category/overall/pnl_check) so they can be merged into
    `results` before compute_newly_red/flag_status_md -- reusing that transition-only, no-respam
    machinery verbatim rather than building a second alarm surface. verdict is directional
    (NOT_REPLAYED, see module-section docstring) -- RED here means 'watch fired, go run a full
    replay', never a proven $ costing.

    GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-COUNT (2026-09-03): the transition-flag/RED threshold now
    reads the cross-account-deduped `episodes_distinct` count (mine_sole_blockers computes it
    once per door+filter and duplicates it onto every matching account cell -- take it from any
    one cell, never sum across cells) instead of naively summing each account's already-
    clustered `n_events`, which double-counted every episode both accounts refuse together.
    `events_raw` (the old naive sum) is still disclosed in full for audit. Cells built by hand
    without the distinct fields (pre-fix callers/fixtures) fall back to the old sum-based
    behavior so nothing that predates this fix breaks."""
    results: dict[str, dict] = {}
    for gate_id, (door, filt) in SOLE_BLOCKER_FLAGSHIPS.items():
        prefix = f"{door}_filter{filt}_"
        cells = [v for k, v in sole_blocker_report.items() if k.startswith(prefix)]
        n_events_raw = sum(v.get("events_raw", v["n_events"]) for v in cells)
        has_distinct = bool(cells) and all("episodes_distinct" in v for v in cells)
        if has_distinct:
            # computed once per door+filter, identical on every matching account cell --
            # read it once, do not sum across accounts.
            n_episodes = cells[0]["episodes_distinct"]
            n_cost = cells[0]["n_cost_money_distinct"]
            n_saved = cells[0]["n_saved_money_distinct"]
            unit = "distinct episode"
        else:
            # legacy fallback: no distinct fields available (hand-built report/fixture) --
            # old naive cross-account sum, kept so pre-fix callers still get a verdict.
            n_episodes = n_events_raw
            n_cost = sum(v["n_cost_money"] for v in cells)
            n_saved = sum(v["n_saved_money"] for v in cells)
            unit = "bar-event"
        if n_episodes == 0:
            overall, reason = "GREEN", (f"{door} sole-[{filt}]: 0 refusal {unit}s in window "
                                        f"({n_events_raw} raw account-row(s))")
        elif n_cost >= floor:
            overall = "RED"
            reason = (f"{door} sole-[{filt}] refused {n_episodes} {unit}(s) ({n_events_raw} raw "
                      f"account-row(s) across safe+bold), {n_cost} >= floor {floor} read "
                      f"cost_money via the day's own P1 WIN (NOT_REPLAYED proxy -- directional "
                      f"smoke alarm, not a dollar costing verdict; a full replay via "
                      f"backtest/tools/postfix_gate_costing.py is the ratifying instrument)")
        elif n_cost > 0:
            overall = "YELLOW"
            reason = (f"{door} sole-[{filt}]: {n_cost} cost_money read(s) of {n_episodes} "
                      f"{unit}s ({n_events_raw} raw account-row(s)), under floor {floor} -- "
                      f"watch, not yet actionable")
        else:
            overall = "GREEN"
            reason = (f"{door} sole-[{filt}]: {n_episodes} refusal {unit}(s) ({n_events_raw} raw "
                      f"account-row(s)), {n_saved} read saved_money, 0 read cost_money")
        results[gate_id] = {
            "id": gate_id, "category": "sole_blocker_watch", "evidence_age_days": None,
            "revalidation_interval_days": None, "evidence_stale": False,
            "pnl_check": {"verdict": overall, "reason": reason, "costing": "NOT_REPLAYED",
                          # "n_events" kept for backward compat -- now the value that DRIVES
                          # the verdict (distinct when available, legacy sum otherwise).
                          "n_events": n_episodes, "n_cost_money": n_cost, "n_saved_money": n_saved,
                          # additive disclosure
                          "n_events_raw": n_events_raw,
                          "n_episodes_distinct": n_episodes if has_distinct else None},
            "overall": overall,
        }
    return results


def compute_newly_red(results: dict[str, dict], prior_gates: dict) -> list[dict]:
    """Gates whose overall verdict is RED THIS run but was NOT RED on the prior run (or had
    no prior run) -- the exact set that should get a fresh STATUS.md line. A persisting RED
    (was RED last run too) is deliberately excluded -- see module docstring's no-respam rule."""
    new_red = []
    for gate_id, r in results.items():
        was_red = prior_gates.get(gate_id, {}).get("overall") == "RED"
        if r["overall"] == "RED" and not was_red:
            new_red.append(r)
    return new_red


def flag_status_md(new_red: list[dict]) -> None:
    """Append ONE loud line per newly-RED gate under '## Known broken' -- byte-for-byte the
    same transition-only, no-respam pattern as setup/guard_runner_slow.py::_flag_status_md."""
    if not new_red:
        return
    try:
        text = STATUS_MD.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    if marker not in text:
        return
    lines = []
    for g in new_red:
        reason = g["pnl_check"].get("reason", "")
        lines.append(
            f"- [{_now()}] GATE-EXPIRY RED :: {g['id']} :: {reason} :: "
            f"re-check: backtest\\.venv\\Scripts\\python.exe backtest\\autoresearch\\gate_expiry_check.py --gate {g['id']}"
        )
    head, _, tail = text.partition(marker + "\n")
    block = "\n".join(lines)
    STATUS_MD.write_text(f"{head}{marker}\n\n{block}\n{tail.lstrip(chr(10))}", encoding="utf-8")


def merge_gate_results(results: dict[str, dict], prior_gates: dict) -> dict:
    """Merge this run's freshly-computed `results` into whatever gates already exist in the
    status file (`prior_gates`) instead of blindly replacing the whole "gates" object.

    FIXES the 2026-08-23 truncation bug (found by this weekend's G-battery run, disclosed
    alongside the naive-RED costing_verdict defect): a `--gate <id>` single-gate debug/
    revalidation run only ever computes ONE gate's row, but main() used to write `results`
    (that one gate) as the entire "gates" object in automation/state/gate-registry-status.json
    -- destroying the other ~22 gates' rows on every filtered run. A full (unfiltered) nightly
    run still recomputes every registry gate each time, so `results` already covers every id
    and this merge is a no-op equivalent to the old full-replace behavior -- only a `--gate`-
    filtered run's blast radius changes (from "wipes the file" to "updates one row")."""
    return {**prior_gates, **results}


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate-expiry instrument: nightly recency check for every armed entry gate/veto")
    ap.add_argument("--lookback", type=int, default=RECENCY_LOOKBACK_TRADING_DAYS)
    ap.add_argument("--floor", type=int, default=CONFIRM_N_FLOOR)
    ap.add_argument("--gate", type=str, default=None, help="only check this gate id (debug)")
    ap.add_argument("--sole-blocker-lookback", type=int, default=20,
                     help="rolling window (trading days) for the filter-checklist sole-blocker miner")
    args = ap.parse_args()

    registry = load_registry()
    gates = registry["gates"]
    run_sole_blockers = args.gate is None or args.gate in SOLE_BLOCKER_FLAGSHIPS
    if args.gate:
        gates = [g for g in gates if g["id"] == args.gate]
        if not gates and not run_sole_blockers:
            print(f"[gate-expiry] unknown gate id {args.gate!r}", flush=True)
            return 1

    today = dt.date.today()

    print("[gate-expiry] loading merged SPY+VIX (master + recent) ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    _align_vix(spy, vix_raw)  # aligned VIX not separately needed by this miner; call kept for parity/side-effect-free reuse
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    trading_days = sorted(spy["date"].unique())
    spy_ts = spy["timestamp_et"]

    ns = argparse.Namespace(end=None, start=None, lookback=args.lookback)
    recent_start, recent_end, cache_last = resolve_window(ns, trading_days)
    print(f"[gate-expiry] recent window {recent_start}..{recent_end} (OPRA cache last {cache_last}), "
          f"floor n>={args.floor}, {len(gates)} gate(s) to check", flush=True)

    prior_gates: dict = {}
    if OUT_JSON.exists():
        try:
            prior_gates = json.loads(OUT_JSON.read_text(encoding="utf-8")).get("gates", {})
        except (OSError, ValueError):
            prior_gates = {}

    results: dict[str, dict] = {}
    for gate in gates:
        r = check_gate(gate, spy, ribbon, spy_ts, recent_start, recent_end, args.floor, today)
        results[gate["id"]] = r
        print(f"[gate-expiry] {gate['id']:38s} overall={r['overall']:18s} "
              f"evidence_age={r['evidence_age_days']}d pnl={r['pnl_check']['verdict']}", flush=True)

    # ---- SOLE-BLOCKER MINER (GATE-EXPIRY-SOLE-BLOCKER-MINER, 2026-09-03) -----------------
    sole_blocker_report: dict[str, dict] = {}
    sole_blocker_session_report: dict[str, dict] = {}
    sole_blocker_top5_20: dict[str, list[dict]] = {}
    # defined outside the try so the summary dict below can reference them even on failure
    # (fail-open, OP-25): session_start/sb_start/sb_end never depend on a risky call.
    session_start = trading_days[-1] if trading_days else recent_end
    ns20 = argparse.Namespace(end=None, start=None, lookback=args.sole_blocker_lookback)
    sb_start, sb_end, _ = resolve_window(ns20, trading_days) if trading_days else (recent_start, recent_end, cache_last)
    if run_sole_blockers:
        try:
            p1_by_day = load_p1_outcomes_by_day()
            sole_blocker_report = mine_sole_blockers(sb_start, sb_end, p1_by_day=p1_by_day)
            sole_blocker_session_report = mine_sole_blockers(session_start, session_start, p1_by_day=p1_by_day)
            sole_blocker_top5_20 = sole_blocker_top5(sole_blocker_report)
            flagship_results = sole_blocker_flagship_results(sole_blocker_report, args.floor)
            results.update(flagship_results)
            for gid, r in flagship_results.items():
                print(f"[gate-expiry] {gid:38s} overall={r['overall']:18s} pnl={r['pnl_check']['verdict']}", flush=True)
        except Exception as exc:  # noqa: BLE001 -- OP-25 fail-open: sole-blocker miner failure must never sink the run
            print(f"[gate-expiry] sole-blocker miner failed: {exc}", flush=True)
            for gid in SOLE_BLOCKER_FLAGSHIPS:
                results[gid] = {"id": gid, "category": "sole_blocker_watch", "overall": "ERROR",
                                "pnl_check": {"verdict": "ERROR", "reason": f"sole-blocker mining failed: {exc}",
                                              "costing": "NOT_REPLAYED"}}

    new_red = compute_newly_red(results, prior_gates)

    summary = {
        "checker": "gate-expiry instrument (J directive 2026-07-31)",
        "run_date": today.isoformat(),
        "recent_window": f"{recent_start}..{recent_end}",
        "opra_cache_last": str(cache_last),
        "confirm_n_floor": args.floor,
        "lookback_trading_days": args.lookback,
        "event_cluster_gap_minutes": EVENT_CLUSTER_GAP_MINUTES,
        "never_blocks_never_kills": True,
        # MERGE, never replace (2026-08-23 truncation-bug fix -- see merge_gate_results
        # docstring): a --gate <id> filtered run must update ONLY that gate's row, not wipe
        # every other gate this file has ever recorded.
        "gates": merge_gate_results(results, prior_gates),
        # GATE-EXPIRY-SOLE-BLOCKER-MINER (2026-09-03): filter-checklist refusal costing,
        # additive schema -- see the SOLE-BLOCKER MINER module section for the costing
        # definition (NOT_REPLAYED directional proxy, never a $ figure).
        "sole_blocker_miner": {
            "costing": "NOT_REPLAYED",
            "rolling_window_trading_days": args.sole_blocker_lookback,
            "rolling_window": f"{sb_start}..{sb_end}" if run_sole_blockers else None,
            "session": str(session_start) if run_sole_blockers else None,
            "cells_rolling_window": sole_blocker_report,
            "cells_last_session": sole_blocker_session_report,
            "top5_sole_blockers_by_door_rolling_window": sole_blocker_top5_20,
            "flagship_watches": list(SOLE_BLOCKER_FLAGSHIPS.keys()),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    flag_status_md(new_red)

    n_red = sum(1 for r in results.values() if r["overall"] == "RED")
    n_naive_red = sum(1 for r in results.values() if r["overall"] == "NAIVE_RED_CONCENTRATED")
    n_stale = sum(1 for r in results.values() if r["overall"] == "STALE_UNVERIFIED")
    print(f"\n[gate-expiry] wrote {OUT_JSON}", flush=True)
    print(f"[gate-expiry] {n_red} gate(s) RED (costing money), {n_naive_red} NAIVE_RED_CONCENTRATED "
          f"(naive-RED, battery required -- NOT actionable), {n_stale} STALE_UNVERIFIED, "
          f"{len(new_red)} newly-RED this run", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
