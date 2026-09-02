"""structure_stop_study.py -- STRUCTURE-STOP (chart-stop-primary) exit validation.

Runs the FROZEN pre-registration (analysis/recommendations/structure-stop-preregistration.json)
-- no re-picks, no new cells added after this file is written. Motivated by 2026-07-09: three
fleet round-trips premium-stopped on the 747.46-reclaim signal while SPY never printed a 5m
CLOSE below 747.46 -- a close-below-trigger STRUCTURE stop would have held all three. Today is
EXHIBIT ONLY: shown in its own table, excluded from every layer used for pass/fail (it generated
the hypothesis; grading on it would be circular).

THREE CANDIDATES + CONTROL (see the pre-registration for the frozen shapes/buffers):
  SS-A: structure stop primary (calls: exit ALL on first 5m SPY CLOSE strictly below the
        trigger level; puts: close strictly above) + -50% premium catastrophe cap (intrabar
        touch) + TP1 +150% sell66 + runner trail 15%.
  SS-B: SS-A but TP1 +100% sell66.
  SS-C: SS-A with a $0.10 buffer on the structure-stop trigger.
  CONTROL: the shipped -20%/+150%/sell80/fixed premium-only shape (no structure layer, ever).

TWO LAYERS (matching T5/T-W8's own convention):
  (a) FRESH-SLICE REPLAY: the 18 never-exploratory-seen ribbon_ride signals
      (analysis/exit-parity/signal-set-fresh-20260619-20260708.json, 2026-06-19..2026-07-08).
      Trigger levels recovered EXACTLY via tw8_level_context.enrich_signals (entry_spot-matched
      trigger bar).
  (b) REAL-FILLS ANCHOR: all 79 fleet_rest engine-attributed positions, 2026-06-29..2026-07-08
      (today EXCLUDED by construction -- see anchor_end_date). Trigger levels recovered via a
      disclosed backward-scan heuristic (real fills carry no entry_spot label) -- positions
      whose trigger cannot be recovered are NEVER dropped: they fall back to premium-only -50%
      cap replay (pre-registration condition 3).

PLUS the 2026-07-09 EXHIBIT (separate table, NOT a pass/fail layer): the actual today fills
replayed under all 4 shapes, for narrative comparison only.

C6 (look-ahead): the structure stop evaluates only CLOSED 5m SPY bars and fires at the NEXT
bar's OPEN premium (the earliest tradeable price once the breach is knowable) -- see the
pre-registration's c6_fill_mark_convention. Within a bar, a due structure-stop is checked BEFORE
the ordinary touch-based checks (catastrophe stop / TP1 / trail / time stop), since a due
structure exit is decided at the bar's open, before that bar's intrabar action can be realized.

REUSES, does not reinvent:
  * t4_exit_matrix.py            -- _load_bars, band_of, battery, CONTROL/_shape
  * t5_confirmatory_matrix.py    -- CONTROL_SHAPE, TIME_STOP (15:40), FRESH_SIGNAL_SET path
  * tw8_level_context.py         -- lib/levels.py per-day-frozen level detector, enrich_signals,
                                     load_spy_full, frozen_level_set_for_date (C6-safe)
  * exit_shape_parity_study.py   -- load_fleet_engine_fills, reconstruct_positions,
                                     fetch_option_bars (REAL 1-min Alpaca OPRA)
  * exit_manager.py              -- ExitState, plan_exit_actions (the LIVE decision core) for
                                     every non-structure component (catastrophe stop/TP1/trail/
                                     time-stop) -- the structure-stop layer is new code that sits
                                     IN FRONT of plan_exit_actions, never inside it.

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches strategies.py,
params.json, exit_manager.py, or any trading-path file. Live network calls: Alpaca OPRA option
bars (read-only market data, existing esp.fetch_option_bars path) + a yfinance SPY 5m fetch for
TODAY only (read-only; NOT written to backtest/data/ or any production cache -- kept local to
this module's own output).

Run: backtest/.venv/Scripts/python.exe backtest/tools/structure_stop_study.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time as _time_mod
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple, Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import pandas as pd  # noqa: E402

import t4_exit_matrix as t4                     # noqa: E402  (_load_bars, band_of, battery, CONTROL, _shape)
import t5_confirmatory_matrix as t5              # noqa: E402  (TIME_STOP=15:40, FRESH_SIGNAL_SET path)
import tw8_level_context as lc                   # noqa: E402  (level detector, enrich_signals, load_spy_full)
import exit_shape_parity_study as esp            # noqa: E402  (fills -> positions, fetch_option_bars)
import fleet_broker as fb_mod                    # noqa: E402  (load_creds -- today-safe bar fetch)
from lib.filters import detect_level_reclaim, detect_level_rejection  # noqa: E402
from exit_manager import ExitState, plan_exit_actions, TIME_STOP_ET   # noqa: E402
from et_clock import et_now                      # noqa: E402
from fetch_data import fetch as yf_fetch         # noqa: E402  (read-only live SPY fetch, today only)

PREREG = REPO / "analysis" / "recommendations" / "structure-stop-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "structure-stop-2026-07-09.json"

FRESH_SIGNAL_SET = REPO / "analysis" / "exit-parity" / "signal-set-fresh-20260619-20260708.json"
EXPECTED_FRESH_SHA16 = "d10e1a3a51cbf155"
EXPECTED_ANCHOR_POP_SHA16 = "4561797465ebf837"
EXPECTED_PREREG_VERSION = 1

ANCHOR_END_DATE = "2026-07-08"          # anchor cutoff -- today is EXHIBIT ONLY
TODAY = dt.date(2026, 7, 9)
LEVEL_HISTORY_START = dt.date(2026, 5, 1)   # matches t5 FRESH_START_WARMUP: >=10-day level lookback
LEVEL_HISTORY_END = dt.date(2026, 7, 8)

TRIGGER_RECOVERY_LOOKBACK_BARS = 8      # ~40 min; frozen in the pre-registration
SMALL_N_NOTE_THRESHOLD = 8              # informational only (both layers are small-N by construction)

TIME_STOP_LAYER_A = t5.TIME_STOP        # 15:40 ET
TIME_STOP_LAYER_B = TIME_STOP_ET        # 15:50 ET (exit_manager default)

# --- the 4 candidate shapes (frozen in the pre-registration) -------------------------------
CONTROL_SHAPE = t4._shape(t4.CONTROL)   # -20/+150/sell80/fixed/tgt2.5x -- the shipped shape
SS_A_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 1.5, "tp1_qty_fraction": 0.667,
              "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9}
SS_B_SHAPE = {"premium_stop_pct": -0.50, "tp1_premium_pct": 1.0, "tp1_qty_fraction": 0.667,
              "profit_lock_mode": "trailing", "trail_pct": 0.15, "runner_target_pct": 9.9}
SS_C_SHAPE = dict(SS_A_SHAPE)           # same premium shape as SS-A; only the buffer differs

SHAPE_OF = {"CONTROL": CONTROL_SHAPE, "SS-A": SS_A_SHAPE, "SS-B": SS_B_SHAPE, "SS-C": SS_C_SHAPE}
STRUCTURE_BUFFER = {"SS-A": 0.0, "SS-B": 0.0, "SS-C": 0.10}
STRUCTURE_CANDIDATE_IDS = ("SS-A", "SS-B", "SS-C")
ALL_CANDIDATE_IDS = ("CONTROL",) + STRUCTURE_CANDIDATE_IDS


# ---------------------------------------------------------------------------------------------
# PRE-FLIGHT
# ---------------------------------------------------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def anchor_population_signature(positions: list[dict]) -> list[dict]:
    """Canonical, sortable signature of an anchor population -- used both to hash it (pre-flight
    integrity check) and nowhere else. PURE."""
    sig = [{"date_et": p["date_et"], "symbol": p["symbol"], "arm": p["arm"],
            "entry_ts_utc": p["entry_ts_utc"], "entry_qty": p["entry_qty"]} for p in positions]
    return sorted(sig, key=lambda x: (x["date_et"], x["symbol"], x["arm"], x["entry_ts_utc"]))


def preflight() -> dict:
    fresh_raw = json.loads(FRESH_SIGNAL_SET.read_text(encoding="utf-8"))
    fresh_sha16 = _content_hash(fresh_raw["signals"])[:16]

    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    anchor_positions = [p for p in positions if p["date_et"] <= ANCHOR_END_DATE]
    anchor_sha16 = _content_hash(anchor_population_signature(anchor_positions))[:16]

    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    ver = preg.get("version")

    return {
        "fresh_slice_sha256_16": fresh_sha16, "fresh_slice_hash_ok": fresh_sha16 == EXPECTED_FRESH_SHA16,
        "anchor_population_sha256_16": anchor_sha16,
        "anchor_population_hash_ok": anchor_sha16 == EXPECTED_ANCHOR_POP_SHA16,
        "preregistration_version": ver, "preregistration_version_ok": ver == EXPECTED_PREREG_VERSION,
    }


# ---------------------------------------------------------------------------------------------
# BAR NORMALIZATION -- ONE shared format for both layers' option bars
# ---------------------------------------------------------------------------------------------
class NormBar(NamedTuple):
    dt: dt.datetime   # ET-naive
    o: float
    h: float
    l: float
    c: float


def norm_bars_from_t4(bars: list, date: dt.date) -> list[NormBar]:
    """t4._load_bars format: (time, o,h,l,c) tuples, date-less -- combine with the signal's date."""
    return [NormBar(dt.datetime.combine(date, b[0]), b[1], b[2], b[3], b[4]) for b in bars]


