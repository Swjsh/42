"""futures_edge3_sim.py -- own-book SIM lane for EDGE #3 (MES leads -> MNQ laggard divergence
catch-up), driving the FROZEN_CONFIG detector against REAL live MES/MNQ quotes with a SIM fill
ledger. No broker, no credentials, no real orders anywhere.

WHY THIS EXISTS (PM decision, 2026-07-18): edge3_mesmnq_div.py's FROZEN_CONFIG has been
dormant since 2026-06-21 behind `enabled=False` + a Trading Technologies (TT) sandbox
credential that was NEVER wired (`docs/futures/`, referenced by accounts.json's
mes-mnq-div-futures arm, does not exist on disk -- verified 2026-07-18). The validated cell
(OOS +$71.46/tr, n=118, 8/8 gates, analysis/recommendations/b5-mesmnq-div-rescue.json) has sat
idle for 4 weeks waiting on an external account that was never provisioned.

ALPACA-FUTURES CHECKED HONESTLY (2026-07-18, live keys, evidence not assumption):
  - `mcp__alpaca__get_all_assets(asset_class="us_future")` on the real Safe-2 paper account
    (PA3DHPT7KIQE) returned `{"result": []}` -- zero assets, no error. The SAME call with
    `asset_class="crypto"` returned 80+ real tradable pairs the same session, proving the
    endpoint/auth path itself works and the empty futures result is a real "nothing here",
    not a broken query or a bad filter string.
  - Alpaca's documented AssetClass enum is {us_equity, us_option, crypto} only (docs.alpaca.
    markets/us/docs/working-with-assets + alpaca-py SDK enums). "us_future" is not a real
    Alpaca asset class as of this date; Alpaca's own community forum has open "futures
    planned?" threads with no ship date. CME's July-27 single-stock-futures launch is a CME
    product, unrelated to Alpaca support.
  - VERDICT: NO. Alpaca does not support futures, paper or live, on any account we hold. No
    "flip an existing paper account into futures mode" path exists. Upgrade path if this ever
    changes: re-run the asset_class probe above; a non-empty result is the trigger to migrate
    this SIM lane onto real Alpaca paper orders.

THE PRAGMATIC PATH (this file): the same pattern already proven live for the crypto twin's
bear-SIM lane (TWIN-B1.5, 2026-07-14) and this repo's OTHER futures shadow lane
(futures_mirror_shadow.py, live since 2026-07-09) -- a HIGH-FIDELITY OWN-BOOK SIM: real-time
quotes, the REAL frozen detector code, a real (simulated) fill ledger, every row clearly
labeled sim-fills-vs-real-quotes. This is mechanism-validation forward evidence, not a claim
of real fills.

NO DRIFT: this module does NOT re-implement the divergence detector, the persistence filter,
the ATR/chart-stop math, or the gate definitions. It imports `edge3_mesmnq_div.py`'s
FROZEN_CONFIG + `signal_for_tick` (which itself imports b4/b5 byte-identical -- see that
file's own docstring) and reuses `edge3.b4`'s own ATR_STOP_MULT / TRAIL_MULT / ATR_LEN /
RTH_OPEN / RTH_CLOSE / ENTRY_CUTOFF / WARMUP_BARS / TICK / SLIP_TICKS constants directly --
zero knobs re-typed here. The FROZEN CONFIG stays FROZEN: this script never tunes threshold,
min_persistence_bars, or exit_mode. The ONLY local override is `enabled=True` on a COPY of
FROZEN_CONFIG (`dataclasses.replace` -- the on-disk file is never touched, never imported
with side effects beyond its own module-load). edge3_mesmnq_div.py's own docstring names this
the sanctioned SIM-caller path verbatim: "Flipping cfg.enabled to True is the only thing that
lets a CALLER act on ENTER, and even then the caller (not this module) places the order." We
are that caller; we place a SIM order, never a real one.

SESSION SCOPE -- RTH ONLY, NOT globex ~23h (an explicit, EVIDENCED correction, not tuning):
  the frozen edge is defined entirely in terms of RTH 5-minute bars (`edge3.b4.RTH_OPEN` =
  09:30 ET, `RTH_CLOSE` = 16:00 ET, `WARMUP_BARS` = 3, `ENTRY_CUTOFF` = 13:00 ET -- session
  VWAP anchored at the RTH session open, `b4.load_futures` itself filters every backtest bar
  to `RTH_OPEN <= t < RTH_CLOSE` before the detector ever sees it). Polling the overnight
  Globex session would never produce a different decision (the detector ignores non-RTH bars
  by construction) and would just burn cycles/quote fetches for nothing -- so this script
  no-ops outside the RTH window (including weekends, holidays, and the Globex overnight
  session) BY DESIGN. This is a disclosed SCOPE decision about WHEN to poll, not an edit to
  any frozen knob.

FILL CONVENTION (REUSE DECISION, matches futures_mirror_shadow.py's own documented pattern):
  entry price = the live quote observed AT THE POLL the signal first fires, +/- 1 tick slip
  (same slip direction/size as `edge3.b4.simulate`'s own entry convention -- worse for us).
  A true next-bar-open fill is not observable in a discrete 5-min live poll; this is the same
  disclosed limitation futures_mirror_shadow.py already carries. Stop-leg fills use
  `futures.fill_sim_broker.gap_aware_stop_fill` (imported, not reimplemented) -- WORSE than
  the stop on a gap, AT the stop on a normal touch -- deliberately MORE conservative than the
  backtest's uniform `stop +/- 1 tick` convention, because a 5-min discrete poll can miss an
  intra-bar touch-and-reverse a continuous backtest walk would catch precisely. The stop LEVEL
  itself (ATR-vs-chart-stop max/min at entry, the ATR chandelier trail every poll) is
  byte-identical to `edge3.b4.simulate`'s own `atr_trail` branch -- only the FILL PRICE
  convention on the stop leg is more conservative, and only because live polling genuinely is
  coarser than a bar-by-bar backtest walk. EOD-flat fills use the backtest's own close +/-
  slip convention (not gap-aware -- it is not a stop touch). Ratchet/touch-check on a given
  position starts the POLL AFTER it opens (never same-poll as the fill) -- simpler code, and
  strictly more conservative than the backtest's own same-bar-can-stop-out convention.

QUOTE SOURCE + QUALITY (disclosed honestly, verified live 2026-07-18 ~10:5x ET Saturday --
  see the CLOCK NOTE below): yfinance 5-minute bars, `ES=F` (MES proxy) / `NQ=F` (MNQ proxy)
  -- the SAME symbol mapping already used by `swing_core_runner.py` (micros track their
  E-mini 1:1 in index points; only the $/point conversion differs, `futures/instruments.py`).
  Verified live this session: both symbols returned real OHLCV with non-zero volume on 5m
  bars, continuous coverage into the extended session. This is a FREE, delayed retail feed
  (not exchange-direct) -- the same quote-quality caveat futures_mirror_shadow.py already
  discloses for its own ES=F proxy feed. The falsification rail below exists specifically to
  catch a real quote-quality gap before trusting this lane's numbers.

CLOCK NOTE: the task that produced this file described "Friday night"; `et_clock.et_now()`
  read live this session as **2026-07-18 Saturday ~10:48 ET**, not Friday night. Per
  CLAUDE.md's real-time discipline, the real clock wins -- this script (and its scheduled-
  task registration) are built around the REAL calendar: next RTH session = Monday
  2026-07-20. See the build session's report for the actual verification tick output.

FALSIFICATION RAIL (task requirement): once >=20 CLOSED sim round-trips exist, compare mean
  pnl_usd_mnq to `FROZEN_CONFIG.validated_oos_per_trade` ($71.46). A material shortfall (mean
  < 50% of validated) sets `progress["falsification"] = "INVESTIGATE_QUOTE_QUALITY"` in
  `edge3-sim-progress.json` -- sim-fill/quote-quality is the FIRST suspect on a shortfall, not
  the frozen signal itself (C3-adjacent: this codebase's standing lesson is that sim-vs-live
  fill divergence is usually a fill-fidelity problem, not a dead edge).

LEDGER (own files under automation/state/futures/, distinct names from every other futures
  lane on disk -- mirror-shadow's mirror-*, the real dormant swing engine's
  position.json/decisions.jsonl, FillSimBroker's fillsim-*.json -- no collision):
    edge3-sim-state.json      last-tick watermark + consumed-sessions (1 signal/session cap)
    edge3-sim-position.json   the one open position (structurally <=1 at a time -- the frozen
                               signal is 1/(laggard,session) by construction)
    edge3-sim-fills.jsonl     every lifecycle row (placed/filled/stopped/eod_flat), each row
                               carrying `"fidelity": "sim_fill_vs_real_quote"` explicitly
    edge3-sim-progress.json   round-trip count / mean pnl / falsification verdict

RUNNER MODE: `python futures_edge3_sim.py --once` -- one poll pass (the only mode). Fail-open:
  main() always returns 0, every exception logged to
  automation/state/logs/futures-edge3-sim-YYYY-MM-DD.log, never raised. Runs under the
  backtest venv (pandas + yfinance) -- automatically reaper-exempt (`_shared.ps1`
  EXEMPT_DAEMONS already covers the whole `backtest\\.venv` interpreter substring), and exits
  in seconds regardless, well under the 5-min staleness threshold.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, popup-storm fix) ===============
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting can
# allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout write.
# Redirect stdio to log files BEFORE any other import gets a chance to write. Copied verbatim
# pattern from futures_mirror_shadow.py / swing_core_runner.py's siblings.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "futures-edge3-sim.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "futures-edge3-sim.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import dataclasses
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts", "automation/state/fleet"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)


def _et_now() -> dt.datetime:
    """ET wall-clock via the repo's DST-aware clock. Lazily re-imports et_clock on every call
    (matches futures_mirror_shadow.py / fill_sim_broker.py exactly) so monkeypatches of
    `et_clock.et_now` are honored by tests. NEVER a naive local-clock read (CLAUDE.md TZ
    scar -- this box runs Mountain time, ET = local + 2h)."""
    import et_clock  # noqa: PLC0415
    return et_clock.et_now()


# ── paths / constants ──────────────────────────────────────────────────────────
STATE_DIR = REPO / "automation" / "state" / "futures"
LOG_DIR = REPO / "automation" / "state" / "logs"
CALENDAR_FILE = REPO / "automation" / "state" / "calendar.json"

STATE_FILE = STATE_DIR / "edge3-sim-state.json"
POSITION_FILE = STATE_DIR / "edge3-sim-position.json"
LEDGER_FILE = STATE_DIR / "edge3-sim-fills.jsonl"
PROGRESS_FILE = STATE_DIR / "edge3-sim-progress.json"

YF_SYMBOL = {"MES": "ES=F", "MNQ": "NQ=F"}   # same mapping as swing_core_runner.YF_SYMBOL

FIDELITY = "sim_fill_vs_real_quote"

EV_PLACED = "placed"
EV_FILLED = "filled"
EV_STOPPED = "stopped"
EV_EOD_FLAT = "eod_flat"
_CLOSING_EVENTS = (EV_STOPPED, EV_EOD_FLAT)

FALSIFICATION_FLOOR = 20          # task requirement: first 20 sim round-trips
FALSIFICATION_FRACTION = 0.50     # mean pnl < 50% of validated -> flag for investigation
CONSUMED_SESSIONS_RETENTION = 30  # OP-22 retention cap (trading days)

STATE_DOC = (
    "Poll watermark for futures_edge3_sim.py (EDGE #3 own-book SIM lane, MES->MNQ divergence "
    "catch-up, TT-credential dependency retired -- see edge3_mesmnq_div.py FROZEN_CONFIG). "
    "consumed_sessions = ISO dates already given ONE entry attempt this session (the frozen "
    "signal is structurally 1/(laggard,session) -- this guards against re-consuming the same "
    "day's signal_for_tick() call as a second entry after the first position closes same "
    "day), pruned to the most recent "
    f"{CONSUMED_SESSIONS_RETENTION} entries. last_action/last_reason record the most recent "
    "poll's outcome for OP-33c glanceability without opening the ledger."
)
POSITION_DOC = (
    "The one open EDGE #3 SIM position (status='flat' when none). Structurally <=1 at a time "
    "-- the frozen signal fires at most once per (MNQ, session). fidelity='sim_fill_vs_real_"
    "quote' always -- no real order was ever placed for any row this file has ever held."
)
LEDGER_DOC = (
    "Every EDGE #3 SIM lifecycle event (placed/filled/stopped/eod_flat), oldest first. Every "
    "row carries fidelity='sim_fill_vs_real_quote' -- simulated fills against REAL yfinance "
    "ES=F/NQ=F quotes, never a real broker order (Alpaca does not support futures as of "
    "2026-07-18 -- see this module's docstring ALPACA-FUTURES CHECKED HONESTLY). Falsification "
    f"rail: once >={FALSIFICATION_FLOOR} stopped/eod_flat rows share a signal_ref count as "
    "closed round trips, edge3-sim-progress.json compares mean pnl_usd_mnq to FROZEN_CONFIG."
    "validated_oos_per_trade ($71.46) -- see PROGRESS_DOC there."
)
PROGRESS_DOC = (
    f"Falsification-rail tracker for the EDGE #3 SIM lane. n_closed_round_trips < "
    f"{FALSIFICATION_FLOOR} -> falsification='PENDING_MORE_DATA' (no verdict yet, by design). "
    f">= {FALSIFICATION_FLOOR}: mean_pnl_usd_mnq < {FALSIFICATION_FRACTION} x "
    "validated_oos_per_trade -> falsification='INVESTIGATE_QUOTE_QUALITY' (sim-fill/quote "
    "fidelity is the first suspect on a shortfall, not the frozen signal -- C3-adjacent "
    "standing lesson in this codebase); otherwise 'TRACKING_VALIDATED'."
)


# ── fail-open IO helpers (pattern matched to every other futures_* script in this repo;
#    each script owns its own copies by established convention -- see futures_mirror_shadow.py
#    module docstring REUSE DECISION) ──
def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = _et_now().strftime("%Y-%m-%d")
        ts = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(LOG_DIR / f"futures-edge3-sim-{day}.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(default))


def _load_holidays() -> set:
    try:
        doc = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
        return set(doc.get("holidays", []))
    except Exception:  # noqa: BLE001
        return set()


# ── the frozen edge (imported, not reimplemented) ───────────────────────────────
def _load_edge3():
    """Lazy import so a monkeypatched sys.path (tests) is honored, and so an import failure
    surfaces as a clean errors[] entry rather than crashing module load."""
    import edge3_mesmnq_div as edge3  # noqa: PLC0415
    return edge3


# ── session gating (RTH only -- see module docstring SESSION SCOPE) ─────────────
def is_rth(now_et: dt.datetime, b4mod, holidays: set) -> bool:
    """PURE. Weekday + not-a-holiday + inside [RTH_OPEN, RTH_CLOSE) -- the exact window the
    frozen edge's own backtest data is filtered to (b4.load_futures)."""
    if now_et.weekday() >= 5:
        return False
    if now_et.strftime("%Y-%m-%d") in holidays:
        return False
    t = now_et.time()
    return b4mod.RTH_OPEN <= t < b4mod.RTH_CLOSE


