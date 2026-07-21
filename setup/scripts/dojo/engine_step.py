"""dojo/engine_step.py — "what does the engine see at this bar" (Agent A).

Spec: markdown/specs/DOJO-ARCHITECTURE-DECISION.md ("engine_step.py (Agent A)") +
markdown/specs/DOJO-REPLAY-TRAINING-SPEC.md. Called by dojo/session.py::cmd_step via `from dojo
import engine_step` (empirically verified 2026-07-20: a bare `import engine_step` ALSO resolves
correctly when session.py is driven via `python -m dojo.session ...` — the package-qualified
import is simply the more explicit, unambiguous spelling). This module works either way: its own
sys.path bootstrap below makes it independently importable as `dojo.engine_step`, standalone, or
under pytest, regardless of how the caller reached it.

THE WHOLE POINT (architecture doc, verbatim): reuse the REAL live decision path so we train the
code that trades, not a re-implementation. Concretely, per bar this module:
  1. builds the exact payload heartbeat_core._build_payload builds live (setup/scripts/
     heartbeat_core.py:544), with historical VIX/levels/VIX-MA/VIX-intraday INJECTED (the same
     injection seam replay_heartbeat_core.py — this repo's only other _build_payload historical
     harness — uses) instead of heartbeat_core's own live yfinance/REST fetches;
  2. calls heartbeat_core._engine_verdict(payload) — the EXACT function
     heartbeat_core.run_account() calls on the payload (setup/scripts/heartbeat_core.py:932) —
     which shells out to `python -m backtest.lib.engine.engine_cli` (score_bar + the 15 gates).
No scoring/gating logic is re-implemented anywhere in this file.

HISTORICAL VIX/LEVELS — DISCLOSED APPROXIMATION (read before trusting a score to the cent):
  - VIX (vix_now/vix_prior/vix_5d_ma/vix_20d_ma/vix_intraday): sourced from the REAL cached
    backtest/data/vix_5m_*.csv (the same OPRA/yfinance-fed cache the backtest uses), aligned to
    the trigger bar via lib.orchestrator._align_vix_to_spy (reused, not reimplemented — the same
    utility replay_heartbeat_core.py uses). This is a faithful historical read, not an
    approximation, PROVIDED a cache file covering replay_day exists.
  - Levels (levels_active/multi_day_levels): heartbeat_core._read_levels reads the LIVE,
    CURRENT automation/state/key-levels.json. No historical key-levels.json snapshot is
    retained anywhere in this repo, so there is no literal "levels as they stood on
    replay_day" source. _load_levels_as_of() reconstructs a best-available approximation from
    the CURRENT key-levels.json: it keeps entries whose `verified_at` date is <= replay_day
    (no look-ahead — a level not yet drawn as of replay_day is excluded) and whose
    `expires_at` had not yet passed AS OF replay_day (mirrors heartbeat_core._level_expired,
    parameterized on replay_day instead of the real live clock), pooling BOTH `levels` and
    `deprecated_levels` (empirically verified 2026-07-20: the live pipeline leaves
    already-expired entries sitting in `levels` rather than deleting them, so this is not a
    strict no-op for old days, but it is still only an approximation of the live level state —
    Gamma_Premarket's daily redraw is not reconstructable from a single current snapshot).
    CONSEQUENCE: score components that don't route through a level-tied trigger
    (level_rejection/level_reclaim, and confluence/sequence built on top of one) are exact;
    components that DO depend on levels_active proximity may diverge from what live actually
    saw. This is disclosed, not silently assumed — see test_dojo_engine_step.py for the
    measured match rate on 2026-07-17.

FLEET ARMS (safe-3, risky-1, risky-3): NOT wired this pass. fleet_executor.plan_all() needs a
"shared signal" dict that automation/state/fleet/build_shared_signal.py only knows how to build
by reading TODAY's automation/state/core-decisions.jsonl + automation/state/sight-beacon.json
off disk (both live-only, not date-parameterized) — wiring it to a historical bar would mean
forking/rewriting a shared production module, out of scope for a dojo-only Phase-1 pass and a
blast-radius risk for zero validated benefit yet. Per the task's own honesty-over-completeness
clause: each fleet arm gets exactly one DojoDecision with verdict="FLEET_VIEW_PENDING" and every
score/trigger field left None (never fabricated).

NO BROKER: this module imports nothing from any alpaca/broker/live-order path (guard-tested in
backtest/tests/test_dojo_fence.py alongside the rest of the dojo package).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

# --- path setup (mirror dojo/session.py + futures_edge3_sim.py): make sibling engine modules
# importable regardless of how THIS module itself was reached (bare `import engine_step` from
# session.py already relies on session.py having done this; repeating it here defensively means
# engine_step.py also works standalone / imported as `dojo.engine_step` / run under pytest). ---
_ROOT = Path(__file__).resolve().parents[3]  # .../42
for _p in ("backtest", "setup/scripts", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

import pandas as pd  # noqa: E402

import heartbeat_core as hc  # noqa: E402 -- the REAL live decision path (bare import, setup/scripts on path)
from lib.orchestrator import _align_vix_to_spy  # noqa: E402 -- reused verbatim, not reimplemented

ET = ZoneInfo("America/New_York")
RTH_OPEN = dtime(9, 30)
RTH_CLOSE = dtime(16, 0)

DATA_DIR = _ROOT / "backtest" / "data"
KEY_LEVELS_PATH = _ROOT / "automation" / "state" / "key-levels.json"

FLEET_ARM_IDS = ("safe-3", "risky-1", "risky-3")
CORE_ACCOUNTS = ("safe", "bold")


# --------------------------------------------------------------------------- DojoDecision
@dataclass(frozen=True)
class DojoDecision:
    """One arm's engine-decision at one bar. Field order matches
    DOJO-ARCHITECTURE-DECISION.md's frozen contract verbatim."""

    arm: str
    side: "str | None"
    verdict: str
    bear_score: "int | None"
    bull_score: "int | None"
    ribbon: "str | None"
    htf_15m: "str | None"
    vix: "float | None"
    triggers: "tuple[str, ...]"
    setup: "str | None"
    trigger_level: "float | None"
    would_place: bool
    spy: "float | None"
    cursor_et: str
    context_bundle: "dict | None"

    def _asdict(self) -> dict:
        return dataclasses.asdict(self)