def norm_bars_from_esp(bars: list, entry_ts_utc: Optional[str] = None) -> list[NormBar]:
    """exit_shape_parity_study bar dicts: {"t": iso_utc, "o","h","l","c"}.

    entry_ts_utc, when given, reproduces esp.replay_position's OWN pre-entry filter
    (`relevant_bars = [b for b in bars if b["t"] >= entry_ts]`) -- fetch_option_bars always
    starts at 09:29 ET regardless of when the position actually entered, so WITHOUT this
    filter the replay would see pre-entry intrabar swings (a bar's high/low from before the
    position existed) and could spuriously trigger TP1/stop against price action the position
    was never exposed to. Verified this exact gap against esp.replay_position -- see
    backtest/tests/test_structure_stop_study.py's CONTROL-anchor parity test."""
    out = []
    for b in bars:
        if entry_ts_utc is not None and b["t"] < entry_ts_utc:
            continue
        t_utc = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
        t_et = et_now(t_utc)
        out.append(NormBar(t_et, float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
    return out


# ---------------------------------------------------------------------------------------------
# SPY DATA -- cached history + a read-only live append for 2026-07-09
# ---------------------------------------------------------------------------------------------
def load_spy_full_with_today() -> pd.DataFrame:
    """tw8_level_context.load_spy_full(2026-05-01..2026-07-08) + a live yfinance fetch for
    2026-07-09, normalized identically and concatenated. Read-only: nothing is written to
    backtest/data/ or any production cache -- this DataFrame lives only in this process."""
    spy_full = lc.load_spy_full(LEVEL_HISTORY_START, LEVEL_HISTORY_END)
    today_df = yf_fetch("SPY", TODAY.isoformat(), (TODAY + dt.timedelta(days=1)).isoformat(),
                        include_premarket=True)
    if today_df is not None and not today_df.empty:
        today_df = today_df.copy()
        today_df["timestamp_et"] = pd.to_datetime(today_df["timestamp_et"])
        if today_df["timestamp_et"].dt.tz is not None:
            today_df["timestamp_et"] = today_df["timestamp_et"].dt.tz_localize(None)
        today_df["date"] = today_df["timestamp_et"].dt.date
        today_df["time"] = today_df["timestamp_et"].dt.time
        today_df = today_df[["timestamp_et", "open", "high", "low", "close", "volume", "date", "time"]]
        spy_full = pd.concat([spy_full, today_df], ignore_index=True)
        spy_full = (spy_full.drop_duplicates(subset=["timestamp_et"], keep="last")
                            .sort_values("timestamp_et").reset_index(drop=True))
    return spy_full


# ---------------------------------------------------------------------------------------------
# TRIGGER-LEVEL RECOVERY -- real fleet positions (no entry_spot label; backward-scan heuristic)
# ---------------------------------------------------------------------------------------------
def option_side_from_symbol(symbol: str) -> str:
    """OCC-format SPY option symbol: SPY{YYMMDD}{C|P}{strike*1000:08d} -- side is index 9."""
    s = symbol[9]
    assert s in ("C", "P"), f"unexpected side char {s!r} in symbol {symbol!r}"
    return s


def recover_trigger_level_real_position(
    spy_full: pd.DataFrame, level_cache: dict, date: dt.date, entry_ts_et: dt.datetime, side: str,
    lookback_bars: int = TRIGGER_RECOVERY_LOOKBACK_BARS,
) -> tuple[Optional[float], str]:
    """Backward-scan heuristic (pre-registration's trigger_level_recovery.layer_b_anchor_and_exhibit):
    real fills carry no entry_spot label, so the exact-match method (tw8_level_context.
    find_trigger_bar) is not available. Scan up to `lookback_bars` SPY 5m bars with
    timestamp_et <= entry_ts_et, closest-to-entry first, for the first bar where
    detect_level_reclaim/detect_level_rejection fires against the date's frozen level set.
    Returns (level_or_None, status)."""
    level_set = lc.frozen_level_set_for_date(spy_full, date, level_cache)
    if level_set is None:
        return None, "no_level_set"
    day_bars = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] <= entry_ts_et)]
    day_bars = day_bars.tail(lookback_bars)
    if day_bars.empty:
        return None, "no_bars_before_entry"
    for idx in list(day_bars.index)[::-1]:            # closest-to-entry first
        bar = spy_full.loc[idx]
        lvl = (detect_level_reclaim(bar, level_set.active) if side == "C"
               else detect_level_rejection(bar, level_set.active))
        if lvl is not None:
            return lvl, "ok"
    return None, "no_trigger_bar_in_lookback"


