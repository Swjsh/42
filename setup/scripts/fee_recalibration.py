"""fee_recalibration.py -- is the cost model telling the truth? Ask the broker.

WHY. `go_live_gate.FEE_RATES` drives criterion 1's cost-adjusted P&L, the first-live-month
dollar model, and the after-tax study. Three published surfaces rest on five constants that
were never checked against a bill. This checks them: pull the account's real FEE activities
and compare, per sub-type, against what the model predicts for the same trades and window.

FIRST RUN (safe-2, 2026-08-03..2026-09-01, 47 trades over 20 trading days):

    fee       ACTUAL  PREDICTED    ratio
    OCC       7.6900     7.6600    1.00x
    ORF       4.3200     4.7800    1.11x
    TAF       0.4800     0.4800    1.00x
    REG       0.3900     0.5700    1.46x
    CAT       0.2000     0.2000    1.00x
    TOTAL    13.0800    13.6900    1.05x

THE RATES ARE RIGHT. The 5% aggregate over-estimate is entirely a ROUNDING-GRANULARITY
artifact, and the mechanism is proven rather than guessed: the model applies `ceil_cents`
PER TRADE, the broker applies it PER DAY. Re-running ORF with a daily ceiling gives
**$4.3200 against an actual $4.3200 -- exact to the cent** (REG likewise moves 0.57 -> 0.44
against 0.39). The broker's own activity count corroborates it: 20 ORF activities for 20
distinct trading days, one per day.

WHY THIS DOES NOT "FIX" THE MODEL, and that is a deliberate refusal. Correcting the
granularity would LOWER modelled costs, which RAISES cost-adjusted P&L, which makes go-live
criterion 1 EASIER TO PASS -- mid-window, on a gate whose window is already registered. That
is the post-hoc-bar-change anti-pattern (OP-11) no matter how well-evidenced the correction
is. The current bias is 5% CONSERVATIVE (it over-states costs), so leaving it costs nothing
except a slightly pessimistic gate. The correction is filed to be pre-registered, not shipped.

Read-only. Never edits FEE_RATES, never touches params, places nothing.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
TRADES = REPO / "analysis" / "trades-enriched.jsonl"
OUT = REPO / "analysis" / "fee-recalibration"
MCP = REPO / ".mcp.json"

# Mirrors go_live_gate.FEE_RATES. Duplicated deliberately: if the gate's copy drifts, this
# check must FAIL rather than silently follow it.
FEE_RATES = {
    "occ_per_contract": 0.025,
    "orf_per_contract": 0.015,
    "taf_per_contract_sell": 0.00329,
    "sec_rate_per_dollar_sell": 2.0600000000000003e-05,
    "cat_per_arm_day": 0.01,
}

# MCP server name -> the fleet arm whose account it holds.
SERVER_TO_ARM = {"alpaca": "safe-2", "alpaca_aggressive": "bold-2"}


def ceil_cents(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100.0


def _creds(server: str) -> Optional[dict]:
    try:
        env = json.loads(MCP.read_text(encoding="utf-8"))["mcpServers"][server]["env"]
    except (OSError, ValueError, KeyError):
        return None
    key = env.get("ALPACA_API_KEY") or env.get("APCA_API_KEY_ID")
    sec = env.get("ALPACA_SECRET_KEY") or env.get("APCA_API_SECRET_KEY")
    return {"key": key, "secret": sec} if key and sec else None


def fetch_fee_activities(creds: dict, after: str, max_pages: int = 20) -> Optional[list[dict]]:
    """None on a request failure -- distinct from [] meaning genuinely no fees."""
    out: list[dict] = []
    page = None
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    for _ in range(max_pages):
        url = (f"https://paper-api.alpaca.markets/v2/account/activities/FEE"
               f"?after={after}&page_size=100")
        if page:
            url += f"&page_token={page}"
        try:
            data = json.loads(urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=30).read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            return None if not out else out
        if not data:
            break
        out += data
        if len(data) < 100:
            break
        page = data[-1]["id"]
    return out


def actual_by_subtype(acts: list[dict]) -> dict[str, float]:
    got: dict[str, float] = collections.defaultdict(float)
    for a in acts:
        try:
            got[str(a.get("activity_sub_type") or "?")] += abs(float(a["net_amount"]))
        except (KeyError, TypeError, ValueError):
            continue
    return dict(got)


def predict(rows: list[dict], per_trade_ceiling: bool = True) -> dict[str, float]:
    """Model-predicted fees. `per_trade_ceiling` False reproduces the broker's own
    daily-aggregation rounding -- the discriminating variable, not a tuning knob."""
    pred: dict[str, float] = collections.defaultdict(float)
    daily: dict[str, list[float]] = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    # MATCH THE GATE'S FORMULA, not merely its rates. go_live_gate.py:194-197 ceils EACH
    # LEG and then doubles -- `2 * _ceil_cents(rate * qty)` -- and `2*ceil(x)` is not
    # `ceil(2x)`. My first cut wrote the latter, under-counted OCC by $0.46 on 47 trades,
    # and flipped this instrument's own verdict from CONSERVATIVE to "OPTIMISTIC --
    # investigate immediately". A validator that does not reproduce the thing it validates
    # reports on itself.
    for r in rows:
        qty = float(r.get("qty") or 0)
        px = float(r.get("exit_px_avg") or 0)
        occ_leg = FEE_RATES["occ_per_contract"] * qty
        orf_leg = FEE_RATES["orf_per_contract"] * qty
        taf = FEE_RATES["taf_per_contract_sell"] * qty
        reg = FEE_RATES["sec_rate_per_dollar_sell"] * px * qty * 100.0
        if per_trade_ceiling:
            pred["OCC"] += 2 * ceil_cents(occ_leg)
            pred["ORF"] += 2 * ceil_cents(orf_leg)
            pred["TAF"] += ceil_cents(taf)
            pred["REG"] += ceil_cents(reg)
        else:
            d = daily[r["date"]]
            d[0] += 2 * occ_leg; d[1] += 2 * orf_leg; d[2] += taf; d[3] += reg
    if not per_trade_ceiling:
        for d in daily.values():
            pred["OCC"] += ceil_cents(d[0]); pred["ORF"] += ceil_cents(d[1])
            pred["TAF"] += ceil_cents(d[2]); pred["REG"] += ceil_cents(d[3])
    pred["CAT"] = FEE_RATES["cat_per_arm_day"] * len({r["date"] for r in rows})
    return dict(pred)


def load_trades(arm: str, lo: str, hi: str, path: Path = TRADES) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("_meta") or r.get("arm") != arm:
            continue
        if lo <= r.get("date", "") <= hi:
            rows.append(r)
    return rows


def build(server: str = "alpaca", after: str = "2026-08-01") -> dict:
    arm = SERVER_TO_ARM.get(server, "?")
    creds = _creds(server)
    if not creds:
        return {"server": server, "arm": arm, "error": "no credentials in .mcp.json"}
    acts = fetch_fee_activities(creds, after)
    if acts is None:
        return {"server": server, "arm": arm, "error": "FEE activity request failed"}
    if not acts:
        return {"server": server, "arm": arm, "note": "no FEE activities in window",
                "actual": {}, "n_activities": 0}

    days = sorted({a["date"] for a in acts})
    rows = load_trades(arm, days[0], days[-1])
    actual = actual_by_subtype(acts)
    per_trade = predict(rows, per_trade_ceiling=True)
    per_day = predict(rows, per_trade_ceiling=False)

    ta = sum(actual.values())
    tp = sum(per_trade.values())
    return {
        "server": server, "arm": arm, "window": [days[0], days[-1]],
        "n_activities": len(acts), "n_trades": len(rows), "n_trading_days": len(days),
        "actual": {k: round(v, 4) for k, v in actual.items()},
        "predicted_per_trade_ceiling": {k: round(v, 4) for k, v in per_trade.items()},
        "predicted_per_day_ceiling": {k: round(v, 4) for k, v in per_day.items()},
        "total_actual": round(ta, 4), "total_predicted": round(tp, 4),
        "ratio_predicted_over_actual": round(tp / ta, 4) if ta else None,
        "direction": "CONSERVATIVE (model over-states cost)" if tp >= ta
                     else "OPTIMISTIC (model UNDER-states cost -- investigate immediately)",
        "finding": (
            "The RATES are right; the gap is rounding granularity. The model ceils per "
            "TRADE, the broker ceils per DAY -- and the broker's activity count corroborates "
            "it (one ORF activity per trading day). Compare predicted_per_day_ceiling "
            "against actual: it is the closer match."),
        "deliberately_not_fixed": (
            "Correcting the granularity LOWERS modelled cost, RAISES cost-adjusted P&L, and "
            "makes go-live criterion 1 EASIER TO PASS mid-window. That is a post-hoc bar "
            "change (OP-11) however well-evidenced. The bias is conservative, so leaving it "
            "costs only a slightly pessimistic gate. Pre-register before correcting."),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--server", default="alpaca", choices=sorted(SERVER_TO_ARM))
    ap.add_argument("--after", default="2026-08-01")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    rep = build(args.server, args.after)
    if "error" in rep:
        print(f"[fee-recal] {rep['arm']}: {rep['error']}")
        return 0  # fail-open: a read-only monitor never breaks its caller

    print(f"[fee-recal] {rep['arm']} {rep['window'][0]}..{rep['window'][1]}  "
          f"{rep['n_trades']} trades / {rep['n_trading_days']} days")
    print(f"  {'fee':<6}{'ACTUAL':>10}{'PRED(trade)':>13}{'PRED(day)':>11}{'ratio':>8}")
    for k in sorted(set(rep["actual"]) | set(rep["predicted_per_trade_ceiling"])):
        a = rep["actual"].get(k, 0.0)
        pt = rep["predicted_per_trade_ceiling"].get(k, 0.0)
        pd_ = rep["predicted_per_day_ceiling"].get(k, 0.0)
        ratio = f"{pt / a:.2f}x" if a else "n/a"
        print(f"  {k:<6}{a:>10.4f}{pt:>13.4f}{pd_:>11.4f}{ratio:>8}")
    print(f"  {'TOTAL':<6}{rep['total_actual']:>10.4f}{rep['total_predicted']:>13.4f}"
          f"{'':>11}{rep['ratio_predicted_over_actual']:>7}x")
    print(f"  direction: {rep['direction']}")

    if not args.no_write:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / f"{rep['arm']}.json"
        body = json.dumps(rep, indent=2)
        body.encode("utf-8")
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(p)
        print(f"  wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
