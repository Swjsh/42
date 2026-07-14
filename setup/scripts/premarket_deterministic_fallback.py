"""premarket_deterministic_fallback.py -- A5, the premarket LLM-step safety net.

WHY THIS EXISTS (analysis/deep-research/2026-07-14-premarket-reliability.md): a
3-week audit found the premarket LLM step (automation/prompts/premarket.md via
`claude --print`) misses 25-44% of trading days across THREE distinct failure
shapes -- CCR/auth outage (400/"Not logged in"), hollow-success (exit 0, empty
falsifiable_predictions), and reaped-silent (killed mid-run, no terminal log
line). All three degrade to the same downstream symptom: a stale
`today-bias.json` the engine's human-readable context layer never refreshes.

The breaker-arm half of Gamma_Premarket (`daily_loss_guard.rearm()`) is ALREADY
deterministic and un-blockable -- it hits Alpaca REST directly, no LLM, no MCP.
This script closes the other half: the bias/levels NARRATIVE. It is pure Python
($0, no LLM, no MCP, no CDP) and reuses the exact same "never-blind" data paths
already proven to survive the outages that kill the LLM step:
  - SPY 5m OHLC bars: direct Alpaca REST (IEX feed), same call shape as
    sight_beacon.py / refresh_levels_intraday.py / heartbeat_core.py.
  - VIX: yfinance ^VIX 5m closes, same call shape as heartbeat_core._fetch_vix.
  - Account equity / day-trades-used: read from circuit-breaker.json /
    aggressive/circuit-breaker.json -- ALREADY freshened this same run by
    run-premarket.ps1's daily_loss_guard.rearm() step (which runs BEFORE the
    LLM attempt and does not depend on it), so no extra network call needed
    for the load-bearing equity fields unless that rearm itself failed too.
  - key_levels: read automation/state/key-levels.json (an independently
    maintained deterministic producer, refresh_levels_intraday.py) for
    today's near-price support/resistance; only recomputes prior-day H/L from
    bars directly if that file is itself stale/missing.
  - news_calendar: setup/scripts/macro_calendar.py#run(do_fetch=False) --
    the calendar's own deterministic, non-LLM producer.
  - rule_version_pin: reads RULE_VERSION_EXPECTED straight out of
    automation/prompts/premarket.md (single source, no hand-duplicated
    constant to drift) vs params.json#rule_version.

BIAS FORMULA (deliberately mechanical, no chart/ribbon/trendline read):
    pct_change = (premarket_close - prior_session_close) / prior_session_close
    overnight_position = (premarket_close - overnight_low) / (overnight_high - overnight_low)
    bullish  if pct_change >  +0.0005 AND overnight_position > 0.5
    bearish  if pct_change <  -0.0005 AND overnight_position < 0.5
    neutral  otherwise (including any disagreement between the two signals)

WHAT THIS DELIBERATELY DOES NOT DO (per the reliability-audit spec, section
"Does NOT attempt"): no chart-based levels, no ribbon/EMA stack, no trendline
read, and it writes ZERO falsifiable_predictions rather than fabricate a
qualitative call it cannot back. Every write is stamped `"degraded": true,
"source": "deterministic_fallback"` at the top level so nothing downstream
(dashboard, journal, any future consumer) can mistake this for the real
LLM-authored narrative read.

FAIL-SAFE BY DESIGN: if the PRIMARY input (SPY bars, needed to compute any
bias at all) cannot be fetched from EITHER Alpaca REST or yfinance, this
script refuses to write a fabricated bias -- it exits non-zero and leaves
today-bias.json untouched, so run-premarket.ps1's existing BROKEN/STALE path
stays in force. Every SECONDARY input (VIX, key levels, news calendar,
equity) degrades independently and explicitly (a null field + a note in
readiness_flags) rather than blocking the whole write or inventing a number.

Wired into: setup/scripts/run-premarket.ps1, invoked only after BOTH LLM
attempts have been exhausted AND the OP-33 deliverable-verify gate has
determined the LLM produced no usable bias (stale date, hollow predictions,
or hand-rebuild author marker).

CLI:
    python setup/scripts/premarket_deterministic_fallback.py             # write today-bias.json
    python setup/scripts/premarket_deterministic_fallback.py --dry-run   # compute + print only
    python setup/scripts/premarket_deterministic_fallback.py --date 2026-07-14  # backfill/testing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
TODAY_BIAS = STATE / "today-bias.json"
KEY_LEVELS = STATE / "key-levels.json"
PARAMS = STATE / "params.json"
SAFE_BREAKER = STATE / "circuit-breaker.json"
BOLD_BREAKER = STATE / "aggressive" / "circuit-breaker.json"
PREMARKET_PROMPT = REPO / "automation" / "prompts" / "premarket.md"

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
from et_clock import et_now, ET_TZ  # noqa: E402 -- DST-aware; never hand-roll a -4 offset
from alpaca_keys import keys_for  # noqa: E402

ACTIVE_BAND = 15.0  # near-price band for carrying key-levels.json entries forward ($, matches
                     # refresh_levels_intraday.py's ACTIVE_BAND=12 with a small safety margin)
BIAS_DEADBAND = 0.0005  # 5bps -- pct_change smaller than this never drives a directional bias


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        Path(tmp).replace(path)
    finally:
        if Path(tmp).exists():
            Path(tmp).unlink()


def _round2(x: Optional[float]) -> Optional[float]:
    return round(x, 2) if isinstance(x, (int, float)) else None


def _et_offset_suffix(dt_et_naive: datetime) -> str:
    """DST-aware '+HH:MM'/'-HH:MM' suffix for a naive ET datetime -- never hardcode -04:00
    (that is wrong 5 months of the year, the exact TZ-SYSTEMIC class of bug et_clock.py
    exists to prevent). Delegates to ET_TZ's own DST lookup (single source of truth)."""
    off = ET_TZ.utcoffset(dt_et_naive)
    total_min = int(off.total_seconds() // 60)
    sign = "+" if total_min >= 0 else "-"
    total_min = abs(total_min)
    return f"{sign}{total_min // 60:02d}:{total_min % 60:02d}"


# --------------------------------------------------------------------------- #
# Market data (un-blockable paths -- mirrors sight_beacon.py / heartbeat_core.py)
# --------------------------------------------------------------------------- #
def fetch_spy_bars(limit: int = 500) -> tuple[list[dict[str, Any]], str]:
    """SPY 5m OHLC bars, ~7 calendar days, direct Alpaca REST (IEX feed).

    Returns (bars, data_source). bars is a list of {date, time_et, open, high,
    low, close} dicts, ASCENDING by time. sort=desc + reverse (NOT sort=asc)
    -- the truncation bug documented in sight_beacon.py: with sort=asc the
    limit cap keeps the OLDEST bars and drops the newest off the tail.
    """
    try:
        key, sec = keys_for("safe")
    except (FileNotFoundError, KeyError):
        return [], "no_key"
    start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars"
           f"?timeframe=5Min&start={start}&limit={limit}&feed=iex&adjustment=raw&sort=desc")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return [], f"alpaca_http_{e.code}"
    except Exception as e:  # noqa: BLE001
        return [], f"alpaca_err_{type(e).__name__}"
    raw = list(reversed(data.get("bars") or []))  # desc -> asc
    bars = _parse_alpaca_bars(raw)
    if not bars:
        return [], "alpaca_empty"
    return bars, f"alpaca_rest_iex_{len(bars)}bars"


