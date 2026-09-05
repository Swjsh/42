"""self_check.py — Gamma checks ITSELF on a cadence so J never has to ask "is it running?".

J 2026-06-29: "I'm not gonna sit in a terminal running this. Wire it into a skill + the
CLAUDE.md framework so you FREQUENTLY check yourself and I don't have to ask 'did it crash,
did you put an em-dash in it and burn an hour with no saved output.'"

This is the DETECTION + ALERT half of gamma_status.py (which is the human-readable view).
It runs every ~30 min (Gamma_SelfCheck), VERIFIES the actual work (not exit codes), and on
any DEGRADED/BROKEN finding writes STATUS.md '## Known broken' + queues ONE Discord ping —
so a silent failure surfaces to J PROACTIVELY instead of festering for hours. GREEN = silent.

Checks (each a fact, OP-33 verify-don't-claim):
  1. EM-DASH / ENCODING CLASS (the 544-day silent-failure pattern): every scheduled-task
     run-*.ps1 must be ASCII-or-BOM, else PS 5.1 reads it as cp1252 and parse-crashes
     silently (lastResult=0). This is the exact bug that killed Gamma_TvWatchdog for hours.
  2. STALE AUTONOMY OUTPUT during the window each task should be producing (level feed during
     RTH, beacon during RTH, heartbeat decisions during RTH).
  3. LIVE-CHAIN health (engine-health RED).
$0, pure-Python, fail-open (never raises into the scheduler).

LASTTASKRESULT-UNTRUSTED-BY-DESIGN (2026-08-08, closes the G-EXITCODE graduated guard,
test_no_monitor_trusts_lasttaskresult_as_authoritative): this file mentions
LastTaskResult/LastRunResult 9 times, ALL of them prose (docstrings + human-readable
finding/message strings) explaining why a given check deliberately does NOT trust Task
Scheduler's exit code and instead reads the task's own OUTPUT ARTIFACT -- scout_output.json's
generated_at/for_session_date (check_scout_premarket_fresh), run_cmd_hidden.py's own
synchronously-captured real exit code in run-cmd-hidden-<date>.log
(check_run_cmd_hidden_masked_exit), or run_ps1_hidden.py's equivalent
run-ps1-hidden-<date>.log (check_run_ps1_hidden_masked_exit). Verified live 2026-08-08 via
grep: this file never calls the scheduler-info cmdlet, never accesses either field as a
struct/object attribute, and never looks either field up as a dict key -- the value is
never read, let alone used as an authority. test_self_check_lasttaskresult_narrative_only.py
pins both halves of this invariant (no programmatic read ever creeps in; the exemption stays
documented, not silently inherited).
"""
from __future__ import annotations
import json, re, sys
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    def et_now(): return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
DISCORD_OUTBOX = STATE / "discord-outbox.jsonl"
LAST = STATE / "self-check-last.json"


def _age_min(p: Path):
    return None if not p.exists() else (dt.datetime.now().timestamp() - p.stat().st_mtime) / 60.0


def check_ps1_encoding() -> list[str]:
    """The em-dash/encoding class: a BOM-less run-*.ps1 with non-ASCII = silent PS-5.1 parse
    crash. Returns a list of offending files (empty = clean)."""
    bad = []
    for p in sorted((REPO / "setup" / "scripts").glob("run-*.ps1")):
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        has_bom = raw[:3] == b"\xef\xbb\xbf"
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(f"{p.name} (not utf-8)"); continue
        non_ascii = any(ord(c) > 127 for c in txt)
        if non_ascii and not has_bom:
            bad.append(p.name)
    return bad


def check_broker_keys() -> list[str]:
    """Broker-key / account health -- the 401-stale-key class (folds the /insights 'broker-health
    MCP' suggestion into self-check; a new MCP server would be unreachable autonomously since the
    engine has no Claude tick). Cheap READ-ONLY GET /v2/account on the two ENGINE-WIRED arms
    (safe-2, bold-2). A 401/403 = stale/revoked key = NO trades can place = BROKEN. Network error =
    DEGRADED (transient). Reuses the proven accounts_status.py pattern. Fail-open: returns [] on any
    unexpected error (never raises into the scheduler; never places orders)."""
    import urllib.request, urllib.error
    out: list[str] = []
    sec_file = STATE / "fleet" / "secrets.json"
    try:
        accts = json.loads(sec_file.read_text(encoding="utf-8")).get("accounts", {})
    except Exception:  # noqa: BLE001
        return []  # can't read secrets -> don't fabricate a problem (fail-open)
    for arm in ("safe-2", "bold-2"):
        a = accts.get(arm, {})
        key = a.get("api_key") or a.get("ALPACA_API_KEY") or a.get("key", "")
        sec = a.get("secret_key") or a.get("ALPACA_SECRET_KEY") or a.get("secret", "")
        base = a.get("base_url", "https://paper-api.alpaca.markets")
        if not key:
            out.append(f"BROKER KEY MISSING: {arm} has no key in fleet/secrets.json -- engine cannot place.")
            continue
        try:
            req = urllib.request.Request(base.rstrip("/") + "/v2/account",
                                         headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read())
            if d.get("status") != "ACTIVE":
                out.append(f"BROKER account {arm} status={d.get('status')} (not ACTIVE) -- trades may be blocked.")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                out.append(f"BROKER KEY STALE/REVOKED: {arm} account-ping HTTP {e.code} -- NO trades can place. RUNBOOK: markdown/infra/MCP-401-RESTART-RUNBOOK.md (rotate w/ J -> update .mcp.json -> RELOAD the MCP server -> re-verify).")
            else:
                out.append(f"BROKER UNREACHABLE: {arm} account-ping HTTP {e.code}.")
        except Exception as e:  # noqa: BLE001
            out.append(f"BROKER UNREACHABLE: {arm} {type(e).__name__} (network/timeout -- likely transient).")
    return out


# ---- STANDING DAILY BROKER RECONCILIATION (2026-08-28, TASK B3) -----------------------
# Ledger P&L (trades-enriched.jsonl, engine-attributed) vs REAL broker equity change, all 5
# active arms, net of the A1 fee model -- reuses go_live_gate.reconciliation_criterion()
# (the SAME instrument the go-live readiness gate reports on) rather than a second,
# divergent implementation. RED here means J is looking at a go-live number this session
# cannot independently verify against the broker -- worth a real, non-silent flag, same
# tier as a stale broker key.
#
# ONCE-PER-ET-DAY gate: reconciliation_criterion() makes 10 live Alpaca REST calls
# (portfolio-history + account, x5 arms) and re-derives daily P&L from the full ledger --
# too much to repeat on self_check's ~30-min cadence for a number that only moves once a
# trading day settles. Persists the last checked-date + full per-arm payload to
# reconciliation-daily.json (also the audit trail a human can read directly) and skips
# the network + recompute entirely once today's check has already run.
RECONCILIATION_STATE = STATE / "reconciliation-daily.json"


