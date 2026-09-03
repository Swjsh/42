"""Guard: setup/scripts/study_curriculum.py (queue.md GAMMA-STUDY-CURRICULUM, MED).

Deterministic, $0 helper backing the conductor STUDY MODE fire
(automation/prompts/conductor.md MODES; doctrine: markdown/doctrine/STUDY-CURRICULUM.md).
Covers the two pieces the LLM fire must NOT have to reason about itself:

  - next-topic: least-recently-studied topic wins ("never" beats any ISO date;
    ties broken by table order for a deterministic rotation).
  - record: appends exactly-10-line notes under the right topic and stamps the
    table's Last Studied cell -- rejects malformed note files (not exactly 10
    non-blank lines) and unknown topic slugs instead of guessing.

All fixtures use a throwaway curriculum file under tmp_path -- this guard never
touches the real markdown/doctrine/STUDY-CURRICULUM.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import study_curriculum as sc  # noqa: E402


SAMPLE = """# STUDY-CURRICULUM (test fixture)

| Topic | Slug | Sources | Last Studied (ET) | Status |
|---|---|---|---|---|
| Candlestick pattern taxonomies | candlestick_taxonomies | 2 | never | seed |
| Volume profile | volume_profile | 2 | 2026-08-01 | studied |
| VWAP bands | vwap_bands | 2 | never | seed |

## Sources

### candlestick_taxonomies -- Candlestick pattern taxonomies
- https://en.wikipedia.org/wiki/Candlestick_pattern (200, verified 2026-09-03)
- https://en.wikipedia.org/wiki/Candlestick_chart (200, verified 2026-09-03)

### volume_profile -- Volume profile
- https://en.wikipedia.org/wiki/Market_profile (200, verified 2026-09-03)
- https://www.tradingview.com/support/solutions/43000502040-volume-profile/ (200, verified 2026-09-03)

### vwap_bands -- VWAP bands
- https://en.wikipedia.org/wiki/Volume-weighted_average_price (200, verified 2026-09-03)
- https://www.nasdaq.com/glossary/v/vwap (200, verified 2026-09-03)

## Study notes

### candlestick_taxonomies -- Candlestick pattern taxonomies
_none yet -- filed by the conductor STUDY-mode fire._

### volume_profile -- Volume profile
_none yet -- filed by the conductor STUDY-mode fire._

#### 2026-08-01 (ET)
1. prior note line one
2. prior note line two
3. prior note line three
4. prior note line four
5. prior note line five
6. prior note line six
7. prior note line seven
8. prior note line eight
9. prior note line nine
10. prior note line ten

