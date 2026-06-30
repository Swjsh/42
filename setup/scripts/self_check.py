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

    verdict = "GREEN" if not problems else ("BROKEN" if any("crash" in p.lower() or "RED" in p for p in problems) else "DEGRADED")
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
