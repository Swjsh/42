"""data_tier_check.py -- TASK B2 instrument 3/3 (built 2026-08-28).

WHY THIS EXISTS: a prior agent this week hit a live 403 --
`{'message': 'subscription does not permit querying recent SIP data'}` --
meaning the engine may be running on Alpaca's FREE market-data tier. This
matters twice per the task framing: (1) COST -- a paid unlimited SIP plan is
a real hurdle on a $5,000 account, and (2) FILL REALISM -- a delayed/limited
feed means paper fills may be systematically better than live (indicative
option quotes are, per Alpaca's own API description, "delayed... and
[quotes are] modified"). This is a READ-ONLY report: it makes the exact same
GET requests the live code makes (and a couple of comparison probes) and
records what comes back. It NEVER changes any subscription and NEVER places
an order.

LIVE-VERIFIED THIS SESSION (2026-08-28, via the alpaca / alpaca_aggressive MCP
servers, safe-2 and bold-2 -- exact evidence quoted, not inferred):
  - GET .../v2/stocks/SPY/bars/latest?feed=sip  -> HTTP 403
    {'message': 'subscription does not permit querying recent SIP data'}
    on BOTH core accounts. feed=iex on the same accounts succeeds.
    => the equity/underlying feed is FREE TIER (IEX only) on both core
    accounts. heartbeat_core.py already hardcodes feed=iex explicitly
    (setup/scripts/heartbeat_core.py lines ~324, ~353) -- this was a KNOWN,
    deliberately-coded-around constraint for the underlying price path.
  - GET .../v1beta1/options/quotes/latest?symbols=...&feed=opra -> HTTP 403
    {'message': 'OPRA agreement is not signed'} on BOTH core accounts.
    feed=indicative on the same symbol succeeds (delayed trades, modified
    quotes, per Alpaca's own field description).
  - GET .../v1beta1/options/bars?symbols=...&timeframe=1Min (HISTORICAL, no
    feed param, no OPRA gate) succeeded on the same account with no
    subscription error -- historical option bars are available regardless
    of the OPRA agreement; only REAL-TIME option quotes are gated on it.
  - automation/state/fleet/fleet_broker.py::get_option_mid (prices the LIVE
    ENTRY marketable-limit order) and ::get_option_quote_hilo (drives the
    EXIT MANAGER's TP1/runner/stop checks -- "the exit manager walks the
    live premium like the simulator walks bar high/low") BOTH call
    `.../v1beta1/options/quotes/latest?symbols={symbol}` with NO feed
    parameter at all. Per Alpaca's own documented default ("`opra` if the
    user has the unlimited subscription, otherwise `indicative`"), and given
    the OPRA-403 confirmed above on both core accounts, this means: the
    LIVE ENTRY PRICE AND EVERY EXIT DECISION on safe-2/bold-2 are computed
    from the "indicative" feed's delayed, modified quotes -- not from a
    real, live, unmodified NBBO. This was never an explicit design choice
    (unlike the hardcoded feed=iex for the underlying) -- nothing in either
    function's history mentions the OPRA gate; it is a silent server-side
    fallback nobody had previously verified.

WHAT THIS SCRIPT DOES GOING FORWARD: reproduces the same checks via direct
REST (fleet_broker.load_creds(), no MCP dependency -- this must work as a
headless nightly instrument) across every ACTIVE arm's own account/key, not
just the two MCP-wired core accounts, so a future subscription or key change
on ANY arm is caught. Every request is a read-only market-data GET; nothing
here can place, cancel, or modify an order or a subscription.

Run:  backtest/.venv/Scripts/python.exe setup/scripts/data_tier_check.py [--quiet]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FILLS_PATH = STATE / "fills-ledger.jsonl"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
OUT_DIR = REPO / "analysis" / "data-tier"
OUT_PATH = OUT_DIR / "summary.json"

KNOWN_BROKEN_MARKER = "## Known broken"
DATA_HOST = "https://data.alpaca.markets"
ACCOUNTS_PATH = STATE / "fleet" / "accounts.json"
_FALLBACK_ACTIVE_ARMS = ("safe-2", "bold-2", "safe-3", "risky-1")  # last-known-good fallback


def _load_active_arms() -> tuple:
    """Derived from accounts.json (status=='active', SPY_0DTE_OPTION), never hardcoded --
    checking a retired arm's live market-data feed wastes an API call against an account
    that no longer trades this instrument (risky-3, retired 2026-08-28, repurposed for the
    weekly-1 non-SPY lane). Falls back to _FALLBACK_ACTIVE_ARMS on any read error."""
    try:
        cfg = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
        arms = tuple(
            str(a["id"]) for a in cfg.get("arms", [])
            if isinstance(a, dict) and a.get("status") == "active"
            and a.get("instrument") == "SPY_0DTE_OPTION"
        )
        return arms or _FALLBACK_ACTIVE_ARMS
    except (OSError, ValueError, KeyError):
        return _FALLBACK_ACTIVE_ARMS


ACTIVE_ARMS = _load_active_arms()  # accounts.json status=active, SPY_0DTE_OPTION

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
from et_clock import et_now  # noqa: E402
import fleet_broker as fb  # noqa: E402 -- load_creds() only, no order-placement calls used


def _get(creds: dict, path: str, timeout: float = 12.0) -> dict:
    """One read-only GET against the market-data host. Never raises -- returns
    {'ok': True, 'body': ...} or {'ok': False, 'status': int|None, 'error': str}."""
    url = f"{DATA_HOST}{path}"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
        return {"ok": True, "status": resp.status, "body": body}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            err = {"raw": str(e)}
        return {"ok": False, "status": e.code, "error": err.get("message") or str(err)}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"ok": False, "status": None, "error": str(e)}


def _most_recent_option_symbol(fills_path: Path = FILLS_PATH) -> "str | None":
    """The most recent real option symbol ANY arm has traded -- data-feed tier is
    account/key-level, not symbol-dependent, so any real symbol is a valid probe.
    None if fills-ledger.jsonl is absent/empty (checks that need a symbol are then
    SKIPPED, never guessed at with a possibly-nonexistent contract)."""
    if not fills_path.exists():
        return None
    best_ts, best_symbol = None, None
    with fills_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not r.get("is_option"):
                continue
            ts = r.get("ts_utc")
            if ts and (best_ts is None or ts > best_ts):
                best_ts, best_symbol = ts, r.get("symbol")
    return best_symbol


def check_account(creds: dict, option_symbol: "str | None") -> dict:
    """All read-only probes for ONE arm's account. Never raises (each _get call is
    already fail-open); this function just assembles the row."""
    stock_sip = _get(creds, "/v2/stocks/SPY/bars/latest?feed=sip")
    stock_iex = _get(creds, "/v2/stocks/SPY/bars/latest?feed=iex")

    row = {
        "stock_sip_ok": stock_sip["ok"], "stock_sip_error": stock_sip.get("error"),
        "stock_iex_ok": stock_iex["ok"], "stock_iex_error": stock_iex.get("error"),
        "option_symbol_probed": option_symbol,
    }
    if option_symbol:
        opt_opra = _get(creds, f"/v1beta1/options/quotes/latest?symbols={option_symbol}&feed=opra")
        opt_indicative = _get(
            creds, f"/v1beta1/options/quotes/latest?symbols={option_symbol}&feed=indicative")
        opt_no_feed = _get(creds, f"/v1beta1/options/quotes/latest?symbols={option_symbol}")
        opt_hist = _get(
            creds, f"/v1beta1/options/bars?symbols={option_symbol}&timeframe=1Min&limit=5")
        row.update({
            "option_opra_ok": opt_opra["ok"], "option_opra_error": opt_opra.get("error"),
            "option_indicative_ok": opt_indicative["ok"],
            "option_indicative_error": opt_indicative.get("error"),
            "option_live_path_ok": opt_no_feed["ok"],  # EXACT replica of fleet_broker's own call
            "option_live_path_error": opt_no_feed.get("error"),
            "option_historical_bars_ok": opt_hist["ok"],
            "option_historical_bars_error": opt_hist.get("error"),
        })
    else:
        row.update({
            "option_opra_ok": None, "option_indicative_ok": None,
            "option_live_path_ok": None, "option_historical_bars_ok": None,
            "note": "no option symbol available to probe (fills-ledger.jsonl empty/missing)",
        })

    # Derived tiers, from the checks above -- never a guess when a check didn't run.
    if row["stock_sip_ok"]:
        row["stock_tier"] = "SIP (paid, all US exchanges)"
    elif row["stock_iex_ok"]:
        row["stock_tier"] = "IEX (free tier)"
    else:
        row["stock_tier"] = "ERROR (neither sip nor iex succeeded -- see errors)"

    if row["option_opra_ok"] is None:
        row["option_realtime_tier"] = "UNPROBED (no symbol available)"
    elif row["option_opra_ok"]:
        row["option_realtime_tier"] = "OPRA (paid, real-time NBBO)"
    elif row["option_indicative_ok"]:
        row["option_realtime_tier"] = "INDICATIVE (free tier -- delayed trades, modified quotes)"
    else:
        row["option_realtime_tier"] = "ERROR (neither opra nor indicative succeeded)"

    # The live path (fleet_broker.get_option_mid / get_option_quote_hilo) sends no feed
    # param at all. Per Alpaca's own documented default ("opra if subscribed, else
    # indicative"), its result is explained by whichever of the two explicit probes
    # above matches its success/failure -- inferred by elimination, not guessed.
    if row["option_opra_ok"] is None:
        row["live_path_feed_inferred"] = "UNPROBED"
    elif row["option_opra_ok"]:
        row["live_path_feed_inferred"] = "OPRA"
    elif row["option_live_path_ok"] and row["option_indicative_ok"]:
        row["live_path_feed_inferred"] = "INDICATIVE (delayed + modified)"
    elif not row["option_live_path_ok"]:
        row["live_path_feed_inferred"] = "ERROR (live-path call itself failed)"
    else:
        row["live_path_feed_inferred"] = "UNCERTAIN (opra/indicative results disagree)"

    # A genuine BREAK, as opposed to a confirmed-and-expected free-tier 403: the baseline
    # iex stock check failing means creds/connectivity themselves are broken, not just tier.
    row["baseline_broken"] = not row["stock_iex_ok"]
    return row


def run_all(fills_path: Path = FILLS_PATH, creds_all: "dict | None" = None) -> dict:
    creds_all = creds_all if creds_all is not None else fb.load_creds()
    option_symbol = _most_recent_option_symbol(fills_path)
    accounts = {}
    for arm in ACTIVE_ARMS:
        creds = creds_all.get(arm)
        if not creds:
            accounts[arm] = {"error": "no creds found in fleet secrets for this arm"}
            continue
        accounts[arm] = check_account(creds, option_symbol)
    return accounts


COST_CONTEXT = (
    "Per the go-live readiness task's own context: a paid Alpaca real-time market-data "
    "plan is quoted around $99/mo -- a real hurdle on a ~$5,000 account. This script does "
    "not independently re-verify that price (out of scope, would need external web pricing "
    "lookup); it is carried forward as given context, not re-derived.")


def summarize(accounts: dict, now_et=None) -> dict:
    now_et = now_et or et_now()
    n_free_stock = sum(1 for a in accounts.values() if a.get("stock_tier") == "IEX (free tier)")
    n_paid_stock = sum(1 for a in accounts.values()
                        if a.get("stock_tier", "").startswith("SIP"))
    n_free_option = sum(1 for a in accounts.values()
                         if (a.get("option_realtime_tier") or "").startswith("INDICATIVE"))
    n_paid_option = sum(1 for a in accounts.values()
                         if (a.get("option_realtime_tier") or "").startswith("OPRA"))
    broken = {arm: a for arm, a in accounts.items() if a.get("baseline_broken")}

    return {
        "generated_at_et": now_et.isoformat(),
        "accounts": accounts,
        "n_accounts_checked": len(accounts),
        "n_free_tier_stock_feed": n_free_stock,
        "n_paid_tier_stock_feed": n_paid_stock,
        "n_free_tier_option_feed": n_free_option,
        "n_paid_tier_option_feed": n_paid_option,
        "n_baseline_broken": len(broken),
        "baseline_broken_arms": list(broken.keys()),
        "live_entry_and_exit_pricing_path": (
            "fleet_broker.get_option_mid (LIVE ENTRY marketable-limit pricing) and "
            "get_option_quote_hilo (EXIT MANAGER's TP1/runner/stop premium walk) both call "
            "the options quotes/latest endpoint with NO feed parameter -- server-side "
            "default per Alpaca's own docs is opra-if-subscribed-else-indicative. See each "
            "account's `live_path_feed_inferred` above."),
        "cost_context": COST_CONTEXT,
        "note": ("READ-ONLY report. No subscription was changed. Every probe above is a "
                 "read-only GET against Alpaca's market-data host; nothing here places, "
                 "cancels, or modifies an order."),
    }


def one_liner(summary: dict) -> str:
    tiers = {arm: a.get("stock_tier", "?") for arm, a in summary["accounts"].items()}
    opt_tiers = {arm: a.get("option_realtime_tier", "?") for arm, a in summary["accounts"].items()}
    broken = f", BASELINE BROKEN: {summary['baseline_broken_arms']}" if summary[
        "n_baseline_broken"] else ""
    return (f"[data-tier] stock: {summary['n_paid_tier_stock_feed']} paid / "
            f"{summary['n_free_tier_stock_feed']} free ({tiers}); "
            f"option-realtime: {summary['n_paid_tier_option_feed']} paid / "
            f"{summary['n_free_tier_option_feed']} free ({opt_tiers}){broken}")


def _flag_status_md(summary: dict, status_md: Path = STATUS_MD) -> bool:
    """Loudly escalate ONLY a genuine connectivity/auth BREAK (baseline_broken) -- a
    confirmed-and-expected free-tier 403 is informational, not a break, and is never
    escalated here. Canonical create-if-missing pattern (see intervention_counter.py /
    itm_at_expiry_assertion.py / monday_verify.py::_flag_known_broken)."""
    if summary["n_baseline_broken"] == 0:
        return False
    try:
        text = status_md.read_text(encoding="utf-8")
    except OSError:
        return False
    line = (f"- [{summary['generated_at_et']}] DATA-TIER-CHECK: baseline connectivity BROKEN "
            f"(not just free-tier) on {summary['baseline_broken_arms']} -- the free-tier iex "
            f"stock feed itself failed, meaning creds/connectivity are broken, not just "
            f"market-data subscription tier. See analysis/data-tier/summary.json.")
    if KNOWN_BROKEN_MARKER not in text:
        text = KNOWN_BROKEN_MARKER + "\n\n" + text
    head, _, tail = text.partition(KNOWN_BROKEN_MARKER + "\n")
    status_md.write_text(
        f"{head}{KNOWN_BROKEN_MARKER}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")
    return True


def run(fills_path: Path = FILLS_PATH, out_path: Path = OUT_PATH,
        status_md: Path = STATUS_MD, creds_all: "dict | None" = None, write: bool = True) -> dict:
    accounts = run_all(fills_path, creds_all)
    summary = summarize(accounts)
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        _flag_status_md(summary, status_md)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    try:
        summary = run()
    except Exception as e:  # noqa: BLE001 -- fail-open notify-only instrument, never propagate
        print(f"[data-tier] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if not args.quiet:
        print(one_liner(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