# --------------------------------------------------------------------------- bar-store loader
_CACHE_END_RE_TMPL = r"^{prefix}_(\d{{4}}-\d{{2}}-\d{{2}})_(\d{{4}}-\d{{2}}-\d{{2}})\.csv$"


def _parse_replay_day(replay_day: str) -> dt.date:
    return dt.datetime.strptime(replay_day, "%Y-%m-%d").date()


def _find_cache_csv(prefix: str, replay_day: dt.date) -> Path:
    """Pick the cached backtest/data/{prefix}_<start>_<end>.csv whose [start, end] window
    covers replay_day, preferring the SMALLEST covering end-date (the snapshot closest to, or
    captured on, replay_day itself — closer to what was actually known then, and deterministic
    across repeated calls). Generalizes replay_today_eval.load_spy_ribbon()'s single hardcoded
    SPY_PATH to an arbitrary day."""
    pattern = re.compile(_CACHE_END_RE_TMPL.format(prefix=re.escape(prefix)))
    candidates: list[tuple[dt.date, Path]] = []
    for p in DATA_DIR.glob(f"{prefix}_*.csv"):
        m = pattern.match(p.name)
        if not m:
            continue
        start = dt.date.fromisoformat(m.group(1))
        end = dt.date.fromisoformat(m.group(2))
        if start <= replay_day <= end:
            candidates.append((end, p))
    if not candidates:
        raise FileNotFoundError(
            f"no {prefix}_*.csv cache under {DATA_DIR} covers replay_day={replay_day} "
            f"(fetch/append that day's data first)"
        )
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def _tz_aware(series: "pd.Series") -> "pd.Series":
    parsed = pd.to_datetime(series)
    return parsed.dt.tz_localize(ET) if parsed.dt.tz is None else parsed.dt.tz_convert(ET)


