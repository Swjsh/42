"""free_model_audit_heartbeat_veto.py — the "heartbeat_veto" AUDIT_SUBJECTS adapter.

Grades heartbeat_core.py's `_free_model_eval` — 2 free-tier lanes (as of 2026-07-11:
"ollama::qwen3:14b" local + "openrouter::nvidia/nemotron-3-super-120b-a12b:free") that vote
GO/NO-GO on a deterministic rules-engine ENTER signal. Veto fires if every lane that answered
says NO-GO (1 dissent allowed — note the logged asymmetry: a lone NO is sufficient to veto,
but a lone GO is sufficient to pass; see heartbeat_core.py:630-634). This is the highest-
stakes free-model surface in the whole rig: it blocks real paper trades right now.

READ-ONLY. This module never imports anything from heartbeat_core that places an order, never
calls fleet_broker's order-placement/cancel methods, never writes core-decisions.jsonl /
aggressive/decisions.jsonl / fleet/*/decisions.jsonl. It reads:
  - automation/state/core-decisions.jsonl   (the ONLY real veto source -- verified: fleet arms
    safe-1/safe-3/risky-1/risky-3 have ZERO free_eval occurrences, and
    automation/state/aggressive/decisions.jsonl is a DEAD pre-2026-06-25 legacy file from the
    old LLM-heartbeat era, superseded when heartbeat_core.py shipped -- confirmed empty of
    free_eval, last row is tick_id 39 dated 2026-06-24. The account="bold" veto-eval activity
    lives in core-decisions.jsonl, same file as "safe", not in aggressive/decisions.jsonl.)
  - fills-ledger.jsonl (via trade_autopsy.load_engine_positions, reused) for real-fill P&L on
    GO decisions.
  - automation/state/circuit-breaker.json / aggressive/circuit-breaker.json for a best-effort
    equity fallback (reconstruction only; never a live account call).

GRADING (see free_model_audit.py module docstring for the full priority order):
  1. Real fill P&L (GO items whose exec reached a real broker fill) — objective, cheapest.
  2. Counterfactual replay (VETOED items, and GO items with no real fill) — reconstructs the
     option symbol via the SAME pure strike-selection formula heartbeat_core._execute uses
     (crypto/lib/strike_selection.pick_strike — deterministic given spot/equity/side/tier,
     needs no historical params.json snapshot since the v15 tier tables are hardcoded
     constants), fetches REAL OPRA 1-min bars (exit_shape_parity_study.fetch_option_bars,
     reused), and replays through the REAL exit_manager decision core
     (exit_shape_parity_study.replay_position, reused) — the exact mechanism
     trade_autopsy.py uses for real fills, applied to the mirror case (a signal that was
     blocked or fell through, not filled).
  3. Blind Sonnet re-judgment (fallback only) — shows Sonnet the IDENTICAL snapshot string
     heartbeat_core._veto_snapshot renders for the free models (imported and called
     byte-identically, not reimplemented), withOUT revealing what the free models answered,
     via the SAME `claude --print --model claude-sonnet-4-6 < promptfile` pattern already
     proven in setup/scripts/manager_overseer.py (grepped first; genuinely reused, not
     reinvented).
  4. `ungraded_insufficient_data` if none of the above produce a real number — never guessed.

KNOWN, DISCLOSED APPROXIMATIONS (logged per-item in `evidence_summary`/`detail`, never hidden):
  - Strike reconstruction uses the GENERIC v15 tier ladder, not any per-setup override
    (heartbeat_core._SETUP_STRIKE_OVERRIDES) -- those overrides key off params.json values at
    veto time, which is not snapshotted historically, so replaying them precisely is not
    reconstructable. This can pick a different (nearby) strike than production would have for
    an armed extra-setup override; documented, not hidden. Does not apply to the core-ribbon
    path (no override there).
  - Entry price proxy = the first post-tick 1-min bar's OPEN (no historical bid/ask quote
    exists for a trade that was never placed); real entries price at ask+buffer, so replay PnL
    is a reasonable-but-not-exact proxy, not an exact fill reconstruction.
  - Equity used for strike-tier lookup: best-effort regex scan of same-day ledger rows'
    embedded "equity $X" text (risk_gate denial reasons routinely carry this), else the
    CURRENT circuit-breaker.json snapshot as a last resort. Method used is always logged.
  - Contract qty fixed at 3 (Rule 6 floor, CLAUDE.md "Min 3 contracts") -- affects reported $
    magnitude but not the correct/wrong sign determination in the vast majority of cases.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

REPO = Path(__file__).resolve().parents[2]
for _p in ("crypto/lib", "automation/state/fleet", "setup/scripts", "backtest/lib", "backtest/tools"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

from et_clock import ET_TZ  # noqa: E402

STATE = REPO / "automation" / "state"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
CIRCUIT_BREAKER_SAFE = STATE / "circuit-breaker.json"
CIRCUIT_BREAKER_BOLD = STATE / "aggressive" / "circuit-breaker.json"
PROMPT_TMP = STATE / ".free-model-audit-prompt.tmp"

_ARM_FOR_ACCOUNT = {"safe": "safe-2", "bold": "bold-2"}
_EXTRA_DIR_TO_SIDE = {"long": "C", "short": "P"}  # mirrors heartbeat_core._EXTRA_DIR_TO_VERDICT
DEFAULT_REPLAY_QTY = 3  # Rule 6 floor ("min 3 contracts"); sign of PnL is qty-invariant here
MARGIN_DOLLARS = 15.0   # noise band (~half a 3-lot at a nickel-wide spread); see module docstring

# Verbatim copy of heartbeat_core._free_model_eval's sysmsg (2026-07-11) -- kept identical on
# purpose so the Sonnet fallback judges against the SAME rubric the free models were given
# (apples-to-apples independent re-judgment, not a different, easier-to-pass bar). A pytest
# guard (test_free_model_audit_heartbeat_veto.py::test_sysmsg_matches_heartbeat_core_source)
# greps heartbeat_core.py for a fragment of this string so drift is caught, not silent.
_SYSMSG = ("You are a 0DTE SPY options risk checker. A deterministic rules engine wants to ENTER. "
          "Your ONLY job: is this a SANE entry given the tape, or is something clearly off "
          "(chop, conflicting HTF, VIX spike, no real level)? You can only VETO a bad entry; "
          "you cannot create one. Default go=true unless something is clearly wrong. JSON only.")

_PROMPT_TEMPLATE = """{sysmsg}