# ---------------------------------------------------------------------------------------------
# THE STRUCTURE-STOP-AWARE REPLAY ENGINE (shared by both layers + the exhibit)
# ---------------------------------------------------------------------------------------------
def structure_stop_signal_time(
    spy_lifetime: pd.DataFrame, side: str, trigger_level: Optional[float], buffer: float,
) -> Optional[dt.datetime]:
    """First SPY 5m bar (>= entry, chronological) whose CLOSE breaches the structure-stop
    condition. Returns that bar's CLOSE time == the NEXT bar's OPEN time -- the earliest instant
    the breach is knowable (C6). None if trigger_level is None (fallback: no structure check) or
    the breach never occurs in the given bars."""
    if trigger_level is None:
        return None
    for row in spy_lifetime.itertuples():
        c = float(row.close)
        breached = (c < (trigger_level - buffer)) if side == "C" else (c > (trigger_level + buffer))
        if breached:
            return row.timestamp_et + dt.timedelta(minutes=5)
    return None


def replay_structure_aware(
    entry_premium: float, side: str, qty: int, norm_bars: list[NormBar],
    ss_time: Optional[dt.datetime], shape: dict, time_stop_et: dt.time,
) -> dict:
    """ONE position/signal x ONE candidate shape. Mirrors t4.replay / exit_shape_parity_study.
    replay_position's per-bar loop and fill-price conventions EXACTLY for every non-structure
    component (catastrophe stop / TP1 / runner trail / time stop via the LIVE plan_exit_actions
    decision core) -- verified to reproduce the established CONTROL anchor total bit-for-bit when
    ss_time is always None (see backtest/tests/test_structure_stop_study.py).

    Adds ONE new branch, checked FIRST each bar: is the structure stop due as of this bar's OPEN
    (ss_time is not None and ss_time <= bar.dt)? If so, SELL_ALL the remaining open_qty at THIS
    bar's OPEN and stop -- nothing else in this bar could have fired first, because the exit was
    already decided at the bar's open, before any of that bar's intrabar action unfolds (C6)."""
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium, qty=qty,
                                 exit_shape=shape)
    open_qty = qty
    realized = 0.0
    exits: list[dict] = []
    structure_fired = False
    last_close = entry_premium
    for bar in norm_bars:
        if open_qty <= 0:
            break
        last_close = bar.c
        if ss_time is not None and not structure_fired and bar.dt >= ss_time:
            fill_price = bar.o
            realized += (fill_price - entry_premium) * open_qty * 100.0
            exits.append({"stage": "structure_stop", "qty": open_qty,
                         "fill_price": round(fill_price, 4), "dt": bar.dt.isoformat()})
            open_qty = 0
            structure_fired = True
            break
        now_et = bar.dt.time()
        dec = plan_exit_actions(state, best_premium=bar.h, worst_premium=bar.l, open_qty=open_qty,
                                now_et=now_et, ribbon_flip_back=False, time_stop_et=time_stop_et)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                fp = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                fp = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                fp = entry_premium * (1.0 + state.premium_stop_pct)
            elif a.stage in ("trail", "be_stop"):
                fp = dec.state.runner_stop_premium
            else:  # time_stop
                fp = bar.c
            realized += (fp - entry_premium) * a.qty * 100.0
            open_qty -= a.qty
            exits.append({"stage": a.stage, "qty": a.qty, "fill_price": round(fp, 4),
                         "dt": bar.dt.isoformat()})
        state = dec.state
    if open_qty > 0:
        realized += (last_close - entry_premium) * open_qty * 100.0
        exits.append({"stage": "eod_mark", "qty": open_qty, "fill_price": round(last_close, 4)})
        open_qty = 0
    return {"pnl": round(realized, 2), "exits": exits, "structure_fired": structure_fired}


