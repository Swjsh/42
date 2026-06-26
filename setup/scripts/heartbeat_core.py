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
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

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
# SHADOW (DISARMED) — left disarmed deliberately; J flips the switch. As of 2026-06-25 the
# historical replay (backtest/replay_heartbeat_core.py) now PASSES the full arm-gate:
#   - bear_score exact-match 98.0% (avg diff 0.02) — input/score wiring byte-faithful
#   - ENTRY FIDELITY 5/5 matched, 0 extra, 0 missed over the 8-day window: after the live
#     FLAT-verify dedup AND the quality-lock (ported below: _quality_lock_check, mirrors the
#     orchestrator's setup_quality_taken_today escalation lock) the live engine trades at the
#     SAME bars/sides the backtest does — no over-trade. SKIP_NO_PULLBACK is irrelevant
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
GATE_KEYS = [
    "block_level_rejection", "trendline_requires_ribbon_flip", "block_elite_bull",
    "block_bull_ribbon_flip", "block_bull_1100_1200", "block_bull_morning_agg",
    "require_bearish_fill_bar", "min_ribbon_momentum_cents", "max_ribbon_duration_bars",
    "midday_trendline_gate", "block_conf_lvl_rej_midday_afternoon", "block_conf_lvl_rec_afternoon",
    "entry_bar_body_pct_min", "entry_bar_body_pct_min_bull", "vix_bear_hard_cap",
    "structure_veto_enabled",
]


def _et_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=-4)


def _is_rth(et: datetime) -> bool:
    h = et.hour + et.minute / 60
    return et.weekday() < 5 and 9.5 <= h <= 16.0


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
        d = yf.download("^VIX", period="2d", interval="5m", auto_adjust=False, progress=False)
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
        d = yf.download("^VIX", period="40d", interval="1d", auto_adjust=False, progress=False)
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


def _read_levels(spy: float) -> tuple[list[float], list[float]]:
    try:
        kl = json.loads((STATE / "key-levels.json").read_text(encoding="utf-8"))
        levels = kl.get("levels") or kl.get("key_levels") or []
        active, multi = [], []
        for lv in levels:
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
                   vix_ma: tuple | None = None) -> dict | None:
    """Live by default; the historical replay injects `vix`=(now,prior),
    `levels`=(active,multi), and `vix_ma`=(5d,20d) so it can reproduce a past bar exactly."""
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
    # Top-level frames the GATES walk via .loc (look-ahead fill-bar + momentum/duration).
    return {"bar_ctx": bar_ctx, "gate_params": gate_params, "score_params": score_params,
            "spy_df": bars_all, "ribbon_df": ribbon_series,
            "sameday_5m_bars": sameday_5m_bars}


def _engine_verdict(payload: dict) -> dict:
    """Pipe to the tested engine_cli (score_bar + 15 gates). Deterministic; fails closed."""
    try:
        proc = subprocess.run([sys.executable, "-m", "backtest.lib.engine.engine_cli"],
                              input=json.dumps(payload), capture_output=True, text=True,
                              cwd=str(REPO), timeout=30)
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        return {"verdict": "SKIP_BAD_INPUT", "error": f"{type(e).__name__}: {e}"}


# ----- 2 free models: veto-only sanity layer ---------------------------------
def _free_model_eval(account: str, payload: dict, verdict: dict) -> dict:
    """2 FREE models each give GO/NO-GO on the rules-engine's ENTER. Veto only — they can
    block a marginal entry, never manufacture one. $0 (groq/cerebras/gemini free pool)."""
    try:
        import swarm_client as sc
    except Exception:
        return {"evaluated": False, "votes": [], "veto": False, "note": "swarm_client unavailable"}
    bc = payload["bar_ctx"]
    snap = (f"SPY={bc['bar']['close']} ribbon={bc['ribbon_now']['stack']} "
            f"spread={bc['ribbon_now']['spread_cents']}c VIX={bc['vix_now']:.2f}(prior {bc['vix_prior']:.2f}) "
            f"HTF15m={bc['htf_15m_stack']} levels_near={bc['levels_active']} "
            f"rules_engine_says={verdict.get('verdict')} side={verdict.get('side')} "
            f"setup={verdict.get('setup_name')} bear={verdict.get('bear_score')}/10 "
            f"bull={verdict.get('bull_score')}/11 triggers={verdict.get('triggers_fired')}")
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


