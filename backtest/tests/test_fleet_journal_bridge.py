"""Guard tests for setup/scripts/fleet_journal_bridge.py (Rule-8 fleet journaling debt).

Covers: exact-schema row rendering (both the dict contract and the actual CSV bytes
written), end-to-end idempotency (a second run over the same fixtures appends zero
rows), the crypto/non-option exclusion, OCC symbol parsing, and a static AST guard
proving the bridge never imports a network/broker module or calls an order-mutating
function -- it is a pure local-file read/transform, never a second write path to the
broker (C1: fills/P&L truth stays broker_fills.py's job; this only journals it).

Pure-logic + tmp_path only -- no network, no live state touched.
"""
from __future__ import annotations

import ast
import csv
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_MODULE_PATH = REPO / "setup" / "scripts" / "fleet_journal_bridge.py"
_SPEC = importlib.util.spec_from_file_location("fleet_journal_bridge", _MODULE_PATH)
fjb = importlib.util.module_from_spec(_SPEC)
sys.modules["fleet_journal_bridge"] = fjb
_SPEC.loader.exec_module(fjb)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _round_trip(**overrides) -> dict:
    rt = {
        "arm": "risky-1", "symbol": "SPY260709C00750000",
        "entry_activity_id": "act-entry-1", "exit_activity_id": "act-exit-1",
        "entry_price": 0.49, "exit_price": 0.42, "qty": 5.0, "pnl": -35.0,
        "entry_ts_et": "2026-07-09T10:28:06.504328",
        "exit_ts_et": "2026-07-09T10:34:05.952098",
        "attribution": "engine", "date_et": "2026-07-09",
    }
    rt.update(overrides)
    return rt


def _entry_dec(**overrides) -> dict:
    row = {
        "ts_et": "2026-07-09T10:28:03.133615-04:00", "arm_id": "risky-1", "equity": 1536.29,
        "action": "ENTER_BULL", "side": "C", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "strike": 750, "qty": 5, "premium": 0.51, "quality": "ELITE", "risk_code": "ALLOW",
        "reason": "ribbon_ride C (ELITE)",
        "placement": {"mode": "LIVE", "symbol": "SPY260709C00750000", "entry_px": 0.54,
                      "stop": 0.41, "tp": 1.27, "broker": {"id": "order-entry-1"}},
        "_order_id": "order-entry-1",
    }
    row.update(overrides)
    return row


def _exit_info(**overrides) -> dict:
    info = {"stage": "premium_stop", "reason": "premium_stop @ 0.43", "_order_id": "order-exit-1"}
    info.update(overrides)
    return info


_ARM_META = {"cell": "risky x tight", "starting_equity": 2000.0}


# --------------------------------------------------------------------------- #
# schema-exact row rendering
# --------------------------------------------------------------------------- #
def test_build_row_has_exactly_the_canonical_columns():
    row = fjb.build_row(_round_trip(), _entry_dec(), _exit_info(), _ARM_META, fjb.PRIMARY_SOURCE_LABEL)
    assert row is not None
    assert set(row.keys()) == set(fjb.SCHEMA)
    # THETA-COCKPIT (2026-08-01): 43 -> 44, `theta_at_entry` appended at the END of SCHEMA
    # (never inserted mid-schema -- see SCHEMA's own comment on why that ordering is load-
    # bearing for every existing by-name CSV reader).
    assert len(fjb.SCHEMA) == 44
    assert fjb.SCHEMA[-1] == "theta_at_entry"