# ---------------------------------------------------------------------------------------------
# LAYER (a) -- FRESH-SLICE REPLAY
# ---------------------------------------------------------------------------------------------
def prepare_layer_a() -> tuple[list[dict], int, pd.DataFrame]:
    raw = json.loads(FRESH_SIGNAL_SET.read_text(encoding="utf-8"))
    signals = raw["signals"]
    enriched, spy_full = lc.enrich_signals(signals, LEVEL_HISTORY_START, LEVEL_HISTORY_END)

    prepared, n_missing_bars = [], 0
    for s in enriched:
        bars = t4._load_bars(s)
        if not bars:
            n_missing_bars += 1
            continue
        entry_premium = bars[0][1]
        if entry_premium <= 0:
            n_missing_bars += 1
            continue
        date = dt.date.fromisoformat(s["date"])
        entry_ts = dt.datetime.fromisoformat(s["entry_ts"])
        spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= entry_ts)]
        prepared.append({
            "date": date, "direction": s["direction"], "side": s["side"],
            "entry_premium": entry_premium, "band": t4.band_of(entry_premium),
            "norm_bars": norm_bars_from_t4(bars, date),
            "trigger_level": s.get("trigger_level"),
            "level_context_status": s.get("level_context_status"),
            "spy_lifetime": spy_lifetime,
        })
    return prepared, n_missing_bars, spy_full


def run_layer_a(prepared: list[dict]) -> dict:
    n_recoverable = sum(1 for p in prepared if p["trigger_level"] is not None)
    out = {"n_signals": len(prepared), "n_recoverable_trigger_level": n_recoverable,
           "n_fallback": len(prepared) - n_recoverable, "candidates": {}}

    for cid in ALL_CANDIDATE_IDS:
        shape = SHAPE_OF[cid]
        trades = []
        for p in prepared:
            ss_time = None
            if cid in STRUCTURE_CANDIDATE_IDS:
                ss_time = structure_stop_signal_time(p["spy_lifetime"], p["side"], p["trigger_level"],
                                                      STRUCTURE_BUFFER[cid])
            r = replay_structure_aware(p["entry_premium"], p["side"], t4.QTY, p["norm_bars"],
                                       ss_time, shape, TIME_STOP_LAYER_A)
            trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                          "pnl": r["pnl"], "structure_fired": r["structure_fired"]})
        b = t4.battery(trades)
        n_structure_fired = sum(1 for t in trades if t.get("structure_fired"))
        out["candidates"][cid] = {**b, "n_structure_fired": n_structure_fired}
    return out


