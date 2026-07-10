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


# =============================================================================
# REHEARSAL-PROBE EXCLUSION (2026-07-10): Gamma_DressRehearsal's nightly ~20:45 ET broker-
# path probes (1-lot $0.01 deep-OTM, canceled <2s after submit) land inside the watcher's
# after=<ET-date>T00:00:00Z window (midnight UTC = 20:00 ET the PRIOR evening) and were
# counted as placed_not_filled -- 2 phantom "placed" on J's glance surface every morning.
# No client_order_id convention exists (the probe POSTs through the engine's own
# _place_simple_entry), so exclusion is by signature; EVERY leg must hold or the order
# stays REAL (fail toward J seeing more, never less).
# =============================================================================

# The REAL 2026-07-10 probe (canceled 0.16s after submit; 20:45 ET = 00:45Z), timestamps
# at nanosecond precision exactly as Alpaca returns them.
PROBE_713P = {
    "id": "83218f52-0f16-4195-b4cc-406e59eddb53",
    "client_order_id": "6a1f9b7c-3d2e-4c58-9f10-8be2a7c41d05",  # broker-generated, no convention
    "symbol": "SPY260710P00713000", "qty": "1", "limit_price": "0.01",
    "side": "buy", "type": "limit", "time_in_force": "day", "status": "canceled",
    "filled_qty": "0", "filled_avg_price": None,
    "submitted_at": "2026-07-10T00:45:03.163947456Z",
    "canceled_at": "2026-07-10T00:45:03.323512128Z",
}

# A genuine engine entry: 3-lot at a real premium, submitted 11:47 ET (inside RTH), filled.
REAL_ENTRY = {
    "id": "1f2e3d4c-5b6a-4789-a0b1-c2d3e4f50617",
    "symbol": "SPY260710C00748000", "qty": "3", "limit_price": "0.62",
    "side": "buy", "type": "limit", "time_in_force": "day", "status": "filled",
    "filled_qty": "3", "filled_avg_price": "0.61",
    "submitted_at": "2026-07-10T15:47:12.5Z", "canceled_at": None,
}


def test_rehearsal_probe_713p_excluded_real_entry_included():
    """End-to-end: the exact 713P probe shape never reaches J's counts; the real fill does."""
    w = _load()
    real, probes = w.split_rehearsal_probes([PROBE_713P, REAL_ENTRY])
    assert [p["id"] for p in probes] == [PROBE_713P["id"]]
    filled, unfilled = w.classify_orders(real)
    assert unfilled == []
    assert len(filled) == 1 and filled[0]["symbol"] == REAL_ENTRY["symbol"]


def test_real_unfilled_entry_still_counted():
    """A genuine placed-not-filled entry (sat at its limit, canceled by the 15:50 ET
    flatten ~108 min later) must stay on the glance surface."""
    w = _load()
    o = dict(REAL_ENTRY, id="real-unfilled", status="canceled", filled_qty="0",
             filled_avg_price=None, submitted_at="2026-07-10T18:02:00Z",
             canceled_at="2026-07-10T19:50:01Z")
    real, probes = w.split_rehearsal_probes([o])
    assert probes == [] and real == [o]
    filled, unfilled = w.classify_orders(real)
    assert filled == [] and len(unfilled) == 1 and unfilled[0]["id"] == "real-unfilled"


def test_probe_signature_legs_are_all_load_bearing():
    """Break each leg one at a time -> the order stays REAL (fail toward visibility)."""
    w = _load()
    variants = [
        # submitted 10:15 ET (inside RTH) -- probe shape alone must not hide an RTH order
        dict(PROBE_713P, submitted_at="2026-07-10T14:15:00.1Z",
             canceled_at="2026-07-10T14:15:00.3Z"),
        # canceled 30s after submit -- not the immediate probe cancel
        dict(PROBE_713P, canceled_at="2026-07-10T00:45:33.163947456Z"),
        dict(PROBE_713P, qty="3"),            # engine-sized
        dict(PROBE_713P, limit_price="0.85"),  # marketable premium
        dict(PROBE_713P, submitted_at=None),   # unparseable -> keep visible
        dict(PROBE_713P, canceled_at=None),    # never canceled -> keep visible
    ]
    for v in variants:
        real, probes = w.split_rehearsal_probes([v])
        assert probes == [] and real == [v], f"leg not load-bearing for: {v}"


def test_probe_detected_in_winter_est_too():
    """DST-aware: a 20:45 ET winter probe is 01:45Z (EST=-5) -- still outside RTH."""
    w = _load()
    v = dict(PROBE_713P, submitted_at="2026-01-15T01:45:03.1Z",
             canceled_at="2026-01-15T01:45:03.3Z")
    real, probes = w.split_rehearsal_probes([v])
    assert real == [] and len(probes) == 1


def test_split_empty_and_none():
    w = _load()
    assert w.split_rehearsal_probes([]) == ([], [])
    assert w.split_rehearsal_probes(None) == ([], [])


def test_rehearsal_probes_wired_into_main_and_artifact():
    """main() must split BEFORE classify and disclose probes under the rehearsal_probes key
    (transparency: excluded from the counts, never silently dropped)."""
    src = (Path(__file__).resolve().parents[2] / "setup" / "scripts" / "trade_today_watcher.py").read_text(encoding="utf-8")
    assert "split_rehearsal_probes(_fetch_orders(creds))" in src
    assert '"rehearsal_probes"' in src and '"rehearsal_probes_today"' in src
