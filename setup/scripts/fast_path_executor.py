"""fast_path_executor -- pure-Python sub-30s alert-to-decision pipeline.

Per markdown/specs/2-MIN-CADENCE-ARCHITECTURE.md + J's directive "under 30s end-to-end".

The LLM heartbeat takes 60-90s per tick (MCP roundtrips + Haiku inference).
For high-conviction numeric alerts, this script bypasses the LLM and makes a
trade decision in pure Python from cached state + REST APIs. Wall time target:
<5s. Combined with 30s L2 cadence, end-to-end (bar close -> decision) is <35s
worst case, <5s best case (if alert lands right after a pulse fire).

OPERATING MODES (per OP-25 ENGINE-BENEFIT AUTONOMY + Rule 9):
  - observer  (default): writes decision to fast-path-decisions.jsonl, does NOT
              place orders. Safe under OP-25 — observation infrastructure only.
              Production-ready as soon as latency is validated <30s.
  - live      (BLOCKED until J ratification): also places bracket orders via
              Alpaca REST. Requires explicit `--mode live` AND a sentinel file
              `automation/state/fast-path-live-enabled.flag` to exist.

This script is INVOKED via:
  1. Manual: `python setup/scripts/fast_path_executor.py --alert-file path.json`
  2. Embedded in numeric_pulse.py after alerts are written (parallel to the
     existing LLM heartbeat trigger).

CLI:
  python setup/scripts/fast_path_executor.py --account safe   # consume latest alert
  python setup/scripts/fast_path_executor.py --account bold --mode observer
  python setup/scripts/fast_path_executor.py --benchmark      # measure latency
  python setup/scripts/fast_path_executor.py --self-test      # synthetic alert
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from et_clock import ET_TZ  # noqa: E402 — DST-aware ET (TZ-SYSTEMIC fix: was timezone(timedelta(hours=-4)))
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Keys are loaded at runtime from .mcp.json (gitignored) — never hardcode here.
_MCP_JSON = PROJECT_ROOT / ".mcp.json"
_SERVER_MAP = {"safe": "alpaca", "bold": "alpaca_aggressive"}


def _load_account_keys() -> dict[str, tuple[str, str]]:
    """Read Alpaca key/secret pairs from the gitignored .mcp.json."""
    try:
        mcp = json.loads(_MCP_JSON.read_text(encoding="utf-8"))
        out: dict[str, tuple[str, str]] = {}
        for alias, server in _SERVER_MAP.items():
            env = mcp["mcpServers"][server]["env"]
            out[alias] = (env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"])
        return out
    except Exception as exc:
        raise RuntimeError(
            f"Cannot load Alpaca keys from {_MCP_JSON}: {exc}\n"
            "Copy .mcp.json.example → .mcp.json and fill in your credentials."
        ) from exc


ACCOUNT_KEYS: dict[str, tuple[str, str]] = _load_account_keys()
ALPACA_BASE = "https://paper-api.alpaca.markets/v2"

DecisionT = Literal[
    "HOLD", "ENTER_BULL", "ENTER_BEAR",
    "SKIP_RTH", "SKIP_VIX", "SKIP_SETUP", "SKIP_LOCK", "SKIP_KILL",
    "SKIP_NO_ALERT", "SKIP_SIZING", "ERROR",
]


@dataclass
class Decision:
    decision: DecisionT
    reason: str
    account: str
    alert_pattern: str | None = None
    alert_bias: str | None = None
    proposed_strike: int | None = None
    proposed_qty: int | None = None
    proposed_premium: float | None = None
    proposed_stop_premium: float | None = None
    proposed_tp1_premium: float | None = None
    filter_results: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    mode: str = "observer"
    placed: bool = False
    bracket_order_id: str | None = None
    placement_error: str | None = None


def _alpaca(endpoint: str, account: str, method: str = "GET",
            data: dict | None = None, timeout: int = 5) -> Any:
    """Lightweight Alpaca REST client. Timeout=5s to keep budget under 30s."""
    key, secret = ACCOUNT_KEYS[account]
    url = f"{ALPACA_BASE}/{endpoint.lstrip('/')}"
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"raw": str(e)}
        return {"_error": str(e), "_status": e.code, "_body": err_body}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"_error": str(e)}


def _is_rth_now() -> bool:
    now_et = datetime.now(ET_TZ)
    if now_et.weekday() >= 5:
        return False
    return dtime(9, 30) <= now_et.time() < dtime(16, 0)


def _is_in_entry_window(params: dict) -> bool:
    """Check entry window from params (default 09:35 - 15:00)."""
    now_et = datetime.now(ET_TZ).time()
    no_before = params.get("entry_no_trade_before_et", "09:35")
    no_after = params.get("entry_no_trade_after_et", "15:00")

    def _parse(s: str) -> dtime:
        h, m = s.split(":")
        return dtime(int(h), int(m))

    return _parse(no_before) <= now_et < _parse(no_after)


def _load_params(account: str) -> dict:
    """Load params_{account}.json + merge over params.json."""
    base = PROJECT_ROOT / "automation" / "state" / "params.json"
    acct = PROJECT_ROOT / "automation" / "state" / f"params_{account}.json"
    merged: dict = {}
    if base.exists():
        try:
            merged = json.loads(base.read_text())
        except (json.JSONDecodeError, OSError):
            merged = {}
    if acct.exists():
        try:
            override = json.loads(acct.read_text())
            merged.update(override)
        except (json.JSONDecodeError, OSError):
            pass
    return merged


def _load_position_state(account: str) -> dict:
    p = PROJECT_ROOT / "automation" / "state" / f"current-position-{account}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _load_loop_state() -> dict:
    p = PROJECT_ROOT / "automation" / "state" / "loop-state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _read_latest_alert(window_sec: int = 60) -> dict | None:
    """Read newest unconsumed alert from numeric-alert.jsonl within window."""
    p = PROJECT_ROOT / "automation" / "state" / "numeric-alert.jsonl"
    if not p.exists():
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_sec)
    latest: dict | None = None
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                fired = datetime.fromisoformat(rec.get("fire_at_utc", ""))
            except ValueError:
                continue
            if fired >= cutoff:
                latest = rec  # last wins (JSONL is append-only chronological)
    return latest


def _fetch_vix_quick() -> dict | None:
    """Fast VIX fetch. Returns {value, direction} or None on failure.
    Targets <2s wall time."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.download("^VIX", interval="5m", period="1d",
                         auto_adjust=False, progress=False, threads=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    closes = df["Close"].dropna().tolist()
    if len(closes) < 2:
        return None
    latest = float(closes[-1])
    prior = float(closes[-2])
    delta = latest - prior
    direction = "rising" if delta > 0.05 else ("falling" if delta < -0.05 else "flat")
    return {"value": round(latest, 2), "direction": direction,
            "prior": round(prior, 2), "delta": round(delta, 2)}


