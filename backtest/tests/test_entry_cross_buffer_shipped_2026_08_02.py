"""ENTRY-CROSS-BUFFER SHIP GUARD (2026-08-02).

Ships the validated `entry_cross_buffer` reduction (0.03 -> 0.015) into
`automation/state/params.json` + `automation/state/aggressive/params.json` --
full evidence in `analysis/deep-research/ENTRY-EXECUTION-COST-2026-08-02.md`,
pre-registration `analysis/recommendations/entry-buffer-reduction-prereg-2026-08-02.json`
(commit 78979314, predates its own runner commit cb30dcd2), results
`analysis/recommendations/entry-buffer-reduction-results-2026-08-02.json`.

Prior value 0.03 was a BARE UNRATIFIED CODE DEFAULT (`params.get("entry_cross_buffer",
0.03)`, never once present in params.json / aggressive/params.json / fleet/accounts.json
in this repo's git history). This suite is the C14 dead-knob class guard for the *opposite*
failure mode: not "ratified but unwired" but "wired at the code default, now overridden --
prove the override actually reaches every consumer." A key added to a params file that no
arm's resolved params dict actually reads would be exactly a silent no-op ship.

THE MECHANISM UNDER TEST (traced 2026-08-02, not assumed):
  - Core arms (safe-2, bold-2; execution="mcp_heartbeat"): heartbeat_core.py's own
    `run_account`/`main` loads `params = json.loads(cfg["params"].read_text())` where
    `cfg = ACCOUNTS[account]` (heartbeat_core.py:1143-1144) -- i.e. THE RAW FILE, no merge
    layer. safe reads automation/state/params.json, bold reads
    automation/state/aggressive/params.json (heartbeat_core.ACCOUNTS).
  - Fleet arms (safe-3, risky-1, risky-3; execution="fleet_rest"): fleet_live.py's
    `decide_arm` calls `fleet_executor._params_for(arm)` (fleet_live.py:579), which is
    `_base_params_for(arm)` (PARAMS_SAFE for safe/PARAMS_BOLD for bold/risky ids, verbatim
    the SAME two files core reads) with the arm's own `accounts.json` `params_patch`
    shallow-merged on top. None of safe-3/risky-1/risky-3's params_patch blocks set
    `entry_cross_buffer` (asserted below, non-vacuously, straight from the live
    accounts.json) -- so all three inherit the base file's value unpatched.
  - Both lanes price the entry via the SAME primitive:
    `fleet_broker.marketable_limit_price(creds, symbol, side="buy",
    buffer=float(params.get("entry_cross_buffer", 0.03)))` -- heartbeat_core.py ~L1932-1933,
    fleet_live.py ~L389-390.
  - `build_shared_signal.py` does NOT read this key (confirmed by grep across the whole
    repo) -- it is a signal PRODUCER (entry triggers/gates), never an entry-price consumer.
  - `entry_manager.py` mentions the mechanism in its own docstring but is SHADOW-ONLY
    (crypto-twin / backtest tooling; not imported by heartbeat_core.py or fleet_live.py) --
    irrelevant to the live SPY order path this ship targets.

RED-PROOF (manual, run once when this file was authored, not re-run automatically):
temporarily reverted `entry_cross_buffer` out of both params files (restoring the exact
pre-edit bytes) and re-ran this file -- test_shipped_value_pinned_in_both_base_files and
test_marketable_limit_price_resolves_shipped_buffer_for_every_active_arm both failed with
the expected AssertionError (0.03 != 0.015), proving the guard actually discriminates. Full
transcript in this ship's STATUS.md entry.

Run: backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_entry_cross_buffer_shipped_2026_08_02.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_SCRIPTS = ROOT / "setup" / "scripts"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(ROOT), str(_SCRIPTS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAFE_PARAMS_PATH = ROOT / "automation" / "state" / "params.json"
BOLD_PARAMS_PATH = ROOT / "automation" / "state" / "aggressive" / "params.json"
ACCOUNTS_PATH = _FLEET / "accounts.json"

SHIPPED_BUFFER = 0.015
REJECTED_BUFFER = 0.01
PRE_SHIP_BARE_DEFAULT = 0.03

_CREDS = {"key": "k", "secret": "s", "base_url": "https://paper-api.example.invalid"}

# The 5 arms that actually place SPY 0DTE option orders today (safe-1 is retired --
# status != "active" gates it out of every live dispatch path, fleet_live._arm_is_processable
# and fleet_executor's own active-status filter alike -- but its base params file is the
# same as safe-3's, so it is included in the informational (non-asserting) sibling test).
ACTIVE_ARM_IDS = {"safe-2", "bold-2", "safe-3", "risky-1", "risky-3"}
CORE_ARM_IDS = {"safe-2": "safe", "bold-2": "bold"}  # arm id -> heartbeat_core.ACCOUNTS key


def _safe_params() -> dict:
    return json.loads(SAFE_PARAMS_PATH.read_text(encoding="utf-8"))


def _bold_params() -> dict:
    return json.loads(BOLD_PARAMS_PATH.read_text(encoding="utf-8"))


def _accounts() -> dict:
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


def _arm_by_id(arm_id: str) -> dict:
    for arm in _accounts()["arms"]:
        if arm.get("id") == arm_id:
            return arm
    raise AssertionError(f"arm {arm_id!r} not found in accounts.json -- roster changed?")


# ── 1. The shipped value is pinned in both base params files ──────────────────────────────

def test_shipped_value_pinned_in_both_base_files():
    safe = _safe_params()
    bold = _bold_params()
    assert safe.get("entry_cross_buffer") == SHIPPED_BUFFER, (
        f"automation/state/params.json entry_cross_buffer = {safe.get('entry_cross_buffer')!r}, "
        f"expected {SHIPPED_BUFFER} -- the ship did not land or was reverted.")
    assert bold.get("entry_cross_buffer") == SHIPPED_BUFFER, (
        f"automation/state/aggressive/params.json entry_cross_buffer = "
        f"{bold.get('entry_cross_buffer')!r}, expected {SHIPPED_BUFFER}.")


def test_doc_sibling_present_in_both_files():
    """The doc sibling is not decorative -- it is the provenance/kill-criterion/revert
    record OP-33 requires for any params change. Its absence means an edit landed without
    the paper trail this ship's own STATUS.md entry promises exists."""
    safe = _safe_params()
    bold = _bold_params()
    for params, label in ((safe, "safe"), (bold, "bold")):
        doc = params.get("_entry_cross_buffer_doc", "")
        assert doc, f"{label} params.json missing _entry_cross_buffer_doc sibling"
        assert "0.015" in doc and "0.03" in doc, f"{label} doc missing before/after values"
        assert "REVERT" in doc.upper(), f"{label} doc missing an explicit revert instruction"


