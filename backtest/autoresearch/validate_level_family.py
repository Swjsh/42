"""Stage-1 price-space scan + real-fills validation for the LEVEL-KEYED watcher family.

Validates 5 level-keyed setups over the 16-month history:
  1. FLOOR_HOLD_DISTRIBUTION_BOUNCE  (floor_hold_bounce_watcher)        [disk-read]
  2. NAMED_LEVEL_WICK_BOUNCE         (named_level_wick_bounce_watcher)  [ctx.levels_active]
  3. NAMED_LEVEL_SECOND_TEST         (named_level_second_test_watcher)  [disk-read]
  4. CLOSE_CEILING_DISTRIBUTION_FADE (close_ceiling_fade_watcher)       [disk-read]
  5. ERL_IRL_SWEEP_FVG              (erl_irl_watcher)                   [ctx.levels_active]

CRITICAL CORRECTNESS NOTE (lesson L59 / theme C4 — read before trusting any number):
  Three of these watchers (floor_hold, close_ceiling, named_level_second_test) read
  `automation/state/key-levels.json` DIRECTLY FROM DISK via a module-level cache. They
  IGNORE ctx.levels_active. In a naive historical backtest this is a LOOK-AHEAD / wrong-
  levels bug: every historical bar would be tested against TODAY's levels.

  The harness (pattern_backtest._derive_named_levels) injects synthetic per-day PDH/PDL/
  PDC/PDO levels into ctx.levels_active — but the three disk-readers never consult ctx, so
  injecting into ctx alone does NOT fix them. This script therefore MONKEYPATCHES each
  disk-reader's level loader so it returns the synthetic per-day levels for the bar's date.
  After the patch the backtest is VALID (per-day levels, no look-ahead) — with the explicit
  caveat that PDH/PDL/PDC are ★★ structural proxies, NOT the production ★★★ named levels the
  live watchers fire on. Real production levels exist only in journal/key-levels-archive/
  (9 days, none covering J anchors or the bulk of the window), so a true ★★★ historical
  validation is impossible. This is disclosed in the scorecard's op20_disclosures block.

Usage:
  python -m autoresearch.validate_level_family --start 2025-01-01 --end 2026-06-16 [--realfills]
    [--out analysis/recommendations/level-family-validation.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)
from lib.watchers.runner import grade_observation  # noqa: E402

# The 5 detectors under test.
from lib.watchers.floor_hold_bounce_watcher import detect_floor_hold_bounce_setup  # noqa: E402
from lib.watchers.named_level_wick_bounce_watcher import detect_nlwb_setup  # noqa: E402
from lib.watchers.named_level_second_test_watcher import detect_named_level_second_test_setup  # noqa: E402
from lib.watchers.close_ceiling_fade_watcher import detect_close_ceiling_fade_setup  # noqa: E402
from lib.watchers.erl_irl_watcher import detect_erl_irl_setup  # noqa: E402

# Watcher modules whose disk-read level caches we monkeypatch per day.
from lib.watchers import floor_hold_bounce_watcher as _fhb_mod  # noqa: E402
from lib.watchers import close_ceiling_fade_watcher as _ccf_mod  # noqa: E402
from lib.watchers import named_level_second_test_watcher as _nlst_mod  # noqa: E402

DATA = REPO / "data"

# Anchor days per CLAUDE.md OP-16 / j_edge_tracker.
ANCHORS: dict[dt.date, str] = {
    dt.date(2026, 4, 29): "WIN",
    dt.date(2026, 5, 1): "WIN",
    dt.date(2026, 5, 4): "WIN",
    dt.date(2026, 5, 5): "LOSS",
    dt.date(2026, 5, 6): "LOSS",
    dt.date(2026, 5, 7): "LOSS",
}
EOD = dt.time(15, 50)

# Stream -> the metadata key that holds the chart level used as the real-fills rejection_level.
_REJ_LEVEL_KEY = {
    "FLOOR_HOLD_BOUNCE": "support_level",
    "NLWB": "bounce_level",
    "NAMED_LEVEL_SECOND_TEST": "named_level",
    "CLOSE_CEILING_FADE": "resistance_level",
    "ERL_IRL": "swept_level",
}

# Which streams read levels from disk (look-ahead trap) vs from ctx.levels_active.
_DISK_READ_STREAMS = {"FLOOR_HOLD_BOUNCE", "NAMED_LEVEL_SECOND_TEST", "CLOSE_CEILING_FADE"}
_CTX_STREAMS = {"NLWB", "ERL_IRL"}


def _load_data(start: dt.date, end: dt.date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the 16-month SPY + VIX 5m CSVs, dedup tz-variant duplicate rows."""
    spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-16.csv")
    vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-16.csv")
    for df in (spy, vix):
        df["_ts"] = pd.to_datetime(df["timestamp_et"], utc=True)
        df.drop_duplicates("_ts", inplace=True)
        df.drop(columns=["_ts"], inplace=True)
    return spy.reset_index(drop=True), vix.reset_index(drop=True)


