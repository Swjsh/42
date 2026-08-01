"""theta_clock.py -- THE THETA COCKPIT: in-trade Greeks visibility instrument.

J's directive (2026-08-01, verbatim): "We can't just be getting in options trades and have
Theta kick our ass without us knowing." VISIBILITY ONLY -- this script never places, closes,
or resizes an order, and never feeds anything back into a gate or exit rule. A THETA-based
EXIT class is explicitly a SEPARATE pre-registered study; nothing here arms one.

WHAT THIS IS: a standalone watcher, run every ~1 min during RTH via its OWN scheduled task
(Gamma_ThetaClock), FULLY OFF the heartbeat hot path (heartbeat_core.py is untouched -- no
network call was added to it). It reads open SPY option positions for every ACTIVE account
(both core mcp_heartbeat arms -- safe-2/bold-2 -- and the fleet_rest arms -- safe-3/risky-1/
risky-3) via `automation/state/fleet/fleet_broker.py` (the SAME credential-loading + REST
module heartbeat_core.py itself already depends on -- read-only calls only: get_positions,
get_option_greeks). For each open position it computes a THETA CLOCK row and appends it to a
daily JSONL + the current-snapshot JSON, and raises ONE loud (never-repeating, never-auto-
acting) STATUS.md line when a position looks like theta is eating a stalled trade.

WHY THE DECOMPOSITION DOES NOT LEAN ON BROKER GREEKS ALONE (empirical finding, this build):
heartbeat_core.py has captured a per-entry greeks snapshot since 2026-07-07 (G8,
`_capture_greeks` / `fleet_broker.get_option_greeks`, POST-placement, log-only, never blocks
a fill) -- but a grep of the real ledger before this build found **29/29 real ENTER rows in
core-decisions.jsonl carry `"greeks": {}`** (empty every single time). The snapshots endpoint
(`/v1beta1/options/snapshots`) that feeds it is explicitly documented as "UNVERIFIED until a
real entry logs greeks" in fleet_broker.py, and apparently still is. This script still
ATTEMPTS the same call every tick (so the day Alpaca's feed actually returns data, it is
captured and labeled `broker_snapshot` with zero code change needed) but the ALERT MECHANISM
and the row's headline numbers do NOT depend on it working: they are computed from data
sources already PROVEN live (the /v2/positions payload itself -- avg_entry_price,
unrealized_plpc, current_price -- and the /v1beta1/options/quotes/latest endpoint, which is
the exact endpoint the live placement path already prices real fills with) plus a
closed-form, PURE, documented ESTIMATE:

  delta_component_est  = intrinsic_now - intrinsic_ref   (MODEL-FREE -- exact intrinsic value
                          from spot/strike/right, no greeks needed at all)
  theta_component_est  = a textbook "0DTE extrinsic value decays roughly like sqrt(time
                          remaining)" heuristic (simplified ATM Black-Scholes approximation),
                          applied to the reference point's own extrinsic value and projected
                          to now's time-to-close. This is what makes the estimate 0DTE-AWARE
                          (theta accelerates intraday) instead of a naive linear
                          theta-per-minute model, which would understate the acceleration.
  residual_est          = whatever is left after removing both modeled components from the
                          REAL premium change -- IV/vega/gamma effects, quote noise, and
                          sqrt-model error all land here rather than being silently folded
                          into delta or theta.

Every one of these is suffixed `_est` and carries a `basis` string. Real broker greeks (when
they DO arrive) are reported alongside, raw, labeled `broker_snapshot`, and preferred for the
`theta_per_contract_per_day` headline figure whenever present. Nothing here is fabricated as
if it were broker truth (C6 / OP-33).

STATE WRITTEN:
  automation/state/theta-clock.json                       -- current snapshot (this tick)
  automation/state/theta-clock/theta-clock-YYYY-MM-DD.jsonl -- append-only daily time series
  automation/state/theta-clock/position-state.json         -- per-position FROZEN first-
                                                                observation entry snapshot +
                                                                alerted flag (immutable once
                                                                written -- see module note on
                                                                the delta_at_entry convention
                                                                below), pruned after
                                                                POSITION_STATE_RETENTION_DAYS.

GO-FORWARD delta_at_entry / iv_at_entry / theta_at_entry CONVENTION (for
fleet_journal_bridge.py, which reads position-state.json as its fallback source): a position's
FIRST theta_clock observation (within ~1 min of fill, since this script runs every minute) is
the entry snapshot. If a real broker greeks snapshot was captured at that first observation,
entry_delta/entry_iv/entry_theta are REAL numbers; if not (the empirically-common case today),
they stay None -- fleet_journal_bridge leaves the corresponding trades.csv cell BLANK rather
than writing a model estimate into a column named as if it were real broker data (a downstream
consumer -- perps leverage calibration -- was cited as blocked on this column meaning real
greeks; fabricating a look-alike number into it would be worse than leaving it blank).

ALERT (THE ONE LOUD LINE, never spammed, never auto-acting): when a position's estimated
theta burn over the last ALERT_WINDOW_MIN minutes exceeds its estimated delta gain over the
same window by more than ALERT_MIN_MARGIN_USD, ONE line is appended to
automation/overnight/STATUS.md's "## Live watch" section (created if absent -- a NEW section,
deliberately NOT "## Known broken": a stalled trade is not a breakage). The position's
`alerted` flag latches permanently once fired -- this position will never alert a second time,
by design (no re-triggering on the same held trade). NEVER closes, resizes, or otherwise acts
on the position.

FAIL-OPEN EVERYWHERE: one account's fetch failure, one position's computation error, or a
totally missing/corrupt state file never stops the rest of the tick, and main() always exits
0. This script writes NO lock/pid file -- Task Scheduler's own `-MultipleInstances IgnoreNew`
setting (see setup/scripts/install-theta-clock.ps1) is the sole overlap guard, so a crashed
run leaves no state that could wedge a future run (J's explicit weekend-limitation requirement).

Guard: backtest/tests/test_theta_clock.py.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, pattern copied from
# setup/guard_runner_slow.py / setup/scripts/firm_brief.py -- adapted to this file's own
# setup/scripts/ depth: parents[2] from here is the repo root, matching firm_brief.py's
# version of this same header, not guard_runner_slow.py's parents[1] (that file lives one
# directory shallower, directly under setup/). Copying the wrong index verbatim would silently
# point the log redirect at the wrong directory -- adapted intentionally, not blindly pasted.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "theta-clock.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "theta-clock.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import math
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("automation/state/fleet", "setup/scripts"):
    _full = str(REPO / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

from et_clock import et_now  # noqa: E402
import fleet_broker as fb  # noqa: E402

STATE = REPO / "automation" / "state"
THETA_DIR = STATE / "theta-clock"
SNAPSHOT_PATH = STATE / "theta-clock.json"
POSITION_STATE_PATH = THETA_DIR / "position-state.json"
ACCOUNTS_JSON = STATE / "fleet" / "accounts.json"
SIGHT_BEACON_PATH = STATE / "sight-beacon.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"

MARKET_CLOSE_ET = dtime(16, 0)
ALERT_WINDOW_MIN = 15          # lookback window for the theta-vs-delta stall check
ALERT_MIN_MARGIN_USD = 5.0     # theta burn must exceed delta gain by this many $ to alert
POSITION_STATE_RETENTION_DAYS = 5
BEACON_MAX_AGE_S = 180
OPTIONS_DATA_HOST = "https://data.alpaca.markets"
QUOTE_TIMEOUT_S = 8

_OCC_RE = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


# --------------------------------------------------------------------------- #
# pure helpers (no I/O -- unit-testable without network/filesystem)
# --------------------------------------------------------------------------- #
def parse_occ_symbol(symbol: str) -> Optional[dict]:
    """OCC option symbol -> {root, expiry (YYYY-MM-DD), right (C/P), strike}. None if
    unparseable. Mirrors fleet_journal_bridge._parse_occ_symbol (kept independent -- small,
    pure, zero-dependency; see that module's own docstring for why this codebase tolerates a
    couple of duplicated pure parsers rather than adding a shared-import coupling)."""
    m = _OCC_RE.match(symbol or "")
    if not m:
        return None
    root, yy, mm, dd, right, strike_raw = m.groups()
    try:
        strike = int(strike_raw) / 1000.0
    except ValueError:
        return None
    return {"root": root, "expiry": f"20{yy}-{mm}-{dd}", "right": right, "strike": strike}


def intrinsic_value(spot: float, strike: float, right: str) -> float:
    """Exact (model-free) intrinsic value of one option share given spot/strike/right."""
    if right == "C":
        return max(0.0, spot - strike)
    if right == "P":
        return max(0.0, strike - spot)
    return 0.0


def minutes_to_close(now_et: datetime) -> float:
    """Minutes remaining until 16:00 ET today. Floored at 0.5 min so downstream sqrt(T)
    ratios can never divide by zero right at/after the close."""
    close_dt = now_et.replace(hour=MARKET_CLOSE_ET.hour, minute=MARKET_CLOSE_ET.minute,
                               second=0, microsecond=0)
    mins = (close_dt - now_et).total_seconds() / 60.0
    return max(mins, 0.5)


def estimate_decomposition(*, premium_ref: float, mid_now: float, strike: Optional[float],
                            right: Optional[str], spot_now: Optional[float],
                            spot_ref: Optional[float], mins_to_close_now: float,
                            mins_to_close_ref: float) -> dict:
    """PURE. Decompose a premium change from a REFERENCE point (true entry, or N-minutes-ago
    for the windowed stall check -- caller decides which) into three ESTIMATED buckets. See
    the module docstring for the full rationale. Every numeric key is suffixed `_est`; `basis`
    documents the method. Returns all-None numerics (never a fabricated 0) when strike/right/
    spot are unavailable -- a missing input must degrade to "unknown", not "zero"."""
    if right not in ("C", "P") or strike is None or spot_now is None or spot_ref is None:
        return {"delta_component_est": None, "theta_component_est": None,
                "residual_est": None, "theta_per_contract_per_day_est": None,
                "basis": "unavailable (missing strike/right/spot)"}

    intrinsic_now = intrinsic_value(spot_now, strike, right)
    intrinsic_ref = intrinsic_value(spot_ref, strike, right)
    delta_component_est = intrinsic_now - intrinsic_ref

    extrinsic_ref = max(0.0, premium_ref - intrinsic_ref)
    t_ref = max(mins_to_close_ref, 0.5)
    t_now = max(mins_to_close_now, 0.5)
    frac = math.sqrt(min(t_now / t_ref, 1.0)) if t_ref > 0 else 0.0
    extrinsic_now_theta_only = extrinsic_ref * frac
    theta_component_est = extrinsic_now_theta_only - extrinsic_ref  # always <= 0

    real_change = mid_now - premium_ref
    residual_est = real_change - delta_component_est - theta_component_est

    # Instantaneous per-day theta implied by the SAME sqrt(T) curve, evaluated at t_now.
    t_now_days = t_now / (60.0 * 24.0)
    t_ref_days = t_ref / (60.0 * 24.0)
    if extrinsic_ref > 0 and t_ref_days > 0:
        theta_per_day_est = -extrinsic_ref / (2.0 * math.sqrt(max(t_now_days, 1e-6) * t_ref_days))
    else:
        theta_per_day_est = 0.0

    return {
        "delta_component_est": round(delta_component_est, 4),
        "theta_component_est": round(theta_component_est, 4),
        "residual_est": round(residual_est, 4),
        "theta_per_contract_per_day_est": round(theta_per_day_est, 4),
        "basis": "sqrt_time_decay_model (textbook ATM extrinsic~sqrt(T) heuristic, NOT fitted/validated)",
    }


def compute_row(*, arm: str, position: dict, quote: dict, greeks: Optional[dict],
                 entry_snap: dict, spot_now: Optional[float], now_et: datetime) -> dict:
    """PURE (no I/O): assemble one theta-clock row from already-fetched inputs."""
    symbol = position.get("symbol", "")
    parsed = parse_occ_symbol(symbol) or {}
    strike = parsed.get("strike")
    right = parsed.get("right")

    try:
        qty = abs(int(float(position.get("qty", 0))))
    except (TypeError, ValueError):
        qty = 0

    try:
        entry_premium = float(position.get("avg_entry_price"))
    except (TypeError, ValueError):
        entry_premium = entry_snap.get("entry_premium")

    mid_now = quote.get("mid")
    if mid_now is None:
        try:
            mid_now = float(position.get("current_price"))
        except (TypeError, ValueError):
            mid_now = None

    unrealized_pct = None
    plpc = position.get("unrealized_plpc")
    if plpc is not None:
        try:
            unrealized_pct = round(float(plpc) * 100.0, 2)
        except (TypeError, ValueError):
            unrealized_pct = None
    if unrealized_pct is None and mid_now is not None and entry_premium:
        try:
            unrealized_pct = round((mid_now - entry_premium) / entry_premium * 100.0, 2)
        except ZeroDivisionError:
            unrealized_pct = None

    spot_entry = entry_snap.get("entry_spot")
    mins_now = minutes_to_close(now_et)
    mins_entry = entry_snap.get("mins_to_close_at_entry")

    decomp = {"delta_component_est": None, "theta_component_est": None,
              "residual_est": None, "theta_per_contract_per_day_est": None,
              "basis": "unavailable (missing strike/right/spot/entry-snapshot)"}
    theta_burn_since_entry_est = None
    underlying_move_since_entry = None
    if (strike is not None and right in ("C", "P") and spot_now is not None
            and spot_entry is not None and mins_entry and entry_premium is not None
            and mid_now is not None):
        decomp = estimate_decomposition(
            premium_ref=entry_premium, mid_now=mid_now, strike=strike, right=right,
            spot_now=spot_now, spot_ref=spot_entry,
            mins_to_close_now=mins_now, mins_to_close_ref=mins_entry)
        theta_burn_since_entry_est = decomp["theta_component_est"]
        underlying_move_since_entry = round(spot_now - spot_entry, 4)

    greeks = greeks or {}
    raw_theta = greeks.get("theta")
    if isinstance(raw_theta, (int, float)):
        theta_per_contract_per_day = round(raw_theta * 100.0, 4)
        theta_source = "broker_snapshot"
    elif decomp.get("theta_per_contract_per_day_est") is not None:
        theta_per_contract_per_day = decomp["theta_per_contract_per_day_est"]
        theta_source = "sqrt_time_decay_model_est"
    else:
        theta_per_contract_per_day = None
        theta_source = "unavailable"

    def _usd(per_share):
        return None if per_share is None else round(per_share * 100.0 * qty, 2)

    return {
        "ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "arm": arm,
        "symbol": symbol,
        "strike": strike, "right": right,
        "qty": qty,
        "entry_premium": entry_premium,
        "mid_now": mid_now,
        "bid": quote.get("bid"), "ask": quote.get("ask"),
        "unrealized_pct": unrealized_pct,
        "theta_per_contract_per_day": theta_per_contract_per_day,
        "theta_per_contract_per_day_source": theta_source,
        "theta_burn_since_entry_est": theta_burn_since_entry_est,
        "theta_burn_since_entry_est_usd": _usd(theta_burn_since_entry_est),
        "delta_gain_since_entry_est": decomp.get("delta_component_est"),
        "delta_gain_since_entry_est_usd": _usd(decomp.get("delta_component_est")),
        "underlying_move_since_entry": underlying_move_since_entry,
        "spot_now": spot_now,
        "mins_to_close_now": round(mins_now, 1),
        "decomposition_est": decomp,
        "greeks_raw": (dict(greeks) if greeks else None),
        "greeks_source": ("broker_snapshot" if greeks else
                           "unavailable (Alpaca options-snapshots feed has returned empty on "
                           "29/29 real entries to date -- see module docstring)"),
    }


def check_stall_alert(rows_window: list, *, min_margin_usd: float = ALERT_MIN_MARGIN_USD) -> Optional[dict]:
    """PURE. `rows_window` = one position's theta-clock rows (any order; sorted here),
    spanning the lookback window. Returns an alert dict when estimated theta burn over the
    window exceeds estimated delta gain by more than min_margin_usd, else None. Needs >= 2
    rows with a usable decomposition; otherwise None (never alerts on thin/missing history --
    a false negative here is safe, a false positive is not, since J acts on this)."""
    usable = sorted(
        (r for r in rows_window if (r.get("decomposition_est") or {}).get("delta_component_est") is not None),
        key=lambda r: r.get("ts_et", ""))
    if len(usable) < 2:
        return None
    first, last = usable[0], usable[-1]
    qty = last.get("qty") or 0
    if qty <= 0:
        return None

    d0, d1 = first["decomposition_est"], last["decomposition_est"]
    theta_window_per_share = d1["theta_component_est"] - d0["theta_component_est"]
    delta_window_per_share = d1["delta_component_est"] - d0["delta_component_est"]
    theta_dollars = round(theta_window_per_share * 100.0 * qty, 2)
    delta_dollars = round(delta_window_per_share * 100.0 * qty, 2)

    if theta_dollars < 0 and abs(theta_dollars) > max(delta_dollars, 0.0) + min_margin_usd:
        return {
            "window_start_ts_et": first["ts_et"], "window_end_ts_et": last["ts_et"],
            "theta_burn_window_usd": theta_dollars,
            "delta_gain_window_usd": delta_dollars,
            "margin_usd": min_margin_usd,
        }
    return None


def _position_key(arm: str, symbol: str) -> str:
    return f"{arm}::{symbol}"


# --------------------------------------------------------------------------- #
# small I/O utilities
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _active_arms(accounts_json_path: Path = ACCOUNTS_JSON) -> list:
    """Every arm this cockpit watches: status=='active' AND a SPY 0DTE option account --
    naturally includes safe-2/bold-2 (core mcp_heartbeat) + safe-3/risky-1/risky-3 (fleet_rest);
    excludes retired safe-1 (would double-count the safe-2 account) and the dormant/
    pending_build futures arms (not this instrument's scope)."""
    data = _load_json(accounts_json_path, {})
    return [a["id"] for a in data.get("arms", [])
            if a.get("status") == "active" and a.get("instrument") == "SPY_0DTE_OPTION"
            and a.get("id")]


def fetch_quote(creds: dict, symbol: str) -> dict:
    """bid/ask/mid for one option symbol via the SAME endpoint fleet_broker.get_option_mid
    uses on the LIVE placement path (a proven-working call, unlike the greeks snapshot
    endpoint) -- this just also keeps bid/ask instead of collapsing straight to the mid.
    Fail-open: {} on any error."""
    url = f"{OPTIONS_DATA_HOST}/v1beta1/options/quotes/latest?symbols={symbol}"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=QUOTE_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return {}
    q = (payload or {}).get("quotes", {}).get(symbol)
    if not q:
        return {}
    out = {}
    bid, ask = q.get("bp"), q.get("ap")
    if isinstance(bid, (int, float)) and bid > 0:
        out["bid"] = bid
    if isinstance(ask, (int, float)) and ask > 0:
        out["ask"] = ask
    if "bid" in out and "ask" in out:
        out["mid"] = round((out["bid"] + out["ask"]) / 2, 4)
    return out


def _fetch_spy_spot_direct(creds: dict) -> Optional[float]:
    """Last-resort direct SPY quote, used ONLY when sight-beacon.json is missing/stale --
    theta_clock must stay useful even if the beacon daemon is down. Fail-open: None on error."""
    url = f"{OPTIONS_DATA_HOST}/v2/stocks/SPY/quotes/latest?feed=iex"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=QUOTE_TIMEOUT_S) as resp:
            q = json.loads(resp.read().decode("utf-8")).get("quote", {})
        bid, ask = q.get("bp"), q.get("ap")
        if bid and ask:
            return round((bid + ask) / 2.0, 4)
    except Exception:  # noqa: BLE001
        pass
    return None


