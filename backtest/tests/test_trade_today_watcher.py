"""Guard: trade_today_watcher classify_orders (OP-33e 'did it trade' instrument, 2026-07-08)."""
from __future__ import annotations
import importlib.util, json, shutil, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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


def test_engine_attributed_true_when_exec_symbol_matches(tmp_path, monkeypatch):
    """2026-07-16 fix: a fill with a matching exec.symbol in core-decisions.jsonl IS
    engine-attributed."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    row = {"ts_et": "2026-07-16T13:56:36", "account": "safe",
           "exec": {"status": "FILLED", "symbol": SYM}}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert w._is_engine_attributed("safe-2", SYM) is True


def test_engine_attributed_true_via_extra_exec_2026_07_16_incident(tmp_path, monkeypatch):
    """This is the exact real-world case that motivated the fix, corrected same-day: a real
    fill (SPY260716P00751000) placed via the extra-setup G4 side-channel (vwap_continuation,
    exec-armed) logs under row["extra_exec"][i]["exec"], NOT the primary row["exec"] dict.
    The first version of this function only checked the primary path and wrongly returned
    False here -- caught when J said "I did not do anything today," forcing re-investigation.

    SANDBOXED 2026-08-15. This ran against the LIVE core-decisions.jsonl until it started
    failing -- not because attribution broke, but because `_decision_rows_for_arm` reads a
    BOUNDED TAIL (2000 lines) and that ledger grew to 27,335 rows. The July-16 rows sit at
    index ~11,124, i.e. 14k lines outside the window. Production is UNAFFECTED: a fill is
    pinged the same day it happens, always inside the tail. Only a test asserting on a
    months-old incident could age out. The real rows are frozen verbatim in
    fixtures/attribution-2026-07-16-core.jsonl -- which also RESCUES them, since the live
    ledger will eventually drop them entirely."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    shutil.copy(FIXTURES / "attribution-2026-07-16-core.jsonl",
                tmp_path / "core-decisions.jsonl")
    assert w._is_engine_attributed("safe-2", "SPY260716P00751000") is True


def test_engine_attributed_true_via_extra_exec_fixture(tmp_path, monkeypatch):
    """Fixture-based companion to the real-incident pin above -- proves the extra_exec
    branch itself, independent of the live state file's future contents."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    row = {"ts_et": "2026-07-16T09:51:03", "account": "safe",
           "extra_exec": [{"setup": "vwap_continuation", "action": "PLACED",
                           "exec": {"status": "PLACED", "symbol": SYM}}]}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert w._is_engine_attributed("safe-2", SYM) is True


def test_engine_attributed_false_when_extra_exec_is_vetoed(tmp_path, monkeypatch):
    """A VETOED_BY_MODELS extra_exec row has no nested "exec" dict (the free-model veto
    blocked it before placement) -- must stay unattributed, not crash."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    row = {"ts_et": "2026-07-16T09:54:04", "account": "safe",
           "extra_exec": [{"setup": "vwap_continuation", "action": "VETOED_BY_MODELS",
                           "free_eval": {"veto": True}}]}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert w._is_engine_attributed("safe-2", SYM) is False


