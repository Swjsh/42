"""Guard: setup/scripts/dojo/engine_step.py -- "what does the engine see at this bar" (Agent A).

OP-33 FAITHFUL-REPLAY PARITY (same discipline as backtest/tools/replay_today_eval.py): proves
engine_step.step() on a REAL trading day (2026-07-17, the +$679 day named in the task) returns
decisions whose safe/bold bear_score/bull_score/verdict/side MATCH the actual
automation/state/core-decisions.jsonl rows for that day at the same bar -- read DIRECTLY off
the live ledger (not a copy-pasted snapshot), so this test can never silently drift from truth.

MEASURED RESULT (fresh run this session, full RTH sweep via the REAL dojo/clock.py cursor
resolution, both accounts, n=153 distinct trigger bars -- quoted, not estimated):
    bear_score exact match:  66/153 = 43.1%
    bull_score exact match:  77/153 = 50.3%
    verdict match (HOLD/ENTER_BEAR/ENTER_BULL/gate-SKIP_*): 133/153 = 86.9%
    side match (P/C/None):   135/153 = 88.2%
    At least one of the day's real ENTER_BEAR ground-truth bars reproduces as ENTER_BEAR/P
    here (see test_real_enter_bear_call_is_reproduced_2026_07_17) -- e.g. the 13:56:03 bar
    reproduces bear=10 EXACT on both accounts.

An EARLIER pass over this same data (ad hoc, not this file) suggested the first 90 minutes of
2026-07-17 might parity-match exactly -- FALSE, and the false claim traced to a truncated
`tail -100` on a longer mismatch dump that silently dropped the early-morning entries out of
view (a `fable-too-good` artifact, not a real finding: the tail showed only its last 100
lines, and the morning-window mismatches were among the ones cut). Corrected once this pytest
file ran the untruncated, real clock.py-driven sweep: the morning window is NOT materially
better than the full-day average. Recorded here so nobody re-derives the same false lead.

NOT a forced 100%, and no "clean window" is claimed. engine_step.py's own module docstring
discloses why the SCORE-level number is what it is: VIX is read from the real cached
backtest/data/vix_5m_*.csv (faithful), but levels_active/multi_day_levels are reconstructed
from the CURRENT automation/state/key-levels.json filtered to "knowable as of replay_day" (no
historical key-levels.json snapshot exists anywhere in this repo) -- a real, disclosed,
partial approximation, not a wiring bug. The much higher VERDICT/SIDE match rate (87-88%) is
the more load-bearing number for the dojo's actual purpose (does the whisper show J the same
HOLD/ENTER call the live engine made): a wrong level nudges a 0-10 score by a point or two far
more often than it flips the winning side or clears every gate. This test asserts on the
numbers actually measured (with a small honest margin, not reverse-fit to whatever came out),
same convention as replay_today_eval.py's FAITHFULNESS_ABS_DOLLARS / replay_heartbeat_core.py's
`score_ok = pct >= 0.95` -- except here the bar is calibrated to what a levels-approximated
historical replay against REAL LIVE data can actually achieve, not to what a same-day
(replay_today_eval) or ground-truth-fed (replay_heartbeat_core) harness can.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_engine_step.py -v
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "setup" / "scripts", ROOT):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import clock, engine_step  # noqa: E402

ET = ZoneInfo("America/New_York")
REPLAY_DAY = "2026-07-17"
CORE_DECISIONS_PATH = ROOT / "automation" / "state" / "core-decisions.jsonl"

# Calibrated to the measured full-day numbers above, with a small margin so the test isn't
# reverse-fit to the exact float this run produced but still regresses hard on a real break.
MIN_VERDICT_MATCH_RATE = 0.75
MIN_SIDE_MATCH_RATE = 0.75
MIN_BEAR_EXACT_RATE = 0.30
MIN_BULL_EXACT_RATE = 0.35


# ============================================================================ ground truth
def _load_ground_truth() -> dict[str, list[dict]]:
    """Every distinct (account, trigger-bar) decision recorded live for REPLAY_DAY, read
    straight off automation/state/core-decisions.jsonl. Consecutive ticks sharing the same
    `spy` value are the SAME 5-min trigger bar (the ribbon only advances once every 5 ticks) --
    collapsed to one row per distinct trigger, keeping the FIRST tick of each run (mirrors how
    replay_today_eval.py treats the ledger as ground truth: read verbatim, never re-derived).
    The first two groups of each account are a carried-over PRIOR-DAY trigger bar (the market
    open before the first bar of REPLAY_DAY has closed) -- excluded, since
    dojo/clock.py.latest_closed_5m_bar_et() returns None for a pre-09:35 cursor and
    session.py never calls step() for it (see clock.py's own docstring); a real dojo session
    structurally cannot reach this test point, so ground-truth rows for it aren't in scope."""
    if not CORE_DECISIONS_PATH.exists():
        pytest.skip(f"{CORE_DECISIONS_PATH} not present in this environment")
    by_acct: dict[str, list[dict]] = collections.defaultdict(list)
    with CORE_DECISIONS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("ts_et", "").startswith(REPLAY_DAY) and row.get("account") in ("safe", "bold"):
                by_acct[row["account"]].append(row)

    groups: dict[str, list[dict]] = {}
    for acct, rows in by_acct.items():
        prev_spy = object()
        acct_groups = []
        for r in rows:
            if r.get("spy") != prev_spy:
                acct_groups.append(r)
                prev_spy = r.get("spy")
        groups[acct] = acct_groups[2:]  # drop the two prior-day carry-over groups
    return groups


def _bar_et_for(ts_et_str: str) -> "dt.datetime | None":
    """The dojo bar_et a session would have resolved for the cursor at this ledger row's own
    wall-clock tick -- via the REAL clock.latest_closed_5m_bar_et(), not a hand-rolled floor."""
    ts = dt.datetime.strptime(ts_et_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ET)
    return clock.latest_closed_5m_bar_et(ts)


@pytest.fixture(scope="module")
def ground_truth() -> dict[str, list[dict]]:
    gt = _load_ground_truth()
    if not gt.get("safe") and not gt.get("bold"):
        pytest.skip("no 2026-07-17 core-decisions.jsonl rows in this environment")
    return gt


@pytest.fixture(scope="module")
def day_bars() -> pd.DataFrame:
    return engine_step.load_day_bars(REPLAY_DAY)


@pytest.fixture(scope="module")
def full_sweep(ground_truth, day_bars) -> list[dict]:
    """ONE pass over every ground-truth trigger bar (both accounts), computed once and reused
    by every assertion below -- each call to step() is 2 real `python -m
    backtest.lib.engine.engine_cli` subprocess round-trips (safe + bold), so re-running this
    sweep per test would multiply an already-slow (~150-bar) real-subprocess walk."""
    rows = []
    for acct, groups in ground_truth.items():
        for g in groups:
            bar_et = _bar_et_for(g["ts_et"])
            if bar_et is None:
                continue  # pre-09:35 cursor -- clock.py says the engine is idle; not reachable
            decisions = engine_step.step(REPLAY_DAY, bar_et, day_bars)
            d = next(x for x in decisions if x.arm == acct)
            rows.append({
                "acct": acct, "ts_et": g["ts_et"], "bar_et": bar_et,
                "gt_bear": g.get("bear_score"), "my_bear": d.bear_score,
                "gt_bull": g.get("bull_score"), "my_bull": d.bull_score,
                "gt_verdict": g.get("verdict"), "my_verdict": d.verdict,
                "gt_side": g.get("side"), "my_side": d.side,
            })
    return rows


# ============================================================================ 1. shape / contract
def test_load_day_bars_covers_replay_day_with_tz_aware_timestamps(day_bars):
    assert list(day_bars.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert day_bars["timestamp"].dt.tz is not None
    on_day = day_bars[day_bars["timestamp"].dt.date == dt.date(2026, 7, 17)]
    assert len(on_day) >= 78, "expected the full RTH session's worth of bars on replay_day"
    assert on_day["timestamp"].max() <= pd.Timestamp(REPLAY_DAY + " 23:59:59", tz=ET)


def test_step_returns_one_decision_per_arm_five_total(day_bars):
    bar_et = dt.datetime(2026, 7, 17, 10, 0, tzinfo=ET)
    decisions = engine_step.step(REPLAY_DAY, bar_et, day_bars)
    arms = [d.arm for d in decisions]
    assert arms == ["safe", "bold", "fleet_safe_3", "fleet_risky_1", "fleet_risky_3"]


def test_dojo_decision_is_json_serializable_via_asdict(day_bars):
    """session.py's _append_ledger() calls json.dumps(row) on the raw dict -- any non-JSON-
    native field (a bare datetime, for instance) would crash every real session's ledger
    write. Guards that regression directly."""
    bar_et = dt.datetime(2026, 7, 17, 10, 0, tzinfo=ET)
    for d in engine_step.step(REPLAY_DAY, bar_et, day_bars):
        row = d._asdict()
        json.dumps(row)  # must not raise


def test_fleet_arms_are_wired_never_fabricated(day_bars):
    """DOJO-FLEET-HISTORICAL-SIGNAL (2026-07-20): the 3 fleet arms now run the REAL
    fleet_executor.plan_all/select_plan pass against a historical shared signal built from
    THIS bar's own safe/bold DojoDecisions (build_shared_signal.build_from_rows) -- no longer
    a permanent FLEET_VIEW_PENDING placeholder. Every arm resolves to a well-formed verdict
    (HOLD/ENTER_BEAR/ENTER_BULL, or FLEET_VIEW_PENDING only as the fail-safe fallback if the
    arm is missing/inactive in accounts.json or its pass raises) -- never a null/garbage verdict."""
    bar_et = dt.datetime(2026, 7, 17, 13, 0, tzinfo=ET)
    decisions = {d.arm: d for d in engine_step.step(REPLAY_DAY, bar_et, day_bars)}
    for arm in ("fleet_safe_3", "fleet_risky_1", "fleet_risky_3"):
        d = decisions[arm]
        assert d.verdict in ("HOLD", "ENTER_BEAR", "ENTER_BULL", "FLEET_VIEW_PENDING")
        if d.verdict in ("ENTER_BEAR", "ENTER_BULL"):
            assert d.would_place is True
            assert d.side in ("P", "C")
        else:
            assert d.would_place is False


def test_fleet_arms_reflect_their_own_gate_strictness(day_bars):
    """The fleet arms carry DIFFERENT gate_override strictness (safe-3/risky-1 =
    min_triggers=2+confluence-or-sequence) -- proves the wiring threads each arm's OWN
    accounts.json config through plan_all, not one shared default. Sampled at a handful of
    representative RTH times (not a full 5-min stride -- each bar already costs 2 engine_cli
    subprocess spawns via the real safe/bold decide path, and
    test_real_enter_bear_call_is_reproduced_2026_07_17 already exercises the full-day sweep
    elsewhere in this file), including 11:35/12:05 -- real risky-1 ENTER_BEAR bars, verified via
    a full-day sweep this session (`python -c` one-off, not committed) after risky-3's
    2026-08-28 retirement (accounts.json status->'retired') made the OLD sample
    (9:35/10:30/13:56/14:30/15:30) go permanently HOLD-only: those 5 bars only ever cleared
    risky-1's tight gate via risky-3's now-retired loose gate riding along, never on their own.
    risky-3 is DELIBERATELY EXCLUDED from the arm loop below -- _decide_for_fleet_arm's own
    status!='active' check (engine_step.py:447) means it now resolves FLEET_VIEW_PENDING FOREVER
    (present-status read, not point-in-time -- a disclosed limitation, not a bug this test
    should paper over) regardless of which historical day is replayed; asserting on it here
    would be asserting a permanent tautology, not wiring fidelity. See risky-3's own
    `retired_reason` field in accounts.json for the retirement rationale."""
    any_fleet_verdict_seen = False
    for h, m in ((9, 35), (10, 30), (11, 35), (12, 5), (13, 56), (14, 30), (15, 30)):
        bar_et = dt.datetime(2026, 7, 17, h, m, tzinfo=ET)
        decisions = {d.arm: d for d in engine_step.step(REPLAY_DAY, bar_et, day_bars)}
        for arm in ("fleet_safe_3", "fleet_risky_1"):
            if decisions[arm].verdict in ("ENTER_BEAR", "ENTER_BULL"):
                any_fleet_verdict_seen = True
    assert any_fleet_verdict_seen, (
        "expected at least one active fleet-arm (safe-3/risky-1) ENTER across the sampled "
        "2026-07-17 RTH bars -- if this ever goes False, the wiring likely regressed to a "
        "permanently-inert HOLD"
    )


def test_step_rejects_naive_bar_et(day_bars):
    with pytest.raises(ValueError):
        engine_step.step(REPLAY_DAY, dt.datetime(2026, 7, 17, 10, 0), day_bars)


# ============================================================================ 2. no-broker fence
def test_engine_step_imports_no_broker_module():
    """Companion to test_dojo_fence.py / test_dojo_no_broker.py, scoped to this file (those
    scan dojo/*.py generally + sim_executor/scorecard specifically; this pins engine_step.py
    by name so a future refactor can't quietly reintroduce a broker import here)."""
    import ast
    import re
    src = (ROOT / "setup" / "scripts" / "dojo" / "engine_step.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    broker_re = re.compile(r"alpaca|broker|place_order|place_option_order", re.IGNORECASE)
    hits = {n for n in names if broker_re.search(n)}
    assert not hits, f"engine_step.py statically imports broker/alpaca module(s): {hits}"


# ============================================================================ 3. faithful-replay parity
def test_full_day_verdict_and_side_parity_2026_07_17(full_sweep):
    n = len(full_sweep)
    verdict_match = sum(1 for r in full_sweep if r["my_verdict"] == r["gt_verdict"])
    side_match = sum(1 for r in full_sweep if r["my_side"] == r["gt_side"])
    verdict_rate = verdict_match / n
    side_rate = side_match / n
    print(f"\n[dojo parity] verdict match {verdict_match}/{n} = {verdict_rate:.1%}")
    print(f"[dojo parity] side match    {side_match}/{n} = {side_rate:.1%}")
    assert verdict_rate >= MIN_VERDICT_MATCH_RATE, (
        f"verdict match rate {verdict_rate:.1%} fell below the {MIN_VERDICT_MATCH_RATE:.0%} "
        f"floor (measured {verdict_match}/{n})"
    )
    assert side_rate >= MIN_SIDE_MATCH_RATE, (
        f"side match rate {side_rate:.1%} fell below the {MIN_SIDE_MATCH_RATE:.0%} floor "
        f"(measured {side_match}/{n})"
    )


def test_full_day_score_parity_disclosed_2026_07_17(full_sweep):
    """NOT a 95%+ gate -- see module docstring. This asserts the DISCLOSED, measured floor so
    a real regression (the levels/VIX injection silently breaking further) still fails loud,
    without pretending the known approximation gap doesn't exist."""
    n = len(full_sweep)
    bear_exact = sum(1 for r in full_sweep if r["my_bear"] == r["gt_bear"])
    bull_exact = sum(1 for r in full_sweep if r["my_bull"] == r["gt_bull"])
    bear_rate = bear_exact / n
    bull_rate = bull_exact / n
    print(f"\n[dojo parity] bear_score exact {bear_exact}/{n} = {bear_rate:.1%}")
    print(f"[dojo parity] bull_score exact {bull_exact}/{n} = {bull_rate:.1%}")
    assert bear_rate >= MIN_BEAR_EXACT_RATE, (
        f"bear_score exact-match rate {bear_rate:.1%} fell below the disclosed "
        f"{MIN_BEAR_EXACT_RATE:.0%} floor (measured {bear_exact}/{n})"
    )
    assert bull_rate >= MIN_BULL_EXACT_RATE, (
        f"bull_score exact-match rate {bull_rate:.1%} fell below the disclosed "
        f"{MIN_BULL_EXACT_RATE:.0%} floor (measured {bull_exact}/{n})"
    )


def test_real_enter_bear_call_is_reproduced_2026_07_17(full_sweep):
    """At least the LOUDEST signal in the ground truth (a real ENTER_BEAR the live engine
    fired on) must reproduce as ENTER_BEAR/P here too -- a sanity floor independent of the
    aggregate rates above."""
    enters = [r for r in full_sweep if r["gt_verdict"] == "ENTER_BEAR"]
    assert enters, "expected at least one real ENTER_BEAR in 2026-07-17 ground truth"
    reproduced = [r for r in enters if r["my_verdict"] == "ENTER_BEAR" and r["my_side"] == "P"]
    assert reproduced, f"reproduced NONE of {len(enters)} real ENTER_BEAR ground-truth bars"
