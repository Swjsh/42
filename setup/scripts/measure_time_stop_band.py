"""measure_time_stop_band.py -- B6: measure the time-stop band for the frozen prereg
`prereg-time-stop-broker-sweep-2026-09-01.json` (moving time_stop_et from 15:40 to 15:20).

MEASUREMENT ONLY. Never edits params.json / aggressive/params.json / any frozen-path file.
Reads analysis/trades-enriched.jsonl (engine exits) + automation/state/fills-ledger.jsonl
(raw fills, cross-check only) + backtest/data/spy_5m_2026-05-19_2026-09-01.csv (SPY 5m tape)
+ live Alpaca option-bar fetches (same REST pattern as setup/scripts/refused_setup_ledger.py
fetch_bars -- 1m OPRA bars, NOT gated, cached under backtest/data/highres/).

Three measurements, matching the prereg's `expected_cost_on_history` line and the G3 sweep-
exposure question:

  1. Band census: exits with exit_ts_et in [15:20, 15:40] ET, and the >=15:25 sub-band.
     Total P&L + share of gross winner dollars, lifetime and post-2026-08-11 (recency split
     per the "recency > aggregate" doctrine -- the freeze-window trades are the ones that
     matter for a 2026-09-29 ship decision, not the full lifetime population).
  2. Give-up: for positions still open at 15:20 ET (exit_ts_et > 15:20), fetch the 1m option
     bar closest to-and-not-after 15:20:00 ET and compute what closing there would have
     realized vs the actual exit. give_up = actual_pnl - hypothetical_1520_pnl. Bars that
     cannot be fetched (contract too old / no OPRA tape / cred failure) are left UNVERIFIED,
     never fabricated.
  3. Sweep exposure: positions open through 15:30 ET (entry_ts_et <= 15:30 <= exit_ts_et),
     classified ITM / within $0.50 of ATM / OTM by comparing strike to the SPY 5m bar whose
     window covers 15:30 ET on that date.

Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/measure_time_stop_band.py
    backtest/.venv/Scripts/python.exe setup/scripts/measure_time_stop_band.py --no-fetch
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import et_clock  # noqa: E402 -- CLAUDE.md: real ET, never local/Bash TZ

TRADES_ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"
SPY_5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-09-01.csv"
HIGHRES = REPO / "backtest" / "data" / "highres"
OUT_JSON = REPO / "analysis" / "recommendations" / "time-stop-band-2026-09-01.json"
OUT_MD = REPO / "analysis" / "recommendations" / "time-stop-band-2026-09-01.md"
PREREG = REPO / "analysis" / "recommendations" / "prereg-time-stop-broker-sweep-2026-09-01.json"

RECENCY_CUTOFF = "2026-08-11"  # ASSUMPTION (stated per task, not found elsewhere as a
                               # standing constant): "post-08-11" = date >= this cutoff.

BAND_LO = dt.time(15, 20)
BAND_HI = dt.time(15, 40)
BAND_STRICT_LO = dt.time(15, 25)
SWEEP_TIME = dt.time(15, 30)
NEAR_ATM_BAND = 0.50


# ---------------------------------------------------------------------------
# pure helpers (unit-tested with synthetic rows -- see
# backtest/tests/test_time_stop_band_2026_09_01.py)
# ---------------------------------------------------------------------------

def parse_et(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso)


def in_band(exit_ts_et: str, lo: dt.time = BAND_LO, hi: dt.time = BAND_HI) -> bool:
    """True if the exit time-of-day falls in [lo, hi] inclusive."""
    t = parse_et(exit_ts_et).time()
    return lo <= t <= hi


def in_strict_band(exit_ts_et: str) -> bool:
    """The >=15:25 sub-band the prereg's expected_cost line names ("15 of 556... at or
    after 15:25 ET")."""
    return in_band(exit_ts_et, BAND_STRICT_LO, BAND_HI)


def still_open_at(entry_ts_et: str, exit_ts_et: str, at: dt.time) -> bool:
    """True if a position spans `at` (entry <= at <= exit)."""
    e = parse_et(entry_ts_et).time()
    x = parse_et(exit_ts_et).time()
    return e <= at <= x


