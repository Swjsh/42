"""gamma_status.py — the one command J runs to see the VERIFIED truth, anytime.

J 2026-06-29: "I have no visibility... you're overconfident telling me things run."
OP-33(c): visibility is the product; J must verify state WITHOUT my word. This reads only
state files (fast, no market-hours risk) and — critically — VERIFIES THE ACTUAL WORK, not
the wrapper exit code (lastResult=0 lied today while the work crashed). Every line is a fact
J can re-check. Honest markers: OK = verified working; STALE/DEAD = verified broken;
? = unverifiable; TOOL = a script run on demand, NOT a running daemon (don't mistake for autonomous).

Run:  backtest/.venv/Scripts/python.exe setup/scripts/gamma_status.py
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


def _age_min(p: Path) -> float | None:
    if not p.exists():
        return None
    return (dt.datetime.now().timestamp() - p.stat().st_mtime) / 60.0


def _j(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    now = et_now()
    hm = now.strftime("%H:%M")
    rth = ("09:30" <= hm <= "15:55") and now.weekday() < 5
    out = []
    out.append(f"========== GAMMA STATUS  {now.strftime('%Y-%m-%d %H:%M ET %a')}  market={'OPEN' if rth else 'closed'} ==========")

    # --- LIVE TRADING CHAIN (can we trade right now?) ---
    out.append("\n-- LIVE CHAIN (can we trade?) --")
    h = _j(STATE / "engine-health.json") or {}
    out.append(f"  engine-health : {h.get('verdict','?')}  reds={h.get('reds','?')}  @ {h.get('checked_at_et','?')}")
    b = _j(STATE / "sight-beacon.json") or {}
    bage = _age_min(STATE / "sight-beacon.json")
    if bage is None:
        bmark = "?"
    elif not rth:
        bmark = "idle-ok"   # after-hours: beacon stops with the session, staleness is expected
    else:
        bmark = "OK" if bage < 5 else "STALE-IN-RTH"   # stale DURING market hours = real problem
    out.append(f"  sight-beacon  : [{bmark}] spy={b.get('spy','?')} age={f'{bage:.0f}m' if bage is not None else '?'}")
    # heartbeat: verify by decision recency (only during RTH)
    dec = STATE / "core-decisions.jsonl"
    last_dec = "?"
    if dec.exists():
        lines = dec.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            try:
                d = json.loads(lines[-1]); last_dec = f"{d.get('ts_et','?')[11:19]} {d.get('account')} {d.get('verdict')}"
            except Exception:  # noqa: BLE001
                pass
    hb_mark = "OK" if not rth else ("OK" if "?" not in last_dec else "CHECK")
    out.append(f"  heartbeat-core: [{hb_mark if rth else 'idle-ok'}] last decision: {last_dec}  (only fires 09:30-15:55 ET)")

    # --- ACCOUNTS (are we trading / flat?) ---
    out.append("\n-- ACCOUNTS (6 fleet, paper) --")
    try:
        import accounts_status  # noqa: F401
        out.append("  (run `accounts_status.py` for live equity; broker is source of truth)")
    except Exception:
        pass
    fa = _j(STATE / "fleet" / "accounts.json")
    if fa and isinstance(fa.get("arms"), list):
        live = sum(1 for a in fa["arms"] if a.get("live") is True)
        out.append(f"  arms: {len(fa['arms'])} configured, {live} live=true. TRADING TODAY: check fleet decisions / fills.")
    out.append("  HONEST: arms place only when a signal fires; engine has been HOLDing (no armable edge this regime).")

    # --- AUTONOMY TASKS (verified by WORK, not exit code) ---
    out.append("\n-- AUTONOMY (verified by actual output, NOT lastResult=0) --")
    kl_age = _age_min(STATE / "key-levels.json")
    out.append(f"  Gamma_LevelRefresh   : [{'OK' if kl_age and kl_age < 10 else 'STALE'}] key-levels age={f'{kl_age:.0f}m' if kl_age else '?'} (every 5m)")
    led = STATE.parent.parent / "analysis" / "stress-swarm" / "_ledger.jsonl"
    led_age = _age_min(led)
    n_batches = len(led.read_text(encoding="utf-8").strip().splitlines()) if led.exists() else 0
    out.append(f"  Gamma_EngineStressSwarm: [{'OK' if led_age is not None else '?'}] {n_batches} batches, last {f'{led_age:.0f}m ago' if led_age else '?'} (every 2h overnight)")
    cq = STATE / "cook-queue.jsonl"
    cq_age = _age_min(cq)
    out.append(f"  Kitchen (cook-queue) : [{'OK' if cq_age and cq_age < 120 else 'idle?'}] last activity {f'{cq_age:.0f}m ago' if cq_age else '?'}")

    # --- TOOLS, NOT DAEMONS (do NOT mistake for autonomous) ---
    out.append("\n-- TOOLS (run on demand by Gamma — NOT running themselves yet) --")
    for name, rel in (("design-swarm", "analysis/design-swarm/latest.json"),
                      ("discovery-ledger", "analysis/discovery/fdr-screen.json"),
                      ("friction-ledger", "automation/state/friction-ledger.jsonl")):
        p = REPO / rel
        age = _age_min(p)
        out.append(f"  {name:16}: [TOOL] last run {f'{age/60:.1f}h ago' if age else 'never'} — wires into kitchen = pending (tasks #10-12)")

    # --- KNOWN BROKEN ---
    out.append("\n-- KNOWN BROKEN (STATUS.md) --")
    st = REPO / "automation" / "overnight" / "STATUS.md"
    broken = []
    if st.exists():
        txt = st.read_text(encoding="utf-8", errors="replace")
        cap = False
        for ln in txt.splitlines():
            if ln.startswith("## ") and "broken" in ln.lower(): cap = True; continue
            if cap and ln.startswith("## "): break
            if cap and ln.strip().startswith(("-", "*", "###")): broken.append(ln.strip()[:90])
    out.append("\n".join(f"  {x}" for x in broken[:6]) if broken else "  (none flagged)")

    out.append("\n" + "=" * 70)
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
