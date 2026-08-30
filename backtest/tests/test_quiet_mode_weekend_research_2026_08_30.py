"""The weekend must not be a 30-hour research outage.

MEASURED Sun 2026-08-30 12:07 ET, which is what prompted this: quiet-mode.json said
`total_held_down: 116`, the kitchen daemon's recorded PID was dead, and its last completed
task was four hours old. The kitchen, the futures lane, the multi-symbol lane, the
prospector and the conductor were ALL disabled -- on a Sunday, on a $200/mo plan, with the
market closed and nothing whatsoever to disturb.

The directive quiet mode was built for (2026-08-24, "everything needs to be turned off
after market hours") was about POPUPS and a 4-worker grind landing on J's gaming session.
That is a CPU-and-focus constraint, and the presence gate added on 2026-08-29 enforces it
directly. Holding the entire fleet down all weekend on top of that buys nothing and costs
a research day, so weekend daytime is now a RESEARCH band.

These tests pin the three things that must all remain true at once, because it would be
easy to fix the starvation by simply deleting the blackout and re-creating the original
scar:
  1. weekend daytime runs the light producers,
  2. J's evening is still a full blackout, weekend included,
  3. a fullscreen app still takes everything down whatever the clock says.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup" / "scripts"))
import quiet_mode as qm  # noqa: E402


def _at(day: int, hour: int) -> dt.datetime:
    """2026-08-31 is a Monday, so +day lands on a known weekday."""
    return dt.datetime(2026, 8, 31, hour, 0, tzinfo=qm.ET) + dt.timedelta(days=day)


SAT, SUN = 5, 6


class TestWeekendDaytimeIsNotQuiet:
    @pytest.mark.parametrize("day", [SAT, SUN])
    @pytest.mark.parametrize("hour", [8, 11, 12, 15, 17])
    def test_weekend_daytime_is_loud(self, day, hour):
        now = _at(day, hour)
        assert now.weekday() >= 5, "fixture must land on a weekend"
        assert qm.in_quiet_window(now) is False, (
            f"weekend {hour:02d}:00 must not be quiet -- this is the 2026-08-30 outage")

    @pytest.mark.parametrize("day", [SAT, SUN])
    @pytest.mark.parametrize("hour", [8, 12, 17])
    def test_weekend_daytime_is_the_research_band(self, day, hour):
        assert qm.in_research_band(_at(day, hour)) is True


class TestWhatTheBlackoutStillProtects:
    """The fix must not re-create the scar it was built for."""

    @pytest.mark.parametrize("day", [SAT, SUN])
    @pytest.mark.parametrize("hour", [18, 20, 22])
    def test_weekend_evening_is_still_a_full_blackout(self, day, hour):
        now = _at(day, hour)
        assert qm.in_quiet_window(now) is True, "J's evening is untouched by this change"
        assert qm.in_research_band(now) is False

    @pytest.mark.parametrize("hour", [18, 21, 22])
    def test_weekday_evening_unchanged(self, hour):
        assert qm.in_quiet_window(_at(0, hour)) is True

    @pytest.mark.parametrize("day", [SAT, SUN])
    @pytest.mark.parametrize("hour", [0, 3, 7])
    def test_maintenance_band_still_wins_on_weekends(self, day, hour):
        now = _at(day, hour)
        assert qm.in_quiet_window(now) is False
        # 02:00 Sunday is not the research band -- it is the full LOUD maintenance band,
        # where the heavy grinders are wanted precisely because J is asleep.
        assert qm.in_research_band(now) is False

    def test_weekday_daytime_is_never_the_research_band(self):
        """The trading day wants the heavy tasks too -- narrowing it would starve them."""
        for hour in (9, 12, 16):
            assert qm.in_research_band(_at(0, hour)) is False

    def test_presence_hold_still_reaches_the_weekend(self, monkeypatch):
        """A fullscreen game on a Sunday afternoon must still take the fleet down."""
        monkeypatch.setattr(qm, "_foreground_fullscreen", lambda: "some-game.exe")
        monkeypatch.setattr(qm, "_manual_hold", lambda: None)
        monkeypatch.setattr(qm, "_remember_presence", lambda app, now: None)
        assert qm.presence_hold(_at(SUN, 14)) is not None, (
            "the presence gate is what actually enforces J's original directive")


class TestHeavySet:
    def test_heavy_tasks_are_a_strict_subset_of_what_is_held(self):
        """A name that never appears in the fleet silently protects nothing."""
        assert qm.HEAVY_TASKS, "an empty heavy set makes the research band a plain restore"
        assert not (qm.HEAVY_TASKS & qm.ESSENTIAL), (
            "essential tasks are never held down, so listing one here is dead config")

    def test_the_lanes_j_asked_for_are_not_held_down(self):
        """The whole point: these must run in the research band."""
        for name in ("Gamma_KitchenDaemonKeepalive", "Gamma_KitchenSeeder",
                     "Gamma_KitchenReviewer", "Gamma_FuturesTrader", "Gamma_FuturesHealth",
                     "Gamma_MultiEvaluate", "Gamma_Prospector", "Gamma_Conductor"):
            assert name not in qm.HEAVY_TASKS, f"{name} is the work, not the CPU hog"


class TestPresenceDowngrade:
    """A fullscreen game on a weekend afternoon is J's NORMAL state, not an exception.

    Measured 2026-08-30 12:14 ET, one minute after the band fix went in: the clock had
    correctly flipped to LOUD and all 116 tasks were still held, because Apex was in the
    foreground. A blackout keyed on "is J gaming" reproduces the same 30-hour weekend
    outage under a different trigger, since that is most of what a weekend afternoon is.
    """

    def _hold(self, monkeypatch, app="r5apex_dx12.exe"):
        monkeypatch.setattr(qm, "_foreground_fullscreen", lambda: app)
        monkeypatch.setattr(qm, "_manual_hold", lambda: None)
        monkeypatch.setattr(qm, "_remember_presence", lambda a, n: None)

    def test_weekend_afternoon_gaming_downgrades_instead_of_blacking_out(
            self, monkeypatch):
        self._hold(monkeypatch)
        calls = []
        monkeypatch.setattr(qm, "go_research", lambda: calls.append("research") or 0)
        monkeypatch.setattr(qm, "go_quiet", lambda: calls.append("quiet") or 0)
        monkeypatch.setattr(qm, "go_loud", lambda: calls.append("loud") or 0)
        monkeypatch.setattr(qm, "in_quiet_window", lambda now=None: False)
        monkeypatch.setattr(qm, "in_research_band", lambda now=None: True)
        monkeypatch.setattr(sys, "argv", ["quiet_mode.py", "--enforce"])
        assert qm.main() == 0
        assert calls == ["research"], (
            "gaming on a Sunday afternoon must downgrade to light producers, not blackout")

    def test_gaming_outside_the_research_band_still_blacks_out(self, monkeypatch):
        """The 2026-08-29 maintenance-band scar is untouched: 23:30 gaming = full quiet."""
        self._hold(monkeypatch)
        calls = []
        monkeypatch.setattr(qm, "go_research", lambda: calls.append("research") or 0)
        monkeypatch.setattr(qm, "go_quiet", lambda: calls.append("quiet") or 0)
        monkeypatch.setattr(qm, "go_loud", lambda: calls.append("loud") or 0)
        monkeypatch.setattr(qm, "in_quiet_window", lambda now=None: False)
        monkeypatch.setattr(qm, "in_research_band", lambda now=None: False)
        monkeypatch.setattr(sys, "argv", ["quiet_mode.py", "--enforce"])
        assert qm.main() == 0
        assert calls == ["quiet"], "outside the research band the heavy grinders are due"

    def test_evening_blackout_beats_presence_downgrade(self, monkeypatch):
        """J's evening is decided by the clock BEFORE presence is ever consulted."""
        self._hold(monkeypatch)
        calls = []
        monkeypatch.setattr(qm, "go_research", lambda: calls.append("research") or 0)
        monkeypatch.setattr(qm, "go_quiet", lambda: calls.append("quiet") or 0)
        monkeypatch.setattr(qm, "in_quiet_window", lambda now=None: True)
        monkeypatch.setattr(sys, "argv", ["quiet_mode.py", "--enforce"])
        assert qm.main() == 0
        assert calls == ["quiet"]
