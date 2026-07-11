"""twin_review.py -- the nightly FREE-LLM review of the CRYPTO TWIN's day.

Runs once per UTC day (triggered internally by twin_sentinel.run_sentinel() after
23:30 UTC -- see that module's docstring; ONE scheduled task does both jobs, this
file is a subroutine, not a second scheduled entrypoint). Also runnable standalone
for manual verification: `python twin_review.py`.

$0 HARD COST RULE (J directive, this build): reads the day's incidents/coverage/
sentinel-history/decisions sample and asks ONE FREE-TIER model for a structured
assessment (anomalies, incident triage mechanism-bug/market-noise/infra, anything a
human should look at) in a SINGLE call -- one $0 call produces both artifacts below.

OUTPUTS (same directory, one call produces both):
  * automation/state/crypto-twin/reviews/YYYY-MM-DD.md   -- human-readable report.
  * automation/state/crypto-twin/reviews/YYYY-MM-DD.json -- structured sidecar for the
    cross-component free-model AUDIT HARNESS (a separate parallel build, coordinator
    request 2026-07-11) to grade mechanically without re-parsing prose:
        {"date", "model_used", "assessment": HEALTHY|DEGRADED|CONCERNING,
         "confidence": 0.0-1.0, "flags_raised": [...], "summary": "<=15 lines"}

MODEL-CLIENT CHOICE -- a deliberate, disclosed DEVIATION from the literal "reuse the
kitchen/swarm free-model client + roster fallback exactly as kitchen_seeder does":
  * USES: swarm_client.call_role_json() -- the genuinely $0 path (schema-validated
    JSON extraction + ONE repair-retry, built for exactly this "get structured output
    from a free small model" problem). Its own module docstring states the design
    contract plainly: "Routes ... across MULTIPLE independent free providers plus a
    LOCAL Ollama floor ... Never goes dark -- every role's lane list ends in the
    local Ollama floor (no quota, no ToS, no rate limit)." This module's "critic"
    role lanes: openrouter nemotron-3-super-120b (:free) -> cerebras zai-glm-4.7
    (free dev tier) -> local ollama qwen3:14b (no cost, no cap, ever).
  * DOES NOT extend to kitchen_daemon.MODEL_LADDER / run_minimax.call_minimax the way
    kitchen_seeder.py's OUTER fallback does. VERIFIED before deciding (not assumed,
    per OP-33/debugging.md "read the evidence"): run_minimax.py's DEFAULT_MODEL is
    "minimax/minimax-m2.5", which its own PRICING dict prices at real $/token and
    which its own comment records as "DEAD (2026-07-01, de-tagged to paid ...)" --
    i.e. that ladder is a PAID OpenRouter path (capped at DAILY_CAP_USD=$5/day,
    kitchen's own PAID_TIER_DAILY_CAP_USD=$3/day), not a free one. Wiring a paid
    fallback into a NEW unattended-forever nightly task would silently violate this
    build's own "$0 baseline ... FREE LLMs only" instruction and CLAUDE.md
    OP-3/section-5 ("no net-new paid vendors without explicit OK"). "the kitchen/
    swarm free-model client + roster fallback" is read here as swarm_client.py's OWN
    internal multi-lane roster cascade (which IS free end to end) -- not
    kitchen_seeder's separate legacy paid safety net.
  * CONSEQUENCE: "all free lanes down" for this module can now only mean the roster
    file itself is missing/corrupt OR the local ollama server process isn't running
    AND every remote free lane also failed -- exactly the case the task spec already
    asks this module to handle explicitly (NO-LLM fallback below), so no coverage
    gap results from skipping the paid ladder.

NO-LLM FALLBACK: if every free lane fails, OR the model's JSON doesn't validate
(missing keys / assessment not one of the 3 allowed values / confidence out of
range / empty summary), writes the deterministic stats-only report+sidecar anyway,
clearly labeled MODE "NO-LLM" with a mechanically-derived (not model-judged)
assessment/confidence/flags -- never skips silently (OP-25/C7).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402
import twin_sentinel as ts  # noqa: E402 -- OUR OWN sibling file (not B1/B2-owned); reuse its
                            # fail-open readers/paths rather than a third copy of the same code

STATE = REPO / "automation" / "state"
REVIEWS_DIR = ts.TWIN_DIR / "reviews"

REVIEW_ROLE = "critic"
REVIEW_MAX_TOKENS = 900
REVIEW_TIMEOUT_S = 90
MAX_DECISIONS_SAMPLE = 25
MAX_INCIDENTS_SAMPLE = 15
MAX_TICK_ERROR_SAMPLE = 10
MAX_SOAK_ROWS_SAMPLE = 24  # one UTC day's worth of hourly rollups

VALID_ASSESSMENTS = ("HEALTHY", "DEGRADED", "CONCERNING")

REVIEW_JSON_SCHEMA = {
    "type": "object",
    "required": ["assessment", "confidence", "flags_raised", "summary"],
    "properties": {
        "assessment": {"type": "string"},
        "confidence": {"type": "number"},
        "flags_raised": {"type": "array"},
        "summary": {"type": "string"},
    },
}

REVIEW_SYSTEM_PROMPT = """You are the nightly reviewer for Project Gamma's CRYPTO TWIN -- a
24/7 mechanism-validation training ground (never an edge/P&L claim; see
markdown/planning/TWIN-PROGRAM.md). You get ONE compact daily digest of decisions,
incidents, and coverage.

