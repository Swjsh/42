"""Guards for setup/scripts/sector_rows.py (GOAL-GAMMA-STATION-2026-09-13 item 13,
plan `dapper-cuddling-peacock.md` Slice 3) and its two call sites:
obsidian_vault_sync.render_sectors_table() and the '## Sectors' block build_home()
must carry exactly once.

Properties pinned here (see sector_rows.py's own module docstring for the full
contract):

1. FAIL-OPEN. A missing/unreadable PRIMARY source for a lane degrades ONLY that
   lane's row to state='unknown' -- never an exception, never a blanked table. This
   is the property that matters most: a dark lane must still render (C7).
2. CLOSED ENUMS. Every row's `state` is in STATE_VALUES and `health` is in
   HEALTH_VALUES, always -- including the fail-open path.
3. window_pnl IS NEVER COMPUTED HERE. It is a number only when an existing summary
   file already states one; otherwise "n/a" -- even when raw per-row fields this
   module could sum are sitting right there in a ledger fixture.
4. THE FUTURES REGRESSION (found while building this module, 2026-09-13):
   analysis/futures/autopsy-latest.json is a list of DIFFERENT-EVIDENCE-CLASS
   reports (fills: BROKER / SIMULATED / UNKNOWN) from the same run, not a time
   series -- picking `[-1]` silently returned the near-empty UNKNOWN bucket over
   real broker evidence. Pinned so nobody "simplifies" this back to `[-1]`.
5. HOME.md carries exactly one '## Sectors' heading, and the CLI runs.

Also pinned: the row this module's own read corrected in gamma-wants.json --
the Kalshi SPY-index leg's credentials (.pem + secrets.json entry) already exist,
so the evidence text must say PRESENT, not MISSING, when the file is there.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECTOR_ROWS = REPO / "setup" / "scripts" / "sector_rows.py"
VAULT_SYNC = REPO / "setup" / "scripts" / "obsidian_vault_sync.py"

LANE_NAMES = (
    "SPY 0DTE core",
    "Crypto twin",
    "Futures",
    "Multi-symbol options",
    "Weekly options (GLD/QQQ)",
    "Tickers (non-SPY 0DTE)",
    "Kalshi (prediction markets)",
    "Station (local loop)",
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _sr(tmp_path):
    return _load(SECTOR_ROWS, f"sector_rows_{id(tmp_path)}")


def _ovs(tmp_path):
    return _load(VAULT_SYNC, f"obsidian_vault_sync_sectors_{id(tmp_path)}")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# --------------------------------------------------------------------- basics


def test_script_exists():
    assert SECTOR_ROWS.exists(), f"missing {SECTOR_ROWS}"


def test_build_sector_rows_returns_one_row_per_lane_on_a_bare_repo(tmp_path):
    """A completely empty repo (no state files at all) must never raise, and must
    still return one row per lane -- every one of them fail-open 'unknown'."""
    m = _sr(tmp_path)
    rows = m.build_sector_rows(tmp_path)
    assert len(rows) == len(LANE_NAMES)
    for row in rows:
        assert row["state"] in m.STATE_VALUES
        assert row["health"] in m.HEALTH_VALUES
        assert row["window_pnl"] == "n/a"


def test_missing_primary_source_names_the_path(tmp_path):
    m = _sr(tmp_path)
    rows = m.build_sector_rows(tmp_path)
    spy_row = next(r for r in rows if r["lane"] == "SPY 0DTE core")
    assert spy_row["state"] == "unknown"
    assert spy_row["health"] == "amber"
    assert spy_row["last_evidence_et"] == "unknown"
    assert "source missing:" in spy_row["evidence"]
    assert "accounts.json" in spy_row["evidence"]


def test_never_raises_even_if_a_source_file_is_garbage(tmp_path):
    m = _sr(tmp_path)
    garbage = tmp_path / "automation" / "state" / "fleet" / "accounts.json"
    garbage.parent.mkdir(parents=True, exist_ok=True)
    garbage.write_text("{not json at all", encoding="utf-8")
    rows = m.build_sector_rows(tmp_path)  # must not raise
    spy_row = next(r for r in rows if r["lane"] == "SPY 0DTE core")
    assert spy_row["state"] == "unknown"


# ------------------------------------------------------ fixture repo, 2 lanes


ACCOUNTS_FIXTURE = {
    "arms": [
        {"id": "safe-2", "instrument": "SPY_0DTE_OPTION", "status": "active"},
        {"id": "bold-2", "instrument": "SPY_0DTE_OPTION", "status": "active"},
        {"id": "safe-1", "instrument": "SPY_0DTE_OPTION", "status": "retired"},
        {"id": "weekly-1", "instrument": "WEEKLY_OPTION_MULTI", "status": "pending_build"},
    ]
}

GATE_FIXTURE = {
    "overall_verdict": "RED",
    "generated_et": "2026-09-03T14:43:34",
    "criteria": {
        "statistical": {
            "book_wide_correlated_rollup": {
                "as_traded": {"n_days": 42, "total_pnl": 2027.0}
            }
        }
    },
}


def test_fixture_repo_two_lanes_populated_rest_unknown(tmp_path):
    m = _sr(tmp_path)
    _write_json(tmp_path / "automation" / "state" / "fleet" / "accounts.json", ACCOUNTS_FIXTURE)
    _write_json(tmp_path / "analysis" / "go-live-gate.json", GATE_FIXTURE)
    _write_jsonl(
        tmp_path / "automation" / "state" / "crypto-twin" / "decisions.jsonl",
        [{"ts_et": "2026-09-13T17:37:51.575096", "action": "MANAGED"}],
    )
    _write_json(
        tmp_path / "automation" / "state" / "crypto-twin" / "challenger-h1-summary.json",
        {
            "h1_forward_start_utc": "2026-09-13T16:25:00+00:00",
            "windows": {"forward_since_start": {"control_n": 0, "control_net_usd": 0}},
        },
    )

    rows = m.build_sector_rows(tmp_path)
    by_lane = {r["lane"]: r for r in rows}

    spy = by_lane["SPY 0DTE core"]
    assert spy["state"] == "armed-paper"
    assert spy["health"] == "green"
    assert spy["arm_or_acct_alias"] == "safe-2, bold-2"  # retired + non-SPY arm excluded
    assert spy["window_pnl"] == 2027.0
    assert spy["last_evidence_et"] == "2026-09-03 14:43:34 ET"

    twin = by_lane["Crypto twin"]
    assert twin["state"] == "armed-paper"
    assert twin["last_evidence_et"] == "2026-09-13 17:37:51 ET"
    assert twin["window_pnl"] == 0.0
    assert "1 decisions rows" in twin["evidence"]

    for lane in LANE_NAMES:
        if lane in ("SPY 0DTE core", "Crypto twin"):
            continue
        assert by_lane[lane]["state"] == "unknown", f"{lane} should be unknown in this fixture"


def test_spy_core_alias_excludes_retired_and_non_spy_instrument(tmp_path):
    """The instrument+status filter is the point of _spy_core_row -- lock it down
    so a future accounts.json addition (another retired arm, another non-SPY lane)
    cannot silently leak into this lane's alias list."""
    m = _sr(tmp_path)
    _write_json(tmp_path / "automation" / "state" / "fleet" / "accounts.json", ACCOUNTS_FIXTURE)
    rows = m.build_sector_rows(tmp_path)
    spy = next(r for r in rows if r["lane"] == "SPY 0DTE core")
    assert "safe-1" not in spy["arm_or_acct_alias"]
    assert "weekly-1" not in spy["arm_or_acct_alias"]


