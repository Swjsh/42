"""right_tail_waves.py -- GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R1 (R4 fix).

Defines and detects a "right-tail wave": a genuine core-engine ENTER event
(`core-decisions.jsonl` row with `verdict` in {ENTER_BULL, ENTER_BEAR} and
`setup` in {BULLISH_RECLAIM_RIDE_THE_RIBBON, BEARISH_REJECTION_RIDE_THE_RIBBON}
-- the two-trigger ribbon reclaim/rejection shape edge-master-doctrine.md's
"August 2026 big-day anatomy" names as the wave shape) whose ATM contract's
ask later prints >= 1.3x its entry premium (net of the backtest engine's
real cost model) at some point later in the same RTH session.

ROOT-CAUSE FIX (2026-09-05, R4 reopen): the original CORE_SCORE eligibility
test was `bull_score/bear_score >= 9 with zero blockers on that side`,
deduped to unique 5-min bars via `zero_enter_autopsy._dedup_by_bar`
("last occurrence per bar wins"). Two independent bugs in that definition,
both discriminated against the real 2026-08-04/06/13 tape this session:

  1. WRONG ANCHOR (kept H1): score>=9-no-blockers is NOT a discrete trigger
     -- once the ribbon reclaim fires, bull_score/blockers stay >= 9/empty
     for the REST of the session (the field encodes "would this side still
     be admitted right now", not "did a new trigger just fire"). A one-shot
     `verdict` check on `core-decisions.jsonl` is what actually marks the
     admission tick: 2026-08-04 row `{"ts_et": "2026-08-04T09:56:03",
     "verdict": "ENTER_BULL", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
     "triggers": ["level_reclaim", "confluence"]}` is the real wave start;
     the score-threshold reader never looked at `verdict` at all.
  2. WRONG DEDUP (kept H3): `_dedup_by_bar` keeps the LAST row per 5-min
     `trigger_bar_et` bucket (correct for zero_enter_autopsy's OWN job --
     grading a NO-ENTER day off the day's final read on a bar -- wrong here).
     Ticks fire every ~1 min; a bar that had an ENTER_BULL row at :56/:57/:58
     often gets a later HOLD row (already-in-position blocker) in the SAME
     5-min bucket (e.g. 2026-08-04T10:00:04 HOLD, blockers=[11], bucket
     09:50) that silently overwrote the entry row -- shifting the detected
     start to 10:00 and, worse, letting the detector wander onto an
     unrelated later bar/contract entirely (the 7.0758x artifact: bucket
     "10:00" priced against a DIFFERENT bar's contract than the real 09:56
     entry). Fix: don't dedup by bar at all for wave detection -- take every
     verdict-ENTER row directly (episode-grouping in `_group_into_waves`
     already collapses the resulting 1-min-cadence repeats of one real
     entry into a single wave, using the FIRST such row as the start).
  3. SINGLE-ACCOUNT UNDERCOUNT (kept H1's sibling): the two core accounts
     ("safe", "bold") don't always admit the same tick -- 2026-08-27's
     11:52 wave (edge-master-doctrine.md) only appears in the `bold`
     account's own ENTER_BULL rows (11:51-11:59); `safe` sits it out and
     doesn't re-admit until 12:31. A safe-only reader misses the doctrine
     wave entirely and reports the wrong (much later) start. Fix: union
     ENTER ticks across both core accounts (CORE_ACCOUNTS), same
     reasoning as FLEET_REFERENCE_ARMS' existing union rationale below.

  Discriminating checks + verdicts for H2 (contract/price-field) and H5
  (window): H2 KILLED -- the entry/peak PRICING path (ATM strike, next-bar
  open+slippage, high-over-window) was never the bug; re-run against the
  corrected 09:56 anchor it reproduces doctrine's ~2.0x at TP1 directly. H5
  KILLED -- the >=1.3x test already runs over the full entry->session-end
  window; the wrong numbers were entirely a wrong-anchor artifact (bugs 1-2
  above), not a windowing bug.

TWO SOURCES, chosen per-date (composed, not reimplemented):
  - CORE_SCORE mode: `core-decisions.jsonl` `verdict` in
    {ENTER_BULL, ENTER_BEAR} rows on `setup` in WAVE_SETUP_NAMES, unioned
    across CORE_ACCOUNTS. Used whenever core-decisions.jsonl actually has
    rows for the requested date (checked via `ts_et`, not the `date`
    field -- see the FLEET_FALLBACK entry below for why).
  - FLEET_FALLBACK mode: a documented DEGRADE PATH for a genuinely missing
    day only (e.g. `automation/state/fleet/<arm>/decisions.jsonl` for a date
    with no core-decisions rows at all). It is NOT the normal path for any
    August date: CORRECTED 2026-09-05 (GOAL-RIGHT-TAIL-CAPTURE-2026-09-05
    reader-truncation fix) -- the ORIGINAL claim here ("core-decisions.jsonl
    has no rows before 2026-08-26, min(date) -> 2026-08-26") was FALSE. It
    was produced by `_core_decisions_has_date` calling
    `conductor_outcome._decisions_for_day`, which filtered strictly on each
    row's `date` key. `heartbeat_core.py`'s `_log()` only started injecting a
    `date` key on 2026-08-25 (its own docstring even flagged this as a
    "LATENT trap" for exactly this kind of consumer); every row written
    before that carries `ts_et` only. So the pre-08-26 rows were never
    "missing" -- 2026-08-04 alone has 776 real rows (verified: `grep -c
    '"ts_et": "2026-08-04' automation/state/core-decisions.jsonl` -> 776) --
    they were silently excluded by a field-presence bug in the reader, not a
    data gap. Fix: `conductor_outcome._decisions_for_day` (via `_row_day`)
    now falls back to `ts_et[:10]` when `date` is absent, so any date with
    real ts_et coverage correctly resolves to CORE_SCORE mode. Guard:
    `backtest/tests/test_right_tail_waves.py::
    test_2026_08_04_core_decisions_has_date_is_true_never_fallback`.

Wave grouping: eligible ticks are grouped into "episodes" -- consecutive
ticks (same side) within WAVE_GAP_MINUTES of each other collapse into one
wave, using the EARLIEST tick as the wave's start (avoids reporting one wave
per 5-min bar of a single multi-bar signal). A gap longer than
WAVE_GAP_MINUTES, or a side change, starts a new wave.

Pricing: ATM strike = round(spy-at-start-tick); the fill convention already
documented in `option_pricing_real.py` ("next 5-min bar after the trigger
bar") is reused -- entry bar = the first OPRA bar at/after
start_tick + 5 minutes; entry premium = entry_bar.open +
DEFAULT_ENTRY_SLIPPAGE (`simulator_real.py`'s real cost model, never a
hand-rolled number, same convention `zero_enter_autopsy._price_thesis_payoff`
uses). Peak = max(high) over every OPRA bar from the entry bar through the
end of the RTH session (16:00 ET) that day. peak_multiple = peak_high /
entry_premium. meets_threshold = peak_multiple >= WAVE_THRESHOLD (1.3).

Fail-open throughout: a missing OPRA cache, missing decisions data, or any
lookup miss degrades a wave to `computed: False` with a `reason` string --
never a crash, never a fabricated number.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (REPO, BACKTEST, BACKTEST / "lib", BACKTEST / "tools", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import conductor_outcome as co  # noqa: E402
from lib.simulator_real import DEFAULT_ENTRY_SLIPPAGE  # noqa: E402
from lib.option_pricing_real import (  # noqa: E402
    option_symbol, load_contract_bars, bar_at_or_after,
)
from _option_bars_1min_cache import load_1min_cache_readonly  # noqa: E402
# GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3: read-only 1-min cache lookup, shared with
# setup/scripts/gate_net_cost_walk.py (OP-22 -- one loader, not copy-pasted).

RESOLUTIONS = ("5min", "1min")

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

WAVE_THRESHOLD = 1.3
WAVE_GAP_MINUTES = 30
# NOTE (2026-09-05 correction): there is no fixed "core-decisions.jsonl min
# date" constant here on purpose -- the previous CORE_DECISIONS_MIN_DATE
# ("2026-08-26") encoded a false claim (see module docstring's FLEET_FALLBACK
# entry) and has been removed. Whether a date has core coverage is decided
# live per-date by `_core_decisions_has_date`, never by a hardcoded cutoff.
# The two core accounts core-decisions.jsonl actually carries (verified:
# `{r.get("account") for r in jsonl}` == {"safe", "bold"}). Unioned for
# CORE_SCORE eligibility -- see module docstring bug #3 (2026-08-27's 11:52
# doctrine wave only exists in `bold`'s own ENTER_BULL rows; a safe-only
# reader misses it and reports the wrong, much-later 12:31 start instead).
CORE_ACCOUNTS = ["safe", "bold"]
# Every real-fills-era fleet arm this repo has run, UNIONED for eligibility (evidence,
# 2026-09-05: safe-3 alone MISSED the entire 2026-08-06 bear-mirror big day -- 0 ENTER_BEAR
# rows that day -- while risky-1/risky-3 each fired one; a single reference arm silently
# drops a real tape-level wave whenever that one arm's own gates happened to sit it out).
FLEET_REFERENCE_ARMS = ["safe-3", "risky-1", "risky-3", "safe-2", "bold-2", "safe-1"]
# The right-tail wave IS the two-trigger ribbon reclaim/rejection shape
# (edge-master-doctrine.md "August 2026 big-day anatomy": "4 of 5 [big days]
# were the same shape ... BULLISH_RECLAIM_RIDE_THE_RIBBON ... the bear mirror
# ... BEARISH_REJECTION"). Evidence, 2026-09-05: without this filter, an
# unrelated setup (VWAP_CONTINUATION also emits ENTER_BULL/ALLOW rows) merges
# into the same wave-episode and drags its start time away from the real
# ribbon-reclaim tick (08-04's risky-1 fired a VWAP_CONTINUATION ENTER at
# 09:46, 12 minutes before the actual 09:58 ribbon-reclaim wave, and the
# 30-minute episode merge swallowed the real start into the wrong one).
WAVE_SETUP_NAMES = {"BULLISH_RECLAIM_RIDE_THE_RIBBON", "BEARISH_REJECTION_RIDE_THE_RIBBON"}
RTH_END_ET = dt.time(16, 0)


def _core_decisions_has_date(day: str) -> bool:
    """True iff core-decisions.jsonl carries at least one row for `day` --
    the deciding factor for which source mode this date uses."""
    try:
        rows = co._decisions_for_day(day, co.DECISIONS_FILE)
    except Exception:
        return False
    return bool(rows)


def _eligible_ticks_core_score(day: str, account: str | None) -> list[dict[str, Any]]:
    """CORE_SCORE mode: every genuine ENTER admission tick on `day` --
    `verdict` in {ENTER_BULL, ENTER_BEAR} and `setup` in WAVE_SETUP_NAMES --
    unioned across CORE_ACCOUNTS (or restricted to one `account` when given,
    e.g. for a single-account capture-scoring join). NOT deduped by bar and
    NOT a score/blockers threshold test -- see module docstring bugs #1/#2
    for why both of those produced the wrong wave anchor on real August
    days. `_group_into_waves` collapses the resulting 1-min-cadence repeats
    of one real entry into a single wave via its own gap-based episode
    grouping, using the earliest tick as the wave start."""
    from zero_enter_autopsy import _decisions_for_day_account

    accounts = [account] if account else CORE_ACCOUNTS
    ticks: list[dict[str, Any]] = []
    for acct in accounts:
        rows = _decisions_for_day_account(day, acct)
        for r in rows:
            verdict = r.get("verdict")
            if verdict not in ("ENTER_BULL", "ENTER_BEAR"):
                continue
            if r.get("setup") not in WAVE_SETUP_NAMES:
                continue
            ts = str(r.get("ts_et", "") or "")
            if len(ts) < 16 or not ("09:35" <= ts[11:16] < "16:00"):
                continue
            spy = r.get("spy")
            if spy is None:
                continue
            side = "bull" if verdict == "ENTER_BULL" else "bear"
            ticks.append({
                "ts": ts, "side": side, "spy": float(spy),
                "source": f"core_score:{acct}",
            })
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def _eligible_ticks_fleet_fallback(day: str, arms: list[str] = FLEET_REFERENCE_ARMS) -> list[dict[str, Any]]:
    """FLEET_FALLBACK mode: the UNION of every reference arm's own admission
    gate (see FLEET_REFERENCE_ARMS docstring for why a single arm undercounts).
    action in {"ENTER_BULL","ENTER_BEAR"} + risk_code == "ALLOW" means that
    arm's fleet gate did not block this tick -- an eligible tick by that arm's
    own admission rules. `strike` (not `spy`) is the field this source
    carries. Ticks from different arms are NOT deduped against each other
    (each is a real, independent admission signal); the wave-grouping step
    collapses same-side ticks within WAVE_GAP_MINUTES regardless of which
    arm produced them."""
    ticks: list[dict[str, Any]] = []
    for arm in arms:
        path = REPO / "automation" / "state" / "fleet" / arm / "decisions.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(r.get("ts_et", "") or "")
            if not ts.startswith(day):
                continue
            action = r.get("action")
            if action not in ("ENTER_BULL", "ENTER_BEAR"):
                continue
            if r.get("risk_code") != "ALLOW":
                continue
            if r.get("setup_name") not in WAVE_SETUP_NAMES:
                continue
            strike = r.get("strike")
            if strike is None:
                continue
            side = "bull" if action == "ENTER_BULL" else "bear"
            ticks.append({
                "ts": ts[:19], "side": side, "spy": float(strike),
                "source": f"fleet_fallback:{arm}",
            })
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def _group_into_waves(ticks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Collapse consecutive same-side ticks within WAVE_GAP_MINUTES of each
    other into one episode; returns a list of tick-groups (one per wave)."""
    groups: list[list[dict[str, Any]]] = []
    for t in ticks:
        ts = dt.datetime.fromisoformat(t["ts"])
        if groups:
            last = groups[-1][-1]
            last_ts = dt.datetime.fromisoformat(last["ts"])
            gap_min = (ts - last_ts).total_seconds() / 60.0
            if last["side"] == t["side"] and gap_min <= WAVE_GAP_MINUTES:
                groups[-1].append(t)
                continue
        groups.append([t])
    return groups