OUTPUT FORMAT (strict): respond with a single JSON object with EXACTLY these fields:
  {
    "assessment": "HEALTHY" | "DEGRADED" | "CONCERNING",
    "confidence": <number 0.0-1.0, your confidence in this assessment>,
    "flags_raised": ["<short flag string>", ...],   // empty array if nothing notable
    "summary": "<=15 lines, plain text. Cover: (1) anomalies noticed (unusual action
                distribution, repeated errors, stuck states), (2) incident triage --
                classify each notable incident/error as MECHANISM-BUG (a code defect)
                / MARKET-NOISE (expected crypto volatility/spread) / INFRA (network,
                broker, scheduling, environment), (3) anything a human (J) should
                specifically look at tomorrow. If nothing notable happened, say so
                plainly in 1-2 lines -- do not pad.>
  }

Ground rules:
  - The twin's P&L is NEVER evidence of a trading edge -- do not comment on profitability.
  - Be concrete in `summary`: cite counts/action names/error strings from the digest,
    not vague generalities.
  - `assessment` reflects MECHANISM health (is the code path running cleanly), never
    profitability.
"""


# ══════════════════════════════════════════════════════════════════════════════════════
# Context gathering
# ══════════════════════════════════════════════════════════════════════════════════════
def gather_day_context(now_utc: datetime) -> dict:
    today_utc_str = now_utc.strftime("%Y-%m-%d")

    decisions_rows = ts._read_jsonl(ts.DECISIONS_PATH)
    todays_decisions = [r for r in decisions_rows if r.get("session_date_utc") == today_utc_str]

    action_dist: dict[str, int] = {}
    for r in todays_decisions:
        a = str(r.get("action", "UNKNOWN"))
        action_dist[a] = action_dist.get(a, 0) + 1
    errors = [r for r in todays_decisions if r.get("action") == "TICK_ERROR"]

    incidents_rows = ts._read_jsonl(ts.INCIDENTS_PATH)
    incidents_today_n, incidents_undated = ts.count_incidents_today(incidents_rows, today_utc_str)

    coverage_raw = ts._read_json(ts.COVERAGE_PATH)
    coverage = ts.parse_path_coverage(coverage_raw, today_utc_str)

    soak_rows = ts._read_jsonl(ts.SOAK_LOG_PATH)
    todays_soak = [r for r in soak_rows if str(r.get("period_start_et", "")).startswith(
        (now_utc.strftime("%Y-%m-%d"),)  # best-effort; soak rows are ET-keyed, so this is a
                                          # loose recency filter, not an exact UTC-day match
    )][-MAX_SOAK_ROWS_SAMPLE:]

    sentinel_snapshot = ts._read_json(ts.SENTINEL_PATH)

    return {
        "today_utc": today_utc_str,
        "n_ticks_today": len(todays_decisions),
        "action_distribution": action_dist,
        "n_tick_errors": len(errors),
        "tick_error_sample": errors[-MAX_TICK_ERROR_SAMPLE:],
        "decisions_sample": todays_decisions[-MAX_DECISIONS_SAMPLE:],
        "incidents_today_n": incidents_today_n,
        "incidents_undated": incidents_undated,
        "incidents_sample": incidents_rows[-MAX_INCIDENTS_SAMPLE:],
        "coverage": coverage,
        "soak_rows_sample": todays_soak,
        "sentinel_snapshot": sentinel_snapshot,
    }


def _build_review_prompt(ctx: dict) -> str:
    lines = [
        f"# Crypto Twin daily digest -- {ctx['today_utc']} (UTC)",
        "",
        f"Ticks today: {ctx['n_ticks_today']}",
        f"Action distribution: {json.dumps(ctx['action_distribution'])}",
        f"TICK_ERROR count: {ctx['n_tick_errors']}",
    ]
    if ctx["tick_error_sample"]:
        lines.append("Recent TICK_ERROR rows:")
        for r in ctx["tick_error_sample"]:
            lines.append(f"  - {r.get('ts_utc', '?')}: {str(r.get('reason', ''))[:200]}")

    lines.append(
        f"Incidents today: {ctx['incidents_today_n']} "
        f"(undated/unattributed, excluded from count: {ctx['incidents_undated']})"
    )
    if ctx["incidents_sample"]:
        lines.append("Incident sample (raw -- schema not yet finalized upstream):")
        for r in ctx["incidents_sample"]:
            lines.append(f"  - {json.dumps(r, default=str)[:250]}")

    if ctx["coverage"]:
        c = ctx["coverage"]
        lines.append(f"Path coverage: {c['green']}/{c['total']} branches green")
    else:
        lines.append("Path coverage: not available today")

    if ctx["soak_rows_sample"]:
        lines.append(f"Hourly soak rollups today ({len(ctx['soak_rows_sample'])} rows):")
        for r in ctx["soak_rows_sample"][-8:]:
            lines.append(
                f"  - {r.get('period_start_et', '?')}..{r.get('period_end_et', '?')}: "
                f"n_ticks={r.get('n_ticks')} n_errors={r.get('n_errors')} "
                f"dist={json.dumps(r.get('action_distribution', {}))}"
            )

    if ctx["sentinel_snapshot"]:
        s = ctx["sentinel_snapshot"]
        lines.append(f"Latest sentinel verdict: {s.get('verdict')} reasons={s.get('reasons')}")

    lines.append("")
    lines.append("Decision sample (most recent, oldest->newest, truncated fields):")
    for r in ctx["decisions_sample"]:
        lines.append(
            f"  - {r.get('ts_utc', '?')} action={r.get('action')} verdict={r.get('verdict')} "
            f"reason={str(r.get('reason', ''))[:120]}"
        )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════════
# Model call -- FREE lanes only (see module docstring for why the paid MODEL_LADDER is
# deliberately excluded), structured JSON in ONE call
# ══════════════════════════════════════════════════════════════════════════════════════
def _call_free_model_json(prompt: str) -> "tuple[dict, Optional[dict]]":
    """Returns (envelope, parsed_or_None). Never raises. `envelope["ok"]` reflects
    whether the CALL succeeded; `parsed` additionally reflects whether the response
    validated against REVIEW_JSON_SCHEMA (swarm_client.call_role_json's own repair-
    retry already tried once) -- callers must check BOTH plus the stricter enum/range
    validation in _validate_parsed() below before trusting the model's judgment."""
    try:
        import swarm_client as _swarm
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"swarm_client import failed: {type(exc).__name__}: {exc}"}, None
    try:
        env, parsed = _swarm.call_role_json(
            REVIEW_ROLE, prompt, REVIEW_JSON_SCHEMA, system=REVIEW_SYSTEM_PROMPT,
            max_tokens=REVIEW_MAX_TOKENS, temperature=0.3, timeout=REVIEW_TIMEOUT_S,
            task_id="twin.review",
        )
        return env, parsed
    except Exception as exc:  # noqa: BLE001 -- a lane crash must never propagate
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, None


