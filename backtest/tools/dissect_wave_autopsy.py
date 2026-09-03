"""
D1 wave-by-wave autopsy of 2026-09-03 (scratch analysis tool, read-only on all ledgers).
No network. No writes to any trading-path or generated-surface file.
Outputs a JSON blob to stdout with every computed number the report needs.
"""
import json
from datetime import datetime

SCRATCH = r"C:\Users\jackw\AppData\Local\Temp\claude\C--Users-jackw-Desktop-42\b6eea006-22c7-498b-a0c1-23c79c635f20\scratchpad"
REPO = r"C:\Users\jackw\Desktop\42"


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


core = load_jsonl(f"{SCRATCH}/core-decisions-today.jsonl")
safe3 = load_jsonl(f"{SCRATCH}/safe3-today.jsonl")
risky1 = load_jsonl(f"{SCRATCH}/risky1-today.jsonl")
fills = load_jsonl(f"{SCRATCH}/fills-today.jsonl")
levels = json.load(open(f"{REPO}/automation/state/key-levels.json"))["levels"]
elr = json.load(open(f"{REPO}/analysis/deep-research/2026-09-03-money/entry-location-rows.json"))["rows"]

level_by_price = {round(l["price"], 4): l for l in levels}


def zone_width_for(price):
    r = round(price, 4)
    if r in level_by_price:
        return level_by_price[r].get("zone_width"), level_by_price[r].get("label")
    best, bd = None, None
    for l in levels:
        d = abs(l["price"] - price)
        if bd is None or d < bd:
            best, bd = l, d
    if best and bd < 0.05:
        return best.get("zone_width"), best.get("label")
    return None, None


safe_ticks = sorted([r for r in core if r.get("account") == "safe"], key=lambda r: r["ts_et"])
bold_ticks = sorted([r for r in core if r.get("account") == "bold"], key=lambda r: r["ts_et"])


def spy_tape_prefix(ts_et_str, ticks=safe_ticks):
    return [(r["ts_et"], r["spy"]) for r in ticks if r["ts_et"] <= ts_et_str]


def range_position_at(ts_et_str, spy_at_entry):
    prefix = spy_tape_prefix(ts_et_str)
    if not prefix:
        return None, None, None, 0
    hi = max(p for _, p in prefix)
    lo = min(p for _, p in prefix)
    if hi == lo:
        return None, hi, lo, len(prefix)
    return round((spy_at_entry - lo) / (hi - lo), 4), hi, lo, len(prefix)


def flip_minutes_before(ts_et_str, ticks, field, want):
    prefix = [r for r in ticks if r["ts_et"] <= ts_et_str]
    if not prefix:
        return None, None
    cur = prefix[-1].get(field)
    if cur != want:
        return None, cur
    flip_ts = prefix[-1]["ts_et"]
    hit_start = True
    for r in reversed(prefix):
        if r.get(field) == want:
            flip_ts = r["ts_et"]
        else:
            hit_start = False
            break
    t_entry = datetime.fromisoformat(ts_et_str)
    t_flip = datetime.fromisoformat(flip_ts)
    mins = round((t_entry - t_flip).total_seconds() / 60.0, 1)
    return mins, ("since_session_open(lower_bound)" if hit_start else "confirmed_flip")


def find_placed_row(account, ts_prefix):
    for r in core:
        if r.get("account") == account and r.get("action") == "PLACED" and r["ts_et"][11:16] == ts_prefix:
            return r
    return None


def find_fleet_entry_row(rows, ts_prefix):
    for r in rows:
        if r.get("action") == "ENTER_BULL" and r.get("ts_et", "")[11:16] == ts_prefix:
            return r
    return None


def exit_pass_series(rows, symbol, ts_from, ts_to, is_fleet):
    """Return list of (ts_et, open_qty, best_premium, worst_premium, actions) within [ts_from, ts_to]."""
    out = []
    for r in rows:
        ep = r.get("exit_pass") or []
        rts = r.get("ts_et", "")
        if is_fleet:
            rts_cmp = rts[:19]  # strip tz offset for compare with plain ts
        else:
            rts_cmp = rts
        if rts_cmp < ts_from or rts_cmp > ts_to:
            continue
        for e in ep:
            if e.get("symbol") == symbol:
                out.append({
                    "ts_et": rts,
                    "open_qty": e.get("open_qty"),
                    "best_premium": e.get("best_premium"),
                    "worst_premium": e.get("worst_premium"),
                    "actions": [(a.get("stage"), a.get("reason"), a.get("placed")) for a in e.get("actions", [])],
                })
    out.sort(key=lambda x: x["ts_et"])
    return out