def test_engine_attributed_false_on_missing_file(tmp_path, monkeypatch):
    """Fail-open: no core-decisions.jsonl at all -> False, never raises."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    assert w._is_engine_attributed("safe-2", SYM) is False


# =============================================================================
# FLEET-ARM ATTRIBUTION (2026-07-17 fix, analysis/daily-brief/2026-07-17-fleet-attribution-
# audit.md): fleet_rest arms (safe-1/safe-3/risky-1/risky-3) write a completely different
# decisions.jsonl schema than the core heartbeat -- action=ENTER_BEAR/ENTER_BULL +
# placement.broker for entries, exit_pass[].actions[].broker for exits -- and NEVER carry
# an "exec"/"extra_exec" key. _is_engine_attributed only checked those core-only keys, so
# EVERY fleet-arm fill was unconditionally mislabeled UNATTRIBUTED regardless of a real,
# complete decision row existing. Same anti-pattern class as the 07-16 exec/extra_exec fix,
# recurring in the sibling branch that fix never touched.
# =============================================================================
FLEET_SYM = "SPY260717P00741000"


def test_engine_attributed_true_for_fleet_arm_enter_row(tmp_path, monkeypatch):
    """A fleet_rest ENTER_BEAR row (placement.broker.symbol) IS engine-attributed."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    d = tmp_path / "fleet" / "risky-3"
    d.mkdir(parents=True)
    row = {"ts_et": "2026-07-17T11:07:02", "arm_id": "risky-3", "action": "ENTER_BEAR",
           "placement": {"broker": {"symbol": FLEET_SYM, "id": "2951f12e"}}}
    (d / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert w._is_engine_attributed("risky-3", FLEET_SYM) is True


def test_engine_attributed_true_for_fleet_arm_exit_row(tmp_path, monkeypatch):
    """A fleet_rest exit_pass row with a placed action (actions[].broker) IS
    engine-attributed, even with no "exec" key anywhere in the row."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    d = tmp_path / "fleet" / "risky-3"
    d.mkdir(parents=True)
    row = {"ts_et": "2026-07-17T11:13:01", "arm_id": "risky-3", "action": "HOLD",
           "exit_pass": [{"symbol": FLEET_SYM, "actions": [
               {"kind": "SELL_ALL", "stage": "structure_stop", "broker": {"id": "8c874be4"}}]}]}
    (d / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert w._is_engine_attributed("risky-3", FLEET_SYM) is True


def test_engine_attributed_false_for_fleet_arm_monitoring_tick_no_actions(tmp_path, monkeypatch):
    """A fleet_rest HOLD tick that is just monitoring an OPEN position (exit_pass present,
    actions empty -- no order placed this tick) must stay unattributed for THIS symbol/tick,
    not spuriously match on the mere presence of exit_pass. Guards against a fix that makes
    everything true."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    d = tmp_path / "fleet" / "risky-3"
    d.mkdir(parents=True)
    row = {"ts_et": "2026-07-17T11:10:03", "arm_id": "risky-3", "action": "HOLD",
           "exit_pass": [{"symbol": FLEET_SYM, "actions": []}]}
    (d / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert w._is_engine_attributed("risky-3", FLEET_SYM) is False


def test_engine_attributed_true_via_real_risky3_2026_07_17_incident(tmp_path, monkeypatch):
    """The exact real-world incident that motivated this fix: risky-3 filled 5 real broker
    orders on 2026-07-17 (+$248 realized) and every single one pinged Discord as
    "UNATTRIBUTED FILL (no matching decision row)" despite a complete ENTER_BEAR +
    exit_pass trail existing in automation/state/fleet/risky-3/decisions.jsonl.

    SANDBOXED 2026-08-15, same cause as the 07-16 pin above: risky-3's ledger grew to 7,306
    rows and the July-17 rows sit at index 2,236 -- outside the 2000-line tail
    `_decision_rows_for_arm` reads. The attribution logic never regressed; the evidence
    scrolled past the window. Frozen verbatim (both ENTER_BEARs + the full exit_pass trail)
    in fixtures/attribution-2026-07-17-risky3.jsonl."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    d = tmp_path / "fleet" / "risky-3"
    d.mkdir(parents=True)
    shutil.copy(FIXTURES / "attribution-2026-07-17-risky3.jsonl", d / "decisions.jsonl")
    assert w._is_engine_attributed("risky-3", "SPY260717P00741000") is True   # ENTER_BEAR entry
    assert w._is_engine_attributed("risky-3", "SPY260717P00743000") is True   # 2nd ENTER_BEAR + exits


def test_unattributed_fleet_fill_label_wired_into_message_before_fix_reproduced(tmp_path, monkeypatch):
    """End-to-end proof the label is actually wired for a fleet arm (not just the helper):
    a fleet-arm fill WITH a real matching ENTER row must say ENGINE TRADE, not UNATTRIBUTED --
    this is the exact end-to-end shape (main() -> _is_engine_attributed -> outbox message)
    that silently mislabeled 13/13 real fleet fills on 2026-07-17 before this fix."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    monkeypatch.setattr(w, "TRADE_TODAY", tmp_path / "trade-today.json")
    monkeypatch.setattr(w, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(w, "PINGED", tmp_path / "pinged.json")
    monkeypatch.setattr(w, "LIFETIME", tmp_path / "lifetime.json")
    d = tmp_path / "fleet" / "risky-3"
    d.mkdir(parents=True)
    row = {"ts_et": "2026-07-17T11:07:02", "arm_id": "risky-3", "action": "ENTER_BEAR",
           "placement": {"broker": {"symbol": FLEET_SYM, "id": "2951f12e"}}}
    (d / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"risky-3": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "2951f12e", "symbol": FLEET_SYM, "qty": 5, "price": 0.46, "side": "buy",
         "status": "filled", "filled_at": "2026-07-17T15:07:06Z"}])
    monkeypatch.setattr(w, "split_rehearsal_probes", lambda orders: (orders, []))
    monkeypatch.setattr(w, "classify_orders", lambda orders: (orders, []))
    monkeypatch.setattr(w, "_load_user_mention", lambda: "")
    w.main()
    content = (tmp_path / "discord-outbox.jsonl").read_text(encoding="utf-8")
    assert "ENGINE TRADE [risky-3" in content  # arm label may carry a "FLEET-LOOSE-R (X15Q)" nickname suffix
    assert "UNATTRIBUTED FILL" not in content


def test_unattributed_fill_label_wired_into_message(tmp_path, monkeypatch):
    """The ping message itself must say UNATTRIBUTED, not ENGINE TRADE, when no exec
    row matches -- proves the label is actually wired, not just the helper function.

    FORMAT CHANGE 2026-08-17 (J: the old single-line pipe-concatenated ping was "just
    gibberish"/"I cannot read them" -- ratified bulleted-message rewrite in
    trade_today_watcher.main()): the old "UNATTRIBUTED FILL (no matching decision row)"
    text moved off line 1 into its own bullet ("UNATTRIBUTED [<arm>]" headline + a
    "no matching decision row" bullet, per J's "it can move to a bullet"). Pin updated
    deliberately to the new format, not weakened."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    monkeypatch.setattr(w, "TRADE_TODAY", tmp_path / "trade-today.json")
    monkeypatch.setattr(w, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(w, "PINGED", tmp_path / "pinged.json")
    monkeypatch.setattr(w, "LIFETIME", tmp_path / "lifetime.json")
    (tmp_path / "fleet" / "safe-2").mkdir(parents=True)
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"safe-2": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "ord1", "symbol": SYM, "qty": 3, "price": 1.22, "side": "buy",
         "status": "filled", "filled_at": "2026-07-16T13:51:29Z"}])
    monkeypatch.setattr(w, "split_rehearsal_probes", lambda orders: (orders, []))
    monkeypatch.setattr(w, "classify_orders", lambda orders: (orders, []))
    monkeypatch.setattr(w, "_load_user_mention", lambda: "")
    (tmp_path / "core-decisions.jsonl").write_text("", encoding="utf-8")
    w.main()
    content = (tmp_path / "discord-outbox.jsonl").read_text(encoding="utf-8")
    assert "UNATTRIBUTED [safe-2]" in content
    assert "no matching decision row" in content
    assert "ENGINE TRADE [" not in content


def test_attributed_fill_label_wired_into_message(tmp_path, monkeypatch):
    """Mirror of the unattributed test above, proving the ENGINE TRADE label still fires
    correctly (via extra_exec) when the fill IS attributed -- guards against a fix that
    makes everything say UNATTRIBUTED."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    monkeypatch.setattr(w, "TRADE_TODAY", tmp_path / "trade-today.json")
    monkeypatch.setattr(w, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(w, "PINGED", tmp_path / "pinged.json")
    monkeypatch.setattr(w, "LIFETIME", tmp_path / "lifetime.json")
    (tmp_path / "fleet" / "safe-2").mkdir(parents=True)
    row = {"ts_et": "2026-07-16T09:51:03", "account": "safe",
           "extra_exec": [{"setup": "vwap_continuation", "action": "PLACED",
                           "exec": {"status": "PLACED", "symbol": SYM}}]}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"safe-2": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "ord2", "symbol": SYM, "qty": 3, "price": 1.22, "side": "buy",
         "status": "filled", "filled_at": "2026-07-16T13:51:29Z"}])
    monkeypatch.setattr(w, "split_rehearsal_probes", lambda orders: (orders, []))
    monkeypatch.setattr(w, "classify_orders", lambda orders: (orders, []))
    monkeypatch.setattr(w, "_load_user_mention", lambda: "")
    w.main()
    content = (tmp_path / "discord-outbox.jsonl").read_text(encoding="utf-8")
    assert "ENGINE TRADE [" in content
    assert "UNATTRIBUTED FILL" not in content


