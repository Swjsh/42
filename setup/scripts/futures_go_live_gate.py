"""futures_go_live_gate.py -- ADVISORY, separate ladder for the futures (MES) lane.

WHY THIS EXISTS (built 2026-09-03, queue.md FUTURES-ABSENT-FROM-GO-LIVE-GATE, filed
2026-08-29 by a Fable futures-parity audit): setup/scripts/go_live_gate.py contained
exactly ONE futures mention -- a disclaimer that the Kalshi/SSR shadows "neither
substitutes for" the SPY criteria -- and evaluated no futures criteria at all.
live_readiness.py tracks only dormant/pending arm names, not the CURRENT
Gamma_FuturesTrader (fillsim "book" lane) / Gamma_FuturesBrokerLane (tastytrade SANDBOX
"broker" lane, REAL fills) pair. Consequence: "is the futures lane ready for more
capital" had no instrument and would have been answered by vibes.

HARD BOUNDARY (do not weaken this): this module is imported by go_live_gate.py and its
output is attached under a NEW top-level `"futures"` key, and printed as a NEW section
AFTER the SPY report. It is NEVER merged into go_live_gate.py's `criteria` dict (the five
groups whose `.pass` values compute `overall_verdict`), so it structurally CANNOT change
the SPY overall_verdict, no matter what it computes. go_live_gate.py wraps the call to
this module in try/except so a bug here can never crash the SPY gate either (see that
file's build_report()).

Futures P&L is NOT the SPY options shape: uncapped loss (margin-backed notional, not a
premium-capped bet), denominated in points x contract multiplier ($5/pt MES, $2/pt MNQ,
confirmed against this repo's own journal/futures/trades.csv point_value column and
risk_usd = stop_points * point_value * qty, 2026-09-03), and the CURRENT evidence base is
two structurally different lanes (see futures_journal.py's own docstring: "fills marked
SIMULATED are mechanism evidence, never edge evidence"):
  - "book"   lane = FillSimBroker  (Gamma_FuturesTrader)       -- simulated fills.
  - "broker" lane = TastytradeBroker SANDBOX (Gamma_FuturesBrokerLane) -- REAL fills, but
                    thin: verified this session (2026-09-03) that journal/futures/
                    trades.csv carries ZERO closed BROKER round trips (3 ENTER events
                    logged in automation/state/futures/trader-broker/decisions.jsonl, 0
                    exits) -- one open real position sits in trader-broker/
                    open-position.json as of 2026-09-02T11:50:01.

Per the queue item's explicit instruction: do NOT reuse go_live_gate.py's SPY PF-CI
thresholds unexamined. Every threshold below is disclosed with its OWN reasoning and
labeled PROVISIONAL where it has not been independently validated for this lane's return
distribution -- a first real bar for a lane group that had none, not a validated one.

OUTPUTS: nothing on its own. `futures_block()` returns a plain dict; go_live_gate.py
attaches it to its JSON report and prints `render_futures_human()`'s text beneath the SPY
human-readable report. Run standalone for a quick look:

    backtest/.venv/Scripts/python.exe setup/scripts/futures_go_live_gate.py
"""
from __future__ import annotations

import csv
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from et_clock import et_now  # noqa: E402

FUTURES_TRADES_CSV = REPO / "journal" / "futures" / "trades.csv"
FUTURES_ACCOUNT_JSON = REPO / "automation" / "state" / "futures" / "account.json"
FUTURES_OPEN_POSITION_JSON = REPO / "automation" / "state" / "futures" / "trader-broker" / "open-position.json"
FUTURES_HEALTH_JSON = REPO / "automation" / "state" / "futures" / "health.json"

# --------------------------------------------------------------------------------------- #
# Constants -- every one disclosed with its reasoning; PROVISIONAL where unexamined.
# --------------------------------------------------------------------------------------- #

# $/point per CME micro contract. Confirmed against this repo's OWN data (not assumed):
# journal/futures/trades.csv rows carry risk_usd == stop_points * point_value * qty to the
# cent (e.g. stop_points=15.3, point_value=5.0, qty=1 -> risk_usd=76.5), and every row's
# instrument to date is MES with point_value=5.0. MNQ's $2/pt is the other CME micro this
# repo's docs (MARGIN-LEVERAGE-RISK.md) name; kept here for when/if that lane trades.
FUTURES_POINT_VALUE = {"MES": 5.0, "MNQ": 2.0}