def fetch_spot(now_et: datetime, *, beacon_path: Path = SIGHT_BEACON_PATH,
               max_age_s: int = BEACON_MAX_AGE_S,
               direct_fetch: Optional[Callable[[], Optional[float]]] = None) -> tuple:
    """(spot_price, source). Prefers the already-fresh sight-beacon.json (refreshed ~1 min by
    Gamma_SightBeacon -- zero extra network call in the common case); falls back to one direct
    REST call only when the beacon is missing/stale."""
    beacon = _load_json(beacon_path, {})
    spy, ts_et_s = beacon.get("spy"), beacon.get("ts_et")
    if spy is not None and ts_et_s:
        try:
            beacon_dt = datetime.strptime(str(ts_et_s)[:19], "%Y-%m-%dT%H:%M:%S")
            age_s = (now_et - beacon_dt).total_seconds()
            if 0 <= age_s <= max_age_s:
                return float(spy), "sight_beacon"
        except (ValueError, TypeError):
            pass
    if direct_fetch is not None:
        val = direct_fetch()
        if val is not None:
            return float(val), "direct_rest_fallback"
    return None, "unavailable"


def _load_position_state(path: Path = POSITION_STATE_PATH) -> dict:
    d = _load_json(path, {})
    d.setdefault("schema", "theta-clock-position-state-v1")
    d.setdefault("positions", {})
    return d


