"""right_tail_waves.py -- GOAL-RIGHT-TAIL-CAPTURE-2026-09-05 R1.

Defines and detects a "right-tail wave": an ENTER-eligible tick (the setup
scored >= 9 on a side with zero blockers -- the same admission bar
`zero_enter_autopsy.py` already reconstructs from `core-decisions.jsonl`)
whose ATM contract's ask later prints >= 1.3x its entry premium (net of the
backtest engine's real cost model) at some point later in the same RTH
session.

TWO SOURCES, chosen per-date (composed, not reimplemented):
  - CORE_SCORE mode: `core-decisions.jsonl` bear_score/bull_score >= 9 with no
    blockers on that side, deduped to unique 5-min bars -- EXACTLY the
    `zero_enter_autopsy._dedup_by_bar` / SCORE_THRESHOLD mechanism, reused via
    import (not reimplemented). Used whenever core-decisions.jsonl actually
    has rows for the requested date (checked via `ts_et`, not the `date`
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
    real ts_et coverage correctly resolves to CORE_SCORE mode. 2026-08-04
    reruns as CORE_SCORE mode: 4 waves at 10:00/13:00/13:35/15:40 ET, peaks
    7.0758x/2.1849x/1.7091x/1.1011x (3 of 4 clear 1.3x) -- this does NOT
    match the stale FLEET_FALLBACK-era "09:58 ~5.4x / 12:28 ~3.0x" numbers
    this docstring and analysis/right-tail/SUMMARY.md previously quoted;
    CORE_SCORE mode is anchored to the `safe` core account's own admission
    ticks, a genuinely different eligibility source from the fleet arms' own
    gates FLEET_FALLBACK used, not a further bug. Guard:
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
for _p in (REPO, BACKTEST, BACKTEST / "lib", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import conductor_outcome as co  # noqa: E402
from lib.simulator_real import DEFAULT_ENTRY_SLIPPAGE  # noqa: E402
from lib.option_pricing_real import (  # noqa: E402
    option_symbol, load_contract_bars, bar_at_or_after,
)

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

WAVE_THRESHOLD = 1.3
WAVE_GAP_MINUTES = 30
SCORE_THRESHOLD = co.ZERO_ENTER_SCORE_THRESHOLD  # 9, reused from conductor_outcome
# NOTE (2026-09-05 correction): there is no fixed "core-decisions.jsonl min
# date" constant here on purpose -- the previous CORE_DECISIONS_MIN_DATE
# ("2026-08-26") encoded a false claim (see module docstring's FLEET_FALLBACK
# entry) and has been removed. Whether a date has core coverage is decided
# live per-date by `_core_decisions_has_date`, never by a hardcoded cutoff.
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


def _eligible_ticks_core_score(day: str, account: str) -> list[dict[str, Any]]:
    """CORE_SCORE mode: reuses zero_enter_autopsy's own dedup-by-bar +
    score/blocker eligibility test (score >= 9, zero blockers on that side)."""
    from zero_enter_autopsy import _decisions_for_day_account, _dedup_by_bar

    rows = _decisions_for_day_account(day, account)
    by_bar = _dedup_by_bar(rows)
    ticks: list[dict[str, Any]] = []
    for tb in sorted(by_bar.keys()):
        r = by_bar[tb]
        for side, score_key, blockers_key in (
            ("bull", "bull_score", "bull_blockers"),
            ("bear", "bear_score", "bear_blockers"),
        ):
            score = r.get(score_key, 0) or 0
            blockers = r.get(blockers_key) or []
            if score >= SCORE_THRESHOLD and not blockers:
                spy = r.get("spy")
                if spy is None:
                    continue
                ticks.append({
                    "ts": tb, "side": side, "spy": float(spy),
                    "source": "core_score",
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


def _price_wave(day: str, side: str, strike_spy: float, start_ts: str) -> dict[str, Any]:
    """Price one wave's peak multiple against the real OPRA cache. Fail-open:
    a missing cache or missing bars degrades to computed=False, never a
    crash or a fabricated number."""
    trade_date = dt.date.fromisoformat(day)
    strike = int(round(strike_spy))
    side_char = "C" if side == "bull" else "P"
    symbol = option_symbol(trade_date, strike, side_char)
    df = load_contract_bars(symbol)
    if df is None or df.empty:
        return {
            "computed": False, "symbol": symbol,
            "reason": f"no OPRA option cache for {symbol}",
            "peak_multiple": None, "peak_time_et": None,
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
        }
    entry_premium = entry_bar.open + DEFAULT_ENTRY_SLIPPAGE
    if entry_premium <= 0:
        return {
            "computed": False, "symbol": symbol,
            "reason": "non-positive entry premium",
            "peak_multiple": None, "peak_time_et": None,
        }
    session_end = dt.datetime.combine(trade_date, RTH_END_ET)
    window = df[(df["timestamp_et"] >= entry_bar.timestamp_et) & (df["timestamp_et"] <= session_end)]
    if window.empty:
        return {
            "computed": False, "symbol": symbol,
            "reason": "no bars in entry->session-end window",
            "peak_multiple": None, "peak_time_et": None,
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
    }


def find_waves(day: str, account: str = "safe") -> list[dict[str, Any]]:
    """Find every right-tail wave on `day`. Returns a list of wave dicts:
    {start_tick_et, side, source_mode, ...pricing fields from _price_wave}.
    Never raises -- a missing/empty data source yields [] (fail-open)."""
    if _core_decisions_has_date(day):
        ticks = _eligible_ticks_core_score(day, account)
        source_mode = "core_score"
    else:
        ticks = _eligible_ticks_fleet_fallback(day)
        source_mode = "fleet_fallback:" + "+".join(FLEET_REFERENCE_ARMS)

    waves: list[dict[str, Any]] = []
    for group in _group_into_waves(ticks):
        start = group[0]
        pricing = _price_wave(day, start["side"], start["spy"], start["ts"])
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
    args = ap.parse_args()
    waves = find_waves(args.date, account=args.account)
    print(json.dumps(waves, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
