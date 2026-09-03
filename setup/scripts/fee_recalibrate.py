"""fee_recalibrate.py -- weekly broker-truth fee drift monitor for go_live_gate.py.

WHY (queue.md FEE-RECALIBRATION-FROM-BROKER, LOW): go_live_gate.py's reconciliation
criterion and cost-adjusted statistical criterion both lean on a STATIC FEE_RATES dict
calibrated once, 2026-08-18. Nothing has checked it against a real bill since. This pulls
Alpaca FEE activities (OCC/ORF/TAF/REG/CAT) for every active arm over the trailing 14 days,
derives the realized rate implied by what the broker actually charged, and reports drift
against the gate's static dict.

FREEZE, NOT AUTO-CORRECT (same discipline as the existing single-arm deep-diagnostic
setup/scripts/fee_recalibration.py, and OP-11 -- never change a bar mid-window post-hoc):
this script NEVER writes FEE_RATES anywhere, in this file or in go_live_gate.py. It writes
only automation/state/fee-calibration.json, a disclosure/monitoring surface. If drift
crosses a threshold, a HUMAN decides whether/when to pre-register a rate change -- this
script's job stops at reporting the number.

RELATIONSHIP TO setup/scripts/fee_recalibration.py: that script is a one-off, single-arm
(--server alpaca|alpaca_aggressive), by-hand deep diagnostic that explains WHY a gap exists
(per-trade vs per-day rounding ceiling) and writes analysis/fee-recalibration/{arm}.json.
THIS script is the RECURRING, ALL-ACTIVE-ARMS (accounts.json-derived roster, matching
go_live_gate's own reconciliation_criterion), book-wide drift monitor meant to run
unattended on a schedule (Gamma_FeeRecalibrate, weekly) and emit one GREEN/YELLOW/RED
status a future consumer can read at a stable path. Both are read-only; neither ever
touches FEE_RATES in go_live_gate.py. Kept as two files, not merged, because they answer
different questions (one-off root-cause vs recurring drift-alarm) and neither script's
tests should have to carry the other's fixture shape.

FEE_RATES below is a DELIBERATE independent copy of go_live_gate.FEE_RATES (not an import)
-- the same defensive posture fee_recalibration.py already uses: a drift-check that imports
the value it is checking cannot catch that value drifting. Guard
backtest/tests/test_fee_recalibrate_2026_09_03.py pins the two copies equal; that pin is
itself the "must FAIL loudly if the gate's copy moves" mechanism.

Realized rate is DERIVED, not independently re-solved per physical unit: each fee type's
dollar total is linear in its own rate constant for a fixed trade set (see go_live_gate.
fee_ex_cat's formula, reproduced verbatim below), so
realized_rate = static_rate * (actual_dollars / predicted_dollars_at_static_rate) recovers
the rate the broker's actual charge implies, without needing a separate per-unit ledger
column Alpaca doesn't expose per FEE activity row.

Run:
    backtest/.venv/Scripts/python.exe setup/scripts/fee_recalibrate.py
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import sys
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from et_clock import et_now  # noqa: E402
import go_live_gate as glg  # noqa: E402 -- READ-ONLY reuse of the canonical active-arm
# roster (accounts.json-derived, avoids re-hardcoding a THIRD stale arm list -- the exact
# bug class go_live_gate._load_active_arms itself was built to fix) and the fleet secrets
# path. This module never calls anything in go_live_gate that writes state, and never
# imports go_live_gate.FEE_RATES (see module docstring above for why that copy stays
# independent).

TRADES_ENRICHED = glg.TRADES_ENRICHED
SECRETS_PATH = glg.SECRETS_PATH
OUT_PATH = REPO / "automation" / "state" / "fee-calibration.json"

LOOKBACK_DAYS = 14

# Independent copy of go_live_gate.FEE_RATES (its 2026-08-18 calibration) -- see module
# docstring for why this is NOT an import. Guard test pins equality.
FEE_RATES = {
    "occ_per_contract": 0.025,
    "orf_per_contract": 0.015,
    "taf_per_contract_sell": 0.00329,
    "sec_rate_per_dollar_sell": 2.0600000000000003e-05,
    "cat_per_arm_day": 0.01,
}

# Alpaca activity_sub_type -> the FEE_RATES key it corresponds to.
SUBTYPE_TO_RATE_KEY = {
    "OCC": "occ_per_contract",
    "ORF": "orf_per_contract",
    "TAF": "taf_per_contract_sell",
    "REG": "sec_rate_per_dollar_sell",
    "CAT": "cat_per_arm_day",
}

YELLOW_DRIFT_PCT = 10.0
RED_DRIFT_PCT = 25.0


def _ceil_cents(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100.0


def _creds(arm: str, secrets: dict) -> "dict | None":
    a = secrets.get(arm, {})
    key = a.get("api_key") or a.get("ALPACA_API_KEY") or a.get("key", "")
    sec = a.get("secret_key") or a.get("ALPACA_SECRET_KEY") or a.get("secret", "")
    base = a.get("base_url", "https://paper-api.alpaca.markets")
    if not key:
        return None
    return {"key": key, "secret": sec, "base": base}


def fetch_fee_activities(creds: dict, after: str, max_pages: int = 20) -> "list[dict] | None":
    """None on a request failure -- distinct from [] meaning genuinely no fees in window."""
    out: list = []
    page = None
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    base = creds["base"].rstrip("/")
    for _ in range(max_pages):
        url = f"{base}/v2/account/activities/FEE?after={after}&page_size=100"
        if page:
            url += f"&page_token={page}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                data = json.loads(r.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            return None if not out else out
        if not data:
            break
        out += data
        if len(data) < 100:
            break
        page = data[-1]["id"]
    return out


def actual_by_subtype(acts: list) -> dict:
    got: dict = collections.defaultdict(float)
    for a in acts:
        try:
            got[str(a.get("activity_sub_type") or "?")] += abs(float(a["net_amount"]))
        except (KeyError, TypeError, ValueError):
            continue
    return dict(got)


def load_trades(arm: str, lo: str, hi: str, path: Path) -> list:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("_meta") or r.get("arm") != arm:
            continue
        if lo <= r.get("date", "") <= hi:
            rows.append(r)
    return rows


def predict_per_type(rows: list, n_arm_days: int) -> dict:
    """Model-predicted fee dollars per type -- reproduces go_live_gate.fee_ex_cat's own
    per-trade-ceiling formula EXACTLY (2 * ceil_cents(rate * qty) for the doubled
    entry+exit legs OCC/ORF; ceil_cents(rate * qty) for TAF sell-leg-only;
    ceil_cents(rate * sell proceeds) for REG/SEC). A predictor that does not reproduce the
    formula it is validating would report on itself, not on the gate."""
    pred: dict = collections.defaultdict(float)
    for r in rows:
        qty = float(r.get("qty") or 0.0)
        px = r.get("exit_px_avg")
        if px is None:
            continue
        px = float(px)
        pred["OCC"] += 2 * _ceil_cents(FEE_RATES["occ_per_contract"] * qty)
        pred["ORF"] += 2 * _ceil_cents(FEE_RATES["orf_per_contract"] * qty)
        pred["TAF"] += _ceil_cents(FEE_RATES["taf_per_contract_sell"] * qty)
        pred["REG"] += _ceil_cents(FEE_RATES["sec_rate_per_dollar_sell"] * px * qty * 100.0)
    pred["CAT"] = FEE_RATES["cat_per_arm_day"] * n_arm_days
    return dict(pred)


def qty_basis_per_type(rows: list, n_arm_days: int) -> dict:
    """The basis each FEE_RATES key is actually denominated in -- contracts (doubled for
    the round-trip legs OCC/ORF), contracts (TAF, sell leg), dollars of sell proceeds
    (REG), arm-days (CAT). Reported alongside the realized rate as n_contracts for context
    only -- never used in the drift-percent math itself (that compares dollar totals)."""
    total_qty = sum(float(r.get("qty") or 0.0) for r in rows)
    total_proceeds = sum(
        float(r.get("qty") or 0.0) * float(r["exit_px_avg"]) * 100.0
        for r in rows if r.get("exit_px_avg") is not None
    )
    return {
        "OCC": 2 * total_qty, "ORF": 2 * total_qty, "TAF": total_qty,
        "REG": total_proceeds, "CAT": float(n_arm_days),
    }


def build(lookback_days: int = LOOKBACK_DAYS) -> dict:
    today = et_now().date()
    after = (today - timedelta(days=lookback_days)).isoformat()

    try:
        secrets = json.loads(SECRETS_PATH.read_text(encoding="utf-8")).get("accounts", {})
    except (OSError, ValueError) as e:
        return {
            "as_of": et_now().isoformat(timespec="seconds"),
            "instrument": "setup/scripts/fee_recalibrate.py",
            "error": f"cannot read {SECRETS_PATH}: {type(e).__name__}: {e}",
            "status": "RED", "per_type": {}, "per_arm": {}, "max_drift_pct": None,
        }

    arms = list(glg.ACTIVE_ARMS)
    actual_totals: dict = collections.defaultdict(float)
    predicted_totals: dict = collections.defaultdict(float)
    basis_totals: dict = collections.defaultdict(float)
    per_arm = {}
    fetch_errors = []

    for arm in arms:
        creds = _creds(arm, secrets)
        if creds is None:
            per_arm[arm] = {"error": "no credentials in fleet/secrets.json"}
            fetch_errors.append(arm)
            continue
        acts = fetch_fee_activities(creds, after)
        if acts is None:
            per_arm[arm] = {"error": "FEE activity request failed"}
            fetch_errors.append(arm)
            continue
        actual = actual_by_subtype(acts)
        act_days = sorted({a.get("date", "") for a in acts if a.get("date")})
        window_lo = act_days[0] if act_days else after
        window_hi = act_days[-1] if act_days else today.isoformat()
        rows = load_trades(arm, window_lo, window_hi, TRADES_ENRICHED)
        n_arm_days = len({r["date"] for r in rows})
        predicted = predict_per_type(rows, n_arm_days)
        basis = qty_basis_per_type(rows, n_arm_days)

        for k in SUBTYPE_TO_RATE_KEY:
            actual_totals[k] += actual.get(k, 0.0)
            predicted_totals[k] += predicted.get(k, 0.0)
            basis_totals[k] += basis.get(k, 0.0)

        per_arm[arm] = {
            "window": [window_lo, window_hi], "n_activities": len(acts),
            "n_trades": len(rows), "n_trading_days": n_arm_days,
            "actual": {k: round(actual.get(k, 0.0), 4) for k in SUBTYPE_TO_RATE_KEY},
            "predicted": {k: round(predicted.get(k, 0.0), 4) for k in SUBTYPE_TO_RATE_KEY},
        }

    per_type = {}
    max_drift = 0.0
    for sub, rate_key in SUBTYPE_TO_RATE_KEY.items():
        static_rate = FEE_RATES[rate_key]
        actual_total = actual_totals[sub]
        predicted_total = predicted_totals[sub]
        basis = basis_totals[sub]
        realized_rate = (round(static_rate * (actual_total / predicted_total), 8)
                          if predicted_total else None)
        drift_pct = (round((actual_total - predicted_total) / predicted_total * 100.0, 2)
                     if predicted_total else None)
        if drift_pct is not None:
            max_drift = max(max_drift, abs(drift_pct))
        per_type[sub] = {
            "rate_key": rate_key,
            "static": static_rate,
            "realized": realized_rate,
            "n_contracts": round(basis, 2),
            "actual_total": round(actual_total, 4),
            "predicted_total": round(predicted_total, 4),
            "drift_pct": drift_pct,
        }

    total_actual = sum(actual_totals.values())
    total_predicted = sum(predicted_totals.values())
    note = ("READ-ONLY drift monitor. NEVER edits go_live_gate.FEE_RATES -- drift is "
            "reported, the gate keeps its static dict (freeze, per OP-11). Realized rates "
            "here are DERIVED (static_rate scaled by the actual/predicted dollar ratio), "
            "not independently re-solved per physical unit -- see module docstring.")

    if arms and fetch_errors == arms:
        status, max_drift_out = "RED", None
        note += " ALL arms failed to fetch -- status forced RED (no data is not GREEN)."
    elif not arms:
        status, max_drift_out = "RED", None
        note += " ACTIVE_ARMS roster is empty -- nothing to reconcile."
    elif total_actual == 0.0 and total_predicted == 0.0:
        status, max_drift_out = "YELLOW", None
        note += (" No FEE activity and no matching trades found for ANY arm in this "
                 "lookback window -- nothing to compare; not a validated GREEN.")
    elif max_drift > RED_DRIFT_PCT:
        status, max_drift_out = "RED", round(max_drift, 2)
    elif max_drift > YELLOW_DRIFT_PCT:
        status, max_drift_out = "YELLOW", round(max_drift, 2)
    else:
        status, max_drift_out = "GREEN", round(max_drift, 2)

    return {
        "as_of": et_now().isoformat(timespec="seconds"),
        "instrument": "setup/scripts/fee_recalibrate.py",
        "note": note,
        "lookback_days": lookback_days,
        "window_after": after,
        "roster": arms,
        "fetch_errors": fetch_errors,
        "per_type": per_type,
        "per_arm": per_arm,
        "max_drift_pct": max_drift_out,
        "status": status,
        "thresholds": {"yellow_gt_pct": YELLOW_DRIFT_PCT, "red_gt_pct": RED_DRIFT_PCT},
    }


def _summary_line(rep: dict) -> str:
    parts = []
    for k, v in rep.get("per_type", {}).items():
        parts.append(f"{k}={v['drift_pct']}%" if v.get("drift_pct") is not None else f"{k}=n/a")
    return (f"[fee-recal] status={rep.get('status')} max_drift_pct={rep.get('max_drift_pct')} "
            f"roster={rep.get('roster')} " + " ".join(parts))


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rep = build(args.lookback_days)

    if not args.no_write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        tmp.replace(OUT_PATH)

    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(_summary_line(rep))
        if not args.no_write:
            print(f"[fee-recal] wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
