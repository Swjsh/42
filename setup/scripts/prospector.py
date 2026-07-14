"""prospector.py -- Gamma_Prospector, the exogenous-idea organ.

WHY THIS EXISTS (J, 2026-07-09, verbatim): "these are things gamma should be
thinking of on its own! where is the autonomy? gamma hasn't introduced a single
new idea like this at all yet." Diagnosis (Fable): every existing idea-producing
organ is ENDOGENOUS -- trade_autopsy.py mines OUR OWN losses, chef proposes OUR
OWN strategy variants, kitchen/grinders tune OUR OWN knobs, swarm_consult reviews
OUR OWN proposals. Not one of them scans OUTWARD: new data feeds, indicator
ecosystems, community tooling, academic intraday anomalies, cross-asset tells.
This module is that organ.

THE LOOP (one nightly fire, Gamma_Prospector 21:30 ET):
  1. pick_next_beat()  -- rotate through 7 fixed research beats; the index is
     persisted in analysis/prospector/state.json so consecutive nights cover
     DIFFERENT ground instead of re-asking the same question.
  2. scan_beat()       -- ONE free-tier LLM call for that beat. Reuses
     swarm_consult.py's provider-call plumbing verbatim (_provider_call: the
     openrouter/cerebras/groq routing, key loading, fail-open error envelope)
     rather than its higher-level consult()/brainstorm mode, because brainstorm
     mode's baked-in prose instructions collide with the strict-JSON contract
     this module needs for triage. Tries each model in
     DEFAULT_PERSPECTIVE_MODELS + PERSPECTIVE_FALLBACK_POOL IN TURN (not a full
     5-way fan-out -- a nightly single-beat scan only needs ONE well-formed
     response; sequential-until-success is the cheaper, leaner choice, and it
     is still fail-open across the WHOLE free roster). If every model fails
     (no free lane up tonight), this is NOT an error: log it and move on --
     the ledger is untouched and remains fully readable ("skip-with-log").
  3. triage_one()      -- coerce each raw LLM object into the fixed idea-row
     schema. Unparseable/ambiguous fields default to the WEAKEST bucket (never
     falsely promotable): unknown cost -> "paid", unknown instrument_fit ->
     "both", unknown testability -> "vague".
  4. append_ledger_rows() -- idempotent append to
     analysis/prospector/ideas-ledger.jsonl, keyed by dedupe_key. A dedupe_key
     that was EVER recorded as killed (a "kind":"kill" row) can never re-enter,
     even under a different beat's future wording of the same idea.
  5. promote_top1()    -- the single oldest not-yet-promoted "battery-ready"
     idea becomes a pre-registered STUDY SPEC stub (hypothesis / data / null /
     pass bar -- NOT code) written into strategy/candidates/_chef-inbox/, the
     SAME standing intake Chef already drains every wake (conductor.md STAGE 1
     priority #5, "author inboxes ... _chef-inbox -> chef"). See
     markdown/infra/PROSPECTOR-SPEC.md for why this beats a generic queue.md
     append or cook-queue.jsonl entry.
  6. surface()         -- writes automation/state/prospector-last.json (the
     SAME pattern trade-autopsy-last.json uses -- firm_brief.py reads it and
     renders one line) and bumps prospector's OWN generative counters in
     analysis/prospector/state.json. Deliberately does NOT touch
     automation/state/autonomy-metric.json: that file is fully
     RECOMPUTED-AND-OVERWRITTEN by conductor_outcome.compute_metric() on every
     call (met_path.write_text(json.dumps(metric...)) with no read-merge --
     verified by reading the function body before writing this module), so any
     externally-added key would be silently wiped on the next natural
     recompute. Per this build's own instructions ("if that file's schema
     allows additive keys") the answer, checked, is NO -- see
     markdown/infra/PROSPECTOR-SPEC.md.

Never touches engine/params/exits. Never places an order. Never edits another
organ's ledger. Notify-only, $0 (free-tier only, no paid fallback), fail-open,
exits 0 always.

Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/prospector.py
    backtest/.venv/Scripts/python.exe setup/scripts/prospector.py --beat options_structure_metrics
    backtest/.venv/Scripts/python.exe setup/scripts/prospector.py --dry-run
    backtest/.venv/Scripts/python.exe setup/scripts/prospector.py --seed   # one-time
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
    _sys.stdout = open(_log_dir / "prospector.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "prospector.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402
import swarm_consult as sc  # noqa: E402 -- reused call plumbing, see module docstring

STATE_DIR = REPO / "automation" / "state"
OUT_DIR = REPO / "analysis" / "prospector"
STATE_FILE = OUT_DIR / "state.json"
LEDGER_FILE = OUT_DIR / "ideas-ledger.jsonl"
LAST_JSON = STATE_DIR / "prospector-last.json"
CHEF_INBOX = REPO / "strategy" / "candidates" / "_chef-inbox"
OUTBOX = STATE_DIR / "discord-outbox.jsonl"

# The 7 fixed research beats (rotating, persisted index -- see pick_next_beat).
BEATS: tuple[str, ...] = (
    "data_feeds_free",
    "tv_community_indicators",
    "options_structure_metrics",
    "academic_intraday_anomalies",
    "cross_asset_signals",
    "futures_positioning",
    "microstructure_internals",
)

_VALID_COST = {"$0", "paid"}
_VALID_FIT = {"0dte", "mes", "both"}
_VALID_TESTABILITY = {"battery-ready", "needs-data", "vague"}

MAX_IDEAS_PER_SCAN = 6  # bound: even a chatty model can't flood one fire


# ─────────────────────────────────────────────────────────────────────────────
# Prompts (the outward-scanning contract)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a market-research scout for Project Gamma, an autonomous
0DTE SPY options + MES/MNQ futures trading system. You are NOT placing trades, NOT
tuning existing parameters, and NOT reviewing Gamma's own work -- your ONLY job is
to scan OUTWARD for external data sources, indicators, community tooling, and
published research the system does not use yet. Be specific and concrete: name the
actual data source / vendor / API / paper wherever you can. A vague category
("look at options data") is worthless; "CBOE VIX1D index, ticker ^VIX1D, free via
most market-data vendors" is useful.

Reply with ONLY a JSON array (no prose, no markdown code fences, no commentary
before or after) of 3 to 5 objects. Each object must have EXACTLY these keys:
  "idea": one sentence -- the idea's name and what it does
  "mechanism_1line": one sentence -- WHY this would help (what edge/insight it exploits)
  "data_source": where the data/signal actually comes from (name the vendor / API /
      URL / paper if you know it -- never just "the internet")
  "cost": the literal string "$0" or "paid"
  "instrument_fit": one of "0dte", "mes", "both" -- which Gamma instrument(s) fit
      (0DTE SPY options, or MES/MNQ futures, or both)
  "testability": one of "battery-ready" (the data already exists somewhere Gamma
      could fetch this week and backtest), "needs-data" (a genuinely new feed or
      pipeline would be needed first), or "vague" (interesting but not yet a
      testable claim)
"""