# ── 2. 0.01 was tested and REJECTED -- must never be the shipped value ────────────────────

def test_rejected_candidate_0_01_is_not_shipped():
    """0.01 FAILED the pre-registered zero-tolerance runner-cohort gate (missed the
    2026-07-31 12:19 ET anchor trade + 1 more real runner-cohort winner, 2 of 10). A future
    session must not quietly ratchet the buffer down to 0.01 without re-running
    entry_buffer_reduction_ab_2026_08_02.py against fresh fill history -- this pins the
    negative space, not just the positive value."""
    safe = _safe_params()
    bold = _bold_params()
    assert safe.get("entry_cross_buffer") != REJECTED_BUFFER, (
        "SAFE entry_cross_buffer == 0.01 -- this candidate was TESTED AND REJECTED "
        "(missed the real runner-cohort anchor trade). Do not ship it without a fresh A/B.")
    assert bold.get("entry_cross_buffer") != REJECTED_BUFFER, (
        "BOLD entry_cross_buffer == 0.01 -- this candidate was TESTED AND REJECTED "
        "(missed the real runner-cohort anchor trade). Do not ship it without a fresh A/B.")


# ── 3. No arm's params_patch silently overrides the shipped base value ────────────────────

def test_no_arm_params_patch_overrides_the_key():
    """Non-vacuous provenance check: the inheritance argument in this ship's doc siblings
    depends on EVERY fleet arm's params_patch being silent on this key. If a future edit
    ever adds an arm-specific entry_cross_buffer override to accounts.json, this must be a
    deliberate, reviewed decision -- not a silent divergence this guard missed."""
    accounts = _accounts()
    patched = [
        arm["id"] for arm in accounts["arms"]
        if "entry_cross_buffer" in (arm.get("params_patch") or {})
    ]
    assert not patched, (
        f"arm(s) {patched} carry an entry_cross_buffer override in params_patch -- the "
        "base-file-only inheritance trace in this ship's doc siblings is now WRONG for "
        "these arms; update the trace and re-verify by execution before trusting this guard."
    )


# ── 4. THE MECHANISM: marketable_limit_price actually resolves ask+0.015 for EVERY ────────
#       active arm's REAL resolved params, through the REAL code paths (vary-and-assert).

