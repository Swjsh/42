"""params.json <-> live-consumer RECONCILIATION RATCHET (PARAMS-CONSUMER-RECONCILE-TEST,
2026-07-02).

WHY THIS EXISTS (audit break #7, markdown/audits/PIPELINE-AUDIT-2026-07-01.md):
dozens of ratified params.json keys silently have NO live reader -- the C14 dead-knob
class. A dead knob is a lie: the doc says the value is authoritative, but changing it
changes nothing. The concrete bite that motivated this guard: ``entry_no_trade_after_et``
was NOT consumed on the placement path, so 10 late ENTER_BEARs on 2026-07-01 all hit
PLACE_FAIL after the 15:00 ceiling should have blocked them; Bold premium stops -7%/-5%
were hardcoded -50%; ``v15_profit_lock_mode`` etc. were flagged silently ignored.

The EXISTING coverage (``test_params_filters_drift.py`` + ``v25_filter_gates`` presence
guard) only covers the GATE/threshold family (``block_*`` / ``*_gate`` / ``*_min`` /
``*_hard_cap`` / ``*_required``) against the HEARTBEAT PROSE. That is a narrow slice.
This ratchet is BROADER: it asserts EVERY ratified (non-underscore, non-metadata) key in
the canonical Safe ``params.json`` is referenced by NAME somewhere in the live consumer
surface (executable code + live prompts + installers), NOT just the gate family and NOT
just the heartbeat.

RATCHET SEMANTICS (same shape as ``test_validated_setups_enabled.py`` KNOWN_UNMONITORED
and the OP-25 index reconciliation baseline):
  1. ``test_no_new_dead_params_knob`` -- the set of dead knobs MUST be a subset of the
     documented ``KNOWN_DEAD`` allowlist. A NEWLY-ratified-but-unwired key trips this
     LOUD, at build time, before it can silently mis-steer the money path.
  2. ``test_known_dead_allowlist_shrinks_only`` -- every KNOWN_DEAD key must STILL be
     dead. The moment a key gains a real consumer, it must be REMOVED from the allowlist
     (the ratchet can only shrink). This is how "restore-or-remove each dead key"
     graduates from a to-do into an enforced obligation.
  3. ``test_known_dead_keys_exist_in_params`` -- hygiene: no stale allowlist entry for a
     key that was already removed from params.json.
  4. ``test_bite_synthetic_dead_knob_is_detected`` -- NON-VACUOUS bite: an injected fake
     knob that no code references IS flagged dead (proves the detector isn't hardwired to
     pass). Plus a live-key control that a genuinely-consumed key is NOT flagged.

Pure static text scan -- no backtest, no network. Anchored to the repo root via __file__
(L21/L42/L49). The archived params snapshots under ``analysis/backtests/*/metadata.json``
are DELIBERATELY NOT in the corpus -- they are frozen copies of params.json, not
consumers; including them would falsely "revive" every dead knob.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PARAMS_PATH = _REPO / "automation" / "state" / "params.json"

# Non-underscore keys that are documentation / metadata STRINGS, not tunable knobs.
# (Underscore-prefixed keys are all _doc / _section / history and are excluded by rule.)
_METADATA_KEYS = {
    "schema_version",
    "rule_version",
    "rule_version_ratified_at",
    "rule_version_v15_3_notes",
    "rule_version_v15_2_notes",
    "rule_version_notes",
    "rule_version_revert_command",
    "v15_ratification_status",
    "v15_hard_gate_logic",
    "v15_profit_lock_decision_data",
}

# The LIVE consumer surface: executable code + live prompts + task installers. A knob is
# "consumed" iff its exact name appears (word-boundary) in this corpus. Excludes tests,
# the worktree duplicate, and the archived params snapshots (not consumers).
_CONSUMER_GLOBS = [
    ("setup/scripts", "*.py"),
    ("setup", "*.py"),
    ("setup", "*.ps1"),
    ("backtest/lib", "**/*.py"),
    ("backtest/autoresearch", "*.py"),
    ("automation/scripts", "*.py"),
    ("crypto/validators", "*.py"),
    ("automation/prompts", "*.md"),
]

# ── The documented dead-knob allowlist (SHRINKS-ONLY). ────────────────────────
# Each key is ratified in params.json but has NO live reader as of 2026-07-02. The tag is
# the disposition owed (RESTORE = wire a consumer; REMOVE = delete the key). Tracked as
# follow-up under PARAMS-CONSUMER-RECONCILE-TEST in queue.md. Removing an entry here is
# only legal once the key is either wired (test 2 forces it) or deleted from params.
KNOWN_DEAD: dict[str, str] = {
    # Scheduler cadence / session-timing: the authoritative consumer is the Windows
    # scheduled-task trigger, which hardcodes the time -- the key is documentation of
    # intent, not a read value. RESTORE (read from params at install) or REMOVE.
    "heartbeat_interval_minutes": "scheduler cadence; task trigger hardcodes 3 (RESTORE-or-REMOVE)",
    "eod_flatten_et": "session-timing; Gamma_EodFlatten trigger hardcodes 15:55 (RESTORE-or-REMOVE)",
    "eod_summary_et": "session-timing; Gamma_EodSummary trigger hardcodes 16:00 (RESTORE-or-REMOVE)",
    "daily_review_et": "session-timing; scheduled trigger hardcodes 16:30 (RESTORE-or-REMOVE)",
    "premarket_et": "session-timing; Gamma_Premarket trigger hardcodes 08:30 (RESTORE-or-REMOVE)",
    "weekly_review_et_sunday": "session-timing; weekly trigger hardcodes 18:00 Sun (RESTORE-or-REMOVE)",
    # Resilience harness: doc says values are "also embedded in _shared.ps1"; the .ps1
    # embeds literals and does not read these keys. RESTORE (read from params) or REMOVE.
    "max_consecutive_failed_mcp_calls": "resilience; _shared.ps1 embeds literal (RESTORE-or-REMOVE)",
    "max_consecutive_tv_failures_before_kill_switch": "resilience; _shared.ps1 embeds literal (RESTORE-or-REMOVE)",
    "min_disk_free_mb": "resilience; _shared.ps1 embeds literal (RESTORE-or-REMOVE)",
    "wedged_state_alert_hours": "resilience; _shared.ps1 embeds literal (RESTORE-or-REMOVE)",
    # Exit-behavior flags: the exit path hardcodes runner/TP1 behavior; these are not read
    # by name on the live or sim exit surface. RESTORE (thread into exit_manager) or REMOVE.
    "runner_be_stop_after_tp1": "exit flag; runner BE behavior hardcoded in exit path (RESTORE-or-REMOVE)",
    "exit_all_on_runner_signal_if_tp1_unfired": "exit flag; hardcoded in exit path (RESTORE-or-REMOVE)",
    # Macro bias inheritance v2: documented in params but never wired into a live consumer.
    "macro_hard_veto_minutes": "macro-bias v2; not wired to any consumer (RESTORE-or-REMOVE)",
    "macro_soft_modifier_minutes": "macro-bias v2; not wired to any consumer (RESTORE-or-REMOVE)",
    "macro_soft_bull_threshold": "macro-bias v2; not wired to any consumer (RESTORE-or-REMOVE)",
    "macro_soft_bear_threshold": "macro-bias v2; not wired to any consumer (RESTORE-or-REMOVE)",
    # Liquidity gate: the live liquidity check is prose-approximate; these named thresholds
    # are not read by the order path. RESTORE (drive pre_order_gate) or REMOVE.
    "bid_ask_spread_max_cents": "liquidity gate; not read by order path (RESTORE-or-REMOVE)",
    "bid_ask_spread_max_pct_of_mid": "liquidity gate; not read by order path (RESTORE-or-REMOVE)",
    "delta_min_abs": "liquidity gate; not read by order path (RESTORE-or-REMOVE)",
    "delta_max_abs": "liquidity gate; not read by order path (RESTORE-or-REMOVE)",
    "liquidity_strike_retries_max": "liquidity gate; not read by order path (RESTORE-or-REMOVE)",
    # Catalyst / journaling flags: aware-only toggles never consumed by code.
    "enable_news_no_trade_windows": "catalyst flag; no live consumer (RESTORE-or-REMOVE)",
    "enable_dealer_level_journaling": "journaling flag; no live consumer (RESTORE-or-REMOVE)",
    # Sizing scale-up cadence: documented but not read by the sizing path.
    "scale_up_min_consecutive_days_above_threshold": "sizing scale-up; no live consumer (RESTORE-or-REMOVE)",
}


def _params() -> dict:
    return json.loads(_PARAMS_PATH.read_text(encoding="utf-8"))


def _ratified_knobs(params: dict) -> list[str]:
    return [k for k in params if not k.startswith("_") and k not in _METADATA_KEYS]


def _consumer_corpus() -> str:
    parts: list[str] = []
    for root, glob in _CONSUMER_GLOBS:
        for p in (_REPO / root).glob(glob):
            rp = str(p).replace("\\", "/")
            if "/.claude/worktrees" in rp or "/backtest/tests/" in rp:
                continue
            try:
                parts.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return "\n".join(parts)


def _is_referenced(key: str, corpus: str) -> bool:
    """Word-boundary match so a dead key that is a SUBSTRING of a live key
    (e.g. premium_stop_pct inside j_vwap_cont_premium_stop_pct) is not falsely revived."""
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])", corpus) is not None


def _dead_knobs() -> list[str]:
    params = _params()
    corpus = _consumer_corpus()
    return [k for k in _ratified_knobs(params) if not _is_referenced(k, corpus)]


# ── 1. No NEW dead knob may appear ────────────────────────────────────────────

def test_no_new_dead_params_knob():
    """RATCHET: every dead knob is documented in KNOWN_DEAD. A newly-ratified key with no
    live reader trips this LOUD -- wire a consumer or don't ratify the key."""
    dead = set(_dead_knobs())
    new_dead = sorted(dead - set(KNOWN_DEAD))
    assert not new_dead, (
        "NEW dead params.json knob(s) with NO live consumer (C14 dead-knob / audit "
        f"break #7): {new_dead}. Either wire a real reader in the live consumer surface "
        "(setup/scripts, backtest/lib, automation/scripts, crypto/validators, "
        "automation/prompts, setup/*.ps1) or remove the key. If it is genuinely dead by "
        "design, add it to KNOWN_DEAD with a RESTORE/REMOVE disposition."
    )


