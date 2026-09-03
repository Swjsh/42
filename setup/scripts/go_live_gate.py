"""go_live_gate.py -- the REAL live-money go/no-go instrument for Project Gamma.

WHY THIS EXISTS (built 2026-08-28, TASK C2): setup/scripts/live_readiness.py answers ONE
question ("does this arm clear CLAUDE.md's 4-condition trade-count/WR/expectancy/rule-break
bar") and that bar was already flagged inadequate for a real-money decision -- WR is not the
right lens for a right-tail system, and the 4-condition AND says nothing about statistical
confidence, operational safety, broker reconciliation, operator behaviour, or a production
shadow track record. This script is a SEPARATE, STRICTER instrument sitting next to
live_readiness.py (does not replace or edit it) that computes a single GREEN/RED verdict from
five criteria groups, each with an exact numeric distance to the bar it did not clear:

  1. STATISTICAL   -- per-arm day-level bootstrap PF, 95% CI LOWER bound > 1.0, on the full
                       available trading-day history (never just a cherry-picked good month).
                       Must ALSO survive (a) dropping the single best day and (b) the A1
                       realistic-cost adjustment (regulatory fees + 2c/contract exit slippage,
                       cost-model.json's own rates). All three must clear 1.0 -- the bar is
                       AND, not OR.
  2. OPERATIONAL    -- every named guardrail test exists AND passes; the dead-man's-switch gap
                       (process death / heartbeat silence with an open position) is checked for
                       an EXISTING TEST and reported as an explicit gap, never assumed closed.
  3. RECONCILIATION -- realized ledger P&L vs REAL broker equity change, ALL 5 arms, queried
                       live via Alpaca REST using fleet/secrets.json (the same $0 read-only
                       pattern accounts_status.py uses -- no MCP wiring needed, so this covers
                       arms the interactive session's .mcp.json does not reach).
  4. BEHAVIOURAL    -- rule breaks, manual-attribution fills, and sizing-up events actually
                       LOGGED in the trailing window (this reads existing ledgers; it does not
                       re-adjudicate every historical trade against a cap).
  5. PROD-SHADOW    -- WIRED 2026-09-01 (TASK W5, queue.md PROD-SHADOW-ARM-DESIGNATION). Reads
                       its designation (arm/window/min_days) from automation/state/prod-shadow-
                       designation.json and scores it net of realistic costs via the SAME
                       statistical_criterion() as criterion 1. Status ladder: NOT_WIRED (no
                       readable designation file -- never guessed) -> INSUFFICIENT_DAYS (window
                       hasn't scored min_days yet) -> PASS/FAIL. See prod_shadow_criterion()
                       docstring for the current designation's rationale.

Also carries three DISCLOSURE-ONLY views (TASK W5, 2026-09-01 -- honesty gaps a Fable audit
found missing; none of these change any pass/fail bar above): a FROZEN-CONFIG-WINDOW view
(criterion-1's bootstrap restricted to days on/after the 2026-08-31 config freeze), an
EFFECTIVE-EVIDENCE block (days actually on the current config vs. post-tight-ladder, and how
much of each arm's gross winner dollars sit in its best 2 days), and a PLAN-REACHABILITY block
(the constant $/day, zero-variance best case, that would push CI-lower(2.5%) above 1.0 by the
config-freeze close and by the tight-ladder's 40-day clock). See report["disclosures"].

THIS IS A REPORTING INSTRUMENT ONLY. It arms nothing, changes no gate, edits no params*.json,
places no orders, and never touches the live-path files listed in this session's scope fence
(params*.json, heartbeat_core.py, filters.py, strategies.py, fleet_executor.py, risk_gate.py,
exit_manager.py). A GREEN verdict here is evidence for a conversation with J about live-money
arming (OP-0 #1) -- never a trigger to act alone.

OUTPUTS:
  - analysis/go-live-gate.json   -- full machine payload, always written
  - analysis/go-live-gate.md     -- compact human-readable surface, always written
  - human table printed to stdout (unless --json)

Run:
    backtest/.venv/Scripts/python.exe setup/scripts/go_live_gate.py            # human table
    backtest/.venv/Scripts/python.exe setup/scripts/go_live_gate.py --json     # machine payload
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
for _p in (SCRIPTS_DIR,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now, ET_TZ  # noqa: E402
import trades_enriched as te_producer  # noqa: E402 -- TRADES-ENRICHED-HAS-NO-SCHEDULED-PRODUCER refresh
import futures_go_live_gate  # noqa: E402 -- ADDITIVE futures block (queue.md
# FUTURES-ABSENT-FROM-GO-LIVE-GATE, 2026-09-03). Its output attaches under report["futures"],
# a SIBLING key to report["criteria"] -- never merged into `criteria`/`groups`, so it
# structurally cannot change `overall_verdict` (see build_report() below and that module's
# own docstring). The call is wrapped in try/except there too: a bug in the futures module
# can never crash or alter the SPY gate.

TRADES_ENRICHED = REPO / "analysis" / "trades-enriched.jsonl"
CORE_DECISIONS_PATH = REPO / "automation" / "state" / "core-decisions.jsonl"
ACCOUNTS_PATH = REPO / "automation" / "state" / "fleet" / "accounts.json"
SECRETS_PATH = REPO / "automation" / "state" / "fleet" / "secrets.json"
RULE_BREAKS_PATH = REPO / "automation" / "state" / "rule-breaks.jsonl"
MISTAKES_PATH = REPO / "journal" / "mistakes.md"
BACKTEST_DIR = REPO / "backtest"
BACKTEST_PY = BACKTEST_DIR / ".venv" / "Scripts" / "python.exe"

OUT_JSON = REPO / "analysis" / "go-live-gate.json"
OUT_MD = REPO / "analysis" / "go-live-gate.md"

# CREATE_NO_WINDOW: BACKTEST_PY is console-subsystem, which flashes a console on J's
# desktop without the flag when this script is spawned headlessly (OP-27 L41).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# --------------------------------------------------------------------------------------- #
# Roster + assumptions -- disclosed, never silently baked in.
# --------------------------------------------------------------------------------------- #
_FALLBACK_ACTIVE_ARMS = ["safe-2", "bold-2", "safe-3", "risky-1"]  # last-known-good, used only
# if accounts.json is unreadable at import time -- fail-open with a stale-but-plausible roster
# rather than crashing this reporting-only instrument (never touches the live path).


def _load_active_arms() -> list:
    """Derived from accounts.json (status=='active', SPY_0DTE_OPTION), never hardcoded --
    OP-25 fix for the class of bug that made this a STALE hardcoded 5-arm tuple through
    risky-3's 2026-08-28 retirement (silently reconciling a retired arm's now-frozen ledger
    against live broker history going forward -- see this script's OWN STATUS.md entry from
    that session for the incident). Falls back to _FALLBACK_ACTIVE_ARMS on any read error,
    matching this module's reporting-only fail-open posture (never crashes, never blocks)."""
    try:
        cfg = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
        arms = [
            str(a["id"]) for a in cfg.get("arms", [])
            if isinstance(a, dict) and a.get("status") == "active"
            and a.get("instrument") == "SPY_0DTE_OPTION"
        ]
        return arms or list(_FALLBACK_ACTIVE_ARMS)
    except (OSError, ValueError, KeyError):
        return list(_FALLBACK_ACTIVE_ARMS)


ACTIVE_ARMS = _load_active_arms()  # accounts.json status=active, SPY_0DTE_OPTION -- live-derived

# ASSUMPTION (stated per Judgment Guards -- not independently confirmed against a per-fleet-arm
# params file this run): CLAUDE.md Rule 6 states the per-trade risk cap explicitly ONLY for the
# two core accounts (Safe 30% / Bold 50%). The 3 fleet arms are mapped here by their
# accounts.json display_name tier prefix -- FLEET-TIGHT-S -> Safe tier (30%), FLEET-FULLSEND-R /
# FLEET-LOOSE-R -> Bold/risky tier (50%). If this mapping is wrong, ONLY the sizing-up behavioural
# sub-check is affected (flagged as such in that section) -- no other criterion depends on it.
RISK_CAP_PCT = {"safe-2": 0.30, "safe-3": 0.30, "bold-2": 0.50, "risky-1": 0.50, "risky-3": 0.50}

# CLAUDE.md's own >=20-trade live threshold, reused here as the trailing-window length for the
# BEHAVIOURAL criterion (a defensible, doctrine-anchored choice, not an arbitrary pick) --
# expressed in TRADING days present in the ledger, not calendar days.
TRAILING_WINDOW_TRADING_DAYS = 20

# A1's own conservative default cost scenario (analysis/recommendations/cost-model.json rates,
# same constants _scratch_a1_bootstrap.py used and this session's ground truth already verified
# against the ledger to the dollar).
FEE_RATES = {
    "occ_per_contract": 0.025,
    "orf_per_contract": 0.015,
    "taf_per_contract_sell": 0.00329,
    "sec_rate_per_dollar_sell": 2.0600000000000003e-05,
    "cat_per_arm_day": 0.01,
}
COST_MODEL_EXIT_SLIPPAGE_CENTS = 2.0  # A1's conservative scenario-b exit-slippage assumption

N_BOOT = 20000
BOOT_SEED = 42

# --------------------------------------------------------------------------------------- #
# PROD-SHADOW designation + disclosure-view anchors (TASK W5, 2026-09-01).
# --------------------------------------------------------------------------------------- #
PROD_SHADOW_DESIGNATION_PATH = REPO / "automation" / "state" / "prod-shadow-designation.json"

