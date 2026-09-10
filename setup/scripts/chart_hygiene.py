"""chart_hygiene.py -- headless, $0 chart-clutter sweep (WS-B, work order §9.5 row B,
markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md#95-workstreams, 2026-09-09).

WHY THIS EXISTS: `draw_list` returned 68 shapes live this session -- ~23 untagged
trendlines back to 2026-05-08, 4 rays, ~15 orange unlabeled premarket LLM lines, and
one-off labels ("Death Cross", "R at LOW", "*** 769.24 BROKEN now RESISTANCE ***") with
NO producer anywhere in the repo (grep-verified). `draw_key_levels.py` and
`trendline_headless_draw.py` each remove only their OWN tag, so nothing ever cleans up
the rest -- this is the missing subtractor.

SAFETY -- the two-step design that makes this impossible to lose J's actual work:
    1. **Registry first, always.** `capture_registry()` is a deliberate, explicit,
       manually-invoked snapshot (`--capture-registry`) of every shape on the chart
       whose text does NOT start with an engine tag (see `engine_shape_tags.py`) --
       i.e. everything that is not provably an engine producer's own drawing is
       treated as J's and frozen into `automation/state/j-shapes.json` forever.
       Membership is APPEND-ONLY and `first_seen_et` is frozen the first time an id is
       ever seen (mirrors `j_drawn_lines_capture.py::build_ledger_rows` -- same
       semantics, deliberately not imported since that module is off-limits this
       session for a concurrent edit by another agent).
       This step is intentionally NOT run automatically inside the recurring sweep --
       if it were, every future session's newly-accumulated clutter would be captured
       and permanently protected before the sweep ever got a chance to age it out.
    2. **The sweep (`run_sweep`) never removes a registered id, ever, full stop** --
       `classify_shape()` checks registry membership before anything else, ahead of any
       tag/band/age reasoning. Untagged shapes NOT in the registry become removal
       candidates only once they persist across >= STALE_SESSIONS_THRESHOLD prior
       sweep-dates (i.e. this is at least their 3rd distinct calendar-day sighting).
       Orphan `[G]`/`[GTL]` shapes (still alive between a producer's own refresh
       cycles, i.e. its normal remove-then-redraw didn't touch them this cycle) are
       judged purely by whether any anchor point sits inside the current draw band --
       in band = kept (still relevant), outside = removal candidate.
    3. `draw_clear`/`removeAllShapes()` is never called anywhere in this file --
       shapes are removed ONE id at a time via `TvChart.remove_entity`.
    4. Dry-run is the DEFAULT. `--apply` is required to actually remove anything, and
       even then every decision (kept AND removed AND would-remove) is logged to
       `analysis/chart-hygiene/{date}.jsonl` so a sweep is always auditable after the
       fact.
    5. Fail-open (C7): TradingView/CDP unreachable -> log + exit 0, remove nothing,
       never raise. An unexpected error is caught, flagged to STATUS.md, and returns 1
       -- loud, never silent, but still never mid-way through a removal loop.

Usage:
    python setup/scripts/chart_hygiene.py --capture-registry   # one-time/rare bootstrap
    python setup/scripts/chart_hygiene.py                      # dry-run sweep (default)
    python setup/scripts/chart_hygiene.py --apply               # actually remove
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(REPO), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytz  # noqa: E402

from tv_cdp import TvChart, TvCdpError, CHART_API  # noqa: E402
import draw_key_levels as dkl  # noqa: E402 -- DEFAULT_BAND_DOLLARS is the single source of truth
from engine_shape_tags import ENGINE_TAG_PREFIXES  # noqa: E402 -- "[G] "/"[GTL] "/"[GE] ", imported not copied

try:
    from et_clock import et_now  # noqa: E402
except Exception:  # pragma: no cover - clock failure must never crash hygiene
    def et_now() -> dt.datetime:  # type: ignore[no-redef]
        return dt.datetime.now(pytz.timezone("America/New_York"))

STATE_DIR = REPO / "automation" / "state"
REGISTRY_FILE = STATE_DIR / "j-shapes.json"
OBSERVATIONS_FILE = STATE_DIR / "chart-hygiene-observations.json"
LOG_DIR = REPO / "analysis" / "chart-hygiene"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
ET = pytz.timezone("America/New_York")

# An untagged, unregistered shape becomes a removal candidate once it has persisted
# across at least this many DISTINCT PRIOR sweep dates (i.e. today is at least its 3rd
# sighting). Named "2 sessions" per the work order.
STALE_SESSIONS_THRESHOLD = 2


# --------------------------------------------------------------------------
# pure helpers -- no CDP, fully unit-testable
# --------------------------------------------------------------------------

def is_engine_tagged(text: str, tag_prefixes: tuple[str, ...] = ENGINE_TAG_PREFIXES) -> str | None:
    """Returns the matching tag prefix, or None if `text` is not engine-drawn."""
    text = text or ""
    for tag in tag_prefixes:
        if text.startswith(tag):
            return tag
    return None


def within_band(points: list[dict] | None, spot: float | None, band_dollars: float) -> bool:
    """True if any anchor point is within `band_dollars` of `spot`.

    Fails open on uncertain data (no spot, no points): "cannot disprove relevance" ->
    treated as in-band -> never removed on a data gap.
    """
    if spot is None or not points:
        return True
    for p in points:
        try:
            price = float(p.get("price"))
        except (TypeError, ValueError, AttributeError):
            continue
        if abs(price - spot) <= band_dollars:
            return True
    return False


def classify_shape(
    shape: dict,
    spot: float | None,
    band_dollars: float,
    registry_ids: set[str],
    prior_dates: list[str],
    today_date: str,
    tag_prefixes: tuple[str, ...] = ENGINE_TAG_PREFIXES,
    stale_threshold: int = STALE_SESSIONS_THRESHOLD,
) -> dict:
    """Pure removal-policy decision for one shape. `shape` = {id, name, text, points}.

    Returns {"action": "keep"|"remove", "reason": str}. Registry membership is checked
    FIRST, unconditionally, ahead of any tag/band/age reasoning -- this is what makes
    "a registered shape is never removed" true regardless of what else is true about it.
    """
    sid = shape.get("id")
    text = shape.get("text") or ""

    if sid in registry_ids:
        return {"action": "keep", "reason": "j_registry"}

    tag = is_engine_tagged(text, tag_prefixes)
    if tag is None:
        distinct_prior = {d for d in (prior_dates or []) if d != today_date}
        if len(distinct_prior) >= stale_threshold:
            return {"action": "remove", "reason": f"untagged_stale_{stale_threshold}plus_sessions"}
        return {"action": "keep", "reason": "untagged_recent"}

    # Tagged, but still alive to be looked at by hygiene at all -- its own producer's
    # normal remove-then-redraw cycle didn't touch it this pass, i.e. an orphan. Band
    # membership is the only signal hygiene itself owns for these.
    if within_band(shape.get("points"), spot, band_dollars):
        return {"action": "keep", "reason": f"{tag.strip()}_in_band"}
    return {"action": "remove", "reason": f"{tag.strip()}_orphan_outside_band"}


# --------------------------------------------------------------------------
# state I/O
# --------------------------------------------------------------------------

def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return dict(default)


def _write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    tmp.replace(path)


def load_registry() -> dict:
    return _load_json(REGISTRY_FILE, {"schema_version": 1, "shapes": {}})


def save_registry(reg: dict) -> None:
    _write_json_atomic(REGISTRY_FILE, reg)


def load_observations() -> dict:
    return _load_json(OBSERVATIONS_FILE, {"schema_version": 1, "shapes": {}})


def save_observations(obs: dict) -> None:
    _write_json_atomic(OBSERVATIONS_FILE, obs)


def flag_status_md(message: str) -> None:
    try:
        STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
        with open(STATUS_MD, "a", encoding="utf-8") as fh:
            fh.write(f"\n### BROKEN: chart-hygiene {stamp}\n- {message}\n")
    except OSError:
        pass


def _append_log(date_str: str, rows: list[dict]) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{date_str}.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


# --------------------------------------------------------------------------
# chart reads (CDP) -- thin wrappers, no policy here
# --------------------------------------------------------------------------

def _get_points(chart: TvChart, entity_id: str) -> list[dict] | None:
    """Same getPoints() read `j_drawn_lines_capture.py` uses -- read-only, no create/remove."""
    js = (
        "(function(){try{var s=%s.getShapeById(%s);var p=s.getPoints();"
        "if(!p) return null;"
        "return p.map(function(pt){return {time: pt.time, price: pt.price};});"
        "}catch(e){return null;}})()" % (CHART_API, json.dumps(entity_id))
    )
    return chart.evaluate(js)


def _all_shapes_with_detail(chart: TvChart) -> list[dict]:
    out = []
    for s in chart.list_shapes():
        sid = s.get("id")
        if not sid:
            continue
        text = chart.shape_text(sid) or ""
        points = _get_points(chart, sid)
        out.append({"id": sid, "name": s.get("name"), "text": text, "points": points})
    return out


# --------------------------------------------------------------------------
# B1 -- J-shape registry capture
# --------------------------------------------------------------------------

def capture_registry(chart: TvChart, now: dt.datetime | None = None) -> dict:
    """Snapshot every non-engine-tagged shape currently on the chart into the permanent
    J-registry. Idempotent: an id already in the registry is never re-timestamped
    (first_seen frozen), mirroring `j_drawn_lines_capture.build_ledger_rows` semantics.
    """
    now = now or et_now()
    today = now.date().isoformat()
    registry = load_registry()
    registry.setdefault("schema_version", 1)
    shapes_reg = registry.setdefault("shapes", {})

    detailed = _all_shapes_with_detail(chart)
    n_engine_tagged = 0
    n_already_registered = 0
    n_newly_registered = 0

    for shape in detailed:
        sid = shape["id"]
        if is_engine_tagged(shape["text"]):
            n_engine_tagged += 1
            continue
        if sid in shapes_reg:
            n_already_registered += 1
            continue
        shapes_reg[sid] = {
            "id": sid,
            "name": shape["name"],
            "text": shape["text"],
            "points": shape["points"],
            "first_seen_et": now.isoformat(),
            "first_seen_date_et": today,
        }
        n_newly_registered += 1

    save_registry(registry)
    return {
        "shapes_on_chart": len(detailed),
        "engine_tagged_skipped": n_engine_tagged,
        "already_registered": n_already_registered,
        "newly_registered": n_newly_registered,
        "registry_size": len(shapes_reg),
    }


# --------------------------------------------------------------------------
# B2 -- hygiene sweep
# --------------------------------------------------------------------------

def run_sweep(
    chart: TvChart,
    apply: bool,
    band_dollars: float | None = None,
    now: dt.datetime | None = None,
) -> tuple[dict, list[dict]]:
    """One sweep pass: classify every shape, log every decision, remove only if `apply`.

    Returns (summary_dict, log_rows). Never calls draw_clear/removeAllShapes -- removal
    is always TvChart.remove_entity(id), one id at a time, and only for ids classified
    "remove" (which by construction excludes every registry id).
    """
    band_dollars = dkl.DEFAULT_BAND_DOLLARS if band_dollars is None else band_dollars
    now = now or et_now()
    today = now.date().isoformat()

    registry = load_registry()
    registry_ids = set((registry.get("shapes") or {}).keys())
    obs = load_observations()
    obs_shapes = obs.setdefault("shapes", {})

    spot = chart.last_price()
    detailed = _all_shapes_with_detail(chart)

    log_rows: list[dict] = []
    remove_ids: list[str] = []
    seen_ids_today: set[str] = set()

    for shape in detailed:
        sid = shape["id"]
        seen_ids_today.add(sid)
        prior_dates = list((obs_shapes.get(sid) or {}).get("sessions_seen") or [])
        decision = classify_shape(shape, spot, band_dollars, registry_ids, prior_dates, today)
        would_remove = decision["action"] == "remove"
        logged_action = "would_remove" if (would_remove and not apply) else decision["action"]
        log_rows.append(
            {
                "ts_et": now.isoformat(),
                "date_et": today,
                "id": sid,
                "name": shape["name"],
                "text": shape["text"],
                "reason": decision["reason"],
                "action": logged_action,
            }
        )
        if would_remove:
            remove_ids.append(sid)

    # Append-only observation bookkeeping for untagged/non-registry shapes so a later
    # sweep can tell "this is at least its 3rd distinct day on the chart". Registered
    # ids never need this (they are permanent regardless of age).
    for sid in seen_ids_today:
        if sid in registry_ids:
            continue
        entry = obs_shapes.setdefault(sid, {"sessions_seen": []})
        if today not in entry["sessions_seen"]:
            entry["sessions_seen"].append(today)
    save_observations(obs)

    removed: list[str] = []
    if apply:
        for sid in remove_ids:
            try:
                if chart.remove_entity(sid):
                    removed.append(sid)
            except TvCdpError:
                continue

    log_path = _append_log(today, log_rows)

    summary = {
        "schema_version": 1,
        "ts_et": now.isoformat(),
        "date_et": today,
        "dry_run": not apply,
        "band_dollars": band_dollars,
        "spot": spot,
        "shapes_seen": len(detailed),
        "registry_size": len(registry_ids),
        "remove_candidates": len(remove_ids),
        "removed": len(removed),
        "log_path": str(log_path),
    }
    return summary, log_rows


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chart hygiene sweep + J-shape registry (WS-B)")
    ap.add_argument("--capture-registry", action="store_true",
                     help="one-time/rare bootstrap: freeze every non-engine-tagged shape as J's")
    ap.add_argument("--apply", action="store_true",
                     help="actually remove sweep candidates (default is dry-run / log-only)")
    ap.add_argument("--band", type=float, default=dkl.DEFAULT_BAND_DOLLARS,
                     help=f"active draw band in dollars (default {dkl.DEFAULT_BAND_DOLLARS})")
    args = ap.parse_args(argv)

    try:
        with TvChart() as chart:
            chart.require_chart_api()

            if args.capture_registry:
                result = capture_registry(chart)
                print(
                    "REGISTRY shapes_on_chart=%d engine_tagged_skipped=%d "
                    "already_registered=%d newly_registered=%d registry_size=%d"
                    % (
                        result["shapes_on_chart"],
                        result["engine_tagged_skipped"],
                        result["already_registered"],
                        result["newly_registered"],
                        result["registry_size"],
                    )
                )
                return 0

            summary, log_rows = run_sweep(chart, apply=args.apply, band_dollars=args.band)
            print(
                "%s shapes_seen=%d registry_size=%d remove_candidates=%d removed=%d log=%s"
                % (
                    "DRY_RUN" if summary["dry_run"] else "OK",
                    summary["shapes_seen"],
                    summary["registry_size"],
                    summary["remove_candidates"],
                    summary["removed"],
                    summary["log_path"],
                )
            )
            for row in log_rows:
                if row["action"] in ("remove", "would_remove"):
                    print(f"   {row['action']:>12}  {row['reason']:<32}  {row['id']}  {row['text'][:44]!r}")
            return 0

    except TvCdpError as exc:
        msg = str(exc)
        print(f"SKIP (TradingView/CDP unavailable): {msg}")
        return 0
    except Exception as exc:  # noqa: BLE001 - unexpected: must be loud, never silent
        msg = f"{type(exc).__name__}: {exc}"
        print(f"ERROR {msg}")
        flag_status_md(f"chart_hygiene failed -- {msg}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
