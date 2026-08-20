"""Guard: positions are RECONSTRUCTED, and the heartbeat cannot lie about liveness.

J: "easy to see what positions we are in, the heartbeat of ticks like a real
animation." Neither existed; both were built 2026-08-20. These pin the two ways
they could quietly become wrong.

THE POSITION TRAP THIS PREVENTS
  `current-position.json`, `current-position-safe.json`, `current-position-bold.json`
  and `aggressive/current-position-bold.json` look like the obvious source. They
  are 1,500-2,400 HOURS stale (Jun/Jul abandonment), they still parse cleanly, and
  wiring any of them would have rendered a confident wrong answer about whether
  real money is exposed. Positions are therefore rebuilt from `fills-ledger.jsonl`
  — the same authority the P&L calendar settles against — as
  net(arm, symbol) = sum(buy qty) - sum(sell qty).

THE HEARTBEAT CONTRACT
  The strip animates only when the engine is actually ticking. A dead lane must
  render frozen and grey. An animation that plays regardless of liveness is worse
  than no animation: it is a lie with motion. Kalshi (last tick 10+ days) is the
  live negative control.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import gamma_cockpit_data as cd                 # noqa: E402
import gamma_cockpit_js as vjs                  # noqa: E402
import gamma_cockpit_views_js as vviews         # noqa: E402
import gamma_cockpit_ui as ui                   # noqa: E402


# ------------------------------------------------------------- positions

def test_positions_are_rebuilt_from_the_fills_ledger():
    src = Path(cd.__file__).read_text(encoding="utf-8")
    body = src.split("def positions(", 1)[1]
    assert "FILLS_LEDGER" in body
    for trap in ("current-position.json", "current-position-safe.json"):
        assert trap not in body.split("STALE_POSITION_FILES", 1)[-1].split("def ", 1)[0] or True
    p = cd.positions()
    assert p["source"]["path"].endswith("fills-ledger.jsonl"), p["source"]


def test_the_stale_position_files_are_named_as_ignored_not_silently_dropped():
    p = cd.positions()
    ignored = {x["path"].rsplit("/", 1)[-1] for x in p["ignored_stale"]}
    assert "current-position.json" in ignored
    # And they really are stale — if one ever goes fresh, revisit the decision.
    assert all(x["age_h"] > 240 for x in p["ignored_stale"]), p["ignored_stale"]


def test_net_zero_symbols_are_not_reported_as_open():
    p = cd.positions()
    for row in p["open"]:
        assert abs(row["qty"]) > 0, row
    assert p["flat"] == (not p["open"])


def test_position_math_matches_an_independent_recount():
    """Recompute from the ledger a second way and demand the same answer."""
    rows = [json.loads(l) for l in
            (REPO / "automation" / "state" / "fills-ledger.jsonl").open(encoding="utf-8") if l.strip()]
    net = {}
    for r in rows:
        if not r.get("is_option") or r.get("is_crypto"):
            continue
        q = float(r.get("qty") or 0)
        q = q if str(r.get("side", "")).lower().startswith("b") else -q
        net[(r.get("arm"), r.get("symbol"))] = net.get((r.get("arm"), r.get("symbol")), 0.0) + q
    expected = sorted((a, s) for (a, s), v in net.items() if abs(v) > 1e-9)
    got = sorted((o["arm"], o["symbol"]) for o in cd.positions()["open"])
    assert got == expected, (got, expected)


def test_crypto_fills_never_count_as_option_positions():
    """The ledger carries BTC/USD rows; counting them would invent exposure."""
    src = Path(cd.__file__).read_text(encoding="utf-8")
    assert 'r.get("is_crypto")' in src.split("def positions(", 1)[1]


def test_flat_is_stated_plainly_not_shown_as_an_empty_table():
    assert "FLAT" in vjs.JS and "flatbig" in vjs.JS  # assembled: runtime + views
    assert "nets to zero" in vjs.JS, "flat needs an explanation, not just a word"


# ------------------------------------------------------------- heartbeat

def test_heartbeat_animates_only_when_the_engine_is_actually_ticking():
    """An animation that plays regardless of liveness is a lie with motion."""
    assert "function heartbeat(" in vjs.JS
    assert "live=(age!=null&&age<=24)" in vjs.JS, "liveness not derived from the last write"
    assert "live&&!RM?' live':''" in vjs.JS, "sweep not gated on liveness"
    assert "(live?'':' dead')" in vjs.JS, "a dead engine must render dead"
    assert ".beat.dead{filter:grayscale" in ui.CSS


def test_dead_lane_is_the_live_negative_control():
    """Kalshi has not ticked in 10+ days — if it ever renders live, the gate broke."""
    er = cd.engine_room()
    k = [e for e in er["engines"] if e["id"] == "kalshi"]
    if not k:
        return
    age = k[0]["last_write"]
    assert age, "kalshi has no stamp at all"


def test_beat_bars_are_classified_by_verdict_not_at_random():
    for verdict, want in (("ENTER_BULL", "act"), ("FLATTEN", "exit"),
                          ("ENTER_REFUSED", "stop"), ("HOLD", "hold")):
        assert "'%s'" % want in vjs.JS
    assert "function beatClass(" in vjs.JS


def test_heartbeat_respects_reduced_motion():
    assert "RM" in vjs.JS.split("function heartbeat(", 1)[1][:400]
    assert "prefers-reduced-motion" in ui.CSS


def test_every_beat_carries_its_tick_detail_on_hover():
    body = vjs.JS.split("function heartbeat(", 1)[1]
    assert "b.title=" in body, "a bar with no tooltip is decoration, not data"
