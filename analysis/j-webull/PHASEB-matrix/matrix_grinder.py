"""Phase B — J-EDGE DEEP MATRIX grinder (2026-07-02).

Implements analysis/j-webull/PHASEB-matrix/DESIGN.md EXACTLY (pre-registered,
committed before this ran). Reuses the E2 replay core (episode rebuild, BS
pricing conventions, C6-causal entry bar, drop accounting) — does not rebuild.

*** BS-SYNTHETIC OPTION PRICING — RANKING-ONLY EVIDENCE PER C1. ***
"""
from __future__ import annotations

import gzip
import io
import json
import sys
import time as _time
from datetime import datetime, time as dtime, timedelta
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

HERE = Path(__file__).resolve().parent          # PHASEB-matrix/
JWB = HERE.parent                               # analysis/j-webull/
SCRIPTS = JWB / "scripts"
REPO = JWB.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO))

from e2_e5_replay import (  # noqa: E402
    MIN_PREM, TIME_STOP, build_episodes_with_fills, load_spy_rth, load_vix,
    tte_years, atm_strike,
)
from webull_parse import SPOT_RATIO, load_fills  # noqa: E402
from backtest.lib.pricing import black_scholes, vix_to_iv  # noqa: E402

CAVEAT = ("BS-SYNTHETIC OPTION PRICING — RANKING-ONLY EVIDENCE PER C1. "
          "No smile, no spread, no fills. Never a promotion gate.")

# ---------------------------------------------------------------- design axes
STOPS = (-0.08, -0.20, -0.35, -0.50)
TP1S = (("tp30x67", 0.30, 2.0 / 3.0), ("tp75x67", 0.75, 2.0 / 3.0),
        ("tp150x80", 1.50, 0.80), ("tpNone", None, None))
TRAILS = (("trailNone", False), ("trailChand", True))
TSTOPS = (("t60", 60), ("t120", 120), ("tEOD", None))
STRIKE_LABELS = ("his", "atm", "itm1", "itm2", "otm1")
SIZES = ("first_fill", "fixed_1", "fixed_3")

CHAND_ARM_RET = 0.05
CHAND_TRAIL = 0.85
TRAIN_CUTOFF = pd.Timestamp("2023-01-01")
K_MAX = 25
MIN_N_TRAIN = 60
MIN_N_TEST = 30
FDR_ALPHA = 0.10
DIV_PER_FILTER_STRIKE = 3
DIV_PER_FILTER = 10

WINDOWS = (("open", dtime(9, 30), dtime(10, 0)),
           ("morning", dtime(10, 0), dtime(11, 0)),
           ("midday", dtime(11, 0), dtime(14, 0)),
           ("late", dtime(14, 0), dtime(16, 0)))


# ---------------------------------------------------------------- exit walker
def walk_exit(rets: np.ndarray, n_cap: int, stop: float, tp1_ret, tp1_frac,
              trail: bool, runner_target=None) -> float:
    """Generalized E2-style walker on precomputed return path (prem/prem0 - 1).

    Returns realized exit value as a RETURN multiple (avg_exit_prem / prem0).
    Order per bar (DESIGN.md): stop -> chandelier -> TP1 (+same-bar runner
    target in anchor mode) -> post-TP1 runner-target / breakeven floor.
    """
    frac = 1.0
    realized = 0.0
    tp1_done = False
    hwm = 1.0
    armed = False
    rel = 1.0
    for i in range(n_cap):
        ret = rets[i]
        rel = 1.0 + ret
        if not tp1_done and ret <= stop:
            realized += frac * rel
            return realized
        if trail:
            if rel > hwm:
                hwm = rel
            if not armed and ret >= CHAND_ARM_RET:
                armed = True
            if armed and rel <= CHAND_TRAIL * hwm:
                realized += frac * rel
                return realized
        if tp1_ret is not None and not tp1_done:
            if ret >= tp1_ret:
                realized += tp1_frac * rel
                frac = 1.0 - tp1_frac
                tp1_done = True
                if runner_target is not None and ret >= runner_target:
                    realized += frac * rel
                    return realized
            continue
        if tp1_done:
            if runner_target is not None and ret >= runner_target:
                realized += frac * rel
                return realized
            if ret <= 0.0:
                realized += frac * rel
                return realized
    realized += frac * rel  # time stop at last evaluated bar
    return realized


