#!/usr/bin/env python
"""fleet_gate_leak_shadow.py -- the FLEET-GATE-LEAK nightly shadow (queue.md
FLEET-GATE-LEAK-SHADOW, MED, filed 2026-09-03 14:51 ET), the instrument the 2026-08-13
36-agent review asked for and `FLEET-STRATEGIES-BYPASS-SAFE-GATES` (closed 2026-09-03)
committed to building.

BACKGROUND. `automation/state/fleet/build_shared_signal.py`'s `sig["strategies"]`
(every fleet arm's ONLY entry-side signal, per `fleet_executor.plan_all`'s
`signal.get("strategies") is not None` branch, unconditionally taken since
`EMIT_STRATEGIES=True`) defaults to SAFE's own (bear, bull) block and substitutes
BOLD's block only when SAFE is gated (`action` starts with `SKIP_`) and BOLD's own
perception separately passes (`verdict in {ENTER_BULL, ENTER_BEAR}`). The mirror also
happens: when BOLD is gated and SAFE passes, fleet arms ride SAFE's undiluted default
signal. Two prior sessions (`veto-scope-safe-3.md`, `fleet-gates-ledger-binding-check.md`
+ its 3 skeptic passes, all under `analysis/deep-research/2026-09-03-money/`) proved the
mechanism and the raw tick-level rates, but a skeptic pass
(`verify-fleet-gates-ledger-binding-check-2.md`) proved the ORIGINAL "did the fleet arm
enter" definition (a fleet arm's OWN `decisions.jsonl` `action` field) is inflated
1.2x-4.7x by `fleet_live.py` re-logging the SAME persisting decision every ~1-3 min while
a signal condition holds, independent of whether an order ever filled. The corrected
definition -- and the one this module uses exclusively -- is a REAL closed round-trip
fill, FIFO-reconstructed from `automation/state/fills-ledger.jsonl` via
`automation/state/fleet/fills_fifo.mine_real_arm_fills` (the ONE such reconstructor in
this repo, C14 -- not re-derived here).

WHAT THIS BUILDS, PER RUN (idempotent, backfill-capable -- NOT forward-only like the
tp1_r50/trendline-tight-exit sibling shadows; the audit needs the 2026-08-06+ history to
be visible, not just fresh accrual)
-------------------------------------------------------------------------------------
For every `core_tick_id` since `WINDOW_START_DATE` (2026-08-06, the date this repo's own
prior audits used) where BOTH `account=safe` and `account=bold` rows exist in
`automation/state/core-decisions.jsonl`:

  BYPASS (refused_account="safe"):  safe.action startswith "SKIP_" AND
                                     bold.verdict in {ENTER_BULL, ENTER_BEAR}
  BYPASS (refused_account="bold"),
  the MIRROR direction:             bold.action startswith "SKIP_" AND
                                     safe.verdict in {ENTER_BULL, ENTER_BEAR}
  CONTROL (both passed):            safe.verdict == bold.verdict, both in
                                     {ENTER_BULL, ENTER_BEAR} -- the arm's own entry (if
                                     any) would have happened whichever perception it read

For each of these "events" and each fleet arm (`ARMS` below), this module asks: did a
REAL fill land inside the entry window that follows this exact tick? "Real" = a CLOSED
FIFO round trip from `fills_fifo.mine_real_arm_fills(arm)` whose `entry_ts_et` falls in
[core_tick_id, core_tick_id + ENTRY_WINDOW_SEC] AND whose option side (C/P) matches the
event's direction (BULL->C, BEAR->P).

ENTRY WINDOW = 300s, STATED AND JUSTIFIED, not guessed:
  - `setup/scripts/fill_latency.py`'s own docstring (line ~134-135): the fleet_rest arms
    (safe-3/risky-1/risky-3/safe-1, all of them) run their OWN read of
    `shared-signal.json` on "their 3-min read cadence vs core's 1-min write cadence" --
    so a fleet arm can act on a given core tick up to ~3 minutes after it was written.
  - `automation/state/fleet/fleet_live.py:283-284`'s `ENTRY_CLAIM_TTL_SEC` comment:
    "real fills resolve in ~0.1-0.2s (measured)" once an order is actually submitted --
    broker latency is negligible next to the read-cadence gap.
  - 300s therefore covers one full fleet read cycle (up to 180s) plus broker latency with
    a ~1.7x margin, and this EXACT window was already independently validated for this
    EXACT join by this session's own skeptic pass
    (`analysis/deep-research/2026-09-03-money/verify-fleet-gates-ledger-binding-check-2.md`:
    "widening the match window to 600s (checked, counts unchanged... window-independent)").
  - Matching mirrors `backtest/tools/fleetgates_realfill_correction.py`'s
    `MATCH_WINDOW_S=300` / order_id-existence-only check, EXTENDED here with option-side
    (C/P) direction filtering and a single-claim dedup (below) so a per-(tick,arm) row can
    be emitted, not just an aggregate count.

DEDUP -- "one real fill counts once" (the exact bug the skeptic pass caught):
  A single real round trip can satisfy more than one nearby qualifying tick (e.g. a 3-tick
  SKIP_CONF_LVL_REC_AFTERNOON streak with one real fill inside it). `assign_real_fills`
  processes all qualifying events for an arm in ONE chronologically-sorted pass and lets
  each round trip be CLAIMED by the EARLIEST unclaimed qualifying event whose window
  contains it and whose side matches -- once claimed, no later event can also claim it.
  This is also the NO-LOOK-AHEAD guarantee: a round trip can only be claimed by an event
  whose own tick_dt is <= the round trip's entry_ts_et (never the reverse), so the gate
  label a row carries always comes from the SAME tick that (if real_fill=True) precedes
  its fill, never a later or earlier one.

  The claim pool is PER ARM, ACROSS ALL EVENTS (every gate + the control cohort together),
  not per-gate-independent. Verified this build (2026-09-03) against
  `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`/risky-1: an isolated per-gate claim pool gives 8
  real entries (matching the prior session's ad hoc `fleetgates_realfill_correction.py`,
  which never shared a claim pool ACROSS gates/tables at all); the shared, per-arm pool
  used here gives 7 -- one real fill's `entry_ts_et` (2026-08-12T13:48:07) falls inside
  BOTH a `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY` bypass tick's window (13:47:03) AND an
  earlier CONTROL tick's window (13:46:02, both accounts already agreed to enter). The
  earlier control tick claims it -- correctly: the trade is better explained by "both
  perceptions had already agreed one minute earlier" than by the LATER re-classification
  as a bypass, and crediting it to both would double-count one real dollar amount across
  two different summary cells. Any per-gate cell in this module's output can therefore be
  a small amount LOWER than a naive per-gate-isolated recount -- this is deliberate, not a
  bug; a fill is never allowed to count as evidence for more than one cohort/gate.

ARMS = safe-3, risky-1, risky-3, safe-1 -- named directly in this queue item's own
mechanism description. risky-3 retired 2026-08-28 and safe-1 retired 2026-07-11 (before
`core_tick_id` existed at all, 2026-08-03) are BOTH included, not silently dropped --
their rows are simply expected to be zero/near-zero, and that absence is itself part of
the disclosed record, not an omission.

NO PLACEMENT, NO FLIP. Read-only over three already-written artifacts
(core-decisions.jsonl, fills-ledger.jsonl, and per-arm nothing else) -- never touches
`accounts.json`, `strategies.py`, `build_shared_signal.py`, or any trading-path file.
The decision this shadow feeds (`prereg-fleet-gate-inheritance-2026-09-03.md`) is a
2026-10-30 config-freeze-window question, not something this module can or does ship.

COST: $0. Pure Python stdlib, no network, no OPRA, no LLM. Runs nightly at 17:20 ET
(`Gamma_FleetGateLeakShadow`), 5 min behind `Gamma_ConvictionC4Sidecar`.

Outputs:
  analysis/recommendations/fleet-gate-leak-ledger.jsonl   append-only, dedup on
                                                            (core_tick_id, arm, cohort,
                                                            refused_account)
  analysis/recommendations/fleet-gate-leak-summary.json   gate x arm tables, control
                                                            cohort, VIX bands, named-day
                                                            + September breakdowns, the
                                                            forward bar this instrument's
                                                            own prereg freezes
"""
from __future__ import annotations