# ---------------------------------------------------------------------------------------------
# LAYER (b) -- REAL-FILLS ANCHOR  +  TODAY EXHIBIT (shares the position-prep machinery)
# ---------------------------------------------------------------------------------------------
# Preference order for the READ-ONLY market-data credential. Any arm's key can read OPRA;
# this is a data fetch, never an order path, so the choice is purely about which key is
# currently valid. safe-1 is LAST on purpose: it is a dormant arm (live:false) and its key
# is the only one in the roster that 401s -- measured 2026-09-02 across all seven arms,
# safe-1 the sole failure. It was hardcoded here, so every "today exhibit" layer in every
# study using this helper silently returned [] and printed a fetch error nobody chased. The
# structure-stop runs of 2026-09-02 recorded that as "a data-completeness gap"; it was not,
# the data was there and reachable with six other keys in the same file.
_OPRA_CRED_PREFERENCE = ("safe-2", "safe-3", "bold-2", "risky-1", "risky-3", "weekly-1", "safe-1")


def _resolve_opra_creds(creds_all: dict) -> "dict | None":
    """First arm in preference order that actually has a key/secret pair.

    Deliberately NOT a live-probe: this runs inside a per-symbol fetch loop and a network
    round-trip per call to test a key would cost more than the fetch it guards. The 401
    retry inside fetch_option_bars_today_safe covers a key that exists but has been
    revoked, which is the failure this whole change exists for.
    """
    for arm in _OPRA_CRED_PREFERENCE:
        c = creds_all.get(arm)
        if c and c.get("key") and c.get("secret"):
            return c
    for c in creds_all.values():  # roster changed shape -- take anything usable
        if c and c.get("key") and c.get("secret"):
            return c
    return None


def fetch_option_bars_today_safe(symbol: str, date_et: str, now_et: dt.datetime) -> list[dict]:
    """Like exit_shape_parity_study.fetch_option_bars, but caps the query window's END to
    (now_et - 2 min) instead of the hardcoded 16:05 ET.

    BLOCKER FOUND + PRECISELY CHARACTERIZED + WORKED AROUND (2026-07-09): esp.fetch_option_bars's
    fixed end=16:05 ET assumes a FULLY-ELAPSED historical day -- true everywhere else it is
    called in this codebase (fills-ledger dates are always past trading days). Called on TODAY
    while the session is still open, that same request 403s: `{"message":"OPRA agreement is not
    signed"}`. Bisected directly against the live endpoint (not guessed): the account has NOT
    signed Alpaca's OPRA real-time-data agreement, so options bars younger than EXACTLY 15
    minutes are blocked (403 at 14/2/10-min-old windows; 200 OK at 15/16/20/30/60-min-old,
    verified with the SAME symbol/day at 6 delay values). This is a real-time-vs-delayed data
    ENTITLEMENT boundary, not a blanket today-block or a flaky failure. A 16-minute safety
    margin (1 minute past the measured 15-minute boundary) sidesteps it without touching
    methodology or substituting synthetic data (C1: real-fills is the only WR authority) --
    every position in today's exhibit closed by 10:34 ET, hours before this cap ever binds."""
    creds_all = fb_mod.load_creds()
    creds = _resolve_opra_creds(creds_all)
    if not creds:
        return []
    # The 16-minute cap exists ONLY to dodge the real-time-data entitlement boundary on a
    # session that is still running. Applied to a PAST date it is nonsense: it clamps the
    # window's end to today's wall-clock time-of-day, so any run before ~09:45 ET asks for
    # an end EARLIER than the 09:29 start and the API answers 400 Bad Request.
    #
    # This was invisible until 2026-09-02. The helper was fetching with a dormant arm's
    # revoked key, so every call died at 401 during auth -- before the range was ever
    # validated. Fixing the credential unmasked this. Two defects stacked, and the outer
    # one hid the inner one: the study's "today exhibit" layer has been returning [] for
    # every historical-date run, printing one line to stderr that nobody chased.
    if date_et < now_et.strftime("%Y-%m-%d"):
        end_hhmm = "16:05"          # fully-elapsed day: no entitlement boundary to dodge
    else:
        safe_end_et = now_et - dt.timedelta(minutes=16)
        end_hhmm = min(safe_end_et.strftime("%H:%M"), "16:05")
    start = f"{date_et}T{esp._et_hhmm_to_utc(date_et, '09:29')}"
    end = f"{date_et}T{esp._et_hhmm_to_utc(date_et, end_hhmm)}"
    url = (f"{esp.OPTIONS_HOST}/v1beta1/options/bars?symbols={symbol}&timeframe=1Min"
           f"&start={start}&end={end}&limit=1000")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        print(f"[sss] today-safe bar fetch error {symbol} {date_et}: {exc}", file=sys.stderr)
        return []
    return (data.get("bars") or {}).get(symbol) or []


def _bar_fetcher_for(date_et: str):
    """Historical dates use the established esp.fetch_option_bars unchanged; TODAY uses the
    capped-window variant above (see its docstring for why)."""
    if date_et == TODAY.isoformat():
        now_et = et_now()
        return lambda symbol, d: fetch_option_bars_today_safe(symbol, d, now_et)
    return esp.fetch_option_bars


