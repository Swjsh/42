"""Guard: no Gamma-authored alert may ASK J for permission on paper work.

SCAR (J 2026-08-31): entry_block_watch.compose_alert_text ended every blocked-setup
voice alert with "J, say the word to arm it." J's response on hearing it read back:
"why am i being asked to arm anything??" -- correct. OP-0 lists the ONLY four things
that route to J (live-money arming, secrets, irreversible external actions, a genuine
doctrine fork). A paper gate refusing a setup is none of them; changing that gate is
Gamma's call via OP-11's eval-first ladder. OP-11 names soliciting permission to ship
a cleared edge as the banned anti-pattern by name.

The alert's job is to REPORT the refusal and its cost. Not to shop for an override.

This guard is text-level on purpose: the violation was never a logic bug, it was COPY.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Modules that compose human/voice-facing alert copy.
ALERT_SOURCES = [
    REPO / "setup" / "scripts" / "entry_block_watch.py",
]

# Phrases that hand J a decision he does not own on paper work.
FORBIDDEN = [
    r"say the word",
    r"want me to\b",
    r"should I\b",
    r"your call\b",
    r"shall I\b",
    r"let me know if you want",
    r"do you want me",
    r"awaiting your approval",
    r"J, .*\barm it\b",
]


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """Source lines with whole-line comments stripped -- a comment may quote the scar."""
    out = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.lstrip().startswith("#"):
            continue
        out.append((i, raw))
    return out


@pytest.mark.parametrize("path", ALERT_SOURCES, ids=lambda p: p.name)
def test_alert_copy_never_asks_j_for_permission(path: Path) -> None:
    assert path.exists(), f"alert source vanished: {path}"
    hits = []
    for lineno, line in _code_lines(path):
        for pat in FORBIDDEN:
            if re.search(pat, line, flags=re.IGNORECASE):
                hits.append(f"{path.name}:{lineno}: /{pat}/ -> {line.strip()[:110]}")
    assert not hits, (
        "Alert copy asks J to authorise paper work (OP-0 / OP-11 forbidden framing).\n"
        "Report the refusal and its cost; change the gate yourself via the eval ladder.\n"
        + "\n".join(hits)
    )


def test_entry_block_alert_text_is_reporting_not_asking() -> None:
    """End-to-end on the real composer: the emitted sentence must not solicit an override."""
    import sys

    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    from entry_block_watch import compose_alert_text  # noqa: PLC0415

    row = {
        "account": "safe",
        "bear_score": 8,
        "bear_triggers_raw": ["level_rejection", "multi_day_confluence"],
        "bear_blockers": [1, 8],
        "bear_rejection_level_raw": 766.76,
        "verdict": "HOLD",
    }
    text = compose_alert_text(row, "bear")
    assert "say the word" not in text.lower()
    assert "arm it" not in text.lower()
    # It must still do its actual job: name the score and the blocker.
    assert "8" in text
    assert "blocker" in text.lower()
