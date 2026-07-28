"""ladder_subset_prereg.py -- EXECUTOR for the FROZEN queue item LADDER-SUBSET-PREREG
(automation/overnight/queue.md, filed 2026-07-27 ~23:35 ET at DISARM time, BEFORE any
per-trade slicing of the replay JSON was read).

FROZEN HYPOTHESIS (quoted verbatim from the queue item; stated from the 2026-07-27 09:40
incident anatomy, NOT from the data):

    "entries restricted to bear_score >= 9 AND 'confluence' in bear_triggers_raw AND
     htf_15m == 'BEAR' at the trigger tick."

FROZEN PASS BAR (same queue item):

    "positive aggregate AND day-majority AND survives-drop-best on the SAME replay
     population (analysis/arm-ladder/LADDER-FULLHIST-2026-07-27.json per-trade detail),
     held-out last-25% split reported separately. If it fails: the ladder concept is dead
     at every granularity we can currently express -- record the null and stop."

POPULATION -- lane floor=9 of LADDER-FULLHIST-2026-07-27.json (the bear_score>=9 lane,
walked one-position-at-a-time with real-OPRA fills by backtest/tools/ladder_fullhist_replay.py).
This is a PURE SLICE of already-walked trades (descriptive attribution per the repo's
discipline: slicing existing trades by pre-existing fields is not search). Every trade in the
subset was actually walked through walk_exit_manager with real OPRA fills; the slice only
REMOVES trades, never invents fills.

HTF RE-DERIVATION (the one field the replay's trade records did not copy out):
lane trades carry trigger_bar_idx = orchestrator bar_idx into the RTH-reindexed frame
(orchestrator.py:805-810 rebuilds spy_df via rth_mask+reset_index; ladder_fullhist_replay.py
build_rth_frame reproduces that frame byte-identically for its own lookups). The base decision
row DOES carry htf_15m_stack (orchestrator.py:1115) sourced from
_precompute_htf_15m_stacks(spy_df)[idx] (orchestrator.py:839 -> :970) -- so recomputing
_precompute_htf_15m_stacks over the SAME reconstructed RTH frame and indexing at
trigger_bar_idx reproduces EXACTLY the value the replay's scoring ctx carried at the trigger
tick. C6 note: stacks[i] uses 15m bars formed from 5m closes up to and including bar i's own
close (searchsorted side='right' - 1, causal EMA) -- the orchestrator's own live-matching
convention, inherited, not re-derived. Alignment is HARD-ASSERTED per referenced bar:
spy_rth.iloc[trigger_bar_idx].timestamp_et must equal the JSON row's trigger_time_et, else
abort (no silent misalignment).

CELLS RUN (ALL reported, nulls included -- no cherry-picking):
  PRIMARY   lane9 trades  AND subset_match            <- the frozen hypothesis, pass bar applies
  INTERMED  lane9 trades  AND confluence (any HTF)    <- decomposition disclosure
  INTERMED  lane9 trades  AND htf==BEAR (any trigger) <- decomposition disclosure
  SENSITIV  lane7/lane8 trades AND subset_match       <- same rule under those lanes' own
            serialization (different NOT_FLAT skipping); sensitivity only, NOT the pass-bar cell
  DISCLOSE  lane9 excluded synthetic-priced candidates matching subset (count only, no P&L --
            real-OPRA-only P&L per C1)

KNOWN CAVEATS carried forward from the parent replay (disclosed, not hidden):
  - Serialization: lane9's NOT_FLAT skipping was driven by the BROADER floor-9 rule; a lane9
    position opened by a non-subset trade can have blocked a subset candidate (such skips were
    not recorded at all). The slice therefore under-represents what a subset-ONLY lane would
    have traded. If the slice PASSED the bar, a dedicated re-walk would be the confirmation
    step before any re-arm proposal; a slice FAIL needs no re-walk (removing blockers only adds
    candidates the broader lane never even reached -- it cannot rescue the cohort's per-trade
    economics).
  - Entry-layer feed provenance: the replay's own 2026-07-27 09:40 calibration row scores 8,
    blockers [5,9] vs the pinned live incident's 9/[5] (cached bar not byte-identical to the
    live IEX bar -- known, root-caused in analysis/arm-ladder/ARM-LADDER-V1-2026-07-27.md).
    The incident bar that MOTIVATED this hypothesis does not itself qualify at floor 9 in this
    replay population.

Run: backtest/.venv/Scripts/python.exe backtest/tools/ladder_subset_prereg.py
Outputs: analysis/arm-ladder/LADDER-SUBSET-VERDICT-2026-07-28.{json,md}
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]            # backtest/
ROOT = REPO.parent                                      # repo root
for _p in (str(ROOT), str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

IN_JSON = ROOT / "analysis" / "arm-ladder" / "LADDER-FULLHIST-2026-07-27.json"
OUT_DIR = ROOT / "analysis" / "arm-ladder"
OUT_JSON = OUT_DIR / "LADDER-SUBSET-VERDICT-2026-07-28.json"
OUT_MD = OUT_DIR / "LADDER-SUBSET-VERDICT-2026-07-28.md"

FROZEN_HYPOTHESIS = (
    "entries restricted to bear_score >= 9 AND 'confluence' in bear_triggers_raw AND "
    "htf_15m == 'BEAR' at the trigger tick"
)
FROZEN_PASS_BAR = (
    "positive aggregate AND day-majority AND survives-drop-best on the SAME replay population "
    "(LADDER-FULLHIST-2026-07-27.json per-trade detail), held-out last-25% reported separately"
)
FROZEN_HELD_OUT_CUTOFF = dt.date(2026, 3, 6)   # must match the parent JSON's held_out_split


def log(msg: str) -> None:
    print(f"[ladder-subset] {msg}", flush=True)


# ======================================================================== pure logic (unit-tested)

def subset_match(bear_score: int, triggers_raw: list, htf_15m: Optional[str]) -> bool:
    """The frozen hypothesis, verbatim: score>=9 AND confluence in raw triggers AND HTF BEAR."""
    return (
        bear_score >= 9
        and "confluence" in (triggers_raw or [])
        and htf_15m == "BEAR"
    )


def check_alignment(spy_rth, rows: list[dict]) -> None:
    """HARD assert: every referenced trigger_bar_idx must land on the exact bar whose
    timestamp the parent replay recorded. Raises AssertionError on the first mismatch --
    a misaligned frame would silently attach the WRONG bar's HTF stack to every trade."""
    for r in rows:
        idx = r["trigger_bar_idx"]
        ts = spy_rth.iloc[idx]["timestamp_et"]
        ts_naive = ts.tz_localize(None) if getattr(ts, "tzinfo", None) is not None else ts
        got = ts_naive.isoformat()
        want = r["trigger_time_et"]
        if got != want:
            raise AssertionError(
                f"bar_idx alignment broken at trigger_bar_idx={idx}: frame has {got}, "
                f"parent JSON recorded {want} -- refusing to attach HTF stacks to a "
                f"misaligned frame"
            )