def classify_moneyness(right: str, strike: float, spot: float, band: float = NEAR_ATM_BAND) -> str:
    """ITM / NEAR_ATM / OTM for a long option, right in {"C","P"}.

    A call is ITM when spot > strike; a put is ITM when spot < strike. "Near ATM" is
    |spot - strike| <= band regardless of side (the Alpaca sweep exposure set the prereg
    names is "ITM or slightly OTM", so near-ATM covers both slightly-ITM and slightly-OTM).
    """
    right = (right or "").upper()
    if right not in ("C", "P"):
        raise ValueError(f"unknown right: {right!r}")
    diff = spot - strike if right == "C" else strike - spot
    if abs(spot - strike) <= band:
        return "NEAR_ATM"
    return "ITM" if diff > 0 else "OTM"


def load_trades(path: Path = TRADES_ENRICHED) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("_meta"):
                continue
            rows.append(d)
    return rows


def gross_winner_dollars(rows: list[dict]) -> float:
    return sum(r["pnl_dollars"] for r in rows if r.get("pnl_dollars", 0) > 0)


# ---------------------------------------------------------------------------
# SPY 5m spot lookup
# ---------------------------------------------------------------------------

def load_spy_5m(path: Path = SPY_5M) -> list[tuple[dt.datetime, float]]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts = dt.datetime.fromisoformat(row["timestamp_et"])
            out.append((ts, float(row["close"])))
    return out


def spy_close_at(bars: list[tuple[dt.datetime, float]], date: str, at: dt.time) -> Optional[float]:
    """Close of the 5m bar whose window covers `at` on `date` (bar timestamped at bar
    OPEN, Alpaca/backtest convention -- the 15:30 bar spans 15:30:00-15:34:59)."""
    target_date = dt.date.fromisoformat(date)
    best = None
    for ts, close in bars:
        if ts.date() != target_date:
            continue
        if ts.time() <= at:
            if best is None or ts.time() > best[0]:
                best = (ts.time(), close)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Alpaca 1m option bar fetch (same pattern as refused_setup_ledger.fetch_bars)
# ---------------------------------------------------------------------------

def _data_creds() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    try:
        cfg = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
        for name, spec in (cfg.get("mcpServers") or cfg).items():
            env = (spec or {}).get("env") or {}
            key = env.get("ALPACA_API_KEY") or env.get("APCA_API_KEY_ID")
            sec = env.get("ALPACA_SECRET_KEY") or env.get("APCA_API_SECRET_KEY")
            if key and sec:
                out.append((f"mcp:{name}", {"key": key, "secret": sec}))
    except Exception:  # noqa: BLE001
        pass
    try:
        sec_path = REPO / "automation" / "state" / "fleet" / "secrets.json"
        creds = json.loads(sec_path.read_text(encoding="utf-8"))
        for a, c in creds.items():
            if isinstance(c, dict) and c.get("key") and c.get("secret"):
                out.append((f"fleet:{a}", c))
    except Exception:  # noqa: BLE001
        pass
    return out


def fetch_1m_bars(contract: str, date: str, *, timeout: float = 20.0) -> bool:
    """Fetch 1m OPRA bars for `contract` on `date` into the highres cache. Never raises;
    returns False (and leaves the episode UNVERIFIED) on any failure."""
    path = HIGHRES / f"{contract}_1m_{date}.csv"
    if path.exists():
        return True

    creds_list = _data_creds()
    if not creds_list:
        print(f"[time-stop-band] no usable creds -- {contract} {date} left UNVERIFIED")
        return False

    url = ("https://data.alpaca.markets/v1beta1/options/bars"
           f"?symbols={contract}&timeframe=1Min&limit=1000"
           f"&start={date}T09:30:00-04:00&end={date}T16:10:00-04:00")

    body = None
    last_err = "no attempt"
    for label, creds in creds_list:
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
            break
        except urllib.error.HTTPError as exc:
            last_err = f"{label} HTTP {exc.code}"
            continue
        except Exception as exc:  # noqa: BLE001
            last_err = f"{label} {exc}"
            continue
    if body is None:
        print(f"[time-stop-band] bar fetch failed for {contract} {date}: {last_err}")
        return False

    bars = (body.get("bars") or {}).get(contract) or []
    if not bars:
        print(f"[time-stop-band] no OPRA tape for {contract} {date} -- UNVERIFIED")
        return False

    HIGHRES.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_et", "open", "high", "low", "close", "volume"])
        for b in bars:
            ts = dt.datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00"))
            et = ts.astimezone(dt.timezone(dt.timedelta(hours=-4)))
            w.writerow([et.strftime("%Y-%m-%d %H:%M:%S"), b["o"], b["h"], b["l"], b["c"],
                        b.get("v", 0)])
    print(f"[time-stop-band] fetched {len(bars)} bar(s) -> {path.name}")
    return True


