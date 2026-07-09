"""engine_contract.py -- T1, HANDOFF-2026-07-10-ENTRY-EXIT-MATRIX.

Auto-generate `automation/state/engine-contract.md` -- the ONE-SCREEN answer to J's
standing question "I don't know what the engine is taking right now" (OP-33(e): a
repeated question is a missing instrument, so BUILD the standing surface that retires it).

The card is DERIVED, never hand-written: it IMPORTS the live sources of truth
(accounts.json arms, strategies.py ExitShapes, params.json / aggressive/params.json
control configs, cap_admission tier tables) and renders them. Because it reads the SAME
objects the engine trades, any code/params change that is NOT followed by a regeneration
leaves the committed card stale -- which the drift guard (test_engine_contract_drift.py)
turns RED. That is the whole design: the card cannot silently lie.

`render_contract()` is DETERMINISTIC (no timestamps, no now()) so the drift guard is a
plain string-equality check: regenerate in memory, compare to the committed file. A diff
means either (a) someone edited a source without regenerating, or (b) someone hand-edited
the card. Both are drift; both are RED.

Regenerated on every Gamma_FirmBrief fire (folded into firm_brief.main via
write_engine_contract()). Pure stdlib -- runs on system python, no backtest venv, no network.

Usage:
    python setup/scripts/engine_contract.py            # write the card
    python setup/scripts/engine_contract.py --check     # exit 1 if the committed card is stale
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
ACCOUNTS = FLEET / "accounts.json"
STRATEGIES_PY = FLEET / "strategies.py"
SAFE_PARAMS = REPO / "automation" / "state" / "params.json"
BOLD_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"
OUT = REPO / "automation" / "state" / "engine-contract.md"


# --- source loaders (import the REAL objects so drift is detectable) ----------------------

def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _import_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_strategies():
    """Import automation/state/fleet/strategies.py (pure stdlib module)."""
    return _import_module("_ec_strategies", STRATEGIES_PY)


def _load_cap_tables() -> dict:
    """Import backtest/lib/cap_admission -- the SINGLE source of the sizing tables. We import
    the module (never re-type the literals) so a table edit shows up in the card and the
    drift guard catches an un-regenerated card. cap_admission -> risk_gate are pure stdlib.

    Uses import_module (the standard cache) rather than a fresh spec-load so we reuse any
    already-imported `lib.cap_admission` under pytest instead of clobbering sys.modules."""
    import importlib
    bt = REPO / "backtest"
    if str(bt) not in sys.path:
        sys.path.insert(0, str(bt))
    cap = importlib.import_module("lib.cap_admission")
    return {
        "SAFE_TIERS": cap.SAFE_MAX_PREMIUM_TIERS,
        "BOLD_TIERS": cap.BOLD_MAX_PREMIUM_TIERS,
        "SAFE_RISK_CAP": cap.SAFE_RISK_CAP,
        "BOLD_RISK_CAP": cap.BOLD_RISK_CAP,
        "SAFE_MIN_CONTRACTS": cap.SAFE_MIN_CONTRACTS,
        "BOLD_MIN_CONTRACTS": cap.BOLD_MIN_CONTRACTS,
    }


# --- formatting helpers -------------------------------------------------------------------

def _g(d: dict, key: str, default: str = "—") -> Any:
    """Read a param; if absent, return a visible marker (never fabricate a value)."""
    v = d.get(key)
    return default if v is None else v


def _pct(x: Any) -> str:
    try:
        return f"{float(x) * 100:.0f}%"
    except (TypeError, ValueError):
        return str(x)


def _shape_str(shape: dict) -> str:
    """Compact one-line exit-shape signature: stop / tp1 / sell-frac / lock / runner / trail / arm."""
    return (f"stop {_pct(shape['premium_stop_pct'])} · "
            f"TP1 +{_pct(shape['tp1_premium_pct'])} · "
            f"sell {_pct(shape['tp1_qty_fraction'])} · "
            f"{shape['profit_lock_mode']} · "
            f"runner {shape.get('runner_target_pct', '—')}x · "
            f"trail {_pct(shape.get('trail_pct', 0))} · "
            f"arm +{_pct(shape.get('profit_lock_arm_pct', 0))}")


def _gate_str(arm: dict) -> str:
    ov = arm.get("gate_override") or {}
    if not ov:
        return "base (production default)"
    bits = []
    if "min_triggers" in ov:
        bits.append(f"min_triggers={ov['min_triggers']}")
    if ov.get("require_confluence_or_sequence"):
        bits.append("confluence/sequence")
    return ", ".join(bits) if bits else json.dumps(ov)


def _strike_str(arm: dict) -> str:
    patch = arm.get("params_patch") or {}
    if patch.get("strike_tier_table") == "bold":
        return "bold tier table (patch)"
    cs = arm.get("config_source", "")
    if "aggressive" in cs:
        return "bold params.json"
    if "inherit bold" in cs:
        return "inherit bold"
    if "params.json" in cs:
        return "safe params.json v15 tier"
    return patch.get("strike_tier_table", "v15 tier")


# --- the renderer (DETERMINISTIC -- no timestamps) ----------------------------------------

def render_contract() -> str:
    accounts = _load_json(ACCOUNTS)
    strat = _load_strategies()
    caps = _load_cap_tables()
    safe = _load_json(SAFE_PARAMS)
    bold = _load_json(BOLD_PARAMS)

    L: list[str] = []
    L.append("# ENGINE CONTRACT — what the engine is actually taking right now")
    L.append("")
    L.append("> AUTO-GENERATED from code+params by `setup/scripts/engine_contract.py`. "
             "**Do not hand-edit** — regenerated every Gamma_FirmBrief fire; a diff here "
             "means a source changed (arms / strategies / params / cap tables). The drift "
             "guard `test_engine_contract_drift.py` RE-DERIVES this and REDs on any mismatch.")
    L.append("")
    L.append("Sources: `automation/state/fleet/accounts.json` (arms) · "
             "`automation/state/fleet/strategies.py` (exit shapes) · "
             "`automation/state/params.json` + `automation/state/aggressive/params.json` "
             "(control configs) · `backtest/lib/cap_admission.py` (sizing tables).")
    L.append("")

    # ── 1. ARMS ──────────────────────────────────────────────────────────────────────────
    L.append("## 1. Arms (an account is a sizing×gate profile, NOT a strategy)")
    L.append("")
    L.append("Every validated strategy in §2 runs on EVERY active arm via `fleet_executor.plan_all`. "
             "The arm only sets gate-strictness and position size.")
    L.append("")
    L.append("| arm | cell | execution | live | gate | strike | note |")
    L.append("|---|---|---|---|---|---|---|")
    spy_arms = [a for a in accounts["arms"] if a.get("instrument") == "SPY_0DTE_OPTION"]
    for a in spy_arms:
        live = "✅" if (a.get("live") or a.get("execution") == "mcp_heartbeat") else "—"
        control = " **(CONTROL)**" if "CONTROL" in (a.get("note", "")) else ""
        L.append(f"| `{a['id']}`{control} | {a.get('cell', '—')} | {a.get('execution', '—')} "
                 f"| {live} | {_gate_str(a)} | {_strike_str(a)} | {a.get('status', '—')} |")
    futures = [a for a in accounts["arms"] if a.get("instrument", "").startswith("M")]
    if futures:
        fnames = ", ".join(f"`{a['id']}` ({a.get('status', '?')})" for a in futures)
        L.append("")
        L.append(f"Futures arms (not in the SPY 0DTE loop): {fnames}.")
    L.append("")

    # ── 2. STRATEGIES + EXIT SHAPES ────────────────────────────────────────────────────────
    L.append("## 2. Strategies + their proven exit shapes (fleet_rest arms)")
    L.append("")
    L.append("The exit shape is a property of the STRATEGY (the grind proved it), realized by the "
             "live `exit_manager`. Fleet_rest arms (safe-1/safe-3/risky-1/risky-3) trade these shapes.")
    L.append("")
    L.append("| strategy | entry setups | exit shape |")
    L.append("|---|---|---|")
    for s in strat.REGISTRY:
        setups = "<br>".join(s.entry_setups)
        L.append(f"| `{s.name}` | {setups} | {_shape_str(s.exit.to_dict())} |")
    L.append("")
    L.append("Direction: both — the side comes from which side-block (bull/bear) fired; "
             f"`enable_bullish={_g(safe, 'enable_bullish')}` (safe). No per-strategy direction lock.")
    L.append("")

    # ── 3. CONTROL ARMS: what the two heartbeat controls trade (params.json shapes) ─────────
    L.append("## 3. Control arms (mcp_heartbeat) — traded from params.json, NOT strategies.py")
    L.append("")
    L.append("`safe-2` and `bold-2` are the production controls the grid is measured against. "
             "They trade the params.json bracket directly (the fleet_rest shapes in §2 are the challengers).")
    L.append("")
    L.append("| control | source | stop | TP1 | sell frac | runner | time-stop |")
    L.append("|---|---|---|---|---|---|---|")
    L.append(f"| `safe-2` | params.json | {_pct(_g(safe, 'premium_stop_pct'))} "
             f"| +{_pct(_g(safe, 'tp1_premium_pct'))} | {_pct(_g(safe, 'tp1_qty_fraction'))} "
             f"| {_g(safe, 'runner_max_premium_pct')}x | {_g(safe, 'time_stop_et')} ET |")
    L.append(f"| `bold-2` | aggressive/params.json | {_pct(_g(bold, 'premium_stop_pct'))} "
             f"| +{_pct(_g(bold, 'tp1_premium_pct'))} | {_pct(_g(bold, 'tp1_qty_fraction'))} "
             f"| {_g(bold, 'runner_max_premium_pct')}x | {_g(bold, 'time_stop_et')} ET |")
    L.append("")

    # ── 4. SIZING MATH (cap_admission — the single authority) ───────────────────────────────
    L.append("## 4. Sizing math (risk_gate.check_order — the single order authority)")
    L.append("")
    L.append(f"- **Per-trade risk cap:** Safe {_pct(caps['SAFE_RISK_CAP'])} · "
             f"Bold {_pct(caps['BOLD_RISK_CAP'])} of equity (notional = premium×qty×100).")
    L.append(f"- **Min contracts:** Safe {caps['SAFE_MIN_CONTRACTS']} · Bold {caps['BOLD_MIN_CONTRACTS']} "
             f"(below floor = hard DENY, never auto-reduced).")
    L.append("- **v15 per-tier max-premium (the usually-binding cap; tighter of this and risk cap):**")
    L.append("")
    L.append("| equity band | Safe max% | Bold max% |")
    L.append("|---|---|---|")
    for st, bt_ in zip(caps["SAFE_TIERS"], caps["BOLD_TIERS"]):
        lo, hi = st["equity_min"], st["equity_max"]
        band = f"${lo:,}–${hi:,}" if hi < 999_999_999 else f"${lo:,}+"
        L.append(f"| {band} | {_pct(st['max_pct'])} | {_pct(bt_['max_pct'])} |")
    L.append("")
    tiers = _g(safe, "v15_strike_offset_per_tier", None)
    if isinstance(tiers, list):
        L.append("- **v15 strike ladder (safe params, negative=OTM in live convention):** "
                 + " · ".join(f"${t.get('equity_min', '?'):,}+ → {t.get('label', t.get('strike_offset'))}"
                              for t in tiers))
        L.append("")

    # ── 5. HARD FLOORS: kill switches + time stops + PDT ────────────────────────────────────
    L.append("## 5. Hard floors (always bind, every arm)")
    L.append("")
    L.append(f"- **Kill switch (Rule 5, per-account ISOLATED):** Safe "
             f"−{_pct(_g(safe, 'daily_loss_kill_switch_pct'))} · Bold "
             f"−{_pct(_g(bold, 'daily_loss_kill_switch_pct'))} of start-of-day equity. "
             f"Safe halting does NOT halt Bold.")
    L.append(f"- **Time stop (in-engine):** Safe {_g(safe, 'time_stop_et')} ET · "
             f"Bold {_g(bold, 'time_stop_et')} ET. **EOD-flatten backstop:** 15:55 ET "
             f"(Gamma_EodFlatten closes any 0DTE not out by 15:50).")
    L.append("- **PDT (Rule 7):** ≥3 day-trades in rolling 5 business days AND equity <$25K → deny.")
    L.append("- **Flat-before-entry (Rule 4 / C11):** any open position blocks a NEW entry.")
    L.append("")

    L.append("---")
    L.append("_One screen. If a number here looks wrong, the SOURCE is wrong — fix the source and "
             "regenerate; do not edit this file._")
    return "\n".join(L) + "\n"


def write_engine_contract() -> Path:
    """Render + write the card. Called by firm_brief.main (folded into Gamma_FirmBrief)."""
    OUT.write_text(render_contract(), encoding="utf-8")
    return OUT


def main() -> int:
    if "--check" in sys.argv:
        if not OUT.exists():
            print(f"[engine_contract] STALE: {OUT} does not exist — run without --check to generate.",
                  file=sys.stderr)
            return 1
        committed = OUT.read_text(encoding="utf-8")
        fresh = render_contract()
        if committed != fresh:
            print(f"[engine_contract] DRIFT: committed {OUT.name} differs from a fresh render "
                  f"(a source changed without regeneration). Run: python setup/scripts/engine_contract.py",
                  file=sys.stderr)
            return 1
        print(f"[engine_contract] OK: {OUT.name} matches code+params (no drift).")
        return 0
    p = write_engine_contract()
    print(f"[engine_contract] wrote {p} ({len(p.read_text(encoding='utf-8').splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