def test_build_row_field_values():
    row = fjb.build_row(_round_trip(), _entry_dec(), _exit_info(), _ARM_META, fjb.PRIMARY_SOURCE_LABEL)
    assert row["date"] == "2026-07-09"
    assert row["time_entry"] == "10:28:06"
    assert row["time_exit"] == "10:34:05"
    assert row["setup"] == "BULLISH_RECLAIM_RIDE_THE_RIBBON"
    assert row["contract"] == "SPY 2026-07-09 750C"
    assert row["dte"] == "0"
    assert row["strike"] == "750"
    assert row["c_or_p"] == "C"
    assert row["qty"] == "5"
    assert row["entry_px"] == "0.49"
    assert row["exit_px"] == "0.42"
    assert row["premium_paid"] == "245"    # 0.49 * 100 * 5
    assert row["premium_received"] == "210"  # 0.42 * 100 * 5
    assert row["dollar_pnl"] == "-35"
    assert row["dollar_risk"] == "245"
    assert row["account_equity_pre"] == "1536.29"     # live decision-time equity, not the static starting_equity
    assert row["stop_px"] == "0.41"
    assert row["target_px"] == "1.27"
    assert row["setup_quality"] == "ELITE"
    assert row["fill_quality"] == "real_fill"
    assert row["gamma_recommended"] == "Y"
    assert row["j_override"] == "N"
    assert row["followed_rules"] == "N/A"
    assert row["hold_minutes"] == "6"
    assert row["tod_bucket"] == "MORNING"
    assert row["account_id"] == "risky-1"
    assert "premium_stop" in row["notes_short"]
    assert "risky-1" in row["notes_short"]
    assert "ribbon_ride" in row["notes_short"]
    aj = json.loads(row["archetype_match_json"])
    assert aj["entry_order_id"] == "order-entry-1"
    assert aj["exit_order_id"] == "order-exit-1"


def test_build_row_missing_decision_context_never_drops_the_fill():
    """If the order-id join fails (e.g. decisions.jsonl was pruned), the round trip
    is still journaled -- honesty over completeness, never silently dropped."""
    row = fjb.build_row(_round_trip(), None, None, {}, fjb.PRIMARY_SOURCE_LABEL)
    assert row is not None
    assert row["setup"] == "UNKNOWN_FLEET_FILL"
    assert row["dollar_pnl"] == "-35"
    assert row["account_id"] == "risky-1"


def test_build_row_rejects_unparseable_symbol():
    assert fjb.build_row(_round_trip(symbol="BTC/USD"), None, None, {}, fjb.PRIMARY_SOURCE_LABEL) is None


def test_csv_bytes_match_header_by_name_not_position(tmp_path):
    """End-to-end proof: what actually lands in trades.csv, read back by column NAME,
    matches the built row -- not just the in-memory dict shape."""
    csv_path = tmp_path / "trades.csv"
    row = fjb.build_row(_round_trip(), _entry_dec(), _exit_info(), _ARM_META, fjb.PRIMARY_SOURCE_LABEL)
    fjb._append_rows(csv_path, [row])

    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        data_rows = list(reader)
    assert header == fjb.SCHEMA
    assert len(data_rows) == 1
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        parsed = list(csv.DictReader(fh))
    assert parsed[0]["setup"] == "BULLISH_RECLAIM_RIDE_THE_RIBBON"
    assert parsed[0]["dollar_pnl"] == "-35"
    assert parsed[0]["account_id"] == "risky-1"


def test_append_never_rewrites_existing_bytes(tmp_path):
    """Appending must not touch pre-existing (even non-canonically-quoted) lines."""
    csv_path = tmp_path / "trades.csv"
    csv_path.write_text(",".join(fjb.SCHEMA) + "\r\n"
                         "2026-05-01,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,pre-existing,safe\r\n",
                         encoding="utf-8")
    before = csv_path.read_bytes()
    row = fjb.build_row(_round_trip(), _entry_dec(), _exit_info(), _ARM_META, fjb.PRIMARY_SOURCE_LABEL)
    fjb._append_rows(csv_path, [row])
    after = csv_path.read_bytes()
    assert after.startswith(before)
    assert after != before  # the new row was in fact appended


# --------------------------------------------------------------------------- #
# crypto / non-option exclusion
# --------------------------------------------------------------------------- #
def test_is_option_excludes_crypto_and_short_symbols():
    assert fjb._is_option("SPY260709C00750000") is True
    assert fjb._is_option("BTC/USD") is False
    assert fjb._is_option("ETH/USD") is False
    assert fjb._is_option("SPY") is False


def test_parse_occ_symbol():
    parsed = fjb._parse_occ_symbol("SPY260709C00750000")
    assert parsed == {"root": "SPY", "expiry": "2026-07-09", "right": "C", "strike": 750.0}
    assert fjb._parse_occ_symbol("BTC/USD") is None
    parsed2 = fjb._parse_occ_symbol("SPY260709P00747500")
    assert parsed2["strike"] == 747.5
    assert parsed2["right"] == "P"


