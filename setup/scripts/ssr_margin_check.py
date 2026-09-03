"""ssr_margin_check.py -- read-only margin-based fundability check for the SSR futures lane.

WHY THIS EXISTS (queue item SSR-FUNDABILITY-MEASURES-NOTIONAL-NOT-MARGIN, filed 2026-08-23
Opus adjudication): ssr_shadow.py's `_fundability` measures notional/equity (the ssr-v2 respec
cut worst-case notional from ~326x this book's equity to ~158x by switching to micro
contracts). But you never POST notional on a futures account, you post MARGIN -- the binding
constraint is day-trade margin AND overnight/initial margin per contract, and SSR holds
positions ACROSS SESSIONS (it books round trips, not scalps), so overnight margin is the real
gate. At 158x notional the old disclosure reads scary-but-passing while "can this $2,000
account carry qty=3 MNQ + qty=3 MGC overnight" is never asked. This script asks it directly,
against the broker's OWN numbers.

READ-ONLY BY DESIGN (this repo is in a broker-read-only window -- GET calls only, no
order/dry-run/POST of any kind): the only broker calls made are tt.Account.get (session
handshake), Account.get_positions, Account.get_margin_requirements, Account.get_balances --
all GET under the hood (tastytrade/session.py Session._get). No NewOrder is ever built, no
place_order (dry_run or otherwise) is ever called. This file deliberately does NOT import or
edit backtest/futures/tastytrade_paper.py (which owns order placement) -- it mirrors that
file's own auth pattern (Session(client_secret, refresh_token, is_test=...)) as a SEPARATE,
strictly-read standalone probe, so a caller here can never accidentally reach an order-placing
method that happens to sit a scope away.

REUSE, NEVER DUPLICATE: CONFIGS/QTY are imported from ssr_shadow.py (the live SSR spec) so
this check can never silently drift from what SSR actually trades. ssr_shadow.py itself stays
broker-free by design (its own docstring: "NEVER TOUCHES A BROKER. NO ACCOUNT, NO CREDS, NO
ALPACA IMPORT ANYWHERE IN THIS FILE") -- this script does NOT add creds there, it only reads
two public constants.

EMPIRICAL (2026-09-03, live sandbox account 5WW73759, 3 consecutive read-only attempts,
~3s apart): the account is FLAT (get_positions == []); Account.get_margin_requirements (the
ONLY endpoint with a per-symbol breakdown) 502'd all 3 times, matching sandbox flakiness this
repo already documented (tastytrade_paper.py's 2026-08-29 comment: "a sandbox that has shown
502s / ReadTimeouts under load"); Account.get_balances succeeded but its account-level
futures_intraday_margin_requirement / futures_overnight_margin_requirement fields both read
$17,107.20 despite ZERO open positions -- an internally inconsistent stale/stuck sandbox
snapshot, not a live per-contract figure, and not symbol-attributable (the balances endpoint
has no per-symbol split; only get_margin_requirements does, and it 502'd every attempt). Per
this task's own instruction, that is exactly the DATA_MISSING case: `compute_fundability`
below never launders the stale aggregate balance figure into a per-symbol number it was never
scoped to answer -- a symbol with no `margin_report_groups` entry (zero held qty, or the GET
failed) is recorded DATA_MISSING and the gauge reads UNPROVEN, never GREEN by omission.

CLI: `python setup/scripts/ssr_margin_check.py` fetches live, computes, and writes
automation/state/futures/ssr-fundability.json. Never raises (every network/parse failure is
captured in the output's `broker_errors` list; C7 -- no silent success).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from ssr_shadow import CONFIGS, QTY  # noqa: E402 -- read-only reuse, no creds added there

STATE_DIR = REPO / "automation" / "state" / "futures"
OUT_FILE = STATE_DIR / "ssr-fundability.json"
ACCOUNT_FILE = STATE_DIR / "account.json"
ENV_FILE = REPO / ".env.tastytrade"

SYMBOLS: tuple = tuple(CONFIGS)  # ("MNQ", "MGC") -- always derived from the live SSR spec


# ── env / equity (fail-open, never fabricated) ──────────────────────────────────────────────
def _load_env_file() -> None:
    """Populate TT_SECRET/TT_REFRESH/TT_SANDBOX/TT_ACCOUNT from .env.tastytrade (gitignored)
    if not already present in the environment. Never prints/logs a value (secrets rule)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip())


def _load_book_equity() -> tuple[Optional[float], str]:
    """Fail-open equity lookup against this book's own recorded state (same file
    ssr_shadow._load_futures_equity reads) -- never a hardcoded/guessed number."""
    try:
        data = json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
        eq = data.get("equity")
        if isinstance(eq, (int, float)) and eq > 0:
            return float(eq), f"{ACCOUNT_FILE.name}:equity"
    except (OSError, json.JSONDecodeError):
        pass
    return None, "unavailable"


def _now_iso() -> str:
    try:
        import et_clock  # noqa: PLC0415
        return et_clock.et_now().isoformat()
    except Exception:  # noqa: BLE001
        return _dt.datetime.utcnow().isoformat() + "Z"


