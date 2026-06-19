"""EOD Deep-Dive orchestrator — the entry point.

Usage:
    python -m autoresearch.eod_deep.main --date 2026-05-14

Steps:
    1. INGEST  — read all sources (state, journal, jsonl logs)
    2. ANALYZE — call each module to produce CategoryScore
    3. COMPOSE — assemble canonical EodDeepDive dataclass
    4. PROJECT — write JSON + markdown + HTML
    5. FEEDBACK — append to sessions.jsonl for downstream backtest pipeline

The script can be invoked from:
    - Gamma_EodDeepDive scheduled task at 16:05 ET (post-EodSummary)
    - Manual: `python -m autoresearch.eod_deep.main --date YYYY-MM-DD`
    - Interactive Claude session (with --inject-alpaca/--inject-tv hooks)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent.parent.parent
# REPO = C:\Users\jackw\Desktop\42

# Allow running as a script or as a module
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(REPO / "backtest"))
    from autoresearch.eod_deep import schema  # noqa
    from autoresearch.eod_deep import ingest as ingest_mod
    from autoresearch.eod_deep.modules import edge as edge_mod
    from autoresearch.eod_deep.modules import forensics as forensics_mod
    from autoresearch.eod_deep.modules import process as process_mod
    from autoresearch.eod_deep.modules import risk as risk_mod
    from autoresearch.eod_deep.modules import engine_health as engine_health_mod
    from autoresearch.eod_deep.modules import tomorrow as tomorrow_mod
    from autoresearch.eod_deep.modules import macro as macro_mod
    from autoresearch.eod_deep.modules import technical as technical_mod
    from autoresearch.eod_deep.modules import watcher_fleet as watcher_fleet_mod
    from autoresearch.eod_deep.modules import lessons as lessons_mod
    from autoresearch.eod_deep.modules import detection as detection_mod
    from autoresearch.eod_deep.modules import _stubs as stubs_mod
    from autoresearch.eod_deep import feedback as feedback_mod
    from autoresearch.eod_deep import drift as drift_mod
    from autoresearch.eod_deep import knob_round_trip as knob_mod
    from autoresearch.eod_deep.projections import markdown as md_proj
    from autoresearch.eod_deep.projections import html as html_proj
else:
    from . import schema
    from . import ingest as ingest_mod
    from . import feedback as feedback_mod
    from . import drift as drift_mod
    from . import knob_round_trip as knob_mod
    from .modules import edge as edge_mod
    from .modules import forensics as forensics_mod
    from .modules import process as process_mod
    from .modules import risk as risk_mod
    from .modules import engine_health as engine_health_mod
    from .modules import tomorrow as tomorrow_mod
    from .modules import macro as macro_mod
    from .modules import technical as technical_mod
    from .modules import watcher_fleet as watcher_fleet_mod
    from .modules import lessons as lessons_mod
    from .modules import detection as detection_mod
    from .modules import _stubs as stubs_mod
    from .projections import markdown as md_proj
    from .projections import html as html_proj


ANALYSIS_OUT_DIR = REPO / "analysis"
SESSIONS_JSONL = REPO / "analysis" / "sessions.jsonl"


def _build_trade_from_csv_row(row: dict, idx: int, data: ingest_mod.IngestedData) -> Optional[schema.TradeRecord]:
    """Construct a TradeRecord from a journal/trades.csv row.

    Phase 2.7 (2026-05-14): added so EOD pipeline gets real trade data
    when invoked outside an active Claude/MCP session (alpaca_orders empty).
    """
    try:
        strike = float(row.get("strike") or 0)
        opt_type = (row.get("c_or_p") or "?").upper()
        qty = int(float(row.get("qty") or 0))
        entry_px = float(row.get("entry_px") or 0)
        exit_px = float(row.get("exit_px") or 0)
        try:
            pnl = float((row.get("dollar_pnl") or "0").replace(",", "").replace("$", ""))
        except (ValueError, AttributeError):
            pnl = 0.0
        try:
            hold_min = int(row.get("hold_minutes") or 0)
        except (ValueError, TypeError):
            hold_min = 0
        time_entry = row.get("time_entry", "")
        time_exit = row.get("time_exit", "")
        contract = row.get("contract", "")
        # Parse expiry from contract like "SPY 2026-05-14 745C"
        expiry_iso = ""
        parts = contract.split()
        if len(parts) >= 2:
            expiry_iso = parts[1]

        fills: list[schema.Fill] = []
        if entry_px > 0 and qty > 0:
            fills.append(schema.Fill(
                time_et=time_entry, side="buy", qty=qty,
                price=entry_px,
                source=("j_manual" if row.get("j_override") == "Y" else "engine_heartbeat"),
                reason="entry", order_id=None,
            ))
        if exit_px > 0:
            fills.append(schema.Fill(
                time_et=time_exit, side="sell", qty=qty,
                price=exit_px,
                source="j_manual" if row.get("j_override") == "Y" else "engine_heartbeat",
                reason="tp1_or_runner", order_id=None,
            ))

        capital = qty * entry_px * 100
        pnl_pct = (pnl / capital * 100) if capital else 0.0

        return schema.TradeRecord(
            id=f"trade_csv_{idx}",
            setup_name=row.get("setup", "") or _infer_setup_name(data),
            direction="long" if opt_type == "C" else "short",
            underlying="SPY",
            expiry_date=expiry_iso,
            strike=strike,
            option_type=opt_type,
            fills=fills,
            entry_price=entry_px,
            avg_exit_price=exit_px,
            qty_entered=qty,
            qty_exited=qty if exit_px > 0 else 0,
            qty_outstanding=0 if exit_px > 0 else qty,
            pnl_dollars_realized=round(pnl, 2),
            pnl_dollars_unrealized=0.0,
            pnl_pct_on_capital=round(pnl_pct, 2),
            hold_minutes=hold_min,
            triggers_fired=_extract_triggers(data),
            setup_score=_extract_setup_score(data),
            doctrine_compliance_score=100.0 if row.get("followed_rules") == "Y" else 80.0,
            rule_breaks=[r.get("type", "?") for r in data.rule_breaks_today],
            journaled_before_entry=True,
            engine_decisions=_extract_engine_decisions(data),
        )
    except Exception:
        return None


def _extract_trades_from_data(data: ingest_mod.IngestedData) -> list[schema.TradeRecord]:
    """Build TradeRecord list from Alpaca orders + journal trades.csv.

    Phase 1: if alpaca_orders_today is populated (from MCP injection), use those.
    Phase 2.7 (2026-05-14): fallback to trades.csv rows when alpaca_orders empty
    so pure-Python EOD invocations don't silently report 0 trades when J actually
    traded. Per OP-25 silent-failure rule.
    """
    trades: list[schema.TradeRecord] = []

    if data.alpaca_orders_today:
        # Group orders by symbol — each unique option symbol = one trade
        by_symbol: dict[str, list[dict]] = {}
        for o in data.alpaca_orders_today:
            sym = o.get("symbol", "UNKNOWN")
            by_symbol.setdefault(sym, []).append(o)

        for i, (sym, orders) in enumerate(by_symbol.items(), start=1):
            # Sort by filled_at
            orders_sorted = sorted(
                [o for o in orders if o.get("status") == "filled"],
                key=lambda x: x.get("filled_at") or x.get("created_at") or ""
            )
            if not orders_sorted:
                continue

            fills: list[schema.Fill] = []
            qty_entered = 0
            qty_exited = 0
            entry_price = 0.0
            avg_exit_price_sum = 0.0
            avg_exit_qty = 0

            for o in orders_sorted:
                filled_at = o.get("filled_at", "")
                # Convert UTC ISO timestamp to ET HH:MM:SS
                # Alpaca returns UTC like "2026-05-14T13:58:35.540746Z"
                # Need ET (UTC - 4 hours for EDT, UTC - 5 for EST)
                time_str = ""
                if filled_at:
                    try:
                        ts_utc = dt.datetime.fromisoformat(filled_at.replace("Z", "+00:00"))
                        # ET = UTC - 4 (DST May-Nov) or UTC - 5 (rest)
                        # 2026-05-14 is in EDT
                        ts_et = ts_utc - dt.timedelta(hours=4)
                        time_str = ts_et.strftime("%H:%M:%S")
                    except (ValueError, AttributeError):
                        time_str = filled_at[11:19]  # fallback to raw UTC
                side = o.get("side", "")
                qty = int(float(o.get("filled_qty") or 0))
                price = float(o.get("filled_avg_price") or 0)
                client_id = o.get("client_order_id", "")
                reason = "entry" if side == "buy" else _infer_exit_reason(client_id, o, side)

                fills.append(schema.Fill(
                    time_et=time_str,
                    side=side,
                    qty=qty,
                    price=price,
                    source=("j_manual" if "scale-out" in client_id else "engine_heartbeat"),
                    reason=reason,
                    order_id=o.get("id"),
                ))

                if side == "buy":
                    qty_entered += qty
                    entry_price = price
                else:
                    qty_exited += qty
                    avg_exit_price_sum += price * qty
                    avg_exit_qty += qty

            avg_exit_price = (avg_exit_price_sum / avg_exit_qty) if avg_exit_qty else 0.0
            pnl_realized = (avg_exit_price - entry_price) * qty_exited * 100 if avg_exit_qty else 0.0

            # Parse OCC symbol for strike + type
            #   SPY260514C00745000 → SPY 260514 C 00745000
            try:
                strike = int(sym[-8:]) / 1000.0
                opt_type = sym[-9]
                expiry_yymmdd = sym[-15:-9]
                expiry_iso = "20" + expiry_yymmdd[:2] + "-" + expiry_yymmdd[2:4] + "-" + expiry_yymmdd[4:6]
            except (ValueError, IndexError):
                strike = 0.0
                opt_type = "?"
                expiry_iso = ""

            # Hold time
            t_first = orders_sorted[0].get("filled_at", "")
            t_last = orders_sorted[-1].get("filled_at", "")
            hold_min = 0
            if t_first and t_last:
                try:
                    f = dt.datetime.fromisoformat(t_first.replace("Z", "+00:00"))
                    l = dt.datetime.fromisoformat(t_last.replace("Z", "+00:00"))
                    hold_min = int((l - f).total_seconds() / 60)
                except Exception:
                    pass

            capital = qty_entered * entry_price * 100
            pnl_pct = (pnl_realized / capital * 100) if capital else 0.0

            trade = schema.TradeRecord(
                id=f"trade_{i}",
                setup_name=_infer_setup_name(data),
                direction="long" if opt_type == "C" else "short",
                underlying="SPY",
                expiry_date=expiry_iso,
                strike=strike,
                option_type=opt_type,
                fills=fills,
                entry_price=entry_price,
                avg_exit_price=round(avg_exit_price, 4),
                qty_entered=qty_entered,
                qty_exited=qty_exited,
                qty_outstanding=qty_entered - qty_exited,
                pnl_dollars_realized=round(pnl_realized, 2),
                pnl_dollars_unrealized=0.0,
                pnl_pct_on_capital=round(pnl_pct, 2),
                hold_minutes=hold_min,
                triggers_fired=_extract_triggers(data),
                setup_score=_extract_setup_score(data),
                doctrine_compliance_score=100.0 if not data.rule_breaks_today else 80.0,
                rule_breaks=[r.get("type", "?") for r in data.rule_breaks_today],
                journaled_before_entry=True,
                engine_decisions=_extract_engine_decisions(data),
            )
            trades.append(trade)

    # Phase 2.7 fallback: if no Alpaca orders attached but trades.csv has rows,
    # build TradeRecords from those so downstream modules see real trade data.
    if not trades and data.trades_csv_rows:
        for i, row in enumerate(data.trades_csv_rows, start=1):
            t = _build_trade_from_csv_row(row, i, data)
            if t is not None:
                trades.append(t)

    return trades


def _infer_exit_reason(client_id: str, order: dict, side: str) -> str:
    """Map order client_order_id to a reason string."""
    if side != "sell":
        return "entry"
    if "scale-out" in client_id:
        return "scale_out"
    if order.get("order_type") == "limit":
        return "tp1"
    # heuristic: market sell late in session = runner_target or trail
    return "runner_target_or_trail"


def _infer_setup_name(data: ingest_mod.IngestedData) -> str:
    """Pick setup name from loop-state developing_setup or first_entry_lock."""
    ls = data.loop_state or {}
    locks = ls.get("first_entry_lock") or []
    if locks and isinstance(locks, list):
        first = locks[0]
        if isinstance(first, dict):
            return first.get("setup_name", "UNKNOWN")
    dev = ls.get("developing_setup") or {}
    if isinstance(dev, dict):
        return dev.get("name", "UNKNOWN")
    return "UNKNOWN"


def _extract_triggers(data: ingest_mod.IngestedData) -> list[str]:
    ls = data.loop_state
    pos = data.current_position
    if pos.get("triggers_fired"):
        return pos["triggers_fired"]
    dev = ls.get("developing_setup") or {}
    if not isinstance(dev, dict):
        return []
    trig = dev.get("trigger", "")
    return trig.split("+") if trig else []


def _extract_setup_score(data: ingest_mod.IngestedData) -> str:
    dev = data.loop_state.get("developing_setup") or {}
    score = dev.get("score") if isinstance(dev, dict) else None
    max_score = dev.get("score_max", 11) if isinstance(dev, dict) else 11
    return f"{score}/{max_score}" if score is not None else "?/?"


def _extract_engine_decisions(data: ingest_mod.IngestedData) -> list[schema.EngineDecision]:
    """Pull notable decisions from decisions.jsonl + loop-state's reason history.

    The producer (heartbeat.md) writes the decision under the field `action`
    (e.g. ENTER_BULL / EXIT_TP1 / SKIP_* / WATCH_ONLY). Older rows may use
    `decision`. Read `action` first, fall back to `decision`, so non-HOLD rows
    (including watcher WATCH_ONLY / *_WOULD_ENTER fires) are not silently dropped.
    """
    decisions = []
    for d in data.decisions_today:
        act = d.get("action") or d.get("decision")
        if act in (None, "HOLD"):
            continue  # only material decisions
        # row time: rows carry `time_et` (HH:MM); legacy rows used `timestamp_et` ISO
        time_et = d.get("time_et") or d.get("timestamp_et", "")[11:19]
        decisions.append(schema.EngineDecision(
            time_et=time_et,
            tick_or_fire_id=d.get("tick_id", -1),
            decision=act,
            reasoning=d.get("reason", ""),
        ))
    return decisions


def _compose_market_session_summary(data: ingest_mod.IngestedData) -> dict:
    ls = data.loop_state
    spy = ls.get("spy", {}) if ls else {}
    vix = ls.get("vix_cache", {}) if ls else {}
    return {
        "session_high": spy.get("session_high"),
        "session_low": spy.get("session_low"),
        "session_close": spy.get("last"),
        "vix_close": vix.get("value"),
        "vix_dir": vix.get("dir"),
        "regime_predicted": (data.news.get("regime") if data.news else None),
    }


def run(date_str: str,
        alpaca_orders: Optional[list] = None,
        alpaca_account: Optional[dict] = None,
        tv_chart_state: Optional[dict] = None,
        tv_screenshot_path: Optional[str] = None,
        tv_ribbon: Optional[dict] = None) -> dict:
    """Top-level entry. Returns the composed dict (also writes files)."""

    # === STAGE 1: INGEST ===
    data = ingest_mod.ingest_all(date_str)
    if alpaca_orders is not None:
        ingest_mod.attach_alpaca_orders(data, alpaca_orders)
    if alpaca_account is not None:
        ingest_mod.attach_alpaca_account(data, alpaca_account)
    if tv_chart_state is not None or tv_screenshot_path or tv_ribbon:
        ingest_mod.attach_tv_chart(data, tv_screenshot_path or "", tv_chart_state or {}, tv_ribbon or {})

    # === STAGE 2: BUILD TRADES ===
    trades = _extract_trades_from_data(data)

    # === STAGE 3: ANALYZE (12 modules) ===
    categories = {
        "execution":     stubs_mod.analyze_execution(data, trades),
        "detection":     detection_mod.analyze_detection(data, trades),   # Tier B MVP REAL
        "edge":          edge_mod.analyze_edge(data, trades),
        "doctrine":      stubs_mod.analyze_doctrine(data, trades),        # Tier A — partial-real already
        "risk":          risk_mod.analyze_risk(data, trades),
        "process":       process_mod.analyze_process(data, trades),
        "macro":         macro_mod.analyze_macro(data, trades),           # Tier A REAL
        "technical":     technical_mod.analyze_technical(data, trades),   # Tier A REAL
        "engine_health": engine_health_mod.analyze_engine_health(data, trades),
        "watcher_fleet": watcher_fleet_mod.analyze_watcher_fleet(data, trades),  # Tier A REAL
        "lessons":       lessons_mod.analyze_lessons(data, trades),       # Tier A REAL (separate from forensics)
        "forensics":     forensics_mod.analyze_forensics(data, trades),   # Phase 2.3 REAL (new key)
        "tomorrow":      tomorrow_mod.analyze_tomorrow(data, trades),
    }

    # === STAGE 4: COMPOSE EodDeepDive ===
    account = data.alpaca_account
    equity_end = float(account.get("equity") or 0) if account else 0
    equity_start = float(account.get("last_equity") or 0) if account else 0

    # Fallback chain for equity_start (Alpaca's `last_equity` is sometimes 0
    # or stale, causing `account_equity_start: 0` in the eod-deep JSON — fix
    # 2026-05-16 after today's 5/15 EOD shipped with equity_start=0).
    if equity_start == 0:
        # 1) Try prior trading day's equity_end from yesterday's eod-deep JSON
        try:
            analysis_dir = Path(__file__).resolve().parents[3] / "analysis"
            candidates = sorted(analysis_dir.glob("eod-deep-*.json"),
                                reverse=True)
            for cand in candidates:
                if date_str in cand.name:
                    continue  # skip today's file if it exists
                try:
                    prior = json.loads(cand.read_text(encoding="utf-8"))
                    prior_end = float(prior.get("account_equity_end") or 0)
                    if prior_end > 0:
                        equity_start = prior_end
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # 2) Back-compute from current equity minus realized day P&L
        if equity_start == 0 and equity_end > 0 and trades:
            equity_start = equity_end - sum(
                t.pnl_dollars_realized for t in trades
            )

    if equity_end == 0 and trades:
        # Phase-1 fallback: sum realized PnL from trades
        equity_end = equity_start + sum(t.pnl_dollars_realized for t in trades)
    day_pnl = equity_end - equity_start

    deep = schema.EodDeepDive(
        schema_version=schema.SCHEMA_VERSION,
        date=date_str,
        generated_at_et=dt.datetime.now().isoformat(timespec="seconds"),
        rule_version_active=data.params.get("rule_version", "unknown"),
        market_session_summary=_compose_market_session_summary(data),
        account_equity_start=round(equity_start, 2),
        account_equity_end=round(equity_end, 2),
        day_pnl_dollars=round(day_pnl, 2),
        day_pnl_pct=round((day_pnl / equity_start * 100) if equity_start else 0, 3),
        day_trade_count=len(trades),
        daily_loss_budget_used_pct=0.0,  # Phase 2
        trades=trades,
        categories=categories,
        research_handoffs={
            "fixes_shipped_today": _extract_fixes_shipped(data),
            "doctrine_candidates_for_grinder": _extract_doctrine_candidates(categories),
            "ingest_warnings": data.ingest_warnings,
        },
        tomorrow_setup=categories["tomorrow"].evidence,
    )
    deep.process_score = schema.compute_process_score(deep)
    deep.edge_capture_pct = categories["edge"].evidence.get("edge_capture_pct", 0.0)

    # === STAGE 4a: DRIFT CHECK (Phase 2.5 Tier B) ===
    # Compare today's P&L to recent v15 backtest distribution.
    try:
        drift_result = drift_mod.compute_drift_check(date_str, day_pnl)
        deep.research_handoffs["drift_check"] = {
            "actual_pnl": drift_result.actual_pnl,
            "verdict": drift_result.verdict,
            "narrative": drift_result.narrative,
            "n_days_in_distribution": drift_result.distribution_n_days,
            "percentiles": {
                "p10": drift_result.p10, "p25": drift_result.p25,
                "p50": drift_result.p50, "p75": drift_result.p75,
                "p90": drift_result.p90,
            },
            "today_percentile_estimate": drift_result.today_percentile_estimate,
            "cache_age_days": drift_result.cache_age_days,
        }
    except Exception as _e_dr:
        deep.research_handoffs["drift_check_error"] = f"{type(_e_dr).__name__}: {_e_dr}"

    # === STAGE 4a.4: HEARTBEAT TICK AUDIT (Fire #41 2026-05-14 evening) ===
    # Verifies the R1 closed-bar fix shipped in heartbeat.md v15.1 is holding
    # day-over-day. Classifies each tick ALIGNED / MISALIGNED-BENIGN /
    # MISALIGNED-CRITICAL / STALE_PAUSED / NO_DATA. Result feeds J's
    # morning brief + auto-flags days where heartbeat reverted to in-progress
    # bar reads (silent failure mode). See `docs/HEARTBEAT-CHART-DATA-AUDIT-2026-05-14.md`.
    try:
        from autoresearch.heartbeat_tick_audit import run_audit as _hb_audit
        _hb_summary = _hb_audit(date_str)
        # Strip the per-tick critical_ticks list to keep EOD JSON small;
        # full per-tick CSV is on disk at automation/state/heartbeat-tick-audit-{date}.csv
        deep.research_handoffs["heartbeat_tick_audit"] = {
            "headline": _hb_summary.get("headline"),
            "counts": _hb_summary.get("counts", {}),
            "live_trading_ticks": _hb_summary.get("live_trading_ticks", 0),
            "misaligned_critical_count": _hb_summary.get("misaligned_critical_count", 0),
            "misaligned_critical_pct_of_live": _hb_summary.get("misaligned_critical_pct_of_live", 0.0),
            "audit_files": _hb_summary.get("audit_files", {}),
            "first_3_critical_ticks": _hb_summary.get("critical_ticks", [])[:3],
        }
    except Exception as _e_hb:
        deep.research_handoffs["heartbeat_tick_audit_error"] = f"{type(_e_hb).__name__}: {_e_hb}"

    # === STAGE 4a.5: KNOB ROUND-TRIP (Phase 2.5 + 2.6) ===
    # For each winner, try sweep on today's bar first. If OPRA cache miss
    # (T+0 typical), fall back to Phase 2.6 analog-based sweep using the
    # forensics analog bars (which ARE in cache).
    try:
        from .modules.forensics import _load_master_with_features
        master_data = _load_master_with_features(target_date=date_str)
        if master_data and trades:
            spy_df_full, ribbon_df_full, _vb, _ff = master_data
            base_knobs = knob_mod.DEFAULT_KNOBS.copy()
            params = data.params or {}
            base_knobs.update({
                "premium_stop_pct": params.get("v15_premium_stop_pct_bear", knob_mod.DEFAULT_KNOBS["premium_stop_pct"]),
                "profit_lock_trail_pct": params.get("v15_profit_lock_trail_pct", knob_mod.DEFAULT_KNOBS["profit_lock_trail_pct"]),
                "profit_lock_threshold_pct": params.get("v15_profit_lock_threshold", knob_mod.DEFAULT_KNOBS["profit_lock_threshold_pct"]),
                "strike_offset": params.get("v15_strike_offset_bear", knob_mod.DEFAULT_KNOBS["strike_offset"]),
            })

            # Get forensics analog bar indices from the JUST-COMPUTED forensics result
            forensics_evidence = deep.categories.get("forensics")
            analog_idxs_per_trade = {}
            if forensics_evidence:
                ev = forensics_evidence.evidence
                for fpt in ev.get("forensics_per_trade", []) or []:
                    # Phase 2.6: forensics now exposes analog_records with bar_idx_in_master
                    analog_records = fpt.get("analog_records", []) or []
                    # Only use analogs that successfully simulated (status="filled")
                    analog_idxs = [
                        r["bar_idx_in_master"] for r in analog_records
                        if r.get("sim_status") == "filled" and r.get("bar_idx_in_master", -1) >= 0
                    ]
                    analog_idxs_per_trade[fpt["trade_id"]] = analog_idxs

            knob_results = []
            for t in [tr for tr in trades if tr.pnl_dollars_realized > 0]:
                # Try today's bar first
                primary = knob_mod.round_trip_one_trade(t, spy_df_full, ribbon_df_full, base_knobs)
                # If today's OPRA missed (dominant_knob is "n/a (opra_cache_miss_today)"),
                # fall back to analog-based
                if "opra_cache_miss" in primary.dominant_knob:
                    analog_idxs = analog_idxs_per_trade.get(t.id, [])
                    if analog_idxs:
                        analog_result = knob_mod.round_trip_via_analogs(
                            t, analog_idxs, spy_df_full, ribbon_df_full, base_knobs
                        )
                        # Tag origin
                        analog_result.narrative = ("[FALLBACK: analog-based] " +
                                                   analog_result.narrative + "\n\n" +
                                                   "[ORIGINAL today-bar attempt] " + primary.narrative)
                        knob_results.append(analog_result)
                    else:
                        knob_results.append(primary)  # keep the honest no-OPRA message
                else:
                    knob_results.append(primary)

            deep.research_handoffs["knob_round_trip_per_trade"] = [
                {
                    "trade_id": r.trade_id,
                    "base_pnl": r.base_pnl,
                    "dominant_knob": r.dominant_knob,
                    "dominant_delta": r.dominant_delta,
                    "dominant_best_level": r.dominant_best_level,
                    "narrative": r.narrative,
                    "sweeps_summary": [
                        {
                            "knob": s.knob_name, "base": s.base_value,
                            "sensitivity": s.sensitivity_dollars,
                            "best_level": s.best_level, "best_pnl": s.best_pnl,
                        } for s in r.sweeps
                    ],
                } for r in knob_results
            ]

            # Auto-queue any knob with meaningful sensitivity as a doctrine candidate
            for r in knob_results:
                for s in r.sweeps:
                    if s.sensitivity_dollars >= 30 and s.best_level != s.base_value:
                        # Add an action to the forensics category so feedback dispatch
                        # picks it up next time we run.
                        forensics_cat = deep.categories.get("forensics")
                        if forensics_cat is not None:
                            forensics_cat.actions.append({
                                "type": "queue_for_grinder",
                                "priority": "MED",
                                "details": {
                                    "candidate_source": "phase_2.6_analog_knob_sweep",
                                    "trade_id": r.trade_id,
                                    "setup_name": data.loop_state.get("first_entry_lock", [{}])[0].get("setup_name", "UNKNOWN") if isinstance(data.loop_state.get("first_entry_lock"), list) else "UNKNOWN",
                                    "knob": s.knob_name,
                                    "current_value": s.base_value,
                                    "proposed_value": s.best_level,
                                    "sensitivity_dollars_per_analog": s.sensitivity_dollars,
                                    "analog_n": 3,  # from forensics
                                    "caveat": "Analog-based proxy (n=3). Needs wider validation via Stage 1 grinder on full 16mo window.",
                                }
                            })
    except Exception as _e_kn:
        deep.research_handoffs["knob_round_trip_error"] = f"{type(_e_kn).__name__}: {_e_kn}"

    # === STAGE 4a.6: SELF-HEAL SKILLS SUITE (Fire #43 2026-05-14 evening) ===
    # Runs 3 Python skills (pin-chain-verify, chart-data-verify, watcher-state-inspector)
    # and reads 1 PowerShell skill output (heartbeat-pulse-check) from disk.
    # Each skill writes a JSON file to automation/state/; we summarise here.
    # Skills run every EOD fire — zero LLM cost (pure Python / file reads).
    # Encoded in: FIRE43-WIRE-EOD-INTEGRATION queue item.
    try:
        import subprocess as _sp
        _state_dir = REPO / "automation" / "state"
        _backtest_dir = REPO / "backtest"
        _skills_out: dict = {}

        # 1) pin-chain-verify (any fire — checks rule_version drift across params/heartbeat/premarket)
        try:
            _sp.run(
                [sys.executable, "-m", "autoresearch.pin_chain_verify", "--quiet"],
                cwd=str(_backtest_dir), capture_output=True, timeout=30,
            )
            _pcv_path = _state_dir / "pin-chain-verify-latest.json"
            if _pcv_path.exists():
                _pcv = json.loads(_pcv_path.read_text(encoding="utf-8"))
                _skills_out["pin_chain_verify"] = {
                    "verdict": _pcv.get("verdict"),
                    "reason": _pcv.get("reason"),
                    "canonical": _pcv.get("canonical_rule_version"),
                    "mismatches": len(_pcv.get("mismatches") or []),
                }
        except Exception as _e1:
            _skills_out["pin_chain_verify_error"] = f"{type(_e1).__name__}: {_e1}"

        # 2) chart-data-verify (post-EOD-appender — validates CSV bars vs live yfinance)
        try:
            _sp.run(
                [sys.executable, "-m", "autoresearch.chart_data_verify",
                 "--date", date_str, "--quiet"],
                cwd=str(_backtest_dir), capture_output=True, timeout=45,
            )
            _cdv_path = _state_dir / f"chart-data-verify-{date_str}.json"
            if _cdv_path.exists():
                _cdv = json.loads(_cdv_path.read_text(encoding="utf-8"))
                _skills_out["chart_data_verify"] = {
                    "verdict": _cdv.get("verdict"),
                    "reason": _cdv.get("reason"),
                    "bars_checked": len(_cdv.get("bars") or []),
                    "max_divergence": _cdv.get("max_divergence"),
                }
        except Exception as _e2:
            _skills_out["chart_data_verify_error"] = f"{type(_e2).__name__}: {_e2}"

        # 3) watcher-state-inspector (post-15:55 ET — verifies ORB/ODF warmup state)
        try:
            _sp.run(
                [sys.executable, "-m", "autoresearch.watcher_state_inspector",
                 "--date", date_str, "--quiet"],
                cwd=str(_backtest_dir), capture_output=True, timeout=45,
            )
            _wsi_path = _state_dir / f"watcher-state-inspector-{date_str}.json"
            if _wsi_path.exists():
                _wsi = json.loads(_wsi_path.read_text(encoding="utf-8"))
                _skills_out["watcher_state_inspector"] = {
                    "verdict": _wsi.get("verdict"),
                    "reason": _wsi.get("reason"),
                    "orb_phase": (_wsi.get("orb_state") or {}).get("phase"),
                    "obs_today": _wsi.get("watcher_obs_count_today", 0),
                }
        except Exception as _e3:
            _skills_out["watcher_state_inspector_error"] = f"{type(_e3).__name__}: {_e3}"

        # 4) heartbeat-pulse-check (written by Gamma_Heartbeat PS task during trading day)
        #    Read from disk — we do NOT re-run it here (it reads the heartbeat log for today)
        _hpc_path = _state_dir / f"heartbeat-pulse-check-{date_str}.json"
        if _hpc_path.exists():
            try:
                _hpc = json.loads(_hpc_path.read_text(encoding="utf-8"))
                _skills_out["heartbeat_pulse_check"] = {
                    "verdict": _hpc.get("verdict"),
                    "fire_count": _hpc.get("fire_count"),
                    "max_gap_minutes": _hpc.get("max_gap_minutes"),
                    "gaps_over_15_min": _hpc.get("gaps_over_15_min", 0),
                }
            except Exception as _e4:
                _skills_out["heartbeat_pulse_check_error"] = f"{type(_e4).__name__}: {_e4}"

        # 5) heartbeat-mcp-self-test (reads latest JSON written by PS skill)
        #    This is a live connectivity probe; run during EOD to catch TV/Alpaca issues.
        _hmcp_path = _state_dir / "heartbeat-mcp-self-test-latest.json"
        if _hmcp_path.exists():
            try:
                _hmcp = json.loads(_hmcp_path.read_text(encoding="utf-8"))
                _skills_out["heartbeat_mcp_self_test"] = {
                    "verdict": _hmcp.get("verdict"),
                    "run_at": _hmcp.get("run_at"),
                    "tv_cdp_ok": _hmcp.get("tv_cdp_ok"),
                    "alpaca_mcp_ok": _hmcp.get("alpaca_mcp_ok"),
                }
            except Exception as _e5:
                _skills_out["heartbeat_mcp_self_test_error"] = f"{type(_e5).__name__}: {_e5}"

        deep.research_handoffs["self_heal_skills"] = _skills_out
    except Exception as _e_sh:
        deep.research_handoffs["self_heal_skills_error"] = f"{type(_e_sh).__name__}: {_e_sh}"

    # === STAGE 4a.7: VISION-vs-HEARTBEAT GRADER (DRAFT 2026-05-17) ===
    # Pairs each chart-vision observation (from automation/state/vision-observations.jsonl)
    # with the heartbeat decision for the same tick, then grades both against next-bar
    # actual SPY close from the master 5m CSV. Writes analysis/vision-vs-heartbeat-{date}.json.
    # No-op (NO_DATA verdict) until the chart_vision_observer task is registered.
    # See docs/VISION-OBSERVER-PROTOCOL.md.
    try:
        from autoresearch.vision_observer_grader import run_grader as _vog_run
        _vog_out = _vog_run(date_str, write_output=True)
        _vog_agg = _vog_out.get("aggregate", {})
        deep.research_handoffs["vision_observer_grader"] = {
            "verdict": (_vog_out.get("verdict") or {}).get("verdict"),
            "total_paired_ticks": _vog_agg.get("total_paired_ticks", 0),
            "aligned": _vog_agg.get("aligned", 0),
            "diverged": _vog_agg.get("diverged", 0),
            "vision_only": _vog_agg.get("vision_only", 0),
            "heartbeat_only": _vog_agg.get("heartbeat_only", 0),
            "vision_accuracy_pct": _vog_agg.get("vision_accuracy_pct"),
            "heartbeat_accuracy_pct": _vog_agg.get("heartbeat_accuracy_pct"),
            "diverged_vision_accuracy_pct": _vog_agg.get("diverged_vision_accuracy_pct"),
            "diverged_heartbeat_accuracy_pct": _vog_agg.get("diverged_heartbeat_accuracy_pct"),
            "vision_minus_heartbeat_diverged_pp": _vog_agg.get("vision_minus_heartbeat_diverged_pp"),
            "ingest_warnings": (_vog_out.get("ingest_warnings") or [])[:5],
        }
    except Exception as _e_vog:
        deep.research_handoffs["vision_observer_grader_error"] = f"{type(_e_vog).__name__}: {_e_vog}"

    # === STAGE 4a.8: CHART PATTERN BACKTEST (2026-05-18 evening, J's "engine eyes" directive) ===
    # Runs the chart-pattern detectors (double_bottom, double_top, failed_breakdown_wick,
    # rejection_at_level) on today's RTH bars. Each hit is graded against next-bar truth
    # and overlayed against heartbeat decisions. Output: analysis/pattern-backtest-{date}.{json,md}.
    # The numeric counterpart to the vision-observer's qualitative pattern reads -- convergence
    # validates both; divergence flags calibration work. See crypto/lib/chart_patterns.py +
    # analysis/vision-backtest-pattern-detection.md.
    try:
        from autoresearch.pattern_backtest import run_pattern_backtest, _autodetect_csv
        from datetime import date as _Date
        _pb_date = _Date.fromisoformat(date_str)
        _pb_csv = _autodetect_csv(_pb_date)
        if _pb_csv is None:
            deep.research_handoffs["pattern_backtest_error"] = f"no CSV covering {date_str}"
        else:
            _pb_result = run_pattern_backtest(_pb_date, _pb_csv)
            deep.research_handoffs["pattern_backtest"] = {
                "bars_count": _pb_result.get("bars_count", 0),
                "total_hits": _pb_result.get("total_hits", 0),
                "detectors_run": _pb_result.get("detectors_run", []),
                "summary_by_detector": _pb_result.get("summary_by_detector", {}),
            }
    except Exception as _e_pb:
        deep.research_handoffs["pattern_backtest_error"] = f"{type(_e_pb).__name__}: {_e_pb}"

    # === STAGE 4b: MISSED-SETUPS SCANNER (2026-05-15 evening, J directive) ===
    # Scans every closed 5m RTH bar for level interactions that WOULD have
    # qualified for one of the 4 active/draft setups (BEARISH_REJECTION,
    # BULLISH_RECLAIM, SNIPER_LEVEL_BREAK, SHOTGUN_SCALPER tiers 1/2/3) but
    # never fired in the live heartbeat. Surfaces the gap J asked about:
    # "chart was all over the key levels but the engine took only 1 trade."
    # Must NEVER crash the rest of EOD — wrapped in a defensive try/except.
    try:
        from .missed_setups_scanner import scan_missed_setups as _scan_missed
        from .missed_setups_section import render_section as _render_missed_md

        _scan_date = dt.date.fromisoformat(date_str)
        _missed = _scan_missed(_scan_date)
        deep.research_handoffs["missed_setups_scan"] = _missed
        # Render and persist the markdown section so downstream (journal,
        # markdown projection) can splice it in without re-running.
        deep.research_handoffs["missed_setups_markdown"] = _render_missed_md(_missed)

        # Append the section to journal/YYYY-MM-DD.md if the journal exists
        # and does not already contain the section header. Idempotent.
        _journal_path = REPO / "journal" / f"{date_str}.md"
        if _journal_path.exists():
            try:
                _existing = _journal_path.read_text(encoding="utf-8")
                if "### Engine Misses Today" not in _existing:
                    _appended = (
                        _existing.rstrip()
                        + "\n\n---\n\n"
                        + deep.research_handoffs["missed_setups_markdown"]
                        + "\n"
                    )
                    _journal_path.write_text(_appended, encoding="utf-8")
                    deep.research_handoffs["missed_setups_appended_to_journal"] = True
                else:
                    deep.research_handoffs["missed_setups_appended_to_journal"] = False
            except Exception as _e_jw:
                deep.research_handoffs["missed_setups_journal_write_error"] = (
                    f"{type(_e_jw).__name__}: {_e_jw}"
                )
    except Exception as _e_ms:
        deep.research_handoffs["missed_setups_error"] = f"{type(_e_ms).__name__}: {_e_ms}"

    # === STAGE 4c: FEEDBACK DISPATCH ===
    # Walk every category's actions[] and queue to recommendations/*.jsonl.
    # Auto-write to LESSONS-LEARNED.md / FUTURE-IMPROVEMENTS.md is BANNED (OP 24).
    try:
        action_counts = feedback_mod.dispatch_actions_from_categories(deep.categories, date_str)
        deep.research_handoffs["feedback_dispatch_counts"] = action_counts
    except Exception as _e_fd:
        deep.research_handoffs["feedback_dispatch_error"] = f"{type(_e_fd).__name__}: {_e_fd}"

    # === STAGE 5: PROJECT (write outputs) ===
    json_path = ANALYSIS_OUT_DIR / f"eod-deep-{date_str}.json"
    md_path = ANALYSIS_OUT_DIR / f"eod-deep-{date_str}.md"
    html_path = ANALYSIS_OUT_DIR / f"trade-card-{date_str}.html"

    ANALYSIS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path.write_text(schema.to_json(deep, indent=2), encoding="utf-8")
    md_path.write_text(md_proj.render(deep), encoding="utf-8")
    html_path.write_text(html_proj.render(deep), encoding="utf-8")

    # === STAGE 6: SESSIONS LEDGER ===
    _append_sessions_ledger(deep)

    return schema.to_dict(deep)


def _extract_fixes_shipped(data: ingest_mod.IngestedData) -> list[str]:
    """Phase 1: scan journal_md for "shipped" / "patched" / "fixed" markers."""
    md = data.journal_md.lower()
    fixes = []
    for marker in ["t76", "t75", "t70", "t71", "t62", "t63", "sniper retired", "tv cdp recovery"]:
        if marker in md:
            fixes.append(marker.upper())
    return fixes


def _extract_doctrine_candidates(categories: dict) -> list[str]:
    """Pull candidate-flag actions out of every category."""
    out = []
    for cat_key, cat in categories.items():
        for a in cat.actions:
            if a.get("type") == "log_doctrine_win" or a.get("type") == "queue_for_grinder":
                out.append({"category": cat_key, **a})
    return out


def _append_sessions_ledger(deep: schema.EodDeepDive) -> None:
    """Append a single one-line summary to analysis/sessions.jsonl."""
    summary = {
        "date": deep.date,
        "rule_version": deep.rule_version_active,
        "trade_count": deep.day_trade_count,
        "day_pnl_dollars": deep.day_pnl_dollars,
        "day_pnl_pct": deep.day_pnl_pct,
        "process_score": deep.process_score,
        "edge_capture_pct": deep.edge_capture_pct,
        "categories_summary": {k: v.score for k, v in deep.categories.items()},
        "fixes_shipped": deep.research_handoffs.get("fixes_shipped_today", []),
        "schema_version": deep.schema_version,
    }
    SESSIONS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with SESSIONS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")


def main_cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=dt.date.today().isoformat())
    p.add_argument("--rerun", action="store_true")
    args = p.parse_args()

    json_path = ANALYSIS_OUT_DIR / f"eod-deep-{args.date}.json"
    if json_path.exists() and not args.rerun:
        print(f"WARNING: {json_path} already exists. Use --rerun to overwrite.")

    result = run(args.date)
    print(f"=== EOD DEEP-DIVE for {args.date} ===")
    print(f"  Process score: {result['process_score']}/100")
    print(f"  Edge capture: {result['edge_capture_pct']}%")
    print(f"  Day P&L: ${result['day_pnl_dollars']:,.2f} ({result['day_pnl_pct']:+.2f}%)")
    print(f"  Trades: {result['day_trade_count']}")
    print(f"  Outputs:")
    print(f"    {ANALYSIS_OUT_DIR / f'eod-deep-{args.date}.json'}")
    print(f"    {ANALYSIS_OUT_DIR / f'eod-deep-{args.date}.md'}")
    print(f"    {ANALYSIS_OUT_DIR / f'trade-card-{args.date}.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