You are being asked to give an INDEPENDENT second opinion for an audit — you have NOT been
told what any other model decided. Judge this entry SOLELY on the snapshot below.

Sanity-check this entry:
{snapshot}

Output ONLY a JSON object: {{"go": true|false, "reason": "<one short sentence>"}}. No preamble,
no code fences, no other text.
"""

SONNET = "claude-sonnet-4-6"  # matches manager_overseer.py's constant exactly (reused pattern)


# --------------------------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------------------------

def _et_naive_to_utc_iso(ts_et: str) -> Optional[str]:
    """'2026-07-08T10:04:04' (naive ET, as logged) -> '2026-07-08T14:04:04Z' (UTC), DST-aware
    via et_clock.ET_TZ (never a hardcoded -4h offset -- CLAUDE.md's standing TZ mandate)."""
    try:
        naive = datetime.fromisoformat(str(ts_et))
    except ValueError:
        return None
    aware_et = naive.replace(tzinfo=ET_TZ)
    return aware_et.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _occ_symbol(side: str, strike: int, expiry: datetime) -> str:
    """Mirrors heartbeat_core._occ verbatim (SPY<yymmdd><C|P><strike*1000, 8-digit>). Kept as
    a local pure copy rather than importing heartbeat_core, so this read-only audit tool never
    drags in that module's heavier (pandas/ribbon) import chain just for a 2-line formula."""
    cp = "C" if side == "C" else "P"
    return f"SPY{expiry.strftime('%y%m%d')}{cp}{int(round(strike * 1000)):08d}"


_EQUITY_RE = re.compile(r"equity \$([0-9][0-9,]*(?:\.[0-9]+)?)")


def _scan_equity_hint(row_blob: str) -> Optional[float]:
    m = _EQUITY_RE.search(row_blob)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _fallback_equity(account: str) -> float:
    path = CIRCUIT_BREAKER_BOLD if account == "bold" else CIRCUIT_BREAKER_SAFE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 2000.0  # last-resort constant, documented; never silently used without logging
    return float(data.get("equity_current") or data.get("current_equity")
                or data.get("equity_start_of_day") or data.get("starting_equity_today") or 2000.0)


def _ts_delta_seconds(a: str, b: str) -> float:
    try:
        da = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        db = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
        return abs((da - db).total_seconds())
    except (ValueError, TypeError):
        return float("inf")


# --------------------------------------------------------------------------------------------
# collect_items -- pure log reader. Returns EVERY evaluated tick (veto AND go) in [since,
# until]; the framework (free_model_audit.py) is responsible for skipping already-graded
# item_ids, so this stays a dumb, stateless, re-runnable reader.
# --------------------------------------------------------------------------------------------

def collect_items(since: Optional[date], until: date, *, path: Path = CORE_DECISIONS) -> list:
    from free_model_audit import AuditItem  # local import: avoids a circular import at module load
    if not path.exists():
        return []
    items: list[AuditItem] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        ts_et = row.get("ts_et")
        if not ts_et:
            continue
        try:
            row_date = date.fromisoformat(str(ts_et)[:10])
        except ValueError:
            continue
        if row_date > until or (since is not None and row_date < since):
            continue
        account = row.get("account") or "?"
        equity_hint = _scan_equity_hint(json.dumps(row))

        fe = row.get("free_eval")
        if isinstance(fe, dict) and fe.get("evaluated"):
            items.append(AuditItem(
                subject="heartbeat_veto", item_id=f"core:{account}:{ts_et}",
                timestamp_et=str(ts_et), account=account,
                context={"is_extra": False, "side": row.get("side"), "setup_name": row.get("setup"),
                        "spy": row.get("spy"), "ribbon": row.get("ribbon"),
                        "spread_cents": row.get("spread_cents"), "vix": row.get("vix"),
                        "htf_15m": row.get("htf_15m"), "verdict_str": row.get("verdict"),
                        "triggers": row.get("triggers") or [], "bear_score": row.get("bear_score"),
                        "bull_score": row.get("bull_score"), "ts_et": ts_et,
                        "date_et": str(ts_et)[:10], "account": account,
                        "equity_hint": equity_hint, "exec": row.get("exec")},
                free_model_output=fe))

        for extra in (row.get("extra_exec") or []):
            efe = extra.get("free_eval")
            if not (isinstance(efe, dict) and efe.get("evaluated")):
                continue
            setup = extra.get("setup")
            direction = None
            for sig in (row.get("extra_signals") or []):
                if sig.get("setup_name") == setup:
                    direction = sig.get("direction")
                    break
            side = _EXTRA_DIR_TO_SIDE.get(str(direction or "").lower())
            items.append(AuditItem(
                subject="heartbeat_veto", item_id=f"extra:{account}:{ts_et}:{setup}",
                timestamp_et=str(ts_et), account=account,
                context={"is_extra": True, "side": side, "setup_name": setup,
                        "spy": row.get("spy"), "ribbon": row.get("ribbon"),
                        "spread_cents": row.get("spread_cents"), "vix": row.get("vix"),
                        "htf_15m": row.get("htf_15m"),
                        "verdict_str": ("ENTER_BULL" if side == "C" else
                                       "ENTER_BEAR" if side == "P" else None),
                        "triggers": (next((sig.get("triggers") for sig in (row.get("extra_signals") or [])
                                          if sig.get("setup_name") == setup), []) or []),
                        "bear_score": None, "bull_score": None,  # extra setups aren't core-scored
                        "ts_et": ts_et, "date_et": str(ts_et)[:10], "account": account,
                        "equity_hint": equity_hint, "exec": extra.get("exec")},
                free_model_output=efe))
    return items


# --------------------------------------------------------------------------------------------
# Ground truth #1: real fill P&L (GO items only)
# --------------------------------------------------------------------------------------------

def _grade_via_real_fill(item) -> Optional[dict]:
    ctx = item.context
    exec_row = ctx.get("exec")
    if not isinstance(exec_row, dict):
        return None
    symbol = exec_row.get("symbol")
    if not symbol:
        return None
    arm = _ARM_FOR_ACCOUNT.get(ctx.get("account"))
    if not arm:
        return None
    try:
        import trade_autopsy as ta  # noqa: PLC0415
    except Exception:
        return None
    try:
        positions = ta.load_engine_positions(ctx["date_et"])
    except Exception:
        return None
    cands = [p for p in positions if p.get("arm") == arm and p.get("symbol") == symbol]
    if not cands:
        return None
    tick_ts = _et_naive_to_utc_iso(ctx["ts_et"]) or ctx["ts_et"]
    best = min(cands, key=lambda p: _ts_delta_seconds(p.get("entry_ts_utc", ""), tick_ts))
    if _ts_delta_seconds(best.get("entry_ts_utc", ""), tick_ts) > 600:
        return None  # not confidently the SAME tick's attempt -- don't guess
    pnl = best.get("actual_exit_pnl")
    if pnl is None:
        return None
    return {"pnl": float(pnl), "source": "real_fill", "symbol": symbol}


# --------------------------------------------------------------------------------------------
# Ground truth #2: counterfactual replay (reuses exit_shape_parity_study + strike_selection)
# --------------------------------------------------------------------------------------------

def _counterfactual_replay(item, *, fetch_bars_fn=None, replay_fn=None) -> Optional[dict]:
    ctx = item.context
    side = ctx.get("side")
    spy = ctx.get("spy")
    if side not in ("C", "P") or not spy:
        return None
    try:
        import strike_selection as ss  # noqa: PLC0415
        import exit_shape_parity_study as esp  # noqa: PLC0415
    except Exception:
        return None
    fetch_bars_fn = fetch_bars_fn or esp.fetch_option_bars
    replay_fn = replay_fn or esp.replay_position

    account = ctx.get("account")
    tiers = ss.V15_SAFE_TIERS if account == "safe" else ss.V15_BOLD_TIERS
    equity = ctx.get("equity_hint")
    equity_method = "reason_text_scan"
    if not equity:
        equity = _fallback_equity(account)
        equity_method = "current_snapshot_fallback"
    try:
        strike = ss.pick_strike(float(spy), float(equity), side, tiers)
    except (ValueError, TypeError):
        return None

    date_et = ctx.get("date_et")
    try:
        expiry = datetime.strptime(date_et, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    symbol = _occ_symbol(side, strike, expiry)

    try:
        bars = fetch_bars_fn(symbol, date_et)
    except Exception:
        bars = []
    if not bars:
        return None

    ts_utc = _et_naive_to_utc_iso(ctx.get("ts_et"))
    if not ts_utc:
        return None
    path_bars = [b for b in bars if b.get("t", "") >= ts_utc]
    if not path_bars:
        return None
    entry_price = path_bars[0].get("o")
    if not entry_price or entry_price <= 0:
        return None

    position = {"symbol": symbol, "entry_ts_utc": ts_utc, "entry_price": float(entry_price),
               "entry_qty": DEFAULT_REPLAY_QTY}
    shape = esp.SHAPES["v15_3_safe_ratified"]  # canonical ratified v15.3 shape (-50/+30/0.8)
    try:
        result = replay_fn(position, bars, shape)
    except Exception:
        return None
    pnl = result.get("pnl")
    if pnl is None:
        return None
    return {"pnl": float(pnl), "source": "replay", "symbol": symbol, "strike": strike,
           "equity_used": equity, "equity_method": equity_method,
           "entry_price_proxy": float(entry_price), "shape": "v15_3_safe_ratified",
           "n_bars": len(bars)}


# --------------------------------------------------------------------------------------------
# Ground truth #3 (fallback): blind Sonnet re-judgment
# --------------------------------------------------------------------------------------------

def _claude_exe() -> str:
    """Identical resolution cascade to manager_overseer.py / discord-responder.py (grepped
    first, genuinely reused -- see module docstring)."""
    import os  # noqa: PLC0415
    cands = [
        Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
        Path(r"C:\Users\jackw\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"),
        Path(r"C:\Users\jackw\AppData\Roaming\Claude\claude-code\2.1.181\claude.exe"),
    ]
    for c in cands:
        if c.exists():
            return str(c)
    return "claude"


def _build_snapshot(item) -> str:
    """Renders via heartbeat_core._veto_snapshot itself (imported, byte-identical rendering)
    whenever available; a manually-formatted equivalent (clearly tagged) is the fallback so a
    heartbeat_core import failure degrades gracefully instead of losing the LLM-fallback path
    entirely."""
    ctx = item.context
    bear = ctx.get("bear_score")
    bull = ctx.get("bull_score")
    try:
        import heartbeat_core as hbc  # noqa: PLC0415
        bc = {"bar": {"close": ctx.get("spy")},
             "ribbon_now": {"stack": ctx.get("ribbon"), "spread_cents": ctx.get("spread_cents")},
             "vix_now": float(ctx.get("vix") or 0.0), "vix_prior": float(ctx.get("vix") or 0.0),
             "htf_15m_stack": ctx.get("htf_15m"),
             "levels_active": "UNKNOWN_NOT_IN_LEDGER"}
        verdict = {"verdict": ctx.get("verdict_str"), "side": ctx.get("side"),
                  "setup_name": ctx.get("setup_name"), "triggers_fired": ctx.get("triggers"),
                  "bear_score": bear, "bull_score": bull}
        return hbc._veto_snapshot(bc, verdict)
    except Exception:
        scores = " ".join(s for s in (f"bear={bear}/10" if bear is not None else None,
                                      f"bull={bull}/11" if bull is not None else None) if s)
        setup_seg = f"setup={ctx.get('setup_name')}" + (f" {scores}" if scores else "")
        return (f"[DEGRADED-RENDER, heartbeat_core import failed] SPY={ctx.get('spy')} "
               f"ribbon={ctx.get('ribbon')} spread={ctx.get('spread_cents')}c VIX={ctx.get('vix')} "
               f"HTF15m={ctx.get('htf_15m')} rules_engine_says={ctx.get('verdict_str')} "
               f"side={ctx.get('side')} {setup_seg} triggers={ctx.get('triggers')}")


def _llm_judgment(item, *, timeout: int = 180) -> Optional[dict]:
    try:
        from swarm_client import extract_json  # noqa: PLC0415
    except Exception:
        extract_json = lambda s: json.loads(s)  # noqa: E731 -- last-ditch, rarely needed

    snap = _build_snapshot(item)
    prompt = _PROMPT_TEMPLATE.format(sysmsg=_SYSMSG, snapshot=snap)
    exe = _claude_exe()
    try:
        PROMPT_TMP.parent.mkdir(parents=True, exist_ok=True)
        PROMPT_TMP.write_text(prompt, encoding="utf-8")
    except OSError:
        return None
    try:
        proc = subprocess.run(f'"{exe}" --print --model {SONNET} < "{PROMPT_TMP}"',
                              shell=True, capture_output=True, text=True, timeout=timeout,
                              cwd=str(REPO), encoding="utf-8", errors="replace",
                              creationflags=_CREATE_NO_WINDOW)
    except Exception:
        return None
    out = extract_json(proc.stdout or "")
    if not isinstance(out, dict) or "go" not in out:
        return None
    return {"sonnet_go": bool(out.get("go")), "sonnet_reason": str(out.get("reason", ""))[:300]}


# --------------------------------------------------------------------------------------------
# grade_item -- the SubjectAdapter.grade entry point
# --------------------------------------------------------------------------------------------

def grade_item(item, opts: dict) -> dict:
    fmo = item.free_model_output
    n_lanes_answered = sum(1 for v in (fmo.get("votes") or []) if "go" in v)
    if not fmo.get("evaluated"):
        return {"decision": "unknown", "n_lanes_answered": n_lanes_answered,
               "grading_method": "ungraded_insufficient_data", "correct": None,
               "evidence_summary": "free models did not evaluate this tick"}

    veto = bool(fmo.get("veto"))
    decision = "veto" if veto else "go"
    base = {"decision": decision, "n_lanes_answered": n_lanes_answered}

    if not veto:
        real = _grade_via_real_fill(item)
        if real is not None:
            correct = real["pnl"] >= -MARGIN_DOLLARS
            return {**base, "grading_method": "counterfactual", "correct": correct,
                   "evidence_summary": f"real fill pnl=${real['pnl']:.2f} symbol={real['symbol']}",
                   "detail": real}

    cf = _counterfactual_replay(item)
    if cf is not None:
        pnl = cf["pnl"]
        correct = (pnl <= MARGIN_DOLLARS) if veto else (pnl >= -MARGIN_DOLLARS)
        return {**base, "grading_method": "counterfactual", "correct": correct,
               "evidence_summary": (f"replay pnl=${pnl:.2f} symbol={cf['symbol']} "
                                    f"strike={cf['strike']} equity_method={cf['equity_method']}"),
               "detail": cf}

    if opts.get("allow_llm_fallback", True):
        llm = _llm_judgment(item)
        if llm is not None:
            correct = (not llm["sonnet_go"]) if veto else llm["sonnet_go"]
            return {**base, "grading_method": "llm_judgment", "correct": correct,
                   "evidence_summary": (f"sonnet_go={llm['sonnet_go']} "
                                        f"reason={llm['sonnet_reason'][:100]}"),
                   "detail": llm}

    return {**base, "grading_method": "ungraded_insufficient_data", "correct": None,
           "evidence_summary": "no real fill + no option bars for replay + no/failed llm fallback"}
