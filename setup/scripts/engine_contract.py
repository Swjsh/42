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
HEARTBEAT_CORE = REPO / "setup" / "scripts" / "heartbeat_core.py"
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


def _load_setup_exit_overrides() -> dict:
    """Extract heartbeat_core._SETUP_EXIT_OVERRIDES from SOURCE via ast (never import --
    heartbeat_core has heavy/live-path imports; the card generator must stay side-effect-free).
    Returns {} if the assignment can't be found/parsed (the card then omits that table, and
    the drift guard still binds on everything else)."""
    import ast
    try:
        tree = ast.parse(HEARTBEAT_CORE.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_SETUP_EXIT_OVERRIDES":
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        return {}
    return {}


def _load_per_band_stop():
    """Import automation/state/fleet/per_band_stop.py (T-W4, exit-B's machinery -- SHADOW
    ONLY, pure stdlib module, no arm consumes it)."""
    return _import_module("_ec_per_band_stop", FLEET / "per_band_stop.py")


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

    # ── 3. CONTROL ARMS: what the two heartbeat controls ACTUALLY trade ─────────────────────
    # Fable review 2026-07-08: options can't bracket (Alpaca 42210000), so the params tp/stop
    # numbers are PLAN-LOG values, not broker legs. With GAMMA_CORE_MANAGES_EXITS=1 (set by
    # run-heartbeat-core.ps1:12 = production), the exit_manager owns exits, and for generic
    # ribbon setups it registers the strategies.py ribbon_ride shape (heartbeat_core ~L1230).
    L.append("## 3. Control arms (mcp_heartbeat) — what they ACTUALLY trade")
    L.append("")
    L.append("Options can't bracket at Alpaca → entries are SIMPLE limits with **no broker-side "
             "TP/stop**; the `exit_manager` owns every exit (production sets "
             "`GAMMA_CORE_MANAGES_EXITS=1` in `run-heartbeat-core.ps1`). Which shape it runs:")
    L.append("")
    L.append("- **Generic ribbon setups** (BEARISH_REJECTION / BULLISH_RECLAIM): the control arms "
             "register **strategies.py `ribbon_ride`'s shape (§2)** with the exit_manager — the "
             "SAME shape the fleet_rest arms trade, NOT the params tp/stop below.")
    ovr = _load_setup_exit_overrides()
    if ovr:
        L.append("- **Per-setup isolated exits** (`_SETUP_EXIT_OVERRIDES`, heartbeat_core) — these "
                 "armed extra setups trade their OWN validated cells from params keys:")
        L.append("")
        L.append("| setup | stop | TP1 | extra knobs |")
        L.append("|---|--:|--:|---|")
        for name, keys in ovr.items():
            stop_v = safe.get(keys.get("stop", ""), "—")
            tp_v = safe.get(keys.get("tp1", ""), "—")
            extras = ", ".join(k for k in ("tq", "plmode", "trail", "runner") if keys.get(k))
            L.append(f"| `{name}` | {_pct(stop_v) if stop_v != '—' else '—'} "
                     f"| +{_pct(tp_v) if tp_v != '—' else '—'} | {extras or '—'} |")
        L.append("")
    L.append("- **params.json bracket values** (plan/log reference only — shown so drift is visible):")
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

    # ── 3b. ENTRY POLICY (the axis the ENTRY-EXIT-MATRIX studies; previously invisible) ─────
    L.append("## 3b. Entry policy (all arms — the current order type)")
    L.append("")
    buf = safe.get("entry_cross_buffer", 0.03)
    L.append(f"- **Marketable simple limit: `ask + entry_cross_buffer` (${float(buf):.2f})** — "
             f"`fleet_broker.marketable_limit_price` / `heartbeat_core` #15 pricing. Crosses the "
             f"spread to fill NOW (pays up into the signal bar).")
    # ENTRY-1 floor (2026-07-09, STOP-B ship 1) — rendered FROM params (never re-typed) so a
    # params edit without a card regen trips the drift guard. 0/absent renders as OFF.
    _mep_safe, _mep_bold = safe.get("min_entry_premium"), bold.get("min_entry_premium")

    def _floor_str(v) -> str:
        try:
            return f"${float(v):.2f}" if v is not None and float(v) > 0 else "OFF"
        except (TypeError, ValueError):
            return "OFF"
    if _floor_str(_mep_safe) == "OFF" and _floor_str(_mep_bold) == "OFF":
        L.append("- **No premium floor** — sub-$0.20 contracts are admitted (T2 diagnostics: "
                 "a −20% stop there = ~2 ticks ≈ the spread).")
    else:
        L.append(f"- **Premium floor `min_entry_premium`: safe {_floor_str(_mep_safe)} · "
                 f"bold {_floor_str(_mep_bold)}** — plan-time strategy admission in BOTH lanes "
                 f"(`heartbeat_core._execute` post-NO_PREMIUM; `fleet_executor.finalize` "
                 f"pre-check_order, shared by fleet_live decide_arm + run_dry). A sub-floor "
                 f"premium is a logged `SKIP_MIN_PREMIUM_FLOOR` row, never an order. Evidence: "
                 f"entry-exit-matrix-2026-07-09.md (T3 n=157; anchor −$72.50 vs −$757.10). "
                 f"0/absent = OFF.")
    L.append("- **No passive/patience logic** — no limit-below-signal, no cancel/convert window. "
             "(The T3 entry-matrix studies exactly this axis; nothing is wired yet.)")
    L.append("- Stale un-crossed BUY limits from a prior tick are cancel-replaced each tick.")
    L.append("")

    # ── 3c. SHADOW MACHINERY (built, NOT armed — rule 17: a knob that isn't on this card
    # doesn't exist, so both land here the moment they exist, before any arm consumes them) ──
    L.append("## 3c. Shadow machinery — built, NOT armed (T-W4/T-W5)")
    L.append("")
    L.append("Zero arms consume either module below. Both ship freely as observability per "
             "HANDOFF-2026-07-11-CONFIRM-AND-WIRE (shadow/paper work needs no STOP sign-off; "
             "ARMING either needs its own P5-survivor pass + STOP-B).")
    L.append("")
    pbs = _load_per_band_stop()
    L.append("- **exit-B per-band stop resolver** (`automation/state/fleet/per_band_stop.py`, "
             "`resolve_stop_pct`) — NOT ARMED. Pre-registered `EXIT_B_BAND_TABLE`:")
    _prev_ceiling = None
    for band in pbs.EXIT_B_BAND_TABLE:
        if band.ceiling is not None:
            label = f"<${band.ceiling:.2f}"
        else:
            label = f">=${_prev_ceiling:.2f}" if _prev_ceiling is not None else "any"
        L.append(f"  - premium {label} → stop {_pct(band.stop_pct)}")
        _prev_ceiling = band.ceiling
    L.append("")
    L.append("- **entry-2 passive-limit state machine** (`automation/state/fleet/"
             "entry_manager.py`, `plan_entry_action`) — NOT ARMED. Pre-registered spec: "
             "limit @ signal×(1−10%), patience 3 bars, miss=cancel.")
    # Fable review 2026-07-08: the shadow ledger's live STATS must NOT render here --
    # entry-shadow.jsonl is untracked runtime state, so embedding its numbers makes the
    # committed card differ from a fresh-clone render (CI drift-guard RED) and drift on
    # every backfill re-run. The card carries only committed-source facts; stats live in
    # the firm brief / the T-W5 report.
    L.append("  - Shadow ledger: `automation/state/entry-shadow.jsonl` (runtime state, "
             "regenerate via `backtest/tools/shadow_entry_backfill.py`; stats reported in "
             "the firm brief, not on this drift-guarded card).")
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