def test_structure_exit_label_wired_into_fill_message(tmp_path, monkeypatch):
    """RENDER-ONLY / reuse proof, updated for the 2026-08-17 bulleted-format ship: main()'s
    composer now reads exit-state.json via _position_exit_info (NOT _structure_exit_label
    -- see that function's docstring for why: reusing _structure_exit_label's EXIT-fill
    decision-log fallback for the new stop bullet would attach a stale/misleading
    "(armed)" structure label to a TP1 partial-sell that didn't actually stop out).
    _structure_exit_label itself is UNCHANGED and still directly unit-tested above (5
    tests); this test instead proves _position_exit_info/_stop_bullet are the ones
    actually wired into the ONE real outbox write -- same reuse-not-duplicate guarantee,
    updated call site."""
    src = (Path(__file__).resolve().parents[2] / "setup" / "scripts" / "trade_today_watcher.py").read_text(encoding="utf-8")
    assert "_position_exit_info(arm_id, symbol)" in src.replace("'", '"')
    assert "_stop_bullet(pos)" in src
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


# =============================================================================
# CROSS-ARM ORDER-ID DEDUP (2026-07-17, task_32d96df3): fleet/secrets.json can carry two+
# credential labels resolved to the SAME broker account (safe-1/safe-2 both -> PA3DHPT7KIQE
# post the 2026-07-11 repoint). load_creds() has no accounts.json status awareness, so both
# labels get polled and every core-Safe fill/order was counted TWICE (46 rows vs 31 unique
# order ids, live-confirmed). Port of accounts_status.py's shared-account dedup workaround,
# generalized to dedup by ALPACA ORDER ID (self-heals for any future credential collision,
# not just this one pair).
# =============================================================================
DUP_ORDER = {"id": "dup-order-1", "symbol": "SPY260717P00745000", "side": "buy",
             "status": "filled", "filled_qty": "3", "filled_avg_price": "1.00",
             "filled_at": "2026-07-17T18:03:18Z"}


