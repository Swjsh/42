"""Guard: the 9 new Command-view tile builders (WS-D, COCKPIT-DESIGN-SPEC-2026-09-03.md sec 5).

Two failure classes this guards against (same C7/OP-33 law as test_gamma_home):
  1. A missing/unparseable source must degrade to {"ok": False, "path": ...}
     -- never raise, never a page-losing exception.
  2. A "say" sentence must never leak "None"/"undefined" -- a card that cannot
     compose a real sentence says NO DATA, it does not print a broken one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import gamma_cockpit_tiles as tiles          # noqa: E402
import gamma_home as gh                      # noqa: E402

ALL_KEYS = ("gate", "prep", "eod", "standup", "shadow", "watchers", "guards", "tasks", "gym")
# ROUND-2 addition (2026-09-04, Agent health sparklines): build_tiles() now also
# carries "health_spark" -- {lane_id: {"series": [7 ints] | None, "path": str | None}}
# for the Agent-health panel's per-lane sparkline. It is deliberately NOT one of the
# 9 tile-contract builders above (no ok/path/stamp_et/verdict/say/fresh_h -- see
# gamma_cockpit_tiles.py's build_health_spark() docstring), so it is asserted on its
# own shape below rather than folded into ALL_KEYS's per-tile contract checks.
HEALTH_SPARK_LANES = ("kitchen", "prospector", "futures", "multi", "spy", "watchers")


# ------------------------------------------------------- missing sources

def test_every_builder_reports_no_data_when_source_missing(tmp_path, monkeypatch):
    """Point every source root at an empty tmp dir: no builder may raise, and
    every tile must degrade to ok:False carrying the path it looked for."""
    nope = tmp_path / "nope"
    monkeypatch.setattr(tiles, "REPO", nope)
    monkeypatch.setattr(tiles, "STATE", nope / "automation" / "state")
    monkeypatch.setattr(tiles, "ANALYSIS", nope / "analysis")

    out = tiles.build_tiles()
    assert set(out.keys()) == set(ALL_KEYS) | {"health_spark"}
    for key in ALL_KEYS:
        row = out[key]
        assert row["ok"] is False, (key, row)
        assert row["path"], (key, row)
        assert row["stamp_et"] is None, (key, row)
        assert row["verdict"] == "off", (key, row)
        assert row["say"].startswith("NO DATA"), (key, row["say"])
        assert "looked for" in row["say"], (key, row["say"])
    # health_spark degrades the same way -- never raises, every lane's series
    # goes honestly to None when its source root doesn't exist.
    hs = out["health_spark"]
    assert set(hs.keys()) == set(HEALTH_SPARK_LANES)
    for lane_id in HEALTH_SPARK_LANES:
        assert hs[lane_id]["series"] is None, (lane_id, hs[lane_id])


def test_missing_source_never_raises_even_with_real_repo_globals():
    """A single builder called directly against a source that plain doesn't
    exist on THIS machine (not monkeypatched) must still degrade cleanly --
    the _safe() wrapper is the contract, not the individual try/except."""
    row = tiles._safe("gate", Path("Z:/definitely/not/a/real/path/go-live-gate.json"),
                       lambda: (_ for _ in ()).throw(OSError("nope")))
    assert row["ok"] is False
    assert row["verdict"] == "off"
    assert "NO DATA" in row["say"]
    assert "error" in row


# ------------------------------------------------------- no fabrication

def test_no_none_or_undefined_leaks_into_any_say_string():
    """Whatever state this machine is actually in right now, every composed
    sentence must read as a sentence -- never the Python str() of a missing
    value."""
    out = tiles.build_tiles()
    for key, row in out.items():
        if key == "health_spark":
            continue  # not a "say"-shaped tile -- see ALL_KEYS' own comment above
        say = row.get("say", "")
        assert "None" not in say, (key, say)
        assert "undefined" not in say, (key, say)
        assert say, (key, "empty say")


def test_build_tiles_carries_all_nine_keys_against_real_repo_state():
    """Same call gamma_home.build() makes -- against THIS machine's real
    files, not a fixture. Every key must be present and every tile must
    carry the common contract fields."""
    out = tiles.build_tiles()
    assert set(out.keys()) == set(ALL_KEYS) | {"health_spark"}
    for key in ALL_KEYS:
        row = out[key]
        for field in ("ok", "path", "stamp_et", "verdict", "say", "fresh_h"):
            assert field in row, (key, field)
        assert row["verdict"] in ("green", "amber", "red", "off"), (key, row["verdict"])
        assert row["fresh_h"] == (6 if key == "guards" else 24), (key, row["fresh_h"])
    assert set(out["health_spark"].keys()) == set(HEALTH_SPARK_LANES)


# ------------------------------------------------------- gate (real file)

def test_gate_say_contains_042_against_the_real_file_when_present():
    """analysis/go-live-gate.json exists on this repo today -- pin its
    read-through against the exact value: CI-lower 0.424 rounds to 0.42."""
    p = REPO / "analysis" / "go-live-gate.json"
    if not p.exists():
        pytest.skip("go-live-gate.json not present on this checkout")
    row = tiles.build_gate()
    assert row["ok"] is True
    assert "0.42" in row["say"], row["say"]
    assert row["overall_verdict"] in ("RED", "GREEN", "YELLOW")
    assert isinstance(row["per_arm"], list) and row["per_arm"]
    assert row["ci"]["as_traded"]["ci_lower"] is not None


def test_gate_falls_back_to_see_expansion_when_ci_field_absent(tmp_path, monkeypatch):
    p = tmp_path / "go-live-gate.json"
    p.write_text(json.dumps({
        "overall_verdict": "RED",
        "criteria": {"statistical": {"book_wide_correlated_rollup": {}}},
    }), encoding="utf-8")
    monkeypatch.setattr(tiles, "ANALYSIS", tmp_path)
    row = tiles.build_gate()
    assert row["ok"] is True
    assert row["say"] == "RED. see expansion"


# ------------------------------------------------------- SHADOW.md parser

FIXTURE_SHADOW = """# Shadow & Prereg Board