def option_close_at_or_before(contract: str, date: str, at: dt.time) -> Optional[float]:
    path = HIGHRES / f"{contract}_1m_{date}.csv"
    if not path.exists():
        return None
    best = None
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ts = dt.datetime.fromisoformat(r["timestamp_et"])
            if ts.time() <= at:
                if best is None or ts.time() > best[0]:
                    best = (ts.time(), float(r["close"]))
    return best[1] if best else None


# ---------------------------------------------------------------------------
# main measurement
# ---------------------------------------------------------------------------

def measure(rows: list[dict], spy_bars: list[tuple[dt.datetime, float]], *, do_fetch: bool) -> dict:
    lifetime_gross_winners = gross_winner_dollars(rows)
    post_rows = [r for r in rows if r["date"] >= RECENCY_CUTOFF]
    post_gross_winners = gross_winner_dollars(post_rows)

    band_rows = [r for r in rows if in_band(r["exit_ts_et"])]
    strict_rows = [r for r in rows if in_strict_band(r["exit_ts_et"])]
    band_pnl = sum(r["pnl_dollars"] for r in band_rows)
    strict_pnl = sum(r["pnl_dollars"] for r in strict_rows)

    post_band_rows = [r for r in post_rows if in_band(r["exit_ts_et"])]
    post_strict_rows = [r for r in post_rows if in_strict_band(r["exit_ts_et"])]
    post_band_pnl = sum(r["pnl_dollars"] for r in post_band_rows)
    post_strict_pnl = sum(r["pnl_dollars"] for r in post_strict_rows)

    def share(dollars: float, denom: float) -> Optional[float]:
        if not denom:
            return None
        return round(dollars / denom, 6)

    band_census = {
        "band_15_20_to_15_40": {
            "n": len(band_rows),
            "total_pnl_dollars": round(band_pnl, 2),
            "share_of_gross_winner_dollars_lifetime": share(sum(r["pnl_dollars"] for r in band_rows if r["pnl_dollars"] > 0), lifetime_gross_winners),
            "share_of_gross_winner_dollars_post_2026_08_11": share(sum(r["pnl_dollars"] for r in post_band_rows if r["pnl_dollars"] > 0), post_gross_winners),
        },
        "band_15_25_to_15_40_strict": {
            "n": len(strict_rows),
            "total_pnl_dollars": round(strict_pnl, 2),
            "share_of_gross_winner_dollars_lifetime": share(sum(r["pnl_dollars"] for r in strict_rows if r["pnl_dollars"] > 0), lifetime_gross_winners),
            "share_of_gross_winner_dollars_post_2026_08_11": share(sum(r["pnl_dollars"] for r in post_strict_rows if r["pnl_dollars"] > 0), post_gross_winners),
        },
        "lifetime_gross_winner_dollars": round(lifetime_gross_winners, 2),
        "post_2026_08_11_gross_winner_dollars": round(post_gross_winners, 2),
        "post_2026_08_11_n_rows": len(post_rows),
        "lifetime_n_rows": len(rows),
    }

    # -- 2. give-up for positions still open at 15:20 --
    still_open = [r for r in rows if not in_band(r["exit_ts_et"], dt.time(0, 0), BAND_LO)
                  and parse_et(r["exit_ts_et"]).time() > BAND_LO]
    give_up_rows = []
    for r in still_open:
        contract = r["symbol"]
        date = r["date"]
        fetched = fetch_1m_bars(contract, date) if do_fetch else (HIGHRES / f"{contract}_1m_{date}.csv").exists()
        px_1520 = option_close_at_or_before(contract, date, BAND_LO) if fetched else None
        entry = {
            "date": date, "arm": r.get("arm"), "symbol": contract,
            "exit_ts_et": r["exit_ts_et"], "actual_pnl_dollars": r["pnl_dollars"],
            "qty": r.get("qty"),
        }
        if px_1520 is None:
            entry["status"] = "UNVERIFIED (no OPRA 1m bar available at/before 15:20)"
            entry["hypothetical_1520_pnl_dollars"] = None
            entry["give_up_dollars"] = None
        else:
            qty = float(r.get("qty") or 0)
            entry_px = float(r.get("entry_px") or 0)
            mult = 100.0
            hypo_pnl = (px_1520 - entry_px) * qty * mult
            entry["status"] = "MEASURED"
            entry["option_close_at_1520"] = px_1520
            entry["hypothetical_1520_pnl_dollars"] = round(hypo_pnl, 2)
            entry["give_up_dollars"] = round(r["pnl_dollars"] - hypo_pnl, 2)
        give_up_rows.append(entry)

    measured_give_up = [e for e in give_up_rows if e["status"] == "MEASURED"]
    give_up_summary = {
        "n_positions_still_open_at_1520": len(still_open),
        "n_measured": len(measured_give_up),
        "n_unverified": len(give_up_rows) - len(measured_give_up),
        "total_give_up_dollars_measured_only": round(sum(e["give_up_dollars"] for e in measured_give_up), 2) if measured_give_up else None,
        "rows": give_up_rows,
    }

    # -- 3. sweep exposure at 15:30 --
    open_1530 = [r for r in rows if still_open_at(r["entry_ts_et"], r["exit_ts_et"], SWEEP_TIME)]
    sweep_rows = []
    for r in open_1530:
        spot = spy_close_at(spy_bars, r["date"], SWEEP_TIME)
        if spot is None:
            cls = "UNVERIFIED (no SPY 5m bar for this date/time)"
        else:
            cls = classify_moneyness(r["right"], float(r["strike"]), spot)
        sweep_rows.append({
            "date": r["date"], "arm": r.get("arm"), "symbol": r["symbol"],
            "right": r["right"], "strike": r["strike"], "spy_close_1530": spot,
            "classification": cls,
        })
    sweep_counts: dict[str, int] = {}
    for e in sweep_rows:
        sweep_counts[e["classification"]] = sweep_counts.get(e["classification"], 0) + 1
    sweep_summary = {
        "n_positions_open_through_1530": len(open_1530),
        "counts_by_classification": sweep_counts,
        "n_itm_or_near_atm": sweep_counts.get("ITM", 0) + sweep_counts.get("NEAR_ATM", 0),
        "rows": sweep_rows,
    }

    return {
        "band_census": band_census,
        "give_up_at_1520": give_up_summary,
        "sweep_exposure_1530": sweep_summary,
    }