# ---------------------------------------------------------------- data build
def strike_ladder(spot0: float, underlying: str, his: float, is_call: bool):
    atm = atm_strike(spot0, underlying)
    step = 5.0 if underlying in ("SPX", "SPXW") else 1.0
    sgn = 1.0 if is_call else -1.0
    return {"his": his, "atm": atm, "itm1": atm - sgn * step,
            "itm2": atm - sgn * 2 * step, "otm1": atm + sgn * step}


def build_universe():
    fills, _ = load_fills()
    ep = build_episodes_with_fills(fills)
    fam = ep[ep["is_family"]].reset_index(drop=True)
    assert len(fam) == 567, f"episode count mismatch: {len(fam)}"
    assert abs(float(fam["pnl"].sum()) - (-12885.0)) < 5.0

    norm = pd.read_csv(JWB / "trades-normalized.csv", parse_dates=["entry_ts_et"])
    norm = norm[norm["is_family"] & norm["closed"]].copy()
    norm["expiry"] = pd.to_datetime(norm["expiry"]).dt.date
    for df in (norm, fam):
        df["key"] = (df["underlying"] + "|" + df["strike"].astype(float).astype(str)
                     + "|" + df["right"] + "|" + df["expiry"].astype(str)
                     + "|" + df["entry_ts_et"].astype(str))
    ctx_cols = ["key", "episode_id", "ctx_ok", "spy_px", "vwap_side",
                "nearest_level", "nearest_level_dist_pct", "bias", "is_0dte",
                "entry_px", "qty"]
    j = fam.merge(norm[ctx_cols], on="key", how="left", suffixes=("", "_norm"))
    assert j["ctx_ok"].notna().all(), "context join failed"

    rth = load_spy_rth()
    vix = load_vix()
    vix_by_date = {r["date"]: r for _, r in vix.iterrows()}
    bars_by_date = dict(tuple(rth.groupby("date")))

    drops = {"no_ctx": 0, "no_vix": 0, "no_entry_bar": 0, "no_path_bars": 0}
    unpriceable = {s: 0 for s in STRIKE_LABELS}
    episodes = []
    for _, r in j.iterrows():
        if not bool(r["ctx_ok"]):
            drops["no_ctx"] += 1
            continue
        d = r["entry_ts_et"].date()
        vrow = vix_by_date.get(d)
        vix_val = None
        if vrow is not None:
            vix_val = vrow["open"] if pd.notna(vrow["open"]) else vrow["prior_close"]
        if vrow is None or pd.isna(vix_val):
            drops["no_vix"] += 1
            continue
        day = bars_by_date.get(d)
        if day is None:
            drops["no_entry_bar"] += 1
            continue
        entry_ts = pd.Timestamp(r["entry_ts_et"])
        prior = day[day["bar_close_ts"] <= entry_ts]
        if prior.empty:
            drops["no_entry_bar"] += 1
            continue
        eb = prior.iloc[-1]
        path = day[(day["bar_close_ts"] > entry_ts)
                   & (day["ts"].dt.time <= TIME_STOP)]
        if path.empty:
            drops["no_path_bars"] += 1
            continue

        ratio = SPOT_RATIO[r["underlying"]]
        spot0 = float(eb["c"]) * ratio
        iv = vix_to_iv(float(vix_val))
        is_call = r["right"] == "C"
        expiry_dt = datetime.combine(r["expiry"], dtime(16, 0))
        t0 = eb["bar_close_ts"].to_pydatetime()

        closes = path["c"].to_numpy(dtype=float) * ratio
        bar_closes = [ts.to_pydatetime() for ts in path["bar_close_ts"]]
        mins = np.array([(bc - t0).total_seconds() / 60.0 for bc in bar_closes])
        ttes = np.array([tte_years(bc, expiry_dt) for bc in bar_closes])

        ladder = strike_ladder(spot0, r["underlying"], float(r["strike"]), is_call)
        rets_by_strike = {}
        prem0_by_strike = {}
        for lbl, k in ladder.items():
            p0, _ = black_scholes(spot0, k, iv, tte_years(t0, expiry_dt), is_call)
            if p0 < MIN_PREM:
                unpriceable[lbl] += 1
                rets_by_strike[lbl] = None
                prem0_by_strike[lbl] = None
                continue
            prems = np.array([black_scholes(c, k, iv, t, is_call)[0]
                              for c, t in zip(closes, ttes)])
            rets_by_strike[lbl] = prems / p0 - 1.0
            prem0_by_strike[lbl] = p0
        # null: ATM strike, OPPOSITE direction (E2 null construction)
        k_atm = ladder["atm"]
        p0n, _ = black_scholes(spot0, k_atm, iv, tte_years(t0, expiry_dt),
                               not is_call)
        prems_n = np.array([black_scholes(c, k_atm, iv, t, not is_call)[0]
                            for c, t in zip(closes, ttes)])

        # entry-time features (C6-causal)
        at_level = bool(pd.notna(r["nearest_level_dist_pct"])
                        and abs(float(r["nearest_level_dist_pct"])) <= 0.1)
        aligned = bool((r["bias"] == "bull" and r["vwap_side"] == "above")
                       or (r["bias"] == "bear" and r["vwap_side"] == "below"))
        et = entry_ts.time()
        window = next((w for w, lo, hi in WINDOWS if lo <= et < hi), "other")
        first_test = retest = False
        if (at_level and pd.notna(r["nearest_level_dist_pct"])
                and pd.notna(r["spy_px"])):
            # build_normalized: dist = (spy/level - 1)*100  ->  reconstruct level
            lvl = float(r["spy_px"]) / (1.0 + float(r["nearest_level_dist_pct"]) / 100.0)
            pre = day[day["bar_close_ts"] < eb["bar_close_ts"]]
            touched = bool(((pre["l"] <= lvl * 1.001)
                            & (pre["h"] >= lvl * 0.999)).any()) if len(pre) else False
            first_test, retest = (not touched), touched

        episodes.append({
            "key": r["key"], "episode_id": int(r["episode_id"]),
            "entry_ts": entry_ts, "is_test": entry_ts >= TRAIN_CUTOFF,
            "is_call": is_call, "at_level": at_level, "aligned": aligned,
            "window": window, "dow": entry_ts.day_name(),
            "first_test": first_test, "retest": retest,
            "first_qty": int(r["first_qty"]), "j_pnl": float(r["pnl"]),
            "mins": mins, "rets": rets_by_strike, "prem0": prem0_by_strike,
            "null_rets": prems_n / p0n - 1.0, "null_prem0": p0n,
        })
    return episodes, drops, unpriceable