BEAT_QUESTIONS: dict[str, str] = {
    "data_feeds_free": (
        "Propose 3-5 FREE or near-free market data feeds Project Gamma likely does "
        "not use yet (beyond Alpaca/TradingView/yfinance/FINRA short-volume/CBOE "
        "OI/CFTC COT, which are already wired or already scouted) that could sharpen "
        "0DTE SPY or MES/MNQ intraday decisions -- e.g. Treasury/FRED macro series, "
        "exchange-published auction data, alternative-data free tiers, options flow "
        "aggregators with a free plan."
    ),
    "tv_community_indicators": (
        "Propose 3-5 TradingView built-in or community (public Pine Script library) "
        "indicators/tools NOT currently used by Project Gamma's own indicator set "
        "(ribbon/EMA/RSI/trendlines/level-memory) that reveal a structural read those "
        "don't -- e.g. volume profile / volume shelves, auction market theory tools, "
        "auto support/resistance scripts, order-flow proxies, harmonic/pattern-grammar "
        "labeling scripts."
    ),
    "options_structure_metrics": (
        "Propose 3-5 options-structure-derived metrics for SPY 0DTE that Project Gamma "
        "does not read today (it already has VIX level + a banked CBOE GEX/OI archive) "
        "-- e.g. put/call ratio, dealer gamma exposure variants, VIX1D (CBOE's 1-day "
        "vol index), IV skew/term structure, dark-pool short-volume ratios (DIX-style), "
        "max pain, 0DTE gamma concentration."
    ),
    "academic_intraday_anomalies": (
        "Propose 3-5 PUBLISHED academic or quant-finance findings about intraday "
        "equity/futures anomalies (name the effect and, if you know it, the paper or "
        "researcher) that could inform 0DTE SPY or MES/MNQ timing -- e.g. opening-range "
        "predictive power, VWAP reversion stats, turn-of-month effects, overnight-gap-"
        "fill statistics, closing-auction imbalance drift, lunch-lull volatility "
        "compression, time-of-day seasonality in win rate."
    ),
    "cross_asset_signals": (
        "Propose 3-5 CROSS-ASSET tells for SPY 0DTE or MES/MNQ direction that Project "
        "Gamma does not read today -- e.g. VIX term structure (contango/backwardation), "
        "10Y-2Y yield spread moves, DXY dollar index, crude oil, high-yield credit "
        "spreads, sector-rotation ETF relative strength."
    ),
    "futures_positioning": (
        "Propose 3-5 futures-positioning data sources relevant to the MES/MNQ swing "
        "mirror -- e.g. CFTC Commitments of Traders (large-speculator net "
        "positioning), CME open interest changes, overnight Globex session high/low/"
        "range, futures curve/basis, exchange volume profile."
    ),
    "microstructure_internals": (
        "Propose 3-5 market-internals or microstructure tells day-traders watch that "
        "Project Gamma does not read today -- e.g. NYSE TICK, advance-decline "
        "line/ADD, TRIN/Arms Index, up/down volume ratio, order-book imbalance "
        "proxies, FINRA daily short-sale volume."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers -- JSON extraction + triage (unit-tested, no I/O)
# ─────────────────────────────────────────────────────────────────────────────


def _slugify(s: str, max_len: int = 48) -> str:
    out = []
    for c in s.lower():
        if c.isalnum():
            out.append(c)
        elif c in " -_":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:max_len] or "untitled"


def make_dedupe_key(beat: str, idea_text: str) -> str:
    """Stable idempotency key: beat-namespaced slug of the idea text.

    A KNOWN v1 limitation (documented in PROSPECTOR-SPEC.md): LLM rewording
    across nights will NOT collapse to the same key -- only identical/near-
    identical repeats (e.g. two models converging on the same phrasing, or a
    re-run the same night) dedupe. Hand-seeded ideas use their own literal
    human-chosen id as the dedupe_key instead (see SEED_IDEAS) -- both are just
    "stable strings," which is all idempotency requires.
    """
    return f"{beat}:{_slugify(idea_text, 40)}"


def _extract_json_array(text: str) -> Optional[list]:
    """Best-effort extraction of a JSON array from free LLM text. Tries, in
    order: (1) the raw text as-is (the compliant case), (2) a fenced ```json
    block if present anywhere in the text, (3) the widest '[' .. ']' slice.
    Returns None if nothing parses as a JSON list -- never raises.
    """
    text = (text or "").strip()
    if not text:
        return None
    candidates = [text]
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1).strip())
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, list):
            return obj
    return None


