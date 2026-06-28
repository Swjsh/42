"""replay_fleet_arms.py — per-ARM entry-fidelity gate for the 4 loose fleet arms.

VALIDATION + SPEC ONLY. Offline replay harness. Touches NO production file:
does NOT modify build_shared_signal.py / fleet_live.py / accounts.json, does NOT
point the live shared-signal at core-decisions.jsonl, places NO orders. The one
production wiring change needed to go LIVE is REPORTED (not applied) at the end.

WHAT THIS PROVES
----------------
heartbeat_core.py writes the DETERMINISTIC verdict (the validated brain) to
automation/state/core-decisions.jsonl. The 4 fleet arms (safe-1, safe-3, risky-1,
risky-3) are live=True but run on fleet_live.py, which reads shared-signal.json
built by build_shared_signal.py — and that producer reads the DEAD LLM ledger
(decisions.jsonl), falls through to the beacon, emits production_action=HOLD, and
benches all 4 arms. The fix is to drive the fleet off core-decisions.jsonl. But
BEFORE any arm consumes the core signal, EACH arm must pass its OWN entry-fidelity
gate — exactly the way safe-2/bold-2 did in replay_heartbeat_core.py (5/5 matched,
0 extra, 0 missed).

GROUND TRUTH (per arm)
----------------------
run_backtest with THAT arm's config:
  - min_triggers override injected as min_triggers_bear=min_triggers_bull=N
  - account_equity = arm.starting_equity (drives the per-tier strike table; entry
    timing is INDEPENDENT of strike depth / qty — strike & qty are a SIZING layer,
    not an ENTRY-timing layer, so they are a separate parity check, not the gate).
  - base params routed SAFE vs BOLD exactly like fleet_executor._base_params_for.
Post-filters run_backtest cannot express (applied to the GT trade set):
  - direction_lock PUT_ONLY  -> keep side=='P' only            (risky-1)
  - require_confluence_or_sequence / min_setup_quality EXCELLENT -> keep ELITE only
  - min_confidence            -> the deterministic signal carries NO confidence, so
    fleet_executor.plan_entry DENIES-on-missing -> the faithful GT is EMPTY. The arm
    is provably benched-by-design on this signal (FLAGGED, not failed).

SIGNAL-DRIVEN ARM TRADES (per arm)
----------------------------------
Per evaluated bar: rebuild heartbeat_core's payload (hc._build_payload) + the
deterministic verdict (decide_payload) — the SAME brain output that drives
core-decisions.jsonl — then SYNTHESIZE the shared-signal block the fleet would have
seen under build_shared_signal's SCORING_PEAK_LIVE dual-perception build (safe arms
read signal['safe'], bold/risky arms read signal['bold']), and run the REAL
fleet_executor.plan_entry(arm, signal, equity, params). An ENTER plan = an arm entry
at that bar. Then apply the SAME dedup (open-position window) + quality-lock gating
replay_heartbeat_core uses, so the arm trade set is compared apples-to-apples to the
backtest trade set: MATCHED == GT trades, EXTRA == 0, MISSED == 0.

Run: backtest/.venv/Scripts/python.exe backtest/replay_fleet_arms.py
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from datetime import time as dtime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
for p in ("backtest", "setup/scripts", "automation/state/fleet"):
    sys.path.insert(0, str(REPO / p))

from lib.orchestrator import run_backtest, _align_vix_to_spy, _params_to_kwargs  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.engine.engine_cli import decide_payload  # noqa: E402
import datetime as _dt  # noqa: E402
import heartbeat_core as hc  # noqa: E402
import fleet_executor as fx  # noqa: E402
import build_shared_signal as bss  # noqa: E402

SPY_CSV = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-06-24.csv"
VIX_CSV = REPO / "backtest" / "data" / "vix_5m_2026-05-19_2026-06-24.csv"
N_DAYS = 8

ACCOUNTS = json.loads((REPO / "automation" / "state" / "fleet" / "accounts.json").read_text(encoding="utf-8"))
ARMS_UNDER_TEST = ("safe-1", "safe-3", "risky-1", "risky-3")


def _norm_params(p: dict) -> dict:
    """Normalize a params dict before feeding heartbeat_core._build_payload.

    HARNESS-SIDE ONLY (does not touch the production file). aggressive/params.json carries
    entry_no_trade_window_et=[] (empty list = "no window"), which _build_payload passes
    straight through as no_trade_window -> engine_cli rejects it (schema expects
    ['HH:MM','HH:MM'] or null). _params_to_kwargs already treats a FALSY window as
    None/disabled (orchestrator.py:386-395), so the canonical reading of [] is None.
    We apply that same normalization so the replayed BOLD verdict matches what the
    orchestrator/backtest would compute. As of 2026-06-25 the live path also normalizes:
    heartbeat_core._norm_no_trade_window applies the identical falsy/non-2-list->None coercion
    in _build_payload, so this harness step is now belt-and-suspenders (idempotent)."""
    q = copy.deepcopy(p)
    w = q.get("entry_no_trade_window_et")
    if isinstance(w, list) and len(w) != 2:
        q["entry_no_trade_window_et"] = None
    return q


PARAMS_SAFE = _norm_params(json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8")))
PARAMS_BOLD = _norm_params(json.loads((REPO / "automation" / "state" / "aggressive" / "params.json").read_text(encoding="utf-8")))


def _arm(arm_id: str) -> dict:
    for a in ACCOUNTS["arms"]:
        if a.get("id") == arm_id:
            return a
    raise KeyError(arm_id)


# =====================================================================
# GROUND TRUTH: run_backtest per arm, then the post-filters run_backtest can't express
# =====================================================================
def _arm_base_params(arm: dict) -> dict:
    """SAFE vs BOLD base params, routed exactly like fleet_executor._base_params_for."""
    src = str(arm.get("config_source", ""))
    if "aggressive" in src or str(arm["id"]).startswith(("bold", "risky")):
        return copy.deepcopy(PARAMS_BOLD)
    return copy.deepcopy(PARAMS_SAFE)


def _arm_run_backtest_params(arm: dict) -> dict:
    """Base params + this arm's min_triggers override injected so _params_to_kwargs
    translates it into min_triggers_bear/_bull. (strike_tier_table / position_sizing_tiers
    do NOT affect entry timing — they are sizing-only, validated separately in §qty.)"""
    p = _arm_base_params(arm)
    g = arm.get("gate_override") or {}
    mt = g.get("min_triggers")
    if mt is not None:
        p["filter_10_min_triggers_bear"] = int(mt)
        p["filter_10_min_triggers_bull"] = int(mt)
    return p


def _is_elite_triggers(triggers) -> bool:
    """ELITE (v13b) mirror of fleet_executor._is_elite over a trigger list."""
    return any("sequence" in str(t).lower() or "confluence" in str(t).lower()
               for t in (triggers or []))


def _ground_truth_trades(arm: dict, spy, vix, start, end):
    """run_backtest GT for the arm, then post-filter for the gates run_backtest cannot model."""
    p = _arm_run_backtest_params(arm)
    eq = float(arm.get("starting_equity") or 2000.0)
    kw = _params_to_kwargs(p, account_equity=eq)
    res = run_backtest(spy.drop(columns=["date"]), vix, start_date=start, end_date=end, **kw)
    trades = list(res.trades)
    notes = []

    g = arm.get("gate_override") or {}
    dl = arm.get("direction_lock")
    if dl == "PUT_ONLY":
        trades = [t for t in trades if getattr(t, "side", "P") == "P"]
        notes.append("direction_lock=PUT_ONLY -> keep P only")
    elif dl == "CALL_ONLY":
        trades = [t for t in trades if getattr(t, "side", "C") == "C"]
        notes.append("direction_lock=CALL_ONLY -> keep C only")

    if g.get("require_confluence_or_sequence") or str(g.get("min_setup_quality", "")).upper() == "EXCELLENT":
        trades = [t for t in trades if _is_elite_triggers(getattr(t, "triggers_fired", []))]
        notes.append("require ELITE (confluence/sequence) -> keep ELITE only")

    benched_by_confidence = False
    if g.get("min_confidence") is not None:
        # The deterministic signal carries NO confidence -> plan_entry DENIES-on-missing.
        # Faithful GT is therefore EMPTY: this arm cannot fire on the confidence-less signal.
        trades = []
        benched_by_confidence = True
        notes.append(f"min_confidence={g['min_confidence']} on confidence-less signal -> benched by design (GT empty)")

    return res, trades, notes, benched_by_confidence


# =====================================================================
# SIGNAL SYNTHESIS: build the shared-signal block the fleet would see, FROM the
# deterministic verdict — exactly the dual-perception shape build_shared_signal emits
# under SCORING_PEAK_LIVE. (This is the spec for the production wiring; here it runs
# offline against the replayed verdict, never against the live producer.)
# =====================================================================
def _passed_for_arm(arm: dict, verdict: dict, side_key: str) -> bool:
    """Mirror build_shared_signal's passed logic for the perception block an arm reads.

    safe arms read signal['safe'] (production-faithful: passed iff the verdict ENTERED
    this side). bold/risky arms read signal['bold'] (scoring-peak: passed iff ENTERED
    OR score>=peak with a fired entry-trigger — bss.passed_scoring_peak)."""
    v = verdict.get("verdict") or ""
    action = "ENTER_BEAR" if v == "ENTER_BEAR" else ("ENTER_BULL" if v == "ENTER_BULL" else v)
    score = verdict.get("bear_score") if side_key == "bear" else verdict.get("bull_score")
    trigs = verdict.get("triggers_fired") or []
    # the producer keeps a single "trigger" + fired flag; the core gives the full fired list.
    # For scoring-peak we need (fired AND trigger in ENTRY_TRIGGERS); replicate with the list.
    fired = bool(trigs)
    trig0 = trigs[0] if trigs else None
    role = "safe" if str(arm["id"]).startswith("safe") else "bold"
    if role == "safe":
        return action == ("ENTER_BEAR" if side_key == "bear" else "ENTER_BULL")
    # bold perception: scoring-peak passed (the looser path the loose arms consume)
    return bss.passed_scoring_peak("bull" if side_key == "bull" else "bear",
                                   action, score, trig0, fired)


def _synth_signal(arm: dict, verdict: dict, payload: dict) -> dict:
    """Synthesize the dual-perception shared-signal the fleet executor consumes, FROM
    the deterministic verdict. Field names match build_shared_signal's emitted contract
    (spot/ribbon_stack/production_action + safe/bold {bull,bear}{passed,score,triggers_fired,setup_name})."""
    bc = payload["bar_ctx"]
    v = verdict.get("verdict") or "HOLD"
    setup = verdict.get("setup_name")
    trigs = verdict.get("triggers_fired") or []

    def _side_block(side_key: str) -> dict:
        passed = _passed_for_arm(arm, verdict, side_key)
        # ELITE-PARITY (the production-wiring fix this gate proves): fleet_executor._is_elite
        # treats a block as ELITE only if block['confluence'] is True OR a 'sequence_*' trigger
        # is in triggers_fired. The deterministic verdict carries 'confluence' /
        # 'multi_day_confluence' as a TRIGGER NAME (not a boolean key) — so without this mapping
        # _is_elite under-classifies every confluence-tied setup as non-ELITE and risky-1 / safe-3
        # (require_confluence_or_sequence) systematically HOLD setups their own backtest TOOK.
        # The faithful signal builder MUST set confluence=True when a confluence trigger fired —
        # exactly matching run_backtest's ELITE definition. (REPORTED as the build_shared_signal
        # change; modeled here, NOT applied to the production file.)
        has_confluence = any("confluence" in str(t).lower() for t in (trigs or []))
        return {
            "passed": passed,
            "score": verdict.get("bear_score") if side_key == "bear" else verdict.get("bull_score"),
            "triggers_fired": list(trigs) if passed else [],
            "setup_name": setup if passed else None,
            "confluence": True if (passed and has_confluence) else False,
            # confidence intentionally ABSENT (core has none) -> safe-3 DENY-on-missing
            # is moot now (current accounts.json safe-3 has no min_confidence).
        }

    bear, bull = _side_block("bear"), _side_block("bull")
    role = "safe" if str(arm["id"]).startswith("safe") else "bold"
    sig = {
        "spot": bc["bar"]["close"],
        "vix": bc.get("vix_now"),
        "vix_dir": None,
        "ribbon_stack": bc["ribbon_now"]["stack"],
        "ribbon_spread_cents": bc["ribbon_now"]["spread_cents"],
        "htf_15m_stack": bc.get("htf_15m_stack"),
        "tick_id": None,
        "production_action": v if v in ("ENTER_BEAR", "ENTER_BULL") else "HOLD",
        "bear": bear, "bull": bull,            # top-level (controls / v1 consumers)
        # dual-perception sub-blocks: the arm's _perception_for_arm reads its role block
        role: {"bull": bull, "bear": bear},
    }
    # also populate the OTHER role block (harmless, keeps the signal shape complete)
    other = "bold" if role == "safe" else "safe"
    sig[other] = {"bull": bull, "bear": bear}
    return sig


# =====================================================================
# PER-BAR replay of the deterministic verdict (ported verbatim from
# replay_heartbeat_core.py — same payload assembly, same level/vix-MA freeze).
# =====================================================================
def _replay_verdicts(spy, vix, days, start, end, params):
    """Return (res, decs, verdict_by_bar, payload_by_bar, score_pct, n, m) — the
    deterministic verdict per evaluated bar UNDER THE GIVEN PARAMS + an input/score-parity
    tally vs the orchestrator's own per-bar values.

    DUAL-PERCEPTION FIDELITY: heartbeat_core writes ONE core-decisions row per account
    per tick (safe row under params.json, bold row under aggressive/params.json) — the
    SAFE gates (midday_trendline_gate, block_level_rejection, vix_bear_hard_cap,
    entry_bar_body_pct_min) are OFF on BOLD, so the two accounts produce DIFFERENT
    verdicts at the same bar. The fleet's _perception_for_arm routes safe arms to the
    safe row and bold/risky arms to the bold row. So this harness replays the verdict
    UNDER the matching param set for each arm class (caller passes SAFE or BOLD params),
    and the ground truth run_backtest is built on the SAME base params (C9 symmetry)."""
    res = run_backtest(spy.drop(columns=["date"]), vix, start_date=start, end_date=end,
                       **_params_to_kwargs(params, account_equity=2000.0))
    decs = [d for d in res.decisions if isinstance(d.get("bar_idx"), int)]

    vix_al = _align_vix_to_spy(spy.drop(columns=["date"]), vix)
    _vr = vix.copy()
    _vr["_date"] = pd.to_datetime(_vr["timestamp_et"], utc=True).dt.date
    _cbd = _vr.groupby("_date")["close"].last()
    _ds = sorted(_cbd.index)
    _ma5, _ma20 = {}, {}
    for _di, _d in enumerate(_ds):
        if _di >= 5:
            _ma5[_d] = sum(_cbd[_ds[_di - 5 + _j]] for _j in range(5)) / 5.0
        if _di >= 20:
            _ma20[_d] = sum(_cbd[_ds[_di - 20 + _j]] for _j in range(20)) / 20.0

    spy2 = spy.copy()
    spy2["timestamp"] = spy2["timestamp_et"]

    _spy_nb = spy2.drop(columns=["timestamp", "date"]).copy()
    _level_per_day: dict = {}
    _bar_date = spy2["timestamp_et"].dt.date
    _bar_time = spy2["timestamp_et"].dt.time
    for _i in range(len(spy2)):
        _bd = _bar_date.iloc[_i]
        if _bd in _level_per_day:
            continue
        if _bar_time.iloc[_i] < _dt.time(9, 35):
            continue
        _level_per_day[_bd] = _detect_from_history(_spy_nb.iloc[: _i + 1].copy(), _bd)

    verdict_by_bar: dict[int, dict] = {}
    payload_by_bar: dict[int, dict] = {}
    m = Counter()
    bear_diffs = []
    n = 0
    for d in decs:
        idx = d["bar_idx"]
        if idx < 60 or idx + 2 > len(spy2):
            continue
        ts = spy2["timestamp_et"].iloc[idx]
        hist = spy2.iloc[: idx + 2]
        try:
            vix_now = float(vix_al.iloc[idx]); vix_prior = float(vix_al.iloc[idx - 1])
            ls = _level_per_day.get(ts.date())
            if ls is None:
                continue
            vix5 = _ma5.get(ts.date(), 0.0); vix20 = _ma20.get(ts.date(), 0.0)
            payload = hc._build_payload(hist, params, vix=(vix_now, vix_prior),
                                        levels=(list(ls.active), list(ls.multi_day)),
                                        vix_ma=(vix5, vix20))
            if payload is None:
                continue
            v = decide_payload(payload)
        except Exception as e:  # noqa: BLE001
            m[f"replay_err:{type(e).__name__}"] += 1
            continue
        n += 1
        verdict_by_bar[idx] = v
        payload_by_bar[idx] = payload
        gb, hb = d.get("bear_score"), v.get("bear_score")
        if isinstance(gb, (int, float)) and isinstance(hb, (int, float)):
            bear_diffs.append(abs(gb - hb))
            if gb == hb:
                m["bear_score_exact"] += 1
    score_pct = (m["bear_score_exact"] / len(bear_diffs)) if bear_diffs else 0.0
    return res, decs, verdict_by_bar, payload_by_bar, score_pct, n, m


# =====================================================================
# ENTRY-FIDELITY comparison (per arm) — same dedup + quality-lock gating as
# replay_heartbeat_core.py, but the ENTER stream is the ARM's plan_entry output.
# =====================================================================
def _bar_index_map(spy):
    ts_to_idx = {ts: i for i, ts in enumerate(spy["timestamp_et"])}

    def _bar_of(ts_val):
        if ts_val is None:
            return None
        t = pd.Timestamp(ts_val)
        bi = ts_to_idx.get(t)
        if bi is None:
            mm = spy[spy["timestamp_et"] == t]
            bi = int(mm.index[0]) if not mm.empty else None
        return bi
    return _bar_of


def _arm_signal_enters(arm, gt_trades, verdict_by_bar, payload_by_bar):
    """For each replayed bar, synthesize the arm's signal block from the verdict and run
    the REAL fleet_executor.plan_entry. ENTER plans -> {bar_idx: side}."""
    params = fx._params_for(arm)
    equity = float(arm.get("starting_equity") or 2000.0)
    enters: dict[int, str] = {}
    for idx, verdict in verdict_by_bar.items():
        payload = payload_by_bar[idx]
        sig = _synth_signal(arm, verdict, payload)
        plan = fx.plan_entry(arm, sig, equity, params)
        if plan.action == "ENTER" and plan.side in ("P", "C"):
            enters[idx] = plan.side
    return enters


def _entry_fidelity(arm, gt_trades, verdict_by_bar, payload_by_bar, gt_decs, spy):
    """gt_decs = the ARM's OWN run_backtest decisions (arm base params + min_triggers),
    so the quality-lock SKIP map is consistent with the arm's ground-truth trade set —
    same discipline as replay_heartbeat_core (it gates against the production decisions
    of the config under test)."""
    _bar_of = _bar_index_map(spy)
    gt_by_bar: dict[int, str] = {}
    blocked_pre: set[int] = set()
    for t in gt_trades:
        ei = _bar_of(getattr(t, "entry_time_et", None))
        if ei is None:
            continue
        gt_by_bar[ei] = getattr(t, "side", "P")
        xi = _bar_of(getattr(t, "runner_exit_time_et", None))
        end = xi if xi is not None else ei + 5
        for bb in range(ei + 1, end + 1):
            blocked_pre.add(bb)

    orch_action = {d["bar_idx"]: d.get("action") for d in gt_decs if isinstance(d.get("bar_idx"), int)}

    # DOWNSTREAM-FILTER PARITY (C15 — gates interact multiplicatively): decide_payload (the
    # deterministic brain feeding core-decisions.jsonl) produces the entry SIGNAL on
    # price/ribbon/level/score only. The PREMIUM floor + the elite/level/midday/momentum
    # cascade live DOWNSTREAM — in run_backtest (SKIP_MIN_PREMIUM / SKIP_ELITE_BULL_LEVEL_RECLAIM
    # / SKIP_LEVEL_REJECTION_GATE / SKIP_RIBBON_MOMENTUM_GATE / SKIP_MIDDAY_TRENDLINE_GATE /
    # SKIP_QUALITY_LOCK) and, LIVE, in fleet_live's get_option_mid (no/low premium -> not
    # placed) + risk_gate. The signal layer this harness exercises (plan_entry) does NOT
    # fetch premium or re-run those gates, so a bar the GT SKIP_*'d for a downstream reason is
    # correctly a NON-TRADE for BOTH the backtest AND the live fleet. We therefore treat ANY
    # GT SKIP_* action as a block — the faithful entry-fidelity comparison is "where the GT
    # actually TRADED vs where the signal-driven arm trades AFTER the same downstream filters."
    def _gt_blocked(b):
        a = orch_action.get(b)
        return isinstance(a, str) and a.startswith("SKIP_")

    raw_enters = _arm_signal_enters(arm, gt_trades, verdict_by_bar, payload_by_bar)
    arm_trades = [b for b in sorted(raw_enters)
                  if b not in blocked_pre and not _gt_blocked(b)]
    matched = [b for b in arm_trades if gt_by_bar.get(b) == raw_enters[b]]
    extra = [b for b in arm_trades if b not in matched]
    missed = [b for b in gt_by_bar if b not in set(arm_trades)]
    return {"gt_by_bar": gt_by_bar, "raw_enters": raw_enters, "arm_trades": arm_trades,
            "matched": matched, "extra": extra, "missed": missed}


def compute_arm_fidelity(spy_csv: Path = SPY_CSV, vix_csv: Path = VIX_CSV,
                         n_days: int = N_DAYS) -> dict:
    """Pure compute (no printing) of the per-arm entry-fidelity parity result.

    Extracted from main() so the curated/full pytest suite can assert the parity
    invariants WITHOUT scraping stdout. main() calls this then prints. Returns:
      {days, start, end, score_pct, safe_n, bold_n, safe_errs, bold_errs,
       rows: [{arm, gt_n, matched, extra, missed, score_pct, ready, benched,
               notes, fid, gt_trades}]}.
    The expensive bits (run_backtest x several) live here -> the harness runs in
    ~36s, so the wrapping test belongs in the FULL suite / CI, NOT the curated
    <2s pre-commit gate (same category as test_graduated_guards.py)."""
    spy = pd.read_csv(spy_csv)
    vix = pd.read_csv(vix_csv)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"])
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"])
    spy = spy[(spy["timestamp_et"].dt.time >= dtime(9, 30))
              & (spy["timestamp_et"].dt.time < dtime(16, 0))].reset_index(drop=True)
    spy["date"] = spy["timestamp_et"].dt.date
    days = sorted(spy["date"].unique())[-n_days:]
    start, end = days[0], days[-1]

    # DUAL-PERCEPTION replay: SAFE arms read the safe-params verdict (core 'safe' row),
    # BOLD/RISKY arms read the bold-params verdict (core 'bold' row). Two replays, routed
    # per arm class by _perception_for_arm semantics.
    safe_pack = _replay_verdicts(spy, vix, days, start, end, PARAMS_SAFE)
    bold_pack = _replay_verdicts(spy, vix, days, start, end, PARAMS_BOLD)
    score_pct = safe_pack[4]  # scoring is param-independent; report from the safe replay

    rows = []
    for arm_id in ARMS_UNDER_TEST:
        arm = _arm(arm_id)
        pack = safe_pack if arm_id.startswith("safe") else bold_pack
        verdict_by_bar, payload_by_bar = pack[2], pack[3]
        _gtres, gt_trades, notes, benched = _ground_truth_trades(arm, spy, vix, start, end)
        fid = _entry_fidelity(arm, gt_trades, verdict_by_bar, payload_by_bar, _gtres.decisions, spy)
        gt_n = len(fid["gt_by_bar"])
        matched, extra, missed = len(fid["matched"]), len(fid["extra"]), len(fid["missed"])
        entry_faithful = (extra == 0 and missed == 0 and matched == gt_n)
        ready = entry_faithful and score_pct >= 0.95
        rows.append({
            "arm": arm_id, "gt_n": gt_n, "matched": matched, "extra": extra,
            "missed": missed, "score_pct": score_pct, "ready": ready,
            "benched": benched, "notes": notes, "fid": fid,
            "gt_trades": gt_trades,
        })

    return {
        "days": days, "start": start, "end": end, "score_pct": score_pct,
        "safe_n": safe_pack[5], "bold_n": bold_pack[5],
        "safe_errs": {k: c for k, c in safe_pack[6].items() if k.startswith("replay_err")},
        "bold_errs": {k: c for k, c in bold_pack[6].items() if k.startswith("replay_err")},
        "rows": rows,
    }


def main() -> int:
    result = compute_arm_fidelity()
    days, start, end = result["days"], result["start"], result["end"]
    score_pct = result["score_pct"]
    rows = result["rows"]
    print(f"replaying {len(days)} days: {start} .. {end}")
    print(f"deterministic verdicts replayed (safe) at {result['safe_n']} bars / (bold) at {result['bold_n']} bars "
          f"| score parity (bear exact) = {score_pct:.1%}")
    for nm, errs in (("safe", result["safe_errs"]), ("bold", result["bold_errs"])):
        if errs:
            print(f"  {nm} replay errors:", errs)

    print("\n" + "=" * 92)
    print("PER-ARM ENTRY-FIDELITY (deterministic-signal-driven arm trades vs run_backtest GT)")
    print("=" * 92)
    hdr = f"{'arm':9} {'bt_trades':9} {'matched':8} {'extra':6} {'missed':6} {'score':7} {'ARM-READY'}"
    print(hdr)
    print("-" * 92)
    for r in rows:
        verdict = "YES" if r["ready"] else "NO"
        if r["benched"] and r["gt_n"] == 0 and r["extra"] == 0:
            verdict = "YES (benched-by-design)"
        print(f"{r['arm']:9} {r['gt_n']:>9} {r['matched']:>8} {r['extra']:>6} {r['missed']:>6} "
              f"{r['score_pct']:>6.1%} {verdict}")

    print("\nPER-ARM DETAIL")
    print("-" * 92)
    for r in rows:
        print(f"\n[{r['arm']}]")
        arm = _arm(r["arm"])
        g = arm.get("gate_override") or {}
        print(f"  config: min_triggers={g.get('min_triggers')} "
              f"min_confidence={g.get('min_confidence')} "
              f"require_elite={bool(g.get('require_confluence_or_sequence') or str(g.get('min_setup_quality','')).upper()=='EXCELLENT')} "
              f"direction_lock={arm.get('direction_lock')} "
              f"strike_table={(arm.get('params_patch') or {}).get('strike_tier_table') or ('bold' if r['arm'].startswith('risky') else 'safe')} "
              f"equity={arm.get('starting_equity')}")
        for nstr in r["notes"]:
            print(f"  GT post-filter: {nstr}")
        gt_desc = [(b, s) for b, s in sorted(r["fid"]["gt_by_bar"].items())]
        print(f"  GT trades (bar,side): {gt_desc}")
        arm_desc = [(b, r['fid']['raw_enters'][b]) for b in r['fid']['arm_trades']]
        print(f"  arm signal-driven trades (deduped+lock-gated): {arm_desc}")
        print(f"  raw arm ENTER bars (pre-dedup/lock): {len(r['fid']['raw_enters'])}")
        print(f"  MATCHED={r['matched']}/{r['gt_n']}  EXTRA={r['fid']['extra']}  MISSED={r['fid']['missed']}")

    print("\n" + "=" * 92)
    print("ARM-GATE VERDICT")
    print("=" * 92)
    all_ready = True
    for r in rows:
        ok = r["ready"] or (r["benched"] and r["gt_n"] == 0 and r["extra"] == 0)
        all_ready = all_ready and ok
        tag = "ARM-READY: YES" if ok else "ARM-READY: NO"
        extra_note = " (benched-by-design on confidence-less signal)" if (r["benched"] and r["gt_n"] == 0) else ""
        print(f"  {r['arm']:9} {tag}{extra_note}  "
              f"(matched={r['matched']}/{r['gt_n']}, extra={r['extra']}, missed={r['missed']}, "
              f"score={r['score_pct']:.1%})")
    print(f"\n  score parity >=95%: {'PASS' if score_pct >= 0.95 else 'FAIL'} ({score_pct:.1%})")
    print(f"  ALL ARMS READY: {'YES' if all_ready else 'NO'}")
    return 0 if all_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
