"""multi/tickers_flatten.py -- EOD safety-net flatten for the TICKERS LANE (14:52 ET).

For each of the three arms with resolvable, pin-consistent credentials: closes every OPEN
equity-option position narrowed to that arm's OWN universe roots
(`multi/lib/broker.py::close_all_equity_options`, which is provably OCC-shape-safe -- see
`backtest/tests/test_multi_broker.py`'s crypto-safety proof) and never touches another arm's
contracts. `--shadow` previews without submitting (armed=False, nothing sent).

This is the SAFETY NET behind `multi/execute.py`'s own expiry-day flatten schedule
(`exits.flatten_schedule_et`, evaluated every 2 minutes inside core.tick()'s exit_eval rows):
a position execute.py's own logic somehow failed to close by its 14:50 hard backstop still
gets one more close attempt here at 14:52 ET, registered as a SEPARATE scheduled task
(`Gamma_TickersEodFlatten`) so a stall or crash in the 2-minute execute.py cadence cannot also
disable this backstop.

$ python multi/tickers_flatten.py [--shadow]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SCRIPTS_DIR = REPO_ROOT / "setup" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from et_clock import et_now  # noqa: E402 -- the ONE clock on this rig

from multi.lib import broker as mb  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import journal as mj  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402
from multi.lib import tickers_lock as tlock  # noqa: E402 -- lane-vs-flatten lock (FIX 3)

DEFAULT_PARAMS_PATH = REPO_ROOT / "automation" / "state" / "tickers" / "params.json"
STATE_DIR = REPO_ROOT / "automation" / "state" / "tickers"
JOURNAL_DIR = REPO_ROOT / "journal"
ARM_NAMES = ("tickers-1", "tickers-2", "tickers-3")

# FIX 3: how long the flatten will WAIT for execute.py's lane lock before proceeding without
# it. The flatten is the safety net and must never be blocked indefinitely -- see flatten_all.
LOCK_WAIT_TIMEOUT_SEC = 90.0
LOCK_WAIT_POLL_SEC = 5.0


def _load_pin(arm: str) -> Optional[str]:
    p = STATE_DIR / arm / "account.json"
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    num = doc.get("account_number")
    return str(num) if num else None


# --- per-arm path helpers, duplicated from multi/execute.py's arm_state_path/arm_journal_path
# (NOT imported -- execute.py's helpers read ITS OWN TICKERS_STATE_DIR/JOURNAL_DIR module
# globals, which tests redirect independently of this script's STATE_DIR/JOURNAL_DIR; keeping
# this script's path resolution self-contained under its own globals avoids a dual-monkeypatch
# coupling between the two modules' test fixtures. Both resolve to the byte-identical real path
# -- pinned by backtest/tests/test_tickers_paths_pinned_2026_09_04.py's sibling AST check on
# THIS file, and by inspection against execute.py's own definitions.) ------------------------
def _arm_state_path(arm: str) -> Path:
    return STATE_DIR / arm / "exit-state.json"


def _arm_journal_path(arm: str) -> Path:
    return JOURNAL_DIR / f"trades-tickers-{arm}.csv"


def _arm_day_path(arm: str, date_str: str) -> Path:
    return STATE_DIR / arm / f"day-{date_str}.json"


def _lookup_closing_fill(creds, contract: str, date_str: str) -> tuple[Optional[float], int]:
    """(weighted_avg_fill_price_or_None, total_filled_qty) across every FILLED sell order for
    `contract` whose fill lands on `date_str` (YYYY-MM-DD). Never raises -- a broker read
    failure or zero matches returns (None, 0); the caller treats that as
    FLATTEN_PNL_UNRESOLVED (the state record is still dropped; the day's P&L reconciles from
    broker account activity separately)."""
    try:
        orders = mb.get_orders(creds, status="closed", symbol=contract, side="sell")
    except mb.BrokerAPIError:
        return None, 0
    total_qty = 0
    total_notional = 0.0
    for o in orders or []:
        if str(o.get("status") or "").lower() != "filled":
            continue
        filled_at = str(o.get("filled_at") or o.get("updated_at") or "")
        if not filled_at.startswith(date_str):
            continue
        try:
            qty = int(float(o.get("filled_qty") or 0))
            price = float(o.get("filled_avg_price"))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        total_qty += qty
        total_notional += price * qty
    if total_qty <= 0:
        return None, 0
    return round(total_notional / total_qty, 4), total_qty


def flatten_one(lane_params: dict, arm: str, *, shadow: bool, ts: str) -> tuple[bool, str]:
    """(ok, one-line report). ok=False on any error for THIS arm -- never raises, and never
    prevents the caller from moving on to the next arm."""
    cfg = (lane_params.get("arms") or {}).get(arm)
    if not isinstance(cfg, dict):
        return True, f"[{ts}] {arm}: SKIP -- arms.{arm} missing from params"

    universe = [str(s).upper() for s in (cfg.get("universe") or [])]
    pinned = _load_pin(arm)
    arm_params = {**lane_params, "account": {"key_source": cfg.get("key_source"), "account_number": pinned or ""}}
    try:
        creds = mc.resolve(arm_params)
        mc.verify_account(creds)
    except mc.CredError as e:
        return True, f"[{ts}] {arm}: NO_CREDS/SKIP -- {e}"
    except Exception as e:  # noqa: BLE001 -- network/parse failure resolving/verifying
        return True, f"[{ts}] {arm}: SKIP -- verify failed {type(e).__name__}: {e}"

    try:
        res = mb.close_all_equity_options(creds, allowed_roots=universe, armed=not shadow, params=arm_params)
    except Exception as e:  # noqa: BLE001 -- one arm's flatten failure must never block the others
        return False, f"[{ts}] {arm}: FLATTEN_ERROR -- {type(e).__name__}: {e}"

    if shadow or res.get("_shadow"):
        return True, f"[{ts}] {arm}: SHADOW would_close={res.get('would_close')}"
    closed, errors = res.get("closed") or [], res.get("errors") or []

    # Verify flat (established project pattern: "verify flat after every flatten" --
    # 2026-06-30 TaskStop-zombie fix). Alpaca's own positions LIST can lag a close by 1-2s;
    # is_flat_equity_options already retries that transient lag. Best-effort -- a verify
    # failure is logged, never treated as fatal; the reconciliation below still runs off
    # `closed`/broker truth regardless of whether this read succeeds.
    flat_verified: Optional[bool] = None
    try:
        flat_verified = mb.is_flat_equity_options(creds, allowed_roots=universe)
    except mb.BrokerAPIError as e:
        print(f"[{ts}] {arm}: VERIFY_FLAT_READ_ERROR -- {type(e).__name__}: {e}", file=sys.stderr)

    # --- FIX 4: reconcile per-arm STATE + JOURNAL against what the broker actually closed ----
    # close_all_equity_options submits a market_sell per open position but never touches this
    # lane's own exit-state.json / journal / day file -- left alone, every position IT closes
    # stays "open" in this executor's own books forever, and the day's P&L never gets a final
    # entry for whatever the flatten itself closed (as opposed to a position execute.py's own
    # tick-based exits already closed earlier in the day).
    recon_notes: list[str] = []
    try:
        state = mps.load_state(path=_arm_state_path(arm))
    except mps.PositionStateError as e:
        state = {}
        recon_notes.append(f"STATE_UNREADABLE({type(e).__name__})")
        print(f"[{ts}] {arm}: STATE_UNREADABLE during flatten reconciliation -- {e}", file=sys.stderr)

    if state:
        date_str = ts[:10]
        day_path = _arm_day_path(arm, date_str)
        try:
            day = json.loads(day_path.read_text(encoding="utf-8")) if day_path.exists() else None
        except (OSError, json.JSONDecodeError):
            day = None
        if not isinstance(day, dict):
            day = {"date": date_str, "arm": arm, "start_of_day_equity": 0.0,
                   "realized_pnl_today": 0.0, "kill_tripped": False, "fills": []}
        day.setdefault("fills", [])
        day.setdefault("realized_pnl_today", 0.0)

        for contract, rec in list(state.items()):
            fill_px, fill_qty = _lookup_closing_fill(creds, contract, date_str)
            if fill_px is None:
                recon_notes.append(f"{contract}:FLATTEN_PNL_UNRESOLVED")
                print(f"[{ts}] {arm}: FLATTEN_PNL_UNRESOLVED {contract} -- closing fill not "
                      f"found; state record dropped anyway, P&L reconciles from broker "
                      f"account activity later", file=sys.stderr)
                state.pop(contract, None)
                continue

            q = fill_qty if fill_qty else rec.qty
            pnl = round((fill_px - rec.entry_premium) * q * 100.0, 2)
            day["realized_pnl_today"] = round(float(day["realized_pnl_today"]) + pnl, 2)
            day["fills"].append({"ts_et": ts, "side": "SELL_ALL", "contract": contract,
                                 "qty": q, "price": fill_px, "pnl_dollars": pnl,
                                 "source": "tickers_flatten"})
            entry_row = next((e for e in mj.open_trades(path=_arm_journal_path(arm))
                              if e.get("contract") == contract), None)
            if entry_row is not None:
                try:
                    mj.append_exit(trade_id=entry_row["trade_id"], exit_date=date_str,
                                   exit_time_et=(ts[11:19] if len(ts) >= 19 else "15:52:00"),
                                   exit_premium=fill_px, exit_reason="eod_flatten_safety_net",
                                   path=_arm_journal_path(arm))
                    recon_notes.append(f"{contract}:reconciled@{fill_px}")
                except mj.JournalError as e:
                    recon_notes.append(f"{contract}:JOURNAL_ERROR({type(e).__name__})")
                    print(f"[{ts}] {arm}: JOURNAL_ERROR reconciling {contract} -- {e}", file=sys.stderr)
            else:
                recon_notes.append(f"{contract}:NO_ENTRY_ROW")
            state.pop(contract, None)

        mps.save_state(state, path=_arm_state_path(arm))
        day_path.write_text(json.dumps(day, indent=2, default=str), encoding="utf-8")

    line = f"[{ts}] {arm}: closed={closed} errors={errors}"
    if flat_verified is False:
        line += " WARNING_STILL_NOT_FLAT_AFTER_VERIFY"
    if recon_notes:
        line += f" reconciled=[{', '.join(recon_notes)}]"
    ok = (not errors) and (flat_verified is not False)
    return ok, line


def flatten_all(params_path: Path = DEFAULT_PARAMS_PATH, *, shadow: bool = False) -> int:
    try:
        lane_params = mc.load_params(params_path)
    except mc.CredError as e:
        print(f"[tickers-flatten] ABORT: cannot load {params_path}: {e}", file=sys.stderr)
        return 1

    ts = et_now().isoformat(timespec="seconds")

    # FIX 3: wait (briefly) for execute.py's lane lock rather than racing it, but NEVER let a
    # stuck lock block the safety net -- if it is still held after LOCK_WAIT_TIMEOUT_SEC,
    # proceed WITHOUT it (logged LOCK_FORCED). The flatten existing as a SEPARATE scheduled
    # task from execute.py's own 2-minute cadence is precisely so a stall in one can never
    # disable the other; a lock that blocked the flatten indefinitely would defeat that.
    lock_path = STATE_DIR / ".lane.lock"
    handle = tlock.acquire(lock_path)
    if handle is None:
        wait_deadline = time.monotonic() + LOCK_WAIT_TIMEOUT_SEC
        while handle is None and time.monotonic() < wait_deadline:
            time.sleep(LOCK_WAIT_POLL_SEC)
            handle = tlock.acquire(lock_path)
        if handle is None:
            holder = tlock.holder_info(lock_path)
            print(f"[tickers-flatten] LOCK_FORCED: {lock_path} still held by pid={holder.get('pid')} "
                  f"age={holder.get('age_sec')}s after a {LOCK_WAIT_TIMEOUT_SEC:.0f}s wait -- "
                  f"proceeding WITHOUT the lock (the flatten is the safety net and must never "
                  f"be blocked)", file=sys.stderr)

    try:
        any_error = False
        for arm in ARM_NAMES:
            try:
                ok, line = flatten_one(lane_params, arm, shadow=shadow, ts=ts)
            except Exception as e:  # noqa: BLE001 -- outer safety net: an arm must never take the process down
                ok, line = False, f"[{ts}] {arm}: UNCAUGHT -- {type(e).__name__}: {e}"
            print(line, file=sys.stderr if not ok else sys.stdout)
            any_error = any_error or not ok
        return 1 if any_error else 0
    finally:
        tlock.release(handle)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--shadow", action="store_true", help="preview only -- armed=False, nothing sent")
    ap.add_argument("--params", default=str(DEFAULT_PARAMS_PATH))
    args = ap.parse_args(argv)
    return flatten_all(Path(args.params), shadow=args.shadow)


if __name__ == "__main__":
    raise SystemExit(main())