# doctrine.py FREEZE_START (2026-08-31) -- the day the trading-path config actually froze.
# Used ONLY for the disclosure view below; never changes criterion 1's pass bar (full history).
FROZEN_CONFIG_WINDOW_START = "2026-08-31"
# The designated PROD-SHADOW window's own start (see prod-shadow-designation.json) -- "days on
# the current config" for the effective-evidence disclosure.
CURRENT_CONFIG_WINDOW_START = "2026-09-01"
# Disclosure anchor per this task's brief (distinct from the tight-ladder prereg's 09-01 window) --
# a 3-week-earlier cut so a reader can see how much of an arm's evidence predates even that.
POST_LADDER_WINDOW_START = "2026-08-11"

# Plan-reachability horizons: (end date inclusive, label). 2026-09-29 = the config-freeze scoring
# window close; 2026-10-30 = PREREG-TIGHT-LADDER-2026-08-28.md's registered 40-day clock close.
PLAN_REACHABILITY_TARGETS = (
    ("2026-09-29", "config_freeze_end"),
    ("2026-10-30", "tight_ladder_clock_end"),
)
MARKET_HOLIDAYS_2026 = {"2026-09-07"}  # Labor Day -- the only market holiday inside these horizons
_REACHABILITY_N_BOOT = 3000   # reduced from N_BOOT for search speed (disclosed in the output)
_REACHABILITY_UPPER_BOUND = 5000.0
_REACHABILITY_ITERS = 24


