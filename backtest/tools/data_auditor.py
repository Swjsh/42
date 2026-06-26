"""data_auditor.py — the gate that protects the gym from bad foraged data.

Plan B sec 4a: the Data Forager may NOT write a new CSV into backtest/data/ or
register it in data-versions.jsonl until it passes this auditor. Failing files
route to backtest/data/_quarantine/ and the auditor FAILS LOUD (non-zero exit +
a scorecard artifact) — never a silent "OK" off an exit code (Lesson C7).

Checks (stdlib only — no pandas, runs anywhere):
  Structural : required columns, row count, monotonic/unique/even timestamps
  Timezone   : ET offset matches the US-DST rule per date (catches UTC-mislabel
               and constant-offset sources — the repo's #1 historical bug class)
  OHLC       : low<=open,close<=high; high>=low; prices>0; stale runs; jumps
  Volume     : >=0; zero-volume on a liquid name during RTH -> WARN
  Options    : + vwap within [low,high]; trade_count>=0; OCC filename parse; RTH-only
  Reconcile  : optional cross-source close-price diff vs a referee file

Verdict: GREEN (no WARN/REJECT) / YELLOW (WARN only) / RED (any REJECT).
RED  => quarantine + exit 2. GREEN/YELLOW => exit 0.

Pure validation, no order placement, no production-state writes (Plan B constraint).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
QUARANTINE_DIR = DATA_DIR / "_quarantine"

SPOT_COLS = ["timestamp_et", "open", "high", "low", "close", "volume"]
OPTION_COLS = ["timestamp_et", "open", "high", "low", "close", "volume", "vwap", "trade_count"]

SEVERITY_RANK = {"PASS": 0, "WARN": 1, "REJECT": 2}

# Tunables (starting thresholds per Plan B sec 4a)
JUMP_PCT = 0.10              # >10% bar-to-bar close move (same day) -> flag
STALE_RUN = 3               # >=3 identical OHLC bars in a row -> stale flag
RTH_BARS_5M = 78            # 09:30..16:00 ET at 5-min
RTH_DEVIATION_WARN = 1      # off by 1 bar -> WARN
RTH_DEVIATION_REJECT = 0.05 # off by >5% of expected -> REJECT day


# ────────────────────────────────────────────────────────────────────────────
# DST-aware ET offset (US rule: 2nd Sun Mar 02:00 .. 1st Sun Nov 02:00 = EDT -4)
# ────────────────────────────────────────────────────────────────────────────


def expected_et_offset_hours(d: datetime) -> int:
    """Return -4 (EDT) or -5 (EST) for a given local date per the US DST rule."""
    y = d.year
    march = datetime(y, 3, 1)
    dst_start = march + timedelta(days=(6 - march.weekday()) % 7 + 7)   # 2nd Sunday
    nov = datetime(y, 11, 1)
    dst_end = nov + timedelta(days=(6 - nov.weekday()) % 7)             # 1st Sunday
    naive = d.replace(tzinfo=None)
    return -4 if (dst_start <= naive < dst_end) else -5


# ────────────────────────────────────────────────────────────────────────────
# Report model
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class Finding:
    check: str
    severity: str   # PASS / WARN / REJECT
    detail: str


@dataclass
class AuditReport:
    path: str
    kind: str
    n_rows: int = 0
    findings: list = field(default_factory=list)

    def add(self, check: str, severity: str, detail: str = "") -> None:
        self.findings.append(Finding(check, severity, detail))

    @property
    def verdict(self) -> str:
        worst = max((SEVERITY_RANK[f.severity] for f in self.findings), default=0)
        return {0: "GREEN", 1: "YELLOW", 2: "RED"}[worst]

    def scorecard(self) -> dict:
        counts = {"PASS": 0, "WARN": 0, "REJECT": 0}
        for f in self.findings:
            counts[f.severity] += 1
        return {
            "path": self.path,
            "kind": self.kind,
            "n_rows": self.n_rows,
            "verdict": self.verdict,
            "counts": counts,
            "findings": [
                {"check": f.check, "severity": f.severity, "detail": f.detail}
                for f in self.findings if f.severity != "PASS"
            ],
        }


# ────────────────────────────────────────────────────────────────────────────
# Row parsing
# ────────────────────────────────────────────────────────────────────────────


def _parse_ts(raw: str) -> Optional[datetime]:
    """Parse an ET-aware ISO timestamp ('2026-05-19 04:00:00-04:00' or with 'T')."""
    s = (raw or "").strip().replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _is_rth(dt: datetime) -> bool:
    """09:30 <= t < 16:00 ET (timestamp is already ET-aware)."""
    h, m = dt.hour, dt.minute
    return (h > 9 or (h == 9 and m >= 30)) and h < 16


# ────────────────────────────────────────────────────────────────────────────
# Core audit
# ────────────────────────────────────────────────────────────────────────────


def audit_csv(path: Path, *, kind: str = "spot", expect_volume: bool = True,
              interval_min: int = 5) -> AuditReport:
    """Audit one OHLCV CSV (kind='spot' or 'options'). Never raises."""
    rep = AuditReport(path=str(path), kind=kind)
    required = OPTION_COLS if kind == "options" else SPOT_COLS

    if not path.exists():
        rep.add("file_exists", "REJECT", f"missing: {path}")
        return rep

    try:
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            missing = [c for c in required if c not in header]
            if missing:
                rep.add("schema", "REJECT", f"missing columns: {missing}")
                return rep
            rep.add("schema", "PASS", f"cols={header}")
            rows = list(reader)
    except OSError as exc:
        rep.add("read", "REJECT", str(exc))
        return rep

    rep.n_rows = len(rows)
    if not rows:
        rep.add("rows", "REJECT", "empty file")
        return rep

    _audit_timestamps(rows, rep, interval_min)
    _audit_ohlc(rows, rep, kind=kind, expect_volume=expect_volume)
    if kind == "options":
        _audit_options_extra(rows, rep, path)
    _audit_rth_counts(rows, rep)
    return rep


def _audit_timestamps(rows: list, rep: AuditReport, interval_min: int) -> None:
    parsed: list[datetime] = []
    bad_tz = 0
    dst_mismatch = 0
    for r in rows:
        dt = _parse_ts(r.get("timestamp_et", ""))
        if dt is None:
            bad_tz += 1
            continue
        parsed.append(dt)
        off_h = dt.utcoffset().total_seconds() / 3600 if dt.utcoffset() else None
        exp = expected_et_offset_hours(dt)
        if off_h is None or int(off_h) != exp:
            dst_mismatch += 1
    if bad_tz:
        rep.add("timestamp_parse", "REJECT",
                f"{bad_tz} rows lack a parseable ET-aware timestamp")
    if dst_mismatch:
        # The repo's #1 bug class: UTC-mislabeled-as-ET or constant-offset source
        rep.add("timezone_dst", "REJECT",
                f"{dst_mismatch} rows have a UTC offset that doesn't match the "
                f"US-DST ET rule (UTC-mislabel or constant-offset source)")
    else:
        rep.add("timezone_dst", "PASS", "ET offset matches DST rule")

    if len(parsed) < 2:
        return
    # Monotonic + unique
    dup = sum(1 for a, b in zip(parsed, parsed[1:]) if a == b)
    nonmono = sum(1 for a, b in zip(parsed, parsed[1:]) if b < a)
    if dup:
        rep.add("timestamp_unique", "REJECT", f"{dup} duplicate timestamps")
    if nonmono:
        rep.add("timestamp_monotonic", "REJECT", f"{nonmono} out-of-order timestamps")
    # Even spacing within a day (ignore cross-day / cross-session gaps)
    bad_spacing = 0
    step = timedelta(minutes=interval_min)
    for a, b in zip(parsed, parsed[1:]):
        if a.date() == b.date() and b - a not in (step,) and 0 < (b - a).total_seconds() < 3600:
            bad_spacing += 1
    if bad_spacing:
        rep.add("timestamp_spacing", "WARN",
                f"{bad_spacing} intra-day gaps != {interval_min}min (possible missing bars)")


def _f(row: dict, key: str) -> Optional[float]:
    try:
        return float(row[key])
    except (KeyError, ValueError, TypeError):
        return None


def _audit_ohlc(rows: list, rep: AuditReport, *, kind: str, expect_volume: bool) -> None:
    viol = 0
    nonpos = 0
    neg_vol = 0
    zero_vol_rth = 0
    jumps = 0
    stale = 0
    prev_close: Optional[float] = None
    prev_day = None
    run_key = None
    run_len = 0

    for r in rows:
        o, h, l, c = _f(r, "open"), _f(r, "high"), _f(r, "low"), _f(r, "close")
        if None in (o, h, l, c):
            viol += 1
            continue
        if not (l <= o <= h and l <= c <= h and h >= l):
            viol += 1
        if min(o, h, l, c) <= 0:
            nonpos += 1
        v = _f(r, "volume")
        if v is not None and v < 0:
            neg_vol += 1
        dt = _parse_ts(r.get("timestamp_et", ""))
        if expect_volume and v == 0 and dt is not None and _is_rth(dt):
            zero_vol_rth += 1
        # Jump (same-day consecutive)
        if prev_close is not None and dt is not None and prev_day == dt.date() and prev_close:
            if abs(c - prev_close) / prev_close > JUMP_PCT:
                jumps += 1
        # Stale run
        key = (o, h, l, c)
        if key == run_key:
            run_len += 1
            if run_len == STALE_RUN:
                stale += 1
        else:
            run_key, run_len = key, 1
        prev_close = c
        prev_day = dt.date() if dt else prev_day

    if viol:
        rep.add("ohlc_integrity", "REJECT", f"{viol} bars violate low<=open,close<=high")
    else:
        rep.add("ohlc_integrity", "PASS", "")
    if nonpos:
        rep.add("price_positive", "REJECT", f"{nonpos} bars with non-positive price")
    if neg_vol:
        rep.add("volume_nonneg", "REJECT", f"{neg_vol} bars with negative volume")
    if zero_vol_rth:
        rep.add("zero_volume_rth", "WARN",
                f"{zero_vol_rth} RTH bars with zero volume (possible fabricated bar)")
    if jumps:
        rep.add("price_jump", "WARN",
                f"{jumps} same-day bars jump >{int(JUMP_PCT * 100)}% (verify vs 2nd source)")
    if stale:
        rep.add("stale_bars", "WARN", f"{stale} runs of >={STALE_RUN} identical OHLC (forward-fill?)")


def _audit_options_extra(rows: list, rep: AuditReport, path: Path) -> None:
    vwap_oob = 0
    bad_tc = 0
    nonrth = 0
    for r in rows:
        l, h = _f(r, "low"), _f(r, "high")
        vwap = _f(r, "vwap")
        if None not in (l, h, vwap) and not (l <= vwap <= h):
            vwap_oob += 1
        tc = _f(r, "trade_count")
        if tc is not None and tc < 0:
            bad_tc += 1
        dt = _parse_ts(r.get("timestamp_et", ""))
        if dt is not None and not _is_rth(dt):
            nonrth += 1
    if vwap_oob:
        rep.add("vwap_in_range", "REJECT", f"{vwap_oob} bars with vwap outside [low,high]")
    else:
        rep.add("vwap_in_range", "PASS", "")
    if bad_tc:
        rep.add("trade_count_nonneg", "REJECT", f"{bad_tc} bars with negative trade_count")
    if nonrth:
        rep.add("options_rth_only", "WARN", f"{nonrth} option bars outside RTH (expected RTH-only)")
    # OCC filename sanity: SPY{YYMMDD}{C|P}{strike*1000:08d}
    stem = path.stem
    import re
    if not re.fullmatch(r"SPY\d{6}[CP]\d{8}", stem):
        rep.add("occ_filename", "WARN", f"filename {stem!r} not OCC format SPY{{YYMMDD}}{{C|P}}{{strike8}}")


def _audit_rth_counts(rows: list, rep: AuditReport) -> None:
    by_day: dict = {}
    for r in rows:
        dt = _parse_ts(r.get("timestamp_et", ""))
        if dt is None or not _is_rth(dt):
            continue
        by_day.setdefault(dt.date(), 0)
        by_day[dt.date()] += 1
    if not by_day:
        rep.add("rth_bar_count", "WARN", "no RTH bars found")
        return
    worst = "PASS"
    detail = []
    for day, n in sorted(by_day.items()):
        dev = abs(n - RTH_BARS_5M)
        if dev > RTH_BARS_5M * RTH_DEVIATION_REJECT:
            worst = "REJECT"
            detail.append(f"{day}:{n}")
        elif dev > RTH_DEVIATION_WARN and worst != "REJECT":
            worst = "WARN"
            detail.append(f"{day}:{n}")
    rep.add("rth_bar_count", worst,
            f"expected {RTH_BARS_5M}/day; off-days: {detail[:8]}" if detail else
            f"all days ~{RTH_BARS_5M} RTH bars")


# ────────────────────────────────────────────────────────────────────────────
# Cross-source reconciliation (optional referee)
# ────────────────────────────────────────────────────────────────────────────


def reconcile_close(path: Path, referee: Path, *, tol_pct: float = 0.1) -> Finding:
    """Compare close prices on overlapping timestamps vs a referee source."""
    def load(p):
        out = {}
        try:
            with open(p, encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    out[r.get("timestamp_et", "").replace(" ", "T", 1)] = _f(r, "close")
        except OSError:
            pass
        return out
    a, b = load(path), load(referee)
    common = [k for k in a if k in b and a[k] and b[k]]
    if not common:
        return Finding("reconcile", "WARN", "no overlapping timestamps with referee")
    diffs = sorted(abs(a[k] - b[k]) / b[k] * 100 for k in common)
    median = diffs[len(diffs) // 2]
    if median > 0.5:
        return Finding("reconcile", "REJECT",
                       f"median close diff {median:.3f}% > 0.5% vs referee ({len(common)} bars)")
    if median > tol_pct:
        return Finding("reconcile", "WARN",
                       f"median close diff {median:.3f}% > {tol_pct}% vs referee")
    return Finding("reconcile", "PASS", f"median close diff {median:.3f}% ({len(common)} bars)")


# ────────────────────────────────────────────────────────────────────────────
# Quarantine + CLI
# ────────────────────────────────────────────────────────────────────────────


def quarantine(path: Path, report: AuditReport) -> Path:
    """Copy a failing file + its scorecard into _quarantine/. Returns the dest."""
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dest = QUARANTINE_DIR / path.name
    try:
        shutil.copy2(path, dest)
    except OSError:
        pass
    (QUARANTINE_DIR / f"{path.stem}.audit.json").write_text(
        json.dumps(report.scorecard(), indent=2), encoding="utf-8")
    return dest


def _main() -> int:
    p = argparse.ArgumentParser(description="Audit an OHLCV CSV before it enters the gym.")
    p.add_argument("csv", help="path to the CSV to audit")
    p.add_argument("--kind", choices=["spot", "options"], default="spot")
    p.add_argument("--no-volume", action="store_true", help="index series (e.g. VIX) — skip zero-volume RTH check")
    p.add_argument("--referee", help="second-source CSV for cross-source reconciliation")
    p.add_argument("--quarantine", action="store_true", help="copy to _quarantine/ on RED")
    args = p.parse_args()

    path = Path(args.csv)
    rep = audit_csv(path, kind=args.kind, expect_volume=not args.no_volume)
    if args.referee:
        rep.findings.append(reconcile_close(path, Path(args.referee)))

    print(json.dumps(rep.scorecard(), indent=2))
    if rep.verdict == "RED":
        if args.quarantine:
            dest = quarantine(path, rep)
            print(f"\nRED -> quarantined to {dest}", file=sys.stderr)
        return 2   # fail loud
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
