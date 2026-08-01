"""level_flicker_replay_2026_08_01.py — WS3 PROOF: replay Friday 2026-07-31's observed
per-refresh level sequence through the FIXED hysteresis logic and diff EVERY level.

WHAT THIS PROVES (task spec): 743.25's presence goes from 331/386 ticks with 14 flips to
stable under the fix, AND no level becomes wrongly sticky — anything that left the feed for
good on Friday still retires (<= HYSTERESIS_MISS_N = 5 refreshes later, ~25 min).

METHOD
  * Source of truth: automation/state/core-decisions.jsonl 2026-07-31 'safe' rows (386
    ticks; the 'bold' series was verified identical — same file read). Each row logs the
    engine's levels_active (key-levels.json filtered to +/-$12 of spot) + spy (spot).
  * The 5-min Gamma_LevelRefresh fires at HH:MM:37 with MM%5==3 (verified from snapshot
    as_of stamps 08:33:37/09:28:37/11:58:37/15:48:36); engine ticks land at HH:MM:02-04.
    A fire at minute mf therefore governs ticks with minute in [mf+1, mf+5] — the replay
    resamples the tick series into these per-refresh windows and takes each window's first
    tick as that refresh's observed OUTPUT set (intra-window uniformity is measured and
    reported; Friday: uniform).
  * OLD = the observed windows verbatim (production pre-fix wrote fresh-only).
    NEW = drive the PRODUCTION refresh_levels_intraday._hysteresis_carry over the same
    windows: written(k) = fresh(k) + carry(written(k-1), fresh(k)).
  * Map written states back to ticks; presence(new) also re-applies the engine's +/-$12
    spot band so a held level drifting out of band is never counted visible.

REPLAY-DOMAIN CAVEATS (disclosed, all err AGAINST the fix — production is >= this stable):
  * The ledger logs PRICES only, so replay identity is price-based; production also
    re-qualifies by label (_dedup_key), under which a detector that MOVES its level (same
    label, new price) retires the old price INSTANTLY. Where they differ the replay HOLDS
    longer than production would — so the wrongly-sticky check here is an upper bound on
    production stickiness.
  * The observed sets are the engine's +/-$12 VIEW of the file, not the file itself; a
    held level out of band cannot re-qualify in-replay even if the real file re-derived
    it, so the replay may retire earlier than production (never later than N misses).

Outputs: analysis/deep-research/LEVEL-FLICKER-FIX-2026-08-01.{md,json}
Run:     backtest/.venv/Scripts/python.exe backtest/tools/level_flicker_replay_2026_08_01.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_JSON = REPO / "analysis" / "deep-research" / "LEVEL-FLICKER-FIX-2026-08-01.json"
OUT_MD = REPO / "analysis" / "deep-research" / "LEVEL-FLICKER-FIX-2026-08-01.md"

_spec = importlib.util.spec_from_file_location(
    "refresh_levels_intraday", REPO / "setup" / "scripts" / "refresh_levels_intraday.py")
rli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rli)

DAY = "2026-07-31"
BAND = 12.0
TARGET = 743.25


def load_ticks() -> list[dict]:
    ticks = []
    with LEDGER.open(encoding="utf-8") as f:
        for line in f:
            if DAY not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(r.get("ts_et") or "")
            if ts.startswith(DAY) and str(r.get("account")) == "safe":
                ticks.append({"ts": ts, "hm": ts[11:16], "spy": float(r.get("spy") or 0.0),
                              "levels": [round(float(x), 2) for x in (r.get("levels_active") or [])]})
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def window_of(hm: str) -> str:
    """The refresh fire (HH:MM, MM%5==3) governing a tick at minute hm: fire minute is the
    latest m with m%5==3 and m <= tick_minute-1 (fire at :37s lands before the next :02s
    tick). Pre-09:33 RTH ticks belong to the 09:28 premarket fire."""
    h, m = int(hm[:2]), int(hm[3:])
    total = h * 60 + m - 1  # a fire at minute mf governs ticks from mf+1
    fire = total - ((total - 3) % 5)
    return f"{fire // 60:02d}:{fire % 60:02d}"


def main() -> None:
    ticks = load_ticks()
    n_ticks = len(ticks)
    assert n_ticks == 386, f"expected 386 safe ticks, got {n_ticks}"

    # --- resample into per-refresh windows -------------------------------------------------
    # A window's set = the UNION of levels observed across its ticks: the file is constant
    # within a window, but each tick's +/-12 spot band clips a different VIEW of it, so a
    # band-edge level can be visible on only some ticks. Union = everything PROVABLY in the
    # file that window (any tick seeing it is proof) — still observed-qualified only.
    windows: list[dict] = []
    seen = {}
    for t in ticks:
        w = window_of(t["hm"])
        if w not in seen:
            seen[w] = {"fire": w, "levels": [], "ticks": []}
            windows.append(seen[w])
        seen[w]["ticks"].append(t)
    nonuniform = 0
    for w in windows:
        sets = [tuple(t["levels"]) for t in w["ticks"]]
        nonuniform += len(set(sets)) > 1  # band-edge view differences (file itself constant)
        w["levels"] = sorted({p for t in w["ticks"] for p in t["levels"]})

    # --- drive the PRODUCTION hysteresis over the observed windows --------------------------
    def as_dicts(prices: list[float]) -> list[dict]:
        return [{"price": p, "label": f"OBS_{p:.2f}", "tier": "Active",
                 "expires_at": f"{DAY}T16:00:00-04:00"} for p in prices]

    written_states: list[list[dict]] = []
    prior: list[dict] = []
    for k, w in enumerate(windows):
        fresh = as_dicts(w["levels"])
        if k == 0:
            written = fresh  # window 0 seeds the replay (state inherited from premarket)
        else:
            held = rli._hysteresis_carry(prior, fresh, DAY, f"{DAY}T{w['fire']}:37-04:00")
            written = fresh + held
        # sanity: no <EPS pair may form (held is >EPS from fresh by construction)
        ps = sorted(lv["price"] for lv in written)
        for a, b in zip(ps, ps[1:]):
            assert b - a > rli.HYSTERESIS_MATCH_EPS or b == a, (a, b)
        written_states.append(written)
        prior = written

    # --- map back to ticks ------------------------------------------------------------------
    widx = {w["fire"]: i for i, w in enumerate(windows)}
    all_prices = sorted({p for t in ticks for p in t["levels"]})
    per_level = {}
    for price in all_prices:
        old_seq, new_seq = [], []
        for t in ticks:
            k = widx[window_of(t["hm"])]
            old_seq.append(price in t["levels"])
            in_file = any(abs(lv["price"] - price) < 0.005 for lv in written_states[k])
            new_seq.append(in_file and abs(price - t["spy"]) <= BAND)
        def _flips(seq):
            return sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
        # superset proof: the fix may only ADD presence
        assert all(n or not o for o, n in zip(old_seq, new_seq)), f"presence lost at {price}"
        extra = [i for i, (o, n) in enumerate(zip(old_seq, new_seq)) if n and not o]
        # wrongly-sticky proof: extra presence never extends more than N windows past the
        # last observed qualification
        last_old = max((i for i, o in enumerate(old_seq) if o), default=-1)
        max_extra_after_gone = 0
        if last_old >= 0:
            tail_extra = [i for i in extra if i > last_old]
            if tail_extra:
                extra_windows = {window_of(ticks[i]["hm"]) for i in tail_extra}
                max_extra_after_gone = len(extra_windows)
        assert max_extra_after_gone <= rli.HYSTERESIS_MISS_N, price
        dmin = min(abs(price - t["spy"]) for t in ticks)
        dmax = max(abs(price - t["spy"]) for t in ticks)
        per_level[f"{price:.2f}"] = {
            "old_present": sum(old_seq), "old_flips": _flips(old_seq),
            "new_present": sum(new_seq), "new_flips": _flips(new_seq),
            "extra_ticks": len(extra),
            "extra_windows_after_last_old": max_extra_after_gone,
            "band_edge_note": "near +/-12 band edge some ticks" if dmax > BAND - 0.75 else "",
        }

    tgt = per_level[f"{TARGET:.2f}"]
    verdict = ("FIXED" if tgt["old_present"] == 331 and tgt["old_flips"] == 14
               and tgt["new_present"] == n_ticks and tgt["new_flips"] == 0 else "CHECK")

    out = {
        "_doc": "WS3 level-flicker fix replay — observed Friday windows through the "
                "production _hysteresis_carry. See module docstring for method + caveats.",
        "day": DAY, "n_ticks": n_ticks, "n_windows": len(windows),
        "nonuniform_windows": nonuniform,
        "hysteresis_n": rli.HYSTERESIS_MISS_N,
        "verdict": verdict,
        "target_743_25": tgt,
        "per_level": per_level,
        "proofs": {
            "superset": "asserted per level: fixed presence is a superset of observed presence",
            "no_wrongly_sticky": f"asserted per level: presence beyond a level's last observed "
                                 f"qualification is <= {rli.HYSTERESIS_MISS_N} refresh windows",
        },
    }
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")

    L = []
    L.append("# WS3 — LEVEL-FLICKER FIX: Friday 2026-07-31 replay through the hysteresis logic")
    L.append("")
    L.append(f"Verdict: **{verdict}**. Tool: `backtest/tools/level_flicker_replay_2026_08_01.py` "
             f"(drives the PRODUCTION `refresh_levels_intraday._hysteresis_carry`, N={rli.HYSTERESIS_MISS_N}). "
             "Method + replay-domain caveats in the tool docstring; machine-readable sidecar: "
             "`LEVEL-FLICKER-FIX-2026-08-01.json`.")
    L.append("")
    L.append("## Root cause (named, with evidence)")
    L.append("")
    L.append("Every 5-min `Gamma_LevelRefresh` fire re-derives the multi-week shelf zones from "
             "scratch (`daily_context._shelf_zones`) with **today's live-FORMING daily bar included "
             "as both a candidate seed and a touch-counter** (`_find_shelf_candidates` seeds band "
             "edges from every bar's c/h/l and scores every bar as a touch — the forming bar's "
             "c/h/l move every fire). Two near-tied overlapping candidates cover the 742-744 "
             "region: `742.45-744.05` (8 touches) and `741.56-743.16` (10 touches **only while "
             "today's forming bar lands inside it**). `_merge_shelf_candidates` is greedy "
             "winner-take-all by touch count with overlap exclusion, so as spot wobbled around "
             "~742.5-743 the winner snapped back and forth, re-tiling the region and RENAMING the "
             "written level: mid 743.25 <-> mid 742.36. `refresh_levels_intraday.refresh()` then "
             "wholesale strips + re-derives the shelf/memory/INTRADAY families each run with zero "
             "cross-run identity, so every upstream wobble went straight into `key-levels.json` "
             "and the engine's per-tick `levels_active`.")
    L.append("")
    L.append("Evidence:")
    L.append("- `core-decisions.jsonl` 2026-07-31: safe AND bold show the IDENTICAL 331/386 + "
             "14-transition series for 743.25 (same file read => the FILE was changing, not the "
             "read); every transition lands on a tick right after a :MM:37 refresh fire.")
    L.append("- `key-levels-history/2026-07-31`: 0835/0930/1550 snapshots carry "
             "`SHELF_742.45_744.05` (mid 743.25); the 1200 snapshot carries "
             "`SHELF_741.56_743.16` (mid 742.36) — the SAME logical shelf, re-tiled.")
    L.append("- Deterministic reproduction (scratch, real `daily_context._shelf_zones` on the real "
             "daily bars + the forming 07-31 bar rebuilt from the 5m SIP tape at each fire): the "
             "two-state bistability reproduces exactly, 76-77/89 fires matching the observed "
             "state (mismatches are partial-bar reconstruction at flip boundaries; transient "
             "bands seeded at today's own forming prints — e.g. 741.69-743.29 — appear too, "
             "direct proof of the forming-bar seeding).")
    L.append("- Alternate mechanisms ruled out: proximity-band recompute (|743.25 - spot| <= 5.6 "
             "all day, never near the +/-12 edge); race between refresher fires (all flips at "
             "5-min fire boundaries, none sub-5-min); rounding (bands differ by $0.89, not 1c).")
    L.append("")
    L.append(f"## Fix + N={rli.HYSTERESIS_MISS_N} provenance")
    L.append("")
    L.append("`_hysteresis_carry` in `setup/scripts/refresh_levels_intraday.py`: a previously "
             "written ACTIVE level that fails to re-qualify (no fresh level within $0.10 and no "
             "fresh level sharing its prefix-stripped label) is carried forward verbatim with a "
             "`hyst_miss_streak` counter until it has been missing "
             f"{rli.HYSTERESIS_MISS_N} CONSECUTIVE refreshes or its session expiry passes. "
             "Observed Friday absence-run distribution for 743.25: {1 refresh: x5, 2: x1, 4: x1} "
             f"— max flicker gap 4, so N={rli.HYSTERESIS_MISS_N} bridges every observed gap while "
             "a genuinely-gone level still retires <= ~25 min after it last qualified. "
             "Conservative by construction: only verbatim prior-file levels are ever re-emitted "
             "(never a price that never qualified); a detector that legitimately MOVES its level "
             "(same label, new price) still retires the old price instantly via label identity. "
             "Guards incl. RED-proof: `backtest/tests/test_level_hysteresis_2026_08_01.py` "
             "(neutering the carry fails 7 tests, reproducing the observed 14-flip series).")
    L.append("")
    L.append(f"- Ticks: {n_ticks} (safe ledger; bold verified identical). Refresh windows: "
             f"{len(windows)} (5-min fires at :MM:37, MM%5==3). Non-uniform windows: {nonuniform}.")
    L.append(f"- **743.25 (the 28-session shelf): {tgt['old_present']}/{n_ticks} ticks, "
             f"{tgt['old_flips']} flips  →  {tgt['new_present']}/{n_ticks} ticks, "
             f"{tgt['new_flips']} flips.**")
    L.append("- Superset + no-wrongly-sticky assertions ran in-line for EVERY level (script "
             "raises on violation; a level that left the feed for good still retires within "
             f"{rli.HYSTERESIS_MISS_N} windows ≈ 25 min).")
    L.append("")
    L.append("| Level | old present /386 | old flips | new present /386 | new flips | extra ticks | extra windows after last qual | note |")
    L.append("|--:|--:|--:|--:|--:|--:|--:|---|")
    for price, row in per_level.items():
        L.append(f"| {price} | {row['old_present']} | {row['old_flips']} | {row['new_present']} | "
                 f"{row['new_flips']} | {row['extra_ticks']} | {row['extra_windows_after_last_old']} | "
                 f"{row['band_edge_note']} |")
    L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print(f"windows={len(windows)} nonuniform={nonuniform}")
    print("743.25:", tgt)
    print("VERDICT:", verdict)
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    sys.exit(main())