# ── broker fetch (network I/O -- GET calls only, see module docstring) ─────────────────────
async def _fetch_margin_snapshot_async(*, timeout: float = 15.0) -> dict[str, Any]:
    """GET-ONLY broker calls: session handshake, positions, margin requirements, balances.
    Never builds or sends an order. Returns a raw dict; never raises -- every failure is
    captured per-field so a partial sandbox outage (e.g. margin-requirements 502ing while
    balances succeeds, observed live 2026-09-03) still returns whatever DID come back."""
    out: dict[str, Any] = {
        "connected": False, "account_number": None, "positions": None,
        "margin_report_groups": None, "account_balance": None, "errors": [],
    }
    try:
        import tastytrade as tt  # noqa: PLC0415
    except ImportError as e:
        out["errors"].append(f"sdk_import_failed:{type(e).__name__}:{e}")
        return out

    secret = os.getenv("TT_SECRET", "")
    refresh = os.getenv("TT_REFRESH", "")
    if not secret or not refresh:
        out["errors"].append("missing_env_var:TT_SECRET_or_TT_REFRESH")
        return out
    sandbox = os.getenv("TT_SANDBOX", "true").lower() != "false"
    target_account = os.getenv("TT_ACCOUNT", "")

    try:
        session = tt.Session(secret, refresh, is_test=sandbox, timeout=timeout)
        accounts = await tt.Account.get(session)
        if not accounts:
            out["errors"].append("no_accounts_found")
            return out
        acct = accounts[0]
        if target_account:
            match = [a for a in accounts if a.account_number == target_account]
            acct = match[0] if match else accounts[0]
        out["connected"] = True
        out["account_number"] = acct.account_number
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"connect_failed:{type(e).__name__}:{e}")
        return out

    try:
        positions = await acct.get_positions(session)
        out["positions"] = [
            {"symbol": p.symbol, "qty": float(p.quantity)} for p in positions
        ]
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"get_positions_failed:{type(e).__name__}:{e}")

    try:
        report = await acct.get_margin_requirements(session)
        groups = []
        for g in report.groups:
            underlying = getattr(g, "underlying_symbol", None)
            if underlying is None:
                continue  # EmptyDict / non-symbol rows -- nothing to attribute
            groups.append({
                "underlying_symbol": underlying,
                "margin_requirement": float(getattr(g, "margin_requirement", 0) or 0),
                "initial_requirement": (
                    float(g.initial_requirement)
                    if getattr(g, "initial_requirement", None) is not None else None),
                "maintenance_requirement": (
                    float(g.maintenance_requirement)
                    if getattr(g, "maintenance_requirement", None) is not None else None),
            })
        out["margin_report_groups"] = groups
    except Exception as e:  # noqa: BLE001 -- observed live: this endpoint 502s under sandbox
                            # load; caller must treat a missing margin_report_groups as
                            # DATA_MISSING, never crash.
        out["errors"].append(f"get_margin_requirements_failed:{type(e).__name__}:{e}")

    try:
        bal = await acct.get_balances(session)
        out["account_balance"] = {
            "futures_intraday_margin_requirement":
                float(bal.futures_intraday_margin_requirement),
            "futures_overnight_margin_requirement":
                float(bal.futures_overnight_margin_requirement),
            "net_liquidating_value": float(bal.net_liquidating_value),
        }
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"get_balances_failed:{type(e).__name__}:{e}")

    return out


def fetch_margin_snapshot(*, timeout: float = 15.0) -> dict[str, Any]:
    """Sync wrapper around _fetch_margin_snapshot_async. Never raises."""
    _load_env_file()
    try:
        return asyncio.run(_fetch_margin_snapshot_async(timeout=timeout))
    except Exception as e:  # noqa: BLE001 -- belt-and-suspenders; the async fn already
                            # catches everything it can reach, this only catches loop-level
                            # failures (e.g. no event loop policy on this platform).
        return {"connected": False, "account_number": None, "positions": None,
                "margin_report_groups": None, "account_balance": None,
                "errors": [f"asyncio_run_failed:{type(e).__name__}:{e}"]}