def check_broker_reconciliation(now, *, force: bool = False) -> list[str]:
    """Ledger-vs-broker P&L reconciliation, all 5 active arms, once per ET day.

    A `reconciled: False` arm (broker vs ledger P&L, net of estimated fees, differs by
    more than max($10, 2% of |broker P&L|) -- the SAME tolerance go_live_gate.py itself
    gates on) is a real, unexplained accounting gap and reports BROKEN (RED). A fetch
    failure (`reconciled: None` -- network/auth, not a data problem) reports DEGRADED,
    distinctly. Fail-open throughout: any unexpected error returns [] rather than
    fabricating or hiding a problem; a prior day's cached PASS is never treated as
    still valid past midnight ET."""
    today = now.strftime("%Y-%m-%d")
    if not force and RECONCILIATION_STATE.exists():
        try:
            prior = json.loads(RECONCILIATION_STATE.read_text(encoding="utf-8"))
            if prior.get("checked_date_et") == today:
                return []  # already checked today -- don't re-hit the broker every ~30 min
        except Exception:  # noqa: BLE001
            pass  # unreadable cache -> fall through and recompute
    try:
        import go_live_gate as glg
        rows = glg.load_ledger_rows()
        engine_rows = [r for r in rows if r.get("attribution") == "engine"]
        result = glg.reconciliation_criterion(engine_rows)
    except Exception as e:  # noqa: BLE001 -- never break the scheduler on this extra check
        return [f"RECONCILIATION CHECK ERROR: {type(e).__name__}: {e} -- broker reconciliation "
                f"could not be computed this run (transient/import failure, not itself a drift)."]

    out: list[str] = []
    for arm_id, r in sorted(result.get("per_arm", {}).items()):
        reconciled = r.get("reconciled")
        if reconciled is True:
            continue
        if reconciled is None:
            out.append(f"RECONCILIATION UNAVAILABLE: {arm_id} -- {r.get('note', 'live fetch failed')}.")
            continue
        diff = r.get("diff_vs_fee_adjusted_ledger")
        tol = r.get("tolerance")
        window = r.get("window")
        try:
            detail_path = RECONCILIATION_STATE.relative_to(REPO).as_posix()
        except ValueError:
            detail_path = str(RECONCILIATION_STATE)  # e.g. under a test's tmp_path
        out.append(
            f"RECONCILIATION RED: {arm_id} ledger vs broker P&L diverge by ${diff:,.2f} "
            f"(tolerance +/-${tol:,.2f}) over {window[0]}..{window[1]} -- broker="
            f"${r.get('broker_pnl_sum'):,.2f} ledger_fee_adj="
            f"${r.get('ledger_pnl_fee_adjusted'):,.2f}. Full detail: {detail_path}."
        )

    try:
        RECONCILIATION_STATE.write_text(json.dumps(
            {"checked_date_et": today, "checked_at_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
             "pass": result.get("pass"), "per_arm": result.get("per_arm", {})},
            indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- the problems list already computed is what matters
        pass
    return out


# ---- PDT (Rule 7) VISIBILITY (2026-07-14) ---------------------------------------------
# The 2026-07-13 scar: core Safe was silently PDT-blocked ALL DAY on a day-trade count it
# INHERITED from an account repoint (commit 61cfca0, safe-2 repointed onto the former
# safe-1 fleet arm's account PA3DHPT7KIQE) -- a real, valid, gate-passing signal denied by
# risk_gate.check_order's PDT check, and nobody knew until a manual review found it
# (analysis/daily-brief/2026-07-13-FULL-AUDIT.md #2). Rule 7 fired CORRECTLY; the miss was
# that NOTHING surfaced the count until someone went looking. This closes that gap: a
# live per-account read every ~30 min (Gamma_SelfCheck cadence), always recorded (even
# when NOT blocked) for firm_brief.py's account section, and flagged DEGRADED/YELLOW
# (never BROKEN/RED -- Rule 7 doing its job is not itself a fault) ONLY when an account
# IS currently blocked.
PDT_ACCOUNTS = ("safe-2", "bold-2")  # the two engine-wired (mcp_heartbeat) accounts
PDT_LABEL = {"safe-2": "safe", "bold-2": "bold"}  # matches heartbeat_core.ACCOUNTS keys

# ---- 2026-07-15 FIX: margin-PDT alert was FICTIONAL for cash_settlement accounts ----
# Both core accounts are CASH accounts pinned to params.pdt_gate_mode="cash_settlement"
# (automation/state/params.json + aggressive/params.json, commit fd09a78, 2026-07-14) --
# risk_gate.check_order NEVER reads day_trades_used_5d for them in that mode (it gates on
# settled cash instead, see backtest/lib/risk_gate.py's cash_settlement branch). The margin
# branch below (unchanged, still correct for pdt_gate_mode="margin_pdt" accounts -- the
# fleet arms are pinned there, fleet_executor.py#finalize) fired
#   "SELF-CHECK DEGRADED: PDT-BLOCKED[safe]: 7/3 day-trades used (rolling 5bd)..."
# at 15:09 ET on 2026-07-15 (automation/state/discord-outbox.jsonl) describing a block that
# never happened -- both of that day's trades filled AFTER the alert's implied block.
# check_pdt_status now reads each account's OWN params.json#pdt_gate_mode FIRST
# (_pdt_gate_mode / _default_account_params) and, for cash_settlement accounts, reports
# settlement-ledger TRUTH instead (check_cash_settlement_status, below): entries used today +
# settled cash remaining vs params.max_same_day_roundtrips -- mirroring EXACTLY the gate
# risk_gate.check_order actually evaluates for these accounts, and alerting ONLY when that
# gate would actually refuse the next entry. Guard: test_self_check_pdt_status.py
# test_cash_settlement_account_ignores_margin_pdt_day_trade_count.


def _default_account_params(label: str) -> dict:
    """Live-read the account's params.json (STATE/params.json for safe,
    STATE/aggressive/params.json for bold -- same per-account path convention as
    heartbeat_core.ACCOUNTS). Fail-open to {} on any read error, which makes
    _pdt_gate_mode fall back to "margin_pdt" -- i.e. an unreadable params file
    degrades to the LEGACY (pre-2026-07-15) behavior, never a fabricated mode."""
    path = (STATE / "aggressive" / "params.json") if label == "bold" else (STATE / "params.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _pdt_gate_mode(account_params: dict) -> str:
    """Single source of truth for the mode string -- byte-identical default
    ("margin_pdt" when the key is absent) to risk_gate.check_order's own
    `pdt_mode = str(params.get("pdt_gate_mode") or "margin_pdt").strip().lower()`."""
    return str((account_params or {}).get("pdt_gate_mode") or "margin_pdt").strip().lower()


def _default_max_same_day_roundtrips() -> int:
    """Live-import risk_gate.DEFAULT_MAX_SAME_DAY_ROUNDTRIPS (single source of
    truth for the sanity-cap default) -- mirrors _pdt_constants()'s import
    pattern. Fail-open to the known-frozen value (5, unchanged since 2026-07-14)."""
    try:
        rg_dir = str(REPO / "backtest" / "lib")
        if rg_dir not in sys.path:
            sys.path.insert(0, rg_dir)
        import risk_gate as _rg  # noqa: PLC0415
        return int(_rg.DEFAULT_MAX_SAME_DAY_ROUNDTRIPS)
    except Exception:  # noqa: BLE001
        return 5


def _default_settlement_status(label: str, now, account_params: dict) -> "dict | None":
    """Live-read TODAY's settlement status for `label` via settlement_ledger.py --
    pure file I/O (no broker network call, unlike the margin path). Start-of-day
    settled cash is read from the account's own circuit-breaker.json (the SAME
    field heartbeat_core._execute uses to seed the ledger: starting_equity_today
    for safe, equity_start_of_day for bold -- see that file's #_schema_note for
    the field-name divergence). Returns None when that value is unreadable -- the
    caller renders this as an honest UNKNOWN, never a fabricated OK/BLOCKED."""
    import settlement_ledger as _sl  # noqa: PLC0415
    cb_path = (STATE / "aggressive" / "circuit-breaker.json") if label == "bold" else (STATE / "circuit-breaker.json")
    try:
        cb = json.loads(cb_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cb = {}
    sod = cb.get("equity_start_of_day") if label == "bold" else cb.get("starting_equity_today")
    try:
        sod = float(sod)
    except (TypeError, ValueError):
        return None
    ledger_path = _sl.ledger_path(STATE, label)
    today_et = now.strftime("%Y-%m-%d")
    return _sl.get_settlement_status(ledger_path, today_et, sod)


def check_cash_settlement_status(label: str, now, account_params: dict, *,
                                  settlement_status=None) -> "tuple[list, dict]":
    """VISIBILITY for pdt_gate_mode="cash_settlement" (2026-07-15 fix -- see the
    comment block above PDT_ACCOUNTS for the scar this closes). Reports
    settlement-ledger TRUTH: settled cash remaining + entries used today vs
    params.max_same_day_roundtrips -- the SAME inputs risk_gate.check_order's
    cash_settlement branch evaluates. Only alerts (DEGRADED, never BROKEN -- the
    gate doing its job correctly is not itself a fault) when that gate would
    ACTUALLY refuse the next entry:
      - entries_used_today >= max_same_day_roundtrips (the sanity cap), OR
      - settled_cash_remaining <= 0 (fully committed -- ANY positive-notional
        order would exceed it, regardless of size).
    Fail-open: an unreadable start-of-day settled cash renders UNKNOWN, never a
    fabricated OK or a false BLOCKED (OP-33)."""
    fetch = settlement_status or _default_settlement_status
    status = fetch(label, now, account_params)
    if status is None:
        return [], {"status": "UNKNOWN", "gate_mode": "cash_settlement",
                     "reason": "no readable start-of-day settled cash (circuit-breaker.json)"}
    max_rt_raw = account_params.get("max_same_day_roundtrips")
    try:
        max_rt = int(max_rt_raw) if max_rt_raw is not None else _default_max_same_day_roundtrips()
    except (TypeError, ValueError):
        max_rt = _default_max_same_day_roundtrips()
    entries_used = int(status.get("entries_used_today") or 0)
    remaining = float(status.get("settled_cash_remaining") or 0.0)
    sod = float(status.get("sod_settled_cash") or 0.0)
    blocked = entries_used >= max_rt or remaining <= 0.0
    entry = {
        "status": "BLOCKED" if blocked else "OK",
        "gate_mode": "cash_settlement",
        "entries_used_today": entries_used,
        "max_same_day_roundtrips": max_rt,
        "settled_cash_remaining": round(remaining, 2),
        "sod_settled_cash": round(sod, 2),
    }
    problems: list = []
    if blocked:
        cause = (f"{entries_used}/{max_rt} same-day entries used (sanity cap reached)"
                 if entries_used >= max_rt else
                 f"${remaining:,.2f} settled cash remaining (fully committed today)")
        problems.append(
            f"SETTLEMENT-BLOCKED[{label}]: {cause} -- pdt_gate_mode=cash_settlement would "
            f"refuse the next entry (SOD settled ${sod:,.2f}, ${remaining:,.2f} remaining, "
            f"{entries_used} entries placed today)."
        )
    return problems, entry


def _pdt_constants() -> "tuple[int, float]":
    """Live-import PDT_DAY_TRADE_LIMIT / PDT_EQUITY_THRESHOLD from risk_gate.py (single
    source of truth -- avoid a hand-copied constant drifting from the real gate). Fail-open
    to the known-frozen values (unchanged since 2026-07-06) on any import error, so a
    broken import degrades to a note, never crashes self_check."""
    try:
        rg_dir = str(REPO / "backtest" / "lib")
        if rg_dir not in sys.path:
            sys.path.insert(0, rg_dir)
        import risk_gate as _rg  # noqa: PLC0415
        return int(_rg.PDT_DAY_TRADE_LIMIT), float(_rg.PDT_EQUITY_THRESHOLD)
    except Exception:  # noqa: BLE001
        return 3, 25_000.0


def _fetch_account_equity(base: str, key: str, sec: str, timeout: float = 8.0):
    """Read-only GET /v2/account -> live equity (float) or None on any error (fail-open).
    A None equity makes check_pdt_status CONSERVATIVELY assume PDT applies (never silently
    assume an account cleared the $25K threshold just because the read failed)."""
    import urllib.request
    try:
        req = urllib.request.Request(base.rstrip("/") + "/v2/account",
                                     headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        return float(d.get("equity"))
    except Exception:  # noqa: BLE001
        return None


def _default_fetch_pdt_detail(creds: dict) -> dict:
    """Lazy import so a missing/broken pdt_tracker degrades this ONE check, not the module
    import of self_check.py itself."""
    import pdt_tracker as _pdt  # noqa: PLC0415
    return _pdt.fetch_day_trades_detail(creds)


def check_pdt_status(now, *, secrets_path=None, fetch_detail=None, fetch_equity=None,
                      account_params=None, settlement_status=None) -> "tuple[list, dict]":
    """VISIBILITY instrument for Rule 7 (PDT/settlement) -- see module-level comment above
    for BOTH scars this closes (2026-07-13 margin-PDT block visibility; 2026-07-15 fix so
    that visibility doesn't fabricate a margin-PDT block for cash_settlement accounts).

    Per account, reads params.json#pdt_gate_mode FIRST (via `account_params`, default
    _default_account_params) and branches:
      "cash_settlement" -> check_cash_settlement_status: settlement-ledger truth (settled
        cash remaining + entries used today vs max_same_day_roundtrips) -- the actual gate
        risk_gate.check_order evaluates for these accounts. No broker network call.
      "margin_pdt" (or absent -- byte-identical legacy default) -> the ORIGINAL live
        day_trades_used_5d + equity fetch via pdt_tracker.fetch_day_trades_detail (the
        HONEST-UNKNOWN variant), UNCHANGED. Still correct for any account pinned to
        margin_pdt (the fleet arms -- fleet_executor.py#finalize).

    Returns (problems, pdt_summary):
      problems    -- ONLY non-empty when an account IS currently blocked by the mode-
                     appropriate gate. DEGRADED/YELLOW severity in both modes (a gate
                     firing correctly is not itself a fault -- neither message matches
                     _problem_is_broken).
      pdt_summary -- ALWAYS populated per account label ("safe"/"bold"), or an explicit
                     {"status": "UNKNOWN", ...} entry on a fetch failure or missing
                     key/params -- NEVER a fabricated 0. Cash-settlement entries carry
                     "gate_mode": "cash_settlement" so firm_brief.render_pdt_lines (and any
                     future consumer) can render them distinctly from the margin-PDT shape.
    Fail-open: a missing/unreadable secrets file returns ([], {}) -- never raises into
    the scheduler."""
    out: list = []
    summary: dict = {}
    sec_file = secrets_path or (STATE / "fleet" / "secrets.json")
    try:
        accts = json.loads(sec_file.read_text(encoding="utf-8")).get("accounts", {})
    except Exception:  # noqa: BLE001
        return out, summary  # can't read secrets -> don't fabricate a problem (fail-open)

    limit, threshold = _pdt_constants()
    fetch_detail = fetch_detail or _default_fetch_pdt_detail
    fetch_equity = fetch_equity or _fetch_account_equity
    account_params = account_params or _default_account_params

    for arm in PDT_ACCOUNTS:
        label = PDT_LABEL[arm]
        params_for_acct = account_params(label) or {}
        gate_mode = _pdt_gate_mode(params_for_acct)

        if gate_mode == "cash_settlement":
            problems_i, entry = check_cash_settlement_status(
                label, now, params_for_acct, settlement_status=settlement_status)
            out.extend(problems_i)
            summary[label] = entry
            continue

        # ---- legacy margin_pdt path (byte-identical to pre-2026-07-15) ----
        a = accts.get(arm, {})
        key = a.get("api_key") or a.get("ALPACA_API_KEY") or a.get("key", "")
        sec = a.get("secret_key") or a.get("ALPACA_SECRET_KEY") or a.get("secret", "")
        base = a.get("base_url", "https://paper-api.alpaca.markets")
        if not key:
            summary[label] = {"status": "UNKNOWN", "reason": "no key in fleet/secrets.json"}
            continue

        detail = fetch_detail({"key": key, "secret": sec, "base_url": base})
        if not detail.get("ok"):
            summary[label] = {"status": "UNKNOWN", "reason": detail.get("error", "fetch failed")}
            continue

        equity = fetch_equity(base, key, sec)
        applies = (equity is None) or (equity < threshold)  # unknown equity -> conservative
        count = int(detail.get("count") or 0)
        rolloff = detail.get("rolloff_date")
        blocked = applies and count >= limit
        entry = {
            "day_trades_used_5d": count,
            "limit": limit,
            "remaining": max(0, limit - count),
            "rolloff_date": rolloff,
            "equity": equity,
            "pdt_applies": applies,
            "status": "BLOCKED" if blocked else ("OK" if applies else "NOT_APPLICABLE"),
        }
        summary[label] = entry
        if blocked:
            eq_s = f"${equity:,.2f}" if equity is not None else "unknown (assumed < $25K, conservative)"
            roll_s = rolloff or "unknown"
            out.append(f"PDT-BLOCKED[{label}]: {count}/{limit} day-trades used (rolling 5bd) at "
                       f"equity {eq_s} -- blocks a 4th day-trade until it rolls off {roll_s}.")
    return out, summary


ENTRY_MIN_TICKS = 30  # enough session elapsed that a tradeable engine should show entries-or-nothing-fired

# Data-gated / validated-correct sit-out signatures — proven NOT a fault by the 2026-06-30
# bull-unblock audit (thread CLOSED): `block_elite_bull` is KEEP (removed cohort net -$241 on
# the fresh OPRA window, DRY_AT_ZERO), `detect_sequence_reclaim` is structurally coupled off,
# and the whole 0DTE-SPY bull frontier is DATA-GATED, not a fixable engine bug. Treating these
# blocks as BROKEN made self_check perpetually-RED on validated behavior, which MASKS a genuine
# future "cannot enter" fault (L189: a persistently-RED audit masks new orphans). The correct
# layer to catch a bull-EDGE regression is `test_bull_unblock_replay_probe.py` (re-REDs the build
# if "block removes losers" ever flips to "unblock adds edge"), NOT the live liveness monitor.
_DATA_GATED_BLOCK_VERDICTS = frozenset({"SKIP_ELITE_BULL_LEVEL_RECLAIM"})


def _today_decisions(now, path=None) -> list:
    """Today's core-decisions rows (ET-date match). Fail-open -> []."""
    p = path or (STATE / "core-decisions.jsonl")
    day = now.strftime("%Y-%m-%d")
    rows = []
    try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln or day not in ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if str(o.get("ts_et", "")).startswith(day):
                rows.append(o)
    except OSError:
        pass
    return rows


def check_engine_tradeability(now, path=None) -> list:
    """CONTENT check (not mtime): did the engine actually REACH an ENTER today, or did
    high-scoring / trigger-firing setups get silently gate-blocked? The 2026-06-30 disease:
    772 ticks, 0 ENTER, 64x SKIP_ELITE_BULL_LEVEL_RECLAIM on a clean bull trend -- self_check
    read GREEN because every check was liveness-only. Flag the exact signature: a populated
    session with 0 entries AND >=1 trigger fired-but-blocked. Weekday, after ~10:30 ET."""
    out = []
    if now.weekday() >= 5 or now.strftime("%H:%M") < "10:30":
        return out  # weekend / too early -- not enough session elapsed to judge
    rows = _today_decisions(now, path)
    safe = [r for r in rows if r.get("account") == "safe"] or rows
    if len(safe) < ENTRY_MIN_TICKS:
        return out  # engine barely ticked -- the staleness checks cover that, not this
    if any(str(r.get("verdict", "")).startswith("ENTER") for r in safe):
        return out  # it entered (or could) -- fine
    # (1) A trigger fired but the entry was gate-blocked. Only a NON-data-gated block is a fault;
    # a validated data-gated block (block_elite_bull) is the engine CORRECTLY sitting out (bull
    # thread CLOSED 2026-06-30). Flag BROKEN only on an *unexpected* blocking verdict.
    blocked = [r for r in safe if str(r.get("verdict", "")).startswith("SKIP") and r.get("triggers")]
    real_blocked = [r for r in blocked if r.get("verdict") not in _DATA_GATED_BLOCK_VERDICTS]
    if real_blocked:
        from collections import Counter
        verdict, n = Counter(r.get("verdict") for r in real_blocked).most_common(1)[0]
        out.append(f"ENGINE CANNOT ENTER: {len(safe)} ticks today, 0 ENTER, {n}x {verdict} -- setups "
                   f"scored AND fired a trigger but every entry was gate-blocked by a NON-data-gated "
                   f"verdict. The engine is structurally sitting out (the 2026-06-30 zero-trade signature).")
        return out
    # (2) High conviction that never fired a trigger. Bull-side (straddle-only reclaim gap) is the
    # DATA-GATED structural condition (thread CLOSED) -> expected, silent. A high BEAR score with no
    # bear trigger is the LIVE-validated direction failing to convert -> a genuine detector concern.
    hi_bear = [r for r in safe if (r.get("bear_score") or 0) >= 9 and not r.get("triggers")]
    if len(hi_bear) >= ENTRY_MIN_TICKS:
        out.append(f"ENGINE NOT ENTERING (bear): {len(safe)} ticks today, 0 ENTER, {len(hi_bear)} ticks "
                   f"scored bear>=9 but no trigger fired (HOLD all day). The LIVE bear direction never "
                   f"converted to a trade -- check the bear trigger detector.")
    return out


def check_fill_funnel(now, core_path=None, fleet_dir=None) -> list:
    """FILL-FUNNEL check (the instrument that retires "is it actually trading?",
    OP-33e). Re-derives ticks -> ENTER -> attempted -> accepted -> filled -> exited
    per account from the decision ledgers (fill_funnel.py) and flags:
      BROKEN   any account attempted>0 with 0 broker-accepted (placement dead --
               the 2026-07-01 signature: 10 ENTER_BEAR, all PLACE_FAIL)
      DEGRADED any ENTER after the 15:00 ET entry ceiling, or (post-EOD) a fill
               with no exit record in the ledger.
    Weekdays only, after 09:40 ET (needs a live session to judge). Fail-open."""
    if now.weekday() >= 5 or now.strftime("%H:%M") < "09:40":
        return []
    try:
        import fill_funnel
        f = fill_funnel.compute_funnel(now.strftime("%Y-%m-%d"), now=now,
                                       core_path=core_path, fleet_dir=fleet_dir)
    except Exception as e:  # noqa: BLE001
        return [f"FILL-FUNNEL UNAVAILABLE: {type(e).__name__}: {e} -- cannot verify the money path."]
    if core_path is None and fleet_dir is None:
        try:
            fill_funnel.write_artifact(f)  # glanceable state file for J (OP-33c)
        except Exception:  # noqa: BLE001
            pass
    return [f"FILL-FUNNEL {fl}" for fl in f.get("flags", [])]


_CEIL_ROLES = {"resistance", "broken_to_support"}
_FLOOR_ROLES = {"support", "broken_to_resistance"}


def check_level_integrity(path=None) -> list:
    """CONTENT check: key-levels.json must be self-consistent. The engine reads every active
    level near spot; if one price carries BOTH a ceiling role (resistance/broken_to_support)
    AND a floor role (support/broken_to_resistance) it is fed contradictory structure (the
    2026-06-30 pollution: 741.81 x9 + 741.61 x7, each as both). Flag contradictory roles (RED)
    and heavy duplicates (>2x, DEGRADED). Fail-open."""
    out = []
    p = path or (STATE / "key-levels.json")
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return out  # missing/unreadable -> staleness check owns it
    from collections import defaultdict, Counter
    roles = defaultdict(set)
    counts = Counter()
    for x in d.get("levels", []):
        if str(x.get("tier", "")).lower() == "expired":
            continue
        try:
            price = round(float(x["price"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        roles[price].add(x.get("role"))
        counts[price] += 1
    contra = sorted(pr for pr, r in roles.items() if (r & _CEIL_ROLES) and (r & _FLOOR_ROLES))
    if contra:
        out.append(f"KEY-LEVELS CONTRADICTORY ROLES: price(s) {contra} carry BOTH a ceiling and a "
                   f"floor role -- the engine reads the same price as resistance AND support at once. "
                   f"refresh_levels_intraday role/dedup bug (2026-06-30).")
    dups = sorted(pr for pr, c in counts.items() if c > 2)
    if dups and not contra:
        out.append(f"KEY-LEVELS DUPLICATED: price(s) {dups} appear >2x in the active feed -- dedup "
                   f"not collapsing repeated writes.")
    return out


def check_dress_rehearsal(now, path=None) -> list:
    """Nightly REAL-broker dress-rehearsal reader (dress_rehearsal.py via Gamma_DressRehearsal
    ~20:45 ET) — the "are we good for tomorrow" instrument. J's pain class: green-lit in the
    evening, fails at the open. BROKEN when the latest rehearsal's overall verdict is RED, or
    when it is >24h old on a weekday evening (the task silently died). INCONCLUSIVE surfaces
    as DEGRADED (after-hours unprovable is NOT a green light). Fail-open outside the weekday-
    evening window when the artifact is missing."""
    p = path or (STATE / "dress-rehearsal.json")
    weekday_evening = now.weekday() < 5 and now.strftime("%H:%M") >= "21:00"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        if weekday_evening:
            return ["DRESS-REHEARSAL MISSING (RED): no broker-boundary rehearsal artifact on a "
                    "weekday evening -- tomorrow's open is UNPROVEN. Run setup/scripts/dress_rehearsal.py."]
        return []
    out: list = []
    overall = str(d.get("overall", "RED"))
    ran = str(d.get("ran_at_et", ""))
    age_h = None
    try:
        age_h = (now - dt.datetime.strptime(ran, "%Y-%m-%dT%H:%M:%S")).total_seconds() / 3600.0
    except ValueError:
        pass
    if overall == "RED":
        out.append(f"DRESS-REHEARSAL RED: broker-boundary rehearsal at {ran} FAILED -- see "
                   f"automation/state/dress-rehearsal.json. Tomorrow's open is NOT proven.")
    elif overall.startswith("INCONCLUSIVE"):
        out.append(f"DRESS-REHEARSAL INCONCLUSIVE at {ran}: a broker-boundary check could not be "
                   f"proven after hours -- do NOT treat tomorrow as green-lit.")
    if weekday_evening and (age_h is None or age_h > 24):
        out.append(f"DRESS-REHEARSAL STALE (RED): last rehearsal '{ran}' is >24h old on a weekday "
                   f"evening -- Gamma_DressRehearsal likely not firing.")
    return out


# ---- MACRO-CALENDAR FRESHNESS (2026-07-15) ---------------------------------------------
# The 2026-07-15 scar: Gamma_MacroCalendar (07:45 ET weekdays, setup/scripts/macro_calendar.py)
# missed its 07-15 fire -- root cause: an overnight Windows-Update reboot chain (3x
# TrustedInstaller "Operating System: Upgrade (Planned)" restarts, System event log 109/1074,
# ending 23:32:56 MT on 07-14) left no interactive logon session (this task, like every
# scheduled task in this repo, runs LogonType=Interactive) through the 05:45 MT/07:45 ET
# trigger window; corroborated by Gamma_ScoutPremarket (03:30 MT) ALSO showing
# NumberOfMissedRuns=1 with LastRunTime stuck at 07-14, while every task from 06:00 MT onward
# (LaunchTV, Premarket, HeartbeatCore) fired normally once the session resumed -- a clean
# ~05:45-06:00 MT boundary. StartWhenAvailable=True did NOT retroactively catch either missed
# task up even once the session returned, a known Task Scheduler limitation for
# LogonType=Interactive tasks. This is UNRELATED to the older (already-fixed 2026-07-09)
# weekly-review-producer staleness incident referenced in STATUS.md's 2026-07-06/07-08
# entries (last_refresh frozen at 2026-06-14, 22-24 days stale then) -- that producer was
# REPLACED by macro_calendar.py + Gamma_MacroCalendar on 2026-07-09, and the new producer's
# own refresh_log (automation/state/macro-calendar.json) shows clean consecutive weekday
# fires on 07-10/07-13/07-14 (all data_quality=live_verified) before this ONE isolated miss
# -- i.e. hours of staleness, not weeks.
#
# context_bundle_producer.py already computes this exact staleness (calendar_stale, in its
# events_context block) but that flag is LOGGED ONLY (bundle note: "not consumed by
# score/gates") with no STATUS.md/Discord surface of its own -- so a miss like 07-15's could
# recur silently. This wires the SAME detection into self_check's alert path so it can't rot
# unnoticed again, regardless of cause (missed fire, dead producer, or a deleted task).
#
# _calendar_staleness below is a PURE reimplementation of
# context_bundle_producer._calendar_staleness -- duplicated (not imported) because
# context_bundle_producer.py imports pandas at module level for its unrelated trend-alignment
# work, while self_check.py runs under the SYSTEM pythonw.exe (Gamma_SelfCheck's install
# script), which has NO pandas (verified 2026-07-15: `pythonw.exe -c "import pandas"` ->
# ModuleNotFoundError) -- importing context_bundle_producer here would make this check
# permanently "UNAVAILABLE" in production, which is worse than not having it. The two copies
# are cross-checked for behavioral parity by
# test_self_check_macro_calendar_freshness.py::test_matches_context_bundle_producer_calendar_staleness
# (runs under backtest/.venv, which DOES have pandas) -- any future change to the anchor logic
# in EITHER file must be mirrored in the other or that test REDs.
CALENDAR_STALE_SLACK_MIN = 30  # mirrors context_bundle_producer.CALENDAR_STALE_SLACK_MIN


def _calendar_staleness(news: "dict | None", *, now_et) -> "tuple[bool, str | None]":
    """True/reason iff news.json's freshness_stamp is older than the most recent expected
    Gamma_MacroCalendar fire (weekdays 07:45 ET) minus a slack window. Honest-degraded: a
    missing/malformed news.json is ALWAYS stale (never silently treated as fresh); a fresh
    file dated before today's 07:45-ET fire simply hasn't happened yet is NOT flagged stale --
    the most recent expected fire is the correct anchor, not "today" unconditionally. See the
    module comment above for why this is a deliberate, tested duplicate of
    context_bundle_producer._calendar_staleness rather than an import."""
    if news is None:
        return True, "news.json missing or malformed"
    stamp = news.get("freshness_stamp") or news.get("as_of")
    if not stamp:
        return True, "news.json has no freshness_stamp/as_of field"
    try:
        stamp_dt = dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return True, f"unparseable freshness_stamp: {stamp!r}"
    if stamp_dt.tzinfo is not None:
        stamp_dt = stamp_dt.replace(tzinfo=None)  # news.json stamps are naive-ET (et_now().isoformat())

    today_fire = now_et.replace(hour=7, minute=45, second=0, microsecond=0)
    if now_et.weekday() >= 5:  # "now" itself falls on a weekend -- anchor to last Friday's fire
        expected = today_fire - dt.timedelta(days=now_et.weekday() - 4)
    elif now_et < today_fire:
        # before today's fire -- anchor to the LAST prior weekday's fire (Monday -> Friday)
        expected = today_fire - dt.timedelta(days=3 if now_et.weekday() == 0 else 1)
    else:
        expected = today_fire
    threshold = expected - dt.timedelta(minutes=CALENDAR_STALE_SLACK_MIN)
    if stamp_dt < threshold:
        age_h = (now_et - stamp_dt).total_seconds() / 3600.0
        return True, (f"freshness_stamp {stamp_dt.isoformat()} predates the expected "
                       f"{expected.isoformat()} ET fire (~{age_h:.1f}h old)")
    return False, None


def check_macro_calendar_freshness(now, news_path=None) -> list:
    """VISIBILITY instrument for the macro/event calendar (2026-07-15 fix -- see the module
    comment above _calendar_staleness for the scar this closes). BROKEN/RED (not DEGRADED,
    unlike most staleness checks in this file) -- a stale calendar means the engine's
    no-trade-window coverage for a fresh CPI/FOMC/NFP/PPI/Retail-Sales print may be silently
    blind, which is a real trading-relevant gate, not a cosmetic staleness (mirrors
    check_dress_rehearsal's "(RED)" idiom for the same reason: a premarket-prep gate that may
    not have run is not provably safe). Fail-open in the sense that a read/parse failure is
    itself treated as stale (never silently 'probably fine')."""
    p = news_path or (STATE / "news.json")
    try:
        news = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        news = None
    stale, reason = _calendar_staleness(news, now_et=now)
    if not stale:
        return []
    return [f"MACRO-CALENDAR STALE (RED): {reason} -- Gamma_MacroCalendar (07:45 ET weekdays) "
            f"may have missed its fire or the producer is dead; the engine's no-trade-window "
            f"coverage for a fresh CPI/FOMC/NFP/PPI/Retail-Sales event may be blind. Re-run "
            f"setup/scripts/macro_calendar.py by hand, or check "
            f"`schtasks /query /tn Gamma_MacroCalendar /v`."]


# ---- WEEKLY-1 EARNINGS-CALENDAR FRESHNESS (2026-08-18) --------------------------------
# WEEKLY-OPTIONS-PROGRAM.md's "trusted earnings calendar" workstream: setup/scripts/
# earnings_calendar.py is the sole guard against the weekly-options lane's single worst
# NEW failure mode vs the core 0DTE SPY book -- holding a single-name option through an
# earnings print, where IV crush loses money even when direction is right. That producer's
# own written contract (automation/state/weekly/earnings-blackout.json#_fail_closed_contract)
# already tells any consumer to treat the feed as BLOCKED for every non-exempt symbol when
# the file is missing/stale -- this wires that SAME rule into the standing self_check alarm
# surface so a dead producer can't rot unnoticed the way Gamma_MacroCalendar's did on
# 2026-07-15 (check_macro_calendar_freshness above; this check deliberately mirrors that
# one's shape and severity).
#
# RED (BROKEN), not DEGRADED, for the same reason as MACRO-CALENDAR STALE: a stale
# earnings feed is a real trading-relevant gap for weekly-1's single-name symbols, not a
# cosmetic staleness.
#
# The staleness threshold is read LIVE from weekly/params.json#entry.
# earnings_feed_stale_hours_fail_closed -- single source of truth shared with the
# producer's own fail-closed contract, never a hand-copied constant here (mirrors
# check_pdt_status's _default_max_same_day_roundtrips "live-read, not hand-copied"
# pattern) -- with a fail-open default of 48h (the value in place at build time) if that
# key is itself unreadable, so a params-read failure degrades to a last-known-good number
# rather than silencing the alarm or fabricating a stricter one.
#
# weekly-1 is shadow-only / paper-pending (no scheduled cadence exists yet for this
# producer at build time) -- this check runs UNCONDITIONALLY (no weekday/RTH gate, unlike
# most staleness checks in this file) so it is ready the moment a cadence is wired, rather
# than silently waiting on a time window that may not match whatever cadence lands.
EARNINGS_BLACKOUT_JSON = STATE / "weekly" / "earnings-blackout.json"
WEEKLY_PARAMS_JSON = STATE / "weekly" / "params.json"
_EARNINGS_FEED_STALE_HOURS_DEFAULT = 48.0  # last-known-good fallback if params.json is unreadable


def check_earnings_calendar_freshness(now, path=None, params_path=None) -> list:
    """VISIBILITY + FAIL-CLOSED alarm for the weekly-1 earnings-blackout feed. See the
    module comment immediately above for the full rationale (mirrors
    check_macro_calendar_freshness's shape/severity for the same reason: both gate a
    real, undisclosed-until-now trading risk, not a cosmetic staleness).

    Missing/unreadable file -> RED (fail-closed: an absent feed must never read as
    'probably fine'). Unparseable generated_at_et -> RED (staleness undetectable, treat
    as stale). Age beyond the live-read threshold -> RED. A fresh, parseable file ->
    silent (no problem)."""
    pp = params_path or WEEKLY_PARAMS_JSON
    try:
        params = json.loads(pp.read_text(encoding="utf-8"))
        stale_hours = float(params["entry"]["earnings_feed_stale_hours_fail_closed"])
    except Exception:  # noqa: BLE001
        stale_hours = _EARNINGS_FEED_STALE_HOURS_DEFAULT

    p = path or EARNINGS_BLACKOUT_JSON
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return [f"EARNINGS-CALENDAR MISSING/UNREADABLE (RED): {p.name} not found or not valid "
                f"JSON -- per its own fail-closed contract, EVERY non-exempt weekly-1 single-"
                f"name symbol must be treated as BLOCKED until this producer runs. Run "
                f"setup/scripts/earnings_calendar.py."]
    gen_at = d.get("generated_at_et")
    try:
        gen_dt = dt.datetime.fromisoformat(str(gen_at))
    except (ValueError, TypeError):
        return [f"EARNINGS-CALENDAR STALE (RED): {p.name} has no parseable generated_at_et "
                f"({gen_at!r}) -- staleness undetectable, treat as stale (fail-closed)."]
    age_h = (now - gen_dt).total_seconds() / 3600.0
    if age_h > stale_hours:
        return [f"EARNINGS-CALENDAR STALE (RED): {p.name} is {age_h:.1f}h old (fail-closed "
                f"threshold {stale_hours:.0f}h, params.json#entry."
                f"earnings_feed_stale_hours_fail_closed) -- per its own fail-closed contract, "
                f"every non-exempt weekly-1 single-name symbol must be treated as BLOCKED "
                f"until setup/scripts/earnings_calendar.py runs again."]
    return []


# ---- PRIOR-TRADING-DAY DARK (2026-07-24) -----------------------------------------------
# The 2026-07-15 scar (see _calendar_staleness above) was diagnosed as ONE producer
# (Gamma_MacroCalendar) missing its fire because an overnight event left no interactive
# logon session through the trigger window -- LogonType=Interactive being this repo's
# universal task-registration convention, and StartWhenAvailable=True NOT retroactively
# catching a missed Interactive-logon task even once the session resumes (a documented Task
# Scheduler limitation, per that scar's own writeup).
#
# 2026-07-24 repeated the SAME mechanism at a MUCH larger scope: the machine entered sleep
# at 2026-07-23 21:48 MT (Kernel-Power evt id 42) and did not wake until 2026-07-25 09:12 MT
# (Saturday) -- a ~35.4h gap spanning the ENTIRE Friday 2026-07-24 trading session.
# core-decisions.jsonl has ZERO rows dated 2026-07-24 (confirmed both accounts); every
# scheduled task from Gamma_LaunchTV (06:00 MT) through Gamma_EodFlatten (15:55 ET) simply
# never fired -- three of those tasks (Premarket/LaunchTV/EodFlatten) already had
# WakeToRun=True set, yet none of them woke the box (powercfg /lastwake: "Wake Source
# Count - 0" for the eventual Saturday wake), so wake-timers alone are NOT a reliable fix.
# No position was open at sleep-onset (engine-health confirmed flat both accounts), so this
# was a missed-opportunity day, not a stuck-position risk -- but it is a full engine-dark
# trading day that went COMPLETELY undetected until this fire, purely as a side-effect of
# check_macro_calendar_freshness ALSO being stale that same window. Every other per-producer
# staleness check in this file is scoped to "today, weekday, after some time" and therefore
# self-heals invisibly once Monday's fresh ticks arrive -- so a fully-dark PAST trading day
# discovered on a weekend read (like this one) had no dedicated first-class check of its own.
#
# This is a RE-VIOLATED lesson (same mechanism, 2nd occurrence, much larger blast radius) --
# OP-25's "a re-violated lesson MUST become a test" applies: this check looks BACKWARD at the
# most recently COMPLETED trading day (not "today"), runs on ANY day of the week (including
# weekends), and persists the flag until that specific date's ledger shows real RTH activity
# -- so the NEXT occurrence (any cause: sleep, reboot, disabled task, crashed process) cannot
# self-heal out of visibility before a human sees it.
DECISIONS_RTH_START = "09:30"
DECISIONS_RTH_END = "15:55"


def _last_completed_trading_day(now, holidays: set) -> str:
    """The most recent weekday, non-holiday date strictly before `now`'s own calendar date
    (i.e. a day that has fully closed -- never judges a day still in progress)."""
    d = now.date() - dt.timedelta(days=1)
    while d.weekday() >= 5 or d.strftime("%Y-%m-%d") in holidays:
        d -= dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def check_prior_trading_day_dark(now, core_path=None, calendar_path=None) -> list:
    """BROKEN iff the most recently COMPLETED trading day has ZERO core-decisions.jsonl rows
    inside the 09:30-15:55 ET RTH window -- i.e. the entire engine (both accounts) never
    ticked once on a real trading day. Runs unconditionally (any weekday, including
    weekends) so the flag can't quietly expire before J sees it. Fail-open: any read/parse
    error returns [] (uninformative, never a false BROKEN) -- this check only asserts on
    POSITIVE evidence of a populated-but-empty ledger window, never on "file missing"."""
    try:
        cal = json.loads((calendar_path or (STATE / "calendar.json")).read_text(encoding="utf-8-sig"))
        holidays = set(cal.get("holidays", []))
    except Exception:  # noqa: BLE001
        holidays = set()
    target = _last_completed_trading_day(now, holidays)
    p = core_path or (STATE / "core-decisions.jsonl")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []  # ledger unreadable -- other checks (fill-funnel, engine-health) own that fault
    rth_rows = 0
    if target in text:  # cheap pre-filter: only line-scan+JSON-parse if the date appears at all
        for ln in text.splitlines():
            if target not in ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            ts = str(o.get("ts_et", ""))
            if not ts.startswith(target):
                continue
            hm = ts[11:16]
            if DECISIONS_RTH_START <= hm <= DECISIONS_RTH_END:
                rth_rows += 1
    if rth_rows > 0:
        return []
    return [f"ENGINE DARK ALL DAY (RED): {target} was a trading day with ZERO core-decisions.jsonl "
            f"rows in the 09:30-15:55 ET RTH window -- the entire engine (both accounts) never "
            f"ticked once. Root-cause candidates (2026-07-24 scar): the box went to sleep and never "
            f"woke for the scheduled tasks (check `powercfg /lastwake`, System event log Kernel-Power "
            f"id 42/1 around that evening/morning), Task Scheduler LogonType=Interactive silently "
            f"dropping every task through the gap (WakeToRun=True alone did NOT fix this in the "
            f"2026-07-24 incident -- 3 of 6 critical tasks already had it set and none fired), or "
            f"Gamma_HeartbeatCore itself disabled/crashed. Verify no position was left open that day "
            f"(engine-health.json position_safe/position_bold) before treating this as cosmetic."]


TRENDLINE_DRAW_STATE = STATE / "trendline-headless-draw.json"

# Statuses meaning the chart's trendlines were actually (re)drawn this run.
TRENDLINE_DRAW_OK_STATUSES = ("OK",)
# The EXPECTED fail-open paths (TradingView/CDP down, or too few bars) -- routine off-hours
# conditions, not a defect. Still worth a quiet, non-alarming trace (report-only), distinct
# from a genuine ERROR status.
TRENDLINE_DRAW_SOFT_SKIP_STATUSES = ("SKIPPED_TV_DOWN", "SKIPPED_NO_DATA")


def check_trendline_draw_freshness(now, path=None) -> list:
    """VISIBILITY instrument for the daily trendline chart-drawing pass.

    RE-POINTED 2026-09-03 AT THE LIVE PRODUCER (TRENDLINE-DRAW-HEADLESS, same shape as
    CHART-DRAWING's 2026-09-02 re-point -- see check_chart_wipe_redraw_freshness above). This
    check used to watch premarket Step 5c, an LLM-discretionary step (automation/prompts/
    premarket.md) that stamped the OLD `trendline-draw-state.json#last_run` -- and which had
    skipped with reason='budget conservation' (an LLM choosing not to run a $0 deterministic
    job) while `trendline_chart_draw.py` sat unused, citing a headless-CDP constraint that
    `Gamma_ChartAutoDraw` (2026-08-06) had already disproved. `setup/scripts/
    trendline_headless_draw.py` (registered as `Gamma_TrendlineHeadlessDraw`) is the fix: a
    pure-Python, $0, no-LLM producer that stamps `trendline-headless-draw.json` instead. This
    check now reads THAT file and never touches the old one -- the old stamp keeps its own
    meaning ("the LLM skill ran today") for anyone still consulting it by hand.

    Gated on STATUS, not just today's date (same reasoning as CHART-DRAWING): the producer
    write_state()s on every path, including its own failure/skip paths, so a bare "as_of is
    today" test would read GREEN on a TradingView-down morning while the chart still carries
    yesterday's lines. `SKIPPED_TV_DOWN`/`SKIPPED_NO_DATA` are the EXPECTED fail-open route
    (this repo's rig is often not staring at a live TradingView session off-hours) and get a
    softer, report-only message than a genuine `ERROR` -- doctrine ordinarily says fail-open
    is a pass, not a defect, so this must never escalate a routine TV-down skip to the same
    severity as an actual bug, while still leaving a non-silent trace either way.

    DEGRADED, never BROKEN: chart drawing is explicitly 'additive visibility, never load-
    bearing for the trading day' -- a miss does not block or misinform trading decisions the
    way a stale macro calendar or contradictory key-levels role does, so no message here may
    contain a BROKEN-classifying substring (see _problem_is_broken)."""
    if now.weekday() >= 5:
        return []  # no weekday draw window on weekends -- nothing to check
    if now.strftime("%H:%M") < "09:00":
        return []  # give the premarket window its slack before judging today stale
    p = path or TRENDLINE_DRAW_STATE
    today = now.strftime("%Y-%m-%d")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict) or not data.get("as_of"):
        return [f"TRENDLINE-DRAW never marked today ({today}) -- trendline_headless_draw.py "
                f"left no stamp in {p.name}, so J's chart may be carrying stale trendlines with "
                f"no trace. Non-load-bearing (visibility only); run "
                f"`python setup/scripts/trendline_headless_draw.py` to catch up."]
    as_of_date = str(data["as_of"])[:10]
    if as_of_date != today:
        return [f"TRENDLINE-DRAW STALE: last stamp was {as_of_date}, not today ({today}) -- "
                f"trendline_headless_draw.py did not complete a run this morning. Non-load-"
                f"bearing (visibility only); run "
                f"`python setup/scripts/trendline_headless_draw.py` to catch up."]
    status = str(data.get("status") or "UNKNOWN")
    if status in TRENDLINE_DRAW_OK_STATUSES:
        return []
    reason = data.get("reason") or "no reason recorded"
    if status in TRENDLINE_DRAW_SOFT_SKIP_STATUSES:
        return [f"TRENDLINE-DRAW skipped today ({today}): status={status} ({reason}) -- the "
                f"expected fail-open path (TradingView/CDP not up), report-only. Non-load-"
                f"bearing; nothing to do unless this persists across multiple days."]
    return [f"TRENDLINE-DRAW DID NOT DRAW today ({today}): status={status} ({reason}) -- ran "
            f"but did not update the chart. Non-load-bearing (visibility only); check "
            f"TradingView/CDP on 9222, then run `python setup/scripts/trendline_headless_draw.py`."]


CHART_AUTODRAW_STATE = STATE / "chart-autodraw.json"

# Statuses of draw_key_levels.py that mean THE CHART WAS ACTUALLY REDRAWN. It calls
# write_state() on its failure paths too (so a run always leaves a trace -- correct), which
# means a bare "as_of is today" test would read GREEN on a TradingView-down morning while
# J's chart still carried yesterday's levels. The status is the load-bearing half.
CHART_AUTODRAW_OK_STATUSES = ("OK",)


def check_chart_wipe_redraw_freshness(now, path=None) -> list:
    """VISIBILITY instrument for the daily chart wipe + level redraw.

    RE-POINTED 2026-09-02 AT THE LIVE PRODUCER. This check was built to watch premarket
    Step 5, an LLM step that stamped `key-levels.json -> chart_drawing_summary.as_of`. That
    producer is RETIRED: `Gamma_ChartAutoDraw` (registered 2026-08-06, $0, 08:35-16:05 ET
    every 30m) replaced it with `setup/scripts/draw_key_levels.py`, which stamps
    `automation/state/chart-autodraw.json` instead and never touches the old field.

    So the old stamp froze at 2026-06-29 and this check reported CHART-DRAWING STALE every
    30 minutes for months -- against a chart that was in fact being redrawn correctly every
    day. Verified 2026-09-02: chart-autodraw.json as_of=2026-09-01T16:05 ET, dry_run=false,
    real removals at spot 761.57, task GREEN in scheduled_task_staleness. A check pointed at
    a dead knob reports on the dead knob (C14), and its noise is what buried the whole
    `### BROKEN` surface (queue.md STATUS-BROKEN-BLOCKS-DRAIN).

    DEGRADED, never BROKEN: the deterministic engine reads key-levels.json's `levels` array
    for entries/exits and never any drawing stamp, so a miss costs J's eyeball context, not
    trading correctness. The message says "CHART-DRAWING" and never the upper-case substring
    "RED" (as in "REDRAW"), which would trip _problem_is_broken's bare "RED" test and
    outrank real trading-critical work in the conductor's triage."""
    if now.weekday() >= 5:
        return []  # no weekday draw window on weekends -- nothing to check
    if now.strftime("%H:%M") < "09:00":
        return []  # first fire is 08:35 ET; give it its slack window before judging today
    p = path or CHART_AUTODRAW_STATE
    today = now.strftime("%Y-%m-%d")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict) or not data.get("as_of"):
        return [f"CHART-DRAWING never marked today ({today}) -- Gamma_ChartAutoDraw "
                f"(draw_key_levels.py) left no stamp in {p.name}, so J's chart may be "
                f"carrying stale levels with no trace. Non-load-bearing (visibility only); "
                f"run `python setup/scripts/draw_key_levels.py` to catch up."]
    as_of_date = str(data["as_of"])[:10]
    if as_of_date != today:
        return [f"CHART-DRAWING STALE: last chart-autodraw stamp was {as_of_date}, not today "
                f"({today}) -- Gamma_ChartAutoDraw did not complete a run this morning. "
                f"Non-load-bearing (visibility only); run "
                f"`python setup/scripts/draw_key_levels.py` to catch up."]
    status = str(data.get("status") or "UNKNOWN")
    if status not in CHART_AUTODRAW_OK_STATUSES:
        return [f"CHART-DRAWING DID NOT DRAW today ({today}): Gamma_ChartAutoDraw ran and "
                f"stamped {p.name}, but status={status} -- it wrote a trace WITHOUT updating "
                f"the chart (TradingView down, or a dry run), so J's chart still carries the "
                f"previous session's levels. Non-load-bearing (visibility only); check "
                f"TradingView/CDP on 9222, then run `python setup/scripts/draw_key_levels.py`."]
    return []


TRENDLINES_FEED = STATE / "trendlines.json"
TRENDLINES_LIVE = STATE / "trendlines-live.json"


def check_trendline_feed_freshness(now, feed_path=None, live_path=None) -> list:
    """D9 LIVENESS GUARD (2026-08-06): trendlines.json sat stale for 47 DAYS (2026-05-14 ->
    2026-08-06) with zero alarms -- its only producer invocation was an LLM prompt step
    (premarket.md step 2) that run-premarket.ps1's deliverable gate never checked (C7).
    The producer is now a deterministic premarket step (run-premarket.ps1 TRENDLINES step,
    automation/scripts/compute_trendlines.py); THIS check is the alarm that fires within a
    day if either trendline surface dies again:
      * trendlines.json      -- the daily premarket context artifact (SHADOW, zero code
                                consumers by design until validated)
      * trendlines-live.json -- the LIVE organ (trendline_engine.py via Gamma_Trendlines,
                                every 5 min RTH; feeds trendline-watch visibility)
    DEGRADED, never BROKEN: both surfaces are shadow/visibility -- a death costs research
    context, not trading correctness (the engine's trendline_rejection trigger computes its
    own line in-process from prior_bars and reads NEITHER file). Weekend/Monday slack keeps
    Sat/Sun/Mon-morning from false-alarming on a Friday-dated file."""
    problems = []
    # calendar slack: file is produced weekday premarket; allow the weekend gap
    slack_days = {5: 2.0, 6: 3.0, 0: 3.5}.get(now.weekday(), 1.5)

    def _age_days(stamp: str):
        try:
            dt_ = dt.datetime.fromisoformat(str(stamp))
            if dt_.tzinfo is not None:
                dt_ = dt_.replace(tzinfo=None)
            return (now - dt_).total_seconds() / 86400.0
        except (ValueError, TypeError):
            return None

    for label, path, stamp_key in (
            ("TRENDLINE-FEED", feed_path or TRENDLINES_FEED, "as_of"),
            ("TRENDLINE-LIVE", live_path or TRENDLINES_LIVE, "generated_at")):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 -- missing/corrupt IS the death this alarms on
            problems.append(f"{label} DEGRADED: {Path(path).name} missing/unreadable -- the "
                            f"producer is dead (47-day-silence class, D9). Shadow surface, "
                            f"non-load-bearing; revive the producer.")
            continue
        stamp = data.get(stamp_key) or data.get("ts_et") or data.get("as_of")
        age = _age_days(stamp)
        if age is None:
            problems.append(f"{label} DEGRADED: {Path(path).name} carries no parseable "
                            f"{stamp_key!r} timestamp ({stamp!r}) -- staleness undetectable, "
                            f"treat as dead (D9).")
        elif age > slack_days:
            problems.append(f"{label} DEGRADED: {Path(path).name} is {age:.1f} days old "
                            f"(stamp {stamp}, limit {slack_days}d) -- the producer died "
                            f"again (47-day-silence class, D9). Shadow surface, non-load-"
                            f"bearing; check run-premarket.ps1 TRENDLINES step / "
                            f"Gamma_Trendlines.")
    return problems


REGIME_STAMP_JSON = STATE / "regime-stamp.json"


def check_regime_stamp_daily(now, stamp_path=None, bias_path=None) -> list:
    """DAILY drift detector for regime-stamp.json <-> today-bias.json#regime_context
    (self-audit gap, flagged 2026-08-02 AND independently re-flagged 2026-08-03 -- a
    2-batch recurrence is the graduation signal per OP-25/C7). Gamma_RegimeStamp (08:22
    ET) writes regime-stamp.json then patches today-bias.json#regime_context; Gamma_
    Premarket (08:30 ET, LLM-authored) is supposed to re-lift the same stamp when it
    regenerates today-bias.json fresh for the day. Until this check, the ONLY verification
    of that handoff was monday_verify.py's WS6 check -- which runs ONCE A WEEK. A Tue-Fri
    silent drift (Premarket's LLM step failing to lift the stamp, or overwriting
    regime_context with a stale/missing value) had no daily detector at all.

    DESCRIPTIVE ONLY, DEGRADED not BROKEN (regime_context is explicitly non-load-bearing --
    "never a live entry input", per regime_stamp.py's own docstring) -- mirrors the
    trendline-draw-freshness pattern immediately above: a real, non-silent flag, but not a
    trading halt. Reuses the exact drift logic monday_verify.py's WS6 check already proved
    correct (dates_match: regime-stamp.json#date == today AND
    today-bias.json#regime_context.stamp_date == today) rather than re-deriving it."""
    if now.weekday() >= 5:
        return []  # no Gamma_RegimeStamp/Gamma_Premarket fire on weekends
    if now.strftime("%H:%M") < "09:00":
        return []  # give the 08:22/08:30 ET fires their window before judging today stale
    today = now.strftime("%Y-%m-%d")
    sp = stamp_path or REGIME_STAMP_JSON
    bp = bias_path or (STATE / "today-bias.json")
    try:
        stamp = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    except Exception:  # noqa: BLE001
        stamp = None
    try:
        bias = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else None
    except Exception:  # noqa: BLE001
        bias = None
    if stamp is None or bias is None:
        return [f"REGIME-STAMP DEGRADED: {'regime-stamp.json' if stamp is None else 'today-bias.json'} "
                f"missing/unreadable today ({today}) -- Gamma_RegimeStamp/Gamma_Premarket handoff "
                f"unverifiable. Non-load-bearing (visibility only)."]
    rc = bias.get("regime_context") if isinstance(bias, dict) else None
    stamp_date = stamp.get("date") if isinstance(stamp, dict) else None
    rc_stamp_date = (rc or {}).get("stamp_date") if isinstance(rc, dict) else None
    if not rc:
        return [f"REGIME-STAMP DRIFT: today-bias.json ({today}) has no regime_context -- "
                f"Gamma_Premarket likely did not re-lift the 08:22 ET stamp. Non-load-bearing "
                f"(visibility only); regime_stamp.py --run to catch up."]
    if stamp_date != today or rc_stamp_date != today:
        return [f"REGIME-STAMP DRIFT: regime-stamp.json date={stamp_date}, today-bias.json "
                f"regime_context.stamp_date={rc_stamp_date}, today={today} -- stale handoff between "
                f"Gamma_RegimeStamp and Gamma_Premarket. Non-load-bearing (visibility only); "
                f"regime_stamp.py --run to catch up."]
    return []


SCOUT_OUTPUT_JSON = STATE.parent / "scout" / "state" / "scout_output.json"


def check_scout_premarket_fresh(now, scout_path=None) -> list:
    """DAILY freshness/liveness check for Gamma_ScoutPremarket (05:30 ET) -> scout_output.json
    (self-audit gap flagged 2026-08-06: "The Scout premarket macro/news scanner repeatedly
    fails due to a low USD budget, leaving scout_output.json stale and biasing downstream
    regime/bias decisions"). Live-verified 2026-08-07: the Windows task itself fires and
    reports LastTaskResult=0 every weekday (it is an LLM-agent-driven task, not a deterministic
    script), but scout-log.jsonl -- the agent's OWN append-only record of its fires -- has
    only 9 entries across 2026-05-20..2026-08-07, with a full month (2026-06-19..2026-07-21)
    of complete silence. LastTaskResult=0 is therefore NOT evidence the agent actually
    regenerated scout_output.json that day (C7: exit-code success != real work) -- this reads
    the CONSUMED ARTIFACT itself, mirroring check_regime_stamp_daily/check_trendline_feed_freshness's
    pattern, rather than trusting the scheduler.

    DEGRADED (never BROKEN): scout_addendum_to_swarm is explicitly an ADDENDUM feed into
    Premarket's 08:30 ET bias write, not itself a live-entry gate -- a stale/missing scout
    read degrades Premarket's macro-news context, it does not halt trading."""
    if now.weekday() >= 5:
        return []  # no Gamma_ScoutPremarket fire on weekends
    if now.strftime("%H:%M") < "08:00":
        return []  # give the 05:30 ET fire (+ any late-fire retry) its window before judging
    today = now.strftime("%Y-%m-%d")
    sp = scout_path or SCOUT_OUTPUT_JSON
    try:
        out = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    except Exception:  # noqa: BLE001
        out = None
    if out is None:
        return [f"SCOUT DEGRADED: scout_output.json missing/unreadable today ({today}) -- "
                f"Gamma_ScoutPremarket produced no readable macro/news feed for Premarket's "
                f"08:30 ET bias write. Non-load-bearing (addendum only); "
                f"run-scout-premarket.ps1 to catch up."]
    gen_at = out.get("generated_at") if isinstance(out, dict) else None
    gen_date = str(gen_at)[:10] if gen_at else None
    session_date = out.get("for_session_date") if isinstance(out, dict) else None
    if gen_date != today and session_date != today:
        return [f"SCOUT STALE: scout_output.json generated_at={gen_at!r} "
                f"for_session_date={session_date!r}, today={today} -- Gamma_ScoutPremarket did "
                f"not refresh today (task LastTaskResult can read 0 even when the agent produced "
                f"nothing new -- exit-code success is not evidence here). Non-load-bearing "
                f"(addendum only); run-scout-premarket.ps1 to catch up."]
    return []


SELF_AUDIT_GAP_LOG = REPO / "analysis" / "self-audit" / "gap-log.jsonl"


def check_self_audit_organ_alive(now, log_path=None) -> list:
    """DAILY liveness check for Gamma_SelfAudit's own dedup ledger (self-audit gap,
    found 2026-08-11: `self_audit.py`'s outer subprocess timeout to swarm_consult.py was
    300s, LESS than swarm_consult's own worst-case internal budget (240s perspectives +
    300s synthesis = 540s) -- 2 consecutive full-audit failures (2026-08-09, 2026-08-10)
    were silently swallowed by a bare `except Exception: return 0`, invisible to Task
    Scheduler (LastTaskResult=0) and to J (new-gaps-flagged.md, a SEPARATE properly-
    committed file, kept looking alive because its own DONE-triage edits are conductor-
    authored, not self_audit.py-authored). This reads the CONSUMED dedup ledger
    (gap-log.jsonl) directly, mirroring check_regime_stamp_daily/check_scout_premarket_fresh's
    'verify the artifact, not the exit code' pattern -- rather than trusting the scheduler.

    Gamma_SelfAudit fires ~17:30 ET EVERY day (including weekends, confirmed live against
    the scheduled task's own info), unlike the weekday-only Premarket/Scout/RegimeStamp checks --
    so this check does NOT skip weekends. DEGRADED (never BROKEN): the gap-finder is a
    proactive-visibility organ, not a trading-path input; a stale ledger degrades J's
    "Gamma catches its own gaps" signal, it does not halt or misdirect a trade."""
    if now.strftime("%H:%M") < "18:15":
        return []  # give the ~17:30 ET fire its 600s swarm budget + buffer before judging
    today = now.strftime("%Y-%m-%d")
    lp = log_path or SELF_AUDIT_GAP_LOG
    if not lp.exists():
        return [f"SELF-AUDIT DEGRADED: gap-log.jsonl missing today ({today}) -- Gamma_SelfAudit "
                f"has never completed a full run, or its state dir was wiped. Non-load-bearing "
                f"(visibility only); run self_audit.py by hand to catch up."]
    newest_date = None
    try:
        for line in lp.read_text(encoding="utf-8").splitlines():
            try:
                ts = json.loads(line).get("ts_et")
            except Exception:  # noqa: BLE001
                continue
            if ts and (newest_date is None or ts[:10] > newest_date):
                newest_date = ts[:10]
    except Exception:  # noqa: BLE001
        return [f"SELF-AUDIT DEGRADED: gap-log.jsonl unreadable today ({today}). Non-load-bearing "
                f"(visibility only)."]
    if newest_date != today:
        return [f"SELF-AUDIT STALE: gap-log.jsonl newest entry dated {newest_date!r}, today={today} "
                f"-- Gamma_SelfAudit's swarm consult likely failed silently (exit-0 on TimeoutExpired "
                f"is by design in self_audit.py's except-block; check self-audit.stdout.log for "
                f"'swarm run failed'). Non-load-bearing (visibility only); "
                f"python setup/scripts/self_audit.py to catch up."]
    return []


def _parse_run_cmd_hidden_log(text: str) -> list[dict]:
    """PURE. Parse run_cmd_hidden.py's own per-fire launcher log (automation/state/logs/
    run-cmd-hidden-<date>.log) into completed [{"cmd": str, "exit": int}] records.

    Each fire writes a 'launching: <cmd>  [pid=<N>]' line, zero or more 'cwd=.../WARN ...'
    lines, then exactly one '  exit=<N>  [pid=<N>]' (or '  exit=<N> (off-desktop)') line
    once the child returns.

    2026-08-21 CONCURRENCY-MISATTRIBUTION FIX: the old parser paired each 'launching:' with
    the NEXT 'exit=' line seen, i.e. a FIFO-of-1 -- correct only if run_cmd_hidden.py fires
    were strictly sequential. Live evidence this fire proved otherwise: this relay routinely
    has 5+ overlapping run_cmd_hidden.py processes writing to the SAME shared per-date log
    file, so their launching/exit lines interleave. Measured on 2026-08-21's real log: 3208
    'launching:' lines produced only 1944 completed pairings under the old FIFO-of-1 logic
    (a ~40% loss rate) -- and worse, several of the survivors could have been silently
    mis-attributed to whichever OTHER script's launch happened to be most recent when an
    unrelated exit line landed. run_cmd_hidden.py now tags both lines with its own PID;
    this parser pairs PID-tagged lines by PID (unambiguous under any interleaving) and
    falls back to the original FIFO-of-1 behavior for legacy/pid-less lines (older log
    files, and this file's own test fixtures) so nothing already depending on the old
    format breaks. An unpaired trailing 'launching:' (process still running, launcher
    crashed before logging an exit, or its PID's exit line never lands) is dropped, not
    guessed at -- this only reports COMPLETED, evidenced outcomes."""
    records: list[dict] = []
    pending_cmd: str | None = None
    pending_by_pid: dict[str, str] = {}
    pid_re = re.compile(r"\s*\[pid=(\d+)\]\s*$")
    for line in text.splitlines():
        if "] launching: " in line:
            raw = line.split("] launching: ", 1)[1].strip()
            m = pid_re.search(raw)
            if m:
                pending_by_pid[m.group(1)] = pid_re.sub("", raw).strip()
            else:
                pending_cmd = raw
            continue
        if "exit=" in line:
            m_pid = pid_re.search(line)
            after = line.split("exit=", 1)[1].strip()
            code_str = after.split()[0] if after.split() else after
            try:
                code = int(code_str)
            except ValueError:
                pending_cmd = None
                continue
            if m_pid and m_pid.group(1) in pending_by_pid:
                records.append({"cmd": pending_by_pid.pop(m_pid.group(1)), "exit": code})
            elif pending_cmd is not None:
                records.append({"cmd": pending_cmd, "exit": code})
                pending_cmd = None
    return records


def _run_cmd_hidden_script_label(cmd: str) -> str:
    """Best-effort script name for a launcher-log cmd line, e.g.
    'C:\\...\\pythonw.exe C:\\...\\broker_fills.py --subject all' -> 'broker_fills.py'.
    Picks the FIRST token ending '.py' (never the trailing args) so a task launched
    with extra CLI args (Gamma_FreeModelAudit '--subject all', Gamma_CryptoTwin
    '--live') still labels correctly instead of reporting the last arg as the script."""
    tokens = cmd.split()
    for t in tokens:
        if t.lower().endswith(".py"):
            return Path(t).name
    return Path(tokens[-1]).name if tokens else cmd


def check_run_cmd_hidden_masked_exit(now, log_path=None) -> list[str]:
    """Fleet-wide generalization of the 2026-08-04 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT
    self-audit gap (self-flagged 2026-08-02 AND 2026-08-04 -- OP-25/C7 two-batch
    recurrence = the graduation signal). ~18 Gamma_* tasks (Gamma_BrokerFills,
    Gamma_Confluence, Gamma_SelfAudit, Gamma_Prospector, Gamma_TradeAutopsy,
    Gamma_GuardsNightly, Gamma_OosCheck, Gamma_CryptoTwin, ... see
    setup/scripts/fix-venv-pythonw-console-leak.ps1's $targets) already route through
    wscript -> run_exe_hidden.vbs -> system-pythonw -> run_cmd_hidden.py. The OUTER
    wscript hop is still fire-and-forget (shell.Run cmd, 0, False) so Task Scheduler's
    LastTaskResult can NEVER see these tasks' real outcome -- but run_cmd_hidden.py's
    OWN process already runs the real child SYNCHRONOUSLY and writes the true exit code
    to automation/state/logs/run-cmd-hidden-<date>.log on every single fire. Verified
    live this fire: zero existing consumers of that file (grepped setup/automation/
    backtest). This closes the same class of gap the regime-stamp fix closed for ONE
    script, generalized to every task already on this relay -- using evidence that
    already exists on disk, zero vbs edits, zero blast radius to Gamma_HeartbeatCore
    (not on this relay; covered separately by engine-health.json content-freshness).

    NOT a substitute for the still-open VBS-WRAPPER-EXIT-CODE-BLIND-SPOT queue item
    (the wrapper itself stays fire-and-forget pending its own /fable-blast-radius pass)
    -- this is the low-risk, additive-only half: read what the relay already writes.

    DEGRADED, never BROKEN: every task on this relay today is R&D/telemetry/analysis,
    not the live trading path (rail-2 fail-open discipline). Fail-open: missing/
    unreadable log, or today's log simply not written yet -> [].

    ALLOWLIST -- scripts that exit non-zero BY DESIGN when they find problems, not
    because they crashed. Their signal is already captured via their own JSON output or
    via STATUS.md writes; re-reporting it as a masked-exit alert is redundant noise that
    buries actionable findings. The wscript hop swallows their exit code from Task
    Scheduler's LastTaskResult anyway, so the non-zero exit carries no additional signal.
      unattended_health.py -- exits 1 when verdict=RED; health written to
                              unattended-health.json and FUTURES-HEALTH surfaced separately.
      roster_liveness.py   -- exits 1 when dead lanes found; dead lanes flagged to
                              STATUS.md ## Known broken directly by flag_known_broken()."""
    _NONZERO_BY_DESIGN: frozenset[str] = frozenset({"unattended_health.py", "roster_liveness.py"})
    lp = log_path or (STATE / "logs" / f"run-cmd-hidden-{now.strftime('%Y-%m-%d')}.log")
    if not lp.exists():
        return []
    try:
        text = lp.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    bad = [r for r in _parse_run_cmd_hidden_log(text)
           if r["exit"] != 0 and _run_cmd_hidden_script_label(r["cmd"]) not in _NONZERO_BY_DESIGN]
    if not bad:
        return []
    # One line per distinct failing script (not per-fire) -- a frequent-cadence task
    # failing repeatedly should read as ONE actionable finding, not per-tick spam.
    by_script: dict[str, list[int]] = {}
    for r in bad:
        by_script.setdefault(_run_cmd_hidden_script_label(r["cmd"]), []).append(r["exit"])
    parts = [f"{s} (exit={sorted(set(codes))}, {len(codes)}x)" for s, codes in sorted(by_script.items())]
    return [f"RUN-CMD-HIDDEN MASKED EXIT: {lp.name} shows {len(bad)} real non-zero exit(s) "
            f"Task Scheduler's LastTaskResult can never see (outer wscript hop is still "
            f"fire-and-forget) -- {', '.join(parts)}. Check the named script's own stderr "
            f"log for the real cause."]


def _parse_run_ps1_hidden_log(text: str) -> list[dict]:
    """PURE. Parse run_ps1_hidden.py's own per-fire launcher log (automation/state/logs/
    run-ps1-hidden-<date>.log) into completed [{"name": str, "exit": int}] records.

    Unlike run_cmd_hidden.py's log (which needs launching/exit LINE-ORDER pairing -- see
    _parse_run_cmd_hidden_log, which assumes the NEXT 'exit=' line belongs to the most
    recent 'launching:' line), run_ps1_hidden.py's own exit line embeds the script name
    directly ('  <name>.ps1 exit=<N>'), so every completed record is self-contained on ONE
    line -- no risk of misattributing a completion to the wrong concurrently-launched task.
    This matters here specifically: live inspection of this log (2026-08-06) shows this
    relay routinely has 5+ concurrent 'launching:' lines queued before their matching exits
    land (most Gamma_* tasks route through THIS relay, not run_cmd_hidden.py's), so a
    sequential-pairing parser would silently misattribute outcomes under real load."""
    records: list[dict] = []
    pattern = re.compile(r"\]\s+(\S+\.ps1) exit=(-?\d+)")
    for line in text.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        try:
            code = int(m.group(2))
        except ValueError:
            continue
        records.append({"name": m.group(1), "exit": code})
    return records


def check_run_ps1_hidden_masked_exit(now, log_path=None) -> list[str]:
    """Sibling of check_run_cmd_hidden_masked_exit for the OTHER already-existing
    exit-code-capturing relay: wscript -> run_exe_hidden.vbs -> system-pythonw ->
    run_ps1_hidden.py -> powershell.exe -File <task>.ps1. The MAJORITY of Gamma_* scheduled
    tasks route through THIS relay (not run_cmd_hidden.py's python-direct one) --
    run_ps1_hidden.py has synchronously captured every child .ps1's real exit code to
    automation/state/logs/run-ps1-hidden-<date>.log since its own '5/17 evening foot-gun
    fix', but nothing ever read it back until this check (verified live via grep this fire,
    zero prior consumers -- same C7 shape as the run_cmd_hidden gap, just a much bigger
    blind spot by task count: 108 Gamma_* tasks route through run_exe_hidden.vbs, 24 were
    already covered by check_run_cmd_hidden_masked_exit, this check covers most of the
    remaining ~84).

    LIVE FINDING this fire (2026-08-06 AFTERHOURS conductor, evidence not fixed here):
    run-eod-flatten-aggressive.ps1 exited 1 on 3 of the last 3 available trading days
    (08-03/08-04/08-05, 1x/day); run-eod-flatten.ps1 (Safe) and run-sight-beacon.ps1 each
    exited 1 once on 08-05. Both LLM-prompt-driven EOD-flatten tasks are BACKSTOPPED by the
    deterministic Gamma_EodFlattenCore (eod_flatten.py, handles BOTH accounts independently,
    LastTaskResult=0 every day checked, fires ~3min before the LLM path) -- cross-checked
    against engine-health.json's position_safe/position_bold (GREEN, flat) for the same
    dates, so no position was actually left open. Root-causing WHY Invoke-Claude returns 1
    on the eod-flatten.md prompt is deliberately NOT attempted blind in this fire (OP-0: no
    one-sentence root cause in hand yet) -- filed as a follow-up queue item instead.

    DEGRADED, never BROKEN (rail-2 fail-open discipline; every task on this relay is either
    R&D/telemetry OR has an independent deterministic/fleet-level backstop -- this check is
    visibility-only, same posture as its run_cmd_hidden sibling). Fail-open: missing/
    unreadable log, or today's log not written yet -> []."""
    lp = log_path or (STATE / "logs" / f"run-ps1-hidden-{now.strftime('%Y-%m-%d')}.log")
    if not lp.exists():
        return []
    try:
        text = lp.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    bad = [r for r in _parse_run_ps1_hidden_log(text) if r["exit"] != 0]
    if not bad:
        return []
    by_script: dict[str, list[int]] = {}
    for r in bad:
        by_script.setdefault(r["name"], []).append(r["exit"])
    parts = [f"{s} (exit={sorted(set(codes))}, {len(codes)}x)" for s, codes in sorted(by_script.items())]
    return [f"RUN-PS1-HIDDEN MASKED EXIT: {lp.name} shows {len(bad)} real non-zero exit(s) "
            f"Task Scheduler's LastTaskResult can never see (outer wscript hop is still "
            f"fire-and-forget) -- {', '.join(parts)}. Check the named .ps1's own Invoke-Claude "
            f"budget/timeout, or its underlying script's stderr log."]


def _parse_run_py_venv_hidden_log(text: str) -> list[dict]:
    """PURE. Parse run_py_venv_hidden.py's own per-fire launcher log (automation/state/logs/
    run-py-venv-hidden-<date>.log) into completed [{"name": str, "exit": int}] records.

    This is the THIRD exit-code-capturing relay (built 2026-08-13, "STOP THESE FUCKING CMD
    POPUS" -- window_leak_detector's console-leak fix: system-pythonw + PYTHONPATH onto the
    backtest venv's site-packages, instead of ever invoking the venv's OWN pythonw, which
    allocates a WindowsTerminal -Embedding host on `import pandas`). Like run_ps1_hidden.py's
    log (NOT run_cmd_hidden.py's), each completed record is self-contained on ONE line --
    '[ts] <script>.py exit=<N>' optionally followed by 'args=[...]' -- so no launching/exit
    line-order pairing is needed, and concurrent interleaved fires can't misattribute."""
    records: list[dict] = []
    pattern = re.compile(r"\]\s+(\S+\.py) exit=(-?\d+)")
    for line in text.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        try:
            code = int(m.group(2))
        except ValueError:
            continue
        records.append({"name": m.group(1), "exit": code})
    return records


def check_run_py_venv_hidden_masked_exit(now, log_path=None) -> list[str]:
    """THIRD sibling of check_run_cmd_hidden_masked_exit / check_run_ps1_hidden_masked_exit
    for the newest relay, run_py_venv_hidden.py (built 2026-08-13). At least 12 Gamma_* tasks
    (ChartAutoDraw, EodBrief, EodDojoManifest, GateExpiryCheck, JIntentExecutor,
    LadderRungShadow, MorningBrief, RegimeShadow, RegimeStamp, RiskyDivergenceWeekly,
    ShadowSignalAudit, WinnerAutopsy -- live-enumerated 2026-08-18 via Get-ScheduledTask, not
    guessed) route wscript -> run_exe_hidden.vbs -> system-pythonw -> run_py_venv_hidden.py ->
    <target>.py. The outer wscript hop is still fire-and-forget, so Task Scheduler's
    LastTaskResult can never see these tasks' real outcome -- but run_py_venv_hidden.py's own
    process runs the child SYNCHRONOUSLY and has been logging the true exit code to
    automation/state/logs/run-py-venv-hidden-<date>.log since its own 2026-08-13 birth. Zero
    prior consumers (verified live via grep this fire, same class of gap as the 2026-08-04/
    2026-08-06 fixes for the other two relays -- those tasks were imperatively migrated off
    the OLD backtest-venv-pythonw-direct wiring onto THIS relay sometime after 2026-08-13, but
    nothing was ever built to read what it already writes).

    DEGRADED, never BROKEN (rail-2 fail-open discipline; every task on this relay today is
    R&D/telemetry/analysis/premarket-visibility, not the live trading path -- JIntentExecutor
    is the daemon that DOES route orders, but it is deliberately excluded from any live-wiring
    template rewrite per the VBS-WRAPPER-EXIT-CODE-BLIND-SPOT queue item's own note; this
    check is read-only visibility, not a gate, so including it in the scan is safe). Fail-open:
    missing/unreadable log, or today's log not written yet -> []."""
    lp = log_path or (STATE / "logs" / f"run-py-venv-hidden-{now.strftime('%Y-%m-%d')}.log")
    if not lp.exists():
        return []
    try:
        text = lp.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    bad = [r for r in _parse_run_py_venv_hidden_log(text) if r["exit"] != 0]
    if not bad:
        return []
    by_script: dict[str, list[int]] = {}
    for r in bad:
        by_script.setdefault(r["name"], []).append(r["exit"])
    parts = [f"{s} (exit={sorted(set(codes))}, {len(codes)}x)" for s, codes in sorted(by_script.items())]
    return [f"RUN-PY-VENV-HIDDEN MASKED EXIT: {lp.name} shows {len(bad)} real non-zero exit(s) "
            f"Task Scheduler's LastTaskResult can never see (outer wscript hop is still "
            f"fire-and-forget) -- {', '.join(parts)}. Check the named script's own stderr "
            f"log for the real cause."]


TV_CDP_URL = "http://localhost:9222/json/version"


def _fetch_tv_cdp_reachable(timeout: float = 5.0) -> "tuple[bool, str]":
    """Live liveness probe -- is TradingView's CDP endpoint actually responding on :9222?
    Fail-open -> (False, detail) on ANY error, never raises (rail-2). Ported from (not
    imported -- see check_macro_calendar_freshness's docstring for why this file deliberately
    duplicates rather than imports) preopen_readiness.py's proven fetch_tv_cdp/assess_tv_cdp
    pair (built 2026-07-06 for the exact same D1-audit-flagged gap)."""
    import urllib.request
    try:
        with urllib.request.urlopen(TV_CDP_URL, timeout=timeout) as r:
            if r.status == 200:
                return True, "CDP responding on :9222"
            return False, f"CDP returned HTTP {r.status}"
    except Exception as e:  # noqa: BLE001 -- fail-open, this is a notify-only observer
        return False, f"CDP unreachable on :9222: {type(e).__name__}: {e}"


def check_tv_cdp(now, fetch=None) -> list:
    """VISIBILITY instrument for TradingView's CDP endpoint (D1-TV-CDP-ROOT-CAUSE queue item,
    part 3 -- OVERNIGHT-READ-D1-2026-07-09.md Finding #3). Motivation: TV/CDP went dead for
    41+ hours 2026-07-07/09 (degraded premarket bias to a real 'no-trade-tv-fail' framing that
    waved off a plausible trading day) and NOTHING in self_check.py/STATUS.md ever surfaced
    it -- preopen_readiness.py's assess_tv_cdp/fetch_tv_cdp already existed and already caught
    this class correctly at its own 08:25 ET one-shot fire, but self_check.py (the file J's
    STATUS.md/engine-health.json morning-brief surface actually reads, running every ~30 min)
    had ZERO tv/cdp/9222/TradingView awareness -- confirmed by grep, 12 days after the audit
    flagged it as effort=S. This ports the same live-probe pattern into that surface.

    RED (BROKEN), not DEGRADED: a dead CDP has a real, disclosed trading-relevant cost (the
    07-08 'no-trade-tv-fail' precedent), matching assess_tv_cdp's own 'critical' classification
    -- unlike TRENDLINE-DRAW-freshness, which is explicitly non-load-bearing.

    Windowed 08:10-16:00 ET weekdays only: Gamma_LaunchTV fires once at 08:00 ET and
    Gamma_TvWatchdog every 5 min 08:05-16:00 ET -- the window gives the 08:00 launch a few
    minutes of slack before judging it dead, and there is no TV-up expectation
    overnight/weekends (matches this file's own rth-gated staleness checks)."""
    if now.weekday() >= 5:
        return []
    hm = now.strftime("%H:%M")
    if hm < "08:10" or hm > "16:00":
        return []
    probe = fetch or _fetch_tv_cdp_reachable
    reachable, detail = probe()
    if reachable:
        return []
    return [f"TV-CDP UNREACHABLE (RED): {detail} -- TradingView's CDP endpoint is not "
            f"responding. Premarket bias generation and named-level chart context may be "
            f"degraded (2026-07-07/09 precedent: a 41+h outage produced a real "
            f"'no-trade-tv-fail' framing, unsurfaced here the whole time). Gamma_LaunchTV "
            f"(08:00 ET) / Gamma_TvWatchdog (5min) should self-heal within a cycle; if this "
            f"persists, manually `taskkill /F /IM TradingView.exe` then run "
            f"`setup\\launch_tv_debug.ps1` by hand."]


CANDIDATES_UNTRACKED_THRESHOLD = 20


def check_candidates_untracked_backlog(run_git=None) -> list:
    """VISIBILITY instrument for the STRATEGY-CANDIDATES-UNTRACKED-BACKFILL scar
    (2026-07-22): 1,176 files under strategy/candidates/ -- live chef/kitchen/prospector
    pipeline state, not gitignored -- had silently accumulated with ZERO commit history
    (no recovery path on disk loss) until a one-time backfill commit. The lesson's own
    fix explicitly named a graduated guard as part (3): 'a cheap periodic check flagging
    strategy/candidates/ untracked-count above a small threshold (>20) so this can't
    silently re-accumulate unnoticed' (C7 -- silent success is failure).

    DEGRADED, never BROKEN: an untracked-file backlog has zero trading-relevant impact
    (it cannot block/misinform a live decision) -- it is a version-control hygiene risk,
    not an engine-tradeability one. $0, fail-open: any git-invocation error returns []
    rather than raising (rail-2 -- this must never be able to interrupt the scheduler)."""
    import subprocess
    # OP-27 L41: bare subprocess.run from headless pythonw flashes a conhost window on
    # Win11 -- and this observer runs every ~7 min, straight into J's face. Flagged RED by
    # audit_window_leak_compliance since at least 2026-07-29T13:48Z; drained 2026-07-29.
    _CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
    probe = run_git or (lambda: subprocess.run(
        ["git", "status", "--porcelain=v1", "--", "strategy/candidates/"],
        cwd=str(REPO), capture_output=True, text=True, timeout=15,
        creationflags=_CREATE_NO_WINDOW))
    try:
        proc = probe()
        lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("??")]
    except Exception:  # noqa: BLE001 -- fail-open, this is a notify-only observer
        return []
    n = len(lines)
    if n <= CANDIDATES_UNTRACKED_THRESHOLD:
        return []
    return [f"CANDIDATES-UNTRACKED: {n} untracked files under strategy/candidates/ "
            f"(threshold {CANDIDATES_UNTRACKED_THRESHOLD}) -- live chef/kitchen/prospector "
            f"pipeline state accumulating with no commit history / no disk-loss recovery "
            f"path. Batch `git add --pathspec-from-file` + commit to clear (see "
            f"STRATEGY-CANDIDATES-UNTRACKED-BACKFILL precedent, 2026-07-22)."]


def check_participation_daily(now, path=None) -> list:
    """GOAL-LAYER reader for participation_daily.py's own automation/state/participation-daily.json
    (Gamma_ParticipationDaily, 16:10 ET weekdays -- per-account safe/bold fills-vs-target
    verdict). Wires that standing instrument into self_check's DEGRADED/BROKEN pipeline the
    same way check_fill_funnel already does -- participation_cascade.py's own module docstring
    names exactly this hookup as the intended next step (PARTICIPATION-DAILY-SELF-CHECK-WIRE,
    filed off the same instrument). Until this landed, a real participation hole only ever
    reached J via participation_daily's own de-duped discord-outbox line -- never STATUS.md's
    '## Known broken' surface or engine-health.json.

    RED -> BROKEN: a CONFIRMED participation hole (an account formed >= RED_ENTER_VERDICT_FLOOR
    ENTER verdicts today and filled ZERO -- participation_daily.account_verdict's own predicate,
    not re-derived here). YELLOW -> DEGRADED (fills below the account's own daily-min target,
    but not zero). IDLE (nothing scored all day -- holiday/feed-down, never itself a fault) and
    GREEN (target met) are silent.

    STALENESS: the artifact only refreshes once/day at 16:10 ET, so its `date` field lags
    "today" for the entire session -- judged (missing-or-stale -> BROKEN) only after 16:20 ET
    on a weekday, mirroring check_dress_rehearsal's evening-only staleness window. Before that,
    or on a not-yet-written day, this is silent (nothing to judge yet). Fail-open: any
    read/parse error outside the weekday-evening window returns []."""
    p = path or (STATE / "participation-daily.json")
    weekday_evening = now.weekday() < 5 and now.strftime("%H:%M") >= "16:20"
    today = now.strftime("%Y-%m-%d")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        if weekday_evening:
            return ["PARTICIPATION-DAILY MISSING (RED): no goal-layer artifact on a weekday "
                    "evening -- Gamma_ParticipationDaily may not be firing. Run "
                    "setup/scripts/participation_daily.py."]
        return []
    if d.get("date") != today:
        if weekday_evening:
            return [f"PARTICIPATION-DAILY STALE (RED): last goal-layer check is dated "
                    f"{d.get('date')}, not today {today} -- Gamma_ParticipationDaily likely "
                    f"did not fire."]
        return []  # not yet run for today -- no verdict to judge
    verdict = d.get("verdict")
    accounts = d.get("accounts") or {}
    if verdict == "RED":
        parts = [f"{acc}={a.get('fills')}/{a.get('target_min')}-{a.get('target_max')} "
                 f"[{a.get('verdict')}]" for acc, a in accounts.items()]
        return [f"PARTICIPATION RED: confirmed goal-layer hole today -- " + " ".join(parts) +
                f" -- see analysis/participation-cascade/{today}.md for the top blockers."]
    if verdict == "YELLOW":
        parts = [f"{acc}={a.get('fills')}/{a.get('target_min')}-{a.get('target_max')}"
                 for acc, a in accounts.items() if a.get("verdict") == "YELLOW"]
        return [f"PARTICIPATION DEGRADED (YELLOW): below daily-min target -- " + " ".join(parts)]
    return []


QUOTE_RECORDER_STATUS = STATE / "quote-recorder-status.json"


def check_quote_recorder_alive(now, status_path=None) -> list[str]:
    """DAILY liveness check for quote_recorder.py's own independent exit-quote side-channel
    (Task B1, built 2026-08-28 -- 'we log NBBO on ~25 of 128 entry events and ZERO on exits;
    every slippage number in every analysis is therefore an ASSUMPTION'). Reads ONLY the
    recorder's own status file (automation/state/quote-recorder-status.json) -- nothing on
    the trading path writes or reads that file, so this check can never see a false read.

    SILENT UNTIL DEPLOYED: a status file that has NEVER been written means the recorder's
    scheduled task has not been registered yet (B1 proposed the wiring -- wscript ->
    run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py -> pythonw ->
    quote_recorder.py --loop, matching the ccr_keepalive/window-leak-detector daemon
    pattern -- but did not register it; arming a new always-on scheduled task is J's call).
    That is a "not yet turned on" state, not a fault, so it stays silent -- the moment the
    file exists for the first time (the daemon's own first real cycle), this check starts
    holding it to account.

    RED (BROKEN): the status file EXISTED (proving the daemon ran at least once) and has now
    gone stale past any plausible cadence (idle=60s, active=20s, off-hours-skip=300s, +buffer)
    -- the process died. Zero exit-quote evidence accumulates while this is red, directly
    starving the exact slippage-measurement gap this instrument exists to close.

    DEGRADED: the daemon is alive (fresh status writes) but failing most of its cycles (a bad
    key, a broker outage, a dead symbol) -- producing status, but not producing rows."""
    sp = status_path or QUOTE_RECORDER_STATUS
    if not sp.exists():
        return []  # never deployed yet -- see SILENT UNTIL DEPLOYED above
    age = _age_min(sp)
    if age is not None and age > 8:
        return [f"QUOTE-RECORDER RED: status file {age:.0f}m stale (cadence is <=60s idle / "
                f"<=20s active / <=5m off-hours) -- Gamma_QuoteRecorder has stopped. Zero "
                f"exit-side NBBO is being captured; every slippage number stays an assumption "
                f"until this is relaunched (setup/scripts/quote_recorder.py --loop)."]
    try:
        d = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return [f"QUOTE-RECORDER DEGRADED: status file unreadable/corrupt at {sp}."]
    fails = d.get("consecutive_cycle_failures", 0) or 0
    if isinstance(fails, (int, float)) and fails >= 5:
        return [f"QUOTE-RECORDER DEGRADED: {int(fails)} consecutive cycle failures "
                f"(last_error={d.get('last_cycle_errors')}) -- process alive, data gap growing."]
    return []


def _problem_is_broken(p: str) -> bool:
    """BROKEN (vs DEGRADED) classifier for a problem string. Module-level so the
    graduated guards can assert the mapping (e.g. PLACEMENT BROKEN -> BROKEN)."""
    return (("crash" in p.lower()) or ("RED" in p) or ("STALE/REVOKED" in p)
            or ("KEY MISSING" in p) or ("CANNOT ENTER" in p)
            or ("CONTRADICTORY ROLES" in p) or ("PLACEMENT BROKEN" in p))


_AUTH_OUTAGE_SIGNATURES = ("Not logged in", "Please run /login")


def check_llm_auth_outage(now, logs_dir=None, lookback_days: int = 7) -> list[str]:
    """THE SINGLE-CAUSE, J-ONLY-FIXABLE OUTAGE. Built 2026-08-15 after finding the entire
    autonomous conductor dead for five days with nobody told.

    WHY THIS IS NOT A DUPLICATE of check_run_ps1_hidden_masked_exit: that sibling correctly
    reported `run-conductor-weekend.ps1 (exit=[1], 5x)` -- a GENERIC non-zero exit, sitting in
    a list next to unrelated exit=1 noise, with the advice "check the named .ps1's own log".
    It cannot say WHY, cannot say the whole LLM fleet shares one cause, and cannot say that no
    amount of automated self-healing will ever fix it. This check reads one level deeper and
    names the condition.

    THE MECHANISM: every LLM-driven task spawns `claude`, which answers
    "Not logged in - Please run /login" and returns 1. Rail-0's budget precheck says PROCEED
    (it measures spend, and a login failure spends $0), so the fire burns its slot and exits.
    Task Scheduler shows LastTaskResult=0 because the outer wscript hop is fire-and-forget.
    Every layer reports success except the work.

    MEASURED AT BUILD TIME: 49 failed fires across 8 distinct tasks from 2026-08-11, 100% of
    conductor fires from 08-12 on. The rig did not visibly break because the deterministic
    backstops held -- eod_flatten.py covered the LLM EOD-flatten path and
    premarket_deterministic_fallback.py covered premarket -- which is exactly the danger: a
    backstop silently carrying production is indistinguishable from a healthy primary until
    the backstop is the thing that fails.

    ONLY J CAN CLEAR IT: `claude /login` is interactive OAuth. This check therefore reports a
    J-ACTION, not a self-heal target -- no automation should retry into it.

    Fail-open (missing/unreadable logs -> []); read-only; $0.
    """
    d = logs_dir or (STATE / "logs")
    try:
        if not d.exists():
            return []
        log_files = sorted(d.glob("*.log"))
    except Exception:  # noqa: BLE001 -- an observer never raises
        return []

    cutoff = (now.date() - dt.timedelta(days=lookback_days)).isoformat()
    per_task: dict[str, int] = {}
    days: set[str] = set()
    newest_fail = ""
    newest_ok = ""
    for f in log_files:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        day = m.group(1) if m else None
        if day is None or day < cutoff:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        # RECOVERY EVIDENCE: a clean `exit=0` LLM fire proves auth works again. Tracked per
        # log file so the alarm can go green on PROOF rather than on a timer.
        if "=== END tick exit=0 ===" in text:
            newest_ok = max(newest_ok, day)
        # One fire logs both signature strings on one line; count LINES, not substrings.
        hits = sum(1 for ln in text.splitlines()
                   if any(s in ln for s in _AUTH_OUTAGE_SIGNATURES))
        if not hits:
            continue
        task = re.sub(r"-?\d{4}-\d{2}-\d{2}.*$", "", f.name) or f.name
        per_task[task] = per_task.get(task, 0) + hits
        days.add(day)
        newest_fail = max(newest_fail, day)

    if not per_task:
        return []

    # CLEARED. An LLM fire has succeeded on or after the newest failure day, so the login was
    # restored. Without this the alarm keeps firing for the whole lookback after the fix --
    # an alarm that cannot go green is one people learn to ignore, which is the exact failure
    # this check was built to end. (Deliberately keyed on a SUCCESSFUL FIRE, not on elapsed
    # time: a weekend has no fires at all, and silence is not recovery.)
    if newest_ok and newest_ok >= newest_fail:
        return []
    total = sum(per_task.values())
    named = ", ".join(f"{t} ({n}x)" for t, n in sorted(per_task.items(), key=lambda kv: -kv[1]))
    span = f"{min(days)}..{max(days)}" if days else "?"
    return [
        f"BROKEN -- CLAUDE CLI IS LOGGED OUT: {total} LLM fire(s) across {len(per_task)} task(s) "
        f"died on 'Not logged in / Please run /login' over {span}. Affected: {named}. "
        f"Rail-0 budget says PROCEED (a logged-out fire spends $0) and Task Scheduler shows "
        f"LastTaskResult=0 (fire-and-forget wscript hop), so every layer reports success "
        f"except the work. The autonomous loop is NOT running. "
        f"J ACTION REQUIRED: run `claude /login` -- this is interactive OAuth, no automation "
        f"can clear it and nothing should retry into it."
    ]


FUTURES_HEALTH_JSON = STATE / "futures" / "health.json"
TASK_STALENESS_JSON = STATE / "scheduled-task-staleness.json"


def check_futures_health(now, path=None) -> list[str]:
    """Fold futures_health.py's own verdict into the ONE health surface (2026-08-29 go-live
    audit gap: this file had ZERO futures awareness before this check, so a multi-week
    futures-lane outage could never reach STATUS.md/Discord no matter how loud
    futures_health.py itself was).

    DO NOT RECOMPUTE the futures logic here -- read the artifact futures_health.py already
    wrote (its own docstring carries the full mechanism: ghost pending_entry deadlock,
    ENTER_REFUSED patterns, broker-transport error rate, data freshness, task liveness).
    This is a thin passthrough, same shape as check_llm_auth_outage/check_quote_recorder_alive.

    SILENT UNTIL DEPLOYED: a missing/unreadable health.json means futures_health.py has not
    fired yet (or was deleted) -- that is a "not yet turned on" state, not a fault, so it
    stays silent (fail-open). A top-level UNKNOWN never happens (futures_health.py's own
    contract guarantees GREEN/YELLOW/RED only) but is treated the same way defensively --
    per the task spec, a futures UNKNOWN must NEVER turn an otherwise-GREEN self_check RED.

    RED -> a problem string containing the substring "RED" (matches _problem_is_broken,
    same convention as the existing `engine-health RED: ...` problem in run() item 3) so a
    genuine futures-lane outage classifies BROKEN, not just DEGRADED.
    YELLOW -> DEGRADED-only (never contains "RED"), so a soft futures issue can never spuriously
    escalate self_check's own verdict past DEGRADED.
    GREEN -> silent, no problem appended."""
    p = path or FUTURES_HEALTH_JSON
    if not p.exists():
        return []  # never deployed / not yet fired -- see SILENT UNTIL DEPLOYED above
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- an unreadable artifact is a fail-open no-op, not a crash
        return []
    if not isinstance(data, dict):
        return []
    verdict = data.get("verdict")
    reasons = data.get("reasons") or []
    reason_str = "; ".join(str(r) for r in reasons[:4]) or "(no reasons listed)"
    if verdict == "RED":
        return [f"FUTURES-HEALTH RED: futures lane cannot be trusted to trade -- {reason_str}"]
    if verdict == "YELLOW":
        return [f"FUTURES-HEALTH DEGRADED: {reason_str}"]
    # GREEN, or an unrecognized/missing verdict field (defensive: never a problem) -> silent
    return []


def check_task_staleness(now, path=None) -> list[str]:
    """Fold scheduled_task_staleness.py's own verdict into the ONE health surface.

    THE GAP (2026-09-02): Gamma_GuardsFull -- the ~11,400-test regression suite -- was dark
    from 08-31 to 09-02 and NOTHING here noticed, because every scheduled-task awareness in
    this file (and in task_state_guard.py) reads State + LastTaskResult. Neither field moves
    when a task simply never starts. The witnesses are LastRunTime and NumberOfMissedRuns,
    which nothing read until scheduled_task_staleness.py.

    DO NOT RECOMPUTE the staleness logic here -- read the artifact that script already
    wrote (its docstring carries the mechanism: quiet mode's presence hold skips triggers,
    and StartWhenAvailable cannot recover a fire missed while the task was Disabled). Thin
    passthrough, same shape as check_futures_health.

    SILENT UNTIL DEPLOYED: a missing/unreadable artifact means Gamma_TaskStaleness has not
    fired yet -- "not yet turned on", not a fault -- so it stays silent (fail-open).

    RED   -> a problem containing "RED" (matches _problem_is_broken) so genuinely dark
             scheduled work classifies BROKEN, same convention as `engine-health RED: ...`.
    YELLOW/UNKNOWN -> DEGRADED-only. UNKNOWN is surfaced rather than swallowed (an
             unreadable scheduler is not a healthy one) but must never escalate past
             DEGRADED on its own, or a transient PowerShell hiccup would spuriously break
             the whole self-check.
    GREEN -> silent.
    """
    p = path or TASK_STALENESS_JSON
    if not p.exists():
        return []  # never deployed / not yet fired -- see SILENT UNTIL DEPLOYED above
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- an unreadable artifact is a fail-open no-op
        return []
    if not isinstance(data, dict):
        return []
    verdict = data.get("verdict")
    findings = data.get("findings") or []
    # Name ONLY the findings whose own verdict matches the headline. Two constraints collide
    # here and this is the shape that satisfies both:
    #   * _problem_is_broken matches the SUBSTRING "RED", so a finding's own verdict can
    #     never be interpolated ("Gamma_X(RED)") -- that made every YELLOW/UNKNOWN message
    #     classify BROKEN, contradicting the DEGRADED-only contract (caught 2026-09-02 by
    #     probing all four verdicts instead of only the happy path).
    #   * but naming the top-5 findings REGARDLESS of severity under a headline that states
    #     the OVERALL verdict reads as though every task listed is at that severity. Live
    #     example the same morning: Gamma_DeadMansSwitch is UNKNOWN ("never run, next fire
    #     09:32 ET, expected for a freshly registered task") and was being listed inside a
    #     "TASK-STALENESS RED" line. Mislabelling a healthy task as RED is the cry-wolf
    #     pattern this whole instrument exists to avoid.
    # So: filter by severity, interpolate no verdict strings.
    def _named(*severities: str) -> str:
        hits = [str(f.get("name")) for f in findings
                if isinstance(f, dict) and f.get("name") and f.get("verdict") in severities]
        return ", ".join(hits[:5]) or "(no tasks named)"

    if verdict == "RED":
        return [f"TASK-STALENESS RED: scheduled work is not running -- {_named('RED')}"]
    if verdict in ("YELLOW", "UNKNOWN"):
        return [f"TASK-STALENESS DEGRADED ({verdict}): {_named('YELLOW', 'UNKNOWN')}"]
    return []


def check_live_watch_field_completeness(now, path=None) -> list[str]:
    """LIVE-WATCH FIELD COMPLETENESS -- self-audit gap batch 2026-08-30 item 7
    ("Live watch lacks enforcement of REQUIRED_POSITION_FIELDS completeness"). The
    2026-08-01 build proved the field-population promise only on a SYNTHETIC position
    (--dry-run-synthetic); the 2026-09-01 05:38 ET archive build (live-watch-archive.jsonl)
    records REQUIRED_POSITION_FIELDS for every real in-trade tick but never ALERTS when one
    comes back null -- so a real degraded field (e.g. a broker quote outage collapsing
    `mid`/`dist_to_stop_pct` to None) could sit silently in the archive forever. This closes
    that live-enforcement gap without recomputing anything: reads the CURRENT production
    live-watch.json tick (thin passthrough, same shape as check_futures_health), and for
    every arm with in_trade=True flags any REQUIRED_POSITION_FIELDS value that is None.

    DEGRADED only -- a visibility gap on a real position is worth a loud flag, but this is
    WS7's own documented contract (VISIBILITY ONLY, places no order, touches no exit rule),
    so it must never classify BROKEN (see _problem_is_broken; no BROKEN-keyword substring
    used here on purpose). Fail-open: a missing/unreadable file, or live_watch's own
    REQUIRED_POSITION_FIELDS import failing, returns [] -- freshness/liveness of the
    live-watch.json tick itself is owned by check_live_watch_liveness (self-audit gap batch
    2026-09-01 item 6) below, NOT by engine-health.json as this docstring previously claimed:
    grepped engine_health.py and dead_mans_switch.py on 2026-09-05, zero live_watch
    references in either -- the writer had NO dead-man switch anywhere until that check
    shipped."""
    p = path or (STATE / "live-watch.json")
    try:
        snap = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(snap, dict):
        return []
    try:
        from live_watch import REQUIRED_POSITION_FIELDS as _FIELDS
    except Exception:  # noqa: BLE001
        return []
    out: list[str] = []
    for arm_id, a in (snap.get("arms") or {}).items():
        if not isinstance(a, dict) or not a.get("in_trade"):
            continue
        pos = a.get("position")
        if not isinstance(pos, dict):
            continue
        missing = [k for k in _FIELDS if pos.get(k) is None]
        if missing:
            out.append(f"LIVE-WATCH INCOMPLETE ({arm_id}): {missing} null on a real "
                       f"in-trade position -- WS7 completeness promise unenforced.")
    return out


def check_live_watch_liveness(now, path=None) -> list[str]:
    """LIVE-WATCH WRITER LIVENESS -- self-audit gap batch 2026-09-01 item 6 ("Live-watch
    writer has no dead-man switch ... if a real position is open and the writer dies,
    nothing alerts") + the swarm's failure-mode #1 on the same batch ("the guard reads
    stale state ... reports GREEN. The position is now blind but the audit says it's fine").

    VERIFIED gap, not assumed: check_live_watch_field_completeness's own docstring (until
    this fire) claimed live-watch.json freshness was "owned by other surfaces
    (engine-health.json)". Grepped setup/scripts/engine_health.py and dead_mans_switch.py --
    ZERO live_watch references in either. Nothing anywhere checked whether Gamma_LiveWatch
    (cadence ~1/min, 09:25-16:10 ET) was still alive; a dead writer freezes live-watch.json
    at its last tick forever, and check_live_watch_field_completeness happily reports clean
    fields off that frozen snapshot with no disclosure that the snapshot itself stopped
    moving.

    RTH-gated with the window's own 3-minute startup slack (mirrors check_dress_rehearsal /
    check_engine_tradeability's existing pattern -- give the 09:25 first-tick its own grace
    before judging staleness). Threshold 4 minutes: the writer's cadence is <=60s, so 4
    consecutive missed ticks is unambiguous death, not scheduler jitter (proportionally
    tighter than QUOTE-RECORDER's 8m vs a <=60s cadence, because live-watch is the ONLY
    surface watching real in-trade positions tick-by-tick). RED (BROKEN, matches the
    QUOTE-RECORDER RED precedent in _problem_is_broken): a dead in-trade watcher during RTH
    is a real visibility outage, not a data-quality nuance. Fail-open: outside the RTH
    window, or the file simply not yet existing this session (pre-09:25), returns []."""
    if now.weekday() >= 5:
        return []
    hm = now.strftime("%H:%M")
    if hm < "09:28" or hm > "16:10":
        return []  # give the 09:25 first tick its own slack; window matches Gamma_LiveWatch
    p = path or (STATE / "live-watch.json")
    if not p.exists():
        return [f"LIVE-WATCH WRITER RED: {p.name} does not exist during RTH ({hm} ET) -- "
                f"Gamma_LiveWatch has never ticked today. No in-trade position is being "
                f"watched."]
    age = _age_min(p)
    if age is not None and age > 4:
        return [f"LIVE-WATCH WRITER RED: {p.name} is {age:.0f}m stale during RTH (cadence "
                f"is ~1/min, 09:25-16:10 ET) -- Gamma_LiveWatch has stopped. Every consumer "
                f"(WS7 field-completeness check, any in-trade dashboard) is now reading a "
                f"frozen snapshot with no disclosure. Relaunch Gamma_LiveWatch."]
    return []


def run() -> dict:
    now = et_now(); hm = now.strftime("%H:%M")
    rth = ("09:30" <= hm <= "15:55") and now.weekday() < 5
    problems = []

    # 1. em-dash / encoding class
    bad_ps1 = check_ps1_encoding()
    if bad_ps1:
        problems.append(f"ENCODING (silent-crash risk): {len(bad_ps1)} run-*.ps1 are non-ASCII without a BOM -> PS 5.1 parse-crashes them (exit-0, no output). Files: {bad_ps1[:6]}")

    # 2. stale autonomy output during the window it should be producing
    if rth:
        kl_age = _age_min(STATE / "key-levels.json")
        if kl_age is not None and kl_age > 12:
            problems.append(f"Gamma_LevelRefresh STALE in RTH: key-levels.json {kl_age:.0f}m old (should be <10m). Engine may be blind to live structure.")
        b_age = _age_min(STATE / "sight-beacon.json")
        if b_age is not None and b_age > 6:
            problems.append(f"Gamma_SightBeacon STALE in RTH: beacon {b_age:.0f}m old (should be <2m). Engine eye may be dark.")
        # heartbeat decisions recent?
        dec = STATE / "core-decisions.jsonl"
        d_age = _age_min(dec)
        if d_age is not None and d_age > 5:
            problems.append(f"Gamma_HeartbeatCore STALE in RTH: last decision {d_age:.0f}m ago (should be ~1m). Engine may not be ticking.")

    # 3. live-chain health
    h = json.loads((STATE / "engine-health.json").read_text(encoding="utf-8")) if (STATE / "engine-health.json").exists() else {}
    if h.get("verdict") == "RED":
        problems.append(f"engine-health RED: reds={h.get('reds')}")

    # 4. broker key / account health (the 401-stale-key class)
    problems.extend(check_broker_keys())

    # 4b. STANDING DAILY RECONCILIATION (TASK B3, 2026-08-28) -- ledger P&L vs real broker
    # equity change, all 5 arms, once per ET day. RED here means the ledger a go-live
    # decision would rest on cannot be trusted against the broker's own numbers.
    problems.extend(check_broker_reconciliation(now))

    # 5. premarket bias freshness -- catches Gamma_Premarket silent-failure (06-30: the LLM task
    # fired 08:30 ET, exited 0, but wrote NO bias; today-bias sat stale-dated until caught by hand).
    if now.weekday() < 5 and hm >= "08:35":
        try:
            tb = json.loads((STATE / "today-bias.json").read_text(encoding="utf-8"))
            if tb.get("date") != now.strftime("%Y-%m-%d"):
                problems.append(f"PREMARKET STALE: today-bias.json date={tb.get('date')} != today {now.strftime('%Y-%m-%d')} -- Gamma_Premarket likely silent-failed (exit-0, no write). Engine opening on a stale bias.")
            elif tb.get("degraded") is True and tb.get("source") == "deterministic_fallback":
                # A5 (2026-07-14): date IS fresh, but the LLM step failed and
                # premarket_deterministic_fallback.py covered for it -- distinct from
                # both PREMARKET STALE (date not fresh at all) and a real VERIFIED LLM
                # pass (per the reliability-audit spec's "distinguish stale from
                # degraded-fresh" ask). Informational only -- date IS fresh, engine is
                # NOT blind, so this must never classify as BROKEN (no BROKEN-keyword
                # substring here; see _problem_is_broken).
                problems.append(f"PREMARKET DEGRADED: today-bias.json is fresh-dated but LLM-authored narrative failed this morning -- running on the deterministic fallback's mechanical bias only (no chart/ribbon/trendline read, zero falsifiable_predictions).")
        except Exception:  # noqa: BLE001
            pass

    # 6. ENGINE TRADEABILITY (content, not mtime) -- the 2026-06-30 disease: GREEN while 0 ENTER all day
    problems.extend(check_engine_tradeability(now))

    # 7. KEY-LEVELS INTEGRITY (content) -- contradictory ceiling/floor roles fed to the engine
    problems.extend(check_level_integrity())

    # 8. FILL FUNNEL (content) -- placement broken / late ENTER / fill-without-exit
    problems.extend(check_fill_funnel(now))

    # 8b. PARTICIPATION-DAILY GOAL LAYER (content) -- per-account fills-vs-target verdict
    # (participation_daily.py, 16:10 ET). RED = confirmed hole; YELLOW = below target.
    problems.extend(check_participation_daily(now))

    # 9. NIGHTLY DRESS REHEARSAL (real broker boundary) -- "are we good for tomorrow" reader
    problems.extend(check_dress_rehearsal(now))

    # 10. loop-state tick truth -- keep the legacy artifact honest for its readers
    # (dashboard, companion, EOD prompts). Fail-open; a failure is a note, not a raise.
    try:
        import loop_state_refresh
        loop_state_refresh.refresh(now)
    except Exception:  # noqa: BLE001
        pass

    # 11. PDT (Rule 7) VISIBILITY -- the 2026-07-13 scar: core Safe was silently
    # PDT-blocked all day on an INHERITED day-trade count and nobody knew until a manual
    # review found it. pdt_summary is ALWAYS recorded (blocked or not) for firm_brief.py's
    # account section; problems only grows on an ACTUAL block (DEGRADED, never BROKEN).
    pdt_problems, pdt_summary = check_pdt_status(now)
    problems.extend(pdt_problems)

    # 12. MACRO-CALENDAR FRESHNESS -- the 2026-07-15 scar: Gamma_MacroCalendar missed its
    # 07:45 ET fire (overnight reboot ate the interactive-logon session) and nothing surfaced
    # it to STATUS.md/Discord (context_bundle_producer's calendar_stale flag is LOGGED ONLY).
    # Standing instrument now, so a future miss (any cause) can't rot silently either.
    problems.extend(check_macro_calendar_freshness(now))

    # 12a. WEEKLY-1 EARNINGS-CALENDAR FRESHNESS -- same shape/severity as #12, for the
    # weekly-options lane's earnings-blackout feed (setup/scripts/earnings_calendar.py).
    # A stale/missing feed means single-name entries can't be verified against an
    # earnings print -- the lane's single worst new IV-crush failure mode.
    problems.extend(check_earnings_calendar_freshness(now))

    # 12b. PRIOR-TRADING-DAY DARK -- the 2026-07-24 scar: unlike every other check above
    # (scoped to "today"), this looks BACKWARD at the most recently completed trading day so
    # a fully-dark engine day can't self-heal invisibly over a weekend before J sees it.
    problems.extend(check_prior_trading_day_dark(now))

    # 13. TRENDLINE-DRAW FRESHNESS -- the 2026-07-16/17 scar: 2 budget-skips of premarket
    # Step 5c in 2 days went to journal only, invisible to J until he noticed a bare chart.
    problems.extend(check_trendline_draw_freshness(now))
    problems.extend(check_trendline_feed_freshness(now))  # D9 liveness (2026-08-06)

    # 13a. CHART-DRAWING (Step 5 wipe+redraw) FRESHNESS -- sibling gap to 13's Step 5c: the
    # chart_drawing_summary.as_of stamp sat 2 MONTHS stale (2026-06-29) with zero alarm.
    problems.extend(check_chart_wipe_redraw_freshness(now))

    # 13b. REGIME-STAMP DRIFT -- the 2026-08-02/08-03 self-audit recurrence: only
    # monday_verify.py's WS6 check verified the Gamma_RegimeStamp -> Gamma_Premarket
    # handoff, and only once a week. This closes the Tue-Fri gap ($0, fail-open, DEGRADED).
    problems.extend(check_regime_stamp_daily(now))

    # 13c. SCOUT PREMARKET FRESHNESS -- the 2026-08-06 self-audit gap: the LLM-agent-driven
    # Gamma_ScoutPremarket task can report LastTaskResult=0 without actually regenerating
    # scout_output.json (scout-log.jsonl shows a full silent month, 06-19..07-21). Nothing
    # verified the CONSUMED ARTIFACT until now ($0, fail-open, DEGRADED-only).
    problems.extend(check_scout_premarket_fresh(now))

    # 14. TV-CDP LIVENESS -- the 2026-07-07/09 scar (D1 audit Finding #1/#3): a 41+ hour
    # TradingView CDP outage degraded premarket bias to real 'no-trade-tv-fail' framing and
    # NOTHING in this file ever saw it. preopen_readiness.py caught this class at its own
    # one-shot 08:25 ET fire; this closes the same gap on the surface J's morning brief reads.
    problems.extend(check_tv_cdp(now))

    # 15. CANDIDATES-UNTRACKED BACKLOG -- the 2026-07-22 scar: 1,176 strategy/candidates/
    # files accumulated with zero commit history before a one-time backfill. Guards against
    # silent re-accumulation (C7); DEGRADED-only, checked every self_check cadence ($0, fail-open).
    problems.extend(check_candidates_untracked_backlog())

    # 16. RUN-CMD-HIDDEN MASKED EXIT -- the 2026-08-04 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT
    # self-audit gap, generalized: read the real per-fire exit codes run_cmd_hidden.py
    # already logs for every task on its relay chain, since Task Scheduler's
    # LastTaskResult structurally cannot see them (fire-and-forget outer wscript hop).
    problems.extend(check_run_cmd_hidden_masked_exit(now))

    # 17. RUN-PS1-HIDDEN MASKED EXIT -- sibling of #16 for the OTHER exit-code-capturing
    # relay (run_ps1_hidden.py), which carries the MAJORITY of Gamma_* scheduled tasks.
    # Same VBS-WRAPPER-EXIT-CODE-BLIND-SPOT self-audit gap, much bigger surface.
    problems.extend(check_run_ps1_hidden_masked_exit(now))

    # 17b. RUN-PY-VENV-HIDDEN MASKED EXIT -- third sibling of #16/#17, for the newest
    # (2026-08-13) console-leak-safe relay. Same VBS-WRAPPER-EXIT-CODE-BLIND-SPOT self-audit
    # gap; these ~12 tasks were imperatively migrated onto it after birth but never got a
    # consumer for the exit-code log it already writes.
    problems.extend(check_run_py_venv_hidden_masked_exit(now))
    # The DIAGNOSIS layer on top of the two masked-exit checks above. They report THAT a
    # fire exited non-zero; this reports the one cause that (a) hits the whole LLM fleet at
    # once, (b) makes rail-0 read PROCEED because it spends $0, and (c) no automation can
    # ever clear. Runs after them so its named verdict lands next to the generic evidence.
    problems.extend(check_llm_auth_outage(now))

    # 18. SELF-AUDIT ORGAN ALIVE -- the 2026-08-11 finding: self_audit.py's own outer
    # subprocess timeout (300s) was smaller than swarm_consult.py's worst-case internal
    # budget (540s), silently killing 2 consecutive full audits (08-09/08-10) with exit-0.
    # Watches the dedup ledger (gap-log.jsonl) directly so a future recurrence surfaces
    # within a day instead of a month.
    problems.extend(check_self_audit_organ_alive(now))

    # 19. QUOTE-RECORDER ALIVE -- Task B1 (2026-08-28): the independent exit-quote
    # side-channel that closes the "zero exit NBBO logged, every slippage number is an
    # assumption" gap. Silent until first deployed (see the check's own docstring); once a
    # status file exists, holds the daemon to its own <=60s/20s cadence.
    problems.extend(check_quote_recorder_alive(now))

    # 20. FUTURES-LANE HEALTH -- 2026-08-29 go-live audit gap: this file had ZERO futures
    # awareness before this line (a multi-week fillsim ghost-order deadlock and a multi-week
    # tastytrade-broker ReadTimeout outage both went undetected on every existing surface).
    # Thin passthrough of futures_health.py's own verdict -- never recomputed here. Silent
    # until futures_health.py has fired at least once; a futures UNKNOWN/missing artifact
    # never turns an otherwise-GREEN self_check RED (see the check's own docstring).
    problems.extend(check_futures_health(now))

    # 21. LIVE-WATCH FIELD COMPLETENESS -- self-audit gap batch 2026-08-30 item 7: the WS7
    # REQUIRED_POSITION_FIELDS promise was only proven synthetically (--dry-run-synthetic);
    # this enforces it live, on real in-trade positions, DEGRADED-only.
    problems.extend(check_live_watch_field_completeness(now))

    # 22. SCHEDULED-TASK STALENESS -- 2026-09-02: Gamma_GuardsFull, the ~11,400-test
    # regression suite, was dark 08-31..09-02 and every surface in this file reported the
    # rig healthy. Every scheduled-task check here and in task_state_guard.py reads State +
    # LastTaskResult; neither moves when a task never starts. Thin passthrough of
    # scheduled_task_staleness.py's own verdict -- never recomputed here. Silent until that
    # task has fired at least once.
    problems.extend(check_task_staleness(now))

    # 23. LIVE-WATCH WRITER LIVENESS -- self-audit gap batch 2026-09-01 item 6: the
    # dead-man switch check_live_watch_field_completeness's own docstring claimed already
    # existed on engine-health.json did not exist anywhere. Closes it.
    problems.extend(check_live_watch_liveness(now))

    verdict = "GREEN" if not problems else ("BROKEN" if any(_problem_is_broken(p) for p in problems) else "DEGRADED")
    result = {"ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": verdict, "problems": problems, "rth": rth,
              "pdt": pdt_summary}
    # SNAPSHOT the previous alert state BEFORE the unconditional write below clobbers it --
    # see _alert()'s docstring for the exact "engine red spam" bug this closes (2026-08-17).
    prev_alert: dict = {}
    if LAST.exists():
        try:
            old = json.loads(LAST.read_text(encoding="utf-8")) or {}
            prev_alert = {"_alerted_sig": old.get("_alerted_sig", ""),
                           "_alerted_at": old.get("_alerted_at"),
                           "_status_sig": old.get("_status_sig", ""),
                           "_status_at": old.get("_status_at")}
        except Exception:  # noqa: BLE001
            prev_alert = {}
    LAST.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if problems:
        _alert(result, prev_alert)
    return result


# A problem's IDENTITY, for dedupe. NOT its full text.
#
# WHY: the dedupe key used to be `" | ".join(result["problems"])` -- the whole message. Half
# these messages embed a running COUNT ("run-*.ps1 shows 15 real non-zero exit(s)", "7
# consecutive cycle failures", "stale for 3.2h"), so the key changed on nearly every fire and
# BOTH consumers broke at once: STATUS.md grew a new `### BROKEN: self-check` block every 30
# minutes (queue.md STATUS-BROKEN-BLOCKS-DRAIN -- four blocks in 23 minutes on 2026-09-02,
# differing ONLY in `13` -> `15` -> `17`), and the 6-hour Discord suppression window below
# never matched, so the same unresolved problem re-pinged all day.
#
# The fix collapses free-standing numbers and nothing else. A digit preceded by a word
# character or a hyphen is part of a NAME and is kept -- `safe-2` must not collapse into
# `safe-3`, and `Gamma_Heartbeat` variants must stay distinguishable. So a task going RED, a
# new arm failing, or a different .ps1 appearing all still read as a changed problem set and
# still append + ping. Only "the same problem, a bigger number" is suppressed.
_COUNT_RUN = re.compile(r"(?<![\w-])\d+(?:\.\d+)?")


def _problem_set_signature(problems: "list[str]") -> str:
    """Stable identity for a set of problems: order-independent, count-insensitive."""
    return " | ".join(sorted(_COUNT_RUN.sub("#", str(p)) for p in problems))


SELF_CHECK_REPEAT_SUPPRESS_MIN = 360  # 6h -- an unresolved problem still re-pings
# periodically (never total silence) but not on every ~30-min self_check cadence tick.


def _alert(result: dict, prev_alert: "dict | None" = None) -> None:
    """Surface to STATUS.md always; ping Discord on a NEW/CHANGED problem set, or on a
    REPEAT of the identical set only once SELF_CHECK_REPEAT_SUPPRESS_MIN has elapsed
    since the last actual SEND.

    BUG FIXED (2026-08-17, J: "I keep getting Discord messages saying engine red and it
    buries the trade pings" -- root-caused via automation/state/discord-outbox.jsonl:
    self_check was the single dominant outbox producer over the trailing 7 days (297 of
    1,049 messages, ~28% of ALL Discord traffic), with CONSECUTIVE BYTE-IDENTICAL-content
    runs up to 25 long -- e.g. the exact same "PREMARKET DEGRADED: today-bias.json is
    fresh-dated but LLM-authored narrative failed..." message re-sent every ~30 min for
    12 straight hours on 2026-08-14). The "Discord ping only on a CHANGED problem set"
    comment on the prior version of this function was the INTENDED behavior but was
    completely inert: run() unconditionally overwrote LAST with a brand-new result dict
    (no _alerted_sig key at all) immediately before calling this function -- so the old
    `prev = ...get("_alerted_sig", "")` here ALWAYS read back "" (the very file it needed
    to compare against had just been clobbered by the SAME run(), a few lines above, in
    the SAME process). `sig != prev` was therefore true 100% of the time there was any
    problem, every single fire. Fix: run() now snapshots the PRE-EXISTING _alerted_sig/
    _alerted_at into `prev_alert` BEFORE its own unconditional write and passes it in
    here; this function never re-reads LAST (by the time it would, the file on disk is
    always this SAME run's own fresh snapshot, not the prior run's).

    engine_health.py's separate "Engine RED"/"Engine DEGRADED" pings were investigated in
    the same pass and are UNCHANGED: only ~8 messages over the same 7 days, each
    describing a DIFFERENT specific failure (state_freshness vs heartbeat_safe vs
    levels_file_stale vs breaker_rearm_safe) -- i.e. NOT repeat-identical content, so that
    producer does not meet the bar for this suppression and was left untouched.

    Never suppresses a FIRST occurrence or a genuinely CHANGED problem set -- only a
    byte-identical repeat within the 6h window is throttled -- and STATUS.md always gets
    the unthrottled snapshot regardless (this throttles the Discord PING only, never the
    underlying detection; no check anywhere in this file was weakened or disabled)."""
    prev_alert = prev_alert or {}
    sig = _problem_set_signature(result["problems"])
    prev_sig = prev_alert.get("_alerted_sig", "")
    prev_at = prev_alert.get("_alerted_at")

    # STATUS.md -- append only when the PROBLEM SET changes, or after the same suppress
    # window the ping uses. It used to append unconditionally on every BROKEN/DEGRADED run,
    # and self_check runs every 30 minutes, so an unresolved problem re-appended forever
    # (queue.md STATUS-BROKEN-BLOCKS-DRAIN). Same transition-only convention as
    # guard_runner_slow._flag_status_md and gate_expiry_check.
    status_sig = prev_alert.get("_status_sig", "")
    status_at = prev_alert.get("_status_at")
    status_stale_enough = True
    if sig == status_sig and status_at:
        try:
            age = (dt.datetime.fromisoformat(result["ts_et"])
                   - dt.datetime.fromisoformat(status_at)).total_seconds() / 60.0
            status_stale_enough = age >= SELF_CHECK_REPEAT_SUPPRESS_MIN
        except ValueError:
            status_stale_enough = True  # unparseable stamp -> never silently suppress
    if sig != status_sig or status_stale_enough:
        try:
            with STATUS_MD.open("a", encoding="utf-8") as f:
                f.write(f"\n### {result['verdict']}: self-check {result['ts_et']}\n")
                for p in result["problems"]:
                    f.write(f"- {p}\n")
            result["_status_sig"] = sig
            result["_status_at"] = result["ts_et"]
        except OSError:
            pass
    else:
        result["_status_sig"] = status_sig
        result["_status_at"] = status_at
    # Discord: always on a NEW/CHANGED problem set. A REPEAT of the identical set is
    # suppressed until SELF_CHECK_REPEAT_SUPPRESS_MIN has elapsed since the last real
    # SEND (never since the last SILENT cycle -- see the `else` branch below).
    repeat_stale_enough = True
    if sig == prev_sig and prev_at:
        try:
            age_min = (dt.datetime.fromisoformat(result["ts_et"])
                       - dt.datetime.fromisoformat(prev_at)).total_seconds() / 60.0
            repeat_stale_enough = age_min >= SELF_CHECK_REPEAT_SUPPRESS_MIN
        except ValueError:
            repeat_stale_enough = True  # unparseable timestamp -> never silently suppress
    send = (sig != prev_sig) or repeat_stale_enough
    if send:
        try:
            with DISCORD_OUTBOX.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": result["ts_et"], "channel": "gamma-ops",
                                    "source": "self_check",
                                    "message": f"SELF-CHECK {result['verdict']}: " + "; ".join(result["problems"])[:500]}) + "\n")
            result["_alerted_at"] = result["ts_et"]
        except OSError:
            pass
    else:
        result["_alerted_at"] = prev_at  # carry the last REAL send time forward
    # remember what we alerted on
    result["_alerted_sig"] = sig
    LAST.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    r = run()
    print(f"[self-check] {r['verdict']} — {len(r['problems'])} problem(s)")
    for p in r["problems"]:
        print(f"  - {p}")
    if r["verdict"] == "GREEN":
        print("  (all verified — nothing to surface)")
    raise SystemExit(0)
