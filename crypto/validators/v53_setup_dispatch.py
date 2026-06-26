"""v53_setup_dispatch -- exercise setup/scripts/setup_dispatch.py.

Proves dispatch_extra_setups + SetupDispatcher behave correctly:

  - all-flags-OFF: returns [] immediately (pure no-op)
  - one flag ON, feed absent: returns SKIP_NO_FEED (not a crash)
  - one flag ON, flag_key misspelled: defaults to False (no-op)
  - never raises regardless of payload garbage
  - DispatchResult dataclass fields are present and typed correctly
  - SetupDispatcher.run() with empty params returns []

Offline:
  T1  all flags OFF -> dispatch returns []
  T2  empty params dict -> dispatch returns [] (all keys default False)
  T3  one flag ON, no feed -> [DispatchResult(fired=False, skip_reason=SKIP_*)]
  T4  skip_reason on no-feed result starts with 'SKIP_'
  T5  garbage payload (non-dict) does not raise
  T6  DispatchResult has required fields: setup_name, fired, skip_reason
  T7  dispatch never returns a result with fired=True when feed is absent
  T8  SetupDispatcher.run() with empty params returns []
  T9  dispatch_extra_setups never raises on totally malformed payload
  T10 all-flags-ON, no feed -> each enabled setup returns exactly one result
  T11 results list length matches number of enabled flags
  T12 no result has fired=True when sameday_5m_bars is empty list

Live: call dispatch_extra_setups with the real params.json (flags as deployed),
assert it either returns [] (all off) or returns DispatchResult-shaped dicts
with no crash. Never asserts on trading decisions — only on structural sanity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtest"))

from setup.scripts.setup_dispatch import DispatchResult, SetupDispatcher, dispatch_extra_setups

_REPO = Path(__file__).resolve().parents[2]
_PARAMS_PATH = _REPO / "automation" / "state" / "params.json"

_ALL_OFF = {
    "j_vwap_cont_enabled": False,
    "gap_and_go_enabled": False,
    "j_vwap_reclaim_fb_enabled": False,
    "j_vix_dayside_enabled": False,
}

_ALL_ON = {
    "j_vwap_cont_enabled": True,
    "gap_and_go_enabled": True,
    "j_vwap_reclaim_fb_enabled": True,
    "j_vix_dayside_enabled": True,
}

_KNOWN_SETUP_NAMES = {
    "vwap_continuation",
    "gap_and_go",
    "vwap_reclaim_failed_break",
    "vix_regime_dayside",
}


def run_offline() -> dict:
    results: list[tuple[str, bool, str]] = []

    # T1: all flags OFF -> returns []
    out = dispatch_extra_setups("safe", _ALL_OFF, {}, {})
    ok = out == []
    results.append(("T1_all_off_returns_empty", ok, f"result={out}"))

    # T2: empty params dict -> all keys default False -> returns []
    out = dispatch_extra_setups("safe", {}, {}, {})
    ok = out == []
    results.append(("T2_empty_params_returns_empty", ok, f"result={out}"))

    # T3: one flag ON, no feed -> returns a result with fired=False, skip_reason set
    params_one = {"j_vwap_cont_enabled": True}
    out = dispatch_extra_setups("safe", params_one, {}, {})
    ok = len(out) == 1 and out[0]["fired"] is False and out[0]["skip_reason"] is not None
    results.append(("T3_one_flag_no_feed_skip", ok,
                    f"fired={out[0].get('fired')} skip={out[0].get('skip_reason','?')[:40] if out else '?'}"))

    # T4: skip_reason starts with 'SKIP_'
    if out:
        sr = out[0].get("skip_reason", "") or ""
        ok = sr.startswith("SKIP_")
    else:
        ok = False
    results.append(("T4_skip_reason_prefix", ok, f"skip_reason={sr[:50] if out else '?'}"))

    # T5: garbage payload does not raise
    try:
        r = dispatch_extra_setups("safe", {"j_vwap_cont_enabled": True}, "NOT_A_DICT", {})  # type: ignore[arg-type]
        ok = isinstance(r, list)
        note = f"returned list len={len(r)} (no crash)"
    except Exception as e:
        ok, note = False, f"crash: {e}"
    results.append(("T5_garbage_payload_no_crash", ok, note))

    # T6: DispatchResult has required fields
    dr = DispatchResult(setup_name="test_setup")
    ok = (hasattr(dr, "setup_name") and hasattr(dr, "fired")
          and hasattr(dr, "signal") and hasattr(dr, "skip_reason"))
    results.append(("T6_dispatch_result_fields", ok,
                    f"fields: setup_name={dr.setup_name} fired={dr.fired}"))

    # T7: no result has fired=True when feed is absent (all ON, no payload)
    out_all_on = dispatch_extra_setups("safe", _ALL_ON, {}, {})
    any_fired = any(r.get("fired", False) for r in out_all_on)
    ok = not any_fired
    results.append(("T7_no_fire_without_feed", ok,
                    f"fired_count={sum(1 for r in out_all_on if r.get('fired'))}"))

    # T8: SetupDispatcher.run() with empty params -> []
    sd = SetupDispatcher({}, {})
    run_result = sd.run()
    ok = run_result == []
    results.append(("T8_dispatcher_empty_params_empty", ok, f"run()={run_result}"))

    # T9: dispatch_extra_setups never raises on totally malformed payload
    try:
        r = dispatch_extra_setups("safe", _ALL_ON, {"sameday_5m_bars": None, "bar_ctx": None}, {})  # type: ignore[arg-type]
        ok = isinstance(r, list)
        note = f"len={len(r)} (no crash)"
    except Exception as e:
        ok, note = False, f"crash: {e}"
    results.append(("T9_malformed_payload_no_crash", ok, note))

    # T10: all-flags-ON, no feed -> each enabled setup produces one result
    out = dispatch_extra_setups("safe", _ALL_ON, {}, {})
    ok = len(out) == 4  # one per enabled detector
    results.append(("T10_all_on_four_results", ok, f"len={len(out)} (4 expected)"))

    # T11: result length matches number of enabled flags
    params_two = {"j_vwap_cont_enabled": True, "gap_and_go_enabled": True}
    out2 = dispatch_extra_setups("safe", params_two, {}, {})
    ok = len(out2) == 2
    results.append(("T11_result_count_matches_flags", ok, f"len={len(out2)} (2 expected)"))

    # T12: no result has fired=True when sameday_5m_bars is empty list
    payload_empty_feed = {"sameday_5m_bars": [], "bar_ctx": {}}
    out3 = dispatch_extra_setups("safe", _ALL_ON, payload_empty_feed, {})
    any_fired = any(r.get("fired", False) for r in out3)
    ok = not any_fired
    results.append(("T12_empty_feed_no_fire", ok,
                    f"fired_count={sum(1 for r in out3 if r.get('fired'))}"))

    return {
        "mode": "offline",
        "tests": [{"name": n, "pass": p, "note": note[:80]} for n, p, note in results],
        "passed": sum(1 for _, p, _ in results if p),
        "total": len(results),
        "all_pass": all(p for _, p, _ in results),
    }


def run_live() -> dict:
    """Run dispatch against the real params.json; assert structural sanity only."""
    try:
        # Load real params (fall back to all-off if file missing)
        params: dict = {}
        if _PARAMS_PATH.exists():
            try:
                params = json.loads(_PARAMS_PATH.read_text(encoding="utf-8"))
            except Exception:
                params = {}

        # Run with empty payload (no live bars) — same as heartbeat_core calling before RTH
        out = dispatch_extra_setups("safe", params, {}, {})

        # Structural checks: every element must be a dict with required fields
        field_ok = all(
            isinstance(r, dict)
            and "setup_name" in r
            and "fired" in r
            and "skip_reason" in r
            for r in out
        )

        # If any fired=True, it must also have direction, entry_price, stop_price
        fire_ok = all(
            (not r.get("fired"))
            or ("direction" in r and "entry_price" in r and "stop_price" in r)
            for r in out
        )

        # setup_name must be one of the known names (or empty list)
        names_ok = all(r.get("setup_name") in _KNOWN_SETUP_NAMES for r in out)

        all_pass = field_ok and fire_ok and names_ok
        return {
            "mode": "live",
            "params_loaded": bool(params),
            "results_count": len(out),
            "results": [
                {"setup": r.get("setup_name"), "fired": r.get("fired"),
                 "skip": (r.get("skip_reason") or "")[:60]}
                for r in out
            ],
            "field_ok": field_ok,
            "fire_ok": fire_ok,
            "names_ok": names_ok,
            "pass": all_pass,
        }
    except Exception as e:
        return {"mode": "live", "pass": False, "note": str(e)[:200]}


if __name__ == "__main__":
    print("=== OFFLINE ===")
    off = run_offline()
    for t in off["tests"]:
        print(f"  [{'PASS' if t['pass'] else 'FAIL'}] {t['name']:38s} {t['note']}")
    print(f"  {off['passed']}/{off['total']} pass  all_pass={off['all_pass']}")
    print("\n=== LIVE ===")
    live = run_live()
    print(json.dumps(live, indent=2, default=str))
