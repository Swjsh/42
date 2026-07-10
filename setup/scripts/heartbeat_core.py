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
    present (the core-ribbon path, always true today) -- this is a pure extraction there."""
    bear, bull = verdict.get("bear_score"), verdict.get("bull_score")
    scores = " ".join(s for s in (
        f"bear={bear}/10" if bear is not None else None,
        f"bull={bull}/11" if bull is not None else None,
    ) if s)
    setup_seg = f"setup={verdict.get('setup_name')}"
    if scores:
        setup_seg += f" {scores}"
    return (f"SPY={bc['bar']['close']} ribbon={bc['ribbon_now']['stack']} "
            f"spread={bc['ribbon_now']['spread_cents']}c VIX={bc['vix_now']:.2f}(prior {bc['vix_prior']:.2f}) "
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
              "you cannot create one. Default go=true unless something is clearly wrong. JSON only.")
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


def run_account(account: str) -> dict:
    cfg = ACCOUNTS[account]
    params = json.loads(cfg["params"].read_text(encoding="utf-8"))
    df = _fetch_spy_5m()
    payload = _build_payload(df, params)
    et = _et_now()
    if payload is None:
        rec = {"ts_et": et.strftime("%Y-%m-%dT%H:%M:%S"), "account": account,
               "verdict": "SKIP_NO_DATA", "armed": ARMED}
        _log(rec)
        return rec
    verdict = _engine_verdict(payload)
    bc = payload["bar_ctx"]
    rec = {"ts_et": et.strftime("%Y-%m-%dT%H:%M:%S"), "account": account, "armed": ARMED,
           "spy": bc["bar"]["close"], "ribbon": bc["ribbon_now"]["stack"],
           "spread_cents": bc["ribbon_now"]["spread_cents"], "vix": round(bc["vix_now"], 2),
           "htf_15m": bc["htf_15m_stack"], "verdict": verdict.get("verdict"),
           "side": verdict.get("side"), "setup": verdict.get("setup_name"),
           "bear_score": verdict.get("bear_score"), "bull_score": verdict.get("bull_score"),
           "triggers": verdict.get("triggers_fired"), "reason": verdict.get("reason"),
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
           "trigger_level_exact": verdict.get("rejection_level")}
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

    v = verdict.get("verdict", "")
    if v in ("ENTER_BEAR", "ENTER_BULL") and _past_entry_ceiling(params, et):
        # FIX1 (2026-07-01): entry-time ceiling — a late ENTER is a logged SKIP, never an
        # order attempt (2026-06-30: all 10 ENTER verdicts fired 15:51-15:55, all rejected
        # by Alpaca 'expires soon'). Checked BEFORE the free-model eval so a late tick spends
        # nothing. _execute has the same check (belt-and-suspenders for the extra-setup route).
        rec["action"] = "SKIP_LATE_ENTRY"
        rec["entry_ceiling_et"] = str(params.get("entry_no_trade_after_et") or "15:00")
    elif v in ("ENTER_BEAR", "ENTER_BULL") and _stale_trigger_bar(payload, et):
        # FIX (2026-07-02): prior-day trigger bar — yesterday's signal, not today's.
        rec["action"] = "SKIP_STALE_TRIGGER"
        rec["trigger_bar_et"] = str(payload["bar_ctx"].get("timestamp_et"))
    elif v in ("ENTER_BEAR", "ENTER_BULL") and _before_entry_floor(params, et):
        # FIX (2026-07-02): wall-clock floor — [09:35, 15:00) now enforced on BOTH ends.
        rec["action"] = "SKIP_EARLY_ENTRY"
        rec["entry_floor_et"] = str(params.get("entry_no_trade_before_et") or "09:35")
    elif v in ("ENTER_BEAR", "ENTER_BULL"):
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
        # G4: on a non-ENTER ribbon verdict (HOLD/SKIP), route any fired + exec-armed extra
        # setup through the SAME _execute path. Default = byte-identical no-op (no setup is
        # exec-armed -> every fired row logs WATCH_NOT_ARMED, _execute is never called). The
        # else-branch placement guarantees the ribbon path and an extra setup never double-
        # place on the same tick (and _execute's own is_flat check is the backstop).
        #
        # FIX (2026-07-06, post-mortem on today's session): structure_veto is a purpose-built
        # directional safety gate (engine_cli.py, added after the 2026-06-26 -$237 wrong-way
        # entry) and was blind to this side-channel — 7 extra-setup entries fired today while
        # the primary verdict was SKIP_STRUCTURE_VETO/HOLD, including one buying the EXACT
        # direction structure_veto had just blocked on the same tick (net -$33 on that
        # cluster). When the primary verdict IS a structure veto, no extra-setup entry fires
        # this tick either — the gate's premise ("this tick's structure makes a new
        # directional entry dangerous") applies account-wide, not just to the primary path.
        # Guard: test_graduated_guards.py::test_structure_veto_blocks_extra_setup_route.
        if extra and v != "SKIP_STRUCTURE_VETO":
            routed = _route_extra_setups(account, extra, payload, params)
            if routed:
                rec["extra_exec"] = routed
        elif extra:
            rec["extra_exec_blocked_by"] = "structure_veto"
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
}
# ISOLATED per-setup exit knobs (params _j_*_isolated_exit_doc): the validated cells for
# these setups carry their OWN stop/TP1 — silently sourcing the global -50% catastrophe
# cap would trade an UNVALIDATED cell (C14/L149; for vix_regime_dayside the -8% stop is
# LOAD-BEARING per its G8 gate). vwap_continuation ADDED 2026-07-02 (exit-parity A/B,
# analysis/recommendations/vwapcont-exit-parity.json): un-overridden it was exit-managed
# by the ribbon_ride shape (-20% stop / tp1 +150%) — a WR-22% lotto with NEGATIVE
# J-anchor capture; its validated cell (stop -0.08 / tp1 0.30) wins per OP-16.
# "runner" is optional.
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
    strike = ss.pick_strike(spy, equity, side, ss.V15_BOLD_TIERS if account == "bold" else ss.V15_SAFE_TIERS) \
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
        kill_switch_tripped=killed, prior_stops_today=[], params=params)
    if not getattr(decision, "allowed", False):
        return {"status": f"RISK_DENY_{getattr(decision,'code','?')}", "reason": getattr(decision, "reason", ""),
                "symbol": symbol, "qty": qty, "premium": mid}
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
            "setup": setup_name}
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
    return {"verdict": v, "side": "P" if v == "ENTER_BEAR" else "C",
            "setup_name": row.get("setup_name"),
            "triggers_fired": list(row.get("triggers") or [])}


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
    still the current-bar signal, which the watchers' current-bar guards enforce)."""
    out: list = []
    placed_this_tick = False
    _TAKEN = {"PLACED", "PLACING", "WOULD_PLACE"}
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
            ev = _free_model_eval(account, payload, sv)
            if ev.get("veto"):
                out.append({"setup": setup, "action": "VETOED_BY_MODELS", "free_eval": ev})
                continue
            if not CORE_PLACES_ORDERS:
                out.append({"setup": setup, "action": "PERCEPTION_ONLY"})
                continue
            ex = _reconcile_exec(_execute(account, sv, payload, params, dry=not ARMED))
            out.append({"setup": setup, "action": ex.get("status"), "exec": ex})
            if ex.get("status") in _TAKEN:
                placed_this_tick = True
        except Exception as e:  # noqa: BLE001 — never crash the tick
            out.append({"setup": setup, "action": "EXTRA_EXEC_ERROR", "err": str(e)[:120]})
    return out


def main() -> int:
    et = _et_now()
    if not _is_rth(et):
        print("skipped (not RTH)")
        return 0
    out = {}
    for account in ACCOUNTS:
        try:
            out[account] = run_account(account)
        except Exception as e:  # noqa: BLE001
            out[account] = {"account": account, "error": f"{type(e).__name__}: {e}"}
            _log({"ts_et": et.strftime("%Y-%m-%dT%H:%M:%S"), "account": account,
                  "verdict": "ERROR", "error": str(e)[:200]})
    for a, r in out.items():
        print(f"{a:5} verdict={r.get('verdict'):16} ribbon={r.get('ribbon')} "
              f"spread={r.get('spread_cents')}c bear={r.get('bear_score')} bull={r.get('bull_score')} "
              f"action={r.get('action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
