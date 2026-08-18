"""trade_today_watcher.py -- the standing "did the engine trade today" instrument (OP-33e).

J's #1 recurring question is "did it trade / did it fill." Answering it ad-hoc is the anti-pattern;
this is the standing surface that retires it. The SOURCE OF TRUTH for engine trades is Alpaca
get_orders, NOT decisions.jsonl (ENTER rows historically skipped the ledger -- wake-protocol
2026-05-13). This queries every account's Alpaca orders for TODAY's SPY-OPTION orders (excluding
J's manual crypto), splits them into FILLED vs PLACED-NOT-FILLED (the placement->fill gap), writes
a glanceable automation/state/trade-today.json, and LOUD-pings J once per new fill (flagged
FIRST ENGINE FILL EVER if it's the first). Dedup by order id. Notify-only, fail-open, $0.

Nightly Gamma_DressRehearsal broker-path probes (dress_rehearsal.py check 1) are real Alpaca
orders and land inside this watcher's after=<ET-date>T00:00:00Z window (midnight UTC = 20:00 ET
the PRIOR evening, so the ~20:45 ET probes read as "today"). They are plumbing checks, not
trading activity -- excluded from both counts by signature and disclosed under rehearsal_probes.

Scheduled every ~2 min during RTH -> J is TOLD the moment the engine fills, without asking.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "trade-today-watcher.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "trade-today-watcher.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))
import fleet_broker as fb  # noqa: E402
from et_clock import et_offset_hours, et_today_str  # noqa: E402

STATE = REPO / "automation" / "state"
OUTBOX = STATE / "discord-outbox.jsonl"
TRADE_TODAY = STATE / "trade-today.json"
PINGED = STATE / "trade-today-pinged.json"
LIFETIME = STATE / "engine-lifetime-fills.json"
DISCORD_CFG = STATE / ".discord-config.json"
ACCOUNTS_PATH = STATE / "fleet" / "accounts.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _load_user_mention() -> str:
    """T3 fix (HANDOFF-2026-07-09-TRUTH-AND-EXITS): every fill ping this module ever queued
    (28/28 as of 2026-07-08, including the FIRST ENGINE FILL EVER message) lacked the
    <@user_id> mention token that other 'LOUD ping' producers (discord-watcher.py) already
    use. Discord's own delivery pipeline confirmed a clean 200/201 send for that message
    (discord-bridge.stderr.log:6489) -- it posted to the channel successfully but, without a
    mention, likely never triggered a phone push if J's notification setting on that channel
    is anything but 'All Messages'. Same fail-open pattern as discord-watcher.py's
    _load_user_mention(). Fail-open -> "" (never blocks the ping itself on a config miss)."""
    try:
        cfg = json.loads(DISCORD_CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:  # noqa: BLE001
        return ""


def _is_spy_option(sym) -> bool:
    return isinstance(sym, str) and sym.startswith("SPY") and len(sym) >= 15


# EXIT-PROFILE COLUMN (2026-07-20, J directive: "one gets stopped out on the ribbon, one
# plays the rejection outside the ribbon, one rides it better" -- every fleet arm now trades
# the SAME shared signal but with a DIFFERENT accounts.json params_patch.exit_patch overlay,
# see fleet_executor.py's _exit_shape_dict docstring). J's #1 recurring ask for this file is
# "did it trade" -- the natural next question once arms carry DIFFERENT exits is "which exit
# banked THIS fill." accounts.json's per-arm "exit_profile" field (RIBBON/TRIG-EXACT/
# ZONE-RIDE/CORE) is the single source of truth (set alongside each arm's exit_patch, not
# duplicated here); this is a thin, fail-open, cached reader -- never used for dispatch,
# read-surface only, mirrors arm_display.py's own _arms() caching pattern.
_ARM_EXIT_PROFILE_CACHE: "dict | None" = None


def _exit_profile_for_arm(arm_id: str) -> str:
    """This arm's short exit-profile label, or '' when the arm/file/field is missing --
    fail-open, must never block the fill ping itself."""
    global _ARM_EXIT_PROFILE_CACHE
    if _ARM_EXIT_PROFILE_CACHE is None:
        try:
            data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
            _ARM_EXIT_PROFILE_CACHE = {
                a["id"]: str(a.get("exit_profile") or "")
                for a in data.get("arms", []) if isinstance(a, dict) and a.get("id")
            }
        except (OSError, ValueError):
            _ARM_EXIT_PROFILE_CACHE = {}
    return _ARM_EXIT_PROFILE_CACHE.get(arm_id, "")


REHEARSAL_MAX_LIMIT = 0.02    # rehearsal PROBE_LIMIT is $0.01, never-marketable
REHEARSAL_MAX_CANCEL_S = 2.0  # rehearsal cancels ~0.16s after submit; the engine never does

_FRAC_RE = re.compile(r"\.(\d{6})\d+")


def _parse_utc(ts) -> "dt.datetime | None":
    """RFC3339 -> aware-UTC datetime. Alpaca emits nanosecond precision; fromisoformat
    accepts at most 6 fractional digits (and no 'Z' before 3.11). None on anything
    unparseable -- callers treat that as NOT-a-probe (fail toward J seeing the order)."""
    if not isinstance(ts, str) or not ts:
        return None
    t = _FRAC_RE.sub(r".\1", ts.strip().replace("Z", "+00:00"), count=1)
    try:
        d = dt.datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _is_rehearsal_probe(o) -> bool:
    """PURE: True iff the order matches the nightly Gamma_DressRehearsal broker-path probe
    (dress_rehearsal.py check 1). The rehearsal sets no client_order_id (it POSTs through the
    engine's own _place_simple_entry: symbol/qty/side/type/limit_price/tif only), so the match
    is by signature. EVERY leg must hold; anything ambiguous stays a REAL order:
      1-lot, limit <= $0.02 (PROBE_LIMIT $0.01, never-marketable),
      canceled < 2s after submit (probe is canceled immediately after acceptance),
      submitted outside RTH (probes fire ~20:45 ET; engine entries exist only 09:35-15:50 ET).
    """
    try:
        qty = float(o.get("qty") or 0)
        lp = float(o.get("limit_price") or 0)
    except (TypeError, ValueError):
        return False
    if not (0 < qty <= 1 and 0 < lp <= REHEARSAL_MAX_LIMIT):
        return False
    sub = _parse_utc(o.get("submitted_at"))
    can = _parse_utc(o.get("canceled_at"))
    if sub is None or can is None:
        return False
    if not (0 <= (can - sub).total_seconds() < REHEARSAL_MAX_CANCEL_S):
        return False
    sub_et = sub + dt.timedelta(hours=et_offset_hours(sub))
    hhmm = sub_et.hour * 100 + sub_et.minute
    return not (930 <= hhmm < 1600)


def split_rehearsal_probes(orders) -> "tuple[list, list[dict]]":
    """PURE: (real_orders, probe_records). SPY-option orders matching the rehearsal
    signature are pulled out as lean records for the trade-today.json transparency key;
    everything else passes through untouched. Testable (no network)."""
    real: list = []
    probes: list[dict] = []
    for o in orders or []:
        if _is_spy_option(o.get("symbol", "")) and _is_rehearsal_probe(o):
            probes.append({"id": o.get("id"), "symbol": o.get("symbol"),
                           "qty": o.get("qty"), "limit_price": o.get("limit_price"),
                           "side": o.get("side"), "status": o.get("status"),
                           "submitted_at": o.get("submitted_at"),
                           "canceled_at": o.get("canceled_at")})
        else:
            real.append(o)
    return real, probes


def classify_orders(orders) -> "tuple[list[dict], list[dict]]":
    """PURE: split today's SPY-OPTION orders into (filled, placed_not_filled). Crypto/stock and
    non-SPY are ignored. Filled = filled_qty>0 AND filled_avg_price>0. Testable (no network)."""
    filled: list[dict] = []
    unfilled: list[dict] = []
    for o in orders or []:
        sym = o.get("symbol", "")
        if not _is_spy_option(sym):
            continue
        try:
            fq = float(o.get("filled_qty") or 0)
            fp = float(o.get("filled_avg_price") or 0)
        except (TypeError, ValueError):
            fq = fp = 0.0
        rec = {"id": o.get("id"), "symbol": sym, "qty": fq, "price": fp,
               "side": o.get("side"), "status": o.get("status"), "filled_at": o.get("filled_at")}
        (filled if (fq > 0 and fp > 0) else unfilled).append(rec)
    return filled, unfilled


def _fetch_orders(creds: dict) -> list:
    try:
        ep = f"orders?status=all&after={et_today_str()}T00:00:00Z&limit=100"
        res = fb._request(creds, ep, method="GET")
        return res if isinstance(res, list) else []
    except Exception:
        return []


# VISIBILITY (2026-07-09, OP-33c/STOP-B first-live-day): mcp_heartbeat arms (safe-2/bold-2)
# log their exit_pass rows into the SHARED core-decisions.jsonl under the SHORT account
# label heartbeat_core.ACCOUNTS uses ("safe"/"bold"), not the arm id -- see heartbeat_core.py
# ACCOUNTS dict. fleet_rest arms (safe-1/safe-3/risky-1/risky-3) log to their OWN
# automation/state/fleet/{arm}/decisions.jsonl. This is the SAME split fleet_live.py and
# heartbeat_core.py already encode; duplicated here (read-only) rather than importing either
# module (this watcher stays a thin, dependency-light poller).
_CORE_ACCOUNT_FOR_ARM = {"safe-2": "safe", "bold-2": "bold"}


def _decision_rows_for_arm(arm: str, tail_lines: int = 2000) -> list:
    """Bounded-tail decision rows relevant to this arm, oldest-first (on-disk order).
    Fail-open -> [] on any missing/corrupt source (never blocks the fill ping)."""
    core_account = _CORE_ACCOUNT_FOR_ARM.get(arm)
    path = (STATE / "core-decisions.jsonl") if core_account else (STATE / "fleet" / arm / "decisions.jsonl")
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-tail_lines:]:
        try:
            row = json.loads(ln)
        except (json.JSONDecodeError, ValueError):
            continue
        if core_account and row.get("account") != core_account:
            continue
        out.append(row)
    return out


def _structure_exit_label(arm: str, symbol: str) -> str:
    """RENDER-ONLY (2026-07-09 visibility build, OP-33c): '' or a ' | exit: structure@<level>'
    suffix for a fill whose position is/was managed under SS-B structure-stop -- fixes the
    known cosmetic gap (STATUS.md 2026-07-09 ~16:20 ET) reaching Discord too, per the mission
    "make the TRUTH glanceable everywhere J looks." Two sources, in priority order:

    1. The LIVE exit-state ledger (automation/state/fleet/{arm}/exit-state.json) -- correct
       for an ENTRY fill, since the position was JUST registered and is still open.
    2. The decision log's exit_pass history (fallback) -- an EXIT fill's symbol is ALREADY
       pruned from exit-state.json by the SAME tick that closed it (exit_actuator.manage_tick
       deletes on SELL_ALL), so source 1 always misses on an exit; this scans backward for the
       structure_stop action that closed it.

    Reuses the EXISTING composer's data (no new Discord path, no new state file). Never
    raises, never returns anything for a premium-mode or undiscoverable position (silently
    '' -- must never block or alter the ping itself)."""
    try:
        est_path = STATE / "fleet" / arm / "exit-state.json"
        if est_path.exists():
            est = json.loads(est_path.read_text(encoding="utf-8"))
            pos = est.get(symbol)
            if isinstance(pos, dict) and pos.get("stop_mode") == "structure":
                return f" | exit: structure@{pos.get('trigger_level')} (armed)"
    except Exception:  # noqa: BLE001
        pass
    try:
        for row in reversed(_decision_rows_for_arm(arm)):
            for ep in (row.get("exit_pass") or []):
                if not isinstance(ep, dict) or ep.get("symbol") != symbol:
                    continue
                for act in (ep.get("actions") or []):
                    if isinstance(act, dict) and act.get("stage") == "structure_stop":
                        return f" | exit: structure@{ep.get('trigger_level')}"
    except Exception:  # noqa: BLE001
        pass
    return ""


def _dedup_by_order_id(records: list, seen_ids: set) -> list:
    """PURE (2026-07-17, port of accounts_status.py's safe-1/safe-2 shared-account dedup
    workaround -- see that module's ORDER list comment): fleet/secrets.json can carry TWO+
    credential labels pointed at the SAME broker account (safe-1 and safe-2 both resolve to
    PA3DHPT7KIQE post the 2026-07-11 repoint -- accounts.json's safe-1._retired_doc). Unlike
    accounts_status.py (which hardcodes an ORDER list that simply omits the retired label),
    this watcher iterates fleet_broker.load_creds() directly (every label in secrets.json,
    with no accounts.json status awareness) -- so every core-Safe fill/order got fetched and
    counted TWICE, once per label. Root cause of the 2026-07-17 46-rows/31-unique-ids
    incident (task_32d96df3). Dedup by ALPACA ORDER ID (not by arm) is the robust fix: it
    self-heals for ANY future credential-label collision, not just this specific pair, and
    doesn't depend on accounts.json status staying in sync. First-seen label (dict iteration
    = secrets.json insertion order, stable across runs) keeps attribution; later duplicates
    are dropped before they ever reach the count/ping path. Records with no "id" pass through
    unfiltered (never silently drop an unidentifiable order)."""
    out = []
    for x in records:
        oid = x.get("id")
        if oid:
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
        out.append(x)
    return out


def _is_engine_attributed(arm: str, symbol: str) -> bool:
    """True if some decision row for this arm has a record naming this symbol -- checks
    FOUR execution-record shapes across the two decisions.jsonl SCHEMAS this repo runs
    (core heartbeat_core.py vs fleet_rest fleet_live.py -- see _decision_rows_for_arm's
    docstring for the path split):
      1. core primary path: row["exec"] (dict).
      2. core extra-setup G4 side-channel: row["extra_exec"][i]["exec"] (dict).
      3. fleet_rest ENTER path: row["action"] startswith "ENTER" + row["placement"]["broker"]
         (dict) -- fleet_live.py's schema has NO "exec"/"extra_exec" key at all.
      4. fleet_rest EXIT path: row["exit_pass"][i]["symbol"] + that entry's ["actions"][j]
         carrying a "broker" dict (an actually-placed exit, not just a monitoring tick with
         empty actions).
    CORRECTED 2026-07-16 (paths 1-2, b5c575e/9a133ee): the first version only checked the
    primary core path and wrongly labeled a REAL vwap_continuation engine trade
    "UNATTRIBUTED" -- caught when J said "I did not do anything today."
    CORRECTED 2026-07-17 (paths 3-4, SAME bug class recurring in the sibling branch that fix
    never touched): fleet_rest arms (safe-1/safe-3/risky-1/risky-3) were STRUCTURALLY
    guaranteed a False here -- their schema never has "exec"/"extra_exec" -- so EVERY
    fleet-arm fill, real or not, was mislabeled "UNATTRIBUTED FILL (no matching decision
    row)" in the Discord ping. Confirmed live: 13/13 fleet fills on 2026-07-17 (safe-3
    x4, risky-1 x4, risky-3 x5) pinged UNATTRIBUTED despite each having a complete,
    correctly-timestamped ENTER_BEAR + exit_pass row with an identical broker order id in
    that arm's OWN decisions.jsonl -- the ledger was never missing anything; this checker
    just couldn't read its schema. See analysis/daily-brief/2026-07-17-fleet-attribution-audit.md.
    Fail-open -> False on any error; never blocks the ping itself."""
    try:
        for row in _decision_rows_for_arm(arm):
            exec_rec = row.get("exec")
            if isinstance(exec_rec, dict) and exec_rec.get("symbol") == symbol:
                return True
            for extra in (row.get("extra_exec") or []):
                if not isinstance(extra, dict):
                    continue
                nested = extra.get("exec")
                if isinstance(nested, dict) and nested.get("symbol") == symbol:
                    return True
            action = row.get("action")
            if isinstance(action, str) and action.startswith("ENTER"):
                broker = (row.get("placement") or {}).get("broker")
                if isinstance(broker, dict) and broker.get("symbol") == symbol:
                    return True
            for ep in (row.get("exit_pass") or []):
                if not isinstance(ep, dict) or ep.get("symbol") != symbol:
                    continue
                for act in (ep.get("actions") or []):
                    if isinstance(act, dict) and isinstance(act.get("broker"), dict):
                        return True
    except Exception:  # noqa: BLE001
        pass
    return False


# =============================================================================
# READABLE FILL FORMAT (2026-08-17, J's exact words after calling the old single-line
# pipe-concatenated message "just gibberish" and "I cannot read them"): "Red or green
# emoji for put or call, and then needs to be, like, 777c five contracts at price with
# a take profit at this level. But it needs to be in, like, a new line and, like, a
# bullet." Replaces the old one-liner --
#   "ENGINE TRADE [safe-2 CORE-SAFE (46VG)]: SPY260817P00775000 x5 @ $0.72 buy
#    (2026-08-17T17:06:05Z) | exit: structure@775.09 (armed) | exit:CORE"
# -- with a direction-emoji headline + bulleted detail:
#   "🔴 775P ×5 @ $0.72 — ENGINE TRADE [bold-2]
#    • TP1 $1.44 (+100%), sell 3
#    • stop: structure @ $775.09
#    • 13:06:05 ET"
# The pretty arm_display.display_name_for_arm_id() suffix (e.g. "CORE-BOLD (U67N)") is
# DROPPED from the tag -- J asked for it SHORT ("[bold-2]"); it was a major contributor
# to the "gibberish" complaint. Newlines survive the outbox->Discord path unmodified:
# discord-bridge.py's drain_outbox only .strip()s the OUTER ends of `content` and posts
# it verbatim as JSON (json={"content": content}), which preserves embedded "\n" through
# both the HTTP JSON encoding and Discord's own multi-line rendering.
# =============================================================================
_OCC_RE = re.compile(r"^[A-Z]+\d{6}([CP])(\d{8})$")


def _parse_occ(symbol: str) -> "tuple[str, str] | None":
    """OCC option symbol -> (right 'C'|'P', human strike label, e.g. '775' or '775.5').
    None on anything that doesn't match the expected shape -- callers fall back to the
    raw symbol string rather than crash or silently mislabel a real fill (fail-open)."""
    m = _OCC_RE.match(symbol or "")
    if not m:
        return None
    right = m.group(1)
    strike = int(m.group(2)) / 1000.0
    strike_s = str(int(strike)) if strike == int(strike) else f"{strike:g}"
    return right, strike_s


def _contract_label(symbol: str) -> str:
    """'SPY260817P00775000' -> '775P'. Falls back to the raw symbol on a parse miss."""
    parsed = _parse_occ(symbol)
    return f"{parsed[1]}{parsed[0]}" if parsed else symbol


def _direction_emoji(symbol: str) -> str:
    """J's literal spec: red for PUT, green for CALL. Neutral white circle on a parse
    miss -- never guess a direction the symbol string didn't actually say."""
    parsed = _parse_occ(symbol)
    if parsed is None:
        return "⚪"  # white circle -- unknown, never silently guess red or green
    return "\U0001F534" if parsed[0] == "P" else "\U0001F7E2"


