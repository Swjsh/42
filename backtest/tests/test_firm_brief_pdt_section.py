"""Guard for firm_brief.render_pdt_lines -- the per-account PDT (Rule 7) visibility
section on the one-page firm brief (2026-07-14).

Motivation: analysis/daily-brief/2026-07-13-FULL-AUDIT.md #2 -- core Safe was
silently PDT-blocked ALL DAY on a day-trade count it INHERITED from an account
repoint (commit 61cfca0), and nobody knew until a manual review found it, not
an instrument. This section reads self_check's cached 'pdt' summary
(self-check-last.json's "pdt" key, written by self_check.check_pdt_status)
and MUST render a blocked account LOUDLY, never blend into a green brief.

Mirrors test_firm_brief_twin_section.py's import convention and the fail-open
contract every firm_brief.py section shares: missing/empty data renders an
honest UNKNOWN, never a fabricated count."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "firm_brief", REPO / "setup" / "scripts" / "firm_brief.py")
fb = importlib.util.module_from_spec(_SPEC)
sys.modules["firm_brief"] = fb
_SPEC.loader.exec_module(fb)


def test_no_self_check_data_renders_unknown():
    lines = fb.render_pdt_lines({})
    assert len(lines) == 1
    assert "UNKNOWN" in lines[0]
    assert "Gamma_SelfCheck" in lines[0]


def test_self_check_present_but_no_pdt_key_renders_unknown():
    """An OLDER self-check-last.json (written before this feature shipped) has no
    'pdt' key at all -- must degrade honestly, not crash or silently show nothing."""
    lines = fb.render_pdt_lines({"verdict": "GREEN", "problems": []})
    assert len(lines) == 1
    assert "UNKNOWN" in lines[0]


def test_blocked_account_renders_loud_with_rolloff_date():
    """The exact 2026-07-13 scenario: core Safe blocked at 9/3, rolls off 2026-07-15."""
    self_check = {"pdt": {
        "safe": {"status": "BLOCKED", "day_trades_used_5d": 9, "limit": 3,
                 "remaining": 0, "rolloff_date": "2026-07-15", "equity": 1746.63},
        "bold": {"status": "OK", "day_trades_used_5d": 0, "limit": 3,
                 "remaining": 3, "rolloff_date": None, "equity": 1963.04},
    }}
    lines = fb.render_pdt_lines(self_check)
    assert len(lines) == 2
    safe_line = next(l for l in lines if "core Safe" in l)
    assert "BLOCKED" in safe_line
    assert "9/3" in safe_line
    assert "2026-07-15" in safe_line
    bold_line = next(l for l in lines if "core Bold" in l)
    assert "BLOCKED" not in bold_line


def test_not_blocked_shows_used_remaining_and_rolloff():
    self_check = {"pdt": {
        "safe": {"status": "OK", "day_trades_used_5d": 1, "limit": 3,
                 "remaining": 2, "rolloff_date": "2026-07-20", "equity": 1746.63},
        "bold": {"status": "OK", "day_trades_used_5d": 0, "limit": 3,
                 "remaining": 3, "rolloff_date": None, "equity": 1963.04},
    }}
    lines = fb.render_pdt_lines(self_check)
    safe_line = next(l for l in lines if "core Safe" in l)
    assert "1/3" in safe_line and "2 remaining" in safe_line and "2026-07-20" in safe_line
    bold_line = next(l for l in lines if "core Bold" in l)
    assert "0/3" in bold_line and "3 remaining" in bold_line
    assert "rolls off" not in bold_line, "zero used -> nothing to roll off, must not print a bogus date"


def test_per_account_fetch_failure_renders_unknown_with_reason():
    self_check = {"pdt": {
        "safe": {"status": "UNKNOWN", "reason": "OSError: Connection refused"},
        "bold": {"status": "OK", "day_trades_used_5d": 1, "limit": 3,
                 "remaining": 2, "rolloff_date": "2026-07-20", "equity": 1963.04},
    }}
    lines = fb.render_pdt_lines(self_check)
    safe_line = next(l for l in lines if "core Safe" in l)
    assert "UNKNOWN" in safe_line
    assert "Connection refused" in safe_line


def test_not_applicable_above_25k_threshold():
    self_check = {"pdt": {
        "safe": {"status": "NOT_APPLICABLE", "day_trades_used_5d": 9, "limit": 3,
                 "remaining": 0, "rolloff_date": "2026-07-15", "equity": 30000.0},
        "bold": {"status": "OK", "day_trades_used_5d": 0, "limit": 3,
                 "remaining": 3, "rolloff_date": None, "equity": 1963.04},
    }}
    lines = fb.render_pdt_lines(self_check)
    safe_line = next(l for l in lines if "core Safe" in l)
    assert "N/A" in safe_line
    assert "$30,000.00" in safe_line


def test_missing_account_entry_renders_unknown_not_crash():
    """Only 'safe' present in the cached summary -- 'bold' missing entirely (e.g. an
    even older schema, or a partial write) must not KeyError, must render UNKNOWN."""
    self_check = {"pdt": {
        "safe": {"status": "OK", "day_trades_used_5d": 1, "limit": 3,
                 "remaining": 2, "rolloff_date": "2026-07-20", "equity": 1746.63},
    }}
    lines = fb.render_pdt_lines(self_check)
    assert len(lines) == 2
    bold_line = next(l for l in lines if "core Bold" in l)
    assert "UNKNOWN" in bold_line


# ---- integration: build_brief includes the section ----

def test_build_brief_includes_pdt_section_header_and_lines():
    import datetime as dt
    self_check = {"verdict": "GREEN", "problems": [], "ts_et": "2026-07-14T11:00:00",
                  "pdt": {
                      "safe": {"status": "BLOCKED", "day_trades_used_5d": 9, "limit": 3,
                              "remaining": 0, "rolloff_date": "2026-07-15", "equity": 1746.63},
                      "bold": {"status": "OK", "day_trades_used_5d": 0, "limit": 3,
                              "remaining": 3, "rolloff_date": None, "equity": 1963.04},
                  }}
    text = fb.build_brief({}, self_check, [], dt.datetime(2026, 7, 14, 11, 0))
    assert "## PDT status (Rule 7" in text
    assert "BLOCKED" in text
    assert "core Safe" in text and "core Bold" in text
