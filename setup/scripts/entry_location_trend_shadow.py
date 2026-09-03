"""entry_location_trend_shadow.py -- F2 ENTRY-LOCATION x TREND-QUALITY SHADOW LEDGER.

Descends from analysis/deep-research/2026-09-03-money/entry-location.md (H1 ENTRY LOCATION,
verdict INCONCLUSIVE) and its two builder tools, backtest/tools/money_entry_location.py +
money_entry_location_stats.py (READ-ONLY imported below, never modified). H1's own
"Proposed change" section named the exact next step this module is:

    "INSTRUMENT_ONLY (recommended next step, $0, no network): promote
    money_entry_location.py / money_entry_location_stats.py from scratch tools into a
    small nightly-refreshable shadow ledger ... that logs range_position, setup, side,
    and realized_pnl per trade going forward ... and require the chase bucket to be
    conditioned on a trend-quality co-signal (e.g. htf_15m/ribbon confirmation duration,
    or distance since the ribbon flip) so a fresh-breakout continuation can be told apart
    from an exhaustion chase before any gate is proposed."

WHY (from entry-location.md's own evidence, restated): BULLISH_RECLAIM_RIDE_THE_RIBBON /
BEARISH_REJECTION_RIDE_THE_RIBBON triggers fire AFTER the directional push that puts price
near the session extreme -- range_position alone cannot tell "SPY is making a fresh high and
this call is riding it" (a winner) from "SPY is exhausted at the extreme and this call is
about to reverse" (a loser); both print range_position~=1.0 by construction. The 2026-08-13
and 2026-08-27 blocked-winner clusters are exactly this confound. A trend-quality co-signal
is the only way to eventually separate the two -- this ledger measures four of them, every
night, forward AND backfilled, so the one pre-registered follow-up test in
analysis/recommendations/prereg-entry-location-trend-2026-09-03.md has a population to read
once it reaches its frozen bar.

WHAT THIS MODULE DOES NOT DO: it does not gate any live trade, it does not re-open H1's own
verdict, and it ships no rule. It is INSTRUMENT_ONLY, descriptive, shadow, status ARMED.
Nothing before 2026-10-30 (config freeze) regardless of what the ledger eventually shows.

PER-TRADE ROW (one per engine fill, ALL 6 SPY-option arms -- safe-1/2/3, bold-2, risky-1,
risky-3 -- population is EVERY trade in analysis/pain-ledger/mae-mfe.json, no date cutoff,
unlike H1's own date>=2026-08-06 restriction, because this instrument's job is to accrue
n toward the prereg's n_chase>=150 floor as fast as honestly possible):

  date, arm, symbol, setup, side, realized_pnl                    -- straight from mae-mfe.json
  range_position                                                  -- H1's own formula, reproduced
                                                                      here (not re-derived): session
                                                                      hi/lo over SPY ticks with
                                                                      ts_et <= entry_ts on the same
                                                                      date, from core-decisions.jsonl
                                                                      (both safe+bold accounts --
                                                                      same underlying instrument for
                                                                      every arm, exactly H1's design)
  minutes_since_ribbon_flip                                       -- minutes since the ribbon stack
                                                                      (core-decisions.jsonl "ribbon"
                                                                      field, BULL/BEAR/MIXED) last
                                                                      flipped INTO the trade's own
                                                                      direction (BULL for calls, BEAR
                                                                      for puts), computed by walking
                                                                      BACKWARD from entry through the
                                                                      SAME no-lookahead prefix -- null
                                                                      when ribbon at entry does not
                                                                      currently match the trade
                                                                      direction, left-censored (flagged,
                                                                      not fabricated) when the matching
                                                                      streak covers the entire visible
                                                                      prefix for that date (true flip
                                                                      time unknown, may be pre-session)
  minutes_since_htf15m_match                                      -- identical mechanism against the
                                                                      "htf_15m" field
  or_extension_dollars / or_extension_multiples                   -- spy_at_entry vs the 09:30-09:45
                                                                      opening-range high (calls) / low
                                                                      (puts), in the trade's own
                                                                      direction, in $ and in multiples
                                                                      of that range's width; computed
                                                                      from ticks in [09:30,09:45] AND
                                                                      <= entry only (a trade entered
                                                                      before 09:45 sees a PARTIAL,
                                                                      honestly-flagged opening range,
                                                                      never the full-session one)
  vix_at_entry / vix_dir                                          -- vix_at_entry from the same
                                                                      no-lookahead tick; vix_dir
                                                                      ("up"/"down"/"flat", |delta|<0.05
                                                                      = flat) compares it to the VIX
                                                                      reading ~15 minutes earlier in
                                                                      the SAME prefix (or the earliest
                                                                      available tick that date if
                                                                      fewer than 15 minutes have
                                                                      elapsed -- left-censored, flagged)
  confirm_bars                                                    -- (B4, 2026-09-03) number of
                                                                      consecutive CLOSED 5-minute SPY
                                                                      bars strictly BEFORE the entry
                                                                      bar whose close already sat
                                                                      beyond trigger_level in the
                                                                      trade's own direction; 0 means
                                                                      the entry fired on the very
                                                                      first bar to cross. Computed by
                                                                      collapsing the SAME no-lookahead
                                                                      `subset` (core-decisions.jsonl's
                                                                      "spy" field IS the 5-minute
                                                                      close, repeated across every
                                                                      faster-cadence heartbeat tick
                                                                      until the next bar closes) into
                                                                      its distinct bar-close sequence,
                                                                      then walking backward from the
                                                                      bar immediately preceding entry.
                                                                      None when trigger_level is
                                                                      unavailable (see below) or the
                                                                      side can't be parsed.
  zone_distance                                                    -- (spy_at_entry - trigger_level)
                                                                      / zone_width in the trade's own
                                                                      direction (positive = already
                                                                      beyond trigger), zone_width
                                                                      resolved per date+level via
                                                                      retest_zone_shadow.resolve_
                                                                      zone_width (REUSED BY IMPORT,
                                                                      never modified) -- flagged
                                                                      zone_width_defaulted=True when
                                                                      no archived width was found
                                                                      (true for the entire current
                                                                      archive as of this build, see
                                                                      that module's own Step 1
                                                                      finding; never silently
                                                                      assumed).
  trigger_level                                                    -- joined from
                                                                      analysis/entry-quality/
                                                                      entry-quality-ledger.json
                                                                      (mae-mfe.json itself carries no
                                                                      trigger_level) by exact
                                                                      (arm, symbol, entry_ts_utc)
                                                                      match against that ledger's own
                                                                      (arm, symbol, ts_utc) -- the
                                                                      SAME three fields, same values,
                                                                      both files sourced from the same
                                                                      fill. None (never fabricated)
                                                                      when no event carries a
                                                                      trigger_level for that key --
                                                                      true for setups that never set
                                                                      one (VWAP_CONTINUATION, etc.)
                                                                      and for a real minority of
                                                                      RIDE_THE_RIBBON fills too.

NO LOOK-AHEAD (verified by test_entry_location_trend_shadow_2026_09_03.py's synthetic-ledger
test): every one of the fields above is computed from a `subset` that is filtered to
`tick_ts <= entry_et` BEFORE any of the helper functions ever see it. A tick recorded after
entry is never in scope to influence a row -- adding one to the fixture and recomputing must
leave every already-scored row byte-identical.

REUSE, NOT REWRITE (money_entry_location.py / money_entry_location_stats.py imported, not
copied line-for-line, and NEVER edited by this module):
  mel.OCC_RE, mel.parse_utc, mel.to_et_naive, mel.parse_ts_et_field, mel.ACCOUNT_TO_ARM
      -- the OCC-symbol side parser and UTC->ET conversion, byte-identical to H1's own.
  mels.classify_chase, mels.bootstrap_mean_ci, mels.bootstrap_diff_ci
      -- H1's own chase-bucket definition (side=='C' and pos>=0.75) or (side=='P' and
      pos<=0.25) and its 5000x nonparametric percentile bootstrap, applied unmodified.
This module's OWN tick loader additionally carries "ribbon" and "htf_15m" per tick (fields
H1's loader never needed), which is why it is a small extension rather than a bare import of
mel.main() -- copying the ~15-line tick-scan loop rather than editing money_entry_location.py
is the "reuse by import or copy, do not modify them" instruction applied literally.

OUTPUTS:
  analysis/recommendations/entry-location-trend-ledger.jsonl    append-only, dedup on row_id
                                                                 (arm::symbol::entry_ts_utc)
  analysis/recommendations/entry-location-trend-summary.json    n per setup, chase-vs-rest with
                                                                 bootstrap CI, the SAME split
                                                                 stratified by each co-signal
                                                                 tercile (or up/down/flat for
                                                                 vix_dir), PLUS (B4) a
                                                                 confirm_bars==0-vs->=1 split per
                                                                 setup and across the four named
                                                                 big winner days -- descriptive,
                                                                 status ARMED, prereg readiness
                                                                 counters for BOTH frozen tests
                                                                 (prereg section 4 and section 9)

B4 (2026-09-03) ADDS two entry-tick features (confirm_bars, zone_distance, both described
above) and a SECOND frozen test in the prereg (section 9, added same day, section 1-4's own
frozen test left untouched): BULLISH_RECLAIM_RIDE_THE_RIBBON chase entries split by
confirm_bars==0 vs confirm_bars>=1, bar n>=100 per cell, decision rule fixed before this
build ever ran the recomputed ledger. Full text: prereg-entry-location-trend-2026-09-03.md
section 9.

BACKFILL: this instrument backfills ALL of mae-mfe.json's history once (dates <= 2026-09-02
are stamped in_sample=true), then accrues forward nightly as mae-mfe.json's own producer
(pain_ledger.py) adds trades -- unlike the sibling tp1_r50_forward_shadow (which is
deliberately forward-only, no backfill, because IT is adjudicating a specific knob against a
frozen bar). This instrument's job is different: it is building the POPULATION the
prereg's own frozen test will eventually read, so backfilling is correct here, not
contamination -- the prereg's decision rule (in the frozen prereg file) is not evaluated
until n_chase>=150 for BULLISH_RECLAIM_RIDE_THE_RIBBON regardless of how the population grew.

COST: $0. Pure local computation over two already-written artifacts (mae-mfe.json,
core-decisions.jsonl) -- no bar fetch, no OPRA, no broker call, no LLM, no network.
Guard: backtest/tests/test_entry_location_trend_shadow_2026_09_03.py.
REVOKE (whole instrument, one shot): Unregister-ScheduledTask
-TaskName Gamma_EntryLocationTrendShadow -Confirm:$false -- analysis-only leaf, nothing on
the trading path depends on this, same class as Gamma_LadderRungShadow /
Gamma_Tp1R50ForwardShadow.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest" / "tools"), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import money_entry_location as mel  # noqa: E402 -- reused read-only, never modified
import money_entry_location_stats as mels  # noqa: E402 -- reused read-only, never modified
import retest_zone_shadow as rzs  # noqa: E402 -- reused, resolve_zone_width only, never modified

MAE_MFE = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
ENTRY_QUALITY_LEDGER = REPO / "analysis" / "entry-quality" / "entry-quality-ledger.json"

OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "entry-location-trend-ledger.jsonl"
SUMMARY = OUT_DIR / "entry-location-trend-summary.json"
PREREG_REL = "analysis/recommendations/prereg-entry-location-trend-2026-09-03.md"

BACKFILL_CUTOFF = "2026-09-02"     # dates <= this are in_sample=true (this build's own date - 1)
CHASE_HI, CHASE_LO = 0.75, 0.25    # H1's own primary threshold, reused via mels.classify_chase

OR_START = dt.time(9, 30)
OR_END = dt.time(9, 45)

VIX_DIR_LOOKBACK_MIN = 15
VIX_DIR_EPS = 0.05

MIN_CELL_N_FOR_CI = 5              # below this a bootstrap diff CI is not reported (too thin)

BULL_PUT_SETUP_FOR_PREREG = "BULLISH_RECLAIM_RIDE_THE_RIBBON"
PREREG_N_CHASE_FLOOR = 150

BIG_WINNER_DAYS = ("2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28")   # per this task's STANDARDS
CONFIRM_BARS_N_FLOOR = 100         # B4 second frozen test (prereg section 9), PER CELL


# ------------------------------------------------------------------------------------------
# ledger I/O -- same tolerant-of-a-torn-last-line contract as the sibling shadow ledgers
# ------------------------------------------------------------------------------------------
def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a torn last line must never kill the accrual
    return rows


def _stamp_now_et() -> str:
    try:
        from et_clock import et_now  # noqa: PLC0415
        return et_now().isoformat()
    except Exception:  # noqa: BLE001 -- a stamp must never break the clock
        return ""


# ------------------------------------------------------------------------------------------
# trigger_level join (B4) -- mae-mfe.json never carries trigger_level; entry-quality-ledger.json
# does, on the SAME (arm, symbol, ts_utc==entry_ts_utc) key both files share (same underlying
# fill). Missing/unreadable ledger -> empty dict, never fabricated: every row's confirm_bars /
# zone_distance simply goes None, exactly like an unparseable symbol already does upstream.
# ------------------------------------------------------------------------------------------
def load_trigger_levels(path: Path) -> dict[tuple[str | None, str | None, str | None], float]:
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[tuple, float] = {}
    for e in doc.get("events", []):
        tl = e.get("trigger_level")
        if tl is None:
            continue
        key = (e.get("arm"), e.get("symbol"), e.get("ts_utc"))
        if key not in out:      # first match wins -- activity_id collisions are not expected
            out[key] = float(tl)
    return out


# ------------------------------------------------------------------------------------------
# tick tape -- extends H1's own loader with "ribbon" + "htf_15m" (H1 never needed them)
# ------------------------------------------------------------------------------------------
def load_tick_tape(core_decisions_path: Path) -> dict[str, list[tuple]]:
    """Per-date, chronologically sorted list of
    (ts_et_naive, spy, vix, ribbon, htf_15m) tuples, built from EVERY row in
    core-decisions.jsonl that carries a 'spy' field (both safe+bold accounts write ticks for
    the same underlying instrument -- exactly H1's own convention, reproduced not re-derived).
    Fleet arms (safe-3/risky-1/risky-3) never write to this file, so it is the ONLY source
    for range_position/ribbon/htf_15m/vix regardless of which arm actually took the trade."""
    ticks_by_date: dict[str, list[tuple]] = collections.defaultdict(list)
    if not core_decisions_path.exists():
        return ticks_by_date
    with core_decisions_path.open(encoding="utf-8") as f:
        for line in f:
            if '"ts_et"' not in line or '"spy"' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_raw = r.get("ts_et")
            spy = r.get("spy")
            if not ts_raw or spy is None:
                continue
            tdt = mel.parse_ts_et_field(ts_raw)
            if tdt is None:
                continue
            d = ts_raw[:10]
            ticks_by_date[d].append((tdt, float(spy), r.get("vix"), r.get("ribbon"), r.get("htf_15m")))
    for d in ticks_by_date:
        ticks_by_date[d].sort(key=lambda x: x[0])
    return ticks_by_date


# ------------------------------------------------------------------------------------------
# trend-quality co-signals -- every helper below is handed an ALREADY-FILTERED `subset`
# (tick_ts <= entry_et), so none of them can see a future tick. This is the no-lookahead
# invariant test_entry_location_trend_shadow_2026_09_03.py's synthetic-ledger test pins.
# ------------------------------------------------------------------------------------------
_TARGET_DIR = {"C": "BULL", "P": "BEAR"}


def _minutes_since_match(subset: list[tuple], field_idx: int, target: str | None,
                          entry_et: dt.datetime) -> dict:
    """Minutes since `field_idx` (3=ribbon, 4=htf_15m) last flipped INTO `target`
    (BULL/BEAR), walking backward through `subset` only. Returns
    {minutes_since_flip, left_censored, note}. `minutes_since_flip` is None when the field
    isn't currently at `target` (nothing to measure) or no ticks carry the field at all;
    `left_censored=True` flags a streak that covers the whole visible prefix -- the TRUE flip
    may have happened before this date's first available tick, and that is never fabricated."""
    if target is None:
        return {"minutes_since_flip": None, "left_censored": None, "note": "no side parsed from symbol"}
    valid = [tk for tk in subset if tk[field_idx] is not None]
    if not valid:
        return {"minutes_since_flip": None, "left_censored": None, "note": "no ticks carry this field in prefix"}
    value_at_entry = valid[-1][field_idx]
    if value_at_entry != target:
        return {"minutes_since_flip": None, "left_censored": None,
                "note": f"value_at_entry={value_at_entry!r} != target {target!r}"}
    i = len(valid) - 1
    while i > 0 and valid[i - 1][field_idx] == target:
        i -= 1
    left_censored = (i == 0)
    flip_ts = valid[i][0]
    minutes = (entry_et - flip_ts).total_seconds() / 60.0
    note = ("left-censored: streak covers the entire visible prefix for this date -- true "
            "flip time unknown, may be pre-session" if left_censored else "flip observed within session")
    return {"minutes_since_flip": round(minutes, 2), "left_censored": left_censored, "note": note}


def _opening_range(ticks_for_date: list[tuple], entry_et: dt.datetime) -> dict:
    """09:30-09:45 SPY high/low, using ticks in that window AND <= entry_et only. A trade
    entered before 09:45 sees a PARTIAL window (honestly flagged via or_window_complete)."""
    window = [tk for tk in ticks_for_date if tk[0] <= entry_et and OR_START <= tk[0].time() <= OR_END]
    if not window:
        return {"or_high": None, "or_low": None, "or_range": None, "or_window_complete": False}
    or_high = max(tk[1] for tk in window)
    or_low = min(tk[1] for tk in window)
    return {"or_high": or_high, "or_low": or_low, "or_range": round(or_high - or_low, 4),
            "or_window_complete": entry_et.time() >= OR_END}


def _or_extension(or_info: dict, spy_at_entry: float | None, side: str | None) -> dict:
    """spy_at_entry vs the opening-range boundary in the TRADE'S OWN direction: calls measure
    distance above or_high, puts measure distance below or_low. Positive = price has already
    extended beyond the opening range in the trade's direction."""
    or_high, or_low, or_range = or_info["or_high"], or_info["or_low"], or_info["or_range"]
    if spy_at_entry is None or or_high is None or side not in ("C", "P"):
        return {"dollars": None, "multiples": None}
    dollars = round(spy_at_entry - or_high, 4) if side == "C" else round(or_low - spy_at_entry, 4)
    multiples = round(dollars / or_range, 4) if or_range and or_range > 1e-9 else None
    return {"dollars": dollars, "multiples": multiples}


def _vix_dir(subset: list[tuple], entry_et: dt.datetime, vix_at_entry: float | None) -> dict:
    """"up"/"down"/"flat" (|delta|<VIX_DIR_EPS=flat) vs the VIX reading ~15 minutes earlier in
    the SAME prefix; falls back to the earliest available tick (left-censored, flagged) when
    fewer than 15 minutes of prefix exist."""
    if vix_at_entry is None:
        return {"vix_dir": None, "vix_delta": None, "note": "no vix_at_entry"}
    ref_time = entry_et - dt.timedelta(minutes=VIX_DIR_LOOKBACK_MIN)
    candidates = [tk for tk in subset if tk[0] <= ref_time and tk[2] is not None]
    if candidates:
        ref = candidates[-1]
        note = f"reference = last tick <= entry-{VIX_DIR_LOOKBACK_MIN}min"
    else:
        with_vix = [tk for tk in subset if tk[2] is not None]
        if not with_vix:
            return {"vix_dir": None, "vix_delta": None, "note": "no vix ticks in prefix"}
        ref = with_vix[0]
        note = f"< {VIX_DIR_LOOKBACK_MIN}min of prefix available -- reference = first tick of prefix (left-censored)"
    delta = round(vix_at_entry - ref[2], 3)
    d = "flat" if abs(delta) < VIX_DIR_EPS else ("up" if delta > 0 else "down")
    return {"vix_dir": d, "vix_delta": delta, "note": note}


def _beyond_trigger(value: float, trigger_level: float, side: str) -> bool:
    """True when `value` (a SPY close) already sits beyond `trigger_level` in the trade's own
    direction -- calls: value > trigger_level; puts: value < trigger_level. Same sign
    convention as _or_extension's `dollars` (positive = beyond)."""
    dollars = (value - trigger_level) if side == "C" else (trigger_level - value)
    return dollars > 0


def _dedup_bar_closes(subset: list[tuple]) -> list[tuple[dt.datetime, float]]:
    """Collapse consecutive core-decision ticks that carry the SAME 'spy' value into one bar
    entry (the ts of the first tick to carry that value, and the close itself). The
    core-decisions feed samples on a faster (heartbeat) cadence than the 5-minute bar closes
    it reports (`spy` is the 5-minute close, held constant across every tick until the next
    bar closes -- see CLAUDE.md task note), so this recovers the true bar-close sequence from
    the repeated tick tape. `subset` is always the caller's already-filtered
    (ts_et <= entry_et) no-lookahead prefix -- this function has no access to any later tick."""
    bars: list[tuple[dt.datetime, float]] = []
    for tk in subset:
        ts, spy = tk[0], tk[1]
        if bars and bars[-1][1] == spy:
            continue
        bars.append((ts, spy))
    return bars


def _confirm_bars(subset: list[tuple], side: str | None, trigger_level: float | None) -> dict:
    """(B4) Count of consecutive CLOSED 5-minute bars STRICTLY BEFORE the entry bar (the last
    distinct bar in `subset`'s own dedup sequence -- the bar in force at entry) whose close was
    already beyond `trigger_level` in the trade's own direction, walking BACKWARD from the bar
    immediately preceding the entry bar and stopping at the first bar that was not yet beyond.
    0 means either the entry bar was itself the first bar to cross (the immediately preceding
    bar had not crossed yet) or there is no prior bar in the visible prefix at all -- both
    read the same way as "0 = the entry fired on the first bar to cross". None when
    trigger_level is unavailable or the side can't be parsed. `subset` is always the caller's
    no-lookahead (ts_et <= entry_et) prefix, so this function never sees a bar at or after
    entry -- a tick added AFTER entry to the caller's own ticks_by_date is filtered out of
    `subset` before this function is ever invoked and cannot change the count."""
    if trigger_level is None or side not in ("C", "P"):
        return {"confirm_bars": None, "n_bars_in_prefix": None,
                "note": "no trigger_level" if trigger_level is None else "side not C/P"}
    bars = _dedup_bar_closes(subset)
    if not bars:
        return {"confirm_bars": None, "n_bars_in_prefix": 0, "note": "no bars in prefix"}
    prior = bars[:-1]      # every closed bar strictly before the entry bar
    count = 0
    for _, value in reversed(prior):
        if _beyond_trigger(value, trigger_level, side):
            count += 1
        else:
            break
    return {"confirm_bars": count, "n_bars_in_prefix": len(bars), "note": "ok"}


def _zone_distance(spy_at_entry: float | None, trigger_level: float | None, side: str | None,
                    date_str: str) -> dict:
    """(B4) (spy_at_entry - trigger_level) / zone_width in the trade's own direction (calls:
    above trigger is positive; puts: below trigger is positive) -- same sign convention as
    _or_extension. zone_width is resolved per (trigger_level, date) via
    retest_zone_shadow.resolve_zone_width (REUSED BY IMPORT, never modified, never
    re-implemented) -- zone_width_defaulted=True whenever that resolver fell back to its
    $0.30 default (no archived snapshot for the date, no matching level, or the matched level
    carries no zone_width field -- true for the entire current archive as of this build, see
    that module's own docstring Step 1 finding). Never silently assumed away."""
    if spy_at_entry is None or trigger_level is None or side not in ("C", "P"):
        return {"zone_distance": None, "zone_width": None, "zone_width_source": None,
                "zone_width_defaulted": None, "zone_width_reason": None}
    zw = rzs.resolve_zone_width(trigger_level, date_str)
    width = zw["width"]
    dollars = (spy_at_entry - trigger_level) if side == "C" else (trigger_level - spy_at_entry)
    zone_distance = round(dollars / width, 4) if width else None
    return {"zone_distance": zone_distance, "zone_width": width,
            "zone_width_source": zw["source"], "zone_width_defaulted": zw["source"] == "default",
            "zone_width_reason": zw["reason"]}


# ------------------------------------------------------------------------------------------
# per-trade row
# ------------------------------------------------------------------------------------------
def compute_row(t: dict, ticks_by_date: dict[str, list[tuple]],
                 trigger_levels: dict | None = None) -> dict | None:
    """One row for one mae-mfe.json trade. Returns None only when the symbol cannot be
    parsed at all (never fabricates a side). `trigger_levels` (B4) is the
    (arm, symbol, entry_ts_utc) -> trigger_level lookup from load_trigger_levels(); omitted
    or missing-key -> confirm_bars/zone_distance simply go None for that row, never
    fabricated."""
    if trigger_levels is None:
        trigger_levels = {}
    sym = t.get("symbol")
    m = mel.OCC_RE.match(sym) if sym else None
    if m is None:
        return None
    side = m.group(2)
    date = t["date"]
    arm = t["arm"]

    entry_utc = mel.parse_utc(t["entry_ts_utc"])
    entry_et = mel.to_et_naive(entry_utc)

    ticks_for_date = ticks_by_date.get(date, [])
    subset = [tk for tk in ticks_for_date if tk[0] <= entry_et]     # THE no-lookahead anchor
    n_ticks_used = len(subset)

    range_position = session_hi = session_lo = spy_at_entry = vix_at_entry = None
    ribbon_at_entry = htf15m_at_entry = None
    if subset:
        session_hi = max(tk[1] for tk in subset)
        session_lo = min(tk[1] for tk in subset)
        spy_at_entry = subset[-1][1]
        vix_at_entry = subset[-1][2]
        ribbon_at_entry = subset[-1][3]
        htf15m_at_entry = subset[-1][4]
        if session_hi > session_lo:
            range_position = round((spy_at_entry - session_lo) / (session_hi - session_lo), 4)

    target_dir = _TARGET_DIR.get(side)
    ribbon_flip = _minutes_since_match(subset, 3, target_dir, entry_et)
    htf_match = _minutes_since_match(subset, 4, target_dir, entry_et)

    or_info = _opening_range(ticks_for_date, entry_et)
    or_ext = _or_extension(or_info, spy_at_entry, side)

    vix_dir_info = _vix_dir(subset, entry_et, vix_at_entry)

    chase = None
    if range_position is not None and side in ("C", "P"):
        chase = mels.classify_chase({"range_position": range_position, "side": side}, CHASE_HI, CHASE_LO)

    trigger_level = trigger_levels.get((arm, sym, t["entry_ts_utc"]))
    confirm = _confirm_bars(subset, side, trigger_level)
    zone = _zone_distance(spy_at_entry, trigger_level, side, date)

    return {
        "row_id": f"{arm}::{sym}::{t['entry_ts_utc']}",
        "date": date, "arm": arm, "symbol": sym, "setup": t.get("setup"), "side": side,
        "outcome": t.get("outcome"), "realized_pnl": t.get("realized_pnl"), "qty": t.get("qty"),
        "hold_minutes": t.get("hold_minutes"),
        "entry_ts_utc": t["entry_ts_utc"], "entry_et": entry_et.isoformat(),
        "range_position": range_position, "session_hi": session_hi, "session_lo": session_lo,
        "spy_at_entry": spy_at_entry, "n_ticks_used_for_range": n_ticks_used,
        "chase_extreme_0.75_0.25": chase,
        "vix_at_entry": vix_at_entry, "ribbon_at_entry": ribbon_at_entry, "htf_15m_at_entry": htf15m_at_entry,
        "minutes_since_ribbon_flip": ribbon_flip["minutes_since_flip"],
        "ribbon_flip_left_censored": ribbon_flip["left_censored"],
        "ribbon_flip_note": ribbon_flip["note"],
        "minutes_since_htf15m_match": htf_match["minutes_since_flip"],
        "htf15m_match_left_censored": htf_match["left_censored"],
        "htf15m_match_note": htf_match["note"],
        "or_high": or_info["or_high"], "or_low": or_info["or_low"], "or_range": or_info["or_range"],
        "or_window_complete": or_info["or_window_complete"],
        "or_extension_dollars": or_ext["dollars"], "or_extension_multiples": or_ext["multiples"],
        "vix_dir": vix_dir_info["vix_dir"], "vix_dir_delta": vix_dir_info["vix_delta"],
        "vix_dir_note": vix_dir_info["note"],
        "trigger_level": trigger_level,
        "confirm_bars": confirm["confirm_bars"],
        "confirm_bars_n_bars_in_prefix": confirm["n_bars_in_prefix"],
        "confirm_bars_note": confirm["note"],
        "zone_distance": zone["zone_distance"], "zone_width": zone["zone_width"],
        "zone_width_source": zone["zone_width_source"],
        "zone_width_defaulted": zone["zone_width_defaulted"],
        "zone_width_reason": zone["zone_width_reason"],
        "in_sample": date <= BACKFILL_CUTOFF,
    }


# ------------------------------------------------------------------------------------------
# summary -- n per setup, chase-vs-rest bootstrap CI, tercile/categorical co-signal splits
# ------------------------------------------------------------------------------------------
def _bucket(rows: list[dict]) -> dict:
    n = len(rows)
    pnls = [r["realized_pnl"] for r in rows if r.get("realized_pnl") is not None]
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    gains = sum(p for p in pnls if p > 0)
    loss_sum = -sum(p for p in pnls if p < 0)
    if loss_sum > 0:
        pf = round(gains / loss_sum, 3)
    else:
        pf = None if gains == 0 else float("inf")
    return {"n": n, "total_pnl": round(total, 2), "mean_pnl": round(total / n, 2) if n else None,
            "wr": round(wins / n, 4) if n else None, "pf": pf, "winners": wins, "losers": losses}


def _diff_ci_or_none(chase_rows: list[dict], rest_rows: list[dict]):
    if len(chase_rows) < MIN_CELL_N_FOR_CI or len(rest_rows) < MIN_CELL_N_FOR_CI:
        return None, f"n<{MIN_CELL_N_FOR_CI} in one or both buckets -- CI not computed"
    diff, dlo, dhi = mels.bootstrap_diff_ci(
        [r["realized_pnl"] for r in chase_rows], [r["realized_pnl"] for r in rest_rows])
    return [round(diff, 2), round(dlo, 2), round(dhi, 2)], None


def _chase_rest_cell(rows: list[dict]) -> dict:
    chase_rows = [r for r in rows if r.get("chase_extreme_0.75_0.25") is True]
    rest_rows = [r for r in rows if r.get("chase_extreme_0.75_0.25") is False]
    ci, ci_note = _diff_ci_or_none(chase_rows, rest_rows)
    out = {"n": len(rows), "chase": _bucket(chase_rows), "rest": _bucket(rest_rows),
           "mean_diff_chase_minus_rest_ci95": ci}
    if ci_note:
        out["ci_note"] = ci_note
    return out


def _tercile_edges(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 2 * MIN_CELL_N_FOR_CI + 2:   # need real spread for 3 non-trivial buckets
        return None
    lo_edge = float(np.percentile(values, 100.0 / 3.0))
    hi_edge = float(np.percentile(values, 200.0 / 3.0))
    if lo_edge >= hi_edge:
        return None
    return round(lo_edge, 4), round(hi_edge, 4)


def stratify_by_tercile(rows: list[dict], key: str) -> dict:
    vals = [r[key] for r in rows if r.get(key) is not None]
    edges = _tercile_edges(vals)
    buckets: dict[str, list[dict]] = {"low": [], "mid": [], "high": [], "null": []}
    for r in rows:
        v = r.get(key)
        if v is None or edges is None:
            buckets["null"].append(r)
            continue
        lo_e, hi_e = edges
        buckets["low" if v <= lo_e else ("mid" if v <= hi_e else "high")].append(r)
    return {"tercile_edges": edges, "buckets": {name: _chase_rest_cell(rs) for name, rs in buckets.items()}}


def stratify_by_category(rows: list[dict], key: str, categories: list[str]) -> dict:
    out = {}
    for cat in categories:
        out[cat] = _chase_rest_cell([r for r in rows if r.get(key) == cat])
    out["null"] = _chase_rest_cell([r for r in rows if r.get(key) is None])
    return out


def _confirm_bars_cell(rows: list[dict]) -> dict:
    """(B4) Descriptive confirm_bars==0 vs >=1 split with bootstrap CI -- the SAME shape as
    _chase_rest_cell, reused for the summary's per-setup + big-day disclosures. Rows with
    confirm_bars=None (no trigger_level) are counted but excluded from both cells, never
    dropped silently."""
    zero_rows = [r for r in rows if r.get("confirm_bars") == 0]
    ge1_rows = [r for r in rows if isinstance(r.get("confirm_bars"), int) and r["confirm_bars"] >= 1]
    n_missing = sum(1 for r in rows if r.get("confirm_bars") is None)
    ci, ci_note = _diff_ci_or_none(zero_rows, ge1_rows)
    out = {"n": len(rows), "n_missing_confirm_bars": n_missing,
           "zero": _bucket(zero_rows), "ge1": _bucket(ge1_rows),
           "mean_diff_zero_minus_ge1_ci95": ci}
    if ci_note:
        out["ci_note"] = ci_note
    return out


def _confirm_bars_big_days(usable: list[dict]) -> dict:
    """(B4) Per this task's STANDARDS clause: disclose the confirm_bars==0 vs >=1 split on
    each of the four named winning days, across the whole usable population (all setups) --
    a proposed rule that looks good in aggregate but is carried by one of these four days, or
    that flips sign on one of them, must be visible here, not just in the aggregate cells."""
    return {d: _confirm_bars_cell([r for r in usable if r["date"] == d]) for d in BIG_WINNER_DAYS}


def _prereg_cut_diagnostic(setup_rows: list[dict]) -> dict:
    """Diagnostic mirror of the ONE frozen prereg test (prereg-entry-location-trend-
    2026-09-03.md section 5): within the chase bucket of BULLISH_RECLAIM_RIDE_THE_RIBBON,
    split by minutes_since_ribbon_flip at the prereg's own named bands (<=15min = fresh
    breakout hypothesis, >45min = exhaustion-chase hypothesis, 15-45min = gray zone, excluded
    from the primary comparison). This is NOT the prereg's official read -- it is a
    descriptive preview so the frozen cut's shape is visible every night, exactly like
    prereg_readiness names the distance to the n_chase floor. The prereg file itself is the
    only authority on when/whether this becomes a verdict."""
    chase_rows = [r for r in setup_rows if r.get("chase_extreme_0.75_0.25") is True]
    fresh, gray, stale, unavailable = [], [], [], []
    for r in chase_rows:
        m = r.get("minutes_since_ribbon_flip")
        if m is None:
            unavailable.append(r)
        elif m <= 15:
            fresh.append(r)
        elif m > 45:
            stale.append(r)
        else:
            gray.append(r)
    ci, ci_note = _diff_ci_or_none(fresh, stale)
    out = {
        "n_chase_total": len(chase_rows),
        "fresh_leq_15min": _bucket(fresh),
        "gray_15_45min_excluded_from_primary_comparison": _bucket(gray),
        "stale_gt_45min": _bucket(stale),
        "ribbon_flip_unavailable_or_not_matching_direction": _bucket(unavailable),
        "mean_diff_fresh_minus_stale_ci95": ci,
        "note": ("Diagnostic preview of prereg-entry-location-trend-2026-09-03.md section 5's "
                 "frozen cut. NOT the prereg's official verdict -- that requires a dedicated "
                 "future read against the frozen decision rule, never this nightly summary."),
    }
    if ci_note:
        out["ci_note"] = ci_note
    return out


def _prereg_cut_diagnostic_confirm_bars(setup_rows: list[dict]) -> dict:
    """(B4) Diagnostic mirror of the SECOND frozen prereg test (prereg-entry-location-trend-
    2026-09-03.md section 9): within the chase bucket of BULLISH_RECLAIM_RIDE_THE_RIBBON,
    split by confirm_bars==0 (entered on the very first closed bar to cross the trigger) vs
    confirm_bars>=1 (price had already sat beyond the trigger for at least one more closed bar
    before this entry fired). This is NOT the prereg's official read -- it is a descriptive
    preview so the frozen cut's shape is visible every night, exactly like
    prereg_cut_diagnostic previews section 1-4's cut. The prereg file itself is the only
    authority on when/whether this becomes a verdict."""
    chase_rows = [r for r in setup_rows if r.get("chase_extreme_0.75_0.25") is True]
    zero = [r for r in chase_rows if r.get("confirm_bars") == 0]
    ge1 = [r for r in chase_rows if isinstance(r.get("confirm_bars"), int) and r["confirm_bars"] >= 1]
    unavailable = [r for r in chase_rows if r.get("confirm_bars") is None]
    ci, ci_note = _diff_ci_or_none(zero, ge1)
    out = {
        "n_chase_total": len(chase_rows),
        "confirm_bars_zero": _bucket(zero),
        "confirm_bars_ge1": _bucket(ge1),
        "confirm_bars_unavailable": _bucket(unavailable),
        "mean_diff_zero_minus_ge1_ci95": ci,
        "note": ("Diagnostic preview of prereg-entry-location-trend-2026-09-03.md section 9's "
                 "frozen cut. NOT the prereg's official verdict -- that requires a dedicated "
                 "future read against the frozen decision rule, never this nightly summary."),
    }
    if ci_note:
        out["ci_note"] = ci_note
    return out


def build_summary(all_rows: list[dict]) -> dict:
    usable = [r for r in all_rows if r.get("range_position") is not None and r.get("side") in ("C", "P")]
    setups = sorted({r.get("setup") for r in usable}, key=lambda s: (s is None, s or ""))

    by_setup = {}
    for setup in setups:
        key = setup or "(unattributed)"
        srows = [r for r in usable if r.get("setup") == setup]
        entry = _chase_rest_cell(srows)
        entry["by_cosignal"] = {
            "minutes_since_ribbon_flip": stratify_by_tercile(srows, "minutes_since_ribbon_flip"),
            "minutes_since_htf15m_match": stratify_by_tercile(srows, "minutes_since_htf15m_match"),
            "or_extension_multiples": stratify_by_tercile(srows, "or_extension_multiples"),
            "vix_at_entry": stratify_by_tercile(srows, "vix_at_entry"),
            "vix_dir": stratify_by_category(srows, "vix_dir", ["up", "down", "flat"]),
        }
        entry["confirm_bars_split"] = _confirm_bars_cell(srows)   # B4
        by_setup[key] = entry

    bull_rows = [r for r in usable if r.get("setup") == BULL_PUT_SETUP_FOR_PREREG]
    bull_chase_rows = [r for r in bull_rows if r.get("chase_extreme_0.75_0.25") is True]
    n_bull_chase = len(bull_chase_rows)
    n_bull_confirm_zero = sum(1 for r in bull_chase_rows if r.get("confirm_bars") == 0)
    n_bull_confirm_ge1 = sum(1 for r in bull_chase_rows
                              if isinstance(r.get("confirm_bars"), int) and r["confirm_bars"] >= 1)

    return {
        "generated_at_et": _stamp_now_et(),
        "prereg": PREREG_REL,
        "status": "ARMED",
        "meta": {
            "population": "analysis/pain-ledger/mae-mfe.json trades, ALL dates (full backfill, no cutoff)",
            "n_total_rows": len(all_rows),
            "n_usable_for_range_position": len(usable),
            "n_excluded_no_range_position_or_side": len(all_rows) - len(usable),
            "backfill_in_sample_cutoff": BACKFILL_CUTOFF,
            "chase_definition": ("side=='C' and range_position>=0.75, OR side=='P' and "
                                  "range_position<=0.25 -- byte-identical to "
                                  "money_entry_location_stats.classify_chase, reused via import"),
        },
        "overall": _chase_rest_cell(usable),
        "by_setup": by_setup,
        "confirm_bars_big_days": _confirm_bars_big_days(usable),   # B4, STANDARDS disclosure
        "prereg_cut_diagnostic": _prereg_cut_diagnostic(bull_rows),
        "prereg_readiness": {
            "target_setup": BULL_PUT_SETUP_FOR_PREREG,
            "n_chase_current": n_bull_chase,
            "n_chase_required": PREREG_N_CHASE_FLOOR,
            "ready": n_bull_chase >= PREREG_N_CHASE_FLOOR,
            "note": ("Reaching this floor is permission to READ the prereg's frozen decision "
                     "rule (section 4), never to ship anything -- see " + PREREG_REL +
                     ". Config freeze through 2026-10-30 blocks any live change regardless."),
        },
        "prereg_cut_diagnostic_confirm_bars": _prereg_cut_diagnostic_confirm_bars(bull_rows),  # B4
        "prereg_readiness_confirm_bars": {   # B4, prereg section 9 (SECOND frozen test)
            "target_setup": BULL_PUT_SETUP_FOR_PREREG,
            "n_confirm_bars_zero_current": n_bull_confirm_zero,
            "n_confirm_bars_ge1_current": n_bull_confirm_ge1,
            "n_required_per_cell": CONFIRM_BARS_N_FLOOR,
            "ready": n_bull_confirm_zero >= CONFIRM_BARS_N_FLOOR
            and n_bull_confirm_ge1 >= CONFIRM_BARS_N_FLOOR,
            "note": ("Reaching BOTH per-cell floors is permission to READ the prereg's SECOND "
                     "frozen decision rule (section 9), never to ship anything -- see " +
                     PREREG_REL + ". Config freeze through 2026-10-30 blocks any live change "
                     "regardless."),
        },
    }


# ------------------------------------------------------------------------------------------
def run() -> dict:
    """Nightly entry point. Fail-open by contract, own scheduled task."""
    try:
        if not MAE_MFE.exists():
            raise RuntimeError(f"population source missing: {MAE_MFE}")
        doc = json.loads(MAE_MFE.read_text(encoding="utf-8"))
        trades = doc.get("trades", [])

        ticks_by_date = load_tick_tape(CORE_DECISIONS)
        trigger_levels = load_trigger_levels(ENTRY_QUALITY_LEDGER)   # B4

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        existing = _read_ledger()
        seen_ids = {r.get("row_id") for r in existing}

        appended: list[dict] = []
        skipped: list[dict] = []
        for t in trades:
            row_id = f"{t.get('arm')}::{t.get('symbol')}::{t.get('entry_ts_utc')}"
            if row_id in seen_ids:
                continue
            row = compute_row(t, ticks_by_date, trigger_levels)
            if row is None:
                skipped.append({"row_id": row_id, "reason": "symbol did not match SPY OCC pattern"})
                continue
            appended.append(row)

        if appended:
            with LEDGER.open("a", encoding="utf-8") as fh:
                for r in appended:
                    fh.write(json.dumps(r) + "\n")

        all_rows = existing + appended
        summary = build_summary(all_rows)
        summary["new_this_run"] = len(appended)
        summary["skipped_this_run"] = skipped
        SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return {"n_total_rows": len(all_rows), "new_this_run": len(appended),
                "n_skipped_this_run": len(skipped), "prereg_readiness": summary["prereg_readiness"]}
    except Exception as e:  # noqa: BLE001 -- descriptive side-product, never fatal
        return {"error": f"{type(e).__name__}: {e}"[:300], "prereg": PREREG_REL}


def main() -> int:
    out = run()
    print(json.dumps(out, indent=1)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