def triage_one(beat: str, raw: Any) -> Optional[dict]:
    """Coerce ONE raw candidate into the fixed idea-row schema. Defensive
    defaults push anything ambiguous to the WEAKEST bucket so a parsing fluke
    can never falsely qualify an idea for promotion. Returns None only if
    there is no usable idea text at all (never raises)."""
    if not isinstance(raw, dict):
        return None
    idea = str(raw.get("idea") or "").strip()
    if not idea:
        return None
    mechanism = str(raw.get("mechanism_1line") or raw.get("mechanism") or "").strip()
    data_source = str(raw.get("data_source") or "").strip() or "unspecified"
    cost_raw = str(raw.get("cost") or "").strip().lower()
    cost = "$0" if cost_raw in ("$0", "0", "0.0", "free") else "paid"
    fit_raw = str(raw.get("instrument_fit") or "").strip().lower()
    fit = fit_raw if fit_raw in _VALID_FIT else "both"
    testability_raw = str(raw.get("testability") or "").strip().lower()
    testability = testability_raw if testability_raw in _VALID_TESTABILITY else "vague"
    dedupe_key = make_dedupe_key(beat, idea)
    return {
        "id": dedupe_key,
        "beat": beat,
        "idea": idea,
        "mechanism_1line": mechanism,
        "data_source": data_source,
        "cost": cost,
        "instrument_fit": fit,
        "testability": testability,
        "dedupe_key": dedupe_key,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ledger I/O (append-only jsonl; kills are rows, never mutations)
# ─────────────────────────────────────────────────────────────────────────────


def load_ledger(path: Path = LEDGER_FILE) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def existing_idea_keys(rows: list[dict]) -> set:
    return {r["dedupe_key"] for r in rows if r.get("kind") != "kill" and r.get("dedupe_key")}


def killed_dedupe_keys(rows: list[dict]) -> set:
    return {r["dedupe_key"] for r in rows if r.get("kind") == "kill" and r.get("dedupe_key")}


def append_ledger_rows(new_rows: list[dict], path: Path = LEDGER_FILE) -> int:
    """Idempotent append: skips any row whose dedupe_key already exists as an
    idea row OR was EVER killed. Returns the count actually appended. Never
    raises (a write failure degrades to 0-appended, logged by the caller)."""
    if not new_rows:
        return 0
    existing = load_ledger(path)
    present = existing_idea_keys(existing)
    killed = killed_dedupe_keys(existing)
    to_write = [
        r for r in new_rows
        if r.get("dedupe_key") and r["dedupe_key"] not in present and r["dedupe_key"] not in killed
    ]
    if not to_write:
        return 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for r in to_write:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError:
        return 0
    return len(to_write)


def kill_idea(dedupe_key: str, reason: str, path: Path = LEDGER_FILE) -> dict:
    """Append a kill row. Ideas ledger is append-only truth -- a kill is a NEW
    row, never a mutation of the original idea row. Once killed, dedupe_key
    can never re-enter (see append_ledger_rows / promote_top1)."""
    row = {
        "kind": "kill",
        "dedupe_key": dedupe_key,
        "reason": reason,
        "ts_et": et_now().isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Beat rotation state
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_STATE: dict = {
    "beat_index": 0,
    "last_beat": None,
    "last_run_et": None,
    "fires_total": 0,
    "ideas_total": 0,
    "promoted_total": 0,
    "promoted_dedupe_keys": [],
}


def load_state(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return dict(_DEFAULT_STATE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return dict(_DEFAULT_STATE)
    if not isinstance(data, dict):
        return dict(_DEFAULT_STATE)
    return {**_DEFAULT_STATE, **data}


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pick_next_beat(state: dict, beats: tuple[str, ...] = BEATS) -> str:
    """Pure: which beat fires next, given the persisted rotation index."""
    idx = int(state.get("beat_index", 0) or 0) % len(beats)
    return beats[idx]


def advance_beat(state: dict, beats: tuple[str, ...] = BEATS) -> dict:
    """Returns a NEW state dict (immutable-update) with beat_index advanced,
    wrapping back to 0 after the last beat."""
    idx = int(state.get("beat_index", 0) or 0) % len(beats)
    return {**state, "beat_index": (idx + 1) % len(beats)}


# ─────────────────────────────────────────────────────────────────────────────
# Free-swarm dispatch (reuses swarm_consult's provider-call plumbing)
# ─────────────────────────────────────────────────────────────────────────────


def scan_beat(
    beat: str,
    *,
    models: Optional[list] = None,
    call_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """ONE free-tier scan for `beat`. Tries each model in
    DEFAULT_PERSPECTIVE_MODELS + PERSPECTIVE_FALLBACK_POOL in turn (sequential,
    not a fan-out -- see module docstring) until one returns content that
    parses as a JSON array. `call_fn` is injectable for tests (defaults to
    swarm_consult._provider_call so production reuses the SAME provider
    routing / key loading / fail-open envelope every other swarm caller in
    this repo uses). Never raises -- ANY exception from a candidate model is
    caught and treated as that candidate failing, so one bad model can never
    take down the scan.

    Returns {"ok": bool, "model": str|None, "ideas_raw": list|None, "error": str|None}.
    """
    call = call_fn or sc._provider_call
    candidates = list(models) if models else list(sc.DEFAULT_PERSPECTIVE_MODELS) + list(
        sc.PERSPECTIVE_FALLBACK_POOL
    )
    question = BEAT_QUESTIONS.get(beat, BEAT_QUESTIONS[BEATS[0]])
    last_err: Optional[str] = None
    for m in candidates:
        try:
            r = call(
                m,
                prompt=question,
                system=SYSTEM_PROMPT,
                max_tokens=2000,
                temperature=0.5,
                timeout=sc.PERSPECTIVE_TIMEOUT_S,
                task_id=f"prospector.{beat}",
            )
        except Exception as exc:  # noqa: BLE001 -- one bad model must never crash the scan
            last_err = f"{type(exc).__name__}: {exc}"
            continue
        if not r.get("ok") or not (r.get("content") or "").strip():
            last_err = r.get("error") or "empty_content"
            continue
        arr = _extract_json_array(r["content"])
        if arr is None:
            last_err = "unparseable_json"
            continue
        return {"ok": True, "model": m, "ideas_raw": arr, "error": None}
    return {"ok": False, "model": None, "ideas_raw": None, "error": last_err or "no_free_lane_up"}


# ─────────────────────────────────────────────────────────────────────────────
# Promotion -- the study-spec stub into Chef's standing intake
# ─────────────────────────────────────────────────────────────────────────────

# Hand-authored spec for this build's named first promotion (task instruction:
# "promote gex_flip as this build's first study-spec stub ... it needs zero new
# data"). Every OTHER future battery-ready promotion gets the generic templated
# spec built from the idea row's own fields inside promote_top1() below.
STUDY_SPECS: dict[str, dict] = {
    "gex_flip_from_banked_cboe": {
        "hypothesis": (
            "SPY's proximity to the CBOE-derived zero-gamma flip point (the strike "
            "where net dealer GEX crosses from negative to positive) predicts a "
            "continuation-vs-reversion regime for 0DTE entries: price BELOW the flip "
            "(negative gamma) sees dealer hedging AMPLIFY moves (favor breakout/"
            "continuation setups), price ABOVE the flip (positive gamma) sees dealer "
            "hedging DAMPEN moves (favor fade/reversion setups, penalize breakout "
            "chases)."
        ),
        "data": (
            "journal/gex-archive/*-cboe.json (Gamma_CboeOiBank, free CBOE CDN, banking "
            "daily since 2026-06-22 -- 14 sessions on disk as of 2026-07-09, ZERO new "
            "fetch needed) joined by date to the existing real-OPRA-fills 0DTE trade "
            "log. gex_regime.py (net-GEX sign / zero-gamma-flip / wall computation) is "
            "ALREADY BUILT -- zero new code needed to read the archive, only to wire it "
            "into a backtest join."
        ),
        "null": (
            "trade outcome (win/loss, MFE, stop-hit rate) for a given setup is "
            "INDEPENDENT of which side of the zero-gamma flip SPY closed the prior "
            "session on -- i.e. the GEX regime tag adds no discriminating power over "
            "the engine's existing filters."
        ),
        "pass_bar": (
            "per gex_regime.assess_backtest_feasibility, a well-powered backtest needs "
            ">= 60-90 as-of days (14 banked as of 2026-07-09 -- this stub is "
            "CHEAPEST-FIRST bookkeeping, not a request to run the full battery early). "
            "Until the floor clears, the bounded FIRST deliverable is NOT a backtest: "
            "it is (a) a feasibility/continuity check confirming the archive is still "
            "accruing daily (Gamma_CboeOiBank + gex_archive_health.py already do this) "
            "and (b) a PRE-REGISTERED backtest design (exact join key, exact null, exact "
            "OP-16 edge_capture pass bar) filed now so the day the day-count crosses the "
            "floor there is zero fresh-design lag. Cross-reference: "
            "'CLIMB-LADDER-NEXT-RUNG-IS-CLASS' in automation/overnight/queue.md already "
            "tracks this exact wait -- this stub gives Chef the pre-registered plan to "
            "execute the moment it clears, instead of re-deriving it from scratch then."
        ),
    },
}

_GENERIC_PASS_BAR = (
    "OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day "
    "no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring "
    "proposal reaches conductor-proposals.jsonl."
)


def _sentence(s: str) -> str:
    """Strip a lone trailing period so callers can safely re-punctuate without
    producing '..' when a field already ends a sentence."""
    s = (s or "").strip()
    return s[:-1] if s.endswith(".") and not s.endswith("..") else s


def render_chef_inbox_item(idea_row: dict, *, date: str, hypothesis: str, data: str,
                           null: str, pass_bar: str, deps: str = "depends:none") -> str:
    """Render ONE _chef-inbox/*.md item matching the format documented in
    strategy/candidates/_chef-inbox/README.md EXACTLY (section headers +
    **Routed by:**/**Priority:**/**Category:**/**Source:** fields) -- Chef (the
    real consumer) reads every item in that shape; this stub must be
    indistinguishable in structure from a hand-authored one."""
    title = idea_row["idea"][:70]
    finding = (
        f"Prospector beat `{idea_row['beat']}` surfaced: "
        f"{_sentence(idea_row['idea'])} -- "
        f"{_sentence(idea_row.get('mechanism_1line', '')) or '(no mechanism given)'}. "
        f"Data source: {_sentence(idea_row.get('data_source', 'unspecified'))}. "
        f"Cost: {idea_row.get('cost', '?')}. "
        f"Instrument fit: {idea_row.get('instrument_fit', '?')}."
    )
    source = idea_row.get("source") or "Gamma_Prospector free swarm"
    return (
        f"# Chef Inbox — {title}\n\n"
        f"**Routed by:** Gamma_Prospector {date}\n"
        f"**Priority:** MED\n"
        f"**Category:** New data signal / exogenous idea\n"
        f"**Source:** {source}\n\n"
        f"## The Finding\n{finding}\n\n"
        f"## Research Question for Chef\n{hypothesis}\n\n"
        f"## Backtest Request\n"
        f"Data: {data}\n"
        f"Null hypothesis: {null}\n"
        f"Pass bar: {pass_bar}\n\n"
        f"## Files for Reference\n"
        f"analysis/prospector/ideas-ledger.jsonl (dedupe_key: {idea_row['dedupe_key']}) "
        f"· markdown/infra/PROSPECTOR-SPEC.md\n\n"
        f"## Priority / Dependencies\n{deps}\n"
    )


def promote_top1(rows: list[dict], state: dict, *, date: str,
                 inbox_dir: Path = CHEF_INBOX) -> Optional[dict]:
    """Pick the single OLDEST not-yet-promoted 'battery-ready' idea (FIFO --
    first surfaced, first studied; simple and fair, no scoring model to game)
    and write it as a pre-registered STUDY SPEC stub into _chef-inbox/. Idempotent:
    a dedupe_key already in state['promoted_dedupe_keys'] is skipped, so calling
    this every fire never double-promotes. Returns the promoted row (plus the
    filename it wrote), or None if nothing is eligible. Writes NO code, only
    the spec markdown."""
    already_promoted = set(state.get("promoted_dedupe_keys", []) or [])
    killed = killed_dedupe_keys(rows)
    candidates = [
        r for r in rows
        if r.get("kind") != "kill"
        and r.get("testability") == "battery-ready"
        and r.get("dedupe_key") not in already_promoted
        and r.get("dedupe_key") not in killed
    ]
    if not candidates:
        return None
    pick = candidates[0]
    spec = STUDY_SPECS.get(pick["dedupe_key"]) or {
        "hypothesis": (
            f"{_sentence(pick['idea'])} -- this carries a testable directional/timing "
            f"edge for {pick.get('instrument_fit', 'both')}."
        ),
        "data": pick.get("data_source", "unspecified"),
        "null": (
            "the signal has no measurable effect on entry/exit quality vs the "
            "existing engine baseline over the same days."
        ),
        "pass_bar": _GENERIC_PASS_BAR,
    }
    text = render_chef_inbox_item(pick, date=date, **spec)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date}-prospector-{pick['dedupe_key'].split(':')[-1][:44]}.md"
    try:
        (inbox_dir / fname).write_text(text, encoding="utf-8")
    except OSError:
        return None
    return {**pick, "_chef_inbox_file": fname}


# ─────────────────────────────────────────────────────────────────────────────
# Seed data -- tonight's 12 entries (2026-07-09 build)
# ─────────────────────────────────────────────────────────────────────────────
# gex_flip_from_banked_cboe is FIRST so promote_top1's FIFO rule promotes it
# ahead of the other 2 battery-ready seeds (vix1d_gate, volume_shelf_tv_vp) --
# exercising the real production promotion path rather than special-casing it.

SEED_IDEAS: tuple[dict, ...] = (
    {
        "id": "gex_flip_from_banked_cboe", "beat": "options_structure_metrics",
        "idea": "Tag every 0DTE session by which side of the CBOE zero-gamma-flip "
                "SPY closed on, using the archive Gamma_CboeOiBank already banks.",
        "mechanism_1line": "Dealer hedging flips from move-dampening (positive gamma) "
                           "to move-amplifying (negative gamma) at the zero-gamma "
                           "strike -- a regime tag no current filter reads.",
        "data_source": "journal/gex-archive/*-cboe.json (Gamma_CboeOiBank, free CBOE "
                       "CDN, 14 sessions banked as of 2026-07-09) + gex_regime.py "
                       "(already built).",
        "cost": "$0", "instrument_fit": "0dte", "testability": "battery-ready",
        "dedupe_key": "gex_flip_from_banked_cboe",
        "source": "fable-2026-07-09",
        "note": "14 sessions ALREADY BANKED by Gamma_CboeOiBank -- nothing consumes "
                "it yet; cheapest first study (zero new data fetch).",
    },
    {
        "id": "vix1d_gate", "beat": "options_structure_metrics",
        "idea": "Read CBOE's VIX1D (1-day volatility index, ticker ^VIX1D) as a "
                "same-horizon vol gate instead of only the 30-day headline VIX.",
        "mechanism_1line": "VIX1D isolates ULTRA-short-dated (next-day/0DTE-horizon) "
                           "implied vol -- a more precisely-dated 'is today expected "
                           "to be calm or violent' gate than 30-day VIX (C5: VIX "
                           "character > VIX level).",
        "data_source": "CBOE VIX1D index -- same access path Gamma already uses for "
                       "VIX (Alpaca index endpoints or yfinance fallback).",
        "cost": "$0", "instrument_fit": "0dte", "testability": "battery-ready",
        "dedupe_key": "vix1d_gate",
        "source": "fable-2026-07-09",
    },
    {
        "id": "volume_shelf_tv_vp", "beat": "tv_community_indicators",
        "idea": "Add TradingView's Volume Profile (Visible Range) study and read its "
                "high-volume-node 'shelves' as a structural level source.",
        "mechanism_1line": "High-volume nodes mark where the market previously "
                           "accepted price for extended time -- SPY/MES tend to "
                           "pause, reject, or accelerate through them, independent "
                           "of Gamma's own trendline/level-memory engines.",
        "data_source": "TradingView built-in Volume Profile (Visible Range) study via "
                       "the existing TV MCP (chart_manage_indicator + "
                       "data_get_pine_boxes/lines).",
        "cost": "$0", "instrument_fit": "both", "testability": "battery-ready",
        "dedupe_key": "volume_shelf_tv_vp",
        "source": "J-2026-07-09",
    },
    {
        "id": "community_pine_sr", "beat": "tv_community_indicators",
        "idea": "Vet and add a published TradingView community support/resistance "
                "or auction-market-theory script as a second, independently-"
                "authored structure lens.",
        "mechanism_1line": "Convergence between an outside author's S/R read and "
                           "Gamma's own level-memory/trendline read is a stronger "
                           "structural signal than either alone.",
        "data_source": "TradingView public Pine Script community library (Scripts "
                       "tab) -- requires manually selecting + adding a specific "
                       "published script before its output is machine-readable.",
        "cost": "$0", "instrument_fit": "both", "testability": "needs-data",
        "dedupe_key": "community_pine_sr",
        "source": "J-2026-07-09",
    },
    {
        "id": "finra_short_volume", "beat": "microstructure_internals",
        "idea": "Ingest FINRA's daily short sale volume files for SPY as a crude "
                "aggressive-short-positioning proxy.",
        "mechanism_1line": "An elevated SPY short-volume ratio the prior session is "
                           "a proxy for aggressive short positioning that can fuel "
                           "a short-covering squeeze on any bullish trigger the next "
                           "0DTE session.",
        "data_source": "FINRA Daily Short Sale Volume Files (cts.finra.org) -- free, "
                       "public, published T+1 per security, no auth; no ingestion "
                       "pipeline exists yet.",
        "cost": "$0", "instrument_fit": "0dte", "testability": "needs-data",
        "dedupe_key": "finra_short_volume",
        "source": "J-2026-07-09",
    },
    {
        "id": "dix_daily", "beat": "options_structure_metrics",
        "idea": "Track a DIX-style dark-pool short-volume ratio (SqueezeMetrics DIX "
                "concept) as a sentiment lens distinct from GEX/options positioning.",
        "mechanism_1line": "DIX measures the fraction of SPY volume happening "
                           "off-exchange (dark pools) at the bid -- historically a "
                           "rising DIX preceded upside continuation.",
        "data_source": "SqueezeMetrics DIX (squeezemetrics.com) or derived from "
                       "FINRA ATS aggregate dark-pool volume -- CURRENT FREE "
                       "AVAILABILITY UNVERIFIED, must confirm before treating as "
                       "battery-ready.",
        "cost": "$0", "instrument_fit": "0dte", "testability": "needs-data",
        "dedupe_key": "dix_daily",
        "source": "J-2026-07-09",
    },
    {
        "id": "pattern_grammar", "beat": "tv_community_indicators",
        "idea": "Adopt a formal pattern-labeling grammar (e.g. the Lo/Mamaysky/Wang "
                "nonparametric kernel-regression method for head-and-shoulders, "
                "double tops, etc.) as a shared vocabulary layered on top of "
                "Gamma's own HH/HL/LH/LL structure engine.",
        "mechanism_1line": "A systematized, citable pattern taxonomy gives structure "
                           "detection a second, methodologically distinct lens "
                           "instead of only the current market_structure.py rules.",
        "data_source": "Lo, Mamaysky & Wang (2000) 'Foundations of Technical "
                       "Analysis', Journal of Finance -- a research-methodology "
                       "idea, not a data feed; needs engineering, not a new vendor.",
        "cost": "$0", "instrument_fit": "both", "testability": "vague",
        "dedupe_key": "pattern_grammar",
        "source": "J-2026-07-09",
    },
    {
        "id": "tick_add_internals", "beat": "microstructure_internals",
        "idea": "Read NYSE TICK ($TICK) and the NYSE advance-decline line (ADD) as "
                "real-time breadth-thrust confirmation/exhaustion signals.",
        "mechanism_1line": "TICK/ADD extremes mark short-term breadth-thrust "
                           "exhaustion or confirmation moments day-traders use to "
                           "time entries/exits independent of SPY's own tape.",
        "data_source": "NYSE TICK and ADD -- typically real-time via a broker/data-"
                       "platform feed (IBKR TWS, ToS, Cboe One); Alpaca does not "
                       "appear to publish these natively.",
        "cost": "paid", "instrument_fit": "both", "testability": "needs-data",
        "dedupe_key": "tick_add_internals",
        "source": "fable-2026-07-09",
    },
    {
        "id": "moc_imbalance_window", "beat": "academic_intraday_anomalies",
        "idea": "Read NYSE Market-on-Close imbalance indications (published from "
                "15:50 ET) as a same-window final-hour drift predictor.",
        "mechanism_1line": "A large one-sided MOC imbalance often front-runs and "
                           "extends the final-hour drift -- directly overlaps "
                           "Gamma's own 15:50-15:55 ET flatten window, a same-"
                           "window read, not a lagging one.",
        "data_source": "NYSE Closing Auction (MOC) Imbalance feed -- the raw "
                       "real-time feed is an exchange data product (typically "
                       "paid); free delayed summaries are sometimes relayed via "
                       "financial news, unverified as a reliable source.",
        "cost": "paid", "instrument_fit": "0dte", "testability": "needs-data",
        "dedupe_key": "moc_imbalance_window",
        "source": "fable-2026-07-09",
    },
    {
        "id": "globex_levels", "beat": "futures_positioning",
        "idea": "Compute the overnight CME Globex session high/low/range for ES/NQ "
                "as pre-cash-open key levels for the MES swing mirror.",
        "mechanism_1line": "The overnight Globex high/low is the futures-trader's "
                           "version of premarket high/low -- a level set BEFORE the "
                           "cash open that the MES swing mirror doesn't currently "
                           "compute or trade against.",
        "data_source": "CME Globex overnight OHLC for ES/NQ, derivable from the SAME "
                       "yfinance ES=F feed futures_mirror_shadow.py already polls -- "
                       "needs a session-boundary rollup, not a new vendor.",
        "cost": "$0", "instrument_fit": "mes", "testability": "needs-data",
        "dedupe_key": "globex_levels",
        "source": "fable-2026-07-09",
    },
    {
        "id": "cot_mes_positioning", "beat": "futures_positioning",
        "idea": "Ingest the weekly CFTC Commitments of Traders report for ES/NQ as a "
                "multi-day positioning-bias context filter for the MES swing mirror.",
        "mechanism_1line": "Extreme net-long/net-short positioning by large "
                           "speculators has historically preceded mean-reverting "
                           "positioning unwinds -- a multi-day CONTEXT filter "
                           "distinct from any of Gamma's intraday price-action "
                           "detectors.",
        "data_source": "CFTC Commitments of Traders report (cftc.gov, free, weekly, "
                       "published Fridays) -- no ingestion pipeline exists yet.",
        "cost": "$0", "instrument_fit": "mes", "testability": "needs-data",
        "dedupe_key": "cot_mes_positioning",
        "source": "fable-2026-07-09",
    },
    {
        "id": "timeofday_seasonality_own_fills", "beat": "academic_intraday_anomalies",
        "idea": "Apply classic time-of-day seasonality analysis (opening range / "
                "lunch lull / power hour literature) to Gamma's OWN fill "
                "timestamps to see if entry hour predicts WR/expectancy.",
        "mechanism_1line": "If entry hour meaningfully predicts WR/expectancy "
                           "independent of setup, Gamma should filter/weight by "
                           "time-of-day -- a lens none of the existing organs "
                           "(autopsy=mechanism tags, chef=strategy variants) "
                           "currently apply.",
        "data_source": "automation/state/fills-ledger.jsonl + journal/trades.csv "
                       "(already on disk, broker-truth, zero new fetch) -- needs "
                       "more accumulated fill volume before the split is "
                       "well-powered.",
        "cost": "$0", "instrument_fit": "both", "testability": "needs-data",
        "dedupe_key": "timeofday_seasonality_own_fills",
        "source": "fable-2026-07-09",
    },
)


def seed_ideas(*, date: str) -> list[dict]:
    """Return SEED_IDEAS as full ledger rows (kind/status/date/ts_et added)."""
    out = []
    for r in SEED_IDEAS:
        out.append({**r, "kind": "idea", "status": "proposed", "date": date,
                    "ts_et": et_now().isoformat()})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Surfacing -- firm-brief snapshot + Discord one-liner
# ─────────────────────────────────────────────────────────────────────────────


def write_last_json(*, date: str, beat: str, scan_ok: bool, n_new_ideas: int,
                    n_total_ideas: int, promoted: Optional[dict], error: Optional[str],
                    path: Path = LAST_JSON) -> None:
    payload = {
        "date": date,
        "beat": beat,
        "scan_ok": scan_ok,
        "n_new_ideas": n_new_ideas,
        "n_total_ideas": n_total_ideas,
        "promoted_idea": promoted.get("dedupe_key") if promoted else None,
        "promoted_file": promoted.get("_chef_inbox_file") if promoted else None,
        "error": error,
        "generated_at": et_now().isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def queue_ping(date: str, beat: str, n_added: int, promoted: Optional[dict],
              scan_ok: bool, outbox_path: Path = OUTBOX) -> None:
    if n_added == 0 and promoted is None and scan_ok:
        return  # quiet night, nothing new -- don't spam (mirrors trade_autopsy's no-trade silence)
    try:
        from trade_today_watcher import _load_user_mention  # noqa: PLC0415
        mention = _load_user_mention()
    except Exception:  # noqa: BLE001
        mention = ""
    promo_s = f"; promoted `{promoted['dedupe_key']}` -> _chef-inbox" if promoted else ""
    lane_s = "" if scan_ok else " (no free lane up tonight)"
    msg = f"{mention}[PROSPECTOR] {date} beat={beat}: {n_added} new idea(s){promo_s}{lane_s}."
    try:
        with outbox_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"content": msg, "source": "prospector",
                                 "queued_at": et_now().isoformat()}) + "\n")
    except OSError as e:
        print(f"[prospector] WARN outbox append failed: {e}", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration -- testable core (run) + thin CLI (main)
# ─────────────────────────────────────────────────────────────────────────────


def run(*, beat: Optional[str] = None, dry_run: bool = False,
       scan_fn: Callable[[str], dict] = scan_beat, date: Optional[str] = None,
       ledger_path: Path = LEDGER_FILE, state_path: Path = STATE_FILE,
       last_json_path: Path = LAST_JSON, inbox_dir: Path = CHEF_INBOX,
       outbox_path: Path = OUTBOX) -> dict:
    """The testable core of one fire. Never raises -- any failure degrades to
    a result dict with an 'error' key; callers (main()) still exit 0.

    Every path is an explicit, overridable parameter (production callers get
    the real repo paths via the defaults; tests pass tmp_path locations) --
    deliberately NOT read from the bare module-level constants at call time,
    since a default-argument value is frozen at function-DEFINITION time and
    would silently ignore a test monkeypatching the module attribute later."""
    date = date or et_now().date().isoformat()
    state = load_state(state_path)
    chosen_beat = beat if beat in BEATS else pick_next_beat(state)

    try:
        scan = scan_fn(chosen_beat)
    except Exception as exc:  # noqa: BLE001 -- fail-open: a scan bug must never break the fire
        scan = {"ok": False, "model": None, "ideas_raw": None,
                "error": f"{type(exc).__name__}: {exc}"}

    new_rows: list[dict] = []
    if scan.get("ok"):
        for raw in (scan.get("ideas_raw") or [])[:MAX_IDEAS_PER_SCAN]:
            row = triage_one(chosen_beat, raw)
            if row:
                row.update({"kind": "idea", "status": "proposed", "date": date,
                            "source": f"swarm:{scan.get('model')}",
                            "ts_et": et_now().isoformat()})
                new_rows.append(row)
    else:
        print(f"[prospector] {date} beat={chosen_beat}: no free lane up "
             f"({scan.get('error')}) -- skip-with-log, ledger still served", file=sys.stderr)

    n_added = 0
    promoted = None
    if not dry_run:
        n_added = append_ledger_rows(new_rows, ledger_path)
        all_rows = load_ledger(ledger_path)
        promoted = promote_top1(all_rows, state, date=date, inbox_dir=inbox_dir)
        if promoted:
            keys = list(state.get("promoted_dedupe_keys", []) or [])
            keys.append(promoted["dedupe_key"])
            state = {**state, "promoted_dedupe_keys": keys,
                     "promoted_total": int(state.get("promoted_total", 0) or 0) + 1}
        state = advance_beat({
            **state, "last_beat": chosen_beat, "last_run_et": et_now().isoformat(),
            "fires_total": int(state.get("fires_total", 0) or 0) + 1,
            "ideas_total": int(state.get("ideas_total", 0) or 0) + n_added,
        })
        save_state(state, state_path)
        n_total = len(load_ledger(ledger_path))
    else:
        n_total = len(load_ledger(ledger_path)) + n_added

    write_last_json(date=date, beat=chosen_beat, scan_ok=bool(scan.get("ok")),
                    n_new_ideas=n_added, n_total_ideas=n_total, promoted=promoted,
                    error=scan.get("error"), path=last_json_path)
    if not dry_run:
        queue_ping(date, chosen_beat, n_added, promoted, bool(scan.get("ok")), outbox_path)

    return {"date": date, "beat": chosen_beat, "scan_ok": bool(scan.get("ok")),
           "n_added": n_added, "n_total": n_total, "promoted": promoted,
           "error": scan.get("error")}


def cmd_seed(*, date: Optional[str] = None, ledger_path: Path = LEDGER_FILE,
            state_path: Path = STATE_FILE, last_json_path: Path = LAST_JSON,
            inbox_dir: Path = CHEF_INBOX) -> dict:
    """One-time seed: append SEED_IDEAS (idempotent) + promote the first
    eligible battery-ready idea (gex_flip_from_banked_cboe, by construction --
    see SEED_IDEAS ordering comment). Does NOT advance beat rotation and does
    NOT call the swarm. Safe to re-run (idempotent append + idempotent
    promote). Paths are explicit/overridable -- see run() docstring."""
    date = date or et_now().date().isoformat()
    state = load_state(state_path)
    rows = seed_ideas(date=date)
    n_added = append_ledger_rows(rows, ledger_path)
    all_rows = load_ledger(ledger_path)
    promoted = promote_top1(all_rows, state, date=date, inbox_dir=inbox_dir)
    if promoted:
        keys = list(state.get("promoted_dedupe_keys", []) or [])
        keys.append(promoted["dedupe_key"])
        state = {**state, "promoted_dedupe_keys": keys,
                "promoted_total": int(state.get("promoted_total", 0) or 0) + 1}
    save_state(state, state_path)
    write_last_json(date=date, beat="seed", scan_ok=True, n_new_ideas=n_added,
                    n_total_ideas=len(load_ledger(ledger_path)), promoted=promoted,
                    error=None, path=last_json_path)
    return {"date": date, "n_added": n_added, "n_total": len(load_ledger(ledger_path)),
           "promoted": promoted}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--beat", default=None, choices=list(BEATS),
                    help="Force a specific beat (default: next in rotation)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Scan + triage but do not write ledger/inbox/state")
    ap.add_argument("--seed", action="store_true",
                    help="One-time: append SEED_IDEAS + promote the first eligible idea")
    args = ap.parse_args()

    try:
        if args.seed:
            result = cmd_seed()
            print(f"[prospector] SEED: {result['n_added']} new idea(s), "
                 f"{result['n_total']} total in ledger, promoted="
                 f"{result['promoted']['dedupe_key'] if result['promoted'] else None}")
            return 0
        result = run(beat=args.beat, dry_run=args.dry_run)
        print(f"[prospector] {result['date']} beat={result['beat']} "
             f"scan_ok={result['scan_ok']} new_ideas={result['n_added']} "
             f"total={result['n_total']} promoted="
             f"{result['promoted']['dedupe_key'] if result['promoted'] else None}")
        return 0
    except Exception as exc:  # noqa: BLE001 -- notify-only: never propagate a failure
        print(f"[prospector] ERROR (fail-open): {exc}", file=sys.stderr)
        try:
            LAST_JSON.parent.mkdir(parents=True, exist_ok=True)
            LAST_JSON.write_text(json.dumps({
                "error": str(exc)[:300], "generated_at": et_now().isoformat(),
            }), encoding="utf-8")
        except OSError:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