def _manage_exits(account: str) -> list:
    """Run the tick-managed scale-out over this account's open positions (flag-gated caller).
    Places only when ARMED (live); WATCH otherwise. Fail-safe: any error is captured, never
    raised, so the exit pass can never abort the entry/verdict path of the armed brain."""
    try:
        import fleet_broker as fb  # noqa: PLC0415
        import exit_actuator as ea  # noqa: PLC0415
        arm = ACCOUNTS[account]["fleet_arm"]
        creds = fb.load_creds().get(arm)
        if not creds:
            return [{"error": "no_creds", "arm": arm}]
        return ea.manage_tick(arm, creds, live=ARMED, now_et=_et_now())
    except Exception as e:  # noqa: BLE001
        return [{"error": f"manage_exits: {type(e).__name__}: {e}"}]


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
           "triggers": verdict.get("triggers_fired"), "reason": verdict.get("reason")}
    # EXIT-MANAGEMENT PASS (flag-gated, default OFF -> byte-identical armed behavior).
    # Manage every open position's scale-out FIRST (before evaluating a new entry), so a
    # winner's TP1/runner or a stop is realized this tick. Places only when ARMED (live);
    # otherwise computes + logs (WATCH). OFF unless GAMMA_CORE_MANAGES_EXITS=1.
    if CORE_MANAGES_EXITS:
        rec["exit_pass"] = _manage_exits(account)
    # EXTRA-SETUP DISPATCH — evaluates 4 validated detectors that are individually
    # flag-gated in params.json. When ALL flags are OFF (current default) this is a
    # pure no-op: dispatch_extra_setups returns [] in O(1). When a flag is ON, the
    # matching detector builds its own BarContext from sameday_5m_bars, runs the
    # watcher, and logs the result. Order placement via these signals is NOT wired here
    # yet — SKIP_NO_FEED / SKIP_NO_SIGNAL are the expected outputs until each detector
    # is promoted to LIVE. This call must never raise (setup_dispatch fails open).
    try:
        from setup_dispatch import dispatch_extra_setups  # noqa: PLC0415
        extra = dispatch_extra_setups(account, params, payload, verdict, armed=ARMED)
        if extra:
            rec["extra_signals"] = extra
    except Exception as _disp_err:  # noqa: BLE001
        logger.warning("[DISPATCH] setup_dispatch import/run failed: %s", _disp_err)

    v = verdict.get("verdict", "")
    if v in ("ENTER_BEAR", "ENTER_BULL"):
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
            rec["exec"] = _execute(account, verdict, payload, params, dry=not ARMED)
            rec["action"] = rec["exec"].get("status")
    else:
        rec["action"] = v
    _log(rec)
    return rec


def _occ(side: str, strike: int, expiry: datetime) -> str:
    cp = "C" if side == "C" else "P"
    return f"SPY{expiry.strftime('%y%m%d')}{cp}{int(round(strike * 1000)):08d}"


# ----- quality-lock (per-day, per-setup escalation lock) ---------------------
# Faithful port of the orchestrator's SKIP_QUALITY_LOCK (backtest/lib/orchestrator.py
# ~1170-1262 + mutation 1474): at most one trade per (date, setup) unless a strictly
# stronger trigger set fires, with one stop-out leg-2 exemption (same rank allowed only
# if the prior fill stopped AND >=45min has passed). The live engine is stateless, so the
# per-day state is reconstructed each tick from today's own ledger rows (entries written by
# _execute) + the broker (prior-fill stop outcome). Filtering rows to "today ET + this
# account + this setup" gives the orchestrator's day-boundary reset for free.
def _quality_rank(side: str, triggers: list) -> tuple[int, str]:
    """(quality_rank, quality_tier) — mirror of orchestrator.py:1174-1207 ranks.
    SUPER=4, ELITE=3, LEVEL=2, TRENDLINE/BASE=1. side: 'P' (bear) | 'C' (bull)."""
    trig = list(triggers or [])
    level_tied = "level_reclaim" if side == "C" else "level_rejection"
    seq_trig = "sequence_reclaim" if side == "C" else "sequence_rejection"
    has_level = level_tied in trig
    has_confluence = "confluence" in trig
    has_sequence = seq_trig in trig
    has_ribbon_flip = "ribbon_flip" in trig
    has_trendline = "trendline_rejection" in trig
    n = len(trig)
    if (has_confluence and has_ribbon_flip) or n >= 3:
        return 4, "SUPER"
    if has_confluence or has_sequence:
        return 3, "ELITE"
    if has_level:
        return 2, "LEVEL"
    if has_trendline:
        return 1, "TRENDLINE"
    return 1, "BASE"