def _compute_filter_rth(decision: Decision, params: dict) -> bool:
    if not _is_rth_now():
        decision.decision = "SKIP_RTH"
        decision.reason = "outside RTH"
        decision.filter_results["rth"] = False
        return False
    if not _is_in_entry_window(params):
        decision.decision = "SKIP_RTH"
        decision.reason = f"outside entry window {params.get('entry_no_trade_before_et')}–{params.get('entry_no_trade_after_et')}"
        decision.filter_results["entry_window"] = False
        return False
    decision.filter_results["rth"] = True
    decision.filter_results["entry_window"] = True
    return True


def _compute_filter_vix(decision: Decision, params: dict, bias: str,
                         vix_data: dict | None) -> bool:
    if vix_data is None:
        # Conservative default: block on VIX uncertainty
        decision.decision = "SKIP_VIX"
        decision.reason = "VIX data unavailable"
        decision.filter_results["vix"] = "unavailable"
        return False

    decision.filter_results["vix_value"] = vix_data["value"]
    decision.filter_results["vix_direction"] = vix_data["direction"]

    thresholds = params.get("vix_entry_thresholds", {})
    bull_max = thresholds.get("bull_max_exclusive_or_falling", 17.20)
    bear_min = thresholds.get("bear_min_exclusive_and_rising", 17.30)
    bull_hard_cap = thresholds.get("bull_hard_cap", 22.00)

    if bias == "bullish":
        # Bull eligible if VIX < bull_max OR VIX is falling; never if > hard_cap
        if vix_data["value"] > bull_hard_cap:
            decision.decision = "SKIP_VIX"
            decision.reason = f"VIX {vix_data['value']} > bull_hard_cap {bull_hard_cap}"
            return False
        if vix_data["value"] < bull_max or vix_data["direction"] == "falling":
            decision.filter_results["vix"] = "pass_bull"
            return True
        decision.decision = "SKIP_VIX"
        decision.reason = f"VIX {vix_data['value']} {vix_data['direction']} blocks bull (need <{bull_max} or falling)"
        return False
    elif bias == "bearish":
        # Bear eligible if VIX > bear_min AND rising
        if vix_data["value"] > bear_min and vix_data["direction"] == "rising":
            decision.filter_results["vix"] = "pass_bear"
            return True
        decision.decision = "SKIP_VIX"
        decision.reason = f"VIX {vix_data['value']} {vix_data['direction']} blocks bear (need >{bear_min} AND rising)"
        return False
    decision.filter_results["vix"] = "neutral_bias_passes"
    return True