# ── 2. The allowlist can only shrink ──────────────────────────────────────────

def test_known_dead_allowlist_shrinks_only():
    """RATCHET: every KNOWN_DEAD key must STILL be dead. If a key gained a consumer, it is
    no longer dead -> remove it from KNOWN_DEAD. This forces the restore-or-remove work to
    close (the ratchet can only shrink, never silently re-admit a revived key)."""
    dead = set(_dead_knobs())
    revived = sorted(set(KNOWN_DEAD) - dead)
    assert not revived, (
        f"KNOWN_DEAD key(s) now HAVE a live consumer: {revived}. They are no longer dead "
        "-- remove them from the KNOWN_DEAD allowlist (ratchet shrinks-only)."
    )


# ── 3. Hygiene: no stale allowlist entry ──────────────────────────────────────

def test_known_dead_keys_exist_in_params():
    """No KNOWN_DEAD entry may reference a key that has already been removed from
    params.json (a stale allowlist entry silently masks a typo'd key name)."""
    params = _params()
    stale = sorted(set(KNOWN_DEAD) - set(params))
    assert not stale, (
        f"KNOWN_DEAD lists key(s) absent from params.json: {stale} -- the key was removed; "
        "drop the stale allowlist entry."
    )


# ── 4. Non-vacuous bite ───────────────────────────────────────────────────────

def test_bite_synthetic_dead_knob_is_detected():
    """The detector must actually flag an unreferenced name AND must NOT flag a genuinely
    consumed one -- proves the reconciliation isn't hardwired to pass."""
    corpus = _consumer_corpus()
    # A name no code references -> detected as dead.
    assert not _is_referenced("gamma_totally_fake_knob_xyz", corpus)
    # A control key known to be live-consumed (engine_cli GATE_KEYS / placement ceiling).
    assert _is_referenced("entry_no_trade_after_et", corpus), (
        "control key entry_no_trade_after_et is not found in the consumer corpus -- the "
        "corpus globs regressed; fix _CONSUMER_GLOBS before trusting this ratchet."
    )
    # And it is NOT in the dead set.
    assert "entry_no_trade_after_et" not in _dead_knobs()