# ── live quote fetch -> b4-shaped dataframe (yfinance; shape matches b4.load_futures) ──
def fetch_intraday_df(symbol_yf: str, b4mod):
    """Best-effort 5m RTH-filtered dataframe for `symbol_yf`, shaped exactly like
    `b4.load_futures`'s output (open/high/low/close/volume floats + date/t columns), so
    `edge3.signal_for_tick` sees the SAME contract it sees in the backtest. Fail-open -> None,
    never raises."""
    try:
        import pandas as pd  # noqa: PLC0415
        import yfinance as yf  # noqa: PLC0415

        raw = yf.download(symbol_yf, period="5d", interval="5m", auto_adjust=False,
                          progress=False, prepost=True)
        if raw is None or raw.empty:
            return None
        if hasattr(raw.columns, "nlevels") and raw.columns.nlevels > 1:
            raw.columns = raw.columns.get_level_values(0)
        idx = raw.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        idx_et = idx.tz_convert("America/New_York").tz_localize(None)
        df = pd.DataFrame({
            "open": raw["Open"].astype(float).to_numpy(),
            "high": raw["High"].astype(float).to_numpy(),
            "low": raw["Low"].astype(float).to_numpy(),
            "close": raw["Close"].astype(float).to_numpy(),
            "volume": raw["Volume"].astype(float).to_numpy(),
        })
        df["timestamp_et"] = idx_et
        df = df.drop_duplicates(subset="timestamp_et", keep="first").sort_values(
            "timestamp_et").reset_index(drop=True)
        df["date"] = df["timestamp_et"].dt.date
        df["t"] = df["timestamp_et"].dt.time
        # byte-identical RTH filter to b4.load_futures (same constants, no re-typing).
        df = df[(df["t"] >= b4mod.RTH_OPEN) & (df["t"] < b4mod.RTH_CLOSE)].reset_index(drop=True)
        if df.empty:
            return None
        return df
    except Exception:  # noqa: BLE001
        return None