def _prune_position_state(state: dict, now_et: datetime,
                           retention_days: int = POSITION_STATE_RETENTION_DAYS) -> dict:
    """PURE. Drop entries whose OCC expiry date is older than retention_days. Unparseable
    symbols are kept (never risk dropping real data over a parse miss)."""
    kept = {}
    for key, rec in (state.get("positions") or {}).items():
        symbol = rec.get("symbol") or key.split("::")[-1]
        parsed = parse_occ_symbol(symbol)
        if not parsed:
            kept[key] = rec
            continue
        try:
            exp = datetime.strptime(parsed["expiry"], "%Y-%m-%d")
        except ValueError:
            kept[key] = rec
            continue
        if (now_et - exp).days <= retention_days:
            kept[key] = rec
    return {**state, "positions": kept}


def _ensure_entry_snapshot(state: dict, key: str, *, arm: str, position: dict,
                            greeks: Optional[dict], spot_now: Optional[float],
                            now_et: datetime) -> dict:
    """Freezes the FIRST-OBSERVATION snapshot for a new position key. NEVER mutates an
    existing entry -- see module docstring's delta_at_entry convention. Returns the (possibly
    newly-created) entry snapshot dict."""
    positions = state.setdefault("positions", {})
    if key in positions:
        return positions[key]
    try:
        entry_premium = float(position.get("avg_entry_price"))
    except (TypeError, ValueError):
        entry_premium = None
    greeks = greeks or {}
    snap = {
        "arm": arm, "symbol": position.get("symbol"),
        "first_seen_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "entry_premium": entry_premium,
        "entry_spot": spot_now,
        "mins_to_close_at_entry": round(minutes_to_close(now_et), 2),
        "entry_delta": greeks.get("delta"), "entry_gamma": greeks.get("gamma"),
        "entry_theta": greeks.get("theta"), "entry_vega": greeks.get("vega"),
        "entry_iv": greeks.get("iv"),
        "greeks_captured_at_entry": bool(greeks),
        "alerted": False, "alerted_at_et": None,
    }
    positions[key] = snap
    return snap


