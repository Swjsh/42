"""live_watch.py -- WS7 LIVE WATCH: the ONE canonical "are we in a trade / what's it doing"
state surface (J should never have to ask).

Rewrites automation/state/live-watch.json every minute during RTH with, PER ARM (the 5
active SPY accounts in fleet/accounts.json: core safe-2/bold-2 + fleet safe-3/risky-1/
risky-3):
  * position: symbol / qty / entry premium / current MID (Alpaca option quote, broker
    position current_price fallback), unrealized P&L $ and % (broker-truth preferred),
  * distance to stop (premium-space % cushion; structure mode also SPY-points to the
    trigger level) and to the CURRENT take-profit target (TP1 before tp1_filled, runner
    target after), read from the engine's own exit-state ledger
    (automation/state/fleet/{arm}/exit-state.json -- exit_manager.ExitState.to_dict),
  * high-water mark premium + profit-lock armed flag,
  * time in trade (entry fill time from today's closed buy orders, cached across fires
    in the previous snapshot so the broker is asked once per position, not per minute),
  * last decision verdict + reason + age (core-decisions.jsonl split by account for the
    two mcp_heartbeat arms; fleet/{arm}/decisions.jsonl for the fleet_rest arms),
  * kill-switch/breaker state, normalized across the THREE breaker vocabularies (safe /
    fleet share one schema; aggressive is fully divergent -- C9 symmetry trap, mapping
    documented in automation/state/circuit-breaker.json's _schema_note),
plus a READ-ONLY link-in of automation/state/theta-clock.json when present (ANOTHER task
owns writing it -- this module must never write that path).

VISIBILITY ONLY: places no order, touches no exit rule, writes nothing any engine reads.
Fail-open everywhere (C7: audit outputs, not exit codes): one arm/position/field failure
degrades THAT field to null + a note, never sinks the tick; production paths always exit 0;
no lock/pid file (the scheduled task's -MultipleInstances IgnoreNew is the overlap guard).
Market closed -> a single state=CLOSED write, then silence (no spam, no churn).

CLI:
  (no args)            one production tick (write live-watch.json)
  --brief              compact per-arm text block (Discord/brief use) from the last snapshot
  --dry-run-synthetic  full assembly with an INJECTED synthetic position through the real
                       code path; proves every field populates; writes live-watch-dryrun.json
                       (never the production file); exit 2 on any missing field (loud proof)
  --force-open         treat the market as open (testing aid for the closed window)

Guard: backtest/tests/test_live_watch.py. Task: Gamma_LiveWatch (install-live-watch.ps1).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "live-watch.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "live-watch.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FLEET = STATE / "fleet"
OUT_PATH = STATE / "live-watch.json"
DRYRUN_OUT_PATH = STATE / "live-watch-dryrun.json"
THETA_PATH = STATE / "theta-clock.json"          # READ-ONLY -- another task writes this
SIGHT_BEACON_PATH = STATE / "sight-beacon.json"
CORE_DECISIONS_PATH = STATE / "core-decisions.jsonl"
ACCOUNTS_PATH = FLEET / "accounts.json"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
sys.path.insert(0, str(FLEET))

SCHEMA_VERSION = 1
# Watcher-active ET window: 5 min before the bell so the surface is alive at 09:30, and
# 5 min past the 16:00 close so a lingering position's final minutes are still shown
# (same rationale as Gamma_ThetaClock's window). Deterministic time window only -- a
# market HOLIDAY inside this window reads as OPEN (cosmetic: all arms will simply be
# flat with stale decisions; documented, not worth a broker clock call per minute).
OPEN_HHMM = "09:25"
CLOSE_HHMM = "16:05"
DECISIONS_TAIL_BYTES = 512 * 1024
_FRAC_RE = re.compile(r"\.(\d{6})\d+")       # nanosecond -> microsecond timestamp trim
_OCC_RE = re.compile(r"^SPY(\d{6})([CP])(\d{8})$")

# Fields the synthetic dry-run must prove populate non-null (the WS7 acceptance list).
REQUIRED_POSITION_FIELDS = (
    "symbol", "qty", "entry_premium", "mid", "mid_source",
    "unrealized_pnl_usd", "unrealized_pnl_pct",
    "stop_mode", "stop_premium", "dist_to_stop_pct",
    "tp_phase", "tp_target_premium", "dist_to_tp_pct",
    "hwm_premium", "hwm_gain_pct", "profit_lock_armed",
    "entry_time_et", "time_in_trade_min",
)


# --------------------------------------------------------------------------- #
# small fail-open IO helpers
# --------------------------------------------------------------------------- #
def _read_json(p: Path) -> Optional[dict]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _tail_lines(p: Path, max_bytes: int = DECISIONS_TAIL_BYTES) -> list[str]:
    """Last lines of a JSONL file reading at most max_bytes from the end (fail-open [])."""
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # drop the partial first line
            data = f.read()
        return data.decode("utf-8", errors="replace").strip().splitlines()
    except OSError:
        return []


def _atomic_write_json(p: Path, payload: dict) -> None:
    """tmp + os.replace so the dashboard (3s poll) never reads a half-written file."""
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _parse_utc(ts: Any) -> Optional[dt.datetime]:
    """RFC3339 (Alpaca, up to ns precision) -> aware-UTC datetime; None if unparseable."""
    if not isinstance(ts, str) or not ts:
        return None
    t = _FRAC_RE.sub(r".\1", ts.strip().replace("Z", "+00:00"), count=1)
    try:
        d = dt.datetime.fromisoformat(t)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _utc_to_et_str(d: dt.datetime) -> Optional[str]:
    try:
        from et_clock import et_offset_hours
        et = d.astimezone(dt.timezone.utc) + dt.timedelta(hours=et_offset_hours(d))
        return et.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        return None


def _age_min(ts_et: Optional[str], now_et: dt.datetime) -> Optional[float]:
    """Minutes between a naive ET timestamp string and now_et (fail-open None)."""
    if not ts_et:
        return None
    try:
        t = dt.datetime.fromisoformat(str(ts_et)[:19])
    except ValueError:
        return None
    return round((now_et.replace(tzinfo=None) - t).total_seconds() / 60.0, 1)


# --------------------------------------------------------------------------- #
# pure builders (unit-tested; no IO)
# --------------------------------------------------------------------------- #
def parse_occ(symbol: str) -> dict:
    """SPY260801C00747000 -> {expiry_yymmdd, right, strike}; {}s on non-OCC input."""
    m = _OCC_RE.match(symbol or "")
    if not m:
        return {"expiry_yymmdd": None, "right": None, "strike": None}
    return {"expiry_yymmdd": m.group(1), "right": m.group(2),
            "strike": int(m.group(3)) / 1000.0}


def normalize_breaker(raw: Optional[dict], flavor: str, path_str: str) -> dict:
    """One kill-switch vocabulary out of three breaker schemas.

    flavor 'safe' covers BOTH the core-safe file and the fleet per-arm files (same keys:
    tripped / tripped_reason / starting_equity_today / daily_loss_limit_pct). flavor
    'aggressive' is the divergent bold vocabulary (trip_reason / equity_start_of_day /
    daily_loss_kill_switch_pct) -- C9: a cross-account consumer that reads the safe keys
    on the bold file gets nulls, so the mapping lives HERE, tested."""
    if not isinstance(raw, dict):
        return {"present": False, "tripped": None, "reason": None,
                "sod_equity": None, "loss_limit_pct": None, "source": path_str}
    if flavor == "aggressive":
        return {
            "present": True,
            "tripped": bool(raw.get("tripped", False)),
            "reason": raw.get("trip_reason"),
            "sod_equity": raw.get("equity_start_of_day"),
            "loss_limit_pct": raw.get("daily_loss_kill_switch_pct"),
            "source": path_str,
        }
    return {
        "present": True,
        "tripped": bool(raw.get("tripped", False)),
        "reason": raw.get("tripped_reason"),
        "sod_equity": raw.get("starting_equity_today"),
        "loss_limit_pct": raw.get("daily_loss_limit_pct"),
        "source": path_str,
    }


def pick_core_decision(lines: list[str], account: str) -> Optional[dict]:
    """Newest core-decisions.jsonl row for account 'safe'|'bold' (fail-open None)."""
    for ln in reversed(lines):
        try:
            row = json.loads(ln)
        except (ValueError, TypeError):
            continue
        if row.get("account") == account:
            return {"verdict": row.get("verdict"), "reason": row.get("reason"),
                    "side": row.get("side"), "setup": row.get("setup"),
                    "ts_et": row.get("ts_et")}
    return None


def pick_fleet_decision(lines: list[str]) -> Optional[dict]:
    """Newest fleet/{arm}/decisions.jsonl row mapped onto the core vocabulary."""
    for ln in reversed(lines):
        try:
            row = json.loads(ln)
        except (ValueError, TypeError):
            continue
        return {"verdict": row.get("action"),
                "reason": row.get("reason") or row.get("risk_code"),
                "side": row.get("side"), "setup": row.get("setup_name"),
                "ts_et": row.get("ts_et")}
    return None


def build_position_view(*, pos_raw: dict, exit_rec: Optional[dict], mid: Optional[float],
                        mid_source: str, spy_last: Optional[float],
                        entry_time_et: Optional[str],
                        now_et: dt.datetime) -> dict:
    """The per-position record -- every WS7 field, honest None when an input is missing.

    exit_rec is the engine's own persisted exit_manager.ExitState dict for this symbol
    (stop/TP/HWM authority). Broker unrealized_pl/plpc preferred for P&L (contract
    multiplier already applied); mid-based % kept alongside for the premium view."""
    symbol = str(pos_raw.get("symbol") or "")
    occ = parse_occ(symbol)
    try:
        qty = int(float(pos_raw.get("qty", 0)))
    except (TypeError, ValueError):
        qty = None
    entry = _f(pos_raw.get("avg_entry_price"))
    if entry is None and exit_rec:
        entry = _f(exit_rec.get("entry_premium"))
    cur_mid = mid if mid is not None else _f(pos_raw.get("current_price"))
    upl = _f(pos_raw.get("unrealized_pl"))
    uplpc = _f(pos_raw.get("unrealized_plpc"))
    upl_pct = round(uplpc * 100.0, 2) if uplpc is not None else None
    if upl_pct is None and cur_mid is not None and entry not in (None, 0):
        upl_pct = round((cur_mid / entry - 1.0) * 100.0, 2)
    if upl is None and cur_mid is not None and entry is not None and qty:
        upl = round((cur_mid - entry) * 100.0 * qty, 2)

    # ---- stop (exit-state authority) ----
    stop_mode = stop_premium = trigger_level = None
    dist_stop_pct = dist_level_pts = None
    tp_phase = tp_target = dist_tp_pct = None
    hwm = hwm_gain_pct = None
    lock_armed = tp1_filled = None
    if isinstance(exit_rec, dict):
        stop_mode = exit_rec.get("stop_mode", "premium")
        stop_premium = _f(exit_rec.get("runner_stop_premium"))
        trigger_level = _f(exit_rec.get("trigger_level"))
        tp1_filled = bool(exit_rec.get("tp1_filled", False))
        e_prem = _f(exit_rec.get("entry_premium")) or entry
        if cur_mid not in (None, 0) and stop_premium is not None:
            dist_stop_pct = round((cur_mid - stop_premium) / cur_mid * 100.0, 1)
        if stop_mode == "structure" and trigger_level is not None and spy_last is not None:
            side = exit_rec.get("side") or occ["right"]  # OCC fallback when side absent
            sign = 1.0 if side == "C" else -1.0
            dist_level_pts = round(sign * (spy_last - trigger_level), 2)
        if e_prem is not None:
            if not tp1_filled:
                tp_phase = "TP1"
                pct = _f(exit_rec.get("tp1_premium_pct"))
                tp_target = round(e_prem * (1.0 + pct), 4) if pct is not None else None
            else:
                tp_phase = "RUNNER"
                pct = _f(exit_rec.get("runner_target_pct"))
                tp_target = round(e_prem * (1.0 + pct), 4) if pct is not None else None
        if tp_target is not None and cur_mid not in (None, 0):
            dist_tp_pct = round((tp_target - cur_mid) / cur_mid * 100.0, 1)
        hwm = _f(exit_rec.get("hwm_premium"))
        if hwm is not None and e_prem not in (None, 0):
            hwm_gain_pct = round((hwm / e_prem - 1.0) * 100.0, 1)
        lock_armed = bool(exit_rec.get("profit_lock_armed", False))

    tim = None
    if entry_time_et:
        tim = _age_min(entry_time_et, now_et)

    return {
        "symbol": symbol, "right": occ["right"], "strike": occ["strike"],
        "qty": qty, "entry_premium": entry,
        "mid": cur_mid, "mid_source": mid_source,
        "unrealized_pnl_usd": upl, "unrealized_pnl_pct": upl_pct,
        "stop_mode": stop_mode, "stop_premium": stop_premium,
        "trigger_level": trigger_level,
        "dist_to_stop_pct": dist_stop_pct, "dist_to_stop_level_pts": dist_level_pts,
        "tp_phase": tp_phase, "tp_target_premium": tp_target, "dist_to_tp_pct": dist_tp_pct,
        "tp1_filled": tp1_filled,
        "hwm_premium": hwm, "hwm_gain_pct": hwm_gain_pct,
        "profit_lock_armed": lock_armed,
        "entry_time_et": entry_time_et, "time_in_trade_min": tim,
        "exit_state_found": isinstance(exit_rec, dict),
    }


def _f(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# broker access (injectable -- tests/dry-run pass stubs, production wires fleet_broker)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Broker:
    """The three read-only broker touchpoints, injectable for tests/dry-run."""
    positions: Callable[[dict], list]                 # creds -> raw Alpaca positions
    option_mid: Callable[[dict, str], Optional[float]]
    entry_fill_utc: Callable[[dict, str], Optional[str]]  # creds, symbol -> filled_at


def _live_entry_fill_utc(creds: dict, symbol: str) -> Optional[str]:
    """Earliest filled BUY order for symbol today (UTC ISO) via /v2/orders. Fail-open."""
    try:
        import fleet_broker as fb
        from et_clock import et_today_str
        rows = fb._request(  # noqa: SLF001 -- deliberate reuse of the fleet REST core
            creds,
            f"orders?status=closed&after={et_today_str()}T00:00:00Z"
            f"&symbols={symbol}&direction=asc&limit=200")
        for o in rows or []:
            if o.get("side") == "buy" and o.get("filled_at"):
                return str(o["filled_at"])
    except Exception:  # noqa: BLE001
        return None
    return None


def _live_broker() -> Broker:
    import fleet_broker as fb
    return Broker(
        positions=lambda creds: fb.open_spy_option_positions(creds),
        option_mid=lambda creds, sym: fb.get_option_mid(creds, sym),
        entry_fill_utc=_live_entry_fill_utc,
    )


# --------------------------------------------------------------------------- #
# arm assembly
# --------------------------------------------------------------------------- #
def _ledger_for_arm(arm_id: str, execution: str) -> tuple[str, Any]:
    """('core', 'safe'|'bold') for the two mcp_heartbeat arms, ('fleet', path) otherwise."""
    if execution == "mcp_heartbeat":
        return ("core", "safe" if arm_id.startswith("safe") else "bold")
    return ("fleet", FLEET / arm_id / "decisions.jsonl")


def _breaker_for_arm(arm_id: str, execution: str) -> tuple[Path, str]:
    if execution == "mcp_heartbeat":
        if arm_id.startswith("safe"):
            return (STATE / "circuit-breaker.json", "safe")
        return (STATE / "aggressive" / "circuit-breaker.json", "aggressive")
    return (FLEET / arm_id / "circuit-breaker.json", "safe")


def assemble_arm(*, arm: dict, creds: Optional[dict], broker: Broker,
                 spy_last: Optional[float], now_et: dt.datetime,
                 core_lines: list[str], prev_arm: Optional[dict],
                 exit_state_override: Optional[dict] = None) -> dict:
    """One arm's full live-watch record. Every sub-step fail-open: a failure degrades the
    field and appends a note, never raises out of this function. exit_state_override lets
    the dry-run/guards inject a {symbol: ExitState-dict} ledger instead of reading the
    arm's real exit-state.json (production passes None = read from disk)."""
    arm_id = str(arm.get("id"))
    execution = str(arm.get("execution") or "")
    notes: list[str] = []
    out: dict = {
        "display_name": arm.get("display_name") or arm_id,
        "execution": execution,
        "in_trade": False,
        "position": None,
        "last_decision": None,
        "kill_switch": None,
        "status": "ok",
    }

    # -- last decision --------------------------------------------------------
    try:
        kind, ref = _ledger_for_arm(arm_id, execution)
        dec = (pick_core_decision(core_lines, ref) if kind == "core"
               else pick_fleet_decision(_tail_lines(ref)))
        if dec:
            dec["age_min"] = _age_min(dec.get("ts_et"), now_et)
        out["last_decision"] = dec
        if dec is None:
            notes.append("no decision row found")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"decision read failed: {exc}")

    # -- kill switch ----------------------------------------------------------
    try:
        bp, flavor = _breaker_for_arm(arm_id, execution)
        out["kill_switch"] = normalize_breaker(_read_json(bp), flavor,
                                               str(bp.relative_to(REPO)))
    except Exception as exc:  # noqa: BLE001
        notes.append(f"breaker read failed: {exc}")

    # -- position -------------------------------------------------------------
    if creds is None:
        notes.append("no creds for arm")
    else:
        try:
            raw_positions = broker.positions(creds) or []
        except Exception as exc:  # noqa: BLE001
            raw_positions = []
            notes.append(f"positions read failed: {exc}")
        views = []
        exit_state = (exit_state_override if exit_state_override is not None
                      else _read_json(FLEET / arm_id / "exit-state.json") or {})
        for p in raw_positions:
            sym = str(p.get("symbol") or "")
            try:
                mid = None
                mid_source = "position.current_price"
                try:
                    mid = broker.option_mid(creds, sym)
                    if mid is not None:
                        mid_source = "option_quote_mid"
                except Exception:  # noqa: BLE001
                    pass
                entry_time_et = _cached_entry_time(prev_arm, sym)
                if entry_time_et is None:
                    fill_utc = None
                    try:
                        fill_utc = broker.entry_fill_utc(creds, sym)
                    except Exception:  # noqa: BLE001
                        pass
                    if fill_utc:
                        d = _parse_utc(fill_utc)
                        entry_time_et = _utc_to_et_str(d) if d else None
                    if entry_time_et is None:
                        notes.append(f"entry time unknown for {sym}")
                views.append(build_position_view(
                    pos_raw=p, exit_rec=exit_state.get(sym), mid=mid,
                    mid_source=mid_source, spy_last=spy_last,
                    entry_time_et=entry_time_et, now_et=now_et))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"position view failed for {sym}: {exc}")
        out["in_trade"] = len(views) > 0
        out["position"] = views[0] if len(views) == 1 else (views or None)

    if notes:
        out["status"] = "degraded: " + "; ".join(notes)[:400]
    return out