import collections
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "automation" / "state" / "fleet"), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fills_fifo  # noqa: E402  -- automation/state/fleet/fills_fifo.py, C14 shared reconstructor

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
FILLS_LEDGER = fills_fifo.FILLS_LEDGER_PATH  # own module-level ref -- see run(): passed
                                              # EXPLICITLY to mine_real_arm_fills so tests
                                              # can monkeypatch it (its own default param
                                              # is bound at import time, immune to patching
                                              # fills_fifo.FILLS_LEDGER_PATH afterward)
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "fleet-gate-leak-ledger.jsonl"
SUMMARY = OUT_DIR / "fleet-gate-leak-summary.json"
PREREG_REL = "analysis/recommendations/prereg-fleet-gate-inheritance-2026-09-03.md"

WINDOW_START_DATE = "2026-08-06"      # matches the prior sessions' own audit window
IN_SAMPLE_CUTOFF = "2026-09-03"       # this build's own date -- rows on/before this are the
                                       # backfilled audit population; later rows are the
                                       # forward accrual the prereg's bar is measured on
FORWARD_START_DATE = "2026-09-04"     # the prereg's forward window opens the day after freeze
ENTRY_WINDOW_SEC = 300                # see module docstring for the full justification
FORWARD_BAR_SESSIONS = 20
FORWARD_BAR_ENTRIES = 20
DECISION_FOCUS_ARMS = ("safe-3", "safe-1")  # the hypothesis under test (safe-role arms)
NAMED_WINNING_DAYS = ("2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28")
SEPTEMBER_START = "2026-09-01"
ARMS = ("safe-3", "risky-1", "risky-3", "safe-1")
RETIRED_ARMS = {"risky-3": "2026-08-28", "safe-1": "2026-07-11"}
ENTER_VERDICTS = ("ENTER_BULL", "ENTER_BEAR")