def test_primary_round_trips_excludes_crypto_and_other_arms(tmp_path):
    stmt = {
        "round_trips": [
            _round_trip(arm="risky-1", symbol="SPY260709C00750000"),
            _round_trip(arm="risky-1", symbol="BTC/USD", entry_activity_id="c1", exit_activity_id="c2"),
            _round_trip(arm="bold-2", symbol="SPY260709C00750000", entry_activity_id="b1", exit_activity_id="b2"),
        ]
    }
    p = tmp_path / "pnl-statement.json"
    p.write_text(json.dumps(stmt), encoding="utf-8")
    out = fjb._primary_round_trips(p, fjb.FLEET_REST_ARMS, None)
    assert len(out) == 1
    assert out[0]["arm"] == "risky-1"
    assert out[0]["symbol"] == "SPY260709C00750000"


# --------------------------------------------------------------------------- #
# end-to-end idempotency
# --------------------------------------------------------------------------- #
def _write_fixture_tree(tmp_path: Path) -> dict:
    state = tmp_path / "state"
    fleet = state / "fleet"
    arm_dir = fleet / "risky-1"
    arm_dir.mkdir(parents=True)
    journal = tmp_path / "journal"
    journal.mkdir()

    stmt = {"round_trips": [_round_trip()]}
    (state / "pnl-statement.json").write_text(json.dumps(stmt), encoding="utf-8")

    fills = [
        {"activity_id": "act-entry-1", "arm": "risky-1", "order_id": "order-entry-1"},
        {"activity_id": "act-exit-1", "arm": "risky-1", "order_id": "order-exit-1"},
    ]
    (state / "fills-ledger.jsonl").write_text(
        "\n".join(json.dumps(f) for f in fills) + "\n", encoding="utf-8")

    (fleet / "accounts.json").write_text(json.dumps({
        "arms": [{"id": "risky-1", "cell": "risky x tight", "starting_equity": 2000.0}]
    }), encoding="utf-8")

    decisions = [
        _entry_dec(),
        {
            "ts_et": "2026-07-09T10:34:05.952098-04:00", "arm_id": "risky-1",
            "exit_pass": [{"symbol": "SPY260709C00750000", "open_qty": 5, "actions": [
                {"kind": "SELL_ALL", "qty": 5, "stage": "premium_stop",
                 "reason": "premium_stop @ 0.43", "placed": True,
                 "broker": {"id": "order-exit-1"}},
            ]}],
        },
    ]
    (arm_dir / "decisions.jsonl").write_text(
        "\n".join(json.dumps(d) for d in decisions) + "\n", encoding="utf-8")

    return {
        "pnl_statement_path": state / "pnl-statement.json",
        "fills_ledger_path": state / "fills-ledger.jsonl",
        "fleet_dir": fleet,
        "accounts_json_path": fleet / "accounts.json",
        "trades_csv_path": journal / "trades.csv",
        "watermark_path": state / ".fleet-journal-watermark.json",
        "arms": ("risky-1",),
    }


def test_idempotent_double_run_writes_zero_new_rows_second_time(tmp_path):
    paths = _write_fixture_tree(tmp_path)

    first = fjb.run_bridge(**paths)
    assert first["n_written"] == 1
    assert first["per_arm"] == {"risky-1": 1}

    second = fjb.run_bridge(**paths)
    assert second["n_written"] == 0
    assert second["skipped_existing"] == 1

    with paths["trades_csv_path"].open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 2  # header + exactly one data row, not two


def test_dry_run_writes_nothing(tmp_path):
    paths = _write_fixture_tree(tmp_path)
    summary = fjb.run_bridge(dry_run=True, **paths)
    assert summary["n_written"] == 1
    assert not paths["trades_csv_path"].exists()
    assert not paths["watermark_path"].exists()


def test_date_filter_narrows_to_one_day(tmp_path):
    paths = _write_fixture_tree(tmp_path)
    summary = fjb.run_bridge(date_filter="2026-07-08", **paths)  # fixture round trip is 07-09
    assert summary["n_written"] == 0