def _compute_filter_setup_allowed(decision: Decision, params: dict,
                                    alert_pattern: str) -> bool:
    """Verify the alert pattern is in the account's allowed setup list."""
    allowed = params.get("setups_allowed", [])
    # Map pattern names to setup archetypes (heartbeat's vocab)
    pattern_to_setup = {
        "failed_breakdown_wick": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "double_bottom": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "rejection_at_level_bearish": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "double_top": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "head_and_shoulders_top": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "momentum_acceleration": None,  # bias-dependent, not a setup
    }
    setup = pattern_to_setup.get(alert_pattern.split("::")[0])  # strip ::contra_regime
    # "ALL" sentinel = accept any mapped setup (Bold profile)
    if "ALL" in allowed:
        if setup is None:
            decision.decision = "SKIP_SETUP"
            decision.reason = f"pattern '{alert_pattern}' has no setup-archetype mapping"
            decision.filter_results["setup"] = False
            return False
        decision.filter_results["setup"] = f"{setup}_via_ALL"
        return True
    if setup is None or setup not in allowed:
        decision.decision = "SKIP_SETUP"
        decision.reason = f"pattern '{alert_pattern}' not in setups_allowed={allowed}"
        decision.filter_results["setup"] = False
        return False
    decision.filter_results["setup"] = setup
    return True


def _compute_filter_first_entry_lock(decision: Decision, alert_pattern: str) -> bool:
    """Check if today's first-entry-after-stop lock blocks this setup."""
    state = _load_loop_state()
    locks = state.get("first_entry_lock", [])
    if not isinstance(locks, list):
        decision.filter_results["first_entry_lock"] = "pass_no_locks"
        return True

    pattern_to_setup = {
        "failed_breakdown_wick": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "double_bottom": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
        "rejection_at_level_bearish": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "double_top": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "head_and_shoulders_top": "BEARISH_REJECTION_RIDE_THE_RIBBON",
    }
    setup_for_alert = pattern_to_setup.get(alert_pattern.split("::")[0])
    today_str = datetime.now(ET_TZ).date().isoformat()

    for lock in locks:
        if not isinstance(lock, dict):
            continue
        if lock.get("setup_name") != setup_for_alert:
            continue
        exit_at = lock.get("exited_at_et", "")
        if not exit_at.startswith(today_str):
            continue
        exit_reason = lock.get("exit_reason", "")
        if exit_reason in ("premium_stop", "chart_stop", "ribbon_flip_back", "stop_market"):
            decision.decision = "SKIP_LOCK"
            decision.reason = (
                f"first_entry_after_stop_blocked — prior {setup_for_alert} "
                f"exited at {exit_at} via {exit_reason}"
            )
            decision.filter_results["first_entry_lock"] = "blocked"
            return False
    decision.filter_results["first_entry_lock"] = "pass"
    return True


