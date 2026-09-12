"""sd_zones_producer.py -- headless, $0 supply/demand zone producer (GOAL-SD-LIQUIDITY-
ZONES-2026-09-11 item b).

WHY THIS EXISTS: J (2026-09-11 ~23:30 ET, verbatim): "what we really need is true supply
and demand liquidity zones fined them and find the indicator an get it on the chart".
Item (a) put `Smart Money Concepts [LuxAlgo]` on the live SPY 5m layout and proved its
order-block boxes are readable headlessly via CDP (`data_get_pine_boxes`). This script is
item (b): turn those boxes into a scored SHADOW state file, `automation/state/sd-
zones.json`, that a future promotion step (item d/e) can compare against the existing
MEMORY/INTRADAY level classes -- WITHOUT ever entering `key-levels.json`.

WHY A SHADOW FILE, NOT key-levels.json: `heartbeat_core._read_level_records` filters on
expiry and +-$12 only -- no tier/role filter (the 2026-09-10 WS-E finding). A zone written
straight into `key-levels.json` would silently enter the live entry gate with zero
validation. This file is invisible to the engine until a pre-registered checkpoint
promotes it (09-29 if risk-reduction-only, 10-30 otherwise) -- see the goal's DONE-WHEN.

WHY A NEW SCRIPT, NOT INSIDE refresh_levels_intraday.py: that file (+3 sibling level
producers) was added to `setup/hooks/doctrine.FROZEN_TRADING_PATH` on 2026-09-11 (FABLE-
FULL-AUDIT-2026-09-11 S3b) for the September clean window (through 2026-10-30). This is a
brand-new file -- the freeze cannot apply to code that does not yet exist -- so the
touches-uniform math is REUSED by import (`_uniform_touches`, `_zone_width`, `_spy_bars`
from `refresh_levels_intraday`, all read-only references, zero edits to that module) so
the ranking rule for "is this zone respected" stays IDENTICAL to the one J already
validated for the most-touched cap, rather than inventing a second one.

MECHANISM: `tv_cdp.TvChart.pine_boxes(study_filter="Smart Money")` reads the LuxAlgo
study's rendered `box.new(...)` primitives over CDP (same walk the TradingView MCP's
`getPineBoxes` performs -- see `TvChart.pine_boxes`'s own docstring). Each box's
[low, high] is treated as a symmetric zone around its midpoint (`price=mid,
zone_width=(high-low)/2`) so `_uniform_touches` -- built for a symmetric level+width pair
-- scores it against real SPY 5m bars with ZERO change to its own logic. `kind` is
supply/demand purely by the zone's position relative to spot at write time (mid > spot =>
supply/resistance-side, mid < spot => demand/support-side); this is a naming heuristic,
not itself validated -- item (d)'s SD_ZONE forward read is what earns or kills it.

FAIL-OPEN (C7): TradingView/CDP unreachable (the normal off-hours state) preserves the
PRIOR zones list untouched with `status=SKIPPED_TV_DOWN` -- never wipes to empty, so a
downstream reader never mistakes "TV was closed" for "the zones disappeared". Any
unexpected error is caught, stamped `status=ERROR`, flagged to STATUS.md, and returns 1
(loud, never a bare traceback into Task Scheduler). This state file is unwired from
`engine_health.py` on purpose -- its absence or staleness can never turn the engine RED.

DRAWING (opt-in, `--draw`): draws each zone as a `rectangle` tagged "[SD] " via
`TvChart.create_rectangle`, mirroring `draw_key_levels.py`/`trendline_headless_draw.py`'s
own-shape-only removal discipline (never touches an untagged/unrecorded shape). Left OFF
by default in the scheduled cadence below -- the SMC LuxAlgo study already paints these
same boxes directly on the chart, and J's most-recent chart directive was "remove all
lines other than the most touched ones, there are too many" (2026-09-11); a second,
redundant rendering of the same zones would work against that. Verified live once
(2026-09-12) to prove the mechanism, not left running unattended.

Usage:
    python setup/scripts/sd_zones_producer.py                # compute + write state
    python setup/scripts/sd_zones_producer.py --dry-run       # compute + log only
    python setup/scripts/sd_zones_producer.py --draw          # also draw rectangles
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
for _p in (str(REPO), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytz  # noqa: E402

from et_clock import et_now  # noqa: E402
from tv_cdp import TvChart, TvCdpError  # noqa: E402

# Read-only reuse of the ALREADY-RATIFIED touch/zone-width math -- refresh_levels_intraday.py
# is on FROZEN_TRADING_PATH (2026-09-11); importing it does not edit it.
from refresh_levels_intraday import _spy_bars, _uniform_touches, _zone_width  # noqa: E402

STATE_DIR = REPO / "automation" / "state"
STATE_FILE = STATE_DIR / "sd-zones.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
ET = pytz.timezone("America/New_York")

# GOAL item (d): a "forward clock" needs one snapshot PER SESSION, not just the latest
# in-place overwrite sd-zones.json already does. Mirrors journal/gex-archive/'s per-day
# file pattern. Only a real, freshly-read capture counts as a session (status == "OK",
# never a --dry-run and never a SKIPPED_TV_DOWN carry-forward of yesterday's zones --
# counting a skip would silently inflate "sessions accrued" with days TV never answered).
ARCHIVE_DIR = REPO / "journal" / "sd-zones-archive"
FORWARD_CLOCK_FILE = STATE_DIR / "sd-zone-forward-clock.json"

# The study added under item (a). A substring match, same convention item (a) verified
# live (`data_get_pine_boxes(study_filter="Smart Money")` returned 5 zones).
STUDY_FILTER = "Smart Money"
SOURCE_STUDY = "Smart Money Concepts [LuxAlgo]"

# INPUT TRIM, ENFORCED PER FIRE (2026-09-12 01:3x ET). The study's inputs are what J wants read:
# in_3  "Show Internal Structure" OFF  -- internal order blocks are the "too many lines" class;
# in_21 "Swing Order Blocks"      ON   -- the supply/demand BASES this goal is about.
# Positional ids read live 2026-09-11 (goal file). Setting them via the page API + Ctrl+S did NOT
# survive a cold TradingView relaunch (verified 2026-09-12 01:28 ET: defaults in_3=true/in_21=false
# came back, box count 10 -> 5), so the producer sets them itself before every read. Deterministic
# across relaunches and auto-updates; fail-open (an enforcement failure is recorded in the state
# file and the boxes are still read).
SD_STUDY_INPUTS: dict[str, bool] = {"in_3": False, "in_21": True}
STUDY_RECOMPUTE_WAIT_S = 3.0   # let the study re-render its boxes after an input change

# Marker for our own drawn rectangles -- distinct from draw_key_levels.py's "[G] " and
# trendline_headless_draw.py's "[GTL] " so all three producers can never mistake each
# other's shapes.
TAG = "[SD] "


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"schema_version": 1, "zones": [], "drawn": []}
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "zones": [], "drawn": []}
    if not isinstance(raw, dict):
        return {"schema_version": 1, "zones": [], "drawn": []}
    raw.setdefault("zones", [])
    raw.setdefault("drawn", [])
    return raw


def write_state(out: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    tmp.replace(STATE_FILE)


def archive_snapshot(day: str, out: dict) -> None:
    """One file per session, last-write-of-the-day wins (matches gex-archive convention).
    Only called for a real successful capture -- see the ARCHIVE_DIR docstring above."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"{day}.json"
    snapshot = {
        "date": day,
        "as_of": out.get("as_of"),
        "chart_symbol": out.get("chart_symbol"),
        "spot": out.get("spot"),
        "zones": out.get("zones") or [],
    }
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2)
    tmp.replace(path)


