"""ghost_order_reconciler -- detect ENTER decisions with no matching Alpaca order.

PROBLEM SOLVED: Heartbeat logs ENTER_BEAR/ENTER_BULL to decisions.jsonl but the
Alpaca MCP order placement silently fails (timeout, auth glitch, race). The engine
loses the trade with no operator visibility. Per J directive 2026-05-22 09:25 ET
("ship reconcile") this watcher fires every 1 min during 09:30-15:55 ET, compares
recent ENTER events against the Alpaca order book, and ALERTS on ghosts.

V1 SCOPE (ALERT-ONLY, per OP-21 watch-first promotion path):
  * Reads decisions.jsonl, filters to ENTER events 60-600 seconds old
    (60s lower bound = give MCP enough time to place; 600s upper bound = stale)
  * For each ENTER: query Alpaca orders endpoint with symbol+time-window
  * No matching order found → GHOST DETECTED
  * Append to automation/state/ghost-reconciler-{date}.jsonl
  * Append RED block to automation/overnight/STATUS.md
  * Discord notify if bridge alive
  * NEVER auto-places orders -- that's V2 with J ratification (risk: double-fill,
    stale-premium fill, PDT-violating re-attempt)

Runs both accounts (Safe + Bold). Decisions for Bold are in the same file
(with "account":"aggressive" field).

Per OP-21 (watch-first) + OP-25 (engine-benefit autonomy, no live order placement)
+ OP-27 L41 (hidden window discipline) + Rule 9 (does NOT touch heartbeat.md).

CLI:
    python setup/scripts/ghost_order_reconciler.py
    python setup/scripts/ghost_order_reconciler.py --dry-run
    python setup/scripts/ghost_order_reconciler.py --account bold
    python setup/scripts/ghost_order_reconciler.py --lookback-sec 1200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "automation" / "state"
STATUS_FILE = PROJECT_ROOT / "automation" / "overnight" / "STATUS.md"
DECISIONS_FILE = STATE_DIR / "decisions.jsonl"

# Same key shape as atomic_bracket_guard.py. If keys drift, audit_scheduled_tasks
# + heartbeat self-test catch it before this silently uses stale creds.
ACCOUNT_KEYS: dict[str, tuple[str, str]] = {
    "safe": (
        "PKGZIUWDJIMDG5QYDGCPFJDGHJ",
        "9EzmHpix6GShFRHH5dUmVJb6V9VPvZppPGmtjdM3WEYs",
    ),
    "bold": (
        # Rotated 2026-05-22 09:35 ET — account PA33W2KUAT40 (Gamma-Risky-2)
        "PKQMQD2NNWII7PYGSTGIDXZU3T",
        "ELWu7QjbQDkGZawg8yM7QfpHPjB7kFQcMdERSEPirUsV",
    ),
}
ALPACA_BASE = "https://paper-api.alpaca.markets/v2"

# DST-aware ET (no tzdata dep, matches sibling scripts).
def _et_offset_hours(dt_utc: datetime) -> int:
    y = dt_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march.weekday()) % 7
    dst_start_utc = (march + timedelta(days=days_to_sun + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov.weekday()) % 7
    dst_end_utc = (nov + timedelta(days=days_to_sun)).replace(hour=6)
    return -4 if (dst_start_utc <= dt_utc < dst_end_utc) else -5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _et_now() -> datetime:
    n = _utc_now()
    return (n + timedelta(hours=_et_offset_hours(n))).replace(tzinfo=None)


# Headless stdio redirect for pythonw launches (per OP-27 L41).
if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    log_dir = STATE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = _et_now().strftime("%Y-%m-%d")
    sys.stdout = open(log_dir / f"ghost-reconciler-{today}.stdout.log",
                      "a", buffering=1, encoding="utf-8")
    sys.stderr = open(log_dir / f"ghost-reconciler-{today}.stderr.log",
                      "a", buffering=1, encoding="utf-8")


def _request(endpoint: str, key: str, secret: str, params: Optional[dict] = None,
             timeout: int = 10) -> Any:
    url = f"{ALPACA_BASE}/{endpoint.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"raw": str(e)}
        return {"_error": str(e), "_status": e.code, "_body": body}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"_error": str(e)}


def _parse_decision_ts(d: dict) -> Optional[datetime]:
    """Decisions.jsonl uses 'timestamp' or 'fire_at_utc' depending on writer version."""
    ts_str = d.get("timestamp") or d.get("fire_at_utc")
    if not ts_str:
        return None
    try:
        # Accept both 'Z' suffix and explicit +00:00 forms
        if ts_str.endswith("Z"):
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        return datetime.fromisoformat(ts_str).astimezone(timezone.utc)
    except Exception:
        return None


def _load_recent_enters(lookback_sec: int, min_age_sec: int) -> list[dict]:
    """Read decisions.jsonl, return ENTER events in [now - lookback_sec, now - min_age_sec].

    min_age_sec is the lower bound -- we wait this long to give the original MCP
    order-placement enough time to finish before we accuse it of being ghost.
    """
    if not DECISIONS_FILE.exists():
        return []

    now = _utc_now()
    upper = now - timedelta(seconds=min_age_sec)        # event must be at least this old
    lower = now - timedelta(seconds=lookback_sec)       # don't look back further than this

    enters: list[dict] = []
    try:
        with open(DECISIONS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(d, dict):
                    continue
                action = str(d.get("action", ""))
                if not action.startswith("ENTER"):
                    continue
                ts = _parse_decision_ts(d)
                if ts is None:
                    continue
                if lower <= ts <= upper:
                    d["_parsed_ts_utc"] = ts.isoformat()
                    enters.append(d)
    except OSError as exc:
        print(f"[ghost-reconciler] WARN cannot read decisions.jsonl: {exc}", file=sys.stderr)
        return []

    return enters


def _fetch_alpaca_orders(account: str, after_utc: datetime, until_utc: datetime,
                         status: str = "all") -> list[dict]:
    """Fetch Alpaca orders for the account in the time window."""
    key, secret = ACCOUNT_KEYS[account]
    params = {
        "status": status,
        "after": after_utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "until": until_utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        "limit": "200",
        "direction": "desc",
    }
    res = _request("orders", key, secret, params=params, timeout=15)
    if isinstance(res, dict) and "_error" in res:
        print(f"[ghost-reconciler] Alpaca {account} error: {res.get('_error')}", file=sys.stderr)
        return []
    if not isinstance(res, list):
        return []
    return res


def _normalize_symbol(s: str) -> str:
    """SPY260519C00738000 -- already normalized; just upper-case strip whitespace."""
    return (s or "").strip().upper()


def _find_matching_order(orders: list[dict], target_symbol: str,
                         decision_ts_utc: datetime, window_sec: int = 180) -> Optional[dict]:
    """An ENTER decision matches an Alpaca order if:
      - The order symbol equals the decision's OPRA symbol
      - The order's submitted_at is within window_sec of the decision timestamp
        (we allow up to 3 min of slack for MCP timeout/retry)
    Returns the order dict on match, or None.
    """
    target_symbol = _normalize_symbol(target_symbol)
    if not target_symbol:
        return None

    for order in orders:
        sym = _normalize_symbol(order.get("symbol", ""))
        if sym != target_symbol:
            # Bracket parents can be on the underlying symbol "SPY" — skip.
            continue
        sub_str = order.get("submitted_at") or order.get("created_at")
        if not sub_str:
            continue
        try:
            if sub_str.endswith("Z"):
                sub_utc = datetime.fromisoformat(sub_str.replace("Z", "+00:00")).astimezone(timezone.utc)
            else:
                sub_utc = datetime.fromisoformat(sub_str).astimezone(timezone.utc)
        except Exception:
            continue
        delta = abs((sub_utc - decision_ts_utc).total_seconds())
        if delta <= window_sec:
            return order
    return None


def _account_for_decision(d: dict) -> str:
    """Bold heartbeat writes 'account':'aggressive'; Safe omits or sets 'safe'."""
    acc = (d.get("account") or "").lower()
    if acc in ("aggressive", "bold"):
        return "bold"
    return "safe"


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _append_status_red(ghosts: list[dict]) -> None:
    if not ghosts:
        return
    if not STATUS_FILE.parent.exists():
        return
    ts = _et_now().strftime("%Y-%m-%d %H:%M:%S")
    lines = ["", f"### RED: GHOST_ORDER detected at {ts} ET (ghost_order_reconciler.py)"]
    for g in ghosts:
        sym = g.get("symbol", "?")
        qty = g.get("qty", "?")
        setup = g.get("setup_name", "?")
        acct = g.get("_account", "?")
        dec_ts = g.get("_decision_ts_utc", "?")
        entry_price = g.get("entry_price", "?")
        lines.append(
            f"- {acct.upper()} {sym} qty={qty} entry_premium=${entry_price} setup={setup} "
            f"decision_at_utc={dec_ts} -- NO matching Alpaca order within 180s window"
        )
    lines.append("- next-step: open Alpaca; if trade is still valid, place manually OR check for MCP timeout in heartbeat logs")
    with open(STATUS_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def reconcile_account(account: str, lookback_sec: int, min_age_sec: int,
                      match_window_sec: int, dry_run: bool) -> tuple[int, list[dict]]:
    """Returns (ghosts_count, ghosts_list)."""
    enters = [e for e in _load_recent_enters(lookback_sec, min_age_sec)
              if _account_for_decision(e) == account]
    if not enters:
        return 0, []

    # Fetch Alpaca orders covering the window of interest (decision ts ± match window)
    now = _utc_now()
    after = now - timedelta(seconds=lookback_sec + match_window_sec + 60)
    until = now + timedelta(seconds=60)
    orders = _fetch_alpaca_orders(account, after, until, status="all")

    ghosts: list[dict] = []
    for e in enters:
        sym = e.get("symbol") or e.get("opt_symbol") or e.get("option_symbol")
        if not sym:
            continue
        ts_utc = datetime.fromisoformat(e["_parsed_ts_utc"]).astimezone(timezone.utc)
        match = _find_matching_order(orders, sym, ts_utc, window_sec=match_window_sec)
        if match is None:
            ghost = dict(e)
            ghost["_account"] = account
            ghost["_decision_ts_utc"] = e["_parsed_ts_utc"]
            ghost["_detected_at_utc"] = _utc_now().isoformat()
            ghost["_reconciler_version"] = "v1-alert-only"
            ghost.pop("_parsed_ts_utc", None)
            ghosts.append(ghost)

    if ghosts and not dry_run:
        out_path = STATE_DIR / f"ghost-reconciler-{_et_now().strftime('%Y-%m-%d')}.jsonl"
        for g in ghosts:
            _append_jsonl(out_path, g)

    return len(ghosts), ghosts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", choices=["safe", "bold", "both"], default="both",
                        help="which account to check (default: both)")
    parser.add_argument("--lookback-sec", type=int, default=600,
                        help="max age of ENTER decisions to check (default: 600s = 10 min)")
    parser.add_argument("--min-age-sec", type=int, default=60,
                        help="min age before ENTER is eligible (default: 60s, gives MCP time to finish)")
    parser.add_argument("--match-window-sec", type=int, default=180,
                        help="Alpaca order matched if within ±N seconds of decision (default: 180)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report only; do not write jsonl or STATUS.md")
    args = parser.parse_args()

    accounts = ["safe", "bold"] if args.account == "both" else [args.account]
    all_ghosts: list[dict] = []
    total = 0
    for acct in accounts:
        try:
            n, ghosts = reconcile_account(
                acct,
                lookback_sec=args.lookback_sec,
                min_age_sec=args.min_age_sec,
                match_window_sec=args.match_window_sec,
                dry_run=args.dry_run,
            )
            total += n
            all_ghosts.extend(ghosts)
            print(f"[ghost-reconciler] {acct}: {n} ghost(s) detected")
        except Exception as exc:
            print(f"[ghost-reconciler] {acct} EXCEPTION: {exc}", file=sys.stderr)

    if all_ghosts and not args.dry_run:
        _append_status_red(all_ghosts)
        print(f"[ghost-reconciler] WROTE {len(all_ghosts)} ghosts to STATUS.md")

    return 0 if total == 0 else 2  # exit=2 = ghosts detected (warning, not fatal)


if __name__ == "__main__":
    sys.exit(main())