def load_day_bars(replay_day: str) -> pd.DataFrame:
    """Load 5-min SIP RTH+context bars up through (and including) replay_day, with the full
    prior history the cache file carries for ribbon/level warmup (heartbeat_core._build_payload
    needs >=80 RTH bars and seeds a 48-EMA ribbon over the WHOLE passed frame, not just the
    window it scores — see that function's docstring). Mirrors
    backtest/tools/replay_today_eval.py::load_spy_ribbon()'s cache-loading pattern, generalized
    from one hardcoded day to any replay_day. Returns the same shape
    heartbeat_core._fetch_spy_5m() returns live: a tz-aware (America/New_York) `timestamp`
    column + open/high/low/close/volume — _build_payload RTH-filters and windows internally,
    so this loader deliberately does NOT RTH-filter (matches the live fetch's own contract)."""
    day = _parse_replay_day(replay_day)
    path = _find_cache_csv("spy_5m", day)
    df = pd.read_csv(path)
    df["timestamp"] = _tz_aware(df["timestamp_et"])
    cutoff = pd.Timestamp(datetime.combine(day, dtime(23, 59, 59), tzinfo=ET))
    df = df[df["timestamp"] <= cutoff].reset_index(drop=True)
    return df[["timestamp", "open", "high", "low", "close", "volume"]].copy()


def _load_vix_cache(replay_day: dt.date) -> pd.DataFrame:
    path = _find_cache_csv("vix_5m", replay_day)
    df = pd.read_csv(path)
    df["timestamp_et"] = _tz_aware(df["timestamp_et"])
    cutoff = pd.Timestamp(datetime.combine(replay_day, dtime(23, 59, 59), tzinfo=ET))
    return df[df["timestamp_et"] <= cutoff].reset_index(drop=True)