def test_dedup_by_order_id_drops_repeat_across_calls():
    """RED-PROOF: without dedup, the SAME order id fetched under two arms would append
    twice. _dedup_by_order_id must keep only the first occurrence across calls sharing one
    seen_ids set (mirrors how main() threads seen_order_ids across the arm loop)."""
    w = _load()
    seen: set = set()
    first_pass = w._dedup_by_order_id([dict(DUP_ORDER)], seen)
    second_pass = w._dedup_by_order_id([dict(DUP_ORDER)], seen)  # same id, "different arm" fetch
    assert len(first_pass) == 1
    assert len(second_pass) == 0, "duplicate order id from a second credential label must be dropped"


def test_dedup_by_order_id_keeps_distinct_ids():
    w = _load()
    seen: set = set()
    a = w._dedup_by_order_id([{"id": "order-a"}], seen)
    b = w._dedup_by_order_id([{"id": "order-b"}], seen)
    assert len(a) == 1 and len(b) == 1


def test_dedup_by_order_id_passes_through_missing_id():
    """A record with no id (defensive -- should not happen for a real Alpaca order) must
    never be silently dropped just because dedup can't key it."""
    w = _load()
    seen: set = set()
    out = w._dedup_by_order_id([{"symbol": "SPY260717P00745000"}], seen)
    assert len(out) == 1


