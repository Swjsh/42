"""free_model_audit.py — reusable harness: Claude (Sonnet) grades free-tier-model decisions.

WHY THIS EXISTS (J, 2026-07-11: "that is good but also worries me about the logic. we need
to audit it every other day until we're confident in it. audit the logs, logic, thought
process, what it vetoed, what it brought to the table... put it into a reusable harness
framework we can benchmark and score to improve. anything we create with free stuff needs
trained with our smart claude llms"). Project Gamma's live 0DTE SPY engine lets 2 FREE-tier
models (heartbeat_core.py's `_free_model_eval`) veto real ENTER signals. That trust was never
independently graded. This module is the standing fix: a GENERIC, pluggable harness that
grades any free-model decision log against ground truth (counterfactual replay, preferred) or
a blind independent Sonnet re-judgment (fallback), tracks a confidence bar per subject, and
self-gates its own cadence so it survives session amnesia.

ARCHITECTURE (subject-agnostic core + pluggable adapters):
  AUDIT_SUBJECTS registry maps subject_name -> SubjectAdapter(collect, grade, wired).
  `collect(since, until) -> list[AuditItem]` reads a subject's logs for a window and yields
  normalized items. `grade(item, opts) -> dict` returns {grading_method, correct, ...}.
  FOUR subjects are wired as of 2026-07-14/15: "heartbeat_veto" (setup/scripts/
  free_model_audit_heartbeat_veto.py) — the production veto gate, highest stakes (blocks
  real paper trades right now) — "twin_review" (setup/scripts/
  free_model_audit_twin_review.py, AUDIT-HARNESS-B2) — the crypto twin's nightly free-LLM
  health review, graded by agreement with twin_sentinel.py's deterministic verdict rather
  than counterfactual replay (see that adapter's module docstring for why the ground-truth
  shape differs per subject) — "prospector" (setup/scripts/free_model_audit_prospector.py,
  AUDIT-HARNESS-B3) — idea-promotion quality, graded by deterministic cross-check against
  ideas-ledger.jsonl kill rows + analysis/recommendations/ artifacts — and "swarm_consult"
  (setup/scripts/free_model_audit_swarm_consult.py, AUDIT-HARNESS-B3) — 2nd-order-brainstorm
  quality, graded by blind Sonnet re-judgment + agreement scoring (capped at 5 consults/run
  to bound cost). Lower stakes than the veto gate (no live-order impact) — both AUDIT-
  HARNESS-B3 subjects are expected to report INSUFFICIENT EVIDENCE on their first real runs.

GRADING METHOD (per-subject adapters choose the ground-truth shape that fits their subject;
NEVER fabricate a grade regardless of which method is used):
  1. Counterfactual replay (objective, preferred where a $ counterfactual exists) — reuses
     trade_autopsy.py's mechanism (exit_shape_parity_study.replay_position + fetch_option_bars)
     against REAL OPRA bars. Used by heartbeat_veto.
  2. Blind Sonnet re-judgment (fallback, only when replay is genuinely infeasible) — shows
     Sonnet the SAME snapshot the free models saw (heartbeat_core._veto_snapshot's exact
     rendering) WITHOUT the free models' answer first (anti-anchoring), compares agreement.
     Used by heartbeat_veto as its own fallback.
  3. Deterministic cross-check (agreement with a SECOND, independently-computed deterministic
     source — not a $ counterfactual, since some subjects have no "would it have made money"
     question) — used by twin_review: its qualitative HEALTHY/DEGRADED/CONCERNING read is
     compared against twin_sentinel.py's deterministic RED/YELLOW/GREEN verdict for the same
     day (recorded snapshot preferred, evaluate()-reconstruction fallback; see that adapter's
     module docstring).
  4. `ungraded_insufficient_data` — logged honestly, never guessed. This project's standing
     "never fabricate" doctrine (CLAUDE.md OP-33) applies to audit grades same as anywhere
     else: an ungraded item does NOT count as evidence toward the confidence bar.

CONFIDENCE BAR — reuses the EXISTING Nemotron promotion standard for consistency (see
analysis/shadow-model/PROMOTION-SCORECARD.md: "Promotion threshold: >=85% DT agreement
across >=3 trading days"): a subject is "confident" once its CUMULATIVE correct-grade rate
is >=85% over >=15 graded evidence points, AND that state has held for >=3 CONSECUTIVE audit
runs (a dip below the bar resets the streak — "sustained", not a one-time cross). State
persists in automation/state/free-model-audit-state.json (per-subject: evidence_n, correct_n,
consecutive_runs_above_bar, last_run_date, confident, cadence_days).

CADENCE — J: "audit it every other day until we're confident in it." Registered as a DAILY
scheduled task (Gamma_FreeModelAudit, ~21:00 ET, after Gamma_TradeAutopsy 16:15 ET) per this
repo's proven DailyTrigger pattern (project lesson: a bare interval/one-time trigger goes
dark — see install-crypto-twin.ps1 / install-dress-rehearsal.ps1 for the pattern this mirrors)
— but the SCRIPT self-gates internally: skip with a clearly-logged "SKIPPED (not due...)"
line unless >=2 days have elapsed since last_run_date (or --force). Once a subject crosses
the confidence bar, its required cadence auto-relaxes to weekly (7 days) and a one-line note
is appended to automation/overnight/STATUS.md — never silent (OP-25/C7).

READ-ONLY / NEVER-PARTICIPATES: this module NEVER places an order, NEVER touches params*.json,
NEVER writes to any decisions.jsonl (core, aggressive, or fleet/*) — it only reads them. It
writes to analysis/free-model-audit/, automation/state/free-model-audit-history.jsonl,
automation/state/free-model-audit-state.json, and (append-only, one line) automation/overnight/
STATUS.md. Cost: see the module docstring in free_model_audit_heartbeat_veto.py for the
measured per-run estimate (counterfactual replay is $0; the Sonnet fallback rides the Max
subscription pool, not metered API spend, same as manager_overseer.py/gamma-drive).

Usage:
  backtest/.venv/Scripts/python.exe setup/scripts/free_model_audit.py --subject heartbeat_veto
  backtest/.venv/Scripts/python.exe setup/scripts/free_model_audit.py --subject heartbeat_veto --force
  backtest/.venv/Scripts/python.exe setup/scripts/free_model_audit.py --subject heartbeat_veto --force --no-llm-fallback

Guard: backtest/tests/test_free_model_audit.py (confidence-bar math + cadence gating, pure,
no I/O) + backtest/tests/test_free_model_audit_heartbeat_veto.py (adapter parsing on REAL
VETOED_BY_MODELS fixture rows).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "free-model-audit.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "free-model-audit.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("crypto/lib", "automation/state/fleet", "setup/scripts", "backtest/lib", "backtest/tools"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
HISTORY = STATE / "free-model-audit-history.jsonl"
BAR_STATE_PATH = STATE / "free-model-audit-state.json"
SCORECARD_ROOT = REPO / "analysis" / "free-model-audit"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"

# Confidence bar -- SAME numbers as the existing Nemotron shadow-model promotion standard
# (analysis/shadow-model/PROMOTION-SCORECARD.md: ">=85% DT agreement across >=3 trading
# days"), reused deliberately for consistency rather than inventing a new bar.
BAR_PCT = 0.85
BAR_MIN_EVIDENCE = 15
BAR_MIN_CONSECUTIVE_RUNS = 3

# Cadence -- J: "every other day until we're confident in it." Days-elapsed gate, checked
# INSIDE the script (the scheduled task itself fires daily; see module docstring).
CADENCE_DEFAULT_DAYS = 2
CADENCE_RELAXED_DAYS = 7

GRADING_METHODS = frozenset({"counterfactual", "llm_judgment", "deterministic_cross_check",
                             "ungraded_insufficient_data"})


# --------------------------------------------------------------------------------------------
# Adapter contract
# --------------------------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AuditItem:
    """One normalized, gradeable decision from ANY subject's log. Adapters produce these;
    the framework grades + scores them without needing to know the subject's log shape."""
    subject: str
    item_id: str            # stable, dedupe-safe: re-collecting the same window must not
                             # produce a different id for the same underlying decision.
    timestamp_et: str
    account: str
    context: dict            # everything the grader needs (subject-specific shape)
    free_model_output: dict  # the free model(s)' verdict AS ORIGINALLY LOGGED (no reinterpretation)
    ground_truth: Optional[dict] = None  # pre-known ground truth, if the adapter already has it


