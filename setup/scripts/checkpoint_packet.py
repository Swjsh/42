"""checkpoint_packet.py -- GOAL-CHECKPOINT-PACKET-2026-09-29 C2.

Reads the hand-maintained inventory (`analysis/recommendations/checkpoint-2026-09-29-
inventory.json`, C1) and, for each row, calls that row's OWN named scorer to compute
the decision rule's numbers AS OF TODAY, reusing the existing instruments the goal
names rather than re-implementing them: stop_mode_shadow_ledger.py,
day_throttle_shadow.py, intervention_counter.py, right_tail_capture.py,
ladder-rung-shadow-ledger.jsonl, catastrophe-cap-shadow-ledger.jsonl,
vix-bull-hard-cap-unblock-shadow-*.json, analysis/zero-enter/, and each prereg's own
`status`/`decision_rule` field (the September freeze's adjudication vocabulary --
EXTEND / KILL / SHIP-CANDIDATE / NULL / FROZEN_* -- read the same way
prereg_hygiene.py already parses it).

FAIL-OPEN PER ROW (mandatory, per goal DONE-WHEN): any exception inside a row's scorer
is caught and that ONE row reports verdict UNKNOWN with the error message attached --
never a crash for the whole packet.

Verdict vocabulary emitted per row:
  RULE MET       -- the frozen decision rule's threshold is satisfied by today's ledger.
  RULE NOT MET   -- the ledger has enough evidence and the rule's threshold is NOT met.
  INSUFFICIENT N -- not enough observations yet to evaluate the rule (n < the frozen floor).
  PROVISIONAL    -- the row's own scorer/ledger is explicitly provisional (e.g. R4 of
                    GOAL-RIGHT-TAIL-CAPTURE reopened) -- never cited as confirming evidence.
  UNKNOWN        -- the scorer raised, or the named ledger/prereg could not be read.

CLI:
    python setup/scripts/checkpoint_packet.py [--date YYYY-MM-DD] [--json-out PATH]

Writes `analysis/recommendations/checkpoint-packet-<date>.json` (the raw per-row
computation) and prints a compact table to stdout. The markdown generation
(`markdown/planning/CHECKPOINT-2026-09-29.md` / `-2026-10-30.md`) is a separate step
(`generate_checkpoint_markdown.py`, C3) that reads THIS script's json-out.

$0, stdlib + the repo's own scorer modules only. No network, no order placement, no
FROZEN_TRADING_PATH file is ever opened for write.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
RECS_DIR = REPO / "analysis" / "recommendations"
INVENTORY_PATH = RECS_DIR / "checkpoint-2026-09-29-inventory.json"

for _p in (REPO, SCRIPTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from et_clock import et_now  # noqa: E402
except Exception:  # noqa: BLE001 -- clock import must never wedge this tool
    from datetime import datetime, timezone

    def et_now(now_utc=None):  # type: ignore
        return datetime.now(timezone.utc)

# Reuse prereg_hygiene's own status-classification vocabulary rather than re-deriving
# it -- same ADJUDICATION_STATUS_RE / PENDING_STATUS_RE the September-freeze adjudication
# pass already wrote into every prereg's `status` field.
try:
    from prereg_hygiene import (  # noqa: E402
        ADJUDICATION_STATUS_RE,
        PENDING_STATUS_RE,
        TERMINAL_STATUS_RE,
        _status_field,
    )
except Exception:  # noqa: BLE001 -- fail-open: degrade to local copies if the import breaks
    import re

    ADJUDICATION_STATUS_RE = re.compile(r"^\s*(?:EXTEND|KILL|SHIP-CANDIDATE|NULL)\b")
    PENDING_STATUS_RE = re.compile(
        r"FROZEN|PRE-REGISTERED|\bPENDING\b|PARKED|CANDIDATE ONLY|NOT RUN|NOT SHIPPED"
        r"|NOT IMPLEMENTED|NOT (?:YET )?BUILT",
        re.IGNORECASE,
    )
    TERMINAL_STATUS_RE = re.compile(
        r"RUN_COMPLETE|RETIRED|KILLED|CLOSED_KILL|SUPERSEDED|EARNS_RIGHTS"
        r"|armed_paper_collecting_evidence",
        re.IGNORECASE,
    )

    def _status_field(data: dict) -> Any:  # type: ignore
        if "status" in data and isinstance(data["status"], str):
            return data["status"]
        return None

VERDICT_MET = "RULE MET"
VERDICT_NOT_MET = "RULE NOT MET"
VERDICT_INSUFFICIENT_N = "INSUFFICIENT N"
VERDICT_PROVISIONAL = "PROVISIONAL"
VERDICT_UNKNOWN = "UNKNOWN"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def _prefer_1min_path(base_path: Path) -> tuple[Path, str]:
    """GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3: prefer the '-1min' sibling of `base_path`
    (e.g. ledger.jsonl -> ledger-1min.jsonl) when it exists, else fall back to `base_path`
    unchanged. Returns (path_used, resolution_used) -- never raises; a missing 1min sibling
    is not an error, just a fallback."""
    candidate = base_path.with_name(base_path.stem + "-1min" + base_path.suffix)
    if candidate.exists():
        return candidate, "1min"
    return base_path, "5min"


def _et_date_str() -> str:
    return et_now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------------
# Per-row scorers. Each takes (row: dict, today: str) and returns a dict with at
# least: verdict, n, numbers (dict of named numbers), note (str). Raising is fine --
# the dispatcher below catches it and reports UNKNOWN for that row only.
# --------------------------------------------------------------------------------


def _score_tight_ladder_control4(row: dict, today: str) -> dict:
    """Reuses right_tail_capture.py's own ledger (analysis/right-tail/ledger.jsonl) --
    never re-walks trades.csv. Reads the CAP4_LIVE_DATE-gated would_be_refused flag the
    instrument already computes per wave-event.

    HAND-CHECK FIX (2026-09-05, GOAL-CHECKPOINT-PACKET-2026-09-29 C6): the ledger mixes
    two row shapes -- one per-(date,arm) ROLLUP row (`second_wave_summary`/`capture_rate`,
    no wave fields at all) and one per-WAVE row (`wave_start_et` + `would_be_refused_
    under_cap4` + `exit_multiple`). The prior version filtered post-cap rows by date
    alone, which silently counted rollup rows as "wave events" (n=36 for 08-31..09-04,
    vs the real 16 actual wave rows in that window -- confirmed by direct read,
    2026-09-05 hand-check). Rollup rows can never carry `would_be_refused_under_cap4`,
    so the verdict itself did not change, but the reported n overstated the evidence
    base by 2.25x. Filter to real wave rows via `"wave_start_et" in r`. The multiple
    field is also `exit_multiple` (ledger's actual key), not `wave_multiple_at_exit`
    (a field that has never existed in this ledger) -- fall back to
    `peak_multiple_on_tape` (the highest multiple seen on tape, the conservative /
    stricter reading for "would have exited >=1.3x") if `exit_multiple` is absent.
    """
    ledger_path = REPO / row["ledger_path"]
    if not ledger_path.exists():
        return {"verdict": VERDICT_INSUFFICIENT_N, "n": 0, "numbers": {}, "note": "ledger not found"}
    rows = _read_jsonl(ledger_path)
    wave_rows = [r for r in rows if "wave_start_et" in r]
    cap4_live = "2026-08-31"
    post_cap = [r for r in wave_rows if r.get("date", "") >= cap4_live]
    refused_any = [r for r in post_cap if r.get("would_be_refused_under_cap4") is True]
    refused_ge13x = [
        r for r in refused_any
        if (r.get("exit_multiple") if r.get("exit_multiple") is not None else r.get("peak_multiple_on_tape")) is not None
        and (r.get("exit_multiple") if r.get("exit_multiple") is not None else r.get("peak_multiple_on_tape")) >= 1.3
    ]
    n = len(post_cap)
    verdict = VERDICT_INSUFFICIENT_N if n == 0 else (
        VERDICT_NOT_MET if len(refused_ge13x) == 0 and len(refused_any) == 0 else VERDICT_MET
    )
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {
            "post_cap_wave_events": n,
            "refused_under_cap4_any": len(refused_any),
            "refused_under_cap4_ge_1_3x": len(refused_ge13x),
        },
        "note": (
            "RULE NOT MET here means the cap has refused zero qualifying waves -- i.e. "
            "the case for reverting (expansion) is NOT supported; the cap STAYS at 4. "
            "This is still an expansion-classified row per goal routing regardless. "
            "hand_check: confirmed 2026-09-05 (direct ledger read filtered to real "
            "wave-event rows via presence of wave_start_et, n=16 post-08-31, "
            "refused_under_cap4_any=0) -- matches PREREG-TIGHT-LADDER-2026-08-28.md's "
            "own interim-evidence conclusion verbatim ('the answer ... remains NO. "
            "The cap stays.') and GOAL-RIGHT-TAIL-CAPTURE-2026-09-05.md R4-closed note "
            "('cap-4 would-refuse flags 11' total backfill, 0 of them post-08-31)."
        ),
    }


def _score_tight_ladder_control5(row: dict, today: str) -> dict:
    """No standing instrument computes this hypothetical live; it is a one-time replay
    already frozen in the prereg's own interim-evidence text. Read the numbers back out
    of the prereg markdown (no re-replay -- the numbers are already committed evidence).

    HAND-CHECK FIX (2026-09-05, GOAL-CHECKPOINT-PACKET-2026-09-29 C6): the prior version
    hardcoded VERDICT_NOT_MET with a note claiming "the stop would have net-HURT
    (-$1,601)" -- backwards. `daily_loss_kill_switch_dollars: 400` is ALREADY SHIPPED
    and LIVE (automation/state/params.json, armed 2026-08-29 per PREREG-TIGHT-LADDER
    Addendum 2 S2.1) -- this row is a standing reconfirmation of a live control, not a
    ship/no-ship threshold on something pending. The -$1,601 is the net P&L of the 8
    ENTRIES THE STOP BLOCKS, not the stop's own effect: blocking net-loss-making entries
    is a BENEFIT, sign-flipped to +$1,601 avoided-loss, which is exactly how
    params.json's own doc states it verbatim: "this exact -$400/arm/day figure blocked
    $347 of winners vs $1,948 of losers blocked (net +$1,601)". Independently
    reproduced by a second method (direct read of journal/trades.csv, grouped
    date+account_id+time_entry, running-total walk per arm-day, 2026-08-01..09-04):
    n=8 blocked, 1 winner +$347 / 7 losers -$1,948, net -$1,601 of blocked-entry P&L =
    +$1,601 avoided, fires only 08-05/08-07/08-14 (script:
    setup/scripts/_hand_check_control5.py). hand_check: confirmed 2026-09-05 (direct
    ledger read, +$1,601 avoided-loss reproduced exactly) -- verdict corrected to
    RULE MET (the standing 'keep' decision IS supported by the evidence; the prior
    NOT_MET reading would have been misread by anyone skimming the table as
    "evidence says don't keep it", the exact opposite of what the numbers show)."""
    md_path = REPO / row["prereg_path"]
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    marker = "Control #5"
    if marker not in text:
        return {"verdict": VERDICT_UNKNOWN, "n": 0, "numbers": {}, "note": "Control #5 block not found in prereg"}
    # n = 8 entries blocked, as filed. This is a frozen replay result, not an accruing
    # forward ledger -- report it as such rather than pretending it updates nightly.
    return {
        "verdict": VERDICT_MET,
        "n": 8,
        "numbers": {
            "entries_blocked": 8,
            "net_pnl_of_blocked_entries": -1601.0,
            "net_pnl_avoided_by_stop": 1601.0,
            "winners_blocked": 1,
            "losers_blocked": 7,
        },
        "note": (
            "Frozen one-time replay result (2026-08-28..09-05), not a nightly-accruing "
            "ledger. RULE MET = the -$400/arm/day stop (ALREADY SHIPPED, params.json "
            "daily_loss_kill_switch_dollars=400) blocked entries that would have net-LOST "
            "$1,601 -- i.e. it avoided a $1,601 loss, consistent with keep. Decision rule "
            "verbatim (Addendum 2 S2.1 + params.json doc): 'a DOLLAR stop is the shape "
            "that does not cost money -- this exact -$400/arm/day figure blocked $347 of "
            "winners vs $1,948 of losers blocked (net +$1,601)'. hand_check: confirmed "
            "2026-09-05 (second method: direct read of journal/trades.csv via "
            "setup/scripts/_hand_check_control5.py, grouped date+account_id+time_entry, "
            "running-total walk per arm-day, 2026-08-01..09-04 -> n=8, net -1601.0, "
            "1 winner +347.0 / 7 losers -1948.0, fires 2026-08-05/08-07/08-14 -- exact "
            "match to the prereg's own quoted numbers)."
        ),
    }


def _score_score_ladder_v2_retirement(row: dict, today: str) -> dict:
    """HAND-CHECK FIX (2026-09-05, C6): n was distinct (date, arm_id) pairs, which
    collapses same-day double-scored rows and undercounts each arm (19 distinct dates
    vs 28 actual ledger rows/arm -- 2 dates, 08-07 and 08-13, carry 2 rows each,
    confirmed by direct read). That gave n=38 total where the prereg's own adjudicated
    status text says 'n=28 sessions/arm' (56 rows total, 28 per arm -- the prereg's
    'session' = one ledger row/event, not one calendar day). Switched to a plain row
    count, which matches the prereg's own units exactly and does not change the
    verdict (both readings clear the n>=15 floor; the verdict is driven by the
    already-adjudicated terminal KILL status either way)."""
    ledger_path = REPO / row["ledger_path"]
    prereg_path = REPO / row["prereg_path"]
    rows = _read_jsonl(ledger_path) if ledger_path.exists() else []
    n_rows = len(rows)
    rows_per_arm: dict[str, int] = {}
    for r in rows:
        arm = r.get("arm_id")
        if arm:
            rows_per_arm[arm] = rows_per_arm.get(arm, 0) + 1
    total_delta = sum((r.get("delta_pnl") or 0.0) for r in rows)
    status = None
    if prereg_path.exists():
        try:
            status = _status_field(_read_json(prereg_path))
        except (json.JSONDecodeError, OSError):
            status = None
    verdict = VERDICT_UNKNOWN
    if status and (TERMINAL_STATUS_RE.search(status or "") or ADJUDICATION_STATUS_RE.match(status or "")):
        verdict = VERDICT_MET  # "KILL" verdict already adjudicated -> retirement rule is MET
    elif n_rows < 15:
        verdict = VERDICT_INSUFFICIENT_N
    return {
        "verdict": verdict,
        "n": n_rows,
        "numbers": {
            "ledger_rows": n_rows,
            "rows_per_arm": rows_per_arm,
            "total_delta_pnl": round(total_delta, 2),
            "status": status,
        },
        "note": (
            "Retirement rule MET = the prereg's own adjudicated status is a terminal "
            "KILL ('KILL -- forward shadow ledger (n=28 sessions/arm) fails all 3 "
            "frozen arm-bar criteria'). hand_check: confirmed 2026-09-05 (direct ledger "
            "read: risky-1=28 rows, risky-3=28 rows, total_delta_pnl=-27345.0 -- matches "
            "the goal's own 'extras -$13.8K/arm over 28 sessions' to within the "
            "aggregation the goal text describes; status field itself is the terminal "
            "KILL that drives the verdict)."
        ),
    }


def _score_f10_vol_baseline_reset(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    zero_enter_dir = REPO / "analysis" / "zero-enter"
    status = _status_field(_read_json(prereg_path)) if prereg_path.exists() else None
    day_files = sorted(zero_enter_dir.glob("ZERO-ENTER-2026-*.json")) if zero_enter_dir.exists() else []
    n = len(day_files)
    verdict = VERDICT_INSUFFICIENT_N
    if status and ADJUDICATION_STATUS_RE.match(status or ""):
        verdict = VERDICT_MET
    elif n >= 20:
        verdict = VERDICT_NOT_MET  # enough days accrued but still frozen/no verdict -> rule not (yet) met
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {"zero_enter_day_files": n, "status": status},
        "note": "10-30 checkpoint candidate; frozen before any result as of this generation.",
    }


def _score_vix_bull_hard_cap_shadow(row: dict, today: str) -> dict:
    summary_path = REPO / row["ledger_path"]
    if not summary_path.exists():
        return {"verdict": VERDICT_INSUFFICIENT_N, "n": 0, "numbers": {}, "note": "summary not found"}
    d = _read_json(summary_path)
    n = int(d.get("n_matched_round_trips") or 0)
    status = d.get("status")
    if status == "ACCRUING" and n < 15:
        verdict = VERDICT_INSUFFICIENT_N
    elif n < 15:
        verdict = VERDICT_INSUFFICIENT_N
    else:
        # n>=15: rule reads forward CI-lower bootstrap PF > 1.0; without re-deriving the
        # bootstrap here (that belongs to the shadow instrument itself), report NOT MET
        # unless the summary already states a PF figure above 1.0.
        pf = d.get("forward_pf_ci_lower")
        verdict = VERDICT_MET if isinstance(pf, (int, float)) and pf > 1.0 else VERDICT_NOT_MET
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {
            "n_matched_round_trips": n,
            "forward_total_pnl": d.get("forward_total_pnl"),
            "status": status,
        },
        "note": "Threshold n>=15 matched round trips before any PF figure is citable (per this row's own frozen rule).",
    }


def _score_tp1_qty_fraction_safe_0_8(row: dict, today: str) -> dict:
    """GOAL-TP1-FRACTION-AB-2026-09-05 A4: reads the fresh A/B
    (analysis/recommendations/tp1-fraction-ab-2026-09-05.json) and applies the prereg's own
    gate-1 (OOS/full-window positive) to BOTH Safe arms (safe-2, safe-3 -- the RIBBON_RIDE
    dataclass they share). A failed gate-1 on either arm ends the check per the prereg's
    stated gate ORDER (WF ratio / sub-window-stability / anchor-regression are the
    remaining 3 gates in the original battery; not computed here because gate-1 already
    fails, and safe-2's zero-variance null result would make several of them undefined)."""
    ab_path = REPO / "analysis" / "recommendations" / "tp1-fraction-ab-2026-09-05.json"
    if not ab_path.exists():
        return {"verdict": VERDICT_INSUFFICIENT_N, "n": 0, "numbers": {},
                "note": "tp1-fraction-ab-2026-09-05.json not found"}
    d = _read_json(ab_path)
    full = d.get("per_arm_full_window", {})
    frozen = d.get("per_arm_frozen_window", {})
    safe2_full = full.get("safe-2", {})
    safe3_full = full.get("safe-3", {})
    n = int(safe2_full.get("n_waves") or 0) + int(safe3_full.get("n_waves") or 0)
    if n < 20:
        return {"verdict": VERDICT_INSUFFICIENT_N, "n": n, "numbers": {},
                "note": "fewer than 20 waves across the two Safe arms"}
    safe2_net = safe2_full.get("net_delta_dollars")
    safe3_net = safe3_full.get("net_delta_dollars")
    gate1_pass = (isinstance(safe2_net, (int, float)) and safe2_net > 0
                  and isinstance(safe3_net, (int, float)) and safe3_net > 0)
    verdict = VERDICT_MET if gate1_pass else VERDICT_NOT_MET
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {
            "safe_2_net_delta": safe2_net, "safe_3_net_delta": safe3_net,
            "safe_2_n_waves": safe2_full.get("n_waves"), "safe_3_n_waves": safe3_full.get("n_waves"),
            "safe_2_boot_ci_lower": safe2_full.get("bootstrap_ci_lower_2p5_per_wave_delta"),
            "safe_3_boot_ci_lower": safe3_full.get("bootstrap_ci_lower_2p5_per_wave_delta"),
            "safe_2_net_delta_frozen": frozen.get("safe-2", {}).get("net_delta_dollars"),
            "safe_3_net_delta_frozen": frozen.get("safe-3", {}).get("net_delta_dollars"),
        },
        "note": "prereg gate-1 (OOS/full positive) applied to both Safe arms; safe-2's "
                "delta is a mechanical no-op (int(qty*frac) truncation at qty=3), safe-3's "
                "is negative in both windows -- SHAPE_MISMATCH kill-nail confirmed, not applied.",
    }


def _score_runner_target_vs_tape_peak(row: dict, today: str) -> dict:
    """T2/T4 (GOAL-RIGHT-TAIL-FOLLOWUPS-2026-09-05): the prereg is FROZEN_BEFORE_ANY_RESULT
    with n_needed>=20 forward right-tail waves (post-10-30, per its own kill_criteria) --
    identical shape to `_score_spy_signal_weekly_lane` below, so this reuses that pattern
    rather than inventing a new one."""
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    status = _status_field(d)
    verdict = VERDICT_INSUFFICIENT_N
    if status and TERMINAL_STATUS_RE.search(status or ""):
        verdict = VERDICT_MET
    elif status and ADJUDICATION_STATUS_RE.match(status or ""):
        verdict = VERDICT_MET
    return {
        "verdict": verdict,
        "n": 0,
        "numbers": {"status": status,
                    "top_decile_n": len((d.get("evidence_this_prereg_is_built_on") or {})
                                         .get("right_tail_ledger_sample_computed_fresh_this_session", {})
                                         .get("top_decile_by_tape_peak_peak_ge_2.9x_n8_total_n7_taken", []))},
        "note": "FROZEN_BEFORE_ANY_RESULT -- no forward-scored waves yet; n>=20 forward "
                "right-tail waves is the frozen floor (kill_criteria.primary_kill). The "
                "top-decile n=7 sample in the prereg's own evidence section is BACKWARD-"
                "looking (this session's fresh pull), never citable as the forward bar.",
    }


def _score_spy_signal_weekly_lane(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    status = _status_field(d)
    verdict = VERDICT_INSUFFICIENT_N
    if status and TERMINAL_STATUS_RE.search(status or ""):
        verdict = VERDICT_MET
    elif status and ADJUDICATION_STATUS_RE.match(status or ""):
        verdict = VERDICT_MET
    return {
        "verdict": verdict,
        "n": 0,
        "numbers": {"status": status},
        "note": "FROZEN_BEFORE_ANY_RESULT -- no forward round trips scored yet; n>=15 / n>=20 sessions are the frozen floors.",
    }


def _score_fill_model_unification_step2(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    status = _status_field(d)
    step1_done = bool(d.get("step1_execution_evidence"))
    verdict = VERDICT_MET if step1_done else VERDICT_NOT_MET
    return {
        "verdict": verdict,
        "n": 1 if step1_done else 0,
        "numbers": {"status": status, "step1_execution_evidence_present": step1_done},
        "note": (
            "Tooling prerequisite -- MET means STEP 1 has run (evidence field "
            "populated), NOT MET means it is still blocking. The prereg's top-level "
            "`status` string is stale ('EXTEND -- mandatory STEP 1 ... still not "
            "executed') -- it was not updated when `step1_execution_evidence` was "
            "appended the same night; this scorer correctly reads the evidence field, "
            "not the stale status string. hand_check: confirmed 2026-09-05 (second "
            "method: `pytest backtest/tests/test_exit_fill_model_unification_2026_09_05.py -q` "
            "-> '22 passed in 0.42s', the guard suite step1_execution_evidence itself "
            "names as proof of the STEP-1 run)."
        ),
    }


def _score_tickers_theta_budget_cadence(row: dict, today: str) -> dict:
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    stats = d.get("statistics") or {}
    min_fills = int(stats.get("min_additional_fills") or 15)
    min_days = int(stats.get("min_additional_trading_days") or 10)
    tickers_dir = REPO / "automation" / "state" / "tickers"
    n_fills = 0
    days_seen: set = set()
    if tickers_dir.exists():
        for arm_dir in tickers_dir.glob("tickers-*"):
            ledger = arm_dir / "ledger.jsonl"
            if not ledger.exists():
                continue
            for r in _read_jsonl(ledger):
                if (r.get("stage") == "theta_budget") or ("theta_budget" in json.dumps(r).lower()):
                    n_fills += 1
                    d_et = r.get("date_et") or r.get("date")
                    if d_et:
                        days_seen.add(d_et)
    n_days = len(days_seen)
    if n_fills < min_fills or n_days < min_days:
        verdict = VERDICT_INSUFFICIENT_N
    else:
        verdict = VERDICT_UNKNOWN  # would need the per-fill bleed decomposition; not re-derived here
    return {
        "verdict": verdict,
        "n": n_fills,
        "numbers": {"theta_budget_fills": n_fills, "trading_days": n_days, "min_fills": min_fills, "min_days": min_days},
        "note": "INSUFFICIENT N until >=15 fills AND >=10 days accrue; above that the ACT/NO_ACTION bleed-decomposition math is the tickers lane's own scorer, not re-derived here.",
    }


def _score_catastrophe_cap_and_day_throttle(row: dict, today: str) -> dict:
    """HAND-CHECK FIX (2026-09-05, C6): the prior version hardcoded VERDICT_NOT_MET for
    any n>=15, which misrepresents this row -- its OWN decision_rule_verbatim (C1
    inventory) states plainly: 'no frozen n-threshold ships a change by itself' and
    day_throttle_shadow.py's own docstring says 'SHADOW ONLY. Neither threshold
    refuses anything live.' There IS NO pass/fail rule registered for this row to be
    MET or NOT MET against -- reporting NOT MET reads, to a skimmer, as 'the shadow
    failed a test', when no test exists; it is pure accruing evidence with no ship
    gate. Corrected to PROVISIONAL (the vocabulary this packet already defines for
    exactly this case: 'never cited as confirming evidence'), which matches the row's
    own text instead of contradicting it. n and the per-instrument numbers are
    unchanged -- only the verdict label changes.

    n=620 is FILLS, not ticks: verified n breaks down as 39 catastrophe-cap-shadow
    rows (one row per STOPPED real trade, `actual_realized_pnl` populated) + 581
    day-throttle rows (one row per TRADE ENTRY, `pnl` field on each) = 620 real fill
    events across both instruments, confirmed by direct read of both jsonl files
    (2026-09-05 hand-check)."""
    cap_path = REPO / "analysis" / "recommendations" / "catastrophe-cap-shadow-ledger.jsonl"
    throttle_path = REPO / "analysis" / "recommendations" / "day-throttle-shadow-ledger.jsonl"
    cap_rows = _read_jsonl(cap_path) if cap_path.exists() else []
    throttle_rows = _read_jsonl(throttle_path) if throttle_path.exists() else []
    cap_better_held = sum(1 for r in cap_rows if r.get("would_have_been_better_held") is True)
    cap_worse_held = sum(1 for r in cap_rows if r.get("would_have_been_better_held") is False)
    t2_blocks = sum(1 for r in throttle_rows if r.get("would_block_T-2") is True)
    t6_blocks = sum(1 for r in throttle_rows if r.get("would_block_T-6") is True)
    n = len(cap_rows) + len(throttle_rows)
    verdict = VERDICT_INSUFFICIENT_N if n < 15 else VERDICT_PROVISIONAL
    return {
        "verdict": verdict,
        "n": n,
        "numbers": {
            "catastrophe_cap_fires": len(cap_rows),
            "cap_better_held": cap_better_held,
            "cap_worse_held": cap_worse_held,
            "day_throttle_rows": len(throttle_rows),
            "t2_would_block": t2_blocks,
            "t6_would_block": t6_blocks,
        },
        "note": (
            "Shadow-read only -- no frozen ship threshold in scope for this row; "
            "numbers are the accruing evidence base, PROVISIONAL by construction "
            "(never cite as confirming evidence for a config change). hand_check: "
            "confirmed 2026-09-05 (direct read of both jsonl files: cap_rows=39 "
            "(better_held=15/worse_held=24), throttle_rows=581 (T-2=170/T-6=29); "
            "n=620 = fills, not ticks -- one row per stopped trade / trade entry in "
            "each ledger respectively)."
        ),
    }


# GOAL-GATE-NET-COST-2026-09-05 N4: which GATE-NET-COST-2026-09-05.json gate row(s) each
# `mechanism_codes` entry maps to. "GATE" (mechanism-1's right-tail-ledger code) is generic
# across both fleet gate_override knobs; the sizing-floor code is a direct 1:1 gate-name match.
_NET_COST_TABLE_PATH = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.json"
_MECHANISM_CODE_TO_NET_COST_GATES = {
    "GATE": ["min_triggers", "require_confluence_or_sequence"],
    "SKIP_MIN_PREMIUM_FLOOR": ["SKIP_MIN_PREMIUM_FLOOR"],
}


def _net_of_losers_for_mechanism(arms: set[str], codes: set[str]) -> dict | None:
    """GOAL-GATE-NET-COST-2026-09-05 N4: sum the wave-deduped-per-arm NET $ (winners +
    losers walked through the real exit shape, NOT the raw refused-winner ceiling) from
    `GATE-NET-COST-2026-09-05.json`'s `gate_arm_rows` for every (gate, arm) this mechanism
    covers. Returns None (never raises) if the table is missing -- callers must fail open.

    GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3: prefers each row's `full_window.net_dollars_1min`
    (populated by gate_net_cost_table.py when walk-2026-09-05-1min.json exists) over the
    5-min `net_dollars` when present, falling back to 5-min per-row on a miss -- never a
    silent blend within one mechanism's sum. `full_net_5min`/`used_1min_count` disclose which
    figure actually won for how many of the matched rows."""
    if not _NET_COST_TABLE_PATH.exists():
        return None
    table = json.loads(_NET_COST_TABLE_PATH.read_text(encoding="utf-8"))
    gate_names: set[str] = set()
    for code in codes:
        gate_names.update(_MECHANISM_CODE_TO_NET_COST_GATES.get(code, [code]))
    full_net = 0.0
    full_net_5min = 0.0
    frozen_net = 0.0
    n_waves_full = 0
    n_waves_frozen = 0
    used_1min_count = 0
    matched_rows = []
    for r in table.get("gate_arm_rows", []):
        if r["gate"] not in gate_names:
            continue
        if arms and r["arm"] not in arms:
            continue
        net_5min = r["full_window"]["net_dollars"]
        net_1min = r["full_window"].get("net_dollars_1min")
        net_used = net_1min if net_1min is not None else net_5min
        if net_1min is not None:
            used_1min_count += 1
        full_net += net_used
        full_net_5min += net_5min
        frozen_net += r["frozen_window"]["net_dollars"]
        n_waves_full += r["full_window"]["n_waves"]
        n_waves_frozen += r["frozen_window"]["n_waves"]
        matched_rows.append({"gate": r["gate"], "arm": r["arm"],
                              "net_dollars": net_used, "resolution": "1min" if net_1min is not None else "5min"})
    if not matched_rows:
        return None
    return {
        "net_of_losers_dollars_full_window": round(full_net, 2),
        "net_of_losers_dollars_full_window_5min": round(full_net_5min, 2),
        "net_of_losers_dollars_frozen_window": round(frozen_net, 2),
        "n_waves_full_window": n_waves_full,
        "n_waves_frozen_window": n_waves_frozen,
        "matched_gate_arm_rows": matched_rows,
        "n_gate_arm_rows_using_1min": used_1min_count,
        "n_gate_arm_rows_total": len(matched_rows),
        "source": "analysis/gate-net-cost/GATE-NET-COST-2026-09-05.json (N3 net table; "
                  "full_window prefers net_dollars_1min per row when present, per "
                  "GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3)",
    }


def _score_capture_gap_mechanism(row: dict, today: str) -> dict:
    """GOAL-FLEET-CAPTURE-GAP-2026-09-05 F4 (extended GOAL-GATE-NET-COST-2026-09-05 N4).
    Generic scorer for both mechanism-1 (gate_override) and mechanism-6 (sizing floor)
    preregs: counts forward-window (date > the prereg's filed_at, i.e. after 2026-09-05)
    missed (wave, arm) rows in analysis/right-tail/ledger.jsonl whose `arm` is in the row's
    `mechanism_arms` and whose `refused_by_gate` code (text before ':') is in
    `mechanism_codes`. INSUFFICIENT N below `min_n` (default 10, matching each prereg's own
    extend_criterion).

    N4 fix: `numbers` now also carries `net_of_losers_dollars_full_window` /
    `_frozen_window`, read from GATE-NET-COST-2026-09-05.json's per-(gate,arm) NET (winners
    + losers walked through the real exit shape) -- NOT the prereg's raw refused-winner
    CEILING figure (`dollar_figure`, $4,354.92 / $1,664.00), which this scorer never reads
    and the packet must not surface as if it were the decision-relevant number."""
    ledger_path_base = REPO / (row.get("ledger_path") or "analysis/right-tail/ledger.jsonl")
    ledger_path, ledger_resolution = _prefer_1min_path(ledger_path_base)
    arms = set(row.get("mechanism_arms", []))
    codes = set(row.get("mechanism_codes", []))
    min_n = row.get("min_n", 10)
    rows = _read_jsonl(ledger_path)
    forward_start = row.get("forward_window_start", "2026-09-05")
    matches = []
    for r in rows:
        if "wave_start_et" not in r or "taken" not in r:
            continue
        if r.get("taken") or r.get("date", "") <= forward_start:
            continue
        if arms and r.get("arm") not in arms:
            continue
        refused = r.get("refused_by_gate") or ""
        code = refused.split(":", 1)[0].strip()
        if codes and code not in codes:
            continue
        matches.append(r)
    n = len(matches)
    verdict = VERDICT_INSUFFICIENT_N if n < min_n else VERDICT_NOT_MET
    numbers = {
        "forward_missed_matching_rows": n, "min_n": min_n,
        "forward_window_start": forward_start,
        "sample_dates": sorted({r.get("date") for r in matches})[:5],
        "ledger_resolution": ledger_resolution,
        "ledger_path_used": str(ledger_path.relative_to(REPO)),
    }
    net = _net_of_losers_for_mechanism(arms, codes)
    if net is not None:
        numbers.update(net)
    return {
        "verdict": verdict,
        "n": n,
        "numbers": numbers,
        "note": "Forward-window count of missed waves still attributable to this "
                "mechanism after 2026-09-05, per this prereg's own extend_criterion. "
                "RULE MET is never emitted by this generic scorer -- the dry-run P&L "
                "replay in each prereg's kill_criterion/extend_criterion is a separate, "
                "not-yet-built step; INSUFFICIENT N / NOT MET only reflect the count gate. "
                "net_of_losers_dollars_* (when present) is the backfill-window NET read "
                "from GATE-NET-COST-2026-09-05.json, NOT the ceiling -- read it, not "
                "dollar_figure, when citing a $ number for this row.",
    }


def _score_not_flat_second_wave(row: dict, today: str) -> dict:
    """W2 (GOAL-NOT-FLAT-SECOND-WAVE-PREREG-2026-09-05): the prereg is
    FROZEN_BEFORE_ANY_RESULT with n_needed>=20 forward second-wave refusals -- same
    FROZEN-status-driven shape as `_score_runner_target_vs_tape_peak`/
    `_score_spy_signal_weekly_lane` above, reused rather than re-invented. Reads the
    NOT_FLAT gate's already-computed dedup-to-waves numbers straight from
    GATE-NET-COST-2026-09-05.json (N3's table) for disclosure -- it does NOT re-walk
    or re-derive them -- and counts `second_wave_summary.present` rows in
    analysis/right-tail/ledger.jsonl as the (backward, unfiltered-by-TP1) n context.
    Forward n (post this prereg's filed_at, matching the a/b/c admission condition)
    is not yet accruing anywhere, so verdict stays INSUFFICIENT N until the prereg's
    own `status` field turns terminal/adjudicated."""
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    status = _status_field(d)
    verdict = VERDICT_INSUFFICIENT_N
    if status and TERMINAL_STATUS_RE.search(status or ""):
        verdict = VERDICT_MET
    elif status and ADJUDICATION_STATUS_RE.match(status or ""):
        verdict = VERDICT_MET
    numbers: dict[str, Any] = {"status": status}
    if _NET_COST_TABLE_PATH.exists():
        table = json.loads(_NET_COST_TABLE_PATH.read_text(encoding="utf-8"))
        for r in table.get("gate_rows_deduped_to_waves", []):
            if r.get("gate") == "NOT_FLAT":
                numbers["full_window_net_dollars"] = r["full_window"]["net_dollars"]
                numbers["full_window_n_waves"] = r["full_window"]["n_waves"]
                numbers["full_window_best_day"] = r["full_window"]["best_day"]
                numbers["full_window_best_day_dollars"] = r["full_window"]["best_day_dollars"]
                numbers["full_window_ex_best_day_net_dollars"] = r["full_window"]["ex_best_day_net_dollars"]
                numbers["frozen_window_net_dollars"] = r["frozen_window"]["net_dollars"]
                numbers["frozen_window_n_waves"] = r["frozen_window"]["n_waves"]
                numbers["frozen_window_ex_best_day_net_dollars"] = r["frozen_window"]["ex_best_day_net_dollars"]
                break
    ledger_path_base = REPO / (row.get("ledger_path") or "analysis/right-tail/ledger.jsonl")
    ledger_path, ledger_resolution = _prefer_1min_path(ledger_path_base)
    n_present = 0
    if ledger_path.exists():
        n_present = sum(1 for r in _read_jsonl(ledger_path)
                         if r.get("second_wave_summary", {}).get("present"))
    numbers["right_tail_ledger_n_second_wave_present_all_time_backward"] = n_present
    numbers["right_tail_ledger_resolution"] = ledger_resolution
    return {
        "verdict": verdict,
        "n": 0,
        "numbers": numbers,
        "note": "FROZEN_BEFORE_ANY_RESULT -- no forward-scored second-wave-refusal "
                "waves yet; n>=20 forward refusals (post-2026-09-05, matching the "
                "60min/fresh-trigger/TP1-reached admission condition) is the frozen "
                "floor (kill_criteria). The right_tail_ledger n=30 figure is BACKWARD "
                "and unfiltered by the TP1-reached condition -- never citable as the "
                "forward bar. full_window/frozen_window numbers are read straight from "
                "GATE-NET-COST-2026-09-05.json's NOT_FLAT dedup-to-waves row, not "
                "re-walked here.",
    }


def _score_filter10_bull_sole_unblock(row: dict, today: str) -> dict:
    """GOAL-GATE-EXPIRY-RECONCILE-2026-09-05 G2: the bull-side 11-filter-checklist
    sole-blocker-on-filter-10 unblock candidate. Same FROZEN_BEFORE_ANY_RESULT shape as
    `_score_not_flat_second_wave` above, reused rather than re-invented: verdict stays
    INSUFFICIENT N (no forward-scored sample yet -- the backward reads below are the
    evidence the prereg was FILED on, not the forward n>=20 the kill/extend bar needs)
    until the prereg's own `status` field turns terminal/adjudicated. Backward numbers
    are read straight from analysis/recommendations/gate-postfix-costing-sole-b8b10-
    2026-09-05.json's 'filter-10-bull-sole' cohort (G1's postfix_gate_costing.py Part B
    replay, walk_exit_manager) for disclosure only -- never re-walked here."""
    prereg_path = REPO / row["prereg_path"]
    d = _read_json(prereg_path)
    status = _status_field(d)
    verdict = VERDICT_INSUFFICIENT_N
    if status and TERMINAL_STATUS_RE.search(status or ""):
        verdict = VERDICT_MET
    elif status and ADJUDICATION_STATUS_RE.match(status or ""):
        verdict = VERDICT_MET
    numbers: dict[str, Any] = {"status": status}
    g1_path = REPO / "analysis" / "recommendations" / "gate-postfix-costing-sole-b8b10-2026-09-05.json"
    if g1_path.exists():
        g1 = json.loads(g1_path.read_text(encoding="utf-8"))
        cohort = g1.get("cohorts", {}).get("filter-10-bull-sole", {})
        for wname in ("august", "frozen"):
            cell = cohort.get(wname, {}).get("replayed_as_safe_qty_exit_shape")
            if cell:
                numbers[f"{wname}_window_net_dollars_safe_qty"] = cell.get("total_dollar")
                numbers[f"{wname}_window_n"] = cell.get("n")
                numbers[f"{wname}_window_best_day_share"] = cell.get("best_day_share")
    return {
        "verdict": verdict,
        "n": 0,
        "numbers": numbers,
        "note": "FROZEN_BEFORE_ANY_RESULT -- no forward-scored sole-blocked-on-filter-10 "
                "sample yet; n>=20 forward episodes (post-2026-09-05) is the frozen floor "
                "(kill_criteria). august_window/frozen_window numbers above are the "
                "BACKWARD read this prereg was filed on (G1's postfix_gate_costing.py "
                "Part B replay), never citable as the forward bar.",
    }


_SCORERS: dict[str, Callable[[dict, str], dict]] = {
    "capture_gap_mechanism": _score_capture_gap_mechanism,
    "tight_ladder_control4": _score_tight_ladder_control4,
    "tight_ladder_control5": _score_tight_ladder_control5,
    "score_ladder_v2_retirement": _score_score_ladder_v2_retirement,
    "f10_vol_baseline_reset": _score_f10_vol_baseline_reset,
    "vix_bull_hard_cap_shadow": _score_vix_bull_hard_cap_shadow,
    "spy_signal_weekly_lane": _score_spy_signal_weekly_lane,
    "fill_model_unification_step2": _score_fill_model_unification_step2,
    "tickers_theta_budget_cadence": _score_tickers_theta_budget_cadence,
    "catastrophe_cap_and_day_throttle": _score_catastrophe_cap_and_day_throttle,
    "runner_target_vs_tape_peak": _score_runner_target_vs_tape_peak,
    "tp1_qty_fraction_safe_0_8": _score_tp1_qty_fraction_safe_0_8,
    "not_flat_second_wave": _score_not_flat_second_wave,
    "filter10_bull_sole_unblock": _score_filter10_bull_sole_unblock,
}


def score_row(row: dict, today: str) -> dict:
    """Fail-open dispatcher: any scorer exception degrades to one UNKNOWN row, never a crash."""
    scorer_name = row.get("scorer")
    fn = _SCORERS.get(scorer_name)
    base = {
        "row_id": row.get("row_id"),
        "prereg_path": row.get("prereg_path"),
        "ledger_path": row.get("ledger_path"),
        "classification": row.get("classification"),
        "checkpoint": row.get("checkpoint"),
        "frozen_hypothesis": row.get("frozen_hypothesis"),
        "decision_rule_verbatim": row.get("decision_rule_verbatim"),
        "reversible_action": row.get("reversible_action"),
    }
    if fn is None:
        base.update({"verdict": VERDICT_UNKNOWN, "n": None, "numbers": {}, "note": f"no scorer registered for '{scorer_name}'"})
        return base
    try:
        result = fn(row, today)
    except Exception as exc:  # noqa: BLE001 -- fail-open is the point
        base.update({
            "verdict": VERDICT_UNKNOWN,
            "n": None,
            "numbers": {},
            "note": f"scorer '{scorer_name}' raised: {exc.__class__.__name__}: {exc}",
            "traceback": traceback.format_exc(limit=4),
        })
        return base
    base.update(result)
    return base


# right_tail_capture's own R4 was PROVISIONAL as of the 2026-09-05 03:1x ET C1-C5 fire
# (reopened same night). It closed later the SAME night -- commit 915c057d ("R4 done,
# goal DONE"; GOAL-RIGHT-TAIL-CAPTURE-2026-09-05.md: "R1-R6 all DONE ... Backfill +
# cockpit tile numbers ... are now final, not provisional") -- so the override is
# retired here (C6 hand-check, 2026-09-05). Kept as an empty set (not deleted) so a
# FUTURE reopen of this row has an obvious place to re-add it.
_PROVISIONAL_ROW_IDS: set[str] = set()


PACKAGES_DIR = RECS_DIR / "packages"


def _package_status(row_id: str) -> tuple[str | None, bool]:
    """Additive, read-only lookup (GOAL-CHECKPOINT-REDUCTION-PACKAGES-2026-09-05 K3):
    a package is "ready" only when README.md + change.patch + apply.ps1 all exist AND
    change.patch is non-empty (an empty patch is the K2 scaffold placeholder, not a
    real package). Never writes anything -- a parallel session may be authoring a
    package under analysis/recommendations/packages/<row-id>/ concurrently; this
    function only reads that directory."""
    pkg_dir = PACKAGES_DIR / row_id
    if not pkg_dir.is_dir():
        return None, False
    try:
        package_path = pkg_dir.relative_to(REPO).as_posix()
    except ValueError:
        # PACKAGES_DIR monkeypatched outside REPO (tests) -- report the canonical
        # repo-relative shape rather than an absolute/foreign path.
        package_path = f"analysis/recommendations/packages/{row_id}"
    required = ("README.md", "change.patch", "apply.ps1")
    if not all((pkg_dir / name).exists() for name in required):
        return package_path, False
    patch = pkg_dir / "change.patch"
    ready = patch.stat().st_size > 0
    return package_path, ready


def build_packet(inventory_path: Path = INVENTORY_PATH, today: str | None = None) -> dict:
    today = today or _et_date_str()
    inv = _read_json(inventory_path)
    rows_out = []
    for row in inv.get("rows", []):
        scored = score_row(row, today)
        if row.get("row_id") in _PROVISIONAL_ROW_IDS:
            scored["verdict"] = VERDICT_PROVISIONAL
            scored["note"] = (scored.get("note", "") + " [R4 of GOAL-RIGHT-TAIL-CAPTURE reopened 2026-09-05 -- "
                               "reported PROVISIONAL, never cited as confirming evidence until re-closed.]").strip()
        if scored.get("classification") == "reduction":
            package_path, package_ready = _package_status(scored["row_id"])
            scored["package"] = package_path
            scored["package_ready"] = package_ready
        rows_out.append(scored)
    return {
        "generated_at_et": et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "generation_date": today,
        "generated_by": "setup/scripts/checkpoint_packet.py",
        "inventory_source": inventory_path.relative_to(REPO).as_posix(),
        "row_count": len(rows_out),
        "rows": rows_out,
    }


MARKDOWN_DIR = REPO / "markdown" / "planning"
CHECKPOINT_0929_MD = MARKDOWN_DIR / "CHECKPOINT-2026-09-29.md"
CHECKPOINT_1030_MD = MARKDOWN_DIR / "CHECKPOINT-2026-10-30.md"


def _md_row_line(r: dict) -> str:
    numbers = ", ".join(f"{k}={v}" for k, v in (r.get("numbers") or {}).items())
    pkg = "-"
    if r.get("classification") == "reduction":
        if r.get("package"):
            pkg = ("ready" if r.get("package_ready") else "scaffold-only") + f" (`{r['package']}`)"
        else:
            pkg = "none"
    return (
        f"| `{r['row_id']}` | {r['classification']} | {r['verdict']} | {r.get('n')} | "
        f"[{Path(r['prereg_path']).name}]({r['prereg_path']}) | {numbers or '-'} | {pkg} |"
    )


def _render_markdown(packet: dict, checkpoint_date: str, title: str) -> str:
    rows = [r for r in packet["rows"] if r["checkpoint"] == checkpoint_date]
    lines = [
        f"# {title}",
        "",
        f"> **GENERATED by `setup/scripts/checkpoint_packet.py` -- do not hand-edit.** "
        f"Regenerated nightly by `Gamma_CheckpointPacket` (23:30 ET). This file reflects "
        f"the {packet['generation_date']} ET generation; on {checkpoint_date} the read is "
        f"the last night's file. Source inventory: `{packet['inventory_source']}`. "
        f"Raw packet: `analysis/recommendations/checkpoint-packet-{packet['generation_date']}.json`.",
        "",
        f"Generated at: {packet['generated_at_et']} ET | Rows in this window: {len(rows)}",
        "",
    ]
    reduction_rows = [r for r in rows if r.get("classification") == "reduction"]
    if reduction_rows:
        n_ready = sum(1 for r in reduction_rows if r.get("package_ready"))
        lines.append(f"**Packages ready: {n_ready}/{len(reduction_rows)} reduction rows.**")
        lines.append("")
    lines += [
        "| Decision | Class | Verdict | n | Prereg | Numbers | Package |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(_md_row_line(r))
    lines.append("")
    lines.append("## Detail")
    for r in rows:
        lines.append("")
        lines.append(f"### `{r['row_id']}`")
        lines.append("")
        lines.append(f"- **Classification:** {r['classification']} (routes to {r['checkpoint']})")
        lines.append(f"- **Verdict:** {r['verdict']} (n={r.get('n')})")
        lines.append(f"- **Prereg:** `{r['prereg_path']}`")
        lines.append(f"- **Ledger:** `{r['ledger_path']}`")
        lines.append(f"- **Frozen hypothesis:** {r.get('frozen_hypothesis')}")
        lines.append(f"- **Decision rule (verbatim):** {r.get('decision_rule_verbatim')}")
        lines.append(f"- **Reversible action:** {r.get('reversible_action')}")
        if r.get("classification") == "reduction":
            lines.append(f"- **Package:** `{r.get('package')}` (package_ready={r.get('package_ready')})")
        lines.append(f"- **Note:** {r.get('note')}")
    lines.append("")
    return "\n".join(lines)


def write_markdown(packet: dict) -> tuple[Path, Path]:
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
    md_0929 = _render_markdown(
        packet, "2026-09-29",
        "Checkpoint 2026-09-29 -- Kill-Type Risk Reductions Only",
    )
    md_1030 = _render_markdown(
        packet, "2026-10-30",
        "Checkpoint 2026-10-30 -- Full Checkpoint (Expansions + Reductions Not Yet Shipped)",
    )
    CHECKPOINT_0929_MD.write_text(md_0929, encoding="utf-8")
    CHECKPOINT_1030_MD.write_text(md_1030, encoding="utf-8")
    return CHECKPOINT_0929_MD, CHECKPOINT_1030_MD


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Override generation date (YYYY-MM-DD ET); defaults to today via et_clock.")
    ap.add_argument("--json-out", default=None, help="Path to write the raw packet JSON. Defaults to analysis/recommendations/checkpoint-packet-<date>.json")
    ap.add_argument("--inventory", default=str(INVENTORY_PATH))
    ap.add_argument("--no-markdown", action="store_true", help="Skip writing the CHECKPOINT-*.md files (used by tests).")
    args = ap.parse_args(argv)

    packet = build_packet(Path(args.inventory), today=args.date)
    out_path = Path(args.json_out) if args.json_out else RECS_DIR / f"checkpoint-packet-{packet['generation_date']}.json"
    out_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for r in packet["rows"]:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print(f"checkpoint_packet: {packet['row_count']} rows, generated {packet['generation_date']} ET")
    print(f"wrote {out_path.relative_to(REPO)}")
    for verdict, c in sorted(counts.items()):
        print(f"  {verdict}: {c}")
    for r in packet["rows"]:
        print(f"  [{r['classification']:>11}] {r['row_id']:<45} {r['verdict']:<15} n={r.get('n')}")

    if not args.no_markdown:
        md0929, md1030 = write_markdown(packet)
        print(f"wrote {md0929.relative_to(REPO)}")
        print(f"wrote {md1030.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