# --------------------------------------------------------- window_pnl discipline


def test_multi_symbol_never_sums_raw_ledger_fields(tmp_path):
    """Regression guard for the module's own 'never computed from raw fills here'
    contract: even though the ledger rows below carry a `pnl` field this module
    COULD sum, window_pnl must stay 'n/a' -- multi-symbol has no summary file."""
    m = _sr(tmp_path)
    _write_jsonl(
        tmp_path / "automation" / "state" / "multi" / "shadow-ledger.jsonl",
        [
            {"ts_et": "2026-08-20T21:00:00-04:00", "symbol": "MRVL", "pnl": 40.0},
            {"ts_et": "2026-08-20T21:31:45-04:00", "symbol": "AVGO", "pnl": -15.0},
        ],
    )
    rows = m.build_sector_rows(tmp_path)
    multi = next(r for r in rows if r["lane"] == "Multi-symbol options")
    assert multi["state"] == "killed"
    assert multi["health"] == "zombie"
    assert multi["window_pnl"] == "n/a"
    assert multi["last_evidence_et"] == "2026-08-20 21:31:45 ET"


def test_futures_picks_the_broker_fills_entry_not_last_element(tmp_path):
    """THE regression this module's own build caught: autopsy-latest.json is 3
    different-evidence-class reports from ONE run, not a time series. Order the
    fixture UNKNOWN-last (matching the real file the day this bug was found) and
    assert window_pnl is the BROKER number, never the trailing $0 bucket."""
    m = _sr(tmp_path)
    _write_json(
        tmp_path / "automation" / "state" / "futures" / "health.json",
        {"verdict": "RED", "checked_at_et": "2026-09-13 17:00:02",
         "reasons": ["[RED] broker_exit_pairing: 2 unpaired ENTERs"]},
    )
    _write_json(
        tmp_path / "analysis" / "futures" / "autopsy-latest.json",
        [
            {"fills": "BROKER", "generated_at_et": "2026-09-11T16:52:01",
             "n_trips": 3, "total_pnl_usd": -93.75},
            {"fills": "SIMULATED", "generated_at_et": "2026-09-11T16:52:01",
             "n_trips": 11, "total_pnl_usd": -404.14},
            {"fills": "UNKNOWN", "generated_at_et": "2026-09-11T16:52:01",
             "n_trips": 0, "total_pnl_usd": 0.0},
        ],
    )
    rows = m.build_sector_rows(tmp_path)
    futures = next(r for r in rows if r["lane"] == "Futures")
    assert futures["window_pnl"] == -93.75
    assert futures["health"] == "red"
    assert "broker_exit_pairing" in futures["evidence"]
    assert "3 broker trip(s), real fills" in futures["evidence"]