> Auto-generated `2026-09-03 16:45:02 Thursday EDT` by obsidian_vault_sync.py.

## Live shadow instruments

- **Score ladder** (`Gamma_LadderRungShadow`) -- one line of detail
- **Chop exposure meter** (`Gamma_ChopMeter`) -- artifact appears after close

## Frozen preregs -- auto-discovered (7 non-terminal)

### `no status field` (4)

- `alpha` -- [[analysis/recommendations/alpha]] -- `no status field`

### `FROZEN_PREREG` (2)

- `beta` -- [[analysis/recommendations/beta]] -- `FROZEN_PREREG`

### `ACCRUING` (1)

- `gamma` -- [[analysis/recommendations/gamma]] -- `ACCRUING`

## Doctrine anchors

- [[MAP.md]]
"""


def test_shadow_fixture_with_3_buckets_parses_counts(tmp_path, monkeypatch):
    p = tmp_path / "SHADOW.md"
    p.write_text(FIXTURE_SHADOW, encoding="utf-8")
    monkeypatch.setattr(tiles, "REPO", tmp_path)
    row = tiles.build_shadow()
    assert row["ok"] is True
    assert len(row["live"]) == 2
    assert row["live"][0]["name"] == "Score ladder"
    assert row["preregs"]["total_non_terminal"] == 7
    buckets = {b["status"]: b["n"] for b in row["preregs"]["buckets"]}
    assert buckets == {"no status field": 4, "FROZEN_PREREG": 2, "ACCRUING": 1}
    assert "2 shadow clocks, 7 preregs, 0 armed" == row["say"]
    # spec 10.1 Vitals "Shadow board" heatmap: one verdict word per live clock
    assert row["heat"] == [c["verdict"] for c in row["live"]]


def test_shadow_clock_verdict_reads_explicit_keywords_only():
    assert tiles._shadow_clock_verdict("ADJUDICATED: V-d1 KILL (p=0.66)") == "red"
    assert tiles._shadow_clock_verdict("EXTEND per pooled F4") == "green"
    assert tiles._shadow_clock_verdict("still collecting, no verdict yet") == "off"


def test_shadow_clock_verdict_does_not_read_a_negation_backwards():
    """Real SHADOW.md line (2026-09-03): the trendline shadow clock's own
    text is 'NOT a green light' -- a bare keyword scan would misread this as
    green, the opposite of what the sentence says."""
    assert tiles._shadow_clock_verdict(
        "95% CI straddles zero -- NOT a green light; promotion bar: [[x]]"
    ) == "off"


def test_shadow_zero_sections_reports_no_data(tmp_path, monkeypatch):
    p = tmp_path / "SHADOW.md"
    p.write_text("no headings here, just prose", encoding="utf-8")
    monkeypatch.setattr(tiles, "REPO", tmp_path)
    row = tiles.build_shadow()
    assert row["ok"] is False
    assert row["say"] == "NO DATA, parser found 0 sections in SHADOW.md"


# ------------------------------------------------------- eod parser

FIXTURE_EOD = """<!-- QUANT:BEGIN (deterministic; code-generated by fill_funnel.py; do not hand-edit) -->
## Quantitative (deterministic -- computed from ledgers, not LLM)

