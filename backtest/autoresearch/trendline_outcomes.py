"""trendline_outcomes.py -- the LEARN loop for trendline breaks.

Built 2026-06-26 (J, watching a break play out live: "you better be documenting and learning
from this"). Logging the LINE isn't learning; learning is: when a support breaks, record the
predicted next-level-down target, then TRACK whether price actually reached it -- and accumulate
those labeled (break -> outcome) examples until we can say whether "trendline break -> next level"
is a tradeable edge (hit-rate, favorable excursion, time-to-target), per the OP-11 data flywheel.

Each run: detect the current support line (via trendline_engine), and if it is BROKEN (a 5m CLOSE
below it), UPSERT a break event keyed by (date, break_et) into analysis/trendlines/break-outcomes.jsonl,
then RESOLVE every still-open event against later bars (HIT_TARGET / BOUNCED / OPEN + MFE/MAE). Prints
the running scorecard. Idempotent; pure stdlib. Run headless or behind /trendline-draw; schedule a
5-min cadence during RTH to auto-resolve, OR call once after a break to seed the record.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trendline_engine as te  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "trendlines" / "break-outcomes.jsonl"
KEY_LEVELS = REPO / "automation" / "state" / "key-levels.json"
TOL = te.TOL
RECLAIM_TOL = 0.15   # close back above the broken line by this much = BOUNCED (reclaimed)


def _levels() -> list[tuple[float, str]]:
    try:
        d = json.loads(KEY_LEVELS.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = d if isinstance(d, list) else d.get("levels", [])
    out = []
    for L in rows:
        if isinstance(L, dict) and L.get("price"):
            out.append((float(L["price"]), str(L.get("label", "?"))))
    return sorted(set(out))


def _next_level_down(price: float) -> tuple[float, str] | None:
    below = [L for L in _levels() if L[0] < price - 0.05]
    return max(below, key=lambda x: x[0]) if below else None


def _line_val(line: te.Trendline, bars: list[dict], j: int) -> float:
    a_idx = next((i for i, b in enumerate(bars) if te._et(b["t"]) == line.a_et), 0)
    return line.a_price + line.slope_per_bar * (j - a_idx)


def _read() -> list[dict]:
    if not OUT.exists():
        return []
    return [json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip()]


def _write(events: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def record_and_resolve(bars: list[dict], date_et: str) -> list[dict]:
    events = _read()
    by_key = {(e["date"], e["break_et"]): e for e in events}

    # 1) detect a fresh support break and seed a break event. Decoupled from the engine's
    # conservative BROKEN label: ANY confirmed close below the line (small margin to skip touch-
    # noise) seeds a record. Marginal closes that later reclaim get labeled BOUNCED -- and the
    # bounce-vs-hit split is exactly the edge we're trying to learn (do breaks follow through?).
    support = next((l for l in te.detect(bars) if l.kind == "support"), None)
    if support:
        # A trendline only EXISTS from its 2nd anchor forward -- searching before it projects the
        # line backward into bars it never described (the 09:35 spurious-break bug). Start at b2+1.
        b2 = next((i for i, b in enumerate(bars) if te._et(b["t"]) == support.b_et), 0)
        b_idx = next((i for i in range(b2 + 1, len(bars)) if bars[i]["c"] < _line_val(support, bars, i) - 0.05), None)
        if b_idx is not None:
            bk_et = te._et(bars[b_idx]["t"])
            key = (date_et, bk_et)
            if key not in by_key:
                tgt = _next_level_down(bars[b_idx]["c"])
                ev = {"date": date_et, "break_et": bk_et, "break_close": round(bars[b_idx]["c"], 2),
                      "broken_line": f"{support.a_et}@{support.a_price}->{support.b_et}@{support.b_price}",
                      "line_value_at_break": round(_line_val(support, bars, b_idx), 2),
                      "respect_count": support.respect_count,
                      "target_price": (round(tgt[0], 2) if tgt else None),
                      "target_label": (tgt[1] if tgt else None),
                      "status": "OPEN", "low_after": None, "high_after": None,
                      "bars_to_target": None, "mfe_dollars": None, "resolved_et": None}
                events.append(ev); by_key[key] = ev

    # 2) resolve every still-open event against later bars
    for ev in events:
        if ev["status"] != "OPEN":
            continue
        after = [b for b in bars if te._et(b["t"]) >= ev["break_et"]]
        if not after:
            continue
        low = min(b["l"] for b in after)
        ev["low_after"] = round(low, 2)
        ev["high_after"] = round(max(b["h"] for b in after), 2)
        ev["mfe_dollars"] = round(ev["break_close"] - low, 2)  # favorable = down (it was a short read)
        tgt = ev.get("target_price")
        if tgt is not None and low <= tgt:
            hit_i = next(i for i, b in enumerate(after) if b["l"] <= tgt)
            ev["status"] = "HIT_TARGET"
            ev["bars_to_target"] = hit_i
            ev["resolved_et"] = te._et(after[hit_i]["t"])
        elif after[-1]["c"] > ev["line_value_at_break"] + RECLAIM_TOL:
            ev["status"] = "BOUNCED"  # reclaimed the broken line before reaching target = failed break
            ev["resolved_et"] = te._et(after[-1]["t"])

    _write(events)
    return events


def _scorecard(events: list[dict]) -> str:
    resolved = [e for e in events if e["status"] in ("HIT_TARGET", "BOUNCED")]
    hits = [e for e in resolved if e["status"] == "HIT_TARGET"]
    n = len(resolved)
    if not events:
        return "  no break events yet"
    hr = f"{len(hits)}/{n} = {100*len(hits)/n:.0f}%" if n else "0 resolved"
    mfes = [e["mfe_dollars"] for e in resolved if e.get("mfe_dollars") is not None]
    avg_mfe = f"${sum(mfes)/len(mfes):.2f}" if mfes else "n/a"
    btt = [e["bars_to_target"] for e in hits if e.get("bars_to_target") is not None]
    avg_btt = f"{sum(btt)/len(btt):.1f} bars" if btt else "n/a"
    return (f"  LEARN scorecard: {len(events)} breaks logged | resolved {n} | "
            f"reached-next-level {hr} | avg MFE-down {avg_mfe} | avg time-to-target {avg_btt}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    bars = te.fetch_spy_5m(f"{day}T13:30:00Z", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if len(bars) < te.MIN_SPAN + 2:
        print("trendline_outcomes: too few bars")
        return 0
    events = record_and_resolve(bars, day)
    todays = [e for e in events if e["date"] == day]
    print(f"trendline_outcomes {day}:")
    for e in todays:
        tgt = f"{e['target_label']} {e['target_price']}" if e.get("target_price") else "no level below"
        line = (f"  break {e['break_et']} @ {e['break_close']} (line {e['line_value_at_break']}, "
                f"respected x{e['respect_count']}) -> target {tgt} | {e['status']}")
        if e["status"] == "HIT_TARGET":
            line += f" in {e['bars_to_target']} bars (low {e['low_after']})"
        elif e["status"] == "OPEN":
            line += f" | low so far {e['low_after']} (MFE-down ${e['mfe_dollars']})"
        print(line)
    print(_scorecard(events))
    print(f"  logged -> {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