def _cached_entry_time(prev_arm: Optional[dict], symbol: str) -> Optional[str]:
    """entry_time_et from the previous snapshot when the same symbol is still open --
    the broker orders endpoint is asked once per position lifetime, not once per minute."""
    if not isinstance(prev_arm, dict):
        return None
    pos = prev_arm.get("position")
    cands = pos if isinstance(pos, list) else [pos]
    for c in cands:
        if isinstance(c, dict) and c.get("symbol") == symbol and c.get("entry_time_et"):
            return str(c["entry_time_et"])
    return None


def read_theta_link() -> Optional[dict]:
    """READ-ONLY link-in of theta-clock.json (owned by Gamma_ThetaClock -- never write)."""
    raw = _read_json(THETA_PATH)
    if not isinstance(raw, dict):
        return None
    return {"ts_et": raw.get("ts_et"), "n_positions": raw.get("n_positions"),
            "n_alerts": raw.get("n_alerts"), "positions": raw.get("positions"),
            "source": "theta-clock.json (read-only link-in)"}


# --------------------------------------------------------------------------- #
# top-level snapshot
# --------------------------------------------------------------------------- #
def market_state_for(now_et: dt.datetime) -> str:
    hm = now_et.strftime("%H:%M")
    return "RTH" if (now_et.weekday() < 5 and OPEN_HHMM <= hm <= CLOSE_HHMM) else "CLOSED"