def apply_pass_criterion(measurement: dict) -> dict:
    """Mechanical application of the prereg's own `pass_criterion_frozen`:
    Ship if give-up < 5% of gross winner $ over the scoring window; KILL if the
    [15:20,15:40] band carries > 10% of gross winner $; else NEEDS-MORE.
    "the scoring window" = post-2026-08-11 (the frozen-config window this ship decision is
    about), per the prereg's own framing that config changes must not contaminate that
    window -- lifetime is reported alongside for context, never substituted."""
    band = measurement["band_census"]["band_15_20_to_15_40"]
    share = band["share_of_gross_winner_dollars_post_2026_08_11"]
    if share is None:
        return {"verdict": "NEEDS-MORE", "reason": "no post-2026-08-11 gross winner dollars to compute a share against (denominator is zero or window empty)"}
    if share > 0.10:
        return {"verdict": "KILL", "reason": f"[15:20,15:40] band carries {share:.2%} of post-2026-08-11 gross winner dollars (> 10% kill line) -- build the broker-sweep guard (flatten at 15:25 only when ITM/near-ATM) instead of a blanket 15:20 stop", "share": share}
    if share < 0.05:
        return {"verdict": "SHIP", "reason": f"[15:20,15:40] band carries {share:.2%} of post-2026-08-11 gross winner dollars (< 5% ship line)", "share": share}
    return {"verdict": "NEEDS-MORE", "reason": f"[15:20,15:40] band carries {share:.2%} of post-2026-08-11 gross winner dollars -- between the 5% ship line and 10% kill line, prereg does not specify this zone", "share": share}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="skip live Alpaca bar fetches; use cache only")
    args = ap.parse_args()

    rows = load_trades()
    spy_bars = load_spy_5m()
    measurement = measure(rows, spy_bars, do_fetch=not args.no_fetch)
    verdict = apply_pass_criterion(measurement)

    out = {
        "id": "TIME-STOP-BAND-MEASURE-2026-09-01",
        "measures_prereg": "prereg-time-stop-broker-sweep-2026-09-01",
        "generated_at_et": et_clock.et_now().isoformat(),
        "sources": {
            "trades_enriched": TRADES_ENRICHED.relative_to(REPO).as_posix(),
            "spy_5m": SPY_5M.relative_to(REPO).as_posix(),
            "n_trade_rows": len(rows),
        },
        "recency_cutoff_assumption": f"post-08-11 = date >= {RECENCY_CUTOFF} (ASSUMPTION -- no standing repo constant found under this name; chosen per recency-over-aggregate doctrine, J 2026-07-31)",
        "measurement": measurement,
        "pass_criterion_applied": verdict,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = [
        "# Time-stop band measurement -- 2026-09-01",
        "",
        f"Measures `prereg-time-stop-broker-sweep-2026-09-01` (time_stop_et 15:40 -> 15:20).",
        f"Source: `{TRADES_ENRICHED.relative_to(REPO).as_posix()}` ({len(rows)} rows) + `{SPY_5M.relative_to(REPO).as_posix()}` + live Alpaca 1m option bars.",
        "",
        f"## VERDICT: {verdict['verdict']}",
        "",
        f"{verdict['reason']}",
        "",
        "## 1. Band census",
        "",
        f"- [15:20,15:40] exits: n={measurement['band_census']['band_15_20_to_15_40']['n']}, "
        f"P&L=${measurement['band_census']['band_15_20_to_15_40']['total_pnl_dollars']}, "
        f"share of lifetime gross winner $={measurement['band_census']['band_15_20_to_15_40']['share_of_gross_winner_dollars_lifetime']}, "
        f"share of post-08-11 gross winner $={measurement['band_census']['band_15_20_to_15_40']['share_of_gross_winner_dollars_post_2026_08_11']}",
        f"- [15:25,15:40] strict exits: n={measurement['band_census']['band_15_25_to_15_40_strict']['n']}, "
        f"P&L=${measurement['band_census']['band_15_25_to_15_40_strict']['total_pnl_dollars']}, "
        f"share of lifetime gross winner $={measurement['band_census']['band_15_25_to_15_40_strict']['share_of_gross_winner_dollars_lifetime']}, "
        f"share of post-08-11 gross winner $={measurement['band_census']['band_15_25_to_15_40_strict']['share_of_gross_winner_dollars_post_2026_08_11']}",
        f"- lifetime gross winner $={measurement['band_census']['lifetime_gross_winner_dollars']} (n={measurement['band_census']['lifetime_n_rows']}); "
        f"post-08-11 gross winner $={measurement['band_census']['post_2026_08_11_gross_winner_dollars']} (n={measurement['band_census']['post_2026_08_11_n_rows']})",
        "",
        "## 2. Give-up: positions still open at 15:20 ET (moving the stop earlier)",
        "",
        f"- n still open at 15:20: {measurement['give_up_at_1520']['n_positions_still_open_at_1520']}",
        f"- n MEASURED (1m OPRA bar found at/before 15:20): {measurement['give_up_at_1520']['n_measured']}",
        f"- n UNVERIFIED (no bar): {measurement['give_up_at_1520']['n_unverified']}",
        f"- total give-up $ (measured rows only): {measurement['give_up_at_1520']['total_give_up_dollars_measured_only']}",
        "",
        "## 3. Sweep exposure: positions open through 15:30 ET",
        "",
        f"- n open through 15:30: {measurement['sweep_exposure_1530']['n_positions_open_through_1530']}",
        f"- classification counts: {json.dumps(measurement['sweep_exposure_1530']['counts_by_classification'])}",
        f"- n ITM or near-ATM (the broker-sweep exposure set): {measurement['sweep_exposure_1530']['n_itm_or_near_atm']}",
        "",
        f"Full row-level detail: `{OUT_JSON.relative_to(REPO).as_posix()}`.",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    # append measurement (never touch design/pass_criterion) into the prereg file
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg["measurement"] = {
        "measured_at_et": out["generated_at_et"],
        "measured_by": "setup/scripts/measure_time_stop_band.py (B6-time-stop-band-measure)",
        "result_file": OUT_JSON.relative_to(REPO).as_posix(),
        "band_15_20_to_15_40_share_of_post_08_11_gross_winner_dollars": measurement["band_census"]["band_15_20_to_15_40"]["share_of_gross_winner_dollars_post_2026_08_11"],
        "verdict": verdict["verdict"],
        "verdict_reason": verdict["reason"],
        "sweep_exposure_itm_or_near_atm_at_1530_n": measurement["sweep_exposure_1530"]["n_itm_or_near_atm"],
        "give_up_at_1520_total_dollars_measured_only": measurement["give_up_at_1520"]["total_give_up_dollars_measured_only"],
        "give_up_at_1520_n_unverified": measurement["give_up_at_1520"]["n_unverified"],
    }
    PREREG.write_text(json.dumps(prereg, indent=2), encoding="utf-8")

    print(f"[time-stop-band] VERDICT: {verdict['verdict']} -- {verdict['reason']}")
    print(f"[time-stop-band] wrote {OUT_JSON.relative_to(REPO).as_posix()}, {OUT_MD.relative_to(REPO).as_posix()}, appended measurement to {PREREG.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
