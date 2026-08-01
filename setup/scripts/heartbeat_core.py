"""heartbeat_core.py — the DETERMINISTIC live trade engine (replaces the LLM heartbeat).

Why (2026-06-25, J: "mainly python reading the bars with 2 free models evaluating each
heartbeat"): the LLM heartbeat crashed daily — it ran the see->decide->act loop on the
most fragile substrate (Haiku + TV-CDP + uvx-Alpaca + a 97KB prose prompt). The decision
logic is pure arithmetic + rules and ALREADY EXISTS deterministically in backtest/lib
(score_bar + evaluate_gates via engine_cli, proven byte-identical to the backtest). This
core assembles live market state, gets the deterministic verdict, has 2 FREE models
sanity-veto an entry, and places the bracket via direct REST. No LLM on the hot path, no
MCP, no CDP — it reads the same un-blockable data the beacon does.

FLOW per account (safe, bold):
  1. live state: SPY 5m bars (REST) + ribbon (compute_ribbon) + VIX (yfinance) + levels
     (key-levels.json) + HTF 15m + baselines  ->  engine_cli bar_ctx payload
  2. verdict: pipe to backtest.lib.engine.engine_cli  ->  ENTER_BEAR/ENTER_BULL/HOLD/SKIP_*
     (the SAME scoring + 15 gates the backtest uses; deterministic; fails CLOSED)
  3. on ENTER: 2 FREE models (groq + cerebras/gemini via swarm_client) each give GO/NO-GO.
     Rules decide; models can only VETO (never create) an entry  ->  safety, not authority.
  4. execute (ARMED only): broker FLAT-verify -> risk_gate sizing -> place_bracket REST.
  5. persist EVERY tick to automation/state/core-decisions.jsonl (Python writes it; no LLM
     to skip the write).

SAFETY: ARMED defaults False (shadow — logs the verdict + what it WOULD place, no order).
Flip to True only after the shadow verdicts are verified against the live tape. Bracket =
entry + TP + -50% catastrophe stop placed atomically (broker manages the exit); EOD flatten
task is the time-stop. Reuses risk_gate (cap/min-contracts/PDT/kill-switch) + is_flat_spy_options
(broker = source of truth, L47/C11).
"""
from __future__ import annotations

import json
import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # no conhost flash on win32 (OP-27 L41)
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

# et_clock is in the same directory; insert its parent so it resolves before the
# bare `setup` entry point adds it later.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1].parent
# Order matters: backtest/lib inserted LAST so it lands FIRST on sys.path — its `ribbon`
# (the exact backtest ribbon, spread=max-min) must win over crypto/lib's same-named module.
for p in ("crypto/lib", "automation/state/fleet", "setup/scripts", "backtest/lib"):
    sys.path.insert(0, str(REPO / p))

import pandas as pd  # noqa: E402
from ribbon import compute_ribbon as _ribbon_compute_df  # lib.ribbon — EXACT backtest ribbon  # noqa: E402


def _nn(x):
    """NaN -> None for JSON; pass floats through."""
    try:
        return None if x is None or x != x else float(x)
    except (TypeError, ValueError):
        return None

STATE = REPO / "automation" / "state"
LEDGER = STATE / "core-decisions.jsonl"
# TICK-COMPLETE MARKER (2026-08-01, WEEKEND-TWELVE #4 race fix). heartbeat_core writes the
# safe row, then the bold row ~1s later (see run_account/main below) -- a reader with its own
# independent cadence (Gamma_FleetExecutor, every 3 min) can land in that gap and pair a fresh
# safe row with a stale bold row from the PRIOR tick (or vice versa). This file is overwritten
# (never appended) with the id of the last tick where BOTH rows are confirmed on disk; see
# main()'s _write_tick_marker call. build_shared_signal.py reads it to pin one tick_id across
# its safe+bold reads instead of two independent last-row scans. Incident:
# analysis/deep-research/WINNER-AUTOPSY-2026-07-31-1219.md (12:16:02.508 fleet read, 0.45s
# after the safe row / 0.5s before the bold row -- forfeited a full 3-min cadence slot).
TICK_MARKER = STATE / "core-decisions-tick.json"
import os  # noqa: E402
import logging  # noqa: E402

# Module logger — was referenced (logger.warning at the dispatch except, logger.critical
# at the bull-wiring guard) but NEVER defined: a latent NameError that would have masked
# the real dispatch error if that except ever fired. Defined here once. Routes to stderr.
logger = logging.getLogger("heartbeat_core")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s heartbeat_core %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# SHADOW (DISARMED) — left disarmed deliberately; J flips the switch. As of 2026-06-25 the
# historical replay (backtest/replay_heartbeat_core.py) now PASSES the full arm-gate:
#   - bear_score exact-match 98.0% (avg diff 0.02) — input/score wiring byte-faithful
#   - ENTRY FIDELITY 5/5 matched, 0 extra, 0 missed over the 8-day window: after the live
#     FLAT-verify dedup the live engine trades at the SAME bars/sides the backtest does.
#     (The quality-lock re-entry suppression that also gated this replay was DELETED
#     2026-07-02 per J's written order — never validated, cost the 07-02 midday trade.)
#     SKIP_NO_PULLBACK is irrelevant
#     (V_PULLBACK off by default; 0 such decisions in-window).
# ARMED still defaults False: arming is J's call, never automatic. Re-arm: `set GAMMA_CORE_ARMED=1`.
ARMED = os.environ.get("GAMMA_CORE_ARMED", "0") == "1"

# EXIT-ENGINE FLAG (2026-06-25, reversible) — wire the validated partial-scale-out /
# runner / profit-lock exit_manager into the core path. DEFAULT OFF so the ARMED
# safe-2/bold-2 behavior is BYTE-IDENTICAL to tonight: with this off, _execute still
# places the single catastrophe-floor bracket and nothing registers/manages a scale-out.
# Set GAMMA_CORE_MANAGES_EXITS=1 to (a) register each real fill with the exit_manager and
# (b) run a per-tick exit-management pass (partial TP1 at tp1_qty_fraction + runner +
# profit-lock + time stop). The management pass only PLACES when ARMED (live); otherwise it
# computes + logs (WATCH). This is the single reversible lever for the exit-engine migration;
# it is orthogonal to ARMED (it chooses whether the brain MANAGES exits, not whether it's live).
CORE_MANAGES_EXITS = os.environ.get("GAMMA_CORE_MANAGES_EXITS", "0") == "1"

# 6-ACCOUNT UNIFICATION LEVER (2026-06-25, reversible) — the brain is the ONE perception
# for all 6 arms (build_shared_signal already reads core-decisions.jsonl, so the 4 fleet_rest
# arms already trade off this brain's verdicts; safe-2/bold-2 are placed here by _execute).
# CORE_PLACES_ORDERS chooses WHO places safe-2/bold-2's orders:
#   "1" (DEFAULT) = TODAY'S EXACT BEHAVIOR — the brain's _execute places safe-2/bold-2.
#   "0"           = perception-only — the brain writes the verdict + ledger row (identical
#                   bytes) but places NOTHING, so the fleet executor can own all 6 arms as
#                   ordinary grid cells (the Path-B migration). The verdict/scores/ledger are
#                   byte-identical either way; only WHO places migrates. This is the single
#                   reversible lever for the safe-2/bold-2 execution migration. Orthogonal to
#                   ARMED (this chooses who places, not whether live).
CORE_PLACES_ORDERS = os.environ.get("GAMMA_CORE_PLACES", "1") == "1"

ACCOUNTS = {
    "safe": {"params": STATE / "params.json", "mcp_server": "alpaca", "fleet_arm": "safe-2"},
    "bold": {"params": STATE / "aggressive" / "params.json", "mcp_server": "alpaca_aggressive",
             "fleet_arm": "bold-2"},
}
# Gate knobs engine_cli reads from params.json (pass-through; missing -> engine default).
# FIX3 (2026-07-01): block_elite_bull_vix_low/high were OMITTED here, so gates.py ran its
# defaults [0.0, 999.0) and the elite-bull block applied at ALL VIX instead of the ratified
# bands (Safe [0,25), Bold [15,18)). Guard: test_money_path_2026_07_01.py::TestGateKeysVixBand.
GATE_KEYS = [
    "block_level_rejection", "trendline_requires_ribbon_flip", "block_elite_bull",
    "block_elite_bull_vix_low", "block_elite_bull_vix_high",
    "block_bull_ribbon_flip", "block_bull_1100_1200", "block_bull_morning_agg",
    "require_bearish_fill_bar", "min_ribbon_momentum_cents", "max_ribbon_duration_bars",
    "midday_trendline_gate", "block_conf_lvl_rej_midday_afternoon", "block_conf_lvl_rec_afternoon",
    "entry_bar_body_pct_min", "entry_bar_body_pct_min_bull", "vix_bear_hard_cap",
    "structure_veto_enabled",
    # STRUCTURE-SHIFT-CONFIRMATION-AT-LEVELS (2026-07-28) — wiring-only addition. Listing
    # the key here does NOT arm anything: pass-through only fires if the key is later added
    # to params.json (a separate ratification decision per the pre-reg's arming_plan).
    # Absent from params.json today -> gate_params never contains the key -> engine_cli's
    # `gate_params.get("structure_shift_confirmation_enabled", False)` stays False ->
    # byte-identical scoring. Pre-reg: analysis/recommendations/
    # prereg-structure-shift-confirmation-2026-07-28.json.
    "structure_shift_confirmation_enabled",
]


from et_clock import et_now as _et_clock_now  # noqa: E402  (after sys.path insert above)


def _et_now() -> datetime:
    """ET from UTC via DST-aware et_clock (replaces hardcoded -4, TZ-SYSTEMIC fix)."""
    return _et_clock_now()


def _is_rth(et: datetime) -> bool:
    h = et.hour + et.minute / 60
    return et.weekday() < 5 and 9.5 <= h <= 16.0


def _past_entry_ceiling(params: dict, now_et: datetime) -> bool:
    """FIX1 (2026-07-01): hard entry-time ceiling. params entry_no_trade_after_et ('15:00',
    the v15.1 [09:35,15:00) window) was NEVER forwarded to engine_cli (only no_trade_before +
    no_trade_window), so on 2026-06-30 the engine's only 10 ENTER verdicts fired 15:51-15:55 ET
    and Alpaca rejected every order ('expires soon'). True => now_et is AT/AFTER the ceiling =>
    the caller logs SKIP_LATE_ENTRY and NEVER attempts an order. Missing/malformed key fails
    CLOSED to the 15:00 doctrine default (theta kills after 3pm — J, v15.1).
    Guard: test_money_path_2026_07_01.py::TestEntryCeiling."""
    raw = params.get("entry_no_trade_after_et") if isinstance(params, dict) else None
    ceiling = time(15, 0)
    if raw:
        try:
            parts = str(raw).split(":")
            ceiling = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (TypeError, ValueError, IndexError):
            ceiling = time(15, 0)
    return now_et.time() >= ceiling


def _before_entry_floor(params: dict, now_et: datetime) -> bool:
    """FIX (2026-07-02): wall-clock entry-time floor — mirror of _past_entry_ceiling.
    entry_no_trade_before_et was enforced only against the TRIGGER BAR timestamp
    (filters.py filter-1), which at the open ticks is still the PRIOR day's 15:50/15:55
    bar — so the 09:35 floor could never fire (2026-07-02: ENTER_BEAR placed 09:30:03).
    True => now_et is BEFORE the floor => the caller logs SKIP_EARLY_ENTRY and never
    attempts an order. Missing/malformed key fails CLOSED to the 09:35 doctrine default.
    Guard: test_entry_floor_2026_07_02.py::TestCoreWallClockFloor."""
    raw = params.get("entry_no_trade_before_et") if isinstance(params, dict) else None
    floor = time(9, 35)
    if raw:
        try:
            parts = str(raw).split(":")
            floor = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (TypeError, ValueError, IndexError):
            floor = time(9, 35)
    return now_et.time() < floor


# SIGHT-FRESHNESS GUARD (DECISION-ROW-SPY-STALENESS, 2026-07-20 investigation) -----------
# ROOT CAUSE: bc['bar']['close'] (the price the score/gates AND every extra-setup watcher's
# entry+stop derive from) is `trig['close']` where trig_idx = n-2 in _build_payload -- the
# trigger is ALWAYS the 2nd-to-last fetched 5m bar (the newest bar is reserved as the
# forward-confirmation bar require_bearish_fill_bar reads), so it only advances once per 5m
# bar-close and is therefore ~5-10 minutes old by DESIGN (matches backtest fidelity -- this
# lag itself is not a bug, and a bare "trigger bar age > N minutes" guard would either be
# toothless (N>=10) or block nearly every tick of this 5m-bar architecture (N<10)).
# _stale_trigger_bar (above) already catches the EXTREME cross-session case (a prior-day bar
# carried at today's open -- proven live: every >$3 divergence in the 2026-07-14..07-20
# ledger is a 09:30-09:35 SKIP_STALE_TRIGGER row). EXTRA-SIGNAL-CHURN-COOLDOWN (commit
# fd91712, same day) already stops a setup from RE-firing on the SAME stale trigger bar after
# a stop-out. What neither catches: a FIRST entry attempt whose trigger bar is still within
# its normal ~5-10min lag but the market has genuinely moved fast INSIDE that window -- the
# live exhibit this guard is built from (2026-07-20 09:51-09:55 ET, safe/vix_regime_dayside):
# bc['bar']['close'] pinned at 747.575 (the 09:45-09:50 bar) for 5 straight ticks while the
# real 1-min SIP tape sold off 747.62->746.14; the 09:54:19 and 09:55:24 fills traded a
# swing-low stop (746.87) and a "buy the day-trend" direction computed against a spot that
# was already $1.12/$1.38 away from reality. Quantification (analysis/recommendations/
# decision-row-spy-staleness-2026-07-20.json, n=3860 RTH rows 07-14..07-20): legitimate
# real-fills entries this same week (excluding the 07-20 cluster and the already-guarded
# session-open rows) topped out at $0.63 divergence; the three 07-20 vix_dayside fills alone
# reached $0.40/$1.12/$1.38 -- so a $1.00 threshold catches exactly the pathological cluster
# without touching a single other real entry this week.
#
# FIX: cross-check the decision spot against a genuinely tick-level read (Alpaca latest-trade,
# NOT another bar close -- a second bar-close read would inherit the identical lag) ONLY at
# the moment an entry is actually being attempted (primary ENTER_BEAR/ENTER_BULL and the
# extra-setup route, after their existing gates/cooldown already passed -- bounded cost, a
# handful of REST calls/day, not a hot-path add). FAIL-OPEN both ways: no live quote
# available -> the guard cannot assert staleness, so it never blocks (NEVER-BLIND doctrine --
# an auxiliary safety check must never become a new single point of failure); a live quote
# IS available and diverges past the threshold -> SKIP_STALE_SIGHT, no order attempted
# (fail-open to NOT-TRADING, never to trading blind). Guard: test_sight_staleness_guard.py.
SIGHT_STALENESS_MAX_DIVERGENCE_USD = 1.00


_SIGHT_NOOP = {"checked": False, "live_spy": None, "divergence": None, "stale": False}


def _sight_staleness_check(trigger_spy: "float | None") -> dict:
    """Compare the decision's trigger-bar spot against a fresh live quote. Returns a dict
    always safe to log verbatim onto a decision row: {checked, live_spy, divergence, stale}.
    `checked=False` (live quote unavailable, trigger_spy missing, OR any unexpected error) ->
    `stale` is always False -> callers may use the result directly without their own
    try/except (this function itself never raises -- self-safe by design, same contract as
    _fetch_live_spy_quote; defense-in-depth beyond that function's own internal try/except)."""
    try:
        if trigger_spy is None:
            return dict(_SIGHT_NOOP)
        live = _fetch_live_spy_quote()
        if live is None:
            return dict(_SIGHT_NOOP)
        divergence = round(abs(float(trigger_spy) - live), 4)
        return {"checked": True, "live_spy": live, "divergence": divergence,
                "stale": divergence > SIGHT_STALENESS_MAX_DIVERGENCE_USD}
    except Exception:  # noqa: BLE001 -- fail-open: never raise, never block on an internal error
        return dict(_SIGHT_NOOP)


def _stale_trigger_bar(payload: dict, now_et: datetime) -> bool:
    """FIX (2026-07-02): an ENTER is only actionable when its trigger bar is from
    TODAY's session. At the open ticks the 2nd-to-last fetched bar is the PRIOR day's
    15:50/15:55 bar — scoring it re-emits yesterday's dying signal at today's prices
    (the 2026-07-02 09:30:03 incident). Malformed/absent timestamp fails CLOSED (stale).
    Guard: test_entry_floor_2026_07_02.py::TestCoreStaleTriggerBar."""
    try:
        ts = str(payload["bar_ctx"]["timestamp_et"])
        return ts[:10] != now_et.strftime("%Y-%m-%d")
    except (KeyError, TypeError, IndexError):
        return True


# ----- live market state -----------------------------------------------------
def _fetch_spy_5m() -> pd.DataFrame:
    """SPY 5m OHLCV, ~5 trading days, via direct Alpaca REST (same un-blockable path as the beacon)."""
    import urllib.request
    m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    key, sec = env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]
    start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min&start={start}"
           f"&limit=600&feed=iex&adjustment=raw&sort=asc")
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=15) as r:
        bars = json.loads(r.read()).get("bars", [])
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame([{"timestamp": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                       "close": b["c"], "volume": b["v"]} for b in bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    return df.reset_index(drop=True)


def _fetch_live_spy_quote() -> "float | None":
    """Tick-level SPY price via Alpaca's latest-trade REST endpoint (NOT a 5m bar close) --
    the sight-freshness cross-check's ground truth. Same un-blockable direct-REST path/creds
    as _fetch_spy_5m; deliberately a DIFFERENT endpoint (/trades/latest, not /bars) so this
    reads the actual last print instead of another bar-close (which would inherit the exact
    same structural lag it's meant to catch — see SIGHT_STALENESS_MAX_DIVERGENCE_USD below).
    None on ANY failure (bad key, timeout, empty payload) -- NEVER raises. Callers must treat
    None as "cannot verify freshness" and fail OPEN (never block a legitimate entry just
    because this one auxiliary read hiccupped -- NEVER-BLIND doctrine); only a POSITIVE,
    successfully-fetched divergence may block. Cost: one REST call, only at actual
    entry-attempt moments (see call sites) -- a handful of times/day, $0 (existing paper-key
    market-data entitlement)."""
    import urllib.request
    try:
        m = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))
        env = m["mcpServers"]["alpaca"]["env"]
        key, sec = env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]
        url = "https://data.alpaca.markets/v2/stocks/SPY/trades/latest?feed=iex"
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        px = (data.get("trade") or {}).get("p")
        return float(px) if px is not None else None
    except Exception:  # noqa: BLE001 -- fail-open: never raise, never block on a fetch hiccup
        return None