def active_spy_arms(accounts: Optional[dict]) -> list[dict]:
    return [a for a in (accounts or {}).get("arms", [])
            if isinstance(a, dict) and a.get("status") == "active"
            and a.get("instrument") == "SPY_0DTE_OPTION"]


def build_snapshot(*, now_et: dt.datetime, broker: Broker,
                   creds_by_arm: dict, accounts: Optional[dict],
                   prev: Optional[dict]) -> dict:
    beacon = _read_json(SIGHT_BEACON_PATH) or {}
    spy_last = _f(beacon.get("spy"))
    core_lines = _tail_lines(CORE_DECISIONS_PATH)
    prev_arms = (prev or {}).get("arms", {}) if isinstance(prev, dict) else {}
    arms_out: dict[str, dict] = {}
    errors: list[str] = []
    for arm in active_spy_arms(accounts):
        arm_id = str(arm.get("id"))
        try:
            arms_out[arm_id] = assemble_arm(
                arm=arm, creds=creds_by_arm.get(arm_id), broker=broker,
                spy_last=spy_last, now_et=now_et, core_lines=core_lines,
                prev_arm=prev_arms.get(arm_id))
        except Exception as exc:  # noqa: BLE001  (belt over assemble_arm's own braces)
            errors.append(f"{arm_id}: {exc}")
            arms_out[arm_id] = {"display_name": arm.get("display_name") or arm_id,
                                "status": f"failed: {exc}", "in_trade": None,
                                "position": None, "last_decision": None,
                                "kill_switch": None}
    if not arms_out:
        errors.append("no active SPY arms resolved from accounts.json")
    n_in_trade = sum(1 for a in arms_out.values() if a.get("in_trade"))
    return {
        "schema_version": SCHEMA_VERSION,
        "written_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "market_state": "RTH",
        "spy": {"last": spy_last, "source": "sight-beacon.json",
                "beacon_ts": beacon.get("ts_et") or beacon.get("checked_at_et")},
        "in_trade_count": n_in_trade,
        "arms": arms_out,
        "theta_clock": read_theta_link(),
        "errors": errors,
    }