# ── pure compute (fully unit-testable with fixture snapshots) ──────────────────────────────
def compute_fundability(snapshot: dict[str, Any], *, symbols: tuple = SYMBOLS,
                        qty: int = QTY, equity: Optional[float] = None,
                        equity_source: str = "unavailable") -> dict[str, Any]:
    """PURE given `snapshot`/`symbols`/`qty`/`equity`/`equity_source`. Never raises.

    Per-symbol day/overnight margin comes ONLY from `margin_report_groups` (the per-symbol
    GET /margin/accounts/{acct}/requirements breakdown) -- the account-level AGGREGATE
    balance fields (futures_intraday_margin_requirement/futures_overnight_margin_requirement)
    are NEVER substituted in per-symbol, even when present, because they price whatever the
    account currently holds in aggregate across ALL symbols, not qty={qty} of one specific
    symbol the account may hold zero of right now (observed live 2026-09-03: those aggregate
    fields read $17,107.20 while positions == [] -- inconsistent with a flat account, and this
    function will never launder that into a per-symbol number it was never scoped to answer).

    Tastytrade's per-symbol MarginReportEntry does not literally label a field "day" vs
    "overnight" the way the account-level balance does. `initial_requirement` is the entry
    margin (closest analogue to day/intraday); `maintenance_requirement` is what must be held
    to keep the position open past the session (closest analogue to overnight) -- both per
    tastytrade/account.py's MarginReportEntry fields. Where the split is absent but a flat
    `margin_requirement` exists, that flat figure is used for BOTH legs and `source` says so
    explicitly (never silently treated as a real day/overnight split).

    day_ok / overnight_ok are True only when EVERY symbol has real data AND qty x its
    margin <= equity. `gauge` reads GREEN only when overnight_ok is True for the whole book
    -- any symbol missing real margin data makes the WHOLE gauge UNPROVEN, never GREEN by
    omission (per this task's own instruction)."""
    groups = snapshot.get("margin_report_groups")
    by_underlying: dict[str, dict] = {g["underlying_symbol"]: g for g in groups} if groups else {}

    per_symbol: dict[str, Any] = {}
    any_missing = False
    day_ok = True
    overnight_ok = True

    for sym in symbols:
        g = by_underlying.get(sym)
        if g is None:
            per_symbol[sym] = {
                "day_margin": None, "overnight_margin": None,
                "source": "DATA_MISSING -- no margin_report_groups entry for this symbol "
                          "(account holds 0 qty of it right now, or the GET failed -- see "
                          "broker_errors)",
            }
            any_missing = True
            day_ok = False
            overnight_ok = False
            continue

        initial = g.get("initial_requirement")
        maint = g.get("maintenance_requirement")
        flat = g.get("margin_requirement")
        day_val = initial if initial is not None else flat
        night_val = maint if maint is not None else flat

        if day_val is None or night_val is None:
            per_symbol[sym] = {
                "day_margin": day_val, "overnight_margin": night_val,
                "source": "DATA_MISSING -- margin_report_groups entry present but no "
                          "initial/maintenance/flat margin_requirement field populated",
            }
            any_missing = True
            day_ok = False
            overnight_ok = False
            continue

        split_note = ("" if initial is not None and maint is not None else
                      " (initial/maintenance split unavailable -- using flat "
                      "margin_requirement for both legs)")
        per_symbol[sym] = {
            "day_margin": round(day_val, 2), "overnight_margin": round(night_val, 2),
            "source": "GET /margin/accounts/{account}/requirements" + split_note,
        }
        if equity is None or (day_val * qty) > equity:
            day_ok = False
        if equity is None or (night_val * qty) > equity:
            overnight_ok = False

    day_ok = bool(day_ok and not any_missing and equity is not None)
    overnight_ok = bool(overnight_ok and not any_missing and equity is not None)
    gauge = "GREEN" if overnight_ok else "UNPROVEN"

    combined_day = (round(sum(v["day_margin"] * qty for v in per_symbol.values()), 2)
                    if not any_missing else None)
    combined_overnight = (round(sum(v["overnight_margin"] * qty for v in per_symbol.values()), 2)
                          if not any_missing else None)

    return {
        "_doc": ("Margin-based fundability check (queue item "
                "SSR-FUNDABILITY-MEASURES-NOTIONAL-NOT-MARGIN). Complements, does not "
                "replace, ssr_shadow.py's notional/equity _fundability disclosure -- THIS "
                "check asks the binding constraint (margin, not notional) and the gauge "
                "reads GREEN only when the book can carry the position OVERNIGHT, since SSR "
                "holds positions across sessions, not scalps."),
        "per_symbol": per_symbol,
        "qty": qty,
        "equity": equity,
        "equity_source": equity_source,
        "combined_day_margin_usd_at_qty": combined_day,
        "combined_overnight_margin_usd_at_qty": combined_overnight,
        "day_ok": day_ok,
        "overnight_ok": overnight_ok,
        "gauge": gauge,
        "any_missing": any_missing,
        "broker_connected": snapshot.get("connected", False),
        "broker_account_number": snapshot.get("account_number"),
        "broker_positions": snapshot.get("positions"),
        "broker_account_balance": snapshot.get("account_balance"),
        "broker_errors": snapshot.get("errors", []),
    }


# ── orchestration ────────────────────────────────────────────────────────────────────────
def run(*, timeout: float = 15.0) -> dict[str, Any]:
    """Full fire: fetch (network, GET-only) + compute (pure) + persist. Never raises."""
    snapshot = fetch_margin_snapshot(timeout=timeout)
    equity, equity_source = _load_book_equity()
    result = compute_fundability(snapshot, equity=equity, equity_source=equity_source)
    result = {"as_of": _now_iso(), **result}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(result, indent=2, sort_keys=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    r = run()
    print(json.dumps({
        "as_of": r["as_of"], "gauge": r["gauge"], "day_ok": r["day_ok"],
        "overnight_ok": r["overnight_ok"], "any_missing": r["any_missing"],
        "per_symbol": r["per_symbol"], "broker_errors": r["broker_errors"],
    }, indent=2))
