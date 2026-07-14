"""Guards for trade_autopsy.py -- the hypothesis organ (J 2026-07-08: 'why doesn't Gamma think
maybe we're stopping out too early'). Pure-logic only: tag classifier, rolling detectors,
dedupe. No network / no ledger. Red-proof style: each detector has a fires case AND a
below-threshold case, so a vacuous always-fires or never-fires regression reds."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "trade_autopsy", REPO / "setup" / "scripts" / "trade_autopsy.py")
ta = importlib.util.module_from_spec(_SPEC)
sys.modules["trade_autopsy"] = ta
_SPEC.loader.exec_module(ta)


# ---------- classify_position ----------

def test_stopped_then_paid_tag():
    c = ta.classify_position(actual_pnl=-58.0, entry_price=0.96, entry_bar_low=0.90,
                             post_exit_high=2.44, cf_pnls={"wide_stop_-50": 231.0})
    assert "stopped_then_paid" in c["tags"]          # the 741P type specimen
    assert "exit_shape_cost" in c["tags"]            # +231 vs -58 > $25
    assert c["best_counterfactual"] == "wide_stop_-50"
    assert abs(c["stop_cost_vs_best"] - 289.0) < 1e-6


def test_winner_not_tagged_stopped_then_paid():
    c = ta.classify_position(actual_pnl=120.0, entry_price=1.0, entry_bar_low=0.95,
                             post_exit_high=2.0, cf_pnls={"no_stop_ride": 110.0})
    assert "stopped_then_paid" not in c["tags"]      # only losses qualify
    assert "exit_shape_cost" not in c["tags"]        # we BEAT the probes


def test_paid_the_spike_threshold():
    hot = ta.classify_position(-10, entry_price=1.10, entry_bar_low=0.95,
                               post_exit_high=None, cf_pnls={})
    cool = ta.classify_position(-10, entry_price=1.00, entry_bar_low=0.98,
                                post_exit_high=None, cf_pnls={})
    assert "paid_the_spike" in hot["tags"] and "paid_the_spike" not in cool["tags"]


def test_exit_beat_theta_honesty_tag():
    """When riding would have lost MORE, the exit was right -- the organ must be able to say
    'our exit won' (no confirmation bias toward wider-is-better)."""
    c = ta.classify_position(actual_pnl=-40.0, entry_price=1.0, entry_bar_low=1.0,
                             post_exit_high=0.9, cf_pnls={"hold_to_time": -95.0})
    assert "exit_beat_theta" in c["tags"]


# ---------- compute_pnl_status: THE 2026-07-14 honesty fix ---------------------------------
# Monday 07-13 root cause: risky-3's real -$25 position was found in the ledger but its bars
# never arrived (OPRA indexing lag), and the OLD code wrote net_pnl=0.0 regardless -- the
# exact same number a genuinely flat day gets. These guard the tri-state classifier that
# makes that collapse impossible again.

def test_pnl_status_flat_when_no_positions_found():
    assert ta.compute_pnl_status(n_positions_found=0, n_no_bars=0) == "flat"


def test_pnl_status_verified_when_all_positions_replayed():
    assert ta.compute_pnl_status(n_positions_found=3, n_no_bars=0) == "verified"


def test_pnl_status_unverified_when_any_position_missing_bars():
    """THE regression guard: a position found but not replayed must NEVER classify as
    'flat' or 'verified' -- both would let a caller print a bare $0.00 net_pnl."""
    assert ta.compute_pnl_status(n_positions_found=1, n_no_bars=1) == "unverified_no_bars"


def test_pnl_status_unverified_even_when_partially_replayed():
    """Mixed day: 3 found, 1 missing bars -- still unverified, not 'verified with a caveat'.
    The whole day's net_pnl must not be trusted if ANY position is unreplayed."""
    assert ta.compute_pnl_status(n_positions_found=3, n_no_bars=1) == "unverified_no_bars"


# ---------- resolve_net_pnl: the single source of truth for the reported dollar figure -----

def test_resolve_net_pnl_flat_is_a_real_zero():
    assert ta.resolve_net_pnl("flat", None) == 0.0