def slice_trades(trades: list[dict], stacks: list[Optional[str]]) -> list[dict]:
    """Apply the frozen subset filter to already-walked trades; annotates htf_15m per trade."""
    out = []
    for t in trades:
        htf = stacks[t["trigger_bar_idx"]]
        if subset_match(t["bear_score"], t["triggers_raw"], htf):
            row = dict(t)
            row["htf_15m"] = htf
            out.append(row)
    return out


def held_out_cutoff_from_parent(parent: dict) -> dt.date:
    """The parent replay froze the split; re-read it and hard-check against this tool's own
    frozen constant so a silently regenerated parent can't move the split under us."""
    cutoff = dt.date.fromisoformat(parent["held_out_split"]["cutoff_date"])
    if cutoff != FROZEN_HELD_OUT_CUTOFF:
        raise AssertionError(
            f"parent held-out cutoff {cutoff} != frozen {FROZEN_HELD_OUT_CUTOFF} -- the parent "
            f"JSON is not the population this pre-registration froze against"
        )
    return cutoff


# ================================================================================ main

def main() -> int:
    t0 = time.time()
    log(f"loading parent replay population: {IN_JSON}")
    parent = json.loads(IN_JSON.read_text(encoding="utf-8"))
    cutoff = held_out_cutoff_from_parent(parent)

    # Heavy imports deferred so the unit tests can import the pure functions cheaply.
    import ladder_fullhist_replay as lfr
    from lib.orchestrator import _precompute_htf_15m_stacks

    log("rebuilding the SAME RTH frame the parent replay's bar_idx space points into")
    spy_df_raw, _vix_df = lfr.load_extended_data()
    spy_rth = lfr.build_rth_frame(spy_df_raw)
    log(f"  {len(spy_rth)} RTH rows")

    lane9 = parent["lanes"]["9"]
    all_rows = list(lane9["trades"]) + list(lane9["excluded"])
    for f in ("7", "8"):
        all_rows += [t for t in parent["lanes"][f]["trades"] if t["bear_score"] >= 9]
    log(f"alignment check on {len(all_rows)} referenced bars (lane9 trades+excluded, "
        f"lane7/8 score>=9 trades)")
    check_alignment(spy_rth, all_rows)
    log("  alignment PASS (every trigger_bar_idx lands on its recorded timestamp)")

    log("recomputing _precompute_htf_15m_stacks over the reconstructed frame "
        "(identical code path to orchestrator.py:839)")
    stacks = _precompute_htf_15m_stacks(spy_rth)

    all_calendar_dates = sorted(spy_rth["timestamp_et"].dt.date.unique())

    # ---- cells --------------------------------------------------------------------
    lane9_trades = lane9["trades"]

    primary = slice_trades(lane9_trades, stacks)
    interm_confluence = [dict(t, htf_15m=stacks[t["trigger_bar_idx"]]) for t in lane9_trades
                          if "confluence" in (t["triggers_raw"] or [])]
    interm_htf_bear = [dict(t, htf_15m="BEAR") for t in lane9_trades
                        if stacks[t["trigger_bar_idx"]] == "BEAR"]
    sens7 = slice_trades(parent["lanes"]["7"]["trades"], stacks)
    sens8 = slice_trades(parent["lanes"]["8"]["trades"], stacks)

    # HTF distribution across lane9's confluence trades (visibility on the gate's bite)
    htf_dist: dict[str, int] = {}
    for t in interm_confluence:
        k = str(t["htf_15m"])
        htf_dist[k] = htf_dist.get(k, 0) + 1

    # Excluded-synthetic disclosure (count only; C1 real-OPRA-only P&L)
    excl_subset = [e for e in lane9["excluded"]
                    if subset_match(e["bear_score"], e["triggers_raw"],
                                     stacks[e["trigger_bar_idx"]])]

    cells = {}
    for name, rows in (
        ("PRIMARY_lane9_subset", primary),
        ("INTERMED_lane9_confluence_anyHTF", interm_confluence),
        ("INTERMED_lane9_htfBEAR_anyTrigger", interm_htf_bear),
        ("SENSITIVITY_lane7_subset", sens7),
        ("SENSITIVITY_lane8_subset", sens8),
    ):
        stats = lfr.lane_stats(rows, all_calendar_dates, cutoff)
        cells[name] = {"stats": stats, "n": len(rows)}
        log(f"  {name}: n={stats['n_trades']} total_pnl=${stats['total_pnl']:+.2f} "
            f"WR={stats['win_rate']} day_majority={stats['day_majority']['is_majority']} "
            f"drop_best_survives={stats['survives_dropping_best_trade']['still_positive']} "
            f"held_out=${stats['held_out_last_25pct']['total_pnl']:+.2f}"
            f"/{stats['held_out_last_25pct']['n_trades']}tr")

    p = cells["PRIMARY_lane9_subset"]["stats"]
    gate_positive = p["total_pnl"] > 0
    gate_daymaj = bool(p["day_majority"]["is_majority"])
    gate_dropbest = bool(p["survives_dropping_best_trade"]["still_positive"])
    passed = gate_positive and gate_daymaj and gate_dropbest

    verdict = {
        "passed": passed,
        "gates": {
            "positive_aggregate": gate_positive,
            "day_majority": gate_daymaj,
            "survives_drop_best": gate_dropbest,
        },
        "held_out_last_25pct_reported_separately": p["held_out_last_25pct"],
        "frozen_consequence_on_fail": (
            "the ladder concept is dead at every granularity we can currently express -- "
            "record the null and stop"
        ),
    }

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "frozen_hypothesis": FROZEN_HYPOTHESIS,
        "frozen_pass_bar": FROZEN_PASS_BAR,
        "population": {
            "source": str(IN_JSON.relative_to(ROOT)),
            "lane": "9 (floor=9, bear_score>=9 by construction)",
            "n_lane9_trades": len(lane9_trades),
            "lane9_total_pnl": parent["lanes"]["9"]["stats"]["total_pnl"],
            "held_out_cutoff": cutoff.isoformat(),
        },
        "htf_derivation": {
            "method": ("_precompute_htf_15m_stacks over the reconstructed RTH frame, indexed at "
                        "trigger_bar_idx -- identical code path to what fed the scoring ctx "
                        "(orchestrator.py:839,970,1115)"),
            "alignment_check": f"PASS on {len(all_rows)} referenced bars (timestamp-exact)",
        },
        "htf_distribution_of_lane9_confluence_trades": htf_dist,
        "verdict": verdict,
        "cells": cells,
        "primary_trades": primary,
        "excluded_synthetic_matching_subset": {
            "n": len(excl_subset),
            "note": "disclosure only -- real-OPRA fills only in P&L (C1); these had no cached "
                     "OPRA bar and are never blended",
        },
        "runtime_seconds": round(time.time() - t0, 1),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"VERDICT: {'PASS' if passed else 'FAIL'} "
        f"(positive={gate_positive} day_majority={gate_daymaj} drop_best={gate_dropbest})")
    return 0


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    return f"+${v:.2f}" if v >= 0 else f"-${abs(v):.2f}"


