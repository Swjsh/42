"""
REPRODUCTION-lens verification of dissect-wave-autopsy.md / .json (2026-09-03).
Independently rebuilds the wave map, P&L, entry features (range_position, zone-width
distance), HWM/MAE premium paths, and the wave-2 structure-stop zone-edge check directly
from the primary ledgers (NOT the original script's scratchpad copies, which this session
cannot read). Read-only on all inputs. No network. No trading-path file touched.

Run: python backtest/tools/dissect_verify_wave-autopsy_2.py
"""
import json
from datetime import datetime

REPO = r"C:\Users\jackw\Desktop\42"


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


fills_all = load_jsonl(f"{REPO}/automation/state/fills-ledger.jsonl")
fills = [r for r in fills_all if r.get("date_et") == "2026-09-03" and r.get("is_option")]
fills.sort(key=lambda r: r["ts_et"])

core_all = load_jsonl(f"{REPO}/automation/state/core-decisions.jsonl")
core = [r for r in core_all if r.get("ts_et", "").startswith("2026-09-03")]

safe3_all = load_jsonl(f"{REPO}/automation/state/fleet/safe-3/decisions.jsonl")
risky1_all = load_jsonl(f"{REPO}/automation/state/fleet/risky-1/decisions.jsonl")
safe3 = [r for r in safe3_all if r.get("ts_et", "").startswith("2026-09-03")]
risky1 = [r for r in risky1_all if r.get("ts_et", "").startswith("2026-09-03")]

kl = json.load(open(f"{REPO}/automation/state/key-levels.json", encoding="utf-8"))["levels"]
level_by_price = {round(l["price"], 4): l for l in kl}

safe_ticks = sorted([r for r in core if r.get("account") == "safe"], key=lambda r: r["ts_et"])

print("=" * 70)
print("STEP 1: raw fill counts")
print("=" * 70)
print("today option fills:", len(fills))
buys = [f for f in fills if f["side"] == "buy"]
sells = [f for f in fills if f["side"] == "sell"]
print("buys:", len(buys), "sells:", len(sells))

# ---------------------------------------------------------------
# STEP 2: rebuild wave P&L purely from fills-ledger, by (arm, symbol, time window)
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 2: wave P&L rebuilt from fills-ledger.jsonl only")
print("=" * 70)

waves = {
    "wave1": {"window": ("09:41:00", "10:05:00"), "arms": ["safe-2", "bold-2", "safe-3", "risky-1"]},
    "wave2": {"window": ("10:16:00", "10:38:00"), "arms": ["safe-2", "bold-2", "safe-3", "risky-1"]},
    "wave3": {"window": ("11:06:00", "11:22:00"), "arms": ["bold-2", "safe-3", "risky-1"]},
}

date_prefix = "2026-09-03T"
wave_pnls = {}
for wname, wdef in waves.items():
    wf, wt = wdef["window"]
    lo_ts, hi_ts = date_prefix + wf, date_prefix + wt
    wave_fills = [f for f in fills if lo_ts <= f["ts_et"] <= hi_ts and f["arm"] in wdef["arms"]]
    per_arm = {}
    for f in wave_fills:
        per_arm.setdefault(f["arm"], []).append(f)
    wave_total = 0.0
    print(f"--- {wname} [{wf}, {wt}] ---")
    for arm in wdef["arms"]:
        arm_fills = sorted(per_arm.get(arm, []), key=lambda f: f["ts_et"])
        arm_buys = [f for f in arm_fills if f["side"] == "buy"]
        arm_sells = [f for f in arm_fills if f["side"] == "sell"]
        if not arm_buys or not arm_sells:
            print(f"  {arm}: NO complete round trip in window (buys={len(arm_buys)} sells={len(arm_sells)}) -- SKIPPED")
            continue
        buy_qty = sum(b["qty"] for b in arm_buys)
        buy_cost = sum(b["qty"] * b["price"] for b in arm_buys)
        avg_entry = buy_cost / buy_qty
        sell_qty = sum(s["qty"] for s in arm_sells)
        sell_proceeds = sum(s["qty"] * s["price"] for s in arm_sells)
        pnl = round((sell_proceeds - buy_cost) * 100, 2)
        wave_total += pnl
        symbols = {f["symbol"] for f in arm_fills}
        print(f"  {arm:10s} symbol={sorted(symbols)} buy_qty={buy_qty:>4.0f} avg_entry={avg_entry:.4f} "
              f"sell_qty={sell_qty:>4.0f} qty_match={'OK' if buy_qty==sell_qty else 'MISMATCH'} pnl=${pnl:>8.2f}")
    wave_pnls[wname] = round(wave_total, 2)
    print(f"  WAVE TOTAL: ${round(wave_total, 2)}")
    print()

