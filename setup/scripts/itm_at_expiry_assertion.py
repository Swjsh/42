"""itm_at_expiry_assertion.py -- TASK B2 instrument 2/3 (built 2026-08-28).

WHY THIS EXISTS: SPY options settle PHYSICALLY. One unclosed ITM 0DTE contract
is assigned 100 shares/contract -- roughly $77,000 of stock exposure per
contract at today's price against a ~$5,000 paper account. The largest single
trade on record was 12 contracts (~$936,000 notional). eod_flatten.py already
tries to close every SPY option position by 15:55 ET and escalates loudly on
failure -- this is the INDEPENDENT, after-the-fact VERIFICATION that it always
worked: for every arm, for every option contract ever traded, assert that
ZERO were held open, in the money, past their own expiry.

SOURCE OF TRUTH:
  - automation/state/fills-ledger.jsonl (broker-truth fills) for what was
    bought/sold, per (arm, symbol) -- net open qty at end of the contract's
    own expiry date.
  - backtest/data/spy_sip_cache/spy_1m_{date}.json (real 1-minute SPY bars,
    664 trading dates on disk) for the settlement reference: the standard
    OCC rule for EQUITY/ETF options is settlement to the 4:00pm ET official
    closing price (NOT a special AM-settlement value like an index option).
    Bar timestamps in this cache are ALREADY naive ET wall-clock (verified
    2026-08-28 against setup/scripts/entry_quality_ledger.py's own read
    pattern: `b['dt'] = datetime.fromisoformat(b['t'])`, no tz conversion --
    the file spans 04:00-16:1x, consistent with ET pre/post-market, not UTC).
    A missing cache file is a COVERAGE GAP, reported as its own category --
    NEVER silently treated as "not ITM" (C7: no silent fallback to a
    favorable assumption on missing data).

READ-ONLY: never writes to fills-ledger.jsonl or any live-trading-path file.
Outputs live under analysis/itm-expiry/ and (loudly, only on any violation)
automation/overnight/STATUS.md.

JUDGABLE-ONLY GATE (C6, no look-ahead): a contract's expiry date is only
judged once market close has actually happened for that date -- either the
date is strictly before "today" (ET), or it IS today and the current ET time
is >= 16:00. A same-day still-open position before the close is never flagged
(it may still get closed by eod_flatten.py before 15:55).

Run:  backtest/.venv/Scripts/python.exe setup/scripts/itm_at_expiry_assertion.py [--quiet]
      (plain `python` also works -- stdlib only, no network, no pandas/venv deps)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FILLS_PATH = STATE / "fills-ledger.jsonl"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
BAR_CACHE_DIR = REPO / "backtest" / "data" / "spy_sip_cache"
OUT_DIR = REPO / "analysis" / "itm-expiry"
OUT_PATH = OUT_DIR / "summary.json"

KNOWN_BROKEN_MARKER = "## Known broken"
QTY_EPS = 1e-9

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402

# root(letters) + YYMMDD + C/P + strike*1000 (8 digits), e.g. SPY260828C00769000
_OCC_RE = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def parse_occ_symbol(symbol: str) -> "dict | None":
    """PURE. {root, expiry_date (YYYY-MM-DD), right, strike} or None if unparseable."""
    m = _OCC_RE.match(symbol or "")
    if not m:
        return None
    root, yy, mm, dd, right, strike_digits = m.groups()
    return {
        "root": root,
        "expiry_date": f"20{yy}-{mm}-{dd}",
        "right": right,
        "strike": int(strike_digits) / 1000.0,
    }


def load_fills(path: Path = FILLS_PATH) -> list:
    fills = []
    if not path.exists():
        return fills
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                fills.append(json.loads(line))
            except ValueError:
                continue
    return fills


def net_positions_by_expiry(fills: list) -> dict:
    """PURE: fills -> {(arm, symbol): {net_qty, root, expiry_date, right, strike,
    n_fills, last_ts_et}} for every OPTION symbol ever traded, option-only
    (is_option / OCC-parseable), crypto never included (it has no OCC symbol)."""
    groups: dict = {}
    for f in fills:
        if not f.get("is_option"):
            continue
        symbol = f.get("symbol")
        parsed = parse_occ_symbol(symbol)
        if parsed is None:
            continue  # unparseable symbol -- never silently guessed at
        key = (f.get("arm"), symbol)
        g = groups.setdefault(key, {
            **parsed, "net_qty": 0.0, "n_fills": 0, "last_ts_et": None,
        })
        qty = float(f.get("qty") or 0)
        sign = 1.0 if f.get("side") == "buy" else -1.0
        g["net_qty"] += sign * qty
        g["n_fills"] += 1
        ts = f.get("ts_et")
        if ts and (g["last_ts_et"] is None or ts > g["last_ts_et"]):
            g["last_ts_et"] = ts
    return groups


def is_judgable(expiry_date: str, now_et) -> bool:
    """C6: only judge a date once its close has actually happened."""
    today = now_et.strftime("%Y-%m-%d")
    if expiry_date < today:
        return True
    if expiry_date == today:
        return now_et.strftime("%H:%M") >= "16:00"
    return False


def settlement_close(expiry_date: str, cache_dir: Path = BAR_CACHE_DIR) -> "float | None":
    """The 4:00pm ET official close for SPY on expiry_date, from the real 1-minute SIP
    cache. Returns None (COVERAGE GAP -- never a guess) if the file or a <=16:00 bar is
    missing. Bar 't' is naive ET wall-clock (see module docstring)."""
    p = cache_dir / f"spy_1m_{expiry_date}.json"
    if not p.exists():
        return None
    try:
        bars = json.loads(p.read_text(encoding="utf-8")).get("bars", [])
    except (ValueError, OSError):
        return None
    candidates = [b for b in bars if isinstance(b.get("t"), str) and b["t"][11:16] <= "16:00"]
    if not candidates:
        return None
    candidates.sort(key=lambda b: b["t"])
    return candidates[-1].get("c")


def is_itm(right: str, strike: float, close: float) -> bool:
    if right == "C":
        return close > strike
    if right == "P":
        return close < strike
    return False  # unreachable given _OCC_RE, but never guess


def assert_all(fills: list, now_et=None, cache_dir: Path = BAR_CACHE_DIR) -> dict:
    """PURE (except reading the bar cache files): the whole check. Returns the summary dict."""
    now_et = now_et or et_now()
    groups = net_positions_by_expiry(fills)

    violations, held_to_close_otm, coverage_gaps, still_open_not_judgable = [], [], [], []
    n_judged = 0
    for (arm, symbol), g in sorted(groups.items()):
        if abs(g["net_qty"]) <= QTY_EPS:
            continue  # closed flat -- nothing to judge
        if not is_judgable(g["expiry_date"], now_et):
            still_open_not_judgable.append({
                "arm": arm, "symbol": symbol, "net_qty": g["net_qty"],
                "expiry_date": g["expiry_date"]})
            continue
        n_judged += 1
        close = settlement_close(g["expiry_date"], cache_dir)
        row = {
            "arm": arm, "symbol": symbol, "root": g["root"], "expiry_date": g["expiry_date"],
            "right": g["right"], "strike": g["strike"], "net_qty": g["net_qty"],
            "n_fills": g["n_fills"], "last_ts_et": g["last_ts_et"], "settlement_close": close,
        }
        if close is None:
            coverage_gaps.append(row)
            continue
        if is_itm(g["right"], g["strike"], close):
            row["notional_usd"] = round(abs(g["net_qty"]) * 100 * close, 2)
            row["itm_by_usd"] = round(
                (close - g["strike"]) if g["right"] == "C" else (g["strike"] - close), 4)
            violations.append(row)
        else:
            held_to_close_otm.append(row)

    return {
        "generated_at_et": now_et.isoformat(),
        "n_symbol_arm_pairs_seen": len(groups),
        "n_judged": n_judged,
        "n_violations": len(violations),
        "violations": violations,
        "has_ever_happened": len(violations) > 0,
        "held_to_close_otm_count": len(held_to_close_otm),
        "held_to_close_otm": held_to_close_otm[:50],  # capped -- informational, not the alarm
        "coverage_gaps": coverage_gaps,
        "n_coverage_gaps": len(coverage_gaps),
        "still_open_not_yet_judgable": still_open_not_judgable,
        "note": ("Settlement reference = last <=16:00 ET 1-minute SPY bar close from "
                 "backtest/data/spy_sip_cache (real SIP data, 664 trading dates on disk). "
                 "A symbol/date with no cache file is a COVERAGE GAP, reported separately -- "
                 "never silently assumed OTM. Standard OCC equity-option settlement rule: "
                 "closing price, not a special AM value (that convention is index-option-only, "
                 "e.g. SPX, and does not apply to SPY)."),
    }


def one_liner(summary: dict) -> str:
    if summary["n_violations"] > 0:
        v0 = summary["violations"][0]
        return (f"[itm-expiry] VIOLATION: {summary['n_violations']} contract(s) held ITM into "
                f"expiry (e.g. {v0['arm']} {v0['symbol']} net_qty={v0['net_qty']} "
                f"itm_by=${v0['itm_by_usd']} notional=${v0['notional_usd']}) -- "
                f"has_ever_happened=True. See analysis/itm-expiry/summary.json")
    gap = f", {summary['n_coverage_gaps']} coverage gap(s)" if summary["n_coverage_gaps"] else ""
    return (f"[itm-expiry] CLEAN: 0 violations across {summary['n_judged']} judged "
            f"(arm,symbol,expiry) position(s){gap} -- has_ever_happened=False")


def _flag_status_md(summary: dict, status_md: Path = STATUS_MD) -> bool:
    """Loudly escalate to STATUS.md '## Known broken' on ANY violation. Canonical
    create-if-missing pattern (monday_verify.py::_flag_known_broken, proven by
    backtest/tests/test_status_known_broken_section_2026_08_20.py): PREPEND the
    heading if absent (position/existing-append cannot be relied on -- the
    conductor prepends new '## [' entries above the preamble, rolling the heading
    into a monthly archive, exactly the June 2026 outage)."""
    if summary["n_violations"] == 0:
        return False
    try:
        text = status_md.read_text(encoding="utf-8")
    except OSError:
        return False
    v0 = summary["violations"][0]
    line = (f"- [{summary['generated_at_et']}] ITM-AT-EXPIRY VIOLATION: "
            f"{summary['n_violations']} contract(s) held ITM into expiry -- PHYSICAL "
            f"ASSIGNMENT RISK REALIZED. First: {v0['arm']} {v0['symbol']} "
            f"net_qty={v0['net_qty']} itm_by=${v0['itm_by_usd']} "
            f"notional=${v0['notional_usd']}. See analysis/itm-expiry/summary.json -- "
            f"MANUAL ACTION REQUIRED (verify no real assignment/exercise landed on the "
            f"broker account).")
    if KNOWN_BROKEN_MARKER not in text:
        text = KNOWN_BROKEN_MARKER + "\n\n" + text
    head, _, tail = text.partition(KNOWN_BROKEN_MARKER + "\n")
    status_md.write_text(
        f"{head}{KNOWN_BROKEN_MARKER}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")
    return True


def run(fills_path: Path = FILLS_PATH, out_path: Path = OUT_PATH,
        status_md: Path = STATUS_MD, cache_dir: Path = BAR_CACHE_DIR, write: bool = True) -> dict:
    fills = load_fills(fills_path)
    summary = assert_all(fills, cache_dir=cache_dir)
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        _flag_status_md(summary, status_md)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    try:
        summary = run()
    except Exception as e:  # noqa: BLE001 -- fail-open notify-only instrument, never propagate
        print(f"[itm-expiry] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    if not args.quiet:
        print(one_liner(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