def write_markdown(out: dict) -> None:
    v = out["verdict"]
    p = out["cells"]["PRIMARY_lane9_subset"]["stats"]
    L = ["# LADDER-SUBSET-PREREG verdict -- 2026-07-28", ""]
    L.append(f"Generated {out['generated_at']}. Runner: `backtest/tools/ladder_subset_prereg.py` "
              f"({out['runtime_seconds']}s). Population: `{out['population']['source']}` lane 9.")
    L.append("")
    L.append("## Verdict first")
    L.append("")
    if v["passed"]:
        L.append("**PASS** -- the frozen subset clears all three gates on the replay population. "
                  "Next step per the pre-registration: dedicated subset-only re-walk (serialization "
                  "confirmation), then a min-size one-arm re-arm proposal to J with both numbers "
                  "side by side.")
    else:
        L.append("**FAIL -- the ladder concept is dead at every granularity we can currently "
                  "express.** (The frozen consequence, recorded as written.)")
    L.append("")
    g = v["gates"]
    L.append(f"- positive_aggregate: **{g['positive_aggregate']}** (total {_fmt(p['total_pnl'])} "
              f"on {p['n_trades']} trades, WR {p['win_rate']})")
    dm = p["day_majority"]
    L.append(f"- day_majority: **{g['day_majority']}** ({dm['win_days']}/{dm['total_trading_days']} "
              f"win days)")
    db = p["survives_dropping_best_trade"]
    L.append(f"- survives_drop_best: **{g['survives_drop_best']}** (best trade "
              f"{_fmt(db['best_trade_pnl'])}, total minus best {_fmt(db['total_minus_best'])})")
    ho = p["held_out_last_25pct"]
    L.append(f"- held-out last 25% (cutoff {ho['cutoff_date']}, reported separately per the "
              f"pre-reg): {ho['n_trades']}tr {_fmt(ho['total_pnl'])} WR {ho['win_rate']}")
    L.append("")
    L.append("## Frozen hypothesis (queue.md, filed 2026-07-27 ~23:35 ET at disarm time)")
    L.append("")
    L.append(f"> {out['frozen_hypothesis']}")
    L.append(f">")
    L.append(f"> Pass bar: {out['frozen_pass_bar']}")
    L.append("")
    L.append("## All cells run (nulls included)")
    L.append("")
    L.append("| Cell | N | Total P&L | WR | Day-majority | Drop-best survives | Held-out (last 25%) |")
    L.append("|---|---|---|---|---|---|---|")
    for name, cell in out["cells"].items():
        s = cell["stats"]
        dm = s["day_majority"]
        db = s["survives_dropping_best_trade"]
        ho = s["held_out_last_25pct"]
        L.append(f"| {name} | {s['n_trades']} | {_fmt(s['total_pnl'])} | {s['win_rate']} | "
                  f"{dm['win_days']}/{dm['total_trading_days']} ({dm['is_majority']}) | "
                  f"{db['still_positive']} | {ho['n_trades']}tr {_fmt(ho['total_pnl'])} |")
    L.append("")
    L.append(f"HTF-15m distribution across lane9 confluence trades: "
              f"`{out['htf_distribution_of_lane9_confluence_trades']}`")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    L.append("- **Population + serialization**: pure slice of lane 9's already-walked trades "
              "(real OPRA fills, walk_exit_manager exits). Lane 9's NOT_FLAT skipping was driven "
              "by the broader floor-9 rule, so the slice under-represents a subset-only lane's "
              "participation; a slice FAIL is still decisive on the cohort's per-trade economics "
              "(see module docstring).")
    L.append("- **HTF re-derivation**: " + out["htf_derivation"]["method"] + ". Alignment: "
              + out["htf_derivation"]["alignment_check"] + ".")
    L.append(f"- **Synthetic-priced candidates matching the subset**: "
              f"{out['excluded_synthetic_matching_subset']['n']} (disclosure only, never in P&L -- C1).")
    L.append("- **Incident-bar caveat**: the 2026-07-27 09:40 bar that motivated this hypothesis "
              "scores 8 (blockers [5,9]) in this replay vs 9 ([5]) live -- known feed-provenance "
              "gap (ARM-LADDER-V1-2026-07-27.md); the motivating bar itself is NOT in the "
              "population. The hypothesis was still tested exactly as frozen.")
    L.append("- Entry+1 convention, structure-stop RIBBON_RIDE exit shape, ATM strike, "
              "min-size 3 contracts -- all inherited unchanged from the parent replay.")
    L.append("")
    L.append("## Honest read")
    L.append("")
    ho_all_pos = all(c["stats"]["held_out_last_25pct"]["total_pnl"] > 0
                      for c in out["cells"].values()
                      if c["stats"]["held_out_last_25pct"]["n_trades"] > 0)
    full_all_fail = not out["verdict"]["passed"]
    if ho_all_pos and full_all_fail:
        L.append("Every cell's held-out window (last 25% by date, cutoff "
                  f"{p['held_out_last_25pct']['cutoff_date']}) is POSITIVE while the full window "
                  "fails all three gates -- the same signature the parent lane 9 shows "
                  "(full -$10,903.50 / held-out +$2,866.00). That is a REGIME observation, "
                  "reported separately exactly as the pre-registration required. It does NOT "
                  "rescue the frozen hypothesis: the pass bar was the full population, and a "
                  "'recent-window-only' variant would be a NEW hypothesis needing its own "
                  "pre-registration BEFORE anyone looks at how to cut the window -- this file "
                  "must not be that pre-registration, because the cut is now data-suggested. "
                  "The frozen consequence stands as written.")
    else:
        L.append("Verdict as tabulated above; no held-out/full-window divergence pattern "
                  "beyond what the table already shows.")
    L.append("")
    L.append("---")
    L.append("_Full per-trade subset detail: `analysis/arm-ladder/LADDER-SUBSET-VERDICT-2026-07-28.json` "
              "(`primary_trades`)._")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
