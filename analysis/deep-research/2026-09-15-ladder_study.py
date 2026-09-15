import csv, json, re
from collections import defaultdict

REPO = r"C:\Users\jackw\Desktop\42"

def occ_symbol(contract_str, date_str):
    # "SPY 2026-09-15 757P" -> "SPY260915P00757000"
    m = re.match(r"(\w+)\s+(\d{4})-(\d{2})-(\d{2})\s+([\d.]+)([CP])", contract_str.strip())
    if not m:
        return None
    root, y, mo, d, strike, cp = m.groups()
    yy = y[2:]
    strike_val = float(strike)
    strike_int = int(round(strike_val * 1000))
    return f"{root}{yy}{mo}{d}{cp}{strike_int:08d}"

ACCOUNT_SRC = {
    "safe": ("core", "safe"),
    "bold": ("core", "bold"),
    "safe-3": ("fleet", "safe-3"),
    "risky-1": ("fleet", "risky-1"),
}

# Load trades.csv, filter
rows = list(csv.DictReader(open(REPO + r"\journal\trades.csv", encoding="utf-8-sig")))
setups = ("BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON")
trades = [r for r in rows if r["setup"] in setups and r["date"] >= "2026-08-10"
          and r["account_id"] in ACCOUNT_SRC]
print("Candidate trades:", len(trades))

# Build tick indexes lazily per source
tick_index = {"core": defaultdict(list), "fleet_safe-3": defaultdict(list), "fleet_risky-1": defaultdict(list)}

def load_core():
    path = REPO + r"\automation\state\core-decisions.jsonl"
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            acct = d.get("account")
            if acct not in ("safe", "bold"):
                continue
            ts = d.get("ts_et")
            if not ts or ts < "2026-08-10":
                continue
            for e in (d.get("exit_pass") or []):
                sym = e.get("symbol")
                if sym is None or "best_premium" not in e:
                    continue
                stages = [a.get("stage") for a in (e.get("actions") or [])]
                tick_index["core"][(acct, sym)].append((ts, e.get("best_premium"), e.get("worst_premium"), stages, e.get("tp1_filled")))

def load_fleet(arm):
    path = REPO + f"\\automation\\state\\fleet\\{arm}\\decisions.jsonl"
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get("ts_et") or d.get("ts")
            if not ts or ts < "2026-08-10":
                continue
            for e in (d.get("exit_pass") or []):
                sym = e.get("symbol")
                if sym is None or "best_premium" not in e:
                    continue
                stages = [a.get("stage") for a in (e.get("actions") or [])]
                tick_index[f"fleet_{arm}"][sym].append((ts, e.get("best_premium"), e.get("worst_premium"), stages, e.get("tp1_filled")))

print("loading core...")
load_core()
print("loading fleet safe-3...")
load_fleet("safe-3")
print("loading fleet risky-1...")
load_fleet("risky-1")
print("done loading")

for k in tick_index:
    for key in tick_index[k]:
        tick_index[k][key].sort(key=lambda x: x[0])

results = []
excluded = []

