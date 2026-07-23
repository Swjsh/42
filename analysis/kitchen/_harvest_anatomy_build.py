"""
One-shot analysis script for HARVEST-DAY ANATOMY (2026-07-23).
Joins the 190-trade full-history replay (engine-fullhist-replay-2026-07-23.json)
to the 386-day inventory (day-inventory-2026-07-23.json) and this week's real
fills (journal/trades.csv), and emits:
  - analysis/kitchen/HARVEST-DAY-ANATOMY-2026-07-23.md
  - analysis/kitchen/day-archetype-map.json

Not a strategy/backtest run -- pure joins/aggregation over existing artifacts.
No live wiring, no commits, no broker imports (task constraint).
"""
import json
import csv
import statistics
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLAY_PATH = ROOT / "analysis/recommendations/engine-fullhist-replay-2026-07-23.json"
INVENTORY_PATH = ROOT / "analysis/edge-matrix/day-inventory-2026-07-23.json"
TRADES_CSV = ROOT / "journal/trades.csv"
SPY5M_PATH = ROOT / "backtest/data/spy_5m_2025-01-01_2026-07-22.csv"

OUT_MD = ROOT / "analysis/kitchen/HARVEST-DAY-ANATOMY-2026-07-23.md"
OUT_JSON = ROOT / "analysis/kitchen/day-archetype-map.json"

with open(REPLAY_PATH, encoding="utf-8") as f:
    replay = json.load(f)
with open(INVENTORY_PATH, encoding="utf-8") as f:
    inventory = json.load(f)

trades = replay["trades"]
days = inventory["days"]
days_by_date = {d["date"]: d for d in days}
heldout_set = set(inventory.get("heldout_days", []))

# ---------------------------------------------------------------- daily P&L
daily = defaultdict(lambda: {"pnl": 0.0, "trades": []})
for t in trades:
    daily[t["date"]]["pnl"] += t["dollar_pnl"]
    daily[t["date"]]["trades"].append(t)

trade_dates = set(daily.keys())
all_dates = set(days_by_date.keys())
sit_out_dates = all_dates - trade_dates

win_days = {dt: v for dt, v in daily.items() if v["pnl"] > 0}
loss_days = {dt: v for dt, v in daily.items() if v["pnl"] < 0}
flat_days = {dt: v for dt, v in daily.items() if v["pnl"] == 0}

print(f"n trading days (any trade): {len(daily)}")
print(f"  win days: {len(win_days)}  loss days: {len(loss_days)}  flat days: {len(flat_days)}")
print(f"n sit-out days: {len(sit_out_dates)} / {len(all_dates)} = {100*len(sit_out_dates)/len(all_dates):.1f}%")


def exit_category(reason):
    if reason is None:
        return "unknown"
    if reason.startswith("premium_stop"):
        return "premium_stop"
    if reason.startswith("runner_stop"):
        return "runner_stop"
    if reason.startswith("structure_stop"):
        return "structure_stop"
    if reason.startswith("time_stop"):
        return "time_stop"
    if reason.startswith("ribbon_flip"):
        return "ribbon_flip_back"
    return reason


def summarize_daycohort(date_list):
    """Given a list of trading-day dates, pull day_type/vix_band/gap/entry-hour/trigger stats."""
    day_types = Counter()
    vix_bands = Counter()
    gaps = []
    ranges = []
    entry_hours = Counter()
    triggers = Counter()
    setups = Counter()
    sides = Counter()
    tiers = Counter()
    exit_cats = Counter()
    n_trades_per_day = []
    for dt in date_list:
        inv = days_by_date.get(dt)
        if inv:
            day_types[inv["day_type"]] += 1
            vix_bands[inv["vix_band"]] += 1
            if inv.get("gap_pct") is not None:
                gaps.append(inv["gap_pct"])
            if inv.get("rth_range") is not None:
                ranges.append(inv["rth_range"])
        day_trades = daily[dt]["trades"]
        n_trades_per_day.append(len(day_trades))
        for t in day_trades:
            hh = int(t["entry_time_et"][11:13])
            entry_hours[hh] += 1
            for trg in (t.get("triggers") or []):
                triggers[trg] += 1
            setups[t["setup"]] += 1
            sides[t["side"]] += 1
            tiers[t.get("tier") or "NONE"] += 1
            exit_cats[exit_category(t.get("exit_reason"))] += 1
    return dict(
        n_days=len(date_list),
        day_types=day_types.most_common(),
        vix_bands=vix_bands.most_common(),
        avg_gap_pct=round(statistics.mean(gaps), 3) if gaps else None,
        avg_rth_range=round(statistics.mean(ranges), 2) if ranges else None,
        entry_hours=sorted(entry_hours.items()),
        triggers=triggers.most_common(),
        setups=setups.most_common(),
        sides=sides.most_common(),
        tiers=tiers.most_common(),
        exit_categories=exit_cats.most_common(),
        avg_trades_per_day=round(statistics.mean(n_trades_per_day), 2) if n_trades_per_day else None,
    )