# --------------------------------------------------------------------------- #
# static safety gate: pure local-file transform, never a second broker-write path
# --------------------------------------------------------------------------- #
_FORBIDDEN_MODULE_ROOTS = {
    "urllib", "requests", "http", "socket", "websocket",
    "fleet_broker", "alpaca", "alpaca_trade_api",
}
_FORBIDDEN_CALL_NAMES = {
    "place_order", "place_option_order", "place_stock_order", "place_crypto_order",
    "submit_order", "cancel_order", "cancel_order_by_id", "cancel_all_orders",
    "close_position", "close_all_positions", "replace_order_by_id",
    "exercise_options_position", "do_not_exercise_options_position", "create_locate",
}


def test_bridge_is_pure_local_file_transform_no_network_no_broker_calls():
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    seen_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            seen_imports.append(node.module)
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            assert name not in _FORBIDDEN_CALL_NAMES, f"forbidden order-mutating call: {name}"

    for mod in seen_imports:
        root = mod.split(".")[0]
        assert root not in _FORBIDDEN_MODULE_ROOTS, f"forbidden import touches broker/network: {mod}"


def test_run_bridge_signature_has_no_credential_or_network_params():
    import inspect
    params = set(inspect.signature(fjb.run_bridge).parameters)
    assert not (params & {"creds", "api_key", "secret", "session", "client"})


# =============================================================================
# CORE-ACCOUNT EXTENSION (2026-07-17, SAFE-TRADES-CSV-JOURNALING-GAP): safe-2/bold-2
# (mcp_heartbeat, execution=core) round trips in pnl-statement.json were NEVER bridged into
# trades.csv -- confirmed live on 2026-07-17 (a real +$105 bollinger_squeeze extra_exec fill
# reached the broker + Discord but never journal/trades.csv). broker_fills.py already
# computes correct engine/manual attribution for these arms; this extension just lets the
# bridge CONSUME that existing signal instead of hard-excluding safe-2/bold-2 by arm id.
# =============================================================================
def _core_round_trip(**overrides) -> dict:
    rt = {
        "arm": "safe-2", "symbol": "SPY260717P00744000",
        "entry_activity_id": "core-act-entry-1", "exit_activity_id": "core-act-exit-1",
        "entry_price": 1.41, "exit_price": 1.29, "qty": 3.0, "pnl": -37.0,
        "entry_ts_et": "2026-07-17T11:06:32.248844",
        "exit_ts_et": "2026-07-17T11:11:04.123456",
        "attribution": "engine", "date_et": "2026-07-17",
    }
    rt.update(overrides)
    return rt


def _core_exec_row(**overrides) -> dict:
    """A primary-path core-decisions.jsonl row (row["exec"])."""
    row = {
        "ts_et": "2026-07-17T11:06:03", "account": "safe",
        "reason": "BEARISH_REJECTION_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
        "exec": {
            "status": "PLACED", "symbol": "SPY260717P00744000", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
            "entry_px": 1.45, "stop": 0.725, "tp": 2.13, "equity": 1485.31,
            "broker": {"id": "core-order-entry-1"},
        },
        "exit_pass": [],
    }
    row.update(overrides)
    return row


def _core_exit_row(**overrides) -> dict:
    row = {
        "ts_et": "2026-07-17T11:11:03", "account": "safe",
        "exit_pass": [{"symbol": "SPY260717P00744000", "actions": [
            {"kind": "SELL_ALL", "stage": "structure_stop", "reason": "structure_stop @ 744.82",
             "placed": True, "broker": {"id": "core-order-exit-1"}},
        ]}],
    }
    row.update(overrides)
    return row


def test_core_arms_constant_maps_to_short_account_id():
    assert fjb.CORE_ARMS == {"safe-2": "safe", "bold-2": "bold"}
    assert fjb.ALL_BRIDGE_ARMS == fjb.FLEET_REST_ARMS + ("safe-2", "bold-2")


def test_build_core_decision_index_primary_path(tmp_path):
    p = tmp_path / "core-decisions.jsonl"
    p.write_text(json.dumps(_core_exec_row()) + "\n" + json.dumps(_core_exit_row()) + "\n",
                 encoding="utf-8")
    by_entry, by_exit = fjb._build_core_decision_index(p, "safe")
    assert by_entry["core-order-entry-1"]["setup_name"] == "BEARISH_REJECTION_RIDE_THE_RIBBON"
    assert by_entry["core-order-entry-1"]["quality"] == "ELITE"
    assert by_entry["core-order-entry-1"]["placement"]["stop"] == 0.725
    assert by_exit["core-order-exit-1"]["stage"] == "structure_stop"