Source ledgers: fixture. Generated 2026-09-03T16:45:38 ET. Funnel verdict: **DEGRADED**.

| account | ticks | signals | ENTER | rule-blocked | attempted | accepted | filled | exited |
|---|---|---|---|---|---|---|---|---|
| core:bold CORE-BOLD (U67N) | 386 | 67 | 50 | 5 | 4 | 4 | 3 | 3 |
| core:safe CORE-SAFE (46VG) | 386 | 67 | 31 | 7 | 4 | 4 | 4 | 4 |
| **TOTAL** | 772 | 134 | 81 | 12 | 8 | 8 | 7 | 7 |

**Why each arm did / did not trade:**

| account | traded | dominant cause | detail |
|---|---|---|---|
| core:bold CORE-BOLD (U67N) | yes | `TRADED` | TRADED -- 3 filled |
| core:safe CORE-SAFE (46VG) | yes | `TRADED` | TRADED -- 4 filled |

<!-- QUANT:END -->
"""


def test_eod_fixture_parses_total_row(tmp_path, monkeypatch):
    day = tmp_path / "analysis" / "eod"
    day.mkdir(parents=True)
    (day / "2026-09-03.md").write_text(FIXTURE_EOD, encoding="utf-8")
    monkeypatch.setattr(tiles, "ANALYSIS", tmp_path / "analysis")
    from datetime import datetime as _dt
    monkeypatch.setattr(tiles, "et_now", lambda now_utc=None: _dt(2026, 9, 3, 12, 0, 0))

    row = tiles.build_eod()
    assert row["ok"] is True
    assert row["funnel_verdict"] == "DEGRADED"
    assert row["total"]["filled"] == 7
    assert row["total"]["enter"] == 81
    assert len(row["accounts"]) == 2
    assert len(row["why"]) == 2
    assert row["why"][0]["traded"] is True
    assert row["say"] == "DEGRADED. 7 filled of 81 ENTER, 2 arms"


def test_eod_missing_quant_markers_degrades_not_raises(tmp_path, monkeypatch):
    day = tmp_path / "analysis" / "eod"
    day.mkdir(parents=True)
    (day / "2026-09-03.md").write_text("# no quant block here", encoding="utf-8")
    monkeypatch.setattr(tiles, "ANALYSIS", tmp_path / "analysis")
    from datetime import datetime as _dt
    monkeypatch.setattr(tiles, "et_now", lambda now_utc=None: _dt(2026, 9, 3, 12, 0, 0))

    out = tiles._safe("eod", tiles.ANALYSIS / "eod" / "2026-09-03.md", tiles.build_eod)
    assert out["ok"] is False
    assert "error" in out


# ------------------------------------------------------- gamma_home wiring

def test_gh_build_carries_all_nine_keys():
    """The acceptance contract: gh.build(quiet=True) must carry every one of
    the 9 new keys, each with the common ok/path/say fields."""
    payload = gh.build(quiet=True)
    for key in ALL_KEYS:
        assert key in payload, key
        row = payload[key]
        assert isinstance(row, dict), key
        assert "ok" in row and "path" in row and "say" in row, (key, row)


def test_payload_json_has_no_undefined_or_object_object():
    """The payload must serialize cleanly to the JSON `const D=` blob the page
    embeds. Scoped to the payload builder's own contract (json.dumps, the same
    call gamma_home.main() makes for payload.json) rather than the full HTML
    render, so this stays green independent of sibling JS modules (tiles_js /
    command_js / producers_js) that other WS-owned files are still landing."""
    payload = gh.build(quiet=True)
    blob = json.dumps(payload, default=str)
    assert "undefined" not in blob
    assert "[object Object]" not in blob
    for key in ALL_KEYS:
        assert '"%s"' % key in blob, key


# ------------------------------------------------------- DAYLINE export

def test_dayline_constant_exported_and_shaped():
    assert isinstance(tiles.DAYLINE, list) and len(tiles.DAYLINE) == 7
    for entry in tiles.DAYLINE:
        assert set(entry.keys()) == {"label", "time_et", "name"}


def test_tasks_builder_against_real_repo_state():
    row = tiles.build_tasks()
    if not row["ok"]:
        pytest.skip("SCHEDULED-TASKS.md or task-state-guard.json not present on this checkout")
    assert row["registered"] >= row["disabled"] >= 0
    assert isinstance(row["lanes"], list) and len(row["lanes"]) == 7
    assert isinstance(row["dayline"], list) and len(row["dayline"]) == 7
    for lane in row["lanes"]:
        assert set(("lane", "worst", "tasks")).issubset(lane.keys())
