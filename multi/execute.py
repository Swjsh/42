"""multi/execute.py -- the ARMED paper executor for the TICKERS LANE (three dedicated
non-SPY 0DTE paper accounts: tickers-1 NVDA/AAPL/AMZN, tickers-2 TSLA/META/AVGO,
tickers-3 QQQ/IWM/GLD). Config: automation/state/tickers/params.json. Prereg:
analysis/recommendations/prereg-tickers-lane-production-scorer-2026-09-04.json.

WHAT THIS FILE IS. `multi/core.py` (SHADOW ONLY, AST-guarded, never touched by this file)
scores each arm's universe and returns rows with a decision (WOULD_PLACE / BLOCKED for
entries, HOLD / SELL_PARTIAL / SELL_ALL for exit_eval rows). This module is the ACTOR: it
calls `core.tick()` per arm, then for every actionable row calls `multi/lib/broker.py` with
`armed=True` (real paper orders) or `armed=False` (`--shadow`: constructed + logged, never
sent). It owns per-arm credential resolution/pinning, per-arm state/ledger/journal paths,
the day-file kill-switch bookkeeping, and the qty clamp down from `size_entry()`'s
largest-affordable answer to the frozen prereg's day-one clamp (exactly 3 contracts).

WHY A SEPARATE FILE, NOT A FLAG ON core.py. core.py's AST guard
(`test_multi_core.py::test_tick_module_contains_no_order_placement_call`) proves it never
places an order. This file is the later, deliberate change that DOES -- a new module, so
that guard on core.py stays intact.

ONE ARM'S FAILURE NEVER TOUCHES ANOTHER'S. Every per-arm path below is wrapped so a
credential problem, a malformed contract, or a broker timeout on tickers-2 can never prevent
tickers-1/tickers-3 from ticking; `run_once()` wraps each `run_arm()` call in its own
try/except as a second, outer safety net.

TIME. Every ET timestamp here comes from `et_clock.et_now()` (this box runs Mountain time;
`datetime.now()` is silently 2h wrong). Never call `datetime.now()` directly below.

WALL-CLOCK BUDGET. Task Scheduler fires this process every 2 minutes with a 3-minute hard
ExecutionTimeLimit. `run_once()` targets a soft 90s budget shared across all three arms:
past the deadline, remaining entries/exits log `*_SKIPPED` (budget) rather than attempting,
so a slow poll on one arm can never starve the others or blow the hard limit.

MONKEYPATCH SURFACE FOR TESTS. Every path helper (`arm_dir`, `arm_*_path`,
`first_fill_marker_path`) reads the module globals (`TICKERS_STATE_DIR`, `JOURNAL_DIR`,
`STATUS_PATH`) FRESH at call time, never baked into a default arg -- so tests can point the
whole module at a tmp_path via `monkeypatch.setattr(execute, "TICKERS_STATE_DIR", tmp_path)`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SCRIPTS_DIR = REPO_ROOT / "setup" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from et_clock import ET_TZ, et_now as _et_now_impl  # noqa: E402 -- the ONE clock on this rig

from multi import core  # noqa: E402
from multi.lib import broker as mb  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import exits as mex  # noqa: E402
from multi.lib import journal as mj  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402
from multi.lib import positions as mpos  # noqa: E402
from multi.lib import tickers_execute_support as tes  # noqa: E402 -- pure helpers, split out
                                                        # to keep this file under its 800-line
                                                        # budget (see that module's docstring)
from multi.lib import tickers_lock as tlock  # noqa: E402 -- lane-vs-flatten lock (FIX 3)

# --- module-level paths -- read FRESH by every helper below, never baked into a default arg
DEFAULT_PARAMS_PATH = REPO_ROOT / "automation" / "state" / "tickers" / "params.json"
TICKERS_STATE_DIR = REPO_ROOT / "automation" / "state" / "tickers"
JOURNAL_DIR = REPO_ROOT / "journal"

# E2E SHADOW PROBE (2026-09-04). The only way to exercise the WHOLE path -- creds, verify,
# funnel, production scorer, exits, entry construction -- before the first session, when the
# tickers secrets file may not exist yet and the market is closed. `--e2e-probe-root <dir>`
# (REQUIRES --shadow; argparse refuses otherwise): every per-arm path is redirected under
# <dir> (so the real automation/state/tickers/<arm>/ is never touched and the crypto-twin
# account number is never pinned there), the 09:30-15:00 self-check window is ignored, and
# every arm resolves the EXISTING crypto-twin paper key by reference (multi/lib/creds.py
# key_source 'crypto-twin' -> accounts.twin). Orders are constructed with armed=False and
# logged as SHADOW_*; nothing is ever sent. Never used by the scheduled task.
E2E_PROBE_ROOT: Optional[Path] = None
_PROBE_KEY_SOURCE = "crypto-twin"
_PROBE_SECRETS = REPO_ROOT / "automation" / "state" / "crypto-twin" / "secrets.json"
_PROBE_SECRETS_ENTRY = "twin"
STATUS_PATH = REPO_ROOT / "automation" / "overnight" / "STATUS.md"

ARM_NAMES = ("tickers-1", "tickers-2", "tickers-3")

WALL_CLOCK_BUDGET_SEC = 90.0
ENTRY_POLL_ATTEMPTS = 6
ENTRY_POLL_SLEEP_SEC = 2.0
EXIT_POLL_ATTEMPTS = 4
EXIT_POLL_SLEEP_SEC = 2.0

InvariantFail = tes.InvariantFail  # re-exported so callers/tests can write execute.InvariantFail


def now_et() -> dt.datetime:
    """Naive ET now, from the canonical clock. Tests monkeypatch THIS name, never
    datetime.now() or _et_now_impl directly, so every call site below (including
    now_et_aware()) reflects the same patched instant."""
    return _et_now_impl()


def now_et_aware() -> dt.datetime:
    """tz-aware ET now for evaluate_exit() (which requires tzinfo). Built from now_et()
    (not a second, independent clock read) so it is byte-identical to the naive value."""
    return now_et().replace(tzinfo=ET_TZ)


# --- per-arm path helpers -------------------------------------------------------------------
def arm_dir(arm: str) -> Path:
    return TICKERS_STATE_DIR / arm


def arm_state_path(arm: str) -> Path:
    return arm_dir(arm) / "exit-state.json"


def arm_level_state_dir(arm: str) -> Path:
    return arm_dir(arm) / "level-states"


def arm_ledger_path(arm: str) -> Path:
    return arm_dir(arm) / "ledger.jsonl"


def arm_cascade_path(arm: str) -> Path:
    return arm_dir(arm) / "participation-cascade.jsonl"


def arm_journal_path(arm: str) -> Path:
    return JOURNAL_DIR / f"trades-tickers-{arm}.csv"


def arm_day_path(arm: str, date_str: str) -> Path:
    return arm_dir(arm) / f"day-{date_str}.json"


def arm_account_pin_path(arm: str) -> Path:
    return arm_dir(arm) / "account.json"


def first_fill_marker_path() -> Path:
    return TICKERS_STATE_DIR / "FIRST_FILL.json"


def lane_lock_path() -> Path:
    """FIX 3 -- guards against this module's 2-minute cadence overlapping
    tickers_flatten.py's 14:52 ET EOD safety net. Lane-wide (not per-arm): the two processes
    race at the LANE level (both iterate all three arms), not per contract."""
    return TICKERS_STATE_DIR / ".lane.lock"


# --- append-only writers ---------------------------------------------------------------------
def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def append_cascade(path: Path, cascade: Any, ts: dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts_et": ts.isoformat(timespec="seconds"), **dict(cascade)},
                             default=str) + "\n")


# --- account pin -------------------------------------------------------------------------
def load_pinned_account(arm: str) -> Optional[str]:
    p = arm_account_pin_path(arm)
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    num = doc.get("account_number")
    return str(num) if num else None


def write_account_pin(arm: str, account_number: str, equity: Any, ts: dt.datetime) -> None:
    p = arm_account_pin_path(arm)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "account_number": account_number, "equity_at_pin": equity,
        "pinned_at_et": ts.isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")


# --- day file (start-of-day equity, realized P&L, kill state, fills) -----------------------
def load_or_init_day_file(arm: str, date_str: str, *, start_of_day_equity: float) -> dict:
    p = arm_day_path(arm, date_str)
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            doc.setdefault("start_of_day_equity", start_of_day_equity)
            doc.setdefault("realized_pnl_today", 0.0)
            doc.setdefault("kill_tripped", False)
            doc.setdefault("fills", [])
            return doc
        except (OSError, json.JSONDecodeError):
            pass  # corrupt -- fall through and reinitialize rather than trading blind
    doc = {"date": date_str, "arm": arm, "start_of_day_equity": start_of_day_equity,
           "realized_pnl_today": 0.0, "kill_tripped": False, "fills": []}
    save_day_file(p, doc)
    return doc


def save_day_file(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")


# --- thin call-throughs into multi/lib/tickers_execute_support.py (the pure-helper module) --
# now/path arguments are injected here (this module owns the clock + the path globals) so the
# support module stays a pure function of its arguments and needs no monkeypatch surface of
# its own. See that module's docstring for why these live there instead of inline.
is_spy_like = tes.is_spy_like
clamp_entry_qty = tes.clamp_entry_qty
parse_hhmm = tes.parse_hhmm


def bars_facts(bars: Optional[dict], symbol: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    return tes.bars_facts(bars, symbol)


def _re_derive_exit_record(rec, r: dict, bars: Optional[dict], arm_params: dict, *, best_override: Any = None):
    return tes.re_derive_exit_record(rec, r, bars, arm_params, now_aware=now_et_aware(),
                                     best_override=best_override)


def check_static_invariants(lane_params: dict, arm: str, arm_cfg: Optional[dict]) -> None:
    if E2E_PROBE_ROOT is not None and isinstance(arm_cfg, dict):
        # the key_source==arm invariant guards real accounts; the probe deliberately borrows one key
        arm_cfg = {**arm_cfg, "key_source": arm}
    tes.check_static_invariants(lane_params, arm, arm_cfg, now=now_et(),
                                ignore_window=E2E_PROBE_ROOT is not None)


def effective_key_source(arm_cfg: Optional[dict]) -> Optional[str]:
    """The key_source creds.resolve() will dereference: the arm's own, or the probe key."""
    if E2E_PROBE_ROOT is not None:
        return _PROBE_KEY_SOURCE
    return (arm_cfg or {}).get("key_source")