def closed_payload(now_et: dt.datetime) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "written_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "market_state": "CLOSED",
        "note": ("market closed -- watcher idle; last RTH snapshot was replaced by this "
                 "single CLOSED marker (no per-minute churn while closed)"),
        "in_trade_count": 0,
        "arms": {},
        "theta_clock": read_theta_link(),
        "errors": [],
    }


# --------------------------------------------------------------------------- #
# brief renderer (Discord / firm-brief use)
# --------------------------------------------------------------------------- #
def render_brief(snap: Optional[dict]) -> str:
    if not isinstance(snap, dict):
        return "LIVE WATCH: no snapshot yet (live-watch.json absent)"
    ts = str(snap.get("written_at_et") or "?")[11:16]
    if snap.get("market_state") == "CLOSED":
        return f"LIVE WATCH {ts} ET: market CLOSED, all quiet"
    spy = (snap.get("spy") or {}).get("last")
    head = f"LIVE WATCH {ts} ET [RTH] SPY {spy if spy is not None else '?'} | in-trade: {snap.get('in_trade_count', '?')}"
    lines = [head]
    for arm_id, a in (snap.get("arms") or {}).items():
        name = str(a.get("display_name") or arm_id)
        dec = a.get("last_decision") or {}
        ks = a.get("kill_switch") or {}
        ks_s = "KS:TRIPPED" if ks.get("tripped") else "KS:ok"
        pos = a.get("position")
        pos = pos[0] if isinstance(pos, list) and pos else pos
        if isinstance(pos, dict):
            seg = (f"IN TRADE {pos.get('symbol')} x{pos.get('qty')} "
                   f"@{pos.get('entry_premium')} mid {pos.get('mid')} "
                   f"({_fmt_pct(pos.get('unrealized_pnl_pct'))} / {_fmt_usd(pos.get('unrealized_pnl_usd'))}) | "
                   f"stop {pos.get('stop_premium')} ({_fmt_pct(pos.get('dist_to_stop_pct'))} away, {pos.get('stop_mode')}) | "
                   f"{pos.get('tp_phase')} {pos.get('tp_target_premium')} ({_fmt_pct(pos.get('dist_to_tp_pct'))} away) | "
                   f"HWM {pos.get('hwm_premium')} | "
                   f"{pos.get('time_in_trade_min') if pos.get('time_in_trade_min') is not None else '?'}m in")
        else:
            age = dec.get("age_min")
            seg = (f"FLAT | last: {dec.get('verdict', '?')} "
                   f"({str(dec.get('reason') or '')[:60]}) "
                   f"{f'{age:.0f}m ago' if isinstance(age, (int, float)) else '?'}")
        stat = a.get("status") or "ok"
        stat_s = "" if stat == "ok" else f" [{str(stat)[:48]}]"
        lines.append(f"{arm_id:8} {name:20}: {seg} | {ks_s}{stat_s}")
    th = snap.get("theta_clock")
    if isinstance(th, dict):
        lines.append(f"theta: {th.get('n_positions', '?')} pos @{str(th.get('ts_et') or '?')[11:16]}")
    return "\n".join(lines)