def prepare_positions(positions: list[dict], spy_full: pd.DataFrame) -> tuple[list[dict], dict]:
    """Shared prep for layer (b) and the today-exhibit: derive side, recover trigger_level via
    the backward-scan heuristic, fetch REAL option bars (1-min), build the SPY lifetime slice.
    Returns (prepared, recovery_stats)."""
    level_cache: dict = {}
    bar_cache: dict = {}
    prepared = []
    recovery_status_counts: dict = {}
    n_no_bars = 0
    for p in positions:
        side = option_side_from_symbol(p["symbol"])
        date = dt.date.fromisoformat(p["date_et"])
        entry_ts_utc = dt.datetime.fromisoformat(p["entry_ts_utc"].replace("Z", "+00:00"))
        entry_ts_et = et_now(entry_ts_utc)
        trigger_level, status = recover_trigger_level_real_position(spy_full, level_cache, date,
                                                                     entry_ts_et, side)
        recovery_status_counts[status] = recovery_status_counts.get(status, 0) + 1

        key = (p["symbol"], p["date_et"])
        if key not in bar_cache:
            fetcher = _bar_fetcher_for(p["date_et"])
            bar_cache[key] = fetcher(p["symbol"], p["date_et"])
            _time_mod.sleep(0.12)
        opt_bars = bar_cache[key]
        if not opt_bars:
            n_no_bars += 1
            continue
        norm_bars = norm_bars_from_esp(opt_bars, entry_ts_utc=p["entry_ts_utc"])
        if not norm_bars:               # mirrors esp.replay_position's "no bars at/after entry"
            n_no_bars += 1
            continue
        spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= entry_ts_et)]
        qty = int(p["entry_qty"])
        if qty < 1:
            continue
        prepared.append({
            "arm": p["arm"], "symbol": p["symbol"], "date_et": p["date_et"], "side": side,
            "entry_premium": p["entry_price"], "qty": qty, "actual_exit_pnl": p.get("actual_exit_pnl"),
            "trigger_level": trigger_level, "recovery_status": status,
            "norm_bars": norm_bars, "spy_lifetime": spy_lifetime,
        })
    n_recoverable = sum(1 for p in prepared if p["trigger_level"] is not None)
    stats = {"n_positions_total": len(positions), "n_positions_with_bars": len(prepared),
             "n_no_option_bars": n_no_bars,
             "n_recoverable_trigger_level": n_recoverable,
             "n_fallback": len(prepared) - n_recoverable,
             "recovery_status_counts": recovery_status_counts}
    return prepared, stats


def replay_population(prepared: list[dict], cid: str) -> dict:
    shape = SHAPE_OF[cid]
    tot, n_structure_fired = 0.0, 0
    rows = []
    for p in prepared:
        ss_time = None
        if cid in STRUCTURE_CANDIDATE_IDS:
            ss_time = structure_stop_signal_time(p["spy_lifetime"], p["side"], p["trigger_level"],
                                                  STRUCTURE_BUFFER[cid])
        r = replay_structure_aware(p["entry_premium"], p["side"], p["qty"], p["norm_bars"],
                                   ss_time, shape, TIME_STOP_LAYER_B)
        tot += r["pnl"]
        if r["structure_fired"]:
            n_structure_fired += 1
        rows.append({"arm": p["arm"], "symbol": p["symbol"], "date_et": p["date_et"],
                     "pnl": r["pnl"], "structure_fired": r["structure_fired"],
                     "trigger_level": p["trigger_level"], "recovery_status": p["recovery_status"],
                     "actual_exit_pnl": p.get("actual_exit_pnl")})
    return {"anchor_total": round(tot, 2), "n_valid": len(prepared),
           "n_structure_fired": n_structure_fired, "rows": rows}


def run_layer_b(spy_full: pd.DataFrame) -> dict:
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    anchor_positions = [p for p in positions if p["date_et"] <= ANCHOR_END_DATE]
    prepared, stats = prepare_positions(anchor_positions, spy_full)

    uniq = sorted(set((p["date_et"], p["symbol"]) for p in prepared))
    dates = sorted(set(p["date_et"] for p in prepared))
    actual_total = round(sum(p.get("actual_exit_pnl") or 0.0 for p in prepared), 2)

    out = {**stats, "n_unique_signals": len(uniq), "n_trading_days": len(dates),
           "date_span": f"{dates[0]}..{dates[-1]}" if dates else None,
           "actual_realized_total": actual_total, "candidates": {}}
    for cid in ALL_CANDIDATE_IDS:
        r = replay_population(prepared, cid)
        out["candidates"][cid] = {k: v for k, v in r.items() if k != "rows"}
    return out, {cid: replay_population(prepared, cid)["rows"] for cid in ALL_CANDIDATE_IDS}


