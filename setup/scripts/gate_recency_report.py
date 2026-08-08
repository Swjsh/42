"""gate_recency_report.py -- THE GATE-RECENCY WEEKLY INSTRUMENT (J directive 2026-08-08:
turn the gate-recency audit that found money-blocking stale gates into PERMANENT DOCTRINE +
a STANDING INSTRUMENT, not a one-off).

THE GAP THIS CLOSES: analysis/recommendations/gate-recency-audit-2026-08-08.{md,json} was a
manual, one-shot audit. It found real money-blocking staleness the existing nightly checker
(backtest/autoresearch/gate_expiry_check.py, Gamma_GateExpiryCheck) structurally cannot see on
its own -- gate_expiry_check.py only mines backtest/lib/engine/gates.py's GATE_ORDER + two named
vetoes + fleet config (per its own _NOT_MEASURED_CATEGORIES and category dispatch in
check_gate()). The scoring-filter layer (backtest/lib/filters.py's numbered filters), the
extra-setup lane (extra_setup_exec_armed), and risk_gate config modes (pdt_gate_mode) are
OUTSIDE that instrument's scope by design. Nobody was re-running the broader audit, so its
findings would have rotted the same way block_elite_bull's 2026-07-10 verdict rotted for 21
days before the 2026-07-31 scar. This script is the fix: a cheap, dependency-light, WEEKLY
re-run of the same broader census, so REVALIDATE/RED gates stay visible on a standing cadence.

WHAT THIS IS NOT: it does NOT re-run gate_expiry_check.py's real-OPRA-fills P&L replay (that
stays the nightly job's exclusive responsibility -- re-simulating it here would duplicate a
multi-minute pandas+OPRA-cache job on a script meant to be cheap and dependency-free). Instead
this script MERGES three cheap, already-available sources:
  (a) automation/state/gate-registry-status.json -- the nightly checker's own RED/YELLOW/GREEN/
      STALE_UNVERIFIED P&L verdicts (read, never recomputed).
  (b) A FRESH decisions.jsonl BLOCK-COUNT pass (raw tick counts, no $ simulation) over the
      trailing 15 distinct armed=true trading days -- the exact method
      gate-recency-audit-2026-08-08.json's "methodology"/"blocks_last_15d.method" fields
      document per gate (sole-blocker attribution for the scoring-filter layer, detector-fired
      for the extra-setup lane, verdict/action equality for GATE_ORDER gates + vetoes +
      risk_gate config modes).
  (c) automation/state/gate-registry.json's provenance dates (last_revalidated,
      revalidation_interval_days) where a gate has a registry row; a hardcoded fallback ported
      from the 2026-08-08 audit for the gates the registry doesn't cover at all (the scoring
      filters, the extra-setup lane, pdt_gate_mode, the two confirmed-dead params bundles).

DEPENDENCY-LIGHT BY DESIGN: pure stdlib (json/pathlib/datetime/argparse) plus the local
et_clock module -- NO pandas, NO OPRA cache, NO lib.simulator_real. This is a deliberate
choice: a "keeps running forever" weekly instrument should have as few ways to break as
possible. Runs fine under system Python; does not require the backtest venv.

NEVER BLOCKS, NEVER KILLS, NEVER AUTO-DISARMS, NEVER WRITES params.json/aggressive/params.json.
Pure report, exactly like gate_expiry_check.py's own "arming/disarming stays a human decision"
rule (OP-16). Fail-open PER SOURCE: a missing/malformed gate-registry.json, gate-registry-
status.json, params.json, or core-decisions.jsonl each independently degrades to a safe empty
default for THAT source only -- never crashes the run, never poisons another source's rows.
Empty-input-safe: with every input source missing, this still writes a valid, schema-complete
report (all gates show blocks_15d=0, expiry_verdict="NOT_IN_EXPIRY_CHECKER" or whatever the
per-source default is) rather than raising.

Output: automation/state/gate-recency-latest.json --
  {generated_et, window, gates:[{name, account, setting, last_validated, days_stale,
   blocks_15d, expiry_verdict, staleness_score, recommendation, category, provenance,
   red_ev_note}], reds:[{name, account, reason}], digest:[<=3 plain-English lines]}
Schema is STABLE (fixed key set on every row) -- a future consumer (a standup, a wants-surface,
gamma_standup.py-style) can key off these fields without special-casing missing ones.

RULE this instrument exists to enforce (see markdown/doctrine/GATE-RECENCY-DOCTRINE.md): any
gate RED on this report for more than 7 days without a filed revalidation pre-reg is a doctrine
violation to flag in standups. This script does not itself check the 7-day clock (it has no
memory of its own prior runs beyond what it overwrites each week) -- that comparison belongs to
whatever reads gate-recency-latest.json over time (a standup, STATUS.md, or a future dedicated
check); this script's job is to make sure the RED verdict is never more than a week stale.

Run:
  backtest/.venv/Scripts/python.exe setup/scripts/gate_recency_report.py [--dry-run]
    [--lookback-days N]
  (or any Python 3.10+ interpreter -- no third-party deps)
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, copied verbatim from
# gate_expiry_check.py / gamma_standup.py). When launched via pythonw.exe (no console),
# Windows 11's default-terminal setting can allocate a visible window on the FIRST
# stdout/stderr write. Redirect to log files BEFORE any other import gets a chance to write.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "gate-recency-report.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "gate-recency-report.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
GATE_REGISTRY = STATE / "gate-registry.json"
GATE_REGISTRY_STATUS = STATE / "gate-registry-status.json"
PARAMS_SAFE = STATE / "params.json"
PARAMS_BOLD = STATE / "aggressive" / "params.json"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
OUT_JSON = STATE / "gate-recency-latest.json"

# Matches gate-recency-audit-2026-08-08.json's recent_window.definition exactly: "last 15
# distinct calendar dates present in core-decisions.jsonl, armed=true rows only".
TRAILING_TRADING_DAYS = 15

# Used only when NEITHER the registry NOR the audit-ported fallback gives a usable date --
# matches gate-recency-audit-2026-08-08.json's own "UNKNOWN provenance uses a 180-day proxy"
# convention verbatim.
UNKNOWN_PROVENANCE_PROXY_DAYS = 180


# ─────────────────────────────────────────────────────────────────────────────────────
# GATE ROSTER -- ported from gate-recency-audit-2026-08-08.json's 17-row ranked table.
# Each entry: which decisions.jsonl field/value proves a refusal ("count_rule"), which
# accounts to track, a fallback display setting + fallback provenance date (used only when
# the live source doesn't have it), and any special-cased recommendation.
#
# count_rule kinds:
#   field_equals  -- row[field] == value                    (GATE_ORDER gates, vetoes, risk_gate config)
#   sole_blocker  -- row[field] == [index] exactly           (scoring-filter layer)
#   extra_fired   -- extra_signals[] has setup_name w/ fired==true   (extra-setup lane)
#   fixed_zero    -- structurally cannot fire (confirmed-dead params bundles)
#
# provenance: gates present in gate-registry.json get their last_revalidated /
# revalidation_interval_days from there LIVE each run (J can keep re-validating gates without
# ever touching this script). Gates outside the registry's scope (the scoring filters, the
# extra-setup lane, pdt_gate_mode, the two dead bundles) use the audit_last_validated /
# audit_interval_days fallback below, ported verbatim from gate-recency-audit-2026-08-08.json.
# ─────────────────────────────────────────────────────────────────────────────────────

GATE_ROSTER: list[dict[str, Any]] = [
    # ---- gates WITH a gate-registry.json row (provenance dates read live from there) -----
    {
        "id": "block_level_rejection",
        "category": "core_gate_order",
        "params_key": "block_level_rejection",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_LEVEL_REJECTION_GATE"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": True},
        "audit_last_validated": "2026-06-17",
        "audit_interval_days": 21,
    },
    {
        "id": "block_bull_1100_1200",
        "category": "core_gate_order",
        "params_key": "block_bull_1100_1200",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_BULL_1100_1200"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": True},
        "audit_last_validated": "2026-06-18",
        "audit_interval_days": 21,
    },
    {
        "id": "require_bearish_fill_bar",
        "category": "core_gate_order",
        "params_key": "require_bearish_fill_bar",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"},
        "accounts": {"safe": False, "bold": True},
        "setting_fallback": {"bold": True},
        "audit_last_validated": "2026-06-17",
        "audit_interval_days": 21,
    },
    {
        "id": "block_conf_lvl_rec_afternoon",
        "category": "core_gate_order",
        "params_key": "block_conf_lvl_rec_afternoon",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_CONF_LVL_REC_AFTERNOON"},
        "accounts": {"safe": False, "bold": True},
        "setting_fallback": {"bold": True},
        "audit_last_validated": "2026-06-18",
        "audit_interval_days": 21,
    },
    {
        "id": "structure_veto_enabled",
        "category": "non_gate_order_veto",
        "params_key": "structure_veto_enabled",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_STRUCTURE_VETO"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": True},
        "audit_last_validated": "2026-06-26",
        "audit_interval_days": 21,
    },
    {
        "id": "free_model_veto",
        "category": "non_gate_order_veto",
        "params_key": None,
        "count_rule": {"kind": "field_equals", "field": "action", "value": "VETOED_BY_MODELS"},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": True, "bold": True},
        "audit_last_validated": "2026-07-09",
        "audit_interval_days": 30,
    },
    {
        "id": "entry_bar_body_pct_min",
        "category": "core_gate_order",
        "params_key": "entry_bar_body_pct_min",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_DOJI_ENTRY_BAR"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": 0.2},
        "audit_last_validated": "2026-06-18",
        "audit_interval_days": 21,
    },
    {
        "id": "block_elite_bull",
        "category": "core_gate_order",
        "params_key": "block_elite_bull",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_ELITE_BULL_LEVEL_RECLAIM"},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": False, "bold": False},
        "audit_last_validated": "2026-08-03",
        "audit_interval_days": 14,
        # FLAGSHIP scar gate (2026-07-31): currently disarmed for an active trade-to-learn
        # trial with its own pre-committed kill criterion (gate-registry.json). This report
        # is not the trial's kill-clock -- it just keeps the row visible, always KEEP/MONITOR.
        "force_recommendation": "KEEP-MONITOR-TRIAL",
    },
    {
        "id": "vix_bear_hard_cap",
        "category": "core_gate_order",
        "params_key": "vix_bear_hard_cap",
        "count_rule": {"kind": "field_equals", "field": "verdict", "value": "SKIP_VIX_BEAR_HIGH"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": 23.0},
        "audit_last_validated": "2026-06-18",
        "audit_interval_days": 21,
    },
    # ---- gate WITHOUT a registry row (audit-ported provenance fallback used directly) -----
    {
        "id": "min_entry_premium",
        "category": "risk_gate_config",
        "params_key": "min_entry_premium",
        "count_rule": {"kind": "field_equals", "field": "action", "value": "SKIP_MIN_PREMIUM_FLOOR"},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": 0.3, "bold": 0.3},
        "audit_last_validated": "2026-07-31",
        "audit_interval_days": 21,
    },
    # ---- scoring-filter layer (backtest/lib/filters.py) -- OUTSIDE gate-registry.json AND
    # OUTSIDE gate_expiry_check.py's scope entirely; this report is the only place these are
    # tracked on a recurring cadence. ----
    {
        "id": "filter_10_min_triggers_bull",
        "category": "scoring_filter",
        "params_key": "filter_10_min_triggers_bull",
        "count_rule": {"kind": "sole_blocker", "field": "bull_blockers", "index": 11},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": 2, "bold": 1},
        "audit_last_validated": None,  # UNKNOWN provenance per the audit -- proxy applies
        "audit_interval_days": 21,
    },
    {
        "id": "filter_9_vol_multiplier",
        "category": "scoring_filter",
        "params_key": "filter_9_vol_multiplier",
        "count_rule": {"kind": "sole_blocker", "field": "bear_blockers", "index": 9},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": 0.7, "bold": 0.7},
        "audit_last_validated": None,  # v11-era, no dated post-v15 scorecard -- proxy applies
        "audit_interval_days": 21,
    },
    # ---- extra-setup lane (automation/state/params.json extra_setup_exec_armed dict) -----
    {
        "id": "extra_setup_exec_armed.vwap_continuation",
        "category": "extra_setup_gate",
        "params_key": "extra_setup_exec_armed",
        "nested_key": "vwap_continuation",
        "count_rule": {"kind": "extra_fired", "setup_name": "vwap_continuation"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": False},
        "audit_last_validated": "2026-07-25",
        "audit_interval_days": 14,
    },
    {
        "id": "extra_setup_exec_armed.vix_regime_dayside",
        "category": "extra_setup_gate",
        "params_key": "extra_setup_exec_armed",
        "nested_key": "vix_regime_dayside",
        "count_rule": {"kind": "extra_fired", "setup_name": "vix_regime_dayside"},
        "accounts": {"safe": True, "bold": False},
        "setting_fallback": {"safe": False},
        "audit_last_validated": "2026-07-25",
        "audit_interval_days": 14,
    },
    # ---- risk_gate config mode -- the audit's #1 dollar-quantified finding -----
    {
        "id": "pdt_gate_mode",
        "category": "risk_gate_config",
        "params_key": "pdt_gate_mode",
        "count_rule": {"kind": "field_equals", "field": "action", "value": "RISK_DENY_PDT"},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": "cash_settlement", "bold": "margin_pdt"},
        "audit_last_validated": "2026-08-06",
        "audit_interval_days": 21,
        # Only escalate to the action-needed label while it is actually blocking something --
        # if it stops firing this correctly falls back through to REVALIDATE/KEEP like any
        # other row instead of getting stuck on a permanent special case.
        "force_if_blocked": "ACT-ON-PENDING-DECISION",
    },
    # ---- confirmed-dead params bundles -- zero code consumers, cannot fire, false-confidence
    # risk rather than a $ risk. Tracked here so RETIRE-CANDIDATE stays visible weekly instead
    # of only existing in one dated audit file. ----
    {
        "id": "liquidity_gate_bundle",
        "category": "dead_config",
        "params_key": None,
        "count_rule": {"kind": "fixed_zero"},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": "6-key bundle, 0 code consumers", "bold": "0 code consumers"},
        "audit_last_validated": None,
        "audit_interval_days": None,
    },
    {
        "id": "macro_veto_bundle",
        "category": "dead_config",
        "params_key": None,
        "count_rule": {"kind": "fixed_zero"},
        "accounts": {"safe": True, "bold": True},
        "setting_fallback": {"safe": "4-key bundle, 0 code consumers", "bold": "0 code consumers"},
        "audit_last_validated": None,
        "audit_interval_days": None,
    },
]


# ─────────────────────────────────────────────────────────────────────────────────────
# Fail-open loaders -- each source degrades independently, never raises.
# ─────────────────────────────────────────────────────────────────────────────────────

def load_registry() -> dict:
    try:
        doc = json.loads(GATE_REGISTRY.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"gates": []}
    except (OSError, ValueError):
        return {"gates": []}


def load_status() -> dict:
    try:
        doc = json.loads(GATE_REGISTRY_STATUS.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"gates": {}}
    except (OSError, ValueError):
        return {"gates": {}}


def load_params() -> dict[str, dict]:
    """{'safe': <params.json dict or {}>, 'bold': <aggressive/params.json dict or {}>}."""
    out: dict[str, dict] = {}
    for account, path in (("safe", PARAMS_SAFE), ("bold", PARAMS_BOLD)):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            out[account] = doc if isinstance(doc, dict) else {}
        except (OSError, ValueError):
            out[account] = {}
    return out


def load_window_rows(path: Path, n_days: int) -> tuple[list[dict], list[str]]:
    """Stream core-decisions.jsonl once; return (armed=true rows within the trailing n_days
    distinct armed=true trading days, that sorted list of dates). Matches gate-recency-audit-
    2026-08-08.json's recent_window.definition exactly. Fail-open: unparseable lines are
    skipped, a missing/unreadable file returns ([], [])."""
    if n_days <= 0 or not path.exists():
        return [], []
    all_rows: list[dict] = []
    armed_dates: set[str] = set()
    try:
        fh = path.open(encoding="utf-8")
    except OSError:
        return [], []
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(r, dict):
                continue
            ts = r.get("ts_et")
            if not isinstance(ts, str) or len(ts) < 10:
                continue
            all_rows.append(r)
            if r.get("armed") is True:
                armed_dates.add(ts[:10])
    if not armed_dates:
        return [], []
    last_n = sorted(armed_dates)[-n_days:]
    start, end = last_n[0], last_n[-1]
    window_rows = [
        r for r in all_rows
        if r.get("armed") is True and start <= (r.get("ts_et") or "")[:10] <= end
    ]
    return window_rows, last_n


# ─────────────────────────────────────────────────────────────────────────────────────
# Block-count mining -- pure in-memory filtering over the already-loaded window rows.
# ─────────────────────────────────────────────────────────────────────────────────────

def _matches(row: dict, account: str, rule: dict) -> bool:
    if row.get("account") != account:
        return False
    kind = rule["kind"]
    if kind == "field_equals":
        return row.get(rule["field"]) == rule["value"]
    if kind == "sole_blocker":
        return row.get(rule["field"]) == [rule["index"]]
    if kind == "extra_fired":
        for sig in (row.get("extra_signals") or []):
            if isinstance(sig, dict) and sig.get("setup_name") == rule["setup_name"] and sig.get("fired") is True:
                return True
        return False
    return False


def count_blocks(rows: list[dict], account: str, rule: dict) -> int:
    if rule.get("kind") == "fixed_zero":
        return 0
    return sum(1 for r in rows if _matches(r, account, rule))


# ─────────────────────────────────────────────────────────────────────────────────────
# Provenance + setting resolution
# ─────────────────────────────────────────────────────────────────────────────────────

def _live_setting(params_by_account: dict, account: str, params_key: Optional[str],
                   nested_key: Optional[str], fallback: Any) -> Any:
    acct_params = params_by_account.get(account) or {}
    if not params_key or params_key not in acct_params:
        return fallback
    val = acct_params[params_key]
    if nested_key:
        if isinstance(val, dict) and nested_key in val:
            return val[nested_key]
        return fallback
    return val


def _days_stale(last_validated: Optional[str], today: dt.date) -> Optional[int]:
    if not last_validated or len(last_validated) < 10:
        return None
    try:
        d = dt.date.fromisoformat(last_validated[:10])
    except ValueError:
        return None
    return (today - d).days


def _recommend(spec: dict, expiry_verdict: str, blocks: int, days_stale: Optional[int],
                interval_days: Optional[int]) -> str:
    if spec["category"] == "dead_config":
        return "RETIRE-CANDIDATE"
    if spec.get("force_recommendation"):
        return spec["force_recommendation"]
    if blocks > 0 and spec.get("force_if_blocked"):
        return spec["force_if_blocked"]
    if blocks == 0:
        return "KEEP"
    if expiry_verdict == "RED":
        return "REVALIDATE"
    if interval_days is not None and days_stale is not None and days_stale > interval_days:
        return "REVALIDATE"
    return "KEEP"


# ─────────────────────────────────────────────────────────────────────────────────────
# Row assembly
# ─────────────────────────────────────────────────────────────────────────────────────

def build_rows(roster: list[dict], registry_by_id: dict, status_by_id: dict, params: dict,
                window_rows: list[dict], today: dt.date) -> list[dict]:
    out: list[dict] = []
    for spec in roster:
        gate_id = spec["id"]
        reg = registry_by_id.get(gate_id)
        status = status_by_id.get(gate_id)

        for account, tracked in spec["accounts"].items():
            if not tracked:
                continue

            setting = _live_setting(
                params, account, spec.get("params_key"), spec.get("nested_key"),
                spec["setting_fallback"].get(account),
            )

            last_validated: Optional[str] = None
            interval_days = spec.get("audit_interval_days")
            provenance = "audit_2026-08-08"
            if isinstance(reg, dict):
                lr = reg.get("last_revalidated")
                if isinstance(lr, str) and len(lr) >= 10:
                    last_validated = lr[:10]
                    provenance = "registry"
                if reg.get("revalidation_interval_days") is not None:
                    interval_days = reg["revalidation_interval_days"]
            if last_validated is None and spec.get("audit_last_validated"):
                last_validated = spec["audit_last_validated"]
                provenance = "audit_2026-08-08"

            days_stale = _days_stale(last_validated, today)
            if days_stale is None:
                days_stale = UNKNOWN_PROVENANCE_PROXY_DAYS
                provenance = "unknown_180d_proxy"

            blocks = count_blocks(window_rows, account, spec["count_rule"])
            staleness_score = days_stale * blocks

            if isinstance(status, dict):
                expiry_verdict = status.get("overall", "NOT_IN_EXPIRY_CHECKER")
                pnl_check = status.get("pnl_check") or {}
                red_ev_note = pnl_check.get("reason") if expiry_verdict == "RED" else None
            else:
                expiry_verdict = "NOT_IN_EXPIRY_CHECKER"
                red_ev_note = None

            recommendation = _recommend(spec, expiry_verdict, blocks, days_stale, interval_days)

            out.append({
                "name": gate_id,
                "account": account,
                "setting": setting,
                "last_validated": last_validated,
                "days_stale": days_stale,
                "blocks_15d": blocks,
                "expiry_verdict": expiry_verdict,
                "staleness_score": staleness_score,
                "recommendation": recommendation,
                "category": spec["category"],
                "provenance": provenance,
                "red_ev_note": red_ev_note,
            })
    return out


def build_digest(rows: list[dict], max_lines: int = 3) -> list[str]:
    """<=max_lines plain-English lines: every RED gate + its refused-cohort EV first, then
    (if room remains) the highest-staleness REVALIDATE/ACT-ON-PENDING-DECISION rows not
    already a RED gate. Never empty -- a quiet week still gets one reassuring line."""
    reds = [r for r in rows if r["expiry_verdict"] == "RED"]
    lines: list[str] = []
    for r in reds:
        if len(lines) >= max_lines:
            break
        note = r.get("red_ev_note") or "refused cohort reads positive on recent real fills"
        lines.append(f"RED -- {r['name']} ({r['account']}): {note}")

    if len(lines) < max_lines:
        watch = [
            r for r in rows
            if r["expiry_verdict"] != "RED" and r["recommendation"] in ("REVALIDATE", "ACT-ON-PENDING-DECISION")
        ]
        watch.sort(key=lambda r: r["staleness_score"], reverse=True)
        for r in watch:
            if len(lines) >= max_lines:
                break
            lines.append(
                f"WATCH -- {r['name']} ({r['account']}): {r['blocks_15d']} block(s)/15d, "
                f"{r['days_stale']}d since last validation, recommendation={r['recommendation']}"
            )

    if not lines:
        lines.append("No RED gates and nothing newly flagged for revalidation this run.")
    return lines[:max_lines]


# ─────────────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────────────

def build_report(lookback_days: int = TRAILING_TRADING_DAYS,
                  today: Optional[dt.date] = None) -> dict:
    """Pure assembly (no I/O side effects beyond the input reads) -- the seam tests call
    directly with monkeypatched module Path constants."""
    today = today or et_now().date()
    registry = load_registry()
    status = load_status()
    params = load_params()
    window_rows, window_dates = load_window_rows(CORE_DECISIONS, lookback_days)

    registry_by_id = {
        g["id"]: g for g in registry.get("gates", []) if isinstance(g, dict) and g.get("id")
    }
    status_gates = status.get("gates")
    status_by_id = status_gates if isinstance(status_gates, dict) else {}

    rows = build_rows(GATE_ROSTER, registry_by_id, status_by_id, params, window_rows, today)
    reds = [
        {"name": r["name"], "account": r["account"], "reason": r["red_ev_note"]}
        for r in rows if r["expiry_verdict"] == "RED"
    ]
    digest = build_digest(rows)

    return {
        "schema": "gate-recency-report-v1",
        "generated_et": et_now().isoformat(timespec="seconds"),
        "window": {
            "trailing_trading_days_requested": lookback_days,
            "distinct_armed_dates_found": len(window_dates),
            "start": window_dates[0] if window_dates else None,
            "end": window_dates[-1] if window_dates else None,
        },
        "gates": rows,
        "reds": reds,
        "digest": digest,
    }


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Weekly deterministic gate-recency instrument (J directive 2026-07-31 / "
                     "2026-08-08): merges the nightly gate-expiry P&L verdicts with a fresh "
                     "15-trading-day block-count pass so REVALIDATE/RED gates stay visible on "
                     "a standing weekly cadence, not just a one-off audit."
    )
    ap.add_argument("--dry-run", action="store_true", help="print only -- no file write")
    ap.add_argument("--lookback-days", type=int, default=TRAILING_TRADING_DAYS,
                     help="trailing distinct armed=true trading days to mine (default 15, "
                          "matches the 2026-08-08 audit)")
    args = ap.parse_args(argv)

    out = build_report(lookback_days=args.lookback_days)

    w = out["window"]
    print(f"[gate-recency] window {w['start']}..{w['end']} "
          f"({w['distinct_armed_dates_found']} armed trading day(s) found), "
          f"{len(out['gates'])} gate/account row(s), {len(out['reds'])} RED")
    for line in out["digest"]:
        print(f"[gate-recency] {line}")

    if args.dry_run:
        print("\n[gate-recency] --dry-run: no file written\n")
        print(json.dumps(out, indent=2))
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_JSON.with_suffix(OUT_JSON.suffix + ".tmp")
    tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
    tmp.replace(OUT_JSON)
    print(f"\n[gate-recency] wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