def _todays_ledger_rows(account: str) -> list[dict]:
    """Today's (ET) committed ledger rows for this account. Tail-read only — cheap."""
    if not LEDGER.exists():
        return []
    today = _et_now().strftime("%Y-%m-%d")
    rows: list[dict] = []
    try:
        with open(LEDGER, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    for line in lines[-400:]:  # a single trading day is well under 400 ticks/account
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("account") != account:
            continue
        if not str(r.get("ts_et", "")).startswith(today):
            continue
        rows.append(r)
    return rows


def _prior_fill_stopped(creds: dict, last_entry_symbol: "str | None") -> tuple[bool, "datetime | None"]:
    """Did the most-recent CLOSED position on this setup today stop out (no TP1, loss)?
    Broker = source of truth (C11). Returns (stopped_without_tp1, last_exit_dt).
    Conservative default (False, None) on any failure -> blocks same-quality re-entry,
    which is the STRICTER behavior (never over-permits a leg-2)."""
    import urllib.request
    try:
        today = _et_now().strftime("%Y-%m-%d")
        url = (creds["base_url"].rstrip("/") +
               f"/v2/account/activities/FILL?date={today}&direction=desc&page_size=100")
        acts = json.loads(urllib.request.urlopen(urllib.request.Request(
            url, headers={"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}),
            timeout=10).read())
        # SPY option sells closing a long today; most recent first. If the close was a
        # stop (price <= entry) with no intervening TP1 partial, treat as stopped_without_tp1.
        sells = [a for a in acts if a.get("symbol", "").startswith("SPY")
                 and a.get("side") in ("sell", "sell_short") and a.get("type") == "fill"]
        if not sells:
            return False, None
        last = sells[0]
        last_exit = None
        try:
            last_exit = datetime.fromisoformat(str(last.get("transaction_time")).replace("Z", "+00:00"))
            last_exit = last_exit + timedelta(hours=-4)  # ET
        except (ValueError, TypeError):
            last_exit = None
        # any partial TP fill on the same symbol today? (qty < position implies a TP1 leg)
        same_sym_sells = [a for a in sells if a.get("symbol") == last.get("symbol")]
        had_partial = len(same_sym_sells) >= 2  # a TP1 leg + runner leg => not a clean stop
        return (not had_partial), last_exit
    except Exception:  # noqa: BLE001 — broker unreachable -> strict default
        return False, None


def _quality_lock_check(account: str, side: str, triggers: list, setup_name: str,
                        creds: dict, now_et: datetime) -> dict:
    """Faithful live port of the orchestrator's escalation lock. Returns
    {"allow": bool, "rank": int, "tier": str, "prior_quality": int, ...}.

    allow rule (orchestrator.py:1218-1234, verbatim):
      rank >  prior                                         -> ENTER (escalation)
      rank == prior AND prior_stopped AND gap >= 45min      -> ENTER (leg-2)
      else                                                  -> BLOCK (SKIP_QUALITY_LOCK)
    """
    rank, tier = _quality_rank(side, triggers)
    rows = _todays_ledger_rows(account)
    # prior_quality = highest quality_rank already TAKEN today on this setup. A row counts
    # as "taken" when it actually placed (or would place in dry/shadow) AND records its rank.
    TAKEN = {"WOULD_PLACE", "PLACING", "PLACED"}
    prior_quality = 0
    last_entry_symbol = None
    for r in rows:
        ex = r.get("exec") or {}
        # quality fields live in the exec sub-dict (see _execute plan); fall back to row-level
        row_setup = ex.get("setup") or r.get("setup")
        row_rank = ex.get("quality_rank")
        if not isinstance(row_rank, int):
            row_rank = r.get("quality_rank")
        if row_setup != setup_name:
            continue
        if (r.get("action") in TAKEN or ex.get("status") in TAKEN) and isinstance(row_rank, int):
            if row_rank >= prior_quality:
                prior_quality = row_rank
                last_entry_symbol = ex.get("symbol") or last_entry_symbol
    if prior_quality == 0:
        return {"allow": True, "rank": rank, "tier": tier, "prior_quality": 0,
                "prior_stopped": False, "gap_min": None}
    if rank > prior_quality:
        return {"allow": True, "rank": rank, "tier": tier, "prior_quality": prior_quality,
                "prior_stopped": None, "gap_min": None}
    # rank <= prior_quality: only the leg-2 exemption can re-open (rank == prior + stopped + gap).
    prior_stopped, last_exit = (False, None)
    if rank == prior_quality:
        prior_stopped, last_exit = _prior_fill_stopped(creds, last_entry_symbol)
    gap_min = None
    gap_ok = False
    if prior_stopped and last_exit is not None:
        gap_min = (now_et - last_exit).total_seconds() / 60.0
        gap_ok = gap_min >= 45.0
    allow = (rank == prior_quality) and prior_stopped and gap_ok
    return {"allow": allow, "rank": rank, "tier": tier, "prior_quality": prior_quality,
            "prior_stopped": prior_stopped, "gap_min": gap_min}


def _execute(account: str, verdict: dict, payload: dict, params: dict, *, dry: bool) -> dict:
    """SIZE + PLACE a 0DTE bracket via the TESTED fleet_broker + risk_gate primitives.
    dry=True computes everything and returns the plan WITHOUT placing (shadow / self-test)."""
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
    day_trades = int(cb.get("day_trades_used_5d") or 0)
    killed = bool(cb.get("tripped")) or (STATE / "kill-switch").exists()
    # FLAT-verify (broker = source of truth, L47/C11)
    if not fb.is_flat_spy_options(creds):
        return {"status": "NOT_FLAT"}
    # QUALITY-LOCK (orchestrator parity, 2026-06-25): being flat is not enough — block a
    # same-or-lower-quality re-entry on the same setup TODAY unless this is a leg-2 re-fire
    # (prior fill stopped + >=45min gap). Without this the live engine over-trades vs the
    # backtest validation by re-entering setups the orchestrator's setup_quality_taken_today
    # lock forbids (measured: +10 SKIP_QUALITY_LOCK bars over the 8-day replay window).
    setup_name = verdict.get("setup_name") or (
        "BEARISH_REJECTION_RIDE_THE_RIBBON" if side == "P" else "BULLISH_RECLAIM_RIDE_THE_RIBBON")
    ql = _quality_lock_check(account, side, verdict.get("triggers_fired") or [],
                             setup_name, creds, _et_now())
    if not ql["allow"]:
        return {"status": "SKIP_QUALITY_LOCK", "quality_rank": ql["rank"], "quality_tier": ql["tier"],
                "prior_quality": ql["prior_quality"], "setup": setup_name,
                "reason": "blocked by quality lock (downgrade or same-quality after winner)"}
    # strike + contract + premium
    strike = ss.pick_strike(spy, equity, side, ss.V15_BOLD_TIERS if account == "bold" else ss.V15_SAFE_TIERS) \
        if ss else (int(round(spy)) + (2 if side == "P" else -2))
    expiry = _et_now()
    symbol = _occ(side, strike, expiry)
    mid = fb.get_option_mid(creds, symbol)
    if not mid or mid <= 0:
        return {"status": "NO_PREMIUM", "symbol": symbol}
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
    tp = round(mid * (1 + float(params.get("tp1_premium_pct", 0.30))), 2)
    stop = round(mid * (1 - 0.50), 2)  # -50% catastrophe cap (chart-stop is a v2 enhancement)
    plan = {"status": "WOULD_PLACE" if dry else "PLACING", "symbol": symbol, "side": side,
            "strike": strike, "qty": qty, "premium": mid, "tp": tp, "stop": stop, "equity": equity,
            # quality fields persisted so the NEXT tick's quality-lock can read prior_quality
            "setup": setup_name, "quality_rank": ql["rank"], "quality_tier": ql["tier"]}
    if dry:
        return plan
    # Options reject broker brackets/oto (code 42210000) -> place a SIMPLE limit entry and
    # let the tick-managed exit_manager own TP/stop. Gated on CORE_MANAGES_EXITS so a simple
    # (stopless-at-broker) entry is NEVER placed unless the engine is managing exits (else it
    # stays PLACE_FAIL, the safe no-op). 2026-06-26: this was the bug blocking every entry.
    res = fb.place_bracket(creds, symbol=symbol, qty=qty, limit_price=mid,
                           take_profit_price=tp, stop_price=stop, live=True,
                           simple_fallback=CORE_MANAGES_EXITS)
    plan["status"] = "PLACED" if not res.get("_error") else "PLACE_FAIL"
    plan["broker"] = res
    # EXIT-ENGINE WIRING (flag-gated, default OFF): on a real fill, register the position
    # with the exit_manager so the validated scale-out (partial TP1 + runner + profit-lock)
    # is realized on later ticks. The bracket above stays the catastrophe-floor backstop;
    # the exit_manager owns the partial TP1 + runner ride the single bracket cannot express.
    # OFF by default -> byte-identical armed behavior (no registration, single bracket only).
    if CORE_MANAGES_EXITS and plan["status"] == "PLACED":
        try:
            import exit_actuator as _ea  # noqa: PLC0415
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
            _ea.register_entry(ACCOUNTS[account]["fleet_arm"], symbol=symbol, side=side,
                               entry_premium=mid, qty=qty, exit_shape=_shape, strategy=setup_name)
            plan["exit_managed"] = True
        except Exception:  # bookkeeping must never fail an accepted entry
            plan["exit_managed"] = False
    return plan


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
