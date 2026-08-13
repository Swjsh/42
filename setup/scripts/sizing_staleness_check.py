"""Detect sizing constants that were correct at one account size and silently rot at another.

THE CLASS THIS EXISTS FOR (found 2026-08-13, J directive "we're not a home run factory"):

    Rule 6's `min_contracts = 3` was authored when an account held $1-2K. It is an ABSOLUTE
    COUNT while every sibling knob (per_trade_risk_cap_pct, daily_loss_kill_switch_pct) is a
    PERCENTAGE. Percentages rescale themselves; counts do not. Equity tripled to ~$5.5K and the
    floor never moved -- it went from 15.4% of equity to 5.6%.

    That mattered because fleet_executor's recency clamp uses the FLOOR as a CEILING
    (`clamped = min(qty, min_contracts)`), so a risk gate that correctly computed 8 contracts
    was overridden back to the $2K-era 3. And 3 contracts cannot recover a trade's cost below
    +50% (n = ceil(Q/(1+r))), which is why the live TP1 sits at +100% and the strategy only
    pays on home runs.

    Nobody edited anything wrong. The number was right once and nothing re-derived it.
    That is L288-L290's class -- "a cap mis-sized at birth fails silently forever" -- and this
    is its standing detector.

WHAT THIS DOES: reads live equity per arm from the broker, compares each ABSOLUTE sizing
constant against the equity it was authored for, and reports drift. Read-only. Places no
orders, writes no params, arms nothing.

WHAT THIS DELIBERATELY DOES NOT DO: propose a new value. The right floor is a pre-registered
A/B decision (the recency clamp it feeds is itself A/B-validated at -$1,274 improvement, so
raising the floor re-opens a proven-live tradeoff). This detector's ONLY job is to make the
drift VISIBLE so it is decided rather than inherited.

Exit code is always 0 -- this is a reporting instrument and must never break a caller (fail-open).
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
SECRETS = REPO / "automation" / "state" / "fleet" / "secrets.json"
OUT = REPO / "automation" / "state" / "sizing-staleness.json"

# Each entry: the constant, where it lives, and the equity it was AUTHORED for.
# authored_equity is the load-bearing field -- without it "drift" is undefined.
TRACKED: tuple[dict[str, Any], ...] = (
    {
        "key": "min_contracts",
        "params": "automation/state/params.json",
        "arm": "safe-2",
        "authored_equity": 2000.0,
        "authored_note": "Rule 6 'Min 3 contracts (2 TP + 1 runner)', $1-2K era",
        "consumed_by": "fleet_executor._apply_recency_min_sizing (as a CEILING via min())",
    },
    {
        "key": "min_contracts",
        "params": "automation/state/aggressive/params.json",
        "arm": "bold-2",
        "authored_equity": 1648.0,
        "authored_note": "recency-confirmation.json config.equity.bold",
        "consumed_by": "fleet_executor._apply_recency_min_sizing (as a CEILING via min())",
    },
)

# Percentage knobs are listed so the report can state explicitly that they are SELF-SCALING.
# Reporting only the broken ones would hide that the design is mostly correct.
SELF_SCALING = ("per_trade_risk_cap_pct", "daily_loss_kill_switch_pct")

DRIFT_WARN = 1.5   # authored-vs-live equity ratio at which the constant is materially stale
DRIFT_RED = 2.5


def _load(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def live_equity(arm: str) -> Optional[float]:
    """Broker read. Returns None on ANY failure -- never a cached or assumed value, because a
    stale equity read is the exact defect this module exists to detect (C7: no silent fallback)."""
    secrets = _load(SECRETS)
    if not secrets:
        return None
    acct = (secrets.get("accounts") or {}).get(arm)
    if not isinstance(acct, dict) or not acct.get("key"):
        return None
    base = str(acct.get("base_url") or "https://paper-api.alpaca.markets").rstrip("/")
    req = urllib.request.Request(
        base + "/v2/account",
        headers={"APCA-API-KEY-ID": acct["key"], "APCA-API-SECRET-KEY": acct["secret"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return float(json.loads(r.read())["equity"])
    except Exception:  # noqa: BLE001 -- fail-open by contract
        return None


def cost_recovery_min_r(qty: int) -> Optional[float]:
    """Lowest first-tranche gain r that fully recovers the trade's cost AND leaves >=1 runner.

    n = ceil(Q/(1+r)) contracts must be sold to return the whole outlay; a runner exists only
    if n < Q. Entry premium cancels out of the inequality, so this depends on Q alone.
    Returns None when no r in the band works -- which is the finding, not an error.
    """
    for r in (0.20, 0.25, 0.30, 0.40, 0.50):
        if qty - math.ceil(qty / (1.0 + r)) >= 1:
            return r
    return None


def assess() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    worst = "GREEN"
    for spec in TRACKED:
        params = _load(REPO / spec["params"])
        value = None if params is None else params.get(spec["key"])
        eq = live_equity(spec["arm"])
        row: dict[str, Any] = {
            "key": spec["key"], "params_file": spec["params"], "arm": spec["arm"],
            "value": value, "authored_equity": spec["authored_equity"],
            "authored_note": spec["authored_note"], "consumed_by": spec["consumed_by"],
            "live_equity": eq,
        }
        if value is None or eq is None or not spec["authored_equity"]:
            # NOT-RUN is not a pass. Conflating "could not measure" with "measured fine" is a
            # documented failure class here (C7 / L286).
            row["status"] = "NOT_RUN"
            row["why"] = "params key missing" if value is None else "live equity unreadable"
            rows.append(row)
            worst = "RED" if worst != "RED" else worst
            continue
        ratio = eq / float(spec["authored_equity"])
        proportional = max(1, round(float(value) * ratio))
        row["equity_ratio"] = round(ratio, 2)
        row["equity_proportional_value"] = proportional
        row["pct_of_equity_when_authored"] = None
        row["cost_recovery_min_r_at_current"] = cost_recovery_min_r(int(value))
        row["cost_recovery_min_r_at_proportional"] = cost_recovery_min_r(proportional)
        row["status"] = "RED" if ratio >= DRIFT_RED else ("YELLOW" if ratio >= DRIFT_WARN else "GREEN")
        if row["status"] == "RED" or (row["status"] == "YELLOW" and worst == "GREEN"):
            worst = row["status"]
        rows.append(row)
    return {
        "_doc": __doc__.split("\n\n")[0],
        "verdict": worst,
        "drift_warn_ratio": DRIFT_WARN,
        "drift_red_ratio": DRIFT_RED,
        "self_scaling_knobs_not_at_risk": list(SELF_SCALING),
        "rows": rows,
        "finding": "analysis/recommendations/COST-RECOVERY-SIZING-2026-08-13.md",
    }


def render(report: dict[str, Any]) -> str:
    out = [f"SIZING STALENESS: {report['verdict']}"]
    for r in report["rows"]:
        if r["status"] == "NOT_RUN":
            out.append(f"  [NOT_RUN] {r['arm']}.{r['key']} -- {r.get('why')}")
            continue
        rmin = r["cost_recovery_min_r_at_current"]
        rprop = r["cost_recovery_min_r_at_proportional"]
        out.append(
            f"  [{r['status']}] {r['arm']}.{r['key']} = {r['value']} "
            f"(authored @ ${r['authored_equity']:,.0f}, live ${r['live_equity']:,.0f}, "
            f"{r['equity_ratio']}x) -> proportional would be {r['equity_proportional_value']}"
        )
        out.append(
            f"          cost-recovery floor: {'+%d%%' % (rmin * 100) if rmin else 'UNREACHABLE'}"
            f"  ->  at proportional: {'+%d%%' % (rprop * 100) if rprop else 'UNREACHABLE'}"
        )
    out.append(f"  self-scaling (not at risk): {', '.join(report['self_scaling_knobs_not_at_risk'])}")
    return "\n".join(out)


def main() -> int:
    report = assess()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(render(report))
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0  # fail-open by contract


if __name__ == "__main__":
    sys.exit(main())