def test_build_core_decision_index_extra_exec_path_same_shape_as_primary(tmp_path):
    """THE core proof: an extra_exec (G4 side-channel) fill normalizes into the EXACT SAME
    entry_dec shape a primary fill does -- identical downstream trades.csv treatment."""
    p = tmp_path / "core-decisions.jsonl"
    row = {
        "ts_et": "2026-07-17T14:03:03", "account": "safe",
        "reason": "no setup passed scoring (neither bear nor bull)",
        "extra_signals": [
            {"setup_name": "bollinger_squeeze", "fired": True, "confidence": "medium",
             "triggers": ["BB_SQUEEZE_RECENT", "BAND_BREAK_DOWN", "VOLUME_CONFIRM"]},
        ],
        "extra_exec": [{
            "setup": "bollinger_squeeze", "action": "PLACED",
            "exec": {"status": "PLACED", "symbol": "SPY260717P00745000", "setup": "bollinger_squeeze",
                     "entry_px": 1.01, "stop": 0.89, "tp": 1.26, "equity": 1675.83,
                     "broker": {"id": "core-order-bollinger-entry"}},
        }],
    }
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    by_entry, _ = fjb._build_core_decision_index(p, "safe")
    entry = by_entry["core-order-bollinger-entry"]
    assert entry["setup_name"] == "bollinger_squeeze"
    assert set(entry.keys()) >= {"setup_name", "quality", "reason", "placement", "equity", "_order_id"}
    assert "bollinger_squeeze" in entry["reason"]
    assert "BB_SQUEEZE_RECENT" in entry["reason"]
    assert entry["_via_extra_exec"] is True


def test_build_core_decision_index_filters_by_account(tmp_path):
    """A 'bold' row must never leak into a 'safe' index (and vice versa)."""
    p = tmp_path / "core-decisions.jsonl"
    row = _core_exec_row(account="bold")
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    by_entry, _ = fjb._build_core_decision_index(p, "safe")
    assert by_entry == {}
    by_entry_bold, _ = fjb._build_core_decision_index(p, "bold")
    assert "core-order-entry-1" in by_entry_bold


def test_primary_round_trips_excludes_manual_core_attribution(tmp_path):
    """THE double-journal guard: a core round trip attribution=='manual' (J-called, already
    journaled via the separate manual pathway) must NEVER be picked up here."""
    stmt = {"round_trips": [
        _core_round_trip(),
        _core_round_trip(symbol="SPY260717C00746000", attribution="manual",
                          entry_activity_id="manual-1", exit_activity_id="manual-2"),
    ]}
    p = tmp_path / "pnl-statement.json"
    p.write_text(json.dumps(stmt), encoding="utf-8")
    out = fjb._primary_round_trips(p, fjb.ALL_BRIDGE_ARMS, None)
    assert len(out) == 1
    assert out[0]["attribution"] == "engine"


def test_primary_round_trips_still_includes_fleet_manual_unfiltered():
    """Fleet_rest arms are 100% engine by broker_fills.py's own rule -- the manual-filter is
    CORE_ARMS-only and must not accidentally start dropping fleet rows tagged manual (which
    would itself be a bug elsewhere worth surfacing, not silently hiding)."""
    stmt = {"round_trips": [
        {"arm": "risky-1", "symbol": "SPY260709C00750000", "attribution": "manual",
         "date_et": "2026-07-09", "entry_activity_id": "e1", "exit_activity_id": "x1"},
    ]}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "pnl-statement.json"
        p.write_text(json.dumps(stmt), encoding="utf-8")
        out = fjb._primary_round_trips(p, fjb.FLEET_REST_ARMS, None)
    assert len(out) == 1


def test_build_row_core_arm_account_id_is_short_name():
    row = fjb.build_row(_core_round_trip(), None, None, {}, fjb.PRIMARY_SOURCE_LABEL)
    assert row["account_id"] == "safe"
    assert "CORE ACCOUNT safe-2" in row["notes_short"]
    assert "FLEET ARM" not in row["notes_short"]


