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
    ("setup/scripts", "*.ps1"),  # ADDED 2026-07-19: _shared.ps1 + run-*.ps1 live HERE, not
    # setup/*.ps1 (that dir is installers only) -- the corpus never scanned the directory
    # where params actually get READ by the .ps1 task scripts, so any knob consumed ONLY by
    # a setup/scripts/*.ps1 file (e.g. min_disk_free_mb via Test-DiskSpaceAvailable) false-
    # flagged dead. Found live via PARAMS-DEAD-KNOB-DISPOSITION slice 1 (2026-07-19,
    # conductor) when restoring min_disk_free_mb tripped this exact gap.
    ("setup", "*.py"),
    ("setup", "*.ps1"),
    ("backtest/lib", "**/*.py"),
    ("backtest/autoresearch", "*.py"),
    ("automation/scripts", "*.py"),
    ("crypto/validators", "*.py"),
    ("automation/prompts", "*.md"),
    ("automation/state/fleet", "*.py"),  # ADDED 2026-07-19: the live fleet-lane consumer
    # (fleet_executor.py etc) was never scanned, so any fleet-only knob (e.g.
    # recency_min_size_enabled, whose OWN _doc names fleet_executor.py as its consumer)
    # false-flagged dead. Same class of gap as the setup/scripts/*.ps1 fix above -- found
    # together via PARAMS-DEAD-KNOB-DISPOSITION slice 1 (2026-07-19, conductor).
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
    # Resilience-harness bucket CLOSED 2026-07-19 (conductor, PARAMS-DEAD-KNOB-DISPOSITION
    # slice 1 of 6): max_consecutive_failed_mcp_calls / max_consecutive_tv_failures_before_
    # kill_switch / wedged_state_alert_hours REMOVED from params.json (verified zero
    # consumers anywhere in the repo -- the doc's "also embedded in _shared.ps1" claim was
    # false; the live self-heal design in run-tv-watchdog.ps1 never counted consecutive
    # failures, it relaunches immediately + always alerts, so no counter was ever built).
    # min_disk_free_mb RESTORED: Test-DiskSpaceAvailable now reads it live via the new
    # Get-ParamsMinDiskFreeMb helper (fail-open to 100) -- no longer dead, removed from
    # this allowlist entirely (see test_min_disk_free_mb_restored_2026_07_19.py).
    # Exit-behavior flags: the exit path hardcodes runner/TP1 behavior; these are not read
    # by name on the live or sim exit surface. RESTORE (thread into exit_manager) or REMOVE.
    "runner_be_stop_after_tp1": "exit flag; runner BE behavior hardcoded in exit path (RESTORE-or-REMOVE)",
    "exit_all_on_runner_signal_if_tp1_unfired": "exit flag; hardcoded in exit path (RESTORE-or-REMOVE)",
    # Macro bias inheritance v2 (4 keys) + liquidity gate (6 keys, incl. open_interest_min
    # which never made it into this dict -- see the audit note) were REMOVED from params.json
    # entirely 2026-08-29 (conductor-weekend, GATE-RECENCY-REVALIDATION queue item,
    # gate-recency-audit-2026-08-08.md ranks 14/15 CONFIRMED_DEAD) rather than restored --
    # RESTORE-or-REMOVE resolved to REMOVE. See params.json's own
    # _macro_section_RETIRED_2026_08_29 / _liquidity_gate_section_RETIRED_2026_08_29 doc keys.
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


def _strip_py_comments(src: str) -> str:
    """Drop `#` comments from Python source before it enters the consumer corpus.

    WHY (2026-08-12). A COMMENT IS NOT A CONSUMER, and treating it as one made this ratchet
    self-defeating: documenting that a knob is dead REVIVED it. Concretely,
    `test_known_dead_allowlist_shrinks_only` failed on `bid_ask_spread_max_cents` whose only two
    "consumers" were prose saying it was dead --

        setup/scripts/heartbeat_core.py:2150   "... bid_ask_spread_max_cents was a dead knob with
                                                zero consumers ..."
        backtest/tests/test_nbbo_capture_2026_07_20.py:5   (already excluded: tests are skipped)

    -- so the ratchet demanded delisting a knob that is still genuinely dead. Delisting it would
    have been the WRONG fix: it would have removed a real dead knob from the allowlist and hidden
    it. Fixing the scanner is the right one.

    Only `#` comments are stripped, and only for .py files. Docstrings are deliberately left in:
    they are far more likely to be a genuine API contract, and tokenize cannot distinguish a
    docstring from a module-level string constant that IS a consumer.

    Fails SAFE: on any tokenize error the raw text is returned. Over-including can only mark a key
    ALIVE (the pre-existing behaviour); under-including would mark a live key DEAD and trip
    test_no_new_dead_params_knob loudly, which is the direction that must never happen silently.
    """
    import io
    import tokenize
    try:
        out, last_end = [], (1, 0)
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.start[0] > last_end[0]:
                out.append("\n" * (tok.start[0] - last_end[0]))
            out.append(tok.string)
            last_end = tok.end
        return "".join(out)
    except Exception:  # noqa: BLE001 -- fail safe toward the pre-existing behaviour
        return src


def _consumer_corpus() -> str:
    parts: list[str] = []
    for root, glob in _CONSUMER_GLOBS:
        for p in (_REPO / root).glob(glob):
            rp = str(p).replace("\\", "/")
            if "/.claude/worktrees" in rp or "/backtest/tests/" in rp:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if p.suffix == ".py":
                text = _strip_py_comments(text)
            parts.append(text)
    return "\n".join(parts)


def _is_referenced(key: str, corpus: str) -> bool:
    """Word-boundary match so a dead key that is a SUBSTRING of a live key
    (e.g. premium_stop_pct inside j_vwap_cont_premium_stop_pct) is not falsely revived."""
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])", corpus) is not None


def _dead_knobs() -> list[str]:
    params = _params()
    corpus = _consumer_corpus()
    return [k for k in _ratified_knobs(params) if not _is_referenced(k, corpus)]


# ── 0. A COMMENT IS NOT A CONSUMER ────────────────────────────────────────────

def test_a_comment_mentioning_a_key_does_not_revive_it():
    """THE SELF-DEFEAT. Before 2026-08-12 this ratchet scanned raw text, so writing
    "# foo_knob was a dead knob with zero consumers" in live code made foo_knob look ALIVE.
    That is exactly what happened to bid_ask_spread_max_cents (heartbeat_core.py:2150), and it
    demanded delisting a knob that is genuinely still dead -- i.e. the ratchet was pushing toward
    HIDING a real dead knob."""
    src = "x = 1  # totally_fake_knob_abc was a dead knob with zero consumers\n"
    assert _is_referenced("totally_fake_knob_abc", src), "fixture sanity: raw text does match"
    assert not _is_referenced("totally_fake_knob_abc", _strip_py_comments(src)), (
        "a comment mentioning a key still revives it -- documenting deadness makes it look alive")


def test_real_code_references_survive_stripping():
    """The other direction: stripping must not blind the ratchet to genuine consumers, which
    would mark a LIVE key dead and trip the ratchet loudly for the wrong reason."""
    src = 'v = params["real_live_knob"]  # real_live_knob comment\n'
    assert _is_referenced("real_live_knob", _strip_py_comments(src))


def test_stripping_fails_safe_on_unparseable_source():
    """Fail toward the pre-existing behaviour (over-include -> ALIVE), never toward marking live
    keys dead."""
    broken = "def f(:\n  # some_knob\n"
    assert _strip_py_comments(broken) == broken


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