@dataclass(frozen=True, slots=True)
class SubjectAdapter:
    """Registry entry. `collect` reads a subject's logs for [since, until] (ET dates,
    inclusive) and returns AuditItems for ALL matching decisions in that window (the
    framework — not the adapter — is responsible for skipping already-graded item_ids, so
    every adapter can stay a dumb, stateless log reader). `grade` takes one AuditItem + an
    options dict ({"allow_llm_fallback": bool}) and returns a dict that MUST include
    "grading_method" (one of GRADING_METHODS) and "correct" (True/False/None — None only
    when grading_method == "ungraded_insufficient_data")."""
    name: str
    collect: Callable[[Optional[date], date], Iterable[AuditItem]]
    grade: Callable[[AuditItem, dict], dict]
    description: str
    wired: bool = True
    # Optional subject-specific scorecard extension (VETO-HTF-CONFLICT-REGRADE, 2026-07-16):
    # takes (all "kind":"item" history rows ever graded for this subject, `until` date) and
    # returns a markdown string appended to the standard scorecard, or "" for nothing to add.
    # None (the default) for every subject that doesn't need one -- purely additive, no other
    # adapter's behavior changes. Only heartbeat_veto sets this as of 2026-07-16.
    extra_scorecard_section: Optional[Callable[[list, date], str]] = None