def _validate_parsed(parsed: Optional[dict]) -> bool:
    """swarm_client's own validate_json only checks top-level type + required keys +
    property TYPES -- it has no enum/range support. This is the stricter check this
    module needs before trusting the model's classification (assessment must be one
    of the 3 allowed values, confidence in [0,1], summary non-empty)."""
    if not isinstance(parsed, dict):
        return False
    if parsed.get("assessment") not in VALID_ASSESSMENTS:
        return False
    conf = parsed.get("confidence")
    if not isinstance(conf, (int, float)) or isinstance(conf, bool):
        return False
    if not (0.0 <= float(conf) <= 1.0):
        return False
    if not isinstance(parsed.get("flags_raised"), list):
        return False
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════════════
# Deterministic NO-LLM classification -- mechanical, never a fabricated model read
# ══════════════════════════════════════════════════════════════════════════════════════
NO_LLM_CONFIDENCE = 0.4  # deliberately LOW -- signals "mechanical stats readout, not
                         # an analytical judgment", never dressed up as a real assessment


def _stats_only_classification(ctx: dict) -> "tuple[str, float, list]":
    flags: list = []
    if ctx["n_tick_errors"] > 0:
        flags.append(f"tick_errors={ctx['n_tick_errors']}")
    if ctx["incidents_today_n"] > 0:
        flags.append(f"incidents={ctx['incidents_today_n']}")
    flags.append("NO-LLM fallback: mechanical stats classification, not a qualitative model read")

    if ctx["incidents_today_n"] >= ts.INCIDENT_SPIKE_RED_COUNT or ctx["n_tick_errors"] >= 5:
        assessment = "CONCERNING"
    elif ctx["n_tick_errors"] > 0 or ctx["incidents_today_n"] > 0:
        assessment = "DEGRADED"
    else:
        assessment = "HEALTHY"
    return assessment, NO_LLM_CONFIDENCE, flags