def _fetch_vix() -> tuple[float, float]:
    """(vix_now, vix_prior) from yfinance ^VIX 5m — direction is what the gates need. Fallback (0,0)."""
    try:
        import yfinance as yf
        d = yf.download("^VIX", period="2d", interval="5m", auto_adjust=False, progress=False, timeout=10)
        if d is None or d.empty:
            return 0.0, 0.0
        if hasattr(d.columns, "nlevels") and d.columns.nlevels > 1:
            d.columns = d.columns.get_level_values(0)
        c = [float(x) for x in d["Close"].tolist() if x == x]
        return (c[-1], c[-2]) if len(c) >= 2 else (c[-1], c[-1]) if c else (0.0, 0.0)
    except Exception:
        return 0.0, 0.0


def _fetch_vix_daily_ma() -> tuple[float, float]:
    """(vix_5d_ma, vix_20d_ma) = mean of the prior 5 / prior 20 DAILY ^VIX closes,
    PRIOR DAYS ONLY (excludes today). Mirrors orchestrator.py:801-817. 0.0 when
    insufficient history (same default the orchestrator's .get(...,0.0) yields)."""
    try:
        import yfinance as yf
        d = yf.download("^VIX", period="40d", interval="1d", auto_adjust=False, progress=False, timeout=10)
        if d is None or d.empty:
            return 0.0, 0.0
        if hasattr(d.columns, "nlevels") and d.columns.nlevels > 1:
            d.columns = d.columns.get_level_values(0)
        closes = [float(x) for x in d["Close"].tolist() if x == x]
        # drop today's (possibly in-progress) close so we average PRIOR sessions only
        et = _et_now().date()
        if len(d.index) and pd.Timestamp(d.index[-1]).date() == et:
            closes = closes[:-1]
        ma5 = sum(closes[-5:]) / 5.0 if len(closes) >= 5 else 0.0
        ma20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else 0.0
        return ma5, ma20
    except Exception:
        return 0.0, 0.0


def _fetch_vix_intraday(cap_ts_et=None) -> list[float] | None:
    """Intraday ^VIX 5m closes (RTH-only, newest LAST) for the vix_regime_dayside regime
    (trailing-median 78 + slope 5). CAUSALLY capped at ``cap_ts_et`` (no VIX bar later than
    the trigger bar — preserves no-look-ahead, C6). Returns the FULL RTH series (warmup +
    today) so the watcher's median(78)/slope(5) have their window; the watcher tail-slices
    to today's RTH frame. None on any failure / empty / all-NaN (fail-open -> watcher SKIPs,
    never guesses the regime). Only fetched when j_vix_dayside_enabled is set, so while the
    setup is DORMANT this is never called (zero hot-path cost)."""
    try:
        import yfinance as yf
        d = yf.download("^VIX", period="2d", interval="5m", auto_adjust=False, progress=False, timeout=10)
        if d is None or d.empty:
            return None
        if hasattr(d.columns, "nlevels") and d.columns.nlevels > 1:
            d.columns = d.columns.get_level_values(0)
        idx = pd.to_datetime(d.index)
        idx = idx.tz_localize("America/New_York") if idx.tz is None else idx.tz_convert("America/New_York")
        s = pd.Series([float(x) for x in d["Close"].tolist()], index=idx).dropna()
        s = s.between_time("09:30", "15:55")  # RTH 5m closes (bars stamped 09:30..15:55 ET)
        if cap_ts_et is not None:
            cap = pd.Timestamp(cap_ts_et)
            cap = cap.tz_localize("America/New_York") if cap.tz is None else cap.tz_convert("America/New_York")
            s = s[s.index <= cap]
        vals = [float(x) for x in s.tolist()]
        return vals or None
    except Exception:
        return None


def _level_expired(lv: dict, today_et: str) -> bool:
    """FIX2 (2026-07-07): a level whose expires_at is BEFORE today's ET date is stale and
    must never reach the live active set / filter-10 (e.g. PML_2026-06-30 @741.61 kept
    matching purely on distance because _read_levels never checked the date). Returns True
    ONLY when expires_at parses to a date strictly before today. FAIL-OPEN: a missing,
    null, or unparseable expires_at returns False (KEEP the level) and never raises — an
    unreadable date must never silently drop a valid level or crash the read.
    Guard: test_audit_fix_heartbeat.py::TestExpiredLevels."""
    raw = lv.get("expires_at") if isinstance(lv, dict) else None
    if not raw:
        return False
    exp = str(raw)[:10]  # tolerate 'YYYY-MM-DD' or a full 'YYYY-MM-DDTHH:MM:SS' timestamp
    try:
        datetime.strptime(exp, "%Y-%m-%d")
    except (TypeError, ValueError):
        return False  # unparseable -> fail open, keep the level
    return exp < today_et


def _read_levels(spy: float) -> tuple[list[float], list[float]]:
    try:
        kl = json.loads((STATE / "key-levels.json").read_text(encoding="utf-8"))
        levels = kl.get("levels") or kl.get("key_levels") or []
        today_et = _et_now().strftime("%Y-%m-%d")
        active, multi = [], []
        for lv in levels:
            if _level_expired(lv, today_et):
                continue  # drop levels that expired on a prior ET day (fail-open on bad/absent date)
            p = lv.get("price") or lv.get("level") or lv.get("value")
            if isinstance(p, (int, float)) and abs(p - spy) <= 12:
                active.append(round(float(p), 2))
                if lv.get("multi_day") or lv.get("role") in ("broken_to_resistance", "resistance", "support"):
                    multi.append(round(float(p), 2))
        return active, multi
    except (OSError, json.JSONDecodeError):
        return [], []


CONTEXT_BUNDLE_STALE_MIN = 20  # older than this -> treat as absent (a stale trend read is
                                # worse than none; matches the 5-min Gamma_ContextBundle cadence
                                # with generous slack for a missed/late fire).