# ---------------------------------------------------------------- filters
def build_filters(eps) -> dict[str, np.ndarray]:
    n = len(eps)
    def arr(fn):
        return np.array([bool(fn(e)) for e in eps])
    f = {"all": np.ones(n, dtype=bool),
         "dir=C": arr(lambda e: e["is_call"]),
         "dir=P": arr(lambda e: not e["is_call"]),
         "at_level": arr(lambda e: e["at_level"]),
         "aligned": arr(lambda e: e["aligned"]),
         "first_test": arr(lambda e: e["first_test"]),
         "retest": arr(lambda e: e["retest"])}
    for w, _, _ in WINDOWS:
        f[f"win={w}"] = arr(lambda e, w=w: e["window"] == w)
    for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
        f[f"dow={d}"] = arr(lambda e, d=d: e["dow"] == d)
    # pairs (DESIGN.md: dir/at_level/aligned/window families only)
    for dname in ("dir=C", "dir=P"):
        f[f"{dname}&at_level"] = f[dname] & f["at_level"]
        f[f"{dname}&aligned"] = f[dname] & f["aligned"]
        for w, _, _ in WINDOWS:
            f[f"{dname}&win={w}"] = f[dname] & f[f"win={w}"]
    f["at_level&aligned"] = f["at_level"] & f["aligned"]
    for w, _, _ in WINDOWS:
        f[f"at_level&win={w}"] = f["at_level"] & f[f"win={w}"]
        f[f"aligned&win={w}"] = f["aligned"] & f[f"win={w}"]
    return f