# Confirmed mapping (verify-fleet-gates-ledger-binding-check-0.md/-1.md, cross-checked
# against both live params files this session's predecessors already read) -- gates NOT
# in this dict are reported by raw action name only, never guessed at a params.json key.
GATE_TO_PARAM_KEY = {
    "SKIP_STRUCTURE_VETO": "structure_veto_enabled",
    "SKIP_BULL_1100_1200": "block_bull_1100_1200",
    "SKIP_CONF_LVL_REC_AFTERNOON": "block_conf_lvl_rec_afternoon",
    "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY": "require_bearish_fill_bar",
}


# ------------------------------------------------------------------------------------------
# ledger I/O (torn-last-line tolerant, matching every sibling shadow ledger)
# ------------------------------------------------------------------------------------------
def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        except Exception:  # noqa: BLE001 -- a torn line must never kill the accrual
            continue
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _parse_iso(ts: "str | None") -> "datetime | None":
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------
# core-decisions.jsonl -> tick pairs -> classified events (pure, no I/O)
# ------------------------------------------------------------------------------------------
def build_core_tick_pairs(core_rows: list[dict], min_date: str) -> dict[str, dict]:
    """{core_tick_id: {"safe": row, "bold": row}} -- only ticks with BOTH accounts present,
    ts_et >= min_date (lexical ISO comparison, identical convention to
    `backtest/tools/fleetgates_realfill_correction.py::build_tables`)."""
    by_tick: dict[str, dict] = {}
    for r in core_rows:
        ts = r.get("ts_et") or ""
        if ts < min_date:
            continue
        ct = r.get("core_tick_id")
        acct = r.get("account")
        if ct is None or acct not in ("safe", "bold"):
            continue
        by_tick.setdefault(ct, {})[acct] = r
    return {ct: accts for ct, accts in by_tick.items() if "safe" in accts and "bold" in accts}


def _direction_of(verdict: "str | None") -> "str | None":
    if verdict == "ENTER_BULL":
        return "BULL"
    if verdict == "ENTER_BEAR":
        return "BEAR"
    return None