def _read_context_bundle() -> "dict | None":
    """Fail-open read of automation/state/context-bundle.json — the multi-timeframe
    TREND-ALIGNMENT context bundle (Phase 0, context-enrichment plan 2026-07-14). Mirrors
    _read_levels's disk-read pattern. Cloned, not shared, deliberately: _read_levels feeds
    the LIVE decision (levels_active/multi_day_levels -> filters.py triggers); this bundle
    is LOGGED ONLY this phase — see the two call sites below (_build_payload's bar_ctx,
    run_account's rec) — nothing on the score/gates/_derive_tier path reads it.

    Returns None when the file is missing/unreadable/malformed, OR when computed_at_et is
    older than CONTEXT_BUNDLE_STALE_MIN minutes (a stale multi-day trend read is treated as
    absent, not as ground truth) — either way LOGGED as an absent bundle rather than crashing
    or fabricating a read. NEVER raises.
    """
    try:
        raw = json.loads((STATE / "context-bundle.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    computed_at = raw.get("computed_at_et") if isinstance(raw, dict) else None
    if not computed_at:
        return None
    try:
        computed_dt = datetime.strptime(str(computed_at), "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return None
    age_min = (_et_now() - computed_dt).total_seconds() / 60.0
    if age_min > CONTEXT_BUNDLE_STALE_MIN:
        return None
    return raw


def _ribbon_df(closes: list[float]) -> pd.DataFrame:
    """lib.ribbon over a close series -> per-bar DataFrame (fast,pivot,slow,spread_cents,stack).
    EXACT backtest ribbon (spread = max-min across the 3 EMAs)."""
    return _ribbon_compute_df(pd.Series([float(c) for c in closes]))


def _ribbon_obj(closes: list[float]) -> dict | None:
    rdf = _ribbon_df(closes)
    if len(rdf) == 0:
        return None
    last = rdf.iloc[-1]
    if str(last["stack"]) == "UNKNOWN" or _nn(last["fast"]) is None:
        return None
    return {"fast": _nn(last["fast"]), "pivot": _nn(last["pivot"]), "slow": _nn(last["slow"]),
            "spread_cents": _nn(last["spread_cents"]), "stack": str(last["stack"])}


def _htf_15m_stack(df: pd.DataFrame) -> str | None:
    try:
        g = df.set_index("timestamp").resample("15min", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        if len(g) < 50:  # match orchestrator: need 48-EMA warmup on the 15m series
            return None
        rb = _ribbon_obj(g["close"].tolist())
        return rb["stack"] if rb else None
    except Exception:
        return None


def _rib_row(r) -> dict:
    """One ribbon DataFrame row (itertuples) -> JSON dict."""
    return {"fast": _nn(r.fast), "pivot": _nn(r.pivot), "slow": _nn(r.slow),
            "spread_cents": _nn(r.spread_cents), "stack": str(r.stack)}


def _rebuild_level_states(win: pd.DataFrame, n: int, levels_active: list, fhh: "float | None") -> dict:
    """STATELESS port of orchestrator._update_level_states (backtest/lib/orchestrator.py:123-210),
    replayed over the bounded window so the filter-10 sequence_rejection/reclaim triggers see the
    SAME role + bounce_history at the trigger bar. JSON-serializable plain dicts (LevelState fields);
    engine_cli.build_bar_context reconstructs them into LevelState objects. Thresholds are the
    orchestrator DEFAULTS (break=0.10, retest=0.30) — orchestrator.py:948 passes no override.
    Fed the SAME effective_levels the orch does (active + fhh)."""
    BREAK, RETEST = 0.10, 0.30
    eff = list(levels_active) + ([fhh] if fhh is not None else [])  # orchestrator effective_levels
    states: dict = {}
    highs = win["high"].astype(float).tolist()
    lows = win["low"].astype(float).tolist()
    closes = win["close"].astype(float).tolist()
    for i in range(n):  # replay EVERY window bar in order — bounce_history accumulates like the orch run
        hi, lo, cl = highs[i], lows[i], closes[i]
        for L in eff:
            key = f"{float(L):.4f}"
            st = states.get(key)
            if st is None:
                st = {"price": float(L), "role": None, "broken_at_bar_idx": None, "bounce_history": []}
                states[key] = st
            role = st["role"]
            if role is None:
                if cl < L - BREAK:
                    st["role"] = "broken_to_resistance"; st["broken_at_bar_idx"] = i; st["bounce_history"] = []
                elif cl > L + BREAK:
                    st["role"] = "broken_to_support"; st["broken_at_bar_idx"] = i; st["bounce_history"] = []
            elif role == "broken_to_resistance":
                if hi > L - RETEST:
                    outcome = "broken_back_through" if cl > L + BREAK else "rejected_close_below"
                    last = st["bounce_history"][-1] if st["bounce_history"] else None
                    if last is None or last.get("bar_idx") != i:
                        st["bounce_history"].append({"bar_idx": i, "high_reached": hi, "outcome": outcome})
                    if outcome == "broken_back_through":
                        st["role"] = None; st["broken_at_bar_idx"] = None; st["bounce_history"] = []
            elif role == "broken_to_support":
                if lo < L + RETEST:
                    outcome = "broken_back_through" if cl < L - BREAK else "rejected_close_above"
                    last = st["bounce_history"][-1] if st["bounce_history"] else None
                    if last is None or last.get("bar_idx") != i:
                        st["bounce_history"].append({"bar_idx": i, "low_reached": lo, "outcome": outcome})
                    if outcome == "broken_back_through":
                        st["role"] = None; st["broken_at_bar_idx"] = None; st["bounce_history"] = []
    return states


def _norm_no_trade_window(value) -> "list | None":
    """Canonical no_trade_window for the engine_cli payload: None, or a 2-element list.

    params.json carries entry_no_trade_window_et as null (Safe) or [] (Bold) to mean
    "no blackout window". engine_cli._coerce_score_kwargs (engine_cli.py:283-290) rejects
    ANY non-2-element list with BadPayload ("expected ['HH:MM','HH:MM']"), so the empty
    list must be coerced to None before it reaches bear_kwargs/bull_kwargs — otherwise the
    Bold verdict silently degrades to SKIP_BAD_INPUT. This mirrors the orchestrator's
    falsy-window->None reading (orchestrator.py:386-395) and the harness-side workaround
    (replay_fleet_arms.py:_norm_params). Only a genuine 2-element list/tuple passes through."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return list(value)
    return None


def _build_payload(df: pd.DataFrame, account_params: dict, *,
                   vix: tuple | None = None, levels: tuple | None = None,
                   vix_ma: tuple | None = None,
                   vix_intraday: list | None = None) -> dict | None:
    """Live by default; the historical replay injects `vix`=(now,prior),
    `levels`=(active,multi), `vix_ma`=(5d,20d), and `vix_intraday`=[5m VIX closes,
    newest last] so it can reproduce a past bar exactly."""
    # RTH-ONLY (>=09:30, <16:00 ET) BEFORE anything — the backtest computes its ribbon +
    # baselines on RTH-only bars (orchestrator.py:786-798, "matches the live indicator").
    # Extended-hours bars shift the EMAs 1-3c and flip the stack -> score drift. This is THE
    # alignment fix (2026-06-25): without it the historical replay was 42% score parity.
    _ts = pd.to_datetime(df["timestamp"]).dt.tz_convert("America/New_York")
    df = df[(_ts.dt.time >= time(9, 30)) & (_ts.dt.time < time(16, 0))].reset_index(drop=True)
    if len(df) < 80:
        return None
    W = 150  # bounded window: enough for trendline(60)/vol(20) lookbacks, cheap per tick
    win = df.iloc[-W:].reset_index(drop=True)
    n = len(win)
    # ribbon for EVERY bar via lib.ribbon (vectorized, full series so the 48-EMA seeds),
    # then slice the window -> ribbon_df the duration/momentum/flip gates walk (index-aligned).
    rib_win = _ribbon_df(df["close"].tolist()).iloc[-n:].reset_index(drop=True)
    ribbon_series = [_rib_row(r) for r in rib_win.itertuples()]
    if any(rr["fast"] is None for rr in ribbon_series):
        return None  # insufficient history to seed every ribbon row — fail safe, skip tick
    # TRIGGER = 2nd-to-last bar; the LAST bar is the forward-confirmation bar the
    # require_bearish_fill_bar gate reads as spy_df.loc[bar_idx+1] (matches the backtest).
    trig_idx = n - 2
    ribbon_now = ribbon_series[trig_idx]
    if ribbon_now["stack"] == "UNKNOWN" or ribbon_now["fast"] is None:
        return None
    trig = win.iloc[trig_idx]
    spy = float(trig["close"])
    vix_now, vix_prior = vix if vix is not None else _fetch_vix()
    vix_5d_ma, vix_20d_ma = vix_ma if vix_ma is not None else _fetch_vix_daily_ma()
    active, multi = levels if levels is not None else _read_levels(spy)
    bars_all = win[["open", "high", "low", "close", "volume"]].astype(float).to_dict("records")
    prior = bars_all[: trig_idx + 1]  # scoring history THROUGH the trigger bar — no look-ahead
    vol20 = float(win["volume"].iloc[max(0, trig_idx - 20):trig_idx].mean())
    rng20 = float((win["high"] - win["low"]).iloc[max(0, trig_idx - 20):trig_idx].mean())
    # first-hour-high supplement (orchestrator.py:922-945): max high of the trigger day's
    # 09:30-09:55 bars, usable as a level only after 10:05 ET. Fed as fhh_level -> the
    # fhh-rejection path of filter-10. Ported 2026-06-25 to close replay parity.
    fhh = None
    _tt = pd.to_datetime(trig["timestamp"])
    if _tt.time() >= time(10, 5):
        _dt = pd.to_datetime(df["timestamp"])
        _fh = df[(_dt.dt.date == _tt.date()) & (_dt.dt.time >= time(9, 30)) & (_dt.dt.time <= time(9, 55))]
        if len(_fh):
            fhh = round(float(_fh["high"].max()), 2)
    # level_states: replay orchestrator._update_level_states over the window THRU the trigger
    # bar (no look-ahead) so filter-10 sequence_rejection/reclaim see the same role+bounce_history.
    # Uses `active` (NOT multi) + fhh = orchestrator effective_levels. WINDOW-TRUNCATION CAVEAT:
    # the orch accumulates level_states from the FIRST bar of the multi-day run (never reset), so a
    # sequence whose break bar predates this 150-bar window will not reconstruct identically (a
    # 3-retest stairstep forms intra-session, so 150 bars covers the realistic case).
    _lwin = win.iloc[: trig_idx + 1].reset_index(drop=True)
    level_states = _rebuild_level_states(_lwin, len(_lwin), active, fhh)
    bar_ctx = {
        "bar_idx": trig_idx,
        "timestamp_et": trig["timestamp"].isoformat(),
        "bar": {"open": float(trig["open"]), "high": float(trig["high"]), "low": float(trig["low"]),
                "close": spy, "volume": float(trig["volume"])},
        "prior_bars": prior,
        "ribbon_now": ribbon_now,
        "ribbon_history": ribbon_series[max(0, trig_idx - 3):trig_idx + 1],
        "vix_now": vix_now, "vix_prior": vix_prior,
        "vol_baseline_20": vol20, "range_baseline_20": rng20,
        "levels_active": active, "multi_day_levels": multi,
        "htf_15m_stack": _htf_15m_stack(df.iloc[:-1]),  # full history thru trigger (no look-ahead)
        # ported 2026-06-25 to close replay parity; level_states + vix-MA now wired (no-op under
        # current params: VIX_DECLINING_REQUIRED_BEAR off, but faithful for when J flips the flag)
        "level_states": level_states, "fhh_level": fhh, "vix_5d_ma": vix_5d_ma, "vix_20d_ma": vix_20d_ma,
        # CONTEXT BUNDLE (Phase 0, 2026-07-14, LOGGED ONLY): pre-computed multi-timeframe
        # trend-alignment read (setup/scripts/context_bundle_producer.py, off the hot path,
        # 5-min RTH cadence). None when the producer file is missing/stale (see
        # _read_context_bundle's CONTEXT_BUNDLE_STALE_MIN). PURITY: build_bar_context
        # (backtest/lib/engine/engine_cli.py) reads ONLY its own named fields off bar_ctx —
        # this key is never one of them, so score_bar/evaluate_gates/_derive_tier never see
        # it. Zero-behavior-change by construction; tagged again onto `rec` in run_account
        # for the decision-row ledger. Guard: test_context_bundle_tag_no_behavior_change.py.
        "context_bundle": _read_context_bundle(),
    }
    gate_params = {k: account_params[k] for k in GATE_KEYS if k in account_params}
    # SCORE kwargs from params.json (filter_10 min_triggers, filter_9 vol_mult, time gates).
    # Without these engine_cli scores with DEFAULTS — the dominant replay score gap (fixed 2026-06-25).
    _vm = account_params.get("filter_9_vol_multiplier", 0.7)
    _times = {"no_trade_before": account_params.get("entry_no_trade_before_et") or "09:35",
              "no_trade_window": _norm_no_trade_window(account_params.get("entry_no_trade_window_et"))}
    score_params = {
        "enable_bullish": True,
        # bear's volume filter is f9; bull's is f10 (distinct kwarg names in evaluate_*_setup)
        "bear_kwargs": dict(_times, f9_vol_mult=_vm, min_triggers=account_params.get("filter_10_min_triggers_bear", 1)),
        "bull_kwargs": dict(_times, f10_vol_mult=_vm, min_triggers=account_params.get("filter_10_min_triggers_bull", 2)),
    }
    # Same-day 5m bars up to and including the trigger bar (for structure_veto_enabled).
    # Uses the full RTH `df` (not the bounded `win`) to capture bars from open onward.
    _trig_ts = pd.to_datetime(trig["timestamp"])
    _trig_date = _trig_ts.date()
    _df_ts = pd.to_datetime(df["timestamp"])
    _sameday_mask = (_df_ts.dt.date == _trig_date) & (_df_ts <= _trig_ts)
    _sd = df[_sameday_mask].copy()
    sameday_5m_bars = []
    for _, _r in _sd.iterrows():
        sameday_5m_bars.append({
            "open": float(_r["open"]), "high": float(_r["high"]),
            "low": float(_r["low"]), "close": float(_r["close"]),
            "volume": float(_r["volume"]),
            "timestamp_iso": str(_r["timestamp"].isoformat() if hasattr(_r["timestamp"], "isoformat")
                                 else _r["timestamp"]),
        })
    # vix_regime_dayside (edge #4) intraday VIX feed (G6). ONLY fetched when the setup is
    # ENABLED — the dispatch loop (setup_dispatch.py) skips _dispatch_vix_dayside entirely
    # while j_vix_dayside_enabled is false, so producer + consumer arm together: dormant =>
    # byte-identical no-op (no extra hot-path download, vix_intraday absent from bar_ctx).
    # Causally capped at the trigger bar; fail-open (None -> watcher SKIPs, never guesses).
    if account_params.get("j_vix_dayside_enabled"):
        _vi = vix_intraday if vix_intraday is not None else _fetch_vix_intraday(_trig_ts)
        if _vi:
            bar_ctx["vix_intraday"] = list(_vi)
    # Top-level frames the GATES walk via .loc (look-ahead fill-bar + momentum/duration).
    return {"bar_ctx": bar_ctx, "gate_params": gate_params, "score_params": score_params,
            "spy_df": bars_all, "ribbon_df": ribbon_series,
            "sameday_5m_bars": sameday_5m_bars}


def _engine_verdict(payload: dict) -> dict:
    """Pipe to the tested engine_cli (score_bar + 15 gates). Deterministic; fails closed."""
    try:
        proc = subprocess.run([sys.executable, "-m", "backtest.lib.engine.engine_cli"],
                              input=json.dumps(payload), capture_output=True, text=True,
                              cwd=str(REPO), timeout=30, creationflags=_CREATE_NO_WINDOW)
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return {"verdict": "SKIP_BAD_INPUT", "error": f"{type(e).__name__}: {e}"}


# ----- 2 free models: veto-only sanity layer ---------------------------------
def _veto_snapshot(bc: dict, verdict: dict) -> str:
    """Render the free-model veto sanity-check snapshot string from bar_ctx + a verdict dict.

    Extracted from _free_model_eval (2026-07-09 fix, GATE-PROVENANCE-CENSUS-2026-07-09.md #2)
    so it's independently testable without mocking swarm_client. `bear_score`/`bull_score`
    exist ONLY on core-ribbon verdicts (engine_cli's 0-10/0-11 rules-engine score) --
    extra-setup verdicts (_synthetic_verdict_from_extra) never carry them, because those
    are watcher-pattern detectors, not scored the same way. Render "bear=N/10"/"bull=N/11"
    ONLY when the value is real; OMIT rather than print the fabricated-looking "bear=None/10"
    that made 7/14 extra-setup vetoes on 2026-07-09 cite a malformed prompt as their stated
    reason. `side` is unaffected by this omission logic -- as of the same fix, both lanes
    always populate a real side, so it renders identically to before on the core path and
    now renders a real value (not None) on the extra-setup path.

    Byte-identical to the pre-fix inline string whenever bear_score AND bull_score are both
    present (the core-ribbon path, always true today) -- this is a pure extraction there.

    UNITS FIX (2026-07-15, false-veto class -- #1 participation sink, 55 VETOED_BY_MODELS
    blocks since 07-01, more than every directional gate combined; see
    markdown/audits/DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md section 3). The old
    rendering (`spread={cents}c`) was misread by the free models as an OPTION BID-ASK
    SPREAD IN DOLLARS -- it is actually the EMA-ribbon fast-vs-slow gap, in CENTS. Real
    example: the 2026-07-15T14:16:27 ET bold ENTER_BEAR (SPY=754.545, spread_cents=75.14,
    a directionally-correct call -- SPY closed 753.63) was vetoed with reason "spread value
    of 75.14 is implausibly large for SPY options (typical spreads are ~$0.10-$0.50),
    indicating a likely data entry error". The trailing "c" suffix alone was not enough
    disambiguation -- the model still read the bare number as a dollar figure. Fix: rename
    the label to `ribbon_width_cents=` and append an explicit, unmissable parenthetical
    stating the unit AND that it is NOT an option spread (mirrored in the sysmsg below).
    PRESENTATION-ONLY: `bc['ribbon_now']['spread_cents']` (the payload key) and the
    `spread_cents` field logged to core-decisions.jsonl by run_account() are UNCHANGED --
    every existing consumer of the logged decision row (including free_model_audit's
    collect_items, which reads spread_cents straight from the ledger) stays compatible.
    Guard: backtest/tests/test_veto_snapshot_units.py."""
    bear, bull = verdict.get("bear_score"), verdict.get("bull_score")
    scores = " ".join(s for s in (
        f"bear={bear}/10" if bear is not None else None,
        f"bull={bull}/11" if bull is not None else None,
    ) if s)
    setup_seg = f"setup={verdict.get('setup_name')}"
    if scores:
        setup_seg += f" {scores}"
    ribbon_width_cents = bc["ribbon_now"]["spread_cents"]
    return (f"SPY={bc['bar']['close']} ribbon={bc['ribbon_now']['stack']} "
            f"ribbon_width_cents={ribbon_width_cents} (EMA-ribbon fast-vs-slow gap in CENTS, "
            f"typical range 5-150c -- this is NOT an option bid-ask spread) "
            f"VIX={bc['vix_now']:.2f}(prior {bc['vix_prior']:.2f}) "
            f"HTF15m={bc['htf_15m_stack']} levels_near={bc['levels_active']} "
            f"rules_engine_says={verdict.get('verdict')} side={verdict.get('side')} "
            f"{setup_seg} triggers={verdict.get('triggers_fired')}")


def _free_model_eval(account: str, payload: dict, verdict: dict) -> dict:
    """2 FREE models each give GO/NO-GO on the rules-engine's ENTER. Veto only — they can
    block a marginal entry, never manufacture one. $0 (groq/cerebras/gemini free pool)."""
    try:
        import swarm_client as sc
    except Exception:
        return {"evaluated": False, "votes": [], "veto": False, "note": "swarm_client unavailable"}
    bc = payload["bar_ctx"]
    snap = _veto_snapshot(bc, verdict)
    # Only `go` is required — the aggregation below consumes go (bool) and never gates on
    # reason. Requiring reason discarded otherwise-valid votes as no_valid_json, because
    # reasoning lanes (nemotron/qwen3) routinely emit a bare {"go": true}. reason stays an
    # optional best-effort field for the ledger.
    schema = {"type": "object", "required": ["go"],
              "properties": {"go": {"type": "boolean", "description": "true = sane entry, false = veto"},
                             "reason": {"type": "string"}}}
    sysmsg = ("You are a 0DTE SPY options risk checker. A deterministic rules engine wants to ENTER. "
              "Your ONLY job: is this a SANE entry given the tape, or is something clearly off "
              "(chop, conflicting HTF, VIX spike, no real level)? You can only VETO a bad entry; "
              "you cannot create one. Default go=true unless something is clearly wrong. "
              "NOTE: ribbon_width_cents in the snapshot is the EMA ribbon's fast-vs-slow gap in "
              "CENTS (typical range 5-150c) -- it is NOT an option bid-ask spread; never veto "
              "just because that number looks like a large dollar spread. JSON only.")
    votes = []
    # Two distinct free lanes: coordinator (groq llama-3.1-8b) + critic (openrouter
    # nemotron-120b) — different provider AND model, so the veto stays independent even
    # if one provider is rate-limited. Both must be real roles in model-roster.json;
    # "analyst" is NOT a roster role (it aliases to "critic" in gamma_manager.ROLE_ALIAS),
    # so passing it raw made resolve_lanes raise KeyError every tick and silently halved
    # veto coverage to the single coordinator lane.
    for role in ("coordinator", "critic"):
        try:
            # max_tokens=800 (was 250): the critic lane (nemotron-120b) and the ollama
            # floor (qwen3) are reasoning models that spend tokens thinking before the JSON.
            # At 250 they were truncated mid-reasoning — the final JSON never landed AND
            # extract_json could scrape a wrong intermediate brace out of the unfinished
            # reasoning prose. 800 lets a reasoning lane finish and emit clean final JSON.
            env, out = sc.call_role_json(role, "Sanity-check this entry:\n" + snap, schema,
                                         system=sysmsg, max_tokens=800, task_id="core_eval")
            if out:
                votes.append({"lane": env.get("lane"), "go": bool(out.get("go")), "reason": out.get("reason", "")[:160]})
            else:
                # Lane resolved but returned no schema-valid JSON (parse/validation miss).
                # Record it as an answered-but-empty lane so it's visible, not silent.
                votes.append({"lane": env.get("lane") or role, "error": "no_valid_json"})
        except Exception as e:  # noqa: BLE001
            # A lane that errors (unmapped roster role, model down, timeout) is logged with
            # FULL detail (type + message) and skipped — it never crashes veto aggregation
            # (the answered-lane logic below tolerates a missing "go" key and fails open to
            # veto=false). str(e) is kept so a recurring config bug is diagnosable from the
            # ledger instead of a bare, uninformative "KeyError".
            votes.append({"lane": role, "error": f"{type(e).__name__}: {e}"})
    gos = [v for v in votes if v.get("go") is True]
    no = [v for v in votes if v.get("go") is False]
    # Veto if BOTH models that answered say NO-GO (unanimous veto); 1 dissent allowed.
    answered = [v for v in votes if "go" in v]
    veto = len(answered) >= 1 and len(gos) == 0 and len(no) >= 1
    return {"evaluated": True, "votes": votes, "veto": veto}


# ----- persistence -----------------------------------------------------------
def _log(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _write_tick_marker(core_tick_id: str, et: datetime) -> None:
    """RACE FIX (2026-08-01, WEEKEND-TWELVE #4). Called from main() ONLY after BOTH accounts
    logged a real (non-exception) row this invocation -- see main()'s ok_accounts check. That
    ordering is what makes the marker trustworthy: by the time this runs, both `_log()` calls
    above have already returned, and each one's `with open(LEDGER, "a") as f: ...` context has
    already closed (flushed) before returning -- so any reader that resolves a row via this
    marker's core_tick_id is guaranteed that row already exists on disk.

    Atomic write (temp file + os.replace): os.replace is a single filesystem rename, all-or-
    nothing on both NTFS and POSIX, so a concurrent reader on its own independent cadence
    (Gamma_FleetExecutor, every 3 min -- NOT synchronized with this 1-min task) can never
    observe a torn/partial marker file.

    Fails open: any error here is swallowed -- a missed marker update just means the NEXT
    tick's readers keep using the prior complete tick (never a crash, never a half-tick
    surfaced). This is a pure visibility/pairing instrument; it never gates ARMED/placement."""
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        payload = {"core_tick_id": core_tick_id, "date": et.strftime("%Y-%m-%d"),
                   "ts_et": et.strftime("%Y-%m-%dT%H:%M:%S"), "accounts": sorted(ACCOUNTS)}
        tmp = TICK_MARKER.with_name(TICK_MARKER.name + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, TICK_MARKER)
    except Exception:  # noqa: BLE001 -- visibility instrument must never abort the tick
        pass


def _ribbon_flip_fn(ribbon_stack: str):
    """Return a ribbon_flip_back_fn for exit_actuator.manage_tick.
    Fires when the ribbon reverses against the open position's direction:
      PUT (bearish): exits when ribbon turns BULL.
      CALL (bullish): exits when ribbon turns BEAR.

    G14 FIX (2026-07-01): the producer (backtest/lib/ribbon.py) emits stack ==
    'BULL'|'BEAR'|'MIXED'|'WARMUP'|'UNKNOWN' — NEVER 'BULLISH'/'BEARISH'. The old
    literals could not match any real ribbon_now['stack'], so the v15.3 chart-stop-
    PRIMARY ribbon-flip-back invalidation silently never fired (C14 string-mismatch
    dead-knob; only the −50% catastrophe cap / target / time stops ran). MIXED/UNKNOWN
    correctly do NOT flip (a genuine opposite-direction reversal, not loss-of-stack).
    Guard: test_graduated_guards.py::test_g14_ribbon_flip_fn_direction (imports the REAL
    fn + asserts against the producer's actual literals).
    """
    def fn(symbol: str, side: str) -> bool:  # noqa: ANN001
        return ribbon_stack == ("BULL" if side == "P" else "BEAR")
    return fn


def _manage_exits(account: str, ribbon_stack: str | None = None,
                  time_stop_et=None, last_closed_5m_close: float | None = None) -> list:
    """Run the tick-managed scale-out over this account's open positions (flag-gated caller).
    Places only when ARMED (live); WATCH otherwise. Fail-safe: any error is captured, never
    raised, so the exit pass can never abort the entry/verdict path of the armed brain.

    `time_stop_et` is params.json's ``time_stop_et`` value, forwarded to the actuator so the
    per-account hard time-stop knob is LIVE (FIX 2026-07-07: was ignored -> hard-coded 15:50).

    `last_closed_5m_close` (2026-07-09, STRUCTURE-STOP) is the trigger bar's close (or None
    when the caller judged it stale/cross-session) -- forwarded to the shared exit_actuator,
    which only consults it for a position whose stop_mode resolved to "structure" at entry."""
    try:
        import fleet_broker as fb  # noqa: PLC0415
        import exit_actuator as ea  # noqa: PLC0415
        arm = ACCOUNTS[account]["fleet_arm"]
        creds = fb.load_creds().get(arm)
        if not creds:
            return [{"error": "no_creds", "arm": arm}]
        flip_fn = _ribbon_flip_fn(ribbon_stack) if ribbon_stack else None
        return ea.manage_tick(arm, creds, live=ARMED, now_et=_et_now(), ribbon_flip_back_fn=flip_fn,
                              time_stop_et=time_stop_et, last_closed_5m_close=last_closed_5m_close)
    except Exception as e:  # noqa: BLE001
        return [{"error": f"manage_exits: {type(e).__name__}: {e}"}]


def _adoption_ping(arm: str, sym: str, qty: int, side: str) -> None:
    """Discord ping when the engine ADOPTS a manual position (D2 2026-07-07) so J is never
    surprised his trade is now engine-managed. Fires once per newly-adopted symbol (adoption
    is idempotent — already-tracked symbols are skipped). Fail-safe: an outbox-write failure
    never aborts adoption."""
    try:
        from datetime import datetime, timezone  # noqa: PLC0415
        row = {"queued_at": datetime.now(timezone.utc).isoformat(),
               "content": (f"Gamma adopted your manual {sym} x{qty} "
                           f"({'PUT' if side == 'P' else 'CALL'}) on {arm} — managing "
                           f"CAP-ONLY (-50% cat-cap + 15:50 flatten, no TP1/trail). "
                           f"You drive the exit; reply to override.")}
        with (STATE / "discord-outbox.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001 — alerting must never abort adoption
        print(f"[adopt] ping failed: {type(e).__name__}: {e}", file=sys.stderr)


def _adopt_untracked_positions(arm: str, creds: dict, positions: list) -> list:
    """FIX1 (2026-07-07, J: "get rid of the lockout") — MANUAL/ENGINE COEXISTENCE.

    When the engine sees an OPEN SPY-option position it did not itself place/track (e.g. a
    manual 'gamma-manual-' trade), it ADOPTS that position into the exit_manager so the
    engine MANAGES its exit instead of sitting frozen all day. This does NOT relax the
    no-stack protection: the caller still refuses to open a 2nd position while any is open
    (Rule-6 per-trade risk cap) — adoption only wires the manual trade's EXIT, it never
    authorizes a stacked entry.

    Idempotent: a symbol already carried in the exit-state ledger is left untouched (its
    evolving tp1_filled / hwm / runner_stop state is preserved — re-registering would reset
    it). Only genuinely-untracked open symbols are registered with a CAP-ONLY exit shape
    (-50% catastrophe cap + 15:50 time-stop ONLY; NO TP1 / chandelier / ribbon-flip — D2
    2026-07-07: the engine never imposes its own exit on a trade J originated). A Discord
    ping fires once per newly-adopted symbol so J is never surprised it is engine-managed.
    Fail-safe: any error is captured and returned, never raised — adoption must never abort
    the FLAT-verify / no-stack guard. Returns a list of per-symbol adoption records.
    Guard: test_audit_fix_heartbeat.py::TestManualCoexistence + TestAdoptedShapeCapOnly."""
    out: list = []
    try:
        import exit_actuator as ea  # noqa: PLC0415
        tracked = set(ea.load_states(arm).keys())
        for p in positions or []:
            sym = str(p.get("symbol", ""))
            if not sym or sym in tracked:
                continue  # idempotent: don't clobber an already-managed position's state
            try:
                entry_px = abs(float(p.get("avg_entry_price") or 0.0))
                qty = abs(int(float(p.get("qty") or 0)))
            except (TypeError, ValueError):
                out.append({"symbol": sym, "adopted": False, "reason": "unparseable_position"})
                continue
            if qty < 1 or entry_px <= 0:
                out.append({"symbol": sym, "adopted": False, "reason": "no_qty_or_premium"})
                continue
            opt_side = "P" if sym[-9:-8] == "P" else "C"  # OCC: SPY<yymmdd><C|P><strike*1000>
            # D2 (2026-07-07): adopted MANUAL positions get CAP-ONLY management. The engine
            # NEVER imposes its own TP/chandelier on a trade J originated (today J scalped
            # 80% + rode runners to 2.5x; a +30% TP1 would have cut his runner). Setting
            # tp1_qty_fraction=0.0 -> tp1_qty=int(qty*0)=0 -> TP1 never fires -> the post-TP1
            # profit-lock never arms. What REMAINS: the -50% catastrophe cap + the 15:50
            # time-stop/EOD-flatten. Ribbon-flip is separately excluded for strategy
            # "adopted_manual" in exit_actuator.manage_tick. J drives the exit; the engine
            # only prevents catastrophe and guarantees the 0DTE is flat by the close.
            shape = {"premium_stop_pct": -0.50, "tp1_premium_pct": 0.30,
                     "tp1_qty_fraction": 0.0, "profit_lock_mode": "none"}
            ea.register_entry(arm, symbol=sym, side=opt_side, entry_premium=entry_px,
                              qty=qty, exit_shape=shape, strategy="adopted_manual")
            _adoption_ping(arm, sym, qty, opt_side)
            out.append({"symbol": sym, "adopted": True, "side": opt_side,
                        "qty": qty, "entry_premium": entry_px, "exit": "cap_only"})
    except Exception as e:  # noqa: BLE001 — adoption must never abort the no-stack guard
        out.append({"error": f"adopt: {type(e).__name__}: {e}"})
    return out


# --- SCORE LADDER hook for the CORE arms (2026-07-27, J: "I specifically said I wanted
# seven out of ten and eight out of tens being traded") -----------------------------------
# The fleet arms (risky-3/risky-1/safe-3) already got this lane via
# automation/state/fleet/build_shared_signal.py#_ladder_block +
# automation/state/fleet/fleet_executor.py#_ladder_plan (commits deb781ea/d6fc72a6) -- but
# safe-2/bold-2 execute HERE, directly (mcp/REST inside run_account/_execute), not through
# fleet_executor, so the ladder needs its own hook on the CORE verdict. Same fail-closed
# contract as the fleet twin, collapsed into ONE function because run_account already HAS
# the raw verdict in hand (no separate producer/ledger-row round-trip needed here).
#
# J's 7/8/8/9/9 spec: safe (Gamma-Safe-2) floor=9, bold (Gamma-Bold-2) floor=8 -- each
# account's OWN params.json carries its own score_ladder_floor (see that key's
# _score_ladder_floor_doc in params.json / aggressive/params.json). BEAR ONLY -- bull
# waits for its own pre-registered evidence (2026-07-27's bull-9 fired mid-fade and would
# have lost); every check below is inherently bear-only (it never reads a bull_* field),
# so there is no bull mirror to accidentally wire in.
#
# FAIL-CLOSED (mirrors fleet's _ladder_block_from_row + _ladder_plan gates exactly):
#   * params has no (or non-numeric) score_ladder_floor      -> unchanged (REVOKE path:
#                                                                 delete the key, next
#                                                                 tick reverts byte-
#                                                                 identical)
#   * verdict isn't a plain scoring HOLD ("no setup passed
#     scoring" in reason)                                    -> unchanged (gate-skip
#                                                                 verdicts like
#                                                                 SKIP_STRUCTURE_VETO and
#                                                                 real ENTERs stay untouched)
#   * bear_score missing/non-numeric or < floor               -> unchanged
#   * bear_triggers_raw has no LEVEL-TIED member               -> unchanged
#   * bear_rejection_level_raw missing/non-numeric             -> unchanged (no stop
#                                                                 anchor, no trade)
# Any single failure returns the SAME verdict object, unmutated -- this function never
# mutates its input, it only ever returns it unchanged or builds a NEW dict (repo
# immutability convention). A caller can `is`-compare before/after to know whether the
# ladder fired, which is exactly how run_account tags entry_lane below.
LADDER_LEVEL_TIED = frozenset({"level_rejection", "fhh_level_rejection", "confluence",
                               "sequence_rejection"})


# ── BLINDNESS BLOCK — SKIP_NO_LEVELS (2026-07-30) ────────────────────────────────────
# THE INCIDENT (2026-07-30): Gamma_LevelRefresh last fired 2026-07-29 20:43 ET, so
# automation/state/key-levels.json still carried yesterday's date and EVERY level in it an
# expires_at of 2026-07-29. _read_levels' expiry filter (_level_expired) did its job
# CORRECTLY and returned ([], []) -- the read was right, the DATA was 19.8h stale. Result:
# levels_active == [] on 386 of 386 safe rows (yesterday: 0 of 375).
#
# WHAT THE ENGINE DID WITH NO EYES: nothing. It did not halt, warn, or degrade. With no
# levels, detect_level_rejection cannot fire, so scoring fell through to the ONLY bear
# trigger that survives blindness -- trendline_rejection -- and the engine silently switched
# to its statistically WORST entry mode: the trendline-only cohort is -$1,830 / WR .19 over
# 124 trades and 89% of every bear ENTER verdict ever recorded, while every dollar the engine
# has ever made is level-tied (+$6,895 / 66 trades)
# (analysis/deep-research/PNL-ATTRIBUTION-2026-07-28). At 11:31-11:46 ET it produced 11
# ENTER_BEAR verdicts at SPY 734.885 -- the LOW OF THE DAY, tier TRENDLINE,
# trigger_level_exact null, triggers [ribbon_flip, trendline_rejection]. SPY then rallied to
# 741.6 into the close: ~-6.7 SPY points wrong. Only RISK_DENY_RISK_CAP / RISK_DENY_PDT
# stopped the fills -- luck, not design.
#
# THE RULE: blind must mean DO NOT TRADE, never "trade the worst cohort". When the engine
# has no usable levels, an ENTER with no level anchor becomes SKIP_NO_LEVELS.
#
# WHY *not* "block every entry when blind": fhh_level_rejection (the first-hour-high
# supplement, computed from TODAY'S OWN BARS in _build_payload -- not from key-levels.json)
# can still fire with levels_active empty, and it is a genuine, price-anchored, level-tied
# trigger from the PROFITABLE cohort. Blocking it would suppress a sighted entry and turn a
# safety rail into an edge change. The rail therefore blocks exactly the cohort the incident
# exposed: an entry with NO price anchor at all.
#
# LEVEL_ANCHOR_TRIGGERS is LADDER_LEVEL_TIED (bear) plus the bull-side names. Deliberately
# EXCLUDED: "trendline_rejection" and "ribbon_flip" -- those two ARE the blind cohort
# (filters.py sets `rejection_level` only from detect_level_rejection/wick/fhh; a
# trendline_rejection never populates it, which is exactly why today's 11:31 row carried
# trigger_level_exact null). Note filters.py has its OWN local `level_tied` set for
# filter-10 that DOES include trendline_rejection -- that one answers "is this more than a
# bare ribbon flip", a different question. Do not merge them.
LEVEL_ANCHOR_TRIGGERS = frozenset(LADDER_LEVEL_TIED | {"level_reclaim", "sequence_reclaim"})


def _is_blind(bar_ctx: dict) -> bool:
    """True when the engine has NO usable key levels this tick.

    FAIL-CLOSED (house rule: fail-open for MONITORING, fail-CLOSED for ENTRY): a MISSING
    levels_active key counts as blind, not as "unknown, proceed". In production the key is
    always present -- _build_payload writes `"levels_active": active` unconditionally -- so
    absence only ever means a synthetic/partial payload, and a payload that cannot state
    what the engine can see must never be allowed to authorize an entry.
    """
    return not (bar_ctx.get("levels_active") or [])


def _level_anchored(verdict: dict) -> bool:
    """True when the winning entry has a real PRICE ANCHOR to trade and stop against.

    Two independent sources, either one sufficient:
      1. a level-tied trigger name in the winning side's triggers_fired, and
      2. a numeric `rejection_level` (engine_cli's winning-side level provenance, logged as
         trigger_level_exact) -- this is what keeps a synthetic extra-setup verdict that
         carries its own concrete level (e.g. VIX_REGIME_DAYSIDE @746.87) correctly
         classified as anchored even though its trigger names are not core-ribbon names.
    A trendline-only entry satisfies NEITHER (proven by today's 11:31 row: triggers
    [ribbon_flip, trendline_rejection], trigger_level_exact null).
    """
    trigs = [t for t in (verdict.get("triggers_fired") or []) if isinstance(t, str)]
    if any(t in LEVEL_ANCHOR_TRIGGERS for t in trigs):
        return True
    return isinstance(verdict.get("rejection_level"), (int, float))


def _blind_block_enabled(params: dict) -> bool:
    """The `block_entries_when_blind` flag. DEFAULT TRUE, including when the key is ABSENT.

    This ships ON because it is a SAFETY RAIL, not an edge experiment -- the failure it
    prevents (shorting the low of the day with no eyes) is unbounded, while the cost of a
    false positive is one skipped trade in the cohort that has lost money on 124 of 124
    measured trades. Only a literal JSON `false` disables it; a null/garbage value still
    blocks (fail-closed).

    REVOKE PATH (no restart, no deploy): add `"block_entries_when_blind": false` to
    automation/state/params.json (Safe) and/or automation/state/aggressive/params.json
    (Bold). run_account re-reads params from disk on EVERY tick, so the next 1-minute
    heartbeat reverts to the exact pre-2026-07-30 behavior.
    """
    return (params or {}).get("block_entries_when_blind", True) is not False


def _apply_score_ladder(verdict: dict, params: dict) -> dict:
    """Pure verdict -> verdict rescue for a SCORING-failed bear tick. See the module
    comment directly above for the full fail-closed contract. Returns the ORIGINAL
    verdict object unchanged when any condition fails; returns a NEW dict
    (verdict="ENTER_BEAR", side="P", setup_name="BEARISH_REJECTION_RIDE_THE_RIBBON",
    rejection_level=<the raw detection's own level>, quality_tier="LADDER",
    entry_lane="score_ladder", reason PREPENDED with the ladder provenance) when the
    ladder fires. Never touches sizing/risk_gate/exit registration -- those stay entirely
    inside _execute, reached only via the normal ENTER_BEAR path this function reroutes
    into (the caller applies this BEFORE any of the entry-ceiling/floor/staleness/free-
    model-veto/risk_gate checks, so a ladder entry clears every guard an organic
    ENTER_BEAR clears).
    Guard: backtest/tests/test_core_score_ladder.py."""
    floor = (params or {}).get("score_ladder_floor")
    if floor is None:
        return verdict
    try:
        floor_i = int(floor)
    except (TypeError, ValueError):
        return verdict
    if verdict.get("verdict") != "HOLD":
        return verdict
    reason = str(verdict.get("reason") or "")
    if "no setup passed scoring" not in reason:
        return verdict
    score = verdict.get("bear_score")
    if not isinstance(score, (int, float)) or score < floor_i:
        return verdict
    raw = [t for t in (verdict.get("bear_triggers_raw") or []) if isinstance(t, str)]
    if not any(t in LADDER_LEVEL_TIED for t in raw):
        return verdict
    level = verdict.get("bear_rejection_level_raw")
    if not isinstance(level, (int, float)):
        return verdict
    new = dict(verdict)
    new["verdict"] = "ENTER_BEAR"
    new["side"] = "P"
    new["setup_name"] = "BEARISH_REJECTION_RIDE_THE_RIBBON"
    new["rejection_level"] = float(level)
    new["quality_tier"] = "LADDER"
    new["entry_lane"] = "score_ladder"
    new["reason"] = (f"SCORE_LADDER floor={floor_i} score={int(score)} "
                     f"blockers={verdict.get('bear_blockers')}: {reason}")
    return new


def run_account(account: str, core_tick_id: str | None = None) -> dict:
    """`core_tick_id` (2026-08-01, WEEKEND-TWELVE #4 race fix): the SAME id main() generates
    once per invocation and passes to every account's run_account call this tick -- purely
    additive ledger field (older rows / any direct caller that omits it get None, unchanged).
    Lets a reader pair the safe+bold rows that belong together instead of two independent
    last-row-per-account scans. See TICK_MARKER's module comment for the full incident."""
    cfg = ACCOUNTS[account]
    params = json.loads(cfg["params"].read_text(encoding="utf-8"))
    df = _fetch_spy_5m()
    payload = _build_payload(df, params)
    et = _et_now()
    if payload is None:
        rec = {"ts_et": et.strftime("%Y-%m-%dT%H:%M:%S"), "account": account,
               "verdict": "SKIP_NO_DATA", "armed": ARMED, "core_tick_id": core_tick_id}
        _log(rec)
        return rec
    verdict = _engine_verdict(payload)
    bc = payload["bar_ctx"]
    rec = {"ts_et": et.strftime("%Y-%m-%dT%H:%M:%S"), "account": account, "armed": ARMED,
           "core_tick_id": core_tick_id,
           "spy": bc["bar"]["close"], "ribbon": bc["ribbon_now"]["stack"],
           "spread_cents": bc["ribbon_now"]["spread_cents"], "vix": round(bc["vix_now"], 2),
           "htf_15m": bc["htf_15m_stack"], "verdict": verdict.get("verdict"),
           "side": verdict.get("side"), "setup": verdict.get("setup_name"),
           "bear_score": verdict.get("bear_score"), "bull_score": verdict.get("bull_score"),
           "triggers": verdict.get("triggers_fired"), "reason": verdict.get("reason"),
           # WHY-NOT PROVENANCE (2026-07-27, TRIGGER-BLINDNESS). LOGGED ONLY, additive.
           #
           # THE INCIDENT: on 2026-07-27 the engine detected J's setup perfectly at 09:40
           # (level_rejection @744.9 + confluence, bear_score 9/10) and refused it on ONE
           # structural blocker -- filter 5, ribbon not BEAR-stacked. The ledger showed
           # `triggers: []`, which cost hours of investigation and sent a 6-agent teardown
           # down a false "the detectors are blind" path.
           #
           # ROOT OF THE BLINDNESS: `triggers` above is engine_cli's WINNING-side list --
           # _derive_routing (engine_cli.py:458-474) returns (None, [], None) whenever
           # NEITHER side passes, so `triggers: []` is genuinely ambiguous between
           # "detected nothing" and "detected everything and got hard-blocked". The raw
           # per-side detections and the blocker list were BOTH already computed and
           # returned by decide_payload (engine_cli.py:565-566) and simply dropped here.
           #
           # These four keys make a no-trade tick self-explaining: blockers say WHICH rule
           # refused it, *_triggers_raw say what the detectors actually saw regardless of
           # who won routing. Never influences verdict/side/gate -- pure telemetry (same
           # contract as shadow_triggers_fired above). Consumers must treat a missing key
           # as "older row shape", never as an empty detection.
           #
           # NOTE for anyone reading trigger counts: "trigger-ticks per day" computed off
           # `triggers` counts scoring PASSES, not detections, and will report a fully
           # sighted engine as blind. Use bear_triggers_raw/bull_triggers_raw instead.
           "bear_blockers": list(verdict.get("bear_blockers") or []),
           "bull_blockers": (None if verdict.get("bull_blockers") is None
                             else list(verdict.get("bull_blockers"))),
           "bear_triggers_raw": list(verdict.get("bear_triggers_raw") or []),
           "bull_triggers_raw": list(verdict.get("bull_triggers_raw") or []),
           # SCORE-LADDER (2026-07-27): the raw detection's own level, so a ladder entry on a
           # blocked tick has a real stop anchor (trigger_level_exact above is winning-side
           # only and None whenever nothing passed).
           "bear_rejection_level_raw": verdict.get("bear_rejection_level_raw"),
           "bull_reclaim_level_raw": verdict.get("bull_reclaim_level_raw"),
           "levels_active": list(bc.get("levels_active") or []),
           # BLINDNESS FLAG (2026-07-30, SKIP_NO_LEVELS). LOGGED ON EVERY ROW, additive,
           # mirroring the why-not provenance fields above. `levels_active: []` already
           # implied this, but only to a reader who knew to look -- on 2026-07-30 it sat
           # empty on 386 of 386 rows and nothing named the condition, so no monitor, no
           # digest and no engine-health surface could ever have alerted on it. A named
           # boolean makes "was the engine blind?" greppable forever, on blocked AND
           # unblocked ticks alike (it is logged independently of whether the block fired,
           # so a revoked flag still leaves the evidence trail intact).
           "blind": _is_blind(bc),
           # LEVEL PROVENANCE (G12, 2026-07-09 night): the EXACT level the winning side's
           # entry trigger fired against -- ground truth from filters.detect_level_rejection/
           # detect_level_reclaim (backtest/lib/filters.py), threaded verbatim through
           # score_bar -> engine_cli._derive_routing -> decide_payload's "rejection_level"
           # (the SAME key names both bear-rejection and bull-reclaim; see engine_cli.py
           # docstring/_derive_routing). None whenever the winning side had no level-tied
           # trigger (e.g. a TRENDLINE-tier entry) or on a HOLD/SKIP tick -- consumers must
           # treat that as "no exact level available" and fall back to the proximity
           # heuristic (exit_manager.nearest_active_level), never guess. DATA-ADDITIVE: a
           # new key: every existing core-decisions.jsonl reader ignores unknown keys.
           "trigger_level_exact": verdict.get("rejection_level"),
           # SHADOW TRIGGERS (2026-07-19, TRENDLINE-FIXES item 4, LOGGED ONLY --
           # queue.md's "thread shadow_triggers_fired into core-decisions.jsonl" ask).
           # engine_cli's decide_payload already tags every tick with the bull side's
           # shadow-only detections (trendline_reclaim/wick_reclaim -- see
           # filters.BullishSetupResult.shadow_triggers_fired); this was computed every
           # tick but discarded before this change (never read past the engine_cli
           # subprocess boundary). Zero-behavior-change: purely additive key, DATA-ONLY,
           # never influences verdict/triggers/side/gate. [] when absent (older verdict
           # shape / bull scoring disabled) -- consumers must treat missing/[] as "no
           # shadow signal this tick", never guess.
           "shadow_triggers_fired": list(verdict.get("shadow_triggers_fired") or []),
           # CONTEXT BUNDLE (Phase 0, 2026-07-14, LOGGED ONLY -- see the matching bar_ctx
           # comment above and context_bundle_producer.py). Tagged straight off the payload
           # so the decision-row ledger carries the SAME bundle (or None) the engine payload
           # did this tick -- never recomputed, never re-read, so the two can't drift.
           "context_bundle": bc.get("context_bundle"),
           # SIGHT PROVENANCE (DECISION-ROW-SPY-STALENESS, 2026-07-20): the trigger bar's own
           # timestamp, now logged on EVERY row (previously only stamped in the
           # SKIP_STALE_TRIGGER branch below). `spy` above IS this bar's close -- by
           # construction it is exactly as old as (now_et - trigger_bar_et), typically
           # 5-10 minutes (trig_idx = n-2 in _build_payload). Purely additive/visibility --
           # answers "how stale was this row's spot" without a cross-reference investigation.
           "trigger_bar_et": str(bc.get("timestamp_et"))}
    # EXIT-MANAGEMENT PASS (flag-gated, default OFF -> byte-identical armed behavior).
    # Manage every open position's scale-out FIRST (before evaluating a new entry), so a
    # winner's TP1/runner or a stop is realized this tick. Places only when ARMED (live);
    # otherwise computes + logs (WATCH). OFF unless GAMMA_CORE_MANAGES_EXITS=1.
    if CORE_MANAGES_EXITS:
        # STRUCTURE-STOP (2026-07-09): bc["bar"]["close"] IS a closed 5m bar (trig_idx = n-2
        # in _build_payload -- there is always a more-recent confirmation bar past it), and
        # _stale_trigger_bar (the SAME guard the entry path already uses) catches the one
        # cross-session edge case (a stale bar carried at the open before enough bars have
        # accumulated today). Fail-open: None -> the structure check simply skips this tick.
        _closed_5m_close = None if _stale_trigger_bar(payload, et) else bc["bar"]["close"]
        rec["exit_pass"] = _manage_exits(account, ribbon_stack=bc["ribbon_now"].get("stack"),
                                         time_stop_et=params.get("time_stop_et"),
                                         last_closed_5m_close=_closed_5m_close)
    # EXTRA-SETUP DISPATCH — evaluates 4 validated detectors that are individually
    # flag-gated in params.json. When ALL flags are OFF (current default) this is a
    # pure no-op: dispatch_extra_setups returns [] in O(1). When a flag is ON, the
    # matching detector builds its own BarContext from sameday_5m_bars, runs the
    # watcher, and logs the result. Order placement via these signals is NOT wired here
    # yet — SKIP_NO_FEED / SKIP_NO_SIGNAL are the expected outputs until each detector
    # is promoted to LIVE. This call must never raise (setup_dispatch fails open).
    extra: list = []
    try:
        from setup_dispatch import dispatch_extra_setups  # noqa: PLC0415
        extra = dispatch_extra_setups(account, params, payload, verdict, armed=ARMED)
        if extra:
            rec["extra_signals"] = extra
    except Exception as _disp_err:  # noqa: BLE001
        logger.warning("[DISPATCH] setup_dispatch import/run failed: %s", _disp_err)

    # SCORE LADDER (2026-07-27): core-arm hook -- rescue a SCORING-failed bear tick per
    # J's 7/8/8/9/9 spec (see _apply_score_ladder's docstring above for the full
    # fail-closed contract). Placed HERE -- after every decision-row field above is
    # computed, AND after the extra-setup dispatch just above has already run off the
    # ORIGINAL verdict (dispatch_extra_setups' own detectors read their own
    # sameday_5m_bars slice, never the `verdict` param, so ordering relative to them is
    # inert either way; kept last, not first, for minimal blast radius) -- and BEFORE `v`
    # below claims the execution branch, so a ladder rewrite rides the EXACT SAME
    # untouched path (stale-trigger/entry-ceiling/entry-floor/sight-staleness guards,
    # free-model veto, then _execute's own FLAT-verify + risk_gate + settlement/PDT/
    # kill-switch checks) any organic ENTER_BEAR clears -- _execute/sizing/risk_gate/exit
    # registration are UNTOUCHED by this hook. `_apply_score_ladder` returns the SAME
    # object when it doesn't fire (`is`-comparable), so the ledger resync below only
    # touches the row on an actual rescue.
    _pre_ladder_verdict = verdict
    verdict = _apply_score_ladder(verdict, params)
    if verdict is not _pre_ladder_verdict:
        # Ledger honesty (OP-33): the row's verdict/reason/side/setup/trigger_level_exact
        # must show the REWRITTEN values -- entry_lane below is the discriminator that
        # lets analytics separate this from an organic pass (the verdict fields alone are
        # deliberately indistinguishable from an organic ENTER_BEAR, per design).
        rec["verdict"] = verdict.get("verdict")
        rec["side"] = verdict.get("side")
        rec["setup"] = verdict.get("setup_name")
        rec["reason"] = verdict.get("reason")
        rec["trigger_level_exact"] = verdict.get("rejection_level")
        rec["entry_lane"] = "score_ladder"

    v = verdict.get("verdict", "")
    # FIX (2026-07-10, GATE-PROVENANCE-SWEEP): staleness must be resolved BEFORE any
    # verdict/gate name can claim this tick's logged action. evaluate_gates() (the 15
    # GATE_ORDER gates, run inside _engine_verdict's engine_cli subprocess call above)
    # scores + gates the payload's trigger bar regardless of whether that bar is from
    # TODAY's session -- at the open, a carried-over prior-session bar can satisfy a
    # GATE_ORDER time-window gate's own predicate (e.g. block_conf_lvl_rec_afternoon's
    # `bt.time() >= 14:00`, true for a bar legitimately timestamped 15:55 ET *yesterday*)
    # and return a named SKIP_* verdict that reads as a live block. The OLD ladder only
    # ever re-checked staleness when `v` was ALREADY ENTER_BEAR/ENTER_BULL, so a
    # gate-produced SKIP_* (or even HOLD) fell straight through to the `else: rec["action"]
    # = v` branch at the bottom of this ladder and was logged under the gate's own name
    # instead of SKIP_STALE_TRIGGER (proven 2026-07-10: SKIP_CONF_LVL_REC_AFTERNOON fired
    # bold 09:31-09:35 ET on a bar timestamped 2026-07-09T15:55 -- SAFE's independent
    # SKIP_STALE_TRIGGER row on the SAME bar at the SAME instants is the smoking gun).
    # Checking staleness FIRST -- unconditional on `v`, ahead of every branch below --
    # guarantees a stale trigger bar is ALWAYS logged as SKIP_STALE_TRIGGER, whatever
    # verdict/gate name evaluate_gates produced for it.
    #
    # gates.py / engine_cli.py are deliberately UNTOUCHED: decide_payload/evaluate_gates
    # are PURE and SHARED with the backtest orchestrator (reused there as the parity-
    # oracle assert-agree check) -- "staleness relative to the live wall clock" has no
    # backtest equivalent (a backtest bar legitimately IS "now" for that simulated tick),
    # so threading it into the shared engine would risk backtest determinism for zero
    # benefit. heartbeat_core.py's post-verdict ladder is LIVE-only (already keyed off
    # _et_now(), a live wall-clock read) -- the correct and smallest seam.
    #
    # Row shape for this branch is byte-for-byte the same 2 lines as the pre-fix
    # ENTER_*-gated branch it replaces -- only WHEN it fires changed, never the shape.
    # Fresh (today's) bars are a complete no-op here (_stale_trigger_bar is False), so the
    # rest of this ladder is untouched for every tick that isn't stale.
    # See markdown/audits/GATE-PROVENANCE-SWEEP-2026-07-10.md.
    # Guard: test_gate_provenance_ordering_2026_07_10.py.
    if _stale_trigger_bar(payload, et):
        rec["action"] = "SKIP_STALE_TRIGGER"
        rec["trigger_bar_et"] = str(payload["bar_ctx"].get("timestamp_et"))
    elif (v in ("ENTER_BEAR", "ENTER_BULL") and _blind_block_enabled(params)
          and _is_blind(bc) and not _level_anchored(verdict)):
        # BLINDNESS BLOCK (2026-07-30) -- see the LEVEL_ANCHOR_TRIGGERS block above for the
        # incident. The engine has NO usable levels AND this entry has no price anchor:
        # that is precisely the trendline-only cohort (-$1,830 / WR .19 / n=124), taken for
        # the only reason it could be -- the engine could not see. Blind => HOLD.
        #
        # WHY HERE, and not in engine_cli.decide_payload: decide_payload/evaluate_gates are
        # PURE and SHARED with the backtest orchestrator, where they are reused as the
        # parity-oracle assert-agree check. Emitting a verdict there that the orchestrator
        # does not emit would break that parity assert and would silently change every
        # historical replay over a bar whose levels_active happened to be empty -- an EDGE
        # change wearing a safety fix's clothes. This is the same reasoning, and the same
        # seam, that GATE-PROVENANCE-SWEEP-2026-07-10 used for SKIP_STALE_TRIGGER: a
        # live-only data-sight condition belongs in heartbeat_core's post-verdict ladder.
        #
        # WHY THIS POSITION IN THE LADDER -- first of the ENTER_*-conditional guards:
        #   * It is the CHEAPEST check (pure in-memory; no clock math, no REST call), so a
        #     blind tick short-circuits before _sight_staleness_check spends a live quote.
        #   * It cannot be bypassed by the SCORE LADDER: _apply_score_ladder runs ABOVE this
        #     line and can rewrite a HOLD into ENTER_BEAR, so any check placed before it
        #     would be jumpable. (A ladder rescue always sets a numeric rejection_level, so
        #     an anchored ladder entry stays allowed -- it is only ever blocked here if it
        #     somehow produced no anchor at all.)
        #   * PRECEDENCE, deliberate: a blind tick that is ALSO late/early now logs
        #     SKIP_NO_LEVELS instead of SKIP_LATE_ENTRY/SKIP_EARLY_ENTRY. Both are
        #     no-entries, so no trading behavior differs -- but "we were blind" is a
        #     SYSTEMIC failure that must reach engine-health, while late/early are routine.
        #     Masking blindness behind a routine label is how this went unseen for 386 ticks.
        #
        # VERDICT IS REWRITTEN, not just the action (the score-ladder precedent above does
        # the same). This is load-bearing, not cosmetic: automation/state/fleet/
        # build_shared_signal.py#_map_core_row takes the fleet's ENTRY DECISION from this
        # row's `verdict` field, NOT its `action` -- leaving verdict=ENTER_BEAR would block
        # safe-2/bold-2 here while the other fleet arms happily entered the same blind
        # trade off the same ledger row. The original engine verdict is preserved verbatim
        # in blind_blocked_verdict, so ledger honesty (OP-33) is intact.
        rec["blind_blocked_verdict"] = v
        rec["verdict"] = "SKIP_NO_LEVELS"
        rec["side"] = None
        rec["reason"] = (
            f"BLIND: levels_active is empty (key-levels.json stale/unrefreshed) and this "
            f"{v} has no level anchor (triggers={verdict.get('triggers_fired')}, "
            f"trigger_level_exact={verdict.get('rejection_level')!r}) -- refusing the "
            f"trendline-only cohort. Original engine verdict: {v}."
        )
        rec["action"] = "SKIP_NO_LEVELS"
        logger.critical(
            "[BLIND] %s %s refused: no key levels loaded (levels_active empty) and no level "
            "anchor on the entry. Check Gamma_LevelRefresh / key-levels.json freshness.",
            account, v,
        )
    elif v in ("ENTER_BEAR", "ENTER_BULL") and _past_entry_ceiling(params, et):
        # FIX1 (2026-07-01): entry-time ceiling — a late ENTER is a logged SKIP, never an
        # order attempt (2026-06-30: all 10 ENTER verdicts fired 15:51-15:55, all rejected
        # by Alpaca 'expires soon'). Checked BEFORE the free-model eval so a late tick spends
        # nothing. _execute has the same check (belt-and-suspenders for the extra-setup route).
        rec["action"] = "SKIP_LATE_ENTRY"
        rec["entry_ceiling_et"] = str(params.get("entry_no_trade_after_et") or "15:00")
    elif v in ("ENTER_BEAR", "ENTER_BULL") and _before_entry_floor(params, et):
        # FIX (2026-07-02): wall-clock floor — [09:35, 15:00) now enforced on BOTH ends.
        rec["action"] = "SKIP_EARLY_ENTRY"
        rec["entry_floor_et"] = str(params.get("entry_no_trade_before_et") or "09:35")
    elif (v in ("ENTER_BEAR", "ENTER_BULL")
          and (_sight := _sight_staleness_check(bc["bar"]["close"])).get("stale")):
        # SIGHT-FRESHNESS GUARD (DECISION-ROW-SPY-STALENESS, 2026-07-20): the trigger bar's
        # close diverges from a fresh live SPY trade by more than SIGHT_STALENESS_MAX_
        # DIVERGENCE_USD -- proof the decision spot is stale relative to the real tape RIGHT
        # NOW, not just "old by the usual ~5-10min bar-close lag". Checked BEFORE the
        # free-model eval (same reasoning as the entry-ceiling/floor checks above: a tick
        # that's never going to place spends nothing). Fail-open logic lives inside
        # _sight_staleness_check itself (no live quote -> stale=False -> this branch never
        # matches -> falls through to the normal ENTER branch below, which also logs the
        # (non-stale) check for visibility -- see rec["sight_check"] there).
        rec["action"] = "SKIP_STALE_SIGHT"
        rec["sight_check"] = _sight
    elif v in ("ENTER_BEAR", "ENTER_BULL"):
        # `_sight` was already computed by the walrus in the preceding elif's condition
        # (it always evaluates when v is ENTER_* -- Python only reaches THIS branch when
        # that condition was False, i.e. stale=False) -- reused here, not re-fetched, so a
        # non-stale ENTER tick costs exactly ONE live-quote REST call, not two.
        rec["sight_check"] = _sight
        rec["free_eval"] = _free_model_eval(account, payload, verdict)
        if rec["free_eval"].get("veto"):
            rec["action"] = "VETOED_BY_MODELS"
        elif not CORE_PLACES_ORDERS:
            # PERCEPTION-ONLY (6-account unification, Path B): the brain emits the verdict +
            # free-eval but places NOTHING — the fleet executor owns all 6 arms' placement.
            # The verdict/scores/ledger row are byte-identical to the places-orders path; only
            # WHO places migrates. DEFAULT (CORE_PLACES_ORDERS=True) never reaches this branch.
            rec["action"] = "PERCEPTION_ONLY"
        else:
            rec["exec"] = _reconcile_exec(_execute(account, verdict, payload, params, dry=not ARMED))
            rec["action"] = rec["exec"].get("status")
            # BULL-WIRING REGRESSION GUARD (2026-06-28, swarm-recommended): an ENTER_BULL
            # verdict MUST reach _execute exactly like ENTER_BEAR. If a future change ever
            # severs the bull path (e.g. a bear-only exec gate sneaks in), this surfaces it
            # instantly in the logs instead of silently reverting to "bear-only".
            if v == "ENTER_BULL" and not rec.get("exec"):
                logger.critical(
                    "[BULL-GUARD] ENTER_BULL produced no exec record — bull path may be severed. "
                    "Bull and bear MUST share the _execute path (see CLAUDE.md OP-16 setup scope)."
                )
    else:
        rec["action"] = v
    # G4: on a non-ENTER ribbon verdict (HOLD/SKIP, INCLUDING a bar the staleness check
    # above just relabeled SKIP_STALE_TRIGGER), route any fired + exec-armed extra setup
    # through the SAME _execute path. Default = byte-identical no-op (no setup is
    # exec-armed -> every fired row logs WATCH_NOT_ARMED, _execute is never called). Gated
    # on the RAW verdict `v` (not rec["action"]) so this reproduces the pre-existing
    # `else`-branch semantics exactly: G4 dispatch depends on WHETHER the primary ribbon
    # path itself attempted an entry (v in ENTER_BEAR/ENTER_BULL already claimed _execute
    # above -- G4 must never double-place on the same tick; _execute's own is_flat check is
    # the backstop), never on what the primary verdict got RELABELED to for logging.
    #
    # FIX (2026-07-10, GATE-PROVENANCE-SWEEP): hoisted out of the `else:` clause above so
    # the staleness short-circuit (which can now claim the tick's `rec["action"]` even when
    # `v` itself is HOLD/a gate-SKIP) does not also silently suppress this independent
    # side-channel. Extra-setup detectors (dispatch_extra_setups, called earlier this tick)
    # read their OWN same-day-bars slice, not the CORE ribbon path's (possibly stale)
    # trigger bar -- their fire/no-fire decision is unaffected by _stale_trigger_bar, so
    # their routing must be too. Byte-identical to the pre-fix behavior for every v that
    # isn't ENTER_BEAR/ENTER_BULL (that was the `else`-branch's exact gating condition).
    #
    # FIX (2026-07-06, post-mortem on that session): structure_veto is a purpose-built
    # directional safety gate (engine_cli.py, added after the 2026-06-26 -$237 wrong-way
    # entry) and was blind to this side-channel — 7 extra-setup entries fired that day while
    # the primary verdict was SKIP_STRUCTURE_VETO/HOLD, including one buying the EXACT
    # direction structure_veto had just blocked on the same tick (net -$33 on that
    # cluster). When the primary verdict IS a structure veto, no extra-setup entry fires
    # this tick either — the gate's premise ("this tick's structure makes a new
    # directional entry dangerous") applies account-wide, not just to the primary path.
    # Guard: test_g4_extra_setup_routing.py::test_structure_veto_blocks_extra_setup_route
    # (corrected 2026-07-10: this test lives here, not in test_graduated_guards.py -- the
    # old comment predates the test's move/split into its own dedicated file) +
    # test_gate_provenance_ordering_2026_07_10.py.
    #
    # BLINDNESS (2026-07-30): the extra-setup route is the ONLY other order-placing path in
    # this file, so a blind block that ignored it would be trivially bypassable -- and 6 of
    # these detectors are flag-ON in params.json today (j_vwap_cont, j_vix_dayside,
    # gap_and_go, bollinger_squeeze, db_base_quiet, j_lbfs), so this is a live lane, not a
    # dormant one. They are blind in the literal sense too: setup_dispatch.py:344 builds
    # their BarContext with `levels_active=list(bar_ctx_d.get("levels_active", []))` -- the
    # SAME empty list the core path just refused to trade on. This mirrors the structure_veto
    # carve-out immediately above verbatim (same premise: an account-wide entry-safety
    # condition applies to every lane, not just the primary one), and rides the SAME
    # block_entries_when_blind flag, so one revoke restores both lanes at once.
    if v not in ("ENTER_BEAR", "ENTER_BULL"):
        _blind_now = _blind_block_enabled(params) and _is_blind(bc)
        if extra and v != "SKIP_STRUCTURE_VETO" and not _blind_now:
            routed = _route_extra_setups(account, extra, payload, params)
            if routed:
                rec["extra_exec"] = routed
        elif extra:
            rec["extra_exec_blocked_by"] = "structure_veto" if v == "SKIP_STRUCTURE_VETO" else "no_levels"
    _log(rec)
    return rec


def _occ(side: str, strike: int, expiry: datetime) -> str:
    cp = "C" if side == "C" else "P"
    return f"SPY{expiry.strftime('%y%m%d')}{cp}{int(round(strike * 1000)):08d}"


def _place_simple_entry(creds: dict, *, symbol: str, qty: int, limit_price: float) -> dict:
    """FIX2 (2026-07-01): the ONE order-POST for a live options entry — a plain marketable
    limit, placed DIRECTLY (no bracket/oto attempt first). Alpaca rejects complex orders for
    options 100% of the time (code 42210000), so the old bracket->oto->simple ladder just ate
    2 guaranteed 422s per entry. TP/stop are engine-managed (exit_manager); the caller enforces
    CORE_MANAGES_EXITS before calling (C2: never a stopless entry without engine-managed exits).
    Mirrors fleet_broker.place_bracket's base leg (buy/limit/day) byte-for-byte.
    Guard: test_money_path_2026_07_01.py::TestSimpleFirstPlacement."""
    import fleet_broker as fb  # noqa: PLC0415
    if qty is None or int(qty) < 1:
        return {"_refused": f"invalid qty {qty}"}
    if limit_price is None or float(limit_price) <= 0:
        return {"_refused": f"invalid limit_price {limit_price}"}
    order = {"symbol": symbol, "qty": str(int(qty)), "side": "buy", "type": "limit",
             "limit_price": str(round(float(limit_price), 2)), "time_in_force": "day"}
    res = fb._request(creds, "orders", method="POST", data=order)
    if not isinstance(res, dict):
        return {"_error": f"unexpected broker response: {res!r}"}
    if not res.get("_error"):
        res["_simple_first"] = True
        res["_note"] = ("simple marketable limit placed directly (options: no broker bracket); "
                        "TP/stop engine-managed (exit_manager)")
    return res


_TERMINAL_ORDER_STATES = frozenset({"filled", "partially_filled", "canceled",
                                    "cancelled", "rejected", "expired", "done_for_day"})


def _reconcile_fill(creds: dict, order: dict, *, max_polls: int = 4,
                    sleep_s: float = 0.6, hard_cap_s: float = 3.0) -> dict:
    """FIX3 (2026-07-07): poll the placed order to a TERMINAL state and return the reconciled
    fill fields, so a filled order's ledger row records status=filled / filled_qty /
    filled_avg_price instead of staying pending_new / filled_qty=0 forever (which logged the
    trade UNKNOWN/ungraded in trades.csv). Reads the order back via fleet_broker._request
    (GET orders/{id}) with BOUNDED retries + short sleeps, hard-capped at hard_cap_s so the
    per-minute tick is never blocked. DEFENSIVE: on any poll failure it returns a
    RECONCILE_PENDING marker (never crashes, never blocks past the cap). Returns a dict of
    the reconciled fields to merge into the broker response
    (status/filled_qty/filled_avg_price[/reconcile_*]). Reads the order back via the public
    fleet_broker.get_order (GET orders/{id}) — the same primitive fleet_live uses.
    Guard: test_audit_fix_heartbeat.py::TestFillReconciliation."""
    import time as _time  # stdlib time module — NOT datetime.time (shadowed at module scope)
    oid = order.get("id") if isinstance(order, dict) else None
    if not oid or (isinstance(order, dict) and (order.get("_error") or order.get("_refused"))):
        return {}  # nothing placed / no id -> nothing to reconcile
    try:
        import fleet_broker as fb  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return {"reconcile_status": "RECONCILE_PENDING", "reconcile_error": f"{type(e).__name__}: {e}"}
    deadline = _time.monotonic() + float(hard_cap_s)
    last = {"reconcile_status": "RECONCILE_PENDING", "reconcile_reason": "no_terminal_before_cap"}
    for i in range(max(1, int(max_polls))):
        try:
            cur = fb.get_order(creds, oid)
        except Exception as e:  # noqa: BLE001 — a poll failure must never crash the tick
            last = {"reconcile_status": "RECONCILE_PENDING", "reconcile_error": f"{type(e).__name__}: {e}"}
            cur = None
        if isinstance(cur, dict) and not cur.get("_error"):
            st = str(cur.get("status", "")).lower()
            if st in _TERMINAL_ORDER_STATES:
                out = {"status": cur.get("status"),
                       "filled_qty": cur.get("filled_qty"),
                       "filled_avg_price": cur.get("filled_avg_price"),
                       "reconcile_status": "RECONCILED"}
                return {k: v for k, v in out.items() if v is not None or k == "reconcile_status"}
            last = {"status": cur.get("status"), "filled_qty": cur.get("filled_qty"),
                    "reconcile_status": "RECONCILE_PENDING", "reconcile_reason": f"non_terminal:{st or '?'}"}
        elif isinstance(cur, dict):
            last = {"reconcile_status": "RECONCILE_PENDING", "reconcile_error": str(cur.get("_error"))[:120]}
        if i < max_polls - 1 and _time.monotonic() + sleep_s < deadline:
            _time.sleep(sleep_s)
        elif _time.monotonic() >= deadline:
            break
    return last


def _reconcile_exec(exec_row: "dict | None") -> "dict | None":
    """FIX3 (2026-07-07): given an _execute result that placed an order, poll its fill to a
    terminal state and reconcile the decision row IN PLACE: the broker sub-row gets
    status=filled / filled_qty / filled_avg_price, and a top-level `fill` summary is added.
    Reads the order back OUTSIDE _execute so the placement path stays a single broker POST.
    The transient `_reconcile` marker (creds + order handle) is always stripped afterward so
    the logged row carries only JSON-native fields. No-op (returns the row unchanged) when
    there is nothing placed to reconcile. Never raises — a reconcile failure must never break
    the tick's ledger write. Guard: test_audit_fix_heartbeat.py::TestFillReconciliation."""
    if not isinstance(exec_row, dict):
        return exec_row
    handle = exec_row.pop("_reconcile", None)  # strip the transient marker either way
    if not isinstance(handle, dict):
        return exec_row
    try:
        recon = _reconcile_fill(handle.get("creds"), handle.get("order") or {})
        if recon:
            broker = exec_row.get("broker")
            if isinstance(broker, dict):
                broker.update(recon)
            exec_row["fill"] = recon
    except Exception as e:  # noqa: BLE001 — reconciliation must never break the ledger write
        exec_row["fill"] = {"reconcile_status": "RECONCILE_PENDING",
                            "reconcile_error": f"{type(e).__name__}: {e}"}
    return exec_row


# ----- re-entry lock: DELETED (J directive 2026-07-02) -----------------------
# The quality-lock / first-entry re-entry suppression (_quality_rank,
# _todays_ledger_rows, _prior_fill_stopped, _quality_lock_check, SKIP_QUALITY_LOCK)
# was removed in full per J's written order: "Gone. We no longer have it in our
# codebase." It was Claude-invented, never A/B-validated, and cost the 2026-07-02
# midday re-entry. An ENTER after a same-setup stop now routes straight to _execute
# (FLAT-verify + risk_gate still apply). Guard: test_tz_quality_lock_2026_07_02.py
# pins the lock's ABSENCE. Any future cooldown gate ships only with A/B evidence
# (analysis/recommendations/reentry-cooldown-ab.json).


# TRADE-TO-LEARN (2026-07-01, J-ratified): per-setup VALIDATED-cell overrides for armed
# extra setups. C29 — validated knobs don't transfer across strike tiers, so each armed
# setup trades ITS scorecard cell, never the generic v15 ladder. Values are params.json
# key names (single source of truth; backtest/lib/filters.py reads the same keys on the
# sim side). Live-params strike convention (v15_strike_offset_per_tier): 0=ATM,
# POSITIVE=ITM, NEGATIVE=OTM; puts strike=ATM+off, calls strike=ATM-off (heartbeat.md:254).
# A setup absent here (or its enable flag off) keeps today's generic behavior byte-identical.
# Guards: test_money_path_2026_07_01.py (vwap_continuation) + test_trade_to_learn_2026_07_01.py.
#
# PROFIT-P2-ARMED (2026-07-11): the two CORE ribbon_ride entry_setups (not an "extra
# setup" — always-on, never gated by extra_setup_exec_armed) were ADDED to this same
# dispatch table, same 3-key shape, same mirror-of-WP5 pattern. Evidence + full provenance:
# params.json#_j_ribbon_ride_strike_override_doc (analysis/recommendations/
# ribbon-ride-strike-exit-ab.json: ATM beats OTM-2 by +$47.96/tr, clears OP-11 auto-ratify).
# Guard: test_ribbon_ride_strike_override_2026_07_11.py + test_trade_to_learn_2026_07_01.py
# (updated TestStrikeOverride.test_ribbon_setup_now_uses_its_own_atm_override pin).
_SETUP_STRIKE_OVERRIDES = {
    # dispatcher setup_name (lower): (enable_flag_key, safe_offset_key, bold_offset_key)
    "vwap_continuation": ("j_vwap_cont_strike_override_enabled",
                          "j_vwap_cont_strike_offset_safe",
                          "j_vwap_cont_strike_offset_bold"),
    "vwap_reclaim_failed_break": ("j_vwap_reclaim_fb_strike_override_enabled",
                                  "j_vwap_reclaim_fb_strike_offset_safe",
                                  "j_vwap_reclaim_fb_strike_offset_bold"),
    "vix_regime_dayside": ("j_vix_dayside_strike_override_enabled",
                           "j_vix_dayside_strike_offset_safe",
                           "j_vix_dayside_strike_offset_bold"),
    "double_bottom_base_quiet": ("j_db_base_quiet_strike_override_enabled",
                                 "j_db_base_quiet_strike_offset_safe",
                                 "j_db_base_quiet_strike_offset_bold"),
    "bollinger_squeeze": ("j_bollinger_squeeze_strike_override_enabled",
                          "j_bollinger_squeeze_strike_offset_safe",
                          "j_bollinger_squeeze_strike_offset_bold"),
    "bearish_rejection_ride_the_ribbon": ("j_ribbon_ride_strike_override_enabled",
                                          "j_ribbon_ride_strike_offset_safe",
                                          "j_ribbon_ride_strike_offset_bold"),
    "bullish_reclaim_ride_the_ribbon": ("j_ribbon_ride_strike_override_enabled",
                                        "j_ribbon_ride_strike_offset_safe",
                                        "j_ribbon_ride_strike_offset_bold"),
}
# ISOLATED per-setup exit knobs (params _j_*_isolated_exit_doc): the validated cells for
# these setups carry their OWN stop/TP1 — silently sourcing the global -50% catastrophe
# cap would trade an UNVALIDATED cell (C14/L149; for vix_regime_dayside the -8% stop is
# LOAD-BEARING per its G8 gate). vwap_continuation ADDED 2026-07-02 (exit-parity A/B,
# analysis/recommendations/vwapcont-exit-parity.json): un-overridden it was exit-managed
# by the ribbon_ride shape (-20% stop / tp1 +150%) — a WR-22% lotto with NEGATIVE
# J-anchor capture; its validated cell (stop -0.08 / tp1 0.30) wins per OP-16.
# "runner" is optional. "stop_mode" is optional (literal "structure"|"premium", NOT a
# params-key lookup like the other entries — see gap_and_go below); its absence keeps the
# pre-2026-07-18 default "premium" byte-identical for every setup that doesn't set it.
#
# gap_and_go ADDED 2026-07-18 (queue GAP-AND-GO-REVALIDATION-BEFORE-ARM, blocker B):
# its validated cell (analysis/recommendations/gap-and-go-LIVE.json go_live_params) is
# CHART-STOP-ONLY (first-RTH-bar opposite extreme) + standard v15 TP1(+30%)/runner/time-
# stop — structurally NOTHING like ribbon_ride's rejection/reclaim-level structure stop OR
# any other isolated setup's premium stop. Before this entry existed, an armed gap_and_go
# fill fell through to the `else` branch (ribbon_ride's exit.to_dict(), a -20%/+150% shape)
# — the EXACT bug class the vwap_continuation fix above closed for that setup in 2026-07-02,
# never closed here (queue item filed 2026-07-16 evening). j_gap_and_go_premium_stop_pct is
# the FAIL-OPEN fallback (mirrors the -0.50 global catastrophe cap) for the tick where
# trigger_level can't resolve (see _synthetic_verdict_from_extra's new rejection_level wire
# below) — NOT the sim's -0.99 "off" value, since production's real catastrophe backstop is
# -50%, matching the already-validated SS-B ribbon_ride pattern. gap_and_go's exec-arm stays
# ABSENT (WATCH only) — this fixes the SHAPE for whenever a future re-validation (blocker A,
# still open) clears it to arm; it does not itself arm anything.
# Guard: test_gap_and_go_exit_wiring_2026_07_18.py.
_SETUP_EXIT_OVERRIDES = {
    "vwap_continuation": {"stop": "j_vwap_cont_premium_stop_pct",
                          "tp1": "j_vwap_cont_tp1_pct"},
    "vwap_reclaim_failed_break": {"stop": "j_vwap_reclaim_fb_premium_stop_pct",
                                  "tp1": "j_vwap_reclaim_fb_tp1_pct"},
    "vix_regime_dayside": {"stop": "j_vix_dayside_premium_stop_pct",
                           "tp1": "j_vix_dayside_tp1_pct"},
    "double_bottom_base_quiet": {"stop": "j_db_base_quiet_premium_stop_pct",
                                 "tp1": "j_db_base_quiet_tp1_pct",
                                 "runner": "j_db_base_quiet_runner_target_pct"},
    "bollinger_squeeze": {"stop": "j_bollinger_squeeze_premium_stop_pct",
                          "tp1": "j_bollinger_squeeze_tp1_pct",
                          "tq": "j_bollinger_squeeze_tp1_qty_fraction",
                          "plmode": "j_bollinger_squeeze_profit_lock_mode",
                          "trail": "j_bollinger_squeeze_profit_lock_trail_pct"},
    "gap_and_go": {"stop": "j_gap_and_go_premium_stop_pct",
                  "tp1": "j_gap_and_go_tp1_pct",
                  "stop_mode": "structure"},
}


def _params_float(params: dict, key: str, default: float) -> float:
    """params[key] as float; missing/malformed -> the validated default (never raises)."""
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _capture_greeks(creds: dict, symbol: str, *, fetch=None) -> dict:
    """Fail-open per-contract greeks/IV snapshot for the entry log (G8, 2026-07-07).

    LOG-ONLY: returns {} on ANY error and is invoked ONLY in the dry branch or AFTER the
    order POST, so it can never delay or break a fill. Accumulates a per-entry greeks corpus
    (delta/gamma/theta/vega/rho/iv) so the 'does a dynamic stop beat a static one' question
    re-opens on REAL greeks instead of VIX-proxied IV + a fixed per-tier delta (the axis the
    dynamic-stop test died on). `fetch` is injectable for tests (default fleet_broker).
    Guard: test_greeks_capture.py."""
    try:
        if fetch is None:
            import fleet_broker as fb  # noqa: PLC0415
            fetch = fb.get_option_greeks
        return fetch(creds, symbol) or {}
    except Exception:  # noqa: BLE001 — greeks capture must never touch the fill path
        return {}


def _execute(account: str, verdict: dict, payload: dict, params: dict, *, dry: bool) -> dict:
    """SIZE + PLACE a 0DTE entry via the TESTED fleet_broker + risk_gate primitives.
    dry=True computes everything and returns the plan WITHOUT placing (shadow / self-test)."""
    # FIX1 belt-and-suspenders (2026-07-01): EVERY route into _execute (core ribbon verdict
    # AND the extra-setup G4 route) hits this ceiling before any broker call. A late signal
    # is a logged SKIP verdict, never an order attempt.
    _now_exec = _et_now()
    if _past_entry_ceiling(params, _now_exec):
        return {"status": "SKIP_LATE_ENTRY",
                "entry_ceiling_et": str(params.get("entry_no_trade_after_et") or "15:00")}
    if _stale_trigger_bar(payload, _now_exec):
        return {"status": "SKIP_STALE_TRIGGER",
                "trigger_bar_et": str(payload["bar_ctx"].get("timestamp_et"))}
    if _before_entry_floor(params, _now_exec):
        return {"status": "SKIP_EARLY_ENTRY",
                "entry_floor_et": str(params.get("entry_no_trade_before_et") or "09:35")}
    import urllib.request
    import fleet_broker as fb  # noqa: PLC0415
    import risk_gate as rg  # noqa: PLC0415
    try:
        import strike_selection as ss  # noqa: PLC0415
    except Exception:
        ss = None
    arm = ACCOUNTS[account]["fleet_arm"]
    creds = fb.load_creds().get(arm)
    if not creds:
        return {"status": "NO_CREDS", "arm": arm}
    side = "P" if verdict["verdict"] == "ENTER_BEAR" else "C"
    spy = float(payload["bar_ctx"]["bar"]["close"])
    # equity (live) + start-of-day + day-trades + kill-switch from broker + circuit-breaker
    cb_path = (STATE / "aggressive" / "circuit-breaker.json") if account == "bold" else (STATE / "circuit-breaker.json")
    cb = json.loads(cb_path.read_text(encoding="utf-8")) if cb_path.exists() else {}
    try:
        acct = json.loads(urllib.request.urlopen(urllib.request.Request(
            creds["base_url"].rstrip("/") + "/v2/account",
            headers={"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}), timeout=10).read())
        equity = float(acct.get("equity", 0))
    except Exception as e:  # noqa: BLE001
        return {"status": "EQUITY_FETCH_FAIL", "err": str(e)[:80]}
    sod = float(cb.get("equity_start_of_day") or cb.get("starting_equity_today") or equity)
    # FIX (2026-07-06): day_trades_used_5d was a hardcoded 0 that no component ever
    # incremented (Rule 7 PDT was structurally unenforceable -- 0 >= 3 is never true).
    # Compute it LIVE from Alpaca's own fill history (broker = source of truth, C11)
    # right here, at the one place it's actually consumed, instead of trusting a
    # stale circuit-breaker.json snapshot. Fail-open to 0 matches pre-fix behavior
    # exactly on a fetch error (see pdt_tracker.py docstring for why that's safe).
    # Guard: test_pdt_tracker_2026_07_06.py.
    import pdt_tracker as _pdt  # noqa: PLC0415
    day_trades = _pdt.fetch_day_trades_used_5d(creds)
    if day_trades != int(cb.get("day_trades_used_5d") or 0):
        try:
            cb["day_trades_used_5d"] = day_trades
            cb["day_trades_used_5d_computed_at"] = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
            cb_path.write_text(json.dumps(cb, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001 -- visibility write must never block the gate
            pass
    # SETTLEMENT LEDGER (2026-07-14): both core accounts are CASH accounts
    # (verified live -- multiplier=1, Alpaca pattern_day_trader/daytrade_count
    # both null) -- PDT never applied to them. day_trades above stays wired for
    # legacy params.pdt_gate_mode="margin_pdt" revert + the VISIBILITY surfaces
    # (self_check.py/firm_brief.py) that still read it; the actual live gate
    # feed is this settled-cash ledger (setup/scripts/settlement_ledger.py) --
    # `sod` above is the account's start-of-day broker cash, which is genuinely
    # SETTLED (both accounts are flat overnight, so nothing from a prior day is
    # still unsettled by today). Fail-open by construction (see that module's
    # docstring) -- a ledger I/O error can only widen availability, never
    # invent a new block.
    import settlement_ledger as _sl  # noqa: PLC0415
    _ledger_path = _sl.ledger_path(STATE, account)
    _today_et = _et_now().strftime("%Y-%m-%d")
    _settlement = _sl.get_settlement_status(_ledger_path, _today_et, sod)
    killed = bool(cb.get("tripped")) or (STATE / "kill-switch").exists()
    # FLAT-verify (broker = source of truth, L47/C11) + MANUAL/ENGINE COEXISTENCE (FIX1,
    # 2026-07-07, J: "get rid of the lockout"). Any open SPY-option position still BLOCKS a
    # 2nd (stacked) entry — that protects the Rule-6 per-trade risk cap. But instead of the
    # engine sitting frozen all day (2026-07-06: a manual position froze every ENTER at
    # NOT_FLAT), it now ADOPTS any UNTRACKED open position into the exit_manager so the
    # engine MANAGES that trade's exit — it is never silently disabled. Adoption is
    # idempotent (already-tracked symbols keep their evolving state) and fail-safe (never
    # raises). We STILL return NOT_FLAT: no stacking. The flat check is the SAME
    # is_flat_spy_options primitive as before (broker = source of truth); only when it is
    # NOT flat do we fetch the position list to adopt the untracked (manual) position.
    if not fb.is_flat_spy_options(creds):
        _adopted = _adopt_untracked_positions(ACCOUNTS[account]["fleet_arm"], creds,
                                              fb.open_spy_option_positions(creds))
        return {"status": "NOT_FLAT", "adopted": _adopted}
    # RE-ENTRY LOCK DELETED (J directive 2026-07-02): the quality-lock that blocked a
    # same-or-lower-quality re-entry on the same setup today is GONE — flat-verify +
    # risk_gate is the gate. Guard: test_tz_quality_lock_2026_07_02.py (absence pin).
    setup_name = verdict.get("setup_name") or (
        "BEARISH_REJECTION_RIDE_THE_RIBBON" if side == "P" else "BULLISH_RECLAIM_RIDE_THE_RIBBON")
    # strike + contract + premium
    # BOLD CORE ATM WIRE (2026-07-18, J explicit "Yes -- wire Bold to ATM" in-chat):
    # bold branch repointed from V15_BOLD_TIERS to V15_BOLD_CORE_TIERS ($0-2K tier only:
    # OTM-3 -> ATM). V15_BOLD_TIERS itself is untouched -- fleet_executor.py's safe-3/
    # risky-1/risky-3 arms still resolve the original OTM-3 table directly. See
    # crypto/lib/strike_selection.py's V15_BOLD_CORE_TIERS docstring for full evidence
    # + revert instructions.
    strike = ss.pick_strike(spy, equity, side, ss.V15_BOLD_CORE_TIERS if account == "bold" else ss.V15_SAFE_TIERS) \
        if ss else (int(round(spy)) + (2 if side == "P" else -2))
    # FIX4/WP-5 + trade-to-learn (2026-07-01): per-setup strike override — each armed extra
    # setup is VALIDATED at a specific strike tier (e.g. vwap_continuation ATM on Safe /
    # ITM-2 on Bold); the generic tier above is a different, UNVALIDATED cell (C29: strikes
    # don't transfer across tiers). Table + convention: _SETUP_STRIKE_OVERRIDES above.
    # Mirrors risk_gate.select_strike_offset's dispatch (the sim/orchestrator-side resolver).
    _sov = _SETUP_STRIKE_OVERRIDES.get(str(setup_name or "").lower())
    if _sov and params.get(_sov[0]):
        _off_key = _sov[2] if account == "bold" else _sov[1]
        try:
            _off = int(params.get(_off_key, 0))
        except (TypeError, ValueError):
            _off = 0
        _atm = int(round(spy))
        strike = (_atm + _off) if side == "P" else (_atm - _off)
    expiry = _et_now()
    symbol = _occ(side, strike, expiry)
    mid = fb.get_option_mid(creds, symbol)
    # MARKETABLE-LIMIT (#15): mid rarely crosses on 0DTE -> "zero fills ever". Price the entry at
    # ask+buffer so it fills; mid stays the base for TP/stop pct + sizing. No quote -> NO_PREMIUM.
    entry_px = fb.marketable_limit_price(creds, symbol, side="buy",
                                         buffer=float(params.get("entry_cross_buffer", 0.03)))
    if not mid or mid <= 0 or not entry_px or entry_px <= 0:
        return {"status": "NO_PREMIUM", "symbol": symbol}
    # NBBO CAPTURE (2026-07-20, queue: PROFIT-P4-NBBO-CAPTURE): the friction stream had NO
    # option bid/ask history anywhere (spread_cents in the ledger is the SPY EMA-ribbon
    # spread, not an option quote) -- bid_ask_spread_max_cents was a dead knob with zero
    # consumers. RECONSTRUCTED from the SAME mid/entry_px this tick already priced off of
    # (get_option_mid + marketable_limit_price above), NOT a third independent quote fetch --
    # that keeps this purely additive telemetry with zero new network round-trips on the
    # entry-critical path and zero risk of drifting from what actually priced the order.
    # ask = entry_px - buffer (marketable_limit_price's own buy-side formula, inverted);
    # bid = 2*mid - ask (get_option_mid's own formula, inverted). Exact when both broker
    # calls this tick saw the same quote (the common case); any drift between the two
    # calls shows up here as a wider/narrower reconstructed spread -- itself honest
    # telemetry (quote movement between calls), not something to hide.
    _nbbo_buf = float(params.get("entry_cross_buffer", 0.03))
    _nbbo_ask = round(entry_px - _nbbo_buf, 2)
    _nbbo_bid = round(2 * mid - _nbbo_ask, 2)
    nbbo = {"bid": _nbbo_bid, "ask": _nbbo_ask, "mid": mid, "spread": round(_nbbo_ask - _nbbo_bid, 2)}
    # ENTRY-1 PREMIUM FLOOR (2026-07-09 ship, STOP-B disposition, entry-exit-matrix-2026-07-09.md
    # scorecard): sub-$0.20 fills are a toxic cohort (T2: ~2-tick stops, ~42% spread proxy -- the
    # stop reads spread noise, not price) that cost ~$685 of the real week's losses (entry-1+
    # control -$72.50 vs control -$757.10, 79 real positions/17 signals). PLAN-TIME strategy
    # admission, NOT a risk_gate rule -- refuses BEFORE sizing/check_order ever runs. params key
    # min_entry_premium (0/absent = OFF, byte-identical). Guard: test_min_entry_premium_floor.py.
    # Revert: set min_entry_premium to 0 or delete the key.
    _min_prem = _params_float(params, "min_entry_premium", 0.0)
    if _min_prem > 0 and mid < _min_prem:
        return {"status": "SKIP_MIN_PREMIUM_FLOOR", "symbol": symbol, "premium": mid,
                "min_entry_premium": _min_prem}
    # sizing: tier base qty, then cap-aware clamp (L180/C11)
    qty = int(params.get("min_contracts", 3))
    afford = rg.max_affordable_qty(equity=equity, premium=mid, params=params)
    if afford and qty > afford:
        qty = afford
    # risk_gate = final authority
    decision = rg.check_order(
        account, equity=equity, start_of_day_equity=sod, proposed_qty=qty, premium=mid,
        setup_name=verdict.get("setup_name") or "BEARISH_REJECTION_RIDE_THE_RIBBON",
        current_position_status=None, day_trades_used_5d=day_trades,
        kill_switch_tripped=killed, prior_stops_today=[], params=params,
        settled_cash_available=_settlement["settled_cash_remaining"],
        same_day_entries_used=_settlement["entries_used_today"])
    if not getattr(decision, "allowed", False):
        _row = {"status": f"RISK_DENY_{getattr(decision,'code','?')}", "reason": getattr(decision, "reason", ""),
                "symbol": symbol, "qty": qty, "premium": mid}
        # BINDING-CONSTRAINT TELEMETRY (2026-07-30 incident). The `reason` above already
        # carries the notional-vs-cap arithmetic, but it cannot distinguish "proposal too
        # big, size down" from "NO legal qty exists at this premium" — on 2026-07-30 core
        # Safe logged 9 identical-looking RISK_DENY_RISK_CAP rows that were all the second
        # kind (equity $1,160 => $1.16/contract ceiling vs $1.42-$2.01 ATM prices), and
        # nothing in the ledger said so. `binding.deadlock` makes that explicit and
        # machine-readable for downstream monitors.
        # ADDITIVE ONLY: a new key inside `exec`; `status`/`reason`/`qty`/`premium` are
        # untouched (free_model_audit_heartbeat_veto.py regex-scrapes "equity $N" out of
        # the serialized row, so `reason` must keep its exact wording — and this block
        # deliberately emits NO "equity $" substring, only numeric fields).
        # FAILS OPEN: telemetry must never break a ledger write or an entry decision.
        try:
            _row["binding"] = rg.explain_block(equity=equity, premium=mid, params=params,
                                               proposed_qty=qty)
        except Exception:  # noqa: BLE001
            pass
        return _row
    # TRADE-TO-LEARN (2026-07-01): per-setup ISOLATED exit knobs — an armed extra setup
    # trades ITS validated stop/TP1 (see _SETUP_EXIT_OVERRIDES); every other setup keeps
    # the global knobs byte-identical (-50% catastrophe cap; chart-stop is a v2 enhancement).
    _xov = _SETUP_EXIT_OVERRIDES.get(str(setup_name or "").lower())
    _tp1_pct = (_params_float(params, _xov["tp1"], 0.30) if _xov
                else float(params.get("tp1_premium_pct", 0.30)))
    _stop_pct = _params_float(params, _xov["stop"], -0.50) if _xov else -0.50
    tp = round(mid * (1 + _tp1_pct), 2)
    stop = round(mid * (1 + _stop_pct), 2)
    plan = {"status": "WOULD_PLACE" if dry else "PLACING", "symbol": symbol, "side": side,
            "strike": strike, "qty": qty, "premium": mid, "tp": tp, "stop": stop, "equity": equity,
            "setup": setup_name, "nbbo": nbbo}
    if dry:
        plan["greeks"] = _capture_greeks(creds, symbol)  # G8 log-only (no fill in dry mode)
        return plan
    # CANCEL-REPLACE (#15): clear any stale never-crossed BUY limit on this symbol from a prior tick.
    for _o in fb.open_buy_orders(creds, symbol):
        if _o.get("id"):
            fb.cancel_order(creds, _o["id"], live=True)
    # FIX2 (2026-07-01): Alpaca NEVER accepts bracket/oto for options (code 42210000) — the
    # old place_bracket(simple_fallback=...) ladder ate 2 guaranteed 422s (bracket_err +
    # oto_err) on EVERY entry before the simple attempt (2026-06-30 exec.broker rows). Go
    # STRAIGHT to the marketable simple limit (#15 pricing: entry_px = ask + entry_cross_buffer).
    # C2 preserved: a simple entry has NO broker-side stop, so it is ONLY placed when the
    # engine manages exits (CORE_MANAGES_EXITS=1 -> exit_manager owns TP/stop); otherwise
    # refuse — the same safe PLACE_FAIL no-op the old path terminated in.
    if not CORE_MANAGES_EXITS:
        plan["status"] = "PLACE_FAIL"
        plan["broker"] = {"_refused": ("options need a simple entry (no broker bracket, 42210000) "
                                       "but exits are not engine-managed -- set GAMMA_CORE_MANAGES_EXITS=1")}
        plan["entry_px"] = entry_px
        return plan
    res = _place_simple_entry(creds, symbol=symbol, qty=qty, limit_price=entry_px)
    plan["status"] = "PLACED" if not res.get("_error") and not res.get("_refused") else "PLACE_FAIL"
    plan["broker"] = res
    plan["entry_px"] = entry_px
    plan["greeks"] = _capture_greeks(creds, symbol)  # G8 log-only, POST-placement (never slows the fill)
    # SETTLEMENT LEDGER DEBIT (2026-07-14): record ONLY on a real ACCEPTED
    # placement (never on dry/shadow calls, which return before this line —
    # see the `if dry: return plan` guard above — and never on a PLACE_FAIL,
    # which committed no capital). notional uses the ACTUAL entry_px, not the
    # mid used for the risk_gate preview, since that's what the account is
    # really committing.
    if plan["status"] == "PLACED":
        _sl.record_entry(_ledger_path, _today_et, sod, entry_px * qty * 100.0,
                          _et_now().strftime("%Y-%m-%dT%H:%M:%S"))
    # FIX3 (2026-07-07): stash the arm creds so the CALLER (run_account / _route_extra_setups
    # via reconcile_exec) can poll this accepted order to a TERMINAL fill and reconcile the
    # decision row. Reconciliation is deliberately done a level UP (not here) so the order-
    # PLACEMENT path stays a single broker POST — the fill-read GETs land outside _execute.
    # This callable is stripped before the row is logged (JSON-only writer).
    if plan["status"] == "PLACED":
        plan["_reconcile"] = {"creds": creds, "order": res}
    # EXIT-ENGINE WIRING (flag-gated, default OFF): on a real fill, register the position
    # with the exit_manager so the validated scale-out (partial TP1 + runner + profit-lock)
    # is realized on later ticks. The bracket above stays the catastrophe-floor backstop;
    # the exit_manager owns the partial TP1 + runner ride the single bracket cannot express.
    # OFF by default -> byte-identical armed behavior (no registration, single bracket only).
    if CORE_MANAGES_EXITS and plan["status"] == "PLACED":
        try:
            import exit_actuator as _ea  # noqa: PLC0415
            import exit_manager as _em  # noqa: PLC0415
            # STRUCTURE-STOP (2026-07-09): trigger_level for register_entry, PROVENANCE-
            # PREFERRED (G12, 2026-07-09 night). Two sources, in priority order:
            #   1. EXACT -- verdict["rejection_level"], the actual level filters.
            #      detect_level_rejection/detect_level_reclaim matched when the entry
            #      trigger fired (threaded verbatim through score_bar/engine_cli -- see the
            #      core-decisions.jsonl "trigger_level_exact" comment above for the full
            #      chain). This is ground truth, not a guess.
            #   2. HEURISTIC fallback -- exit_manager.nearest_active_level's proximity guess
            #      (nearest same-side key-level within $2 of spot), used ONLY when the exact
            #      level is unavailable (e.g. a TRENDLINE-tier entry with no level-tied
            #      trigger, or a synthetic verdict from the extra-setup route that never
            #      carries rejection_level -- see _synthetic_verdict_from_extra).
            # structure_stop_enabled reads params.json directly (default False/absent ->
            # "premium" mode, byte-identical -- see exit_manager.ExitState.from_entry).
            _trigger_level_exact = verdict.get("rejection_level")
            _trigger_level_exact = (float(_trigger_level_exact)
                                    if _trigger_level_exact is not None else None)
            _trigger_level_heuristic = _em.nearest_active_level(
                payload["bar_ctx"].get("levels_active") or [], spy, side)
            _trigger_level = (_trigger_level_exact if _trigger_level_exact is not None
                              else _trigger_level_heuristic)
            _structure_enabled = bool(params.get("structure_stop_enabled", False))
            if _xov is not None:
                # TRADE-TO-LEARN (2026-07-01): the exit_manager runs the setup's ISOLATED
                # validated shape (same _stop_pct/_tp1_pct as the plan above), never the
                # generic ribbon_ride shape — the stop IS part of the validated cell.
                # WIRE-BOLLINGER (2026-07-02): optional per-setup tq / plmode / trail keys
                # so a cell validated with a runner split + chandelier trail
                # (bollinger_squeeze: tq 0.667 / trailing 0.15) trades ITS shape,
                # not the global 0.8 / hard-coded "fixed".
                _shape = {"premium_stop_pct": _stop_pct, "tp1_premium_pct": _tp1_pct,
                          "tp1_qty_fraction": (_params_float(params, _xov["tq"], 0.667)
                                               if _xov.get("tq")
                                               else float(params.get("tp1_qty_fraction", 0.667))),
                          "profit_lock_mode": (str(params.get(_xov["plmode"], "fixed"))
                                               if _xov.get("plmode") else "fixed")}
                if _xov.get("trail"):
                    _shape["trail_pct"] = _params_float(params, _xov["trail"], 0.15)
                if _xov.get("runner"):
                    _shape["runner_target_pct"] = _params_float(params, _xov["runner"], 2.5)
                # STOP_MODE (2026-07-18, gap_and_go): a LITERAL "structure"|"premium" value,
                # not a params-key lookup (unlike every other _xov entry above) — the setup's
                # validated cell either uses a chart-level structure stop or it doesn't; that
                # isn't a tunable number. Absent -> "premium" (byte-identical for every setup
                # added before this one; none of them declared this key). ExitState.from_entry
                # (exit_manager.py) still requires structure_stop_enabled=True AND a resolved
                # trigger_level for this to actually take effect (both already required for
                # ribbon_ride's existing structure stop) — declaring it here alone changes
                # nothing until those two also hold.
                if _xov.get("stop_mode"):
                    _shape["stop_mode"] = str(_xov["stop_mode"])
            else:
                try:
                    import strategies as _strat  # noqa: PLC0415
                    _s = _strat.by_name("ribbon_ride")
                    _shape = _s.exit.to_dict() if _s else None
                except Exception:
                    _shape = None
            if _shape is None:  # fallback to the placed bracket's own pcts
                _shape = {"premium_stop_pct": -0.50, "tp1_premium_pct": float(params.get("tp1_premium_pct", 0.30)),
                          "tp1_qty_fraction": float(params.get("tp1_qty_fraction", 0.667)),
                          "profit_lock_mode": str(params.get("profit_lock_mode", "fixed"))}
            _exit_state = _ea.register_entry(
                ACCOUNTS[account]["fleet_arm"], symbol=symbol, side=side,
                entry_premium=entry_px, qty=qty, exit_shape=_shape, strategy=setup_name,
                trigger_level=_trigger_level, structure_stop_enabled=_structure_enabled)
            plan["exit_managed"] = True
            # VISIBILITY (2026-07-09, render-only; OP-33c/STOP-B known-cosmetic-bug fix): the
            # plan-log "stop" field must show the TRUTH this position is actually managed
            # under. When register_entry just above resolved STRUCTURE mode, the `stop` value
            # computed at line ~1199 (from the flag-OFF premium fallback -- -50% for every
            # non-isolated setup, i.e. ribbon_ride today) is NOT what protects this trade --
            # exit_manager enforces the chart-level + catastrophe cap instead. Both fields are
            # log-only (never sent to the broker -- _place_simple_entry above took only
            # symbol/qty/limit_price), so correcting them here changes nothing about what was
            # placed. Isolated (_xov) setups never declare stop_mode="structure" in `_shape`
            # above, so this is a no-op for every setup except ribbon_ride today.
            if _exit_state is not None and _exit_state.stop_mode == "structure":
                plan["stop"] = _exit_state.runner_stop_premium
                plan["premium_stop_pct"] = _exit_state.catastrophe_stop_pct
            else:
                plan["premium_stop_pct"] = _stop_pct
            plan["stop_display"] = _ea.describe_stop(_exit_state, fallback_price=stop, fallback_pct=_stop_pct)
            plan["stop_mode"] = _exit_state.stop_mode if _exit_state is not None else "premium"
            plan["trigger_level"] = _exit_state.trigger_level if _exit_state is not None else None
        except Exception:  # bookkeeping must never fail an accepted entry
            plan["exit_managed"] = False
    return plan


# ----- extra-setup execution routing (G4) ------------------------------------
# The 4 validated detectors (vwap_continuation / gap_and_go / vwap_reclaim_failed_break /
# vix_regime_dayside) are individually enabled in params (j_*_enabled) to EVALUATE + LOG a
# signal each tick (WATCH). Routing a fired signal to a LIVE order is a SEPARATE arming step,
# gated on params["extra_setup_exec_armed"][setup_name] is True — a NEW key, default ABSENT ->
# nothing armed -> this whole path is a byte-identical no-op. This decouples the detector-enable
# (perception) from the execution-arm (capital): the books are recency-RED (DIRECTION-BLOCK-
# BATCH-RECONCILE) so exec-arm stays OFF until license_monitor clears the RED->green; a J params
# edit (rail-4) arms it setup-by-setup. Execution reuses the SAME _execute (flat-verify +
# quality-lock + risk_gate + place) plus the same free-model veto, so an extra-setup entry is
# held to identical safety as a core ribbon entry.
_EXTRA_DIR_TO_VERDICT = {"long": "ENTER_BULL", "short": "ENTER_BEAR"}


def _synthetic_verdict_from_extra(row: dict) -> "dict | None":
    """Map a FIRED dispatch_extra_setups row to a verdict dict _execute understands.
    Returns None for non-fired / neutral / malformed rows (fail-closed -> no trade).

    FIX (2026-07-09, GATE-PROVENANCE-CENSUS-2026-07-09.md #2 / BUG-CONFIRMED): `side` is
    now populated using the IDENTICAL derivation _execute uses for the core-ribbon path
    (`side = "P" if verdict == ENTER_BEAR else "C"`, see _execute ~L1091) so the free-model
    veto snapshot (_veto_snapshot / _free_model_eval) never renders "side=None" for an
    extra-setup entry. Before this fix, this dict carried ONLY verdict/setup_name/
    triggers_fired -- _free_model_eval's snapshot builder then rendered "side=None
    bear=None/10 bull=None/11" on every extra-setup veto call, and at least 7 of 14
    extra-setup veto events on 2026-07-09 cited that exact malformed prompt as their
    stated reasoning (e.g. 10:31:03 vwap_reclaim_failed_break: "rules_engine_says=
    ENTER_BULL but side=None"), suppressing 5 already-validated setups for a non-reason.
    bear_score/bull_score are deliberately still NOT set here -- extra setups are watcher-
    pattern detectors, not scored on the core engine's 0-10/0-11 scale, so there is no real
    value to report. _veto_snapshot omits those fields when absent rather than fabricate
    a fake "None/10" reading (never fabricate)."""
    if not isinstance(row, dict) or not row.get("fired"):
        return None
    v = _EXTRA_DIR_TO_VERDICT.get(str(row.get("direction", "")).lower())
    if v is None:  # neutral / unknown direction -> no trade
        return None
    sv = {"verdict": v, "side": "P" if v == "ENTER_BEAR" else "C",
          "setup_name": row.get("setup_name"),
          "triggers_fired": list(row.get("triggers") or [])}
    # REJECTION_LEVEL WIRE (2026-07-18, queue GAP-AND-GO-REVALIDATION-BEFORE-ARM blocker B):
    # dispatch_extra_setups already stamps row["stop_price"] from the watcher's own
    # WatcherSignal (setup_dispatch.py:661) — for gap_and_go this IS the go_live_params
    # chart stop (first-RTH-bar opposite extreme), the exact level its validated cell exits
    # on. Before this, _execute's trigger_level resolution (see the "EXACT vs HEURISTIC"
    # comment above _trigger_level_exact) had NOTHING here and fell through to the nearest-
    # key-level PROXIMITY heuristic — a semantically wrong level for a first-bar-extreme
    # stop. Threading it through generically (any extra-setup row with a stop_price) is
    # INERT for every setup that doesn't ALSO declare stop_mode="structure" in
    # _SETUP_EXIT_OVERRIDES (only gap_and_go does, as of this fire) — resolved_structure in
    # exit_manager.ExitState.from_entry requires the shape to opt in first, so
    # vwap_continuation/vix_regime_dayside/etc stay byte-identical "premium" mode regardless
    # of this key's presence. Guard: test_gap_and_go_exit_wiring_2026_07_18.py.
    if row.get("stop_price") is not None:
        sv["rejection_level"] = row.get("stop_price")
    return sv


def _extra_exec_armed(params: dict, setup_name: "str | None") -> bool:
    """A fired extra-setup is routed to a LIVE order ONLY when params explicitly arms it.
    Default (key absent / not a dict / value not True) -> OFF -> the G4 path is a pure no-op."""
    if not setup_name:
        return False
    armed_map = params.get("extra_setup_exec_armed")
    return isinstance(armed_map, dict) and armed_map.get(setup_name) is True


def _route_extra_setups(account: str, extra: list, payload: dict, params: dict) -> list:
    """Route fired + exec-armed extra-setup signals through the SAME _execute path as the
    ribbon verdict. Returns a list of {setup, action, ...} ledger outcomes. Never raises.

    ONE ENTRY PER TICK (2026-07-01, trade-to-learn hardening): with 4 setups armed, two
    rows can fire on the SAME tick (the reclaim/dayside families share trend days; db is
    the opposite side of a below-VWAP day). _execute's flat-verify reads POSITIONS, not
    working orders, so two same-tick placements would both pass it and could fill 3P+3C
    simultaneously — violating one-position-at-a-time. First placement wins the tick;
    later fired rows log SKIP_TICK_ENTRY_TAKEN (they re-fire on a later tick only if
    still the current-bar signal, which the watchers' current-bar guards enforce).

    SAME-BAR RE-ENTRY COOLDOWN (EXTRA-SIGNAL-CHURN-COOLDOWN, 2026-07-20): the watchers'
    current-bar guards stop a setup firing a *duplicate* signal within one bar, but they do
    NOT stop a *fresh* entry once the account goes flat again mid-bar (e.g. a stop-out) --
    live exhibit 2026-07-20 09:51-09:55 ET, safe/vix_regime_dayside: 3x 748C entries on what
    was a single closed 5m bar (09:52/09:53 blocked only by the nondeterministic free-model
    veto, not a real gate), each stopped out in under a minute, net -$87. Before ANY new
    entry attempt for a setup, refuse it if that setup already attempted an entry on this
    EXACT trigger bar (exit_actuator.same_bar_cooldown_active) -- a stop-out on bar N no
    longer re-arms the setup until bar N+1 closes and a genuinely new trigger bar exists.
    Chose "requires-new-trigger-bar" over a hand-picked N-minute duration deliberately: this
    is a brand-new mechanism with no existing trade population to pre-register a numeric
    cooldown against, so the bar-boundary is the smallest non-arbitrary unit available.
    Scoped to the extra-setup lane only (this function) -- the primary ribbon path already
    has its own one-position-at-a-time + gate discipline and is out of this fix's scope.
    Guard: test_extra_signal_churn_cooldown_2026_07_20.py."""
    out: list = []
    placed_this_tick = False
    _TAKEN = {"PLACED", "PLACING", "WOULD_PLACE"}
    _arm = ACCOUNTS.get(account, {}).get("fleet_arm")
    _trigger_bar_et = str(payload.get("bar_ctx", {}).get("timestamp_et") or "") or None
    for row in extra or []:
        sv = _synthetic_verdict_from_extra(row)
        if sv is None:
            continue
        setup = sv.get("setup_name")
        if not _extra_exec_armed(params, setup):
            out.append({"setup": setup, "action": "WATCH_NOT_ARMED"})
            continue
        if placed_this_tick:
            out.append({"setup": setup, "action": "SKIP_TICK_ENTRY_TAKEN"})
            continue
        try:
            import exit_actuator as _ea_cd  # noqa: PLC0415
            if _arm and _ea_cd.same_bar_cooldown_active(_arm, setup, _trigger_bar_et):
                out.append({"setup": setup, "action": "SKIP_COOLDOWN_SAME_BAR",
                           "trigger_bar_et": _trigger_bar_et})
                continue
        except Exception:  # noqa: BLE001 -- fail-open: a cooldown-check error never blocks
            pass
        # SIGHT-FRESHNESS GUARD (DECISION-ROW-SPY-STALENESS, 2026-07-20): the exact live
        # exhibit this fix is built from (09:51-09:55 ET, safe/vix_regime_dayside, see the
        # module-level SIGHT_STALENESS_MAX_DIVERGENCE_USD comment above _stale_trigger_bar)
        # fired on THIS lane -- the extra-setup route reads bc['bar']['close'] via its own
        # BarContext (setup_dispatch._build_ctx -> sameday_5m_bars), the SAME stale-by-design
        # trigger bar the primary path uses. Same cross-check, same fail-open contract.
        _sight = {"checked": False, "stale": False}
        try:
            _sight = _sight_staleness_check(payload.get("bar_ctx", {}).get("bar", {}).get("close"))
        except Exception:  # noqa: BLE001 -- fail-open: a sight-check error never blocks
            pass
        if _sight.get("stale"):
            out.append({"setup": setup, "action": "SKIP_STALE_SIGHT", "sight_check": _sight})
            continue
        try:
            ev = _free_model_eval(account, payload, sv)
            if ev.get("veto"):
                out.append({"setup": setup, "action": "VETOED_BY_MODELS", "free_eval": ev})
                continue
            if not CORE_PLACES_ORDERS:
                out.append({"setup": setup, "action": "PERCEPTION_ONLY"})
                continue
            ex = _reconcile_exec(_execute(account, sv, payload, params, dry=not ARMED))
            out.append({"setup": setup, "action": ex.get("status"), "exec": ex, "sight_check": _sight})
            if ex.get("status") in _TAKEN:
                placed_this_tick = True
                if _arm and _trigger_bar_et:
                    try:
                        _ea_cd.record_entry_bar(_arm, setup, _trigger_bar_et)
                    except Exception:  # noqa: BLE001 -- never abort an already-placed entry
                        pass
        except Exception as e:  # noqa: BLE001 — never crash the tick
            out.append({"setup": setup, "action": "EXTRA_EXEC_ERROR", "err": str(e)[:120]})
    return out


def main() -> int:
    et = _et_now()
    if not _is_rth(et):
        print("skipped (not RTH)")
        return 0
    # TICK-COMPLETE MARKER (2026-08-01, WEEKEND-TWELVE #4 race fix): one id per main()
    # invocation, threaded into BOTH accounts' ledger rows below (additive "core_tick_id"
    # field) so a reader can pair the safe+bold rows that belong to the SAME tick instead of
    # two independent "latest for this account" scans that can straddle the ~1s safe->bold
    # write gap. Microsecond precision off THIS SAME et -> trivially unique per invocation.
    core_tick_id = et.strftime("%Y-%m-%dT%H:%M:%S.%f")
    out = {}
    ok_accounts = []
    for account in ACCOUNTS:
        try:
            out[account] = run_account(account, core_tick_id=core_tick_id)
            ok_accounts.append(account)
        except Exception as e:  # noqa: BLE001
            # PRE-EXISTING GAP, FIXED IN PASSING (2026-08-01, caught by this fire's own new
            # marker test exercising the error branch for the first time): this in-memory dict
            # never carried "verdict", so the summary print below (f"{r.get('verdict'):16}")
            # raised TypeError on a real account exception -- the loop's OWN error path could
            # not run to completion. "ERROR" now mirrors the ledger row's verdict one line down.
            out[account] = {"account": account, "verdict": "ERROR", "error": f"{type(e).__name__}: {e}"}
            _log({"ts_et": et.strftime("%Y-%m-%dT%H:%M:%S"), "account": account,
                  "verdict": "ERROR", "error": str(e)[:200], "core_tick_id": core_tick_id})
    for a, r in out.items():
        print(f"{a:5} verdict={r.get('verdict'):16} ribbon={r.get('ribbon')} "
              f"spread={r.get('spread_cents')}c bear={r.get('bear_score')} bull={r.get('bull_score')} "
              f"action={r.get('action')}")
    # Mark this tick COMPLETE only when BOTH accounts logged a real row this invocation -- an
    # errored account withholds the marker update entirely, so every consumer keeps reading
    # the last GOOD paired tick until this one recovers (never a half-tick surfaced).
    if set(ok_accounts) == set(ACCOUNTS):
        _write_tick_marker(core_tick_id, et)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
