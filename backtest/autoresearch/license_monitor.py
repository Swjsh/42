"""LICENSE-MONITOR — times the dormant validated deploys (WP-5 / WP-6 / WP-8 / WP-0).

THE GAP IT CLOSES: `recency_check.py` answers "is edge X RED *now*" — it is a
contemporaneous gate with NO RED->green TRANSITION detector. So the validated WP-8
doubler (1DTE + dollar-anchored stop on the live vwap_continuation edge, already
flag-deployed in both params files) just sits HELD with nobody watching for the day
it becomes flip-eligible. This monitor watches the recency verdicts, diffs them
against the last snapshot, and on a meaningful transition pings J via Discord +
STATUS.md so the doubler ships the FIRST eligible day after the drawdown ends —
turning a passive weekly chore into an active trigger.

NEVER flips anything (Rule 9) — it only NOTIFIES. Pure $0 monitor (free; the optional
--run refresh just re-invokes the existing recency sim on cached data).

Deploy-status mapping (from the deploy_first synthesis 2026-06-21):
  verdict CONFIRM -> LICENSED  (flip-eligible AND capital-scaling licensed)
  verdict YELLOW  -> ELIGIBLE  (ship-eligible per the WP gates; size conservatively)
  verdict RED / NO_FILLS -> BLOCKED (no live flip; do not add size into the drawdown)

Run (nightly, evening, after the OPRA cache extends a day):
  backtest/.venv/Scripts/python.exe backtest/autoresearch/license_monitor.py --run
Manual standing check (no pings):
  ... license_monitor.py --force-ping --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]              # ...\42\backtest
ROOT = REPO.parent                                       # ...\42
STATE = ROOT / "automation" / "state"
RECENCY_JSON = STATE / "recency-confirmation.json"
RECENCY_PY = REPO / "autoresearch" / "recency_check.py"
SNAP = STATE / "license-monitor-last.json"
OUTBOX = STATE / "discord-outbox.jsonl"
CFG = STATE / ".discord-config.json"
STATUS_MD = ROOT / "automation" / "overnight" / "STATUS.md"

# Which WPs each live-tier verdict gates (from the deploy_first synthesis).
TIER_WPS = {
    "#1 ATM (Safe-2)": "WP-5/6/8 (Safe: re-strike + chandelier + 1DTE/dollar-stop doubler)",
    "#1 ITM-2 (Bold)": "WP-5/6/8 (Bold: re-strike + chandelier + 1DTE/dollar-stop doubler)",
    "#2 ATM": "WP-0 overlay (#2 vwap_reclaim_failed_break as a #1-overlay)",
    "#4 ATM": "WP-0 overlay (#4 vix_regime_dayside as a #1-overlay)",
}

# Map each live tier to its (edge, tier) path in the recency JSON, for recent-exp color.
TIER_PATH = {
    "#1 ATM (Safe-2)": ("vwap_continuation", "ATM"),
    "#1 ITM-2 (Bold)": ("vwap_continuation", "ITM-2"),
    "#2 ATM": ("vwap_reclaim_failed_break", "ATM"),
    "#4 ATM": ("vix_regime_dayside", "ATM"),
}

# verdict -> deploy status; ship-eligible at >= YELLOW per the WP gates.
_STATUS = {"CONFIRM": "LICENSED", "YELLOW": "ELIGIBLE", "RED": "BLOCKED", "NO_FILLS": "BLOCKED"}
_RANK = {"BLOCKED": 0, "ELIGIBLE": 1, "LICENSED": 2}


def classify(verdict: str | None) -> str:
    """Map a recency verdict to a deploy status (default BLOCKED for the unknown/cautious)."""
    return _STATUS.get(verdict or "", "BLOCKED")


def transition(prev_status: str | None, cur_status: str) -> str | None:
    """Return the meaningful deploy-state transition between two statuses, or None."""
    if prev_status is None or prev_status == cur_status:
        return None
    p, c = _RANK[prev_status], _RANK[cur_status]
    if p == 0 and c >= 1:
        return "UNBLOCKED"      # RED -> flip-eligible (the one we are waiting for)
    if p == 1 and c == 2:
        return "UPGRADED"       # YELLOW -> CONFIRM (capital-scale licensed)
    if p >= 1 and c == 0:
        return "RE-BLOCKED"     # eligible/licensed -> RED (hold; do not add size)
    if p == 2 and c == 1:
        return "DOWNGRADED"     # CONFIRM -> YELLOW (still eligible, scale license lapsed)
    return None


def diff_tiers(prev: dict | None, cur: dict) -> list[dict]:
    """Per-tier transition events between two ``live_tier_verdicts`` dicts."""
    events: list[dict] = []
    for tier, cur_verdict in cur.items():
        cur_status = classify(cur_verdict)
        prev_verdict = (prev or {}).get(tier)
        prev_status = classify(prev_verdict) if prev_verdict else None
        kind = transition(prev_status, cur_status)
        if kind:
            events.append({
                "tier": tier, "kind": kind,
                "prev_verdict": prev_verdict, "cur_verdict": cur_verdict,
                "prev_status": prev_status, "cur_status": cur_status,
                "wps": TIER_WPS.get(tier, "?"),
            })
    return events


def _recent_exp(data: dict, tier: str) -> str:
    """Pull the recent-window per-trade expectancy for color; '' if unavailable."""
    path = TIER_PATH.get(tier)
    if not path:
        return ""
    try:
        rw = data["edges"][path[0]]["tiers"][path[1]]["recent_window"]
        exp = rw.get("exp_per_trade")
        n = rw.get("n")
        return f"recent ${exp}/tr, n={n}" if exp is not None else ""
    except Exception:
        return ""


_EMOJI = {"UNBLOCKED": "\U0001F7E2", "UPGRADED": "⭐",
          "RE-BLOCKED": "\U0001F534", "DOWNGRADED": "\U0001F7E1"}


def message_for(ev: dict, color: str) -> str:
    """Build the J-facing one-liner for an event (sharp-operator voice, Rule-9 safe)."""
    tier, wps = ev["tier"], ev["wps"]
    pv, cv = ev["prev_verdict"], ev["cur_verdict"]
    tail = f" ({color})" if color else ""
    head = f"{_EMOJI.get(ev['kind'], '')} **LICENSE-MONITOR — {tier} {ev['kind']}** ({pv}->{cv}{tail})."
    if ev["kind"] == "UNBLOCKED":
        return (f"{head} {wps} is now flip-**ELIGIBLE** — capitalize in the next daytime block. "
                f"Rule 9: I won't auto-flip; your go.")
    if ev["kind"] == "UPGRADED":
        return f"{head} Capital-scaling now **LICENSED**, not just flip-eligible. {wps}."
    if ev["kind"] == "RE-BLOCKED":
        return f"{head} **HOLD** {wps}; do not add size into the drawdown."
    if ev["kind"] == "DOWNGRADED":
        return f"{head} Still flip-eligible but the capital-scale license lapsed; size conservatively. {wps}."
    return head


def _user_mention() -> str:
    if not CFG.exists():
        return ""
    try:
        cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:
        return ""


def _queue(content: str) -> None:
    row = {"queued_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "content": _user_mention() + content}
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _write_status(run_date: str, lines: list[str]) -> None:
    """Idempotently prepend a LICENSE-MONITOR wake-block to STATUS.md (OP-25 signal)."""
    import re as _re
    block = (f"## [{run_date}] LICENSE-MONITOR (deploy-timing for WP-5/6/8/0)\n\n"
             + "\n".join(f"> - {ln}" for ln in lines)
             + "\n> - Files: `automation/state/license-monitor-last.json`, "
               "`backtest/autoresearch/license_monitor.py`.\n\n---\n\n")
    existing = STATUS_MD.read_text(encoding="utf-8") if STATUS_MD.exists() else ""
    existing = _re.sub(r"## \[[^\]]*\] LICENSE-MONITOR \(deploy-timing[^\n]*\).*?\n---\n\n",
                       "", existing, flags=_re.DOTALL)
    STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
    STATUS_MD.write_text(block + existing, encoding="utf-8")


def _refresh_recency() -> None:
    """Re-invoke recency_check.py (same interpreter) to refresh the verdicts on the latest cache."""
    try:
        subprocess.run([sys.executable, str(RECENCY_PY)], cwd=str(ROOT),
                       check=True, capture_output=True, text=True, timeout=900)
    except Exception as e:  # noqa: BLE001 — fail-loud, then fall back to existing JSON (OP-25)
        print(f"[license-monitor] WARN recency refresh failed ({e}); using existing JSON", flush=True)


def run(*, refresh: bool, announce_baseline: bool, force_ping: bool, dry_run: bool) -> dict:
    if refresh:
        _refresh_recency()
    if not RECENCY_JSON.exists():
        print(f"[license-monitor] no recency JSON at {RECENCY_JSON} — run with --run first", flush=True)
        return {"ok": False, "reason": "no recency json"}

    data = json.loads(RECENCY_JSON.read_text(encoding="utf-8"))
    cur = data.get("headline", {}).get("live_tier_verdicts", {})
    run_date = data.get("run_date", dt.date.today().isoformat())

    prev_snap = json.loads(SNAP.read_text(encoding="utf-8")) if SNAP.exists() else None
    prev = prev_snap.get("live_tier_verdicts") if prev_snap else None

    events = diff_tiers(prev, cur)

    out_lines: list[str] = []
    if events:
        for ev in events:
            msg = message_for(ev, _recent_exp(data, ev["tier"]))
            out_lines.append(msg)
            print(msg, flush=True)
            if not dry_run:
                _queue(msg)
    elif prev is None:
        base = (f"baseline recorded: "
                + "; ".join(f"{t}={v}({classify(v)})" for t, v in cur.items()))
        print(f"[license-monitor] {base}", flush=True)
        if announce_baseline and not dry_run:
            _queue(f"\U0001F4DD **LICENSE-MONITOR armed** — {base}. I'll ping the day a tier flips.")
    else:
        standing = "; ".join(f"{t}={v}({classify(v)})" for t, v in cur.items())
        print(f"[license-monitor] no transition. standing: {standing}", flush=True)
        if force_ping and not dry_run:
            _queue(f"\U0001F4CD **LICENSE-MONITOR standing** ({run_date}): {standing}. No change.")

    if (events or force_ping) and not dry_run:
        _write_status(run_date, out_lines or
                      ["; ".join(f"{t}={v}({classify(v)})" for t, v in cur.items())])

    if not dry_run:
        SNAP.write_text(json.dumps({
            "checked_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "recency_run_date": run_date,
            "live_tier_verdicts": cur,
        }, indent=2), encoding="utf-8")

    return {"ok": True, "events": events, "current": cur, "run_date": run_date}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true",
                    help="refresh recency verdicts (re-invoke recency_check.py) before diffing")
    ap.add_argument("--announce-baseline", action="store_true",
                    help="on first run (no prior snapshot), emit a one-time 'armed' ping")
    ap.add_argument("--force-ping", action="store_true",
                    help="emit a standing-state ping even with no transition")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print only; never queue Discord / touch STATUS / persist snapshot")
    args = ap.parse_args()
    res = run(refresh=args.run, announce_baseline=args.announce_baseline,
              force_ping=args.force_ping, dry_run=args.dry_run)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
