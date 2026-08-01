"""monday_preview_scrimmage_2026_08_03.py — WS1 SUNDAY SCRIMMAGE (weekend integration test).

Replays Friday 2026-07-31's full core-decisions tape through the fleet signal->plan path
AS IT NOW STANDS ON HEAD, and diffs per-arm expected entries/refusals against what the
fleet actually did on Friday. Report-only: touches NO production file, places NO orders,
writes ONE analysis JSON artifact.

WHY THE CORE LEDGER IS A VALID HEAD INPUT (verified 2026-08-01): `git log --since=
"2026-07-31 09:30"` over backtest/lib/engine, backtest/lib/orchestrator.py,
backtest/lib/levels.py, setup/scripts/heartbeat_core.py, crypto/lib/strike_selection.py
returns ZERO commits — the deterministic brain is byte-identical to the one that wrote
Friday's rows, so Friday's per-tick verdicts ARE what HEAD's brain would produce on the
same tape. The two commits that DID land (e28d210c FULL-SEND, 43bb979d ATM extension)
changed only the fleet producer/consumer — exactly the layer this scrimmage replays.

METHOD (one implementation, no re-derivation):
  per 1-min tick: raw safe+bold rows -> bss._map_core_row -> bss.build_from_rows(
      row=safe, bold_row=bold, probe_row=safe, run_vwap=False, write=False)
  -> fleet_executor.plan_all(arm, sig, equity=Friday SoD from circuit-breaker.json,
      params=fx._params_for(arm), probe_cfg=accounts.probe_arm)
  build_from_rows is the SAME producer logic the live fleet consumes (its docstring:
  "exactly one implementation of what a core row means as a fleet signal").

DISCLOSED LIMITS (stated in the preview doc too):
  * PLAN-level replay: fleet_executor.finalize()'s premium floor / risk cap / broker
    flat-check need live quotes — episodes here are signal-availability, fills <= plans.
  * 1-min tick replay vs the fleet's real ~3-min cadence: availability windows are
    exact; WHICH tick inside a window a live fire lands on depends on cadence phase.
  * _ribbon_strategy_entries' trigger_level FALLBACK + _recency_verdict read TODAY's
    on-disk state (key-levels.json / recency-confirmation.json), not Friday's — the
    exact trigger_level and the 12->5 qty clamp are state-sensitive; ENTER/HOLD is not.
  * Missing safe/bold row at a minute (write race): carry the LAST row forward, which
    is exactly what the live producer's latest-today-row read does.

Run: backtest/.venv/Scripts/python.exe backtest/tools/monday_preview_scrimmage_2026_08_03.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
for p in ("backtest", "setup/scripts", "automation/state/fleet"):
    sys.path.insert(0, str(REPO / p))

import build_shared_signal as bss  # noqa: E402
import fleet_executor as fx        # noqa: E402

DAY = "2026-07-31"
CORE = REPO / "automation" / "state" / "core-decisions.jsonl"
ACCOUNTS = json.loads((REPO / "automation" / "state" / "fleet" / "accounts.json").read_text(encoding="utf-8"))
OUT_JSON = REPO / "analysis" / "deep-research" / "monday-preview-scrimmage-2026-08-03.json"

# Friday's REAL start-of-day equities (automation/state/fleet/<arm>/circuit-breaker.json,
# last_reset 2026-07-31T09:31:02-0400) — the equities the live fleet actually sized with.
FRIDAY_SOD_EQUITY = {"safe-3": 1893.04, "risky-1": 1756.87, "risky-3": 2076.35}
ARMS = ("safe-3", "risky-1", "risky-3")

# Friday's ACTUAL fleet entries (automation/state/fleet/<arm>/decisions.jsonl):
ACTUAL = {
    "safe-3": [("12:31", "C", 747, 3, 0.33)],
    "risky-1": [],
    "risky-3": [("12:19", "C", 746, 5, 0.30), ("13:25", "C", 747, 5, 0.54)],
}

EPISODE_GAP_MIN = 15  # same <=15-min mapping convention as elite-bull-requal fills mapping


def _arm(arm_id: str) -> dict:
    for a in ACCOUNTS["arms"]:
        if a.get("id") == arm_id:
            return a
    raise KeyError(arm_id)


def load_day_rows() -> dict[str, dict[str, dict]]:
    """{minute 'HH:MM': {'safe': raw_row, 'bold': raw_row}} for DAY, last row per minute wins
    (mirrors the live producer's latest-today-row read)."""
    ticks: dict[str, dict[str, dict]] = {}
    for line in CORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or f'"{DAY}' not in line[:120]:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = str(row.get("ts_et") or "")
        if ts[:10] != DAY:
            continue
        minute = ts[11:16]
        acct = row.get("account")
        if acct not in ("safe", "bold"):
            continue
        ticks.setdefault(minute, {})[acct] = row
    return ticks


def _minutes_between(a: str, b: str) -> int:
    ah, am = int(a[:2]), int(a[3:5])
    bh, bm = int(b[:2]), int(b[3:5])
    return (bh * 60 + bm) - (ah * 60 + am)


def episodes(minutes: list[str]) -> list[tuple[str, str, int]]:
    """Collapse sorted minute list into (start, end, n_ticks) episodes split on
    > EPISODE_GAP_MIN gaps."""
    out: list[tuple[str, str, int]] = []
    if not minutes:
        return out
    start = prev = minutes[0]
    n = 1
    for m in minutes[1:]:
        if _minutes_between(prev, m) > EPISODE_GAP_MIN:
            out.append((start, prev, n))
            start, n = m, 0
        prev = m
        n += 1
    out.append((start, prev, n))
    return out


def main() -> int:
    ticks = load_day_rows()
    minutes = sorted(ticks)
    print(f"scrimmage day {DAY}: {len(minutes)} tick-minutes "
          f"(safe rows {sum(1 for m in minutes if 'safe' in ticks[m])}, "
          f"bold rows {sum(1 for m in minutes if 'bold' in ticks[m])})")

    recency = fx._recency_verdict()
    print(f"recency verdict AT REPLAY TIME (state-sensitive, Friday-live was RED): {recency}")

    arms = {a: _arm(a) for a in ARMS}
    params = {a: fx._params_for(arms[a]) for a in ARMS}
    probe_cfg = ACCOUNTS.get("probe_arm")

    # windows from each arm's own params (entry floor/ceiling enforced downstream live)
    win = {a: (params[a].get("entry_no_trade_before_et", "09:35"),
               params[a].get("entry_no_trade_after_et", "15:00")) for a in ARMS}

    enters: dict[str, list[dict]] = {a: [] for a in ARMS}
    lane_counts: dict[str, Counter] = {a: Counter() for a in ARMS}
    fs_avail: list[dict] = []
    fs_unavail_why = Counter()
    errors = Counter()

    last_safe = last_bold = None
    for minute in minutes:
        raw_safe = ticks[minute].get("safe")
        raw_bold = ticks[minute].get("bold")
        if raw_safe is not None:
            last_safe = raw_safe
        if raw_bold is not None:
            last_bold = raw_bold
        if last_safe is None and last_bold is None:
            continue
        m_safe = bss._map_core_row(last_safe) if last_safe else None
        m_bold = bss._map_core_row(last_bold) if last_bold else None
        now_dt = datetime.fromisoformat(str((last_safe or last_bold)["ts_et"]))
        try:
            sig = bss.build_from_rows(m_safe, now_dt, bold_row=m_bold, probe_row=m_safe,
                                      run_vwap=False, write=False)
        except Exception as e:  # noqa: BLE001
            errors[f"build:{type(e).__name__}"] += 1
            continue

        # full-send availability diagnostic (producer half, straight off the bold row)
        fs = (sig.get("full_send") or {})
        avail_side = next((s for s in ("bull", "bear")
                           if isinstance(fs.get(s), dict) and fs[s].get("available")), None)
        if avail_side:
            fs_avail.append({"minute": minute, "side": avail_side,
                             "score": fs[avail_side].get("score"),
                             "level": fs[avail_side].get("level"),
                             "blocked_verdict": fs[avail_side].get("blocked_verdict")})
        elif m_bold is not None and m_bold.get("action") in bss.FULL_SEND_ALLOWED_VERDICTS:
            # allowlisted verdict but block not emitted -> name the reason
            raw = last_bold
            if not raw.get("setup"):
                fs_unavail_why["no setup_name"] += 1
            elif raw.get("side") not in ("C", "P"):
                fs_unavail_why["no side"] += 1
            elif bss._full_send_level(m_bold, raw.get("side")) is None:
                fs_unavail_why["no level"] += 1
            else:
                fs_unavail_why["trigger not in ENTRY_TRIGGERS"] += 1

        for a in ARMS:
            try:
                plans = fx.plan_all(arms[a], sig, FRIDAY_SOD_EQUITY[a], params[a],
                                    probe_cfg=probe_cfg, probe_entries_today=0)
            except Exception as e:  # noqa: BLE001
                errors[f"plan:{a}:{type(e).__name__}"] += 1
                continue
            for p in plans:
                if p.action != "ENTER":
                    continue
                reason = p.reason or ""
                lane = ("FULL_SEND" if reason.startswith("FULL_SEND")
                        else "SCORE_LADDER" if reason.startswith("SCORE_LADDER")
                        else "PROBE" if reason.startswith("PROBE_ARM")
                        else "NORMAL")
                lane_counts[a][lane] += 1
                enters[a].append({"minute": minute, "lane": lane, "side": p.side,
                                  "setup": p.setup_name, "strike": p.strike, "qty": p.qty,
                                  "quality": p.quality, "strategy": p.strategy,
                                  "trigger_level": p.trigger_level, "reason": reason})

    # ---- report ----
    result: dict = {"day": DAY, "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "recency_verdict_at_replay": recency,
                    "friday_sod_equity": FRIDAY_SOD_EQUITY,
                    "tick_minutes": len(minutes), "errors": dict(errors),
                    "full_send_available_ticks": len(fs_avail),
                    "full_send_unavailable_why": dict(fs_unavail_why),
                    "arms": {}}

    print("\n" + "=" * 96)
    print(f"PER-ARM HEAD-CONFIG REPLAY OF {DAY} (plan-level; fills <= plans; "
          f"window + premium gates run downstream live)")
    print("=" * 96)
    for a in ARMS:
        lo, hi = win[a]
        all_minutes = sorted({e["minute"] for e in enters[a]})
        tradeable = [m for m in all_minutes if lo <= m < hi]
        eps = episodes(tradeable)
        actual = ACTUAL[a]
        matched = [t for t in actual if any(s <= t[0] <= e for s, e, _ in eps)]
        regressions = [t for t in actual if not any(s <= t[0] <= e for s, e, _ in eps)]
        lanes = dict(lane_counts[a])
        strikes = sorted({(e["side"], e["strike"]) for e in enters[a] if e["minute"] in tradeable})
        qtys = sorted({e["qty"] for e in enters[a] if e["minute"] in tradeable})
        print(f"\n[{a}] equity ${FRIDAY_SOD_EQUITY[a]:.2f}  lanes={lanes}")
        print(f"  ENTER-plan ticks: {len(all_minutes)} raw, {len(tradeable)} inside "
              f"[{lo},{hi}) entry window")
        print(f"  availability episodes (> {EPISODE_GAP_MIN}min gap splits): "
              f"{[(s, e, n) for s, e, n in eps]}")
        print(f"  strikes seen {strikes}  qtys seen {qtys}")
        print(f"  ACTUAL Friday entries: {actual}")
        print(f"  actual-covered-by-replay: {len(matched)}/{len(actual)}"
              + (f"  *** REGRESSION (actual entry outside replayed availability): "
                 f"{regressions}" if regressions else ""))
        result["arms"][a] = {
            "lanes": lanes, "enter_ticks_raw": len(all_minutes),
            "enter_ticks_in_window": len(tradeable),
            "episodes": [{"start": s, "end": e, "n_ticks": n} for s, e, n in eps],
            "strikes": [list(s) for s in strikes], "qtys": qtys,
            "actual": [list(t) for t in actual],
            "actual_covered": len(matched), "regressions": [list(t) for t in regressions],
            "sample_enters": enters[a][:3] + enters[a][-3:] if enters[a] else [],
        }

    print(f"\nfull-send producer block available on {len(fs_avail)} ticks; "
          f"allowlisted-but-unavailable reasons: {dict(fs_unavail_why)}")
    if fs_avail:
        print(f"  first {fs_avail[0]}  last {fs_avail[-1]}")
    if errors:
        print(f"errors: {dict(errors)}")

    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