# ── position math (byte-identical stop/trail levels to edge3.b4.simulate's atr_trail branch) ──
def open_position(decision, entry_quote: float, atr_at_signal: float, now_et: dt.datetime,
                  b4mod, cfg) -> dict:
    """PURE. `entry_quote` is this poll's live close; slip applied same direction/size as
    b4.simulate's own entry convention."""
    long = decision.side == "long"
    slip = b4mod.SLIP_TICKS * b4mod.TICK
    entry = entry_quote + slip if long else entry_quote - slip
    if long:
        atr_stop = entry - b4mod.ATR_STOP_MULT * atr_at_signal
        chart = min(decision.chart_stop, entry - b4mod.TICK)
        stop = max(atr_stop, chart)
    else:
        atr_stop = entry + b4mod.ATR_STOP_MULT * atr_at_signal
        chart = max(decision.chart_stop, entry + b4mod.TICK)
        stop = min(atr_stop, chart)
    return {
        "edge_id": cfg.edge_id, "arm_id": cfg.arm_id, "laggard": decision.laggard,
        "direction": decision.side, "status": "open", "qty": cfg.qty_micros,
        "entry": round(entry, 4), "stop": round(stop, 4),
        "atr_at_entry": round(float(atr_at_signal), 4),
        "hh": round(entry, 4), "ll": round(entry, 4),
        "entry_time_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_date": now_et.date().isoformat(),
        "closed_at_et": None, "persistence": decision.persistence, "fidelity": FIDELITY,
    }