def _price_wave(day: str, side: str, strike_spy: float, start_ts: str,
                 resolution: str = "5min") -> dict[str, Any]:
    """Price one wave's peak multiple against the real OPRA cache. Fail-open:
    a missing cache or missing bars degrades to computed=False, never a
    crash or a fabricated number.

    resolution (GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3, default unchanged): "1min" looks up
    the 1-min cache read-only via `_option_bars_1min_cache.load_1min_cache_readonly` for the
    resolved contract/day; a cache miss falls back to the normal 5-min `load_contract_bars`
    cache, disclosed via the returned `resolution_used` / `resolution_1min_fallback` fields
    -- never a live fetch from inside this pricer, never a silent resolution blend."""
    trade_date = dt.date.fromisoformat(day)
    strike = int(round(strike_spy))
    side_char = "C" if side == "bull" else "P"
    symbol = option_symbol(trade_date, strike, side_char)
    resolution_1min_fallback = False
    if resolution == "1min":
        df = load_1min_cache_readonly(symbol, day)
        resolution_used = "1min"
        if df is None:
            df = load_contract_bars(symbol)
            resolution_used = "5min"
            resolution_1min_fallback = True
    else:
        df = load_contract_bars(symbol)
        resolution_used = "5min"
    if df is None or df.empty:
        return {
            "computed": False, "symbol": symbol,
            "reason": f"no OPRA option cache for {symbol}",
            "peak_multiple": None, "peak_time_et": None,
            "resolution_used": resolution_used,
            "resolution_1min_fallback": resolution_1min_fallback,
        }
    df = df.copy()
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"]).dt.tz_localize(None)
    start_dt = dt.datetime.fromisoformat(start_ts)
    if start_dt.tzinfo is not None:
        start_dt = start_dt.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
    entry_lookup = start_dt + dt.timedelta(minutes=5)  # next-bar fill convention
    entry_bar = bar_at_or_after(df, entry_lookup)
    if entry_bar is None:
        return {
            "computed": False, "symbol": symbol,
            "reason": f"no {symbol} bar at/after {entry_lookup.isoformat()}",
            "peak_multiple": None, "peak_time_et": None,
            "resolution_used": resolution_used,
            "resolution_1min_fallback": resolution_1min_fallback,
        }
    entry_premium = entry_bar.open + DEFAULT_ENTRY_SLIPPAGE
    if entry_premium <= 0:
        return {
            "computed": False, "symbol": symbol,
            "reason": "non-positive entry premium",
            "peak_multiple": None, "peak_time_et": None,
            "resolution_used": resolution_used,
            "resolution_1min_fallback": resolution_1min_fallback,
        }
    session_end = dt.datetime.combine(trade_date, RTH_END_ET)
    window = df[(df["timestamp_et"] >= entry_bar.timestamp_et) & (df["timestamp_et"] <= session_end)]
    if window.empty:
        return {
            "computed": False, "symbol": symbol,
            "reason": "no bars in entry->session-end window",
            "peak_multiple": None, "peak_time_et": None,
            "resolution_used": resolution_used,
            "resolution_1min_fallback": resolution_1min_fallback,
        }
    peak_idx = window["high"].idxmax()
    peak_high = float(window.loc[peak_idx, "high"])
    peak_time = window.loc[peak_idx, "timestamp_et"]
    peak_multiple = round(peak_high / entry_premium, 4)
    return {
        "computed": True,
        "symbol": symbol,
        "strike": strike,
        "side": side_char,
        "entry_bar_et": entry_bar.timestamp_et.isoformat(),
        "entry_premium": round(entry_premium, 4),
        "peak_high": peak_high,
        "peak_time_et": peak_time.isoformat(),
        "peak_multiple": peak_multiple,
        "meets_threshold": peak_multiple >= WAVE_THRESHOLD,
        "resolution_used": resolution_used,
        "resolution_1min_fallback": resolution_1min_fallback,
    }