def update_forward_clock(day: str) -> dict:
    """Append `day` to the accrued-sessions list (idempotent) and recompute eligibility.
    GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item (d) needs >= 10 accrued sessions before the
    forward read (item e) is meaningful -- see prereg-sd-zone-anchor-promotion-2026-09-12.md."""
    if FORWARD_CLOCK_FILE.exists():
        try:
            clock = json.loads(FORWARD_CLOCK_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            clock = {}
    else:
        clock = {}
    if not isinstance(clock, dict):
        clock = {}
    dates = sorted(set(clock.get("archived_dates") or []) | {day})
    clock = {
        "schema_version": 1,
        "first_archived_date": dates[0],
        "archived_dates": dates,
        "sessions_accrued": len(dates),
        "eligible_for_forward_read": len(dates) >= 10,
        "updated_at": day,
    }
    tmp = FORWARD_CLOCK_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clock, fh, indent=2)
    tmp.replace(FORWARD_CLOCK_FILE)
    return clock


def flag_status_md(message: str) -> None:
    try:
        STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
        with open(STATUS_MD, "a", encoding="utf-8") as fh:
            fh.write(f"\n### BROKEN: sd_zones_producer {stamp}\n- {message}\n")
    except OSError:
        pass


def _enforce_inputs_js() -> str:
    return """
    (function() {
      var want = %s, filter = %s, out = [];
      var c = window.TradingViewApi.activeChart();
      c.getAllStudies().forEach(function(s) {
        if ((s.name || '').indexOf(filter) === -1) return;
        var st = c.getStudyById(s.id);
        var pick = function(vals) { return vals.filter(function(x) { return Object.prototype.hasOwnProperty.call(want, x.id); })
                                                .map(function(x) { return [x.id, x.value]; }); };
        var before = pick(st.getInputValues());
        var need = before.filter(function(p) { return p[1] !== want[p[0]]; });
        if (need.length) { st.setInputValues(need.map(function(p) { return {id: p[0], value: want[p[0]]}; })); }
        out.push({id: s.id, name: s.name, changed: need.length, before: before, after: pick(st.getInputValues())});
      });
      return out;
    })()
    """ % (json.dumps(SD_STUDY_INPUTS), json.dumps(STUDY_FILTER))