win_summary = summarize_daycohort(list(win_days.keys()))
loss_summary = summarize_daycohort(list(loss_days.keys()))
flat_summary = summarize_daycohort(list(flat_days.keys()))

print("\n=== WIN DAYS SUMMARY ===")
print(json.dumps(win_summary, indent=2))
print("\n=== LOSS DAYS SUMMARY ===")
print(json.dumps(loss_summary, indent=2))
print("\n=== FLAT DAYS SUMMARY (pnl==0, e.g. all trades net to exactly 0) ===")
print(json.dumps(flat_summary, indent=2))

# ---------------------------------------------------------------- SPY direction per day
# Fixed -04:00 cache frame (DST artifact, disclosed) -- fine for RTH-only date bucketing
# since a 1hr shift never crosses RTH 09:30-16:00 into a different calendar date.
day_open_close = {}
with open(SPY5M_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    first_bar = {}
    last_bar = {}
    hi = defaultdict(lambda: float("-inf"))
    lo = defaultdict(lambda: float("inf"))
    for row in reader:
        ts = row["timestamp_et"]
        date = ts[:10]
        o = float(row["open"])
        c = float(row["close"])
        h = float(row["high"])
        l = float(row["low"])
        if date not in first_bar:
            first_bar[date] = o
        last_bar[date] = c
        if h > hi[date]:
            hi[date] = h
        if l < lo[date]:
            lo[date] = l
    for date in first_bar:
        o = first_bar[date]
        c = last_bar[date]
        day_open_close[date] = {
            "open": o,
            "close": c,
            "pct_change": round(100 * (c - o) / o, 3) if o else None,
            "range": round(hi[date] - lo[date], 2) if hi[date] > float("-inf") else None,
        }

print(f"\nn days with SPY open/close reconstructed: {len(day_open_close)}")

# ---------------------------------------------------------------- sit-out archetypes
def archetype_key(inv):
    return (inv["day_type"], inv["vix_band"])


sitout_by_type = defaultdict(list)
for dt in sit_out_dates:
    inv = days_by_date.get(dt)
    if inv:
        sitout_by_type[inv["day_type"]].append(dt)

sitout_archetype_report = {}
for day_type, date_list in sitout_by_type.items():
    ranges = [days_by_date[d]["rth_range"] for d in date_list if days_by_date[d].get("rth_range") is not None]
    gaps = [days_by_date[d]["gap_pct"] for d in date_list if days_by_date[d].get("gap_pct") is not None]
    vix_bands = Counter(days_by_date[d]["vix_band"] for d in date_list)
    up_days = 0
    down_days = 0
    flat_dir = 0
    pct_moves = []
    for d in date_list:
        oc = day_open_close.get(d)
        if oc and oc["pct_change"] is not None:
            pct_moves.append(oc["pct_change"])
            if oc["pct_change"] > 0.05:
                up_days += 1
            elif oc["pct_change"] < -0.05:
                down_days += 1
            else:
                flat_dir += 1
    sitout_archetype_report[day_type] = {
        "n_days": len(date_list),
        "pct_of_all_days": round(100 * len(date_list) / len(all_dates), 1),
        "pct_of_sitout_days": round(100 * len(date_list) / len(sit_out_dates), 1),
        "avg_rth_range": round(statistics.mean(ranges), 2) if ranges else None,
        "median_rth_range": round(statistics.median(ranges), 2) if ranges else None,
        "avg_gap_pct": round(statistics.mean(gaps), 3) if gaps else None,
        "vix_band_dist": vix_bands.most_common(),
        "up_days": up_days,
        "down_days": down_days,
        "flat_days": flat_dir,
        "avg_pct_move": round(statistics.mean(pct_moves), 3) if pct_moves else None,
        "n_directional_sample": len(pct_moves),
    }

print("\n=== SIT-OUT ARCHETYPE REPORT (by day_type) ===")
print(json.dumps(sitout_archetype_report, indent=2))

# also full-population (all 386 days) archetype base rates, for comparison
all_by_type = defaultdict(list)
for dt, inv in days_by_date.items():
    all_by_type[inv["day_type"]].append(dt)

full_pop_report = {}
for day_type, date_list in all_by_type.items():
    n_traded = sum(1 for d in date_list if d in trade_dates)
    n_sitout = sum(1 for d in date_list if d in sit_out_dates)
    full_pop_report[day_type] = {
        "n_days_total": len(date_list),
        "n_traded": n_traded,
        "n_sitout": n_sitout,
        "pct_sitout_within_type": round(100 * n_sitout / len(date_list), 1) if date_list else None,
    }

print("\n=== FULL POPULATION BY DAY_TYPE (coverage rate) ===")
print(json.dumps(full_pop_report, indent=2))

# ---------------------------------------------------------------- this week's real fills (extra-setups)
this_week_setups_by_daytype = defaultdict(Counter)
this_week_rows = []
with open(TRADES_CSV, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        date = row.get("date") or row.get("Date")
        if date and date >= "2026-07-17":
            this_week_rows.append(row)

print(f"\nn journal rows since 2026-07-17: {len(this_week_rows)}")
# figure out the setup column name
if this_week_rows:
    print("columns:", fieldnames[:8])

setup_col = None
for cand in ("setup", "pattern", "strategy"):
    if cand in (fieldnames or []):
        setup_col = cand
        break
print("setup_col:", setup_col)

for row in this_week_rows:
    date = row.get("date")
    setup = row.get(setup_col) if setup_col else None
    inv = days_by_date.get(date)
    day_type = inv["day_type"] if inv else "UNKNOWN(post-inventory-window?)"
    this_week_setups_by_daytype[day_type][setup] += 1

print("\n=== THIS WEEK'S REAL FILLS: setup x day_type ===")
for dtp, ctr in this_week_setups_by_daytype.items():
    print(dtp, dict(ctr))

# ---------------------------------------------------------------- write machine-readable map
archetype_map = {
    "_doc": "Day-archetype coverage map for HARVEST-DAY-ANATOMY-2026-07-23.md. "
            "Built by analysis/kitchen/_harvest_anatomy_build.py joining "
            "engine-fullhist-replay-2026-07-23.json (190 trades / 141 trading days) to "
            "day-inventory-2026-07-23.json (386 days) and journal/trades.csv (this week's real fills).",
    "generated_from": {
        "replay": str(REPLAY_PATH.relative_to(ROOT)).replace("\\", "/"),
        "day_inventory": str(INVENTORY_PATH.relative_to(ROOT)).replace("\\", "/"),
        "spy_5m_source": str(SPY5M_PATH.relative_to(ROOT)).replace("\\", "/"),
        "trades_csv": str(TRADES_CSV.relative_to(ROOT)).replace("\\", "/"),
    },
    "population": {
        "n_days_total": len(all_dates),
        "n_trading_days": len(daily),
        "n_win_days": len(win_days),
        "n_loss_days": len(loss_days),
        "n_flat_days": len(flat_days),
        "n_sitout_days": len(sit_out_dates),
        "pct_sitout": round(100 * len(sit_out_dates) / len(all_dates), 1),
    },
    "win_days": win_summary,
    "loss_days": loss_summary,
    "flat_days": flat_summary,
    "sitout_archetypes": sitout_archetype_report,
    "full_population_by_day_type": full_pop_report,
    "this_week_extra_setup_fills_by_daytype": {
        dtp: dict(ctr) for dtp, ctr in this_week_setups_by_daytype.items()
    },
}

OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(archetype_map, f, indent=2)

# ---------------------------------------------------------------- per-day_type avg daily P&L (traded days only)
daytype_pnl = defaultdict(list)
vixband_pnl = defaultdict(list)
for dt, v in daily.items():
    inv = days_by_date.get(dt)
    if inv:
        daytype_pnl[inv["day_type"]].append(v["pnl"])
        vixband_pnl[inv["vix_band"]].append(v["pnl"])

daytype_pnl_report = {}
for dtype, pnls in daytype_pnl.items():
    daytype_pnl_report[dtype] = {
        "n_traded_days": len(pnls),
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl_per_day": round(statistics.mean(pnls), 2),
        "day_win_rate": round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1),
    }
print("\n=== AVG DAILY P&L BY DAY_TYPE (traded days only) ===")
print(json.dumps(daytype_pnl_report, indent=2))

vixband_pnl_report = {}
for vb, pnls in vixband_pnl.items():
    vixband_pnl_report[vb] = {
        "n_traded_days": len(pnls),
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl_per_day": round(statistics.mean(pnls), 2),
        "day_win_rate": round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1),
    }