def test_marketable_limit_price_resolves_shipped_buffer_for_every_active_arm(monkeypatch):
    """For each of the 5 active SPY arms, resolve params the SAME way the live code does
    (core: raw file load via heartbeat_core.ACCOUNTS; fleet: fleet_executor._params_for's
    real base+patch merge), then feed that into the REAL fleet_broker.marketable_limit_price
    -- only the network boundary (get_option_quote_hilo) is stubbed. This proves the key
    reaches the actual pricing arithmetic for every arm the A/B measured, not just that the
    raw params file has the right value."""
    import fleet_broker as fb
    import fleet_executor as fx
    import heartbeat_core as hc

    monkeypatch.setattr(fb, "get_option_quote_hilo", lambda creds, symbol: (1.00, 0.90))

    accounts = _accounts()
    arms_by_id = {a["id"]: a for a in accounts["arms"]}
    resolved: dict[str, float] = {}

    for arm_id in sorted(ACTIVE_ARM_IDS):
        if arm_id in CORE_ARM_IDS:
            account_key = CORE_ARM_IDS[arm_id]
            params = json.loads(hc.ACCOUNTS[account_key]["params"].read_text(encoding="utf-8"))
        else:
            arm = arms_by_id[arm_id]
            params = fx._params_for(arm)
        buffer = float(params.get("entry_cross_buffer", PRE_SHIP_BARE_DEFAULT))
        resolved[arm_id] = buffer
        entry_px = fb.marketable_limit_price(_CREDS, f"TESTSYM_{arm_id}", side="buy", buffer=buffer)
        expected = round(1.00 + SHIPPED_BUFFER, 2)
        assert entry_px == pytest.approx(expected), (
            f"arm {arm_id!r}: marketable_limit_price returned {entry_px}, expected "
            f"{expected} (ask 1.00 + shipped buffer {SHIPPED_BUFFER}). Resolved buffer for "
            f"this arm was {buffer} -- the ship did not reach this arm's real params."
        )

    # Every active arm must have resolved EXACTLY the shipped value -- if any arm still
    # resolves the bare 0.03 default, the ship is INCOMPLETE for that arm.
    stale = {arm: buf for arm, buf in resolved.items() if buf != SHIPPED_BUFFER}
    assert not stale, (
        f"arm(s) still resolving a non-shipped buffer: {stale} -- ship incomplete, some "
        "arm's real resolved params were not reached by the params.json/aggressive edits."
    )


def test_retired_safe1_shares_the_shipped_base_value(monkeypatch):
    """Informational, non-blocking-for-dispatch: safe-1 is retired (no live orders), but it
    shares automation/state/params.json as its base, so it resolves the shipped value too --
    documents that a future un-retirement would not need a separate ship."""
    import fleet_executor as fx
    arm = _arm_by_id("safe-1")
    assert arm.get("status") == "retired"
    params = fx._params_for(arm)
    assert params.get("entry_cross_buffer") == SHIPPED_BUFFER


def test_absent_key_falls_back_to_bare_pre_ship_default():
    """Documents the exact one-line-revert contract the doc siblings promise: deleting the
    key must be byte-identical to pre-ship behavior (params.get's own hardcoded default),
    never silently drop to $0 or raise."""
    without_key = dict(_safe_params())
    without_key.pop("entry_cross_buffer", None)
    assert float(without_key.get("entry_cross_buffer", PRE_SHIP_BARE_DEFAULT)) == PRE_SHIP_BARE_DEFAULT


# ── 5. Structural confirmation that this knob cannot touch exit management ────────────────

def test_build_shared_signal_does_not_reference_the_key():
    """Structural check backing the doc siblings' claim that build_shared_signal.py (the
    signal PRODUCER) never reads this key -- if a future edit wires it in there, the
    inheritance trace above would need re-verification (a second consumer this guard
    doesn't cover)."""
    src = (_FLEET / "build_shared_signal.py").read_text(encoding="utf-8", errors="ignore")
    assert "entry_cross_buffer" not in src


# ── 6. engine-contract.md display bug (found BY this ship's own regeneration) ─────────────

def _load_engine_contract():
    import importlib.util
    spec = importlib.util.spec_from_file_location("engine_contract", _SCRIPTS / "engine_contract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_money_helper_avoids_the_float_formatting_artifact():
    """0.015's nearest IEEE-754 double is a hair UNDER the true decimal value, so naive
    f"{0.015:.2f}" silently renders "0.01" (verified: this is exactly what the FIRST
    regeneration of engine-contract.md after this ship produced -- caught before commit,
    not a hypothetical). engine_contract._money must render the human-intended value."""
    ec = _load_engine_contract()
    assert ec._money(0.015) == "$0.015"
    assert ec._money(0.03) == "$0.03"
    assert ec._money(0.01) == "$0.01"
    assert ec._money(0.02) == "$0.02"


def test_engine_contract_card_renders_shipped_value_not_the_float_artifact():
    """End-to-end: the actual rendered card must show the correct $0.015, never the
    silently-wrong $0.01 a naive :.2f would produce for this exact value."""
    ec = _load_engine_contract()
    card = ec.render_contract()
    assert "entry_cross_buffer` ($0.015)" in card, (
        "engine-contract.md does not render the shipped $0.015 buffer correctly -- "
        "check engine_contract.py's _money() call site in the 3b entry-policy section."
    )
    assert "entry_cross_buffer` ($0.01)" not in card, (
        "engine-contract.md renders $0.01 for the entry_cross_buffer line -- this is the "
        "float-formatting artifact (0.015's nearest double rounds DOWN under naive :.2f), "
        "not the shipped value. Use engine_contract._money(), not f'{x:.2f}'."
    )
