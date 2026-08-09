#!/usr/bin/env python3
"""Build the per-station weather calibration table from archived forecasts vs official records.

TWO INDEPENDENT SOURCES, deliberately:
  * forecast : Open-Meteo historical-forecast archive -- what the model ACTUALLY SAID at the
               time. Not reanalysis/analysis, which has already seen the weather and would be
               look-ahead (C6).
  * truth    : NOAA NCEI daily-summaries (GHCN) TMAX -- the official daily max for the exact
               station. This is the same basis Kalshi settles on.

WHY REGIME STRATIFICATION: a first pass on Central Park gave mean bias +0.48F over 432 days --
but +3.49F over the most recent hot week and +7.1F on a single hot day. A single global constant
would therefore be WRONG exactly when the market is most interesting. So bias is fit per
temperature band, and the band's own residual sigma is what sizing must use.

The output is not a strategy. It is the honest uncertainty that any strategy must respect:
if sigma is wider than the market's implied spread, there is no edge and we say so.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "weather-calibration-table.json"

# series -> (GHCN station id, NWS id, lat, lon, label). GHCN id is the settlement record.
STATIONS = [
    ("KXHIGHNY",   "USW00094728", "KNYC", 40.7789,  -73.9692, "NYC Central Park"),
    ("KXHIGHCHI",  "USW00014819", "KMDW", 41.7860,  -87.7524, "Chicago Midway"),
    ("KXHIGHMIA",  "USW00012839", "KMIA", 25.7906,  -80.3164, "Miami Intl"),
    ("KXHIGHAUS",  "USW00013904", "KAUS", 30.1975,  -97.6664, "Austin-Bergstrom"),
    ("KXHIGHLAX",  "USW00023174", "KLAX", 33.9381, -118.3889, "Los Angeles Intl"),
    ("KXHIGHDEN",  "USW00003017", "KDEN", 39.8467, -104.6564, "Denver Intl"),
    ("KXHIGHPHIL", "USW00013739", "KPHL", 39.8683,  -75.2311, "Philadelphia Intl"),
]

START, END = "2024-01-01", "2026-08-07"

# Temperature bands (F) for regime-stratified bias. Bands are on the FORECAST value, because
# at decision time that is all we have -- conditioning on the observation would be look-ahead.
BANDS = [(-99, 50), (50, 65), (65, 75), (75, 85), (85, 95), (95, 999)]
MIN_BAND_N = 20     # below this a band's own stats are noise; fall back to the global fit


def _fetch(url: str, retries: int = 2) -> str:
    for a in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "gamma-weather-cal/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode()
        except Exception:  # noqa: BLE001
            if a == retries:
                raise
            time.sleep(2 * (a + 1))
    return ""


def official_tmax(ghcn: str) -> dict[str, float]:
    url = ("https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries"
           f"&stations={ghcn}&startDate={START}&endDate={END}"
           "&dataTypes=TMAX&format=csv&units=standard")
    rows = list(csv.DictReader(io.StringIO(_fetch(url))))
    return {r["DATE"]: float(r["TMAX"]) for r in rows if r.get("TMAX") not in (None, "")}


def archived_forecast(lat: float, lon: float) -> dict[str, float]:
    url = ("https://historical-forecast-api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}&start_date={START}&end_date={END}"
           "&daily=temperature_2m_max&temperature_unit=fahrenheit"
           "&timezone=auto&models=gfs_seamless")
    d = json.loads(_fetch(url)).get("daily", {})
    return {day: v for day, v in zip(d.get("time", []), d.get("temperature_2m_max", []))
            if v is not None}


def band_of(f: float) -> str:
    for lo, hi in BANDS:
        if lo <= f < hi:
            return f"{lo}-{hi}"
    return "unknown"


def calibrate(series: str, ghcn: str, nws: str, lat: float, lon: float, label: str) -> dict:
    truth = official_tmax(ghcn)
    fcst = archived_forecast(lat, lon)
    pairs = [(d, fcst[d], truth[d]) for d in sorted(fcst) if d in truth]
    if len(pairs) < 50:
        return {"series": series, "label": label, "n": len(pairs), "usable": False,
                "reason": "insufficient paired history"}

    errs = [f - o for _, f, o in pairs]
    g_bias, g_sd = statistics.mean(errs), statistics.stdev(errs)

    bands: dict[str, dict] = {}
    for lo, hi in BANDS:
        sel = [f - o for _, f, o in pairs if lo <= f < hi]
        key = f"{lo}-{hi}"
        if len(sel) >= MIN_BAND_N:
            bands[key] = {"n": len(sel), "bias": round(statistics.mean(sel), 3),
                          "sigma": round(statistics.stdev(sel), 3)}
        elif sel:
            bands[key] = {"n": len(sel), "bias": round(g_bias, 3), "sigma": round(g_sd, 3),
                          "fallback": True}

    return {
        "series": series, "label": label, "ghcn": ghcn, "nws": nws,
        "lat": lat, "lon": lon, "n": len(pairs), "usable": True,
        "global": {"bias": round(g_bias, 3), "sigma": round(g_sd, 3)},
        "bands": bands,
        "window": [START, END],
    }


def main() -> int:
    table = {"_doc": "Per-station forecast->settlement calibration. bias = forecast - observed; "
                     "SUBTRACT bias from a raw forecast. sigma = residual uncertainty AFTER "
                     "correction -- that is what sizing must use, never the ensemble spread.",
             "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "sources": {"forecast": "open-meteo historical-forecast (archived model runs)",
                         "truth": "NOAA NCEI daily-summaries GHCN TMAX"},
             "stations": {}}

    print(f"{'STATION':<22}{'N':>6}{'BIAS':>9}{'SIGMA':>8}   HOT-BAND (85-95 / 95+)")
    print("-" * 82)
    for args in STATIONS:
        try:
            c = calibrate(*args)
        except Exception as e:  # noqa: BLE001
            print(f"{args[5]:<22} ERROR {str(e)[:40]}")
            continue
        table["stations"][args[0]] = c
        if not c.get("usable"):
            print(f"{c['label']:<22}{c['n']:>6}   UNUSABLE ({c.get('reason')})")
            continue
        hot = c["bands"].get("85-95", {})
        vhot = c["bands"].get("95-999", {})
        hs = f"{hot.get('bias', float('nan')):+.2f}/{hot.get('sigma', float('nan')):.2f}" if hot else "n/a"
        vs = f"{vhot.get('bias', float('nan')):+.2f}/{vhot.get('sigma', float('nan')):.2f}" if vhot else "n/a"
        print(f"{c['label']:<22}{c['n']:>6}{c['global']['bias']:>+8.2f}F{c['global']['sigma']:>7.2f}F"
              f"   {hs:>12}  {vs:>12}")
        time.sleep(0.5)

    OUT.write_text(json.dumps(table, indent=2))
    print("-" * 82)
    ok = sum(1 for c in table["stations"].values() if c.get("usable"))
    print(f"calibrated {ok}/{len(STATIONS)} stations -> {OUT.name}")
    print("\nSIGMA is the number that decides tradeability: it must be NARROWER than the")
    print("market's implied spread. Bias is fixable; sigma is not.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