# --------------------------------------------------------------------------- trigger-bar location
def _rth_filter(df: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    """Byte-identical to heartbeat_core._build_payload's own RTH filter (that function's first
    real line) — reproduced here ONLY to locate which bar _build_payload will treat as the
    trigger (trig_idx = n-2) so the VIX/levels injected for it are for the RIGHT bar. Does not
    duplicate any scoring/gating."""
    ts = pd.to_datetime(df[ts_col]).dt.tz_convert(ET)
    mask = (ts.dt.time >= RTH_OPEN) & (ts.dt.time < RTH_CLOSE)
    return df[mask].reset_index(drop=True)


def _trigger_bar(sliced: pd.DataFrame) -> "tuple[pd.Timestamp, float] | None":
    """(trigger_ts, trigger_close) for the bar _build_payload will score as trig_idx=n-2 of
    `sliced`'s RTH-filtered tail — None if fewer than 2 RTH bars are available yet (mirrors
    _build_payload's own `len(df) < 80` / ribbon-seed fail-safes returning None, but cheaper:
    this check runs BEFORE the VIX/levels fetches, which are pointless without a trigger bar)."""
    rth = _rth_filter(sliced)
    if len(rth) < 2:
        return None
    row = rth.iloc[-2]
    return pd.Timestamp(row["timestamp"]), float(row["close"])


# --------------------------------------------------------------------------- VIX injection
def _vix_for_trigger(sliced: pd.DataFrame, vix_df: pd.DataFrame) -> tuple[float, float]:
    """(vix_now, vix_prior) at the trigger bar, via lib.orchestrator._align_vix_to_spy (REUSED
    verbatim — same utility replay_heartbeat_core.py uses for this exact purpose) aligned onto
    `sliced`'s own RTH-filtered frame, so position -2/-3 line up with trig_idx=n-2/n-3 exactly
    as heartbeat_core would see them live (heartbeat_core._fetch_vix() itself is a plain
    'latest 2 live VIX closes' read, independent of the trigger bar; replay_heartbeat_core.py's
    per-trigger-bar alignment is the established historical-replay precedent this mirrors)."""
    rth = _rth_filter(sliced)
    if len(rth) == 0:
        return 0.0, 0.0
    spy_for_align = rth.rename(columns={"timestamp": "timestamp_et"})
    vix_al = _align_vix_to_spy(spy_for_align, vix_df)
    if len(vix_al) == 0:
        return 0.0, 0.0
    now_v = float(vix_al.iloc[-2]) if len(vix_al) >= 2 else float(vix_al.iloc[-1])
    prior_v = float(vix_al.iloc[-3]) if len(vix_al) >= 3 else now_v
    return now_v, prior_v


def _vix_daily_ma_asof(vix_df: pd.DataFrame, trig_date: dt.date) -> tuple[float, float]:
    """(vix_5d_ma, vix_20d_ma) = mean of the prior 5 / prior 20 DAILY VIX closes strictly
    BEFORE trig_date (never including trig_date itself). Mirrors
    heartbeat_core._fetch_vix_daily_ma / lib.orchestrator's per-day precompute (orchestrator.py
    ~801-817, reproduced here rather than imported since it's a ~6-line groupby, not scoring
    logic). 0.0 when insufficient prior history, the same default both of those use."""
    d = vix_df.copy()
    d["_date"] = d["timestamp_et"].dt.date
    closes_by_day = d.groupby("_date")["close"].last()
    prior_days = sorted(dd for dd in closes_by_day.index if dd < trig_date)
    ma5 = sum(closes_by_day[dd] for dd in prior_days[-5:]) / 5.0 if len(prior_days) >= 5 else 0.0
    ma20 = sum(closes_by_day[dd] for dd in prior_days[-20:]) / 20.0 if len(prior_days) >= 20 else 0.0
    return ma5, ma20


def _historical_vix_intraday(vix_df: pd.DataFrame, cap_ts_et: "pd.Timestamp") -> "list[float] | None":
    """Historical stand-in for heartbeat_core._fetch_vix_intraday() (RTH 5m ^VIX closes,
    newest last, causally capped at cap_ts_et). heartbeat_core._build_payload only reads its
    injected `vix_intraday` argument when account_params['j_vix_dayside_enabled'] is true
    (params.json: true for safe as of 2026-07-20) — WITHOUT this, _build_payload would fall
    back to calling the LIVE yfinance fetch internally (today's real VIX, not replay_day's),
    silently leaking live data into a historical replay. Always computed and passed so that
    leak is structurally impossible regardless of the flag's value."""
    ts = vix_df["timestamp_et"]
    mask = (ts.dt.time >= dtime(9, 30)) & (ts.dt.time <= dtime(15, 55))
    s = vix_df.loc[mask]
    s = s[s["timestamp_et"] <= cap_ts_et]
    vals = [float(x) for x in s["close"].tolist() if x == x]
    return vals or None


# --------------------------------------------------------------------------- levels injection
def _level_expired_asof(lv: dict, as_of_day: str) -> bool:
    """heartbeat_core._level_expired, parameterized on `as_of_day` instead of the real live
    clock (see module docstring's HISTORICAL VIX/LEVELS disclosure)."""
    raw = lv.get("expires_at") if isinstance(lv, dict) else None
    if not raw:
        return False
    exp = str(raw)[:10]
    try:
        dt.date.fromisoformat(exp)
    except ValueError:
        return False
    return exp < as_of_day


def _load_levels_as_of(replay_day: dt.date, spy_price: float) -> tuple[list[float], list[float]]:
    """heartbeat_core._read_levels's proximity-filtered active/multi split, sourced from the
    CURRENT key-levels.json but restricted to entries knowable as of replay_day (see module
    docstring's disclosed-approximation note). Fail-open to ([], []) on any read error, same
    as _read_levels."""
    try:
        kl = json.loads(KEY_LEVELS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    day_str = replay_day.isoformat()
    pool = list(kl.get("levels") or []) + list(kl.get("deprecated_levels") or [])
    active: list[float] = []
    multi: list[float] = []
    seen: set[tuple[float, "str | None"]] = set()
    for lv in pool:
        if not isinstance(lv, dict):
            continue
        p = lv.get("price") or lv.get("level") or lv.get("value")
        if not isinstance(p, (int, float)):
            continue
        verified = str(lv.get("verified_at") or "")[:10]
        if verified and verified > day_str:
            continue  # not yet drawn as of replay_day -- no look-ahead
        if _level_expired_asof(lv, day_str):
            continue
        key = (round(float(p), 2), lv.get("label"))
        if key in seen:
            continue
        seen.add(key)
        if abs(float(p) - spy_price) <= 12:
            active.append(round(float(p), 2))
            if lv.get("multi_day") or lv.get("role") in ("broken_to_resistance", "resistance", "support"):
                multi.append(round(float(p), 2))
    return active, multi


# --------------------------------------------------------------------------- per-account decide
def _decide_for_account(account: str, sliced: pd.DataFrame, bar_et: datetime,
                        vix_now: float, vix_prior: float, vix5: float, vix20: float,
                        levels_active: list[float], levels_carry: list[float],
                        vix_intraday: "list[float] | None") -> DojoDecision:
    """Calls the REAL live path: heartbeat_core._build_payload (setup/scripts/heartbeat_core.py
    :544) then heartbeat_core._engine_verdict (the exact function run_account() calls on the
    payload, setup/scripts/heartbeat_core.py:932) — reused verbatim, nothing re-implemented.

    `would_place` reflects the rules-engine verdict ONLY (ENTER_BEAR/ENTER_BULL), i.e. what
    run_account checks BEFORE its free-model veto / entry-ceiling / staleness / risk-sizing
    ladder. The dojo is ZERO-LLM by design (DOJO-ARCHITECTURE-DECISION.md) and those later
    checks are keyed off the REAL live wall clock (_et_now()), which is meaningless for a
    replayed past bar — so this intentionally does not attempt to reproduce them."""
    cfg = hc.ACCOUNTS[account]
    params = json.loads(cfg["params"].read_text(encoding="utf-8"))
    payload = hc._build_payload(
        sliced, params,
        vix=(vix_now, vix_prior),
        levels=(levels_active, levels_carry),
        vix_ma=(vix5, vix20),
        vix_intraday=vix_intraday,
    )
    if payload is None:
        return DojoDecision(
            arm=account, side=None, verdict="SKIP_NO_DATA", bear_score=None, bull_score=None,
            ribbon=None, htf_15m=None, vix=None, triggers=(), setup=None, trigger_level=None,
            would_place=False, spy=None, cursor_et=bar_et.isoformat(), context_bundle=None,
        )
    verdict = hc._engine_verdict(payload)
    bc = payload["bar_ctx"]
    v = verdict.get("verdict")
    return DojoDecision(
        arm=account,
        side=verdict.get("side"),
        verdict=v or "SKIP_BAD_INPUT",
        bear_score=verdict.get("bear_score"),
        bull_score=verdict.get("bull_score"),
        ribbon=bc["ribbon_now"]["stack"],
        htf_15m=bc["htf_15m_stack"],
        vix=round(float(bc["vix_now"]), 2),
        triggers=tuple(verdict.get("triggers_fired") or []),
        setup=verdict.get("setup_name"),
        trigger_level=verdict.get("rejection_level"),
        would_place=v in ("ENTER_BEAR", "ENTER_BULL"),
        spy=bc["bar"]["close"],
        cursor_et=bar_et.isoformat(),
        context_bundle=bc.get("context_bundle"),
    )


def _fleet_view_pending(arm_id: str, bar_et: datetime) -> DojoDecision:
    """Honest placeholder — see module docstring FLEET ARMS. No score/trigger field is ever
    fabricated; every one is None."""
    return DojoDecision(
        arm=f"fleet_{arm_id.replace('-', '_')}", side=None, verdict="FLEET_VIEW_PENDING",
        bear_score=None, bull_score=None, ribbon=None, htf_15m=None, vix=None, triggers=(),
        setup=None, trigger_level=None, would_place=False, spy=None,
        cursor_et=bar_et.isoformat(), context_bundle=None,
    )


# --------------------------------------------------------------------------- the contract entry point
def step(replay_day: str, bar_et: datetime, bars_df: pd.DataFrame) -> "list[DojoDecision]":
    """Frozen contract (DOJO-ARCHITECTURE-DECISION.md): slice bars_df to <= bar_et, produce the
    engine's decision for BOTH core accounts (safe, bold) via the REAL live decide path, plus
    one honest placeholder per fleet arm. One DojoDecision per arm, 5 total."""
    if bar_et.tzinfo is None:
        raise ValueError("bar_et must be timezone-aware (ET)")
    bar_et = bar_et.astimezone(ET)
    sliced = bars_df[bars_df["timestamp"] <= pd.Timestamp(bar_et)].reset_index(drop=True)

    trig = _trigger_bar(sliced)
    if trig is None:
        vix_now = vix_prior = vix5 = vix20 = 0.0
        levels_active: list[float] = []
        levels_carry: list[float] = []
        vix_intraday_hist = None
    else:
        trig_ts, trig_close = trig
        day = _parse_replay_day(replay_day)
        vix_df = _load_vix_cache(day)
        vix_now, vix_prior = _vix_for_trigger(sliced, vix_df)
        vix5, vix20 = _vix_daily_ma_asof(vix_df, trig_ts.date())
        levels_active, levels_carry = _load_levels_as_of(day, trig_close)
        vix_intraday_hist = _historical_vix_intraday(vix_df, trig_ts)

    decisions = [
        _decide_for_account(account, sliced, bar_et, vix_now, vix_prior, vix5, vix20,
                            levels_active, levels_carry, vix_intraday_hist)
        for account in CORE_ACCOUNTS
    ]
    decisions.extend(_fleet_view_pending(arm_id, bar_et) for arm_id in FLEET_ARM_IDS)
    return decisions