def _fmt_pct(v: Any) -> str:
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else "?%"


def _fmt_usd(v: Any) -> str:
    return f"${v:+.0f}" if isinstance(v, (int, float)) else "$?"


# --------------------------------------------------------------------------- #
# synthetic dry-run (weekend-runnable capability proof; guards call the same parts)
# --------------------------------------------------------------------------- #
def synthetic_fixture() -> tuple[dict, dict, Broker]:
    """A fake arm + creds + Broker stub that behaves like one open structure-mode call."""
    arm = {"id": "safe-2", "display_name": "CORE-SAFE (KIQE)",
           "execution": "mcp_heartbeat", "status": "active",
           "instrument": "SPY_0DTE_OPTION"}
    pos = {"symbol": "SPY260801C00747000", "qty": "5", "avg_entry_price": "0.62",
           "current_price": "0.70", "unrealized_pl": "40.0", "unrealized_plpc": "0.129"}
    broker = Broker(
        positions=lambda creds: [pos],
        option_mid=lambda creds, sym: 0.71,
        # 13:52 UTC = 09:52 ET on 2026-08-03 (EDT, offset -4) -> 23m before the fake now
        entry_fill_utc=lambda creds, sym: "2026-08-03T13:52:00.123456789Z",
    )
    return arm, {"key": "SYNTH", "secret": "SYNTH", "base_url": "synthetic"}, broker