def _close(position: dict, price: float, now_et: dt.datetime, event: str, reason: str,
          b4mod, *, gap_aware: bool) -> tuple[dict, dict]:
    from futures.instruments import MNQ  # noqa: PLC0415
    from futures.fill_sim_broker import gap_aware_stop_fill  # noqa: PLC0415

    direction = position["direction"]
    long = direction == "long"
    slip = b4mod.SLIP_TICKS * b4mod.TICK
    if gap_aware:
        fill = gap_aware_stop_fill(direction, position["stop"], price, None)
    else:
        fill = price - slip if long else price + slip
    qty = position["qty"]
    pts = (fill - position["entry"]) if long else (position["entry"] - fill)
    pnl = round(pts * MNQ.point_value * qty - MNQ.round_turn_usd * qty, 2)
    new_pos = {**position, "status": "closed", "qty": 0,
              "closed_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S")}
    row = {
        "ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "edge_id": position["edge_id"],
        "arm_id": position["arm_id"], "laggard": position["laggard"], "direction": direction,
        "entry": position["entry"], "stop": position["stop"], "event": event,
        "pnl_pts": round(pts, 4), "pnl_usd_mnq": pnl, "exit_qty": qty,
        "fill_price": round(fill, 4), "reason": reason, "fidelity": FIDELITY,
        "persistence": position.get("persistence"), "session_date": position.get("session_date"),
    }
    return row, new_pos


