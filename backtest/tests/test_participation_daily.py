"""Guards for setup/scripts/participation_daily.py -- the GOAL-LAYER daily instrument
(root-cause audit 2026-07-15 SS9: ~36 monitoring instruments existed, zero measured goal
attainment). Mirrors test_participation_cascade.py's real-fixture philosophy: the
TestComputeDailyOnRealTape class below reuses the SAME committed fixtures
(backtest/tests/fixtures/participation-cascade-2026-07-0{9,10}/) rather than synthetic rows,
so the two modules are proven to agree on the same real tape, not just on hand-built data.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_participation_daily.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIX = Path(HERE) / "fixtures"


def _load(name: str, relpath: str):
    path = os.path.join(ROOT, *relpath.split("/"), f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pdaily = _load("participation_daily", "setup/scripts")
pc = _load("participation_cascade", "backtest/tools")


def _event(arm, stage, category="gate", blocker=None):
    """Minimal synthetic event matching compute_cascade_day's per-event shape --
    only the 4 keys account_stats() actually reads."""
    return {"arm": arm, "stage": stage, "category": category, "blocker": blocker}


# ---------------------------------------------------------------------------
# account_verdict -- the 4-way GREEN/YELLOW/RED/IDLE classifier
# ---------------------------------------------------------------------------

class TestAccountVerdict:
    def test_idle_when_nothing_scored(self):
        assert pdaily.account_verdict(fills=0, enter_verdicts=0, target_min=2) == "IDLE"

    def test_red_needs_both_zero_fills_and_five_plus_enter_verdicts(self):
        assert pdaily.account_verdict(fills=0, enter_verdicts=5, target_min=2) == "RED"
        assert pdaily.account_verdict(fills=0, enter_verdicts=4, target_min=2) == "YELLOW", (
            "4 enter_verdicts is below the RED floor -- must fall to YELLOW, not RED")

    def test_yellow_when_fills_short_of_target_but_nonzero(self):
        assert pdaily.account_verdict(fills=1, enter_verdicts=8, target_min=2) == "YELLOW"

    def test_green_when_target_met_or_beaten(self):
        assert pdaily.account_verdict(fills=2, enter_verdicts=8, target_min=2) == "GREEN"
        assert pdaily.account_verdict(fills=5, enter_verdicts=8, target_min=2) == "GREEN"

    def test_a_single_fill_is_never_red_even_with_many_enter_verdicts(self):
        """RED strictly requires ZERO fills -- one real fill always outranks the
        enter-verdict count, no matter how large."""
        assert pdaily.account_verdict(fills=1, enter_verdicts=50, target_min=2) == "YELLOW"


class TestRollupVerdict:
    def test_worst_wins(self):
        assert pdaily.rollup_verdict(["GREEN", "RED"]) == "RED"
        assert pdaily.rollup_verdict(["GREEN", "YELLOW"]) == "YELLOW"
        assert pdaily.rollup_verdict(["GREEN", "IDLE"]) == "IDLE", (
            "IDLE outranks GREEN -- a same-day split where one account traded normally and "
            "the other scored ZERO signals all day is itself worth a glance (real precedent "
            "in this repo: Bold's afternoon strike-floor collision), so 'no data' must not "
            "read as friendlier than a confirmed success elsewhere masking a real gap")
        assert pdaily.rollup_verdict(["IDLE", "YELLOW"]) == "YELLOW", (
            "YELLOW (a CONFIRMED shortfall) still outranks IDLE (merely ambiguous/no-data)")

    def test_all_idle_rolls_up_idle(self):
        assert pdaily.rollup_verdict(["IDLE", "IDLE"]) == "IDLE"

    def test_empty_list_is_idle(self):
        assert pdaily.rollup_verdict([]) == "IDLE"


# ---------------------------------------------------------------------------
# account_stats -- buckets one arm's events out of a mixed multi-arm list
# ---------------------------------------------------------------------------

class TestAccountStats:
    def test_buckets_by_arm_and_stage(self):
        cascade_day = {"events": [
            _event("safe-2", "PLACED", category="success"),
            _event("safe-2", "FILLED", category="success"),
            _event("safe-2", "RISK_GATE_DENY", category="risk_gate", blocker="min_premium_floor"),
            _event("safe-2", "RISK_GATE_DENY", category="risk_gate", blocker="min_premium_floor"),
            _event("safe-2", "GATE_BLOCK", category="gate", blocker="block_elite_bull"),
            _event("safe-2", "NO_SIGNAL", category="none"),
            _event("bold-2", "FILLED", category="success"),   # different arm -- must not leak in
        ]}
        stats = pdaily.account_stats(cascade_day, "safe-2")
        # enter_verdicts = PLACED + FILLED + RISK_GATE_DENY(x2) = 4
        assert stats["enter_verdicts"] == 4
        # attempts = PLACED + FILLED = 2
        assert stats["attempts"] == 2
        assert stats["fills"] == 1
        assert stats["top_no_order_sinks"][0] == {
            "blocker": "min_premium_floor", "category": "risk_gate", "n_events": 2}

    def test_other_arms_events_never_leak_into_the_count(self):
        cascade_day = {"events": [_event("bold-2", "FILLED"), _event("risky-1", "FILLED")]}
        stats = pdaily.account_stats(cascade_day, "safe-2")
        assert stats == {"enter_verdicts": 0, "attempts": 0, "fills": 0, "top_no_order_sinks": []}

    def test_no_order_sinks_exclude_no_data_and_no_signal(self):
        """NO_DATA/NO_SIGNAL are pre-scoring noise, not 'blocked' candidates -- must never
        appear in the no-order-sink leaderboard (mirrors participation_cascade's own
        passed_scoring exclusion)."""
        cascade_day = {"events": [
            _event("safe-2", "NO_DATA", category="none"),
            _event("safe-2", "NO_SIGNAL", category="none"),
        ]}
        stats = pdaily.account_stats(cascade_day, "safe-2")
        assert stats["top_no_order_sinks"] == []


# ---------------------------------------------------------------------------
# account_target -- params-overridable, default 2/4
# ---------------------------------------------------------------------------

class TestAccountTarget:
    def test_default_when_no_override_present(self, tmp_path, monkeypatch):
        empty = tmp_path / "params.json"
        empty.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(pdaily, "SAFE_PARAMS", empty)
        assert pdaily.account_target("safe") == (2, 4)

    def test_reads_override_when_present(self, tmp_path, monkeypatch):
        custom = tmp_path / "aggressive_params.json"
        custom.write_text(json.dumps({"participation_target_fills_min": 3, "participation_target_fills_max": 6}),
                           encoding="utf-8")
        monkeypatch.setattr(pdaily, "BOLD_PARAMS", custom)
        assert pdaily.account_target("bold") == (3, 6)

    def test_missing_params_file_fails_open_to_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pdaily, "SAFE_PARAMS", tmp_path / "does-not-exist.json")
        assert pdaily.account_target("safe") == (2, 4)


# ---------------------------------------------------------------------------
# end-to-end on the SAME real 2026-07-09 / 2026-07-10 fixtures
# test_participation_cascade.py pins against.
# ---------------------------------------------------------------------------

class TestComputeDailyOnRealTape:
    def _cascade_day(self, day: str) -> dict:
        d = FIX / f"participation-cascade-{day}"
        return pc.compute_cascade_day(day, core_glob_dir=d, fleet_dir=d / "fleet", data_dir=d)

    def test_2026_07_09_both_core_accounts_idle(self):
        """Real finding, pinned: even on 07-09 ('the engine participated' day per
        test_participation_cascade.py -- 10 real orders), ALL 10 landed on the 4 FLEET
        research arms; safe-2/bold-2 (the 2 accounts J actually holds, per CLAUDE.md's
        account-context table) scored zero ENTER-adjacent events that day. A future
        regression that quietly blurs fleet participation back into 'the engine is
        fine' will fail this test."""
        daily = pdaily.compute_daily(self._cascade_day("2026-07-09"))
        assert daily["accounts"]["safe"]["verdict"] == "IDLE"
        assert daily["accounts"]["bold"]["verdict"] == "IDLE"
        assert daily["accounts"]["safe"]["fills"] == 0
        assert daily["accounts"]["bold"]["fills"] == 0
        assert daily["verdict"] == "IDLE"

    def test_2026_07_10_both_core_accounts_yellow(self):
        """The PARTICIPATION_HOLE day (31 passed-scoring events, 0 orders, cascade
        verdict=PARTICIPATION_HOLE). Core accounts individually stay below the RED floor
        (safe=1, bold=2 enter_verdicts, both <5) so the correct read is YELLOW (missed
        target) not RED (a confirmed hole) -- pinned exact counts."""
        daily = pdaily.compute_daily(self._cascade_day("2026-07-10"))
        assert daily["accounts"]["safe"]["fills"] == 0
        assert daily["accounts"]["safe"]["enter_verdicts"] == 1
        assert daily["accounts"]["safe"]["verdict"] == "YELLOW"
        assert daily["accounts"]["bold"]["fills"] == 0
        assert daily["accounts"]["bold"]["enter_verdicts"] == 2
        assert daily["accounts"]["bold"]["verdict"] == "YELLOW"
        assert daily["verdict"] == "YELLOW"
        assert daily["cascade"]["cascade_verdict"] == "PARTICIPATION_HOLE"

    def test_render_line_is_one_line_and_names_both_accounts(self):
        daily = pdaily.compute_daily(self._cascade_day("2026-07-10"))
        line = pdaily.render_line(daily)
        assert "\n" not in line
        assert "safe=" in line and "bold=" in line
        assert "YELLOW" in line


