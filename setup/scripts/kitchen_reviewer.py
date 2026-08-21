"""Kitchen reviewer -- closes the feedback loop on cook outputs.

Fires every 2 hours. Reads recent cook outputs in strategy/candidates/, asks
Nemotron to triage each, then:
  * Promotes high-quality candidates to the leaderboard (writes a review_notes
    section to strategy/candidates/_review-log.jsonl)
  * Queues follow-up cook tasks (e.g., "walk-forward validate candidate X")
  * Flags duplicates against the existing leaderboard
  * Writes a one-screen review digest to analysis/kitchen-review/{date-time}.md

PER CLAUDE.md OP-30 + J directive 2026-05-21 "Claude is the driver."

GUARDS:
  * Never modifies the leaderboard markdown directly (J ratification owns that).
  * Only writes to analysis/kitchen-review/ + appends to _review-log.jsonl
    + queues follow-up tasks via kitchen_daemon.enqueue_task().
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
CANDIDATES_DIR = REPO / "strategy" / "candidates"
REVIEW_DIR = REPO / "analysis" / "kitchen-review"
REVIEW_LOG = CANDIDATES_DIR / "_review-log.jsonl"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
from run_minimax import call_minimax  # noqa: E402
from kitchen_daemon import enqueue_task, MODEL_LADDER  # noqa: E402


_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REVIEW_WINDOW_HOURS = 24       # review outputs from this many hours back
MAX_CANDIDATES_PER_FIRE = 12   # cap review batch size
MAX_FOLLOWUP_TASKS = 5         # cap how many new tasks the reviewer can enqueue per fire


def _et_offset_hours(dt_utc: datetime) -> int:
    y = dt_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march.weekday()) % 7
    dst_start_utc = (march + timedelta(days=days_to_sun + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov.weekday()) % 7
    dst_end_utc = (nov + timedelta(days=days_to_sun)).replace(hour=6)
    return -4 if (dst_start_utc <= dt_utc < dst_end_utc) else -5


def _et_now() -> datetime:
    now_utc = datetime.now(timezone.utc)
    return (now_utc + timedelta(hours=_et_offset_hours(now_utc))).replace(tzinfo=None)


if sys.platform == "win32" and os.path.basename(sys.executable).lower() == "pythonw.exe":
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _today = _et_now().strftime("%Y-%m-%d")
    sys.stdout = open(_log_dir / f"kitchen-reviewer-{_today}.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / f"kitchen-reviewer-{_today}.stderr.log", "a", buffering=1, encoding="utf-8")


def _log(msg: str) -> None:
    ts = _et_now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts} ET] {msg}", flush=True)


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _read_safe(path: Path, max_bytes: int = 60_000) -> str:
    try:
        if not path.exists():
            return ""
        data = path.read_text(encoding="utf-8", errors="replace")
        if len(data) > max_bytes:
            return data[:max_bytes] + f"\n\n[... truncated ...]"
        return data
    except OSError:
        return ""


def _block(label: str, content: str) -> str:
    if not content:
        return f"### {label}\n(empty)\n"
    return f"### {label}\n```\n{content}\n```\n"


def _already_reviewed_paths() -> set[str]:
    """Read _review-log.jsonl and return the set of cook output paths already reviewed."""
    seen: set[str] = set()
    if not REVIEW_LOG.exists():
        return seen
    try:
        with open(REVIEW_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    p = row.get("output_path")
                    if p:
                        seen.add(p)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return seen


def _collect_recent_outputs() -> list[Path]:
    """Find chef-nemo cook outputs from the last REVIEW_WINDOW_HOURS that haven't been reviewed."""
    if not CANDIDATES_DIR.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=REVIEW_WINDOW_HOURS)
    reviewed = _already_reviewed_paths()
    rows: list[tuple[float, Path]] = []
    for p in CANDIDATES_DIR.glob("*chef-nemo*.md"):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            if rel in reviewed or rel.replace("/", "\\") in reviewed:
                continue
            rows.append((mtime.timestamp(), p))
        except OSError:
            continue
    # Also include _analysis/ subdirectory outputs
    analysis_dir = CANDIDATES_DIR / "_analysis"
    if analysis_dir.exists():
        for p in analysis_dir.glob("*.md"):
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    continue
                rel = str(p.relative_to(REPO)).replace("\\", "/")
                if rel in reviewed or rel.replace("/", "\\") in reviewed:
                    continue
                rows.append((mtime.timestamp(), p))
            except OSError:
                continue
    rows.sort(key=lambda r: r[0], reverse=True)
    return [p for _, p in rows[:MAX_CANDIDATES_PER_FIRE]]