# PROVISIONAL: the HIGH end of markdown/futures/MARGIN-LEVERAGE-RISK.md's own illustrative
# day-trade-margin range ("often low hundreds... e.g. ~$50-$500 depending on broker/
# volatility... confirm live with broker"). Deliberately the CONSERVATIVE (higher) end for
# a safety check -- assume the worst plausible margin requirement, never the best case.
# Never reused for the P&L math itself (that comes from each trade's own recorded
# stop_points/point_value), only for the open-position margin-utilization check below.
FUTURES_DAY_MARGIN_CONSERVATIVE = {"MES": 500.0, "MNQ": 500.0}

# CLAUDE.md's own >=20-trading-day live threshold is already reused inside go_live_gate.py
# itself (TRAILING_WINDOW_TRADING_DAYS) as a doctrine-anchored, non-arbitrary floor. Reused
# here as the futures lane's minimum scored-session count too -- SAME reasoning (a bootstrap
# CI on <20 days is not a stable read), but PROVISIONAL for futures specifically: nobody has
# examined whether 20 is the right number for THIS lane's day-level P&L variance (thinner
# trade count per day, fatter-tailed uncapped-loss distribution than a premium-capped
# option). Revisit once real sessions exist to test it.
FUTURES_MIN_SCORED_SESSIONS = 20

# PROVISIONAL: PF CI-lower(2.5%) > 1.0 (breakeven) is a SHAPE choice reused from
# go_live_gate.py's SPY statistical_criterion() -- "the bootstrap must clear breakeven
# under its worst-plausible 2.5th-percentile draw" is not itself a SPY-specific number. But
# the underlying return distribution IS SPY-specific evidence (capped-loss option premium);
# futures P&L is margin-backed and uncapped, a materially different shape. Kept as the
# starting bar because breakeven is the only universally defensible floor with zero real
# futures evidence to calibrate against yet -- explicitly flagged PROVISIONAL, not silently
# inherited.
FUTURES_PF_CI_THRESHOLD = 1.0

FUTURES_N_BOOT = 20000
FUTURES_BOOT_SEED = 42

# PROVISIONAL: >=80% of overlapping trading days must show the SAME round-trip COUNT and
# DIRECTION SET between the book (fillsim) and broker (SANDBOX real) lanes. Checks
# STRUCTURAL agreement (both lanes read the same signals and should act on them the same
# way), never PRICE agreement -- sim fills and real broker fills will legitimately differ
# in price/slippage even when they agree on what to trade. Unexamined bar (no real broker
# round trips exist yet to calibrate against); revisit once evidence accumulates.
FUTURES_RECONCILIATION_AGREEMENT_THRESHOLD = 0.80

# Operational health.json is written by futures_health.py on its own schedule
# (Gamma_FuturesHealth or equivalent); a report older than this is stale evidence, not
# live evidence, and this module refuses to launder a stale RED into a false GREEN or vice
# versa -- staleness itself degrades the lane verdict (see operational_block()).
FUTURES_HEALTH_STALE_AFTER_MINUTES = 240


# ========================================================================================= #
# Small IO helpers -- self-contained (own path constants, own parsing) so this module and
# its tests never depend on futures_journal.py's/futures_health.py's internal state shape.
# ========================================================================================= #
def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _read_futures_trades(csv_path: Path, fills: str) -> list[dict]:
    """Closed round trips from journal/futures/trades.csv, filtered to ONE fills class
    ('SIMULATED' or 'BROKER') -- never mixed, matching futures_journal.py's own rule."""
    if not csv_path.exists():
        return []
    out: list[dict] = []
    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("fills") != fills:
                    continue
                try:
                    pv_raw = row.get("point_value")
                    out.append({
                        "date": row.get("date", ""),
                        "instrument": row.get("instrument", "MES") or "MES",
                        "direction": row.get("direction", ""),
                        "qty": float(row.get("qty") or 1.0),
                        "stop_points": float(row.get("stop_points") or 0.0),
                        "point_value": float(pv_raw) if pv_raw not in (None, "") else None,
                        "dollar_pnl": float(row.get("dollar_pnl") or 0.0),
                        "exit_reason": row.get("exit_reason", ""),
                    })
                except (TypeError, ValueError):
                    continue
    except OSError:
        return []
    return out