# =============================================================================
# EXIT-PROFILE COLUMN (2026-07-20, J directive: "one gets stopped out on the ribbon, one
# plays the rejection outside the ribbon, one rides it better" -- exit_patch A/B build).
# accounts.json's per-arm "exit_profile" field (RIBBON/TRIG-EXACT/ZONE-RIDE/CORE) is read
# by _exit_profile_for_arm and threaded into both trade-today.json's fill records and the
# Discord fill ping, so "which exit banked this fill" answers itself without J asking.
# =============================================================================
def test_exit_profile_for_arm_reads_accounts_json(tmp_path, monkeypatch):
    w = _load()
    accounts = {"arms": [
        {"id": "safe-3", "exit_profile": "RIBBON"},
        {"id": "risky-1", "exit_profile": "TRIG-EXACT"},
        {"id": "no-label-arm"},
    ]}
    (tmp_path / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
    monkeypatch.setattr(w, "ACCOUNTS_PATH", tmp_path / "accounts.json")
    monkeypatch.setattr(w, "_ARM_EXIT_PROFILE_CACHE", None)
    assert w._exit_profile_for_arm("safe-3") == "RIBBON"
    assert w._exit_profile_for_arm("risky-1") == "TRIG-EXACT"
    assert w._exit_profile_for_arm("no-label-arm") == ""
    assert w._exit_profile_for_arm("unknown-arm") == ""


def test_exit_profile_for_arm_fails_open_on_missing_file(tmp_path, monkeypatch):
    w = _load()
    monkeypatch.setattr(w, "ACCOUNTS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(w, "_ARM_EXIT_PROFILE_CACHE", None)
    assert w._exit_profile_for_arm("safe-3") == ""


def test_exit_profile_matches_live_accounts_json():
    """Runs against the REAL fleet/accounts.json (2026-07-20 build) -- pins the actual
    assignment so a future accounts.json edit that silently drops/renames a label is caught
    here, not just in the fleet-side test suite."""
    w = _load()
    monkeypatch_cache = w._ARM_EXIT_PROFILE_CACHE
    w._ARM_EXIT_PROFILE_CACHE = None
    try:
        assert w._exit_profile_for_arm("safe-3") == "RIBBON"
        # risky-1 was TRIG-EXACT (the untouched registry-verbatim control) until 2026-07-29,
        # when J's "rip apart the shared exit shape" directive made it a challenger lane. BE-FLOOR
        # was armed then REVERTED the same session (its backtest showed profit_lock_mode="fixed"
        # also disables post-TP1 ratcheting -- confounded); what survives is REACHABLE-TP1
        # (tp1 1.0 -> 0.5 only). The control
        # role moved to the core arms (safe-2/bold-2), which still run the registry shape.
        assert w._exit_profile_for_arm("risky-1") == "REACHABLE-TP1"
        # risky-3 was ZONE-RIDE until 2026-08-09, when `1a2692c4` armed it on the
        # PREMIUM-STOP lane as a one-variable live paper A/B for the stop_mode finding
        # (prereg `a2d7c3e4`, frozen BEFORE the config change). RE-PINNED 2026-08-15, not
        # sandboxed: this assertion exists to catch accounts.json edits and it caught a real
        # one -- the edit was deliberate and pre-registered, so the pin moves to match.
        # NOTE for the exit review: this arm is a CONFOUND in any PRE/POST 08-10 exit split.
        assert w._exit_profile_for_arm("risky-3") == "PREMIUM-STOP"
        assert w._exit_profile_for_arm("safe-2") == "CORE"
        assert w._exit_profile_for_arm("bold-2") == "CORE"
    finally:
        w._ARM_EXIT_PROFILE_CACHE = monkeypatch_cache


def test_exit_profile_wired_into_fill_ping_message(tmp_path, monkeypatch):
    """End-to-end: main()'s ping message carries a 'profile: <PROFILE>' bullet for a
    fleet arm with a label -- proves the label is actually wired, not just the helper
    function. FORMAT CHANGE 2026-08-17: the old inline ' | exit:<PROFILE>' suffix moved
    to its own bullet in the ratified bulleted-message rewrite (pin updated deliberately)."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    monkeypatch.setattr(w, "TRADE_TODAY", tmp_path / "trade-today.json")
    monkeypatch.setattr(w, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(w, "PINGED", tmp_path / "pinged.json")
    monkeypatch.setattr(w, "LIFETIME", tmp_path / "lifetime.json")
    accounts = {"arms": [{"id": "risky-3", "exit_profile": "ZONE-RIDE"}]}
    (tmp_path / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
    monkeypatch.setattr(w, "ACCOUNTS_PATH", tmp_path / "accounts.json")
    monkeypatch.setattr(w, "_ARM_EXIT_PROFILE_CACHE", None)
    d = tmp_path / "fleet" / "risky-3"
    d.mkdir(parents=True)
    row = {"ts_et": "2026-07-20T11:07:02", "arm_id": "risky-3", "action": "ENTER_BEAR",
           "placement": {"broker": {"symbol": FLEET_SYM, "id": "2951f12e"}}}
    (d / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"risky-3": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "2951f12e", "symbol": FLEET_SYM, "qty": 5, "price": 0.46, "side": "buy",
         "status": "filled", "filled_at": "2026-07-20T15:07:06Z"}])
    monkeypatch.setattr(w, "split_rehearsal_probes", lambda orders: (orders, []))
    monkeypatch.setattr(w, "classify_orders", lambda orders: (orders, []))
    monkeypatch.setattr(w, "_load_user_mention", lambda: "")
    w.main()
    content = (tmp_path / "discord-outbox.jsonl").read_text(encoding="utf-8")
    assert "profile: ZONE-RIDE" in content
    trade_today = json.loads((tmp_path / "trade-today.json").read_text(encoding="utf-8"))
    assert trade_today["fills"][0]["exit_profile"] == "ZONE-RIDE"


def test_exit_profile_tag_omitted_when_label_missing(tmp_path, monkeypatch):
    """An arm with no exit_profile label yet must not print an empty profile bullet.
    FORMAT CHANGE 2026-08-17: re-pinned to the new 'profile: <X>' bullet text (the old
    ' | exit:' substring no longer appears in ANY message under the new format, so that
    assertion alone would no longer guard anything -- strengthened, not weakened)."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    monkeypatch.setattr(w, "TRADE_TODAY", tmp_path / "trade-today.json")
    monkeypatch.setattr(w, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(w, "PINGED", tmp_path / "pinged.json")
    monkeypatch.setattr(w, "LIFETIME", tmp_path / "lifetime.json")
    (tmp_path / "accounts.json").write_text(json.dumps({"arms": []}), encoding="utf-8")
    monkeypatch.setattr(w, "ACCOUNTS_PATH", tmp_path / "accounts.json")
    monkeypatch.setattr(w, "_ARM_EXIT_PROFILE_CACHE", None)
    (tmp_path / "fleet" / "safe-2").mkdir(parents=True)
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"safe-2": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "ord3", "symbol": SYM, "qty": 3, "price": 1.22, "side": "buy",
         "status": "filled", "filled_at": "2026-07-20T13:51:29Z"}])
    monkeypatch.setattr(w, "split_rehearsal_probes", lambda orders: (orders, []))
    monkeypatch.setattr(w, "classify_orders", lambda orders: (orders, []))
    monkeypatch.setattr(w, "_load_user_mention", lambda: "")
    w.main()
    content = (tmp_path / "discord-outbox.jsonl").read_text(encoding="utf-8")
    assert " | exit:" not in content
    assert "profile:" not in content