def enforce_study_inputs(chart) -> dict:
    """Set SD_STUDY_INPUTS on every matching study before the box read (see the constant's note).
    Fail-open: a chart client without `evaluate` (tests, older clients) or a JS failure is RECORDED,
    never raised -- the box read that follows is the fire's real job."""
    ev = getattr(chart, "evaluate", None)
    if ev is None:
        return {"status": "unavailable", "wanted": dict(SD_STUDY_INPUTS)}
    try:
        res = ev(_enforce_inputs_js()) or []
    except Exception as exc:  # noqa: BLE001 -- enforcement is best-effort by design
        return {"status": "error", "message": f"{type(exc).__name__}: {exc}"[:160], "wanted": dict(SD_STUDY_INPUTS)}
    changed = sum(int(r.get("changed") or 0) for r in res)
    if changed and STUDY_RECOMPUTE_WAIT_S > 0:
        time.sleep(STUDY_RECOMPUTE_WAIT_S)
    return {"status": "ok" if res else "no_study", "changed": changed, "studies": res, "wanted": dict(SD_STUDY_INPUTS)}


def classify_zones(raw_zones: list[dict], spot: float, df) -> list[dict]:
    """[{low, high, mid, kind, touches_uniform, source_study}, ...] per the goal's schema.

    `kind` is a naming heuristic (position relative to spot at write time), NOT a
    validated classification -- see this module's own docstring. `touches_uniform` reuses
    `_uniform_touches` unchanged: the zone's [low, high] IS [price-w, price+w] for
    price=mid, w=(high-low)/2, so the symmetric-zone assumption that function was built
    for holds exactly.
    """
    out: list[dict] = []
    for z in raw_zones:
        try:
            high, low = float(z["high"]), float(z["low"])
        except (KeyError, TypeError, ValueError):
            continue
        if high < low:
            high, low = low, high
        mid = round((high + low) / 2, 2)
        half = (high - low) / 2
        if half <= 0:
            half = _zone_width(mid)
        kind = "supply" if mid > spot else ("demand" if mid < spot else "liquidity")
        role = "resistance" if kind == "supply" else "support"
        touches = _uniform_touches({"price": mid, "zone_width": half, "role": role}, df, spot)
        out.append({
            "low": round(mid - half, 2),
            "high": round(mid + half, 2),
            "mid": mid,
            "kind": kind,
            "touches_uniform": touches,
            "source_study": SOURCE_STUDY,
        })
    out.sort(key=lambda z: -z["touches_uniform"])
    return out


def _own_rectangles(chart: TvChart) -> list[dict]:
    return [s for s in chart.list_shapes() if s.get("name") == "rectangle"]


def remove_own_drawings(chart: TvChart, state: dict, dry_run: bool) -> list[dict]:
    """Remove every rectangle provably ours: recorded entity_id, or TAG-prefixed text
    (orphan recovery). NEVER touches a horizontal_line/trend_line/untagged rectangle."""
    recorded = {d.get("entity_id") for d in state.get("drawn") or [] if d.get("entity_id")}
    on_chart = _own_rectangles(chart)
    on_chart_ids = {s["id"] for s in on_chart}

    targets: list[dict] = []
    for sid in recorded & on_chart_ids:
        targets.append({"entity_id": sid, "why": "recorded_in_state"})
    already = {t["entity_id"] for t in targets}
    for shape in on_chart:
        if shape["id"] in already:
            continue
        text = chart.shape_text(shape["id"]) or ""
        if text.startswith(TAG):
            targets.append({"entity_id": shape["id"], "why": "tagged_orphan", "text": text})

    if dry_run:
        return targets
    removed = []
    for t in targets:
        try:
            if chart.remove_entity(t["entity_id"]):
                removed.append(t)
        except TvCdpError:
            continue
    return removed