def classify_tick(core_tick_id: str, safe_row: dict, bold_row: dict) -> list[dict]:
    """PURE: one tick's (safe, bold) row pair -> 0-3 qualifying "events" (bypass-safe,
    bypass-bold-mirror, control). Each event carries everything downstream needs EXCEPT
    the real-fill match (added by `assign_real_fills`)."""
    tick_dt = _parse_iso(core_tick_id)
    if tick_dt is None:
        return []
    s_action = safe_row.get("action") or ""
    b_action = bold_row.get("action") or ""
    s_verdict = safe_row.get("verdict")
    b_verdict = bold_row.get("verdict")
    s_gated = s_action.startswith("SKIP_")
    b_gated = b_action.startswith("SKIP_")
    date_et = (safe_row.get("ts_et") or bold_row.get("ts_et") or "")[:10]
    vix = safe_row.get("vix")
    if vix is None:
        vix = bold_row.get("vix")

    base = {"core_tick_id": core_tick_id, "tick_dt": tick_dt, "date_et": date_et, "vix": vix}
    events: list[dict] = []

    b_dir = _direction_of(b_verdict)
    if s_gated and b_dir is not None:
        events.append({
            **base, "cohort": "bypass", "refused_account": "safe", "gate": s_action,
            "gate_param_key": GATE_TO_PARAM_KEY.get(s_action),
            "is_symmetric_gate": (s_action == b_action), "direction": b_dir,
        })

    s_dir = _direction_of(s_verdict)
    if b_gated and s_dir is not None:
        events.append({
            **base, "cohort": "bypass", "refused_account": "bold", "gate": b_action,
            "gate_param_key": GATE_TO_PARAM_KEY.get(b_action),
            "is_symmetric_gate": (s_action == b_action), "direction": s_dir,
        })

    if s_verdict == b_verdict and s_dir is not None:
        events.append({
            **base, "cohort": "control", "refused_account": None, "gate": None,
            "gate_param_key": None, "is_symmetric_gate": None, "direction": s_dir,
        })

    return events


# ------------------------------------------------------------------------------------------
# real-fill assignment -- the dedup + no-look-ahead core (pure, unit-tested directly)
# ------------------------------------------------------------------------------------------
_SIDE_OF_DIRECTION = {"BULL": "C", "BEAR": "P"}


def assign_real_fills(events: list[dict], round_trips: list[dict],
                       window_sec: int = ENTRY_WINDOW_SEC) -> list[dict]:
    """PURE. `events`: list of dicts each with `tick_dt` (datetime) and `direction`
    ("BULL"/"BEAR"). `round_trips`: `fills_fifo.mine_real_arm_fills`'s own output shape
    (`entry_ts_et`, `exit_ts_et`, `side`, `qty`, `real_pnl`). Returns a NEW list (events
    untouched) with `real_fill`/`entry_ts_et`/`exit_ts_et`/`real_pnl`/`qty` added.

    Each round trip is claimed by AT MOST ONE event: the chronologically-EARLIEST
    unclaimed event (sorted by `tick_dt`) whose window [tick_dt, tick_dt+window_sec]
    contains that round trip's `entry_ts_et` AND whose expected option side matches.
    NO LOOK-AHEAD: a round trip can only be claimed by an event whose tick_dt is <=
    the round trip's own entry_ts_et -- never the reverse."""
    parsed_trips = []
    for i, rt in enumerate(round_trips):
        edt = _parse_iso(rt.get("entry_ts_et"))
        if edt is not None:
            parsed_trips.append({"idx": i, "entry_dt": edt, "rt": rt})

    claimed: set = set()
    out: list[dict] = []
    for ev in sorted(events, key=lambda e: e["tick_dt"]):
        want_side = _SIDE_OF_DIRECTION.get(ev["direction"])
        window_end = ev["tick_dt"] + timedelta(seconds=window_sec)
        candidates = [
            p for p in parsed_trips
            if p["idx"] not in claimed
            and p["rt"].get("side") == want_side
            and ev["tick_dt"] <= p["entry_dt"] <= window_end
        ]
        row = dict(ev)
        if candidates:
            best = min(candidates, key=lambda p: p["entry_dt"])
            claimed.add(best["idx"])
            rt = best["rt"]
            row.update(real_fill=True, entry_ts_et=rt.get("entry_ts_et"),
                       exit_ts_et=rt.get("exit_ts_et"), real_pnl=rt.get("real_pnl"),
                       qty=rt.get("qty"))
        else:
            row.update(real_fill=False, entry_ts_et=None, exit_ts_et=None,
                       real_pnl=None, qty=None)
        out.append(row)
    return out


