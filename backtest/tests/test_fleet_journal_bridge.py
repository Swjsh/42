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
    assert len(fjb.SCHEMA) == 43


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
