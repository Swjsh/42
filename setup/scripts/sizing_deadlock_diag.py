"""sizing_deadlock_diag.py — explain, per arm, WHY an order would be refused.

THE INSTRUMENT THIS EXISTS FOR (2026-07-30 incident)
----------------------------------------------------
Core Safe produced 9 x RISK_DENY_RISK_CAP in one session and the ledger could not
say whether that was "the proposal was too big" or "this arm cannot trade AT ALL at
today's option prices". It was the second one:

    equity $1,160.42 x per_trade_risk_cap_pct 0.30 = $348.13 cap
    min_contracts 3 x $1.42 premium x 100          = $426 notional
    => no legal qty exists; the arm is blind above $1.16/contract,
       and ATM 0DTE SPY traded $1.42-$2.01 all session.

That condition recurs at ANY equity where `min_contracts x premium x 100` exceeds
the effective cap, so it needs a standing instrument, not a one-off note.

WHAT IT DOES
------------
  * --all-arms (default): the per-arm ceiling table — for each live arm, the premium
    above which that arm cannot trade at all. This is the number an operator needs.
  * --arm ID --premium X: full binding-constraint explanation for one candidate order,
    including the equity at which that premium would become tradeable.

READ-ONLY / DRY-RUN ONLY. There is no mode that places, cancels, or modifies anything;
`--dry-run` is accepted and defaulted ON purely so the intent is explicit at the call
site. The only network calls are Alpaca GET /v2/account for equity (skippable with
--equity). Keys are loaded at runtime from the gitignored fleet/secrets.json and are
never printed. $0, no LLM.

Run:
    python setup/scripts/sizing_deadlock_diag.py
    python setup/scripts/sizing_deadlock_diag.py --arm safe-2 --premium 1.50
    python setup/scripts/sizing_deadlock_diag.py --all-arms --equity 2000 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest/lib", "automation/state/fleet", "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

import risk_gate as rg  # noqa: E402

# Display order = the 5 LIVE SPY arms. Mirrors accounts_status.ORDER (the canonical
# roster view); safe-1 is deliberately absent (retired 2026-07-11, and it points at
# the SAME broker account as safe-2 — listing it double-counts).
ARM_ORDER = ["safe-2", "safe-3", "bold-2", "risky-1", "risky-3"]

ACCOUNTS_JSON = REPO / "automation" / "state" / "fleet" / "accounts.json"
SECRETS_JSON = REPO / "automation" / "state" / "fleet" / "secrets.json"


def _load_arms() -> dict:
    """arm_id -> arm dict, from the fleet roster (the source of truth for arms)."""
    data = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    return {str(a["id"]): a for a in data.get("arms", [])}


def _params_for(arm: Mapping[str, Any]) -> dict:
    """Per-arm params via fleet_executor's OWN resolver — never a re-implementation.

    fleet_executor._params_for is what the live fleet path uses (base SAFE/BOLD
    params.json + the arm's params_patch), and heartbeat_core reads the same two
    params.json files for safe-2/bold-2, so this is faithful for all 5 arms.
    """
    import fleet_executor as fx  # noqa: PLC0415 - heavy import, CLI-only

    return fx._params_for(arm)


def _live_equity(arm_id: str) -> Optional[float]:
    """Live equity via Alpaca REST, using the same read path as accounts_status.py.

    Returns None on any failure — the caller then requires an explicit --equity.
    Secrets are read from the gitignored fleet/secrets.json and NEVER printed.
    """
    try:
        import accounts_status as acs  # noqa: PLC0415

        secrets = json.loads(SECRETS_JSON.read_text(encoding="utf-8")).get("accounts", {})
        a = secrets.get(arm_id, {})
        key = a.get("api_key") or a.get("ALPACA_API_KEY") or a.get("key", "")
        sec = a.get("secret_key") or a.get("ALPACA_SECRET_KEY") or a.get("secret", "")
        base = a.get("base_url", "https://paper-api.alpaca.markets")
        if not key:
            return None
        r = acs._query(key, sec, base)
        return float(r["equity"]) if r.get("ok") else None
    except Exception:  # noqa: BLE001 - diagnostic must never hard-fail on a broker hiccup
        return None


def arm_report(arm_id: str, arm: Mapping[str, Any], equity: Optional[float],
               premium: Optional[float]) -> dict:
    """Full diagnostic for one arm. Pure aside from the params read."""
    params = _params_for(arm)
    out: dict = {
        "arm": arm_id,
        "display_name": arm.get("display_name"),
        "account_number": arm.get("account_number"),
        "equity": equity,
        "min_contracts": params.get("min_contracts"),
        "per_trade_risk_cap_pct": params.get("per_trade_risk_cap_pct"),
        "has_v15_tier_table": "v15_max_premium_pct_of_account" in params,
        "min_entry_premium": params.get("min_entry_premium"),
    }
    if equity is None:
        out["error"] = "no live equity (broker unreachable / no key) — pass --equity"
        return out

    # The ceiling is premium-independent, so probe at any legal premium to get the
    # cap block, then read premium_ceiling off it.
    base = rg.explain_block(equity=equity, premium=0.01, params=params)
    if not base.get("available"):
        out["error"] = base.get("why")
        return out
    out.update({
        "effective_cap_dollars": base["effective_cap_dollars"],
        "risk_cap_dollars": base["risk_cap_dollars"],
        "tier_cap_dollars": base["tier_cap_dollars"],
        "binding_cap": base["binding_cap"],
        "premium_ceiling": base["premium_ceiling"],
    })
    # Quote-safe ceiling comes from risk_gate itself (floored to the cent there) — this
    # CLI never re-derives cap math (C14). Asserted against the live gate below.
    out["premium_ceiling_tradeable_cents"] = base["premium_ceiling_cents"]

    if premium is not None:
        exp = rg.explain_block(equity=equity, premium=premium, params=params,
                               proposed_qty=params.get("min_contracts"))
        out["candidate"] = exp
        if exp.get("available") and exp.get("deadlock"):
            out["candidate"]["min_equity_for_premium"] = rg.min_equity_for_premium(
                premium=premium, params=params)
    return out


def _fmt_table(reports: list[dict], premium: Optional[float]) -> str:
    lines = []
    hdr = (f"{'ARM':<9}{'ACCOUNT':<15}{'EQUITY':>10}{'MINC':>6}{'CAP%':>7}"
           f"{'CAP$':>10}{'BINDS':>18}{'CEILING$':>10}")
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for r in reports:
        if r.get("error"):
            lines.append(f"{r['arm']:<9}{str(r.get('account_number') or '?'):<15}  ERROR: {r['error']}")
            continue
        lines.append(
            f"{r['arm']:<9}{str(r['account_number']):<15}{r['equity']:>10.2f}"
            f"{r['min_contracts']:>6}{r['per_trade_risk_cap_pct']:>7.2f}"
            f"{r['effective_cap_dollars']:>10.2f}{r['binding_cap']:>18}"
            f"{r['premium_ceiling_tradeable_cents']:>10.2f}"
        )
    lines.append("")
    lines.append("CEILING$ = highest per-contract premium at which this arm can place its")
    lines.append("           SMALLEST legal order (min_contracts). Above it: NO legal qty exists.")
    if premium is not None:
        lines.append("")
        lines.append(f"CANDIDATE PREMIUM ${premium:.2f}:")
        for r in reports:
            c = r.get("candidate") or {}
            if not c.get("available"):
                lines.append(f"  {r['arm']:<9} n/a ({c.get('why') or r.get('error')})")
                continue
            tag = "BLOCKED " if c["deadlock"] else "OK      "
            lines.append(f"  {r['arm']:<9} {tag}{c['headline']}")
            if c.get("min_equity_for_premium"):
                lines.append(f"  {'':<9}         tradeable once equity reaches "
                             f"${c['min_equity_for_premium']:,.0f}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Explain why an order would be refused and what constraint binds.")
    ap.add_argument("--arm", help="single arm id (default: all live arms)")
    ap.add_argument("--all-arms", action="store_true", help="report every live arm (default)")
    ap.add_argument("--premium", type=float, help="candidate per-contract premium to test")
    ap.add_argument("--equity", type=float,
                    help="override equity (skips the broker read; applies to every arm shown)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="explicit no-op: this tool is read-only and has no other mode")
    args = ap.parse_args(argv)

    arms = _load_arms()
    ids = [args.arm] if args.arm else ARM_ORDER
    unknown = [i for i in ids if i not in arms]
    if unknown:
        print(f"unknown arm(s): {unknown}; known: {sorted(arms)}", file=sys.stderr)
        return 2

    reports = []
    for arm_id in ids:
        eq = args.equity if args.equity is not None else _live_equity(arm_id)
        reports.append(arm_report(arm_id, arms[arm_id], eq, args.premium))

    if args.json:
        print(json.dumps({"dry_run": True, "reports": reports}, indent=1))
    else:
        print(_fmt_table(reports, args.premium))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