_KNOWN_FUTURES_ROOTS = ("MES", "MNQ", "MYM", "M2K")


def _instrument_from_symbol(symbol: str) -> str:
    """'/MESU6' -> 'MES'. A CME symbol is root + single-letter month code + 1-2 digit
    year (e.g. MES + U + 6) -- a bare leading-letters regex would wrongly include the
    month code (MESU). Checked against the known micro roots first; falls back to the
    leading-letters regex for an unrecognized root rather than guessing where it ends."""
    s = (symbol or "").lstrip("/").upper()
    for root in _KNOWN_FUTURES_ROOTS:
        if s.startswith(root):
            return root
    m = re.match(r"([A-Za-z]+)", s)
    return m.group(1) if m else ""


# ========================================================================================= #
# F1. STATISTICAL -- day-level bootstrap PF CI-lower, REAL sandbox (BROKER) fills only.
# ========================================================================================= #
def _profit_factor(values: list[float]) -> float:
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return gains / losses


def _bootstrap_pf_ci(day_values: list[float], n_boot: int = FUTURES_N_BOOT,
                      seed: int = FUTURES_BOOT_SEED) -> dict | None:
    """Percentile bootstrap over trading DAYS -- same methodology as go_live_gate.py's
    bootstrap_pf_ci() (resample-with-replacement respects within-day trade correlation),
    reimplemented locally so this module has zero import coupling to the SPY gate."""
    n = len(day_values)
    if n < 2:
        return None
    rng = random.Random(seed)
    pfs = []
    for _ in range(n_boot):
        sample = [day_values[rng.randrange(n)] for _ in range(n)]
        pf = _profit_factor(sample)
        if pf == pf and pf != float("inf"):  # drop NaN and +inf (all-win resample)
            pfs.append(pf)
    if not pfs:
        return None
    pfs.sort()
    lo_idx = int(0.025 * len(pfs))
    hi_idx = min(int(0.975 * len(pfs)), len(pfs) - 1)
    point = _profit_factor(day_values)
    return {
        "n_days": n,
        "ci_lower_2.5": round(pfs[lo_idx], 3),
        "ci_upper_97.5": round(pfs[hi_idx], 3),
        "pf_point": round(point, 3) if math.isfinite(point) else None,
        "total_pnl": round(sum(day_values), 2),
    }


def statistical_criterion_real_fills(broker_trades: list[dict],
                                      min_sessions: int = FUTURES_MIN_SCORED_SESSIONS) -> dict:
    by_day: dict[str, float] = defaultdict(float)
    for t in broker_trades:
        by_day[t["date"]] += t["dollar_pnl"]
    n_sessions = len(by_day)

    if n_sessions < min_sessions:
        return {
            "status": "INSUFFICIENT",
            "pass": False,
            "n_scored_sessions": n_sessions,
            "min_scored_sessions_required": min_sessions,
            "criterion": f"day-level bootstrap PF, CI-lower(2.5%) > {FUTURES_PF_CI_THRESHOLD} on "
                         f"REAL (broker/SANDBOX) fills only -- PROVISIONAL threshold, see module docstring",
            "note": (f"only {n_sessions} scored session(s) with a closed REAL (broker/SANDBOX) round "
                     f"trip -- needs >= {min_sessions} before a bootstrap CI is meaningful. This is the "
                     f"exact gap the queue item named: 'is futures ready for more capital' has no "
                     f"instrument yet because there is not enough real-fill evidence to compute one."),
        }

    ci = _bootstrap_pf_ci(list(by_day.values()))
    passed = bool(ci and ci["ci_lower_2.5"] > FUTURES_PF_CI_THRESHOLD)
    return {
        "status": "SCORED",
        "pass": passed,
        "n_scored_sessions": n_sessions,
        "min_scored_sessions_required": min_sessions,
        "ci": ci,
        "criterion": f"day-level bootstrap PF, CI-lower(2.5%) > {FUTURES_PF_CI_THRESHOLD} on "
                     f"REAL (broker/SANDBOX) fills only -- PROVISIONAL threshold, see module docstring",
    }