def _has_active_position(account: str) -> tuple[bool, dict | None]:
    """Check both the local state file AND Alpaca REST for an active position.

    Returns (has_position, position_info). Looking in two places defends against:
      - Stale state file (LLM heartbeat hasn't written yet)
      - Stale Alpaca (we placed an order seconds ago, hasn't filled yet)
    """
    # 1. Local state file
    pos_state = _load_position_state(account)
    if pos_state.get("status") in ("open", "pending_fill"):
        return True, pos_state

    # 2. Alpaca REST: any open option positions?
    positions = _alpaca("positions", account)
    if isinstance(positions, list):
        spy_options = [p for p in positions
                       if isinstance(p, dict) and p.get("symbol", "").startswith("SPY")
                       and abs(int(float(p.get("qty", 0)))) > 0]
        if spy_options:
            return True, {"source": "alpaca_rest", "positions": spy_options}

    # 3. Alpaca REST: any pending bracket parent orders for SPY options?
    orders = _alpaca("orders?status=open&nested=true&limit=50", account)
    if isinstance(orders, list):
        spy_orders = [o for o in orders
                      if isinstance(o, dict)
                      and o.get("symbol", "").startswith("SPY")
                      and o.get("side") == "buy"
                      and o.get("status") in ("new", "accepted", "pending_new", "partially_filled")]
        if spy_orders:
            return True, {"source": "alpaca_pending_orders", "orders": spy_orders}

    return False, None


def _recent_fast_path_fire(account: str, lookback_sec: int = 90) -> dict | None:
    """Check if fast_path has placed an ENTER decision for `account` within the
    last `lookback_sec`. Returns the recent decision dict, or None.

    Prevents the "alert fires twice in 30s -> fast_path opens 2 positions" foot-gun
    even if Alpaca hasn't updated positions/orders yet (eventual consistency).
    """
    p = PROJECT_ROOT / "automation" / "state" / "fast-path-decisions.jsonl"
    if not p.exists():
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=lookback_sec)
    last_enter: dict | None = None
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("account") != account:
                continue
            if not str(rec.get("decision", "")).startswith("ENTER"):
                continue
            if not rec.get("placed"):
                continue  # only count actually-placed orders
            try:
                ts = datetime.fromisoformat(rec.get("decided_at_utc", ""))
            except ValueError:
                continue
            if ts >= cutoff:
                last_enter = rec  # last in file wins
    return last_enter


def _compute_filter_no_concurrent_position(decision: Decision, account: str) -> bool:
    """Block entry if account has an active position, pending order, OR
    fast-path placed an ENTER within the last 90s.

    Per Rule 6 + J's 2026-05-18 ratification chat: "we shouldn't be hedging
    our bets or doing anything ... we should make sure we have stuff like
    that wired in." One trade at a time per account.
    """
    has_pos, pos_info = _has_active_position(account)
    if has_pos:
        decision.decision = "SKIP_LOCK"
        decision.reason = f"concurrent position blocked: {pos_info}"
        decision.filter_results["concurrent_position"] = "blocked"
        return False

    recent = _recent_fast_path_fire(account, lookback_sec=90)
    if recent is not None:
        decision.decision = "SKIP_LOCK"
        decision.reason = (
            f"recent fast-path fire {recent.get('decided_at_et')} blocks new entry "
            f"(90s cooldown — prevents Alpaca eventual-consistency double-fire)"
        )
        decision.filter_results["concurrent_position"] = "recent_fire_cooldown"
        return False

    decision.filter_results["concurrent_position"] = "pass"
    return True


def _compute_filter_kill_switch(decision: Decision, account: str, params: dict) -> bool:
    """Check daily P&L vs kill-switch threshold."""
    # Fast path: query Alpaca account equity vs start-of-day baseline
    account_info = _alpaca("account", account)
    if isinstance(account_info, dict) and account_info.get("_error"):
        decision.filter_results["kill_switch"] = "skipped_api_error"
        return True  # don't block on API errors; LLM heartbeat will catch
    if not isinstance(account_info, dict):
        decision.filter_results["kill_switch"] = "skipped_bad_resp"
        return True

    try:
        equity = float(account_info.get("equity", 0))
        last_equity = float(account_info.get("last_equity", equity))  # yesterday close
    except (TypeError, ValueError):
        decision.filter_results["kill_switch"] = "skipped_parse_error"
        return True

    if last_equity <= 0:
        decision.filter_results["kill_switch"] = "skipped_zero_baseline"
        return True

    pnl_pct = (equity - last_equity) / last_equity
    kill_threshold = -abs(params.get("daily_loss_kill_switch_pct", 0.30))

    decision.filter_results["pnl_pct_today"] = round(pnl_pct, 4)
    decision.filter_results["kill_threshold"] = kill_threshold
    decision.filter_results["equity"] = round(equity, 2)

    if pnl_pct <= kill_threshold:
        decision.decision = "SKIP_KILL"
        decision.reason = f"daily kill-switch hit ({pnl_pct:.1%} vs {kill_threshold:.0%} threshold)"
        return False
    decision.filter_results["kill_switch"] = "pass"
    return True


