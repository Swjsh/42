"""Guard: automation/overnight/queue.md must not silently regrow past a retention cap.

WHY THIS GUARD EXISTS
----------------------
2026-08-09: a conductor fire archived ~1019 lines of fully-resolved queue.md
content to keep the live file under the Read tool's 256KB single-read limit
(the archive note is still visible verbatim at the top of "## Active
backlog" in queue.md). Nobody wired anything to catch the file re-growing
past that limit afterward -- OP-22 says "every append-only producer has a
retention cap; hitting it triggers CONSOLIDATION", but the cap was prose,
not code.

By 2026-08-19 queue.md had grown BACK to 598,612 bytes (2.3x the 256KB Read
limit) with zero warning -- every fire that needed the full file had to
special-case around the Read tool's size error, and 70+ fully-resolved
"[x] ... status:done/closed/resolved" items (each a multi-hundred-word
after-action writeup) were sitting in the LIVE backlog instead of the
archive, crowding out genuinely-open work when a human or a fresh Claude
session skimmed the file.

That fire consolidated it back down (598,612 -> ~348,523 bytes, verbatim
archive at automation/overnight/queue-archive-2026-08-19.md, verified zero
`depends:` references broken). This test is the code-side guard so the SAME
silent-regrowth class can't recur unnoticed a second time: it RED-fails
once the file crosses a cap, forcing the next fire that touches queue.md to
either consolidate again or consciously raise the cap with a stated reason
-- it can never again just keep growing in silence.

The cap (450_000 bytes) is set with headroom above the 2026-08-19
post-consolidation size (348,523) so ordinary day-to-day appends don't
thrash this test, but well below where the file becomes unreadable by the
Read tool in one call (a >256KB single Read already forces callers to use
task_scorer.py or offset/limit workarounds -- 450KB is deliberately closer
to "needs another consolidation pass soon" than "still fine").
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUEUE_MD = REPO / "automation" / "overnight" / "queue.md"

# Headroom above the 2026-08-19 post-consolidation size (348,523 bytes).
# Read tool's hard single-call limit is 262,144 bytes (256KB) -- this cap is
# intentionally well above that (task_scorer.py, not raw Read, is the
# designed way to consume this file) but still bounded so regrowth can't go
# unnoticed indefinitely.
RETENTION_CAP_BYTES = 450_000


def test_queue_md_exists():
    assert QUEUE_MD.exists(), f"queue.md missing at {QUEUE_MD} -- conductor's external memory is gone"


def test_queue_md_under_retention_cap():
    size = QUEUE_MD.stat().st_size
    assert size < RETENTION_CAP_BYTES, (
        f"automation/overnight/queue.md is {size:,} bytes, over the "
        f"{RETENTION_CAP_BYTES:,}-byte retention cap (OP-22: 'every "
        f"append-only producer has a retention cap; hitting it triggers "
        f"CONSOLIDATION'). Run the same archival pass as the 2026-08-19 "
        f"conductor fire: extract every '## Active backlog' (and later-"
        f"section) item whose checkbox is [x] AND whose terminal status "
        f"resolves to done/closed/resolved/cancelled/decided into a new "
        f"dated automation/overnight/queue-archive-<date>.md, verifying "
        f"first that no still-open item's 'depends:' references an "
        f"archived id."
    )


def test_queue_archive_2026_08_19_exists_and_nonempty():
    """The 2026-08-19 consolidation's output must actually be on disk --
    a passing size-cap test with a missing/empty archive would mean data
    was deleted, not archived."""
    archive = REPO / "automation" / "overnight" / "queue-archive-2026-08-19.md"
    assert archive.exists(), "2026-08-19 consolidation archive is missing -- was the archived content deleted instead of moved?"
    assert archive.stat().st_size > 50_000, "2026-08-19 archive file exists but looks too small to hold the ~70 archived items"