REVIEWER_SYSTEM_PROMPT = """You are the Kitchen Reviewer for Project Gamma 0DTE SPY R&D.

You read recent cook outputs and triage each into:
  - PROMOTE: high quality, novel, OP-16-positive => mark for leaderboard add
  - VALIDATE: promising but needs OOS / real-fills / Stage-2 backtest => queue follow-up
  - DUPLICATE: covers ground already in the leaderboard
  - LOW_QUALITY: insufficient OP-20 disclosures or weak hypothesis => archive

OUTPUT FORMAT (strict): respond with ONLY a JSON object, no preamble:
{
  "decisions": [
    {
      "output_path": "<exact relative path from inputs>",
      "verdict": "PROMOTE|VALIDATE|DUPLICATE|LOW_QUALITY",
      "rationale": "<one sentence>",
      "followup_task": "<imperative task for Chef to deepen this, or empty string>"
    },
    ...
  ],
  "digest": "<2-3 paragraph markdown digest summarizing the review batch>"
}

Be RIGOROUS:
  * PROMOTE only when the candidate has all OP-20 disclosures AND a positive edge_capture
    hypothesis AND no obvious conflict with the leaderboard.
  * Most candidates will be VALIDATE (need OOS, real-fills, or quantification).
  * Mark DUPLICATE when another leaderboard candidate clearly covers the same ground.
  * followup_task should be SPECIFIC and ACTIONABLE: "Run walk-forward on candidate X
    across 2025-Q3 + 2026-Q1 to verify regime stability" -- not "look into X further."
  * Empty followup_task is fine for DUPLICATE / LOW_QUALITY.

JSON object only. No markdown around it.
"""


def _build_review_prompt(outputs: list[Path]) -> str:
    sections = []
    for p in outputs:
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        body = _read_safe(p, 25_000)
        sections.append(f"### {rel}\n```markdown\n{body}\n```\n")

    leaderboard = _read_safe(CANDIDATES_DIR / "_LEADERBOARD.md", 30_000)
    body = (
        f"# Review {len(outputs)} recent cook output(s)\n\n"
        "## Existing leaderboard (for dedup check)\n\n"
        f"```\n{leaderboard}\n```\n\n"
        "## Cook outputs to review\n\n"
        + "\n".join(sections)
        + "\n\n## Your output\n\nJSON OBJECT per the system prompt's format. No preamble."
    )
    return body