def _sig_to_obs(s) -> dict:
    return {
        "direction": s.direction,
        "entry_price": s.entry_price,
        "stop_price": s.stop_price,
        "tp1_price": s.tp1_price,
        "runner_price": s.runner_price,
        "would_be_outcome": None,
    }


def _grade(sig, rth: pd.DataFrame, idx: int, bar_date: dt.date) -> tuple[str, float]:
    """SPY-price grade: walk forward to EOD with TP1+runner partial accounting."""
    day = rth[rth["timestamp_et"].dt.date == bar_date]
    fut = day[
        (day["timestamp_et"] > rth.iloc[idx]["timestamp_et"])
        & (day["timestamp_et"].dt.time <= EOD)
    ]
    o = grade_observation(_sig_to_obs(sig), fut)
    return o.get("would_be_outcome"), float(o.get("would_be_pnl_dollars") or 0.0)


def _stats(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "wr": 0.0, "total": 0.0, "exp": 0.0}
    wins = sum(1 for r in rows if r["pnl"] > 0)
    tot = sum(r["pnl"] for r in rows)
    return {"n": n, "wr": round(100 * wins / n, 1), "total": round(tot, 2), "exp": round(tot / n, 2)}


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}Q{q}"


def _per_quarter(rows: list[dict]) -> dict:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[_quarter(r["date"])].append(r)
    return {q: _stats(buckets[q]) for q in sorted(buckets)}


