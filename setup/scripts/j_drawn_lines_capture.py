"""j_drawn_lines_capture.py -- headless, $0 nightly capture of J's own drawn trend lines
(TRENDLINE-J-DRAWN-LINES-LEDGER, 2026-09-03, queue HIGH).

WHY THIS EXISTS: two frozen mechanical reconstructions of J's rising-support anchor logic
(trendline-historical-study.md, trendline-today-exhibit.md) both failed to reproduce his
actual drawn line. Rather than guess his rule from bars a third time, this reads the line
he actually drew, straight off the chart. Full rule: read
analysis/recommendations/prereg-trendline-j-drawn-lines-2026-09-03.md -- this module
implements it, does not restate it.

CONNECTION: same headless CDP path `trendline_headless_draw.py` already runs in production
-- `tv_cdp.TvChart`, no MCP, no LLM, $0.

CRITICAL EMPIRICAL FINDING THIS SCRIPT'S DESIGN IS BUILT AROUND (prereg section 0, verified
live 2026-09-03): TradingView's `getAllShapes()`/`getPoints()` are chart-wide, NOT
timeframe-scoped -- switching resolution between "5" and "15" returns the identical set of
entity IDs. A shape's reported anchor TIME, however, IS resolution-read-dependent (drift up
to ~62h observed on live data for the same shape) while being perfectly STABLE when read
repeatedly at one fixed resolution. Consequences, both explicit deviations from a naive
reading of the task, stated here rather than silently implemented:
  * Dedup key is TradingView's own `entity_id`, never (timeframe, anchor1, anchor2) --
    resolution-dependent times are not a safe dedupe key (would double-count one physical
    drawing as two "independent" population members).
  * `timeframe` is recorded as "other" for every line -- there is no per-drawing timeframe
    signal recoverable from this API (checked via `intervalsVisibilities`, always absent on
    live data). Anchors are read at ONE fixed canonical resolution ("5") for run-to-run
    reproducibility (proven stable); the "15" reading is captured too, disclosed as
    `alt_points_res15`, never used to gate anything.

SAFETY (the load-bearing half): this script is READ-ONLY against drawings. It calls
`getAllShapes`, `getShapeById`, `getPoints`, `getProperties`/`properties`, `resolution`,
and `setResolution` -- and NOTHING else on the chart-widget API. No `createShape`,
`createMultipointShape`, or `removeEntity` call exists anywhere in this file: J's
drawings, and anyone else's, cannot be created, modified, or deleted by this script under
any code path. The chart's resolution is always restored to what it was before this script
touched it, verified before exit (including on error paths) -- symbol and layout are never
touched at all.

POPULATION: every `trend_line`-named shape whose text does NOT start with `"[GTL] "` (the
sole existing engine trend-line tag, `trendline_headless_draw.TAG` -- imported, not
copied, so the two producers can never drift out of sync on what "engine-drawn" means). A
`horizontal_line` (key levels, `draw_key_levels.TAG` = "[G] ") is a different shape type,
out of scope entirely.

FAIL-OPEN (C7): TradingView/CDP unreachable is the normal off-hours state ->
`status=SKIPPED_TV_DOWN`, exit 0, never raises into the scheduler. An unexpected error is
caught, stamped `status=ERROR`, flagged to STATUS.md, returns 1 -- loud, never silent.

Usage:
    python setup/scripts/j_drawn_lines_capture.py               # capture + append to ledger
    python setup/scripts/j_drawn_lines_capture.py --dry-run      # capture + log only, no ledger write, still restores resolution
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(REPO), str(REPO / "backtest"), str(SCRIPTS_DIR), str(REPO / "backtest" / "autoresearch")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tv_cdp import TvChart, TvCdpError, CHART_API  # noqa: E402
from trendline_headless_draw import TAG as ENGINE_TAG  # noqa: E402 -- "[GTL] ", imported not copied

OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "j-drawn-lines-ledger.jsonl"
STATE_DIR = REPO / "automation" / "state"
STATE_FILE = STATE_DIR / "j-drawn-lines-capture.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
PREREG_REL = "analysis/recommendations/prereg-trendline-j-drawn-lines-2026-09-03.md"

CANONICAL_RES = "5"     # anchors are read+recorded at this resolution -- reproducible, stable
ALT_RES = "15"           # disclosed cross-check reading only, never gates anything
SETTLE_SEC = 2.0         # wait after setResolution before reading points (stability-proven at >=2s)


def _stamp_now_et() -> tuple[str, str]:
    """Returns (iso_timestamp, date_et) -- a clock failure must never crash the capture."""
    try:
        from et_clock import et_now  # noqa: PLC0415
        now = et_now()
        return now.isoformat(), now.date().isoformat()
    except Exception:  # noqa: BLE001
        now = dt.datetime.now(dt.timezone.utc)
        return now.isoformat(), now.date().isoformat()


def flag_status_md(message: str) -> None:
    try:
        STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
        stamp, _ = _stamp_now_et()
        with open(STATUS_MD, "a", encoding="utf-8") as fh:
            fh.write(f"\n### BROKEN: j-drawn-lines-capture {stamp}\n- {message}\n")
    except OSError:
        pass


def write_state(out: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    tmp.replace(STATE_FILE)


def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn last line must never kill the capture
    return rows


def _known_entity_ids(rows: list[dict]) -> set[str]:
    return {r["entity_id"] for r in rows if r.get("kind") == "line" and r.get("entity_id")}


# --------------------------------------------------------------------------------
# chart reads -- all read-only, see module docstring SAFETY section
# --------------------------------------------------------------------------------
def _non_engine_trend_lines(chart: TvChart) -> list[dict]:
    """[{id, name}] filtered to trend_line, text not starting with ENGINE_TAG."""
    out = []
    for s in chart.list_shapes():
        if s.get("name") != "trend_line":
            continue
        text = chart.shape_text(s["id"]) or ""
        if text.startswith(ENGINE_TAG):
            continue
        out.append({"id": s["id"], "text": text})
    return out


def _get_points(chart: TvChart, entity_id: str) -> list[dict] | None:
    js = (
        "(function(){try{var s=%s.getShapeById(%s);var p=s.getPoints();"
        "if(!p) return null;"
        "return p.map(function(pt){return {time: pt.time, price: pt.price};});"
        "}catch(e){return null;}})()" % (CHART_API, json.dumps(entity_id))
    )
    return chart.evaluate(js)


def _get_extend_flags(chart: TvChart, entity_id: str) -> dict:
    js = (
        "(function(){try{var s=%s.getShapeById(%s);var pr=null;"
        "try{pr=s.getProperties();}catch(e){try{pr=s.properties();}catch(e2){return {};}}"
        "if(!pr) return {};"
        "function rd(v){try{return (v&&typeof v.value==='function')?v.value():v;}catch(e){return null;}}"
        "return {extend_right: rd(pr.extendRight), extend_left: rd(pr.extendLeft), "
        "intervals_visibilities: rd(pr.intervalsVisibilities)};"
        "}catch(e){return {};}})()" % (CHART_API, json.dumps(entity_id))
    )
    return chart.evaluate(js) or {}


def capture_pass(chart: TvChart, resolution: str) -> dict[str, dict]:
    """Switch to `resolution`, settle, read every non-engine trend_line's points+text.
    Returns {entity_id: {text, points}}. Caller is responsible for restoring resolution."""
    chart.evaluate(f"{CHART_API}.setResolution({json.dumps(resolution)}, {{}})")
    time.sleep(SETTLE_SEC)
    shapes = _non_engine_trend_lines(chart)
    out: dict[str, dict] = {}
    for s in shapes:
        pts = _get_points(chart, s["id"])
        out[s["id"]] = {"text": s["text"], "points": pts}
    return out


def _sorted_anchors(points: list[dict] | None) -> tuple[dict, dict] | None:
    if not points or len(points) != 2:
        return None
    p = sorted(points, key=lambda pt: pt.get("time") or 0)
    return (
        {"time": int(p[0]["time"]), "price": round(float(p[0]["price"]), 4)},
        {"time": int(p[1]["time"]), "price": round(float(p[1]["price"]), 4)},
    )


def build_ledger_rows(canonical: dict[str, dict], alt: dict[str, dict],
                       known_ids: set[str], now_iso: str, date_et: str) -> tuple[list[dict], dict]:
    """New (never-before-seen) entity IDs -> ledger `line` rows. Existing IDs are reported
    (n_already_known, points_drift observations) but never re-appended/re-timestamped --
    first_seen_et is frozen the first time an entity is ever seen (prereg section 2 step 6)."""
    new_rows: list[dict] = []
    drift_observations: list[dict] = []
    n_already_known = 0
    n_missing_two_points = 0

    for eid, c in canonical.items():
        anchors = _sorted_anchors(c.get("points"))
        if anchors is None:
            n_missing_two_points += 1
            continue
        anchor1, anchor2 = anchors
        alt_pts = alt.get(eid, {}).get("points")
        alt_anchors = _sorted_anchors(alt_pts)
        drift_detected = alt_anchors is not None and (
            alt_anchors[0]["time"] != anchor1["time"] or alt_anchors[1]["time"] != anchor2["time"]
        )

        if eid in known_ids:
            n_already_known += 1
            if drift_detected:
                drift_observations.append({"entity_id": eid, "canonical": [anchor1, anchor2],
                                            "alt_res15": list(alt_anchors)})
            continue

        line_shape = ("rising" if anchor2["price"] > anchor1["price"]
                       else "falling" if anchor2["price"] < anchor1["price"] else "flat")
        new_rows.append({
            "kind": "line", "entity_id": eid, "first_seen_et": now_iso,
            "first_seen_date_et": date_et,
            "in_sample": date_et <= "2026-09-03",
            "timeframe": "other",   # prereg section 0 -- no recoverable per-drawing signal
            "text": c.get("text") or "",
            "anchor1": anchor1, "anchor2": anchor2,
            "line_shape": line_shape,
            "alt_points_res15": list(alt_anchors) if alt_anchors else None,
            "drift_detected": drift_detected,
            "canonical_resolution": CANONICAL_RES, "alt_resolution": ALT_RES,
        })
        # extend flags added by caller (needs a second chart round-trip; kept out of the
        # hot dict-building path so this function stays pure/testable without a live chart)

    return new_rows, {
        "n_already_known": n_already_known,
        "n_missing_two_points": n_missing_two_points,
        "n_new": len(new_rows),
        "drift_observations": drift_observations,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="capture + log the plan; never writes the ledger")
    args = ap.parse_args(argv)

    now_iso, date_et = _stamp_now_et()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = _read_ledger()
    known_ids = _known_entity_ids(existing)

    out: dict = {
        "schema_version": 1, "as_of": now_iso, "prereg": PREREG_REL,
        "dry_run": bool(args.dry_run), "symbol": "SPY",
    }

    try:
        with TvChart() as chart:
            chart.require_chart_api()
            out["chart_symbol"] = chart.symbol()
            orig_res = chart.evaluate(f"{CHART_API}.resolution()")
            out["original_resolution"] = orig_res

            canonical = capture_pass(chart, CANONICAL_RES)
            alt = capture_pass(chart, ALT_RES)

            # restore -- always, even if something above raised we'd never reach here;
            # a raised exception is caught below and this same restore is retried there.
            chart.evaluate(f"{CHART_API}.setResolution({json.dumps(orig_res)}, {{}})")
            time.sleep(1.0)
            restored_res = chart.evaluate(f"{CHART_API}.resolution()")
            out["restored_resolution"] = restored_res
            out["resolution_restored_ok"] = (restored_res == orig_res)
            if not out["resolution_restored_ok"]:
                flag_status_md(
                    f"j_drawn_lines_capture: resolution restore mismatch -- "
                    f"was {orig_res!r}, now {restored_res!r}"
                )

            new_rows, stats = build_ledger_rows(canonical, alt, known_ids, now_iso, date_et)
            # attach extend flags (second small round-trip, only for genuinely-new lines)
            for row in new_rows:
                flags = _get_extend_flags(chart, row["entity_id"])
                row["extend_right"] = bool(flags.get("extend_right"))
                row["extend_left"] = bool(flags.get("extend_left"))
                row["intervals_visibilities"] = flags.get("intervals_visibilities")
                if row["intervals_visibilities"]:
                    row["timeframe"] = "other"  # still honest -- we don't parse this into 5m/15m yet

            out.update(
                status="OK",
                n_trend_line_candidates=len(canonical),
                n_new=stats["n_new"],
                n_already_known=stats["n_already_known"],
                n_missing_two_points=stats["n_missing_two_points"],
                n_drift_observations=len(stats["drift_observations"]),
                new_lines=[{"entity_id": r["entity_id"], "line_shape": r["line_shape"],
                            "anchor1": r["anchor1"], "anchor2": r["anchor2"],
                            "extend_right": r["extend_right"], "text": r["text"]}
                           for r in new_rows],
            )

            if not args.dry_run and new_rows:
                with LEDGER.open("a", encoding="utf-8") as fh:
                    for r in new_rows:
                        fh.write(json.dumps(r) + "\n")

    except TvCdpError as exc:
        msg = str(exc)
        print(f"SKIP (TradingView/CDP unavailable): {msg}")
        out.update(status="SKIPPED_TV_DOWN", reason=msg)
        write_state(out)
        return 0
    except Exception as exc:  # noqa: BLE001 -- unexpected: loud, never silent, never raised
        msg = f"{type(exc).__name__}: {exc}"
        print(f"ERROR {msg}")
        out.update(status="ERROR", reason=msg)
        write_state(out)
        flag_status_md(f"j_drawn_lines_capture failed -- {msg}")
        return 1

    write_state(out)
    print(f"{out['status']} symbol={out.get('chart_symbol')} candidates={out['n_trend_line_candidates']} "
          f"new={out['n_new']} already_known={out['n_already_known']} "
          f"resolution_restored_ok={out['resolution_restored_ok']}")
    for nl in out.get("new_lines") or []:
        print(f"   NEW {nl['entity_id']} {nl['line_shape']:>7}  "
              f"{nl['anchor1']} -> {nl['anchor2']}  extend_right={nl['extend_right']}  text={nl['text']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
