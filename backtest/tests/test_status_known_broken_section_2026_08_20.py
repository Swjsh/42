"""Guard: a failure report must LAND on STATUS.md even when the section is missing.

THE OUTAGE (found 2026-08-20, while wiring the trendline shadow's failure path)
------------------------------------------------------------------------------
`## Known broken` is the surface a dozen unattended scripts escalate to. It was
absent from the live STATUS.md and present only in STATUS-archive-2026-06.md.

Mechanism: status_retention.py rebuilds STATUS.md as `preamble + newest entries`,
splitting on `## [` boundaries and rolling the older tail to a monthly archive.
`## Known broken` does not match `## [`, so wherever it sat below the first dated
entry it was absorbed into that entry and rolled off with it in June.

Why it stayed invisible for two months: the writers split into two camps.
  * CREATE-IF-MISSING (catastrophe_cap_shadow_ledger.py, eod_flatten.py) kept
    working, so the channel still carried traffic and looked alive.
  * SILENT-RETURN (guard_runner_slow, guard_runner_full, monday_verify) all did
    `if marker not in text: return` -- every RED they raised from June onward was
    discarded, while the runners still exited cleanly and reported success.

A guard runner whose failure report goes nowhere is worse than no guard runner: it
manufactures the belief that something is watching. That is the C7 silent-success
class operating one level up, on the alarm channel itself.

WHAT IS PINNED HERE, AND WHY IT IS NOT A LAYOUT TEST
  The first version of this guard asserted the heading sits in STATUS.md's preamble.
  That is true today and STILL not sufficient: the conductor PREPENDS each new
  `## [` entry at the very top of the file, so the heading stops being the preamble
  on the next fire and becomes roll-off-eligible all over again. Position cannot be
  the invariant.

  The invariant is BEHAVIOURAL: given a STATUS.md with no section at all, every
  escalating writer must still produce a file containing its report. These tests
  drive each writer against a temp file and demand the line lands.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

MARKER = "## Known broken"
NO_SECTION = "## [2026-08-20 10:00 ET] a dated entry and nothing else\nfiller\n"


def _writers():
    """(name, callable(status_path) -> None) for each escalating writer.

    Imported lazily and skipped individually so one refactor cannot blind the rest.
    """
    out = []
    try:
        import guard_runner_full as grf

        def _full(p):
            grf.STATUS = p
            grf._append_status("red", "1 passed, 2 failed, 0 skipped", ["tests/test_x.py::test_y"])
        out.append(("guard_runner_full", _full))
    except Exception:                                     # noqa: BLE001
        pass
    try:
        import guard_runner_slow as grs

        def _slow(p):
            grs.STATUS = p
            grs._flag_status_md("red", "3 passed, 1 failed")
        out.append(("guard_runner_slow", _slow))
    except Exception:                                     # noqa: BLE001
        pass
    try:
        import monday_verify as mv

        def _monday(p):
            mv._flag_known_broken(
                [{"id": "SOME-CHECK", "observed": "went red", "expected": "green"}],
                "2026-08-20", status_md=p)
        out.append(("monday_verify", _monday))
    except Exception:                                     # noqa: BLE001
        pass
    try:
        import intervention_counter as ivc  # TASK B2, 2026-08-28

        def _intervention(p):
            ivc._flag_status_md({
                "generated_at_et": "2026-08-20T10:00:00", "date_et": "2026-08-20",
                "today": {"n_round_trips": 1, "by_category": {"manual_both": 1},
                          "by_arm": {"safe-2": 1}, "realized_pnl": -12.0}}, status_md=p)
        out.append(("intervention_counter", _intervention))
    except Exception:                                     # noqa: BLE001
        pass
    try:
        import itm_at_expiry_assertion as itm  # TASK B2, 2026-08-28

        def _itm(p):
            itm._flag_status_md({
                "generated_at_et": "2026-08-20T10:00:00", "n_violations": 1,
                "violations": [{"arm": "safe-2", "symbol": "SPY260820C00770000",
                                 "net_qty": 3.0, "itm_by_usd": 1.0, "notional_usd": 231000.0}],
            }, status_md=p)
        out.append(("itm_at_expiry_assertion", _itm))
    except Exception:                                     # noqa: BLE001
        pass
    return out


@pytest.mark.parametrize("name,write", _writers(), ids=lambda v: v if isinstance(v, str) else "")
def test_report_lands_even_with_no_section(name, write, tmp_path):
    """The whole outage in one assertion: no section, report must still arrive."""
    p = tmp_path / "STATUS.md"
    p.write_text(NO_SECTION, encoding="utf-8")
    write(p)
    after = p.read_text(encoding="utf-8")
    assert MARKER in after, (
        f"{name} did not create '{MARKER}' when it was missing. It is silently "
        "discarding failure reports -- the exact June 2026 outage. Recreate the "
        "section instead of returning early."
    )
    assert len(after) > len(NO_SECTION), f"{name} wrote no report line at all"
    assert "2026-08-20" in after or "ET]" in after, f"{name} wrote an unstamped report"


@pytest.mark.parametrize("name,write", _writers(), ids=lambda v: v if isinstance(v, str) else "")
def test_report_lands_when_the_section_does_exist(name, write, tmp_path):
    """The happy path must not regress while fixing the missing-section path."""
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n- an older escalation\n\n" + NO_SECTION, encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    write(p)
    after = p.read_text(encoding="utf-8")
    assert len(after) > len(before), f"{name} wrote nothing when the section existed"
    assert after.count(MARKER) == 1, (
        f"{name} duplicated the '{MARKER}' heading instead of writing under the existing one"
    )
    assert "- an older escalation" in after, f"{name} destroyed prior escalations"


def test_there_is_at_least_one_writer_to_check():
    """If every writer is renamed away, this file must fail rather than pass empty."""
    assert _writers(), (
        "no escalating writer could be imported -- guard_runner_full/_slow/monday_verify "
        "were renamed or moved. Re-point this guard; do not delete it."
    )


def test_live_status_has_the_section():
    """Advisory, not the invariant: nice to have it present, but the tests above are
    what actually protect the channel."""
    status = REPO / "automation" / "overnight" / "STATUS.md"
    assert status.exists(), status
    if MARKER not in status.read_text(encoding="utf-8"):
        pytest.skip("section absent from live STATUS.md -- writers recreate it on next fire")