net3 = round(sum(wave_pnls.values()), 2)
print(f"3-wave net (independently rebuilt): ${net3}")
print(f"Report claimed: wave1=-779.00 wave2=-266.00 wave3=+1049.00 net=+4.00")
print(f"Rebuilt matches report: "
      f"wave1={'MATCH' if wave_pnls['wave1']==-779.00 else 'MISMATCH '+str(wave_pnls['wave1'])} "
      f"wave2={'MATCH' if wave_pnls['wave2']==-266.00 else 'MISMATCH '+str(wave_pnls['wave2'])} "
      f"wave3={'MATCH' if wave_pnls['wave3']==1049.00 else 'MISMATCH '+str(wave_pnls['wave3'])} "
      f"net={'MATCH' if net3==4.00 else 'MISMATCH '+str(net3)}")

# ---------------------------------------------------------------
# STEP 3: independently recompute range_position (session-so-far) at each wave's
# shared entry tick, using the safe-account per-minute SPY tape (session-so-far
# methodology as described in the report).
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 3: range_position (session-so-far) at each wave entry tick")
print("=" * 70)


def rp_at(ts):
    prefix = [r for r in safe_ticks if r["ts_et"] <= ts and r.get("spy") is not None]
    if not prefix:
        return None
    spys = [r["spy"] for r in prefix]
    hi, lo = max(spys), min(spys)
    spy_e = prefix[-1]["spy"]
    if hi == lo:
        return None
    return round((spy_e - lo) / (hi - lo), 4), hi, lo, len(prefix), spy_e


entry_ticks = {
    "wave1": "2026-09-03T09:41:03",
    "wave2": "2026-09-03T10:16:03",
    "wave3": "2026-09-03T11:06:04",
}
reported_rp = {"wave1": 1.0000, "wave2": 0.6953, "wave3": 1.0000}
for wname, ts in entry_ticks.items():
    rp, hi, lo, n, spy_e = rp_at(ts)
    print(f"  {wname} @ {ts}: spy={spy_e} hi={hi} lo={lo} n_ticks={n} range_position={rp} "
          f"(report claims {reported_rp[wname]}) -> {'MATCH' if rp == reported_rp[wname] else 'MISMATCH'}")

# ---------------------------------------------------------------
# STEP 4: zone-width / distance-from-level check
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 4: trigger level, zone_width, distance-in-zone-widths")
print("=" * 70)
level_checks = [
    ("wave1", 769.735, 769.36),
    ("wave2", 768.37, 768.00),
    ("wave3", 770.445, 769.36),
]
reported_zw = {"wave1": (0.8, 0.469), "wave2": (0.384, 0.964), "wave3": (0.8, 1.356)}
for wname, spy_e, trig in level_checks:
    lvl = level_by_price.get(round(trig, 4))
    zw = lvl.get("zone_width") if lvl else None
    dist = round(spy_e - trig, 4)
    ratio = round(dist / zw, 3) if zw else None
    exp_zw, exp_ratio = reported_zw[wname]
    print(f"  {wname}: trig={trig} label={lvl.get('label') if lvl else '??'} zone_width={zw} "
          f"dist=${dist} ratio={ratio} (report: zw={exp_zw} ratio={exp_ratio}) -> "
          f"{'MATCH' if zw == exp_zw and ratio == exp_ratio else 'MISMATCH'}")

# ---------------------------------------------------------------
# STEP 5: wave2 structure-stop zone-edge check (the report's headline doctrine-gap claim)
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 5: wave2 structure_stop mechanics -- raw-level vs zone-edge breach")
print("=" * 70)
stop_rows = []
for r in core:
    if r.get("ts_et", "")[11:16] in ("10:35", "10:36", "10:37"):
        for e in (r.get("exit_pass") or []):
            for a in e.get("actions", []):
                if a.get("placed") and a.get("stage") == "structure_stop":
                    stop_rows.append((r["ts_et"], r.get("account"), e.get("symbol"),
                                       e.get("trigger_level"), e.get("last_closed_5m_close")))
for r in safe3 + risky1:
    for e in (r.get("exit_pass") or []):
        for a in e.get("actions", []):
            if a.get("placed") and a.get("stage") == "structure_stop":
                stop_rows.append((r["ts_et"], "fleet", e.get("symbol"),
                                   e.get("trigger_level"), e.get("last_closed_5m_close")))
seen = set()
for ts, acct, sym, trig, close5m in stop_rows:
    key = (ts, acct, sym)
    if key in seen:
        continue
    seen.add(key)
    zone_edge = round(trig - 0.384, 4) if trig == 768.0 else None
    breach_raw = round(trig - close5m, 4) if trig is not None and close5m is not None else None
    breach_zone = round(zone_edge - close5m, 4) if zone_edge is not None and close5m is not None else None
    print(f"  {ts} {acct:6s} {sym} trigger={trig} zone_edge={zone_edge} last_5m_close={close5m} "
          f"breach_raw=${breach_raw} breach_zone=${breach_zone} "
          f"zone_breached={'YES' if breach_zone is not None and breach_zone > 0 else 'NO'}")