def finalize_row(arm: str, matched_event: dict, in_sample_cutoff: str = IN_SAMPLE_CUTOFF) -> dict:
    """PURE: matched event (has a python datetime `tick_dt`) -> JSON-safe ledger row."""
    return {
        "core_tick_id": matched_event["core_tick_id"],
        "date_et": matched_event["date_et"],
        "arm": arm,
        "cohort": matched_event["cohort"],
        "refused_account": matched_event["refused_account"],
        "gate": matched_event["gate"],
        "gate_param_key": matched_event["gate_param_key"],
        "is_symmetric_gate": matched_event["is_symmetric_gate"],
        "direction": matched_event["direction"],
        "vix": matched_event["vix"],
        "real_fill": matched_event["real_fill"],
        "entry_ts_et": matched_event["entry_ts_et"],
        "exit_ts_et": matched_event["exit_ts_et"],
        "real_pnl": matched_event["real_pnl"],
        "qty": matched_event["qty"],
        "in_sample": matched_event["date_et"] <= in_sample_cutoff,
    }


def _row_key(r: dict) -> tuple:
    return (r["core_tick_id"], r["arm"], r["cohort"], r.get("refused_account"))


# ------------------------------------------------------------------------------------------
# summary statistics (day-clustered bootstrap, matching go_live_gate.bootstrap_pf_ci /
# tp1_r50_forward_shadow._bootstrap_day_clustered_mean's own established methodology)
# ------------------------------------------------------------------------------------------
def _bootstrap_day_clustered_mean(rows: list[dict], n_boot: int = 2000,
                                   seed: int = 20260906) -> "dict | None":
    by_day: dict[str, list[float]] = collections.defaultdict(list)
    for r in rows:
        if r.get("real_pnl") is not None:
            by_day[r["date_et"]].append(r["real_pnl"])
    days = sorted(by_day)
    n_days = len(days)
    if n_days < 2:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample_days = [days[rng.randrange(n_days)] for _ in range(n_days)]
        vals = [v for d in sample_days for v in by_day[d]]
        if vals:
            means.append(sum(vals) / len(vals))
    if not means:
        return None
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    return {"n_boot": n_boot, "n_days_clustered": n_days,
            "ci_lower_2.5": round(lo, 4), "ci_upper_97.5": round(hi, 4)}


def _top3_concentration_share(rows: list[dict]) -> "float | None":
    deltas = [r["real_pnl"] for r in rows if r.get("real_pnl") is not None]
    if len(deltas) < 3:
        return None
    total_abs = sum(abs(d) for d in deltas)
    if total_abs <= 1e-9:
        return 0.0
    top3_abs = sum(sorted((abs(d) for d in deltas), reverse=True)[:3])
    return round(top3_abs / total_abs, 4)


def _pnl_stats(rows: list[dict]) -> dict:
    filled = [r for r in rows if r.get("real_fill")]
    vals = [r["real_pnl"] for r in filled if r.get("real_pnl") is not None]
    n = len(vals)
    if n == 0:
        return {"n": 0, "sum": 0.0, "mean": None, "ci": None, "top3_concentration_share": None}
    return {
        "n": n, "sum": round(sum(vals), 2), "mean": round(sum(vals) / n, 4),
        "ci": _bootstrap_day_clustered_mean(filled),
        "top3_concentration_share": _top3_concentration_share(filled),
    }


def _cell_stats(rows: list[dict]) -> dict:
    n_ticks = len(rows)
    n_real = sum(1 for r in rows if r.get("real_fill"))
    share = round(n_real / n_ticks, 4) if n_ticks else None
    return {"n_ticks": n_ticks, "n_real_entries": n_real, "share": share, "pnl": _pnl_stats(rows)}


