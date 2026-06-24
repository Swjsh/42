"""End-to-end integration guard for watcher_live.main() (WATCHER-FEED-REARM-CONFIRM).

WHY THIS EXISTS (the gap the two prior unit guards leave open):
  - test_watcher_live_rth_gate.py  -> pins `_rth_gate_ok` (the ET window) in isolation.
  - test_watcher_live_load_fallback.py -> pins `_load_with_fallback` (corrupt-CSV
    degradation) in isolation.
  Neither exercises the FULL pipeline main() runs every RTH tick:
      gate -> load -> yfinance top-up -> ribbon/VIX/HTF precompute -> level detection
      -> run_all_watchers (the 28-watcher fleet) -> log_observation -> RICH end-of-fn diag.
  The 2026-06-23 TOTAL-DARKNESS day was a CRASH *inside* that pipeline (before the
  load-fallback fix) that produced ZERO diag rows. The two unit guards prove the
  sub-components; they do NOT prove that a HEALTHY frame traverses main() to
  completion and emits the rich diag. Prior fires deferred that confirmation to
  "the next live RTH" -- this test does it NOW (verify-now-not-later), $0, offline,
  on a deterministic synthetic frame.

CONTRACT PINNED:
  (1) HEALTHY PATH: given a valid gate + a clean 2-day 5m frame + a no-op yfinance,
      main() returns 0 and writes the RICH end-of-function diag (the row carrying
      `signals_emitted` + `multi_day_rth_rows`), proving it did NOT early-bail or
      crash anywhere in the pipeline.
  (2) FLEET-CRASH STAYS LOUD (C7): if run_all_watchers raises, main() must NOT crash
      silently -- it writes a `watcher_run_exception` diag and returns 0.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import types

import pandas as pd
import pytest

from autoresearch import runner as ar_runner
from autoresearch import watcher_live
from lib.watchers import runner as watchers_runner


def _synth_day(date: dt.date, base: float) -> list[tuple]:
    """One full RTH day of 5m bars (09:30-15:55 ET) as (ts_str, o,h,l,c,v) rows.

    Deterministic gentle walk -- enough bars for SMA50 warmup, all volume>0 so the
    incomplete-bar filter keeps them, realistic enough that ribbon/level detection
    runs without NaN blow-ups.
    """
    rows: list[tuple] = []
    t = dt.datetime.combine(date, dt.time(9, 30))
    end = dt.datetime.combine(date, dt.time(15, 55))
    px = base
    i = 0
    while t <= end:
        drift = math.sin(i / 7.0) * 0.4
        o = px
        c = px + drift
        h = max(o, c) + 0.15
        l = min(o, c) - 0.15
        rows.append((t.strftime("%Y-%m-%d %H:%M:%S"), round(o, 2), round(h, 2),
                     round(l, 2), round(c, 2), 200_000 + (i % 5) * 1_000))
        px = c
        t += dt.timedelta(minutes=5)
        i += 1
    return rows


def _fake_load_data(lookback_start: dt.date, today: dt.date):
    """Stand-in for ar_runner.load_data: builds a clean [today-1, today] frame so
    the frame ALWAYS matches main()'s internally-computed `today` (no date drift)."""
    prior = today - dt.timedelta(days=1)
    spy_rows = _synth_day(prior, 745.0) + _synth_day(today, 746.0)
    spy = pd.DataFrame(spy_rows, columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    vix = pd.DataFrame(
        [(r[0], 17.0, 17.3, 16.8, 17.1, 0) for r in spy_rows],
        columns=["timestamp_et", "open", "high", "low", "close", "volume"],
    )
    return spy, vix


@pytest.fixture
def _wired(tmp_path, monkeypatch):
    """Redirect every output sink to tmp, bypass the wall-clock gate, stub the
    network, and feed the synthetic loader -- so main() runs offline + hermetically."""
    # Output sinks -> tmp (diag + live-state on watcher_live; obs log on the runner).
    monkeypatch.setattr(watcher_live, "STATE_DIR", tmp_path)
    monkeypatch.setattr(watcher_live, "LIVE_STATE", tmp_path / ".watcher-live-state.json")
    monkeypatch.setattr(watcher_live, "OUTBOX", tmp_path / "discord-outbox.jsonl")
    monkeypatch.setattr(watcher_live, "CFG", tmp_path / ".discord-config.json")
    monkeypatch.setattr(watchers_runner, "OBS_LOG", tmp_path / "watcher-observations.jsonl")

    # Gate: pass deterministically regardless of the day/time the test runs.
    monkeypatch.setattr(watcher_live, "_rth_gate_ok", lambda now_et: True)

    # Loader: clean synthetic frame keyed to main()'s own `today`.
    monkeypatch.setattr(ar_runner, "load_data", _fake_load_data)

    # Network: no-op yfinance so the top-up (if triggered) is harmless + offline.
    fake_yf = types.ModuleType("yfinance")
    fake_yf.download = lambda *a, **k: pd.DataFrame()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    return tmp_path


def _read_diag(tmp_path) -> list[dict]:
    f = tmp_path / "watcher-live-diag.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_healthy_path_runs_end_to_end_and_writes_rich_diag(_wired):
    """The core REARM guard: a healthy frame must traverse main() to completion."""
    rc = watcher_live.main()
    assert rc == 0

    diag = _read_diag(_wired)
    assert diag, "main() produced NO diag row on a healthy frame -- TOTAL DARKNESS regression"

    # The RICH end-of-function diag (only written if main() reached the very end,
    # i.e. did NOT early-bail or crash anywhere in the pipeline).
    rich = [d for d in diag if "signals_emitted" in d]
    assert rich, (
        "no rich end-of-function diag -> main() bailed early. Skip reasons seen: "
        f"{[d.get('skip_reason') for d in diag]}"
    )
    last = rich[-1]
    assert last["multi_day_rth_rows"] > 60   # warmup satisfied (SMA50)
    assert last["today_rth_rows"] > 0
    assert last["signals_emitted"] >= 0      # fleet ran (0 fires is fine on synthetic)

    # And it must NOT have hit any of the crash/early-bail reasons.
    bad = {"no_bars_after_topup", "rth_empty", "ribbon_exception",
           "watcher_run_exception", "stale_csv_date"}
    seen = {str(d.get("skip_reason", "")).split(":")[0] for d in diag}
    assert not (seen & bad), f"healthy path hit an early-bail/crash reason: {seen & bad}"


def test_fleet_crash_writes_loud_diag_not_silent(_wired, monkeypatch):
    """C7: if the watcher fleet raises, main() must surface a loud diag + return 0,
    never crash the producer into a zero-row darkness day."""
    def _boom(*a, **k):
        raise RuntimeError("synthetic watcher fleet explosion")

    monkeypatch.setattr(watcher_live, "run_all_watchers", _boom)

    rc = watcher_live.main()
    assert rc == 0  # producer must survive

    diag = _read_diag(_wired)
    reasons = [str(d.get("skip_reason", "")) for d in diag]
    assert any(r.startswith("watcher_run_exception") for r in reasons), (
        f"fleet crash did NOT write a loud diag (silent darkness). reasons={reasons}"
    )
    # The exception type must be surfaced for triage (not swallowed).
    crash = next(d for d in diag if str(d.get("skip_reason", "")).startswith("watcher_run_exception"))
    assert "RuntimeError" in crash.get("exc", "")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