# ========================================================================================= #
# F2. MARGIN -- dollar/point-denominated, margin-aware (MARGIN-LEVERAGE-RISK.md).
# ========================================================================================= #
def margin_criterion(trades: list[dict], open_positions: list[dict], account: dict) -> dict:
    equity = account.get("equity")
    daily_loss_limit = account.get("daily_loss_limit")

    worst_loss = 0.0
    violations = []
    for t in trades:
        pv = t.get("point_value") or FUTURES_POINT_VALUE.get(t.get("instrument"), FUTURES_POINT_VALUE["MES"])
        stop_pts = t.get("stop_points") or 0.0
        qty = t.get("qty") or 1.0
        loss = stop_pts * pv * qty
        worst_loss = max(worst_loss, loss)
        if daily_loss_limit is not None and loss > daily_loss_limit:
            violations.append({
                "date": t.get("date"), "instrument": t.get("instrument"),
                "worst_case_loss": round(loss, 2), "daily_loss_limit": daily_loss_limit,
            })

    open_margin_required = 0.0
    for p in open_positions:
        instrument = _instrument_from_symbol(p.get("symbol", ""))
        qty = abs(float(p.get("qty") or 0))
        open_margin_required += qty * FUTURES_DAY_MARGIN_CONSERVATIVE.get(
            instrument, FUTURES_DAY_MARGIN_CONSERVATIVE["MES"])

    margin_ok = True if equity is None else (open_margin_required <= equity)
    has_evidence = bool(trades or open_positions)
    passed = has_evidence and (not violations) and margin_ok

    return {
        "status": "SCORED" if has_evidence else "INSUFFICIENT",
        "pass": passed,
        "n_trades_checked": len(trades),
        "worst_case_single_trade_loss": round(worst_loss, 2),
        "daily_loss_limit": daily_loss_limit,
        "per_trade_violations": violations,
        "open_position_margin_required_conservative": round(open_margin_required, 2),
        "account_equity": equity,
        "margin_within_equity": margin_ok,
        "criterion": ("PROVISIONAL: no single trade's stop-distance-based worst-case loss "
                      "(stop_points x point_value x qty) may exceed the account's own daily_loss_limit "
                      "(account.json); open-position margin at the conservative HIGH-end day-margin "
                      "estimate (MARGIN-LEVERAGE-RISK.md) must not exceed account equity."),
    }


# ========================================================================================= #
# F3. RECONCILIATION -- book (fillsim) vs broker (SANDBOX real fills), structural agreement.
# ========================================================================================= #
def reconciliation_criterion(book_trades: list[dict], broker_trades: list[dict],
                              agreement_threshold: float = FUTURES_RECONCILIATION_AGREEMENT_THRESHOLD) -> dict:
    if not broker_trades:
        return {
            "status": "INSUFFICIENT",
            "pass": False,
            "n_book_round_trips": len(book_trades),
            "n_broker_round_trips": 0,
            "note": ("zero closed BROKER (real sandbox) round trips recorded in "
                     "journal/futures/trades.csv -- cannot compute a book-vs-broker agreement rate "
                     "yet. See automation/state/futures/trader-broker/open-position.json for any "
                     "not-yet-closed real position."),
        }

    by_day_book: dict[str, list[dict]] = defaultdict(list)
    by_day_broker: dict[str, list[dict]] = defaultdict(list)
    for t in book_trades:
        by_day_book[t["date"]].append(t)
    for t in broker_trades:
        by_day_broker[t["date"]].append(t)

    days = sorted(set(by_day_book) | set(by_day_broker))
    detail_rows = []
    agree_days = 0
    for d in days:
        b = by_day_book.get(d, [])
        k = by_day_broker.get(d, [])
        dir_b = Counter(x["direction"] for x in b)
        dir_k = Counter(x["direction"] for x in k)
        matched = (len(b) == len(k)) and (dir_b == dir_k)
        if matched:
            agree_days += 1
        detail_rows.append({
            "date": d, "book_n": len(b), "broker_n": len(k),
            "book_directions": dict(dir_b), "broker_directions": dict(dir_k), "agree": matched,
        })

    agreement_rate = round(agree_days / len(days), 3) if days else None
    passed = agreement_rate is not None and agreement_rate >= agreement_threshold
    return {
        "status": "SCORED",
        "pass": passed,
        "n_book_round_trips": len(book_trades),
        "n_broker_round_trips": len(broker_trades),
        "n_days_compared": len(days),
        "agreement_rate_direction_and_size": agreement_rate,
        "detail": detail_rows,
        "criterion": (f"PROVISIONAL: >= {agreement_threshold:.0%} of overlapping days show matching "
                      f"round-trip COUNT and DIRECTION set between book (fillsim) and broker "
                      f"(SANDBOX real fills) lanes -- structural agreement, not price agreement."),
    }