# ---------------------------------------------------------------------------
# extra_exec lane fill flows through to the goal-layer instrument (2026-08-04)
# ---------------------------------------------------------------------------

class TestExtraExecFillFlowsThroughToParticipationDaily:
    """Closes the participation-daily leg of the 2026-08-03 safe/bollinger_squeeze incident:
    proves participation_cascade.build_events's new extra_exec event (see
    test_participation_cascade.py::TestExtraExecEvents) flows all the way through to this
    module's account_stats() output, not just to the underlying cascade module. Built via the
    REAL build_events() call (not a hand-fabricated event dict) on the real 08-03 fixture rows.

    This is ALSO the fix for self_check.py's check_participation_daily: that function is a
    PURE READER of automation/state/participation-daily.json with no independent
    core-decisions.jsonl parsing of its own (confirmed by reading setup/scripts/self_check.py
    -- it only loads the JSON artifact this module writes). Once compute_daily/account_stats
    here report the fill correctly, check_participation_daily inherits the fix for free --
    no code change there, and test_self_check_participation_daily.py's existing suite
    (synthetic participation-daily.json fixtures, unrelated to core-decisions.jsonl shape)
    needs no new test to prove it."""

    _PRIMARY_ROW = {
        "ts_et": "2026-08-03T13:21:03", "account": "safe", "armed": True,
        "verdict": "SKIP_ELITE_BULL_LEVEL_RECLAIM", "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM",
        "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "reason": "blocked by entry gate block_elite_bull",
        "extra_exec": [
            {"setup": "bollinger_squeeze", "action": "PLACED",
             "exec": {"status": "PLACED", "symbol": "SPY260803C00757000", "side": "C",
                       "strike": 757, "qty": 3, "premium": 0.55}},
        ],
    }
    _EXIT_PASS_ROW = {
        "ts_et": "2026-08-03T13:22:04", "account": "safe", "armed": True, "verdict": "HOLD",
        "reason": "no setup passed scoring (neither bear nor bull)",
        "exit_pass": [{"symbol": "SPY260803C00757000", "open_qty": 3}],
    }

    def test_safe_account_fills_go_from_zero_to_one(self):
        events = pc.build_events([self._PRIMARY_ROW, self._EXIT_PASS_ROW], "safe-2", "core")
        cascade_day = {"date": "2026-08-03", "events": events}
        stats = pdaily.account_stats(cascade_day, "safe-2")
        assert stats["fills"] == 1, (
            f"pre-fix this was 0 -- the real extra_exec fill was invisible to build_events: {events}")
        assert stats["enter_verdicts"] >= 1

    def test_red_proof_pre_fix_shape_would_have_shown_zero_fills(self):
        """RED-PROOF: strip the extra_exec-derived event out (simulating pre-fix
        build_events output, which never emitted it) and confirm fills reverts to 0 -- proves
        the assertion above genuinely exercises the fix rather than being a tautology."""
        events = pc.build_events([self._PRIMARY_ROW, self._EXIT_PASS_ROW], "safe-2", "core")
        pre_fix_events = [e for e in events if e.get("setup") != "bollinger_squeeze"]
        cascade_day = {"date": "2026-08-03", "events": pre_fix_events}
        stats = pdaily.account_stats(cascade_day, "safe-2")
        assert stats["fills"] == 0