def find_waves(day: str, account: str | None = None, resolution: str = "5min") -> list[dict[str, Any]]:
    """Find every right-tail wave on `day`. Returns a list of wave dicts:
    {start_tick_et, side, source_mode, ...pricing fields from _price_wave}.
    `account` defaults to None -- union both CORE_ACCOUNTS (the tape-level
    wave, per module docstring bug #3); pass a specific account (e.g.
    "safe") to restrict eligibility to that account's own admission ticks
    only, for a single-account capture-scoring join. Never raises -- a
    missing/empty data source yields [] (fail-open).

    resolution (GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3, default unchanged): passed straight
    through to `_price_wave` -- see that function's docstring."""
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {RESOLUTIONS}, got {resolution!r}")
    if _core_decisions_has_date(day):
        ticks = _eligible_ticks_core_score(day, account)
        source_mode = "core_score"
    else:
        ticks = _eligible_ticks_fleet_fallback(day)
        source_mode = "fleet_fallback:" + "+".join(FLEET_REFERENCE_ARMS)

    waves: list[dict[str, Any]] = []
    for group in _group_into_waves(ticks):
        start = group[0]
        pricing = _price_wave(day, start["side"], start["spy"], start["ts"], resolution=resolution)
        waves.append({
            "date": day,
            "source_mode": source_mode,
            "start_tick_et": start["ts"],
            "side": start["side"],
            "n_ticks_in_wave": len(group),
            **pricing,
        })
    return waves


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    ap.add_argument("--account", default="safe")
    ap.add_argument("--resolution", default="5min", choices=list(RESOLUTIONS))
    args = ap.parse_args()
    waves = find_waves(args.date, account=args.account, resolution=args.resolution)
    print(json.dumps(waves, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
