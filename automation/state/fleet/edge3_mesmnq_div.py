"""EDGE #3 — MES->MNQ divergence catch-up (futures), FROZEN CONFIG, DORMANT.

WHAT THIS IS
------------
The validated B5 "concentration rescue" of the B4 MES->MNQ lead-lag divergence edge,
packaged as a FROZEN-CONFIG fleet arm for the futures paper track. It is REGISTERED
but DORMANT — `FROZEN_CONFIG.enabled is False` — so it never auto-trades until a
human flips it on. There is NO live order path in this module; `signal_for_tick`
emits a pure decision object only.

VALIDATED CELL (the ONLY cell that cleared all 8 gates — analysis/recommendations/
b5-mesmnq-div-rescue.json :: best_cell):
    config        = MES leads -> trade MNQ laggard
    threshold     = 0.0015 (normalized-return spread r_MES - r_MNQ)
    fix           = d_persistence, knob n2  (divergence must HOLD >= 2 consecutive
                    closed bars before entry — the concentration fix that lifts
                    drop-top5 per-trade from -$4.70 to +$3.65)
    OOS per-trade = +$71.46  (n=118, drop-top5 +$3.65, top5_day_pct 92.4%, 8/8 gates)
    instrument    = MNQ micro, point-P&L, ATR-trail stop + EOD-flat
    qty           = 1 micro

NO DRIFT (the #1 foot-gun): this module does NOT re-implement the signal, the
persistence filter, the simulator, or the gates. It IMPORTS them byte-identical from
the proven research modules:
    backtest/autoresearch/_b4_mes_mnq_divergence.py  (detect_divergence, simulate, ...)
    backtest/autoresearch/_b5_mesmnq_div_rescue.py   (enrich_signals, fix_min_persistence)
So the live frozen config and the validated backtest are the SAME code. The only thing
defined here is the FROZEN KNOB VALUES + a dormant registration + a thin live-tick
adapter that reuses the imported detectors.

ISOLATION (the edge-#2 scar): the persistence-filter and threshold are ISOLATED, per-
edge keys carried on FROZEN_CONFIG (not a shared global), and the live-tick adapter
(`signal_for_tick`) READS those exact keys and applies `fix_min_persistence` to the
same enriched signals the backtest used. The dormant flag means nothing reads them for
a live order yet; when enabled, the order path MUST call `signal_for_tick` (which honors
min_persistence_bars) — verified by test_edge3_mesmnq_div.py.

Run the reproduction (proves the validated expectancy SIGN, pure Python, $0):
    backtest/.venv/Scripts/python.exe automation/state/fleet/edge3_mesmnq_div.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

# --- locate repo root + load the PROVEN research modules by absolute path (C9) ---
FLEET_DIR = Path(__file__).resolve().parent
REPO_ROOT = FLEET_DIR.parents[2]  # automation/state/fleet -> repo root
AUTORESEARCH = REPO_ROOT / "backtest" / "autoresearch"


def _load_module(modname: str, path: Path):
    """Load a module by absolute path, registering it so its own intra-package
    imports (b5 imports b4 by name) resolve. Anchored to __file__ (C9)."""
    if modname in sys.modules:
        return sys.modules[modname]
    if str(AUTORESEARCH) not in sys.path:
        sys.path.insert(0, str(AUTORESEARCH))
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise ImportError(f"cannot load {modname} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# Import the validated machinery byte-identical (no reimplementation -> no drift).
b4 = _load_module("_b4_mes_mnq_divergence", AUTORESEARCH / "_b4_mes_mnq_divergence.py")
b5 = _load_module("_b5_mesmnq_div_rescue", AUTORESEARCH / "_b5_mesmnq_div_rescue.py")


# --- the FROZEN CONFIG (the validated cell, isolated per-edge keys) -------------
@dataclass(frozen=True)
class FrozenConfig:
    """Immutable frozen knobs for EDGE #3. Per-edge ISOLATED keys (edge-#2 scar):
    the order path reads min_persistence_bars + threshold FROM HERE, never a shared
    global stop key."""

    edge_id: str
    arm_id: str
    enabled: bool                  # DORMANT until a human flips it on
    leader: str                    # instrument that must break first
    laggard: str                   # instrument we TRADE (the catch-up)
    threshold: float               # normalized-return spread r_lead - r_lag
    min_persistence_bars: int      # the validated concentration fix (>=2 closed bars)
    qty_micros: int
    exit_mode: str                 # "atr_trail" = chart-stop floor + ATR chandelier
    entry_cutoff: dt.time          # no catch-up entries after this (same-session edge)
    validated_oos_per_trade: float # disclosure: the gate-clearing OOS expectancy
    source_recommendation: str
    notes: str = ""


FROZEN_CONFIG = FrozenConfig(
    edge_id="edge3_mesmnq_div",
    arm_id="mes-mnq-div-futures",
    enabled=False,                 # <-- DORMANT. Do NOT enable here; a human flips this.
    leader="MES",
    laggard="MNQ",
    threshold=0.0015,
    min_persistence_bars=2,        # n2 — the ONLY cell that cleared all 8 gates
    qty_micros=1,
    exit_mode="atr_trail",
    entry_cutoff=b4.ENTRY_CUTOFF,  # 13:00 ET, from the proven module (no drift)
    validated_oos_per_trade=71.46,
    source_recommendation="analysis/recommendations/b5-mesmnq-div-rescue.json",
    notes=(
        "MES leads -> trade MNQ laggard; divergence must persist >=2 consecutive closed "
        "bars (concentration fix lifts drop-top5/tr to +$3.65). ATR-trail + EOD-flat, "
        "1 MNQ micro. Registered DORMANT; no live order path here."
    ),
)


# --- value type emitted by the live-tick adapter -------------------------------
@dataclass(frozen=True)
class Edge3Decision:
    edge_id: str
    arm_id: str
    enabled: bool
    action: str                    # "ENTER_LONG" | "ENTER_SHORT" | "HOLD"
    laggard: Optional[str]
    side: Optional[str]            # "long" | "short" | None
    entry_idx: Optional[int]       # global bar idx in the laggard df; fill NEXT bar open
    chart_stop: Optional[float]
    persistence: Optional[int]
    reason: str


def _hold(reason: str) -> Edge3Decision:
    return Edge3Decision(
        edge_id=FROZEN_CONFIG.edge_id, arm_id=FROZEN_CONFIG.arm_id,
        enabled=FROZEN_CONFIG.enabled, action="HOLD", laggard=None, side=None,
        entry_idx=None, chart_stop=None, persistence=None, reason=reason,
    )


# --- live-tick adapter: reuse the IMPORTED detectors, honor the frozen knobs ----
def signal_for_tick(
    lead_df: Any,
    lag_df: Any,
    *,
    as_of_date: dt.date,
    cfg: FrozenConfig = FROZEN_CONFIG,
) -> Edge3Decision:
    """Return today's EDGE #3 decision for `as_of_date`, applying the FROZEN persistence
    filter. Reuses b4.detect_divergence + b5.enrich_signals + b5.fix_min_persistence so
    the live read is the SAME code as the validated backtest.

    DORMANT: when cfg.enabled is False this still COMPUTES the decision (so a shadow/
    monitor can log it) but the action is forced to HOLD with a 'dormant' reason — there
    is no order path. Flipping cfg.enabled to True is the only thing that lets a caller
    act on ENTER, and even then the caller (not this module) places the order.

    Causal: only the named `as_of_date` session's bars are inspected; b4/b5 internals
    use closed-bar [.. signal] look-back only (no look-ahead)."""
    if cfg.leader != "MES" or cfg.laggard != "MNQ":  # defensive: frozen to the validated cell
        return _hold(f"unsupported config {cfg.leader}->{cfg.laggard} (validated cell is MES->MNQ)")

    lead_atr = b4.atr_series(lead_df["high"], lead_df["low"], lead_df["close"], b4.ATR_LEN)
    lag_atr = b4.atr_series(lag_df["high"], lag_df["low"], lag_df["close"], b4.ATR_LEN)
    lead_state = b4._per_session_state(lead_df)
    lag_state = b4._per_session_state(lag_df)

    if as_of_date not in lead_state or as_of_date not in lag_state:
        return _hold(f"no aligned session bars for {as_of_date}")

    enriched = b5.enrich_signals(
        lead_df, lag_df, lead_state, lag_state, cfg.laggard, cfg.threshold, lag_atr
    )
    # apply the FROZEN persistence filter (isolated per-edge knob, read from cfg)
    kept = b5.fix_min_persistence(enriched, cfg.min_persistence_bars)
    todays = [s for s in kept if s.date == as_of_date]
    if not todays:
        return _hold(
            f"no divergence persisting >= {cfg.min_persistence_bars} bars on {as_of_date}"
        )
    sig = todays[0]  # structurally 1/day (b4 'fired' flag)
    persistence = next(
        (e["persistence"] for e in enriched if e["sig"] is sig), cfg.min_persistence_bars
    )

    if not cfg.enabled:
        return Edge3Decision(
            edge_id=cfg.edge_id, arm_id=cfg.arm_id, enabled=False, action="HOLD",
            laggard=cfg.laggard, side=sig.side, entry_idx=sig.idx,
            chart_stop=sig.chart_stop, persistence=persistence,
            reason="DORMANT (enabled=False): signal present but no order path",
        )
    return Edge3Decision(
        edge_id=cfg.edge_id, arm_id=cfg.arm_id, enabled=True,
        action="ENTER_LONG" if sig.side == "long" else "ENTER_SHORT",
        laggard=cfg.laggard, side=sig.side, entry_idx=sig.idx,
        chart_stop=sig.chart_stop, persistence=persistence,
        reason=f"divergence persisted {persistence} bars (>= {cfg.min_persistence_bars})",
    )


# --- reproduction: prove the validated expectancy SIGN (pure Python, $0) --------
def reproduce_validated_expectancy(cfg: FrozenConfig = FROZEN_CONFIG) -> dict:
    """Re-run the EXACT validated cell end-to-end using the imported b4/b5 machinery and
    return its OOS metrics. The test asserts the SIGN of per-trade matches the validated
    +$71.46 (a guard that the frozen knobs still map to the gate-clearing cell)."""
    mes = b4.load_futures(cfg.leader)
    mnq = b4.load_futures(cfg.laggard)
    common = sorted(set(mes["date"]) & set(mnq["date"]))
    mes = mes[mes["date"].isin(common)].reset_index(drop=True)
    mnq = mnq[mnq["date"].isin(common)].reset_index(drop=True)

    lag_atr = b4.atr_series(mnq["high"], mnq["low"], mnq["close"], b4.ATR_LEN)
    lag_de = {d: int(g.index[-1]) for d, g in mnq.groupby("date")}
    state_mes = b4._per_session_state(mes)
    state_mnq = b4._per_session_state(mnq)

    cut = int(len(common) * b4.OOS_TRAIN_FRAC)
    oos_days = set(common[cut:])

    enriched = b5.enrich_signals(
        mes, mnq, state_mes, state_mnq, cfg.laggard, cfg.threshold, lag_atr
    )
    sigs = b5.fix_min_persistence(enriched, cfg.min_persistence_bars)
    fills = [
        f for s in sigs
        if (f := b4.simulate(
            mnq, s, cfg.laggard, atr=lag_atr, day_end=lag_de, exit_mode=cfg.exit_mode
        ))
    ]
    oos_fills = [f for f in fills if f.date in oos_days]
    m_all = b4.metrics(fills)
    m_oos = b4.metrics(oos_fills)
    return {
        "n_all": m_all.get("n"),
        "n_oos": m_oos.get("n"),
        "oos_per_trade": m_oos.get("per_trade"),
        "full_per_trade": m_all.get("per_trade"),
        "drop_top5_per_trade": m_all.get("drop_top5_per_trade"),
        "top5_day_pct": m_all.get("top5_day_pct"),
    }


def main() -> None:
    print(f"[edge3] FROZEN CONFIG: {FROZEN_CONFIG.leader}->{FROZEN_CONFIG.laggard} "
          f"thr={FROZEN_CONFIG.threshold} persistence>={FROZEN_CONFIG.min_persistence_bars} "
          f"enabled={FROZEN_CONFIG.enabled} (DORMANT)")
    res = reproduce_validated_expectancy()
    print(f"[edge3] REPRODUCTION: n_all={res['n_all']} n_oos={res['n_oos']} "
          f"oos_pt=${res['oos_per_trade']} drop5=${res['drop_top5_per_trade']} "
          f"top5%={res['top5_day_pct']}")
    print(f"[edge3] validated OOS/tr (recommendation) = ${FROZEN_CONFIG.validated_oos_per_trade}")
    sign_ok = res["oos_per_trade"] is not None and res["oos_per_trade"] > 0
    print(f"[edge3] OOS expectancy SIGN positive: {sign_ok}")


if __name__ == "__main__":
    main()
