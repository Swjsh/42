"""multi/lib/tickers_execute_support.py -- pure, I/O-light helpers for multi/execute.py.

Split out from execute.py purely to keep that module under its 800-line budget (coding-style:
many small files > few large files, extract utilities from large modules). Nothing here
resolves credentials, calls the broker, or places an order -- every function is either a pure
computation or a single, narrowly-scoped local file read (`precheck_creds`), so this module is
trivially unit-testable without any of execute.py's monkeypatch surface (no module-level path
globals to redirect -- every path this file touches is passed in by the caller).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Optional

from multi.lib import exits as mex
from multi.lib import levels as mlv

INVARIANT_MAX_CONTRACTS_CEILING = 5
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


class InvariantFail(RuntimeError):
    """A named, loud, arm-scoped self-check failure. Aborts the ONE arm, never the process."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def is_spy_like(root_or_symbol: Optional[str]) -> bool:
    """True if the (uppercased) root/symbol IS or STARTS WITH 'SPY' -- a PREFIX check, not
    exact-equality: this lane must never touch the separate live-money SPY engine's turf, and
    a prefix match is the more conservative direction to be wrong in."""
    if not root_or_symbol:
        return False
    return str(root_or_symbol).upper().startswith("SPY")


def clamp_entry_qty(raw_qty: Any, *, min_contracts: int, max_contracts: int) -> tuple[int, Optional[str]]:
    """(qty, block_reason). block_reason is None iff qty >= min_contracts.

    `raw_qty` (read from a WOULD_PLACE row's "qty") may be None or "" -- both are treated as
    0, the safe direction. The result is clamped to [0, max_contracts]; a clamped qty below
    min_contracts is blocked (block_reason set) rather than silently rounded up to the
    minimum."""
    try:
        qty = int(raw_qty) if raw_qty is not None and raw_qty != "" else 0
    except (TypeError, ValueError):
        qty = 0
    qty = max(0, min(qty, int(max_contracts)))
    if qty < int(min_contracts):
        return qty, (f"qty {raw_qty!r} clamped to {qty} < min_contracts {min_contracts} "
                      f"(max_contracts {max_contracts})")
    return qty, None


def parse_hhmm(value: Any) -> dt.time:
    m = _HHMM_RE.match(str(value).strip())
    if not m:
        raise InvariantFail("bad_hhmm", f"{value!r} is not an HH:MM[:SS] time string")
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return dt.time(hh, mm, ss)