def manage_position(position: dict, price: float, bar_high: float, bar_low: float,
                    now_et: dt.datetime, b4mod) -> tuple[Optional[dict], dict]:
    """PURE (returns NEW dicts, never mutates). Ratchet-then-check every poll AFTER the entry
    poll (see module docstring FILL CONVENTION). Priority: 1) EOD/session-rollover flatten
    (unconditional) 2) chandelier/chart stop leg. No target leg -- FROZEN_CONFIG has no TP,
    matches b4's own 'let the laggard run to the leader' hypothesis."""
    if position.get("status") != "open":
        return None, position

    long = position["direction"] == "long"
    a = position["atr_at_entry"]
    new_hh = max(position["hh"], bar_high)
    new_ll = min(position["ll"], bar_low)
    stop = position["stop"]
    if long:
        stop = max(stop, new_hh - b4mod.TRAIL_MULT * a)
    else:
        stop = min(stop, new_ll + b4mod.TRAIL_MULT * a)
    working = {**position, "hh": new_hh, "ll": new_ll, "stop": stop}

    session_rolled = now_et.date().isoformat() != position.get("session_date")
    if session_rolled or now_et.time() >= b4mod.RTH_CLOSE:
        return _close(working, price, now_et, EV_EOD_FLAT, "rth_close_same_session", b4mod,
                     gap_aware=False)

    stop_hit = (bar_low <= stop) if long else (bar_high >= stop)
    if stop_hit:
        return _close(working, price, now_et, EV_STOPPED, "atr_trail_or_chart_stop_hit", b4mod,
                     gap_aware=True)

    if working != position:
        return None, working
    return None, position


