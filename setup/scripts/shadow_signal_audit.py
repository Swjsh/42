#!/usr/bin/env python
"""shadow_signal_audit.py - standing SHADOW-SIGNAL / ORPHAN detector.

WHY THIS EXISTS (2026-07-31, forensic finding):
On 2026-07-31 J called three entries off the chart. At 10:15 ET the engine's
`wick_reclaim` detector FIRED, was written to the ledger, and was architecturally
incapable of moving score or blockers -- shadow triggers are LOGGED-ONLY by the
2026-07-15 decision. Separately `trendline_engine.py` correctly logged the 10:15:02
trend break and NOTHING consumed it. That is lesson-cluster C7 (silent success)
at ARCHITECTURE scale: the rig SEES more than it can ACT on, and nobody was
counting the gap.

This script counts the gap, every night, and screams when it GROWS.

WHAT IT DOES (mechanical, no LLM, $0):
  1. For every registered signal producer, re-derives the CONSUMER FACTS from the
     working tree: how many non-test, non-worktree callsites/readers exist, and
     whether any of them lie on the live decision path.
  2. Auto-discovers NEW producers in the scanned modules that are not in the
     registry at all -> flagged NEW_UNREGISTERED (this is how a future orphan gets
     caught the night it is born).
  3. Diffs today's facts against the registry's recorded expectation and against
     the previous run -> flags DRIFT (a WIRED signal that lost its last consumer,
     an ORPHAN that silently gained one, a registered producer whose file vanished).
  4. Rewrites the AUTOGEN block of the standing inventory markdown, writes the
     machine state, and on a NEW-orphan/drift TRANSITION appends ONE loud line to
     STATUS.md "## Known broken" (OP-25: silent failure is the only true failure).

CLASSIFICATIONS
  WIRED             - output reaches a live entry/exit decision.
  SHADOW_BY_DESIGN  - deliberately logged-only, with a DATED decision on record.
                      Requires `provenance` to be non-empty; a shadow signal with
                      no dated decision is not shadow, it is an orphan wearing a
                      lab coat (J: unvalidated invented gates get DELETED, not tuned).
  RESEARCH_ONLY     - consumed by backtest/eval tooling only; never claimed live.
  ORPHANED          - nothing reads it and no decision says it should be shadow.
  STALE             - writes a state file whose consumers stopped reading / whose
                      producer stopped writing.

L249 DISCIPLINE: this script NEVER trusts a docstring. Every consumer claim in the
output is a grep over the working tree, re-run at audit time.

FAIL-OPEN by construction: always exits 0. This is an instrument, never a gate --
it must never block J's session or a scheduled fire (OP-25 guards fail open).

Manual run (foreground, prints the table):
    python setup/scripts/shadow_signal_audit.py --print
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Copied verbatim from setup/guard_runner_slow.py (the proven layer-3 pattern).
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "shadow-signal-audit.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "shadow-signal-audit.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import ast
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "automation" / "state"
OUT_JSON = STATE / "shadow-signal-audit.json"
INVENTORY_MD = ROOT / "analysis" / "deep-research" / "SHADOW-SIGNAL-INVENTORY-2026-07-31.md"
STATUS_MD = ROOT / "automation" / "overnight" / "STATUS.md"

AUTOGEN_BEGIN = "<!-- BEGIN AUTOGEN: shadow_signal_audit.py -- do not hand-edit below -->"
AUTOGEN_END = "<!-- END AUTOGEN -->"

# Directories never scanned as consumers: parallel worktrees (other sessions'
# checkouts -- counting them would fake consumers), vendored deps, build output.
EXCLUDE_DIR_PARTS = (
    ".claude/worktrees", ".claude\\worktrees",
    ".venv", "site-packages", "node_modules", "__pycache__",
    ".git/", ".git\\", "_archive",
)

# A callsite in any of these is a TEST or a DOC, not a live consumer.
TEST_PAT = re.compile(r"(^|[/\\])(tests?|_lesson-inbox)[/\\]|(^|[/\\])test_[^/\\]*\.py$|_test\.py$|smoke[_-]?test", re.I)

# The live decision path: heartbeat_core -> engine_cli -> gates/score -> filters.
# A consumer is "live" only if its path is one of these. Derived by import-trace
# 2026-07-31 (heartbeat_core imports NO watcher; engine_cli imports only
# lib.engine.gates, lib.engine.score, lib.filters, lib.ribbon).
LIVE_PATH_FILES = (
    "setup/scripts/heartbeat_core.py",
    "backtest/lib/engine/engine_cli.py",
    "backtest/lib/engine/gates.py",
    "backtest/lib/engine/score.py",
    "backtest/lib/filters.py",
    "backtest/lib/risk_gate.py",
    "backtest/lib/exit_manager_walk.py",
    "automation/state/fleet/fleet_live.py",
    "automation/state/fleet/entry_manager.py",
    "automation/state/fleet/exit_manager.py",
    "automation/state/fleet/build_shared_signal.py",
    "setup/scripts/j_intent_executor.py",
)

# Modules swept for auto-discovery of NEW producers.
SCAN_MODULES = (
    "backtest/lib/filters.py",
    "backtest/autoresearch/trendline_engine.py",
    "crypto/lib/chart_patterns.py",
    "crypto/lib/market_structure.py",
    "crypto/lib/confluence.py",
    "backtest/lib/structure_shift.py",
    "backtest/lib/level_strength.py",
    "setup/scripts/refresh_levels_intraday.py",
    "setup/scripts/confluence_producer.py",
    "setup/scripts/context_bundle_producer.py",
)
PRODUCER_DEF_PAT = re.compile(r"^(detect|scan|find|compute|classify|analyze|evaluate|score)_\w+$")

# Files that read a state file's FRESHNESS/existence, never its content as a signal.
# These must never be counted as consumers -- otherwise a completely dead shadow file
# looks "consumed" purely because a health monitor watches its mtime.
MONITOR_ONLY_FILES = (
    "setup/scripts/engine_health.py",
    "setup/scripts/state_freshness_selfheal.py",
    "setup/scripts/recovery_splice_2026_07_14.py",
)

# ---------------------------------------------------------------------------
# REGISTRY -- curated. `expected` is the classification a human/agent ratified,
# with dated `provenance`. The script's job is to prove the tree still matches.
# ---------------------------------------------------------------------------
REGISTRY: list[dict] = [
    # --- bull shadow trigger mirrors: the 10:15 archetype ---
    dict(id="wick_reclaim", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_wick_reclaim_bullish", expected="SHADOW_BY_DESIGN",
         provenance="2026-07-15 DIRECTIONAL-GATE-DEEP-RESEARCH §4; quarantined out of "
                    "triggers/blockers/bull_score; guard test_bull_trendline_wick_reclaim_shadow_only.py",
         detects="bullish wick rejection reclaiming a tracked level",
         goes_to="BullishSetupResult.shadow_triggers_fired -> engine_cli base dict -> core-decisions.jsonl (LOGGED ONLY)"),
    dict(id="trendline_reclaim", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_trendline_reclaim_bullish", expected="SHADOW_BY_DESIGN",
         provenance="2026-07-15 DIRECTIONAL-GATE-DEEP-RESEARCH §4 (bull mirror of bear "
                    "trendline_rejection); guard test_bull_trendline_wick_reclaim_shadow_only.py",
         detects="close reclaiming a fitted descending trendline",
         goes_to="shadow_triggers_fired -> core-decisions.jsonl (LOGGED ONLY)"),
    dict(id="pullback_hold", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_pullback_hold_bullish", expected="SHADOW_BY_DESIGN",
         provenance="2026-07-15 shadow-only precedent, added alongside the other two bull "
                    "mirrors; guard test_pullback_hold_shadow_only.py",
         detects="pullback into a level zone that holds N bars",
         goes_to="shadow_triggers_fired -> core-decisions.jsonl (LOGGED ONLY)"),
    # --- the true orphan ---
    dict(id="candlestick_pattern_bullish", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_candlestick_pattern_bullish", expected="ORPHANED",
         provenance="",
         detects="bullish candlestick pattern (hammer / bullish engulfing / bullish marubozu)",
         goes_to="NOWHERE -- zero references in the entire tree incl. tests"),
    # --- wired bear/bull counterparts, for contrast + drift detection ---
    dict(id="candlestick_pattern_bearish", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_candlestick_pattern_bearish", expected="WIRED",
         provenance="live bear scoring path (filters.py evaluate_bearish_setup)",
         detects="bearish candlestick pattern", goes_to="evaluate_bearish_setup -> bear_score"),
    dict(id="level_reclaim", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_level_reclaim", expected="WIRED", provenance="live bull trigger",
         detects="closed bar reclaiming a tracked level", goes_to="triggers_fired -> bull_score/routing"),
    dict(id="level_rejection", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_level_rejection", expected="WIRED", provenance="live bear trigger",
         detects="rejection at a tracked level", goes_to="triggers_fired -> bear_score/routing"),
    dict(id="confluence", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_confluence", expected="WIRED", provenance="live trigger both sides",
         detects="multiple levels stacked near price", goes_to="triggers_fired"),
    dict(id="ribbon_flip_bullish", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_ribbon_flip_bullish", expected="WIRED", provenance="live bull path",
         detects="EMA ribbon restack to BULL", goes_to="ribbon_just_flipped_bullish -> scoring"),
    dict(id="sequence_reclaim", kind="detector", file="backtest/lib/filters.py",
         symbol="detect_sequence_reclaim", expected="WIRED", provenance="live bull path (level_state)",
         detects="break-then-reclaim sequence on a level", goes_to="evaluate_bullish_setup"),
    dict(id="fvg", kind="detector", file="backtest/lib/filters.py", symbol="detect_fvg",
         expected="RESEARCH_ONLY", provenance="consumed only by lib/watchers/erl_irl_watcher.py (research fleet)",
         detects="fair value gap", goes_to="erl_irl_watcher (backtest/eval only, not on the live path)"),
    # --- shadow STATE FILES ---
    dict(id="trendlines_live", kind="state_file", file="backtest/autoresearch/trendline_engine.py",
         symbol="automation/state/trendlines-live.json", expected="SHADOW_BY_DESIGN",
         provenance="2026-07-08 V3 engine-vision ship: 'engine does NOT trade off these yet, "
                    "entry-wire A/B-gated NEEDS-REVIEW' (setup/install-trendlines.ps1 description)",
         detects="respected multi-day SPY trendlines (wick + body families, RTH-only)",
         goes_to="confluence_producer.py + engine_health freshness only -- NO decision consumer"),
    dict(id="confluence_zones", kind="state_file", file="setup/scripts/confluence_producer.py",
         symbol="automation/state/confluence-zones.json", expected="RESEARCH_ONLY",
         provenance="",
         detects="scored confluence zones (>=2 sources within +/-0.85)",
         goes_to="NOTHING outside its own producer -- confirmed zero consumers "
                 "TRENDLINE-SUBSYSTEM-AUDIT-2026-07-14 and re-confirmed 2026-07-31"),
    dict(id="context_bundle", kind="state_file", file="setup/scripts/context_bundle_producer.py",
         symbol="automation/state/context-bundle.json", expected="SHADOW_BY_DESIGN",
         provenance="2026-07-14 context-enrichment plan Phase 0; heartbeat_core._read_context_bundle "
                    "docstring + guard test_context_bundle_tag_no_behavior_change.py proves no behavior change",
         detects="multi-timeframe trend alignment (daily/hourly/m15) + events + prior-day context",
         goes_to="heartbeat_core rec dict -> core-decisions.jsonl (LOGGED ONLY)"),
    dict(id="trendline_log", kind="state_file", file="backtest/autoresearch/trendline_engine.py",
         symbol="analysis/trendlines/trendline-log.jsonl", expected="SHADOW_BY_DESIGN",
         provenance="2026-07-08 V3 ship (append-only record J asked for)",
         detects="every detected trendline instance, per fire",
         # VERIFIED 2026-07-31 by direct grep: ZERO programmatic readers. The earlier
         # assumption that trendline_outcomes.py/break_replay read it was FALSE -- those
         # read break-outcomes.jsonl / break-dataset.jsonl, different files (L249).
         goes_to="NOTHING reads it in code -- producer + a recovery utility + docs only"),
]


# ---------------------------------------------------------------------------
# mechanics
# ---------------------------------------------------------------------------
def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def _excluded(rel: str) -> bool:
    return any(part in rel for part in EXCLUDE_DIR_PARTS)


def iter_source_files() -> list[Path]:
    """Every scannable source file in the tree, worktrees and vendored deps removed."""
    self_rel = _rel(Path(__file__).resolve())
    out: list[Path] = []
    for ext in ("*.py", "*.ps1", "*.ts", "*.tsx", "*.js"):
        for p in ROOT.rglob(ext):
            rel = _rel(p)
            if _excluded(rel):
                continue
            # THIS script names every registered symbol in its REGISTRY. Counting
            # itself would credit every orphan with one phantom consumer -- the
            # exact self-fulfilling artifact this audit exists to catch.
            if rel == self_rel:
                continue
            out.append(p)
    return out


DEF_LINE_PAT = "def {sym}("


def scan_references(files: list[Path], needle: str, own_file: str, skip_own: bool = False) -> dict:
    """Grep the tree for `needle` and split the hits into decision-relevant buckets.

    IMPORTANT MECHANIC (fixed 2026-07-31): for a DETECTOR, a call from the producer's
    OWN file is a REAL callsite, not noise. `filters.py` defines AND calls
    `detect_wick_reclaim_bullish`, and filters.py is on the live path -- discarding
    same-file hits would report every live detector as having zero consumers.

    For a STATE FILE the opposite holds: the producer script naming its own output path
    is a WRITE, not a read, so `skip_own` drops it. This is what the 2026-07-14 trendline
    audit meant by "zero consumers outside its own producer script".
    """
    live, research, tests, monitors = [], [], [], []
    is_path = "/" in needle
    pat = re.compile(re.escape(needle)) if is_path else re.compile(r"\b" + re.escape(needle) + r"\b")
    def_marker = DEF_LINE_PAT.format(sym=needle)
    for p in files:
        rel = _rel(p)
        if skip_own and rel == own_file:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not pat.search(text):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if not pat.search(line):
                continue
            if def_marker in line:          # the definition is not a consumer
                continue
            if not is_path and line.lstrip().startswith(("#", '"', "*")):
                continue                    # comment/docstring mention is not a callsite
            hit = f"{rel}:{i}"
            if TEST_PAT.search(rel):
                tests.append(hit)
            elif rel in MONITOR_ONLY_FILES:
                # A freshness/health monitor reads the file's MTIME, not its content
                # as a signal. Counting it as a consumer would let a dead shadow file
                # masquerade as wired -- the exact false-negative this audit exists for.
                monitors.append(hit)
            elif rel in LIVE_PATH_FILES:
                live.append(hit)
            else:
                research.append(hit)
            break                            # one hit per file is the fact we need
    return dict(live=sorted(live), research=sorted(research), tests=sorted(tests),
                monitors=sorted(monitors))


def guard_exists(provenance: str) -> bool | None:
    """Does the guard test named in `provenance` actually exist on disk?

    This is the ONLY mechanically checkable proof that a SHADOW_BY_DESIGN claim is
    real. grep cannot see that a detector's RESULT was assigned to a logged-only
    field -- that is data flow, not call structure. A named, existing guard test
    that pins 'no behavior change' is the substitute. No guard named -> unproven.
    L249: never accept the docstring's word for it.
    """
    m = re.search(r"(test_[A-Za-z0-9_]+\.py)", provenance or "")
    if not m:
        return None
    name = m.group(1)
    return any((ROOT / "backtest" / "tests" / name).exists()
               for _ in (0,)) or bool(list(ROOT.rglob(name)))


def classify(entry: dict, refs: dict) -> tuple[str, str]:
    """Derive the classification the TREE supports, ignoring what the registry claims.

    Returns (classification, evidence_note).
    """
    n_live, n_res = len(refs["live"]), len(refs["research"])
    has_decision = bool(entry.get("provenance"))
    claims_shadow = entry.get("expected") == "SHADOW_BY_DESIGN"

    if n_live == 0 and n_res == 0:
        # Zero programmatic readers. A DATED decision to keep it as a record is the
        # only thing separating "deliberate append-only log" from "dead weight".
        if claims_shadow and has_decision:
            return "SHADOW_BY_DESIGN", ("ZERO programmatic readers -- ad-hoc/human research "
                                        "only, but a dated decision keeps it on purpose")
        return "ORPHANED", "zero non-test callsites anywhere in the tree"

    if n_live == 0:
        # No live-path consumer. If a DATED decision says "logged-only for now",
        # that is deliberate shadow. Without one it is just research tooling --
        # or, if it claims shadow with no decision, an orphan in a lab coat.
        if claims_shadow and has_decision:
            return "SHADOW_BY_DESIGN", f"dated decision on record; {n_res} research consumer(s), 0 live"
        if claims_shadow:
            return "ORPHANED", "claims shadow but no dated decision on record"
        return "RESEARCH_ONLY", f"{n_res} callsite(s), none on the live decision path"

    # Reaches a live-path FILE. Whether it reaches the live DECISION is DATA FLOW,
    # which grep cannot resolve -- so demand a dated decision AND an existing guard test.
    if claims_shadow:
        g = guard_exists(entry.get("provenance", ""))
        if g is True:
            return "SHADOW_BY_DESIGN", "quarantine pinned by an existing named guard test"
        if g is None:
            return "UNPROVEN_SHADOW", "claimed shadow but provenance names no guard test"
        return "UNPROVEN_SHADOW", "named guard test does not exist on disk"
    return "WIRED", f"{n_live} live-path callsite(s)"


def state_file_age_days(sym: str) -> float | None:
    p = ROOT / sym
    if not p.exists():
        return None
    age = dt.datetime.now().timestamp() - p.stat().st_mtime
    return round(age / 86400.0, 2)


def discover_unregistered(files_by_rel: dict[str, Path], registered: set[str]) -> list[dict]:
    """Parse SCAN_MODULES with ast; report producer-shaped defs not in the registry."""
    found: list[dict] = []
    for rel in SCAN_MODULES:
        p = ROOT / rel
        if not p.exists():
            found.append(dict(module=rel, symbol="<MODULE MISSING>", line=0))
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:  # top-level defs only
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            if not PRODUCER_DEF_PAT.match(node.name):
                continue
            if node.name in registered:
                continue
            found.append(dict(module=rel, symbol=node.name, line=node.lineno))
    return found


def build_report() -> dict:
    files = iter_source_files()
    files_by_rel = {_rel(p): p for p in files}
    rows = []
    for entry in REGISTRY:
        refs = scan_references(files, entry["symbol"], entry["file"],
                               skip_own=(entry["kind"] == "state_file"))
        actual, evidence = classify(entry, refs)
        row = dict(evidence=evidence, n_monitors=len(refs["monitors"]),
            id=entry["id"], kind=entry["kind"], file=entry["file"], symbol=entry["symbol"],
            detects=entry["detects"], goes_to=entry["goes_to"],
            expected=entry["expected"], actual=actual,
            provenance=entry.get("provenance", ""),
            n_live=len(refs["live"]), n_research=len(refs["research"]), n_tests=len(refs["tests"]),
            live_sites=refs["live"][:6], research_sites=refs["research"][:6],
            drift=(actual != entry["expected"]),
        )
        if entry["kind"] == "state_file":
            row["age_days"] = state_file_age_days(entry["symbol"])
        # A SHADOW_BY_DESIGN claim with no dated decision is an orphan in a lab coat.
        if entry["expected"] == "SHADOW_BY_DESIGN" and not entry.get("provenance"):
            row["actual"] = "ORPHANED"
            row["drift"] = True
            row["evidence"] = "shadow claimed with NO dated decision -> treated as ORPHANED"
        rows.append(row)

    registered_syms = {e["symbol"] for e in REGISTRY}
    unregistered = discover_unregistered(files_by_rel, registered_syms)

    orphans = [r for r in rows if r["actual"] in ("ORPHANED", "UNPROVEN_SHADOW")]
    drifted = [r for r in rows if r["drift"]]
    return dict(
        generated_at_et=dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        n_registered=len(rows), n_orphaned=len(orphans), n_drift=len(drifted),
        n_unregistered=len(unregistered),
        orphan_ids=[r["id"] for r in orphans], drift_ids=[r["id"] for r in drifted],
        rows=rows, unregistered=unregistered,
    )


# ---------------------------------------------------------------------------
# rendering + fail-loud
# ---------------------------------------------------------------------------
def render_autogen(rep: dict) -> str:
    L = [AUTOGEN_BEGIN, "",
         f"_Regenerated by `setup/scripts/shadow_signal_audit.py` at {rep['generated_at_et']} ET._",
         "",
         f"**{rep['n_registered']} registered producers | {rep['n_orphaned']} ORPHANED | "
         f"{rep['n_drift']} DRIFT vs registry | {rep['n_unregistered']} unregistered producer-shaped defs**",
         "",
         "| id | kind | classification | live | rsrch | test | detects | output reaches | evidence |",
         "|---|---|---|---|---|---|---|---|---|"]
    order = {"ORPHANED": 0, "UNPROVEN_SHADOW": 1, "SHADOW_BY_DESIGN": 2, "RESEARCH_ONLY": 3, "WIRED": 4}
    for r in sorted(rep["rows"], key=lambda x: (order.get(x["actual"], 9), x["id"])):
        flag = " (DRIFT)" if r["drift"] else ""
        age = f" (age {r['age_days']}d)" if r.get("age_days") is not None else ""
        L.append(f"| `{r['id']}` | {r['kind']} | **{r['actual']}**{flag} | {r['n_live']} | "
                 f"{r['n_research']} | {r['n_tests']} | {r['detects']} | {r['goes_to']}{age} | {r['evidence']} |")
    L += ["", "### Unregistered producer-shaped defs (candidate new orphans)", ""]
    if rep["unregistered"]:
        L.append("| module | symbol | line |")
        L.append("|---|---|---|")
        for u in rep["unregistered"]:
            L.append(f"| `{u['module']}` | `{u['symbol']}` | {u['line']} |")
    else:
        L.append("_none — every producer-shaped def in the scanned modules is registered._")
    L += ["", AUTOGEN_END]
    return "\n".join(L)


def splice_inventory(rep: dict) -> bool:
    """Rewrite only the AUTOGEN block, preserving the hand-written analysis above it."""
    if not INVENTORY_MD.exists():
        return False
    text = INVENTORY_MD.read_text(encoding="utf-8")
    if AUTOGEN_BEGIN not in text or AUTOGEN_END not in text:
        return False
    pre = text.split(AUTOGEN_BEGIN)[0]
    post = text.split(AUTOGEN_END)[1]
    INVENTORY_MD.write_text(pre + render_autogen(rep) + post, encoding="utf-8")
    return True


def fail_loud_on_transition(rep: dict) -> str | None:
    """Append ONE line to STATUS.md '## Known broken' when the orphan/drift set GROWS.

    A persisting condition is not re-spammed (same sentinel discipline as
    guard_runner_slow.py); only a transition into a WORSE state speaks.
    """
    if not OUT_JSON.exists():
        # FIRST RUN = baseline seeding. Every existing orphan/unregistered def would fire
        # at once and bury the signal in 29 lines of noise. A monitor that shouts on day
        # one teaches the reader to ignore it (C18 status-format discipline). Record the
        # baseline silently; from here on, only what CHANGES speaks.
        return None
    try:
        prev = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        prev = {}
    prev_bad = set(prev.get("orphan_ids", [])) | set(prev.get("drift_ids", []))
    now_bad = set(rep["orphan_ids"]) | set(rep["drift_ids"])
    new_bad = sorted(now_bad - prev_bad)
    prev_unreg = {(u["module"], u["symbol"]) for u in prev.get("unregistered", [])}
    now_unreg = {(u["module"], u["symbol"]) for u in rep["unregistered"]}
    new_unreg = sorted(now_unreg - prev_unreg)
    if not new_bad and not new_unreg:
        return None
    bits = []
    if new_bad:
        bits.append("newly ORPHANED/DRIFTED: " + ", ".join(new_bad))
    if new_unreg:
        bits.append("new unregistered producer(s): " + ", ".join(f"{m}::{s}" for m, s in new_unreg))
    line = (f"- [{rep['generated_at_et']} ET] shadow_signal_audit: " + "; ".join(bits)
            + ". A detector produces output no decision path consumes (C7 at architecture scale)."
            + " See analysis/deep-research/SHADOW-SIGNAL-INVENTORY-2026-07-31.md.\n")
    try:
        text = STATUS_MD.read_text(encoding="utf-8") if STATUS_MD.exists() else ""
        if "## Known broken" in text:
            head, tail = text.split("## Known broken", 1)
            nl = tail.find("\n")
            text = head + "## Known broken" + tail[:nl + 1] + line + tail[nl + 1:]
        else:
            text += "\n## Known broken\n" + line
        STATUS_MD.write_text(text, encoding="utf-8")
    except OSError:
        return line
    return line


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="do_print", action="store_true", help="print the table")
    ap.add_argument("--no-write", action="store_true", help="compute only, write nothing")
    args = ap.parse_args()

    rep = build_report()
    if args.do_print:
        print(render_autogen(rep))
    if not args.no_write:
        spoke = fail_loud_on_transition(rep)   # read prev state BEFORE overwriting
        rep["status_line"] = spoke
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        spliced = splice_inventory(rep)
        if args.do_print:
            print(f"\n[wrote] {_rel(OUT_JSON)} | inventory spliced: {spliced} | STATUS line: {bool(spoke)}")
    return 0  # ALWAYS fail-open


if __name__ == "__main__":
    raise SystemExit(main())