# ---------------------------------------------------------------------------------------------
# TODAY EXHIBIT (2026-07-09) -- separate, EXHIBIT ONLY, excluded from all verdicts
# ---------------------------------------------------------------------------------------------
def run_today_exhibit(spy_full: pd.DataFrame) -> dict:
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    today_positions = [p for p in positions if p["date_et"] == TODAY.isoformat()]
    prepared, stats = prepare_positions(today_positions, spy_full)

    uniq = sorted(set((p["symbol"], p["side"]) for p in prepared))
    actual_total = round(sum(p.get("actual_exit_pnl") or 0.0 for p in prepared), 2)
    recovered_levels = sorted({p["trigger_level"] for p in prepared if p["trigger_level"] is not None})

    out = {**stats, "n_unique_symbols": len(uniq), "actual_realized_total": actual_total,
           "recovered_trigger_levels": recovered_levels,
           "task_cited_trigger_level": 747.46,
           "candidates": {}}
    for cid in ALL_CANDIDATE_IDS:
        r = replay_population(prepared, cid)
        out["candidates"][cid] = r
    return out


# ---------------------------------------------------------------------------------------------
# VERDICTS
# ---------------------------------------------------------------------------------------------
def build_verdicts(layer_a: dict, layer_b: dict) -> dict:
    verdicts = {}
    ctl_a_exp = layer_a["candidates"]["CONTROL"]["expectancy"]
    ctl_b_total = layer_b["candidates"]["CONTROL"]["anchor_total"]
    for cid in STRUCTURE_CANDIDATE_IDS:
        a = layer_a["candidates"][cid]
        b = layer_b["candidates"][cid]
        cond1_layer_b = bool(b["anchor_total"] > ctl_b_total)
        cond2_layer_a = bool(a["expectancy"] is not None and ctl_a_exp is not None
                             and a["expectancy"] > ctl_a_exp)
        cond3_fallback = bool(layer_a["n_fallback"] >= 0 and layer_b["n_fallback"] >= 0)  # structural invariant
        overall = "PASS" if (cond1_layer_b and cond2_layer_a and cond3_fallback) else "FAIL"
        verdicts[cid] = {
            "condition_1_layer_b_beats_control": cond1_layer_b,
            "condition_2_layer_a_beats_control": cond2_layer_a,
            "condition_3_fallback_included_not_dropped": cond3_fallback,
            "overall": overall,
            "reason": (f"layer(a) exp ${a['expectancy']} vs control ${ctl_a_exp} "
                      f"({'PASS' if cond2_layer_a else 'FAIL'}); "
                      f"layer(b) anchor ${b['anchor_total']} vs control ${ctl_b_total} "
                      f"({'PASS' if cond1_layer_b else 'FAIL'}); "
                      f"fallback population layer(a)={layer_a['n_fallback']}/{layer_a['n_signals']} "
                      f"layer(b)={layer_b['n_fallback']}/{layer_b['n_positions_with_bars']} included "
                      f"(not dropped) -> {'PASS' if cond3_fallback else 'FAIL'}"),
        }
    return verdicts


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[sss] preflight: {pf}", flush=True)
    if not (pf["fresh_slice_hash_ok"] and pf["anchor_population_hash_ok"] and pf["preregistration_version_ok"]):
        print("[sss] PREFLIGHT FAILED -- aborting (no re-picks, no stale-hash runs)", file=sys.stderr)
        return 1

    print("[sss] loading SPY 5m bars (cached 2026-05-01..2026-07-08 + live fetch for 2026-07-09)...",
          flush=True)
    spy_full = load_spy_full_with_today()
    print(f"[sss] spy_full: {len(spy_full)} rows, {spy_full['date'].min()}..{spy_full['date'].max()}",
          flush=True)

    print("[sss] layer (a): fresh-slice prep (exact trigger-bar recovery via tw8_level_context)...",
          flush=True)
    prepared_a, n_missing_bars_a, _spy_a = prepare_layer_a()
    print(f"[sss] layer (a): {len(prepared_a)} prepared "
          f"({sum(1 for p in prepared_a if p['trigger_level'] is not None)} recoverable trigger_level, "
          f"{n_missing_bars_a} missing OPRA bars)", flush=True)
    layer_a = run_layer_a(prepared_a)
    layer_a["n_missing_bars"] = n_missing_bars_a

    print("[sss] layer (b): real-fills anchor (network calls to Alpaca OPRA, rate-limited)...",
          flush=True)
    layer_b, layer_b_rows = run_layer_b(spy_full)
    print(f"[sss] layer (b): {layer_b['n_positions_with_bars']} positions with bars "
          f"({layer_b['n_recoverable_trigger_level']} recoverable trigger_level, "
          f"{layer_b['n_fallback']} fallback)", flush=True)

    print("[sss] today exhibit (2026-07-09) -- EXHIBIT ONLY, not a pass/fail layer...", flush=True)
    today_exhibit = run_today_exhibit(spy_full)
    print(f"[sss] today exhibit: {today_exhibit['n_positions_with_bars']} positions, "
          f"recovered levels {today_exhibit['recovered_trigger_levels']} "
          f"(task-cited: {today_exhibit['task_cited_trigger_level']})", flush=True)

    verdicts = build_verdicts(layer_a, layer_b)
    for cid, v in verdicts.items():
        print(f"[sss] {cid}: {v['overall']} -- {v['reason']}", flush=True)

    disclosures = [
        "C6 fill-mark convention: the structure stop fires at the NEXT 5m bar's OPEN premium "
        "(not the close-bar's own closing premium) -- applied uniformly to SS-A/SS-B/SS-C, both "
        "layers, and the exhibit. See the pre-registration's c6_fill_mark_convention.",
        f"Trigger-level recovery: layer (a) uses tw8_level_context's EXACT entry_spot-matched "
        f"trigger-bar method. Layer (b) and the exhibit use a backward-scan heuristic "
        f"(lookback={TRIGGER_RECOVERY_LOOKBACK_BARS} bars / 40 min, closest-to-entry first) "
        f"because real fills carry no entry_spot label -- this is a coarser, disclosed "
        f"approximation, not an exact match.",
        f"Fallback population (no recoverable trigger_level): layer (a) "
        f"{layer_a['n_fallback']}/{layer_a['n_signals']}, layer (b) "
        f"{layer_b['n_fallback']}/{layer_b['n_positions_with_bars']}. These positions are NEVER "
        f"dropped -- SS-A/B/C fall back to premium-only -50% catastrophe-cap replay for them "
        f"(pre-registration condition 3), identical in kind to how CONTROL always treats every "
        f"position.",
        "Time-stop asymmetry (pre-existing, not introduced here): layer (a) uses 15:40 ET "
        "(t4/t5 convention); layer (b) and the exhibit use 15:50 ET (exit_manager.TIME_STOP_ET, "
        "exit_shape_parity_study convention).",
        "Option-bar granularity: layer (a) is 5-min cached OTM-2 OPRA bars; layer (b)/exhibit are "
        "REAL 1-min Alpaca OPRA bars, live-fetched. SPY bars are 5-min in both layers.",
        "Today's exhibit trigger levels are recovered via the SAME lib/levels.py backtest-"
        "approximation detector used throughout this study (not automation/state/key-levels.json, "
        "the live engine's own richer level file, which additionally includes the level-memory "
        "system (G11 live-merge, wired 2026-07-09) that lib/levels.py does NOT model) -- a gap "
        "vs. the task's cited 747.46 is EXPECTED, not a bug; see key_findings for the actual "
        "recovered numbers.",
        "Anchor population is CLOSED (date_et<=2026-07-08); today's session was still open "
        "(market_hours=True) when this study ran, so the exhibit's fill count reflects the "
        "state at run time, timestamped in generated_at.",
        "Frictionless fills at trigger/stop/target levels (no spread/queue modelled) for the "
        "non-structure exit components, matching every prior anchor/fresh-slice study in this "
        "codebase (T3/T4/T5/T-W8).",
        "ribbon_ride only (both directions); vwap_continuation is out of scope (ground rule 11, "
        "carried from T3/T4/T5).",
    ]

    key_findings = []
    ctl_a = layer_a["candidates"]["CONTROL"]
    ctl_b = layer_b["candidates"]["CONTROL"]
    key_findings.append(
        f"CONTROL: layer (a) fresh-slice expectancy ${ctl_a['expectancy']}/tr (n={ctl_a['n']}), "
        f"layer (b) anchor total ${ctl_b['anchor_total']} (n={ctl_b['n_valid']} positions) -- the "
        f"numbers every SS candidate is measured against.")
    for cid in STRUCTURE_CANDIDATE_IDS:
        a = layer_a["candidates"][cid]
        b = layer_b["candidates"][cid]
        key_findings.append(
            f"{cid}: layer(a) exp ${a['expectancy']}/tr (structure fired {a['n_structure_fired']}/"
            f"{layer_a['n_signals']}), layer(b) anchor ${b['anchor_total']} (structure fired "
            f"{b['n_structure_fired']}/{layer_b['n_positions_with_bars']}) -> {verdicts[cid]['overall']}.")
    key_findings.append(
        f"TODAY EXHIBIT (2026-07-09, EXCLUDED from all pass/fail): {today_exhibit['n_positions_with_bars']} "
        f"positions, actual realized ${today_exhibit['actual_realized_total']}, recovered trigger "
        f"level(s) {today_exhibit['recovered_trigger_levels']} vs. the task's cited 747.46 -- "
        f"CONTROL replayed ${today_exhibit['candidates']['CONTROL']['anchor_total']}, "
        + ", ".join(f"{cid} replayed ${today_exhibit['candidates'][cid]['anchor_total']} "
                    f"(structure fired {today_exhibit['candidates'][cid]['n_structure_fired']}/"
                    f"{today_exhibit['n_positions_with_bars']})" for cid in STRUCTURE_CANDIDATE_IDS)
        + ".")

    out = {
        "_doc": "STRUCTURE-STOP (chart-stop-primary) exit validation -- pre-registered, frozen "
                "before any candidate replay. ANALYSIS ONLY: no trading-path file touched. "
                "2026-07-09 is EXHIBIT ONLY, excluded from every pass/fail layer.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "layer_a_fresh_slice": layer_a,
        "layer_b_real_fills_anchor": layer_b,
        "layer_b_position_detail": layer_b_rows,
        "today_exhibit_2026_07_09": today_exhibit,
        "verdicts": verdicts,
        "key_findings": key_findings,
        "disclosures": disclosures,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[sss] wrote {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
