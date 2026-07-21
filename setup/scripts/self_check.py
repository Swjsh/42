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
"""
from __future__ import annotations
import json, sys
import datetime as dt
from pathlib import Path

REPO = Path(__file__).resolve().parents[1].parent
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    def et_now(): return dt.datetime.utcnow() - dt.timedelta(hours=4)

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


TRENDLINE_DRAW_STATE = STATE / "trendline-draw-state.json"


def check_trendline_draw_freshness(now, path=None) -> list:
    """VISIBILITY instrument for premarket Step 5c (TRENDLINE-FIXES-2026-07-17 item 1: 'PREMARKET
    DRAW CANNOT SILENTLY SKIP'). Step 5c (automation/prompts/premarket.md) draws the live engine's
    trendlines on J's chart once daily inside the 08:30 ET Gamma_Premarket fire -- an LLM-driven
    step with a context-budget ceiling, unlike the pure-Python producers this file mostly watches.
    Two budget-skips happened in two days (2026-07-16/17) and both went ONLY to journal
    '## Setups skipped' -- nothing self_check/engine-health/STATUS.md ever surfaced, so J found out
    only by noticing his chart was bare. trendline_draw_state.mark_run() (called by the skill /
    Step 5c on both the success and the skip path) is the producer this reads.

    DEGRADED, never BROKEN: Step 5c is explicitly 'additive visibility, never load-bearing for the
    trading day' (premarket.md's own words) -- a miss does not block or misinform trading decisions
    the way a stale macro calendar or contradictory key-levels role does, so this must not classify
    as BROKEN (see _problem_is_broken) even though it is still worth a real, non-silent flag."""
    if now.weekday() >= 5:
        return []  # no premarket fire on weekends -- nothing to check
    if now.strftime("%H:%M") < "09:00":
        return []  # give Step 5c (08:30 ET) its slack window before judging today stale
    p = path or TRENDLINE_DRAW_STATE
    today = now.strftime("%Y-%m-%d")
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    last_run = state.get("last_run") if isinstance(state, dict) else None
    if not isinstance(last_run, dict) or not last_run.get("date_et"):
        return [f"TRENDLINE-DRAW never marked today ({today}) -- Step 5c may have silently "
                f"skipped (context-budget or TV-down) with no trace beyond the journal. Non-load-"
                f"bearing (visibility only); run the trendline-draw skill by hand to catch up."]
    if last_run["date_et"] != today:
        return [f"TRENDLINE-DRAW STALE: last mark_run was {last_run['date_et']} ({last_run.get('status')}), "
                f"not today ({today}) -- Step 5c likely didn't fire this morning. Non-load-bearing "
                f"(visibility only); run the trendline-draw skill by hand to catch up."]
    if last_run.get("status") == "skipped":
        reason = last_run.get("reason") or "no reason recorded"
        return [f"TRENDLINE-DRAW SKIPPED today ({today}): {reason}. Non-load-bearing (visibility "
                f"only); run the trendline-draw skill by hand if J wants the chart populated."]
    return []


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


def _problem_is_broken(p: str) -> bool:
    """BROKEN (vs DEGRADED) classifier for a problem string. Module-level so the
    graduated guards can assert the mapping (e.g. PLACEMENT BROKEN -> BROKEN)."""
    return (("crash" in p.lower()) or ("RED" in p) or ("STALE/REVOKED" in p)
            or ("KEY MISSING" in p) or ("CANNOT ENTER" in p)
            or ("CONTRADICTORY ROLES" in p) or ("PLACEMENT BROKEN" in p))


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

    # 13. TRENDLINE-DRAW FRESHNESS -- the 2026-07-16/17 scar: 2 budget-skips of premarket
    # Step 5c in 2 days went to journal only, invisible to J until he noticed a bare chart.
    problems.extend(check_trendline_draw_freshness(now))

    # 14. TV-CDP LIVENESS -- the 2026-07-07/09 scar (D1 audit Finding #1/#3): a 41+ hour
    # TradingView CDP outage degraded premarket bias to real 'no-trade-tv-fail' framing and
    # NOTHING in this file ever saw it. preopen_readiness.py caught this class at its own
    # one-shot 08:25 ET fire; this closes the same gap on the surface J's morning brief reads.
    problems.extend(check_tv_cdp(now))

    verdict = "GREEN" if not problems else ("BROKEN" if any(_problem_is_broken(p) for p in problems) else "DEGRADED")
    result = {"ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": verdict, "problems": problems, "rth": rth,
              "pdt": pdt_summary}
    LAST.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if problems:
        _alert(result)
    return result


def _alert(result: dict) -> None:
    """Surface to STATUS.md + Discord — ONLY on a NEW problem set (no spam when unchanged)."""
    sig = " | ".join(result["problems"])
    prev = ""
    if LAST.exists():
        try:
            prev = (json.loads(LAST.read_text(encoding="utf-8")) or {}).get("_alerted_sig", "")
        except Exception:  # noqa: BLE001
            pass
    # STATUS.md (always append the current snapshot)
    try:
        with STATUS_MD.open("a", encoding="utf-8") as f:
            f.write(f"\n### {result['verdict']}: self-check {result['ts_et']}\n")
            for p in result["problems"]:
                f.write(f"- {p}\n")
    except OSError:
        pass
    # Discord ping only on a CHANGED problem set (avoid every-30-min spam)
    if sig != prev:
        try:
            with DISCORD_OUTBOX.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": result["ts_et"], "channel": "gamma-ops",
                                    "source": "self_check",
                                    "message": f"SELF-CHECK {result['verdict']}: " + "; ".join(result["problems"])[:500]}) + "\n")
        except OSError:
            pass
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