def bars_facts(bars: Optional[dict], symbol: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """(underlying_price, atr14) recomputed from the SAME daily bars dict the tick already
    used -- mirrors multi/core.py::manage_open_positions's DAILY-CLOSE fallback derivation
    exactly (identical >15-bar guard, same mlv._atr call).

    FALLBACK ONLY as of the 2026-09-04 review (BUG 2 fix): manage_open_positions's own
    underlying_price is no longer just this daily close -- it prefers a LIVE quote first
    (core.fetch_underlying_last) and falls back to the daily close (this same computation)
    only when that live read fails, disclosing which one won via row["underlying_source"].
    `re_derive_exit_record` below therefore PREFERS the row's own persisted underlying_price/
    atr14 (the exact facts the tick actually evaluated against, live or stale) and calls this
    function only when the row doesn't carry them -- so a re-derive never silently swaps a
    live figure the tick used for a different, always-stale one recomputed here."""
    df = (bars or {}).get(symbol) if symbol else None
    if df is None or len(df) <= 15:
        return None, None
    try:
        return float(df["close"].iloc[-1]), mlv._atr(df)
    except Exception:  # noqa: BLE001 -- a bad bar frame degrades to "cannot re-derive", never crashes
        return None, None


def re_derive_exit_record(rec, r: dict, bars: Optional[dict], arm_params: dict, *,
                          now_aware: dt.datetime, best_override: Any = None):
    """Re-run evaluate_exit with the row's OWN bid/ask (never a fresh quote -- that would race
    the price tick() already decided this row against) purely to obtain the touched
    PositionRecord for persistence: tick()'s exit_eval rows carry the DECISION but not
    `.record`. Raises mex.ExitConfigError on malformed params -- the caller logs and
    continues, per execute.py's fail-per-row design.

    open_qty/underlying_price/atr14 all PREFER the row `r` (the exact facts manage_open_
    positions actually evaluated this contract against this tick -- broker-truth qty, a live
    or disclosed-stale underlying, per-tick ATR14) and fall back to rec.qty / a fresh
    bars_facts() recomputation only when the row lacks them (an older or foreign row shape).
    Falling back to rec.qty here would reintroduce BUG 1 (the original entry qty, never
    decremented after a partial close) for this specific caller; falling back to bars_facts()
    when the row already has better facts would reintroduce BUG 2 (a stale daily close) for
    it -- both bugs fixed 2026-09-04."""
    row_underlying = r.get("underlying_price")
    row_atr14 = r.get("atr14")
    if row_underlying is not None and row_atr14 is not None:
        underlying, atr14 = row_underlying, row_atr14
    else:
        underlying, atr14 = bars_facts(bars, r.get("symbol"))
    best = best_override if best_override is not None else (r.get("ask") or rec.hwm_premium)
    worst = r.get("bid") or rec.entry_premium
    row_open_qty = r.get("open_qty")
    open_qty = row_open_qty if isinstance(row_open_qty, int) and row_open_qty > 0 else rec.qty
    ed = mex.evaluate_exit(rec, now_et=now_aware, best_premium=float(best),
                           worst_premium=float(worst), open_qty=open_qty,
                           underlying_price=underlying, atr14=atr14, params=arm_params)
    return ed.record if ed.record is not None else rec


def check_static_invariants(lane_params: dict, arm: str, arm_cfg: Optional[dict], *,
                            now: dt.datetime, ignore_window: bool = False) -> None:
    """Every check raises InvariantFail (never exits the process). `now` is injected (the
    caller's et_clock-derived now_et()) so this stays a pure function of its arguments.
    Creds/paper-only is NOT checked here -- that needs the NO_CREDS self-heal file read and a
    live resolve(), both of which are execute.py's own concern (run_arm, steps 2-3)."""
    if str(lane_params.get("arm")) != "tickers":
        raise InvariantFail("lane_arm_mismatch", f"params.arm={lane_params.get('arm')!r}, expected 'tickers'")
    if not isinstance(lane_params.get("shadow_only"), bool):
        raise InvariantFail("shadow_only_not_bool", f"shadow_only={lane_params.get('shadow_only')!r}")
    if lane_params.get("scorer") != "production":
        raise InvariantFail("scorer_mismatch", f"scorer={lane_params.get('scorer')!r}, expected 'production'")
    if not isinstance(arm_cfg, dict):
        raise InvariantFail("arm_config_missing", f"arms.{arm} missing from params.json")
    if arm_cfg.get("key_source") != arm:
        raise InvariantFail("key_source_mismatch",
                             f"arms.{arm}.key_source={arm_cfg.get('key_source')!r}, expected {arm!r} "
                             f"(a mismatch would trade this arm's signals on another arm's account)")
    universe = arm_cfg.get("universe")
    if not isinstance(universe, list) or not universe:
        raise InvariantFail("universe_empty", f"arms.{arm}.universe is empty")
    for sym in universe:
        if is_spy_like(str(sym)):
            raise InvariantFail("universe_contains_spy", f"arms.{arm}.universe contains {sym!r}")
    risk = lane_params.get("risk") or {}
    max_c, min_c = risk.get("max_contracts"), risk.get("min_contracts")
    if max_c is None:
        raise InvariantFail("max_contracts_missing", "risk.max_contracts missing")
    if int(max_c) > INVARIANT_MAX_CONTRACTS_CEILING:
        raise InvariantFail("max_contracts_too_high",
                             f"risk.max_contracts={max_c} > ceiling {INVARIANT_MAX_CONTRACTS_CEILING}")
    if min_c is None:
        raise InvariantFail("min_contracts_missing", "risk.min_contracts missing")
    if int(min_c) > int(max_c):
        raise InvariantFail("min_gt_max_contracts", f"min_contracts {min_c} > max_contracts {max_c}")
    if now.weekday() >= 5:
        raise InvariantFail("weekend", f"now_et={now.isoformat()} is a weekend")
    hhmm = now.hour * 100 + now.minute
    if ignore_window:
        return  # SHADOW-ONLY E2E probe (execute.py --e2e-probe-root): off-hours dry run, nothing is sent
    if not (930 <= hhmm <= 1500):
        raise InvariantFail("outside_session_window",
                             f"now_et={now.isoformat()} outside the 09:30-15:00 ET self-check "
                             f"window (Gamma_TickersEodFlatten at 14:52 ET is the safety net for "
                             f"anything after; the scheduled task itself never fires outside "
                             f"09:35-14:55, so this only guards manual/off-hours runs)")


def precheck_creds(secrets_path: Path, key_source: Optional[str], arm: str) -> Optional[str]:
    """Returns an error string when `secrets_path` is missing, or the arm's entry is
    missing/placeholder -- None when it looks pasteable-and-real. Purely a local file check
    (never touches the broker) so a fresh box with no secrets.json yet logs ONE clear NO_CREDS
    line instead of a traceback."""
    if not key_source:
        return f"arms.{arm}.key_source is not set"
    if not secrets_path.exists():
        return f"{secrets_path} missing -- paste it (template: secrets.json.example)"
    try:
        doc = json.loads(secrets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"cannot read {secrets_path}: {e}"
    entry = (doc.get("accounts") or {}).get(key_source)
    if not isinstance(entry, dict):
        return f"{secrets_path} missing accounts.{key_source} entry -- paste it (template: secrets.json.example)"
    key = str(entry.get("key") or entry.get("api_key") or "")
    secret = str(entry.get("secret") or entry.get("api_secret") or "")
    if not key or not secret or "<PASTE" in key or "<PASTE" in secret:
        return (f"accounts.{key_source} in {secrets_path} is a placeholder -- paste it "
                f"(template: secrets.json.example)")
    return None