def _parse_alpaca_bars(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in raw:
        try:
            ts_utc = datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00"))
            ts = ts_utc.astimezone(ET_TZ)  # DST-aware (ET_TZ.fromutc) -- never a hardcoded -4
        except (KeyError, ValueError):
            continue
        out.append({
            "date": ts.strftime("%Y-%m-%d"), "time_et": ts.strftime("%H:%M"),
            "open": float(b.get("o", b.get("c", 0.0))), "high": float(b.get("h", b.get("c", 0.0))),
            "low": float(b.get("l", b.get("c", 0.0))), "close": float(b["c"]),
        })
    return out


def fetch_spy_bars_yfinance() -> tuple[list[dict[str, Any]], str]:
    """yfinance fallback -- no auth, the path watcher_live.py already proves works."""
    try:
        import yfinance as yf
    except ImportError:
        return [], "no_yfinance"
    try:
        df = yf.download("SPY", period="7d", interval="5m", auto_adjust=False,
                          progress=False, prepost=True)
        if df is None or df.empty:
            return [], "yfinance_empty"
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        idx = df.index
        bars: list[dict[str, Any]] = []
        for i in range(len(df)):
            try:
                ts = idx[i].to_pydatetime()
                if ts.tzinfo is not None:
                    ts = ts.astimezone(ET_TZ)  # DST-aware -- never a hardcoded -4
                o, h, l, c = (float(df["Open"].iloc[i]), float(df["High"].iloc[i]),
                              float(df["Low"].iloc[i]), float(df["Close"].iloc[i]))
            except (ValueError, TypeError):
                continue
            if c != c:  # NaN
                continue
            bars.append({"date": ts.strftime("%Y-%m-%d"), "time_et": ts.strftime("%H:%M"),
                         "open": o, "high": h, "low": l, "close": c})
        if not bars:
            return [], "yfinance_empty_after_parse"
        return bars, f"yfinance_{len(bars)}bars"
    except Exception as e:  # noqa: BLE001
        return [], f"yfinance_err_{type(e).__name__}"


def fetch_vix() -> tuple[Optional[float], Optional[float], str]:
    """(vix_now, vix_prior, note) -- yfinance ^VIX 5m closes. (None, None, reason) on failure.
    Mirrors heartbeat_core._fetch_vix exactly (same un-blockable, no-auth path)."""
    try:
        import yfinance as yf
        d = yf.download("^VIX", period="2d", interval="5m", auto_adjust=False, progress=False, timeout=10)
        if d is None or d.empty:
            return None, None, "vix_empty"
        if hasattr(d.columns, "nlevels") and d.columns.nlevels > 1:
            d.columns = d.columns.get_level_values(0)
        c = [float(x) for x in d["Close"].tolist() if x == x]
        if not c:
            return None, None, "vix_all_nan"
        if len(c) >= 2:
            return c[-1], c[-2], f"vix_ok_{len(c)}bars"
        return c[-1], c[-1], f"vix_ok_1bar"
    except Exception as e:  # noqa: BLE001
        return None, None, f"vix_err_{type(e).__name__}"


def fetch_equity_direct(account: str) -> Optional[float]:
    """Direct Alpaca REST /v2/account equity read (secondary path -- only used
    when the breaker's own rearm-freshened equity is unavailable)."""
    try:
        key, sec = keys_for(account)
        req = urllib.request.Request(
            "https://paper-api.alpaca.markets/v2/account",
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return float(data["equity"])
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Deterministic computation
# --------------------------------------------------------------------------- #
def compute_bias(bars: list[dict[str, Any]], today_str: str) -> dict[str, Any]:
    """Mechanical bias from premarket-close-vs-prior-close + overnight-range
    position (see module docstring for the exact formula). Fail-open: any
    missing input returns bias='neutral_no_data' rather than guess."""
    prior_bars = [b for b in bars if b["date"] < today_str]
    today_bars = [b for b in bars if b["date"] == today_str]

    if not prior_bars:
        return {"bias": "neutral_no_data", "pct_change": None, "overnight_position": None,
                "prior_session_close": None, "premarket_close": None,
                "overnight_high": None, "overnight_low": None,
                "reason": "no_prior_session_bars_available"}

    prior_close = prior_bars[-1]["close"]

    premarket_bars = [b for b in today_bars if b["time_et"] < "09:30"]
    if premarket_bars:
        ref_bars_for_close = premarket_bars
        window_note = "premarket_bars"
    elif today_bars:
        ref_bars_for_close = today_bars  # running late / post-open recovery fire
        window_note = "today_bars_post_open"
    else:
        ref_bars_for_close = prior_bars[-6:]  # thin-liquidity overnight: use tail of prior session
        window_note = "prior_session_tail_only"

    premarket_close = ref_bars_for_close[-1]["close"]
    overnight_high = max(b["high"] for b in ref_bars_for_close)
    overnight_low = min(b["low"] for b in ref_bars_for_close)

    pct_change = (premarket_close - prior_close) / prior_close if prior_close else 0.0
    rng = overnight_high - overnight_low
    overnight_position = (premarket_close - overnight_low) / rng if rng > 0 else 0.5

    if pct_change > BIAS_DEADBAND and overnight_position > 0.5:
        bias = "bullish"
    elif pct_change < -BIAS_DEADBAND and overnight_position < 0.5:
        bias = "bearish"
    else:
        bias = "neutral"

    return {
        "bias": bias, "pct_change": round(pct_change, 5), "overnight_position": round(overnight_position, 3),
        "prior_session_close": _round2(prior_close), "premarket_close": _round2(premarket_close),
        "overnight_high": _round2(overnight_high), "overnight_low": _round2(overnight_low),
        "reason": window_note,
    }


def compute_vix_context(vix_now: Optional[float], params: dict[str, Any]) -> dict[str, Any]:
    """vix_bias / iv_regime against the EXISTING static thresholds in params.json
    (vix_iv_regime_bands / vix_entry_thresholds) -- never hardcodes a new number."""
    if vix_now is None:
        return {"vix_at_open": None, "vix_bias": "UNKNOWN_vix_fetch_failed",
                "iv_regime": "UNKNOWN", "iv_source": "vix_proxy", "iv_value": None}

    bands = params.get("vix_iv_regime_bands", {}) or {}
    low_max = ((bands.get("low") or {}).get("max_exclusive"))
    high_min = ((bands.get("high") or {}).get("min_exclusive"))
    if isinstance(low_max, (int, float)) and vix_now < low_max:
        iv_regime = "LOW"
    elif isinstance(high_min, (int, float)) and vix_now > high_min:
        iv_regime = "HIGH"
    else:
        iv_regime = "MID"

    thr = params.get("vix_entry_thresholds", {}) or {}
    bear_min = thr.get("bear_min_exclusive_and_rising")
    bull_max = thr.get("bull_max_exclusive_or_falling")
    if isinstance(bear_min, (int, float)) and vix_now < bear_min:
        vix_bias = f"{iv_regime}_below_bear_threshold"
    elif isinstance(bull_max, (int, float)) and vix_now > bull_max:
        vix_bias = f"{iv_regime}_above_bull_threshold"
    else:
        vix_bias = f"{iv_regime}_mixed_eligibility"

    return {"vix_at_open": round(vix_now, 2), "vix_bias": vix_bias,
            "iv_regime": iv_regime, "iv_source": "vix_proxy", "iv_value": round(vix_now, 2)}


def compute_key_levels(bars: list[dict[str, Any]], today_str: str) -> tuple[dict[str, Any], str]:
    """Prefer today's already-fresh key-levels.json (an independent deterministic
    producer, refresh_levels_intraday.py) filtered to non-expired near-price
    entries; fall back to a minimal prior-day H/L/close computed from bars
    directly (per the reliability-audit spec's fallback-of-fallback shape)."""
    kl = _load_json(KEY_LEVELS, {})
    spot = bars[-1]["close"] if bars else None
    levels = kl.get("levels") if isinstance(kl, dict) else None
    as_of = str(kl.get("as_of", "")) if isinstance(kl, dict) else ""
    fresh_today = as_of[:10] == today_str

    if fresh_today and isinstance(levels, list) and levels and spot is not None:
        resistance, support = [], []
        for lv in levels:
            if not isinstance(lv, dict):
                continue
            exp = str(lv.get("expires_at") or "")[:10]
            if exp and exp < today_str:
                continue
            price = lv.get("price")
            if not isinstance(price, (int, float)):
                continue
            if abs(price - spot) > ACTIVE_BAND:
                continue
            role = lv.get("role") or lv.get("type")
            if role == "resistance":
                resistance.append(round(float(price), 2))
            elif role == "support":
                support.append(round(float(price), 2))
        resistance = sorted(set(resistance))[:8]
        support = sorted(set(support), reverse=True)[:8]
        return ({
            "resistance": resistance, "support": support,
            "ema_fast": None, "ema_pivot": None, "ema_slow": None, "sma_50": None,
            "ema_read_failed": True,
            "ribbon_source": "deterministic_fallback_carried_key_levels_json_no_chart_read",
        }, "key_levels_json_fresh_today")

    # fallback-of-fallback: prior-day H/L/close directly from bars (spec's literal shape)
    prior_bars = [b for b in bars if b["date"] < today_str]
    if prior_bars:
        prior_date = prior_bars[-1]["date"]
        prior_day_bars = [b for b in prior_bars if b["date"] == prior_date]
        resistance = [round(max(b["high"] for b in prior_day_bars), 2)]
        support = [round(min(b["low"] for b in prior_day_bars), 2)]
        return ({
            "resistance": resistance, "support": support,
            "ema_fast": None, "ema_pivot": None, "ema_slow": None, "sma_50": None,
            "ema_read_failed": True,
            "ribbon_source": "deterministic_fallback_prior_day_hl_no_chart_read",
        }, "prior_day_hl_from_bars")

    return ({"resistance": [], "support": [], "ema_fast": None, "ema_pivot": None, "ema_slow": None,
              "sma_50": None, "ema_read_failed": True,
              "ribbon_source": "deterministic_fallback_no_data"}, "no_data")


def compute_news_calendar(today_str: str) -> dict[str, Any]:
    """Delegates to macro_calendar.py's own deterministic producer (do_fetch=False
    -- offline/baseline mode, no network dependency in this failure path)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import macro_calendar as mc  # noqa: PLC0415
        summary = mc.run(REPO, today=today_str, do_fetch=False, dry_run=True)
        events_today = summary.get("events_today", [])
        no_trade = summary.get("no_trade_windows_today", [])
        return {
            "events_today": events_today, "no_trade_window": no_trade,
            "size_modifier_windows": [], "catalyst_narrative": {
                "narrative": "Not computed by deterministic fallback (no chart/live read) -- "
                              "see automation/state/news.json for the mechanical macro digest.",
                "source": "macro_calendar.py (deterministic, do_fetch=False)"},
            "stale": False, "calendar_freshness_days": 0,
        }
    except Exception as e:  # noqa: BLE001
        return {"events_today": [], "no_trade_window": [], "size_modifier_windows": [],
                "catalyst_narrative": {"narrative": f"macro_calendar.py unavailable: {type(e).__name__}: {e}",
                                        "source": "unavailable"},
                "stale": True, "calendar_freshness_days": None}


def compute_rule_version_pin(params: dict[str, Any]) -> dict[str, Any]:
    """RULE_VERSION_EXPECTED read straight from premarket.md (single source --
    never hand-duplicate the constant) vs params.json#rule_version."""
    expected = None
    try:
        text = PREMARKET_PROMPT.read_text(encoding="utf-8")
        m = re.search(r'RULE_VERSION_EXPECTED\s*=\s*"([^"]+)"', text)
        if m:
            expected = m.group(1)
    except OSError:
        pass
    actual = params.get("rule_version")
    return {"expected": expected, "actual": actual, "match": (expected is not None and expected == actual)}


def compute_accounts_context(today_str: str, fetch_equity: Callable[[str], Optional[float]]) -> dict[str, Any]:
    """Prefers the equity daily_loss_guard.rearm() already froze fresh THIS run
    (circuit-breaker.json / aggressive/circuit-breaker.json); only makes a fresh
    REST call if that rearm itself did not land today (e.g. Alpaca was also down)."""
    safe_breaker = _load_json(SAFE_BREAKER, {}) or {}
    bold_breaker = _load_json(BOLD_BREAKER, {}) or {}

    safe_date = str(safe_breaker.get("last_reset", ""))[:10]
    safe_equity = safe_breaker.get("starting_equity_today") if safe_date == today_str else None
    if safe_equity is None:
        safe_equity = fetch_equity("safe")

    bold_date = str(bold_breaker.get("session_id", ""))[:10]
    bold_equity = bold_breaker.get("equity_start_of_day") if bold_date == today_str else None
    if bold_equity is None:
        bold_equity = fetch_equity("bold")

    daily_loss_budget = safe_breaker.get("daily_loss_limit_dollars") if safe_date == today_str else None

    day_trades_remaining = None
    used = safe_breaker.get("day_trades_used_5d")
    if isinstance(used, (int, float)):
        limit = 3  # PDT_DAY_TRADE_LIMIT static fallback (matches self_check.py's frozen default)
        try:
            sys.path.insert(0, str(REPO / "backtest" / "lib"))
            import risk_gate as _rg  # noqa: PLC0415
            limit = int(_rg.PDT_DAY_TRADE_LIMIT)
        except Exception:  # noqa: BLE001
            pass
        day_trades_remaining = max(0, limit - int(used))

    return {
        "safe_equity_confirmed": _round2(safe_equity), "bold_equity": _round2(bold_equity),
        "daily_loss_budget_dollars": _round2(daily_loss_budget), "day_trades_remaining": day_trades_remaining,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def build(
    repo_root: Path = REPO,
    now_et: Optional[datetime] = None,
    fetch_bars: Optional[Callable[[], tuple[list[dict[str, Any]], str]]] = None,
    fetch_vix_fn: Optional[Callable[[], tuple[Optional[float], Optional[float], str]]] = None,
    fetch_equity_fn: Optional[Callable[[str], Optional[float]]] = None,
) -> dict[str, Any]:
    """Assemble a today-bias.json-shaped dict. Returns {"ok": False, ...} (never
    raises) if the PRIMARY input -- SPY bars -- is unavailable from every source;
    callers must NOT write that result (see main()/run())."""
    now_et = now_et or et_now()
    today_str = now_et.strftime("%Y-%m-%d")
    tz_suffix = _et_offset_suffix(now_et)
    fetch_bars = fetch_bars or (lambda: _fetch_bars_with_fallback())
    fetch_vix_fn = fetch_vix_fn or fetch_vix
    fetch_equity_fn = fetch_equity_fn or fetch_equity_direct

    bars, bars_source = fetch_bars()
    if not bars:
        return {"ok": False, "reason": f"no_spy_bars_from_any_source ({bars_source})",
                "date": today_str, "degraded": True, "source": "deterministic_fallback"}

    bias_calc = compute_bias(bars, today_str)
    vix_now, vix_prior, vix_note = fetch_vix_fn()
    params = _load_json(PARAMS, {}) or {}
    vix_ctx = compute_vix_context(vix_now, params)
    key_levels, key_levels_source = compute_key_levels(bars, today_str)
    news_calendar = compute_news_calendar(today_str)
    rule_pin = compute_rule_version_pin(params)
    accounts = compute_accounts_context(today_str, fetch_equity_fn)

    readiness_flags = [
        f"DETERMINISTIC FALLBACK FIRED: the premarket LLM step did not produce a usable bias "
        f"this run -- this is a mechanical, non-LLM write (bars_source={bars_source}, "
        f"vix_note={vix_note}, key_levels_source={key_levels_source}). NO chart/ribbon/trendline "
        f"read was performed -- ema/pivot/slow are null, ema_read_failed=true.",
        "falsifiable_predictions intentionally EMPTY -- the fallback does not fabricate a "
        "qualitative call it cannot back (see the deep-research spec).",
    ]
    if bias_calc.get("bias") == "neutral_no_data":
        readiness_flags.append("bias could not be computed (no prior-session bars) -- "
                                "treat bias as UNKNOWN, not a real neutral read.")
    if vix_now is None:
        readiness_flags.append(f"VIX read failed ({vix_note}) -- vix_bias is UNKNOWN, "
                                "engine's own live VIX filters still apply independently.")
    if accounts["safe_equity_confirmed"] is None or accounts["bold_equity"] is None:
        readiness_flags.append("one or both account equities could not be confirmed "
                                "(breaker rearm AND direct fetch both failed) -- LOAD-BEARING "
                                "for strike-tier selection, verify manually before relying on sizing.")

    bias_note = (
        f"DEGRADED DETERMINISTIC FALLBACK (source=deterministic_fallback, no LLM/chart read). "
        f"premarket_close={bias_calc.get('premarket_close')} vs prior_session_close="
        f"{bias_calc.get('prior_session_close')} (pct_change={bias_calc.get('pct_change')}), "
        f"overnight_position={bias_calc.get('overnight_position')} within [{bias_calc.get('overnight_low')}, "
        f"{bias_calc.get('overnight_high')}] -> bias={bias_calc.get('bias')}. VIX={vix_ctx.get('vix_at_open')} "
        f"-> {vix_ctx.get('vix_bias')}. This bias is MECHANICAL ONLY (premarket-close-vs-prior-close + "
        f"overnight-range-position) -- it carries no chart-structure, trendline, or ribbon read. "
        f"Falsifiable predictions intentionally empty; do not treat this as the qualitative LLM narrative."
    )

    return {
        "ok": True,
        "date": today_str,
        "bias": bias_calc["bias"],
        "bias_note": bias_note,
        "key_levels": key_levels,
        "falsifiable_predictions": [],
        "falsifiable_hypothesis": None,
        "vix_at_open": vix_ctx["vix_at_open"], "vix_bias": vix_ctx["vix_bias"],
        "iv_regime": vix_ctx["iv_regime"], "iv_source": vix_ctx["iv_source"], "iv_value": vix_ctx["iv_value"],
        "session_window": {
            "open_et": f"{today_str}T09:30:00{tz_suffix}", "close_et": f"{today_str}T16:00:00{tz_suffix}",
        },
        "news_calendar": news_calendar,
        "daily_loss_budget_dollars": accounts["daily_loss_budget_dollars"],
        "day_trades_remaining": accounts["day_trades_remaining"],
        "safe_equity_confirmed": accounts["safe_equity_confirmed"],
        "bold_equity": accounts["bold_equity"],
        "swarm_context": {
            "consensus_bias": None, "swarm_confidence": None, "consensus_strength": None,
            "dissent_flag": {"active": False, "dissenting_agents": [], "reason": None},
            "battle_level_price": None, "top_invalidation_scenario": None, "synthesis_narrative": None,
            "swarm_predictions": [], "agreement_with_premarket": None,
            "unavailable_reason": "SWARM_CONTEXT_UNAVAILABLE -- not computed by the deterministic fallback.",
        },
        "drift_gate": {"status": "DRIFT_GATE_NO_DATA", "note": "not computed by the deterministic fallback."},
        "rule_version_pin": rule_pin,
        "prior_day_review_hint": None,
        "readiness_flags": readiness_flags,
        "updated_at": now_et.strftime("%Y-%m-%dT%H:%M:%S") + tz_suffix,
        "updated_by": "premarket_deterministic_fallback.py",
        "degraded": True,
        "source": "deterministic_fallback",
    }


def _fetch_bars_with_fallback() -> tuple[list[dict[str, Any]], str]:
    bars, note = fetch_spy_bars()
    if len(bars) >= 20:
        return bars, note
    ybars, ynote = fetch_spy_bars_yfinance()
    if len(ybars) > len(bars):
        return ybars, ynote
    return bars, note  # whichever (possibly empty) is best we have


def run(repo_root: Path = REPO, now_et: Optional[datetime] = None, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    result = build(repo_root=repo_root, now_et=now_et, **kwargs)
    if result.get("ok") and not dry_run:
        _atomic_write_json(TODAY_BIAS, {k: v for k, v in result.items() if k != "ok"})
    return result


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--dry-run", action="store_true", help="compute and print, do not write")
    ap.add_argument("--date", default=None, help="override 'today' as YYYY-MM-DD (testing/backfill)")
    args = ap.parse_args(argv)

    now_override = None
    if args.date:
        now_override = et_now().replace(year=int(args.date[:4]), month=int(args.date[5:7]), day=int(args.date[8:10]))

    try:
        result = run(REPO, now_et=now_override, dry_run=args.dry_run)
    except Exception as e:  # noqa: BLE001 -- never crash the parent wrapper silently
        print(json.dumps({"ok": False, "reason": f"unhandled_exception: {type(e).__name__}: {e}"}))
        return 1

    print(json.dumps({k: result.get(k) for k in
                      ("ok", "date", "bias", "degraded", "source", "vix_bias", "reason") if k in result},
                     indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
