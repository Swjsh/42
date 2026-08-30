"""gamma_cost_meter.py -- deterministic LIVE COST METER for Project Gamma.

WHY (J, 2026-08-29): "cost-consciousness is a principle with no number behind it."
This module puts the number behind it -- for TODAY and the trailing 7 ET days,
broken down by origin where the data actually supports it.

THIS IS A READER, NOT A NEW LEDGER. Investigation before writing this file found
spend is ALREADY recorded on this box in three places, and this module reads all
three rather than re-deriving pricing or inventing a parallel accounting system:

  1. `spend_summary.py` -- the canonical Claude Code + MiniMax + Groq cost estimator.
     It walks real Claude Code session transcripts (~/.claude/projects/.../*.jsonl),
     sums token usage by tier, and prices it at Anthropic's PUBLISHED LIST RATES
     (spend_summary.PRICING). This module imports `_scan_claude_sessions` /
     `_scan_minimax` / `_scan_swarm_calls` directly and calls them live -- same
     function, same pricing table, not a re-implementation. This is the only
     figure close to a ground-truth AGGREGATE (it is origin-blind: interactive
     terminal sessions, conductor fires, companion escalations, and this very
     subagent's own session all land in the same pool).
  2. `conductor-outcomes.jsonl` + `conductor_budget.py` -- the conductor family
     (the dominant automation spender, ~93% of automation burn per that module's
     own census) self-reports `cost_usd` per fire. `conductor_budget.py` already
     proved that self-report UNDER-COUNTS real spend by a measured factor
     (SELF_REPORT_CORRECTION, currently 2.16x, independently re-derived
     2026-08-08 against real session transcripts -- see that module's docstring).
     This module imports that constant and applies it -- it does NOT hardcode a
     second copy of "2.16" that could drift out of sync with the real governor.
  3. `gamma-companion/lib/escalate.js` -- every companion escalation (chat +
     card-fire) streams a `{"step":"result","cost":<usd>}` frame into
     `automation/state/companion-ask-feed/<id>.jsonl`. THIS is the only place a
     per-escalation dollar figure is durably written; `appendResult()` (which
     writes the durable `companion-ask-results.jsonl` ledger with the `origin`
     tag, "chat" | "card" | "cockpit-chat" | "diagram" | "text") never carries
     the cost field, and `logActivity()` hardcodes `cost_usd: 0` for every
     escalation row. This module JOINS the two by ask id: cost comes from the
     feed frame, origin comes from the results row for the same id. The join is
     necessarily best-effort on BOTH sides -- the feed directory is pruned to
     the ~50 most-recently-completed asks repo-wide (`pruneFeedDir()`), and
     `companion-ask-results.jsonl` is itself a low-traffic channel (this box
     was found mid-investigation to have a ~10-week gap between companion-chat
     rows, which is plausible given most autonomous work runs through the
     conductor family rather than the companion HTTP server, not necessarily a
     bug) -- so an id present in the feed but missing from the results ledger
     lands in `companion_other` (priced, origin unattributed) rather than being
     silently folded into "chat" or dropped. `companion_results_staleness_flag()`
     checks this live on every run and raises a `data_quality_flags` entry
     whenever the results ledger is currently behind the feed, rather than
     assuming it always is.

HONESTY REQUIREMENT (load-bearing, J's own words): every dollar figure below
carries its provenance and says plainly when it is an ESTIMATE, not a bill.
Claude Code's own docs state the session-cost figure is a CLIENT-SIDE ESTIMATE
computed from token counts at list price -- nothing in this file, or in the
sources it reads, is an invoice. Concretely:

  * Every figure is `{"usd": <float|null>, "known": <bool>, "coverage":
    "full"|"partial"|"unknown", "method": "...", "note": "..."}`.
  * `coverage: "unknown"` FORCES `"usd": null` and `"known": false` -- a category
    that cannot be measured is reported as unknown, never as a silent zero
    (zero reads as "nothing was spent", which is a different, false claim).
  * `coverage: "full"` is only set when the source was read successfully for
    the WHOLE window being asked about (a day, or all 7 days for a trailing
    aggregate). A genuinely-empty-but-readable ledger (file exists, zero
    matching rows) IS a legitimate `"full"`/zero -- that is a verified absence
    of spend, not a measurement gap. The distinction is drawn explicitly in
    `conductor_by_day()` and `companion_by_day()`'s docstrings.
  * `coverage: "partial"` is used only for the 7-day AGGREGATE, when some days
    in the window are known and others are not -- the partial sum is shown
    (still useful) but `known` stays `false` and a note states how many of the
    7 days it actually covers.

Writes `automation/state/cost-meter.json`. Wired into the cockpit payload via
`setup/scripts/gamma_home.py` (`payload["cost_meter"]`), same `_load_json`
pattern every other cockpit section uses (missing/stale source -> visible
"NO DATA", never a fabricated number).

Pure Python, $0, no network, no LLM. Fails loud per-source (every reader
returns `(data_or_None, error_or_None)` and a caller-visible flag), never
crashes the whole report on one bad source (C7 -- audit outputs, not exit
codes).

CLI:
  python setup/scripts/gamma_cost_meter.py                  # write cost-meter.json
  python setup/scripts/gamma_cost_meter.py --check-only      # print JSON, no write
  python setup/scripts/gamma_cost_meter.py --date 2026-08-20 # anchor a different ET day
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
OUT_JSON = STATE_DIR / "cost-meter.json"

CONDUCTOR_OUTCOMES = STATE_DIR / "conductor-outcomes.jsonl"
COMPANION_FEED_DIR = STATE_DIR / "companion-ask-feed"
COMPANION_RESULTS = STATE_DIR / "companion-ask-results.jsonl"

WINDOW_DAYS = 7
# Must match escalate.js#pruneFeedDir(root, 50) -- the number of most-recently-
# modified ask-feed files the companion keeps. Used only to decide whether a
# day's companion coverage can be trusted as complete (see companion_by_day).
FEED_PRUNE_KEEP = 50

# --- reuse the existing accounting systems, don't invent a second one --------
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import spend_summary as _spend  # noqa: E402
import et_clock as _et  # noqa: E402

try:
    import conductor_budget as _cbud  # noqa: E402
    _CONDUCTOR_CORRECTION: Optional[float] = _cbud.SELF_REPORT_CORRECTION
    _CONDUCTOR_IMPORT_ERROR: Optional[str] = None
except Exception as e:  # noqa: BLE001 -- an import failure must degrade, not crash (C7)
    _cbud = None
    _CONDUCTOR_CORRECTION = None
    _CONDUCTOR_IMPORT_ERROR = str(e)


# --------------------------------------------------------------- figure helper

def _fig(usd, coverage: str, method: str, note: Optional[str] = None, **extra) -> dict:
    """One dollar figure with mandatory provenance.

    coverage:
      "full"    -- measured completely for the window this figure covers.
      "partial" -- some but not all of the window measured (aggregates only);
                   `usd` is still the partial sum, `known` is False, and a
                   caller-supplied note should say how much of the window it covers.
      "unknown" -- nothing measured; `usd` and `known` are forced regardless
                   of what was passed in, so a category that cannot be
                   measured can never come out looking like a verified zero.
    """
    if coverage not in ("full", "partial", "unknown"):
        raise ValueError("coverage must be full/partial/unknown, got %r" % (coverage,))
    out = {
        "usd": round(float(usd), 4) if (coverage != "unknown" and usd is not None) else None,
        "known": coverage == "full",
        "coverage": coverage,
        "method": method,
    }
    if note:
        out["note"] = note
    out.update(extra)
    return out


# ------------------------------------------------------------- date windowing

def trailing_et_dates(anchor_date: str, n: int = WINDOW_DAYS) -> list:
    """[anchor_date, anchor_date-1, ..., anchor_date-(n-1)] as 'YYYY-MM-DD', newest first."""
    anchor = datetime.strptime(anchor_date, "%Y-%m-%d")
    return [(anchor - timedelta(days=k)).strftime("%Y-%m-%d") for k in range(n)]


# ---------------------------------------------- source 1: Claude Code / MiniMax / Groq

def claude_minimax_groq_by_day(dates: list):
    """Live scan via spend_summary's OWN scanners -- the canonical Claude Code
    accounting system, called directly (not re-derived). Returns (per_date, error).

    On success every date in `dates` is a key (spend_summary._scan_claude_sessions
    pre-seeds a DayReport per target date, so a day with zero activity comes back
    as a genuine, verified zero -- not a gap). On failure `per_date` is {} and
    every caller must treat every date as unknown, never silently zero.
    """
    if not _spend.CC_PROJECT_DIR.exists():
        return {}, "Claude Code session dir not found: %s" % _spend.CC_PROJECT_DIR
    target = set(dates)
    try:
        reports = _spend._scan_claude_sessions(target)
        _spend._scan_minimax(reports)
        _spend._scan_swarm_calls(reports)
    except Exception as e:  # noqa: BLE001 -- a scan failure must not crash the meter
        return {}, "spend_summary scan failed: %s" % e
    out = {}
    for d in dates:
        r = reports.get(d)
        if r is None:
            continue
        out[d] = {
            "claude_usd": r.claude_total_cost,
            "minimax_usd": round(r.minimax_cost, 4),
            "groq_usd": round(r.groq_cost, 4),
            "claude_sessions": r.claude_sessions,
        }
    return out, None


# --------------------------------------------------------------- source 2: conductor

def _iso_to_et_date(stamp: str) -> Optional[str]:
    """ET calendar date for an ISO8601 stamp (conductor's `fired_at`, the
    companion feed's UTC `t`, etc). Reuses conductor_budget's own DST-aware
    UTC->ET conversion when importable, so every source in this module buckets
    a day the SAME way; falls back to a plain substring (UTC date) only when
    that conversion is unavailable or the stamp is unparseable."""
    if _cbud is not None:
        try:
            d = _cbud._stamp_to_et_date(stamp)
            if d:
                return d
        except Exception:  # noqa: BLE001
            pass
    return stamp[:10] if len(stamp) >= 10 else None


def conductor_by_day(dates: list, path: Optional[Path] = None, correction: Optional[float] = None):
    """Sum conductor-outcomes.jsonl's self-reported cost_usd per ET date, then
    apply the SAME correction factor conductor_budget.py's governor uses.

    Returns (per_date, error). A MISSING or unreadable ledger -> (None, error):
    every date must read unknown. An EXISTING, readable, empty (or day has zero
    matching rows) ledger -> a real dict with raw_usd=0.0 for that date -- a
    verified zero, because the ledger was actually read and had nothing to
    report, which is a different fact than "we couldn't check."
    Malformed rows (bad JSON, non-dict, unparseable cost_usd) are skipped, never
    fatal (C7).
    """
    path = path or CONDUCTOR_OUTCOMES
    correction = _CONDUCTOR_CORRECTION if correction is None else correction
    target = set(dates)
    if not path.exists():
        return None, "%s not found" % path
    raw = {d: 0.0 for d in dates}
    fires = {d: 0 for d in dates}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(row, dict):
                    continue
                stamp = str(row.get("fired_at") or row.get("ts_et") or "")
                d = _iso_to_et_date(stamp)
                if d not in target:
                    continue
                try:
                    c = float(row.get("cost_usd") or 0.0)
                except (TypeError, ValueError):
                    continue
                raw[d] += c
                fires[d] += 1
    except OSError as e:
        return None, str(e)
    out = {}
    for d in dates:
        out[d] = {
            "raw_usd": round(raw[d], 4),
            "fires": fires[d],
            "corrected_usd": round(raw[d] * correction, 4) if correction is not None else None,
        }
    return out, None


# --------------------------------------------------------------- source 3: companion

def companion_feed_scan(feed_dir: Optional[Path] = None):
    """Read every ask-feed file's terminal `{"step":"result", "cost": ...}` frame.

    Returns (records, error). records: list of {"id", "ts", "date", "cost_usd"}
    (cost_usd is None when the file has no result frame, or the frame carries no
    "cost" -- e.g. a busy/duplicate/halted no-op). A malformed file/line is
    skipped, never fatal (C7). A MISSING directory -> (None, error).
    """
    feed_dir = feed_dir or COMPANION_FEED_DIR
    if not feed_dir.exists():
        return None, "%s not found" % feed_dir
    try:
        files = sorted(feed_dir.glob("*.jsonl"))
    except OSError as e:
        return None, str(e)
    records = []
    for fp in files:
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        result_rec = None
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("step") == "result":
                result_rec = rec
                break
        if result_rec is None:
            continue
        ts = str(result_rec.get("t") or "")
        cost = result_rec.get("cost")
        try:
            cost = float(cost) if cost is not None else None
        except (TypeError, ValueError):
            cost = None
        records.append({
            "id": fp.stem,
            "ts": ts,
            "date": _iso_to_et_date(ts) if ts else None,
            "cost_usd": cost,
        })
    return records, None


# Origin strings escalate.js actually writes (server.js call sites + escalate.js's own
# "text" default) that count as the companion CHAT channel, as opposed to a card-fire tap.
CHAT_ORIGINS = frozenset({"chat", "cockpit-chat", "text", "diagram", "voice"})


def companion_origin_index(results_path: Optional[Path] = None):
    """id -> origin string, from companion-ask-results.jsonl (the only file that
    tags origin). Returns (index_or_None, error). Malformed rows are skipped,
    never fatal (C7). A row missing `id` or `origin` is skipped -- it simply
    cannot contribute to the join."""
    results_path = results_path or COMPANION_RESULTS
    if not results_path.exists():
        return None, "%s not found" % results_path
    idx = {}
    try:
        with open(results_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(row, dict):
                    continue
                rid, origin = row.get("id"), row.get("origin")
                if rid and origin:
                    idx[str(rid)] = str(origin)
    except OSError as e:
        return None, str(e)
    return idx, None


def companion_by_day(dates: list, feed_dir: Optional[Path] = None,
                      results_path: Optional[Path] = None, prune_keep: int = FEED_PRUNE_KEEP):
    """Per-date companion spend, split into card_fire / chat / companion_other,
    by JOINING the ask-feed's cost (`companion_feed_scan`) to the results
    ledger's origin (`companion_origin_index`) on ask id.

    Returns (per_date, error, coverage_meta). `error` is set only when the feed
    directory itself (the cost source) is unreadable -- the origin ledger is a
    best-effort join, not a hard dependency: an id with no origin match lands in
    `companion_other` (priced, just not attributable to chat vs card) rather
    than failing the whole read.

    The feed dir is pruned to the `prune_keep` most-recently-modified files
    REPO-WIDE, not per day, so an older day showing zero asks can mean either
    "genuinely no escalations that day" or "they existed and were pruned out" --
    those are different facts and this function does not conflate them:
      * If the directory currently holds FEWER than `prune_keep` files, nothing
        has ever been pruned (pruning only fires once the count exceeds the
        cap), so the full history present is complete and every day's count is
        a verified zero-or-real number -> every date is "full" coverage.
      * If the directory is AT the cap, only days on/after the oldest retained
        ask's date are guaranteed complete; anything older is "unknown", even
        if this scan finds zero matching records for it.
      * A day with at least one un-priced record (a result frame with no "cost",
        e.g. a busy/duplicate no-op) is NOT downgraded to unknown for that
        reason alone -- those are legitimately-zero-cost outcomes; only
        coverage (pruning) can make a day unknown.
    """
    records, err = companion_feed_scan(feed_dir)
    if err is not None:
        return None, err, None
    origin_idx, origin_err = companion_origin_index(results_path)

    file_count = len(records)
    dated = sorted(r["date"] for r in records if r["date"])
    oldest_retained = dated[0] if dated else None
    newest_retained = dated[-1] if dated else None
    at_cap = file_count >= prune_keep
    coverage_meta = {
        "files_retained": file_count,
        "prune_keep": prune_keep,
        "oldest_retained_date": oldest_retained,
        "newest_retained_date": newest_retained,
        "at_prune_cap": at_cap,
        "origin_index_available": origin_idx is not None,
        "origin_index_error": origin_err,
    }

    buckets = ("card_fire", "chat", "companion_other")
    per_day = {d: {b: {"usd": 0.0, "asks": 0} for b in buckets} for d in dates}
    for r in records:
        d = r["date"]
        if d not in per_day:
            continue
        origin = (origin_idx or {}).get(r["id"])
        if origin == "card":
            b = "card_fire"
        elif origin in CHAT_ORIGINS:
            b = "chat"
        else:
            b = "companion_other"
        per_day[d][b]["usd"] += r["cost_usd"] or 0.0
        per_day[d][b]["asks"] += 1

    out = {}
    for d in dates:
        if not at_cap:
            covered = True  # nothing ever pruned -- full history present
        else:
            covered = oldest_retained is not None and d >= oldest_retained
        out[d] = {"known": covered}
        for b in buckets:
            out[d][b] = {"usd": round(per_day[d][b]["usd"], 4), "asks": per_day[d][b]["asks"]}
    return out, None, coverage_meta


def companion_results_staleness_flag(results_path: Optional[Path] = None, feed_dir: Optional[Path] = None):
    """One human-readable string, checked LIVE on every run, for when the
    origin-tagged ledger (companion-ask-results.jsonl -- the only file that
    carries chat/card origin) is CURRENTLY behind real feed activity, else
    None. Deliberately a live check rather than an assumed-permanent fact:
    investigation while building this module found a real ~10-week gap in that
    ledger (2026-06-22 -> 2026-08-30) that self-resolved the moment another
    session used the companion again -- low traffic on a channel, not
    necessarily a broken one. When this DOES fire it explains why some ids in
    `companion_other` below couldn't be attributed to chat vs card_fire."""
    results_path = results_path or COMPANION_RESULTS
    feed_dir = feed_dir or COMPANION_FEED_DIR
    latest_result_ts = None
    if results_path.exists():
        try:
            with open(results_path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    ts = str(row.get("finished") or row.get("started") or "")
                    if ts and (latest_result_ts is None or ts > latest_result_ts):
                        latest_result_ts = ts
        except OSError:
            return "companion-ask-results.jsonl exists but is unreadable -- chat/card origin split degraded to companion_other"
    records, err = companion_feed_scan(feed_dir)
    if err or not records:
        return None
    feed_ts = [r["ts"] for r in records if r["ts"]]
    if not feed_ts:
        return None
    newest_feed_ts = max(feed_ts)
    if latest_result_ts is None or newest_feed_ts > latest_result_ts:
        return (
            "companion-ask-results.jsonl (the only ledger tagging origin=chat|card) is currently "
            "behind companion-ask-feed activity (latest tagged row: %s; latest feed activity: %s) "
            "-- asks completed after the ledger's latest row cannot be split into card_fire/chat "
            "and land in companion_other, priced but origin-unattributed, until the ledger catches up."
        ) % (latest_result_ts or "never", newest_feed_ts)
    return None


# ---------------------------------------------------------------- assembly

# The origin buckets carried per day, in the shape J asked for: card fire, chat,
# and conductor are real, data-backed categories; "workflow" is NOT currently
# tracked by any ledger on this box (no scheduled task outside the conductor
# family tags its own Claude Code spend) -- `other` is the honest stand-in,
# a residual that includes whatever "workflow" would have meant PLUS interactive
# terminal sessions PLUS companion escalations that couldn't be origin-matched.
ORIGIN_KEYS = ("conductor", "card_fire", "chat", "companion_other", "other")


def _residual_fig(claude_fig: dict, cond_fig: dict, card_fig: dict, chat_fig: dict,
                   comp_other_fig: dict) -> dict:
    """other = claude_code total - conductor - card_fire - chat - companion_other, for ONE day.

    Everything that is Claude Code spend but not a conductor fire and not a
    companion escalation of any kind: interactive terminal sessions (including
    this very subagent), scheduled tasks outside the conductor family, kitchen
    daemon calls, etc. -- the closest honest stand-in for a "workflow" bucket,
    since nothing tags that spend at the source. Only computed when every term
    is itself known for the day.
    """
    if not claude_fig["known"] or claude_fig["usd"] is None:
        return _fig(None, "unknown",
                    "other = claude_code_total - conductor - card_fire - chat - companion_other",
                    note="claude_code total unknown for this day")
    known_sum = 0.0
    any_unknown = False
    for f in (cond_fig, card_fig, chat_fig, comp_other_fig):
        if f["known"] and f["usd"] is not None:
            known_sum += f["usd"]
        else:
            any_unknown = True
    r = claude_fig["usd"] - known_sum
    notes = []
    if r < -0.01:
        notes.append("negative: self-reported origin costs exceeded the token-priced Claude "
                      "Code total for this day -- a methodology mismatch (self-report vs "
                      "token-priced aggregate), not a real credit")
    if any_unknown:
        notes.append("one or more origin sources unknown for this day -- this residual may "
                      "still contain some of their unmeasured spend")
    coverage = "unknown" if any_unknown else "full"
    return _fig(r, coverage,
                "other = claude_code_total - conductor - card_fire - chat - companion_other",
                note="; ".join(notes) if notes else None)


def _day_report(d: str, cmg: dict, cond: dict, comp: dict) -> dict:
    day_cmg = cmg.get(d)
    claude_known = day_cmg is not None
    claude_usd = day_cmg["claude_usd"] if claude_known else None
    minimax_usd = day_cmg["minimax_usd"] if claude_known else None
    groq_usd = day_cmg["groq_usd"] if claude_known else None
    claude_cov = "full" if claude_known else "unknown"

    claude_fig = _fig(claude_usd, claude_cov,
                       "live scan of Claude Code session transcripts, Anthropic list-price "
                       "token estimate (spend_summary.py's own scanner, called directly)",
                       note=None if claude_known else
                       "Claude Code session directory unreadable/unavailable")
    minimax_fig = _fig(minimax_usd, claude_cov,
                        "minimax-calls.jsonl real cost_usd telemetry (OpenRouter)")
    groq_fig = _fig(groq_usd, claude_cov,
                     "swarm-calls.jsonl tokens priced at Groq's published on-demand rate")

    day_cond = cond.get(d) if cond is not None else None
    cond_ok = day_cond is not None and _CONDUCTOR_CORRECTION is not None
    cond_fig = _fig(
        day_cond["corrected_usd"] if cond_ok else None,
        "full" if cond_ok else "unknown",
        "self-reported cost_usd from conductor-outcomes.jsonl, corrected x%s (same factor "
        "conductor_budget.py's spend governor applies -- imported, not re-derived)"
        % (("%.2f" % _CONDUCTOR_CORRECTION) if _CONDUCTOR_CORRECTION is not None else "?"),
        note=(None if cond_ok else (
            "conductor_budget.SELF_REPORT_CORRECTION unavailable (%s)" % _CONDUCTOR_IMPORT_ERROR
            if _CONDUCTOR_IMPORT_ERROR else "conductor-outcomes.jsonl unreadable")),
        **({"fires": day_cond["fires"], "raw_self_reported_usd": day_cond["raw_usd"]}
           if day_cond is not None else {}),
    )

    day_comp = comp.get(d) if comp is not None else None
    comp_ok = day_comp is not None and day_comp["known"]
    comp_note = None if comp_ok else \
        "companion-ask-feed coverage does not reach this date (pruned) or the feed dir is unreadable"

    def _comp_bucket_fig(bucket_key: str, method: str) -> dict:
        bucket = day_comp.get(bucket_key) if day_comp is not None else None
        return _fig(
            bucket["usd"] if bucket is not None else None,
            "full" if comp_ok else "unknown",
            method,
            note=comp_note,
            **({"asks_seen": bucket["asks"]} if bucket is not None else {}),
        )

    card_fig = _comp_bucket_fig(
        "card_fire", "SDK self-reported per-query cost, companion-ask-feed joined to "
                     "companion-ask-results.jsonl origin=='card'")
    chat_fig = _comp_bucket_fig(
        "chat", "SDK self-reported per-query cost, companion-ask-feed joined to "
                "companion-ask-results.jsonl origin in {chat,cockpit-chat,text,diagram,voice}")
    comp_other_fig = _comp_bucket_fig(
        "companion_other", "SDK self-reported per-query cost, companion-ask-feed id with no "
                            "origin match in companion-ask-results.jsonl (join gap, not zero spend)")

    other_fig = _residual_fig(claude_fig, cond_fig, card_fig, chat_fig, comp_other_fig)

    total_usd = None
    if claude_known:
        total_usd = (claude_usd or 0.0) + (minimax_usd or 0.0) + (groq_usd or 0.0)
    total_fig = _fig(total_usd, claude_cov, "claude_code + minimax + groq")

    return {
        "date_et": d,
        "claude_code": claude_fig,
        "minimax": minimax_fig,
        "groq": groq_fig,
        "total_usd": total_fig,
        "by_origin": {
            "conductor": cond_fig,
            "card_fire": card_fig,
            "chat": chat_fig,
            "companion_other": comp_other_fig,
            "other": other_fig,
        },
    }


def _agg(days: dict, getter, method: str) -> dict:
    """Sum one figure across the whole window. `known`/`coverage` reflect how
    many of the days actually had a known figure -- a partial sum is still
    shown (labeled partial), a fully-unknown category is not."""
    vals = []
    for rec in days.values():
        f = getter(rec)
        if f["known"] and f["usd"] is not None:
            vals.append(f["usd"])
    n_known = len(vals)
    n_total = len(days)
    if n_known == 0:
        return _fig(None, "unknown", method, note="0/%d days known" % n_total)
    s = sum(vals)
    if n_known == n_total:
        return _fig(s, "full", method)
    return _fig(s, "partial", method,
                note="partial: %d/%d days known, sum reflects only those" % (n_known, n_total))


def _aggregate_window(days: dict) -> dict:
    return {
        "claude_code": _agg(days, lambda r: r["claude_code"], "sum of daily claude_code"),
        "minimax": _agg(days, lambda r: r["minimax"], "sum of daily minimax"),
        "groq": _agg(days, lambda r: r["groq"], "sum of daily groq"),
        "total_usd": _agg(days, lambda r: r["total_usd"], "sum of daily total_usd"),
        "by_origin": {
            k: _agg(days, (lambda r, k=k: r["by_origin"][k]), "sum of daily %s" % k)
            for k in ORIGIN_KEYS
        },
    }


def build_report(anchor_date: Optional[str] = None) -> dict:
    anchor_date = anchor_date or _et.et_today_str()
    dates = trailing_et_dates(anchor_date, WINDOW_DAYS)

    cmg, cmg_err = claude_minimax_groq_by_day(dates)
    cond, cond_err = conductor_by_day(dates)
    comp, comp_err, comp_coverage = companion_by_day(dates)

    flags = []
    if cmg_err:
        flags.append("Claude Code / MiniMax / Groq scan unavailable: %s -- claude_code, "
                      "minimax, groq and total_usd are UNKNOWN for every day below." % cmg_err)
    if cond_err:
        flags.append("conductor-outcomes.jsonl unavailable: %s -- conductor origin is UNKNOWN "
                      "for every day below." % cond_err)
    if comp_err:
        flags.append("companion-ask-feed unavailable: %s -- companion origin is UNKNOWN for "
                      "every day below." % comp_err)
    if _CONDUCTOR_IMPORT_ERROR:
        flags.append("conductor_budget.py import failed (%s) -- the self-report correction "
                      "factor is unavailable, so conductor spend is reported UNKNOWN rather "
                      "than shown uncorrected (an uncorrected self-report is known to "
                      "under-count by ~2x)." % _CONDUCTOR_IMPORT_ERROR)
    stale_flag = companion_results_staleness_flag()
    if stale_flag:
        flags.append(stale_flag)

    days = {d: _day_report(d, cmg, cond or {}, comp or {}) for d in dates}
    trailing = _aggregate_window(days)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of_et_date": anchor_date,
        "window_days": WINDOW_DAYS,
        "provenance_note": (
            "Every usd figure here is a CLIENT-SIDE ESTIMATE (Anthropic list-price token "
            "counts, or an SDK/self-reported query cost) -- NONE of it is a billed invoice. "
            "coverage=\"unknown\" always means usd=null, never a silent zero; a real zero only "
            "appears when the underlying ledger was actually read and had nothing to report."
        ),
        "today": days.get(anchor_date),
        "trailing_7d": trailing,
        "days": days,
        "companion_feed_coverage": comp_coverage,
        "data_quality_flags": flags,
        "sources": {
            "claude_code_minimax_groq": "setup/scripts/spend_summary.py (_scan_claude_sessions/"
                                         "_scan_minimax/_scan_swarm_calls, called live)",
            "conductor": "automation/state/conductor-outcomes.jsonl, corrected via "
                         "conductor_budget.SELF_REPORT_CORRECTION",
            "card_fire_and_chat": "automation/state/companion-ask-feed/*.jsonl result frames "
                                   "(pruned to the %d most-recently-completed asks repo-wide), "
                                   "joined by ask id to companion-ask-results.jsonl's origin tag"
                                   % FEED_PRUNE_KEEP,
            "companion_other": "same feed, ask ids with no origin match in companion-ask-results.jsonl",
            "other": "residual = claude_code total - conductor - card_fire - chat - companion_other "
                     "(no distinct 'workflow' ledger exists on this box -- see module docstring)",
        },
    }


# --------------------------------------------------------------------- CLI

def _fmt(fig: Optional[dict]) -> str:
    if not fig:
        return "UNKNOWN"
    v = fig.get("usd")
    if v is None:
        return "UNKNOWN(%s)" % fig.get("coverage", "?")
    return "$%.2f" % v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="Anchor ET date YYYY-MM-DD (default: today)")
    ap.add_argument("--check-only", action="store_true", help="print JSON to stdout, don't write cost-meter.json")
    a = ap.parse_args()

    report = build_report(anchor_date=a.date)

    if a.check_only:
        print(json.dumps(report, indent=2))
        return 0

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(OUT_JSON)

    today = report.get("today") or {}
    origin = today.get("by_origin", {})
    print("wrote -> %s" % OUT_JSON.relative_to(REPO))
    print("today (%s):  total=%s  claude_code=%s  conductor=%s  card_fire=%s  chat=%s  "
          "companion_other=%s  other=%s"
          % (report["as_of_et_date"], _fmt(today.get("total_usd")), _fmt(today.get("claude_code")),
             _fmt(origin.get("conductor")), _fmt(origin.get("card_fire")), _fmt(origin.get("chat")),
             _fmt(origin.get("companion_other")), _fmt(origin.get("other"))))
    t7 = report["trailing_7d"]
    t7origin = t7.get("by_origin", {})
    print("trailing_7d:  total=%s  claude_code=%s  conductor=%s  card_fire=%s  chat=%s  "
          "companion_other=%s  other=%s"
          % (_fmt(t7.get("total_usd")), _fmt(t7.get("claude_code")), _fmt(t7origin.get("conductor")),
             _fmt(t7origin.get("card_fire")), _fmt(t7origin.get("chat")),
             _fmt(t7origin.get("companion_other")), _fmt(t7origin.get("other"))))
    if report["data_quality_flags"]:
        print("DATA QUALITY FLAGS:")
        for f in report["data_quality_flags"]:
            print("  - %s" % f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