def _synthetic_levels_for_day(
    spy_full: pd.DataFrame, bar_date: dt.date
) -> tuple[list[float], list[float], list[float]]:
    """Synthesize the per-day PDH/PDL/PDC/PDO proxies (mirror of pattern_backtest
    ._derive_named_levels) directly from the data, with NO look-ahead.

    Returns (all_levels, support_levels, resistance_levels). PDH→resistance, PDL→support,
    PDC/PDO→both. These are the ★★ structural proxies the harness uses for ctx.levels_active.
    """
    prior = spy_full[spy_full["date"] < bar_date]
    if prior.empty:
        return [], [], []
    # Prior trading day's RTH bars.
    prior_day = prior["date"].max()
    pd_bars = spy_full[
        (spy_full["date"] == prior_day)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    if pd_bars.empty:
        return [], [], []
    pdh = round(float(pd_bars["high"].max()), 2)
    pdl = round(float(pd_bars["low"].min()), 2)
    pdc = round(float(pd_bars.iloc[-1]["close"]), 2)
    # Today's RTH open (known at bar 0, no look-ahead for any intraday bar).
    today_bars = spy_full[
        (spy_full["date"] == bar_date)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
    ]
    pdo = round(float(today_bars.iloc[0]["open"]), 2) if not today_bars.empty else None

    supports = [pdl, pdc]
    resistances = [pdh, pdc]
    if pdo is not None:
        supports.append(pdo)
        resistances.append(pdo)
    all_levels = sorted(set([pdh, pdl, pdc] + ([pdo] if pdo is not None else [])))
    return all_levels, sorted(set(supports)), sorted(set(resistances))


def _patch_disk_readers_for_day(
    supports: list[float], resistances: list[float], today_str: str
) -> None:
    """Force each disk-reading watcher's per-day cache to the SYNTHETIC per-day levels.

    This is the L59/C4 look-ahead fix: without it the watchers read today's live
    key-levels.json for every historical bar. We set the module-level caches directly
    (the loaders short-circuit when _cached_levels_date == today_str), so the watchers
    consume per-day proxies and the backtest is valid.
    """
    # floor_hold: single support list.
    _fhb_mod._cached_levels = sorted(set(supports))
    _fhb_mod._cached_levels_date = today_str
    # close_ceiling: single resistance list.
    _ccf_mod._cached_levels = sorted(set(resistances))
    _ccf_mod._cached_levels_date = today_str
    # named_level_second_test: separate support + resistance lists.
    _nlst_mod._cached_support = sorted(set(supports))
    _nlst_mod._cached_resistance = sorted(set(resistances))
    _nlst_mod._cached_levels_date = today_str


def _reset_watcher_state() -> None:
    """Reset per-watcher module cooldown + cache state so a fresh run is deterministic."""
    for mod in (_fhb_mod, _ccf_mod, _nlst_mod):
        if hasattr(mod, "_last_signal_time"):
            mod._last_signal_time = None
    _fhb_mod._cached_levels = []
    _fhb_mod._cached_levels_date = None
    _ccf_mod._cached_levels = []
    _ccf_mod._cached_levels_date = None
    _nlst_mod._cached_support = []
    _nlst_mod._cached_resistance = []
    _nlst_mod._cached_levels_date = None


def run(start: dt.date, end: dt.date, do_realfills: bool) -> dict:
    spy_full, vix_full = _load_data(start, end)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    streams: dict[str, list[dict]] = {
        "FLOOR_HOLD_BOUNCE": [],
        "NLWB": [],
        "NAMED_LEVEL_SECOND_TEST": [],
        "CLOSE_CEILING_FADE": [],
        "ERL_IRL": [],
    }
    anchor_hits: dict[dt.date, dict[str, dict]] = defaultdict(
        lambda: {k: {"n": 0, "pnl": 0.0} for k in streams}
    )
    # real-fills inputs: stream -> list of (idx, bar, sig)
    realfills_inputs: dict[str, list] = {k: [] for k in streams}

    _reset_watcher_state()
    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    # Per-day synthetic-level cache so we compute proxies once per day.
    _day_levels_cache: dict[dt.date, tuple[list[float], list[float], list[float]]] = {}

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = bar_time.date()
        if start and bar_date < start:
            continue
        if end and bar_date > end:
            continue
        if last_date is not None and bar_date != last_date:
            ribbon_history = []
            level_states = {}
        last_date = bar_date
        if idx < 60:
            continue

        try:
            r = ribbon_df.iloc[idx]
            ribbon_state = RibbonState(
                fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                stack=str(r["stack"]), spread_cents=float(r["spread_cents"]),
            )
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]

        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        # ---- Synthetic per-day levels (no look-ahead): both into ctx AND patched into disk-readers ----
        if bar_date not in _day_levels_cache:
            _day_levels_cache[bar_date] = _synthetic_levels_for_day(spy_full, bar_date)
        all_levels, supports, resistances = _day_levels_cache[bar_date]
        today_str = bar_date.isoformat()
        _patch_disk_readers_for_day(supports, resistances, today_str)

        # multi_day subset: PDH/PDL/PDC/PDO are all prior-day-derived → treat as multi_day.
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None
        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time.to_pydatetime(),
            bar=bar,
            prior_bars=rth.iloc[: idx + 1],
            ribbon_now=ribbon_state,
            ribbon_history=ribbon_history,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline,
            levels_active=all_levels,
            multi_day_levels=all_levels,
            htf_15m_stack=htf,
            level_states=level_states,
        )
        _update_level_states(level_states, all_levels, bar, idx)

        # ---- Fire all 5 detectors ----
        detectors = [
            ("FLOOR_HOLD_BOUNCE", detect_floor_hold_bounce_setup),
            ("NLWB", detect_nlwb_setup),
            ("NAMED_LEVEL_SECOND_TEST", detect_named_level_second_test_setup),
            ("CLOSE_CEILING_FADE", detect_close_ceiling_fade_setup),
            ("ERL_IRL", detect_erl_irl_setup),
        ]
        for stream, fn in detectors:
            try:
                sig = fn(ctx)
            except Exception as exc:  # surface, never swallow (C7)
                sys.stderr.write(f"{stream} exception @ {bar_time}: {type(exc).__name__}: {exc}\n")
                continue
            if sig is None:
                continue
            out, pnl = _grade(sig, rth, idx, bar_date)
            streams[stream].append({
                "date": today_str, "conf": sig.confidence, "dir": sig.direction,
                "out": out, "pnl": pnl, "vix": round(vix_now, 1),
            })
            if bar_date in ANCHORS:
                anchor_hits[bar_date][stream]["n"] += 1
                anchor_hits[bar_date][stream]["pnl"] = round(anchor_hits[bar_date][stream]["pnl"] + pnl, 2)
            realfills_inputs[stream].append((idx, bar, sig))

    # ---- Dedup: one signal per (date, direction) per stream, keep first ----
    def _dedup(rows: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        kept: list[dict] = []
        for r in rows:
            key = (r["date"], r["dir"])
            if key in seen:
                continue
            seen.add(key)
            kept.append(r)
        return kept

    streams_out: dict[str, dict] = {}
    for stream, rows in streams.items():
        deduped = _dedup(rows)
        distinct_dates = len({r["date"] for r in rows})
        streams_out[stream] = {
            "raw": _stats(rows),
            "deduped": _stats(deduped),
            "per_quarter_deduped": _per_quarter(deduped),
            "distinct_dates": distinct_dates,
        }

    result: dict = {
        "window": f"{start}..{end}",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "level_source_correctness": {
            "ctx_levels_active_streams": sorted(_CTX_STREAMS),
            "disk_read_streams": sorted(_DISK_READ_STREAMS),
            "disk_read_fix": (
                "Disk-read watchers (floor_hold, close_ceiling, named_level_second_test) "
                "ignore ctx.levels_active and read automation/state/key-levels.json from disk. "
                "Without a fix that is a look-ahead bug (today's levels on all historical bars). "
                "This run MONKEYPATCHES each disk-reader's per-day cache to synthetic PDH/PDL/PDC/PDO "
                "proxies (mirror of pattern_backtest._derive_named_levels) so the backtest is VALID. "
                "CAVEAT: proxies are ★★ structural levels, NOT production ★★★ named levels — production "
                "key-levels.json is not archived historically (9 archive days only, none on J anchors)."
            ),
            "synthetic_level_basis": "PDH(resistance ★★) / PDL(support ★★) / PDC(both ★) / PDO(both ★)",
        },
        "streams": streams_out,
        "anchor_days": {
            str(d): {
                "label": ANCHORS[d],
                **{k: anchor_hits[d][k] for k in streams},
            }
            for d in sorted(ANCHORS)
        },
    }

    # ---- Real-fills (optional) ----
    if do_realfills:
        from lib.simulator_real import simulate_trade_real
        rf: dict = {}
        for stream, inputs in realfills_inputs.items():
            rej_key = _REJ_LEVEL_KEY[stream]
            for label, offset in (("ATM", 0), ("ITM2", -2)):
                rows: list[dict] = []
                for (idx, bar, sig) in inputs[:120]:
                    side = "C" if sig.direction == "long" else "P"
                    rej = sig.metadata.get(rej_key)
                    if rej is None:
                        rej = sig.stop_price
                    try:
                        fill = simulate_trade_real(
                            entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                            rejection_level=float(rej), triggers_fired=list(sig.triggers_fired),
                            side=side, qty=3, setup=sig.setup_name,
                            premium_stop_pct=-0.99, strike_offset=offset,
                        )
                    except Exception as exc:
                        sys.stderr.write(f"realfills {stream}/{label} exc @ {bar['timestamp_et']}: "
                                         f"{type(exc).__name__}: {exc}\n")
                        fill = None
                    if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
                        rows.append({"pnl": float(fill.dollar_pnl)})
                rf[f"{stream}_{label}"] = _stats(rows)
        result["real_fills_capped"] = rf

    # ---- Per-stream verdicts + top-level verdict ----
    result["verdict"] = _build_verdicts(result)
    result["op20_disclosures"] = _op20_disclosures(result)
    return result


def _build_verdicts(result: dict) -> dict:
    """Per-stream PROMOTE-CANDIDATE / WATCH-ONLY / FAILS-REAL-FILLS / NOT-VALIDATABLE.

    Gates: n>=20, WR>=45%, exp>0 (deduped SPY-space), real-fills exp>0 if available,
    anchor-no-regression (no net loss on WIN days, no net loss-add on LOSS days).
    """
    verdicts: dict = {}
    rf = result.get("real_fills_capped", {})
    anchors = result["anchor_days"]
    for stream, s in result["streams"].items():
        dd = s["deduped"]
        n, wr, exp = dd["n"], dd["wr"], dd["exp"]
        # anchor check
        win_pnl = sum(anchors[d][stream]["pnl"] for d in anchors if anchors[d]["label"] == "WIN")
        loss_pnl = sum(anchors[d][stream]["pnl"] for d in anchors if anchors[d]["label"] == "LOSS")
        anchor_ok = (win_pnl >= 0) and (loss_pnl >= 0)
        rf_atm = rf.get(f"{stream}_ATM", {})
        rf_itm2 = rf.get(f"{stream}_ITM2", {})
        rf_atm_exp = rf_atm.get("exp")
        rf_itm2_exp = rf_itm2.get("exp")

        if n < 20:
            enum = "WATCH-ONLY"
            why = (f"Insufficient n (deduped n={n} < 20). SPY-space WR={wr}% exp=${exp}. "
                   f"Accumulate more observations.")
        elif wr < 45 or exp <= 0:
            enum = "WATCH-ONLY"
            why = (f"SPY-space gate FAIL (n={n}, WR={wr}%, exp=${exp}). "
                   f"No edge even under generous PDH/PDL/PDC proxies.")
        elif rf and (rf_atm_exp is not None) and rf_atm_exp <= 0 and (rf_itm2_exp is None or rf_itm2_exp <= 0):
            enum = "FAILS-REAL-FILLS"
            why = (f"SPY-space passes (n={n}, WR={wr}%, exp=${exp}) but real-fills negative "
                   f"(ATM exp=${rf_atm_exp}, ITM2 exp=${rf_itm2_exp}). R:R/theta mismatch.")
        elif not anchor_ok:
            enum = "WATCH-ONLY"
            why = (f"SPY-space passes (n={n}, WR={wr}%) but anchor regression "
                   f"(WIN-day pnl=${round(win_pnl,2)}, LOSS-day pnl=${round(loss_pnl,2)}).")
        else:
            enum = "PROMOTE-CANDIDATE"
            why = (f"SPY-space n={n}, WR={wr}%, exp=${exp}; real-fills ATM exp=${rf_atm_exp}, "
                   f"ITM2 exp=${rf_itm2_exp}; anchors clean. Confirm on production ★★★ levels before live wiring.")

        validity = "VALID_ON_PROXY" if stream in _CTX_STREAMS else "VALID_ON_PROXY_VIA_MONKEYPATCH"
        verdicts[stream] = {
            "verdict": enum,
            "why": why,
            "historical_validity": validity,
            "level_source": "ctx.levels_active" if stream in _CTX_STREAMS else "disk-read (monkeypatched to per-day proxy)",
        }
    verdicts["gate"] = (
        "Gates: deduped n>=20 AND WR>=45% AND exp>0 AND real-fills exp>0 AND anchor-no-regression. "
        "All level-keyed watchers remain WATCH-ONLY in production (OP-21) until live J confirmations. "
        "NOTE: every verdict is on ★★ PDH/PDL/PDC PROXIES — production ★★★ levels are not historically "
        "archived. The honest production-validity status for the 3 disk-readers is NOT-VALIDATABLE on real "
        "★★★ levels (no archive); the numbers above are the best obtainable proxy lower-bound."
    )
    return verdicts


def _op20_disclosures(result: dict) -> dict:
    return {
        "account_size_assumption": "Per-contract P&L, qty=3 (SPY price * 100). No account-equity sizing applied.",
        "simulator": "SPY-price grader (lib.watchers.runner.grade_observation, TP1+runner partials). "
                     "Real-fills via lib.simulator_real.simulate_trade_real + OPRA cache (valid through 2026-05-29).",
        "oos_sample_size": "16-month window 2025-01-01..2026-06-16; see per-stream distinct_dates + per_quarter_deduped.",
        "concentration": "Inspect per_quarter_deduped for single-quarter clustering; deduped to 1 signal/(date,dir).",
        "worst_case": "Real-fills total_pnl is the realized worst-case dollar figure per stream (premium_stop=-0.99, chart-stop only).",
        "synthetic_levels_caveat": (
            "ALL FIVE streams are validated against SYNTHETIC PDH/PDL/PDC/PDO (★★/★ proxies), NOT the production "
            "★★★ named levels in key-levels.json. The 3 disk-reading watchers were monkeypatched to consume these "
            "proxies (otherwise look-ahead). NLWB + ERL_IRL read ctx.levels_active natively (also proxies here). "
            "Production key-levels.json has no historical archive beyond 9 recent days (none on J anchor days), so a "
            "true ★★★ historical validation is impossible. Numbers here are a LOWER-BOUND proxy: PDL-class proxies "
            "historically understate ★★★ WR by up to ~20pp (see NLWB docstring / L58)."
        ),
        "live_schema_caveat": (
            "SEPARATE BUG (another agent owns it): the LIVE key-levels.json uses `tier` (Active/Carry/Reference) "
            "and has NO `strength.stars` field, while these watchers filter on strength.stars>=2. So floor_hold / "
            "close_ceiling / named_level_second_test currently fire on NOTHING live. This validation bypasses that "
            "by injecting synthetic levels with explicit support/resistance roles; it does not fix the live schema."
        ),
        "grading_caveat": (
            "SPY-price grade uses +$ proxy targets; it systematically overstates 0DTE call/put P&L in low-VIX "
            "(theta drag). Real-fills is the only WR authority (theme C1). Trust real_fills_capped over SPY-space."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-06-16")
    ap.add_argument("--realfills", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end), a.realfills)
    print(json.dumps(res, indent=2, default=str))
    if a.out:
        out_path = Path(a.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