def fills_for(arm, symbol, ts_from, ts_to):
    out = [f for f in fills if f["arm"] == arm and f["symbol"] == symbol and ts_from <= f["ts_et"] <= ts_to]
    out.sort(key=lambda f: f["ts_et"])
    return out


def spy_path(ts_from, minutes=60):
    t0 = datetime.fromisoformat(ts_from)
    out = []
    for ts, spy in [(r["ts_et"], r["spy"]) for r in safe_ticks]:
        t = datetime.fromisoformat(ts)
        if t0 <= t <= t0.replace() and (t - t0).total_seconds() <= minutes * 60 and t >= t0:
            out.append((ts, spy))
    return out


# ---- entry-location population stats for BULLISH_RECLAIM (calls), by outcome ----
brr = [r for r in elr if r["setup"] == "BULLISH_RECLAIM_RIDE_THE_RIBBON" and r["side"] == "C"]
winners = [r["range_position"] for r in brr if r["outcome"] == "winner" and r["range_position"] is not None]
losers = [r["range_position"] for r in brr if r["outcome"] == "loser" and r["range_position"] is not None]
hold_win = [r["hold_minutes"] for r in brr if r["outcome"] == "winner"]
hold_lose = [r["hold_minutes"] for r in brr if r["outcome"] == "loser"]


def mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


pop_stats = {
    "n_bullish_reclaim_calls": len(brr),
    "n_winners": len(winners), "mean_range_position_winners": mean(winners),
    "n_losers": len(losers), "mean_range_position_losers": mean(losers),
    "mean_hold_minutes_winners": mean(hold_win), "mean_hold_minutes_losers": mean(hold_lose),
}

# ================= WAVE DEFINITIONS =================
waves = {
    "wave1": {
        "window": ("09:41:00", "10:05:00"),
        "positions": [
            {"arm": "safe-2", "account": "safe", "symbol": "SPY260903C00770000", "entry_ts": "09:41",
             "equity": 5653.81},
            {"arm": "bold-2", "account": "bold", "symbol": "SPY260903C00772000", "entry_ts": "09:42",
             "equity": 5593.52},
            {"arm": "safe-3", "symbol": "SPY260903C00770000", "entry_ts": "09:42", "equity": None, "fleet": "safe3"},
            {"arm": "risky-1", "symbol": "SPY260903C00770000", "entry_ts": "09:42", "equity": None, "fleet": "risky1"},
        ],
    },
    "wave2": {
        "window": ("10:16:00", "10:38:00"),
        "positions": [
            {"arm": "safe-2", "account": "safe", "symbol": "SPY260903C00768000", "entry_ts": "10:16",
             "equity": 5653.81},
            {"arm": "bold-2", "account": "bold", "symbol": "SPY260903C00770000", "entry_ts": "10:16",
             "equity": 5593.52},
            {"arm": "safe-3", "symbol": "SPY260903C00768000", "entry_ts": "10:17", "equity": None, "fleet": "safe3"},
            {"arm": "risky-1", "symbol": "SPY260903C00768000", "entry_ts": "10:17", "equity": None, "fleet": "risky1"},
        ],
    },
    "wave3": {
        "window": ("11:06:00", "11:22:00"),
        "positions": [
            {"arm": "bold-2", "account": "bold", "symbol": "SPY260903C00772000", "entry_ts": "11:06",
             "equity": 5593.52},
            {"arm": "safe-3", "symbol": "SPY260903C00770000", "entry_ts": "11:07", "equity": None, "fleet": "safe3"},
            {"arm": "risky-1", "symbol": "SPY260903C00770000", "entry_ts": "11:07", "equity": None, "fleet": "risky1"},
        ],
    },
}

report = {"pop_stats": pop_stats, "waves": {}}