def _vix_band(vix: "float | None") -> str:
    if vix is None:
        return "unknown"
    if vix < 15:
        return "<15"
    if vix < 18:
        return "15-18"
    if vix < 22:
        return "18-22"
    return ">=22"


def summarize(all_rows: list[dict], all_session_dates: list[str]) -> dict:
    n_ticks_joined = len({r["core_tick_id"] for r in all_rows})
    by_gate_arm: dict[tuple, list[dict]] = collections.defaultdict(list)
    control_by_arm: dict[str, list[dict]] = collections.defaultdict(list)
    for r in all_rows:
        if r["cohort"] == "bypass":
            by_gate_arm[(r["gate"], r["refused_account"], r["arm"])].append(r)
        elif r["cohort"] == "control":
            control_by_arm[r["arm"]].append(r)

    gate_arm_cells = []
    for (gate, refused_account, arm), rows in sorted(by_gate_arm.items(), key=lambda kv: kv[0]):
        cell = _cell_stats(rows)
        is_sym = rows[0].get("is_symmetric_gate")
        gate_arm_cells.append({
            "gate": gate, "gate_param_key": GATE_TO_PARAM_KEY.get(gate),
            "refused_account": refused_account, "arm": arm,
            "is_symmetric_gate_note": (
                "fires on BOTH accounts at these ticks -- shared session/time gate, NOT a "
                "safe/bold cohort divergence; do not read this cell as evidence of a leak"
                if is_sym else None),
            **cell,
        })

    control_cohort = [{"arm": arm, **_cell_stats(rows)}
                       for arm, rows in sorted(control_by_arm.items())]

    # VIX bands -- bypass cohort only, aggregated across gates per arm (n too thin per
    # gate x band cell to report separately)
    vix_bands: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in all_rows:
        if r["cohort"] == "bypass":
            vix_bands[(r["arm"], _vix_band(r.get("vix")))].append(r)
    vix_band_rows = [{"arm": arm, "band": band, **_cell_stats(rows)}
                      for (arm, band), rows in sorted(vix_bands.items())]

    # Named winning days + September window -- bypass vs control, per arm
    def _window_breakdown(rows_subset: list[dict]) -> dict:
        by_arm_bypass: dict[str, list[dict]] = collections.defaultdict(list)
        by_arm_control: dict[str, list[dict]] = collections.defaultdict(list)
        for r in rows_subset:
            if r["cohort"] == "bypass":
                by_arm_bypass[r["arm"]].append(r)
            elif r["cohort"] == "control":
                by_arm_control[r["arm"]].append(r)
        arms_seen = sorted(set(by_arm_bypass) | set(by_arm_control))
        return {arm: {"bypass": _cell_stats(by_arm_bypass.get(arm, [])),
                      "control": _cell_stats(by_arm_control.get(arm, []))}
                for arm in arms_seen}

    named_days = {d: _window_breakdown([r for r in all_rows if r["date_et"] == d])
                  for d in NAMED_WINNING_DAYS}
    september = _window_breakdown([r for r in all_rows if r["date_et"] >= SEPTEMBER_START])

    # Forward bar (the prereg's own frozen bar -- see PREREG_REL)
    n_forward_sessions = len([d for d in all_session_dates if d >= FORWARD_START_DATE])
    forward_by_arm = {}
    for arm in ARMS:
        n_forward_entries = sum(
            1 for r in all_rows
            if r["arm"] == arm and r["cohort"] == "bypass" and r.get("real_fill")
            and r["date_et"] >= FORWARD_START_DATE)
        bar_met = (n_forward_sessions >= FORWARD_BAR_SESSIONS
                   and n_forward_entries >= FORWARD_BAR_ENTRIES)
        entry: dict = {"n_forward_real_bypass_entries": n_forward_entries, "bar_met": bar_met}
        if arm in RETIRED_ARMS:
            entry["note"] = f"retired {RETIRED_ARMS[arm]} -- will not accrue new forward entries"
        forward_by_arm[arm] = entry

    focus_bar_met = any(forward_by_arm[a]["bar_met"] for a in DECISION_FOCUS_ARMS)
    forward_status = "BAR_MET_AWAITING_VERDICT" if focus_bar_met else "ACCRUING"

    return {
        "prereg": PREREG_REL,
        "generated_at_et": _stamp_now_et(),
        "window": {
            "start_date": WINDOW_START_DATE, "in_sample_cutoff": IN_SAMPLE_CUTOFF,
            "entry_window_sec": ENTRY_WINDOW_SEC,
            "entry_window_basis": (
                "fleet_rest arms read shared-signal.json on a ~3-min cadence vs core's "
                "1-min write cadence (fill_latency.py); real fills resolve in ~0.1-0.2s "
                "once submitted (fleet_live.py ENTRY_CLAIM_TTL_SEC comment). 300s = ~1.7x "
                "margin over one full fleet read cycle; independently validated for this "
                "exact join at 600s with no count change (verify-fleet-gates-ledger-"
                "binding-check-2.md)."),
        },
        "n_ticks_joined_since_start": n_ticks_joined,
        "gate_arm_cells": gate_arm_cells,
        "control_cohort_by_arm": control_cohort,
        "vix_bands_bypass_only": vix_band_rows,
        "named_winning_days": named_days,
        "september_window": {"start_date": SEPTEMBER_START, "by_arm": september},
        "forward_bar": {
            "start_date": FORWARD_START_DATE,
            "min_forward_sessions": FORWARD_BAR_SESSIONS,
            "min_real_bypass_entries": FORWARD_BAR_ENTRIES,
            "n_forward_sessions_elapsed": n_forward_sessions,
            "decision_focus_arms": list(DECISION_FOCUS_ARMS),
            "by_arm": forward_by_arm,
            "status": forward_status,
        },
        "status": forward_status,
        "decision_rule": (
            f"This ledger NEVER ships a trading-path change by itself. Once the forward "
            f"bar (>= {FORWARD_BAR_SESSIONS} forward sessions AND >= {FORWARD_BAR_ENTRIES} "
            f"real bypass entries) is met for a decision-focus arm, the FROZEN rule in "
            f"{PREREG_REL} applies -- reaching the bar is permission to READ the verdict, "
            "never to ship regardless of the read."),
    }