def _read_window_rows(daily_jsonl: Path, key: str, now_et: datetime, window_min: int) -> list:
    """Today's already-appended rows for `key` within the last window_min minutes (inclusive),
    oldest-first. Read back from the daily JSONL rather than a separate ring buffer -- the
    JSONL already IS the time series."""
    arm, symbol = key.split("::", 1)
    cutoff = now_et - timedelta(minutes=window_min)
    rows = []
    try:
        with daily_jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("arm") != arm or r.get("symbol") != symbol:
                    continue
                try:
                    ts = datetime.strptime(str(r["ts_et"])[:19], "%Y-%m-%dT%H:%M:%S")
                except (KeyError, ValueError, TypeError):
                    continue
                if ts >= cutoff:
                    rows.append((ts, r))
    except OSError:
        return []
    rows.sort(key=lambda t: t[0])
    return [r for _, r in rows]


def _flag_live_watch(*, arm: str, symbol: str, alert: dict, row: dict,
                      status_md_path: Path = STATUS_MD) -> None:
    """Append ONE loud line to STATUS.md's '## Live watch' section (created on first use) --
    mirrors setup/guard_runner_slow.py::_flag_status_md's exact "insert newest-first right
    after the marker" idiom, but this is a NEW section, deliberately separate from
    '## Known broken': a stalled trade is an operational-awareness ping, not a breakage.
    ALERT ONLY -- never touches the position. Fail-open: any error here must never break the
    tick that found the stall (caller already wraps this in try/except; this function also
    guards its own file read defensively)."""
    try:
        text = status_md_path.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Live watch"
    if marker not in text:
        block = (
            f"{marker}\n\n"
            "_Standing visibility-only flag surface (THETA COCKPIT, 2026-08-01 J directive) -- "
            "NOT a breakage list, no auto-exit ever. Producers append ONE loud line here on a "
            "NEW stalled-position threshold crossing; never re-fired for the same position. "
            "Producer: setup/scripts/theta_clock.py._\n\n---\n\n"
        )
        kb = "## Known broken"
        text = text.replace(kb, block + kb, 1) if kb in text else block + text
    theta_d, delta_d = alert["theta_burn_window_usd"], alert["delta_gain_window_usd"]
    line = (f"- [{row['ts_et']} ET] THETA STALL :: {arm} {symbol} qty={row.get('qty')} :: "
            f"est theta burn {theta_d:+.2f} vs est delta gain {delta_d:+.2f} over last "
            f"{ALERT_WINDOW_MIN}min (mid={row.get('mid_now')}, unrealized="
            f"{row.get('unrealized_pct')}%) -- ALERT ONLY, never auto-exits. "
            f"detail: automation/state/theta-clock.json")
    head, _, tail = text.partition(marker + "\n")
    status_md_path.write_text(f"{head}{marker}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run_once(*, now_et: Optional[datetime] = None,
             creds_by_arm: Optional[dict] = None,
             active_arms: Optional[list] = None,
             positions_fn: Optional[Callable] = None,
             greeks_fn: Optional[Callable] = None,
             quote_fn: Optional[Callable] = None,
             spot_fn: Optional[Callable] = None,
             state_path: Path = POSITION_STATE_PATH,
             snapshot_path: Path = SNAPSHOT_PATH,
             theta_dir: Path = THETA_DIR,
             status_md_path: Path = STATUS_MD) -> dict:
    """The full tick. Every dependency is injectable (mirrors this codebase's
    `fetch=None` idiom, e.g. heartbeat_core._capture_greeks) so tests AND the weekend
    dry-run can run this end-to-end with zero network/credentials touched, against a
    SYNTHETIC position, isolated to tmp_path state files.

    FAIL-OPEN at every boundary: one account/position's failure never stops the others.
    Always returns a summary dict; never raises (main() wraps this again as belt-and-
    suspenders, since a caller could pass a bad injected fn)."""
    now_et = now_et or et_now()
    positions_fn = positions_fn or (lambda arm, creds: fb.open_spy_option_positions(creds))
    greeks_fn = greeks_fn or (lambda creds, symbol: fb.get_option_greeks(creds, symbol))
    quote_fn = quote_fn or fetch_quote

    summary = {"ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "accounts_checked": [],
               "accounts_failed": [], "n_positions": 0, "n_alerts": 0, "positions": []}

    if creds_by_arm is None:
        try:
            creds_by_arm = fb.load_creds()
        except Exception as e:  # noqa: BLE001
            summary["error"] = f"load_creds failed: {type(e).__name__}: {e}"
            _atomic_write_json(snapshot_path, summary)
            return summary

    if active_arms is None:
        active_arms = _active_arms()

    if spot_fn is None:
        def spot_fn():
            any_creds = next(iter(creds_by_arm.values()), None)
            direct = (lambda: _fetch_spy_spot_direct(any_creds)) if any_creds else None
            return fetch_spot(now_et, direct_fetch=direct)
    spot_now, spot_source = spot_fn()
    summary["spot_now"], summary["spot_source"] = spot_now, spot_source

    state = _prune_position_state(_load_position_state(state_path), now_et)
    theta_dir.mkdir(parents=True, exist_ok=True)
    daily_jsonl = theta_dir / f"theta-clock-{now_et.strftime('%Y-%m-%d')}.jsonl"

    for arm in active_arms:
        creds = creds_by_arm.get(arm)
        if not creds:
            summary["accounts_failed"].append({"arm": arm, "reason": "no_creds"})
            continue
        try:
            positions = positions_fn(arm, creds) or []
        except Exception as e:  # noqa: BLE001
            summary["accounts_failed"].append({"arm": arm, "reason": f"{type(e).__name__}: {e}"})
            continue
        summary["accounts_checked"].append(arm)

        for position in positions:
            symbol = None
            try:
                symbol = position.get("symbol", "") if isinstance(position, dict) else ""
                key = _position_key(arm, symbol)

                try:
                    greeks = greeks_fn(creds, symbol)
                except Exception:  # noqa: BLE001
                    greeks = None

                entry_snap = _ensure_entry_snapshot(state, key, arm=arm, position=position,
                                                     greeks=greeks, spot_now=spot_now, now_et=now_et)

                try:
                    quote = quote_fn(creds, symbol)
                except Exception:  # noqa: BLE001
                    quote = {}

                row = compute_row(arm=arm, position=position, quote=quote, greeks=greeks,
                                   entry_snap=entry_snap, spot_now=spot_now, now_et=now_et)
                summary["positions"].append(row)
                summary["n_positions"] += 1

                with daily_jsonl.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")

                if not entry_snap.get("alerted"):
                    window_rows = _read_window_rows(daily_jsonl, key, now_et, ALERT_WINDOW_MIN)
                    alert = check_stall_alert(window_rows)
                    if alert:
                        entry_snap["alerted"] = True
                        entry_snap["alerted_at_et"] = now_et.strftime("%Y-%m-%dT%H:%M:%S")
                        try:
                            _flag_live_watch(arm=arm, symbol=symbol, alert=alert, row=row,
                                              status_md_path=status_md_path)
                        except Exception:  # noqa: BLE001 -- the flag write must never break the tick
                            pass
                        summary["n_alerts"] += 1
            except Exception as e:  # noqa: BLE001 -- one position must never sink the tick
                summary["accounts_failed"].append(
                    {"arm": arm, "symbol": symbol, "reason": f"position_error {type(e).__name__}: {e}"})

    _atomic_write_json(state_path, state)
    _atomic_write_json(snapshot_path, summary)
    return summary


def main() -> int:
    try:
        summary = run_once()
        print(f"[theta_clock] {summary.get('ts_et')} "
              f"accounts_checked={summary.get('accounts_checked')} "
              f"n_positions={summary.get('n_positions')} n_alerts={summary.get('n_alerts')} "
              f"accounts_failed={summary.get('accounts_failed')}")
    except Exception as e:  # noqa: BLE001 -- fail-open: this watcher must NEVER affect trading
        print(f"[theta_clock] FAIL-OPEN: {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