def test_futures_health_color_mapping(tmp_path):
    m = _sr(tmp_path)
    for verdict, expected in (("GREEN", "green"), ("YELLOW", "amber"), ("RED", "red")):
        _write_json(
            tmp_path / "automation" / "state" / "futures" / "health.json",
            {"verdict": verdict, "checked_at_et": "2026-09-13 17:00:02", "reasons": []},
        )
        rows = m.build_sector_rows(tmp_path)
        futures = next(r for r in rows if r["lane"] == "Futures")
        assert futures["health"] == expected, verdict


# ------------------------------------------------------------------- kalshi


def test_kalshi_reports_pem_present_when_it_exists(tmp_path):
    """VERIFIED CORRECTION lock-in: the real repo's kalshi-1.pem + secrets.json
    entry have existed since 2026-08-09 -- this must never regress to claiming
    the key is missing just because the SPY-index leg is dark."""
    m = _sr(tmp_path)
    _write_jsonl(
        tmp_path / "automation" / "state" / "kalshi" / "weather-predictions.jsonl",
        [{"ts_utc": "2026-09-12T05:40:07.656145+00:00", "day": "2026-09-12"}],
    )
    _write_json(
        tmp_path / "automation" / "state" / "kalshi" / "last-tick.json",
        {"date": "2026-08-09"},
    )
    pem = tmp_path / "automation" / "state" / "fleet" / "kalshi-1.pem"
    pem.parent.mkdir(parents=True, exist_ok=True)
    pem.write_text("not a real key -- test fixture placeholder", encoding="utf-8")

    rows = m.build_sector_rows(tmp_path)
    kalshi = next(r for r in rows if r["lane"] == "Kalshi (prediction markets)")
    assert "credentials PRESENT since 08-09" in kalshi["evidence"]
    assert "credentials MISSING" not in kalshi["evidence"]
    assert kalshi["state"] == "shadow"
    assert kalshi["health"] == "amber"


