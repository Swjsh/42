"""shelf_bistability_source_fix_2026_08_01.py -- Next-Twelve #7: source-fix A/B for the
shelf-merge bistability that WS3's hysteresis (`refresh_levels_intraday._hysteresis_carry`,
shipped 114a7a6b) papers over at the feed choke-point, not the source.

FROZEN PRE-REG: analysis/recommendations/shelf-bistability-prereg-2026-08-01.md, committed
07697c7d BEFORE this file existed (et_clock 2026-08-01 14:23:21 Saturday EDT). This runner
implements the prereg faithfully; every deviation is disclosed in the output under
"deviations".

MECHANISM UNDER TEST: daily_context._find_shelf_candidates / _merge_shelf_candidates re-derive
shelf zones from scratch every 5-min refresh with today's still-forming daily bar as both a
candidate seed and a touch-counter -- ordinary intraday noise in the forming bar's running
H/L/C can flip which near-tied overlapping candidate the greedy merge picks for a region,
renaming the written level. Four arms compared: BASELINE (current HEAD, unmodified),
ARM_A (incumbent-stable literal tie-break in the merge), ARM_B (exclude the forming bar from
shelf discovery), ARM_AB (both). daily_context.py and refresh_levels_intraday.py are imported
READ-ONLY throughout this runner -- nothing is edited here; a ship decision (if any) is a
SEPARATE, later, minimal, guarded edit.

ANALYSIS ONLY: no live config/param/gate/order touched. Real OPRA only; exclusions counted,
never synthetic. Does not touch refresh_levels_intraday.py's hysteresis or params/exit files
(the hysteresis function is imported and RUN unmodified, never edited).

Run:  backtest/.venv/Scripts/python.exe backtest/tools/shelf_bistability_source_fix_2026_08_01.py
      [--smoke]      last 10 sessions only, scratch outputs
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]              # backtest/
ROOT = REPO.parent                                        # repo root
for _p in (str(ROOT), str(REPO), str(ROOT / "setup" / "scripts"),
           str(ROOT / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

# read-only imports of the REAL production modules under study (loaded by explicit file path
# so this runner never depends on package layout / sys.path collisions with other tools).


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dcx = _load_module("daily_context", ROOT / "setup" / "scripts" / "daily_context.py")
rli = _load_module("refresh_levels_intraday", ROOT / "setup" / "scripts" / "refresh_levels_intraday.py")

from lib.et_frame import parse_timestamp_et  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.filters import detect_level_reclaim  # noqa: E402
import strategies as fleet_strategies  # noqa: E402

DATA = REPO / "data"
OLD_SPY = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
NEW_SPY = DATA / "spy_5m_2026-05-19_2026-07-31.csv"
OPT_DIR = DATA / "options"
DAILY_CACHE = DATA / "spy_daily_bars_real_2024-10-01_2026-08-01.json"

FULL_START = dt.date(2025, 1, 2)
FULL_END = dt.date(2026, 7, 31)
EXPECTED_DAYS = 391
HALF_DAYS = {dt.date(2025, 7, 3), dt.date(2025, 11, 28), dt.date(2025, 12, 24)}

SHELF_UPSERT_BAND = 20.0          # refresh_levels_intraday.SHELF_UPSERT_BAND parity
SHELF_LOOKBACK_CAL_DAYS = 60      # daily_context.LOOKBACK_DAYS parity
HYSTERESIS_MATCH_EPS = rli.HYSTERESIS_MATCH_EPS
HYSTERESIS_MISS_N = rli.HYSTERESIS_MISS_N

QTY = 3
PREMIUM_FLOOR = 0.30
TIME_STOP_ET = dt.time(15, 40)
ENTRY_NOT_BEFORE = dt.time(9, 35)
BLACKOUT = (dt.time(15, 0), dt.time(16, 0))

ARMS = ("BASELINE", "ARM_A", "ARM_B", "ARM_AB")

OUT_JSON = ROOT / "analysis" / "recommendations" / "shelf-bistability-2026-08-01.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "shelf-bistability-2026-08-01.md"
SMOKE_JSON = ROOT / "analysis" / "recommendations" / "shelf-bistability-2026-08-01.smoke.json"


def log(msg: str) -> None:
    print(f"[shelf-bistab] {msg}", flush=True)


# ============================================================== data loading (real only)

def fetch_daily_bars_real() -> list[dict]:
    """Real SIP daily bars, same endpoint/params as daily_context._fetch_daily_bars. Cached
    (gitignored backtest/data/) once fetched this session; re-fetched only if the cache file
    is absent."""
    if DAILY_CACHE.exists():
        return json.loads(DAILY_CACHE.read_text(encoding="utf-8"))
    log("fetching real daily bars via Alpaca REST (cache miss)...")
    m = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    env = m["mcpServers"]["alpaca"]["env"]
    key, sec = env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]
    url = ("https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day"
           "&start=2024-10-01T00:00:00Z&limit=10000&feed=sip&adjustment=raw&sort=asc")
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read()).get("bars", [])
    out = [{"date": str(b["t"])[:10], "o": float(b["o"]), "h": float(b["h"]),
            "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v") or 0)} for b in raw]
    DATA.mkdir(parents=True, exist_ok=True)
    DAILY_CACHE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _load_csv_et2(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp_et"] = parse_timestamp_et(df["timestamp_et"], frame="et-v2")
    return df


def load_merged_spy() -> pd.DataFrame:
    old = _load_csv_et2(OLD_SPY)
    new = _load_csv_et2(NEW_SPY)
    tail = new[new["timestamp_et"].dt.date > dt.date(2026, 7, 22)]
    out = (pd.concat([old, tail], ignore_index=True)
             .sort_values("timestamp_et").reset_index(drop=True))
    return out.drop_duplicates(subset="timestamp_et").reset_index(drop=True)


def build_rth(spy_df: pd.DataFrame) -> pd.DataFrame:
    mask = ((spy_df["timestamp_et"].dt.time >= dt.time(9, 30))
            & (spy_df["timestamp_et"].dt.time < dt.time(16, 0)))
    return spy_df.loc[mask].reset_index(drop=True)


_OPT_CACHE: dict[str, Optional[pd.DataFrame]] = {}


def load_opt_et2(symbol: str) -> Optional[pd.DataFrame]:
    if symbol in _OPT_CACHE:
        return _OPT_CACHE[symbol]
    path = OPT_DIR / f"{symbol}.csv"
    if not path.exists():
        _OPT_CACHE[symbol] = None
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = parse_timestamp_et(df["timestamp_et"], frame="et-v2")
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    _OPT_CACHE[symbol] = df
    return df


def option_symbol(day: dt.date, strike: int) -> str:
    return f"SPY{day.strftime('%y%m%d')}C{strike * 1000:08d}"


# ============================================================== fire schedule (WS3 parity)

def _fire_schedule() -> list[dt.time]:
    out = []
    for h in range(9, 16):
        for m in range(0, 60, 5):
            total = h * 60 + m + 3
            hm = f"{total // 60:02d}:{total % 60:02d}"
            if hm < "09:33" or hm > "15:53":
                continue
            out.append(dt.time(total // 60, total % 60))
    return out


FIRES = _fire_schedule()
assert len(FIRES) == 77, f"expected 77 fires (WS3 parity), got {len(FIRES)}"


# ============================================================== merge arms (pure functions)

def merge_incumbent_stable(candidates: list[dict], incumbent: list[tuple]) -> list[dict]:
    """ARM_A: literal-tie-break variant of daily_context._merge_shelf_candidates -- on an
    EXACT tie in touch count, the candidate that IS a prior-fire kept band (same identity,
    not merely a region overlap -- overlap is too loose in a contested region where EVERY
    nearby candidate overlaps every other by definition) sorts first; otherwise identical
    stable order to the unmodified function. Identity = mid within HYSTERESIS_MATCH_EPS
    ($0.10), reusing the SAME constant refresh_levels_intraday's hysteresis already uses for
    "same level" -- zero new magic numbers.

    BUG FOUND BY GUARD (test_arm_a_resolves_the_named_tie_toward_incumbent, this session): an
    earlier draft used raw band-OVERLAP to detect the incumbent, which spuriously flagged
    MULTIPLE mutually-overlapping candidates in a contested region as "incumbent"
    simultaneously, defeating the tie-break entirely (it degenerated back to the plain
    band_low order). Fixed before the reported study run; see prereg/report for the
    before/after numbers."""
    if not candidates:
        return []
    incumbent = incumbent or []

    def _is_incumbent(c: dict) -> bool:
        c_mid = (c["band_low"] + c["band_high"]) / 2
        return any(abs(c_mid - (lo + hi) / 2) <= HYSTERESIS_MATCH_EPS for lo, hi in incumbent)

    ranked = sorted(candidates,
                     key=lambda c: (-c["touches"], 0 if _is_incumbent(c) else 1, c["band_low"]))
    kept: list[dict] = []
    for c in ranked:
        if any(not (c["band_high"] < k["band_low"] or c["band_low"] > k["band_high"]) for k in kept):
            continue
        kept.append(c)
    return sorted(kept, key=lambda c: c["band_low"])


def _bands(kept: list[dict]) -> list[tuple]:
    return [(m["band_low"], m["band_high"]) for m in kept]


# ============================================================== hysteresis plumbing (reused)

def _to_hyst_dict(shelf: dict, day_iso: str, now_iso: str) -> dict:
    lo, hi = shelf["band_low"], shelf["band_high"]
    mid = round((lo + hi) / 2, 2)
    return {"price": mid, "band_low": lo, "band_high": hi, "touches": shelf["touches"],
            "span_sessions": shelf["span_sessions"], "tier": "Active",
            "label": f"SHELF_{lo:.2f}_{hi:.2f}_{day_iso}",
            "source": "daily_context_shelf",
            "expires_at": f"{day_iso}T16:00:00-04:00"}


def near_spot(kept: list[dict], spot: float, band: float = SHELF_UPSERT_BAND) -> list[dict]:
    return [m for m in kept if abs((m["band_low"] + m["band_high"]) / 2 - spot) <= band]


# ============================================================== per-day simulation

def trailing_bars(daily_sorted: list[dict], day: dt.date) -> list[dict]:
    start = (dt.datetime.combine(day, dt.time(0, 0)) - dt.timedelta(days=SHELF_LOOKBACK_CAL_DAYS)).date().isoformat()
    diso = day.isoformat()
    return [b for b in daily_sorted if start <= b["date"] < diso]


def forming_bar_asof(day_rth: pd.DataFrame, day: dt.date, t: dt.time) -> Optional[dict]:
    sub = day_rth[day_rth["timestamp_et"].dt.time <= t]
    if sub.empty:
        return None
    return {"date": day.isoformat(), "o": float(sub["open"].iloc[0]), "h": float(sub["high"].max()),
            "l": float(sub["low"].min()), "c": float(sub["close"].iloc[-1]),
            "v": float(sub["volume"].sum())}


def simulate_population(days: list[dt.date], daily_sorted: list[dict],
                        day_frames: dict[str, pd.DataFrame]) -> dict:
    """Full 391-day x 77-fire x 4-arm simulation. Returns per-day per-arm per-fire
    (spot, kept-shelf-list) sequences (RAW, pre-hysteresis). ARM_B/ARM_AB candidates are
    invariant within a day (forming bar excluded) -- computed ONCE per day, a valid (not
    approximate) speedup since the input literally does not change intraday."""
    incumbent_A: list[tuple] = []      # continuous across the WHOLE population, no day reset
    incumbent_AB: list[tuple] = []
    out: dict[str, dict] = {}
    t0 = time.time()
    for k, day in enumerate(days):
        diso = day.isoformat()
        trail = trailing_bars(daily_sorted, day)
        day_rth = day_frames.get(diso)
        # ---- ARM_B / ARM_AB: candidates fixed for the whole day (forming bar excluded) ----
        cands_B = dcx._find_shelf_candidates(trail)
        merged_B_day = dcx._merge_shelf_candidates(cands_B)
        merged_AB_day = merge_incumbent_stable(cands_B, incumbent_AB)
        incumbent_AB = _bands(merged_AB_day)

        fires_out = {arm: [] for arm in ARMS}
        for t in FIRES:
            fb = forming_bar_asof(day_rth, day, t) if day_rth is not None else None
            bars_today = trail + ([fb] if fb else [])
            spot = fb["c"] if fb else (trail[-1]["c"] if trail else None)
            cands = dcx._find_shelf_candidates(bars_today)
            merged_baseline = dcx._merge_shelf_candidates(cands)
            merged_A = merge_incumbent_stable(cands, incumbent_A)
            incumbent_A = _bands(merged_A)

            fires_out["BASELINE"].append((spot, merged_baseline))
            fires_out["ARM_A"].append((spot, merged_A))
            fires_out["ARM_B"].append((spot, merged_B_day))
            fires_out["ARM_AB"].append((spot, merged_AB_day))
        out[diso] = fires_out
        if (k + 1) % 50 == 0:
            log(f"  simulated {k + 1}/{len(days)} days ({time.time() - t0:.1f}s elapsed)")
    log(f"simulate_population done in {time.time() - t0:.1f}s")
    return out


# ============================================================== metric (a)/(b): flicker + fidelity

def apply_hysteresis_sequence(day_order: list[str], per_day: dict, arm: str) -> dict[str, list[list[dict]]]:
    """Drives the REAL unmodified refresh_levels_intraday._hysteresis_carry across the full
    population in fire order for one arm, continuous across day boundaries (matches
    production: key-levels.json is never wiped overnight; the function's own expires_at
    check is what retires stale-dated levels). Returns {day: [written_fresh_list x 77]}."""
    prior: list[dict] = []
    out: dict[str, list[list[dict]]] = {}
    for diso in day_order:
        fires = per_day[diso][arm]
        written_day = []
        for spot, kept in fires:
            fresh_near = near_spot(kept, spot) if spot is not None else []
            fresh_dicts = [_to_hyst_dict(m, diso, f"{diso}T12:00:00-04:00") for m in fresh_near]
            held = rli._hysteresis_carry(prior, fresh_dicts, diso, f"{diso}T12:00:00-04:00")
            written = fresh_dicts + held
            written_day.append(written)
            prior = written
        out[diso] = written_day
    return out


def mid_set(levels: list[dict]) -> frozenset:
    """Written (post-hysteresis) hyst-dicts carry 'price'."""
    return frozenset(round(float(lv["price"]), 2) for lv in levels)


def raw_mid_set(kept: list[dict]) -> frozenset:
    """Raw merge output carries band_low/band_high, not 'price' -- mid computed directly."""
    return frozenset(round((m["band_low"] + m["band_high"]) / 2, 2) for m in kept)


def flip_count(seq: list[frozenset]) -> int:
    return sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])


def compute_flicker_and_fidelity(day_order: list[str], per_day: dict,
                                 written: dict[str, dict[str, list]]) -> dict:
    """metric (a) RAW + WRITTEN flip counts per arm, per day; metric (b) EOD + full-day-union
    fidelity vs BASELINE per arm, per day."""
    per_arm_day = {arm: {} for arm in ARMS}
    for diso in day_order:
        for arm in ARMS:
            raw_seq = [raw_mid_set(near_spot(kept, spot)) if spot is not None else frozenset()
                      for spot, kept in per_day[diso][arm]]
            written_seq = [mid_set(w) for w in written[arm][diso]]
            per_arm_day[arm][diso] = {
                "raw_flips": flip_count(raw_seq),
                "written_flips": flip_count(written_seq),
                "raw_eod": sorted(raw_seq[-1]) if raw_seq else [],
                "written_eod": sorted(written_seq[-1]) if written_seq else [],
                "raw_union": sorted(frozenset().union(*raw_seq)) if raw_seq else [],
            }
    # fidelity vs BASELINE (written EOD + full-day union), per arm
    fidelity = {arm: {} for arm in ARMS if arm != "BASELINE"}
    for diso in day_order:
        base_eod = frozenset(per_arm_day["BASELINE"][diso]["written_eod"])
        base_union = frozenset(per_arm_day["BASELINE"][diso]["raw_union"])
        for arm in fidelity:
            arm_eod = frozenset(per_arm_day[arm][diso]["written_eod"])
            arm_union = frozenset(per_arm_day[arm][diso]["raw_union"])
            fidelity[arm][diso] = {
                "eod_only_in_arm": sorted(arm_eod - base_eod),
                "eod_only_in_baseline": sorted(base_eod - arm_eod),
                "union_only_in_arm": sorted(arm_union - base_union),
                "union_only_in_baseline": sorted(base_union - arm_union),
            }
    return per_arm_day, fidelity


# ============================================================== metric (c): entry impact

def governing_fire_idx(bar_start: dt.time) -> Optional[int]:
    idx = None
    for i, f in enumerate(FIRES):
        if f <= bar_start:
            idx = i
        else:
            break
    return idx


class TradeResolver:
    def __init__(self, shape: dict, spy_day_frames: dict[str, pd.DataFrame]):
        self.shape = shape
        self.spy_day_frames = spy_day_frames
        self.cache: dict[tuple, dict] = {}

    def resolve(self, day: str, entry_tick: pd.Timestamp, strike: int, zone_floor: float) -> dict:
        key = (day, entry_tick, strike, round(zone_floor, 2))
        if key in self.cache:
            return self.cache[key]
        symbol = option_symbol(dt.date.fromisoformat(day), strike)
        out = {"symbol": symbol, "strike": strike}
        opt_df = load_opt_et2(symbol)
        if opt_df is None or opt_df.empty:
            out["status"] = "EXCLUDED_NO_OPRA"
            self.cache[key] = out
            return out
        after = opt_df[opt_df["timestamp_et"] >= entry_tick]
        if after.empty:
            out["status"] = "EXCLUDED_NO_PRINT"
            self.cache[key] = out
            return out
        fill = after.iloc[0]
        entry_premium = float(fill["open"])
        if entry_premium <= 0:
            out["status"] = "EXCLUDED_ZERO_PRINT"
            self.cache[key] = out
            return out
        if entry_premium < PREMIUM_FLOOR:
            out["status"] = "EXCLUDED_FLOOR"
            self.cache[key] = out
            return out
        fill_ts = pd.Timestamp(fill["timestamp_et"])
        spy_day = self.spy_day_frames[day]
        r = walk_exit_manager(
            symbol=symbol, side="C", entry_time_et=fill_ts.to_pydatetime(),
            entry_premium=entry_premium, qty=QTY, exit_shape=self.shape,
            structure_stop_enabled=True, trigger_level=float(zone_floor),
            strategy="ribbon_ride", time_stop_et=TIME_STOP_ET,
            opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=spy_day)
        if r.exit_time_et is None:
            out["status"] = "EXCLUDED_NO_WALK"
            self.cache[key] = out
            return out
        out.update(status="FILLED", entry_premium=round(entry_premium, 4),
                   fill_ts=fill_ts.isoformat(), pnl=round(r.dollar_pnl, 2),
                   exit_reason=r.exit_reason, exit_time=r.exit_time_et.isoformat())
        self.cache[key] = out
        return out


def scan_entries_for_arm(day: str, day_df: pd.DataFrame, written_day: list[list[dict]]) -> list[dict]:
    """Bar-by-bar detect_level_reclaim scan (F1 time gate only, disclosed scope) against the
    WRITTEN near-spot shelf anchors active as-of each bar (most recent fire at-or-before the
    bar's start -- mirrors the engine reading whatever key-levels.json currently holds)."""
    sigs = []
    for i in range(len(day_df)):
        bar = day_df.iloc[i]
        ts = bar["timestamp_et"]
        t = ts.time()
        if t < ENTRY_NOT_BEFORE or (BLACKOUT[0] <= t < BLACKOUT[1]):
            continue
        fidx = governing_fire_idx(t)
        if fidx is None:
            continue
        active = written_day[fidx]
        if not active:
            continue
        by_price = {round(float(lv["price"]), 2): lv for lv in active}
        mids = list(by_price.keys())
        lvl = detect_level_reclaim(bar, mids)
        if lvl is None:
            continue
        anchor = by_price[round(lvl, 2)]
        entry_tick = ts + pd.Timedelta(minutes=5)
        sigs.append({"day": day, "bar_i": i, "bar_ts": ts.isoformat(),
                     "entry_tick": entry_tick.isoformat(), "level": float(lvl),
                     "zone_floor": float(anchor["band_low"]), "trig_close": float(bar["close"])})
    return sigs


def run_entry_cell(sigs: list[dict], resolver: TradeResolver) -> dict:
    """Occupancy-aware admission (one position at a time, busy-until = this trade's own exit
    time -- single-lane variant of shelf_hold_reclaim_study.py's run_entry_cell)."""
    taken = []
    excl = {"EXCLUDED_NO_OPRA": 0, "EXCLUDED_NO_PRINT": 0, "EXCLUDED_ZERO_PRINT": 0,
            "EXCLUDED_FLOOR": 0, "EXCLUDED_NO_WALK": 0}
    busy_until = None
    cur_day = None
    for s in sigs:
        if s["day"] != cur_day:
            cur_day = s["day"]
            busy_until = None
        entry_tick = pd.Timestamp(s["entry_tick"])
        if busy_until is not None and not (entry_tick > busy_until):
            continue
        strike = int(round(s["trig_close"]))
        res = resolver.resolve(s["day"], entry_tick, strike, s["zone_floor"])
        if res["status"] != "FILLED":
            excl[res["status"]] += 1
            continue
        busy_until = pd.Timestamp(res["exit_time"])
        taken.append({**s, "strike": strike, "entry_premium": res["entry_premium"],
                      "pnl": res["pnl"], "exit_reason": res["exit_reason"]})
    return {"taken": taken, "exclusions": excl}


def diff_entries(base_sigs: list[dict], arm_sigs: list[dict]) -> dict:
    base_by_bar = {(s["day"], s["bar_i"]): s for s in base_sigs}
    arm_by_bar = {(s["day"], s["bar_i"]): s for s in arm_sigs}
    gained = [arm_by_bar[k] for k in arm_by_bar if k not in base_by_bar]
    lost = [base_by_bar[k] for k in base_by_bar if k not in arm_by_bar]
    moved = [{"day": k[0], "bar_i": k[1], "base_level": base_by_bar[k]["level"],
             "arm_level": arm_by_bar[k]["level"]}
            for k in (set(base_by_bar) & set(arm_by_bar))
            if abs(base_by_bar[k]["level"] - arm_by_bar[k]["level"]) > HYSTERESIS_MATCH_EPS]
    return {"gained": len(gained), "lost": len(lost), "moved": len(moved)}


# ============================================================== main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    control_shape = fleet_strategies.RIBBON_RIDE.exit.to_dict()
    assert control_shape == fleet_strategies.by_name("ribbon_ride").exit.to_dict()
    log(f"CONTROL shape (registry byte-identical): {json.dumps(control_shape)}")

    log("loading real daily bars (SIP, cache-or-fetch)...")
    daily_sorted = sorted(fetch_daily_bars_real(), key=lambda b: b["date"])
    log(f"  {len(daily_sorted)} daily bars {daily_sorted[0]['date']}..{daily_sorted[-1]['date']}")

    log("loading SPY merged frame (et-v2)...")
    spy_raw = load_merged_spy()
    spy_rth = build_rth(spy_raw)
    all_days = [d for d in sorted(spy_rth["timestamp_et"].dt.date.unique())
               if FULL_START <= d <= FULL_END and d not in HALF_DAYS]
    log(f"population: {len(all_days)} RTH sessions {all_days[0]}..{all_days[-1]} "
        f"(expected {EXPECTED_DAYS})")
    if len(all_days) != EXPECTED_DAYS:
        log("FATAL: population != the verified 391 -- aborting before any cell is computed")
        return 1

    study_days = all_days[-10:] if args.smoke else all_days
    recent_start = all_days[-25].isoformat()
    day_order = [d.isoformat() for d in study_days]

    day_frames: dict[str, pd.DataFrame] = {}
    for d, grp in spy_rth.groupby(spy_rth["timestamp_et"].dt.date, sort=True):
        if d in set(study_days):
            day_frames[d.isoformat()] = grp.reset_index(drop=True)

    log(f"simulating {len(study_days)} days x {len(FIRES)} fires x {len(ARMS)} arms "
        f"(smoke={args.smoke})...")
    per_day = simulate_population(study_days, daily_sorted, day_frames)

    log("applying REAL unmodified _hysteresis_carry per arm (continuous fire order)...")
    written = {arm: apply_hysteresis_sequence(day_order, per_day, arm) for arm in ARMS}

    log("computing flicker (a) + fidelity (b)...")
    per_arm_day, fidelity = compute_flicker_and_fidelity(day_order, per_day, written)

    def _agg(days_subset: list[str], arm: str, field: str) -> int:
        return sum(per_arm_day[arm][d][field] for d in days_subset)

    recent_days = [d for d in day_order if d >= recent_start]
    summary_a = {}
    for arm in ARMS:
        summary_a[arm] = {
            "raw_flips_total": _agg(day_order, arm, "raw_flips"),
            "written_flips_total": _agg(day_order, arm, "written_flips"),
            "raw_flips_recent25": _agg(recent_days, arm, "raw_flips"),
            "written_flips_recent25": _agg(recent_days, arm, "written_flips"),
            "days_with_written_flip": sum(1 for d in day_order if per_arm_day[arm][d]["written_flips"] > 0),
            "days_with_raw_flip": sum(1 for d in day_order if per_arm_day[arm][d]["raw_flips"] > 0),
        }

    summary_b = {}
    for arm in fidelity:
        eod_div_days = [d for d in day_order if fidelity[arm][d]["eod_only_in_arm"]
                        or fidelity[arm][d]["eod_only_in_baseline"]]
        union_div_days = [d for d in day_order if fidelity[arm][d]["union_only_in_arm"]
                          or fidelity[arm][d]["union_only_in_baseline"]]
        summary_b[arm] = {
            "eod_divergence_days": len(eod_div_days),
            "eod_divergence_day_list": eod_div_days[:50],
            "union_divergence_days": len(union_div_days),
        }

    # ---- interesting-day pruning for metric (c), PROVEN not sampled ----
    interesting = set()
    for d in day_order:
        if per_arm_day["BASELINE"][d]["written_flips"] > 0:
            interesting.add(d)
        for arm in fidelity:
            if fidelity[arm][d]["eod_only_in_arm"] or fidelity[arm][d]["eod_only_in_baseline"]:
                interesting.add(d)
    non_interesting = [d for d in day_order if d not in interesting]
    # PROOF (not assumption): every arm's written fire-by-fire sequence is byte-identical to
    # BASELINE's on every non-interesting day.
    proof_failures = []
    for d in non_interesting:
        base_seq = [mid_set(w) for w in written["BASELINE"][d]]
        for arm in ("ARM_A", "ARM_B", "ARM_AB"):
            arm_seq = [mid_set(w) for w in written[arm][d]]
            if arm_seq != base_seq:
                proof_failures.append({"day": d, "arm": arm})
    if proof_failures:
        log(f"PRUNING PROOF FAILED on {len(proof_failures)} (day,arm) pairs -- "
            f"widening interesting-day set to include them")
        interesting.update(f["day"] for f in proof_failures)
        non_interesting = [d for d in day_order if d not in interesting]
    log(f"interesting days (metric c population): {len(interesting)}/{len(day_order)} "
        f"({len(interesting) / len(day_order):.1%}); pruning proof "
        f"{'CLEAN' if not proof_failures else 'WIDENED'} on the remaining "
        f"{len(non_interesting)} days")

    interesting_days_sorted = sorted(interesting)
    resolver = TradeResolver(control_shape, day_frames)
    entry_sigs = {arm: [] for arm in ARMS}
    for d in interesting_days_sorted:
        day_df = day_frames.get(d)
        if day_df is None or day_df.empty:
            continue
        for arm in ARMS:
            sigs = scan_entries_for_arm(d, day_df, written[arm][d])
            entry_sigs[arm].extend(sigs)
    log(f"raw geometry-C fires on interesting days: "
        f"{ {arm: len(entry_sigs[arm]) for arm in ARMS} }")

    cells = {}
    for arm in ARMS:
        ec = run_entry_cell(entry_sigs[arm], resolver)
        taken = ec["taken"]
        total = round(sum(t["pnl"] for t in taken), 2)
        recent_taken = [t for t in taken if t["day"] >= recent_start]
        cells[arm] = {"n": len(taken), "total_pnl": total, "exclusions": ec["exclusions"],
                      "recent25_n": len(recent_taken),
                      "recent25_total_pnl": round(sum(t["pnl"] for t in recent_taken), 2),
                      "trades": taken}

    diffs = {arm: diff_entries(cells["BASELINE"]["trades"], cells[arm]["trades"])
            for arm in ARMS if arm != "BASELINE"}
    for arm in diffs:
        diffs[arm]["pnl_delta_total"] = round(cells[arm]["total_pnl"] - cells["BASELINE"]["total_pnl"], 2)
        diffs[arm]["pnl_delta_recent25"] = round(
            cells[arm]["recent25_total_pnl"] - cells["BASELINE"]["recent25_total_pnl"], 2)

    # ---- gates ----
    verdicts = {}
    for arm in ("ARM_A", "ARM_B", "ARM_AB"):
        g1 = (summary_a[arm]["written_flips_total"] < summary_a["BASELINE"]["written_flips_total"]
              and summary_a[arm]["written_flips_recent25"] <= summary_a["BASELINE"]["written_flips_recent25"])
        g2 = summary_b[arm]["eod_divergence_days"] == 0
        g3 = diffs[arm]["pnl_delta_total"] >= 0 and diffs[arm]["pnl_delta_recent25"] >= 0
        verdicts[arm] = {
            "g1_flicker_materially_reduced": g1,
            "g2_steady_state_fidelity_preserved": g2,
            "g3_entry_pnl_not_degraded": g3,
            "ships": bool(g1 and g2 and g3),
        }

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": "analysis/recommendations/shelf-bistability-prereg-2026-08-01.md @ 07697c7d",
        "smoke": bool(args.smoke),
        "population": {"n_days": len(study_days), "start": study_days[0].isoformat(),
                       "end": study_days[-1].isoformat(), "recent_25_start": recent_start,
                       "n_fires_per_day": len(FIRES)},
        "control_shape": control_shape,
        "mechanism_reproduction": {
            "flip_example": "2026-07-31 09:43->09:48 ET: forming-bar low $742.79->$741.98 "
                            "(1 bar, -$0.81) flips region winner 742.36(10t) -> "
                            "{741.60(10t),743.25(8t)}",
            "validation_vs_real_5min_cadence_2026-07-31": "63/77 fires match (81.8%)",
        },
        "metric_a_flicker": summary_a,
        "metric_b_fidelity": summary_b,
        "metric_b_fidelity_detail": {arm: fidelity[arm] for arm in fidelity},
        "metric_c_entry_impact": {
            "interesting_days": len(interesting), "non_interesting_days": len(non_interesting),
            "pruning_proof": "CLEAN" if not proof_failures else f"WIDENED ({len(proof_failures)} pairs)",
            "cells": {arm: {k: v for k, v in cells[arm].items() if k != "trades"} for arm in ARMS},
            "diffs_vs_baseline": diffs,
        },
        "verdicts": verdicts,
        "deviations": [
            "metric (c) detector scope: detect_level_reclaim (geometry C) only, F1 time gate "
            "only (no ribbon/VIX/volume filters) -- disclosed in prereg SS4(c), a regression "
            "check vs today's baseline, not a re-validation of shelf_hold_reclaim's edge "
            "(WS5 already NULLed that this same weekend).",
            "hysteresis simulated on the shelf family in isolation (not the full "
            "key-levels.json level book) -- disclosed in prereg SS4(a); _hysteresis_carry "
            "itself is imported and run completely unmodified.",
            "ribbon_tick_df=None in walk_exit_manager (ribbon_flip_back exits cannot fire in "
            "this harness) -- structure_stop/time_stop/premium-based exits are unaffected; "
            "disclosed, matches this study's narrower exit-lane scope (CONTROL only, no "
            "ZONE_RIDE, no ribbon flip-back) relative to WS5's fuller harness.",
        ],
        "runtime_seconds": round(time.time() - t0, 1),
    }
    dest = SMOKE_JSON if args.smoke else OUT_JSON
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log(f"wrote {dest}")
    log(f"metric_a (written flips, full pop): { {a: summary_a[a]['written_flips_total'] for a in ARMS} }")
    log(f"metric_b (EOD divergence days): { {a: summary_b[a]['eod_divergence_days'] for a in summary_b} }")
    log(f"metric_c (pnl delta total): { {a: diffs[a]['pnl_delta_total'] for a in diffs} }")
    log(f"verdicts: { {a: verdicts[a]['ships'] for a in verdicts} }")
    log(f"runtime {out['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
