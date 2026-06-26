"""Offline tests for data_auditor (stdlib only; creates temp CSVs).

    python backtest/tools/test_data_auditor.py
    pytest backtest/tools/test_data_auditor.py
"""
from __future__ import annotations

import csv
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_auditor as da  # noqa: E402


def _write(rows: list[dict], cols: list[str], name: str = "spy_5m_test.csv") -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / name
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return p


def _good_day(date="2026-07-15", offset="-04:00", n=78, base=550.0):
    """n valid 5-min RTH bars from 09:30, EDT offset, volume>0."""
    rows = []
    start = datetime.fromisoformat(f"{date}T09:30:00{offset}")
    for i in range(n):
        t = start + timedelta(minutes=5 * i)
        px = base + (i % 5) * 0.1
        rows.append({"timestamp_et": t.isoformat(), "open": f"{px:.2f}",
                     "high": f"{px + 0.5:.2f}", "low": f"{px - 0.5:.2f}",
                     "close": f"{px + 0.1:.2f}", "volume": str(10000 + i)})
    return rows


def test_good_spot_green():
    p = _write(_good_day(), da.SPOT_COLS)
    rep = da.audit_csv(p, kind="spot")
    assert rep.verdict == "GREEN", rep.scorecard()


def test_missing_column_reject():
    rows = _good_day(n=3)
    for r in rows:
        del r["volume"]
    p = _write(rows, [c for c in da.SPOT_COLS if c != "volume"])
    rep = da.audit_csv(p, kind="spot")
    assert rep.verdict == "RED"
    assert any(f.check == "schema" for f in rep.findings)


def test_bad_ohlc_reject():
    rows = _good_day(n=10)
    rows[5]["low"] = "999.0"   # low > high
    p = _write(rows, da.SPOT_COLS)
    rep = da.audit_csv(p, kind="spot")
    assert rep.verdict == "RED"
    assert any(f.check == "ohlc_integrity" and f.severity == "REJECT" for f in rep.findings)


def test_utc_mislabel_reject():
    # Summer date but timestamps carry +00:00 (UTC) instead of -04:00 (ET).
    rows = _good_day(offset="+00:00", n=10)
    p = _write(rows, da.SPOT_COLS)
    rep = da.audit_csv(p, kind="spot")
    assert rep.verdict == "RED"
    assert any(f.check == "timezone_dst" and f.severity == "REJECT" for f in rep.findings)


def test_wrong_dst_offset_reject():
    # July is EDT (-04:00); a file claiming -05:00 (EST) is mislabeled.
    rows = _good_day(offset="-05:00", n=10)
    p = _write(rows, da.SPOT_COLS)
    rep = da.audit_csv(p, kind="spot")
    assert any(f.check == "timezone_dst" and f.severity == "REJECT" for f in rep.findings)


def test_winter_est_offset_ok():
    # January IS EST (-05:00) — must NOT flag.
    rows = _good_day(date="2026-01-15", offset="-05:00", n=10)
    p = _write(rows, da.SPOT_COLS)
    rep = da.audit_csv(p, kind="spot")
    assert not any(f.check == "timezone_dst" and f.severity == "REJECT" for f in rep.findings), rep.scorecard()


def test_negative_price_reject():
    rows = _good_day(n=10)
    rows[3]["close"] = "-1.0"
    p = _write(rows, da.SPOT_COLS)
    rep = da.audit_csv(p, kind="spot")
    assert any(f.check == "price_positive" and f.severity == "REJECT" for f in rep.findings)


def test_options_vwap_out_of_range_reject():
    rows = []
    start = datetime.fromisoformat("2026-07-15T09:30:00-04:00")
    for i in range(10):
        t = start + timedelta(minutes=5 * i)
        rows.append({"timestamp_et": t.isoformat(), "open": "1.20", "high": "1.50",
                     "low": "1.00", "close": "1.30",
                     "vwap": ("9.99" if i == 4 else "1.25"),  # one vwap outside [low,high]
                     "volume": "500", "trade_count": "10"})
    p = _write(rows, da.OPTION_COLS, name="SPY260715C00550000.csv")
    rep = da.audit_csv(p, kind="options")
    assert any(f.check == "vwap_in_range" and f.severity == "REJECT" for f in rep.findings), rep.scorecard()


def test_stale_run_warns():
    rows = _good_day(n=10)
    for i in range(2, 7):  # 5 identical OHLC bars
        rows[i].update(open="550.00", high="550.00", low="550.00", close="550.00")
    p = _write(rows, da.SPOT_COLS)
    rep = da.audit_csv(p, kind="spot")
    assert any(f.check == "stale_bars" for f in rep.findings), rep.scorecard()


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