print()
print("Report claims: last_closed_5m_close=767.96, breach_of_raw_level=$0.04, "
      "zone_edge=767.616, zone NOT breached (767.96 is $0.344 inside zone)")

# ---------------------------------------------------------------
# STEP 6: SPY path after wave2 stop -- rally to 772.93 claim
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 6: SPY path 55 min after wave2 stop (767.96 @ 10:36)")
print("=" * 70)
t0 = datetime.fromisoformat("2026-09-03T10:36:03")
window = [(r["ts_et"], r["spy"]) for r in safe_ticks
          if datetime.fromisoformat(r["ts_et"]) >= t0 and
          (datetime.fromisoformat(r["ts_et"]) - t0).total_seconds() <= 3600]
vals = [v for _, v in window]
if vals:
    mx = max(vals)
    mx_ts = window[vals.index(mx)][0]
    print(f"  n_ticks={len(window)} min={min(vals)} max={mx} @ {mx_ts} last={vals[-1]} @ {window[-1][0]}")
    print(f"  Report claims: rally to 772.93 by 11:31:03, +$4.97 move -> "
          f"{'MATCH' if abs(mx-772.93)<0.001 and mx_ts=='2026-09-03T11:31:03' else 'CHECK (see values above)'}")

# ---------------------------------------------------------------
# STEP 7: safe-2 wave3 refusal -- gate rows
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 7: safe-2 wave3 refusal rows (11:06-11:22)")
print("=" * 70)
for r in core:
    if r.get("account") == "safe" and "11:06" <= r.get("ts_et", "")[11:16] <= "11:22":
        print(f"  {r['ts_et']} action={r.get('action')} spy={r.get('spy')} reason={r.get('reason')}")

# ---------------------------------------------------------------
# STEP 8: structure_veto_enabled config divergence (read-only)
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 8: structure_veto_enabled config check (read-only)")
print("=" * 70)
params = json.load(open(f"{REPO}/automation/state/params.json", encoding="utf-8"))
agg = json.load(open(f"{REPO}/automation/state/aggressive/params.json", encoding="utf-8"))
print("  safe params.json structure_veto_enabled:", params.get("structure_veto_enabled"))
print("  bold aggressive/params.json structure_veto_enabled:", agg.get("structure_veto_enabled"))

# ---------------------------------------------------------------
# STEP 9: HWM/MAE cross-check for wave1 (safe-2, bold-2 from core; safe-3, risky-1 from fleet)
# ---------------------------------------------------------------
print()
print("=" * 70)
print("STEP 9: HWM/MAE premium path for wave1 (all 4 arms)")
print("=" * 70)


def hwm_mae(rows, symbol, ts_from, ts_to):
    hwm = None
    hwm_ts = None
    mae = None
    mae_ts = None
    for r in rows:
        rts = r.get("ts_et", "")[:19]
        if rts < ts_from or rts > ts_to:
            continue
        for e in (r.get("exit_pass") or []):
            if e.get("symbol") != symbol:
                continue
            bp = e.get("best_premium")
            wp = e.get("worst_premium")
            if bp is not None and (hwm is None or bp > hwm):
                hwm, hwm_ts = bp, rts
            if wp is not None and (mae is None or wp < mae):
                mae, mae_ts = wp, rts
    return hwm, hwm_ts, mae, mae_ts


w1_checks = [
    ("safe-2", core, "SPY260903C00770000", "2026-09-03T09:41:04", "2026-09-03T10:03:03", 1.15, 0.47),
    ("bold-2", core, "SPY260903C00772000", "2026-09-03T09:42:06", "2026-09-03T09:58:04", 0.38, 0.18),
    ("safe-3", safe3, "SPY260903C00770000", "2026-09-03T09:42:05", "2026-09-03T10:01:06", 1.14, 0.55),
    ("risky-1", risky1, "SPY260903C00770000", "2026-09-03T09:42:05", "2026-09-03T10:02:07", 1.15, 0.49),
]
for arm, rows, sym, tf, tt, exp_hwm, exp_mae in w1_checks:
    hwm, hwm_ts, mae, mae_ts = hwm_mae(rows, sym, tf, tt)
    print(f"  {arm:10s} hwm={hwm} @ {hwm_ts} (report {exp_hwm}) mae={mae} @ {mae_ts} (report {exp_mae}) -> "
          f"{'MATCH' if hwm == exp_hwm and mae == exp_mae else 'CHECK'}")

print()
print("DONE.")