### vwap_bands -- VWAP bands
_none yet -- filed by the conductor STUDY-mode fire._
"""

TEN_LINE_NOTE = "\n".join(f"line {i}" for i in range(1, 11)) + "\n"


@pytest.fixture()
def curriculum_path(tmp_path: Path) -> Path:
    p = tmp_path / "STUDY-CURRICULUM.md"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


# --------------------------------------------------------------------------------- #
# parse_table / parse_sources
# --------------------------------------------------------------------------------- #
def test_parse_table_reads_all_rows():
    rows = sc.parse_table(SAMPLE)
    slugs = {r["slug"] for r in rows}
    assert slugs == {"candlestick_taxonomies", "volume_profile", "vwap_bands"}


def test_parse_table_empty_raises():
    with pytest.raises(sc.CurriculumError):
        sc.parse_table("# no table here\n")


def test_parse_sources_maps_slug_to_urls():
    sources = sc.parse_sources(SAMPLE)
    assert len(sources["candlestick_taxonomies"]) == 2
    assert sources["candlestick_taxonomies"][0]["url"] == "https://en.wikipedia.org/wiki/Candlestick_pattern"
    assert len(sources["volume_profile"]) == 2


# --------------------------------------------------------------------------------- #
# pick_next_topic -- least-recently-studied wins
# --------------------------------------------------------------------------------- #
def test_pick_next_topic_never_beats_studied():
    rows = sc.parse_table(SAMPLE)
    topic = sc.pick_next_topic(rows)
    # both candlestick_taxonomies and vwap_bands are "never" -- table order breaks
    # the tie, candlestick_taxonomies appears first
    assert topic["slug"] == "candlestick_taxonomies"


def test_pick_next_topic_oldest_date_wins_among_studied():
    rows = [
        {"name": "A", "slug": "a", "sources": 1, "last_studied": "2026-08-15", "status": "studied"},
        {"name": "B", "slug": "b", "sources": 1, "last_studied": "2026-07-01", "status": "studied"},
        {"name": "C", "slug": "c", "sources": 1, "last_studied": "2026-08-30", "status": "studied"},
    ]
    topic = sc.pick_next_topic(rows)
    assert topic["slug"] == "b"  # earliest date = most overdue


# --------------------------------------------------------------------------------- #
# next-topic CLI
# --------------------------------------------------------------------------------- #
def test_cmd_next_topic_json(curriculum_path: Path, capsys):
    rc = sc.main(["next-topic", "--curriculum", str(curriculum_path), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    import json

    payload = json.loads(out)
    assert payload["slug"] == "candlestick_taxonomies"
    assert len(payload["sources"]) == 2


# --------------------------------------------------------------------------------- #
# record CLI
# --------------------------------------------------------------------------------- #
def test_cmd_record_success_updates_table_and_appends_note(curriculum_path: Path, tmp_path: Path, capsys):
    note_file = tmp_path / "note.txt"
    note_file.write_text(TEN_LINE_NOTE, encoding="utf-8")

    rc = sc.main(
        [
            "record",
            "--topic",
            "candlestick_taxonomies",
            "--note-file",
            str(note_file),
            "--curriculum",
            str(curriculum_path),
            "--now",
            "2026-09-10T21:00:00-04:00",
        ]
    )
    assert rc == 0

    updated = curriculum_path.read_text(encoding="utf-8")
    # table's Last Studied cell moved from "never" to the stamped date
    assert "| Candlestick pattern taxonomies | candlestick_taxonomies | 2 | 2026-09-10 | studied |" in updated
    # note block appended under the right topic heading, not another one
    assert "#### 2026-09-10 (ET)" in updated
    assert "1. line 1" in updated
    assert "10. line 10" in updated

    # re-parsing after the write must still succeed (round-trip integrity)
    rows_after = sc.parse_table(updated)
    by_slug = {r["slug"]: r for r in rows_after}
    assert by_slug["candlestick_taxonomies"]["last_studied"] == "2026-09-10"
    # the OTHER topics' notes / dates are untouched
    assert by_slug["volume_profile"]["last_studied"] == "2026-08-01"
    assert "prior note line one" in updated


def test_cmd_record_wrong_line_count_rejected(curriculum_path: Path, tmp_path: Path):
    note_file = tmp_path / "bad_note.txt"
    note_file.write_text("only one line\n", encoding="utf-8")

    rc = sc.main(
        [
            "record",
            "--topic",
            "candlestick_taxonomies",
            "--note-file",
            str(note_file),
            "--curriculum",
            str(curriculum_path),
        ]
    )
    assert rc == 2
    # curriculum file must be untouched on rejection
    assert curriculum_path.read_text(encoding="utf-8") == SAMPLE


def test_cmd_record_unknown_topic_rejected(curriculum_path: Path, tmp_path: Path):
    note_file = tmp_path / "note.txt"
    note_file.write_text(TEN_LINE_NOTE, encoding="utf-8")

    rc = sc.main(
        [
            "record",
            "--topic",
            "not_a_real_topic",
            "--note-file",
            str(note_file),
            "--curriculum",
            str(curriculum_path),
        ]
    )
    assert rc == 2


def test_cmd_record_missing_note_file_rejected(curriculum_path: Path, tmp_path: Path):
    rc = sc.main(
        [
            "record",
            "--topic",
            "candlestick_taxonomies",
            "--note-file",
            str(tmp_path / "does_not_exist.txt"),
            "--curriculum",
            str(curriculum_path),
        ]
    )
    assert rc == 2


def test_record_then_next_topic_rotates_away(curriculum_path: Path, tmp_path: Path, capsys):
    """After recording candlestick_taxonomies, the next pick should be the other
    'never' topic (vwap_bands) -- proves the rotation actually advances."""
    note_file = tmp_path / "note.txt"
    note_file.write_text(TEN_LINE_NOTE, encoding="utf-8")
    sc.main(
        [
            "record",
            "--topic",
            "candlestick_taxonomies",
            "--note-file",
            str(note_file),
            "--curriculum",
            str(curriculum_path),
            "--now",
            "2026-09-10T21:00:00-04:00",
        ]
    )
    capsys.readouterr()  # discard record's stdout

    rc = sc.main(["next-topic", "--curriculum", str(curriculum_path), "--json"])
    assert rc == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["slug"] == "vwap_bands"