# ------------------------------------------------------------------------------------------
def run() -> dict:
    """Nightly entry point. Backfill-capable: recomputes the FULL window from the two raw
    artifacts every run (cheap at today's data volume -- ~1.2s over 38K core rows), so
    `all_finalized` is ALWAYS the complete, correctly-deduplicated row set for the summary
    -- it is NEVER `existing-on-disk PLUS freshly-recomputed` (that would double every row
    still present from a prior run, since recomputation reproduces the same rows). The
    on-disk ledger's `existing` content is read ONLY to decide which of the freshly
    recomputed rows are NEW (per `_row_key`) and therefore need appending -- it never
    feeds the summary directly. Fail-open by contract, own scheduled task."""
    try:
        core_rows = _read_jsonl(CORE_DECISIONS)
        pairs = build_core_tick_pairs(core_rows, WINDOW_START_DATE)
        all_session_dates = sorted({(r.get("ts_et") or "")[:10] for r in core_rows
                                     if (r.get("ts_et") or "") >= WINDOW_START_DATE})

        events_master: list[dict] = []
        for ct, accts in pairs.items():
            events_master.extend(classify_tick(ct, accts["safe"], accts["bold"]))

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing_keys = {_row_key(r) for r in _read_jsonl(LEDGER)}

        all_finalized: list[dict] = []
        new_rows: list[dict] = []
        for arm in ARMS:
            round_trips = fills_fifo.mine_real_arm_fills(arm, ledger_path=FILLS_LEDGER)
            matched = assign_real_fills(events_master, round_trips, ENTRY_WINDOW_SEC)
            for m in matched:
                row = finalize_row(arm, m)
                all_finalized.append(row)
                if _row_key(row) not in existing_keys:
                    new_rows.append(row)

        if new_rows:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in new_rows:
                    fh.write(json.dumps(r) + "\n")

        summary = summarize(all_finalized, all_session_dates)
        summary["new_this_run"] = len(new_rows)
        summary["n_rows_total"] = len(all_finalized)
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:400], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:3500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