# ========================================================================================= #
# F4. OPERATIONAL -- fold in futures_health.py's own verdict, never reimplemented.
# ========================================================================================= #
_TRANSPORT_RATE_RE = re.compile(r"rate (\d+)%")


def _extract_transport_error_rate(detail: str) -> int | None:
    m = _TRANSPORT_RATE_RE.search(detail or "")
    return int(m.group(1)) if m else None


def operational_block(health_path: Path = FUTURES_HEALTH_JSON, now_et: datetime | None = None,
                       stale_after_minutes: int = FUTURES_HEALTH_STALE_AFTER_MINUTES) -> dict:
    now_et = now_et if now_et is not None else et_now()
    data = _load_json(health_path, None)
    if not data:
        return {
            "status": "INSUFFICIENT",
            "pass": False,
            "source": str(health_path),
            "note": f"{health_path} unreadable/missing -- futures_health.py has not produced a report yet",
        }

    checked_at = data.get("checked_at_et")
    checked_dt = None
    if checked_at:
        try:
            checked_dt = datetime.strptime(checked_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            checked_dt = None

    age_min = None
    stale = True
    if checked_dt is not None:
        age_min = (now_et - checked_dt).total_seconds() / 60.0
        stale = age_min > stale_after_minutes

    underlying_verdict = data.get("verdict", "RED")
    checks_by_name = {c.get("name"): c for c in data.get("checks", []) if isinstance(c, dict)}
    broker_transport = checks_by_name.get("broker_transport", {})
    task_liveness = checks_by_name.get("task_liveness", {})

    lane_status = "INSUFFICIENT" if (checked_dt is None or stale) else underlying_verdict

    return {
        "status": lane_status,
        "pass": lane_status == "GREEN",
        "source": str(health_path),
        "checked_at_et": checked_at,
        "age_minutes": round(age_min, 1) if age_min is not None else None,
        "stale": stale,
        "underlying_verdict": underlying_verdict,
        "connect_failure_rate_pct": _extract_transport_error_rate(broker_transport.get("detail", "")),
        "coverage_status": task_liveness.get("status"),
        "reasons": data.get("reasons", []),
        "criterion": (f"fold futures_health.py's own verdict verbatim (never reimplemented); a report "
                      f"older than {stale_after_minutes}m is treated as INSUFFICIENT, not laundered "
                      f"into a stale GREEN or RED."),
    }


# ========================================================================================= #
# Lane rollup -- deterministic severity ladder, worst sub-verdict wins.
# ========================================================================================= #
_SEVERITY = {"GREEN": 0, "YELLOW": 1, "INSUFFICIENT": 2, "RED": 3}


def _sub_verdict(block: dict) -> str:
    status = block.get("status")
    if status in _SEVERITY:
        return status
    return "GREEN" if block.get("pass") else "RED"


def _lane_verdict(*blocks: dict) -> str:
    """Worst-wins rollup: RED (a confirmed, evidenced problem) outranks INSUFFICIENT (no
    evidence yet either way), which outranks YELLOW, which outranks GREEN. A lane is only
    GREEN when every criterion below has BOTH enough evidence AND clears its bar."""
    worst = max(blocks, key=lambda b: _SEVERITY.get(_sub_verdict(b), 3))
    return _sub_verdict(worst)


# ========================================================================================= #
# Top-level entry point.
# ========================================================================================= #
def futures_block(now_et: datetime | None = None) -> dict:
    now_et = now_et if now_et is not None else et_now()

    book_trades = _read_futures_trades(FUTURES_TRADES_CSV, "SIMULATED")
    broker_trades = _read_futures_trades(FUTURES_TRADES_CSV, "BROKER")
    account = _load_json(FUTURES_ACCOUNT_JSON, {}) or {}
    open_pos_doc = _load_json(FUTURES_OPEN_POSITION_JSON, {}) or {}
    open_positions = open_pos_doc.get("positions") or []

    statistical = statistical_criterion_real_fills(broker_trades)
    margin = margin_criterion(book_trades + broker_trades, open_positions, account)
    reconciliation = reconciliation_criterion(book_trades, broker_trades)
    operational = operational_block(FUTURES_HEALTH_JSON, now_et)

    lane_verdict = _lane_verdict(statistical, margin, reconciliation, operational)

    return {
        "generated_et": now_et.isoformat(timespec="seconds"),
        "instrument": "setup/scripts/futures_go_live_gate.py",
        "note": ("ADVISORY, separate ladder for the futures MES lane -- NEVER substitutes for or "
                 "feeds the SPY criteria/verdict above. Every threshold is PROVISIONAL (first real "
                 "bar for a lane group that had none before this file -- see queue.md "
                 "FUTURES-ABSENT-FROM-GO-LIVE-GATE)."),
        "lane_verdict": lane_verdict,
        "criteria": {
            "statistical_real_fills": statistical,
            "margin": margin,
            "reconciliation_book_vs_broker": reconciliation,
            "operational": operational,
        },
        "evidence_counts": {
            "book_round_trips_simulated": len(book_trades),
            "broker_round_trips_real": len(broker_trades),
            "open_real_positions": len(open_positions),
        },
    }


def render_futures_human(block: dict) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"FUTURES LANE (advisory, separate ladder -- never substitutes for SPY criteria) "
                 f"-- {block['generated_et']} ET")
    lines.append(f"LANE VERDICT: {block['lane_verdict']}")
    lines.append(block["note"])
    lines.append("")

    c = block["criteria"]

    s = c["statistical_real_fills"]
    lines.append(f"F1. STATISTICAL (real sandbox fills) [{s['status']}] -- "
                 f"n_scored_sessions={s['n_scored_sessions']}/{s['min_scored_sessions_required']}")
    if s["status"] == "INSUFFICIENT":
        lines.append(f"    {s['note']}")
    else:
        ci = s.get("ci") or {}
        lines.append(f"    CI_lo={ci.get('ci_lower_2.5')} CI_hi={ci.get('ci_upper_97.5')} "
                     f"pf_point={ci.get('pf_point')} [{'PASS' if s['pass'] else 'FAIL'}]")
    lines.append("")

    m = c["margin"]
    lines.append(f"F2. MARGIN [{'PASS' if m['pass'] else 'FAIL'}] ({m['status']}) -- "
                 f"worst_case_single_trade_loss=${m['worst_case_single_trade_loss']:.2f} "
                 f"vs daily_loss_limit={m.get('daily_loss_limit')} | "
                 f"open_position_margin_required(conservative)="
                 f"${m['open_position_margin_required_conservative']:.2f} vs equity={m.get('account_equity')}")
    if m["per_trade_violations"]:
        lines.append(f"    VIOLATIONS: {m['per_trade_violations']}")
    lines.append("")

    r = c["reconciliation_book_vs_broker"]
    tail = (f" agreement_rate={r.get('agreement_rate_direction_and_size')}"
            if r["status"] != "INSUFFICIENT" else "")
    lines.append(f"F3. RECONCILIATION (book vs broker) [{r['status']}] -- "
                 f"book_n={r['n_book_round_trips']} broker_n={r['n_broker_round_trips']}{tail}")
    if r["status"] == "INSUFFICIENT":
        lines.append(f"    {r['note']}")
    lines.append("")

    o = c["operational"]
    lines.append(f"F4. OPERATIONAL (futures_health.py) [{o['status']}] "
                 f"underlying_verdict={o.get('underlying_verdict')} stale={o.get('stale')} "
                 f"age_min={o.get('age_minutes')} connect_failure_rate_pct={o.get('connect_failure_rate_pct')} "
                 f"coverage={o.get('coverage_status')}")
    for reason in o.get("reasons", []):
        lines.append(f"    - {str(reason)[:140]}")
    lines.append("")

    ec = block["evidence_counts"]
    lines.append(f"Evidence: book(sim)={ec['book_round_trips_simulated']} round trips, "
                 f"broker(real)={ec['broker_round_trips_real']} round trips, "
                 f"open_real_positions={ec['open_real_positions']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    block = futures_block()
    print(render_futures_human(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