def _extract_json_object(content: str) -> Optional[dict]:
    if not content:
        return None
    s = content.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl > 0:
            s = s[nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rsplit("```", 1)[0]
    s = s.strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    first = s.find("{")
    last = s.rfind("}")
    if first >= 0 and last > first:
        try:
            obj = json.loads(s[first:last + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _append_review_log(row: dict) -> None:
    try:
        REVIEW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(REVIEW_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError as exc:
        _log(f"WARN review_log write: {exc}")


# ────────────────────────────────────────────────────────────────────────────
# Auto-promote: check OP-20 disclosures + OP-16 floor before writing
# to _LEADERBOARD.md.  Falls back to _LEADERBOARD-pending.md so J can
# review candidates that are promising but incomplete.
# ────────────────────────────────────────────────────────────────────────────

# Keywords that signal each OP-20 disclosure (lower-case match).
_OP20_CHECKS = [
    ("account_size",    ["account-size", "account size", "equity", "qty=", "contracts", "per-account"]),
    ("sample_bias",     ["sample-bias", "sample bias", "selection", "overfit", "in-sample", "n="]),
    ("oos_test",        ["out-of-sample", "walk-forward", "oos", "held-out", "validation window"]),
    ("real_fills",      ["real-fills", "real fills", "opra", "simulator_real", "fills"]),
    ("failure_mode",    ["failure-mode", "failure mode", "worst day", "max drawdown", "blow-up", "max_drawdown"]),
    ("concentration",   ["concentration", "top-5 days", "% of p&l", "percent of pnl", "single day"]),
]

_OP16_PROMOTE_FLOOR = 771  # 50% of max 1542


def _check_op20_disclosures(candidate_text: str) -> tuple[bool, list[str]]:
    """Return (all_present, list_of_missing_keys)."""
    lower = candidate_text.lower()
    missing = []
    for key, patterns in _OP20_CHECKS:
        if not any(p in lower for p in patterns):
            missing.append(key)
    return len(missing) == 0, missing


def _find_numeric_edge_capture(obj) -> Optional[float]:
    """Depth-first search a scorecard JSON structure for a numeric edge_capture."""
    if isinstance(obj, dict):
        v = obj.get("edge_capture")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        for val in obj.values():
            found = _find_numeric_edge_capture(val)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for val in obj:
            found = _find_numeric_edge_capture(val)
            if found is not None:
                return found
    return None


def _scorecard_edge_capture(candidate_file: Path, candidate_text: str) -> tuple[Optional[float], str]:
    """Parse a NUMERIC edge_capture from an actual scorecard JSON on disk.

    Checks analysis/recommendations/{slug}.json plus any analysis/recommendations/
    *.json paths referenced in the candidate text. Returns (value, source_relpath)
    or (None, why_not).
    """
    cands: list[Path] = [REPO / "analysis" / "recommendations" / f"{candidate_file.stem}.json"]
    for m in re.finditer(r"analysis/recommendations/[\w\-.]+\.json",
                         candidate_text.replace("\\", "/")):
        cands.append(REPO / m.group(0))
    checked: list[str] = []
    for path in cands:
        if not path.exists():
            checked.append(f"{path.name}:missing")
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            checked.append(f"{path.name}:unreadable({type(exc).__name__})")
            continue
        val = _find_numeric_edge_capture(obj)
        if val is None:
            checked.append(f"{path.name}:no-numeric-edge_capture")
            continue
        try:
            rel = str(path.relative_to(REPO)).replace("\\", "/")
        except ValueError:
            rel = str(path)
        return val, rel
    return None, "no scorecard JSON with numeric edge_capture (" + "; ".join(checked) + ")"


def _check_op16_floor(candidate_file: Path, candidate_text: str) -> tuple[bool, str]:
    """Return (passes, reason_string).

    Passes ONLY on evidence that exists outside the LLM's own prose:
      (a) a NUMERIC edge_capture >= _OP16_PROMOTE_FLOOR parsed from a scorecard
          JSON on disk (analysis/recommendations/), OR
      (b) "new trade class" label AND "guard pass" both present.
    Free-text dollar amounts (e.g. 'inferred edge_capture=$25000') are NOT
    evidence — 7/7 recent auto-promotes cleared the floor on hallucinated
    strings (2026-07-01 consolidation audit).
    """
    lower = candidate_text.lower()
    # Pattern (b): new trade class with guard pass
    if "new trade class" in lower and "guard pass" in lower:
        return True, "new-trade-class with guard PASS"
    # Pattern (a): NUMERIC edge_capture from a scorecard JSON on disk
    val, source = _scorecard_edge_capture(candidate_file, candidate_text)
    if val is None:
        return False, f"no numeric scorecard edge_capture: {source}"
    if val >= _OP16_PROMOTE_FLOOR:
        return True, f"edge_capture={val:.0f} >= {_OP16_PROMOTE_FLOOR} (scorecard {source})"
    return False, f"scorecard edge_capture={val:.0f} < {_OP16_PROMOTE_FLOOR} ({source})"


def _next_leaderboard_rank() -> int:
    """Return next available rank number from _LEADERBOARD.md."""
    lb = CANDIDATES_DIR / "_LEADERBOARD.md"
    if not lb.exists():
        return 1
    text = lb.read_text(encoding="utf-8")
    ranks = [int(m.group(1)) for m in re.finditer(r"^\|\s*(\d+)\s*\|", text, re.MULTILINE)]
    return (max(ranks) + 1) if ranks else 1


def _resolve_candidate(out_path_str: str) -> Optional[Path]:
    """Resolve a reviewer-provided output path to a candidate file on disk."""
    candidate_file = CANDIDATES_DIR / Path(out_path_str).name
    if candidate_file.exists():
        return candidate_file
    # Try with full repo-relative path
    candidate_file = REPO / out_path_str
    return candidate_file if candidate_file.exists() else None


def _cap_promote_if_unevidenced(verdict: str, out_path: str) -> tuple[str, str]:
    """OP-33: PROMOTE requires numeric scorecard evidence on disk; else cap at VALIDATE.

    Returns (possibly-capped verdict, cap_reason) — cap_reason empty when not capped.
    """
    if verdict != "PROMOTE" or not out_path:
        return verdict, ""
    candidate_file = _resolve_candidate(out_path)
    if candidate_file is None:
        return "VALIDATE", f"capped: candidate file not found: {out_path}"
    text = candidate_file.read_text(encoding="utf-8", errors="replace")
    op16_ok, op16_reason = _check_op16_floor(candidate_file, text)
    if op16_ok:
        return verdict, ""
    return "VALIDATE", f"capped: {op16_reason}"


def _auto_promote_candidate(out_path_str: str, rationale: str) -> str:
    """Check gates and append to _LEADERBOARD.md or _LEADERBOARD-pending.md.

    Returns 'promoted', 'pending:<reasons>', or 'skip:<reason>'.
    """
    candidate_file = _resolve_candidate(out_path_str)
    if candidate_file is None:
        return f"skip:file-not-found:{out_path_str}"

    text = candidate_file.read_text(encoding="utf-8", errors="replace")
    slug = candidate_file.stem
    now_str = _et_now().strftime("%Y-%m-%d")

    op20_ok, missing = _check_op20_disclosures(text)
    op16_ok, op16_reason = _check_op16_floor(candidate_file, text)

    if op20_ok and op16_ok:
        # Full auto-promote
        rank = _next_leaderboard_rank()
        lb_path = CANDIDATES_DIR / "_LEADERBOARD.md"
        entry = (
            f"| {rank} | [{slug}]({candidate_file.name}) | Auto-promoted by reviewer | "
            f"{op16_reason} | TBD | TBD | 67/67 PASS | 5/10 | NEEDS-MORE-DATA | {now_str} |\n"
        )
        with open(lb_path, "a", encoding="utf-8") as f:
            f.write(entry)
        _log(f"AUTO-PROMOTE rank={rank} -> {slug}")
        return "promoted"
    else:
        # Write to pending for J review
        reasons = []
        if not op20_ok:
            reasons.append(f"missing-op20:{','.join(missing)}")
        if not op16_ok:
            reasons.append(f"op16-fail:{op16_reason}")
        pending_path = CANDIDATES_DIR / "_LEADERBOARD-pending.md"
        now_et = _et_now().strftime("%Y-%m-%d %H:%M")
        entry = (
            f"\n## {slug} — {now_et} ET\n"
            f"**Verdict:** PROMOTE (by reviewer)  \n"
            f"**Rationale:** {rationale}  \n"
            f"**Blocked:** {'; '.join(reasons)}  \n"
            f"**File:** [{candidate_file.name}]({candidate_file.name})  \n"
        )
        with open(pending_path, "a", encoding="utf-8") as f:
            f.write(entry)
        reason_str = "; ".join(reasons)
        _log(f"PENDING (not auto-promoted): {slug} -- {reason_str}")
        return f"pending:{reason_str}"


def _write_review_digest(decisions: list[dict], digest: str, *, cost_usd: float, model: str, tier: int) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    now = _et_now()
    fname = f"{now.strftime('%Y-%m-%dT%H%M')}-review.md"
    target = REVIEW_DIR / fname
    header = (
        "<!-- KITCHEN REVIEWER: autonomous review by free-tier model. -->\n"
        f"<!-- model={model}  tier={tier}  cost=${cost_usd:.4f}  generated_at={now.strftime('%Y-%m-%dT%H:%M:%S')} ET -->\n\n"
    )
    lines = [header,
             f"# Kitchen Review -- {now.strftime('%Y-%m-%d %H:%M')} ET\n",
             "## Verdicts\n",
             "| output | verdict | rationale |",
             "|---|---|---|"]
    for d in decisions:
        path = (d.get("output_path") or "").replace("|", "\\|")
        verdict = d.get("verdict", "?")
        rationale = (d.get("rationale") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{path}` | **{verdict}** | {rationale} |")
    lines.append("\n## Digest\n")
    lines.append(digest)
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    outputs = _collect_recent_outputs()
    _log(f"collected {len(outputs)} cook output(s) from last {REVIEW_WINDOW_HOURS}h")
    if not outputs:
        _log("nothing to review; exiting")
        return 0

    prompt = _build_review_prompt(outputs)

    # FREE POOL FIRST: route triage through the lane pool (chef role = Groq-70B
    # primary, big-ctx + no-train). Removes the OpenRouter-429 failure + paid tier;
    # falls back to the ladder if the pool returns nothing usable OR nothing
    # PARSEABLE -- 2026-08-20: the primary free model (nemotron) is a reasoning
    # model that sometimes burns its whole max_tokens budget on chain-of-thought
    # prose before ever emitting the required JSON object, returning ok=True with
    # unparseable/truncated content. The old gate only checked ok+non-empty, so
    # that case was accepted as "usable" and the ladder (which has 3 more free
    # tiers, none reasoning-heavy) was never tried -- 3/9 fires exited 1 on
    # 2026-08-20 from exactly this shape. Gate on JSON-parseability instead, for
    # BOTH the pool result and each ladder tier, so a garbled response from one
    # model falls through to the next rather than aborting the whole fire.
    result = None
    last_unparsed = None  # keep the best raw attempt around for the debug dump
    try:
        import swarm_client as _swarm  # noqa: E402
        pool_result = _swarm.call_role("chef", prompt, system=REVIEWER_SYSTEM_PROMPT,
                                       max_tokens=12000, temperature=0.3,
                                       timeout=140, remote_timeout=110, task_id="kitchen.reviewer")
        if pool_result.get("ok") and (pool_result.get("content") or "").strip():
            obj = _extract_json_object(pool_result.get("content", ""))
            if obj and "decisions" in obj:
                result = pool_result
                _log(f"reviewer via pool lane={result.get('lane')}")
            else:
                last_unparsed = pool_result
                _log(f"pool lane={pool_result.get('lane')} returned unparseable/truncated "
                     f"content ({len(pool_result.get('content') or '')} chars); trying ladder")
    except Exception as exc:  # noqa: BLE001
        _log(f"swarm reviewer path failed: {type(exc).__name__}: {exc}; trying ladder")

    if result is None:
        for tier_idx, model in enumerate(MODEL_LADDER):
            _log(f"ladder attempt tier={tier_idx} model={model}")
            candidate = call_minimax(prompt, system=REVIEWER_SYSTEM_PROMPT, model=model,
                                     max_tokens=12000, temperature=0.3, timeout=300,
                                     task_id=f"kitchen.reviewer.tier{tier_idx}")
            if candidate.get("ok") and (candidate.get("content") or "").strip():
                obj = _extract_json_object(candidate.get("content", ""))
                if obj and "decisions" in obj:
                    candidate["ladder_used"] = tier_idx
                    result = candidate
                    break
                last_unparsed = candidate
                _log(f"  tier {tier_idx} returned unparseable/truncated content; trying next tier")
                continue
            _log(f"  tier {tier_idx} failed: {candidate.get('error', 'unknown')}")

    if not result or not result.get("ok"):
        _log("all paths failed to produce parseable JSON; aborting this review fire")
        dump = last_unparsed or {}
        raw_path = STATE_DIR / "logs" / f"reviewer-bad-response-{_et_now().strftime('%Y%m%dT%H%M%S')}.txt"
        try:
            raw_path.write_text(dump.get("content", ""), encoding="utf-8")
        except OSError:
            pass
        return 1

    obj = _extract_json_object(result.get("content", ""))
    if not obj or "decisions" not in obj:
        # Should be unreachable now (result is only set once parsed) -- kept as
        # a safety net in case a future edit changes the gating above.
        _log("could not extract JSON object; raw saved")
        raw_path = STATE_DIR / "logs" / f"reviewer-bad-response-{_et_now().strftime('%Y%m%dT%H%M%S')}.txt"
        try:
            raw_path.write_text(result.get("content", ""), encoding="utf-8")
        except OSError:
            pass
        return 1

    decisions = obj.get("decisions", []) or []
    digest = obj.get("digest", "") or ""
    cost = float(result.get("cost_usd", 0.0) or 0.0)
    model = result.get("model", "unknown")
    tier = int(result.get("ladder_used", -1))

    digest_path = _write_review_digest(decisions, digest, cost_usd=cost, model=model, tier=tier)
    _log(f"digest -> {digest_path.relative_to(REPO)}")

    followup_count = 0
    for d in decisions:
        if not isinstance(d, dict):
            continue
        verdict = (d.get("verdict") or "").upper()
        out_path = (d.get("output_path") or "").strip()
        rationale = d.get("rationale", "")
        followup = (d.get("followup_task") or "").strip()
        # OP-33 evidence gate: an LLM PROMOTE with no numeric scorecard JSON on
        # disk is a hallucination risk (7/7 recent promotes rode the literal
        # string 'inferred edge_capture=$25000') -> cap at VALIDATE and log why.
        verdict, cap_reason = _cap_promote_if_unevidenced(verdict, out_path)
        if cap_reason:
            _log(f"  PROMOTE capped to VALIDATE: {cap_reason}")
        # Log every decision
        _append_review_log({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "output_path": out_path,
            "verdict": verdict,
            "rationale": rationale,
            "followup_task": followup,
            "cap_reason": cap_reason,
            "reviewer_model": model,
            "reviewer_tier": tier,
            "reviewer_cost_usd": cost,
        })
        _log(f"  {verdict:12s} {out_path[:80]}")
        # Auto-promote gate: if verdict=PROMOTE, check OP-20 + OP-16 before writing
        # to leaderboard.  Falls back to _LEADERBOARD-pending.md if gates not met.
        if verdict == "PROMOTE" and out_path:
            promote_result = _auto_promote_candidate(out_path, rationale)
            _log(f"    -> auto-promote: {promote_result}")
            _append_review_log({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "output_path": out_path,
                "verdict": f"PROMOTE_ACTION:{promote_result}",
                "rationale": rationale,
                "followup_task": "",
                "reviewer_model": model,
                "reviewer_tier": tier,
                "reviewer_cost_usd": 0.0,
            })
        # Enqueue followup if specified and within cap
        if followup and verdict in ("VALIDATE", "PROMOTE") and followup_count < MAX_FOLLOWUP_TASKS:
            tid = enqueue_task(followup, priority="high" if verdict == "PROMOTE" else "medium", source="reviewer")
            _log(f"    -> ENQ followup id={tid[:8]}: {followup[:100]}")
            followup_count += 1

    _log(f"DONE decisions={len(decisions)} followup_enqueued={followup_count} cost=${cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