def _stats_only_summary(ctx: dict) -> str:
    bits = [
        f"{ctx['n_ticks_today']} ticks",
        f"{ctx['n_tick_errors']} tick-errors",
        f"{ctx['incidents_today_n']} incidents",
    ]
    if ctx["coverage"]:
        bits.append(f"coverage {ctx['coverage']['green']}/{ctx['coverage']['total']}")
    return "NO-LLM stats-only: " + ", ".join(bits) + "."


# ══════════════════════════════════════════════════════════════════════════════════════
# Report rendering + writing
# ══════════════════════════════════════════════════════════════════════════════════════
def _render_report_md(ctx: dict, *, mode: str, model_used: Optional[str], assessment: str,
                      confidence: float, flags_raised: list, summary: str,
                      now_et: datetime) -> str:
    lines = [
        f"# Crypto Twin nightly review -- {ctx['today_utc']} (UTC)",
        "",
        f"MODE: {mode}" + (f" (model: {model_used})" if model_used else ""),
        f"ASSESSMENT: {assessment} (confidence {confidence:.2f})",
        f"FLAGS: {', '.join(flags_raised) if flags_raised else '(none)'}",
        f"Generated: {now_et.isoformat()} ET",
        "",
        "## Stats",
        f"- Ticks today (UTC day): {ctx['n_ticks_today']}",
        f"- Action distribution: {json.dumps(ctx['action_distribution'])}",
        f"- TICK_ERROR count: {ctx['n_tick_errors']}",
        f"- Incidents today: {ctx['incidents_today_n']} (undated excluded: {ctx['incidents_undated']})",
        f"- Path coverage: "
        + (f"{ctx['coverage']['green']}/{ctx['coverage']['total']} branches green"
           if ctx["coverage"] else "not available today"),
        "",
        "## Assessment",
        summary.strip() if summary.strip() else "(empty response)",
        "",
    ]
    return "\n".join(lines)