def _compute_sizing(decision: Decision, account: str, params: dict,
                     spy_close: float, bias: str) -> bool:
    """Pure-Python sizing math. Picks strike + qty."""
    account_info = _alpaca("account", account)
    if not isinstance(account_info, dict) or account_info.get("_error"):
        decision.decision = "SKIP_SIZING"
        decision.reason = f"account fetch failed: {account_info.get('_error') if isinstance(account_info, dict) else 'no response'}"
        return False
    try:
        equity = float(account_info.get("equity", 0))
        buying_power = float(account_info.get("buying_power", 0))
    except (TypeError, ValueError):
        decision.decision = "SKIP_SIZING"
        decision.reason = "account equity parse failed"
        return False

    # Strike offset per tier
    tiers = params.get("v15_strike_offset_per_tier", [])
    strike_offset = 0
    for t in tiers:
        if t.get("equity_min", 0) <= equity < t.get("equity_max", 999999999):
            strike_offset = int(t.get("strike_offset", 0))
            break

    # Convert SPY close + offset to strike
    base_strike = round(spy_close)
    if bias == "bullish":
        # Calls: OTM = above price. Offset is "how far OTM"
        strike = base_strike + strike_offset
    else:
        # Puts: OTM = below price.
        strike = base_strike - strike_offset

    # Sizing: per_trade_risk_cap_pct of equity
    risk_cap_pct = params.get("per_trade_risk_cap_pct", 0.30)
    max_capital = equity * risk_cap_pct

    # Assume ~$1.00 premium baseline (will refine at order placement time)
    # Per-contract cost = premium * 100
    assumed_premium = 1.00
    max_contracts = int(max_capital / (assumed_premium * 100))
    min_contracts = 3  # rule 6
    qty = max(min_contracts, min(max_contracts, 5))  # cap at 5 for $1K tier

    decision.proposed_strike = strike
    decision.proposed_qty = qty
    decision.proposed_premium = assumed_premium
    decision.filter_results["equity"] = round(equity, 2)
    decision.filter_results["strike_offset"] = strike_offset
    decision.filter_results["buying_power"] = round(buying_power, 2)
    decision.filter_results["max_capital_per_trade"] = round(max_capital, 2)
    return True


def evaluate_alert(account: str, alert: dict, *, vix_data: dict | None = None) -> Decision:
    """The hot path: decide given an alert. Pure-Python. Target <5s wall time."""
    started = time.monotonic()
    decision = Decision(
        decision="HOLD",
        reason="",
        account=account,
        alert_pattern=alert.get("pattern"),
        alert_bias=alert.get("bias"),
    )

    if not alert:
        decision.decision = "SKIP_NO_ALERT"
        decision.reason = "no alert in window"
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    bias = alert.get("bias", "neutral")
    spy_close = float(alert.get("spy_close", 0))
    pattern = alert.get("pattern", "")

    params = _load_params(account)

    # FILTER PIPELINE (numeric subset of the 11-filter heartbeat rubric)
    if not _compute_filter_rth(decision, params):
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    if vix_data is None:
        vix_data = _fetch_vix_quick()

    if not _compute_filter_vix(decision, params, bias, vix_data):
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    if not _compute_filter_setup_allowed(decision, params, pattern):
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    if not _compute_filter_first_entry_lock(decision, pattern):
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    # CRITICAL safeguard (J 2026-05-18 chat): "one trade at a time per account,
    # no hedging." Checks local state + Alpaca positions + pending orders +
    # recent-fast-path-fire (Alpaca eventual-consistency window).
    if not _compute_filter_no_concurrent_position(decision, account):
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    if not _compute_filter_kill_switch(decision, account, params):
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    if not _compute_sizing(decision, account, params, spy_close, bias):
        decision.elapsed_ms = int((time.monotonic() - started) * 1000)
        return decision

    # All filters passed
    decision.decision = "ENTER_BULL" if bias == "bullish" else "ENTER_BEAR"
    decision.reason = (
        f"alert={pattern} conf={alert.get('confidence')} all filters passed"
    )

    # Compute stop + tp1 premiums
    if bias == "bullish":
        stop_pct = params.get("premium_stop_pct_bull", -0.08)
    else:
        stop_pct = params.get("premium_stop_pct_bear", -0.20)
    tp1_pct = params.get("tp1_premium_pct", 0.30)
    decision.proposed_stop_premium = round(
        decision.proposed_premium * (1 + stop_pct), 2
    )
    decision.proposed_tp1_premium = round(
        decision.proposed_premium * (1 + tp1_pct), 2
    )
    decision.elapsed_ms = int((time.monotonic() - started) * 1000)
    return decision


