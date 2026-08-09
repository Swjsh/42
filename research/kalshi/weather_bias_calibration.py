#!/usr/bin/env python3
"""Weather-market calibration harness — measure model-vs-settlement bias BEFORE trading it.

ORIGIN (2026-08-09): a naive ensemble-vs-market comparison produced an apparent "+34% edge"
on Kalshi's NYC high-temp market. It was entirely model error. Ground truth that evening:

    Central Park (KNYC) actual high : 87.1 F
    GFS 0.25 ensemble median        : 94.2 F   <- off by 7.1 F
    ensemble full range 91.7-96.8   : did not even CONTAIN the observed value
    the market priced "<=90" at 95-97c and was RIGHT

Root cause: Kalshi settles on ONE specific station. Central Park is a vegetated park and runs
~4-5 F cooler than the surrounding airports (LGA 91.4, EWR 91.9, JFK 91.4 the same day). A
0.25-degree GFS cell (~25 km) averages the whole metro, which is dominated by urban/asphalt
surfaces. So the grid is structurally warmer than the sensor that decides the payout.

THE LESSON, generalised: on any settlement-based market, the model must be calibrated to the
EXACT settlement instrument, not to the general area. An uncalibrated model does not produce a
small edge -- it produces a large FAKE one, with the sign determined by a systematic bias.

WHAT THIS DOES: appends one row per city per day of (forecast distribution, actual settlement)
so a per-station bias correction can be FIT rather than guessed. It places no trades and
computes no edge. Trading is gated on the calibration existing first.

    python research/kalshi/weather_bias_calibration.py            # log today + show status
    python research/kalshi/weather_bias_calibration.py --report   # calibration report only
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "weather-calibration.jsonl"

# Kalshi high-temp series -> the NWS station that ACTUALLY settles it, plus that station's
# coordinates. The station is the contract's truth; the coordinates are only what we feed the
# model. Getting this pairing wrong is the entire bug this file exists to prevent.
CITIES = [
    # series,       station, lat,      lon,        label
    ("KXHIGHNY",   "KNYC", 40.7789,  -73.9692, "NYC Central Park"),
    ("KXHIGHCHI",  "KMDW", 41.7860,  -87.7524, "Chicago Midway"),
    ("KXHIGHMIA",  "KMIA", 25.7906,  -80.3164, "Miami Intl"),
    ("KXHIGHAUS",  "KAUS", 30.1975,  -97.6664, "Austin-Bergstrom"),
    ("KXHIGHLAX",  "KLAX", 33.9381,  -118.3889, "Los Angeles Intl"),
    ("KXHIGHDEN",  "KDEN", 39.8467,  -104.6564, "Denver Intl"),
    ("KXHIGHPHIL", "KPHL", 39.8683,  -75.2311, "Philadelphia Intl"),
]

# Minimum paired observations before ANY calibrated probability may be used for sizing.
MIN_SAMPLES_TO_TRADE = 30


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "gamma-weather-calibration/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def ensemble_distribution(lat: float, lon: float, days: int = 2) -> dict[str, list[float]]:
    """Raw GFS ensemble daily max temps (F), keyed by ISO date. UNCALIBRATED by construction."""
    url = (f"https://ensemble-api.open-meteo.com/v1/ensemble?latitude={lat}&longitude={lon}"
           f"&daily=temperature_2m_max&models=gfs025&temperature_unit=fahrenheit"
           f"&forecast_days={days}&timezone=auto")
    d = _get(url)
    daily = d.get("daily", {})
    members = [k for k in daily if k.startswith("temperature_2m_max")]
    out: dict[str, list[float]] = {}
    for i, day in enumerate(daily.get("time", [])):
        vals = [daily[m][i] for m in members if daily[m][i] is not None]
        if vals:
            out[day] = vals
    return out


def observed_high(station: str, day: str) -> float | None:
    """Actual observed max temp (F) for a station on an ISO date -- the settlement truth."""
    try:
        obs = _get(f"https://api.weather.gov/stations/{station}/observations?limit=200")
    except Exception:  # noqa: BLE001 - a dead station is data, not a crash
        return None
    temps = [
        p["temperature"]["value"] * 9 / 5 + 32
        for f in obs.get("features", [])
        if (p := f.get("properties")) and p.get("timestamp", "")[:10] == day
        and (p.get("temperature") or {}).get("value") is not None
    ]
    return round(max(temps), 1) if temps else None


@dataclass
class Row:
    day: str
    series: str
    station: str
    label: str
    n_members: int
    fcst_median: float
    fcst_p10: float
    fcst_p90: float
    observed: float | None
    error: float | None       # forecast_median - observed; POSITIVE = model runs warm


def collect(day: str) -> list[Row]:
    rows: list[Row] = []
    for series, station, lat, lon, label in CITIES:
        try:
            dist = ensemble_distribution(lat, lon)
        except Exception as e:  # noqa: BLE001
            print(f"  {label:<22} ensemble ERR {str(e)[:40]}")
            continue
        vals = dist.get(day)
        if not vals:
            print(f"  {label:<22} no ensemble data for {day}")
            continue
        vals = sorted(vals)
        n = len(vals)
        obs = observed_high(station, day)
        med = round(statistics.median(vals), 1)
        rows.append(Row(
            day=day, series=series, station=station, label=label, n_members=n,
            fcst_median=med,
            fcst_p10=round(vals[max(0, int(0.10 * n))], 1),
            fcst_p90=round(vals[min(n - 1, int(0.90 * n))], 1),
            observed=obs,
            error=round(med - obs, 1) if obs is not None else None,
        ))
    return rows


def append(rows: list[Row]) -> int:
    """Idempotent per (day, station): re-running the same day overwrites, never duplicates."""
    existing: dict[tuple[str, str], dict] = {}
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[(r.get("day"), r.get("station"))] = r
    for row in rows:
        existing[(row.day, row.station)] = row.__dict__
    with LEDGER.open("w", encoding="utf-8") as fh:
        for _, r in sorted(existing.items()):
            fh.write(json.dumps(r) + "\n")
    return len(existing)


def report() -> None:
    if not LEDGER.exists():
        print("no calibration data yet -- run without --report first")
        return
    by_station: dict[str, list[dict]] = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("error") is not None:
            by_station.setdefault(r["station"], []).append(r)

    print(f"\n{'STATION':<10}{'CITY':<22}{'N':>4}{'MEAN BIAS':>11}{'STDEV':>8}"
          f"{'|MAX ERR|':>10}   STATUS")
    print("-" * 84)
    for station, rows in sorted(by_station.items()):
        errs = [r["error"] for r in rows]
        n = len(errs)
        mean = statistics.mean(errs)
        sd = statistics.stdev(errs) if n > 1 else float("nan")
        status = ("CALIBRATING" if n < MIN_SAMPLES_TO_TRADE
                  else "READY (apply correction)")
        label = rows[-1].get("label", "")[:21]
        sd_s = f"{sd:>7.2f}" if n > 1 else f"{'n/a':>7}"
        print(f"{station:<10}{label:<22}{n:>4}{mean:>+10.2f}F{sd_s}{max(abs(e) for e in errs):>9.1f}F"
              f"   {status}")
    total = sum(len(v) for v in by_station.values())
    print("-" * 84)
    print(f"paired samples: {total} | gate: {MIN_SAMPLES_TO_TRADE} per station before ANY sizing")
    print("\nMEAN BIAS is the correction to SUBTRACT from the raw ensemble median.")
    print("STDEV is the residual after correction -- THAT is the real forecast uncertainty,")
    print("and it must be narrower than the market's implied spread for an edge to exist.")
    print("A large mean bias is fixable. A large STDEV is not -- it means no edge, ever.")


def backfill_observations() -> int:
    """Fill in settlements for stored forecasts whose day has now COMPLETED.

    Deliberately forward-only: we store the forecast as it existed BEFORE the day resolved,
    then attach the observation afterwards. Reading a model's after-the-fact analysis for a
    past day would be look-ahead (C6) -- the analysis has already seen the weather, so it
    would flatter the model and manufacture an edge that cannot be traded.
    """
    if not LEDGER.exists():
        return 0
    rows, filled = [], 0
    today = date.today().isoformat()
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("observed") is None and r.get("day", "") < today:
            obs = observed_high(r["station"], r["day"])
            if obs is not None:
                r["observed"] = obs
                r["error"] = round(r["fcst_median"] - obs, 1)
                filled += 1
                print(f"  backfilled {r['label']:<22} {r['day']}  "
                      f"fcst={r['fcst_median']:.1f}F obs={obs:.1f}F  err={r['error']:+.1f}F")
        rows.append(r)
    with LEDGER.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return filled


def main() -> int:
    ap = argparse.ArgumentParser(description="Kalshi weather calibration harness")
    ap.add_argument("--report", action="store_true", help="report only, collect nothing")
    args = ap.parse_args()

    if args.report:
        report()
        return 0

    print("[1/2] backfilling settlements for completed days ...")
    n = backfill_observations()
    print(f"      {n} row(s) resolved")

    # Store the CURRENT forecast for today and tomorrow. The observation is attached on a
    # later run, once the day is over -- that ordering is what keeps this look-ahead-free.
    print("[2/2] recording current forecasts ...")
    stored = 0
    for offset in (0, 1):
        day = (date.today() + timedelta(days=offset)).isoformat()
        rows = collect(day)
        for r in rows:
            print(f"  {r.label:<22} {day}  fcst_med={r.fcst_median:>6.1f}F  "
                  f"p10-p90 {r.fcst_p10:.1f}-{r.fcst_p90:.1f}F"
                  + (f"  observed={r.observed:.1f}F err={r.error:+.1f}F" if r.observed is not None else ""))
        stored += len(rows)
        append(rows)

    print(f"\nstored {stored} forecast rows -> {LEDGER.name}")
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
