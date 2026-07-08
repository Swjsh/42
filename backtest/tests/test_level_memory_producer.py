"""Guard: level_memory shadow producer selection (V1, engine-vision build 2026-07-08).

The producer surfaces multi-day MEMORY levels to a SHADOW key (not the live entry feed). This
pins the selection logic: >= MIN_MEMORY filter, dedup-into-zones (strongest wins — no wall of
pivots), TOP_N cap, and ONE structural role per price (no contradictory-role bug).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(REPO / "backtest"))


def _prod():
    spec = importlib.util.spec_from_file_location(
        "level_memory_producer", REPO / "setup" / "scripts" / "level_memory_producer.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["level_memory_producer"] = m
    spec.loader.exec_module(m)
    return m


def _lvl(price, role, mem):
    from lib.watchers.level_memory import Level
    return Level(price=price, role=role, memory_score=mem, touches=int(mem // 2), wicks=1,
                 bars_consolidated=10, role_flips=1, first_seen_idx=0, last_touch_idx=5)


def test_min_memory_filter():
    prod = _prod()
    raw = [_lvl(750.0, "resistance", 50.0), _lvl(745.0, "support", 5.0)]  # 5 < MIN_MEMORY
    out = prod.select_levels(raw)
    assert all(o["memory_score"] >= prod.MIN_MEMORY for o in out)
    assert 745.0 not in [o["price"] for o in out]


def test_dedup_into_zone_keeps_strongest():
    prod = _prod()
    raw = [_lvl(746.7, "support", 151.0), _lvl(746.3, "support", 107.0)]  # within DEDUP_EPS
    out = prod.select_levels(raw)
    assert len(out) == 1 and out[0]["memory_score"] == 151.0  # strongest wins the zone


def test_top_n_cap():
    prod = _prod()
    raw = [_lvl(700.0 + i * 2, "support", 100.0 - i) for i in range(30)]  # 30 well-spaced levels
    out = prod.select_levels(raw)
    assert len(out) <= prod.TOP_N


def test_role_preserved_one_per_price():
    prod = _prod()
    raw = [_lvl(747.4, "support", 120.0), _lvl(748.8, "resistance", 111.0)]
    out = prod.select_levels(raw)
    roles = {o["price"]: o["role"] for o in out}
    assert roles[747.4] == "support" and roles[748.8] == "resistance"
    prices = [o["price"] for o in out]
    assert len(prices) == len(set(prices))  # one role per price


# --- V1c reject-ping (dedup + outbox) ---
def test_dedup_ok():
    prod = _prod()
    import datetime as dt
    now = dt.datetime(2026, 7, 8, 14, 0, tzinfo=dt.timezone.utc)
    assert prod.dedup_ok({}, "747.41", now) is True                           # never pinged
    recent = (now - dt.timedelta(minutes=5)).isoformat()
    assert prod.dedup_ok({"747.41": recent}, "747.41", now) is False          # 5min < 30min
    old = (now - dt.timedelta(minutes=45)).isoformat()
    assert prod.dedup_ok({"747.41": old}, "747.41", now) is True              # 45min >= 30min


def test_ping_rejection_writes_then_dedups(tmp_path):
    prod = _prod()
    import json as _json
    import pandas as pd
    from lib.watchers.level_memory import Interaction, Level, Snapshot
    prod.OUTBOX = tmp_path / "outbox.jsonl"
    prod.PING_STATE = tmp_path / "ping-state.json"
    lvl = Level(price=747.41, role="support", memory_score=120.0, touches=63, wicks=10,
                bars_consolidated=20, role_flips=17, first_seen_idx=0, last_touch_idx=5)
    it = Interaction(kind="reject", level=lvl, distance=0.3, detail="wicked below S")
    snap = Snapshot(idx=10, timestamp_et=pd.Timestamp("2026-07-08 10:00"), close=747.7,
                    levels=(lvl,), nearest=lvl, interaction=it)

    class FakeLM:
        def snapshot(self, idx, lookback_days=5):
            return snap

    m1 = prod._ping_rejection(FakeLM(), 10)
    assert m1 and "REJECT" in m1
    rows = [_json.loads(x) for x in prod.OUTBOX.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1 and "content" in rows[0]
    m2 = prod._ping_rejection(FakeLM(), 10)                                    # within dedup window
    assert m2 is None
    rows2 = [x for x in prod.OUTBOX.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows2) == 1                                                     # deduped, no 2nd row


# --- V2 gap-fill: prior RTH close ---
def test_prior_rth_close_derives_prior_day():
    prod = _prod()
    import pandas as pd
    ts = ["2026-07-07 09:30", "2026-07-07 15:55", "2026-07-07 16:30",   # 16:30 = after RTH, excluded
          "2026-07-08 09:30", "2026-07-08 09:35"]
    df = pd.DataFrame({"timestamp_et": pd.to_datetime(ts).tz_localize("America/New_York"),
                       "open": [1] * 5, "high": [1] * 5, "low": [1] * 5,
                       "close": [750.0, 751.31, 999.0, 748.0, 747.7], "volume": [1] * 5})
    assert prod.prior_rth_close(df) == 751.31   # prior day's last <=16:00 close, not the AH bar
    # single-day frame -> no prior day -> None
    one = df[df["timestamp_et"].dt.date == df["timestamp_et"].dt.date.iloc[-1]]
    assert prod.prior_rth_close(one) is None