for wname, wdef in waves.items():
    wout = {"positions": []}
    for pos in wdef["positions"]:
        arm = pos["arm"]
        symbol = pos["symbol"]
        is_fleet = "fleet" in pos
        fleet_rows = safe3 if pos.get("fleet") == "safe3" else (risky1 if pos.get("fleet") == "risky1" else None)

        # entry row
        if is_fleet:
            entry_row = find_fleet_entry_row(fleet_rows, pos["entry_ts"])
            entry_ts_full = entry_row["ts_et"][:19] if entry_row else None
            spy_at_entry_row = None
            # get spy/ribbon/htf from the SAME core_tick_id on the safe/bold side (shared signal)
            core_tick_id = entry_row.get("core_tick_id") if entry_row else None
            matching_core = None
            if core_tick_id:
                for r in core:
                    if r.get("core_tick_id") == core_tick_id:
                        matching_core = r
                        break
            trigger_level = entry_row.get("trigger_level") if entry_row else None
            entry_premium_signal = entry_row.get("premium") if entry_row else None
            quality = entry_row.get("quality") if entry_row else None
            setup = entry_row.get("setup_name") if entry_row else None
        else:
            account = pos["account"]
            entry_row = find_placed_row(account, pos["entry_ts"])
            entry_ts_full = entry_row["ts_et"] if entry_row else None
            matching_core = entry_row
            trigger_level = entry_row.get("bull_reclaim_level_raw") if entry_row else None
            entry_premium_signal = None
            quality = None
            setup = entry_row.get("setup") if entry_row else None

        spy_at_entry = matching_core.get("spy") if matching_core else None
        ribbon = matching_core.get("ribbon") if matching_core else None
        htf_15m = matching_core.get("htf_15m") if matching_core else None
        vix = matching_core.get("vix") if matching_core else None
        spread_cents = matching_core.get("spread_cents") if matching_core else None
        bar_fresh = matching_core.get("bar_freshness", {}).get("age_min") if matching_core else None
        conviction = matching_core.get("conviction") if matching_core else None

        rp, hi, lo, n_ticks = (None, None, None, 0)
        if entry_ts_full and spy_at_entry:
            rp, hi, lo, n_ticks = range_position_at(entry_ts_full[:19], spy_at_entry)

        ribbon_flip_min, ribbon_note = (None, None)
        htf_flip_min, htf_note = (None, None)
        if entry_ts_full:
            ribbon_flip_min, ribbon_note = flip_minutes_before(entry_ts_full[:19], safe_ticks, "ribbon", "BULL")
            htf_flip_min, htf_note = flip_minutes_before(entry_ts_full[:19], safe_ticks, "htf_15m", "BULL")

        zw, zlabel = (None, None)
        if trigger_level:
            zw, zlabel = zone_width_for(trigger_level)

        dist_dollars = None
        dist_zw = None
        if trigger_level and spy_at_entry:
            dist_dollars = round(spy_at_entry - trigger_level, 4)
            if zw:
                dist_zw = round(dist_dollars / zw, 3)

        # fills for this position within the wave window
        wf, wt = wdef["window"]
        date_prefix = "2026-09-03T"
        pos_fills = fills_for(arm, symbol, date_prefix + wf, date_prefix + wt)
        buys = [f for f in pos_fills if f["side"] == "buy"]
        sells = [f for f in pos_fills if f["side"] == "sell"]
        entry_fill = buys[0] if buys else None
        entry_price = entry_fill["price"] if entry_fill else None
        entry_qty = sum(b["qty"] for b in buys) if buys else None

        # exit_pass series
        rows_for_ep = fleet_rows if is_fleet else core
        ts_ep_from = entry_fill["ts_et"] if entry_fill else (date_prefix + wf)
        ts_ep_to = sells[-1]["ts_et"] if sells else (date_prefix + wt)
        ep_series = exit_pass_series(rows_for_ep, symbol, ts_ep_from, ts_ep_to, is_fleet)

        hwm = None
        hwm_ts = None
        mae_worst = None
        mae_ts = None
        for e in ep_series:
            if e["best_premium"] is not None and (hwm is None or e["best_premium"] > hwm):
                hwm = e["best_premium"]
                hwm_ts = e["ts_et"]
            if e["worst_premium"] is not None and (mae_worst is None or e["worst_premium"] < mae_worst):
                mae_worst = e["worst_premium"]
                mae_ts = e["ts_et"]

        time_to_hwm_min = None
        if hwm_ts and entry_fill:
            t0 = datetime.fromisoformat(entry_fill["ts_et"])
            t1 = datetime.fromisoformat(hwm_ts[:19])
            time_to_hwm_min = round((t1 - t0).total_seconds() / 60.0, 1)

        exits = []
        for s in sells:
            exits.append({"ts_et": s["ts_et"], "qty": s["qty"], "price": s["price"]})

        realized_pnl = None
        if entry_price and sells:
            realized_pnl = round(sum((s["price"] - entry_price) * s["qty"] * 100 for s in sells), 2)
        cost_basis = round(entry_price * entry_qty * 100, 2) if entry_price and entry_qty else None
        pnl_pct_premium = round(realized_pnl / cost_basis * 100, 2) if realized_pnl is not None and cost_basis else None
        pnl_pct_equity = round(realized_pnl / pos["equity"] * 100, 2) if realized_pnl is not None and pos.get("equity") else None

        # exit stage tags from actions
        exit_stages = []
        for e in ep_series:
            for (stage, reason, placed) in e["actions"]:
                if placed:
                    exit_stages.append({"ts": e["ts_et"], "stage": stage, "reason": reason})

        # SPY path 60 min after final exit -- summarized, not the full tape
        final_exit_ts = sells[-1]["ts_et"][:19] if sells else None
        spy_after = []
        if final_exit_ts:
            t0 = datetime.fromisoformat(final_exit_ts)
            for ts, spy in [(r["ts_et"], r["spy"]) for r in safe_ticks]:
                t = datetime.fromisoformat(ts)
                if t >= t0 and (t - t0).total_seconds() <= 3600:
                    spy_after.append([ts, spy])
        spy_after_summary = None
        if spy_after:
            vals = [v for _, v in spy_after]
            spy_after_summary = {
                "spy_at_exit": spy_after[0][1],
                "min_60m": min(vals), "min_ts": spy_after[[v for _, v in spy_after].index(min(vals))][0],
                "max_60m": max(vals), "max_ts": spy_after[[v for _, v in spy_after].index(max(vals))][0],
                "last_60m": spy_after[-1][1], "last_ts": spy_after[-1][0],
                "n_ticks": len(spy_after),
            }

        wout["positions"].append({
            "arm": arm, "symbol": symbol,
            "entry": {
                "ts_et": entry_ts_full, "spy_at_entry": spy_at_entry,
                "range_position_session_so_far": rp, "session_hi": hi, "session_lo": lo, "n_ticks_in_prefix": n_ticks,
                "ribbon": ribbon, "ribbon_flip_minutes_before_entry": ribbon_flip_min, "ribbon_flip_note": ribbon_note,
                "htf_15m": htf_15m, "htf_15m_flip_minutes_before_entry": htf_flip_min, "htf_15m_flip_note": htf_note,
                "vix": vix, "spread_cents": spread_cents, "bar_freshness_age_min": bar_fresh,
                "trigger_level": trigger_level, "zone_width": zw, "zone_label": zlabel,
                "distance_dollars": dist_dollars, "distance_zone_widths": dist_zw,
                "conviction": conviction, "setup": setup, "quality": quality,
                "entry_fill_price": entry_price, "entry_fill_qty": entry_qty, "entry_premium_signal": entry_premium_signal,
            },
            "premium_path": {
                "hwm": hwm, "hwm_ts": hwm_ts, "time_to_hwm_min": time_to_hwm_min,
                "mae_worst_premium": mae_worst, "mae_ts": mae_ts,
                "n_exit_pass_ticks": len(ep_series),
            },
            "exits": exits, "exit_stages": exit_stages,
            "pnl": {"realized_pnl_dollars": realized_pnl, "cost_basis_dollars": cost_basis,
                    "pnl_pct_of_premium": pnl_pct_premium, "pnl_pct_of_equity": pnl_pct_equity},
            "spy_after_exit_60min_summary": spy_after_summary,
        })
    report["waves"][wname] = wout