def test_build_row_core_arm_bold_maps_to_bold():
    row = fjb.build_row(_core_round_trip(arm="bold-2"), None, None, {}, fjb.PRIMARY_SOURCE_LABEL)
    assert row["account_id"] == "bold"


def test_build_row_core_arm_preserves_fleet_notes_format_unchanged():
    """Non-regression: a fleet arm's build_row output must be byte-identical in shape to
    before this extension (guards the shared code path)."""
    row = fjb.build_row(_round_trip(), _entry_dec(), _exit_info(), _ARM_META, fjb.PRIMARY_SOURCE_LABEL)
    assert "FLEET ARM risky-1" in row["notes_short"]
    assert row["account_id"] == "risky-1"


def test_end_to_end_core_bridge_writes_row_with_correct_account_id_and_setup(tmp_path):
    """Full run_bridge() over a core-account fixture tree: proves the wiring (not just the
    unit pieces) -- a core round trip becomes a trades.csv row with account_id='safe' and
    the extra_exec setup name correctly attributed."""
    state = tmp_path / "state"
    journal = tmp_path / "journal"
    state.mkdir()
    journal.mkdir()
    (state / "pnl-statement.json").write_text(json.dumps({"round_trips": [
        {"arm": "safe-2", "symbol": "SPY260717P00745000",
         "entry_activity_id": "core-act-entry-b", "exit_activity_id": "core-act-exit-b",
         "entry_price": 1.00, "exit_price": 1.49, "qty": 3.0, "pnl": 105.0,
         "entry_ts_et": "2026-07-17T14:03:18.909912", "exit_ts_et": "2026-07-17T14:24:03.000000",
         "attribution": "engine", "date_et": "2026-07-17"},
    ]}), encoding="utf-8")
    (state / "fills-ledger.jsonl").write_text(
        json.dumps({"activity_id": "core-act-entry-b", "arm": "safe-2", "order_id": "core-order-b-entry"}) + "\n"
        + json.dumps({"activity_id": "core-act-exit-b", "arm": "safe-2", "order_id": "core-order-b-exit"}) + "\n",
        encoding="utf-8")
    (state / "core-decisions.jsonl").write_text(
        json.dumps({
            "ts_et": "2026-07-17T14:03:03", "account": "safe",
            "reason": "no setup passed scoring (neither bear nor bull)",
            "extra_signals": [{"setup_name": "bollinger_squeeze", "fired": True,
                               "confidence": "medium", "triggers": ["BB_SQUEEZE_RECENT"]}],
            "extra_exec": [{"setup": "bollinger_squeeze", "action": "PLACED",
                            "exec": {"status": "PLACED", "symbol": "SPY260717P00745000",
                                     "setup": "bollinger_squeeze", "entry_px": 1.01, "stop": 0.89,
                                     "tp": 1.26, "equity": 1675.83,
                                     "broker": {"id": "core-order-b-entry"}}}],
        }) + "\n"
        + json.dumps({
            "ts_et": "2026-07-17T14:24:03", "account": "safe",
            "exit_pass": [{"symbol": "SPY260717P00745000", "actions": [
                {"kind": "SELL_ALL", "stage": "trail", "reason": "runner_stop @ 1.49",
                 "placed": True, "broker": {"id": "core-order-b-exit"}}]}],
        }) + "\n",
        encoding="utf-8")
    (state / "fleet").mkdir()
    (state / "fleet" / "accounts.json").write_text(json.dumps({"arms": []}), encoding="utf-8")

    summary = fjb.run_bridge(
        pnl_statement_path=state / "pnl-statement.json",
        fills_ledger_path=state / "fills-ledger.jsonl",
        fleet_dir=state / "fleet",
        accounts_json_path=state / "fleet" / "accounts.json",
        core_decisions_path=state / "core-decisions.jsonl",
        trades_csv_path=journal / "trades.csv",
        watermark_path=state / ".fleet-journal-watermark.json",
        arms=("safe-2",),
    )
    assert summary["n_written"] == 1
    row = summary["rows"][0]
    assert row["account_id"] == "safe"
    assert row["setup"] == "bollinger_squeeze"
    assert row["dollar_pnl"] == "105"
    assert "G4 extra-setup side-channel" in row["notes_short"]

    with (journal / "trades.csv").open(encoding="utf-8-sig", newline="") as fh:
        parsed = list(csv.DictReader(fh))
    assert len(parsed) == 1
    assert parsed[0]["account_id"] == "safe"