# =============================================================================
# READABLE FILL FORMAT (2026-08-17): J's exact words after calling the old single-line
# pipe-concatenated fill ping "just gibberish"/"I cannot read them" -- "Red or green
# emoji for put or call, and then needs to be, like, 777c five contracts at price with
# a take profit at this level... in a new line and, like, a bullet." These 4 tests pin
# the ratified bulleted-message rewrite (trade_today_watcher.main() + the new
# _parse_occ/_contract_label/_direction_emoji/_tp1_bullet/_stop_bullet helpers).
# =============================================================================
def _wire_common(w, tmp_path, monkeypatch):
    """Shared plumbing for the 4 tests below -- state-path monkeypatches every other
    end-to-end test in this file already uses."""
    monkeypatch.setattr(w, "STATE", tmp_path)
    monkeypatch.setattr(w, "TRADE_TODAY", tmp_path / "trade-today.json")
    monkeypatch.setattr(w, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(w, "PINGED", tmp_path / "pinged.json")
    monkeypatch.setattr(w, "LIFETIME", tmp_path / "lifetime.json")
    monkeypatch.setattr(w, "_load_user_mention", lambda: "")
    monkeypatch.setattr(w, "split_rehearsal_probes", lambda orders: (orders, []))
    monkeypatch.setattr(w, "classify_orders", lambda orders: (orders, []))


def _last_ping_content(tmp_path) -> str:
    lines = (tmp_path / "discord-outbox.jsonl").read_text(encoding="utf-8").strip().splitlines()
    return json.loads(lines[-1])["content"]


def test_put_entry_renders_red_emoji_strike_qty_price_and_tp1_bullet(tmp_path, monkeypatch):
    """(1) A PUT entry fill renders \U0001F534 (red circle) + parsed '775P' + qty + price
    on line 1, and a 'TP1 $X.XX (+NN%), sell Q' bullet sourced from a tmp exit-state.json
    fixture. Uses the EXACT numbers behind the real 2026-08-17 13:06:05 ET bold-2 fill
    (775P x5 @ $0.72, ribbon_ride's registered entry_premium/tp1_premium_pct/tp1_qty ->
    TP1 $1.44 +100%, sell 3) so this test is anchored to a real, verified trade."""
    w = _load()
    _wire_common(w, tmp_path, monkeypatch)
    put_sym = "SPY260817P00775000"
    d = tmp_path / "fleet" / "bold-2"
    d.mkdir(parents=True)
    (d / "exit-state.json").write_text(json.dumps({
        put_sym: {"entry_premium": 0.72, "tp1_premium_pct": 1.0, "tp1_qty": 3,
                  "stop_mode": "structure", "trigger_level": 775.09,
                  "catastrophe_stop_pct": -0.50}}), encoding="utf-8")
    row = {"ts_et": "2026-08-17T13:06:05", "account": "bold",
           "exec": {"status": "FILLED", "symbol": put_sym}}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"bold-2": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "930f75b8", "symbol": put_sym, "qty": 5, "price": 0.72, "side": "buy",
         "status": "filled", "filled_at": "2026-08-17T17:06:05Z"}])
    w.main()
    msg = _last_ping_content(tmp_path)
    lines = msg.split("\n")
    assert lines[0].startswith("\U0001F534 775P ×5 @ $0.72"), lines[0]
    assert "ENGINE TRADE [bold-2]" in lines[0]
    assert "TP1 $1.44 (+100%), sell 3" in msg
    assert "stop: structure @ $775.09" in msg
    assert "13:06:05 ET" in msg