# safe-2 wave-3 refusal detail
safe_refusal = []
for r in core:
    if r.get("account") == "safe" and r.get("action") in ("SKIP_BULL_1100_1200", "SKIP_STRUCTURE_VETO") and "11:0" <= r["ts_et"][11:16] <= "11:22":
        safe_refusal.append({"ts_et": r["ts_et"], "action": r["action"], "spy": r.get("spy"), "reason": r.get("reason")})
report["safe2_wave3_refusal"] = safe_refusal


# ---- Q2 supplement: SPY-points-at-stop / implied realized delta ----
def spy_window(ts_from, ts_to):
    t0 = datetime.fromisoformat(ts_from[:19])
    t1 = datetime.fromisoformat(ts_to[:19])
    return [(r["ts_et"], r["spy"]) for r in safe_ticks if t0 <= datetime.fromisoformat(r["ts_et"]) <= t1]


loss_math = []
for name, ets, xts, ep, xp, stop_kind in [
    ("safe-2/770C-w1", "2026-09-03T09:41:03", "2026-09-03T10:03:03", 0.98, 0.50, "premium_stop(-50%)"),
    ("bold-2/772C-w1", "2026-09-03T09:42:05", "2026-09-03T09:58:04", 0.37, 0.20, "premium_stop(-50%)"),
    ("safe-3/770C-w1", "2026-09-03T09:42:05", "2026-09-03T10:01:06", 1.11, 0.57, "premium_stop(-50%)"),
    ("risky-1/770C-w1", "2026-09-03T09:42:05", "2026-09-03T10:02:07", 1.08, 0.52, "premium_stop(-50%)"),
    ("safe-2/768C-w2", "2026-09-03T10:16:03", "2026-09-03T10:36:04", 1.40, 1.18, "structure_stop(768.00)"),
    ("bold-2/770C-w2", "2026-09-03T10:16:08", "2026-09-03T10:36:05", 0.48, 0.34, "structure_stop(768.00)"),
    ("safe-3/768C-w2", "2026-09-03T10:17:06", "2026-09-03T10:37:06", 1.31, 1.18, "structure_stop(768.00)"),
    ("risky-1/768C-w2", "2026-09-03T10:17:06", "2026-09-03T10:37:07", 1.31, 1.18, "structure_stop(768.00)"),
]:
    w = spy_window(ets, xts)
    spys = [v for _, v in w]
    spy_entry, spy_exit = (w[0][1], w[-1][1]) if w else (None, None)
    d_prem = round(xp - ep, 4)
    d_spy = round(spy_exit - spy_entry, 4) if spy_entry and spy_exit else None
    eff_delta = round(d_prem / d_spy, 3) if d_spy else None
    loss_math.append({
        "position": name, "stop_kind": stop_kind,
        "spy_entry": spy_entry, "spy_at_stop": spy_exit, "spy_move_dollars": d_spy,
        "premium_entry": ep, "premium_at_stop": xp, "premium_move_dollars": d_prem,
        "implied_realized_delta_1min_resolution": eff_delta,
        "note": "delta computed from 1-min-cadence SPY snapshots around entry/exit; NOT tick-level, true intraminute move could differ",
    })
report["q2_spy_points_at_stop"] = loss_math

# ---- Q3 supplement: zone-edge counterfactual for wave2's structure stop ----
report["q3_wave2_zone_edge_counterfactual"] = {
    "trigger_level": 768.00,
    "zone_width": 0.384,
    "zone_edge_lower": round(768.00 - 0.384, 4),
    "actual_stop_basis": "last_closed_5m_close",
    "actual_stop_5m_close": 767.96,
    "breach_of_raw_level_dollars": round(768.00 - 767.96, 4),
    "breach_of_zone_edge_dollars": round((768.00 - 0.384) - 767.96, 4),
    "zone_edge_breached": (767.96 < (768.00 - 0.384)),
    "spy_60min_after_actual_stop_max": 772.93,
    "spy_60min_after_actual_stop_max_ts": "2026-09-03T11:31:03",
    "note": "actual structure_stop fired on a 4-cent breach of the RAW level (768.00), while the 5m close (767.96) never breached the level's own zone_width edge (767.616) -- under a zone-edge-adjusted stop rule this position would not have exited at 10:36",
}

print(json.dumps(report, indent=2, default=str))
