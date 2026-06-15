"""Daily crypto-harness digest writer.

Reads scorecards from crypto/data/scorecards/, writes a markdown digest to
crypto/data/scorecards/daily/{date}.md. Called from run-crypto-daily.ps1.

Extracted from inline `python -` here-string (which leaked conhost) per OP-27 L41
(2026-05-17 evening foot-gun fix).

Usage:
  python _crypto_daily_digest.py <date_str> <digest_path> \
    <regression_last_result> <regression_missed> \
    <keepalive_last_result> <keepalive_missed>
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _safe_load(p: str) -> dict | None:
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main(argv: list[str]) -> int:
    if len(argv) < 7:
        print(f"usage error: got {len(argv)} args, need >=7", file=sys.stderr)
        return 2

    date = argv[1]
    digest = Path(argv[2])
    regression_last_result = argv[3]
    regression_missed = argv[4]
    keepalive_last_result = argv[5]
    keepalive_missed = argv[6]

    latest = _safe_load("crypto/data/scorecards/latest.json")
    drift = _safe_load("crypto/data/scorecards/drift_report.json")
    ginfo = _safe_load("crypto/data/scorecards/grinder_analysis.json")

    lines: list[str] = []
    lines.append(f"# Crypto Harness Daily Digest -- {date}")
    lines.append("")
    lines.append(f"_generated: {datetime.now(timezone.utc).isoformat()}_")
    lines.append("")
    lines.append("## Headline numbers")
    if latest:
        s = latest.get("summary", {})
        lines.append(
            f"- Latest cron run: {s.get('passed', '?')}/{s.get('stages', '?')} stages passed, "
            f"overall_pass={s.get('overall_pass')}"
        )
        if "benchmark_5_14" in s:
            b = s["benchmark_5_14"]
            lines.append(
                f"- 5/14 floor: OLD {b['OLD_error_rate_pct']}% -> NEW {b['NEW_error_rate_pct']}% "
                f"(critical misread OLD={b['critical_misread_OLD']}, NEW={b['critical_misread_NEW']})"
            )
    if drift:
        lines.append(f"- Drift health: {drift.get('overall_health', '?')}")
        for a in drift.get("alerts", []) or []:
            lines.append(f"  - ALERT: {a}")
        rate = drift.get("cron_pass_rate_by_window", {}).get("24h")
        if rate:
            lines.append(f"- Cron pass rate 24h: {rate['passed']}/{rate['total']} ({rate['rate_pct']}%)")
    lines.append("")
    lines.append("## Grinder activity (last 24h)")
    if ginfo:
        lines.append(f"- Iterations: {ginfo.get('iterations', '?')}")
        lines.append(
            f"- v01 foot-gun catches: {ginfo.get('v01_foot_gun_catches', '?')} "
            f"({ginfo.get('v01_foot_gun_catch_rate_pct', '?')}%)"
        )
        lines.append(
            f"- v02 disagreement iterations: {ginfo.get('v02_disagreement_iters_with_drift', '?')} "
            f"(max disagreements per iter: {ginfo.get('v02_disagreement_max', '?')})"
        )
        rsi = ginfo.get("v03_rsi_14_stats") or {}
        if rsi:
            lines.append(
                f"- RSI(14) range: {rsi.get('min', '?')}-{rsi.get('max', '?')} "
                f"(mean {rsi.get('mean', '?')})"
            )
        lines.append("- Pattern fires per iteration:")
        for pat, ps in (ginfo.get("v04_pattern_count_stats") or {}).items():
            if ps:
                lines.append(
                    f"  - {pat}: mean={ps.get('mean', '?')}  range=[{ps.get('min', '?')},{ps.get('max', '?')}]"
                )
    lines.append("")
    lines.append("## Recommendations queued")
    recs = (ginfo or {}).get("recommendations") or []
    if recs:
        for r in recs:
            lines.append(f"- {r}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Equipment health")
    lines.append("```")
    lines.append(
        f"Gamma_CryptoRegression       last_result={regression_last_result} missed_runs={regression_missed}"
    )
    lines.append(
        f"Gamma_CryptoGrinderKeepalive last_result={keepalive_last_result} missed_runs={keepalive_missed}"
    )
    lines.append("```")
    lines.append("")

    verdict = "GREEN"
    if drift and drift.get("overall_health") == "RED":
        verdict = "RED"
    elif latest and not latest.get("summary", {}).get("overall_pass"):
        verdict = "RED"
    lines.append(f"## Verdict for today")
    suffix = "All systems training the right muscles." if verdict == "GREEN" else "Investigate alerts above."
    lines.append(f"**{verdict}** -- {suffix}")
    lines.append("")

    digest.parent.mkdir(parents=True, exist_ok=True)
    digest.write_text("\n".join(lines), encoding="utf-8")
    print(f"digest written: {digest}")
    print(f"verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