for r in trades:
    acct = r["account_id"]
    src, key = ACCOUNT_SRC[acct]
    sym = occ_symbol(r["contract"], r["date"])
    if sym is None:
        excluded.append((r, "bad symbol parse"))
        continue
    if src == "core":
        ticks = tick_index["core"].get((key, sym), [])
    else:
        ticks = tick_index[f"fleet_{key}"].get(sym, [])
    # restrict to this trade's date
    ticks = [t for t in ticks if t[0].startswith(r["date"])]
    if not ticks:
        excluded.append((r, "no ticks found"))
        continue
    try:
        entry = float(r["entry_px"])
        exitpx = float(r["exit_px"])
        pnl = float(r["dollar_pnl"])
    except ValueError:
        excluded.append((r, "bad numeric field"))
        continue
    if entry <= 0:
        excluded.append((r, "entry<=0"))
        continue

    # find peak (max best_premium) and its tick time
    peak = entry
    peak_ts = ticks[0][0]
    for ts, best, worst, stages, tp1f in ticks:
        if best is not None and best > peak:
            peak = best
            peak_ts = ts
    mfe_pct = (peak - entry) / entry

    # find real exit tick: last tick with a SELL_ALL/SELL_PARTIAL stage matching exit family,
    # approximate as the tick whose stages list is non-empty and is the LAST tick in our slice
    # (exit_pass entries stop being logged once position is flat, so the last tick with stages
    # non-empty, or simply the last tick overall, approximates the exit tick).
    exit_stage = None
    exit_tick_idx = len(ticks) - 1
    for i, (ts, best, worst, stages, tp1f) in enumerate(ticks):
        if stages:
            exit_stage = stages[-1]
            exit_tick_idx = i
    if exit_stage is None:
        exit_stage = "UNKNOWN(no-stage-tick-found)"

    # first tick where tp1_filled flips True -- the pre_tp1_ladder mechanism (per
    # exit_manager.py comment "PRE-TP1 ONLY") stops applying at/after this point; post-TP1
    # the real ribbon_ride shape switches to the trailing chandelier (arm +5%, trail 15%),
    # a DIFFERENT and more protective mechanism this study does not re-simulate. Capping the
    # counterfactual ladder check at this tick avoids the artifact of applying a stale
    # pre-TP1 fixed floor to a leg that, in reality, was already running under chandelier
    # protection (see the too-good-to-be-true correction in the written report).
    tp1_tick_idx = None
    for i, (ts, best, worst, stages, tp1f) in enumerate(ticks[:exit_tick_idx + 1]):
        if tp1f:
            tp1_tick_idx = i
            break
    ladder_cutoff_idx = (tp1_tick_idx - 1) if tp1_tick_idx is not None else exit_tick_idx

    rung1_armed_real = False
    hwm = entry
    rung1_arm_ts = None
    for ts, best, worst, stages, tp1f in ticks[:exit_tick_idx + 1]:
        if best is not None:
            hwm = max(hwm, best)
        if hwm >= entry * 1.50 and not rung1_armed_real:
            rung1_armed_real = True
            rung1_arm_ts = ts

    # counterfactual simulation for arm thresholds 0.30 and 0.40, lock 0.30 -- ONLY evaluated
    # up to ladder_cutoff_idx (real TP1 fill tick, or real exit tick if TP1 never fired).
    def simulate(arm_pct, lock_pct):
        hwm_ = entry
        floor = None
        for i, (ts, best, worst, stages, tp1f) in enumerate(ticks[:ladder_cutoff_idx + 1]):
            if best is not None:
                hwm_ = max(hwm_, best)
            if floor is None and hwm_ >= entry * (1.0 + arm_pct):
                floor = entry * (1.0 + lock_pct)
            if floor is not None and worst is not None and worst <= floor:
                return ("cf_stop", i, ts, floor)
        return ("no_earlier_stop", None, None, floor)

    cf30 = simulate(0.30, 0.30)
    cf40 = simulate(0.40, 0.30)

    qty = float(r["qty"]) if r["qty"] else None

    def cf_outcome(cf):
        kind, idx, ts, floor = cf
        if kind == "no_earlier_stop":
            return exitpx, pnl, "unchanged(real exit stands)"
        # counterfactual exits earlier: fill at the TICK'S worst_premium (the value that
        # crossed the floor), not the floor level itself -- more realistic than assuming a
        # perfect fill exactly at the stop price (real premium_stop fills land near tick
        # worst_premium, per E1 evidence: bold-2 2026-09-15 floor=0.611, tick worst ~0.62,
        # real fill 0.62 -- using the floor itself would be the optimistic/generous number).
        cf_fill_ts, cf_fill_best, cf_fill_worst, _stages, _tp1f = ticks[idx]
        cf_exit_px = cf_fill_worst if cf_fill_worst is not None else floor
        if qty is None:
            cf_pnl = None
        else:
            cf_pnl = qty * 100.0 * (cf_exit_px - entry)
        return cf_exit_px, cf_pnl, f"cf_stop@tick{idx}_ts={ts}_floor={round(floor,4)}"

    cf30_px, cf30_pnl, cf30_note = cf_outcome(cf30)
    cf40_px, cf40_pnl, cf40_note = cf_outcome(cf40)

    results.append({
        "date": r["date"], "account": acct, "symbol": sym,
        "entry": entry, "peak": round(peak,4), "mfe_pct": round(mfe_pct*100,1),
        "peak_ts": peak_ts, "exit_px": exitpx, "exit_stage": exit_stage,
        "tp1_fired": tp1_tick_idx is not None,
        "dollar_pnl": pnl, "rung1_armed_real": rung1_armed_real,
        "n_ticks": len(ticks),
        "cf30_pnl": cf30_pnl, "cf30_note": cf30_note,
        "cf40_pnl": cf40_pnl, "cf40_note": cf40_note,
    })

print("Matched with ticks:", len(results))
print("Excluded:", len(excluded))
exclusion_reasons = defaultdict(int)
for r, reason in excluded:
    exclusion_reasons[reason] += 1
print(exclusion_reasons)

outpath = r"C:\Users\jackw\AppData\Local\Temp\claude\C--Users-jackw-Desktop-42\5385b0a5-8695-42c3-a1ef-f20bf49a345c\scratchpad\ladder_results.json"
with open(outpath, "w") as f:
    json.dump({"results": results, "excluded_count": len(excluded), "exclusion_reasons": dict(exclusion_reasons)}, f, indent=2)
print("wrote", outpath)