def test_call_entry_renders_green_emoji(tmp_path, monkeypatch):
    """(2) A CALL entry fill renders \U0001F7E2 (green circle) + parsed strike+'C'."""
    w = _load()
    _wire_common(w, tmp_path, monkeypatch)
    call_sym = "SPY260817C00778000"
    d = tmp_path / "fleet" / "safe-2"
    d.mkdir(parents=True)
    (d / "exit-state.json").write_text(json.dumps({
        call_sym: {"entry_premium": 0.50, "tp1_premium_pct": 1.0, "tp1_qty": 2,
                  "stop_mode": "premium", "trigger_level": None,
                  "catastrophe_stop_pct": -0.50}}), encoding="utf-8")
    row = {"ts_et": "2026-08-17T10:00:00", "account": "safe",
           "exec": {"status": "FILLED", "symbol": call_sym}}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"safe-2": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "call-ord-1", "symbol": call_sym, "qty": 3, "price": 0.50, "side": "buy",
         "status": "filled", "filled_at": "2026-08-17T14:00:00Z"}])
    w.main()
    msg = _last_ping_content(tmp_path)
    lines = msg.split("\n")
    assert lines[0].startswith("\U0001F7E2 778C ×3 @ $0.50"), lines[0]
    assert "stop: catastrophe cap -50% ($0.25)" in msg  # premium-mode fallback, no trigger_level


def test_exit_fill_renders_no_tp1_bullet(tmp_path, monkeypatch):
    """(3) A SELL-side fill renders as an EXIT line with NO TP1 bullet -- even when the
    exit-state ledger STILL has the symbol (the real shape of a TP1 partial sell, where
    the runner leg is still open and the record hasn't been pruned yet). J's spec: "EXIT
    fills: ... no TP bullet", unconditionally on side, not conditionally on ledger state."""
    w = _load()
    _wire_common(w, tmp_path, monkeypatch)
    put_sym = "SPY260817P00775000"
    d = tmp_path / "fleet" / "bold-2"
    d.mkdir(parents=True)
    # Deliberately STILL present (tp1_filled True, runner still open) -- proves the
    # omission is driven by side=="sell", not by exit-state absence.
    (d / "exit-state.json").write_text(json.dumps({
        put_sym: {"entry_premium": 0.72, "tp1_premium_pct": 1.0, "tp1_qty": 3,
                  "tp1_filled": True, "stop_mode": "structure", "trigger_level": 775.09,
                  "catastrophe_stop_pct": -0.50}}), encoding="utf-8")
    row = {"ts_et": "2026-08-17T13:06:05", "account": "bold",
           "exec": {"status": "FILLED", "symbol": put_sym}}
    (tmp_path / "core-decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"bold-2": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "5d51e6ed", "symbol": put_sym, "qty": 3, "price": 1.50, "side": "sell",
         "status": "filled", "filled_at": "2026-08-17T17:26:04Z"}])
    w.main()
    msg = _last_ping_content(tmp_path)
    lines = msg.split("\n")
    assert lines[0].startswith("\U0001F534 775P EXIT ×3 @ $1.50"), lines[0]
    assert "[bold-2]" in lines[0]
    assert "TP1" not in msg
    assert "stop:" not in msg
    assert "13:26:04 ET" in msg


