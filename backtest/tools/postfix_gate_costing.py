"""postfix_gate_costing.py -- window-scoped refusal costing for EVERY entry gate/filter.

Born Lane 1, 2026-08-04 ("make sure nothing is gated that actually works", J week
directive): the nightly gate-expiry instrument mines only SKIP_* verdicts, so the
10/11-filter checklist (which refuses via HOLD rows with per-door blocker lists, not SKIP
verdicts) had NO refusal-costing instrument at all. This tool closes that gap for any
window (default: the post-level-feed-fix era 2026-07-31..2026-08-03).

Reuses gate_expiry_check's machinery byte-for-bit (armed=True rows, 15-min event
clustering, stale-bar drop). Parts:
  A. core SKIP-verdict gates (whatever fired in the window, regardless of current armed
     flag -- unlike the nightly, which INERTs a now-disarmed gate and loses its history)
  B. filter sole-blocker cohorts from HOLD rows, per door (bear/bull) x filter 1..11:
     rows where the checklist failed on EXACTLY ONE filter -- the honest per-filter
     binding cohort (multi-blocker rows are cascade cohorts, C15: no single filter may
     claim them; census reported separately, the bear [5,8] both-lifted cell priced as
     ORACLE only)
  C. fleet SKIP_MIN_PREMIUM_FLOOR events priced at the counterfactual ATM strike (what
     ATM-TIER-EXTENSION-2K-10K plans) -- SIM label, per-event independent (no
     NOT_FLAT sequencing), refused OTM quote recorded alongside.

Output: analysis/recommendations/gate-postfix-costing-<end>.json (or --out).
Never blocks, never kills, never edits params -- a report, same doctrine as the nightly.

SOUNDNESS FIX (POSTFIX-GATE-COSTING-UNSOUND-REPLAY, 2026-08-08 night, filed the SAME
session `backtest/autoresearch/gate_expiry_check.py` was fixed, commit 97a2e2ac):
this tool used to forward-replay every refused signal via `gate_expiry_check.simulate_event`,
which is `lib.simulator_real.simulate_trade_real` under the hood -- the SAME unsound engine
(exit-shape divergence from the real production exit_manager, 2026-07-17 FRAME AUDIT;
same-bar/intrabar look-ahead, BACKTESTING-PLAYBOOK.md 2.12) that was just removed from the
gate-expiry instrument. `simulate_event` was kept in `gate_expiry_check.py` UNCHANGED purely
because this file imported it -- this fix removes that import and, with it, the last live
caller of the unsound path. Every call site (Part A, Part B, the bear[5,8] ORACLE cell, Part
C) now replays through `backtest/lib/exit_manager_walk.walk_exit_manager` (the ACTUAL
production `exit_manager.plan_exit_actions` core) via a lazy import of
`backtest/tools/gate_revalidation_ab.py`'s `replay_row`/`account_config`/`build_ribbon_lookup`
-- byte-for-byte the same lazy-import-to-avoid-circularity pattern, and the same sound path,
`gate_expiry_check.py::evaluate_gate_pnl` now uses. Every EV-bearing section this script
writes (part_a[action], part_b[key], oracle_bear_5_8[account], part_c[arm]) is stamped
`replay_engine`/`replay_soundness` so a future reader can never mistake a freshly-computed
number for one produced by the retired path. Guard: `backtest/tests/test_postfix_gate_costing.py`
(spies on `lib.simulator_real.simulate_trade_real`, asserts it is never called).

Run: backtest/.venv/Scripts/python.exe backtest/tools/postfix_gate_costing.py
     [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch.gate_expiry_check import (  # noqa: E402
    CORE_DECISIONS, EVENT_CLUSTER_GAP_MINUTES, cluster_events, load_decision_rows,
)
from autoresearch.recency_check import (  # noqa: E402
    load_merged_spy_vix, window_metrics,
)
from autoresearch._edgehunt_vwap_continuation import _normalize_spy  # noqa: E402

REPLAY_ENGINE = "walk_exit_manager"
REPLAY_SOUNDNESS = "sound"

# ============================================================ SOUND forward-replay (2026-08-08
# POSTFIX-GATE-COSTING-UNSOUND-REPLAY fix -- see module docstring). Lazy-imported + cached
# EXACTLY like gate_expiry_check.py's own _sound_replay_module: this file already lives in
# backtest/tools/ (same dir as gate_revalidation_ab.py) so a bare top-level import would also
# work, but the lazy/cached form is kept identical to the reference implementation for
# consistency and so tests can monkeypatch it the same way test_gate_expiry_check.py does. ===
_SOUND_REPLAY_MODULE = None
_REPLAY_CTX_CACHE: dict = {}


def _sound_replay_module():
    global _SOUND_REPLAY_MODULE
    if _SOUND_REPLAY_MODULE is None:
        tools_dir = str(REPO / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import gate_revalidation_ab as _grab  # noqa: PLC0415 -- deferred, mirrors gate_expiry_check.py
        _SOUND_REPLAY_MODULE = _grab
    return _SOUND_REPLAY_MODULE


def _replay_context(spy: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """(spy_by_date, ribbon_lookup), memoized per spy DataFrame identity -- mine() loads spy
    ONCE and reuses it across every part/door/arm this run."""
    key = id(spy)
    if key not in _REPLAY_CTX_CACHE:
        grab = _sound_replay_module()
        spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
        ribbon_lookup = grab.build_ribbon_lookup(spy)
        _REPLAY_CTX_CACHE[key] = (spy_by_date, ribbon_lookup)
    return _REPLAY_CTX_CACHE[key]


def replay_event(row: dict, spy: pd.DataFrame, spy_ts: pd.Series, spy_by_date: dict,
                  ribbon_lookup: pd.DataFrame, cfg: dict) -> dict:
    """SOUND forward-replay: thin wrapper over gate_revalidation_ab.replay_row (walk_exit_manager
    / the production exit_manager.plan_exit_actions core). Replaces the retired
    gate_expiry_check.simulate_event helper (simulator-real-backed) this tool used to call --
    kept the signature shape close (row, spy, ..., cfg) so every call site below needed only a
    minimal diff. `cfg` carries {"qty", "structure_stop_enabled", "time_stop_et"}
    (from gate_revalidation_ab.account_config() for the two core accounts, or a per-event
    override for fleet arms in Part C -- see mine())."""
    grab = _sound_replay_module()
    return grab.replay_row(row, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                            ribbon_lookup=ribbon_lookup, cfg=cfg)


DOORS = {
    "bear": ("bear_blockers", "P", "bear_rejection_level_raw"),
    "bull": ("bull_blockers", "C", "bull_reclaim_level_raw"),
}
FLEET_ARMS = ("safe-3", "risky-1", "risky-3")


def mine(start: dt.date, end: dt.date) -> dict:
    print("[postfix] loading SPY+VIX frame ...", flush=True)
    spy_raw, _vix = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    spy_ts = spy["timestamp_et"]
    spy_by_date, ribbon_lookup = _replay_context(spy)
    grab = _sound_replay_module()
    account_cfg = grab.account_config()

    rows = [r for r in load_decision_rows(CORE_DECISIONS, start)
            if r.get("ts_et", "")[:10] <= end.isoformat() and r.get("armed") is True]
    print(f"[postfix] core rows in window: {len(rows)}", flush=True)
    verdict_counts = Counter((r.get("account"), r.get("verdict")) for r in rows)

    # ---- PART A ------------------------------------------------------------------
    skip_actions = sorted({v for (_a, v) in verdict_counts if v and v.startswith("SKIP")})
    part_a = {}
    for action in skip_actions:
        per_account, all_ok, door_keys, late = {}, [], set(), 0
        for account in ("safe", "bold"):
            sub = [r for r in rows if r.get("account") == account and r.get("verdict") == action]
            events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
            sims = [replay_event(ev, spy, spy_ts, spy_by_date, ribbon_lookup, account_cfg[account])
                    for ev in events]
            ok = [s for s in sims if s["status"] == "ok"]
            m = window_metrics(ok, start, end) if ok else {"n": 0}
            per_account[account] = {"n_raw_fires": len(sub), "n_events": len(events),
                                    "status_counts": dict(Counter(s["status"] for s in sims)), **m}
            all_ok.extend(ok)
            for ev in events:
                door_keys.add(ev["ts_et"][:16])
                if ev["ts_et"][11:16] >= "15:00":
                    late += 1
        combined = window_metrics(all_ok, start, end) if all_ok else {"n": 0}
        late_ok = [s for s in all_ok if str(s.get("ts_et", ""))[11:16] >= "15:00"]
        part_a[action] = {
            "per_account": per_account, "combined": combined,
            "door_level_distinct_clusters_across_accounts": len(door_keys),
            "events_at_or_after_1500_et": late,
            "pnl_at_or_after_1500_et": round(sum(s["pnl"] for s in late_ok), 2),
            "replay_engine": REPLAY_ENGINE, "replay_soundness": REPLAY_SOUNDNESS,
        }
        print(f"[postfix] A {action}: n={combined.get('n')} total=${combined.get('total_dollar')}", flush=True)

    # ---- PART B ------------------------------------------------------------------
    part_b = {}
    for door, (bkey, side, lvl_key) in DOORS.items():
        for account in ("safe", "bold"):
            holds = [r for r in rows if r.get("account") == account and r.get("verdict") == "HOLD"]
            for filt in range(1, 12):
                sub = []
                for r in holds:
                    if (r.get(bkey) or []) == [filt]:
                        ev = dict(r)
                        ev["side"] = side
                        if r.get(lvl_key) is not None:
                            ev["trigger_level_exact"] = r[lvl_key]
                        sub.append(ev)
                if not sub:
                    continue
                events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
                sims = [replay_event(ev, spy, spy_ts, spy_by_date, ribbon_lookup, account_cfg[account])
                        for ev in events]
                ok = [s for s in sims if s["status"] == "ok"]
                m = window_metrics(ok, start, end) if ok else {"n": 0}
                key = f"{door}_filter{filt}_{account}"
                part_b[key] = {"n_raw_sole_blocker_rows": len(sub), "n_events": len(events),
                               "status_counts": dict(Counter(s["status"] for s in sims)), **m,
                               "vix_at_events": [round(float(e.get("vix") or 0), 2) for e in events][:12],
                               "replay_engine": REPLAY_ENGINE, "replay_soundness": REPLAY_SOUNDNESS}
                print(f"[postfix] B {key}: events={len(events)} total=${m.get('total_dollar')}", flush=True)

    combo_counts = {}
    for door, (bkey, _s, _l) in DOORS.items():
        c = Counter()
        for r in rows:
            if r.get("verdict") == "HOLD":
                combo = tuple(r.get(bkey) or [])
                if combo:
                    c[combo] += 1
        combo_counts[door] = {"|".join(map(str, k)): v for k, v in c.most_common(12)}

    oracle_58 = {}
    for account in ("safe", "bold"):
        sub = []
        for r in rows:
            if (r.get("account") == account and r.get("verdict") == "HOLD"
                    and (r.get("bear_blockers") or []) == [5, 8]):
                ev = dict(r)
                ev["side"] = "P"
                if r.get("bear_rejection_level_raw") is not None:
                    ev["trigger_level_exact"] = r["bear_rejection_level_raw"]
                sub.append(ev)
        events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
        sims = [replay_event(ev, spy, spy_ts, spy_by_date, ribbon_lookup, account_cfg[account])
                for ev in events]
        ok = [s for s in sims if s["status"] == "ok"]
        m = window_metrics(ok, start, end) if ok else {"n": 0}
        oracle_58[account] = {"n_rows": len(sub), "n_events": len(events),
                              "status_counts": dict(Counter(s["status"] for s in sims)), **m,
                              "replay_engine": REPLAY_ENGINE, "replay_soundness": REPLAY_SOUNDNESS}
        print(f"[postfix] ORACLE bear[5,8] {account}: total=${m.get('total_dollar')}", flush=True)

    # ---- PART C ------------------------------------------------------------------
    part_c = {}
    for arm in FLEET_ARMS:
        # fleet arms have no dedicated params.json; both safe-3 (structure stop_mode patch)
        # and risky-1/risky-3 (same patch) leave structure_stop_enabled=True and time_stop_et
        # unpatched (15:40, shared with both core accounts) -- see automation/state/fleet/
        # accounts.json's params_patch.exit_patch per arm, hand-verified 2026-08-08 during this
        # fix. Base off the matching core account's cfg (safe-prefixed arms -> "safe", else
        # "bold"); qty is overridden per-event below (fleet decisions carry their own qty).
        base_cfg = account_cfg["safe" if arm.startswith("safe") else "bold"]
        fp = ROOT / "automation" / "state" / "fleet" / arm / "decisions.jsonl"
        sub = []
        if fp.exists():
            for line in fp.open(encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                ts = str(r.get("ts_et") or "")
                if (start.isoformat() <= ts[:10] <= end.isoformat()
                        and r.get("risk_code") == "SKIP_MIN_PREMIUM_FLOOR"):
                    sub.append(r)
        events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
        sims, refused = [], []
        for ev in events:
            e = dict(ev)
            e["ts_et"] = e["ts_et"][:19]
            e.setdefault("side", "C")
            qty = int(ev.get("qty") or (3 if arm.startswith("safe") else 5))
            cfg = {"qty": qty, "structure_stop_enabled": base_cfg["structure_stop_enabled"],
                   "time_stop_et": base_cfg["time_stop_et"]}
            sims.append(replay_event(e, spy, spy_ts, spy_by_date, ribbon_lookup, cfg))
            refused.append({"ts": ev["ts_et"][:16], "planned_strike": ev.get("strike"),
                            "refused_premium": ev.get("premium"), "qty": qty})
        ok = [s for s in sims if s["status"] == "ok"]
        m = window_metrics(ok, start, end) if ok else {"n": 0}
        by_day = defaultdict(float)
        for s in ok:
            by_day[s["date"]] += s["pnl"]
        part_c[arm] = {"n_raw_floor_rows": len(sub), "n_events": len(events),
                       "status_counts": dict(Counter(s["status"] for s in sims)), **m,
                       "by_day": {k: round(v, 2) for k, v in sorted(by_day.items())},
                       "refused_quotes_sample": refused[:10],
                       "replay_engine": REPLAY_ENGINE, "replay_soundness": REPLAY_SOUNDNESS}
        print(f"[postfix] C {arm}: floor_rows={len(sub)} ATM-cf total=${m.get('total_dollar')}", flush=True)

    return {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "window": f"{start}..{end}",
        "conventions": {
            "miner": "gate_expiry_check machinery (armed=True, 15-min clustering, stale-bar drop)",
            "pricing": "real OPRA 5m cache, ATM strike, production exit_manager.plan_exit_actions exit shape via exit_manager_walk.walk_exit_manager (shared with the sound nightly gate-expiry instrument and gate_revalidation_ab.py -- see replay_engine below)",
            "resolution_bias": "5-min bars under-detect intra-bar stops (one-directional, flattering) -- OPTION-BAR-RESOLUTION-BIAS-2026-08-02",
            "per_account_double_count": "safe+bold rows at the same tick are the same door signal logged per account (instrument-consistent; door-level distinct clusters reported separately)",
            "part_c_label": "SIM counterfactual (ATM strike under ATM-TIER-EXTENSION-2K-10K), NOT broker fills; per-event independent; overlaps Part A's elite cohort (same door) -- never sum A+C; fleet-arm exit cfg (structure_stop_enabled/time_stop_et) approximated from the matching core account (safe-3->safe, risky-1/risky-3->bold) since fleet arms have no dedicated params.json -- hand-verified 2026-08-08 that both patch stop_mode='structure' (already true at the core baseline) and leave time_stop_et unpatched (15:40, shared)",
        },
        "replay_engine": REPLAY_ENGINE, "replay_soundness": REPLAY_SOUNDNESS,
        "_correction_2026_08_08": {
            "note": (
                "POSTFIX-GATE-COSTING-UNSOUND-REPLAY fix (filed the same evening "
                "gate_expiry_check.py was rewired off simulator_real, commit 97a2e2ac). This "
                "file (and its default output path, gate-postfix-costing-<end>.json) used to "
                "forward-replay via gate_expiry_check.simulate_event -> "
                "lib.simulator_real.simulate_trade_real, which carries two independently-"
                "documented, dated defects (exit-shape divergence from the real production "
                "exit_manager, 2026-07-17 FRAME AUDIT; same-bar/intrabar look-ahead, "
                "BACKTESTING-PLAYBOOK.md 2.12). This run and every run after it replays through "
                "backtest/lib/exit_manager_walk.walk_exit_manager (the actual production "
                "exit_manager.plan_exit_actions core) instead -- see replay_engine/"
                "replay_soundness on every EV-bearing section. THIS regeneration OVERWROTE the "
                "prior 2026-08-03 file in place -- the pre-fix numbers below are hand-transcribed "
                "from that prior run (also recoverable from git history, this file's prior "
                "committed revision) so this correction is self-contained and does not depend on "
                "a since-overwritten path."
            ),
            "pre_fix_headline_totals_2026_08_03_window": {
                "part_a_SKIP_ELITE_BULL_LEVEL_RECLAIM_total_dollar": 3576.92,
                "part_b_bull_filter8_bold_total_dollar": -118.80,
                "part_b_bull_filter8_safe_total_dollar": -71.28,
                "part_b_bull_filter10_bold_total_dollar": 2940.80,
                "part_b_bull_filter11_bold_total_dollar": 2168.10,
                "oracle_bear_5_8_bold_total_dollar": 669.60,
                "oracle_bear_5_8_safe_total_dollar": 401.76,
                "part_c_safe_3_total_dollar": 669.20,
                "part_c_risky_1_total_dollar": 2164.20,
                "part_c_risky_3_total_dollar": 329.20,
                "note": "sample of the largest/most-cited cells; see part_a/part_b/oracle/part_c below for the full sound-engine AFTER figures on the identical window",
            },
            "biggest_moves": (
                "bull_filter8 FLIPPED SIGN on both accounts (bold -$118.80 -> +$1,692.90, safe "
                "-$71.28 -> +$992.95); bull_filter10/11 roughly doubled-to-quadrupled; "
                "oracle_bear_5_8 dropped ~19x (bold $669.60 -> $35.00); part_c fleet-floor "
                "counterfactuals roughly tripled. Directional take: several previously-"
                "unremarkable or negative cells are now the largest positive cells in the whole "
                "report -- any prior read of this artifact that ranked cells by dollar size is "
                "now STALE, not just off by a scale factor."
            ),
        },
        "verdict_counts_in_window": {f"{a}|{v}": n for (a, v), n in sorted(verdict_counts.items())},
        "part_a_skip_gates": part_a,
        "part_b_filter_sole_blockers": part_b,
        "blocker_combo_census_hold_rows": combo_counts,
        "oracle_bear_5_8_both_lifted": {
            "label": ("ORACLE -- lifting filter 8 alone admits none of these (ribbon filter 5 "
                      "still blocks; filter-5 deletion is graveyarded); both-lifted upper bound only"),
            **oracle_58},
        "part_c_fleet_floor_atm_counterfactual": part_c,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Window-scoped refusal costing for every entry gate/filter")
    ap.add_argument("--start", default="2026-07-31")
    ap.add_argument("--end", default="2026-08-03")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    out = mine(start, end)
    out_path = Path(args.out) if args.out else (
        ROOT / "analysis" / "recommendations" / f"gate-postfix-costing-{end.isoformat()}.json")
    out_path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"[postfix] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