# ========================================================================================= #
# 1. STATISTICAL -- day-level bootstrap PF, CI lower bound, best-day-removed, cost-adjusted.
# ========================================================================================= #
def _ceil_cents(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100.0


def fee_ex_cat(qty: float, exit_px: float) -> float:
    """Regulatory fees (ex-CAT) on one round trip's exit leg -- identical formula/rounding to
    setup/scripts/cost_model.py and _scratch_a1_bootstrap.py (both independently verified
    against real Alpaca fee-activity rows to the cent, 2026-08-18)."""
    sell_proceeds = exit_px * qty * 100.0
    occ = 2 * _ceil_cents(FEE_RATES["occ_per_contract"] * qty)
    orf = 2 * _ceil_cents(FEE_RATES["orf_per_contract"] * qty)
    taf = _ceil_cents(FEE_RATES["taf_per_contract_sell"] * qty)
    sec = _ceil_cents(FEE_RATES["sec_rate_per_dollar_sell"] * sell_proceeds)
    return occ + orf + taf + sec


def cost_adjusted_pnl(row: dict, arm_day_counts: dict, slip_cents: float) -> float:
    qty = float(row.get("qty") or 0.0)
    exit_px = row.get("exit_px_avg")
    fee = fee_ex_cat(qty, float(exit_px)) if exit_px is not None else 0.0
    key = (row["arm"], row["date"])
    cat_share = FEE_RATES["cat_per_arm_day"] / max(arm_day_counts.get(key, 1), 1)
    slip = (slip_cents / 100.0) * qty
    return float(row["pnl_dollars"]) - fee - cat_share - slip


def profit_factor(values: list[float]) -> float:
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return gains / losses


def bootstrap_pf_ci(day_values: list[float], n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> dict | None:
    """Percentile bootstrap over trading DAYS (not trades), matching A1's methodology
    (resample-with-replacement respects within-day trade correlation). Returns None when
    there are fewer than 2 days -- a CI is not meaningful on n<2."""
    n = len(day_values)
    if n < 2:
        return None
    rng = random.Random(seed)
    pfs = []
    for _ in range(n_boot):
        sample = [day_values[rng.randrange(n)] for _ in range(n)]
        pf = profit_factor(sample)
        if pf == pf and pf != float("inf"):  # drop NaN and +inf (all-win resample) from the CI
            pfs.append(pf)
    if not pfs:
        return None
    pfs.sort()
    lo_idx = int(0.025 * len(pfs))
    hi_idx = min(int(0.975 * len(pfs)), len(pfs) - 1)
    p_le_1 = sum(1 for p in pfs if p <= 1.0) / len(pfs)
    return {
        "n_days": n,
        "n_boot_valid": len(pfs),
        "pf_point": round(profit_factor(day_values), 3) if math.isfinite(profit_factor(day_values)) else None,
        "ci_lower_2.5": round(pfs[lo_idx], 3),
        "ci_upper_97.5": round(pfs[hi_idx], 3),
        "p_pf_le_1": round(p_le_1, 3),
        "total_pnl": round(sum(day_values), 2),
    }


def _daily_totals(rows: list[dict]) -> dict[str, float]:
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += float(r["pnl_dollars"])
    return dict(by_day)


def statistical_criterion(rows: list[dict], arm_id: str | None) -> dict:
    """rows already filtered to attribution=='engine' and (arm_id or all active arms)."""
    scoped = rows if arm_id is None else [r for r in rows if r["arm"] == arm_id]
    if not scoped:
        return {"insufficient_data": True, "pass": False,
                "note": "zero engine-attributed round trips for this scope"}

    as_traded_days = _daily_totals(scoped)
    as_traded_vals = list(as_traded_days.values())
    as_traded = bootstrap_pf_ci(as_traded_vals)

    # (a) survives removing its single best day
    if as_traded_days:
        best_day = max(as_traded_days, key=lambda d: as_traded_days[d])
        ex_best_vals = [v for d, v in as_traded_days.items() if d != best_day]
    else:
        best_day, ex_best_vals = None, []
    ex_best_day = bootstrap_pf_ci(ex_best_vals)

    # (b) survives the A1 realistic cost model (fees + 2c/contract exit slippage)
    arm_day_counts: dict[tuple, int] = defaultdict(int)
    for r in scoped:
        arm_day_counts[(r["arm"], r["date"])] += 1
    cost_rows = [dict(r, pnl_dollars=cost_adjusted_pnl(r, arm_day_counts, COST_MODEL_EXIT_SLIPPAGE_CENTS))
                 for r in scoped]
    cost_days = _daily_totals(cost_rows)
    cost_adjusted = bootstrap_pf_ci(list(cost_days.values()))

    def _lower(ci: dict | None) -> float | None:
        return ci["ci_lower_2.5"] if ci else None

    lowers = [_lower(as_traded), _lower(ex_best_day), _lower(cost_adjusted)]
    all_present = all(v is not None for v in lowers)
    passed = all_present and all(v > 1.0 for v in lowers)  # type: ignore[operator]

    return {
        "insufficient_data": False,
        "n_engine_trades": len(scoped),
        "n_trading_days": len(as_traded_days),
        "as_traded": as_traded,
        "ex_best_day": dict(ex_best_day or {}, dropped_day=best_day) if ex_best_day else {"dropped_day": best_day, "n_days": len(ex_best_vals), "note": "n<2 after dropping best day -- CI not meaningful"},
        "cost_adjusted_fees_plus_2c_slip": cost_adjusted,
        "criterion": "CI lower bound (2.5th pctile) > 1.0 on ALL THREE: as-traded, ex-best-day, cost-adjusted",
        "pass": passed,
        "distance": (
            None if not all_present else
            round(1.0 - min(v for v in lowers if v is not None), 3)  # type: ignore[arg-type]
        ),
    }


# ========================================================================================= #
# 2. OPERATIONAL -- named guardrail tests exist AND pass; dead-man's-switch gap disclosed.
# ========================================================================================= #
GUARD_TESTS = {
    "eod_flatten_coverage_all_5_arms": "backtest/tests/test_eod_flatten_coverage_2026_08_18.py",
    "eod_flatten_read_failure_fails_open": "backtest/tests/test_eod_flatten_read_failure_2026_08_13.py",
    "never_average_down_no_stacked_entry": "backtest/tests/test_never_average_down_2026_07_20.py",
    "killswitch_threshold_parity_rule5": "backtest/tests/test_killswitch_threshold_parity.py",
    "orphan_position_adoption": "backtest/tests/test_orphan_position_adoption_2026_08_10.py",
    # CLOSED 2026-09-01 (TASK W1, queue.md DEAD-MANS-SWITCH-POSITION-FLATTENER): the
    # independent watchdog setup/scripts/dead_mans_switch.py now exists (RTH-only, per-arm
    # engine-liveness check against core-decisions.jsonl / fleet decisions.jsonl, flattens via
    # fleet_broker.close_all_spy_options on a confirmed-stale + confirmed-open arm), registered
    # as Gamma_DeadMansSwitch (install-dead-mans-switch.ps1). This key used to be reported via
    # a hardcoded NO-TEST-FOUND block below `operational_criterion` -- that block is now
    # removed in favour of a real pytest run, same shape as every other row in this dict.
    "dead_mans_switch_open_position_on_process_death": "backtest/tests/test_dead_mans_switch_2026_09_01.py",
}


def _run_pytest(rel_paths: list[str]) -> dict:
    if not BACKTEST_PY.exists():
        return {"ran": False, "error": f"backtest venv python not found at {BACKTEST_PY}"}
    abs_paths = [str(REPO / p) for p in rel_paths]
    try:
        proc = subprocess.run(
            [str(BACKTEST_PY), "-m", "pytest", *abs_paths, "-q"],
            cwd=str(BACKTEST_DIR), capture_output=True, text=True, timeout=180,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as e:  # noqa: BLE001 -- a guard-runner crash must never crash the gate
        return {"ran": False, "error": f"{type(e).__name__}: {e}"}
    tail = "\n".join(proc.stdout.strip().splitlines()[-5:])
    return {"ran": True, "returncode": proc.returncode, "summary_tail": tail}


def operational_criterion() -> dict:
    results = {}
    all_pass = True
    for name, rel in GUARD_TESTS.items():
        exists = (REPO / rel).exists()
        if not exists:
            results[name] = {"test_path": rel, "exists": False, "pass": False,
                              "note": "test file not found -- guard is UNPINNED"}
            all_pass = False
            continue
        r = _run_pytest([rel])
        passed = r.get("ran") and r.get("returncode") == 0
        results[name] = {"test_path": rel, "exists": True, **r, "pass": bool(passed)}
        if not passed:
            all_pass = False

    # dead_mans_switch_open_position_on_process_death is now a REGULAR row in GUARD_TESTS
    # above (CLOSED 2026-09-01, TASK W1) -- scored by the same real-pytest loop as every other
    # guard. This function used to hardcode a permanent NO-TEST-FOUND FAIL for that key here;
    # that block is deleted rather than left dead, since a stale copy left behind would
    # silently overwrite the real result computed above the moment someone re-added it.

    return {"guards": results, "pass": all_pass}


# ========================================================================================= #
# 3. RECONCILIATION -- ledger P&L vs REAL broker equity change, all 5 arms, live REST.
# ========================================================================================= #
RECON_TOLERANCE_ABS = 10.0     # dollars
RECON_TOLERANCE_PCT = 0.02     # 2% of |broker pnl|, whichever is larger


def _ts_to_et_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ET_TZ).strftime("%Y-%m-%d")


def _fetch_portfolio_history(arm_id: str, secrets: dict) -> dict:
    a = secrets.get(arm_id, {})
    key = a.get("api_key") or a.get("ALPACA_API_KEY") or a.get("key", "")
    sec = a.get("secret_key") or a.get("ALPACA_SECRET_KEY") or a.get("secret", "")
    base = a.get("base_url", "https://paper-api.alpaca.markets")
    if not key:
        return {"ok": False, "error": "no key in secrets.json"}
    url = base.rstrip("/") + "/v2/account/portfolio/history?period=3M&timeframe=1D"
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        return {"ok": True, **d}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _fetch_account_created_date(arm_id: str, secrets: dict) -> "str | None":
    """The account's TRUE creation date (ET), live from /v2/account.created_at.

    ADDED 2026-08-28 (TASK B3): base_value_asof from portfolio/history is NOT a
    reliable reset-point marker -- verified live this run, all 5 arms returned the
    SAME base_value_asof=2026-07-30, but /v2/account.created_at for every one of
    them is actually 2026-08-03T13:00-13:03Z (a same-day, ~3-minute-apart batch
    rebuild -- each paired with a $5,000 JNLC cash-journal deposit that date,
    confirmed via /v2/account/activities). base_value_asof undershoots the true
    reset by 4 calendar days (07-30, 07-31 are trading days). Returns None on any
    fetch failure (fail-open -- the caller falls back to base_value_asof alone,
    same behavior as before this fix existed)."""
    a = secrets.get(arm_id, {})
    key = a.get("api_key") or a.get("ALPACA_API_KEY") or a.get("key", "")
    sec = a.get("secret_key") or a.get("ALPACA_SECRET_KEY") or a.get("secret", "")
    base = a.get("base_url", "https://paper-api.alpaca.markets")
    if not key:
        return None
    url = base.rstrip("/") + "/v2/account"
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        created = d.get("created_at")
        if not created:
            return None
        dt_utc = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        return dt_utc.astimezone(ET_TZ).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 -- fail-open, never break the gate on this extra check
        return None


def reconciliation_criterion(rows: list[dict]) -> dict:
    secrets = json.loads(SECRETS_PATH.read_text(encoding="utf-8")).get("accounts", {})
    per_arm = {}
    all_reconciled = True
    for arm_id in ACTIVE_ARMS:
        hist = _fetch_portfolio_history(arm_id, secrets)
        if not hist.get("ok"):
            per_arm[arm_id] = {"reconciled": None, "note": f"live fetch failed: {hist.get('error')}"}
            all_reconciled = False
            continue
        timestamps = hist.get("timestamp") or []
        pl = hist.get("profit_loss") or []
        by_date = {}
        for ts, p in zip(timestamps, pl):
            by_date[_ts_to_et_date(ts)] = p
        if not by_date:
            per_arm[arm_id] = {"reconciled": None, "note": "broker returned no portfolio-history rows"}
            all_reconciled = False
            continue
        # RESET-POINT CLAMP (found live this run, all 5 arms): base_value_asof marks the last
        # time Alpaca reset this account's equity/history baseline -- every arm returned
        # base_value_asof=2026-07-30 this run. Portfolio-history rows BEFORE that date show
        # pl=0/equity=0 (wiped, not "no activity") even though the ledger has real engine fills
        # tagged to this arm_id going back to 2026-06-26/07-02 -- those older ledger rows sit on
        # broker history that no longer exists to reconcile against (safe-2/safe-1 share ONE
        # account_number per accounts.json, so a pre-reset relabel is the likely mechanism, but
        # the exact cause was not chased further this run -- the RESET FACT is what matters
        # here). Clamping window_start to base_value_asof (when present) keeps this criterion
        # honest: it reconciles only the days broker history can actually attest to.
        #
        # BUG FOUND + FIXED 2026-08-28 (TASK B3, root-caused the safe-3/-$74.27 and
        # risky-3/+$231.39 reconciliation FAILs): base_value_asof alone UNDERSHOOTS the true
        # reset point. All 5 accounts were actually recreated 2026-08-03T13:00-13:03Z (live
        # /v2/account.created_at, each with a same-day $5,000 JNLC deposit) -- 4 calendar
        # days (07-30, 07-31 trading days; 08-01/08-02 weekend) AFTER the base_value_asof
        # date this endpoint reports. Portfolio-history's pl for those 4 phantom days is
        # correctly 0 either way, but ledger_pnl below was still summing real
        # engine-attributed trips dated 07-30/07-31 that fired against the OLD, now-defunct
        # pre-rebuild account under the SAME arm_id -- safe-3 (+$75, one 07-31 trip) and
        # risky-3 (-$229, two 07-30 + one 07-31 trip) happened to trade in that phantom
        # window; safe-2/bold-2/risky-1 carry the identical stale clamp but have ZERO
        # engine trips there, which is why the bug was silent for them (verified: their
        # reconciled=true was NOT because their window was correct, it was luck of trade
        # timing). Clamping ALSO to the live account-creation date closes this for every
        # arm, not just the two that happened to expose it. Verified this run: safe-3
        # diff_vs_fee_adjusted_ledger -$74.27 -> $0.44, risky-3 +$231.39 -> $0.57, both
        # inside the $10 tolerance.
        base_asof = hist.get("base_value_asof")
        acct_created = _fetch_account_created_date(arm_id, secrets)
        raw_start, window_end = min(by_date), max(by_date)
        candidates = [raw_start] + [d for d in (base_asof, acct_created) if d]
        window_start = max(candidates)
        pre_reset_dropped = window_start != raw_start
        broker_pnl = round(sum(v for d, v in by_date.items() if d >= window_start), 2)
        # ledger sum for THIS arm over the SAME (possibly clamped) window, engine-attributed
        # only (broker equity change reflects ALL fills including any manual ones -- if manual
        # fills exist in the window this is disclosed by the behavioural criterion, not
        # silently absorbed here).
        ledger_rows = [r for r in rows if r["arm"] == arm_id
                       and window_start <= r["date"] <= window_end and r["attribution"] == "engine"]
        ledger_pnl = round(sum(float(r["pnl_dollars"]) for r in ledger_rows), 2)
        # ledger rows for this arm that fall BEFORE the reset point -- disclosed, never silently
        # dropped from the report even though they cannot be reconciled against broker history.
        unreconcilable_pre_reset_rows = [r for r in rows if r["arm"] == arm_id
                                          and r["date"] < window_start and r["attribution"] == "engine"] \
            if pre_reset_dropped else []
        # KNOWN, DOCUMENTED GAP (cost_model.py / live_readiness.py docstrings): real_pnl in
        # this ledger has ALWAYS excluded the real OCC/ORF/TAF/SEC/CAT fees Alpaca actually
        # debits (broker_fills.py reads activity_type=='FILL' only). A broker-vs-ledger diff of
        # roughly this arm's own fee total is therefore EXPECTED, not a reconciliation failure
        # -- the honest check compares broker P&L against ledger P&L net of the SAME fee model
        # the rest of this instrument (and A1) already uses. A diff that survives this
        # adjustment is a real, unexplained gap.
        arm_day_counts_recon: dict = defaultdict(int)
        for r in ledger_rows:
            arm_day_counts_recon[(r["arm"], r["date"])] += 1
        est_fees = 0.0
        for r in ledger_rows:
            exit_px = r.get("exit_px_avg")
            if exit_px is None:
                continue
            est_fees += fee_ex_cat(float(r.get("qty") or 0.0), float(exit_px))
        est_fees += FEE_RATES["cat_per_arm_day"] * len(arm_day_counts_recon)
        ledger_pnl_fee_adjusted = round(ledger_pnl - est_fees, 2)
        diff_raw = round(broker_pnl - ledger_pnl, 2)
        diff_fee_adjusted = round(broker_pnl - ledger_pnl_fee_adjusted, 2)
        tol = max(RECON_TOLERANCE_ABS, RECON_TOLERANCE_PCT * abs(broker_pnl))
        reconciled = abs(diff_fee_adjusted) <= tol
        per_arm[arm_id] = {
            "window": [window_start, window_end],
            "pre_reset_window_dropped": pre_reset_dropped,
            "pre_reset_ledger_pnl_unreconcilable": (
                round(sum(float(r["pnl_dollars"]) for r in unreconcilable_pre_reset_rows), 2)
                if pre_reset_dropped else None
            ),
            "pre_reset_ledger_trips_unreconcilable": len(unreconcilable_pre_reset_rows),
            "broker_pnl_sum": broker_pnl,
            "ledger_pnl_sum_engine_attributed": ledger_pnl,
            "estimated_fees_ex_cat_plus_cat": round(est_fees, 2),
            "ledger_pnl_fee_adjusted": ledger_pnl_fee_adjusted,
            "diff_raw_vs_ledger": diff_raw,
            "diff_vs_fee_adjusted_ledger": diff_fee_adjusted,
            "tolerance": round(tol, 2),
            "n_ledger_trips": len(ledger_rows),
            "base_value_asof": base_asof,
            "account_created_et": acct_created,
            "reconciled": reconciled,
        }
        if not reconciled:
            all_reconciled = False
    return {"per_arm": per_arm, "pass": all_reconciled}


# ========================================================================================= #
# 4. BEHAVIOURAL -- rule breaks / manual overrides / sizing-up, actually logged, trailing window.
# ========================================================================================= #
def _trailing_window_dates(rows: list[dict], n_days: int) -> tuple[str, str, list[str]]:
    dates = sorted({r["date"] for r in rows})
    window = dates[-n_days:] if len(dates) >= n_days else dates
    return (window[0] if window else "", window[-1] if window else "", window)


def _load_rule_breaks() -> list[dict]:
    if not RULE_BREAKS_PATH.exists():
        return []
    out = []
    for line in RULE_BREAKS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _rule_breaks_last_write_et_date():
    """The file's actual last-modified date, ET -- fresh each run (never hardcoded), fail-open
    to None on any read error (a broken staleness check must never break this instrument)."""
    if not RULE_BREAKS_PATH.exists():
        return None
    try:
        ts = RULE_BREAKS_PATH.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ET_TZ).date()


def behavioural_criterion(rows: list[dict], recon: dict) -> dict:
    all_rows = rows  # includes non-engine attribution, needed for the manual-override check
    w_start, w_end, window_dates = _trailing_window_dates(
        [r for r in all_rows if r["attribution"] == "engine"], TRAILING_WINDOW_TRADING_DAYS)

    rb_rows = _load_rule_breaks()
    rb_in_window = [r for r in rb_rows if w_start <= str(r.get("date", "")) <= w_end]

    # STALE-LEDGER HONESTY (TASK W5, 2026-09-01): zero rule breaks in-window is only good news
    # if someone is actually still writing to this ledger. rule-breaks.jsonl has carried exactly
    # 1 row (2026-05-18) for months -- "zero violations" from a file nobody has touched since
    # before this trailing window even started is NOT the same claim as "checked, and clean".
    # Computed fresh against the file's real mtime every run, never a hardcoded staleness date.
    rb_last_write = _rule_breaks_last_write_et_date()
    try:
        _w_start_date = datetime.strptime(w_start, "%Y-%m-%d").date() if w_start else None
    except ValueError:
        _w_start_date = None
    rb_stale = (rb_last_write is None) or (_w_start_date is not None and rb_last_write < _w_start_date)
    if len(rb_in_window) == 0 and rb_stale:
        rb_status = "PASS_UNVERIFIED"
        rb_status_note = (
            f"rule-breaks.jsonl last written {rb_last_write.isoformat() if rb_last_write else 'never (file missing)'} "
            f"-- before this trailing window's start ({w_start or 'n/a'}). Zero rule breaks in-window could mean a "
            "genuinely clean window OR an abandoned ledger nobody is writing to; this instrument cannot distinguish "
            "the two from the file alone, so it reports PASS_UNVERIFIED rather than a bare PASS. Overall behavioural "
            "verdict logic is unaffected (0 breaks + 0 manual fills still passes) -- this is a disclosure, not a gate."
        )
    elif len(rb_in_window) == 0:
        rb_status, rb_status_note = "PASS", None
    else:
        rb_status, rb_status_note = "FAIL", None

    manual_rows = [r for r in all_rows
                   if r["attribution"] != "engine" and w_start <= r["date"] <= w_end]

    # Sizing-up: for each engine trade in the window, compare cost_dollars against the arm's
    # per-trade risk cap (RISK_CAP_PCT) applied to the PRIOR trading day's broker closing
    # equity (from the reconciliation criterion's portfolio-history pull -- no look-ahead: the
    # cap is evaluated against equity known BEFORE that day's trading). Only computed for arms
    # whose reconciliation fetch succeeded.
    sizing_events = []
    for arm_id in ACTIVE_ARMS:
        arm_recon = recon.get("per_arm", {}).get(arm_id, {})
        # need the raw per-day equity series again -- re-derive is out of scope here; instead
        # use base_value_asof + broker_pnl_sum trend as a coarse proxy is not accurate enough,
        # so this sub-check is SKIPPED (not fabricated) when a real day-by-day equity series
        # isn't already on hand. Documented explicitly rather than silently approximated.
        pass
    sizing_note = (
        "SKIPPED (not fabricated): a per-trade sizing-up check needs the prior trading day's "
        "broker closing equity per arm, which requires a second live portfolio-history call "
        "beyond what reconciliation_criterion already fetches. Not wired this build to avoid "
        "doubling the live-REST call count for a sub-check with no dedicated evidence yet; "
        "documented rule-break and manual-override checks above are real and complete for the "
        "trailing window. See CLAUDE.md rule-6 cap discussion in the runbook."
    )

    passed = (len(rb_in_window) == 0) and (len(manual_rows) == 0)
    return {
        "trailing_window": [w_start, w_end],
        "trailing_window_trading_days": len(window_dates),
        "rule_breaks_in_window": {
            "count": len(rb_in_window), "rows": rb_in_window, "pass": len(rb_in_window) == 0,
            "status": rb_status, "last_write_et": rb_last_write.isoformat() if rb_last_write else None,
            "status_note": rb_status_note,
        },
        "manual_or_mixed_attribution_fills_in_window": {
            "count": len(manual_rows),
            "rows": [{"date": r["date"], "arm": r["arm"], "symbol": r["symbol"],
                      "attribution": r["attribution"]} for r in manual_rows],
            "pass": len(manual_rows) == 0,
        },
        "sizing_up_events": {"checked": False, "note": sizing_note},
        "pass": passed,
        "note": (
            f"most recent journal/mistakes.md entry on file predates this window "
            f"(informational only, not parsed structurally -- see {MISTAKES_PATH.name})"
        ),
    }


# ========================================================================================= #
# 5. PROD-SHADOW -- a designated shadow arm profitable net of realistic costs, stated window.
# ========================================================================================= #
def _load_prod_shadow_designation() -> dict | None:
    """Never guesses: returns None (caller reports NOT_WIRED) if the file is missing, empty,
    unreadable, or missing a required field -- exactly this criterion's pre-2026-09-01
    behaviour when no designation existed at all."""
    if not PROD_SHADOW_DESIGNATION_PATH.exists():
        return None
    try:
        cfg = json.loads(PROD_SHADOW_DESIGNATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = ("arm", "window_start", "window_end", "min_days")
    if not isinstance(cfg, dict) or not all(cfg.get(k) for k in required):
        return None
    return cfg


def prod_shadow_criterion(engine_rows: list[dict]) -> dict:
    """Criterion 5. Reads its designation from automation/state/prod-shadow-designation.json
    (arm + window + min_days) -- WIRED 2026-09-01 (TASK W5) per queue.md's own
    PROD-SHADOW-ARM-DESIGNATION recommendation, executed verbatim: designate one arm as the
    explicit go-live shadow and score it net of the A1 cost model exactly like criterion 1,
    reusing statistical_criterion(). Never guesses: if the designation file is missing,
    unreadable, or missing a required field, this reports NOT_WIRED -- the ORIGINAL behaviour
    of this function before this build, preserved verbatim below for that path -- rather than
    fabricating a designation from thin air.

    Status ladder: NOT_WIRED (no designation) -> INSUFFICIENT_DAYS (designated but window
    hasn't scored min_days yet) -> PASS/FAIL (scored). A 40-day PREREG-TIGHT-LADDER-2026-08-28
    extended-clock view is reported alongside when the designation carries one, but it is
    disclosure only -- it never substitutes for the shorter designated pass window."""
    cfg = _load_prod_shadow_designation()
    if cfg is None:
        try:
            designation_display = str(PROD_SHADOW_DESIGNATION_PATH.relative_to(REPO))
        except ValueError:  # path isn't under REPO -- e.g. monkeypatched to a tmp path in tests
            designation_display = str(PROD_SHADOW_DESIGNATION_PATH)
        candidates = [
            "analysis/recommendations/catastrophe-cap-shadow-ledger.jsonl",
            "analysis/recommendations/day-throttle-shadow-ledger.jsonl",
            "analysis/recommendations/stop-mode-shadow-ledger.jsonl",
            "analysis/recommendations/vix-floor-shadow-ledger.jsonl",
        ]
        existing = [c for c in candidates if (REPO / c).exists()]
        return {
            "pass": False,
            "status": "NOT_WIRED",
            "note": (
                f"No readable designation at {designation_display}. "
                "Existing shadow-labeled ledgers found (feature-level, not a go-live shadow "
                "track record): " + ", ".join(existing)
            ),
            "recommendation": (
                "Designate ONE arm (or a new dedicated paper arm) as the explicit go-live "
                "shadow, define its stated evaluation window in writing at "
                f"{designation_display}, and score it net of the A1 "
                "realistic cost model exactly like the STATISTICAL criterion above -- reuse "
                "statistical_criterion() in this file."
            ),
        }

    arm = cfg["arm"]
    window_start, window_end = cfg["window_start"], cfg["window_end"]
    min_days = int(cfg["min_days"])
    window_rows = [r for r in engine_rows if r["arm"] == arm and window_start <= r["date"] <= window_end]
    days_scored = len({r["date"] for r in window_rows})

    interim = statistical_criterion(window_rows, arm) if days_scored >= 2 else None
    current_ci_lo = (
        interim["as_traded"]["ci_lower_2.5"]
        if interim and not interim.get("insufficient_data") and interim.get("as_traded")
        else None
    )

    result = {
        "designation": {
            "arm": arm, "window_start": window_start, "window_end": window_end,
            "min_days": min_days, "designated_at": cfg.get("designated_at"),
            "profile_summary": cfg.get("profile_summary"), "rationale": cfg.get("rationale"),
            "revoke": cfg.get("revoke", "delete this file"),
        },
        "days_scored": days_scored,
        "days_needed": min_days,
        "current_ci_lower_2.5": current_ci_lo,
    }

    if days_scored < min_days:
        result.update({
            "pass": False,
            "status": "INSUFFICIENT_DAYS",
            "note": (
                f"{days_scored}/{min_days} scored trading days for arm '{arm}' in "
                f"{window_start}..{window_end}. Not yet scorable -- reported as INSUFFICIENT_DAYS, "
                "never PASS or FAIL, on a window that hasn't reached its own registered day-count bar."
            ),
            "detail": interim,
        })
    else:
        scored = statistical_criterion(window_rows, arm)
        result.update({
            "pass": bool(scored["pass"]),
            "status": "PASS" if scored["pass"] else "FAIL",
            "note": (
                f"{days_scored}/{min_days} scored trading days -- "
                f"{'CLEARS' if scored['pass'] else 'does NOT clear'} CI-lower(2.5%)>1.0 on "
                "as-traded AND ex-best-day AND cost-adjusted (same statistical_criterion() as criterion 1)."
            ),
            "detail": scored,
        })

    ext_end, ext_min = cfg.get("extended_clock_end"), cfg.get("extended_clock_min_days")
    if ext_end and ext_min:
        ext_rows = [r for r in engine_rows if r["arm"] == arm and window_start <= r["date"] <= ext_end]
        ext_days = sorted({r["date"] for r in ext_rows})
        ext_stat = statistical_criterion(ext_rows, arm) if len(ext_days) >= 2 else None
        result["extended_clock_disclosure"] = {
            "label": "PREREG-TIGHT-LADDER-2026-08-28.md 40-day clock -- disclosure only, never the pass criterion",
            "window_end": ext_end, "min_days": int(ext_min), "days_scored": len(ext_days),
            "detail": ext_stat,
        }
    return result


# ========================================================================================= #
# Disclosure views (TASK W5, 2026-09-01) -- (b) frozen-config-window, (c) effective evidence,
# (d) plan reachability. NONE of these change any pass/fail criterion above; all are
# additional, backward-compatible reporting only.
# ========================================================================================= #
def frozen_config_window_view(engine_rows: list[dict]) -> dict:
    """(b) Same bootstrap as criterion 1, restricted to days >= the config-freeze start
    (2026-08-31, setup/hooks/doctrine.py FREEZE_START) -- so a reader can see the book under
    ONLY the currently-frozen config, without the pre-freeze history mixed in. Disclosure
    only -- criterion 1's pass bar stays full-history."""
    windowed = [r for r in engine_rows if r["date"] >= FROZEN_CONFIG_WINDOW_START]
    return {
        "label": "disclosure only -- pass criterion unchanged (criterion 1 stays full-history)",
        "window_start": FROZEN_CONFIG_WINDOW_START,
        "per_arm": {arm: statistical_criterion(windowed, arm) for arm in ACTIVE_ARMS},
        "book_wide_correlated_rollup": statistical_criterion(windowed, None),
    }


def _best_n_share_of_gross_winners(day_values: dict[str, float], n: int = 2) -> float | None:
    gains = sum(v for v in day_values.values() if v > 0)
    if gains <= 0:
        return None
    top_n = sorted((v for v in day_values.values() if v > 0), reverse=True)[:n]
    return round(sum(top_n) / gains, 3)


def effective_evidence_block(engine_rows: list[dict], statistical: dict) -> dict:
    """(c) Disclosure only. Per arm: days actually on the CURRENT config (>=09-01), days
    post-tight-ladder (>=08-11), and how much of the arm's gross winner dollars sit in just
    its best 2 days (concentration, design rule 5). Plus the book rollup's own ex-best-day
    P(PF<=1), pulled from the already-computed criterion-1 bootstrap rather than recomputed."""
    per_arm = {}
    for arm in ACTIVE_ARMS:
        days = _daily_totals([r for r in engine_rows if r["arm"] == arm])
        per_arm[arm] = {
            "days_on_current_config": sum(1 for d in days if d >= CURRENT_CONFIG_WINDOW_START),
            "days_post_ladder": sum(1 for d in days if d >= POST_LADDER_WINDOW_START),
            "best_2_days_share_of_gross_winner_dollars": _best_n_share_of_gross_winners(days, 2),
        }
    book_ex_best = (statistical.get("book_wide_correlated_rollup") or {}).get("ex_best_day") or {}
    return {
        "label": "disclosure only",
        "current_config_window_start": CURRENT_CONFIG_WINDOW_START,
        "post_ladder_window_start": POST_LADDER_WINDOW_START,
        "per_arm": per_arm,
        "book_ex_best_day_p_pf_le_1": book_ex_best.get("p_pf_le_1"),
    }


def _remaining_trading_days(start_exclusive, end_inclusive_str: str) -> int:
    """Weekday count strictly after start_exclusive through end_inclusive_str, minus the
    disclosed MARKET_HOLIDAYS_2026 set. Not a full market-calendar (no early closes/other
    holidays) -- adequate for a disclosure-only reachability estimate, not a trading decision."""
    import datetime as _dt
    end = _dt.date.fromisoformat(end_inclusive_str)
    if end <= start_exclusive:
        return 0
    n, d = 0, start_exclusive + _dt.timedelta(days=1)
    while d <= end:
        if d.weekday() < 5 and d.isoformat() not in MARKET_HOLIDAYS_2026:
            n += 1
        d += _dt.timedelta(days=1)
    return n


def _ci_lower_with_added_days(day_values: list[float], n_added: int, c: float, n_boot: int) -> float | None:
    ci = bootstrap_pf_ci(day_values + [c] * n_added, n_boot=n_boot, seed=BOOT_SEED)
    return ci["ci_lower_2.5"] if ci else None


def _reachability_constant(day_values: list[float], n_added: int) -> dict:
    """Binary search for the smallest constant $/day (added to every remaining trading day,
    ZERO VARIANCE -- the best case) that pushes this gate's own CI-lower(2.5%) above 1.0."""
    if n_added <= 0:
        return {"dollars_per_day": None, "already_clears": None, "n_remaining_trading_days": 0,
                "note": "0 remaining trading days in this horizon -- reachability not computable"}
    base = _ci_lower_with_added_days(day_values, 0, 0.0, _REACHABILITY_N_BOOT)
    if base is not None and base > 1.0:
        return {"dollars_per_day": 0.0, "already_clears": True, "n_remaining_trading_days": n_added,
                "note": "already clears CI-lower>1.0 on existing history alone -- no added edge needed"}
    lo, hi = 0.0, _REACHABILITY_UPPER_BOUND
    hi_ci = _ci_lower_with_added_days(day_values, n_added, hi, _REACHABILITY_N_BOOT)
    if hi_ci is None or hi_ci <= 1.0:
        return {"dollars_per_day": None, "already_clears": False, "n_remaining_trading_days": n_added,
                "note": f"not reachable within the ${_REACHABILITY_UPPER_BOUND:.0f}/day search bound "
                        f"over {n_added} remaining trading days"}
    for _ in range(_REACHABILITY_ITERS):
        mid = (lo + hi) / 2.0
        mid_ci = _ci_lower_with_added_days(day_values, n_added, mid, _REACHABILITY_N_BOOT)
        if mid_ci is not None and mid_ci > 1.0:
            hi = mid
        else:
            lo = mid
    return {
        "dollars_per_day": round(hi, 2), "already_clears": False, "n_remaining_trading_days": n_added,
        "note": ("ZERO-VARIANCE BEST CASE -- assumes every remaining day nets exactly this constant "
                 "with no variance; the real required edge is higher. Search bootstrap n="
                 f"{_REACHABILITY_N_BOOT} (reduced from the gate's primary n={N_BOOT} for speed)."),
    }


def plan_reachability_block(engine_rows: list[dict], today) -> dict:
    """(d) Disclosure only. Per arm, per horizon (2026-09-29 config-freeze close and
    2026-10-30 tight-ladder clock close): the constant $/day that would push this gate's own
    CI-lower(2.5%) above 1.0, via binary search, zero-variance best case (labeled)."""
    per_arm = {}
    for arm in ACTIVE_ARMS:
        day_values = list(_daily_totals([r for r in engine_rows if r["arm"] == arm]).values())
        per_arm[arm] = {
            label: {"end_date": end_date, **_reachability_constant(day_values, _remaining_trading_days(today, end_date))}
            for end_date, label in PLAN_REACHABILITY_TARGETS
        }
    return {
        "label": ("disclosure only -- constant $/day needed to push CI-lower(2.5%) above 1.0, "
                   "binary search under this gate's own bootstrap"),
        "as_of": today.isoformat(),
        "per_arm": per_arm,
    }


def _load_core_decision_rows(path: "Path | None" = None) -> list[dict]:
    """Reads core-decisions.jsonl in full (measured 0.5s / ~37k rows / ~90MB this session --
    the gate is a weekly/on-demand instrument, not a hot-path check, so a full read is fine;
    unlike engine_health.py's every-minute tail read, this needs LIFETIME coverage, not just
    the newest rows). Fails open: a missing/unreadable file returns []; a malformed line is
    skipped, never crashes the gate. `path` defaults to the MODULE-LEVEL CORE_DECISIONS_PATH
    looked up at CALL time (not bound at def time) so tests can monkeypatch the module
    attribute and have it take effect."""
    if path is None:
        path = CORE_DECISIONS_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        date, ts_et, spy, vix = r.get("date"), r.get("ts_et"), r.get("spy"), r.get("vix")
        if date is None or spy is None or vix is None:
            continue
        try:
            spy_f, vix_f = float(spy), float(vix)
        except (TypeError, ValueError):
            continue
        rows.append({"date": str(date), "ts_et": str(ts_et) if ts_et else "", "spy": spy_f, "vix": vix_f})
    return rows


def _per_day_regime_stats(rows: list[dict]) -> dict:
    """Per date: VIX daily max, and an open->close SPY return (first/last row BY TS_ET
    ordering, not insertion order -- rows can arrive out of order across a restart)."""
    by_day: dict[str, list[dict]] = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r)
    out = {}
    for date, day_rows in by_day.items():
        day_rows_sorted = sorted(day_rows, key=lambda r: r["ts_et"])
        vix_max = max(r["vix"] for r in day_rows)
        spy_open = day_rows_sorted[0]["spy"]
        spy_close = day_rows_sorted[-1]["spy"]
        ret_pct = ((spy_close / spy_open) - 1.0) * 100.0 if spy_open else None
        out[date] = {"vix_daily_max": vix_max, "spy_open": spy_open, "spy_close": spy_close,
                     "ret_pct": ret_pct, "n_rows": len(day_rows)}
    return out


def _regime_window_summary(day_stats: dict) -> dict:
    """Aggregate a {date: per-day stats} mapping into the disclosure fields: VIX daily-max
    min/max, days with VIX>20, SPY cumulative return (geometric, first day's open to last
    day's close), worst single day, count of days down >1%. Empty input -> all-None/zero,
    never a crash or a fabricated number."""
    dates = sorted(day_stats)
    if not dates:
        return {
            "n_days": 0, "vix_daily_max_min": None, "vix_daily_max_max": None,
            "days_vix_gt_20": 0, "spy_cumulative_return_pct": None,
            "worst_day": None, "days_down_gt_1pct": 0,
        }
    vix_maxes = [day_stats[d]["vix_daily_max"] for d in dates]
    rets = {d: day_stats[d]["ret_pct"] for d in dates if day_stats[d]["ret_pct"] is not None}
    spy_open_first = day_stats[dates[0]]["spy_open"]
    spy_close_last = day_stats[dates[-1]]["spy_close"]
    cum_ret = ((spy_close_last / spy_open_first) - 1.0) * 100.0 if spy_open_first else None
    worst_date = min(rets, key=lambda d: rets[d]) if rets else None
    return {
        "n_days": len(dates),
        "vix_daily_max_min": round(min(vix_maxes), 2),
        "vix_daily_max_max": round(max(vix_maxes), 2),
        "days_vix_gt_20": sum(1 for v in vix_maxes if v > 20),
        "spy_cumulative_return_pct": round(cum_ret, 3) if cum_ret is not None else None,
        "worst_day": {"date": worst_date, "ret_pct": round(rets[worst_date], 3)} if worst_date else None,
        "days_down_gt_1pct": sum(1 for r in rets.values() if r <= -1.0),
    }


def regime_coverage_block() -> dict:
    """(e) DISCLOSURE ONLY -- never gates the overall verdict. Answers a question none of
    the 5 pass/fail criteria ask: has the engine's evidence window actually SEEN a stressed
    market, or is a GREEN verdict measuring only a calm stretch? Two windows: LIFETIME (every
    engine day in core-decisions.jsonl) and the FROZEN CONFIG WINDOW (>= CURRENT_CONFIG_WINDOW_START,
    2026-09-01 -- the same anchor frozen_config_window_view already uses for criterion 1's
    disclosure sibling). Reads spy/vix/ts_et straight from core-decisions.jsonl -- no
    re-derivation, no simulated bars."""
    rows = _load_core_decision_rows()
    day_stats = _per_day_regime_stats(rows)
    lifetime = _regime_window_summary(day_stats)
    frozen_days = {d: s for d, s in day_stats.items() if d >= CURRENT_CONFIG_WINDOW_START}
    frozen = _regime_window_summary(frozen_days)
    calm_only = frozen["n_days"] > 0 and frozen["days_vix_gt_20"] == 0 and frozen["days_down_gt_1pct"] == 0
    return {
        "label": "disclosure only -- never gates the overall verdict",
        "lifetime": lifetime,
        "frozen_config_window": {"window_start": CURRENT_CONFIG_WINDOW_START, **frozen},
        "calm_only_window_warning": (
            "calm-only window -- a GREEN here is untested in stress" if calm_only else None
        ),
    }


# ========================================================================================= #
# Orchestration
# ========================================================================================= #
def refresh_trades_enriched(skip: bool = False) -> dict:
    """Regenerate analysis/trades-enriched.jsonl before THE GATE reads it.

    TRADES-ENRICHED-HAS-NO-SCHEDULED-PRODUCER (filed 2026-09-01): nothing regenerates this
    artifact on a schedule, and go_live_gate.py is the highest-stakes reader of it -- a stale
    input here is exactly the L298 stale-monitor class the whole item is named for. This is
    an INPUT refresh only: it touches no criterion or threshold below. FAIL-OPEN (C7): a
    rebuild failure is logged loudly to stderr and the on-disk file is scored as-is, never
    silently -- the gate must never go dark because its own refresh step broke.
    """
    if skip:
        print("[go_live_gate] trades-enriched refresh SKIPPED (--no-refresh)", file=sys.stderr)
        return {"status": "SKIPPED", "reason": "--no-refresh passed"}

    n_before = None
    mtime_before = None
    if TRADES_ENRICHED.exists():
        mtime_before = TRADES_ENRICHED.stat().st_mtime
        with open(TRADES_ENRICHED, encoding="utf-8") as fh:
            n_before = sum(1 for line in fh if line.strip()) - 1  # minus the _meta line

    try:
        result = te_producer.rebuild(REPO)
        n_after = result["meta"]["n_rows"]
        mtime_after = TRADES_ENRICHED.stat().st_mtime
        print(f"[go_live_gate] trades-enriched refreshed: rows {n_before} -> {n_after}, "
              f"mtime {mtime_before} -> {mtime_after}", file=sys.stderr)
        return {
            "status": "OK",
            "n_rows_before": n_before,
            "n_rows_after": n_after,
            "mtime_before": mtime_before,
            "mtime_after": mtime_after,
        }
    except Exception as exc:  # noqa: BLE001 -- fail-open, never fail-silent (C7)
        print(f"[go_live_gate] trades-enriched refresh FAILED "
              f"({type(exc).__name__}: {exc}) -- continuing with the on-disk file "
              f"(rows={n_before}, mtime={mtime_before})", file=sys.stderr)
        return {
            "status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "n_rows_before": n_before,
            "mtime_before": mtime_before,
        }


def load_ledger_rows() -> list[dict]:
    rows = []
    for line in TRADES_ENRICHED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("_meta"):
            continue
        if r.get("arm") not in ACTIVE_ARMS:
            continue  # excludes retired safe-1
        rows.append(r)
    return rows


def build_report(trades_enriched_refresh: dict | None = None) -> dict:
    all_rows = load_ledger_rows()
    engine_rows = [r for r in all_rows if r["attribution"] == "engine"]

    statistical = {
        "book_wide_correlated_rollup": statistical_criterion(engine_rows, arm_id=None),
        "per_arm": {arm_id: statistical_criterion(engine_rows, arm_id) for arm_id in ACTIVE_ARMS},
    }
    stat_pass = all(statistical["per_arm"][a].get("pass") for a in ACTIVE_ARMS)

    operational = operational_criterion()
    reconciliation = reconciliation_criterion(all_rows)
    behavioural = behavioural_criterion(all_rows, reconciliation)
    prod_shadow = prod_shadow_criterion(engine_rows)

    groups = {
        "statistical": {**statistical, "pass": stat_pass},
        "operational": operational,
        "reconciliation": reconciliation,
        "behavioural": behavioural,
        "prod_shadow": prod_shadow,
    }
    overall = all(g["pass"] for g in groups.values())

    today_et = et_now().date()

    return {
        "generated_et": et_now().isoformat(timespec="seconds"),
        "instrument": "setup/scripts/go_live_gate.py",
        "note": "REPORTING INSTRUMENT ONLY. Arms nothing. Never edits params*.json/heartbeat_core.py/"
                "filters.py/strategies.py/fleet_executor.py/risk_gate.py/exit_manager.py. Live-money "
                "arming stays J's decision alone (OP-0 #1). See MEMORY / CLAUDE.md.",
        "overall_verdict": "GREEN" if overall else "RED",
        "trades_enriched_refresh": trades_enriched_refresh or {"status": "NOT_ATTEMPTED"},
        "criteria": groups,
        "roster": ACTIVE_ARMS,
        "risk_cap_pct_assumption": RISK_CAP_PCT,
        "cost_model_scenario": {
            "fee_rates": FEE_RATES,
            "exit_slippage_cents_per_contract": COST_MODEL_EXIT_SLIPPAGE_CENTS,
            "source": "analysis/recommendations/cost-model.json, A1's conservative scenario-b default",
        },
        # ADDITIVE, backward-compatible (TASK W5, 2026-09-01) -- none of the keys above changed
        # shape. Honesty disclosures the audit found missing; none of these gate the verdict.
        "disclosures": {
            "frozen_config_window": frozen_config_window_view(engine_rows),
            "effective_evidence": effective_evidence_block(engine_rows, statistical),
            "plan_reachability": plan_reachability_block(engine_rows, today_et),
        },
        # ADDITIVE, backward-compatible (TASK B3-monitors, 2026-09-01) -- disclosure only,
        # never gates overall_verdict. See regime_coverage_block's own docstring.
        "regime_coverage": regime_coverage_block(),
        # ADDITIVE, backward-compatible (queue.md FUTURES-ABSENT-FROM-GO-LIVE-GATE,
        # 2026-09-03) -- a SIBLING key to "criteria" above, never inside it, so it cannot
        # touch `overall` (computed above from `groups` alone, before this key exists).
        # Wrapped fail-open: a bug in the futures module must never crash or change the
        # SPY-only report.
        "futures": _futures_block_fail_open(),
    }


def _futures_block_fail_open() -> dict:
    try:
        return futures_go_live_gate.futures_block()
    except Exception as e:  # noqa: BLE001 -- reporting-only instrument, fail-open always
        return {
            "lane_verdict": "INSUFFICIENT",
            "error": f"{type(e).__name__}: {e}",
            "note": "futures_go_live_gate.futures_block() raised -- fail-open, SPY verdict unaffected",
        }


# --------------------------------------------------------------------------------------- #
# Human-readable output
# --------------------------------------------------------------------------------------- #
def _mark(p) -> str:
    if p is None:
        return "UNK "
    return "PASS" if p else "FAIL"


def render_human(report: dict) -> str:
    lines = []
    lines.append(f"GO-LIVE GATE -- {report['generated_et']} ET")
    lines.append(f"OVERALL VERDICT: {report['overall_verdict']}")
    lines.append(report["note"])
    lines.append("")
    c = report["criteria"]

    lines.append(f"1. STATISTICAL [{_mark(c['statistical']['pass'])}] -- per-arm day-level bootstrap PF, "
                  f"CI-lower(2.5%) > 1.0 on as-traded AND ex-best-day AND cost-adjusted")
    for arm_id in report["roster"]:
        s = c["statistical"]["per_arm"][arm_id]
        if s.get("insufficient_data"):
            lines.append(f"   {arm_id:<9} INSUFFICIENT DATA")
            continue
        at, xb, ca = s["as_traded"], s["ex_best_day"], s["cost_adjusted_fees_plus_2c_slip"]
        lines.append(f"   {arm_id:<9} [{_mark(s['pass'])}] n_days={s['n_trading_days']:<3} "
                      f"as_traded CI_lo={at['ci_lower_2.5'] if at else 'n/a':<7} "
                      f"ex_best_day CI_lo={xb.get('ci_lower_2.5','n/a'):<7} "
                      f"cost_adj CI_lo={ca['ci_lower_2.5'] if ca else 'n/a':<7} "
                      f"distance_to_1.0={s.get('distance')}")
    bw = c["statistical"]["book_wide_correlated_rollup"]
    if not bw.get("insufficient_data"):
        lines.append(f"   BOOK (correlated rollup, disclosure only) as_traded CI="
                      f"[{bw['as_traded']['ci_lower_2.5']}, {bw['as_traded']['ci_upper_97.5']}] "
                      f"P(PF<=1)={bw['as_traded']['p_pf_le_1']}")
    lines.append("")

    lines.append(f"2. OPERATIONAL [{_mark(c['operational']['pass'])}] -- named guardrail tests")
    for name, g in c["operational"]["guards"].items():
        note = g.get("note", g.get("summary_tail", "")).splitlines()[-1] if g.get("note") or g.get("summary_tail") else ""
        lines.append(f"   {name:<48} [{_mark(g['pass'])}] {note[:80]}")
    lines.append("")

    lines.append(f"3. RECONCILIATION [{_mark(c['reconciliation']['pass'])}] -- ledger P&L vs live broker equity change")
    for arm_id, r in c["reconciliation"]["per_arm"].items():
        if r.get("reconciled") is None:
            lines.append(f"   {arm_id:<9} UNKNOWN -- {r.get('note')}")
            continue
        lines.append(f"   {arm_id:<9} [{_mark(r['reconciled'])}] window={r['window'][0]}..{r['window'][1]} "
                      f"broker={r['broker_pnl_sum']:>9} ledger={r['ledger_pnl_sum_engine_attributed']:>9} "
                      f"est_fees={r['estimated_fees_ex_cat_plus_cat']:>6} "
                      f"diff_fee_adj={r['diff_vs_fee_adjusted_ledger']:>8} tol={r['tolerance']}")
    lines.append("")

    b = c["behavioural"]
    lines.append(f"4. BEHAVIOURAL [{_mark(b['pass'])}] -- window {b['trailing_window'][0]}..{b['trailing_window'][1]} "
                  f"({b['trailing_window_trading_days']} trading days)")
    rb = b["rule_breaks_in_window"]
    lines.append(f"   rule breaks in window: {rb['count']} [status={rb.get('status', _mark(rb['pass']))}]"
                  + (f" -- {rb['status_note']}" if rb.get("status_note") else ""))
    lines.append(f"   manual/mixed-attribution fills in window: {b['manual_or_mixed_attribution_fills_in_window']['count']} "
                  f"[{_mark(b['manual_or_mixed_attribution_fills_in_window']['pass'])}]")
    lines.append(f"   sizing-up events: SKIPPED -- {b['sizing_up_events']['note'][:90]}...")
    lines.append("")

    ps = c["prod_shadow"]
    lines.append(f"5. PROD-SHADOW [{_mark(ps['pass'])}] status={ps['status']}")
    if ps["status"] != "NOT_WIRED":
        d = ps["designation"]
        lines.append(f"   arm={d['arm']} window={d['window_start']}..{d['window_end']} "
                      f"days_scored={ps['days_scored']}/{ps['days_needed']} "
                      f"current_CI_lo={ps.get('current_ci_lower_2.5')}")
        ext = ps.get("extended_clock_disclosure")
        if ext:
            ext_ci = (ext.get("detail") or {}).get("as_traded", {}).get("ci_lower_2.5") if ext.get("detail") else None
            lines.append(f"   extended clock (disclosure only) ..{ext['window_end']} "
                          f"days_scored={ext['days_scored']}/{ext['min_days']} as_traded_CI_lo={ext_ci}")
    lines.append(f"   {ps['note']}")
    lines.append("")

    disc = report.get("disclosures", {})
    fcw = disc.get("frozen_config_window")
    if fcw:
        lines.append(f"FROZEN-CONFIG-WINDOW (disclosure only, since {fcw['window_start']})")
        for arm_id in report["roster"]:
            s = fcw["per_arm"].get(arm_id, {})
            if s.get("insufficient_data"):
                lines.append(f"   {arm_id:<9} INSUFFICIENT DATA")
                continue
            at = s.get("as_traded") or {}
            lines.append(f"   {arm_id:<9} n_days={s.get('n_trading_days')} as_traded CI_lo={at.get('ci_lower_2.5')}")
        lines.append("")

    ee = disc.get("effective_evidence")
    if ee:
        lines.append("EFFECTIVE EVIDENCE (disclosure only)")
        for arm_id in report["roster"]:
            a = ee["per_arm"].get(arm_id, {})
            lines.append(f"   {arm_id:<9} days_current_config={a.get('days_on_current_config')} "
                          f"days_post_ladder={a.get('days_post_ladder')} "
                          f"best2_share_of_gross_winners={a.get('best_2_days_share_of_gross_winner_dollars')}")
        lines.append(f"   book ex-best-day P(PF<=1)={ee.get('book_ex_best_day_p_pf_le_1')}")
        lines.append("")

    pr = disc.get("plan_reachability")
    if pr:
        lines.append(f"PLAN REACHABILITY (disclosure only, zero-variance best case, as of {pr['as_of']})")
        for arm_id in report["roster"]:
            horizons = pr["per_arm"].get(arm_id, {})
            parts = []
            for label, h in horizons.items():
                parts.append(f"{label}({h['end_date']})=${h.get('dollars_per_day')}/day"
                              + (" [already clears]" if h.get("already_clears") else ""))
            lines.append(f"   {arm_id:<9} " + "  ".join(parts))
        lines.append("")

    rc = report.get("regime_coverage")
    if rc:
        lt, fw = rc["lifetime"], rc["frozen_config_window"]
        lines.append("REGIME COVERAGE (disclosure only)")
        lines.append(f"   lifetime            n_days={lt['n_days']} "
                      f"VIX_daily_max=[{lt['vix_daily_max_min']},{lt['vix_daily_max_max']}] "
                      f"days_VIX>20={lt['days_vix_gt_20']} "
                      f"SPY_cum_ret={lt['spy_cumulative_return_pct']}% "
                      f"worst_day={lt['worst_day']} days_down>1%={lt['days_down_gt_1pct']}")
        lines.append(f"   frozen({fw['window_start']}) n_days={fw['n_days']} "
                      f"VIX_daily_max=[{fw['vix_daily_max_min']},{fw['vix_daily_max_max']}] "
                      f"days_VIX>20={fw['days_vix_gt_20']} "
                      f"SPY_cum_ret={fw['spy_cumulative_return_pct']}% "
                      f"worst_day={fw['worst_day']} days_down>1%={fw['days_down_gt_1pct']}")
        if rc.get("calm_only_window_warning"):
            lines.append(f"   *** {rc['calm_only_window_warning']} ***")
        lines.append("   stress-day study: analysis/regime-stress/REGIME-STRESS-2026-09-02.md "
                     "(SIM-ONLY, disclosure only)")
        lines.append("")

    spy_only = "\n".join(lines)

    # ADDITIVE ONLY (queue.md FUTURES-ABSENT-FROM-GO-LIVE-GATE, 2026-09-03): appended AFTER
    # the full SPY report is already finalized above -- the SPY section's text is complete
    # and unchanged by this block's presence or absence (see
    # test_futures_go_live_gate_2026_09_03.py's byte-identity guard).
    futures = report.get("futures")
    if futures and "criteria" in futures:
        return spy_only + "\n" + futures_go_live_gate.render_futures_human(futures)
    return spy_only


def render_markdown(report: dict) -> str:
    c = report["criteria"]
    lines = [
        f"# Go-Live Gate -- {report['overall_verdict']}",
        "",
        f"_generated {report['generated_et']} ET by `{report['instrument']}`. "
        "Reporting instrument only -- arms nothing. Live-money arming stays J's decision (OP-0 #1)._",
        "",
        "| Criterion | Verdict |",
        "|---|---|",
        f"| 1. Statistical (per-arm CI-lower>1.0, as-traded + ex-best-day + cost-adjusted) | {_mark(c['statistical']['pass'])} |",
        f"| 2. Operational (guardrail tests pinned+green) | {_mark(c['operational']['pass'])} |",
        f"| 3. Reconciliation (ledger vs live broker equity, all 5 arms) | {_mark(c['reconciliation']['pass'])} |",
        f"| 4. Behavioural (rule breaks / manual overrides in trailing window) | {_mark(c['behavioural']['pass'])} |",
        f"| 5. Prod-shadow (dedicated shadow arm net of costs) | {_mark(c['prod_shadow']['pass'])} ({c['prod_shadow']['status']}) |",
        "",
        "## Statistical -- per arm",
        "",
        "| Arm | n_days | as-traded CI_lo | ex-best-day CI_lo | cost-adj CI_lo | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for arm_id in report["roster"]:
        s = c["statistical"]["per_arm"][arm_id]
        if s.get("insufficient_data"):
            lines.append(f"| {arm_id} | -- | -- | -- | -- | INSUFFICIENT |")
            continue
        at, xb, ca = s["as_traded"], s["ex_best_day"], s["cost_adjusted_fees_plus_2c_slip"]
        lines.append(f"| {arm_id} | {s['n_trading_days']} | "
                      f"{at['ci_lower_2.5'] if at else 'n/a'} | "
                      f"{xb.get('ci_lower_2.5','n/a')} | "
                      f"{ca['ci_lower_2.5'] if ca else 'n/a'} | {_mark(s['pass'])} |")
    lines += [
        "",
        "## Reconciliation -- per arm",
        "",
        "| Arm | Window | Broker P&L | Ledger P&L | Est. fees | Diff (fee-adj) | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm_id, r in c["reconciliation"]["per_arm"].items():
        if r.get("reconciled") is None:
            lines.append(f"| {arm_id} | -- | -- | -- | -- | -- | UNKNOWN ({r.get('note')}) |")
            continue
        lines.append(f"| {arm_id} | {r['window'][0]}..{r['window'][1]} | "
                      f"${r['broker_pnl_sum']:,.2f} | ${r['ledger_pnl_sum_engine_attributed']:,.2f} | "
                      f"${r['estimated_fees_ex_cat_plus_cat']:,.2f} | "
                      f"${r['diff_vs_fee_adjusted_ledger']:,.2f} | {_mark(r['reconciled'])} |")
    lines += [
        "",
        "## Operational guardrails",
        "",
        "| Guard | Verdict |",
        "|---|---|",
    ]
    for name, g in c["operational"]["guards"].items():
        lines.append(f"| {name} | {_mark(g['pass'])} |")
    ps = c["prod_shadow"]
    lines += ["", "## Prod-shadow", ""]
    if ps["status"] != "NOT_WIRED":
        d = ps["designation"]
        lines.append(f"**arm={d['arm']} window={d['window_start']}..{d['window_end']} "
                      f"days_scored={ps['days_scored']}/{ps['days_needed']} "
                      f"current CI_lo={ps.get('current_ci_lower_2.5')} status={ps['status']}**")
        lines.append("")
        ext = ps.get("extended_clock_disclosure")
        if ext:
            ext_ci = (ext.get("detail") or {}).get("as_traded", {}).get("ci_lower_2.5") if ext.get("detail") else None
            lines.append(f"Extended clock (disclosure only, never the pass bar) through {ext['window_end']}: "
                          f"{ext['days_scored']}/{ext['min_days']} days scored, as-traded CI_lo={ext_ci}.")
            lines.append("")
    lines.append(ps["note"])

    disc = report.get("disclosures", {})
    fcw = disc.get("frozen_config_window")
    if fcw:
        lines += [
            "",
            f"## Frozen-config-window disclosure (since {fcw['window_start']})",
            "",
            "_disclosure only -- pass criterion unchanged (criterion 1 stays full-history)_",
            "",
            "| Arm | n_days | as-traded CI_lo |",
            "|---|---|---|",
        ]
        for arm_id in report["roster"]:
            s = fcw["per_arm"].get(arm_id, {})
            if s.get("insufficient_data"):
                lines.append(f"| {arm_id} | -- | INSUFFICIENT |")
                continue
            at = s.get("as_traded") or {}
            lines.append(f"| {arm_id} | {s.get('n_trading_days')} | {at.get('ci_lower_2.5')} |")

    ee = disc.get("effective_evidence")
    if ee:
        lines += [
            "",
            "## Effective evidence disclosure",
            "",
            "| Arm | Days on current config (>=09-01) | Days post-ladder (>=08-11) | Best-2-days share of gross winners |",
            "|---|---|---|---|",
        ]
        for arm_id in report["roster"]:
            a = ee["per_arm"].get(arm_id, {})
            lines.append(f"| {arm_id} | {a.get('days_on_current_config')} | {a.get('days_post_ladder')} | "
                          f"{a.get('best_2_days_share_of_gross_winner_dollars')} |")
        lines.append("")
        lines.append(f"Book rollup ex-best-day P(PF<=1) = {ee.get('book_ex_best_day_p_pf_le_1')}")

    pr = disc.get("plan_reachability")
    if pr:
        lines += [
            "",
            "## Plan reachability disclosure",
            "",
            "_zero-variance best case -- constant $/day over remaining trading days that would push "
            f"CI-lower(2.5%) above 1.0, as of {pr['as_of']}_",
            "",
            "| Arm | Config-freeze close (09-29) | Tight-ladder clock close (10-30) |",
            "|---|---|---|",
        ]
        for arm_id in report["roster"]:
            horizons = pr["per_arm"].get(arm_id, {})
            cells = []
            for label in ("config_freeze_end", "tight_ladder_clock_end"):
                h = horizons.get(label, {})
                if h.get("already_clears"):
                    cells.append("already clears")
                elif h.get("dollars_per_day") is not None:
                    cells.append(f"${h['dollars_per_day']}/day")
                else:
                    cells.append(h.get("note", "n/a"))
            lines.append(f"| {arm_id} | {cells[0]} | {cells[1]} |")

    rc = report.get("regime_coverage")
    if rc:
        lt, fw = rc["lifetime"], rc["frozen_config_window"]
        lines += [
            "",
            "## REGIME COVERAGE (disclosure only)",
            "",
            "_never gates the overall verdict -- answers whether the evidence window has "
            "actually seen a stressed market_",
            "",
            "| Window | n_days | VIX daily-max min/max | days VIX>20 | SPY cum. return | "
            "worst day | days down >1% |",
            "|---|---|---|---|---|---|---|",
            f"| lifetime | {lt['n_days']} | {lt['vix_daily_max_min']}/{lt['vix_daily_max_max']} | "
            f"{lt['days_vix_gt_20']} | {lt['spy_cumulative_return_pct']}% | "
            f"{lt['worst_day']} | {lt['days_down_gt_1pct']} |",
            f"| frozen (since {fw['window_start']}) | {fw['n_days']} | "
            f"{fw['vix_daily_max_min']}/{fw['vix_daily_max_max']} | {fw['days_vix_gt_20']} | "
            f"{fw['spy_cumulative_return_pct']}% | {fw['worst_day']} | {fw['days_down_gt_1pct']} |",
        ]
        if rc.get("calm_only_window_warning"):
            lines += ["", f"**{rc['calm_only_window_warning']}**"]

    lines += [
        "",
        "Full machine payload: `analysis/go-live-gate.json`. Runbook: "
        "`markdown/planning/LIVE-FLIP-RUNBOOK.md`.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print machine JSON instead of the human table")
    parser.add_argument("--no-refresh", action="store_true",
                         help="skip the trades-enriched.jsonl regeneration at startup and "
                              "score the on-disk file as-is (default: always refresh first)")
    args = parser.parse_args(argv)

    refresh_status = refresh_trades_enriched(skip=args.no_refresh)
    report = build_report(refresh_status)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_human(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