def draw_zones(chart: TvChart, zones: list[dict], dry_run: bool) -> list[dict]:
    now_unix = int(dt.datetime.now(dt.timezone.utc).timestamp())
    drawn: list[dict] = []
    for z in zones:
        text = f"{TAG}{z['kind']} {z['touches_uniform']}t"
        if dry_run:
            drawn.append({"entity_id": None, "low": z["low"], "high": z["high"], "text": text})
            continue
        p1 = {"time": now_unix - 3600 * 8, "price": z["low"]}
        p2 = {"time": now_unix, "price": z["high"]}
        eid = chart.create_rectangle(p1, p2, text)
        drawn.append({"entity_id": eid, "low": z["low"], "high": z["high"], "text": text})
    return drawn


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="compute + log; touch nothing")
    ap.add_argument("--draw", action="store_true", help="also draw rectangles on the chart")
    args = ap.parse_args(argv)

    now = et_now()
    state = load_state()
    out: dict = {
        "schema_version": 1,
        "as_of": now.isoformat(),
        "study_filter": STUDY_FILTER,
        "dry_run": bool(args.dry_run),
    }

    try:
        df = _spy_bars()
    except Exception as exc:  # noqa: BLE001 -- bar fetch failure is real, never silent
        msg = f"bar fetch failed: {type(exc).__name__}: {exc}"
        print(f"ERROR {msg}")
        out.update(status="ERROR", reason=msg, zones=state.get("zones", []), drawn=state.get("drawn", []))
        write_state(out)
        flag_status_md(f"sd_zones_producer failed -- {msg}")
        return 1

    try:
        with TvChart() as chart:
            chart.require_chart_api()
            out["chart_symbol"] = chart.symbol()
            spot = chart.last_price()
            if spot is None:
                raise TvCdpError("chart.last_price() returned None")

            out["inputs_enforced"] = enforce_study_inputs(chart)
            studies = chart.pine_boxes(study_filter=STUDY_FILTER)
            raw_zones: list[dict] = []
            for s in studies:
                raw_zones.extend(s.get("zones") or [])
            zones = classify_zones(raw_zones, spot, df)
            out["spot"] = spot
            out["n_studies_matched"] = len(studies)
            out["zones"] = zones

            if args.dry_run:
                out["status"] = "DRY_RUN"
                out["drawn"] = state.get("drawn", [])
                print(json.dumps(out, indent=2))
                return 0

            if args.draw:
                removed = remove_own_drawings(chart, state, dry_run=False)
                drawn = draw_zones(chart, zones, dry_run=False)
                out["removed"] = removed
                out["drawn"] = drawn
            else:
                out["drawn"] = state.get("drawn", [])

            out["status"] = "OK"

    except TvCdpError as exc:
        msg = str(exc)
        print(f"SKIP (TradingView/CDP unavailable): {msg}")
        # Fail-open: preserve the LAST KNOWN GOOD zones, never wipe to empty on a TV-down tick.
        out.update(status="SKIPPED_TV_DOWN", reason=msg,
                    zones=state.get("zones", []), drawn=state.get("drawn", []))
        write_state(out)
        return 0
    except Exception as exc:  # noqa: BLE001 -- unexpected: loud, never a bare traceback
        msg = f"{type(exc).__name__}: {exc}"
        print(f"ERROR {msg}")
        out.update(status="ERROR", reason=msg, zones=state.get("zones", []), drawn=state.get("drawn", []))
        write_state(out)
        flag_status_md(f"sd_zones_producer failed -- {msg}")
        return 1

    write_state(out)
    if out["status"] == "OK" and not args.dry_run:
        day = now.strftime("%Y-%m-%d")
        try:
            archive_snapshot(day, out)
            update_forward_clock(day)
        except OSError as exc:  # noqa: BLE001 -- archiving is best-effort, never blocks the live write
            flag_status_md(f"sd_zones_producer archive/clock write failed -- {exc}")
    print(f"{out['status']} symbol={out.get('chart_symbol')} spot={out.get('spot')} "
          f"n_zones={len(out.get('zones') or [])}")
    for z in out.get("zones") or []:
        print(f"   {z['kind']:>8}  {z['low']:.2f}-{z['high']:.2f}  touches={z['touches_uniform']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