SYNTHETIC_EXIT_REC = {
    "symbol": "SPY260801C00747000", "side": "C", "entry_premium": 0.62,
    "total_qty": 5, "tp1_qty": 4, "runner_qty": 1,
    "premium_stop_pct": -0.50, "tp1_premium_pct": 0.30,
    "profit_lock_mode": "trailing", "runner_target_pct": 2.5, "trail_pct": 0.15,
    "profit_lock_arm_pct": 0.05, "tp1_filled": False,
    "runner_stop_premium": 0.31, "hwm_premium": 0.74, "profit_lock_armed": True,
    "strategy": "ribbon_ride", "stop_mode": "structure", "trigger_level": 746.09,
    "catastrophe_stop_pct": -0.50, "profit_lock_arm_scope": "post_tp1",
}


def run_dry_run_synthetic() -> int:
    """Assemble ONE synthetic arm through the real path and prove every field populates."""
    now_et = dt.datetime(2026, 8, 3, 10, 15, 0)  # a Monday, mid-RTH
    arm, creds, broker = synthetic_fixture()
    view = build_position_view(
        pos_raw=broker.positions(creds)[0], exit_rec=SYNTHETIC_EXIT_REC,
        mid=0.71, mid_source="option_quote_mid", spy_last=746.79,
        entry_time_et="2026-08-03T09:52:00", now_et=now_et)
    missing = [k for k in REQUIRED_POSITION_FIELDS if view.get(k) is None]
    print("=== live_watch --dry-run-synthetic ===")
    for k in REQUIRED_POSITION_FIELDS:
        print(f"  {'OK  ' if view.get(k) is not None else 'MISS'} {k} = {view.get(k)}")
    arm_entry = assemble_arm(arm=arm, creds=creds, broker=broker, spy_last=746.79,
                             now_et=now_et, core_lines=_tail_lines(CORE_DECISIONS_PATH),
                             prev_arm=None,
                             exit_state_override={SYNTHETIC_EXIT_REC["symbol"]:
                                                  SYNTHETIC_EXIT_REC})
    pos_from_assembly = arm_entry.get("position")
    missing_asm = ([] if isinstance(pos_from_assembly, dict) else ["position"]) + [
        k for k in REQUIRED_POSITION_FIELDS
        if isinstance(pos_from_assembly, dict) and pos_from_assembly.get(k) is None]
    snap = {
        "schema_version": SCHEMA_VERSION, "_synthetic": True,
        "written_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "market_state": "RTH",
        "spy": {"last": 746.79, "source": "synthetic"},
        "in_trade_count": 1 if arm_entry.get("in_trade") else 0,
        "arms": {arm["id"]: arm_entry}, "theta_clock": read_theta_link(), "errors": [],
    }
    _atomic_write_json(DRYRUN_OUT_PATH, snap)
    print(f"\nwrote {DRYRUN_OUT_PATH} (production live-watch.json untouched)")
    print("\n--- brief render of the synthetic snapshot ---")
    print(render_brief(snap))
    if missing or missing_asm:
        print(f"\nDRY-RUN FAIL: direct-view misses={missing} assembly-path misses={missing_asm}")
        return 2
    print(f"\nDRY-RUN PASS: all {len(REQUIRED_POSITION_FIELDS)} required fields populated "
          "on BOTH the direct view and the full assemble_arm path")
    return 0


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run_once(force_open: bool = False) -> int:
    """One production tick. Always exits 0 (fail-open); the OUTPUT carries the truth."""
    try:
        from et_clock import et_now
        now_et = et_now()
    except Exception:  # noqa: BLE001
        now_et = dt.datetime.utcnow() + dt.timedelta(hours=-4)
    state = "RTH" if force_open else market_state_for(now_et)
    prev = _read_json(OUT_PATH)

    if state == "CLOSED":
        if isinstance(prev, dict) and prev.get("market_state") == "CLOSED":
            print(f"[live_watch] {now_et:%H:%M} ET closed; snapshot already CLOSED -- no write")
            return 0
        try:
            _atomic_write_json(OUT_PATH, closed_payload(now_et))
            print(f"[live_watch] {now_et:%H:%M} ET closed; wrote single CLOSED marker")
        except Exception as exc:  # noqa: BLE001
            print(f"[live_watch] CLOSED write failed: {exc}")
        return 0

    creds_by_arm: dict = {}
    try:
        import fleet_broker as fb
        creds_by_arm = fb.load_creds()
    except Exception as exc:  # noqa: BLE001
        print(f"[live_watch] load_creds failed ({exc}); arms will degrade")
    try:
        broker = _live_broker()
    except Exception as exc:  # noqa: BLE001
        print(f"[live_watch] broker unavailable ({exc}); writing degraded snapshot")
        broker = Broker(positions=lambda c: [], option_mid=lambda c, s: None,
                        entry_fill_utc=lambda c, s: None)
    try:
        snap = build_snapshot(now_et=now_et, broker=broker, creds_by_arm=creds_by_arm,
                              accounts=_read_json(ACCOUNTS_PATH), prev=prev)
        _atomic_write_json(OUT_PATH, snap)
        print(f"[live_watch] {now_et:%H:%M} ET RTH snapshot written "
              f"(in_trade={snap['in_trade_count']}, arms={len(snap['arms'])}, "
              f"errors={len(snap['errors'])})")
    except Exception as exc:  # noqa: BLE001
        # last-ditch: never leave the surface silently stale without a signal
        try:
            _atomic_write_json(OUT_PATH, {
                "schema_version": SCHEMA_VERSION,
                "written_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
                "market_state": "RTH", "arms": {}, "in_trade_count": 0,
                "errors": [f"snapshot build failed: {exc}"]})
        except Exception:  # noqa: BLE001
            pass
        print(f"[live_watch] snapshot build failed: {exc}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="WS7 live-watch canonical state surface")
    ap.add_argument("--brief", action="store_true",
                    help="print the compact per-arm text block from the last snapshot")
    ap.add_argument("--dry-run-synthetic", action="store_true",
                    help="prove every field populates with an injected synthetic position")
    ap.add_argument("--force-open", action="store_true",
                    help="treat the market as open (testing aid)")
    args = ap.parse_args(argv)
    if args.dry_run_synthetic:
        return run_dry_run_synthetic()
    if args.brief:
        print(render_brief(_read_json(OUT_PATH)))
        return 0
    return run_once(force_open=args.force_open)


if __name__ == "__main__":
    raise SystemExit(main())