def _build_registry() -> dict[str, SubjectAdapter]:
    """Built lazily (not at import time) so a missing/broken adapter module for an UNWIRED
    subject can never prevent importing this framework or grading the WIRED subject(s)."""
    reg: dict[str, SubjectAdapter] = {}
    try:
        import free_model_audit_heartbeat_veto as hv  # noqa: PLC0415
        reg["heartbeat_veto"] = SubjectAdapter(
            name="heartbeat_veto", collect=hv.collect_items, grade=hv.grade_item,
            description="heartbeat_core.py's _free_model_eval 2-lane veto gate on real "
                        "ENTER_BEAR/ENTER_BULL + extra-setup signals (core-decisions.jsonl). "
                        "Production, highest stakes -- blocks real paper trades right now.",
            wired=True,
            extra_scorecard_section=hv.veto_reason_class_scorecard_section)
    except Exception as e:  # noqa: BLE001 -- a broken adapter must never break the framework
        print(f"[free_model_audit] WARN heartbeat_veto adapter failed to load: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
    try:
        import free_model_audit_twin_review as tr_adapter  # noqa: PLC0415
        reg["twin_review"] = SubjectAdapter(
            name="twin_review", collect=tr_adapter.collect_items, grade=tr_adapter.grade_item,
            description="AUDIT-HARNESS-B2: crypto twin's nightly free-LLM health review "
                        "(twin_review.py's HEALTHY/DEGRADED/CONCERNING sidecar) graded by "
                        "agreement with twin_sentinel.py's deterministic RED/YELLOW/GREEN "
                        "verdict for the same UTC day (grading_method="
                        "'deterministic_cross_check', not counterfactual replay -- there is "
                        "no $ counterfactual for a mechanism-health read). Medium stakes -- "
                        "no live-order impact, but feeds J's trust in the twin oversight "
                        "pyramid.",
            wired=True)
    except Exception as e:  # noqa: BLE001 -- a broken adapter must never break the framework
        print(f"[free_model_audit] WARN twin_review adapter failed to load: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
    # AUDIT-HARNESS-B3: idea quality (prospector) + brainstorm quality (swarm_consult) --
    # lower stakes (no live-order impact) than the veto gate, lower priority, wired 2026-07-15.
    try:
        import free_model_audit_prospector as pa  # noqa: PLC0415
        reg["prospector"] = SubjectAdapter(
            name="prospector", collect=pa.collect_items, grade=pa.grade_item,
            description="AUDIT-HARNESS-B3: prospector.py's idea-promotion judgment -- for "
                        "every idea promoted to strategy/candidates/_chef-inbox/, did it "
                        "survive its downstream battery, get killed, or is it still pending "
                        "(grading_method='deterministic_cross_check' against ideas-ledger.jsonl "
                        "kill rows + analysis/recommendations/ artifacts -- no LLM call, this "
                        "is pure record-linkage). Lower stakes -- no live-order impact.",
            wired=True)
    except Exception as e:  # noqa: BLE001 -- a broken adapter must never break the framework
        print(f"[free_model_audit] WARN prospector adapter failed to load: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
    try:
        import free_model_audit_swarm_consult as sca  # noqa: PLC0415
        reg["swarm_consult"] = SubjectAdapter(
            name="swarm_consult", collect=sca.collect_items, grade=sca.grade_item,
            description="AUDIT-HARNESS-B3: swarm_consult.py's free-tier synthesized answers, "
                        "graded by BLIND Sonnet re-judgment (answers the same question never "
                        "having seen the swarm's answer) + a second Sonnet call scoring "
                        "agreement (grading_method='llm_judgment' -- there is no $ "
                        "counterfactual or second deterministic source for open-ended "
                        "brainstorm/decide/critique/audit questions). Capped at 5 consults/run "
                        "to bound cost. Lower stakes -- no live-order impact.",
            wired=True)
    except Exception as e:  # noqa: BLE001 -- a broken adapter must never break the framework
        print(f"[free_model_audit] WARN swarm_consult adapter failed to load: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
    return reg


AUDIT_SUBJECTS: dict[str, SubjectAdapter] = _build_registry()


# --------------------------------------------------------------------------------------------
# Confidence-bar math -- PURE (no I/O), unit-testable in isolation.
# --------------------------------------------------------------------------------------------

def default_bar_state() -> dict:
    return {"evidence_n": 0, "correct_n": 0, "consecutive_runs_above_bar": 0,
            "last_run_date": None, "confident": False, "cadence_days": CADENCE_DEFAULT_DAYS,
            "confident_since": None}


def update_confidence_state(prior: dict, *, run_evidence_n: int, run_correct_n: int,
                            run_date: str, bar_pct: float = BAR_PCT,
                            min_evidence: int = BAR_MIN_EVIDENCE,
                            min_consecutive: int = BAR_MIN_CONSECUTIVE_RUNS) -> dict:
    """Fold one run's (evidence_n, correct_n) into the CUMULATIVE per-subject state and
    recompute the confidence streak. PURE — takes and returns plain dicts, no file I/O, no
    clock reads (run_date is passed in). A run with run_evidence_n == 0 (nothing new to
    grade, or everything ungraded) still advances last_run_date but leaves the cumulative
    rate/streak untouched (an empty run is neither evidence FOR nor AGAINST confidence).

    Streak semantics: "sustained across >=3 consecutive audit runs" — the cumulative rate
    must be >=bar_pct (with >=min_evidence total graded points) on THIS run AND the
    min_consecutive-1 runs before it, unbroken. Any run where the cumulative rate dips below
    the bar (or evidence is still short of the floor) resets the streak to 0 -- a streak is
    consecutive-runs-CURRENTLY-passing, not lifetime-best.
    """
    new = dict(prior)
    new["evidence_n"] = int(prior.get("evidence_n", 0)) + int(run_evidence_n)
    new["correct_n"] = int(prior.get("correct_n", 0)) + int(run_correct_n)
    new["last_run_date"] = run_date
    if run_evidence_n > 0:
        rate = new["correct_n"] / new["evidence_n"] if new["evidence_n"] else 0.0
        passes = new["evidence_n"] >= min_evidence and rate >= bar_pct
        new["consecutive_runs_above_bar"] = (
            int(prior.get("consecutive_runs_above_bar", 0)) + 1 if passes else 0)
    # else: no new evidence this run -- streak carries over unchanged (neither built nor broken)
    was_confident = bool(prior.get("confident"))
    now_confident = new["consecutive_runs_above_bar"] >= min_consecutive
    new["confident"] = now_confident
    if now_confident and not was_confident:
        new["confident_since"] = run_date
        new["cadence_days"] = CADENCE_RELAXED_DAYS  # auto-relax, per J's "until we're confident"
    elif not now_confident:
        new["confident_since"] = None
        new["cadence_days"] = CADENCE_DEFAULT_DAYS
    return new


def cumulative_rate(state: dict) -> float:
    n = int(state.get("evidence_n", 0))
    return (int(state.get("correct_n", 0)) / n) if n else 0.0


# --------------------------------------------------------------------------------------------
# Cadence self-gate -- PURE (no I/O; caller supplies "today").
# --------------------------------------------------------------------------------------------

def should_run(state: dict, today: date, *, force: bool = False) -> tuple[bool, str]:
    """Never silent: always returns a reason string, whether running or skipping."""
    if force:
        return True, "forced (--force)"
    last = state.get("last_run_date")
    if not last:
        return True, "first run (no last_run_date on record)"
    try:
        last_d = date.fromisoformat(str(last)[:10])
    except ValueError:
        return True, f"unparseable last_run_date={last!r}, running defensively"
    gap = (today - last_d).days
    required = int(state.get("cadence_days") or CADENCE_DEFAULT_DAYS)
    if gap >= required:
        return True, f"due ({gap}d since {last}, cadence={required}d)"
    return False, f"SKIPPED (not due, last run {last}, cadence={required}d, {gap}d elapsed)"


# --------------------------------------------------------------------------------------------
# History ledger (append-only jsonl) -- one row per graded item + one summary row per run.
# --------------------------------------------------------------------------------------------

def already_graded_ids(subject: str, history_path: Optional[Path] = None) -> set[str]:
    # NOTE (2026-07-16, VETO-HTF-CONFLICT-REGRADE incident): the default must be resolved
    # HERE, inside the function body, not as `history_path: Path = HISTORY` in the signature.
    # A signature default is bound ONCE at module-import time -- `monkeypatch.setattr(fma,
    # "HISTORY", tmp_path)` (or any other runtime reassignment of the module-level HISTORY
    # constant) silently does NOT change it, so a caller relying on "the module constant
    # got patched" keeps writing to the REAL path. This exact bug let a test's fake
    # run_subject() call append 7 junk rows to the real automation/state/
    # free-model-audit-history.jsonl (caught and cleaned up same session) -- fixed here AND
    # in save_bar_state/load_bar_state/append_history/load_history_items/append_status_note
    # below, all of which had the identical bound-default shape.
    history_path = history_path if history_path is not None else HISTORY
    if not history_path.exists():
        return set()
    out: set[str] = set()
    for line in history_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("subject") == subject and r.get("kind") == "item" and r.get("item_id"):
            out.add(r["item_id"])
    return out


def load_history_items(subject: str, history_path: Optional[Path] = None) -> list[dict]:
    """Every "kind":"item" row EVER graded for a subject (oldest-first), across all past
    runs -- not just this run's newly-graded items. Read-only. Used by a subject's optional
    `extra_scorecard_section` (e.g. heartbeat_veto's per-reason-class breakdown) that needs
    the FULL graded population, not just the trickle of items newly graded today."""
    history_path = history_path if history_path is not None else HISTORY  # see already_graded_ids
    if not history_path.exists():
        return []
    out: list[dict] = []
    for line in history_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("subject") == subject and r.get("kind") == "item":
            out.append(r)
    return out


def append_history(rows: list[dict], history_path: Optional[Path] = None) -> None:
    history_path = history_path if history_path is not None else HISTORY  # see already_graded_ids
    if not rows:
        return
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


# --------------------------------------------------------------------------------------------
# Bar-state persistence (per-subject json)
# --------------------------------------------------------------------------------------------

def load_bar_state(path: Optional[Path] = None) -> dict:
    path = path if path is not None else BAR_STATE_PATH  # see already_graded_ids
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_bar_state(all_state: dict, path: Optional[Path] = None) -> None:
    path = path if path is not None else BAR_STATE_PATH  # see already_graded_ids
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(all_state, indent=2, default=str), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Scorecard renderer -- REUSES shadow_model_eval.py's markdown-scorecard pattern (per-model
# summary table + tick-by-tick detail + verdict section), adapted to grading rows.
# --------------------------------------------------------------------------------------------

def render_scorecard(subject: str, date_str: str, graded: list[dict], run_summary: dict,
                     bar_state: dict) -> str:
    total = len(graded)
    n_correct = sum(1 for g in graded if g.get("correct") is True)
    n_wrong = sum(1 for g in graded if g.get("correct") is False)
    n_ungraded = sum(1 for g in graded if g.get("correct") is None)
    n_counterfactual = sum(1 for g in graded if g.get("grading_method") == "counterfactual")
    n_llm = sum(1 for g in graded if g.get("grading_method") == "llm_judgment")

    vetoes = [g for g in graded if g.get("decision") == "veto"]
    gos = [g for g in graded if g.get("decision") == "go"]
    true_vetoes = sum(1 for g in vetoes if g.get("correct") is True)
    false_vetoes = sum(1 for g in vetoes if g.get("correct") is False)
    veto_graded = true_vetoes + false_vetoes
    single_lane_vetoes = sum(1 for g in vetoes if g.get("n_lanes_answered") == 1)
    go_correct = sum(1 for g in gos if g.get("correct") is True)
    go_wrong = sum(1 for g in gos if g.get("correct") is False)
    go_graded = go_correct + go_wrong
    veto_rate = round(100 * true_vetoes / veto_graded, 1) if veto_graded else None
    go_rate = round(100 * go_correct / go_graded, 1) if go_graded else None

    rate = round(100 * n_correct / (n_correct + n_wrong), 1) if (n_correct + n_wrong) else 0.0
    cum_rate = round(100 * cumulative_rate(bar_state), 1)

    L: list[str] = [
        f"# free-model-audit — {subject} — {date_str}", "",
        f"**Subject:** `{subject}`  ",
        f"**Generated:** {et_now().strftime('%Y-%m-%dT%H:%M:%S%z')}  ",
        f"**Confidence bar:** >={int(BAR_PCT*100)}% correct-grade rate over "
        f">={BAR_MIN_EVIDENCE} graded evidence points, sustained across "
        f">={BAR_MIN_CONSECUTIVE_RUNS} consecutive runs (same bar as the Nemotron shadow-"
        f"model promotion standard, analysis/shadow-model/PROMOTION-SCORECARD.md).",
        "",
        "## This run", "",
        "| Metric | Value |", "|---|---|",
        f"| Items collected | {run_summary.get('n_collected', 0)} |",
        f"| Already graded (skipped, dedupe) | {run_summary.get('n_already_graded', 0)} |",
        f"| Newly graded this run | {total} |",
        f"| Correct | {n_correct} |",
        f"| Wrong | {n_wrong} |",
        f"| Ungraded (insufficient data) | {n_ungraded} |",
        f"| This-run correct-grade rate | {n_correct}/{n_correct+n_wrong} = **{rate}%** |",
        f"| Graded via counterfactual replay | {n_counterfactual} |",
        f"| Graded via blind Sonnet judgment (fallback) | {n_llm} |",
        "",
        "## Veto-specific (the costlier error class is FALSE-VETO — a blocked winner)", "",
        "| Metric | Value |", "|---|---|",
        f"| Vetoes graded | {veto_graded} / {len(vetoes)} |",
        f"| TRUE vetoes (correctly blocked a loser/marginal) | {true_vetoes} |",
        f"| FALSE vetoes (wrongly blocked a winner) | {false_vetoes} |",
        f"| **Veto-only accuracy** (the safety-net's actual job) "
        f"| {'**' + str(veto_rate) + '%**' if veto_rate is not None else 'n/a'} |",
        f"| GO decisions graded | {go_graded} / {len(gos)} |",
        f"| **GO-only accuracy** (fill went on to be non-losing) "
        f"| {'**' + str(go_rate) + '%**' if go_rate is not None else 'n/a'} |",
        f"| Single-lane vetoes (only 1 model answered — asymmetry: a lone NO is enough to "
        f"veto, a lone GO is enough to pass) | {single_lane_vetoes} / {len(vetoes)} |",
        "",
        "**Read this split, not just the blended rate above.** The blended \"correct-grade "
        "rate\" mixes two DIFFERENT questions: (1) did the veto layer correctly catch a bad "
        "entry (its actual job), and (2) did a GO'd trade go on to make money (mostly a "
        "function of the underlying 0DTE strategy's own win rate, which CLAUDE.md's own live "
        "threshold sets at only >=45% — most 0DTE signals are EXPECTED to lose sometimes; "
        "that is not a veto-layer defect). A low blended rate driven by GO-side losses is NOT "
        "the same finding as a low veto-only rate — only the latter says the safety net itself "
        "is unreliable. Read both numbers above before concluding which one moved.",
        "",
        "## Cumulative (all-time, this subject)", "",
        "| Metric | Value |", "|---|---|",
        f"| Evidence points | {bar_state.get('evidence_n', 0)} |",
        f"| Cumulative correct-grade rate | **{cum_rate}%** |",
        f"| Consecutive runs above bar | {bar_state.get('consecutive_runs_above_bar', 0)} "
        f"/ {BAR_MIN_CONSECUTIVE_RUNS} |",
        f"| Confident | {'YES' if bar_state.get('confident') else 'no'} |",
        f"| Current cadence | every {bar_state.get('cadence_days', CADENCE_DEFAULT_DAYS)} day(s) |",
        "",
        "## Detail", "",
        "| item_id | decision | grading_method | correct | evidence |",
        "|---|---|---|---|---|",
    ]
    for g in graded:
        corr = {True: "OK", False: "XX", None: "?"}[g.get("correct")]
        ev = str(g.get("evidence_summary", ""))[:140].replace("|", "/")
        L.append(f"| {g.get('item_id','?')} | {g.get('decision','?')} "
                f"| {g.get('grading_method','?')} | {corr} | {ev} |")
    L.append("")
    L.append("## Verdict")
    L.append("")
    if bar_state.get("confident"):
        L.append(f"**CONFIDENT** — cumulative {cum_rate}% over {bar_state.get('evidence_n')} "
                f"evidence points, sustained {bar_state.get('consecutive_runs_above_bar')} "
                f"consecutive runs. Cadence relaxed to every {CADENCE_RELAXED_DAYS} days.")
    elif bar_state.get("evidence_n", 0) < BAR_MIN_EVIDENCE:
        L.append(f"**INSUFFICIENT EVIDENCE** — {bar_state.get('evidence_n', 0)}/"
                f"{BAR_MIN_EVIDENCE} graded points. Keep auditing every "
                f"{bar_state.get('cadence_days', CADENCE_DEFAULT_DAYS)} days.")
    else:
        L.append(f"**NOT YET CONFIDENT** — cumulative {cum_rate}% "
                f"(bar {int(BAR_PCT*100)}%), streak {bar_state.get('consecutive_runs_above_bar')}"
                f"/{BAR_MIN_CONSECUTIVE_RUNS} consecutive runs above bar.")
    L.append("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------------
# STATUS.md note (one line, append-only, never overwrites)
# --------------------------------------------------------------------------------------------

def append_status_note(msg: str, status_path: Optional[Path] = None) -> None:
    status_path = status_path if status_path is not None else STATUS_MD  # see already_graded_ids
    try:
        with status_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n- [{et_now():%Y-%m-%d %H:%M} ET] free-model-audit: {msg}\n")
    except OSError as e:
        print(f"[free_model_audit] WARN STATUS.md append failed: {e}", file=sys.stderr)


# --------------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------------

def run_subject(subject: str, *, force: bool = False, allow_llm_fallback: bool = True,
                today: Optional[date] = None) -> dict:
    """Run one subject's audit. Always returns a summary dict; NEVER silent (prints a
    SKIPPED line and returns early if not due, per OP-25/C7 -- a scheduled fire that does
    nothing must still say so)."""
    today = today or et_now().date()
    adapter = AUDIT_SUBJECTS.get(subject)
    if adapter is None:
        msg = f"unknown subject {subject!r} (known: {sorted(AUDIT_SUBJECTS)})"
        print(f"[free_model_audit] ERROR {msg}", file=sys.stderr)
        return {"subject": subject, "status": "ERROR", "reason": msg}
    if not adapter.wired:
        msg = f"SKIPPED — subject {subject!r} is a registered TODO stub, not wired yet"
        print(f"[free_model_audit] {msg}")
        return {"subject": subject, "status": "SKIPPED_UNWIRED", "reason": msg}

    all_state = load_bar_state()
    prior = all_state.get(subject) or default_bar_state()
    run, reason = should_run(prior, today, force=force)
    print(f"[free_model_audit] {subject}: {reason}")
    if not run:
        return {"subject": subject, "status": "SKIPPED_NOT_DUE", "reason": reason}

    since = date.fromisoformat(str(prior["last_run_date"])[:10]) if prior.get("last_run_date") else None
    items = list(adapter.collect(since, today))
    seen = already_graded_ids(subject)
    new_items = [it for it in items if it.item_id not in seen]
    n_skipped_dedupe = len(items) - len(new_items)

    opts = {"allow_llm_fallback": allow_llm_fallback}
    graded_rows: list[dict] = []
    history_rows: list[dict] = []
    for it in new_items:
        try:
            result = adapter.grade(it, opts)
        except Exception as e:  # noqa: BLE001 -- one bad item must never abort the run
            result = {"grading_method": "ungraded_insufficient_data", "correct": None,
                      "reason": f"grader raised {type(e).__name__}: {e}"}
        if result.get("grading_method") not in GRADING_METHODS:
            result["grading_method"] = "ungraded_insufficient_data"
            result["correct"] = None
        row = {**result, "item_id": it.item_id, "subject": subject,
               "timestamp_et": it.timestamp_et, "account": it.account}
        graded_rows.append(row)
        history_rows.append({"kind": "item", **row, "logged_at": et_now().isoformat()})

    run_evidence_n = sum(1 for g in graded_rows if g.get("correct") is not None)
    run_correct_n = sum(1 for g in graded_rows if g.get("correct") is True)
    new_state = update_confidence_state(prior, run_evidence_n=run_evidence_n,
                                        run_correct_n=run_correct_n,
                                        run_date=today.isoformat())
    all_state[subject] = new_state
    save_bar_state(all_state)

    run_summary = {"n_collected": len(items), "n_already_graded": n_skipped_dedupe,
                   "n_new_graded": len(graded_rows), "n_correct": run_correct_n,
                   "n_evidence": run_evidence_n}
    date_str = today.isoformat()
    scorecard = render_scorecard(subject, date_str, graded_rows, run_summary, new_state)
    if adapter.extra_scorecard_section is not None:
        try:
            extra_md = adapter.extra_scorecard_section(load_history_items(subject), today)
        except Exception as e:  # noqa: BLE001 -- an extension failing must never break the run
            extra_md = (f"\n_extra_scorecard_section failed: {type(e).__name__}: {e}_\n")
            print(f"[free_model_audit] WARN {subject} extra_scorecard_section failed: "
                 f"{type(e).__name__}: {e}", file=sys.stderr)
        if extra_md:
            scorecard += "\n" + extra_md
    out_dir = SCORECARD_ROOT / subject.replace("_", "-")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}-scorecard.md"
    out_path.write_text(scorecard, encoding="utf-8")

    history_rows.append({"kind": "run_summary", "subject": subject, "date": date_str,
                         **run_summary, "cumulative_state": new_state,
                         "logged_at": et_now().isoformat()})
    append_history(history_rows)

    if new_state.get("confident") and not prior.get("confident"):
        append_status_note(
            f"subject '{subject}' crossed confidence bar (cumulative "
            f"{round(100*cumulative_rate(new_state),1)}% over {new_state['evidence_n']} pts, "
            f"{new_state['consecutive_runs_above_bar']} consecutive runs) — cadence relaxed "
            f"to every {CADENCE_RELAXED_DAYS} days. Scorecard: "
            f"{out_path.relative_to(REPO)}")

    print(f"[free_model_audit] {subject}: collected={len(items)} new_graded={len(graded_rows)} "
         f"correct={run_correct_n}/{run_evidence_n} cumulative="
         f"{round(100*cumulative_rate(new_state),1)}%/{new_state['evidence_n']}pts "
         f"streak={new_state['consecutive_runs_above_bar']} -> {out_path.relative_to(REPO)}")
    return {"subject": subject, "status": "RAN", **run_summary, "scorecard": str(out_path),
           "bar_state": new_state}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", default="all",
                    help=f"one of {sorted(AUDIT_SUBJECTS)}, or 'all' to run every registered "
                         "subject in sequence (default: all -- each subject still self-gates "
                         "its OWN cadence independently, so 'all' is safe to fire daily)")
    ap.add_argument("--force", action="store_true", help="ignore the cadence gate")
    ap.add_argument("--no-llm-fallback", action="store_true",
                    help="counterfactual-only; ungrade rather than call Sonnet")
    args = ap.parse_args()
    ok_statuses = ("RAN", "SKIPPED_NOT_DUE", "SKIPPED_UNWIRED")
    subjects = sorted(AUDIT_SUBJECTS) if args.subject == "all" else [args.subject]
    exit_code = 0
    for subject in subjects:
        result = run_subject(subject, force=args.force,
                             allow_llm_fallback=not args.no_llm_fallback)
        if result.get("status") not in ok_statuses:
            print(f"[free_model_audit] {subject}: FAILED status={result.get('status')}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
