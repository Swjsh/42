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

REGISTRY = ROOT / "automation" / "state" / "gate-registry.json"
OUT_JSON = ROOT / "automation" / "state" / "gate-registry-status.json"
STATUS_MD = ROOT / "automation" / "overnight" / "STATUS.md"
CORE_DECISIONS = ROOT / "automation" / "state" / "core-decisions.jsonl"

# sim convention shared with recency_check.py / the harnesses (NEG=ITM, POS=OTM offset; 0=ATM)
PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4
STRIKE_OFFSET_ATM = 0

# consecutive same-gate fires within this many minutes are ONE tradeable event, not N.
EVENT_CLUSTER_GAP_MINUTES = 15

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
    recency_check.verdict_for's shape, INVERTED semantics (see module docstring)."""
    n = m.get("n", 0)
    if n == 0:
        return "INSUFFICIENT_DATA", "no refused signals survived mining in the recent window"
    exp = m.get("exp_per_trade")
    if exp is not None and exp > 0:
        if n >= floor:
            return "RED", f"refused cohort would have EARNED ${exp}/tr, n={n} >= floor {floor} -- COSTING money"
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate-expiry instrument: nightly recency check for every armed entry gate/veto")
    ap.add_argument("--lookback", type=int, default=RECENCY_LOOKBACK_TRADING_DAYS)
    ap.add_argument("--floor", type=int, default=CONFIRM_N_FLOOR)
    ap.add_argument("--gate", type=str, default=None, help="only check this gate id (debug)")
    args = ap.parse_args()

    registry = load_registry()
    gates = registry["gates"]
    if args.gate:
        gates = [g for g in gates if g["id"] == args.gate]
        if not gates:
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
        "gates": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    flag_status_md(new_red)

    n_red = sum(1 for r in results.values() if r["overall"] == "RED")
    n_stale = sum(1 for r in results.values() if r["overall"] == "STALE_UNVERIFIED")
    print(f"\n[gate-expiry] wrote {OUT_JSON}", flush=True)
    print(f"[gate-expiry] {n_red} gate(s) RED (costing money), {n_stale} STALE_UNVERIFIED, "
          f"{len(new_red)} newly-RED this run", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
