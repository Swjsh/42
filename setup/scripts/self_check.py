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

    verdict = "GREEN" if not problems else ("BROKEN" if any(_problem_is_broken(p) for p in problems) else "DEGRADED")
    result = {"ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": verdict, "problems": problems, "rth": rth}
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
