#!/usr/bin/env python3
"""The autonomous Kalshi weather lane: predict -> score itself -> earn the right to trade.

DESIGN PRINCIPLE: the loop does not start by trading. It starts by being MEASURED. Each run
it (1) scores every past prediction against the official settlement, (2) makes new predictions,
and (3) trades ONLY the cities whose live scorecard has cleared the bar. A city that has not
proven itself stays in shadow indefinitely. Nobody has to remember to check.

WHY THE BAR EXISTS -- two hard lessons from 2026-08-09, both earned the same day:
  * An UNCALIBRATED model showed a "+34% edge" on NYC temps. It was 7F of model error. The
    market was right. Uncalibrated models do not produce small errors; they produce large
    confident ones.
  * After calibration our sigma is narrower than the market's implied sigma in 6 of 7 cities
    -- but our MU still disagrees by up to 1.5F. A tight sigma on a wrong mu is WORSE than no
    model: it sizes up into the wrong bucket. So sigma alone can never authorise a trade.
    Only realised, out-of-sample hit rate can.

Scoring is honest by construction: the prediction is written BEFORE the day resolves and is
never rewritten. Settlement is attached afterwards from NOAA's official record.

    python kalshi_auto.py              # score + predict + (trade only if earned)
    python kalshi_auto.py --scorecard  # show the scorecard, change nothing
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[1]

from kalshi_client import KalshiClient, KalshiError, load_credentials, fee_dollars  # noqa: E402

CAL_TABLE = REPO / "research" / "kalshi" / "weather-calibration-table.json"
STATE = REPO / "automation" / "state" / "kalshi"
PREDICTIONS = STATE / "weather-predictions.jsonl"
TRADES = STATE / "weather-trades.jsonl"

ARM_ENV = "GAMMA_KALSHI_ARMED"

# --- the bar a city must clear before ANY real money is committed -------------
MIN_SCORED_DAYS = 20          # out-of-sample settled predictions required
MIN_HIT_RATE = 0.45           # our top-pick bucket must actually win this often
MAX_MEAN_ABS_ERR = 1.6        # our mu must land within this many F on average

# --- per-trade gates ---------------------------------------------------------
MIN_EDGE = 0.06               # model P minus ask, after fees
MAX_SPREAD_CENTS = 3.0
MIN_DEPTH = 25
KELLY_FRACTION = 0.25         # quarter Kelly -- the ruin model made this non-negotiable
MAX_STAKE_FRAC = 0.20         # never risk >20% of balance on one contract
MIN_CONTRACTS = 5             # below this the fee ceiling surcharge bites


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "gamma-kalshi-auto/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def ticker_tag(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.year % 100:02d}{d.strftime('%b').upper()}{d.day:02d}"


def band_for(station: dict, raw: float) -> dict:
    """Regime-stratified bias. rsplit handles the negative lower bound ('-99-50')."""
    for key, val in station.get("bands", {}).items():
        lo, hi = key.rsplit("-", 1)
        if float(lo) <= raw < float(hi):
            return val
    return station["global"]


def forecast(station: dict) -> list[tuple[str, float]]:
    """Current gfs_seamless forecast -- MUST match the model the calibration was fit on."""
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={station['lat']}&longitude={station['lon']}"
           "&daily=temperature_2m_max&temperature_unit=fahrenheit"
           "&forecast_days=2&timezone=auto&models=gfs_seamless")
    d = _get(url).get("daily", {})
    return [(day, v) for day, v in zip(d.get("time", []), d.get("temperature_2m_max", []))
            if v is not None]


def official_high(ghcn: str, day: str) -> float | None:
    url = ("https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries"
           f"&stations={ghcn}&startDate={day}&endDate={day}&dataTypes=TMAX"
           "&format=json&units=standard")
    try:
        rows = _get(url)
    except Exception:  # noqa: BLE001
        return None
    for r in rows or []:
        if r.get("TMAX") not in (None, ""):
            return float(r["TMAX"])
    return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def score_pending() -> int:
    """Attach settlements to predictions whose day has closed. Never rewrites a prediction."""
    rows = read_jsonl(PREDICTIONS)
    today = date.today().isoformat()
    filled = 0
    for r in rows:
        if r.get("observed") is not None or r.get("day", "") >= today:
            continue
        obs = official_high(r["ghcn"], r["day"])
        if obs is None:
            continue                      # NCEI lags a day or two; try again next run
        r["observed"] = obs
        r["abs_err"] = round(abs(r["mu"] - obs), 2)
        lo, hi = r.get("pick_lo"), r.get("pick_hi")
        if lo is not None and hi is not None:
            r["pick_won"] = bool(lo < obs <= hi)
        filled += 1
    if filled:
        write_jsonl(PREDICTIONS, rows)
    return filled


def scorecard() -> dict[str, dict]:
    """Per-city realised performance. This -- not sigma -- is what authorises trading."""
    out: dict[str, dict] = {}
    for r in read_jsonl(PREDICTIONS):
        if r.get("observed") is None:
            continue
        s = out.setdefault(r["series"], {"label": r["label"], "n": 0, "hits": 0,
                                         "err_sum": 0.0, "scored": []})
        s["n"] += 1
        s["hits"] += 1 if r.get("pick_won") else 0
        s["err_sum"] += r.get("abs_err", 0.0)
    for s in out.values():
        s["hit_rate"] = s["hits"] / s["n"] if s["n"] else 0.0
        s["mean_abs_err"] = s["err_sum"] / s["n"] if s["n"] else float("inf")
        s["earned"] = (s["n"] >= MIN_SCORED_DAYS
                       and s["hit_rate"] >= MIN_HIT_RATE
                       and s["mean_abs_err"] <= MAX_MEAN_ABS_ERR)
    return out


def ladder(client: KalshiClient, series: str, tag: str) -> list[dict]:
    """FULL ladder via pagination -- a partial fetch silently halves the probability mass."""
    out, cursor = [], ""
    while True:
        path = f"/markets?series_ticker={series}&status=open&limit=1000"
        if cursor:
            path += f"&cursor={cursor}"
        resp = client._request("GET", path)  # noqa: SLF001 - pagination needs the raw call
        out += resp.get("markets", [])
        cursor = resp.get("cursor") or ""
        if not cursor:
            break
    return [m for m in out if tag in m.get("ticker", "")]


def evaluate(client: KalshiClient, series: str, station: dict) -> dict | None:
    """Produce one prediction + the best available trade candidate for a city."""
    fc = forecast(station)
    if len(fc) < 2:
        return None
    day, raw = fc[1]                       # tomorrow: today's high is already largely set
    tag = ticker_tag(day)
    markets = ladder(client, series, tag)
    buckets = [m for m in markets
               if m.get("floor_strike") is not None and m.get("cap_strike") is not None]
    if len(buckets) < 4:
        return None

    band = band_for(station, raw)
    mu, sd = raw - band["bias"], band["sigma"]

    scored = []
    for m in buckets:
        lo, hi = m["floor_strike"], m["cap_strike"]
        try:
            bid = float(m.get("yes_bid_dollars") or 0)
            ask = float(m.get("yes_ask_dollars") or 0)
        except (TypeError, ValueError):
            continue
        if ask <= 0:
            continue
        p = ncdf((hi - mu) / sd) - ncdf((lo - mu) / sd)
        scored.append({"ticker": m["ticker"], "lo": lo, "hi": hi,
                       "bid": bid, "ask": ask, "p": p})
    if not scored:
        return None

    mass = sum(s["p"] for s in scored)
    top = max(scored, key=lambda s: s["p"])
    return {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "day": day, "series": series, "label": station["label"], "ghcn": station["ghcn"],
        "raw_forecast": raw, "bias": band["bias"], "sigma": sd, "mu": round(mu, 2),
        "ladder_mass": round(mass, 3),
        "pick_ticker": top["ticker"], "pick_lo": top["lo"], "pick_hi": top["hi"],
        "pick_p": round(top["p"], 4), "pick_ask": top["ask"],
        "observed": None, "candidates": scored,
    }


def best_trade(pred: dict, balance: float) -> dict | None:
    """Kelly-sized maker order on the strongest edge, or None if nothing clears the gates."""
    best = None
    for s in pred["candidates"]:
        spread = round((s["ask"] - s["bid"]) * 100, 1)
        if spread > MAX_SPREAD_CENTS or s["bid"] <= 0:
            continue
        price = s["bid"]                        # MAKER: join the bid, never cross
        fee = fee_dollars(100, price, maker=True) / 100
        edge = s["p"] - price - fee
        if edge < MIN_EDGE or s["p"] <= price:
            continue
        kelly = (s["p"] - price) / (1 - price)
        frac = min(kelly * KELLY_FRACTION, MAX_STAKE_FRAC)
        stake = balance * frac
        contracts = int(stake // price)
        if contracts < MIN_CONTRACTS:
            continue
        cand = {**s, "spread_cents": spread, "edge": round(edge, 4),
                "kelly": round(kelly, 4), "fraction": round(frac, 4),
                "contracts": contracts, "stake": round(contracts * price, 2),
                "limit_cents": int(round(price * 100))}
        if best is None or cand["edge"] > best["edge"]:
            best = cand
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="Autonomous Kalshi weather lane")
    ap.add_argument("--scorecard", action="store_true", help="show scorecard only")
    args = ap.parse_args()

    table = json.loads(CAL_TABLE.read_text())
    stations = {k: v for k, v in table["stations"].items() if v.get("usable")}

    if args.scorecard:
        show_scorecard()
        return 0

    print("[1/3] scoring settled predictions ...")
    print(f"      {score_pending()} newly settled")

    creds = load_credentials("kalshi-1")
    client = KalshiClient(creds)
    armed = os.environ.get(ARM_ENV, "").strip() == "1" and creds is not None

    balance = 0.0
    if creds:
        try:
            cents = client.balance().get("balance")
            balance = float(cents) / 100 if isinstance(cents, (int, float)) else 0.0
        except KalshiError as e:
            print(f"      balance unavailable ({e}) -- shadow only")
            armed = False
    print(f"[2/3] balance ${balance:.2f} | armed={armed} | mode={'LIVE' if armed else 'SHADOW'}")

    card = scorecard()
    preds = read_jsonl(PREDICTIONS)
    seen = {(p["day"], p["series"]) for p in preds}

    print("[3/3] predictions for tomorrow:")
    placed = 0
    for series, st in stations.items():
        try:
            pred = evaluate(client, series, st)
        except Exception as e:  # noqa: BLE001 - one bad city must not kill the run
            print(f"   {st['label']:<22} ERROR {str(e)[:40]}")
            continue
        if pred is None:
            print(f"   {st['label']:<22} no complete ladder listed yet")
            continue

        cs = card.get(series, {})
        earned = cs.get("earned", False)
        status = (f"n={cs.get('n', 0)} hit={cs.get('hit_rate', 0):.0%} "
                  f"err={cs.get('mean_abs_err', float('nan')):.2f}F")
        trade = best_trade(pred, balance) if (earned and balance > 0) else None

        print(f"   {pred['label']:<22} mu={pred['mu']:.1f}F sd={pred['sigma']:.2f} "
              f"pick={pred['pick_lo']:.0f}-{pred['pick_hi']:.0f} p={pred['pick_p']:.0%} "
              f"ask={pred['pick_ask']:.2f} | {status} | "
              f"{'EARNED' if earned else 'NOT EARNED - shadow'}")

        if trade:
            pred["intended_trade"] = trade
            if armed:
                coid = f"gamma-wx-{uuid.uuid4().hex[:14]}"
                try:
                    resp = client.place_order(
                        ticker=trade["ticker"], side="yes", action="buy",
                        count=trade["contracts"], limit_price_cents=trade["limit_cents"],
                        client_order_id=coid)
                    order = resp.get("order") or {}
                    pred["order_id"] = order.get("order_id")
                    placed += 1
                    print(f"      PLACED {trade['contracts']}x @ {trade['limit_cents']}c "
                          f"(${trade['stake']:.2f}, edge {trade['edge']:.1%})")
                    with TRADES.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({**trade, "day": pred["day"],
                                             "series": series, "order_id": order.get("order_id"),
                                             "ts_utc": pred["ts_utc"]}) + "\n")
                except (KalshiError, ValueError) as e:
                    print(f"      ORDER FAILED: {e}")
            else:
                print(f"      would place {trade['contracts']}x @ {trade['limit_cents']}c "
                      f"(${trade['stake']:.2f}, edge {trade['edge']:.1%}) [shadow]")

        if (pred["day"], series) not in seen:
            preds.append(pred)

    write_jsonl(PREDICTIONS, preds)
    print(f"\npredictions on file: {len(preds)} | orders placed this run: {placed}")
    show_scorecard()
    return 0


def show_scorecard() -> None:
    card = scorecard()
    print(f"\n{'CITY':<22}{'SCORED':>8}{'HIT RATE':>10}{'MEAN |ERR|':>12}   STATUS")
    print("-" * 74)
    if not card:
        print("  (no settled predictions yet -- the loop must run for several days first)")
    for series, s in sorted(card.items()):
        print(f"{s['label']:<22}{s['n']:>8}{s['hit_rate']:>9.0%}{s['mean_abs_err']:>11.2f}F"
              f"   {'EARNED - trading' if s['earned'] else 'shadow'}")
    print("-" * 74)
    print(f"bar: >={MIN_SCORED_DAYS} settled days, hit rate >={MIN_HIT_RATE:.0%}, "
          f"mean |err| <={MAX_MEAN_ABS_ERR}F")
    print("Sigma being narrower than the market does NOT authorise a trade -- only this does.")


if __name__ == "__main__":
    sys.exit(main())