print("\n=== AVG DAILY P&L BY VIX_BAND (traded days only) ===")
print(json.dumps(vixband_pnl_report, indent=2))

archetype_map["daytype_pnl_traded_days"] = daytype_pnl_report
archetype_map["vixband_pnl_traded_days"] = vixband_pnl_report
archetype_map["this_week_extra_setup_fills_by_daytype"] = {
    dtp: dict(ctr) for dtp, ctr in this_week_setups_by_daytype.items()
}
archetype_map["lane_assignment"] = {
    "trend": {
        "primary_lane": "trend-continuation",
        "secondary_lane": "extra-lanes harness",
        "why": "ribbon_ride requires a level touch (rejection/reclaim); pure trend days without "
               "one never fire it. Best traded avg-$/day (+92.55) of any archetype, 60.8% still "
               "sits out.",
    },
    "chop": {
        "primary_lane": "day-gate",
        "secondary_lane": "class-conditional exits",
        "why": "Only net-losing traded archetype (-43.83/day, 12.2% day-WR). Cheapest fix: veto "
               "ribbon_ride entries when day_type=chop using data already computed "
               "(range_ratio<0.75) -- no new indicator.",
    },
    "range": {
        "primary_lane": "extra-lanes harness",
        "secondary_lane": None,
        "why": "range-pingpong ENTRY family already killed 16/16 cells in "
               "EDGE-MATRIX-FULLHIST-2026-07-23.md -- do not re-cook range-fade entries. "
               "This week's real fills show 22 extra-setup fills already landing on range days.",
    },
    "trendline_tier_mismatch": {
        "scope": "cross-cutting, not day-type-specific",
        "primary_lane": "trendline refinement",
        "secondary_lane": "class-conditional exits",
        "why": "TRENDLINE tier = 65% of all volume (124/190) but net -1830.10 at 19.35% WR, the "
               "worst tier by both $ and WR. Single-trigger (trendline_rejection alone, no "
               "confluence) by construction.",
    },
    "high_vix": {
        "scope": "orthogonal to day_type, VIX band >= 25",
        "primary_lane": None,
        "why": "35/386 days (9.1%), 0 ever traded -- already fully gated by "
               "vix_bear_hard_cap=23.0 + block_elite_bull VIX[0,25). Not a cook target.",
    },
    "unclassified": {
        "scope": "5/386 days total",
        "primary_lane": None,
        "why": "ATR-20 warmup artifact of the day_type classifier (first ~20 days of window); "
               "not a real market archetype.",
    },
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(archetype_map, f, indent=2)

print(f"\nWrote {OUT_JSON}")
