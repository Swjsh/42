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
try:
    from arm_display import display_name_for_arm_id
except Exception:  # noqa: BLE001
    def display_name_for_arm_id(arm_id): return arm_id


def _age_min(p: Path) -> float | None:
    if not p.exists():
        return None
    return (dt.datetime.now().timestamp() - p.stat().st_mtime) / 60.0


def _j(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _structure_stop_glance(fa: dict | None) -> str:
    """VISIBILITY (2026-07-09, OP-33c/STOP-B first-live-day): 'EXIT MODE: structure (SS-B)
    since 2026-07-09; positions open under structure: N; last structure exit: <ts or none>'.
    Reads ONLY persisted state (exit-state.json per arm + the decision ledgers) -- same
    VERIFIED-not-CLAIMED discipline as every other line in this script. 0 open + 'none' is
    the HONEST, EXPECTED reading before the first real structure-mode fill ever lands."""
    arms = [a["id"] for a in (fa or {}).get("arms", [])
           if a.get("instrument") == "SPY_0DTE_OPTION"]
    n_structure = 0
    for arm_id in arms:
        est = _j(STATE / "fleet" / arm_id / "exit-state.json") or {}
        for pos in est.values():
            if isinstance(pos, dict) and pos.get("stop_mode") == "structure":
                n_structure += 1
    last_ts, last_sym = None, None
    paths = [STATE / "core-decisions.jsonl"] + [STATE / "fleet" / a / "decisions.jsonl" for a in arms]
    for p in paths:
        if not p.exists():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except OSError:
            continue
        for ln in lines[-3000:]:
            try:
                row = json.loads(ln)
            except (json.JSONDecodeError, ValueError):
                continue
            ts = row.get("ts_et")
            for ep in (row.get("exit_pass") or []):
                if not isinstance(ep, dict):
                    continue
                for act in (ep.get("actions") or []):
                    if isinstance(act, dict) and act.get("stage") == "structure_stop" \
                            and ts and (last_ts is None or ts > last_ts):
                        last_ts, last_sym = ts, ep.get("symbol")
    safe_flag = (_j(STATE / "params.json") or {}).get("structure_stop_enabled")
    bold_flag = (_j(STATE / "aggressive" / "params.json") or {}).get("structure_stop_enabled")
    flag_s = f"safe={'ON' if safe_flag else 'OFF'} bold={'ON' if bold_flag else 'OFF'}"
    last_s = f"{last_ts} {last_sym}" if last_ts else "none"
    return (f"  EXIT MODE: structure (SS-B) since 2026-07-09 [{flag_s}]; "
            f"positions open under structure: {n_structure}; last structure exit: {last_s}")


def _push_glance() -> list[str]:
    """PUSH block (2026-07-18, OP-33e): does the companion actually push to J's
    phone/watch, or does he have to keep asking "is it running"? Two-layer
    root cause found this fire: VAPID keys DO exist (generated 2026-06-21) so
    sendPush() is NOT silently disabled at that layer -- but
    push-subscriptions.json is `[]`, 27 days later. ZERO devices have ever
    subscribed. Per gamma-companion/MOBILE_PWA_DESIGN.md, Android Chrome
    refuses push/voice over plain http://192.168.x.x -- J needs an HTTPS
    front-door (Tailscale Serve is the documented path) + one
    Add-to-Home-Screen + one notification-permission grant on his phone.
    Physical device step only J can do; count-only read here, never prints
    endpoint/key content (push-subscriptions.json holds live push
    endpoints+keys per device)."""
    vapid_present = (STATE / ".vapid.json").exists()
    n_subs = 0
    try:
        n_subs = len(json.loads((STATE / "push-subscriptions.json").read_text(encoding="utf-8")) or [])
    except Exception:  # noqa: BLE001
        pass
    if not vapid_present:
        return [
            "  [DISABLED] .vapid.json absent -- sendPush() is a silent no-op",
            "  fix (J-only, one time): cd gamma-companion && node tools/gen-vapid.js",
        ]
    if n_subs > 0:
        return [f"  [OK] VAPID configured, {n_subs} device(s) subscribed -- pushes are live"]
    return [
        "  [DISABLED] VAPID configured but 0 devices subscribed -- nowhere to send",
        "  fix (J-only, one-time device setup, see gamma-companion/MOBILE_PWA_DESIGN.md):",
        "  1) expose the companion over HTTPS (Tailscale Serve is the documented path)",
        "  2) open it on your phone, Add to Home Screen, grant notification permission",
    ]


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
        # DISPLAY NAMES (2026-07-17): raw ids (safe-1/2/3, risky-1/3, bold-2) carry no meaning
        # on their own and safe-1/safe-2 share ONE broker account (KIQE) -- print id + the
        # accounts.json display_name (which embeds the account last-4) side by side so that
        # collision is visible at a glance instead of causing a double-count.
        for a in fa["arms"]:
            out.append(f"    - {a.get('id', '?'):<20} {display_name_for_arm_id(a.get('id', '')):<30} "
                       f"[{a.get('status', '?')}]")
    out.append("  HONEST: arms place only when a signal fires; engine has been HOLDing (no armable edge this regime).")

    # --- EXIT MODE (SS-B structure-stop, first live day 2026-07-09) ---
    out.append(_structure_stop_glance(fa))

    # --- PUSH (2026-07-18, OP-33e) ---
    out.append("\n-- PUSH (phone/watch) --")
    out.extend(_push_glance())

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