def maybe_e6_filters(eps, f: dict) -> str:
    """DESIGN.md: check E6 results.json ONCE at grind time; join its top
    train-weighted features (by |point-biserial|, positive sign) as single
    filters. Join key = episode_id (episodes-scored.csv). E6 covers 467 of
    the 542 ctx-ok episodes (its early-entry drop); non-members = False.
    Thresholds: >0 for favor/recency features; train-median for counts
    (train rows only — no test leakage)."""
    res_p = JWB / "E6-structure-read" / "results.json"
    csv_p = JWB / "E6-structure-read" / "episodes-scored.csv"
    if not res_p.exists() or not csv_p.exists():
        return "absent"
    try:
        data = json.loads(res_p.read_text(encoding="utf-8"))
        weights = data.get("train_weights_point_biserial", {})
        top = sorted(((k, v) for k, v in weights.items() if v > 0),
                     key=lambda kv: -abs(kv[1]))[:3]
        if not top:
            return "present_no_positive_features"
        sc = pd.read_csv(csv_p)
        by_id = sc.set_index("episode_id")
        train_ids = set(sc[~sc["is_test"]]["episode_id"])
        added = []
        for name, _w in top:
            col = by_id[name]
            if name == "touch_count":
                thr = float(sc[~sc["is_test"]][name].median())
                rule = f">= train-median {thr:g}"
            else:
                thr = 0.0
                rule = "> 0"
            mask = []
            for e in eps:
                eid = e["episode_id"]
                if eid not in by_id.index:
                    mask.append(False)
                    continue
                v = col.loc[eid]
                mask.append(bool(v >= thr if name == "touch_count" else v > thr))
            f[f"e6:{name}({rule})"] = np.array(mask)
            added.append(f"{name} {rule}")
        _ = train_ids  # membership documented; thresholds train-only
        return ("added [E6 verdict=" + str(data.get("verdict")) + "]: "
                + "; ".join(added))
    except Exception as exc:  # noqa: BLE001 — disclosed, not fatal
        return f"present_but_failed:{exc}"


# ---------------------------------------------------------------- grind
def combo_list():
    combos = []
    for stop, (tp1n, tp1r, tp1f), (trn, tr), (tsn, tsm) in product(
            STOPS, TP1S, TRAILS, TSTOPS):
        combos.append({"id": f"stop{int(stop*100)}|{tp1n}|{trn}|{tsn}",
                       "stop": stop, "tp1_ret": tp1r, "tp1_frac": tp1f,
                       "trail": tr, "tmin": tsm})
    return combos


def grind_pnl_matrix(eps, combos):
    """Per-contract $ P&L matrix: rows = (combo x strike), cols = episodes."""
    n_eps = len(eps)
    rows = {}
    for ci, cfg in enumerate(combos):
        for s in STRIKE_LABELS:
            rows[(ci, s)] = np.full(n_eps, np.nan)
    for ei, e in enumerate(eps):
        mins = e["mins"]
        n_all = len(mins)
        ncaps = {}
        for tsn, tsm in TSTOPS:
            ncaps[tsm] = n_all if tsm is None else max(1, int((mins <= tsm).sum()))
        for s in STRIKE_LABELS:
            rets = e["rets"][s]
            if rets is None:
                continue
            p0 = e["prem0"][s]
            for ci, cfg in enumerate(combos):
                mult = walk_exit(rets, ncaps[cfg["tmin"]], cfg["stop"],
                                 cfg["tp1_ret"], cfg["tp1_frac"], cfg["trail"])
                rows[(ci, s)][ei] = 100.0 * p0 * (mult - 1.0)
    return rows


