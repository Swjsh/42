"""gym_harvester — close the feedback loop from the crypto gym to the work queue.

Coach's finding: the gym is 30/30 PASS but `live_grinder.py` only exercises v01-v04
and produces zero new tasks for `automation/overnight/queue.md`. This module tails
the scorecard JSONLs, identifies edge cases worth investigating, and appends them
as candidate tasks to the queue.

The 7 edge-case rules are deliberately narrow — each one must point at a concrete
piece of evidence (timestamp + numeric measurement) so the queued task has the
context to act on it cold.

Pure file I/O. No live data fetch. No LLM in the loop. Zero recurring cost beyond
the daily Gamma_CryptoDaily fire that invokes it.

Per CLAUDE.md OP-27 L41 + project root rules, this module declares the
CREATE_NO_WINDOW constant up front for future-proofing even though it issues no
subprocess calls today.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

# OP-27 L41 layer 1: any subprocess.run/Popen/check_output added later MUST pass
# creationflags=_CREATE_NO_WINDOW on Windows.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# -- Project paths ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCORECARDS_DIR = PROJECT_ROOT / "crypto" / "data" / "scorecards"
GRINDER_PATH = SCORECARDS_DIR / "grinder.jsonl"
HISTORY_PATH = SCORECARDS_DIR / "history.jsonl"
LATEST_PATH = SCORECARDS_DIR / "latest.json"
STATE_PATH = SCORECARDS_DIR / "harvester-state.json"
SEEN_KEYS_PATH = SCORECARDS_DIR / "harvester-seen-keys.json"
HARVESTER_LOG_PATH = SCORECARDS_DIR / "harvester-log.jsonl"
QUEUE_PATH = PROJECT_ROOT / "automation" / "overnight" / "queue.md"
# Overflow rows pruned from the HARVESTED-FROM-GYM section land here verbatim
# (append-only audit trail). Keeps the ACTIVE queue.md section bounded.
QUEUE_HARVEST_ARCHIVE_PATH = PROJECT_ROOT / "automation" / "overnight" / "queue-harvest-archive.md"

# Cap on seen-keys persistence (FIFO).
SEEN_KEYS_CAP = 10_000

# Retention cap on the informational HARVESTED-FROM-GYM catalogue section.
# These EDGE_REGIME_EXTREME / EDGE_BREAKOUT_CLUSTER / EDGE_RSI_EXTREME / etc. rows
# are data-flywheel exhaust (OP-22 "the 371st untriaged candidate is debt") — they
# accumulate with no consumer draining them. We keep the newest N HARVEST-* rows in
# the live section and archive the overflow verbatim. The deterministic
# EDGE_REGRESSION_FAIL (CRIT) class lives in the `## CRITICAL` section and is NEVER
# touched by this cap — those are real engine-correctness gates (see L169 guard).
HARVESTED_SECTION_CAP = 15

# Sections in queue.md where harvested rows are inserted. CRITICAL is reserved
# for EDGE_REGRESSION_FAIL; everything else goes under HARVESTED-FROM-GYM.
SECTION_CRITICAL_HDR = "## CRITICAL"
SECTION_HARVESTED_HDR = "## HARVESTED-FROM-GYM (auto-queued by crypto/benchmarks/gym_harvester.py)"


# -- Rule registry ------------------------------------------------------------
# Short codes are baked into the queue.md row IDs (HARVEST-<RULE_SHORT>-<TS>).
@dataclass(frozen=True)
class Rule:
    code: str
    short: str
    priority: str  # "CRIT" | "HIGH" | "MED" | "LOW"


RULES = {
    "EDGE_FOOT_GUN_CAUGHT": Rule("EDGE_FOOT_GUN_CAUGHT", "FOOTGUN", "MED"),
    "EDGE_SOURCE_DISAGREEMENT": Rule("EDGE_SOURCE_DISAGREEMENT", "SRCDISAGREE", "MED"),
    "EDGE_RSI_EXTREME": Rule("EDGE_RSI_EXTREME", "RSIEXTREME", "MED"),
    "EDGE_VOLUME_SPIKE": Rule("EDGE_VOLUME_SPIKE", "VOLSPIKE", "MED"),
    "EDGE_RIBBON_FLIP": Rule("EDGE_RIBBON_FLIP", "RIBBONFLIP", "MED"),
    "EDGE_SWEEP_DETECTED": Rule("EDGE_SWEEP_DETECTED", "SWEEP", "MED"),
    "EDGE_REGRESSION_FAIL": Rule("EDGE_REGRESSION_FAIL", "REGFAIL", "CRIT"),
    # New rules from expanded grinder coverage (v09/v11, added 2026-05-19)
    "EDGE_REGIME_EXTREME": Rule("EDGE_REGIME_EXTREME", "REGIMEEXT", "LOW"),
    "EDGE_BREAKOUT_CLUSTER": Rule("EDGE_BREAKOUT_CLUSTER", "BRKCLUSTER", "MED"),
}


# -- Value types --------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    rule: str
    key: str          # dedup key, format: "{rule}:{date}:{bar_iso_or_ref}"
    description: str  # one-line, with key numbers baked in
    priority: str     # "CRIT"|"HIGH"|"MED"|"LOW"
    source_ts: str    # ISO timestamp of the evidence point


@dataclass
class HarvestStats:
    candidates_scanned: int = 0
    candidates_new: int = 0
    candidates_appended_to_queue: int = 0
    candidates_skipped_dup: int = 0
    candidates_skipped_already_in_queue: int = 0
    candidates_archived: int = 0  # catalogue rows pruned over HARVESTED_SECTION_CAP
    by_rule: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


# -- IO helpers ---------------------------------------------------------------
def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_seen_keys() -> list:
    """Return seen-keys as an ordered list (oldest first). FIFO eviction at cap."""
    if SEEN_KEYS_PATH.exists():
        try:
            data = json.loads(SEEN_KEYS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "keys" in data:
                return list(data["keys"])
            if isinstance(data, list):
                return list(data)
        except json.JSONDecodeError:
            pass
    return []


def _save_seen_keys(keys: list) -> None:
    if len(keys) > SEEN_KEYS_CAP:
        keys = keys[-SEEN_KEYS_CAP:]
    SEEN_KEYS_PATH.write_text(
        json.dumps({"keys": keys, "cap": SEEN_KEYS_CAP}, indent=2),
        encoding="utf-8",
    )


def _parse_iso_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _tail_jsonl_since(
    path: Path,
    cutoff: datetime,
    ts_key_candidates: tuple[str, ...] = ("started_at", "fetched_at", "checked_at"),
) -> Iterable[dict]:
    """Yield JSONL records whose timestamp is >= cutoff.

    Records with no parseable timestamp are skipped. Parse errors on a line are
    logged-and-skipped (the loop never aborts on one bad row — the JSONL is the
    crash-tolerant signal-conveyance layer).
    """
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts_str = None
            for k in ts_key_candidates:
                if k in rec and rec[k]:
                    ts_str = rec[k]
                    break
            ts = _parse_iso_ts(ts_str) if ts_str else None
            if ts is None or ts < cutoff:
                continue
            yield rec


def _load_latest_json() -> dict | None:
    if not LATEST_PATH.exists():
        return None
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# -- Thresholds ---------------------------------------------------------------
# Only queue a foot-gun catch when the in-progress bar's close was >$5 away from
# the eventual closed-bar close (BTC-cent units).  Sub-threshold catches are
# evidence the filter WORKS correctly — not bugs to investigate.  They are logged
# to grinder.jsonl but NOT queued as action items.
FOOT_GUN_MIN_DRIFT_CENTS: float = 500.0


# -- Edge-case detectors ------------------------------------------------------
def _detect_foot_gun(rec: dict) -> Candidate | None:
    """EDGE_FOOT_GUN_CAUGHT — v01_live caught TV/source returning an in-progress bar.

    Only queues when |close_drift| >= FOOT_GUN_MIN_DRIFT_CENTS (default 500 BTC-cents
    = $5.00).  Sub-threshold catches confirm the filter is working as designed and
    don't need individual investigation; they accumulate silently in grinder.jsonl
    for aggregate review.
    """
    v01 = rec.get("results", {}).get("v01_live", {})
    if not isinstance(v01, dict):
        return None
    if not v01.get("foot_gun_caught_this_fetch"):
        return None
    bar_open = v01.get("naive_last_bar_open") or rec.get("started_at", "")
    rejected = v01.get("bars_rejected_as_in_progress", 0)
    secs_until_close = v01.get("naive_last_bar_seconds_until_close")
    delta = v01.get("ohlc_delta_naive_minus_filtered") or {}
    close_drift = delta.get("close", 0.0) if isinstance(delta, dict) else 0.0
    # Only queue when the in-progress vs closed-bar close differs significantly.
    if abs(close_drift) < FOOT_GUN_MIN_DRIFT_CENTS:
        return None
    key = f"EDGE_FOOT_GUN_CAUGHT:{bar_open}"
    desc = (
        f"v01_live foot-gun caught at bar_open={bar_open} | "
        f"bars_rejected={rejected} secs_until_close={secs_until_close} "
        f"close_drift_naive_vs_filtered={close_drift:+.2f} "
        f"[EXCEEDS {FOOT_GUN_MIN_DRIFT_CENTS:.0f}c threshold — investigate]"
    )
    return Candidate(
        rule="EDGE_FOOT_GUN_CAUGHT",
        key=key,
        description=desc,
        priority=RULES["EDGE_FOOT_GUN_CAUGHT"].priority,
        source_ts=v01.get("fetched_at") or rec.get("started_at", ""),
    )


def _detect_source_disagreement(rec: dict) -> list[Candidate]:
    """EDGE_SOURCE_DISAGREEMENT — v02 or v15 found a >tolerance OHLC delta.

    v02_source_parity is in KNOWN_FLAKY_LIVE_SOURCE (OP-26 carve-out) — live-source
    timing jitter at bar boundaries is expected and NOT a bug.  Skip v02 entirely
    so the queue is not polluted with known-normal disagreements.
    """
    out: list[Candidate] = []
    # v02_source_parity is KNOWN_FLAKY_LIVE_SOURCE (OP-26 carve-out) — live-source
    # timing jitter at bar boundaries is a normal event, not a bug.  v02 is already
    # excluded from `overall_pass` in runner.py.  Skip queuing its disagreements.
    # v15_three_source_parity.live is similarly carved out.
    # v15 / v02 inside latest.json runs[] (different shape) — skipped for same reason.
    return out


def _detect_rsi_extreme(rec: dict) -> Candidate | None:
    """EDGE_RSI_EXTREME — BTC at oversold/overbought boundary (<20 or >80)."""
    v03 = rec.get("results", {}).get("v03_indicators_live", {})
    if not isinstance(v03, dict):
        return None
    rsi = v03.get("rsi_14_last")
    if rsi is None:
        return None
    if not (rsi < 20 or rsi > 80):
        return None
    last_close = v03.get("last_close")
    started = rec.get("started_at", "")
    # Bucket the timestamp into a 5-min bin so multiple iterations in the same
    # 5-min window dedup against the same key.
    ts = _parse_iso_ts(started)
    if ts is not None:
        bin_iso = ts.replace(second=0, microsecond=0,
                             minute=(ts.minute // 5) * 5).isoformat()
    else:
        bin_iso = started
    direction = "oversold" if rsi < 20 else "overbought"
    key = f"EDGE_RSI_EXTREME:{bin_iso}:{direction}"
    desc = (
        f"BTC v03_indicators rsi_14={rsi:.2f} ({direction}) "
        f"at last_close={last_close} bin={bin_iso}"
    )
    return Candidate(
        rule="EDGE_RSI_EXTREME",
        key=key,
        description=desc,
        priority=RULES["EDGE_RSI_EXTREME"].priority,
        source_ts=started,
    )


def _detect_volume_spike_from_latest(latest: dict) -> Candidate | None:
    """EDGE_VOLUME_SPIKE — v07_volume.live shows > 15 bars >3x rolling vol in 200-bar window."""
    runs = latest.get("runs", [])
    for run in runs:
        if run.get("name") != "v07_volume.live":
            continue
        result = run.get("result", {})
        bars_above_3x = result.get("bars_above_3x")
        if bars_above_3x is None or bars_above_3x <= 15:
            return None
        closed_bars = result.get("closed_bars", 0)
        started = latest.get("summary", {}).get("started_at", "")
        ts = _parse_iso_ts(started)
        bin_iso = ts.replace(second=0, microsecond=0).isoformat() if ts else started
        # Hour-bucket so successive harvests don't fire on the same 200-bar window.
        if ts is not None:
            hour_bin = ts.replace(minute=0, second=0, microsecond=0).isoformat()
        else:
            hour_bin = bin_iso
        key = f"EDGE_VOLUME_SPIKE:{hour_bin}"
        desc = (
            f"v07_volume.live bars_above_3x={bars_above_3x} "
            f"(>15 over {closed_bars}-bar window) — high-vol cluster "
            f"potential level-break test setup"
        )
        return Candidate(
            rule="EDGE_VOLUME_SPIKE",
            key=key,
            description=desc,
            priority=RULES["EDGE_VOLUME_SPIKE"].priority,
            source_ts=started,
        )
    return None


def _detect_ribbon_flip_from_latest(latest: dict) -> Candidate | None:
    """EDGE_RIBBON_FLIP — v08_ribbon.live shows directional flip with spread > 100."""
    runs = latest.get("runs", [])
    for run in runs:
        if run.get("name") != "v08_ribbon.live":
            continue
        result = run.get("result", {})
        last = result.get("last", {}) or {}
        spread = last.get("spread", 0.0)
        status = last.get("status", "")
        # Per spec: MIXED -> BULL/BEAR with spread > 100. We don't have the prior
        # snapshot inline, but a current BULL/BEAR with spread > 100 AND a non-
        # trivial MIXED population in the recent distribution is a strong proxy.
        dist = result.get("status_distribution", {}) or {}
        mixed_count = dist.get("MIXED", 0)
        bull_count = dist.get("BULL", 0)
        bear_count = dist.get("BEAR", 0)
        total = bull_count + bear_count + mixed_count
        if total == 0:
            return None
        mixed_share = mixed_count / total
        if status not in ("BULL", "BEAR"):
            return None
        if spread <= 100:
            return None
        if mixed_share < 0.10:
            # Without recent chop there's no "flip" — skip.
            return None
        started = latest.get("summary", {}).get("started_at", "")
        ts = _parse_iso_ts(started)
        hour_bin = (
            ts.replace(minute=0, second=0, microsecond=0).isoformat()
            if ts else started
        )
        key = f"EDGE_RIBBON_FLIP:{hour_bin}:{status}"
        desc = (
            f"v08_ribbon flip MIXED -> {status} | spread={spread:.2f}>100 | "
            f"recent dist BULL={bull_count} BEAR={bear_count} MIXED={mixed_count}"
        )
        return Candidate(
            rule="EDGE_RIBBON_FLIP",
            key=key,
            description=desc,
            priority=RULES["EDGE_RIBBON_FLIP"].priority,
            source_ts=started,
        )
    return None


def _detect_sweep_from_latest(latest: dict) -> list[Candidate]:
    """EDGE_SWEEP_DETECTED — v14_sweep.live sweep hits with close_back_pct > 0.05."""
    out: list[Candidate] = []
    runs = latest.get("runs", [])
    for run in runs:
        if run.get("name") != "v14_sweep.live":
            continue
        result = run.get("result", {})
        if (result.get("sweep_hits") or 0) <= 0:
            return []
        for ex in result.get("examples", []):
            close_back = ex.get("close_back_pct", 0.0)
            if close_back <= 0.05:
                continue
            level = ex.get("level")
            direction = ex.get("dir") or ex.get("direction") or "?"
            bar_idx = ex.get("bar_idx") or ex.get("bar")
            started = latest.get("summary", {}).get("started_at", "")
            key = f"EDGE_SWEEP_DETECTED:{started}:{level}:{direction}:{bar_idx}"
            wick_excess = ex.get("wick_excess_pct", 0.0)
            desc = (
                f"v14_sweep liquidity-grab at level={level} dir={direction} "
                f"bar_idx={bar_idx} | wick_excess={wick_excess:.4f}% "
                f"close_back={close_back:.4f}% — feeds v15.2 sweep-blocker doctrine"
            )
            out.append(Candidate(
                rule="EDGE_SWEEP_DETECTED",
                key=key,
                description=desc,
                priority=RULES["EDGE_SWEEP_DETECTED"].priority,
                source_ts=started,
            ))
    return out


def _detect_regime_extreme(rec: dict) -> Candidate | None:
    """EDGE_REGIME_EXTREME — v09_regime.live shows >70% TREND_DOWN or >70% TREND_UP.

    A dominant BTC regime cluster (70%+ of 100 bars in one direction) correlates with
    sustained-trend SPY sessions. LOW priority — correlation study, not a direct trigger.
    Hour-bucketed to avoid spam on multi-hour trend days.
    """
    v09 = rec.get("results", {}).get("v09_live", {})
    if not isinstance(v09, dict) or v09.get("mode") != "live":
        return None
    dist = v09.get("regime_distribution", {}) or {}
    total = sum(dist.values())
    if total == 0:
        return None
    trend_down = dist.get("TREND_DOWN", 0)
    trend_up = dist.get("TREND_UP", 0)
    dominant_pct = max(trend_down, trend_up) / total
    if dominant_pct < 0.70:
        return None
    direction = "TREND_DOWN" if trend_down > trend_up else "TREND_UP"
    dominant_count = max(trend_down, trend_up)
    started = rec.get("started_at", "")
    ts = _parse_iso_ts(started)
    hour_bin = ts.replace(minute=0, second=0, microsecond=0).isoformat() if ts else started
    key = f"EDGE_REGIME_EXTREME:{hour_bin}:{direction}"
    desc = (
        f"v09_regime {direction} dominant: {dominant_count}/{total} bars "
        f"({dominant_pct:.0%}) | last_regime={v09.get('last_regime')} "
        f"atr_14={v09.get('atr_14', 0):.0f} — sustained BTC trend; check SPY correlation"
    )
    return Candidate(
        rule="EDGE_REGIME_EXTREME",
        key=key,
        description=desc,
        priority=RULES["EDGE_REGIME_EXTREME"].priority,
        source_ts=started,
    )


def _detect_breakout_cluster(rec: dict) -> Candidate | None:
    """EDGE_BREAKOUT_CLUSTER — v11_breakout.live shows ≥3 breakout hits in 100-bar window.

    Multiple level breaks in a short window indicate a high-volatility/trending session.
    This confirms the breakout-detection primitive is working AND flags unusually active
    price action worth studying for SPY correlation.
    """
    v11 = rec.get("results", {}).get("v11_live", {})
    if not isinstance(v11, dict) or v11.get("mode") != "live":
        return None
    hits = v11.get("breakout_hits", 0) or 0
    if hits < 3:
        return None
    examples = v11.get("examples", []) or []
    started = rec.get("started_at", "")
    ts = _parse_iso_ts(started)
    hour_bin = ts.replace(minute=0, second=0, microsecond=0).isoformat() if ts else started
    key = f"EDGE_BREAKOUT_CLUSTER:{hour_bin}"
    levels_hit = {ex.get("level_price") for ex in examples if ex.get("level_price")}
    by_dir = v11.get("by_direction", {}) or {}
    desc = (
        f"v11_breakout {hits} breaks in {v11.get('closed_bars', '?')}-bar window "
        f"(up={by_dir.get('up', 0)} down={by_dir.get('down', 0)}) "
        f"across {len(levels_hit)} levels — high-activity price action cluster"
    )
    return Candidate(
        rule="EDGE_BREAKOUT_CLUSTER",
        key=key,
        description=desc,
        priority=RULES["EDGE_BREAKOUT_CLUSTER"].priority,
        source_ts=started,
    )


# Stages whose failure is environmental (live-data-source dependent), never a
# deterministic code regression. A `.live` stage fails when the data feed is
# unreachable (network blip / rate-limit) — every `.live` stage fails at once and
# self-heals on the next run. v02_source_parity / v15_three_source_parity.live are
# the named KNOWN_FLAKY_LIVE_SOURCE carve-outs (already excluded from overall_pass
# in runner.py). Only an `.offline` / `.fixture` failure is a reproducible engine
# break worth a CRITICAL queue item.
KNOWN_FLAKY_LIVE_STAGES = frozenset({
    "v02_source_parity",
    "v15_three_source_parity.live",
})


def _is_deterministic_stage(name: str) -> bool:
    """True iff a failure of this stage is a reproducible code regression.

    Live/source-dependent stages are environmental: a transient data-feed outage
    fails them all simultaneously and self-heals, so they must NOT raise a CRITICAL
    (harvester false-CRITICAL flood — see L-index C7 / OP-22).
    """
    if name in KNOWN_FLAKY_LIVE_STAGES:
        return False
    return not name.endswith(".live")


def _detect_regression_fail(rec: dict) -> Candidate | None:
    """EDGE_REGRESSION_FAIL — history.jsonl overall_pass=false. CRITICAL priority.

    Guard (OP-25): suppress when the failure is purely environmental — i.e. every
    failed stage is a `.live`/known-flaky source-dependent stage. Those are transient
    data-feed outages that self-heal, not engine regressions, and previously flooded
    the queue's `## CRITICAL` section with un-drainable phantom items. A CRITICAL only
    fires when at least one DETERMINISTIC (`.offline`/`.fixture`) stage fails, OR when
    no per_stage breakdown is available to classify (conservative: still flag).
    """
    if rec.get("overall_pass") is not False:
        return None
    failed_stages = [
        name for name, ok in (rec.get("per_stage") or {}).items() if not ok
    ]
    deterministic_failures = [s for s in failed_stages if _is_deterministic_stage(s)]
    if failed_stages and not deterministic_failures:
        # All failed stages are live-source/environmental — transient outage that
        # self-heals next run. Not a code regression; do not emit a CRITICAL.
        return None
    started = rec.get("started_at", "")
    key = f"EDGE_REGRESSION_FAIL:{started}"
    failed_summary = ",".join(failed_stages) if failed_stages else "unknown"
    desc = (
        f"regression RED at {started} | failed stages: {failed_summary} | "
        f"passed={rec.get('passed')}/{rec.get('stages')} — CRITICAL gate breach"
    )
    return Candidate(
        rule="EDGE_REGRESSION_FAIL",
        key=key,
        description=desc,
        priority=RULES["EDGE_REGRESSION_FAIL"].priority,
        source_ts=started,
    )


def _detect_three_source_disagreement_from_latest(latest: dict) -> list[Candidate]:
    """EDGE_SOURCE_DISAGREEMENT extension — v15_three_source_parity violations."""
    out: list[Candidate] = []
    runs = latest.get("runs", [])
    for run in runs:
        if run.get("name") != "v15_three_source_parity.live":
            continue
        result = run.get("result", {})
        if (result.get("violations_count") or 0) <= 0:
            return []
        for v in result.get("violations", []):
            bar_open = v.get("open_time", "")
            key = f"EDGE_SOURCE_DISAGREEMENT:v15:{bar_open}"
            desc = (
                f"v15 three-way (coinbase/yfinance/alpaca) disagreement "
                f"at bar={bar_open} — pricing skew between sources"
            )
            out.append(Candidate(
                rule="EDGE_SOURCE_DISAGREEMENT",
                key=key,
                description=desc,
                priority=RULES["EDGE_SOURCE_DISAGREEMENT"].priority,
                source_ts=result.get("checked_at", ""),
            ))
    return out


# -- Queue.md interaction -----------------------------------------------------
HARVEST_ROW_RE = re.compile(
    r"^- \[[ x]\] HARVEST-[A-Z]+-\d{8}-\d{6}\b.*$",
    re.MULTILINE,
)


def _extract_existing_keys_from_queue(queue_text: str) -> set[str]:
    """Return the dedup keys baked into HARVEST-* rows already in queue.md.

    Rows we append have a sentinel `key=<DEDUP_KEY>` at the end of the
    description block so we can perfectly de-dup on re-runs without parsing
    free-form text. Falls back to the row id alone when sentinel is missing.
    """
    seen: set[str] = set()
    for m in HARVEST_ROW_RE.finditer(queue_text):
        line = m.group(0)
        # Sentinel: ` key=<DEDUP_KEY> ::`
        km = re.search(r"\bkey=([^\s:]+(?::[^\s:]+)*?)(?=\s+::|\s*$)", line)
        if km:
            seen.add(km.group(1))
        # Also record the row id as a fallback identifier.
        idm = re.search(r"HARVEST-[A-Z]+-\d{8}-\d{6}", line)
        if idm:
            seen.add(idm.group(0))
    return seen


def _format_queue_row(c: Candidate, ts_now: datetime) -> str:
    """Render a candidate as a queue.md row.

    Format (matches existing queue.md schema):
        - [ ] HARVEST-<RULE_SHORT>-<YYYYMMDD-HHMMSS> (PRI) :: <description> :: \
              key=<KEY> :: depends:none :: status:queued
    """
    rule_short = RULES[c.rule].short
    ts_id = ts_now.strftime("%Y%m%d-%H%M%S")
    row_id = f"HARVEST-{rule_short}-{ts_id}"
    return (
        f"- [ ] {row_id} ({c.priority}) :: {c.description} :: "
        f"key={c.key} :: depends:none :: status:queued"
    )


def _ensure_harvested_section(queue_text: str) -> tuple[str, int]:
    """Make sure HARVESTED-FROM-GYM section exists. Returns (text, insertion_idx).

    insertion_idx points at the first newline AFTER the section header so new
    rows are inserted directly under the header (newest first).
    """
    if SECTION_HARVESTED_HDR in queue_text:
        idx = queue_text.index(SECTION_HARVESTED_HDR)
        # Move idx to the newline after the header line.
        eol = queue_text.index("\n", idx)
        # Skip the immediate blank line after the header if present.
        if queue_text[eol:eol + 2] == "\n\n":
            eol += 1
        return queue_text, eol + 1

    # Insert new section after the SWARM-BACKFILL section. The SWARM-BACKFILL
    # block ends at the next "## " or end of file.
    swarm_hdr = "## SWARM-BACKFILL"
    if swarm_hdr in queue_text:
        start = queue_text.index(swarm_hdr)
        # Find the next "## " section header after this one.
        next_section = queue_text.find("\n## ", start + len(swarm_hdr))
        if next_section == -1:
            # No next section — append at end.
            insertion = len(queue_text)
        else:
            insertion = next_section + 1  # skip the leading newline
    else:
        # No SWARM-BACKFILL section — append at end.
        insertion = len(queue_text)

    section_block = (
        f"\n{SECTION_HARVESTED_HDR}\n\n"
    )
    new_text = queue_text[:insertion] + section_block + queue_text[insertion:]
    new_idx = insertion + len(section_block)
    return new_text, new_idx


def _ensure_critical_section(queue_text: str) -> tuple[str, int]:
    """Return (text, insertion_idx) for the CRITICAL section.

    insertion_idx is the line right after `## CRITICAL` (above `(empty)` if
    present, otherwise above any existing rows).
    """
    if SECTION_CRITICAL_HDR not in queue_text:
        # Prepend section at very top.
        section_block = f"{SECTION_CRITICAL_HDR}\n\n"
        return section_block + queue_text, len(section_block)

    idx = queue_text.index(SECTION_CRITICAL_HDR)
    eol = queue_text.index("\n", idx)
    after = eol + 1
    # If "(empty)" line follows, replace it.
    next_line_end = queue_text.find("\n", after)
    if next_line_end == -1:
        next_line_end = len(queue_text)
    next_line = queue_text[after:next_line_end].strip()
    if next_line == "(empty)":
        # Replace "(empty)" with our insertion point.
        new_text = queue_text[:after] + queue_text[next_line_end + 1:]
        return new_text, after
    return queue_text, after


# -- Retention cap (OP-22 compound-don't-accumulate) --------------------------
def _prune_harvested_section(
    queue_text: str, cap: int,
) -> tuple[str, list[str]]:
    """Trim the HARVESTED-FROM-GYM section to the newest `cap` HARVEST-* rows.

    Rows are inserted newest-first directly under the section header, so in
    document order the FIRST `cap` HARVEST rows are the newest — we keep those and
    return the overflow (oldest) rows for verbatim archival. Only lines matching
    HARVEST_ROW_RE are considered: free-text `### T-GYM-*` sub-blocks, blank lines,
    and the deterministic CRITICAL section (a separate section) are left untouched.

    Returns (new_text, archived_rows). No-op (archived_rows == []) when the section
    is absent or already at/under the cap.
    """
    if cap < 0 or SECTION_HARVESTED_HDR not in queue_text:
        return queue_text, []
    start = queue_text.index(SECTION_HARVESTED_HDR)
    after_hdr = queue_text.index("\n", start) + 1
    next_section = queue_text.find("\n## ", after_hdr)
    end = len(queue_text) if next_section == -1 else next_section + 1
    section = queue_text[after_hdr:end]
    lines = section.split("\n")

    harvest_idxs = [i for i, ln in enumerate(lines) if HARVEST_ROW_RE.match(ln)]
    if len(harvest_idxs) <= cap:
        return queue_text, []

    archive_idxs = set(harvest_idxs[cap:])  # oldest beyond the cap
    archived_rows = [lines[i] for i in harvest_idxs[cap:]]
    new_lines = [ln for i, ln in enumerate(lines) if i not in archive_idxs]
    new_section = "\n".join(new_lines)
    new_text = queue_text[:after_hdr] + new_section + queue_text[end:]
    return new_text, archived_rows


def _append_harvest_archive(rows: list[str], ts_now: datetime) -> None:
    """Append pruned catalogue rows verbatim to the harvest archive (audit trail)."""
    if not rows:
        return
    if QUEUE_HARVEST_ARCHIVE_PATH.exists():
        existing = QUEUE_HARVEST_ARCHIVE_PATH.read_text(encoding="utf-8")
    else:
        existing = (
            "# Harvested-from-gym catalogue archive\n\n"
            "> Overflow rows pruned from `queue.md` `## HARVESTED-FROM-GYM` by the "
            "`gym_harvester` retention cap (OP-22 compound-don't-accumulate). "
            "Verbatim, append-only audit trail. The deterministic "
            "`EDGE_REGRESSION_FAIL` (CRITICAL) class is never pruned here.\n"
        )
    header = (
        f"\n## Archived {ts_now.strftime('%Y-%m-%d %H:%M:%SZ')} — "
        f"{len(rows)} catalogue row(s) over cap ({HARVESTED_SECTION_CAP})\n\n"
    )
    body = "\n".join(rows) + "\n"
    QUEUE_HARVEST_ARCHIVE_PATH.write_text(existing + header + body, encoding="utf-8")


# -- Main orchestration -------------------------------------------------------
def harvest(hours: int = 24, dry_run: bool = False) -> HarvestStats:
    """Run one harvest pass. Returns stats; appends to queue.md unless dry_run."""
    stats = HarvestStats()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    candidates: list[Candidate] = []

    # 1) Grinder iterations: foot-gun + RSI extreme + regime extreme + breakout cluster.
    #    v02 source-disagreement detector is a no-op (KNOWN_FLAKY_LIVE_SOURCE carve-out).
    #    v09 + v11 detectors added 2026-05-19 after grinder expanded to cover v01-v25.
    try:
        for rec in _tail_jsonl_since(GRINDER_PATH, cutoff):
            stats.candidates_scanned += 1
            if (c := _detect_foot_gun(rec)) is not None:
                candidates.append(c)
            candidates.extend(_detect_source_disagreement(rec))
            if (c := _detect_rsi_extreme(rec)) is not None:
                candidates.append(c)
            if (c := _detect_regime_extreme(rec)) is not None:
                candidates.append(c)
            if (c := _detect_breakout_cluster(rec)) is not None:
                candidates.append(c)
    except OSError as e:
        stats.errors.append(f"grinder.jsonl read error: {e}")

    # 2) Regression history: overall_pass=false (CRITICAL).
    try:
        for rec in _tail_jsonl_since(HISTORY_PATH, cutoff):
            stats.candidates_scanned += 1
            if (c := _detect_regression_fail(rec)) is not None:
                candidates.append(c)
    except OSError as e:
        stats.errors.append(f"history.jsonl read error: {e}")

    # 3) latest.json snapshot: v07 volume / v08 ribbon / v14 sweep / v15 three-way.
    #    These live in latest.json's `runs[]` array from the regression runner.
    #    grinder.jsonl now carries v01-v25 results per iteration (expanded 2026-05-19)
    #    but we still harvest v07/v08/v14 edge-cases from latest.json for the regime-
    #    aware detectors below — they need the `status_distribution` and `examples`
    #    fields that runner.py populates but grinder.jsonl compresses. One observation
    #    per harvester fire; regression task rewrites latest.json every 30 min.
    latest = _load_latest_json()
    if latest is not None:
        stats.candidates_scanned += 1
        if (c := _detect_volume_spike_from_latest(latest)) is not None:
            candidates.append(c)
        if (c := _detect_ribbon_flip_from_latest(latest)) is not None:
            candidates.append(c)
        candidates.extend(_detect_sweep_from_latest(latest))
        candidates.extend(_detect_three_source_disagreement_from_latest(latest))

    # Dedup phase 1: seen-keys persistence (across harvester fires).
    seen_keys_list = _load_seen_keys()
    seen_keys = set(seen_keys_list)

    # Dedup phase 2: existing queue.md rows (catches the case where seen-keys
    # file was wiped but queue still has the rows).
    queue_text = QUEUE_PATH.read_text(encoding="utf-8") if QUEUE_PATH.exists() else ""
    original_queue_text = queue_text
    existing_queue_keys = _extract_existing_keys_from_queue(queue_text)

    new_candidates: list[Candidate] = []
    intra_batch_keys: set[str] = set()
    for c in candidates:
        if c.key in seen_keys:
            stats.candidates_skipped_dup += 1
            continue
        if c.key in existing_queue_keys:
            stats.candidates_skipped_already_in_queue += 1
            seen_keys_list.append(c.key)  # backfill into seen-keys
            continue
        if c.key in intra_batch_keys:
            # Two records in the same harvest pass produced the same key
            # (e.g., two grinder iterations both catching the foot-gun on the
            # same bar boundary). Collapse to one row.
            stats.candidates_skipped_dup += 1
            continue
        intra_batch_keys.add(c.key)
        new_candidates.append(c)
        stats.candidates_new += 1
        stats.by_rule[c.rule] = stats.by_rule.get(c.rule, 0) + 1

    if dry_run:
        return stats

    # Append rows to queue.md. CRITICAL items get their own section; everything
    # else lands under HARVESTED-FROM-GYM.
    if new_candidates:
        ts_now = datetime.now(timezone.utc)
        crit_cands = [c for c in new_candidates if c.priority == "CRIT"]
        other_cands = [c for c in new_candidates if c.priority != "CRIT"]

        # Insert CRITICAL rows first so their timestamps are most recent.
        if crit_cands:
            queue_text, ins_idx = _ensure_critical_section(queue_text)
            # Add a small monotonic offset to timestamps so two crit rows in
            # the same second still get distinct IDs.
            block = []
            for i, c in enumerate(crit_cands):
                row = _format_queue_row(c, ts_now + timedelta(seconds=i))
                block.append(row)
            block_text = "\n".join(block) + "\n"
            queue_text = queue_text[:ins_idx] + block_text + queue_text[ins_idx:]
            stats.candidates_appended_to_queue += len(crit_cands)
            for c in crit_cands:
                seen_keys_list.append(c.key)

        if other_cands:
            queue_text, ins_idx = _ensure_harvested_section(queue_text)
            block = []
            for i, c in enumerate(other_cands):
                # Offset by len(crit) + i so ids stay unique within the fire.
                offset = len(crit_cands) + i
                row = _format_queue_row(c, ts_now + timedelta(seconds=offset))
                block.append(row)
            block_text = "\n".join(block) + "\n"
            queue_text = queue_text[:ins_idx] + block_text + queue_text[ins_idx:]
            stats.candidates_appended_to_queue += len(other_cands)
            for c in other_cands:
                seen_keys_list.append(c.key)

    # Enforce the retention cap on the informational catalogue section every run
    # (self-heals an already-overflowing section even when 0 new candidates were
    # appended this fire). The CRITICAL section is a separate section and untouched.
    queue_text, archived_rows = _prune_harvested_section(queue_text, HARVESTED_SECTION_CAP)
    if archived_rows:
        _append_harvest_archive(archived_rows, datetime.now(timezone.utc))
        stats.candidates_archived = len(archived_rows)

    if queue_text != original_queue_text:
        QUEUE_PATH.write_text(queue_text, encoding="utf-8")

    _save_seen_keys(seen_keys_list)

    # Run-state ledger (cursor + log line).
    state = _load_state()
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    state["last_run_hours_window"] = hours
    state["last_run_stats"] = {
        "candidates_scanned": stats.candidates_scanned,
        "candidates_new": stats.candidates_new,
        "candidates_appended_to_queue": stats.candidates_appended_to_queue,
        "candidates_skipped_dup": stats.candidates_skipped_dup,
        "candidates_skipped_already_in_queue": stats.candidates_skipped_already_in_queue,
        "candidates_archived": stats.candidates_archived,
        "by_rule": stats.by_rule,
    }
    _save_state(state)

    # Append per-fire log row.
    log_row = {
        "run_at": state["last_run_at"],
        "hours_window": hours,
        "candidates_scanned": stats.candidates_scanned,
        "candidates_new": stats.candidates_new,
        "candidates_appended_to_queue": stats.candidates_appended_to_queue,
        "candidates_skipped_dup": stats.candidates_skipped_dup,
        "candidates_skipped_already_in_queue": stats.candidates_skipped_already_in_queue,
        "candidates_archived": stats.candidates_archived,
        "by_rule": stats.by_rule,
        "errors": stats.errors,
    }
    with HARVESTER_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_row) + "\n")

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crypto gym harvester")
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Tail window in hours over grinder.jsonl + history.jsonl (default 24)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be appended without writing to queue.md",
    )
    args = parser.parse_args(argv)

    try:
        stats = harvest(hours=args.hours, dry_run=args.dry_run)
    except OSError as e:
        print(f"gym_harvester I/O error: {e}", file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError) as e:
        print(f"gym_harvester parse error: {e}", file=sys.stderr)
        return 1

    print(json.dumps({
        "dry_run": args.dry_run,
        "hours": args.hours,
        "candidates_scanned": stats.candidates_scanned,
        "candidates_new": stats.candidates_new,
        "candidates_appended_to_queue": stats.candidates_appended_to_queue,
        "candidates_skipped_dup": stats.candidates_skipped_dup,
        "candidates_skipped_already_in_queue": stats.candidates_skipped_already_in_queue,
        "candidates_archived": stats.candidates_archived,
        "by_rule": stats.by_rule,
        "errors": stats.errors,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