def apply_last_review_note_to_sentinel(note: dict, *, sentinel_path: Path = None) -> None:
    """Read-modify-write ONLY the last_review_note key of twin-sentinel.json. Used by
    the standalone CLI path; the normal scheduled path (run_sentinel() calling
    run_review() as a subroutine, then doing its OWN single write) never calls this --
    avoids a double-writer race between sentinel and review within the same fire."""
    path = sentinel_path or ts.SENTINEL_PATH
    data = ts._read_json(path) or {}
    data["last_review_note"] = note
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════════
def run_review(
    *,
    now_utc: Optional[datetime] = None,
    now_et: Optional[datetime] = None,
    reviews_dir: Path = None,
) -> dict:
    """Runs ONE review cycle end to end. Never raises (every failure mode degrades to
    the NO-LLM stats-only report+sidecar, per the task spec's "never skip silently").
    Writes BOTH YYYY-MM-DD.md (human) and YYYY-MM-DD.json (machine, audit-harness
    sidecar) from the SAME single $0 call. Returns {"ok", "mode", "model",
    "assessment", "confidence", "flags_raised", "summary_line", "report_path",
    "sidecar_path"}."""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_et or et_now()
    reviews_dir = reviews_dir or REVIEWS_DIR

    ctx = gather_day_context(now_utc)
    prompt = _build_review_prompt(ctx)

    try:
        env, parsed = _call_free_model_json(prompt)
    except Exception as exc:  # noqa: BLE001 -- absolute belt-and-suspenders
        env, parsed = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, None

    if env.get("ok") and _validate_parsed(parsed):
        mode = "LLM"
        model_used = env.get("model") or env.get("lane")
        assessment = parsed["assessment"]
        confidence = float(parsed["confidence"])
        flags_raised = list(parsed["flags_raised"])
        summary = parsed["summary"].strip()
    else:
        mode = "NO-LLM"
        model_used = None
        assessment, confidence, flags_raised = _stats_only_classification(ctx)
        # env.get("error") is genuinely None when the CALL succeeded but the content
        # simply didn't validate (e.g. a reasoning model drifting into prose instead of
        # strict JSON -- observed live with the critic role's primary nemotron lane) --
        # showing literal "None" in that case reads as a confusing non-answer, so the
        # two failure modes (call failed vs. call succeeded but invalid) get distinct,
        # honest messages instead of collapsing to the same unclear text.
        if env.get("ok"):
            fail_reason = "model call succeeded but response did not validate against the required JSON schema"
        else:
            fail_reason = env.get("error") or "unknown failure"
        summary = _stats_only_summary(ctx) + f" (LLM unavailable/invalid: {fail_reason})"

    report_md = _render_report_md(
        ctx, mode=mode, model_used=model_used, assessment=assessment, confidence=confidence,
        flags_raised=flags_raised, summary=summary, now_et=now_et,
    )
    report_path = reviews_dir / f"{ctx['today_utc']}.md"
    sidecar_path = reviews_dir / f"{ctx['today_utc']}.json"
    sidecar = {
        "date": ctx["today_utc"],
        "model_used": model_used,
        "assessment": assessment,
        "confidence": confidence,
        "flags_raised": flags_raised,
        "summary": summary,
    }

    ok = True
    try:
        reviews_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_md, encoding="utf-8")
    except OSError as exc:
        ok = False
        summary = f"REPORT WRITE FAILED: {exc}. " + summary
    try:
        reviews_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(json.dumps(sidecar, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        ok = False
        sidecar["_write_error"] = str(exc)

    summary_line = (summary.strip().splitlines() or [""])[0][:280]

    return {
        "ok": ok,
        "mode": mode,
        "model": model_used,
        "assessment": assessment,
        "confidence": confidence,
        "flags_raised": flags_raised,
        "summary_line": summary_line,
        "report_path": str(report_path),
        "sidecar_path": str(sidecar_path),
        "ctx_stats": {
            "n_ticks_today": ctx["n_ticks_today"],
            "n_tick_errors": ctx["n_tick_errors"],
            "incidents_today_n": ctx["incidents_today_n"],
        },
    }


def main(argv: Optional[list] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Nightly FREE-LLM review of the crypto twin's day")
    parser.add_argument("--no-sentinel-write", action="store_true",
                        help="skip applying last_review_note to twin-sentinel.json (dry run)")
    args = parser.parse_args(argv)

    result = run_review()
    if not args.no_sentinel_write:
        today_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        apply_last_review_note_to_sentinel({
            "date_utc": today_utc_str,
            "mode": result.get("mode"),
            "summary": result.get("summary_line", ""),
            "assessment": result.get("assessment"),
            "confidence": result.get("confidence"),
            "report_path": result.get("report_path"),
            "sidecar_path": result.get("sidecar_path"),
        })
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