def _placed_filled_rows(position: dict, decision, now_et: dt.datetime) -> tuple[dict, dict]:
    base = {
        "ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "edge_id": position["edge_id"],
        "arm_id": position["arm_id"], "laggard": position["laggard"],
        "direction": position["direction"], "entry": position["entry"],
        "stop": position["stop"], "fidelity": FIDELITY, "persistence": position.get("persistence"),
        "reason": decision.reason, "session_date": position.get("session_date"),
    }
    placed = {**base, "event": EV_PLACED, "pnl_pts": 0.0, "pnl_usd_mnq": 0.0, "exit_qty": 0,
             "fill_price": None}
    filled = {**base, "event": EV_FILLED, "pnl_pts": 0.0, "pnl_usd_mnq": 0.0,
             "exit_qty": position["qty"], "fill_price": position["entry"]}
    return placed, filled


# ── falsification-rail progress ─────────────────────────────────────────────────
def compute_progress(cfg, *, ledger_file: Path = LEDGER_FILE) -> dict:
    rows = []
    if ledger_file.exists():
        for raw in ledger_file.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "_doc" in r:
                continue
            rows.append(r)
    closed = [r for r in rows if r.get("event") in _CLOSING_EVENTS]
    n = len(closed)
    total_pnl = round(sum(float(r.get("pnl_usd_mnq", 0.0)) for r in closed), 2)
    mean_pnl = round(total_pnl / n, 2) if n else None
    validated = cfg.validated_oos_per_trade
    falsification = "PENDING_MORE_DATA"
    if n >= FALSIFICATION_FLOOR:
        if mean_pnl is not None and mean_pnl < FALSIFICATION_FRACTION * validated:
            falsification = "INVESTIGATE_QUOTE_QUALITY"
        else:
            falsification = "TRACKING_VALIDATED"
    return {
        "_doc": PROGRESS_DOC, "n_closed_round_trips": n, "total_pnl_usd_mnq": total_pnl,
        "mean_pnl_usd_mnq": mean_pnl, "validated_oos_per_trade": validated,
        "falsification_floor": FALSIFICATION_FLOOR, "falsification": falsification,
        "computed_at_et": _et_now().strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ── state load/save ──────────────────────────────────────────────────────────
def load_state() -> dict:
    return _load_json(STATE_FILE, {"consumed_sessions": [], "last_run_et": None,
                                    "last_action": None, "last_reason": None})


def load_position() -> dict:
    return _load_json(POSITION_FILE, {"status": "flat"})


def _save_position(position: dict) -> None:
    body = position if position.get("status") == "open" else {"status": "flat"}
    _atomic_write_json(POSITION_FILE, {"_doc": POSITION_DOC, **body})


def _save_state(state: dict) -> None:
    _atomic_write_json(STATE_FILE, {"_doc": STATE_DOC, **state})


# ── orchestration ────────────────────────────────────────────────────────────
def run_once(*, now_et: Optional[dt.datetime] = None, lead_fetcher=None, lag_fetcher=None) -> dict:
    """ONE poll pass. Never raises internally -- every step is try/except-guarded and any
    failure lands in the returned summary's `errors` list."""
    if now_et is None:
        now_et = _et_now()

    errors: list = []
    try:
        edge3 = _load_edge3()
    except Exception as e:  # noqa: BLE001
        _log(f"noop: edge3 import failed: {type(e).__name__}: {e}")
        return {"action": "noop", "reason": "edge3_import_failed", "errors": [str(e)]}
    b4mod = edge3.b4
    cfg = edge3.FROZEN_CONFIG

    state = load_state()
    position = load_position()
    holidays = _load_holidays()

    if not is_rth(now_et, b4mod, holidays):
        state = {**state, "last_run_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
                 "last_action": "noop", "last_reason": "market_closed_outside_rth"}
        _save_state(state)
        _log(f"noop: outside RTH (weekday={now_et.weekday()} t={now_et.time().isoformat()})")
        return {"action": "noop", "reason": "market_closed_outside_rth", "in_rth": False,
                "errors": errors, "position_open": position.get("status") == "open"}

    lead_fetcher = lead_fetcher or (lambda: fetch_intraday_df(YF_SYMBOL["MES"], b4mod))
    lag_fetcher = lag_fetcher or (lambda: fetch_intraday_df(YF_SYMBOL["MNQ"], b4mod))
    try:
        lead_df = lead_fetcher()
    except Exception as e:  # noqa: BLE001
        errors.append(f"lead_fetch_failed:{type(e).__name__}:{e}")
        lead_df = None
    try:
        lag_df = lag_fetcher()
    except Exception as e:  # noqa: BLE001
        errors.append(f"lag_fetch_failed:{type(e).__name__}:{e}")
        lag_df = None

    if lead_df is None or lag_df is None or lead_df.empty or lag_df.empty:
        state = {**state, "last_run_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
                 "last_action": "noop", "last_reason": "quote_fetch_failed"}
        _save_state(state)
        _log(f"noop: quote fetch failed (lead_ok={lead_df is not None} lag_ok={lag_df is not None})")
        return {"action": "noop", "reason": "quote_fetch_failed", "in_rth": True,
                "errors": errors, "position_open": position.get("status") == "open"}

    price = float(lag_df["close"].iloc[-1])
    bar_high = float(lag_df["high"].iloc[-1])
    bar_low = float(lag_df["low"].iloc[-1])
    today = now_et.date()
    events: list = []
    consumed = list(state.get("consumed_sessions", []))

    if position.get("status") == "open":
        row, new_position = manage_position(position, price, bar_high, bar_low, now_et, b4mod)
        position = new_position
        if row is not None:
            _append_jsonl(LEDGER_FILE, row)
            events.append(row["event"])
            sd = row.get("session_date")
            if sd and sd not in consumed:
                consumed.append(sd)
    elif now_et.time() <= b4mod.ENTRY_CUTOFF and today.isoformat() not in consumed:
        try:
            sim_cfg = dataclasses.replace(cfg, enabled=True)
            decision = edge3.signal_for_tick(lead_df, lag_df, as_of_date=today, cfg=sim_cfg)
        except Exception as e:  # noqa: BLE001
            errors.append(f"signal_for_tick_failed:{type(e).__name__}:{e}")
            decision = None
        if decision is not None and decision.action in ("ENTER_LONG", "ENTER_SHORT"):
            try:
                lag_atr = b4mod.atr_series(lag_df["high"], lag_df["low"], lag_df["close"],
                                          b4mod.ATR_LEN)
                a = (lag_atr[decision.entry_idx]
                    if decision.entry_idx is not None and decision.entry_idx < len(lag_atr)
                    else float("nan"))
            except Exception as e:  # noqa: BLE001
                errors.append(f"atr_compute_failed:{type(e).__name__}:{e}")
                a = float("nan")
            if a != a or a <= 0:  # NaN/invalid -- retry next poll, do NOT consume the session
                _log(f"signal fired but ATR invalid at idx={decision.entry_idx}; retry next poll")
            else:
                position = open_position(decision, price, float(a), now_et, b4mod, cfg)
                placed, filled = _placed_filled_rows(position, decision, now_et)
                _append_jsonl(LEDGER_FILE, placed)
                _append_jsonl(LEDGER_FILE, filled)
                events.extend([EV_PLACED, EV_FILLED])
                consumed.append(today.isoformat())

    consumed = sorted(set(consumed))[-CONSUMED_SESSIONS_RETENTION:]
    _save_position(position)
    state = {**state, "consumed_sessions": consumed,
             "last_run_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
             "last_action": "tick", "last_reason": ",".join(events) if events else "hold"}
    _save_state(state)

    try:
        progress = compute_progress(cfg)
        _atomic_write_json(PROGRESS_FILE, progress)
    except Exception as e:  # noqa: BLE001
        errors.append(f"progress_failed:{type(e).__name__}:{e}")

    return {"action": "tick", "in_rth": True, "events": events,
            "position_open": position.get("status") == "open", "errors": errors}


def main() -> int:
    """CLI entry point. ALWAYS returns 0 (fail-open) -- every exception is caught + logged,
    never re-raised (task requirement: a scheduled fire must never break the chain)."""
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--once", action="store_true",
                        help="run exactly one poll pass (the only mode this script has)")
        ap.parse_args()
        summary = run_once()
        _log(f"pass complete: {json.dumps(summary, default=str)[:2000]}")
        return 0
    except Exception as e:  # noqa: BLE001 -- fail-open is the task's explicit requirement
        try:
            _log(f"main() FAILED (fail-open, exit 0 anyway): {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}")
        except Exception:  # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
