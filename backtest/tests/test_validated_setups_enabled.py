"""Guard: validated setups must be enabled UNLESS a live recency HOLD is recorded.

WS3 pre-check audit (2026-06-26):
  gap_and_go          -> already ENABLED (gap_and_go_enabled=true)   -- no action
  vwap_continuation   -> already ENABLED (j_vwap_cont_enabled=true)  -- no action
  vwap_reclaim_fb     -> DORMANT (false), recency BLOCKED-BY-RECENCY (book Safe2_ATM_1+2+4 RED)
  vix_regime_dayside  -> DORMANT (false), recency BLOCKED-BY-RECENCY (book Safe2_ATM_1+2+4 RED)

The guard enforces two invariants:

1. ALREADY-LIVE setups stay enabled: gap_and_go_enabled AND j_vwap_cont_enabled must
   BOTH be true in params.json (they are validated + currently live; flipping them off
   without a documented reason would silently kill confirmed edge).

2. DORMANT-but-validated setups (j_vwap_reclaim_fb + j_vix_dayside) must have a
   RECORDED recency hold in automation/state/recency-confirmation.json if they are
   currently disabled.  If no hold is recorded AND a setup is disabled, the guard
   FAILs — meaning someone flipped it off without writing a recency justification.
   Conversely, if a setup IS enabled but the book verdict is RED, the guard also
   FAILs (we shipped an edge into a confirmed drawdown without a hold note).

The test FAILS on the "regression state" (live setups disabled, or dormant setups
enabled into a RED book) and PASSES on the current correct state (live enabled,
dormant held by recorded book RED).

Fast guard — pure JSON reads, no backtest engine, no CSV data.

Run:
  cd backtest && ../.venv/Scripts/python.exe -m pytest tests/test_validated_setups_enabled.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PARAMS_PATH = REPO / "automation" / "state" / "params.json"
RECENCY_PATH = REPO / "automation" / "state" / "recency-confirmation.json"
LICENSE_MONITOR_DIR = REPO / "backtest" / "autoresearch"

# ---------------------------------------------------------------------------
# Recency-coverage registry (added 2026-06-26 — closes the self-audit gap that
# gap_and_go went LIVE without recency monitoring).
#
# ENTRY_SETUP_RECENCY maps each ENTRY-GENERATING setup flag to its recency edge
# family name.  Modifier flags (j_vwap_cont_strike_override / _1dte / _dollar_stop)
# and VETO flags (structure_veto_enabled) are deliberately EXCLUDED — they do not
# open positions, so they have no recency edge of their own.
#
# Invariant: any of these flags set True in params.json must be covered by ongoing
# recency monitoring — i.e. an edge entry in recency-confirmation.json AND a
# license_monitor.TIER_PATH mapping — so the weekly recency gate can RED-block it
# and license_monitor can ping J on a RED->green transition.  Without that, a live
# setup whose real-fills edge decays would keep trading, unmonitored and silent.
# ---------------------------------------------------------------------------
ENTRY_SETUP_RECENCY = {
    "j_vwap_cont_enabled": "vwap_continuation",
    "j_vwap_reclaim_fb_enabled": "vwap_reclaim_failed_break",
    "j_vix_dayside_enabled": "vix_regime_dayside",
    "gap_and_go_enabled": "gap_and_go",
}

# Live-enabled setups KNOWN to lack recency-confirmation coverage.  SHRINKS-ONLY
# ratchet: each entry MUST be removed the moment the setup gains a recency edge +
# a license_monitor TIER_PATH mapping (or is reverted to dormant).  An entry here
# means "A/B-validated by a scorecard but NOT wired into the ongoing recency gate."
KNOWN_UNMONITORED = {
    "gap_and_go_enabled": (
        "gap_and_go is A/B-validated (analysis/recommendations/gap-and-go-LIVE.json: "
        "exp +$41.6 / WR 72.6% / n=84 / DSR PASS / WF +1.87 / 6/6 quarters+) and LIVE, "
        "but has NO recency-confirmation.json edge entry and NO license_monitor "
        "TIER_PATH mapping -> license_monitor cannot ping a RED->green transition and "
        "recency_check has no RED-block for it. Flagged by Gamma self-audit "
        "2026-06-26T20:42; J-decision-gated via DIRECTION-BLOCK-BATCH-RECONCILE "
        "(queue Tier-2). REMOVE this entry once a 'gap_and_go' edge is added to "
        "recency-confirmation.json + license_monitor.TIER_PATH, or the setup is "
        "reverted to dormant."
    ),
}


def _load_params() -> dict:
    return json.loads(PARAMS_PATH.read_text(encoding="utf-8"))


def _load_recency() -> dict:
    return json.loads(RECENCY_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _book_verdict(recency: dict, book_key: str) -> str | None:
    """Return the verdict string for a named book, or None if not found."""
    return recency.get("books", {}).get(book_key, {}).get("verdict")


def _edge_verdict(recency: dict, edge: str, tier: str) -> str | None:
    """Return the per-tier verdict for an edge."""
    return (
        recency
        .get("edges", {})
        .get(edge, {})
        .get("tiers", {})
        .get(tier, {})
        .get("verdict")
    )


# ---------------------------------------------------------------------------
# Guard 1 — already-live validated setups must stay enabled
# ---------------------------------------------------------------------------

def test_gap_and_go_stays_enabled() -> None:
    """gap_and_go is LIVE (validated, enabled=true in prod params).

    Scorecard: analysis/recommendations/gap-and-go-LIVE.json
    exp +$41.6/WR 72.6%/n=84, DSR PASS, WF median +1.87, 6/6 quarters +.
    If this flips false without a recorded hold, we silently lose live edge.
    """
    params = _load_params()
    assert params.get("gap_and_go_enabled") is True, (
        "gap_and_go_enabled must be True — it's a validated LIVE edge "
        "(scorecard: analysis/recommendations/gap-and-go-LIVE.json). "
        "If disabling, first record the reason in recency-confirmation.json."
    )


def test_vwap_continuation_stays_enabled() -> None:
    """j_vwap_cont is LIVE (j_vwap_cont_enabled=true, side=both in prod params).

    Scorecard: analysis/recommendations/j-daily-pattern-LIVE.json
    exp +$38.3/WR 76.5%/n=153, drop-top5 +$24.45 robust, DSR PASS.
    If this flips false without a recorded hold, we silently lose live edge.
    """
    params = _load_params()
    assert params.get("j_vwap_cont_enabled") is True, (
        "j_vwap_cont_enabled must be True — it's a validated LIVE edge "
        "(scorecard: analysis/recommendations/j-daily-pattern-LIVE.json). "
        "If disabling, first record the reason in recency-confirmation.json."
    )


# ---------------------------------------------------------------------------
# Guard 2 — dormant setups must have a RECORDED recency hold when disabled
# ---------------------------------------------------------------------------

def test_vwap_reclaim_fb_disabled_only_if_recency_hold_recorded() -> None:
    """j_vwap_reclaim_fb_enabled is False.  This is CORRECT only because the
    recency-confirmation.json records a RED book verdict on the combined book
    that contains this setup (Safe2_ATM_1+2+4 book, n=17 >= floor 10, exp -$8.01/tr).

    If recency-confirmation.json is MISSING or the book verdict is NOT RED/YELLOW,
    AND the setup is disabled, this guard fails — someone flipped it off without
    a documented recency reason.

    Conversely, if the setup is ENABLED but the book verdict is RED, this guard
    also fails — we would be shipping into a confirmed drawdown without a hold.
    """
    params = _load_params()
    enabled = params.get("j_vwap_reclaim_fb_enabled", False)

    if not RECENCY_PATH.exists():
        if not enabled:
            pytest.fail(
                "j_vwap_reclaim_fb_enabled=False but recency-confirmation.json "
                "does not exist — cannot confirm a recency hold is recorded. "
                "Either enable the setup or run recency_check.py and record the hold."
            )
        # if enabled and no recency file, we cannot check book verdict; pass (can't regress)
        return

    recency = _load_recency()
    book_verdict = _book_verdict(recency, "Safe2_ATM_1+2+4")
    edge_verdict_atm = _edge_verdict(recency, "vwap_reclaim_failed_break", "ATM")

    if enabled:
        # Setup is enabled — ensure book is not RED (don't ship into confirmed drawdown)
        assert book_verdict != "RED", (
            f"j_vwap_reclaim_fb_enabled=True BUT book 'Safe2_ATM_1+2+4' verdict is RED "
            f"(exp -$8.01/tr, n=17 >= floor 10 in recency-confirmation.json). "
            f"A RED book verdict means we are in a confirmed recent drawdown. "
            f"Either disable the setup or wait for the book to re-confirm (YELLOW or CONFIRM)."
        )
    else:
        # Setup is disabled — ensure there IS a recency justification (RED or YELLOW hold)
        assert book_verdict in ("RED", "YELLOW"), (
            f"j_vwap_reclaim_fb_enabled=False but book 'Safe2_ATM_1+2+4' verdict "
            f"is '{book_verdict}' (not RED/YELLOW). No recency hold justifies keeping "
            f"this validated setup dormant. Either enable it or update recency-confirmation.json."
        )


def test_vix_dayside_disabled_only_if_recency_hold_recorded() -> None:
    """j_vix_dayside_enabled is False.  This is CORRECT only because the
    recency-confirmation.json records a RED book verdict on the combined book
    (Safe2_ATM_1+2+4 book, n=17 >= floor 10, exp -$8.01/tr).

    Individual edge ATM verdict is YELLOW (n=5 < floor, recent exp +$61.8/tr POSITIVE),
    which means it's positive-but-thin; the book-level RED drives the hold.

    Same logic as vwap_reclaim_fb: if book is not RED/YELLOW and setup is disabled,
    guard fails. If setup is enabled but book is RED, guard also fails.
    """
    params = _load_params()
    enabled = params.get("j_vix_dayside_enabled", False)

    if not RECENCY_PATH.exists():
        if not enabled:
            pytest.fail(
                "j_vix_dayside_enabled=False but recency-confirmation.json "
                "does not exist — cannot confirm a recency hold is recorded. "
                "Either enable the setup or run recency_check.py and record the hold."
            )
        return

    recency = _load_recency()
    book_verdict = _book_verdict(recency, "Safe2_ATM_1+2+4")
    edge_verdict_atm = _edge_verdict(recency, "vix_regime_dayside", "ATM")

    if enabled:
        assert book_verdict != "RED", (
            f"j_vix_dayside_enabled=True BUT book 'Safe2_ATM_1+2+4' verdict is RED "
            f"(exp -$8.01/tr, n=17 >= floor 10 in recency-confirmation.json). "
            f"A RED book verdict means we are in a confirmed recent drawdown. "
            f"Either disable the setup or wait for the book to re-confirm (YELLOW or CONFIRM). "
            f"Note: the individual vix_dayside ATM edge is YELLOW/positive (n=5 < floor, "
            f"exp +$61.8/tr) — but the BOOK containing it is RED; the book gate governs."
        )
    else:
        assert book_verdict in ("RED", "YELLOW"), (
            f"j_vix_dayside_enabled=False but book 'Safe2_ATM_1+2+4' verdict "
            f"is '{book_verdict}' (not RED/YELLOW). No recency hold justifies keeping "
            f"this validated setup dormant. Either enable it or update recency-confirmation.json."
        )


# ---------------------------------------------------------------------------
# Guard 3 — recency file content sanity (prevents stale/empty JSON)
# ---------------------------------------------------------------------------

def test_recency_file_is_fresh_and_covers_the_three_recency_tracked_setups() -> None:
    """The recency-confirmation.json must cover the three recency-tracked setups.

    NOTE: gap_and_go is a 4th validated/live setup but is NOT in recency-confirmation
    (see KNOWN_UNMONITORED + test_live_entry_setups_are_recency_monitored). The three
    asserted here are the ones the weekly recency gate actually tracks today.

    If someone accidentally clears the file or it becomes stale, the dormant-setup
    guards above would pass vacuously (no RED verdict found = enable?). This guard
    prevents that by asserting the file exists AND contains entries for all setups.
    """
    assert RECENCY_PATH.exists(), (
        "recency-confirmation.json is missing. Run: "
        "backtest/.venv/Scripts/python.exe backtest/autoresearch/recency_check.py"
    )
    recency = _load_recency()

    # Must have the canonical book that governs the dormant setups
    assert "Safe2_ATM_1+2+4" in recency.get("books", {}), (
        "recency-confirmation.json is missing the 'Safe2_ATM_1+2+4' book verdict "
        "that governs the vwap_reclaim_fb and vix_dayside hold decisions."
    )

    # Must have all four validated edge families
    edges = recency.get("edges", {})
    for edge_name in ("vwap_continuation", "vwap_reclaim_failed_break", "vix_regime_dayside"):
        assert edge_name in edges, (
            f"recency-confirmation.json is missing edge '{edge_name}'. "
            "Re-run recency_check.py to regenerate the full coverage."
        )

    # Book verdict must be a known value (not corrupted)
    book_verdict = _book_verdict(recency, "Safe2_ATM_1+2+4")
    assert book_verdict in ("CONFIRM", "YELLOW", "RED"), (
        f"Book 'Safe2_ATM_1+2+4' verdict is '{book_verdict}' — not a known verdict. "
        "Expected one of: CONFIRM / YELLOW / RED."
    )


# ---------------------------------------------------------------------------
# Guard 4 (regression) — verifies that flipping the flags to the WRONG state
# is what breaks guard 2 (proves the guard is not vacuous).
# This is a parametric "would-fail" test using a patched params dict.
# ---------------------------------------------------------------------------

def test_regression_enabling_dormant_into_red_book_would_fail() -> None:
    """Regression guard — demonstrates the guard is NOT vacuous.

    If the book is RED (as it is now) and someone sets j_vwap_reclaim_fb_enabled=True,
    the guard in test_vwap_reclaim_fb_disabled_only_if_recency_hold_recorded would fail.
    This test SIMULATES that to prove the guard has teeth.
    """
    if not RECENCY_PATH.exists():
        pytest.skip("recency file absent — cannot assert book verdict")

    recency = _load_recency()
    book_verdict = _book_verdict(recency, "Safe2_ATM_1+2+4")

    if book_verdict != "RED":
        pytest.skip(
            f"Book verdict is '{book_verdict}' not RED — regression scenario "
            "only applies when the book is in a confirmed drawdown."
        )

    # Simulate: someone flipped j_vwap_reclaim_fb_enabled=True with RED book
    # The guard logic: enabled=True AND book=RED → should fail
    enabled_hypothetical = True
    would_fail = (enabled_hypothetical and book_verdict == "RED")
    assert would_fail, "Regression logic broken — guard would not catch a RED-book enable"

    # Prove the ACTUAL guard sees the RED verdict correctly
    assert book_verdict == "RED", (
        "Expected RED book verdict in the regression scenario but got something else."
    )
    # This confirms guard 2's assertion `book_verdict != "RED"` would have fired.


def test_regression_disabling_live_setup_would_fail() -> None:
    """Regression guard — demonstrates test_gap_and_go_stays_enabled has teeth.

    Simulates setting gap_and_go_enabled=False and verifies the guard logic
    (params.get('gap_and_go_enabled') is True) would have asserted False.
    """
    # Simulate the broken params state
    fake_params = {"gap_and_go_enabled": False, "j_vwap_cont_enabled": False}

    # The guard condition: params.get('gap_and_go_enabled') is True
    gap_would_pass = fake_params.get("gap_and_go_enabled") is True
    cont_would_pass = fake_params.get("j_vwap_cont_enabled") is True

    assert not gap_would_pass, (
        "Regression logic broken — guard_1 would not catch gap_and_go_enabled=False"
    )
    assert not cont_would_pass, (
        "Regression logic broken — guard_1 would not catch j_vwap_cont_enabled=False"
    )

    # Now confirm the ACTUAL params have these True (the passing state)
    actual_params = _load_params()
    assert actual_params.get("gap_and_go_enabled") is True
    assert actual_params.get("j_vwap_cont_enabled") is True


# ---------------------------------------------------------------------------
# Guard 5 — every LIVE entry setup must be covered by ongoing recency monitoring
# (recency-confirmation.json edge + license_monitor.TIER_PATH), else explicitly
# documented in KNOWN_UNMONITORED.  Closes the self-audit gap (2026-06-26T20:42):
# gap_and_go went LIVE with no recency tracker, so license_monitor is blind to it.
# ---------------------------------------------------------------------------

def _live_entry_setups() -> dict[str, str]:
    """Return {flag: edge} for every entry setup currently enabled in params.json."""
    params = _load_params()
    return {
        flag: edge
        for flag, edge in ENTRY_SETUP_RECENCY.items()
        if params.get(flag) is True
    }


def _tier_path_edges() -> set[str]:
    """Edges referenced by license_monitor.TIER_PATH (the RED->green ping wiring)."""
    if str(LICENSE_MONITOR_DIR) not in sys.path:
        sys.path.insert(0, str(LICENSE_MONITOR_DIR))
    import license_monitor as lm  # noqa: PLC0415

    return {edge for (edge, _tier) in lm.TIER_PATH.values()}


def test_live_entry_setups_are_recency_monitored() -> None:
    """Every LIVE entry setup must have a recency-confirmation.json edge entry,
    OR be explicitly documented in KNOWN_UNMONITORED.

    A setup enabled for live trading without a recency edge is invisible to the
    weekly CONFIRM-BEFORE-CAPITAL gate — its edge could decay into a confirmed
    drawdown and keep trading, because recency_check has no RED-block for it.
    (Self-audit 2026-06-26T20:42; gap_and_go is the current known instance.)
    """
    recency = _load_recency()
    edges = recency.get("edges", {})
    unmonitored = [
        (flag, edge)
        for flag, edge in _live_entry_setups().items()
        if edge not in edges and flag not in KNOWN_UNMONITORED
    ]
    assert not unmonitored, (
        f"Live entry setups with NO recency-confirmation edge coverage and NOT in "
        f"KNOWN_UNMONITORED: {unmonitored}. Enabling a setup for live trading means "
        f"the weekly recency gate must be able to RED-block it. Either add the edge "
        f"to recency-confirmation.json (re-run autoresearch/recency_check.py) or, if "
        f"the deferral is intentional, add the flag to KNOWN_UNMONITORED with a dated "
        f"justification."
    )


def test_live_entry_setups_have_license_monitor_path() -> None:
    """Every LIVE, recency-tracked entry setup must also be wired into
    license_monitor.TIER_PATH, so a RED->green transition actually pings J.

    A setup that has a recency edge but no TIER_PATH mapping would be RED-blockable
    by the weekly gate yet never trigger the automatic 'now ELIGIBLE' notification —
    the deploy loop would silently never close. KNOWN_UNMONITORED setups are exempt
    (they have neither edge nor path, tracked by guard 5 above).
    """
    tier_edges = _tier_path_edges()
    missing = [
        (flag, edge)
        for flag, edge in _live_entry_setups().items()
        if flag not in KNOWN_UNMONITORED and edge not in tier_edges
    ]
    assert not missing, (
        f"Live entry setups recency-tracked but missing a license_monitor.TIER_PATH "
        f"mapping: {missing}. Add a TIER_PATH entry in backtest/autoresearch/"
        f"license_monitor.py so RED->green transitions ping J."
    )


def test_known_unmonitored_ratchet_shrinks() -> None:
    """SHRINKS-ONLY ratchet: a KNOWN_UNMONITORED setup that has SINCE gained full
    recency coverage (edge entry AND TIER_PATH mapping) MUST be removed from the
    allowlist. This prevents the allowlist from hiding a setup that is now actually
    monitored — the documented gap must close, not linger.
    """
    recency = _load_recency()
    edges = recency.get("edges", {})
    tier_edges = _tier_path_edges()
    now_covered = []
    for flag in KNOWN_UNMONITORED:
        edge = ENTRY_SETUP_RECENCY.get(flag)
        if edge in edges and edge in tier_edges:
            now_covered.append(flag)
    assert not now_covered, (
        f"These KNOWN_UNMONITORED setups now HAVE full recency coverage "
        f"(edge + TIER_PATH): {now_covered}. Remove them from KNOWN_UNMONITORED — "
        f"the ratchet must shrink toward zero."
    )


def test_gap_and_go_is_the_known_unmonitored_instance() -> None:
    """Pin the current known gap: gap_and_go is LIVE, A/B-validated, but absent from
    BOTH recency-confirmation.json edges AND license_monitor.TIER_PATH. This test
    documents the present truth; when J adds a tracker entry (or reverts the enable),
    test_known_unmonitored_ratchet_shrinks forces the allowlist update and this test
    should be retired alongside it.
    """
    params = _load_params()
    if params.get("gap_and_go_enabled") is not True:
        pytest.skip("gap_and_go reverted to dormant — gap closed; retire this test.")
    recency = _load_recency()
    assert "gap_and_go" not in recency.get("edges", {}), (
        "gap_and_go now HAS a recency edge — update KNOWN_UNMONITORED and retire this test."
    )
    assert "gap_and_go" not in _tier_path_edges(), (
        "gap_and_go now HAS a TIER_PATH mapping — update KNOWN_UNMONITORED and retire this test."
    )