def _fmt_fill_time_et(filled_at) -> str:
    """RFC3339 UTC fill timestamp -> 'HH:MM:SS' in ET (DST-aware via et_offset_hours,
    the SAME helper _is_rehearsal_probe already uses for this identical conversion).
    '' on anything unparseable -- fail-open, never blocks the rest of the ping."""
    parsed = _parse_utc(filled_at)
    if parsed is None:
        return ""
    et_dt = parsed + dt.timedelta(hours=et_offset_hours(parsed))
    return et_dt.strftime("%H:%M:%S")


def _position_exit_info(arm: str, symbol: str) -> "dict | None":
    """The live exit-state.json record for (arm, symbol), or None if absent/unreadable.
    Same read _structure_exit_label's source 1 already uses (STATE/fleet/{arm}/
    exit-state.json) -- an ENTRY fill's position is registered the SAME tick this
    watcher pings it, so it is always still present here. Deliberately does NOT fall
    back to _structure_exit_label's source-2 decision-log scan: that fallback exists for
    an EXIT fill whose position was just pruned, and reusing it for a TP1-bullet/stop-
    bullet context would attach a stale "(armed)" stop label to a fill that may have
    closed for an unrelated reason (e.g. a TP1 partial sell, not a stop-out) -- see the
    main() loop comment for why EXIT fills render no stop bullet at all. Fail-open."""
    try:
        est_path = STATE / "fleet" / arm / "exit-state.json"
        if not est_path.exists():
            return None
        est = json.loads(est_path.read_text(encoding="utf-8"))
        pos = est.get(symbol)
        return pos if isinstance(pos, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _tp1_bullet(pos: dict) -> str:
    """'TP1 $X.XX (+NN%), sell Q' from a freshly-registered exit-state record (tp1_level
    math mirrors exit_manager.py's own `entry * (1 + tp1_premium_pct)`, ~line 591 of
    automation/state/fleet/exit_manager.py -- same formula, read-only, never re-derives
    or overrides it). '' on any missing/malformed field or a zero tp1_qty (an all-runner
    shape has nothing to report here) -- fail-open, never blocks the rest of the ping."""
    try:
        entry = float(pos["entry_premium"])
        pct = float(pos["tp1_premium_pct"])
        qty = int(pos["tp1_qty"])
    except (KeyError, TypeError, ValueError):
        return ""
    if qty <= 0:
        return ""
    tp1_price = entry * (1.0 + pct)
    return f"TP1 ${tp1_price:.2f} ({pct * 100:+.0f}%), sell {qty}"


def _stop_bullet(pos: dict) -> str:
    """'stop: structure @ $LEVEL' (v15.3 chart-stop-primary) or 'stop: catastrophe cap
    NN% ($PRICE)' (premium-mode fallback -- CLAUDE.md 2026-06-18: "premium stops are now
    -50% catastrophe caps both sides") -- whichever this position actually resolved to
    ONCE at entry (stop_mode never flaps mid-trade, per exit_manager.ExitState's own
    contract). '' when neither is available -- fail-open, never blocks the ping."""
    try:
        entry = float(pos["entry_premium"])
    except (KeyError, TypeError, ValueError):
        return ""
    if str(pos.get("stop_mode", "premium")) == "structure" and pos.get("trigger_level") is not None:
        try:
            return f"stop: structure @ ${float(pos['trigger_level']):.2f}"
        except (TypeError, ValueError):
            return ""
    try:
        cat_pct = float(pos.get("catastrophe_stop_pct"))
    except (TypeError, ValueError):
        return ""
    cat_price = entry * (1.0 + cat_pct)
    return f"stop: catastrophe cap {cat_pct * 100:.0f}% (${cat_price:.2f})"


def main() -> int:
    creds_all = fb.load_creds()
    pinged = {}
    if PINGED.exists():
        try:
            pinged = json.loads(PINGED.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pinged = {}
    ever_filled = False
    if LIFETIME.exists():
        try:
            ever_filled = bool(json.loads(LIFETIME.read_text(encoding="utf-8")).get("ever_filled"))
        except (OSError, ValueError):
            ever_filled = False

    all_filled: list[dict] = []
    all_unfilled: list[dict] = []
    all_probes: list[dict] = []
    new: list[dict] = []
    seen_order_ids: set = set()  # cross-arm dedup (2026-07-17) -- see _dedup_by_order_id
    for arm, creds in creds_all.items():
        real, probes = split_rehearsal_probes(_fetch_orders(creds))
        f, u = classify_orders(real)
        for x in f + u + probes:
            x["arm"] = arm
            x["exit_profile"] = _exit_profile_for_arm(arm)
        f = _dedup_by_order_id(f, seen_order_ids)
        u = _dedup_by_order_id(u, seen_order_ids)
        all_filled += f
        all_unfilled += u
        all_probes += probes
        for x in f:
            if x["id"] and x["id"] not in pinged:
                new.append(x)
                pinged[x["id"]] = _now()

    TRADE_TODAY.write_text(json.dumps({
        "date": et_today_str(), "checked_at": _now(),
        "spy_fills_today": len(all_filled), "placed_not_filled_today": len(all_unfilled),
        "rehearsal_probes_today": len(all_probes),
        "ever_filled": ever_filled or bool(new),
        "fills": all_filled, "unfilled": all_unfilled,
        "rehearsal_probes": all_probes}, indent=2), encoding="utf-8")

    mention = _load_user_mention()
    for x in new:
        first = not ever_filled
        arm_id = x["arm"]              # SHORT tag only (J's spec) -- the pretty
                                        # arm_display display_name suffix is dropped, see
                                        # the READABLE FILL FORMAT comment above.
        symbol = x["symbol"]
        side = str(x.get("side") or "").lower()
        is_exit = side == "sell"       # entries are always broker BUYs in this system
                                        # (never averages down / never shorts options --
                                        # see MEMORY "never_average_down" guard); a SELL
                                        # is unambiguously a TP1/runner/stop exit fill.
        attributed = _is_engine_attributed(arm_id, symbol)
        # EXIT-PROFILE (2026-07-20): which exit_patch overlay banked this fill -- RIBBON /
        # TRIG-EXACT / ZONE-RIDE / CORE / PREMIUM-STOP (see _exit_profile_for_arm). '' when
        # the arm has no label yet -- omitted rather than printing an empty bullet.
        profile = x.get("exit_profile") or _exit_profile_for_arm(arm_id)
        fill_et = _fmt_fill_time_et(x.get("filled_at"))
        emoji = _direction_emoji(symbol)
        contract = _contract_label(symbol)
        qty_i = int(x["qty"])
        price = x["price"]

        if is_exit:
            head = f"{emoji} {contract} EXIT ×{qty_i} @ ${price:.2f} [{arm_id}]"
        else:
            verb = "ENGINE TRADE" if attributed else "UNATTRIBUTED"
            head = f"{emoji} {contract} ×{qty_i} @ ${price:.2f} — {verb} [{arm_id}]"

        bullets: list[str] = []
        if not is_exit:
            # TP1/stop bullets are ENTRY-ONLY (J's spec: EXIT fills get "no TP bullet";
            # a stop bullet on an EXIT would be either stale [the position is already
            # gone] or actively misleading on a TP1 partial-sell EXIT, whose position is
            # STILL open and would otherwise print "(armed)" stop info that had nothing
            # to do with why THIS fill happened -- see _position_exit_info's docstring).
            pos = _position_exit_info(arm_id, symbol)
            if pos:
                tp1 = _tp1_bullet(pos)
                if tp1:
                    bullets.append(tp1)
                stop = _stop_bullet(pos)
                if stop:
                    bullets.append(stop)
        if fill_et:
            bullets.append(f"{fill_et} ET")
        if profile:
            bullets.append(f"profile: {profile}")
        if not attributed:
            # J relies on this warning (rule-10 "if Gamma flags a rule violation, the
            # trade does not happen" territory when it's a ROGUE fill) -- moved off line 1
            # into a bullet per J's explicit "it can move to a bullet".
            bullets.append("⚠️ UNATTRIBUTED — no matching decision row")
        if first:
            bullets.append("\U0001F389 FIRST ENGINE FILL EVER")

        msg = "\n".join([head] + [f"• {b}" for b in bullets])
        with OUTBOX.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"content": mention + msg,
                                 "source": "trade_today_watcher", "queued_at": _now()}) + "\n")
        print("PINGED J:", msg.replace("\n", " | "))
        ever_filled = True

    if new and not LIFETIME.exists():
        LIFETIME.write_text(json.dumps({"ever_filled": True, "first_fill_at": _now()}), encoding="utf-8")
    PINGED.write_text(json.dumps(pinged), encoding="utf-8")
    print(f"[trade_today_watcher] SPY today: {len(all_filled)} FILLED, "
          f"{len(all_unfilled)} placed-not-filled; {len(all_probes)} rehearsal probe(s) "
          f"excluded; {len(new)} new ping(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