# ---------------------------------------------------------------------------
# discord alert de-dup
# ---------------------------------------------------------------------------

class TestDiscordAlert:
    def test_green_never_alerts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pdaily, "DISCORD_OUTBOX", tmp_path / "outbox.jsonl")
        monkeypatch.setattr(pdaily, "LAST_ALERT_F", tmp_path / "last-alert.json")
        daily = {"date": "2026-07-09", "verdict": "GREEN", "generated_at_et": "2026-07-09T16:10:00",
                 "accounts": {}, "cascade": {"n_passed_scoring_events": 0, "n_orders": 0,
                 "joint_participation_pct": None, "spy_range_pct": None, "cascade_verdict": "IDLE"}}
        assert pdaily.maybe_alert_discord(daily) is False
        assert not (tmp_path / "outbox.jsonl").exists()

    def test_yellow_alerts_once_then_dedupes_same_day_same_verdict(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.jsonl"
        monkeypatch.setattr(pdaily, "DISCORD_OUTBOX", outbox)
        monkeypatch.setattr(pdaily, "LAST_ALERT_F", tmp_path / "last-alert.json")
        daily = {"date": "2026-07-15", "verdict": "YELLOW", "generated_at_et": "2026-07-15T16:10:00",
                 "accounts": {"safe": {"arm": "safe-2", "target_min": 2, "target_max": 4, "verdict": "YELLOW",
                                        "enter_verdicts": 5, "attempts": 1, "fills": 1, "top_no_order_sinks": []}},
                 "cascade": {"n_passed_scoring_events": 5, "n_orders": 1, "joint_participation_pct": 20.0,
                             "spy_range_pct": 0.5, "cascade_verdict": "LOW_PARTICIPATION"}}
        assert pdaily.maybe_alert_discord(daily) is True
        assert outbox.exists()
        lines_after_first = outbox.read_text(encoding="utf-8").splitlines()
        assert len(lines_after_first) == 1
        row = json.loads(lines_after_first[0])
        assert row["source"] == "participation_daily"
        assert row["channel"] == "gamma-ops"
        assert "YELLOW" in row["message"]
        # same verdict, same day -- re-run must NOT double-alert
        assert pdaily.maybe_alert_discord(daily) is False
        assert len(outbox.read_text(encoding="utf-8").splitlines()) == 1

    def test_verdict_change_same_day_alerts_again(self, tmp_path, monkeypatch):
        outbox = tmp_path / "outbox.jsonl"
        monkeypatch.setattr(pdaily, "DISCORD_OUTBOX", outbox)
        monkeypatch.setattr(pdaily, "LAST_ALERT_F", tmp_path / "last-alert.json")
        base = {"date": "2026-07-15", "generated_at_et": "2026-07-15T16:10:00", "accounts": {},
                "cascade": {"n_passed_scoring_events": 0, "n_orders": 0, "joint_participation_pct": None,
                            "spy_range_pct": None, "cascade_verdict": "IDLE"}}
        assert pdaily.maybe_alert_discord({**base, "verdict": "YELLOW"}) is True
        assert pdaily.maybe_alert_discord({**base, "verdict": "RED"}) is True
        assert len(outbox.read_text(encoding="utf-8").splitlines()) == 2
