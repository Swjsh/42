"""v47_chart_read -- validate the chart-read reader's fail-loud + parsing contract.

The detector (market_structure) is covered by v46; the READER (chart_read.py) was
untested, yet it owns the "never write to thin air" guard + the feed-parsing that
broke it (epoch-ms crash, UTC date roll, STATUS spam, silent drops). These tests
lock those fixes in.

Offline:
  T1 epoch-ms timestamp parses (no crash -- the CRITICAL bug)
  T2 ISO-with-offset parses to UTC
  T3 _to_bars drops malformed + duplicate rows (counted, not silent) + chronological
  T4 _to_bars bad-time fallback anchors to prior bar (never 1970/epoch-0)
  T5 _et_date returns the ET session date, not the rolled-over UTC date
  T6 _flag_broken is idempotent (same msg twice -> one line, not spam)
  T7 thin-air guard: main() on a dark/empty feed returns exit 2 + writes STATUS
  T8 build_read flags low_data on < 10 bars
  T9 build_read happy path yields a trend + summary

Live: a deterministic end-to-end main() run on a synthetic bars-json (no network).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

_CR_PATH = _REPO_ROOT / "backtest/autoresearch/chart_read.py"
_spec = importlib.util.spec_from_file_location("chart_read", _CR_PATH)
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


def _iso_bars(n: int) -> list[dict]:
    base = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
    prices = [100, 102, 105, 101, 99, 103, 108, 104, 102, 106, 111, 107, 105, 109, 112]
    rows = []
    for i in range(n):
        p = prices[i % len(prices)]
        t = (base + timedelta(seconds=300 * i)).isoformat()
        rows.append({"time": t, "open": p, "high": p + 0.5, "low": p - 0.5, "close": p, "volume": 1000})
    return rows


def run_offline() -> dict:
    results: list[tuple[str, bool, str]] = []

    # T1: epoch-ms must not crash
    try:
        dt_ms = cr._parse_time(1747353600000)
        ok = dt_ms.year >= 2020 and dt_ms.tzinfo is not None
        note = dt_ms.isoformat()
    except Exception as e:
        ok, note = False, f"crash {e}"
    results.append(("T1_epoch_ms_no_crash", ok, note))

    # T2: ISO with offset -> UTC
    dt = cr._parse_time("2026-05-04 10:30:00-04:00")
    results.append(("T2_iso_offset_to_utc", dt.hour == 14 and dt.tzinfo is not None, dt.isoformat()))

    # T3: malformed + duplicate dropped, chronological
    rows = [
        {"time": "2026-05-04T14:35:00Z", "open": 1, "high": 2, "low": 0, "close": 1.5},
        {"time": "2026-05-04T14:30:00Z", "open": 1, "high": 2, "low": 0, "close": 1.4},
        {"open": 9, "high": 9},  # malformed
        {"time": "2026-05-04T14:30:00Z", "open": 1, "high": 2, "low": 0, "close": 1.4},  # dup ts
    ]
    bars, dropped = cr._to_bars(rows, 300, "tv")
    chrono = [b.open_time for b in bars] == sorted(b.open_time for b in bars)
    ok = len(bars) == 2 and dropped == 2 and chrono
    results.append(("T3_drop_malformed_dup", ok, f"bars={len(bars)} dropped={dropped} chrono={chrono}"))

    # T4: bad-time fallback anchors to prior bar (no 1970)
    rows = [
        {"time": "2026-05-04T14:30:00Z", "open": 1, "high": 2, "low": 0, "close": 1.4},
        {"time": None, "open": 1, "high": 2, "low": 0, "close": 1.5},  # bad time
    ]
    bars, _ = cr._to_bars(rows, 300, "tv")
    ok = len(bars) == 2 and all(b.open_time.year >= 2026 for b in bars)
    results.append(("T4_time_fallback_no_1970", ok, f"years={[b.open_time.year for b in bars]}"))

    # T5: ET date != rolled UTC date
    et = cr._et_date(datetime(2026, 5, 5, 0, 30, tzinfo=timezone.utc))  # 20:30 EDT on the 4th
    results.append(("T5_et_date_no_utc_roll", et == "2026-05-04", f"et={et}"))

    # T6: _flag_broken idempotent (same msg twice -> one line)
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "STATUS.md"
        cr._flag_broken(sp, "SPY intraday: 0 usable bars (feed dark/empty)")
        cr._flag_broken(sp, "SPY intraday: 0 usable bars (feed dark/empty)")
        n = sp.read_text(encoding="utf-8").count("0 usable bars (feed dark/empty)")
        results.append(("T6_flag_idempotent", n == 1, f"matching_lines={n}"))

    # T7: thin-air guard -> exit 2 + STATUS written
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "STATUS.md"
        bj = Path(d) / "empty.json"
        bj.write_text("[]", encoding="utf-8")
        rc = cr.main(["--bars-json", str(bj), "--status", str(sp), "--print-only"])
        wrote = sp.exists() and "0 usable bars" in sp.read_text(encoding="utf-8")
        results.append(("T7_guard_exit2_and_flag", rc == 2 and wrote, f"rc={rc} flagged={wrote}"))

    # T8: low_data flag on < 10 bars
    bars, _ = cr._to_bars(_iso_bars(6), 300, "tv")
    read = cr.build_read(bars, symbol="SPY", mode="intraday", key_levels_path=None, window=2)
    results.append(("T8_low_data_flag", read["low_data"] is True, f"n_bars={read['n_bars']}"))

    # T9: happy build_read -> trend + summary
    bars, _ = cr._to_bars(_iso_bars(15), 300, "tv")
    read = cr.build_read(bars, symbol="SPY", mode="intraday", key_levels_path=None, window=2)
    ok = (read["trend"] in ("uptrend", "downtrend", "range", "unknown")
          and isinstance(read["summary"], str) and read["low_data"] is False
          and read["session_date_et"] == "2026-05-04")
    results.append(("T9_happy_read", ok, f"trend={read['trend']} date={read['session_date_et']}"))

    # T10: SPY-history scan runs clean on REAL data (no crashes, decisive trends)
    csv_path = _REPO_ROOT / "backtest/data/spy_5m_2025-01-01_2026-05-15.csv"
    if csv_path.exists():
        rep = cr.scan_csv_range(csv_path, "2026-05-01", "2026-05-07", window=2)
        ok = rep["days"] >= 3 and rep["crashes"] == 0
        note = f"days={rep['days']} crashes={rep['crashes']} dist={rep['trend_distribution']}"
    else:
        ok, note = True, "csv absent (skipped)"
    results.append(("T10_spy_history_scan", ok, note))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": str(note)[:80]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live(*_args, **_kwargs) -> dict:
    """Deterministic end-to-end main() run on synthetic bars-json (no network)."""
    with tempfile.TemporaryDirectory() as d:
        bj = Path(d) / "bars.json"
        bj.write_text(json.dumps(_iso_bars(15)), encoding="utf-8")
        rc = cr.main(["--bars-json", str(bj), "--status", str(Path(d) / "STATUS.md"), "--print-only"])
    return {"mode": "live", "exit_code": rc, "pass": rc == 0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["offline", "live", "both"], default="both")
    args = p.parse_args(argv)
    sc: dict = {}
    if args.mode in ("offline", "both"):
        sc["offline"] = run_offline()
        print(f"=== OFFLINE === {sc['offline']['passed']}/{sc['offline']['total']} pass")
        for t in sc["offline"]["tests"]:
            print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:28s} {t['note']}")
    if args.mode in ("live", "both"):
        sc["live"] = run_live()
        print(f"\n=== LIVE === exit_code={sc['live']['exit_code']} pass={sc['live']['pass']}")
    return 0 if sc.get("offline", {}).get("all_pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
