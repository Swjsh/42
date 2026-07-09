"""Guard: trade_today_watcher classify_orders (OP-33e 'did it trade' instrument, 2026-07-08)."""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def _load():
    for p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "trade_today_watcher", REPO / "setup" / "scripts" / "trade_today_watcher.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["trade_today_watcher"] = m
    spec.loader.exec_module(m)
    return m


def test_classify_filled_vs_unfilled_spy_only():
    w = _load()
    orders = [
        {"id": "1", "symbol": "SPY260708P00745000", "side": "buy", "filled_qty": "3", "filled_avg_price": "1.20", "status": "filled"},
        {"id": "2", "symbol": "SPY260708P00710000", "side": "buy", "filled_qty": "0", "filled_avg_price": None, "status": "canceled"},
        {"id": "3", "symbol": "BTC/USD", "side": "buy", "filled_qty": "0.001", "filled_avg_price": "63000", "status": "filled"},  # crypto -> ignore
        {"id": "4", "symbol": "AAPL", "side": "buy", "filled_qty": "10", "filled_avg_price": "200", "status": "filled"},          # stock -> ignore
    ]
    filled, unfilled = w.classify_orders(orders)
    assert len(filled) == 1 and filled[0]["symbol"] == "SPY260708P00745000" and filled[0]["qty"] == 3.0
    assert len(unfilled) == 1 and unfilled[0]["symbol"] == "SPY260708P00710000"
    syms = [x["symbol"] for x in filled + unfilled]
    assert "BTC/USD" not in syms and "AAPL" not in syms


def test_empty_and_none():
    w = _load()
    assert w.classify_orders([]) == ([], [])
    assert w.classify_orders(None) == ([], [])


def test_load_user_mention_reads_config(tmp_path, monkeypatch):
    """T3 (HANDOFF-2026-07-09): every prior fill ping (incl. FIRST ENGINE FILL EVER) lacked
    the <@user_id> mention token, so it likely never pushed to J's phone even though Discord
    accepted the message. Locks in the fix -- fail-open on a missing/malformed config."""
    w = _load()
    cfg = tmp_path / ".discord-config.json"
    cfg.write_text('{"user_id": "207983230618435584"}', encoding="utf-8")
    monkeypatch.setattr(w, "DISCORD_CFG", cfg)
    assert w._load_user_mention() == "<@207983230618435584> "


def test_load_user_mention_fails_open_on_missing_config(tmp_path, monkeypatch):
    w = _load()
    monkeypatch.setattr(w, "DISCORD_CFG", tmp_path / "missing.json")
    assert w._load_user_mention() == ""


# =============================================================================
# VISIBILITY (2026-07-09, OP-33c/STOP-B first-live-day): _structure_exit_label extends the
# EXISTING fill-ping composer so a fill's Discord message discloses "exit: structure@<level>"
# when the position is/was SS-B structure-stop managed. Two sources: the live exit-state
# ledger (ENTRY fill, still open) and the decision log's exit_pass history (EXIT fill,
# already pruned from the ledger by the SAME tick that closed it).
# =============================================================================
SYM = "SPY260709P00747000"


def test_structure_exit_label_entry_fill_reads_live_ledger(tmp_path, monkeypatch):
    """An ENTRY fill: the position is freshly registered, still IN exit-state.json."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    d = tmp_path / "fleet" / "safe-2"
    d.mkdir(parents=True)
    (d / "exit-state.json").write_text(
        json.dumps({SYM: {"stop_mode": "structure", "trigger_level": 747.41}}), encoding="utf-8")
    label = w._structure_exit_label("safe-2", SYM)
    assert label == " | exit: structure@747.41 (armed)"


def test_structure_exit_label_premium_position_is_silent(tmp_path, monkeypatch):
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    d = tmp_path / "fleet" / "safe-2"
    d.mkdir(parents=True)
    (d / "exit-state.json").write_text(
        json.dumps({SYM: {"stop_mode": "premium", "trigger_level": None}}), encoding="utf-8")
    assert w._structure_exit_label("safe-2", SYM) == ""


def test_structure_exit_label_exit_fill_falls_back_to_core_decisions(tmp_path, monkeypatch):
    """An EXIT fill: exit-state.json no longer carries the symbol (pruned the SAME tick the
    SELL_ALL fired) -- falls back to core-decisions.jsonl's exit_pass history (safe-2 is an
    mcp_heartbeat arm -> logs under account label 'safe')."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    (tmp_path / "fleet" / "safe-2").mkdir(parents=True)
    (tmp_path / "fleet" / "safe-2" / "exit-state.json").write_text("{}", encoding="utf-8")
    row = {"ts_et": "2026-07-09T11:05:00", "account": "safe",
           "exit_pass": [{"symbol": SYM, "trigger_level": 747.41,
                         "actions": [{"kind": "SELL_ALL", "stage": "structure_stop",
                                     "reason": "structure_stop @ 747.41"}]}]}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    label = w._structure_exit_label("safe-2", SYM)
    assert label == " | exit: structure@747.41"


def test_structure_exit_label_exit_fill_fleet_arm_uses_own_decisions_file(tmp_path, monkeypatch):
    """A fleet_rest arm (safe-1) logs to its OWN decisions.jsonl, not core-decisions.jsonl --
    and does NOT filter by an 'account' field (the fleet row has none)."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    d = tmp_path / "fleet" / "safe-1"
    d.mkdir(parents=True)
    (d / "exit-state.json").write_text("{}", encoding="utf-8")
    row = {"ts_et": "2026-07-09T11:05:00", "arm_id": "safe-1",
           "exit_pass": [{"symbol": SYM, "trigger_level": 747.41,
                         "actions": [{"kind": "SELL_ALL", "stage": "structure_stop"}]}]}
    (d / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert w._structure_exit_label("safe-1", SYM) == " | exit: structure@747.41"


def test_structure_exit_label_no_info_is_silent_not_crash(tmp_path, monkeypatch):
    """No exit-state.json, no decisions.jsonl at all -> '' , never raises (must never block
    or alter the fill ping itself)."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    assert w._structure_exit_label("safe-2", SYM) == ""


def test_structure_exit_label_wired_into_fill_message(tmp_path, monkeypatch):
    """RENDER-ONLY / reuse proof: main()'s existing composer calls _structure_exit_label and
    the suffix lands in the SAME message + SAME outbox path -- no new Discord path was built."""
    src = (Path(__file__).resolve().parents[2] / "setup" / "scripts" / "trade_today_watcher.py").read_text(encoding="utf-8")
    assert "_structure_exit_label(x[\"arm\"], x[\"symbol\"])" in src.replace("'", '"')
    assert src.count('OUTBOX.open("a"') == 1, \
        "must reuse the ONE existing outbox write, not add a second Discord path"