def test_resolve_net_pnl_verified_returns_the_known_sum():
    assert ta.resolve_net_pnl("verified", -381.5) == -381.5


def test_resolve_net_pnl_unverified_is_never_zero_or_a_number():
    """THE Monday 07-13 bug, pinned: risky-3 lost real money (-$25) but 0 rows replayed, so
    the naive `sum(rows) if rows else 0.0` produced net_pnl_known=None-ish-0.0. Even if a
    caller mistakenly passes a nonzero net_pnl_known alongside 'unverified_no_bars' (e.g. a
    stale/partial value), the day's headline net_pnl must still refuse to report anything
    but None -- the caller is responsible for surfacing net_pnl_known_partial separately."""
    assert ta.resolve_net_pnl("unverified_no_bars", None) is None
    assert ta.resolve_net_pnl("unverified_no_bars", -25.0) is None


# ---------- detectors ----------

def _row(pnl, tags=(), spike=None, cost=None):
    return {"actual_pnl": pnl, "tags": list(tags), "entry_spike_pct": spike,
            "stop_cost_vs_best": cost}


def test_stop_noise_hypothesis_fires_and_respects_floor():
    losers = [_row(-50, tags=["stopped_then_paid"]) for _ in range(5)] + [_row(-40)]
    rows = losers + [_row(30)] * 4                          # 6 losers, 5/6 stopped-then-paid
    hyps = ta.detect_hypotheses(rows, "2026-07-09")
    assert any(h["mechanism"] == "stop_inside_noise_floor" for h in hyps)
    # below the MIN_LOSERS floor: silent (n-honesty -- no claims off 3 trades)
    hyps2 = ta.detect_hypotheses([_row(-50, tags=["stopped_then_paid"])] * 3, "2026-07-09")
    assert not any(h["mechanism"] == "stop_inside_noise_floor" for h in hyps2)


def test_stop_noise_below_fraction_is_silent():
    losers = [_row(-50, tags=["stopped_then_paid"]) for _ in range(3)] + [_row(-40)] * 4
    hyps = ta.detect_hypotheses(losers, "2026-07-09")       # 3/7 = 43% < 60%
    assert not any(h["mechanism"] == "stop_inside_noise_floor" for h in hyps)


def test_entry_spike_hypothesis():
    rows = [_row(-10, spike=0.12) for _ in range(9)]        # median 12% >= 8%, n>=8
    hyps = ta.detect_hypotheses(rows, "2026-07-09")
    assert any(h["mechanism"] == "paying_the_signal_spike" for h in hyps)
    rows2 = [_row(-10, spike=0.03) for _ in range(9)]
    assert not any(h["mechanism"] == "paying_the_signal_spike"
                   for h in ta.detect_hypotheses(rows2, "2026-07-09"))


def test_left_on_table_hypothesis():
    rows = [_row(-30, cost=120.0) for _ in range(5)]        # sum cost 600 >= 300 and >= 2*|net -150|
    hyps = ta.detect_hypotheses(rows, "2026-07-09")
    assert any(h["mechanism"] == "exit_shape_dominated" for h in hyps)


def test_dedupe_one_emission_per_week():
    new = [{"id": "H-2026-07-09-stop-noise", "mechanism": "stop_inside_noise_floor"}]
    recent = [{"mechanism": "stop_inside_noise_floor", "date": "2026-07-05"}]
    old = [{"mechanism": "stop_inside_noise_floor", "date": "2026-06-20"}]
    assert ta.dedupe_hypotheses(new, recent, "2026-07-09") == []      # emitted 4 days ago
    assert ta.dedupe_hypotheses(new, old, "2026-07-09") == new        # last emission stale


def test_every_hypothesis_carries_evidence_and_tests():
    """The contract with the downstream consumers (chef/conductor): a hypothesis without
    evidence numbers + concrete proposed_tests is just vibes -- reject at the source."""
    losers = [_row(-50, tags=["stopped_then_paid"]) for _ in range(6)]
    for h in ta.detect_hypotheses(losers + [_row(20)] * 3, "2026-07-09"):
        assert h["evidence"] and h["proposed_tests"] and h["claim"] and h["id"]