def precheck_creds(key_source: Optional[str], arm: str) -> Optional[str]:
    if E2E_PROBE_ROOT is not None:
        return tes.precheck_creds(_PROBE_SECRETS, _PROBE_SECRETS_ENTRY, arm)
    return tes.precheck_creds(TICKERS_STATE_DIR / "secrets.json", key_source, arm)


# --- first-fill STATUS.md line (once per lane lifetime) --------------------------------------
def maybe_write_first_fill_status(arm: str, contract: str, qty: int, price: float, ts: dt.datetime) -> None:
    marker = first_fill_marker_path()
    if marker.exists():
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({
        "arm": arm, "contract": contract, "qty": qty, "price": price,
        "ts_et": ts.isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")
    line = (f"- [{ts.isoformat(timespec='seconds')} ET] TICKERS-LANE FIRST FILL :: {arm} "
            f"{contract} qty {qty} @ {price} -- REVOKE: set shadow_only true in "
            f"automation/state/tickers/params.json")
    try:
        import status_known_broken as skb  # setup/scripts is on sys.path (see top of file)
        skb.upsert("TICKERS-LANE FIRST FILL", line, status_path=STATUS_PATH)
    except Exception as e:  # noqa: BLE001 -- STATUS.md visibility is best-effort, never fatal
        print(f"[tickers] WARN: could not write STATUS.md first-fill line: "
              f"{type(e).__name__}: {e}", file=sys.stderr)


# --- order finalization (FIX 1, 2026-09-04 adversarial review -- BLOCKER) -------------------
# THE BLOCKER: poll_fill's own attempts (6x2s entries, 4x2s exits) can exhaust without ever
# reaching a terminal status, and the OLD code just logged *_FILL_UNCONFIRMED and abandoned the
# order_id -- the order stayed resting live on the book. The next tick's concurrency check only
# looks at FILLED positions, so it re-scores the same contract and places a SECOND order.
# poll_fill also returns the instant filled_qty > 0 on a partially_filled order -- the
# remainder stayed live and untracked. finalize_order() closes both holes: whatever poll_fill
# did not confirm as FULLY filled gets CANCELED (never left resting), then re-read up to 3x so
# a fill that raced the cancel (the broker fully filled it between the last poll and the cancel
# call) is reported as filled, not lost.
_TERMINAL_ORDER_STATUSES = ("filled", "canceled", "expired", "rejected", "done_for_day")


def finalize_order(creds, order_id: str, *, requested_qty: int, shadow: bool, arm_params: dict,
                   attempts: int, sleep_sec: float) -> dict:
    """Poll `order_id` to fill; if it is not FULLY filled within the poll window, cancel the
    resting remainder and re-read broker truth. Returns
    {status, filled_qty:int, filled_avg_price:float|None, canceled:bool, limbo:bool}.

    `canceled` is True whenever the final filled_qty falls short of `requested_qty` for ANY
    reason (an explicit cancel/expire/reject, or a still-partial fill even after the cancel
    attempt). `limbo` is True only when broker truth is STILL non-terminal after the re-reads
    -- FIX 2's startup sweep (run_arm step 6a, next tick) cleans that up; this function never
    spins waiting for it, so one stuck order can never blow the 90s wall-clock budget alone.

    Only ever reached on a REAL submission: the shadow path (armed=False) `continue`s at
    SHADOW_ENTRY_PREVIEW/SHADOW_EXIT_PREVIEW before an order_id resolving to a live broker
    order exists, so this function carries no shadow/armed branch of its own.
    """
    fill = mb.poll_fill(creds, order_id, attempts=attempts, sleep_sec=sleep_sec)
    status = str(fill.get("status") or "unknown").lower()
    if status == "filled":
        return {"status": status, "filled_qty": int(fill.get("filled_qty") or 0),
                "filled_avg_price": fill.get("filled_avg_price"), "canceled": False, "limbo": False}

    # Not (fully) filled: "unfilled"/"new"/"accepted"/"pending_new", or "partially_filled" with
    # a live remainder. Cancel it rather than abandon it on the book.
    try:
        mb.cancel_order(creds, order_id, armed=(not shadow), params=arm_params)
    except mb.BrokerAPIError:
        pass  # a cancel can 422 if the order filled in the gap between poll_fill's last read
              # and this call -- fine, the re-read below reports whatever actually happened
    except mb.ShadowModeError:
        pass  # armed=(not shadow) with shadow=False but lane params.shadow_only still true --
              # the interlock already fired on the ORIGINAL submission; this is best-effort
              # cleanup on an order that structurally cannot exist for real in that state

    last = fill
    for _ in range(3):
        time.sleep(1.0)
        try:
            last = mb.get_order(creds, order_id)
        except mb.BrokerAPIError:
            continue
        if str(last.get("status") or "").lower() in _TERMINAL_ORDER_STATUSES:
            break

    final_status = str(last.get("status") or status or "unknown").lower()
    try:
        raw_fq = last.get("filled_qty")
        final_qty = int(float(raw_fq if raw_fq is not None else (fill.get("filled_qty") or 0)))
    except (TypeError, ValueError):
        final_qty = int(fill.get("filled_qty") or 0)
    fap = last.get("filled_avg_price", fill.get("filled_avg_price"))
    try:
        final_price = float(fap) if fap not in (None, "") else None
    except (TypeError, ValueError):
        final_price = None
    try:
        req_i = int(requested_qty)
    except (TypeError, ValueError):
        req_i = final_qty

    is_terminal = final_status in _TERMINAL_ORDER_STATUSES
    canceled = final_status in ("canceled", "expired", "rejected") or final_qty < req_i
    return {"status": final_status, "filled_qty": final_qty, "filled_avg_price": final_price,
            "canceled": canceled, "limbo": not is_terminal}


# --- weighted exit price (FIX 1) -------------------------------------------------------------
# A SELL_ALL close can now legitimately span more than one broker fill: finalize_order cancels
# a partial's live remainder and the NEXT tick's exit re-evaluation finishes the close, so the
# day file can carry two (or more) SELL_ALL/SELL_ALL_PARTIAL fills for the same contract at two
# different prices before it is fully flat. The journal's one EXIT row needs ONE price -- the
# qty-weighted average across just those closing fills (never TP1's SELL_PARTIAL fill, which is
# a separate, already-realized sale at its own price).
_CLOSING_SELL_SIDES = ("SELL_ALL", "SELL_ALL_PARTIAL")


def weighted_exit_price(fills: list, contract: str) -> Optional[float]:
    """Qty-weighted average price across every `_CLOSING_SELL_SIDES` fill recorded for
    `contract` in a day file's `fills` list. Pure function. Returns None if there are no
    qualifying fills to average (caller falls back to the single fill's own price)."""
    total_qty = 0
    total_notional = 0.0
    for f in fills or []:
        if not isinstance(f, dict) or f.get("contract") != contract:
            continue
        if f.get("side") not in _CLOSING_SELL_SIDES:
            continue
        try:
            qty = int(f.get("qty") or 0)
            price = float(f.get("price"))
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        total_qty += qty
        total_notional += price * qty
    if total_qty <= 0:
        return None
    return round(total_notional / total_qty, 4)


# --- OCC tail parse for orphan adoption (FIX 2b) ----------------------------------------------
def _parse_occ_contract(contract: str) -> tuple[Optional[str], Optional[str]]:
    """(side "C"|"P", expiry ISO date) parsed from an OCC-shaped symbol's fixed-width tail
    (YYMMDD + C|P + 8-digit strike -- mirrors multi.lib.positions's own tail-slice approach,
    duplicated locally rather than added to that module, which is not this build's file to
    extend). Returns (None, None) if `contract` is not OCC-shaped or the date segment does not
    parse -- callers must not assume a non-None root implies a parseable tail."""
    if mpos.occ_root(contract) is None:
        return None, None
    tail = contract[-15:]
    yy, mm, dd, side = tail[0:2], tail[2:4], tail[4:6], tail[6]
    try:
        expiry = dt.date(2000 + int(yy), int(mm), int(dd)).isoformat()
    except ValueError:
        return None, None
    return (side if side in ("C", "P") else None), expiry


# --- the per-arm run -------------------------------------------------------------------------
def run_arm(arm: str, lane_params: dict, bars: dict, attention: dict, *,
            shadow: bool, deadline: float) -> dict:
    """Runs ONE arm end to end: invariants -> creds -> tick() -> act on exits -> act on
    entries. NEVER raises -- every failure mode is a logged ledger row and an early return.
    Returns the one-line stderr summary dict."""
    ts = now_et()
    arm_cfg = (lane_params.get("arms") or {}).get(arm)
    ledger = arm_ledger_path(arm)
    scorer = lane_params.get("scorer")
    summary = {"arm": arm, "acct": None, "equity": None, "open": None,
               "would_place": 0, "placed": 0, "exits": 0, "kill": False, "creds": "NO_CREDS"}

    def log(extra: dict) -> None:
        row = {"ts_et": now_et().isoformat(timespec="seconds"), "arm": arm,
               "armed": (not shadow), "shadow": shadow, "scorer": scorer,
               "account": summary["acct"], **extra}
        append_jsonl(ledger, row)

    # 1. static invariants ---------------------------------------------------------------
    try:
        check_static_invariants(lane_params, arm, arm_cfg)
    except InvariantFail as e:
        log({"decision": "INVARIANT_FAIL", "code": e.code, "reason": str(e)})
        print(f"[tickers] {arm} INVARIANT_FAIL {e.code}: {e}", file=sys.stderr)
        return summary

    # 2. creds self-heal pre-check -------------------------------------------------------
    key_source = effective_key_source(arm_cfg)
    precheck_err = precheck_creds(key_source, arm)
    if precheck_err:
        log({"decision": "NO_CREDS", "reason": precheck_err})
        print(f"NO_CREDS {arm}: {precheck_err} -- retrying next tick", file=sys.stderr)
        return summary

    # 3. resolve (paper-only invariant is enforced INSIDE creds.resolve()) ---------------
    pinned = load_pinned_account(arm)
    arm_params = {**lane_params, "account": {"key_source": key_source, "account_number": pinned or ""}}
    try:
        creds = mc.resolve(arm_params)
    except mc.CredError as e:
        msg = str(e)
        if "NON-PAPER" in msg.upper():
            log({"decision": "INVARIANT_FAIL", "code": "paper_only", "reason": msg})
            print(f"[tickers] {arm} INVARIANT_FAIL paper_only: {msg}", file=sys.stderr)
        else:
            log({"decision": "NO_CREDS", "reason": msg})
            print(f"NO_CREDS {arm}: {msg} -- retrying next tick", file=sys.stderr)
        return summary

    # 4. verify + pin (verify_account itself raises "ACCOUNT MISMATCH" when the resolved
    #    account differs from the account_number we just fed it via arm_params -- so the pin
    #    check is enforced by the library we already trust, not re-implemented here) --------
    try:
        acct = mc.verify_account(creds)
    except mc.CredError as e:
        code = "ACCOUNT_PIN_MISMATCH" if "MISMATCH" in str(e).upper() else "NO_CREDS"
        log({"decision": code, "reason": str(e)})
        print(f"[tickers] {arm} {code}: {e}", file=sys.stderr)
        return summary
    except Exception as e:  # noqa: BLE001 -- network/parse failure verifying the account
        log({"decision": "ACCOUNT_VERIFY_ERROR", "reason": f"{type(e).__name__}: {e}"})
        print(f"[tickers] {arm} ACCOUNT_VERIFY_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return summary

    got_number = str(acct.get("account_number") or "")
    if pinned is None:
        write_account_pin(arm, got_number, acct.get("equity"), ts)

    summary["creds"] = "ok"
    summary["acct"] = got_number
    equity = 0.0
    try:
        equity = float(acct.get("equity") or 0.0)
    except (TypeError, ValueError):
        equity = 0.0
    summary["equity"] = equity
    if equity <= 0:
        log({"decision": "INVARIANT_FAIL", "code": "equity_nonpositive", "reason": f"equity={acct.get('equity')!r}"})
        print(f"[tickers] {arm} INVARIANT_FAIL equity_nonpositive: {acct.get('equity')!r}", file=sys.stderr)
        return summary

    # 5. day file / kill switch ------------------------------------------------------------
    date_str = ts.date().isoformat()
    day = load_or_init_day_file(arm, date_str, start_of_day_equity=equity)
    kill_pct = float(lane_params["risk"]["daily_loss_kill_switch_pct"])
    realized = float(day.get("realized_pnl_today") or 0.0)
    sod_equity = float(day.get("start_of_day_equity") or equity)
    kill_tripped = realized <= -kill_pct * sod_equity
    day["kill_tripped"] = kill_tripped
    summary["kill"] = kill_tripped

    # 6. per-arm state paths -----------------------------------------------------------------
    state_path = arm_state_path(arm)
    level_dir = arm_level_state_dir(arm)
    mps.ensure_initialized(path=state_path)

    arm_universe = [str(s).upper() for s in (arm_cfg.get("universe") or [])]
    universe_set = set(arm_universe)

    state_cache: Optional[dict] = None
    state_load_error: Optional[str] = None

    def _state() -> dict:
        nonlocal state_cache, state_load_error
        if state_cache is None:
            try:
                state_cache = mps.load_state(path=state_path)
            except mps.PositionStateError as e:
                log({"decision": "STATE_UNREADABLE", "reason": str(e)})
                state_cache = {}
                state_load_error = str(e)
        return state_cache

    try:
        open_opts = mb.equity_option_positions(creds, allowed_roots=arm_universe)
    except mb.BrokerAPIError as e:
        open_opts = None
        log({"decision": "BROKER_READ_ERROR", "gate": "positions", "reason": str(e)})
        print(f"[tickers] {arm} BROKER_READ_ERROR reading positions: {e}", file=sys.stderr)
    summary["open"] = len(open_opts) if open_opts is not None else -1

    # 6a. STALE-ORDER SWEEP (FIX 2, startup reconciliation) -- catches an order left resting on
    # the book by a process killed mid-flight (Task Scheduler's 3-minute hard
    # ExecutionTimeLimit can kill this process before finalize_order() ever reaches its own
    # cancel step). Restricted to BUY-side orders: this lane is long_premium_only and never
    # buys to close, so a resting BUY can only be an entry parent this executor itself placed
    # and never resolved -- exactly the blocker scenario (a stuck entry causes a duplicate
    # entry next tick). SELL-side orders in this arm's own universe are deliberately left alone
    # even so: place_bracket's take-profit/stop-loss CHILD legs are long-lived, INTENTIONAL
    # protective orders (the same defense-in-depth role tickers_flatten.py plays for the whole
    # lane) -- sweeping them as if they were garbage would strip a filled position of its only
    # broker-side protection the instant this process itself stops ticking (a naked long, C2).
    try:
        open_orders = mb.get_orders(creds, status="open")
    except mb.BrokerAPIError as e:
        open_orders = []
        log({"decision": "ORDERS_READ_ERROR", "reason": f"{type(e).__name__}: {e}"})
        print(f"[tickers] {arm} ORDERS_READ_ERROR: {e}", file=sys.stderr)
    for o in open_orders:
        o_sym = str(o.get("symbol") or "")
        o_id = o.get("id")
        o_root = mpos.occ_root(o_sym)
        if o_root is None:
            continue  # not an OCC option order at all -- never this lane's concern either way
        if o_root.upper() not in universe_set:
            log({"decision": "FOREIGN_OPEN_ORDER", "order_id": o_id, "symbol": o_sym,
                 "side": o.get("side"),
                 "reason": f"root {o_root!r} not in {arm} universe {sorted(universe_set)} -- left alone"})
            continue
        if str(o.get("side") or "").lower() != "buy" or not o_id:
            continue  # ours, but a sell-side leg (protective TP/stop) -- not swept, see above
        try:
            cres = mb.cancel_order(creds, o_id, armed=(not shadow), params=arm_params)
        except mb.ShadowModeError as e:
            log({"decision": "SHADOW_ONLY_INTERLOCK", "order_id": o_id, "symbol": o_sym, "reason": str(e)})
            continue
        except mb.BrokerAPIError as e:
            log({"decision": "STALE_ORDER_CANCEL_ERROR", "order_id": o_id, "symbol": o_sym,
                 "reason": f"{type(e).__name__}: {e}"})
            continue
        if isinstance(cres, dict) and cres.get("_shadow"):
            log({"decision": "SHADOW_STALE_ORDER_CANCEL_PREVIEW", "order_id": o_id, "symbol": o_sym,
                 "side": o.get("side"), "qty": o.get("qty")})
            continue
        log({"decision": "STALE_ORDER_CANCELED", "order_id": o_id, "symbol": o_sym,
             "side": o.get("side"), "qty": o.get("qty"), "submitted_at": o.get("submitted_at")})

    # 6b. ORPHAN-POSITION ADOPTION (FIX 2) -- a broker fill this executor's own state never
    # recorded (the process was killed between the broker confirming the fill and this code
    # persisting the PositionRecord) is otherwise invisible to exit management forever:
    # core.tick()'s manage_open_positions loop only iterates THIS arm's own state file, never
    # broker positions directly. Adopting it here, before tick() runs below, means THIS SAME
    # tick's exit evaluation already sees it -- not one tick (2 minutes) late. Skipped when the
    # state file itself is unreadable (STATE_UNREADABLE already logged above) -- adopting on
    # top of an unknown state risks silently overwriting real, if corrupt-on-disk, history.
    if open_opts is not None and state_load_error is None:
        known_contracts = set(_state().keys())
        for pos in open_opts:
            a_contract = str(pos.get("symbol") or "")
            if not a_contract or a_contract in known_contracts:
                continue
            a_side, a_expiry = _parse_occ_contract(a_contract)
            a_root = mpos.occ_root(a_contract)
            try:
                a_entry_premium = float(pos.get("avg_entry_price"))
            except (TypeError, ValueError):
                a_entry_premium = None
            try:
                a_qty = abs(int(float(pos.get("qty", 0))))
            except (TypeError, ValueError):
                a_qty = 0

            a_underlying, _atr = bars_facts(bars, a_root)
            if a_underlying is None:
                try:
                    cp = pos.get("current_price")
                    a_underlying = float(cp) if cp is not None else None
                except (TypeError, ValueError):
                    a_underlying = None
            if a_underlying is None and a_entry_premium is not None:
                a_underlying = a_entry_premium  # last resort -- a real number, never a fake 0.0

            if a_side is None or a_expiry is None or a_entry_premium is None or a_qty < 1 or a_underlying is None:
                log({"decision": "ADOPTION_FAILED", "contract": a_contract,
                     "reason": f"could not derive PositionRecord fields from broker position "
                               f"{pos!r}"[:300]})
                continue
            try:
                a_rec = mps.PositionRecord(
                    symbol=str(a_root or ""), contract=a_contract, side=a_side,
                    entry_premium=a_entry_premium, entry_underlying_price=a_underlying,
                    qty=a_qty, entry_session_date=date_str, expiry=a_expiry,
                    hwm_premium=a_entry_premium, strategy="production_ribbon_ride",
                )
            except (ValueError, TypeError) as e:
                log({"decision": "ADOPTION_FAILED", "contract": a_contract,
                     "reason": f"PositionRecord rejected: {type(e).__name__}: {e}"})
                continue

            adopted_state = dict(_state())
            adopted_state[a_contract] = a_rec
            mps.save_state(adopted_state, path=state_path)
            state_cache = adopted_state
            known_contracts.add(a_contract)

            adopt_ts = now_et()
            adopt_trade_id = f"adopted-{arm}-{a_contract}-{adopt_ts.strftime('%H%M%S')}"
            try:
                mj.append_entry(trade_id=adopt_trade_id, symbol=a_rec.symbol, contract=a_contract,
                                side=a_rec.side, entry_date=adopt_ts.date(),
                                entry_time_et=adopt_ts.strftime("%H:%M:%S"),
                                entry_premium=a_rec.entry_premium, qty=a_qty, arm=arm,
                                feed="adopted", path=arm_journal_path(arm))
            except mj.JournalError as e:
                log({"decision": "JOURNAL_ERROR", "contract": a_contract,
                     "reason": f"adoption journal entry failed: {e}"})
            log({"decision": "POSITION_ADOPTED", "contract": a_contract, "qty": a_qty,
                 "entry_premium": a_entry_premium, "side": a_side, "expiry": a_expiry,
                 "trade_id": adopt_trade_id})

    # 7. tick() ------------------------------------------------------------------------------
    try:
        rows, cascade = core.tick(
            arm_params, creds, arm_universe, dry_bars=bars, attention_override=attention,
            state_path=state_path, level_state_dir=level_dir,
            realized_pnl_today=realized, kill_switch_tripped=kill_tripped,
        )
    except Exception as e:  # noqa: BLE001 -- a tick failure must not crash the process
        log({"decision": "TICK_ERROR", "reason": f"{type(e).__name__}: {e}"})
        print(f"[tickers] {arm} TICK_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return summary

    for r in rows:
        log(dict(r))
    append_cascade(arm_cascade_path(arm), cascade, ts)

    # 8. ACT ON EXITS FIRST --------------------------------------------------------------
    n_exits = 0
    exit_rows = [r for r in rows if r.get("kind") == "exit_eval"]
    for r in exit_rows:
        decision_kind = r.get("decision")
        contract = r.get("contract")

        if decision_kind == "STALE_STATE":
            # core.py's broker-flat detector (gate="broker_flat"): the broker reports this
            # contract flat but our own state still carries a record for it (a close this
            # ledger never saw the fill for -- a crash, a race, or a manual close outside this
            # executor). Drop the record; write NO journal row -- the flatten / broker
            # activity feed is what reconciles the actual P&L, since this lane's own ledger has
            # no fill of its own to attribute it to.
            if contract:
                state = _state()
                if contract in state:
                    new_state = dict(state)
                    new_state.pop(contract, None)
                    mps.save_state(new_state, path=state_path)
                    state_cache = new_state
                log({"decision": "STATE_RECORD_DROPPED", "contract": contract,
                     "reason": r.get("reason") or "core.py STALE_STATE/broker_flat"})
            continue

        if decision_kind not in (mex.ACTION_HOLD, mex.ACTION_SELL_PARTIAL, mex.ACTION_SELL_ALL):
            continue  # BLOCKED (quote error, unreadable state) -- nothing to act on or persist
        symbol = r.get("symbol")
        if not contract:
            continue

        # crypto/foreign-contract safety net -- independent of what THIS arm's own state
        # contains, never sell a contract whose root is not in THIS arm's configured universe.
        root = mpos.occ_root(contract)
        if root is None or root.upper() not in universe_set:
            if decision_kind in (mex.ACTION_SELL_PARTIAL, mex.ACTION_SELL_ALL):
                log({"decision": "FOREIGN_CONTRACT_IGNORED", "contract": contract,
                     "reason": f"root {root!r} not in {arm} universe {sorted(universe_set)}"})
            continue

        state = _state()
        rec = state.get(contract)
        if rec is None:
            log({"decision": "EXIT_SKIPPED", "contract": contract,
                 "reason": "no PositionRecord for this contract in per-arm state"})
            continue

        if decision_kind == mex.ACTION_HOLD:
            try:
                new_rec = _re_derive_exit_record(rec, r, bars, arm_params)
            except mex.ExitConfigError as e:
                log({"decision": "EXIT_PERSIST_ERROR", "contract": contract, "reason": str(e)})
                continue
            new_state = dict(state)
            new_state[contract] = new_rec
            mps.save_state(new_state, path=state_path)
            state_cache = new_state
            continue

        # SELL_PARTIAL / SELL_ALL -----------------------------------------------------------
        n_exits += 1
        qty_to_close = r.get("qty_to_close")
        try:
            qty_i = int(qty_to_close)
        except (TypeError, ValueError):
            qty_i = 0
        if qty_i < 1:
            log({"decision": "EXIT_SKIPPED", "contract": contract,
                 "reason": f"qty_to_close={qty_to_close!r} is not a positive integer"})
            continue
        if time.monotonic() > deadline:
            log({"decision": "EXIT_SKIPPED", "contract": contract,
                 "reason": "wall-clock budget exhausted"})
            continue

        # Belt-and-suspenders (FIX 1): core.py derives qty_to_close from the PositionRecord's
        # ORIGINAL qty (position_state.py: "never decremented"), which goes stale the instant a
        # PRIOR partial close has already shrunk what the broker actually holds. Clamp to
        # broker truth here, at the last possible moment before submission, rather than trust a
        # decision that may be one or more ticks old.
        try:
            held = mb.get_position_qty(creds, contract)
        except mb.BrokerAPIError as e:
            log({"decision": "EXIT_QTY_READ_ERROR", "contract": contract,
                 "reason": f"{type(e).__name__}: {e}"})
            continue  # never sell blind on an unknown held qty
        if held == 0:
            new_state = dict(state)
            if contract in new_state:
                new_state.pop(contract, None)
                mps.save_state(new_state, path=state_path)
                state_cache = new_state
            log({"decision": "EXIT_SKIPPED_FLAT", "contract": contract,
                 "reason": "broker reports 0 held for this contract -- nothing to sell; state record dropped"})
            continue
        qty_i = min(qty_i, held)

        try:
            res = mb.market_sell(creds, symbol=contract, qty=qty_i, armed=(not shadow), params=arm_params)
        except mb.ShadowModeError as e:
            log({"decision": "SHADOW_ONLY_INTERLOCK", "contract": contract, "reason": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            log({"decision": "EXIT_ORDER_ERROR", "contract": contract, "reason": f"{type(e).__name__}: {e}"})
            continue

        if isinstance(res, dict) and res.get("_shadow"):
            log({"decision": "SHADOW_EXIT_PREVIEW", "contract": contract, "qty": qty_i,
                 "action": decision_kind, "preview": res.get("would_submit")})
            continue
        if isinstance(res, dict) and res.get("_error"):
            log({"decision": "EXIT_ORDER_REJECTED", "contract": contract,
                 "reason": str(res.get("_error"))[:250]})
            continue

        order_id = res.get("id") if isinstance(res, dict) else None
        if not order_id:
            log({"decision": "EXIT_ORDER_ERROR", "contract": contract,
                 "reason": f"no order id in broker response: {res!r}"[:300]})
            continue

        result = finalize_order(creds, order_id, requested_qty=qty_i, shadow=shadow,
                                arm_params=arm_params, attempts=EXIT_POLL_ATTEMPTS,
                                sleep_sec=EXIT_POLL_SLEEP_SEC)
        if result["limbo"]:
            log({"decision": "ORDER_LIMBO", "contract": contract, "order_id": order_id,
                 "status": result["status"]})
        filled_qty = result["filled_qty"]
        if filled_qty == 0:
            log({"decision": "EXIT_CANCELED", "contract": contract, "order_id": order_id,
                 "reason": f"final status={result['status']} after "
                           f"{EXIT_POLL_ATTEMPTS}x{EXIT_POLL_SLEEP_SEC}s poll window"})
            continue

        exit_time = now_et()
        exit_px = result["filled_avg_price"]

        new_state = dict(state)
        if decision_kind == mex.ACTION_SELL_ALL:
            if filled_qty < qty_i:
                # Partial close -- broker truth carries the remainder; the record stays OPEN
                # (never popped) so the NEXT tick's SELL_ALL re-evaluation finishes it, clamped
                # again to broker truth by the belt-and-suspenders check above.
                partial_pnl = (round((float(exit_px) - rec.entry_premium) * filled_qty * 100.0, 2)
                              if exit_px is not None else None)
                if partial_pnl is not None:
                    day["realized_pnl_today"] = realized = round(realized + partial_pnl, 2)
                day["fills"].append({"ts_et": exit_time.isoformat(timespec="seconds"),
                                     "side": "SELL_ALL_PARTIAL", "contract": contract,
                                     "qty": filled_qty, "price": exit_px, "pnl_dollars": partial_pnl})
                save_day_file(arm_day_path(arm, date_str), day)
                log({"decision": "EXIT_PARTIAL", "action": "SELL_ALL", "contract": contract,
                     "requested_qty": qty_i, "qty": filled_qty, "price": exit_px,
                     "pnl_dollars": partial_pnl, "order_id": order_id})
                continue

            # FULLY closed (this fill's qty matches qty_i, which was itself clamped to broker-
            # held qty moments earlier) -- pop the record and write the journal EXIT row, price
            # is the qty-weighted average across every closing fill for this contract today (a
            # prior partial may have filled at a different price than this final one).
            new_state.pop(contract, None)
            mps.save_state(new_state, path=state_path)
            state_cache = new_state
            day["fills"].append({"ts_et": exit_time.isoformat(timespec="seconds"), "side": "SELL_ALL",
                                 "contract": contract, "qty": filled_qty, "price": exit_px})
            journal_px = weighted_exit_price(day["fills"], contract)
            if journal_px is None:
                journal_px = exit_px
            entry_row = next((e for e in mj.open_trades(path=arm_journal_path(arm))
                              if e.get("contract") == contract), None)
            pnl = None
            if entry_row is not None and journal_px:
                try:
                    exit_row = mj.append_exit(
                        trade_id=entry_row["trade_id"], exit_date=exit_time.date(),
                        exit_time_et=exit_time.strftime("%H:%M:%S"), exit_premium=float(journal_px),
                        exit_reason=str(r.get("stage") or decision_kind), path=arm_journal_path(arm),
                    )
                    pnl = float(exit_row.get("pnl_dollars") or 0.0)
                except mj.JournalError as e:
                    log({"decision": "JOURNAL_ERROR", "contract": contract, "reason": str(e)})
            else:
                log({"decision": "EXIT_JOURNAL_LOOKUP_FAILED", "contract": contract,
                     "reason": "no open ENTRY row found for this contract"})
            if pnl is not None:
                day["realized_pnl_today"] = realized = round(realized + pnl, 2)
            save_day_file(arm_day_path(arm, date_str), day)
            log({"decision": "EXIT_FILLED", "action": "SELL_ALL", "contract": contract,
                 "qty": filled_qty, "price": exit_px, "journal_price": journal_px,
                 "pnl_dollars": pnl, "order_id": order_id})
        else:  # SELL_PARTIAL (TP1) -- record the ACTUAL filled qty; keep the existing re-derive
               # path. No journal EXIT row (journal.py has no PARTIAL row type -- only the
               # FINAL close is a trade).
            try:
                new_state[contract] = _re_derive_exit_record(
                    rec, r, bars, arm_params, best_override=(exit_px or r.get("ask")))
            except mex.ExitConfigError as e:
                log({"decision": "EXIT_PERSIST_ERROR", "contract": contract, "reason": str(e)})
            mps.save_state(new_state, path=state_path)
            state_cache = new_state
            day["fills"].append({"ts_et": exit_time.isoformat(timespec="seconds"), "side": "SELL_PARTIAL",
                                 "contract": contract, "qty": filled_qty, "price": exit_px})
            save_day_file(arm_day_path(arm, date_str), day)
            log({"decision": "EXIT_FILLED", "action": "SELL_PARTIAL", "contract": contract,
                 "qty": filled_qty, "price": exit_px, "order_id": order_id})
            if filled_qty < qty_i:
                log({"decision": "EXIT_PARTIAL_REMAINDER_CANCELED", "contract": contract,
                     "order_id": order_id, "requested_qty": qty_i, "filled_qty": filled_qty})

    summary["exits"] = n_exits

    # re-read the kill state in case an exit's realized P&L just tripped it this same tick
    kill_tripped = realized <= -kill_pct * sod_equity
    summary["kill"] = kill_tripped

    # 9. ACT ON ENTRIES -------------------------------------------------------------------
    last_entry_et = parse_hhmm(lane_params["tick_cadence"]["last_entry_et"])
    max_contracts = int(lane_params["risk"]["max_contracts"])
    min_contracts = int(lane_params["risk"]["min_contracts"])
    max_concurrent = int(lane_params["risk"]["max_concurrent_positions"])

    entry_rows = [r for r in rows if r.get("kind") != "exit_eval" and r.get("decision") == "WOULD_PLACE"]
    summary["would_place"] = len(entry_rows)
    n_placed = 0

    for r in entry_rows:
        contract = r.get("contract")
        if time.monotonic() > deadline:
            log({"decision": "ENTRY_SKIPPED", "contract": contract, "reason": "wall-clock budget exhausted"})
            continue
        if now_et().time() > last_entry_et:
            log({"decision": "ENTRY_WINDOW_CLOSED", "contract": contract,
                 "reason": f"now {now_et().time().isoformat('minutes')} > last_entry_et "
                           f"{last_entry_et.isoformat('minutes')}"})
            continue
        if kill_tripped:
            log({"decision": "KILL_BLOCKED", "contract": contract,
                 "reason": f"realized_pnl_today {realized} <= -{kill_pct * 100:.2f}% of "
                           f"start-of-day equity {sod_equity}"})
            continue
        if open_opts is None:
            log({"decision": "ENTRY_BLOCKED", "contract": contract,
                 "reason": "broker position read failed -- cannot verify concurrency"})
            continue
        if len(open_opts) >= max_concurrent:
            log({"decision": "MAX_CONCURRENT_BLOCKED", "contract": contract,
                 "reason": f"{len(open_opts)} open >= max_concurrent {max_concurrent}"})
            continue

        root = mpos.occ_root(contract) if contract else None
        if not contract or root is None or is_spy_like(root) or root.upper() not in universe_set:
            log({"decision": "INVARIANT_FAIL", "code": "entry_contract_out_of_universe",
                 "contract": contract, "reason": f"root {root!r} not a safe {arm} universe member"})
            continue

        qty, block_reason = clamp_entry_qty(r.get("qty"), min_contracts=min_contracts, max_contracts=max_contracts)
        if block_reason:
            log({"decision": "SIZE_BELOW_MIN", "contract": contract, "reason": block_reason})
            continue

        ask, mid = r.get("ask"), r.get("mid")
        if ask is None or mid is None:
            log({"decision": "ENTRY_BLOCKED", "contract": contract,
                 "reason": "missing ask/mid on WOULD_PLACE row -- cannot price the order"})
            continue
        try:
            ask_f, mid_f = float(ask), float(mid)
        except (TypeError, ValueError):
            log({"decision": "ENTRY_BLOCKED", "contract": contract, "reason": "ask/mid not numeric"})
            continue

        limit_price = round(ask_f + 0.01, 2)
        tp1_pct = float(lane_params["exits"]["tp1_premium_pct"])
        cat_pct = float(lane_params["exits"]["catastrophe_stop_pct"])
        take_profit = round(mid_f * (1.0 + tp1_pct / 100.0), 2)
        stop = round(mid_f * (1.0 + cat_pct / 100.0), 2)
        if stop <= 0:
            stop = 0.01

        try:
            res = mb.place_bracket(creds, symbol=contract, qty=qty, limit_price=limit_price,
                                   take_profit_price=take_profit, stop_price=stop,
                                   armed=(not shadow), simple_fallback=True, params=arm_params)
        except mb.ShadowModeError as e:
            log({"decision": "SHADOW_ONLY_INTERLOCK", "contract": contract, "reason": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            log({"decision": "ENTRY_ORDER_ERROR", "contract": contract, "reason": f"{type(e).__name__}: {e}"})
            continue

        if isinstance(res, dict) and res.get("_shadow"):
            log({"decision": "SHADOW_ENTRY_PREVIEW", "contract": contract, "qty": qty,
                 "preview": res.get("would_submit")})
            continue
        if isinstance(res, dict) and res.get("_error"):
            log({"decision": "ENTRY_REJECTED", "contract": contract, "reason": str(res.get("_error"))[:250]})
            continue

        order_id = res.get("id") if isinstance(res, dict) else None
        if not order_id:
            log({"decision": "ENTRY_ORDER_ERROR", "contract": contract,
                 "reason": f"no order id in broker response: {res!r}"[:300]})
            continue

        result = finalize_order(creds, order_id, requested_qty=qty, shadow=shadow,
                                arm_params=arm_params, attempts=ENTRY_POLL_ATTEMPTS,
                                sleep_sec=ENTRY_POLL_SLEEP_SEC)
        if result["limbo"]:
            log({"decision": "ORDER_LIMBO", "contract": contract, "order_id": order_id,
                 "status": result["status"]})
        filled_qty = result["filled_qty"]
        if filled_qty == 0:
            log({"decision": "ENTRY_CANCELED", "contract": contract, "order_id": order_id,
                 "reason": f"final status={result['status']} after "
                           f"{ENTRY_POLL_ATTEMPTS}x{ENTRY_POLL_SLEEP_SEC}s poll window"})
            continue

        entry_time = now_et()
        fill_px = result["filled_avg_price"] or limit_price
        try:
            rec = mps.PositionRecord(
                symbol=str(r.get("symbol") or root), contract=contract, side=str(r.get("side")),
                entry_premium=float(fill_px), entry_underlying_price=float(r.get("spot") or 0.0),
                qty=filled_qty, entry_session_date=entry_time.date().isoformat(),
                expiry=str(r.get("expiry")), hwm_premium=float(fill_px),
                strategy="production_ribbon_ride",
            )
        except (ValueError, TypeError) as e:
            log({"decision": "ENTRY_RECORD_ERROR", "contract": contract,
                 "reason": f"broker filled but the position record could not be constructed: "
                           f"{type(e).__name__}: {e} -- MANUAL RECONCILIATION NEEDED"})
            continue

        state = _state()
        new_state = dict(state)
        new_state[contract] = rec
        mps.save_state(new_state, path=state_path)
        state_cache = new_state

        trade_id = f"{arm}-{contract}-{entry_time.strftime('%H%M%S')}"
        try:
            mj.append_entry(trade_id=trade_id, symbol=rec.symbol, contract=contract, side=rec.side,
                            entry_date=entry_time.date(), entry_time_et=entry_time.strftime("%H:%M:%S"),
                            entry_premium=rec.entry_premium, qty=filled_qty, arm=arm, feed="indicative",
                            spread_pct_at_entry=r.get("spread_pct"), path=arm_journal_path(arm))
        except mj.JournalError as e:
            log({"decision": "JOURNAL_ERROR", "contract": contract, "reason": str(e)})

        day["fills"].append({"ts_et": entry_time.isoformat(timespec="seconds"), "side": "BUY",
                             "contract": contract, "qty": filled_qty, "price": rec.entry_premium,
                             "trade_id": trade_id})
        save_day_file(arm_day_path(arm, date_str), day)

        n_placed += 1
        log({"decision": "ENTRY_FILLED", "contract": contract, "qty": filled_qty,
             "price": rec.entry_premium, "trade_id": trade_id, "order_id": order_id})
        maybe_write_first_fill_status(arm, contract, filled_qty, rec.entry_premium, entry_time)
        if filled_qty < qty:
            log({"decision": "ENTRY_PARTIAL_REMAINDER_CANCELED", "contract": contract,
                 "order_id": order_id, "requested_qty": qty, "filled_qty": filled_qty})

        # a fresh fill counts toward THIS tick's concurrency for any further WOULD_PLACE rows
        # in the SAME pass (max_concurrent_positions=1 makes this the common case).
        open_opts = list(open_opts or []) + [{"symbol": contract, "qty": str(filled_qty)}]

    summary["placed"] = n_placed
    return summary


# --- process-level driver ---------------------------------------------------------------------
def market_is_open(creds) -> tuple:
    """(is_open | None, reason). None = the clock could not be read (BrokerAPIError or a
    malformed payload) -- the caller proceeds under the weekday/window invariants and
    discloses it, because a clock outage must not silently halt the lane (fail-open here is
    bounded by tickers_execute_support.check_static_invariants' own weekday + 09:30-15:00
    window) and must equally not be mistaken for "closed".

    WHY THIS EXISTS (2026-09-04): the static invariants check weekday() only. Monday 2026-09-07
    is Labor Day -- without the broker's own clock the lane would fire into a closed market
    every 2 minutes (funnel bars stale, entries rejected, 480 rows of noise per arm)."""
    try:
        c = mb.get_clock(creds)
    except Exception as e:  # noqa: BLE001 -- classified, not swallowed: the caller logs it per arm
        return None, f"{type(e).__name__}: {e}"[:200]
    is_open = bool(c.get("is_open"))
    return is_open, (f"broker clock is_open={is_open} next_open={c.get('next_open')} "
                     f"next_close={c.get('next_close')}")


def run_once(arms: list[str], params_path: Path, *, shadow: bool = False) -> int:
    """One pass over `arms`: shared bar fetch, then each arm run independently. Never raises;
    returns 1 only when params.json itself cannot be loaded at all (nothing per-arm to run).

    FIX 3 (lane-vs-flatten lock): holds `<TICKERS_STATE_DIR>/.lane.lock` for the WHOLE pass.
    If tickers_flatten.py (or a second overlapping instance of this same process) already
    holds it, this pass is skipped entirely -- logged LOCK_HELD, returns 0 (a skipped pass is
    not an error; the next scheduled tick two minutes later tries again)."""
    lock_path = lane_lock_path()
    handle = tlock.acquire(lock_path)
    if handle is None:
        holder = tlock.holder_info(lock_path)
        print(f"[tickers] LOCK_HELD: {lock_path} held by pid={holder.get('pid')} "
              f"age={holder.get('age_sec')}s -- skipping this pass (tickers_flatten.py's own "
              f"safety net is unaffected)", file=sys.stderr)
        return 0
    try:
        return _run_once_locked(arms, params_path, shadow=shadow)
    finally:
        tlock.release(handle)


def _run_once_locked(arms: list[str], params_path: Path, *, shadow: bool = False) -> int:
    """The original run_once() body, now called only while lane_lock_path() is held."""
    pass_start = time.monotonic()
    deadline = pass_start + WALL_CLOCK_BUDGET_SEC

    try:
        lane_params = mc.load_params(params_path)
    except mc.CredError as e:
        print(f"[tickers] ABORT: cannot load params at {params_path}: {e}", file=sys.stderr)
        return 1

    arms_cfg = lane_params.get("arms") or {}
    seen: set = set()
    all_universe: list[str] = []
    for a in arms:
        cfg = arms_cfg.get(a) or {}
        for s in cfg.get("universe") or []:
            su = str(s).upper()
            if su not in seen:
                seen.add(su)
                all_universe.append(su)

    shared_creds = None
    for a in arms:
        cfg = arms_cfg.get(a) or {}
        key_source = effective_key_source(cfg)
        if precheck_creds(key_source, a):
            continue
        pinned = load_pinned_account(a)
        probe_params = {**lane_params, "account": {"key_source": key_source, "account_number": pinned or ""}}
        try:
            shared_creds = mc.resolve(probe_params)
            break
        except mc.CredError:
            continue

    # MARKET-CLOCK GATE (2026-09-04): the broker's own is_open, not our weekday() -- holidays
    # and early closes exist. Closed -> one MARKET_CLOSED row per arm (so the ledger shows the
    # task fired and why nothing happened; the day-check treats MARKET_CLOSED-only as SKIP) and
    # the pass ends. Unreadable -> proceed under the static invariants, disclosed per arm.
    # The E2E probe bypasses the gate (it runs off-hours by design) and says so.
    if shared_creds is not None:
        if E2E_PROBE_ROOT is not None:
            print("[tickers] E2E SHADOW PROBE: market-clock gate BYPASSED (probe runs off-hours)",
                  file=sys.stderr)
        else:
            is_open, clock_why = market_is_open(shared_creds)
            if is_open is False:
                for a in arms:
                    append_jsonl(arm_ledger_path(a), {
                        "ts_et": now_et().isoformat(timespec="seconds"), "arm": a,
                        "decision": "MARKET_CLOSED", "reason": clock_why,
                        "armed": not shadow, "shadow": shadow, "scorer": lane_params.get("scorer"),
                    })
                print(f"[tickers] MARKET_CLOSED -- {clock_why}; pass ends, nothing evaluated",
                      file=sys.stderr)
                return 0
            if is_open is None:
                for a in arms:
                    append_jsonl(arm_ledger_path(a), {
                        "ts_et": now_et().isoformat(timespec="seconds"), "arm": a,
                        "decision": "CLOCK_READ_ERROR", "reason": clock_why,
                        "armed": not shadow, "shadow": shadow, "scorer": lane_params.get("scorer"),
                    })
                print(f"[tickers] WARN: broker clock unreadable ({clock_why}) -- proceeding under "
                      f"the weekday/window invariants", file=sys.stderr)

    bars: dict = {}
    attention: dict = {}
    if shared_creds is not None and all_universe:
        try:
            bars = core.fetch_bars_batch(shared_creds, all_universe, "1Day", limit=400)
            attention = core.merge_scanner_attention(core.attention_from_bars(bars), lane_params, shared_creds)
        except Exception as e:  # noqa: BLE001 -- a bad shared fetch must not block per-arm runs
            print(f"[tickers] WARN: shared bar fetch failed: {type(e).__name__}: {e}", file=sys.stderr)
    else:
        print("[tickers] WARN: no arm has usable creds yet this pass -- each arm will still "
              "log its own NO_CREDS/INVARIANT_FAIL row", file=sys.stderr)

    for a in arms:
        try:
            summary = run_arm(a, lane_params, bars, attention, shadow=shadow, deadline=deadline)
        except Exception as e:  # noqa: BLE001 -- outer safety net: an arm must never take the process down
            print(f"[tickers] {a} UNCAUGHT: {type(e).__name__}: {e}", file=sys.stderr)
            try:
                append_jsonl(arm_ledger_path(a), {
                    "ts_et": now_et().isoformat(timespec="seconds"), "arm": a,
                    "decision": "UNCAUGHT_ERROR", "reason": f"{type(e).__name__}: {e}",
                    "armed": not shadow, "shadow": shadow, "scorer": lane_params.get("scorer"),
                })
            except Exception:  # noqa: BLE001 -- even the error-logging must not crash the process
                pass
            continue
        print(f"[tickers] {summary['arm']} acct={summary['acct']} equity={summary['equity']} "
              f"open={summary['open']} would_place={summary['would_place']} "
              f"placed={summary['placed']} exits={summary['exits']} "
              f"kill={summary['kill']} creds={summary['creds']}", file=sys.stderr)

    print(f"[tickers] pass complete in {time.monotonic() - pass_start:.1f}s "
          f"(budget {WALL_CLOCK_BUDGET_SEC:.0f}s)", file=sys.stderr)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--arm", action="append", choices=list(ARM_NAMES), default=None,
                    help="restrict to one arm (repeatable); default = all three")
    ap.add_argument("--shadow", action="store_true",
                    help="construct+log every order with armed=False; nothing is ever sent")
    ap.add_argument("--once", action="store_true",
                    help="run one pass over all arms and exit (the Task Scheduler install "
                         "always uses this -- the OS trigger provides the 2-minute cadence)")
    ap.add_argument("--params", default=str(DEFAULT_PARAMS_PATH))
    ap.add_argument("--e2e-probe-root", default=None,
                    help="SHADOW-ONLY off-hours end-to-end probe: redirect all per-arm state under "
                         "this dir, ignore the session window, borrow the crypto-twin paper key. "
                         "Refused without --shadow. Never used by the scheduled task.")
    args = ap.parse_args(argv)
    if args.e2e_probe_root and not args.shadow:
        ap.error("--e2e-probe-root requires --shadow (the probe can never arm)")

    arms = args.arm or list(ARM_NAMES)
    params_path = Path(args.params)
    if args.e2e_probe_root:
        global E2E_PROBE_ROOT, TICKERS_STATE_DIR, JOURNAL_DIR
        E2E_PROBE_ROOT = Path(args.e2e_probe_root).resolve()
        TICKERS_STATE_DIR = E2E_PROBE_ROOT / "state"
        JOURNAL_DIR = E2E_PROBE_ROOT / "journal"
        print(f"[tickers] E2E SHADOW PROBE: state -> {TICKERS_STATE_DIR}, key -> {_PROBE_KEY_SOURCE}, "
              f"window ignored, armed=False everywhere", file=sys.stderr)

    if args.once:
        return run_once(arms, params_path, shadow=args.shadow)

    cadence_sec = 120.0
    try:
        lp = mc.load_params(params_path)
        cadence_sec = max(30.0, float((lp.get("tick_cadence") or {}).get("minutes", 2)) * 60.0)
    except Exception:  # noqa: BLE001 -- fall back to the documented default cadence
        pass
    rc = 0
    while True:
        rc = run_once(arms, params_path, shadow=args.shadow)
        time.sleep(cadence_sec)
    return rc  # pragma: no cover -- unreachable (loop only exits via signal/interrupt)


if __name__ == "__main__":
    raise SystemExit(main())