def test_kalshi_reports_pem_missing_when_absent(tmp_path):
    m = _sr(tmp_path)
    _write_jsonl(
        tmp_path / "automation" / "state" / "kalshi" / "weather-predictions.jsonl",
        [{"ts_utc": "2026-09-12T05:40:07.656145+00:00", "day": "2026-09-12"}],
    )
    rows = m.build_sector_rows(tmp_path)
    kalshi = next(r for r in rows if r["lane"] == "Kalshi (prediction markets)")
    assert "credentials MISSING" in kalshi["evidence"]


# --------------------------------------------------------------------- CLI


def test_cli_print_runs_and_prints_header(tmp_path, capsys):
    m = _sr(tmp_path)
    rc = m.main(["--print"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "lane" in out and "health" in out
    for lane in LANE_NAMES:
        assert lane in out


def test_cli_json_flag_parses_and_matches_row_count(tmp_path, capsys):
    """GAMMA-HQ-VISUALS (2026-09-13): dashboard/lib/hq.ts shells `--json` and
    JSON.parses stdout directly -- this pins that the flag emits ONE valid JSON
    array (no table noise mixed in) with exactly one row per lane, matching
    build_sector_rows() called the same way (no repo_root override, i.e. the
    real repo)."""
    m = _sr(tmp_path)
    rc = m.main(["--json"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) == len(m.build_sector_rows()) == len(LANE_NAMES)
    for row in parsed:
        assert row["state"] in m.STATE_VALUES
        assert row["health"] in m.HEALTH_VALUES


# ------------------------------------------------- obsidian_vault_sync wiring


def test_render_sectors_table_has_one_heading_and_the_footer(tmp_path):
    m = _ovs(tmp_path)
    _write_json(tmp_path / "automation" / "state" / "fleet" / "accounts.json", ACCOUNTS_FIXTURE)
    _write_json(tmp_path / "analysis" / "go-live-gate.json", GATE_FIXTURE)

    out = m.render_sectors_table(repo_root=tmp_path)
    text = "\n".join(out)
    assert text.count("## Sectors") == 1
    assert "Rendered by sector_rows.py" in text
    assert "Station loop's first cards" in text
    assert "SPY 0DTE core" in text


def test_render_sectors_table_doc_link_missing_shows_alarm(tmp_path):
    """A lane whose `doc` path does not exist on disk must render the ⛔MISSING
    marker (mirrors the MAP_SPEC loop's own convention) instead of a silently
    dead wikilink."""
    m = _ovs(tmp_path)
    # No source files at all -> every lane is 'unknown' with doc='...' pointing at
    # real repo-relative doctrine paths that do not exist under tmp_path.
    out = m.render_sectors_table(repo_root=tmp_path)
    text = "\n".join(out)
    assert "⛔MISSING" in text


def test_render_sectors_table_never_raises_when_sector_rows_import_breaks(tmp_path, monkeypatch):
    """If sector_rows.py itself is broken/missing, this must degrade to the 'n/a'
    branch, never break HOME generation."""
    m = _ovs(tmp_path)
    import builtins

    real_import = builtins.__import__

    def _blow_up(name, *args, **kwargs):
        if name == "sector_rows":
            raise RuntimeError("simulated import failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blow_up)
    out = m.render_sectors_table(repo_root=tmp_path)
    text = "\n".join(out)
    assert "## Sectors" in text
    assert "n/a" in text


def test_build_home_carries_exactly_one_sectors_block(tmp_path, monkeypatch):
    m = _ovs(tmp_path)
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "JOURNAL", tmp_path)
    monkeypatch.setattr(m, "FLEET_DIR", tmp_path / "fleet")
    monkeypatch.setattr(m, "PNL_STATEMENT_PATH", tmp_path / "pnl-statement.json")
    monkeypatch.setattr(m, "PREREG_ANCHOR_CLASS_PATH", tmp_path / "does-not-exist.md")
    monkeypatch.setattr(m, "REPO", tmp_path)
    snap = {"ok": False, "arms": {}, "total_day": 0.0, "error": "offline test"}
    home = m.build_home("2026-09-13", "stamp", False, snap)
    assert home.count("## Sectors") == 1