# ---------- FLEET-BLINDNESS FIX (2026-07-09) coverage ----------------------------------------
# The prior fire (16:15 ET) wrote "No closed engine positions today" while 10 real fleet
# round trips sat in the ledger. These guard the two mechanisms behind that miss (universe
# scope + bars-retry) plus the attribution/read-only requirements added alongside the fix.

def _fill(arm, symbol, side, qty, price, ts_utc, date_et, attribution="engine",
          is_option=True, is_crypto=False):
    return {"arm": arm, "symbol": symbol, "side": side, "qty": qty, "price": price,
            "ts_utc": ts_utc, "date_et": date_et, "attribution": attribution,
            "is_option": is_option, "is_crypto": is_crypto,
            "activity_id": f"act-{arm}-{symbol}-{side}-{ts_utc}",
            "order_id": f"ord-{arm}-{symbol}-{side}"}


# ---- universe scope: fleet arms must be in it, core arms must stay in it --------------------

def test_load_engine_positions_includes_fleet_and_core_arms(tmp_path):
    """THE regression guard for the fleet-blindness bug: a fleet_rest arm's closed round
    trip must appear in the universe alongside a core arm's. If a future edit reintroduces
    a core-only filter (e.g. gating on CORE_ARM_ACCOUNT), this REDs."""
    date = "2026-07-09"
    ledger = tmp_path / "fills-ledger.jsonl"
    rows = [
        _fill("safe-1", "SPY260709C00750000", "buy", 3, 0.50, f"{date}T14:28:05Z", date),
        _fill("safe-1", "SPY260709C00750000", "sell", 3, 0.42, f"{date}T14:34:05Z", date),
        _fill("safe-2", "SPY260709C00751000", "buy", 2, 0.55, f"{date}T14:28:06Z", date),
        _fill("safe-2", "SPY260709C00751000", "sell", 2, 0.48, f"{date}T14:34:06Z", date),
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    positions = ta.load_engine_positions(date, ledger_path=ledger)
    arms = {p["arm"] for p in positions}
    assert "safe-1" in arms, "fleet_rest arm missing from the universe (core-only-blind bug)"
    assert "safe-2" in arms, "core arm dropped -- the fleet fix must not regress core coverage"
    assert len(positions) == 2


def test_load_engine_positions_covers_all_four_fleet_rest_arms(tmp_path):
    date = "2026-07-09"
    ledger = tmp_path / "fills-ledger.jsonl"
    rows = []
    for i, arm in enumerate(ta.FLEET_REST_ARMS):
        t_entry, t_exit = f"{date}T14:2{i}:00Z", f"{date}T14:3{i}:00Z"
        rows.append(_fill(arm, "SPY260709C00750000", "buy", 1, 0.50, t_entry, date))
        rows.append(_fill(arm, "SPY260709C00750000", "sell", 1, 0.40, t_exit, date))
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    positions = ta.load_engine_positions(date, ledger_path=ledger)
    assert {p["arm"] for p in positions} == set(ta.FLEET_REST_ARMS)


def test_load_engine_positions_excludes_manual_and_crypto(tmp_path):
    date = "2026-07-09"
    ledger = tmp_path / "fills-ledger.jsonl"
    rows = [
        _fill("safe-1", "SPY260709C00750000", "buy", 3, 0.50, f"{date}T14:28:05Z", date),
        _fill("safe-1", "SPY260709C00750000", "sell", 3, 0.42, f"{date}T14:34:05Z", date),
        _fill("safe-1", "SPY260709C00751000", "buy", 1, 0.30, f"{date}T15:00:00Z", date,
              attribution="manual"),
        _fill("safe-1", "SPY260709C00751000", "sell", 1, 0.10, f"{date}T15:05:00Z", date,
              attribution="manual"),
        _fill("safe-1", "BTC/USD", "buy", 0.01, 60000, f"{date}T15:10:00Z", date,
              is_option=False, is_crypto=True),
        _fill("safe-1", "BTC/USD", "sell", 0.01, 59000, f"{date}T15:11:00Z", date,
              is_option=False, is_crypto=True),
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    positions = ta.load_engine_positions(date, ledger_path=ledger)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "SPY260709C00750000"


def test_load_engine_positions_filters_by_date(tmp_path):
    ledger = tmp_path / "fills-ledger.jsonl"
    rows = [
        _fill("safe-1", "SPY260708C00750000", "buy", 3, 0.50, "2026-07-08T14:28:05Z", "2026-07-08"),
        _fill("safe-1", "SPY260708C00750000", "sell", 3, 0.42, "2026-07-08T14:34:05Z", "2026-07-08"),
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert ta.load_engine_positions("2026-07-09", ledger_path=ledger) == []
    assert len(ta.load_engine_positions("2026-07-08", ledger_path=ledger)) == 1


def test_load_engine_positions_missing_ledger_returns_empty(tmp_path):
    assert ta.load_engine_positions("2026-07-09", ledger_path=tmp_path / "nope.jsonl") == []


# ---- bars-availability retry (the actual mechanism behind the 2026-07-09 miss) --------------

class _StubEsp:
    """Fake esp.fetch_option_bars: returns one scripted value per call (the last value
    repeats once the script is exhausted)."""
    def __init__(self, sequence):
        self._seq = list(sequence)
        self.calls = 0

    def fetch_option_bars(self, symbol, date_et):
        self.calls += 1
        idx = min(self.calls - 1, len(self._seq) - 1)
        return self._seq[idx]


def test_fetch_bars_cached_retries_then_succeeds():
    """THE 2026-07-09 mechanism: bars come back empty on the first tries (OPRA indexing
    lag right after the 16:00 ET close), then land. Must retry with backoff instead of
    giving up on the first empty response (the old `if not bars: return None` behavior)."""
    bars = [{"t": "2026-07-09T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1}]
    stub = _StubEsp([[], [], bars])
    sleeps = []
    result = ta.fetch_bars_cached(stub, "SPY260709C00750000", "2026-07-09", {},
                                  sleep_fn=sleeps.append)
    assert result == bars
    assert stub.calls == 3
    assert len(sleeps) == 2                  # 3rd call succeeded before a 3rd sleep


def test_fetch_bars_cached_gives_up_after_exhausting_retries():
    stub = _StubEsp([[]])                    # always empty -- true "no data" case
    sleeps = []
    result = ta.fetch_bars_cached(stub, "SPY260709C00750000", "2026-07-09", {},
                                  sleep_fn=sleeps.append)
    assert result == []
    assert stub.calls == 1 + len(ta.BARS_RETRY_BACKOFF_SEC)
    assert len(sleeps) == len(ta.BARS_RETRY_BACKOFF_SEC)


def test_fetch_bars_cached_caches_per_symbol():
    """Several fleet arms routinely fill the SAME signal within the same second --
    must only fetch/retry once per (symbol, date), not once per position."""
    bars = [{"t": "2026-07-09T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1}]
    stub = _StubEsp([bars])
    cache: dict = {}
    r1 = ta.fetch_bars_cached(stub, "SPY260709C00750000", "2026-07-09", cache)
    r2 = ta.fetch_bars_cached(stub, "SPY260709C00750000", "2026-07-09", cache)
    assert r1 == bars and r2 == bars
    assert stub.calls == 1                   # 2nd call served from cache


# ---- render_md: INCOMPLETE must never collapse into the flat-day message --------------------

def test_render_md_flat_day_is_unambiguous():
    """A genuinely flat day (0 positions in the ledger) keeps the original message."""
    md = ta.render_md("2026-07-09", [], [], n_positions_found=0, n_no_bars=0)
    assert "No closed engine positions today" in md
    assert "INCOMPLETE" not in md


def test_render_md_incomplete_when_positions_found_but_unreplayable():
    """THE bug this fix closes: positions existed in the broker-truth ledger but couldn't
    be replayed (bars unavailable) -- must render as INCOMPLETE, never as the same
    'nothing to autopsy' text a flat day gets (OP-33/C7 silent-success-is-failure)."""
    md = ta.render_md("2026-07-09", [], [], n_positions_found=10, n_no_bars=10)
    assert "INCOMPLETE" in md
    assert "10 closed engine position" in md
    assert "No closed engine positions today" not in md


def test_render_md_shows_strategy_and_stop_mode_columns():
    """Attribution (arm + strategy + stop_mode) must be visible in the human-facing
    digest, not just the raw jsonl -- J reads the .md, not the jsonl."""
    row = {"date": "2026-07-09", "arm": "safe-1", "strategy": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
           "stop_mode": None, "symbol": "SPY260709C00750000", "entry_ts_utc": "x",
           "entry_price": 0.5, "qty": 3, "actual_pnl": -24.0, "mfe_pct": 3.2, "mae_pct": -0.3,
           "counterfactuals": {"wide_stop_-50": 208.5}, "tags": ["stopped_then_paid"],
           "stop_cost_vs_best": 232.5, "best_counterfactual": "wide_stop_-50",
           "entry_spike_pct": -0.02}
    md = ta.render_md("2026-07-09", [row], [], n_positions_found=1, n_no_bars=0)
    assert "BULLISH_RECLAIM_RIDE_THE_RIBBON" in md
    assert "| symbol | arm | strategy | stop_mode |" in md
    assert "| C00750000 | safe-1 | BULLISH_RECLAIM_RIDE_THE_RIBBON | — |" in md


# ---- queue_ping: the INCOMPLETE case must never be silent -----------------------------------

def test_queue_ping_flat_day_writes_nothing(tmp_path):
    outbox = tmp_path / "discord-outbox.jsonl"
    ta.queue_ping("2026-07-09", [], [], n_positions_found=0, n_no_bars=0, outbox_path=outbox)
    assert not outbox.exists() or outbox.read_text(encoding="utf-8") == ""


def test_queue_ping_incomplete_never_silent(tmp_path):
    """Positions existed but 0 replayed -- must ping, never fall into the 'silent on a
    no-trade day' branch (that would hide a broken-autopsy day as a quiet flat one)."""
    outbox = tmp_path / "discord-outbox.jsonl"
    ta.queue_ping("2026-07-09", [], [], n_positions_found=10, n_no_bars=10, outbox_path=outbox)
    assert outbox.exists()
    content = outbox.read_text(encoding="utf-8")
    assert "INCOMPLETE" in content
    assert "10" in content


# ---- attribution joins: strategy + stop_mode, fleet AND core --------------------------------

def test_closest_broker_created_row_picks_nearest_and_respects_window():
    rows = [
        {"placement": {"symbol": "X", "broker": {"created_at": "2026-07-09T14:00:00Z", "id": "far"}}},
        {"placement": {"symbol": "X", "broker": {"created_at": "2026-07-09T14:28:03Z", "id": "near"}}},
        {"placement": {"symbol": "Y", "broker": {"created_at": "2026-07-09T14:28:04Z", "id": "wrong-symbol"}}},
    ]
    best = ta._closest_broker_created_row(rows, "X", "2026-07-09T14:28:05Z", "placement")
    assert best["placement"]["broker"]["id"] == "near"

    far_only = [rows[0]]                     # outside the 120s window -> None, never guessed
    assert ta._closest_broker_created_row(far_only, "X", "2026-07-09T14:28:05Z", "placement") is None


def test_lookup_strategy_fleet_arm_matches_by_broker_created_at(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "STATE", tmp_path)
    fleet_dir = tmp_path / "fleet" / "safe-1"
    fleet_dir.mkdir(parents=True)
    row = {
        "action": "ENTER_BULL", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "placement": {"symbol": "SPY260709C00750000",
                      "broker": {"id": "ord-1", "created_at": "2026-07-09T14:28:04.000000Z"}},
    }
    (fleet_dir / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    strategy = ta.lookup_strategy("safe-1", "SPY260709C00750000", "2026-07-09T14:28:05.476570Z")
    assert strategy == "BULLISH_RECLAIM_RIDE_THE_RIBBON"


def test_lookup_strategy_returns_none_outside_window(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "STATE", tmp_path)
    fleet_dir = tmp_path / "fleet" / "safe-1"
    fleet_dir.mkdir(parents=True)
    row = {
        "action": "ENTER_BULL", "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "placement": {"symbol": "SPY260709C00750000",
                      "broker": {"id": "ord-1", "created_at": "2026-07-09T09:00:00Z"}},
    }
    (fleet_dir / "decisions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    strategy = ta.lookup_strategy("safe-1", "SPY260709C00750000", "2026-07-09T14:28:05Z")
    assert strategy is None                  # best-effort: absence, never a fabricated guess


def test_lookup_strategy_core_arm_uses_core_decisions(tmp_path, monkeypatch):
    """Core behavior intact: safe-2/bold-2 attribution still resolves via
    core-decisions.jsonl's `account`/`exec` shape, unaffected by the fleet fix."""
    core_path = tmp_path / "core-decisions.jsonl"
    monkeypatch.setattr(ta, "CORE_DECISIONS", core_path)
    row = {
        "account": "safe", "setup": "BEARISH_REJECTION",
        "exec": {"symbol": "SPY260709P00745000",
                 "broker": {"id": "ord-core-1", "created_at": "2026-07-09T14:00:00Z"}},
    }
    core_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    strategy = ta.lookup_strategy("safe-2", "SPY260709P00745000", "2026-07-09T14:00:01Z")
    assert strategy == "BEARISH_REJECTION"


def test_lookup_strategy_unknown_arm_returns_none():
    assert ta.lookup_strategy("bogus-arm", "SPY260709C00750000", "2026-07-09T14:00:00Z") is None


def test_lookup_stop_mode_non_fleet_arm_is_none():
    """Core arms persist exit state via a different mechanism (current-position.json)
    this module doesn't read -- None there is honest absence, not a bug."""
    assert ta.lookup_stop_mode("safe-2", "SPY260709C00750000") is None


def test_lookup_stop_mode_reads_exit_state_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "STATE", tmp_path)
    fleet_dir = tmp_path / "fleet" / "safe-1"
    fleet_dir.mkdir(parents=True)
    (fleet_dir / "exit-state.json").write_text(
        json.dumps({"SPY260709C00750000": {"stop_mode": "structure"}}), encoding="utf-8")
    assert ta.lookup_stop_mode("safe-1", "SPY260709C00750000") == "structure"


def test_lookup_stop_mode_missing_symbol_or_file_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "STATE", tmp_path)
    assert ta.lookup_stop_mode("safe-1", "SPY260709C00750000") is None   # no exit-state.json at all
    fleet_dir = tmp_path / "fleet" / "safe-1"
    fleet_dir.mkdir(parents=True)
    (fleet_dir / "exit-state.json").write_text(
        json.dumps({"OTHER_SYMBOL": {"stop_mode": "premium"}}), encoding="utf-8")
    assert ta.lookup_stop_mode("safe-1", "SPY260709C00750000") is None   # symbol not tracked there


# ---- read-only broker guard ------------------------------------------------------------------

_FORBIDDEN_BROKER_CALLS = (
    "place_bracket(", "cancel_order(", "market_sell(", "replace_stop_order(",
    "close_all_spy_options(", "place_option_order(", "place_stock_order(",
    "place_crypto_order(", ".submit_order(", ".exercise_options_position(",
)


def test_autopsy_never_calls_broker_mutators():
    """Static-assert: trade_autopsy.py may only touch broker-adjacent modules for READS
    (credentials + market-data GETs). No order-placement/cancel/replace/close method name
    may appear anywhere in its source."""
    src = (REPO / "setup" / "scripts" / "trade_autopsy.py").read_text(encoding="utf-8")
    hits = [name for name in _FORBIDDEN_BROKER_CALLS if name in src]
    assert not hits, f"trade_autopsy.py references broker mutator(s): {hits}"


def test_replay_helper_never_calls_broker_mutators():
    """Same guard on exit_shape_parity_study.py -- the module trade_autopsy delegates
    bar-fetch/replay to (it imports fleet_broker directly, for credentials only)."""
    esp_src = (REPO / "backtest" / "tools" / "exit_shape_parity_study.py").read_text(encoding="utf-8")
    hits = [name for name in _FORBIDDEN_BROKER_CALLS if name in esp_src]
    assert not hits, f"exit_shape_parity_study.py references broker mutator(s): {hits}"