def cell_stats(vals: np.ndarray) -> dict:
    n = len(vals)
    if n == 0:
        return {"n": 0}
    total = float(vals.sum())
    top3 = np.sort(vals)[-3:]
    return {"n": n, "total": round(total, 2),
            "mean": round(float(vals.mean()), 2),
            "wr": round(100.0 * float((vals > 0).mean()), 1),
            "t": round(float(vals.mean() / (vals.std(ddof=1) / np.sqrt(n))), 3)
                 if n > 1 and vals.std(ddof=1) > 0 else 0.0,
            "drop_top3": round(total - float(top3[top3 > 0].sum()), 2)}


def main() -> None:
    t_start = _time.time()
    eps, drops, unpriceable = build_universe()
    n_eps = len(eps)
    is_test = np.array([e["is_test"] for e in eps])
    qty = np.array([e["first_qty"] for e in eps], dtype=float)
    print(f"[universe] episodes={n_eps} train={int((~is_test).sum())} "
          f"test={int(is_test.sum())} drops={drops} unpriceable={unpriceable}")

    filters = build_filters(eps)
    e6_status = maybe_e6_filters(eps, filters)
    print(f"[filters] n={len(filters)} e6={e6_status}")

    combos = combo_list()
    print(f"[grind] {len(combos)} exit combos x {len(STRIKE_LABELS)} strikes "
          f"x {n_eps} episodes ...")
    pnl = grind_pnl_matrix(eps, combos)
    print(f"[grind] pnl matrix done in {_time.time()-t_start:.1f}s")

    # ---------------- anchors: E2 (a)/(b) exact configs must reproduce
    e2 = json.loads((JWB / "E2-machine-management-replay.json").read_text())
    anchors = {}
    for lbl, strike in (("a_his_strike", "his"), ("b_atm_strike", "atm")):
        vals = []
        for ei, e in enumerate(eps):
            rets = e["rets"][strike]
            if rets is None:
                continue
            mult = walk_exit(rets, len(e["mins"]), -0.50, 0.30, 0.80, False,
                             runner_target=1.5)
            vals.append(e["first_qty"] * 100.0 * e["prem0"][strike] * (mult - 1.0))
        got_n, got_total = len(vals), float(np.sum(vals))
        exp = e2["e2"]["variants"][lbl]
        anchors[lbl] = {"n": got_n, "expected_n": exp["n"],
                        "total": round(got_total, 2),
                        "expected_total": exp["machine_total"],
                        "match": got_n == exp["n"]
                                 and abs(got_total - exp["machine_total"]) < 2.0}
        print(f"[anchor:{lbl}] n={got_n}/{exp['n']} "
              f"total={got_total:.2f}/{exp['machine_total']} "
              f"match={anchors[lbl]['match']}")
    assert all(a["match"] for a in anchors.values()), \
        "E2 anchor reproduction FAILED — engine bug, no results published"

    # ---------------- train grid
    grid_rows = []
    n_cells = 0
    n_train_positive = 0
    eligible = []
    for (ci, s), pc in pnl.items():
        ok = ~np.isnan(pc)
        for fname, fmask in filters.items():
            tr = ok & fmask & ~is_test
            te_n = int((ok & fmask & is_test).sum())
            for size in SIZES:
                w = qty if size == "first_fill" else (1.0 if size == "fixed_1" else 3.0)
                vals = pc[tr] * (w[tr] if size == "first_fill" else w)
                st = cell_stats(vals)
                n_cells += 1
                if st["n"] and st["mean"] > 0:
                    n_train_positive += 1
                row = {"combo": combos[ci]["id"], "strike": s, "filter": fname,
                       "size": size, "n_train": st["n"], "n_test_members": te_n,
                       **{f"train_{k}": v for k, v in st.items() if k != "n"}}
                # per-contract expectancy
                pc_vals = pc[tr]
                row["train_exp_per_contract"] = round(float(pc_vals.mean()), 2) \
                    if len(pc_vals) else None
                grid_rows.append(row)
                if (size != "fixed_3" and st["n"] >= MIN_N_TRAIN
                        and st.get("mean", 0) > 0 and st.get("drop_top3", 0) > 0
                        and te_n >= MIN_N_TEST):
                    eligible.append({**row, "ci": ci,
                                     "rank_t": st["t"]})
    grid = pd.DataFrame(grid_rows)
    with gzip.open(HERE / "train-grid.csv.gz", "wt", newline="") as fh:
        grid.to_csv(fh, index=False)
    print(f"[grid] cells={n_cells} train_positive={n_train_positive} "
          f"eligible={len(eligible)}")

    # ---------------- top-K selection (train only) with diversity caps
    eligible.sort(key=lambda r: r["rank_t"], reverse=True)
    topk, per_fs, per_f = [], {}, {}
    for r in eligible:
        kfs, kf = (r["filter"], r["strike"]), r["filter"]
        if per_fs.get(kfs, 0) >= DIV_PER_FILTER_STRIKE or \
           per_f.get(kf, 0) >= DIV_PER_FILTER:
            continue
        topk.append(r)
        per_fs[kfs] = per_fs.get(kfs, 0) + 1
        per_f[kf] = per_f.get(kf, 0) + 1
        if len(topk) >= K_MAX:
            break
    print(f"[topk] selected {len(topk)} cells")

    # ---------------- ONE test evaluation of top-K
    rng = np.random.default_rng(42)
    entry_ts_arr = np.array([e["entry_ts"].value for e in eps])
    for r in topk:
        pc = pnl[(r["ci"], r["strike"])]
        fmask = filters[r["filter"]]
        m = ~np.isnan(pc) & fmask & is_test
        idx = np.where(m)[0][np.argsort(entry_ts_arr[np.where(m)[0]])]
        w = qty[idx] if r["size"] == "first_fill" else \
            (np.ones(len(idx)) if r["size"] == "fixed_1" else np.full(len(idx), 3.0))
        vals = pc[idx] * w
        st = cell_stats(vals)
        n = st["n"]
        r["test"] = st
        r["test_exp_per_contract"] = round(float(pc[idx].mean()), 2) if n else None
        if n > 1 and np.std(vals, ddof=1) > 0:
            r["p"] = float(sstats.ttest_1samp(vals, 0.0, alternative="greater").pvalue)
        else:
            r["p"] = 1.0
        boot = rng.choice(vals, size=(10000, n), replace=True).sum(axis=1) \
            if n else np.array([0.0])
        r["p_boot_sum_le_0"] = round(float((boot <= 0).mean()), 4)
        h = n // 2
        r["half1_total"] = round(float(vals[:h].sum()), 2)
        r["half2_total"] = round(float(vals[h:].sum()), 2)
        # null diagnostic: opposite direction @ ATM through the same exit cfg
        cfg = combos[r["ci"]]
        nvals = []
        for ei in idx:
            e = eps[ei]
            ncap = len(e["mins"]) if cfg["tmin"] is None else \
                max(1, int((e["mins"] <= cfg["tmin"]).sum()))
            mult = walk_exit(e["null_rets"], ncap, cfg["stop"], cfg["tp1_ret"],
                             cfg["tp1_frac"], cfg["trail"])
            nvals.append(100.0 * e["null_prem0"] * (mult - 1.0))
        nvals = np.array(nvals) * w
        r["null_test_total"] = round(float(nvals.sum()), 2)
        r["null_dominated"] = bool(st.get("total", 0) <= r["null_test_total"])

    # ---------------- BH FDR across the K test p-values
    ps = np.array([r["p"] for r in topk])
    order = np.argsort(ps)
    K = len(topk)
    qs = np.empty(K)
    prev = 1.0
    for rank_i in range(K - 1, -1, -1):
        i = order[rank_i]
        q = min(prev, ps[i] * K / (rank_i + 1))
        qs[i] = q
        prev = q
    for r, q in zip(topk, qs):
        r["q"] = round(float(q), 4)
        t = r["test"]
        r["survivor"] = bool(
            r["q"] <= FDR_ALPHA and t.get("n", 0) >= MIN_N_TEST
            and t.get("drop_top3", -1) > 0
            and r["half1_total"] > 0 and r["half2_total"] > 0)

    survivors = [r for r in topk if r["survivor"]]
    test_positive = [r for r in topk if r["test"].get("total", 0) > 0]
    if survivors:
        verdict = "SURVIVORS_FOUND"
    elif eligible:
        verdict = "TRAIN_ONLY_MIRAGE" if not survivors else "SURVIVORS_FOUND"
    else:
        verdict = "NOTHING_POSITIVE"

    funnel = {"cells_ground": n_cells, "train_positive": n_train_positive,
              "eligible_after_gates": len(eligible), "top_k_tested": K,
              "test_positive_total": len(test_positive),
              "fdr_survivors": len(survivors)}
    runtime_s = round(_time.time() - t_start, 1)

    def cell_public(r):
        return {k: v for k, v in r.items() if k != "ci"}

    results = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "caveat": CAVEAT,
        "design": "analysis/j-webull/PHASEB-matrix/DESIGN.md (committed pre-grind)",
        "universe": {"episodes": n_eps, "train": int((~is_test).sum()),
                     "test": int(is_test.sum()), "drops": drops,
                     "unpriceable_by_strike": unpriceable},
        "e6_filter_status": e6_status,
        "anchors_e2_reproduction": anchors,
        "funnel": funnel,
        "verdict": verdict,
        "top_k": [cell_public(r) for r in topk],
        "survivors": [cell_public(r) for r in survivors],
        "runtime_seconds": runtime_s,
    }
    (HERE / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8")
    write_results_md(results)
    print(f"[done] verdict={verdict} funnel={funnel} runtime={runtime_s}s")


def write_results_md(res: dict) -> None:
    buf = io.StringIO()
    w = buf.write
    w("# Phase B — J-EDGE DEEP MATRIX: results (%s)\n\n" % res["generated"][:10])
    w("> ## ⚠ %s\n\n" % res["caveat"])
    w("> Pre-registered design: [DESIGN.md](DESIGN.md) — committed BEFORE the "
      "grind. Grinder: `matrix_grinder.py`. Full train grid: `train-grid.csv.gz`. "
      "JSON twin: `results.json`.\n\n")
    u = res["universe"]
    w("## Universe\n\n%d episodes replayed (train %d / test %d). Drops: %s. "
      "Unpriceable (BS prem < $0.05) by strike: %s.\n\n"
      % (u["episodes"], u["train"], u["test"], u["drops"],
         u["unpriceable_by_strike"]))
    w("E6 structure features at grind time: **%s**.\n\n" % res["e6_filter_status"])
    w("## E2 anchor reproduction (gate: must match before results count)\n\n")
    w("| Anchor | n (got/exp) | total (got/exp) | match |\n|---|---|---|---|\n")
    for lbl, a in res["anchors_e2_reproduction"].items():
        w("| %s | %d / %d | %+.2f / %+.2f | %s |\n"
          % (lbl, a["n"], a["expected_n"], a["total"], a["expected_total"],
             "PASS" if a["match"] else "FAIL"))
    f = res["funnel"]
    w("\n## The funnel (honest)\n\n")
    w("| Stage | count |\n|---|---|\n")
    w("| Cells ground (exit x strike x filter x size) | %d |\n" % f["cells_ground"])
    w("| Train-positive (mean > 0) | %d |\n" % f["train_positive"])
    w("| Eligible (n_train>=60, drop-top3>0, n_test>=30 members) | %d |\n"
      % f["eligible_after_gates"])
    w("| Top-K taken to test (ONE evaluation) | %d |\n" % f["top_k_tested"])
    w("| Test-positive (total > 0) | %d |\n" % f["test_positive_total"])
    w("| **BH-FDR survivors (q<=0.1 + drop-top3 + both halves)** | **%d** |\n\n"
      % f["fdr_survivors"])
    w("## VERDICT: **%s**\n\n" % res["verdict"])
    w("## Top-K test table\n\n")
    w("| # | cell (exit / strike / filter / size) | n_tr | train $/tr | train t "
      "| n_te | test $/tr | test total | drop-top3 | p | q | halves | null-dom "
      "| SURV |\n")
    w("|" + "---|" * 14 + "\n")
    for i, r in enumerate(sorted(res["top_k"], key=lambda x: x["q"]), 1):
        t = r["test"]
        w("| %d | `%s` %s %s %s | %d | %+.1f | %.2f | %d | %+.1f | %+.0f | "
          "%+.0f | %.3f | %.3f | %+.0f/%+.0f | %s | %s |\n"
          % (i, r["combo"].replace("|", "·"), r["strike"], r["filter"],
             r["size"], r["n_train"],
             r["train_mean"], r["train_t"], t.get("n", 0), t.get("mean", 0.0),
             t.get("total", 0.0), t.get("drop_top3", 0.0), r["p"], r["q"],
             r["half1_total"], r["half2_total"],
             "YES" if r["null_dominated"] else "no",
             "**YES**" if r["survivor"] else "no"))
    if res["survivors"]:
        w("\n## Survivors -> Phase-C port specs\n\n")
        for i, r in enumerate(res["survivors"], 1):
            t = r["test"]
            w("### C-spec %d: `%s` / strike=%s / filter=%s / size=%s\n\n"
              % (i, r["combo"].replace("|", "·"), r["strike"], r["filter"],
                 r["size"]))
            w("- Train: n=%d, %+.1f $/tr, t=%.2f. Test: n=%d, %+.1f $/tr, "
              "total %+.0f, WR %.1f%%, p=%.4f, q=%.4f, boot P(sum<=0)=%.4f, "
              "drop-top3 %+.0f, halves %+.0f/%+.0f, null_total %+.0f%s.\n"
              % (r["n_train"], r["train_mean"], r["train_t"], t["n"], t["mean"],
                 t["total"], t["wr"], r["p"], r["q"], r["p_boot_sum_le_0"],
                 t["drop_top3"], r["half1_total"], r["half2_total"],
                 r["null_test_total"],
                 " (NULL-DOMINATED — treat as ladder artifact)"
                 if r["null_dominated"] else ""))
            w("- **Detector (Phase C, 2025-26 OPRA):** J-entry-context screen = "
              "`%s`; strike rule = %s; exit = %s; size = %s. Validate on real "
              "fills per C1 before anything ships.\n\n"
              % (r["filter"], r["strike"], r["combo"], r["size"]))
    else:
        w("\n## Survivors\n\nNone. See verdict.\n")
    w("\n## Caveats\n\n- All E2 caveats inherit (BS-synthetic, VIX-open IV, 5m "
      "bar-close granularity, entry priced up to 5 min before his tick, "
      "non-0DTE force-flattened same day, r=4%).\n"
      "- Test year capacity: only broad filters can reach n_test>=30 (71 test "
      "episodes total) — registered in DESIGN.md before grinding.\n"
      "- fixed_3 size rows are 3x fixed_1 by construction (identical signal); "
      "excluded from ranking, present in the grid.\n"
      "- his-strike cells ride on mispriced BS entry premia (median "
      "BS/actual = 0.222, E2 calibration) — noisiest axis, drops adversely "
      "selective.\n"
      "- Null diagnostic per cell: opposite-direction ATM through the same exit "
      "cfg; null-dominated survivors are convexity-harvest artifacts, not "
      "J-direction edge.\n")
    w("\nRuntime: %.1f s, single process.\n" % res["runtime_seconds"])
    (HERE / "RESULTS.md").write_text(buf.getvalue(), encoding="utf-8")


if __name__ == "__main__":
    main()