# --------------------------------------------------------------------------- #
# THETA-COCKPIT (2026-08-01): delta/iv/theta_at_entry sourcing + schema migration
# --------------------------------------------------------------------------- #
def test_greeks_at_entry_prefers_broker_snapshot_over_fallback():
    entry_dec = {"greeks": {"delta": -0.42, "iv": 0.187, "theta": -0.55}}
    fallback = {"entry_delta": -0.99, "entry_iv": 0.99, "entry_theta": -0.99}
    out = fjb._greeks_at_entry(entry_dec, fallback)
    assert out["delta_at_entry"] == -0.42
    assert out["iv_at_entry"] == 0.187
    assert out["theta_at_entry"] == -0.55
    assert out["_sources"]["delta"].startswith("broker_snapshot")


def test_greeks_at_entry_falls_back_to_theta_clock_when_broker_greeks_empty():
    """The empirically-common case (G8's own capture returned {} on 29/29 real entries
    checked before this build) -- must fall back cleanly, not blank out."""
    entry_dec = {"greeks": {}}
    fallback = {"entry_delta": -0.35, "entry_iv": 0.21, "entry_theta": -0.44}
    out = fjb._greeks_at_entry(entry_dec, fallback)
    assert out["delta_at_entry"] == -0.35
    assert out["iv_at_entry"] == 0.21
    assert out["theta_at_entry"] == -0.44
    assert out["_sources"]["delta"] == "theta_clock_first_observation (~1min-of-fill fallback)"


def test_greeks_at_entry_blank_when_neither_source_has_data():
    """NEVER fabricates -- both sources missing means every field stays the SAME blank ""
    every other unpopulated cell in this schema already uses."""
    out = fjb._greeks_at_entry({}, None)
    assert out["delta_at_entry"] == "" and out["iv_at_entry"] == "" and out["theta_at_entry"] == ""


def test_greeks_at_entry_per_field_independent_fallback():
    """Mixed case: broker snapshot has delta but not theta -- each field resolves
    independently, not all-or-nothing."""
    entry_dec = {"greeks": {"delta": -0.40}}
    fallback = {"entry_delta": -0.99, "entry_theta": -0.50}
    out = fjb._greeks_at_entry(entry_dec, fallback)
    assert out["delta_at_entry"] == -0.40  # broker wins
    assert out["theta_at_entry"] == -0.50  # falls back per-field
    assert out["iv_at_entry"] == ""        # neither source has it


def test_build_row_wires_theta_clock_entry_through():
    row = fjb.build_row(_round_trip(), _entry_dec(), _exit_info(), _ARM_META,
                         fjb.PRIMARY_SOURCE_LABEL,
                         theta_clock_entry={"entry_delta": 0.55, "entry_iv": 0.19, "entry_theta": -0.61})
    assert row["delta_at_entry"] == 0.55
    assert row["iv_at_entry"] == 0.19
    assert row["theta_at_entry"] == -0.61


def test_build_row_theta_clock_entry_defaults_none_byte_identical(tmp_path):
    """Every PRE-EXISTING call site (no theta_clock_entry kwarg) must render byte-identical
    to before this change -- default-None is truly inert when the fallback isn't supplied."""
    row = fjb.build_row(_round_trip(), _entry_dec(), _exit_info(), _ARM_META, fjb.PRIMARY_SOURCE_LABEL)
    assert row["delta_at_entry"] == "" and row["iv_at_entry"] == "" and row["theta_at_entry"] == ""