def _persist_decision(decision: Decision) -> Path:
    """Append decision to fast-path-decisions.jsonl."""
    today = datetime.now(ET_TZ).date().isoformat()
    state_dir = PROJECT_ROOT / "automation" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out = state_dir / "fast-path-decisions.jsonl"
    record = {
        "decided_at_utc": datetime.now(timezone.utc).isoformat(),
        "decided_at_et": datetime.now(ET_TZ).isoformat(),
        **decision.__dict__,
    }
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return out


def _live_enabled() -> bool:
    """Live-trade gate: requires explicit sentinel file (J's ratification)."""
    sentinel = PROJECT_ROOT / "automation" / "state" / "fast-path-live-enabled.flag"
    return sentinel.exists()


# Safety: max N live bracket placements per account per trading day.
# Prevents runaway / oscillation. v1: 3 fires/account/day. Tune after observation.
LIVE_DAILY_FIRE_CAP = 3
LIVE_FIRE_COUNTER_FILE = (
    PROJECT_ROOT / "automation" / "state" / "fast-path-live-fires.json"
)


def _live_fires_today(account: str) -> int:
    """Count live placements for this account today. State persisted on disk."""
    today = datetime.now(ET_TZ).date().isoformat()
    if not LIVE_FIRE_COUNTER_FILE.exists():
        return 0
    try:
        state = json.loads(LIVE_FIRE_COUNTER_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    return state.get(today, {}).get(account, 0)


def _bump_live_fires(account: str) -> int:
    """Atomically increment the live-fire counter for today. Returns new count."""
    today = datetime.now(ET_TZ).date().isoformat()
    LIVE_FIRE_COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {}
    if LIVE_FIRE_COUNTER_FILE.exists():
        try:
            state = json.loads(LIVE_FIRE_COUNTER_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}
    day_state = state.setdefault(today, {})
    day_state[account] = day_state.get(account, 0) + 1
    LIVE_FIRE_COUNTER_FILE.write_text(json.dumps(state, indent=2))
    return day_state[account]


def _resolve_option_symbol(account: str, strike: int, bias: str) -> str | None:
    """Find today's 0DTE SPY option contract symbol matching strike + direction.

    Returns OPRA symbol (e.g. SPY260518C00740000) or None on miss.
    """
    today = datetime.now(ET_TZ).strftime("%y%m%d")
    side = "C" if bias == "bullish" else "P"
    return f"SPY{today}{side}{strike * 1000:08d}"


def _place_live_bracket(
    account: str,
    decision: "Decision",
) -> tuple[bool, str | None, str | None]:
    """Place a real Alpaca paper bracket order. Returns (success, order_id, error).

    Per heartbeat.md doctrine: bracket order with parent limit @ mid, take_profit
    leg at +30% (Safe) / +75% (Bold) premium, stop_loss leg at -8% premium.

    Safety gates applied here:
      - Live-enable sentinel must exist (checked at caller)
      - Daily fire cap (LIVE_DAILY_FIRE_CAP) per account
      - Decision must be ENTER_BULL or ENTER_BEAR
      - All proposed prices must be set
    """
    if not decision.decision.startswith("ENTER"):
        return False, None, f"decision was {decision.decision}, not ENTER"
    if not all([decision.proposed_strike, decision.proposed_qty,
                decision.proposed_premium, decision.proposed_stop_premium,
                decision.proposed_tp1_premium]):
        return False, None, "missing required price/qty fields"

    # Daily fire cap
    fires_today = _live_fires_today(account)
    if fires_today >= LIVE_DAILY_FIRE_CAP:
        return False, None, f"daily fire cap {LIVE_DAILY_FIRE_CAP} hit (fired {fires_today} today)"

    symbol = _resolve_option_symbol(account, decision.proposed_strike,
                                      decision.alert_bias or "bullish")
    if symbol is None:
        return False, None, "could not resolve option symbol"

    # Build bracket order request
    # Note: Alpaca paper options API uses "order_class=bracket" with
    # take_profit + stop_loss legs. parent type=limit, side=buy.
    payload = {
        "symbol": symbol,
        "qty": str(decision.proposed_qty),
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": str(decision.proposed_premium),
        "order_class": "bracket",
        "take_profit": {"limit_price": str(decision.proposed_tp1_premium)},
        "stop_loss": {"stop_price": str(decision.proposed_stop_premium)},
    }
    resp = _alpaca("orders", account, method="POST", data=payload, timeout=10)
    if isinstance(resp, dict) and resp.get("_error"):
        err = resp.get("_body", {}).get("message", resp.get("_error"))
        return False, None, f"Alpaca rejected: {err}"
    order_id = resp.get("id") if isinstance(resp, dict) else None
    if order_id:
        _bump_live_fires(account)
        return True, order_id, None
    return False, None, "no order_id in response"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", choices=["safe", "bold", "both"], default="both")
    parser.add_argument("--mode", choices=["observer", "live"], default="observer")
    parser.add_argument("--alert-window-sec", type=int, default=60)
    parser.add_argument("--benchmark", action="store_true",
                        help="Run synthetic alert to measure latency, exit")
    parser.add_argument("--self-test", action="store_true",
                        help="Print test-mode synthetic alert decision")
    parser.add_argument("--silent", action="store_true")
    args = parser.parse_args()

    if args.benchmark or args.self_test:
        # Synthetic alert for testing
        synthetic_alert = {
            "fire_at_utc": datetime.now(timezone.utc).isoformat(),
            "pattern": "failed_breakdown_wick::contra_regime",
            "bias": "bullish",
            "confidence": 0.75,
            "key_price": 735.0,
            "spy_close": 735.40,
            "level_distance_dollars": 0.10,
            "level_name": "PML",
        }
        started = time.monotonic()
        results = []
        for a in (["safe", "bold"] if args.account == "both" else [args.account]):
            d = evaluate_alert(a, synthetic_alert)
            d.mode = args.mode
            results.append(d)
        total_ms = int((time.monotonic() - started) * 1000)
        for d in results:
            print(f"{d.account}: {d.decision} ({d.elapsed_ms}ms) — {d.reason}")
            if not args.silent:
                print(f"  filters: {d.filter_results}")
        print(f"TOTAL wall time (both accounts, synthetic): {total_ms}ms "
              f"({'PASS' if total_ms < 30000 else 'FAIL'} <30s target)")
        return 0

    # Real run: read latest alert, evaluate, persist
    alert = _read_latest_alert(window_sec=args.alert_window_sec)
    if alert is None:
        if not args.silent:
            print(f"No alert in last {args.alert_window_sec}s — exiting")
        return 0

    # Fetch VIX once for both accounts (saves ~1.5s)
    vix_data = _fetch_vix_quick()

    targets = ["safe", "bold"] if args.account == "both" else [args.account]
    decisions = []
    for a in targets:
        d = evaluate_alert(a, alert, vix_data=vix_data)
        d.mode = args.mode
        # LIVE MODE: only place if sentinel exists + mode=live + decision is ENTER_*
        # Defense in depth: 3 conditions all required.
        if args.mode == "live" and _live_enabled() and d.decision.startswith("ENTER"):
            success, order_id, err = _place_live_bracket(a, d)
            d.placed = success
            d.bracket_order_id = order_id
            d.placement_error = err
        decisions.append(d)
        _persist_decision(d)

    if not args.silent:
        for d in decisions:
            print(f"{d.account}: {d.decision} ({d.elapsed_ms}ms) — {d.reason}")
            if d.proposed_strike:
                print(f"  proposed: strike={d.proposed_strike} qty={d.proposed_qty} "
                      f"premium~${d.proposed_premium} stop=${d.proposed_stop_premium} "
                      f"tp1=${d.proposed_tp1_premium}")
    # Return 1 if any ENTER decision was reached (informational signal)
    any_enter = any(d.decision.startswith("ENTER") for d in decisions)
    return 1 if any_enter else 0


if __name__ == "__main__":
    sys.exit(main())