def test_unattributed_label_still_appears_for_unattributed_fill(tmp_path, monkeypatch):
    """(4) The UNATTRIBUTED warning J relies on still appears (moved to a bullet, per
    J's explicit "it can move to a bullet") when no decision row matches -- re-verified
    here against a CALL fill (distinct fixture from the pre-existing pin test above) so
    this is a genuinely independent guard, not a duplicate of it."""
    w = _load()
    _wire_common(w, tmp_path, monkeypatch)
    call_sym = "SPY260817C00780000"
    d = tmp_path / "fleet" / "risky-1"
    d.mkdir(parents=True)
    (tmp_path / "core-decisions.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"risky-1": {}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [
        {"id": "rogue-1", "symbol": call_sym, "qty": 2, "price": 0.40, "side": "buy",
         "status": "filled", "filled_at": "2026-08-17T15:00:00Z"}])
    w.main()
    msg = _last_ping_content(tmp_path)
    lines = msg.split("\n")
    assert "UNATTRIBUTED [risky-1]" in lines[0]
    assert "ENGINE TRADE" not in lines[0]
    assert "⚠️ UNATTRIBUTED — no matching decision row" in msg


def test_two_credential_labels_one_account_produce_one_counted_fill_per_order_id(tmp_path, monkeypatch):
    """END-TO-END, THE EXACT INCIDENT SHAPE: two credential labels ("safe-1", "safe-2") both
    resolving to the same broker account both return the SAME order id from _fetch_orders
    (as the real Alpaca API would for one shared account polled under two key pairs). Before
    the fix, main() would append it twice to all_filled AND double the spy_fills_today count.
    After the fix: exactly one counted fill, one ping."""
    w = _load()
    monkeypatch.setattr(w, "STATE", tmp_path)
    monkeypatch.setattr(w, "TRADE_TODAY", tmp_path / "trade-today.json")
    monkeypatch.setattr(w, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(w, "PINGED", tmp_path / "pinged.json")
    monkeypatch.setattr(w, "LIFETIME", tmp_path / "lifetime.json")
    (tmp_path / "fleet" / "safe-1").mkdir(parents=True)
    (tmp_path / "fleet" / "safe-2").mkdir(parents=True)
    # dict order matters: safe-1 is fetched first, mirroring secrets.json's real insertion
    # order (safe-1 predates the 2026-07-11 safe-2 repoint) -- first-seen arm keeps the fill.
    monkeypatch.setattr(w.fb, "load_creds", lambda: {"safe-1": {"tag": "safe-1"},
                                                       "safe-2": {"tag": "safe-2"}})
    monkeypatch.setattr(w, "_fetch_orders", lambda creds: [dict(DUP_ORDER)])  # SAME order both times
    monkeypatch.setattr(w, "_load_user_mention", lambda: "")
    w.main()

    trade_today = json.loads((tmp_path / "trade-today.json").read_text(encoding="utf-8"))
    assert trade_today["spy_fills_today"] == 1, (
        f"expected exactly 1 deduped fill, got {trade_today['spy_fills_today']} "
        "-- the 2026-07-17 double-count regression"
    )
    assert len(trade_today["fills"]) == 1
    assert trade_today["fills"][0]["arm"] == "safe-1", "first-seen credential label keeps attribution"

    outbox_path = tmp_path / "discord-outbox.jsonl"
    pings = outbox_path.read_text(encoding="utf-8").strip().splitlines() if outbox_path.exists() else []
    assert len(pings) == 1, f"expected exactly 1 Discord ping for the one real fill, got {len(pings)}"
