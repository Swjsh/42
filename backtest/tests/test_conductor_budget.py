"""Guards for conductor_budget -- the nightly spend governor.

Context: a measured census (2026-07-25) found the conductor family = 93.3% of automation token
burn. The subtle failure mode this file pins: the conductor UNDER-REPORTS its own cost by ~2.2x
($3.44 self-reported vs $7.69 measured), so a cap read naively off `cost_usd` would silently
permit ~2x the intended spend. The correction is the point of the module.

RE-MEASURED 2026-08-08 (CONDUCTOR-BUDGET-ARITHMETIC): the 07-25 numbers above were never
independently re-checked and the constant was updated 2.2 -> 2.16 off a fresh transcript-based
measurement (n=16 real-work fires, see conductor_budget.SELF_REPORT_CORRECTION's own comment
for the full citation and
analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.md for the writeup).
Tests below that reference "2.2x" in their names/comments are about the CORRECTION MECHANISM
(a constant > 1.0 is applied at all), not the specific value -- they read SELF_REPORT_CORRECTION
dynamically and still pass unchanged at 2.16.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "setup" / "scripts"))

from conductor_budget import (  # noqa: E402
    DEFAULTS,
    EXIT_EXHAUSTED,
    EXIT_PROCEED,
    SELF_REPORT_CORRECTION,
    check,
    load_config,
    main,
    spend_today,
)

DAY = "2026-07-25"


def _outcomes(tmp_path: Path, rows) -> Path:
    # T16:00:00+00:00 = noon ET (EDT, UTC-4) -- safely mid-day, so it maps to `DAY`'s own ET
    # calendar date under BOTH the old substring match and the corrected UTC->ET conversion.
    # (T02:00:00+00:00 would map to the PREVIOUS ET day -- see test_conductor_budget below.)
    p = tmp_path / "conductor-outcomes.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for cost in rows:
            fh.write(json.dumps({"fired_at": f"{DAY}T16:00:00+00:00",
                                 "task_id": "T", "cost_usd": cost}) + "\n")
    return p


def _cfg(cap=30.0, fires=4, enabled=True):
    return {"daily_cap_usd": cap, "max_fires": fires, "enabled": enabled}


# ------------------------------------------------------- the correction factor (the whole point)
def test_self_report_is_corrected_upward():
    assert SELF_REPORT_CORRECTION > 1.0, "the conductor under-reports; correction must scale UP"


def test_self_report_correction_matches_2026_08_08_remeasurement():
    """Provenance (CONDUCTOR-BUDGET-ARITHMETIC queue item): the prior 2.2 (2026-07-25) traced
    to prose only -- no census script/artifact survived in the repo, and
    automation/state/autonomy-metric.json's total_cost_usd turned out to be the SAME
    self-reported figure the constant is meant to correct, not an independent check.

    backtest/tools/measure_conductor_cost.py closes that gap: it matches conductor-family
    conductor-outcomes.jsonl rows to their own Claude Code session transcripts
    (~/.claude/projects/.../*.jsonl) via a literal conductor.md marker string + nearest-
    timestamp, then prices the REAL tokens used against Anthropic's published per-token rates
    (independent of the LLM's own self-report) -- same methodology as spend_summary.py /
    token_forensics.py, applied per-fire instead of per-day.

    Result: n=16 real-work fires matched (self-report >= $0.25, 2026-07-26..2026-08-08).
    ALL 16 individual ratios > 1.0 (self-report under-counts every single time; median 1.81,
    mean 4.35 -- right-skewed by investigation-heavy fires up to 14.2x). Dollar-weighted
    aggregate (sum(real)/sum(self) -- the statistic that matches how the constant is actually
    applied, to a SUM of a day's fires) = 2.155, rounds to 2.16.

    Full distribution + matched-fire list + a SEPARATE structural finding (near-zero-self-
    report no-op fires still cost ~$1.25 real each -- no multiplicative constant can fix that,
    0 x anything == 0) + the Max-subscription-vs-real-money verdict + a 32-day slot-admission
    replay (2.20 vs 2.16 changes ZERO days -- this is an accuracy fix, not a starvation fix):
    analysis/recommendations/conductor-cost-correction-measurement-2026-08-08.json
    """
    assert SELF_REPORT_CORRECTION == 2.16


def test_the_2x2_correction_is_actually_applied(tmp_path):
    """A $15 self-reported day must read as EXHAUSTED against a $30 cap ($15 x 2.2 = $33)."""
    led = _outcomes(tmp_path, [5.0, 5.0, 5.0])  # raw $15
    s = spend_today(DAY, led)
    assert s["raw_usd"] == 15.0
    assert s["corrected_usd"] == round(15.0 * SELF_REPORT_CORRECTION, 2)
    res = check(DAY, _cfg(cap=30.0, fires=99), led)
    assert res["verdict"] == "EXHAUSTED", "naive (uncorrected) math would have said PROCEED here"


def test_uncorrected_reading_would_have_passed_same_data(tmp_path):
    """Explicitly pins the bug being prevented: raw $15 < $30, corrected $33 >= $30."""
    led = _outcomes(tmp_path, [15.0])
    s = spend_today(DAY, led)
    assert s["raw_usd"] < 30.0 <= s["corrected_usd"]


# ------------------------------------------------------- proceed / exhaust behaviour
def test_fresh_day_proceeds(tmp_path):
    res = check(DAY, _cfg(), _outcomes(tmp_path, []))
    assert res["verdict"] == "PROCEED"
    assert res["fires"] == 0


def test_under_cap_proceeds(tmp_path):
    res = check(DAY, _cfg(cap=100.0, fires=99), _outcomes(tmp_path, [3.0, 3.0]))
    assert res["verdict"] == "PROCEED"


def test_fire_count_cap_independently_exhausts(tmp_path):
    """Even with trivial cost, too many fires stops the night."""
    res = check(DAY, _cfg(cap=10_000.0, fires=3), _outcomes(tmp_path, [0.01] * 5))
    assert res["verdict"] == "EXHAUSTED"
    assert "fires" in res["reason"]


def test_disabled_config_always_proceeds(tmp_path):
    res = check(DAY, _cfg(cap=0.01, fires=1, enabled=False), _outcomes(tmp_path, [99.0] * 9))
    assert res["verdict"] == "PROCEED"


# ------------------------------------------------------- fail-open contract
def test_missing_ledger_fails_open(tmp_path):
    res = check(DAY, _cfg(), tmp_path / "nope.jsonl")
    assert res["verdict"] == "PROCEED", "a governor must never block on its own missing telemetry"


def test_garbled_rows_are_skipped_not_fatal(tmp_path):
    p = tmp_path / "conductor-outcomes.jsonl"
    p.write_text("{broken\n" + json.dumps({"fired_at": f"{DAY}T01:00:00", "cost_usd": "NaNish"})
                 + "\n" + json.dumps({"fired_at": f"{DAY}T02:00:00", "cost_usd": 2.0}) + "\n",
                 encoding="utf-8")
    s = spend_today(DAY, p)
    assert s["fires"] == 2 and s["raw_usd"] == 2.0


def test_missing_config_uses_safe_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.json")
    assert cfg["daily_cap_usd"] > 0 and cfg["max_fires"] > 0 and cfg["enabled"] is True


def test_other_days_do_not_count(tmp_path):
    p = tmp_path / "conductor-outcomes.jsonl"
    p.write_text(json.dumps({"fired_at": "2026-07-24T02:00:00", "cost_usd": 500.0}) + "\n",
                 encoding="utf-8")
    assert spend_today(DAY, p)["fires"] == 0


# ------------------------------------------------------- pacing (LANE-A-UNSTARVE-CONDUCTOR)
def _outcomes_at(tmp_path: Path, rows) -> Path:
    """Like `_outcomes` but with explicit per-row (fired_at, cost_usd) pairs -- needed to
    replay a REAL chronological sequence of fires within one ET day."""
    p = tmp_path / "conductor-outcomes.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for fired_at, cost in rows:
            fh.write(json.dumps({"fired_at": fired_at, "task_id": "T", "cost_usd": cost}) + "\n")
    return p


def _pacing_cfg(cap=30.0, expected=4, floor=2.0, max_fires=99):
    return {"daily_cap_usd": cap, "max_fires": max_fires, "enabled": True,
            "expected_fires_per_day": expected, "min_allowance_usd": floor}


def test_first_fire_of_day_gets_generous_carry_over_allowance(tmp_path):
    """No special-case branch for fire #1 -- the SAME reservation formula must still leave it
    nearly the whole cap (only a token reserve held back for the other nominal slots)."""
    led = _outcomes(tmp_path, [])  # nothing has fired yet today
    res = check(DAY, _pacing_cfg(cap=30.0, expected=4, floor=2.0), led)
    assert res["verdict"] == "PROCEED"
    # remaining_slots = max(4-0,1)=4, reserve=(4-1)*2=6, allowance=30-6=24 -- most of the cap,
    # with zero special-casing for k==0 in the implementation.
    assert res["remaining_slots"] == 4
    assert res["reserve_for_future_usd"] == 6.0
    assert res["allowance_usd"] == 24.0


def test_pacing_allowance_shrinks_as_slots_are_consumed(tmp_path):
    # SELF_REPORT_CORRECTION re-measured 2.2 -> 2.16 on 2026-08-08 (CONDUCTOR-BUDGET-ARITHMETIC);
    # the arithmetic below is dynamically dependent on the constant via check()/spend_today(),
    # so these literals track whatever SELF_REPORT_CORRECTION currently is, not a fixed 2.2.
    led = _outcomes(tmp_path, [3.0])  # 1 fire done, raw $3 -> corrected $3*2.16=$6.48
    res = check(DAY, _pacing_cfg(cap=30.0, expected=4, floor=2.0), led)
    assert res["verdict"] == "PROCEED"
    # remaining_slots = 4-1=3, reserve=(3-1)*2=4, allowance=(30-6.48)-4=19.52
    assert res["remaining_slots"] == 3
    assert res["reserve_for_future_usd"] == 4.0
    assert res["allowance_usd"] == round((30.0 - 3.0 * SELF_REPORT_CORRECTION) - 4.0, 2)


def test_pacing_blocks_before_reservation_dips_below_floor(tmp_path):
    """A fire whose paced allowance has fallen under the floor is EXHAUSTED even though the
    raw cumulative spend has NOT yet hit the hard cap -- the actual pacing behavior."""
    led = _outcomes(tmp_path, [10.0, 10.0])  # 2 fires, raw $20 -> corrected $44 (already >cap,
    # so use a bigger cap here specifically to isolate the PACING gate from the hard-cap gate)
    res = check(DAY, _pacing_cfg(cap=100.0, expected=3, floor=5.0), led)
    # remaining_slots = 3-2=1, reserve=(1-1)*5=0, allowance=(100-44)-0=56 -- still fine, PROCEED
    assert res["verdict"] == "PROCEED"
    led2 = _outcomes(tmp_path, [10.0, 10.0, 10.0])  # 3 fires now, corrected=66
    res2 = check(DAY, _pacing_cfg(cap=68.0, expected=3, floor=5.0), led2)
    # remaining_slots = max(3-3,1)=1, reserve=0, allowance=68-66=2 < floor(5) -> pacing-blocked
    assert res2["verdict"] == "EXHAUSTED"
    assert "pacing" in res2["reason"]


def test_pacing_never_produces_negative_allowance_or_reserve(tmp_path):
    led = _outcomes(tmp_path, [500.0])  # wildly over cap
    res = check(DAY, _pacing_cfg(cap=30.0, expected=4, floor=2.0), led)
    assert res["verdict"] == "EXHAUSTED"  # hard cap catches this first
    assert res["allowance_usd"] >= 0.0
    assert res["reserve_for_future_usd"] >= 0.0


def test_pacing_remaining_slots_floors_at_one_past_expected_count(tmp_path):
    led = _outcomes(tmp_path, [0.01] * 10)  # far more fires today than expected_fires_per_day
    res = check(DAY, _pacing_cfg(cap=30.0, expected=3, floor=2.0, max_fires=999), led)
    assert res["remaining_slots"] == 1


def test_min_allowance_zero_disables_pacing_but_keeps_cap_and_fire_count(tmp_path):
    led = _outcomes(tmp_path, [10.0, 10.0])  # corrected 44 < cap 100, would pacing-block at
    # floor>0 with a tight expected count, but floor=0 must never block
    res = check(DAY, _pacing_cfg(cap=100.0, expected=2, floor=0.0), led)
    assert res["verdict"] == "PROCEED"
    assert res["allowance_usd"] >= 0.0


def test_pacing_config_missing_new_keys_falls_back_to_defaults(tmp_path):
    """Old-style config dicts (pre-dating this fix, e.g. hand-authored) that lack
    expected_fires_per_day/min_allowance_usd must not KeyError -- they fall back to
    DEFAULTS, exactly like every other optional key in this module."""
    led = _outcomes(tmp_path, [])
    old_style_cfg = {"daily_cap_usd": 30.0, "max_fires": 4, "enabled": True}
    res = check(DAY, old_style_cfg, led)
    assert res["verdict"] == "PROCEED"
    assert res["expected_fires_per_day"] == DEFAULTS["expected_fires_per_day"]
    assert res["min_allowance_usd"] == DEFAULTS["min_allowance_usd"]


# ------------------------------------------------------- the real incident, replayed (step 4)
# Real conductor-outcomes.jsonl rows, quoted verbatim (cost_usd only; timestamps kept, task_id
# dropped) for ET-day 2026-08-08 -- a Gamma_ConductorWake-triggered escalation cluster:
#   2026-08-08T04:08:40Z  cost 3.90   (EOD-FLATTEN-LLM-PROMPT-EXIT1)      -> 00:08 ET
#   2026-08-08T05:32:02Z  cost 9.35   (VBS-WRAPPER-EXIT-CODE-4TH-PASS)    -> 01:32 ET
#   2026-08-08T06:07:17Z  cost 2.80   (BUDGET-ROSTER-AUDIT-MAXBUDGETUSD)  -> 02:07 ET
# raw sum $16.05, corrected (x2.2) $35.31 -- OVER the real $30 cap, matching the live
# QUIET-BUDGET-EXHAUSTED-2026-08-08-0400 row's "corrected 5.31>=0 cap"-truncated-log but the
# real math (raw sums, x2.2) below.
REAL_INCIDENT_ROWS = [
    ("2026-08-08T04:08:40+00:00", 3.90),
    ("2026-08-08T05:32:02+00:00", 9.35),
    ("2026-08-08T06:07:17+00:00", 2.80),
]
REAL_INCIDENT_DAY = "2026-08-08"


def _old_style_check(day, cfg, path):
    """Reference re-implementation of the PRE-FIX gate (flat cumulative cap + fire-count only,
    no pacing) -- used ONLY in this comparison test to quote a real before/after, not shipped
    production code."""
    s = spend_today(day, path)
    if s["corrected_usd"] >= float(cfg["daily_cap_usd"]):
        return "EXHAUSTED"
    if s["fires"] >= int(cfg["max_fires"]):
        return "EXHAUSTED"
    return "PROCEED"


def test_real_incident_2026_08_08_old_vs_new_pacing(tmp_path):
    """PROVE IT (step 4): replay today's REAL cost sequence through OLD vs NEW logic and quote
    how many of the day's fire slots each leaves usable.

    NOTE (2026-08-08, CONDUCTOR-BUDGET-ARITHMETIC): SELF_REPORT_CORRECTION was re-measured
    2.2 -> 2.16 the same day this incident happened. The dollar figures asserted below are
    computed DYNAMICALLY off the live constant (via spend_today()/check()), so they now read
    $34.67/$28.62 rather than the incident's own originally-logged $35.31/$29.15 (those were
    computed under the 2.2 that was live in production AT THE TIME -- see REAL_INCIDENT_ROWS'
    docstring above, left unchanged as an accurate historical quote). The qualitative
    conclusion this test proves (OLD flat-cap gate lets the breach through; NEW pacing blocks
    fire 3 before it spends) is unaffected by the constant's exact value."""
    cfg = _pacing_cfg(cap=30.0, expected=4, floor=2.0, max_fires=99)

    # Build the ledger incrementally, exactly as it accrues in production (each fire's check
    # only sees the fires that happened STRICTLY BEFORE it).
    old_verdicts, new_verdicts = [], []
    for i in range(len(REAL_INCIDENT_ROWS)):
        prior_rows = REAL_INCIDENT_ROWS[:i]
        led = _outcomes_at(tmp_path, prior_rows)
        old_verdicts.append(_old_style_check(REAL_INCIDENT_DAY, cfg, led))
        new_verdicts.append(check(REAL_INCIDENT_DAY, cfg, led)["verdict"])

    # OLD: pure first-come-first-served against the flat cap -- all 3 fires proceed (cumulative
    # corrected only crosses the $30 cap AFTER fire 3 finishes, so fire 3's own check, which
    # only sees fires 1+2's cumulative $29.15, still says PROCEED).
    assert old_verdicts == ["PROCEED", "PROCEED", "PROCEED"], (
        f"OLD logic verdicts (quote): {old_verdicts} -- matches the real incident, all 3 "
        f"fires ran, final corrected spend breached the cap AFTER the fact ($35.31 > $30)")

    # NEW: fire 3's pacing reservation (2 nominal slots left incl. this one after 2 fires
    # already spent $29.15 of $30 -- remaining_budget $0.85 < floor $2.00) blocks it BEFORE it
    # spends, so the day's cumulative spend never exceeds the cap at all.
    assert new_verdicts == ["PROCEED", "PROCEED", "EXHAUSTED"], (
        f"NEW logic verdicts (quote): {new_verdicts}")

    old_final = spend_today(REAL_INCIDENT_DAY, _outcomes_at(tmp_path, REAL_INCIDENT_ROWS))
    new_final = spend_today(REAL_INCIDENT_DAY,
                             _outcomes_at(tmp_path, REAL_INCIDENT_ROWS[:2]))  # fire 3 blocked,
                             # never spends, so it never appends a real-cost row under NEW
    expected_old = round(sum(c for _, c in REAL_INCIDENT_ROWS) * SELF_REPORT_CORRECTION, 2)
    expected_new = round(sum(c for _, c in REAL_INCIDENT_ROWS[:2]) * SELF_REPORT_CORRECTION, 2)
    assert old_final["corrected_usd"] == expected_old, f"OLD final corrected spend: ${old_final['corrected_usd']}"
    assert new_final["corrected_usd"] == expected_new, f"NEW final corrected spend: ${new_final['corrected_usd']}"
    assert old_final["corrected_usd"] > 30.0, "OLD breaches the hard cap"
    assert new_final["corrected_usd"] <= 30.0, "NEW never breaches the hard cap"


def test_pacing_resets_at_et_day_rollover(tmp_path):
    """Guard (step 5): pacing state must not leak across the ET day boundary -- reuses the
    SAME cross-midnight shape as test_late_night_fire_counts_for_its_own_et_day_not_the_next
    (a 20:30 ET fire on day D has a UTC calendar date of D+1), but asserts on the PACING
    fields specifically (remaining_slots/allowance), not just the raw fire count."""
    # 20:30 ET fire on 2026-07-28 -- UTC date already 2026-07-29 (ET=UTC-4).
    led = _outcomes_at(tmp_path, [("2026-07-29T00:30:52+00:00", 20.0)])
    cfg = _pacing_cfg(cap=30.0, expected=4, floor=2.0, max_fires=99)

    same_day = check("2026-07-28", cfg, led)
    assert same_day["fires"] == 1
    assert same_day["remaining_slots"] == 3  # 4 - 1 fire already counted against day D

    next_day = check("2026-07-29", cfg, led)
    assert next_day["fires"] == 0, "must not leak the prior evening's fire into the new day"
    assert next_day["remaining_slots"] == 4, "pacing must start the new day with a full reset"
    assert next_day["allowance_usd"] == 24.0, "same generous first-fire allowance as any fresh day"


def test_pacing_would_have_saved_a_larger_hypothetical_fire3(tmp_path):
    """The real fire 3 only cost $2.80 -- small. Pacing's actual protective value is against a
    LARGER one: prove a hypothetical $9 fire 3 would ALSO have been blocked pre-spend (whereas
    OLD logic would have let it through, pushing the breach from +$5.31 to +$14.71)."""
    cfg = _pacing_cfg(cap=30.0, expected=4, floor=2.0, max_fires=99)
    prior_rows = REAL_INCIDENT_ROWS[:2]  # the 2 real early fires, corrected $29.15
    led = _outcomes_at(tmp_path, prior_rows)
    assert _old_style_check(REAL_INCIDENT_DAY, cfg, led) == "PROCEED", (
        "OLD logic would ALSO admit a much bigger fire 3 here -- no size-awareness at all")
    assert check(REAL_INCIDENT_DAY, cfg, led)["verdict"] == "EXHAUSTED", (
        "NEW logic blocks admission regardless of how big fire 3 would have been")


# ------------------------------------------------------- cross-midnight ET/UTC boundary (bug fix)
# 2026-07-29: the self-audit flagged "conductor firing far more than max_fires" 3 nights running
# (07-27/07-28/07-29). Root cause: ET is UTC-4 (EDT), so the scheduled 20:30 ET evening fire on
# day D writes `fired_at` with a UTC CALENDAR DATE of D+1 (20:30 ET + 4h = 00:30 UTC next day).
# The old substring-match code counted that row against BOTH D's own check (correct, it ran
# then) AND D+1's very first check the next morning (wrong -- it leaked forward), so every ET
# day silently started already "1 fire spent" before its own first legitimate tick.
def test_evening_et_fire_does_not_leak_into_next_day():
    """A 20:30 ET fire on 07-28 (fired_at UTC date 07-29) must count toward 07-28's budget,
    NOT 07-29's -- pins the exact incident shape (3-night repeat self-audit flag)."""
    evening_et_fire_utc = "2026-07-29T00:30:52+00:00"  # 20:30 ET on 2026-07-28
    assert _stamp_to_et_date_helper(evening_et_fire_utc) == "2026-07-28"


def test_late_night_fire_counts_for_its_own_et_day_not_the_next(tmp_path):
    p = tmp_path / "conductor-outcomes.jsonl"
    # The 20:30 ET fire on 07-28 -- UTC date is already 07-29.
    p.write_text(json.dumps({"fired_at": "2026-07-29T00:30:52+00:00", "cost_usd": 1.0}) + "\n",
                 encoding="utf-8")
    assert spend_today("2026-07-28", p)["fires"] == 1, "must count toward the ET day it fired in"
    assert spend_today("2026-07-29", p)["fires"] == 0, "must NOT leak forward into the next ET day"


def test_early_morning_utc_fire_counts_for_previous_et_day():
    """Symmetric case: a fire just after UTC midnight (~20:xx ET the evening before) must map
    back to the EARLIER ET date, not the UTC date."""
    assert _stamp_to_et_date_helper("2026-07-26T02:15:00+00:00") == "2026-07-25"


def _stamp_to_et_date_helper(stamp: str) -> str:
    import conductor_budget as cb
    return cb._stamp_to_et_date(stamp)


# ------------------------------------------------------- CLI exit codes (what conductor.md reads)
def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    import conductor_budget as cb

    monkeypatch.setattr(cb, "OUTCOMES", _outcomes(tmp_path, []))
    monkeypatch.setattr(cb, "CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(cb, "STATUS_OUT", tmp_path / "status.json")
    assert main(["--check", "--date", DAY]) == EXIT_PROCEED

    monkeypatch.setattr(cb, "OUTCOMES", _outcomes(tmp_path, [50.0] * 3))
    assert main(["--check", "--date", DAY]) == EXIT_EXHAUSTED
    capsys.readouterr()


def test_status_never_blocks(tmp_path, monkeypatch, capsys):
    import conductor_budget as cb

    monkeypatch.setattr(cb, "OUTCOMES", _outcomes(tmp_path, [99.0] * 9))
    monkeypatch.setattr(cb, "CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(cb, "STATUS_OUT", tmp_path / "status.json")
    assert main(["--status", "--date", DAY]) == EXIT_PROCEED
    capsys.readouterr()


# ------------------------------------------------------- pacing default reverted (2026-08-08 audit)
# A full chronological replay of all 32 real ET-days in conductor-outcomes.jsonl (279 rows) swept
# min_allowance_usd across {0,1,2,3,3.25,5,6.89,7.15,7.69,8,10,15} (6.89/7.15 = measured corrected
# mean/median real-fire cost) and found ZERO rescues at EVERY floor tested, while extra_blocks
# (pacing blocking a fire the old flat-cap gate would have admitted) strictly grows with the
# floor: 2 extra_blocks at floor=2.0 (the shipped-then-reverted default), rising to 101 at
# floor=15.0. Admission-only gating structurally cannot rescue a later slot -- an admitted fire's
# real spend is never bounded by the reservation, so recalibrating the floor cannot fix this; it
# can only make extra_blocks worse. min_allowance_usd now defaults to 0.0 (pacing disabled),
# restoring pure flat-cap + max_fires behavior, until a genuine per-fire $ cap exists inside
# conductor.md (the only mechanism that bounds an admitted fire's spend rather than merely gating
# admission before it).
def test_default_min_allowance_usd_is_zero_pacing_disabled():
    assert DEFAULTS["min_allowance_usd"] == 0.0, (
        "pacing must be OFF by default -- the 2026-08-08 replay found it never rescues a slot "
        "at any floor and only ever adds extra blocks vs. the old flat-cap gate")


def test_pacing_with_zero_floor_never_blocks_regardless_of_spend_shape():
    """Property check backing the replay finding: with floor=0.0, `_pacing()`'s `blocked`
    condition (`allowance < floor`) can never be True, because `allowance` is always clamped
    to >= 0.0 -- i.e. pacing is a true no-op at the default, for ANY spend/fire-count shape,
    not just the shapes present in today's ledger snapshot."""
    import conductor_budget as cb

    for fires_so_far in (0, 1, 4, 10, 50):
        for corrected_spend in (0.0, 5.0, 29.99, 30.0, 100.0):
            s = {"fires": fires_so_far, "corrected_usd": corrected_spend}
            cfg = dict(DEFAULTS)  # shipped defaults -- min_allowance_usd=0.0
            info = cb._pacing(s, cfg)
            assert info["pacing_blocked"] is False, (
                f"floor=0.0 blocked admission at fires={fires_so_far} "
                f"corrected=${corrected_spend} -- pacing must be inert at the default")


def test_default_config_never_diverges_from_old_flat_cap_gate_on_real_ledger():
    """Guard against re-introducing the falsified regression (proves it on the REAL, on-disk
    ledger, not just a synthetic fixture): replay conductor-outcomes.jsonl chronologically per
    ET day under the ACTUAL shipped DEFAULTS and confirm `check()`'s admission decision matches
    the pre-pacing flat-cap+max_fires-only gate on every row. With min_allowance_usd=0.0 this is
    a mathematical certainty (see test above), but this replay is the same methodology + the
    same evidence source the audit used, so a future change to DEFAULTS that reintroduces
    divergence fails loudly here."""
    import conductor_budget as cb

    if not cb.OUTCOMES.exists():
        return  # nothing to replay in this environment -- not a governor failure (C7)

    rows = []
    with open(cb.OUTCOMES, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)

    by_day: dict = {}
    for r in rows:
        stamp = str(r.get("fired_at") or r.get("ts_et") or "")
        et_date = cb._stamp_to_et_date(stamp)
        if et_date is None:
            continue
        by_day.setdefault(et_date, []).append((stamp, r))

    cfg = dict(DEFAULTS)  # the ACTUAL shipped defaults, no test-only overrides
    mismatches = []
    for day, day_rows in by_day.items():
        day_rows.sort(key=lambda t: t[0])
        raw_cum = 0.0
        fires_so_far = 0
        for stamp, row in day_rows:
            s = {"fires": fires_so_far, "raw_usd": round(raw_cum, 2),
                 "corrected_usd": round(raw_cum * SELF_REPORT_CORRECTION, 2)}
            old_ok = (s["corrected_usd"] < cfg["daily_cap_usd"]) and (s["fires"] < cfg["max_fires"])
            new_ok = old_ok and not cb._pacing(s, cfg)["pacing_blocked"]
            if old_ok != new_ok:
                mismatches.append((day, stamp))
            try:
                raw_cum += float(row.get("cost_usd") or 0.0)
            except (TypeError, ValueError):
                pass
            fires_so_far += 1

    assert mismatches == [], (
        f"pacing under the shipped DEFAULTS diverged from the old flat-cap gate on "
        f"{len(mismatches)} real rows -- expected zero divergence: {mismatches[:10]}")


def test_status_file_written_with_pacing_fields(tmp_path, monkeypatch, capsys):
    """Step 3: the spend-shape record (slots_used/slots_remaining/allowance_next) must land
    on disk after a --check fire, without check() itself having any file-write side effect."""
    import conductor_budget as cb

    status_path = tmp_path / "status.json"
    monkeypatch.setattr(cb, "OUTCOMES", _outcomes(tmp_path, [3.0]))
    monkeypatch.setattr(cb, "CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(cb, "STATUS_OUT", status_path)
    main(["--check", "--date", DAY])
    capsys.readouterr()
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["day"] == DAY
    assert payload["slots_used"] == 1
    assert payload["slots_remaining"] >= 1
    assert "allowance_next_usd" in payload and "reserve_for_future_usd" in payload


# ----------------------------------- CONDUCTOR-GATE-PRECHECK stale-prose fix (2026-08-08) ------
# Companion follow-up to the cost-correction measurement: the measurement doc's own "Known
# stale prose" section flagged automation/prompts/conductor.md's STAGE-0 text and
# setup/scripts/autonomy_report.py's module docstring as still citing the OLD "x2.2" factor
# after SELF_REPORT_CORRECTION was re-measured to 2.16. These tests pin the fix so a future
# edit can't silently reintroduce the stale figure. They also pin that run-conductor.ps1's
# new pre-check (setup/scripts/run-conductor.ps1, CONDUCTOR-GATE-PRECHECK) is documented in
# conductor.md's STAGE 0 prose, so a reader of the prompt isn't left thinking the in-prompt
# gate is still the primary/first check for the AFTERHOURS `conductor` task.
CONDUCTOR_MD = ROOT / "automation" / "prompts" / "conductor.md"
AUTONOMY_REPORT_PY = ROOT / "setup" / "scripts" / "autonomy_report.py"


def test_conductor_md_stage0_prose_cites_2_16_not_stale_2_2():
    src = CONDUCTOR_MD.read_text(encoding="utf-8")
    assert "×2.16" in src, (
        "conductor.md STAGE 0 must cite the re-measured 2.16x correction factor")
    assert "corrects your self-report ×2.2." not in src, (
        "the OLD stale '×2.2.' sentence must not survive -- it was flagged by the "
        "2026-08-08 measurement doc as stale prose")


def test_autonomy_report_docstring_cites_2_16_correction():
    src = AUTONOMY_REPORT_PY.read_text(encoding="utf-8")
    assert "2.16x self-report correction" in src, (
        "autonomy_report.py's module docstring must cite the re-measured 2.16x factor "
        "(flagged as stale '2.2x' prose by the 2026-08-08 measurement doc)")
    # The historical incident narrative (raw $16.05 x2.2 = $35.31) is an accurate quote of
    # what the constant WAS at the moment that real incident happened -- it must survive
    # unchanged, this test only pins that the CURRENT/general-mechanism sentence is fixed.
    assert "raw $16.05 x2.2 = $35.31" in src, (
        "the historical incident quote must not be rewritten -- it describes what actually "
        "happened under the constant that was live AT THE TIME, not the current value")


def test_conductor_md_stage0_documents_the_wrapper_precheck_frontrun():
    """CONDUCTOR-GATE-PRECHECK (2026-08-08): run-conductor.ps1 now runs conductor_budget.py
    --check BEFORE spawning this Claude session at all, for the AFTERHOURS `conductor` task.
    The in-prompt STAGE 0 gate stays mandatory (belt-and-braces + the only gate for
    conductor-weekend), but a reader must not be left thinking it's still the FIRST check."""
    src = CONDUCTOR_MD.read_text(encoding="utf-8")
    stage0_start = src.index("0. **BUDGET GATE")
    stage1_start = src.index("1. **MARKET-HOURS GATE")
    stage0_text = src[stage0_start:stage1_start]
    assert "run-conductor.ps1" in stage0_text
    assert "belt-and-braces" in stage0_text
    assert "ConductorWeekend" in stage0_text or "conductor-weekend" in stage0_text
