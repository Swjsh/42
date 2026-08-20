"""multi_status.py -- the one-glance answer to "how is the multi-symbol lane doing?"

LANE `multi-symbol`, ARM `multi-1`, account PA38EG1JTFBT. J has said repeatedly the system
"works but is invisible" and, this week, of prior lane work specifically: *"I still don't
really know where that stands."* This script is the visibility layer for that lane: it prints
a readable terminal table AND writes `automation/state/multi/status.json`, and it never has to
be asked twice what happened -- it reads the lane's own ledgers and says so.

WHAT IT SHOWS (all sourced from files this lane itself writes, never guessed):
  * open positions (from `journal/trades-multi.csv`, via `multi/lib/journal.py`) with DAYS
    HELD in trading sessions (the multi-day-specific fact a same-day lane never needed) and
    current P&L when a live quote is reachable.
  * capital committed (this lane's own book: sum of entry premium x qty x 100 for every open
    position) vs available.
  * today's participation cascade -- how many symbols got evaluated, funnel-filtered, scored,
    went directional, would-place -- and the single TOP BLOCKING GATE, i.e. "why didn't it
    trade" in one read (`automation/state/multi/participation-cascade.jsonl`).
  * the current watchlist top names by relative volume, straight from the latest tick's rows
    in `automation/state/multi/shadow-ledger.jsonl`.
  * scheduled-task health: when `Gamma_MultiCore` (the tick task, `multi/core.py`) last wrote
    a row, and whether that ledger is FRESH. A silently-dead scheduled task is this shop's
    single most repeated failure class (L199, C7) -- staleness must be LOUD, never a quiet
    green light.

============================================================================================
CRITICAL FRAMING -- READ BEFORE TRUSTING ANY NUMBER THIS SCRIPT PRINTS
============================================================================================
Account PA38EG1JTFBT is SHARED with the crypto twin (`setup/scripts/crypto_twin_broker.py`),
which is ARMED and trades BTC/USD every ~60 seconds on this same account, all day, every day.
That means the account's raw `equity` figure is a BLEND of two unrelated programs' P&L, and
**account equity is NOT evidence for either program** (this lane's own creds/broker modules
state the identical rule -- see `multi/lib/creds.py` and `multi/lib/broker.py`). This script
enforces that doctrine structurally, not just by convention:
  * `realized_pnl_today_dollars` is computed EXCLUSIVELY from `journal/trades-multi.csv`'s own
    EXIT rows. It is never derived from, blended with, or corrected against account equity.
  * Account equity, when reachable at all, is surfaced ONLY inside the `capital` block, labeled
    explicitly as shared/contextual, immediately next to a disclosure string. It is never
    printed under a P&L heading and never substituted for `realized_pnl_today_dollars`.
  * If you are extending this script: any temptation to say "just read account equity, it's
    right there" is the exact bug this framing exists to prevent. Read the lane's own ledger.

Run:      backtest/.venv/Scripts/python.exe setup/scripts/multi_status.py
Tests:    backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_multi_journal.py -q
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi.lib import journal as mj  # noqa: E402
from multi.core import GATES as _CORE_GATES  # noqa: E402 -- single source of truth for gate order

ET = ZoneInfo("America/New_York")
STATE_DIR = REPO_ROOT / "automation" / "state" / "multi"
PARAMS_PATH = STATE_DIR / "params.json"
SHADOW_LEDGER = STATE_DIR / "shadow-ledger.jsonl"
CASCADE_PATH = STATE_DIR / "participation-cascade.jsonl"
STATUS_OUT = STATE_DIR / "status.json"
TASK_NAME = "Gamma_MultiCore"

# The funnel stages (multi/lib/watchlist.py) precede the per-symbol gate stack (multi/core.py's
# GATES) in the cascade dict. Combined here into one ordered chain so "top blocking gate" can
# see the WHOLE funnel->engine path in one pass, not just the engine half.
FUNNEL_STAGES: tuple[str, ...] = ("funnel_universe", "funnel_liquidity", "funnel_attention", "funnel_setup")
# NOTE: `cascade["evaluated"]` in multi/core.py's tick() increments once per symbol in the
# FULL input universe (parallel to funnel_universe, same value) -- it is NOT downstream of
# funnel_setup. Splicing it in after funnel_setup would fabricate a fake drop between
# funnel_setup and bars_ok equal to however many symbols the funnel already filtered out
# (that loss is real but it belongs to the funnel stages above, not to a "bars_ok gate").
# Deliberately excluded from the chain for that reason; funnel_setup feeds bars_ok directly.
CASCADE_CHAIN: tuple[str, ...] = FUNNEL_STAGES + tuple(_CORE_GATES)

STALE_AFTER_MIN = 90.0  # ">90 min during RTH is stale" -- CLAUDE.md multi-lane journaling brief


def now_et() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(ET)


def _is_rth(t: dt.datetime) -> bool:
    if t.weekday() >= 5:
        return False
    open_t = t.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = t.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= t <= close_t


# --- low-level readers: never raise on absence, tolerate a crash-truncated tail line -----

def load_params(path: Path = PARAMS_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a crash-truncated trailing partial line
    return out


def latest_cascade(path: Path = CASCADE_PATH) -> Optional[dict]:
    rows = _read_jsonl(path)
    return rows[-1] if rows else None


def top_blocking_gate(cascade: Optional[dict]) -> Optional[dict]:
    """Where the funnel/engine loses the MOST symbols, stage over stage. The single most
    useful number on this whole status surface: "why didn't it trade" in one read.

    Compares every consecutive pair in `CASCADE_CHAIN` present in `cascade` and returns the
    (label, dropped-count) pair with the largest drop. Missing keys (older cascade rows
    predate the funnel stages) are skipped rather than treated as zero, so a partial/older
    record never falsely reports a giant drop from an absent field.
    """
    if not cascade:
        return None
    present = [(k, cascade[k]) for k in CASCADE_CHAIN if isinstance(cascade.get(k), (int, float))]
    if len(present) < 2:
        return None
    worst_label, worst_drop = None, -1
    for (prev_k, prev_v), (cur_k, cur_v) in zip(present, present[1:]):
        drop = prev_v - cur_v
        if drop > worst_drop:
            worst_drop = drop
            worst_label = f"{prev_k} -> {cur_k}"
    if worst_drop <= 0:
        return {"gate": None, "dropped": 0,
                "note": "no symbols were lost between any two measured stages this tick"}
    return {"gate": worst_label, "dropped": worst_drop}


def read_watchlist_top(path: Path = SHADOW_LEDGER, top_n: int = 8) -> list[dict]:
    """Symbols examined on the LAST tick (by ts_et), ranked by relative volume -- the same
    ranking `multi/lib/watchlist.py` stage 2 uses, read back from what the tick actually
    recorded rather than re-derived."""
    rows = _read_jsonl(path)
    if not rows:
        return []
    latest_ts = max((r.get("ts_et") for r in rows if r.get("ts_et")), default=None)
    if latest_ts is None:
        return []
    latest_rows = [r for r in rows if r.get("ts_et") == latest_ts]
    latest_rows.sort(
        key=lambda r: r["rel_volume"] if isinstance(r.get("rel_volume"), (int, float)) else -1.0,
        reverse=True,
    )
    return [
        {"symbol": r.get("symbol"), "rel_volume": r.get("rel_volume"),
         "decision": r.get("decision"), "action": r.get("action"), "gate": r.get("gate")}
        for r in latest_rows[:top_n]
    ]


def ledger_freshness(now: dt.datetime, path: Path = SHADOW_LEDGER,
                      stale_after_min: float = STALE_AFTER_MIN) -> dict:
    """FRESH / STALE / NO_DATA -- never silently reports a dead task as healthy.

    STALE is reported honestly regardless of whether `now` falls in RTH: a scheduled task
    that silently died is exactly as dead outside market hours as inside it. `checked_during_rth`
    is carried alongside as CONTEXT (Gamma_MultiCore is registered RTH-only, so an off-hours
    STALE reading is expected and not itself alarming) -- but the status field is never
    softened to hide it.
    """
    rows = _read_jsonl(path)
    ts_values: list[dt.datetime] = []
    for r in rows:
        ts = r.get("ts_et")
        if not ts:
            continue
        try:
            ts_values.append(dt.datetime.fromisoformat(ts))
        except ValueError:
            continue
    if not ts_values:
        return {
            "status": "NO_DATA", "last_ts_et": None, "age_minutes": None,
            "stale_threshold_minutes": stale_after_min,
            "note": ("shadow-ledger.jsonl has no readable rows -- Gamma_MultiCore may never "
                     "have run, or the file is missing/corrupt"),
        }
    last_ts = max(ts_values)
    age_min = (now - last_ts).total_seconds() / 60.0
    status = "STALE" if age_min > stale_after_min else "FRESH"
    return {
        "status": status, "last_ts_et": last_ts.isoformat(timespec="seconds"),
        "age_minutes": round(age_min, 1), "stale_threshold_minutes": stale_after_min,
        "checked_during_rth": _is_rth(now),
    }


# --- open-position enrichment (journal is authoritative; broker is a best-effort overlay) --

def _open_position_rows(now: dt.datetime, journal_path: Path,
                         quote_fn: Optional[Callable[[Optional[str]], Optional[float]]]) -> tuple[list[dict], float]:
    try:
        open_rows = mj.open_trades(journal_path)
    except Exception as e:  # noqa: BLE001 -- a journal read failure must not crash the status surface
        return [{"_error": f"journal.open_trades failed: {type(e).__name__}: {e}"}], 0.0

    out: list[dict] = []
    committed = 0.0
    for r in open_rows:
        try:
            entry_date = mj.parse_date(r["entry_date"])
            sessions_held = mj.trading_sessions_held(entry_date, now.date())
            qty = int(float(r["qty"]))
            entry_prem = float(r["entry_premium"])
            committed += qty * entry_prem * 100.0

            cur_prem = None
            if quote_fn is not None:
                try:
                    cur_prem = quote_fn(r.get("contract"))
                except Exception:  # noqa: BLE001 -- a bad quote must never crash the report
                    cur_prem = None
            unreal = None
            if cur_prem is not None:
                unreal = round((float(cur_prem) - entry_prem) * qty * 100.0, 2)

            out.append({
                "trade_id": r.get("trade_id"), "symbol": r.get("symbol"),
                "contract": r.get("contract"), "side": r.get("side"),
                "entry_date": r.get("entry_date"), "qty": qty,
                "entry_premium": entry_prem, "days_held_sessions": sessions_held,
                "current_premium": cur_prem, "unrealized_pnl_dollars": unreal,
            })
        except (KeyError, ValueError, TypeError, mj.JournalError) as e:
            out.append({"trade_id": r.get("trade_id"), "_error": f"{type(e).__name__}: {e}"})
    return out, committed


def _realized_pnl_today(now: dt.datetime, journal_path: Path) -> tuple[float, int]:
    """Sourced EXCLUSIVELY from journal EXIT rows -- see module docstring's CRITICAL FRAMING.
    Never touches account equity, never accepts an equity value as an input."""
    try:
        closed = mj.closed_trades(journal_path)
    except Exception:  # noqa: BLE001
        return 0.0, 0
    today = now.date().isoformat()
    total = 0.0
    n_today = 0
    for r in closed:
        if r.get("exit_date") != today:
            continue
        pnl = r.get("pnl_dollars")
        if pnl in (None, ""):
            continue
        try:
            total += float(pnl)
            n_today += 1
        except (TypeError, ValueError):
            continue
    return round(total, 2), n_today


# --- top-level status assembly -------------------------------------------------------------

def build_status(
    *,
    now: Optional[dt.datetime] = None,
    params_path: Path = PARAMS_PATH,
    ledger_path: Path = SHADOW_LEDGER,
    cascade_path: Path = CASCADE_PATH,
    journal_path: Path = mj.JOURNAL_PATH,
    quote_fn: Optional[Callable[[Optional[str]], Optional[float]]] = None,
    equity_fn: Optional[Callable[[], float]] = None,
) -> dict:
    """Assemble the full status dict. Every sub-read is individually best-effort (a missing or
    corrupt source is reported IN the output, never allowed to crash the whole surface) except
    the journal reads, which are this lane's primary evidence and are reported honestly rather
    than papered over. No network call is made unless `quote_fn`/`equity_fn` are supplied.
    """
    now = now or now_et()
    result: dict[str, Any] = {
        "lane": "multi-symbol", "arm": "multi-1", "as_of_et": now.isoformat(timespec="seconds"),
    }

    try:
        params = load_params(params_path)
        result["mode"] = {
            "shadow_only": bool(params.get("shadow_only", True)),
            "live": bool(params.get("live", False)),
            "account": (params.get("account") or {}).get("account_number"),
        }
    except (OSError, json.JSONDecodeError) as e:
        result["mode"] = {"error": f"{type(e).__name__}: {e}", "shadow_only": True, "live": False}

    positions, committed = _open_position_rows(now, journal_path, quote_fn)
    result["open_positions"] = positions

    equity = None
    if equity_fn is not None:
        try:
            equity = float(equity_fn())
        except Exception:  # noqa: BLE001 -- broker unreachable must never crash the report
            equity = None
    result["capital"] = {
        "committed_dollars": round(committed, 2),
        "account_equity_dollars": equity,
        "available_dollars": (round(equity - committed, 2) if equity is not None else None),
        "_disclosure": (
            "account_equity_dollars is the SHARED balance with the crypto twin (BTC/USD, "
            "armed, trading every ~60s on the same account, PA38EG1JTFBT) -- it is NOT "
            "evidence of this lane's P&L and is never used to compute realized_pnl_today_dollars. "
            "This lane's only P&L evidence is journal/trades-multi.csv."
        ),
    }

    cascade = latest_cascade(cascade_path)
    result["cascade"] = cascade
    result["top_blocking_gate"] = top_blocking_gate(cascade)
    result["watchlist_top"] = read_watchlist_top(ledger_path)
    result["ledger_health"] = ledger_freshness(now, ledger_path)
    result["scheduled_task"] = TASK_NAME

    realized, n_closed_today = _realized_pnl_today(now, journal_path)
    result["realized_pnl_today_dollars"] = realized
    result["closed_trades_today"] = n_closed_today
    try:
        result["closed_trades_total"] = len(mj.closed_trades(journal_path))
    except Exception:  # noqa: BLE001
        result["closed_trades_total"] = 0

    return result


# --- rendering -------------------------------------------------------------------------

def _money(v: Optional[float]) -> str:
    return "N/A" if v is None else f"${v:,.2f}"


def format_table(status: dict) -> str:
    lines: list[str] = []
    W = 78
    lines.append("=" * W)
    lines.append(f"MULTI-SYMBOL LANE STATUS -- arm {status.get('arm')} -- as of {status.get('as_of_et')}")
    lines.append("=" * W)

    mode = status.get("mode") or {}
    shadow = mode.get("shadow_only", True)
    live = mode.get("live", False)
    banner = "SHADOW ONLY -- NO REAL ORDERS ARE EVER SENT" if shadow and not live else (
        "*** ARMED -- REAL ORDERS CAN BE SENT ***" if live else "UNKNOWN MODE -- treat as shadow until verified"
    )
    lines.append(f"MODE: {banner}")
    lines.append(f"  shadow_only={shadow}  live={live}  account={mode.get('account') or 'N/A'} "
                 f"(SHARED with crypto twin -- see CAPITAL section)")
    lines.append("")

    lines.append("OPEN POSITIONS (source: journal/trades-multi.csv -- this lane's own book)")
    positions = status.get("open_positions") or []
    if not positions:
        lines.append("  (none open)")
    else:
        lines.append(f"  {'SYMBOL':<8}{'SIDE':<5}{'QTY':<5}{'ENTRY':<9}{'DAYS':<6}{'CUR':<9}{'UNREAL $':<12}")
        for p in positions:
            if "_error" in p:
                lines.append(f"  [unreadable position: {p['_error']}]")
                continue
            cur = p.get("current_premium")
            unreal = p.get("unrealized_pnl_dollars")
            lines.append(
                f"  {str(p.get('symbol')):<8}{str(p.get('side')):<5}{str(p.get('qty')):<5}"
                f"{p.get('entry_premium'):<9.2f}{str(p.get('days_held_sessions')):<6}"
                f"{(f'{cur:.2f}' if cur is not None else 'N/A'):<9}"
                f"{(_money(unreal) if unreal is not None else 'N/A'):<12}"
            )
    lines.append("")

    cap = status.get("capital") or {}
    lines.append("CAPITAL")
    lines.append(f"  Committed (this lane's own book) : {_money(cap.get('committed_dollars'))}")
    lines.append(f"  Account equity (SHARED, context only, NOT this lane's P&L): "
                 f"{_money(cap.get('account_equity_dollars'))}")
    lines.append(f"  Available (equity - committed, informational)             : "
                 f"{_money(cap.get('available_dollars'))}")
    lines.append(f"  ⚠ {cap.get('_disclosure', '')}")
    lines.append("")

    lines.append("TODAY'S PARTICIPATION CASCADE (why did/didn't it trade)")
    cascade = status.get("cascade")
    if not cascade:
        lines.append("  (no cascade rows yet -- Gamma_MultiCore has not written a tick)")
    else:
        chain_str = " -> ".join(f"{k}={cascade[k]}" for k in CASCADE_CHAIN if k in cascade)
        lines.append(f"  {chain_str}")
        tbg = status.get("top_blocking_gate")
        if tbg and tbg.get("gate"):
            lines.append(f"  TOP BLOCKING GATE: {tbg['gate']}  (dropped {tbg['dropped']})")
        elif tbg:
            lines.append(f"  TOP BLOCKING GATE: {tbg.get('note', 'n/a')}")
    lines.append("")

    lines.append("WATCHLIST TOP (last tick, ranked by relative volume)")
    watch = status.get("watchlist_top") or []
    if not watch:
        lines.append("  (no watchlist rows yet)")
    else:
        lines.append(f"  {'SYMBOL':<8}{'RVOL':<8}{'DECISION':<10}{'GATE':<20}")
        for w in watch:
            rv = w.get("rel_volume")
            rv_s = f"{rv:.2f}" if isinstance(rv, (int, float)) else "N/A"
            lines.append(f"  {str(w.get('symbol')):<8}{rv_s:<8}{str(w.get('decision')):<10}"
                         f"{str(w.get('gate') or ''):<20}")
    lines.append("")

    lh = status.get("ledger_health") or {}
    lines.append(f"SCHEDULED TASK: {status.get('scheduled_task')}")
    st = lh.get("status")
    marker = {"FRESH": "OK", "STALE": "*** STALE ***", "NO_DATA": "*** NO DATA ***"}.get(st, st)
    lines.append(f"  Shadow ledger: {marker}   last row: {lh.get('last_ts_et') or 'N/A'}   "
                 f"age: {lh.get('age_minutes')} min (threshold {lh.get('stale_threshold_minutes')})")
    if lh.get("note"):
        lines.append(f"  {lh['note']}")
    lines.append("")

    lines.append(f"REALIZED P&L TODAY (source: journal/trades-multi.csv EXIT rows ONLY, "
                 f"never account equity): {_money(status.get('realized_pnl_today_dollars'))}"
                 f"  ({status.get('closed_trades_today')} closed today, "
                 f"{status.get('closed_trades_total')} closed all-time)")
    lines.append("=" * W)
    return "\n".join(lines)


# --- optional live wiring (network -- never used by tests) --------------------------------

def _live_quote_fn(contract: Optional[str]) -> Optional[float]:
    if not contract:
        return None
    from multi.core import fetch_option_quote
    from multi.lib import creds as mc

    params = load_params()
    c = mc.resolve(params)
    q = fetch_option_quote(c, contract)
    if not q:
        return None
    return (float(q["bid"]) + float(q["ask"])) / 2.0


def _live_equity_fn() -> float:
    from multi.lib import broker as mb
    from multi.lib import creds as mc

    params = load_params()
    c = mc.resolve(params)
    acct = mb.get_account(c)
    return float(acct.get("equity") or 0.0)


def main(argv: Optional[list[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp1252 console fix
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-write", action="store_true", help="skip writing status.json")
    ap.add_argument("--no-live", action="store_true",
                     help="skip live broker calls (quotes/equity) -- ledger-only status")
    args = ap.parse_args(argv)

    quote_fn = None if args.no_live else _live_quote_fn
    equity_fn = None if args.no_live else _live_equity_fn

    status = build_status(quote_fn=quote_fn, equity_fn=equity_fn)
    print(format_table(status))

    if not args.no_write:
        STATUS_OUT.parent.mkdir(parents=True, exist_ok=True)
        STATUS_OUT.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
        print(f"\n[multi_status] wrote {STATUS_OUT}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