# --------------------------------------------------------------------------- #
# schema header migration
# --------------------------------------------------------------------------- #
def test_ensure_schema_header_migrates_old_43col_file(tmp_path):
    csv_path = tmp_path / "trades.csv"
    old_schema = fjb.SCHEMA[:-1]  # everything except the new theta_at_entry column
    old_row = ["x"] * len(old_schema)
    csv_path.write_text(",".join(old_schema) + "\n" + ",".join(old_row) + "\n", encoding="utf-8-sig")

    changed = fjb._ensure_schema_header(csv_path)
    assert changed is True

    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        lines = fh.readlines()
    new_header = next(csv.reader([lines[0]]))
    assert new_header == fjb.SCHEMA
    # the OLD data row is untouched byte-for-byte (still 43 raw values on that line) --
    # DictReader fills the new trailing column with None for it, never misaligns.
    assert lines[1].strip() == ",".join(old_row)
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        parsed = list(csv.DictReader(fh))
    assert parsed[0]["theta_at_entry"] is None
    assert parsed[0]["date"] == "x"  # first column still aligned correctly


def test_ensure_schema_header_idempotent_second_call_is_noop(tmp_path):
    csv_path = tmp_path / "trades.csv"
    old_schema = fjb.SCHEMA[:-1]
    csv_path.write_text(",".join(old_schema) + "\n" + ",".join(["x"] * len(old_schema)) + "\n",
                         encoding="utf-8-sig")
    assert fjb._ensure_schema_header(csv_path) is True
    before = csv_path.read_bytes()
    assert fjb._ensure_schema_header(csv_path) is False  # already migrated -> no-op
    assert csv_path.read_bytes() == before  # byte-identical, no needless rewrite


def test_ensure_schema_header_noop_on_missing_or_empty_file(tmp_path):
    missing = tmp_path / "does-not-exist.csv"
    assert fjb._ensure_schema_header(missing) is False
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert fjb._ensure_schema_header(empty) is False


def test_ensure_schema_header_already_current_is_noop(tmp_path):
    csv_path = tmp_path / "trades.csv"
    csv_path.write_text(",".join(fjb.SCHEMA) + "\n" + ",".join(["x"] * len(fjb.SCHEMA)) + "\n",
                         encoding="utf-8-sig")
    assert fjb._ensure_schema_header(csv_path) is False


def test_run_bridge_end_to_end_falls_back_to_theta_clock_position_state(tmp_path):
    """Full wiring proof: a fleet_rest arm (no G8 greeks path at all) picks up its
    delta/iv/theta_at_entry from a synthetic theta-clock position-state.json fixture, and the
    value survives all the way into the written trades.csv row."""
    state = tmp_path / "state"
    journal = tmp_path / "journal"
    state.mkdir()
    journal.mkdir()
    (state / "fleet").mkdir()
    (state / "fleet" / "safe-3").mkdir()

    (state / "pnl-statement.json").write_text(json.dumps({"round_trips": [_round_trip()]}), encoding="utf-8")
    (state / "fills-ledger.jsonl").write_text(
        json.dumps({"arm": "safe-1_unused", "activity_id": "x", "order_id": "y"}) + "\n", encoding="utf-8")
    (state / "fleet" / "accounts.json").write_text(json.dumps({"arms": []}), encoding="utf-8")
    (state / "fleet" / "safe-3" / "decisions.jsonl").write_text("", encoding="utf-8")
    (state / "theta-clock").mkdir()
    (state / "theta-clock" / "position-state.json").write_text(json.dumps({
        "positions": {
            "risky-1::SPY260709C00750000": {
                "entry_delta": 0.61, "entry_iv": 0.205, "entry_theta": -0.72,
            }
        }
    }), encoding="utf-8")

    summary = fjb.run_bridge(
        pnl_statement_path=state / "pnl-statement.json",
        fills_ledger_path=state / "fills-ledger.jsonl",
        fleet_dir=state / "fleet",
        accounts_json_path=state / "fleet" / "accounts.json",
        core_decisions_path=state / "core-decisions.jsonl",
        trades_csv_path=journal / "trades.csv",
        watermark_path=state / ".fleet-journal-watermark.json",
        theta_clock_position_state_path=state / "theta-clock" / "position-state.json",
        arms=("risky-1",),
    )
    assert summary["n_written"] == 1
    row = summary["rows"][0]
    assert row["delta_at_entry"] == 0.61
    assert row["iv_at_entry"] == 0.205
    assert row["theta_at_entry"] == -0.72

    with (journal / "trades.csv").open(encoding="utf-8-sig", newline="") as fh:
        parsed = list(csv.DictReader(fh))
    assert parsed[0]["theta_at_entry"] == "-0.72"
