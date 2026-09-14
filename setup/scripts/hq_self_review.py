"""hq_self_review.py -- Gamma looks at its own HQ (GOAL-GAMMA-STATION-2026-09-13,
2026-09-14 coordinator-directed build C9/C10, CREW-RIG).

THE GAP THIS CLOSES: J -- "Gamma should be opening this up and seeing what I'm seeing."
The /hq three.js space station (dashboard/) renders a live company world for J to watch,
but nothing on Gamma's own side ever consumes that SAME payload -- Gamma has no idea
whether the world a human sees is healthy, stale, or a ghost town. This module closes
that loop: it fetches the exact JSON the dashboard's /hq page renders from
(`GET http://127.0.0.1:3000/api/hq`, loopback only), grades it deterministically (no
LLM), and writes `automation/state/station/hq-review.json` every Station fire.

C9 -- deterministic grading:
  - Every persona in the payload's `company.personas[]` is bucketed live/stale/ghost from
    its own `quietReason` (the dashboard's own "no producer for " prefix convention IS a
    ghost signal, see lib/personas.ts's own docstring), `status` (GREEN/YELLOW/RED/IDLE --
    already cadence-aware server-side, see dashboard/lib/personas.ts), and
    `deliverable.{exists,ageMin}`. A persona with a genuine crew-events.jsonl row in the
    last 2h is promoted to 'live' even if momentarily YELLOW/RED by cadence alone --
    real recent activity is stronger evidence than an aging-clock heuristic.
  - `desks` (dashboard/lib/desk-content.ts's own per-persona `.stale` flag, already
    cadence-aware) folds into `desks_stale`.
  - `trading` (the trading-status strip) folds into the score as a presence check.
  - `score_0_100` = 100 * crew_live/crew_total, minus 10/ghost, minus 5/stale-desk, minus
    10 if the trading strip is absent -- clamped [0, 100]. Deliberately simple and stated
    inline (`_score`), not a hidden formula.
  - Writes `automation/state/station/hq-review.json` and appends ONE Coach `hq_review`
    crew-event row, but ONLY when `score_0_100` or the stale-name-set changed since the
    last review -- the same "don't spam a re-computed non-change" discipline
    station_loop.py's Chef-verdict ticker already needed (see that module's own
    docstring on hypothesis_scorer re-writing an unchanged verdict every fire).
  - Optional real-screen capture: gated on presence.json saying J is absent, outside RTH,
    and at most CAPTURE_MAX_PER_DAY/day -- runs `hq_capture.ps1` (CREATE_NO_WINDOW, ~40s)
    and records the nonblack-sample count. NEVER while J is present -- see that script's
    own header.

C10 -- optional vision note (qwen2.5vl:7b, local Ollama, $0): only when a capture was
  actually taken THIS fire, AND the same yield gates the Station's own LLM step uses
  (station mode not gaming/off, GPU util <= 50%). Downscales the capture to 1280px wide
  JPEG via Pillow (skips with no note if Pillow isn't importable -- NEVER sends the raw
  ~2MB PNG). Request shape copied verbatim from the coordinator's own verified smoke
  test (POST /api/generate, temperature 0.2, num_predict 400, keep_alive "2m"). Writes
  `vision_notes` onto hq-review.json and appends ONE Gamma `hq_look` crew-event row, but
  ONLY when the first (most important) problem line changed from the previous look.
  NEVER writes an ideas-board card from this -- it is a note, not a hypothesis (the
  coordinator's own smoke test found the model's output too generic to be evidence).

SYNTHETIC-CLOCK GUARD: mirrors station_loop._write_sectors_and_crew_events's own guard
(added 2026-09-14 after a real leak from a sibling test file) -- a caller whose now_utc
is far from actual wall-clock time, writing to the real REPO-derived path, skips
entirely rather than corrupting live state. Defense in depth on top of proper test
isolation (station_loop.py's own tests stub this whole module's review_once()).

Never touches the trading path. Never writes an ideas-board card. Fail-open throughout:
one bad sub-step (a down dashboard, a missing Pillow, an unreachable Ollama) degrades
only that piece, never crashes the caller.

Usage: python setup/scripts/hq_self_review.py [--once]
"""
from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from et_clock import et_now, et_offset_hours, is_market_hours  # noqa: E402
import station_board  # noqa: E402
import crew_events  # noqa: E402

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

STATION_DIR = REPO / "automation" / "state" / "station"
REVIEW_PATH = STATION_DIR / "hq-review.json"
CREW_EVENTS_PATH = STATION_DIR / "crew-events.jsonl"
PRESENCE_PATH = STATION_DIR / "presence.json"
MODE_PATH = STATION_DIR / "mode.json"
CAPTURES_DIR = STATION_DIR / "captures"
CAPTURE_LOG_PATH = STATION_DIR / "hq-capture-log.jsonl"

HQ_URL = "http://127.0.0.1:3000/api/hq"
HQ_FETCH_TIMEOUT_S = 5.0
CAPTURE_MAX_PER_DAY = 4
CAPTURE_SUBPROCESS_TIMEOUT_S = 90  # hq_capture.ps1 itself runs ~40s (35s settle + Edge start/kill)

OLLAMA_BASE_URL = "http://localhost:11434"
VISION_MODEL = "qwen2.5vl:7b"
VISION_TIMEOUT_S = 60
GPU_BUSY_PCT = 50.0

# Copied VERBATIM from the coordinator's own verified smoke test (vision_smoke.py) --
# same prompt, same request shape, same options. Do not invent a different prompt here.
VISION_PROMPT = (
    "You are Gamma, reviewing a screenshot of your own 3D company headquarters (a game-like office world "
    "with employees at desks, a hub in the middle, a HUD on the right and a ticker at the bottom). The owner "
    "is demanding and wants it to look like a finished, connected building where people visibly work. "
    "List the 6 most important VISUAL problems you see, most important first, one line each, concrete and "
    "specific to what is in the image (lighting, exposure, composition, readability, clutter, empty areas, "
    "broken geometry). Then one line: what looks good. No preamble."
)

_NONBLACK_RE = re.compile(r"nonblack=(\d+)/(\d+)")


# --------------------------------------------------------------------------- #
# HQ payload fetch
# --------------------------------------------------------------------------- #

def _fetch_hq_payload(url: str = HQ_URL, timeout: float = HQ_FETCH_TIMEOUT_S) -> "tuple[Optional[dict], Optional[str]]":
    """(payload, error). error is None iff payload is a usable dict. Never raises --
    a down/unreachable dashboard is the expected common case when nobody has `npm run
    dev` running, not a bug in this module."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- loopback only
            status = getattr(resp, "status", 200)
            if not (200 <= status < 300):
                return None, f"http {status}"
            data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, dict):
                return None, "non-object response"
            return data, None
    except Exception as exc:  # noqa: BLE001 -- fail-open: unreachable dashboard is a normal case
        return None, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Timestamp helper (same convention/trick as station_loop._parse_et_stamp --
# duplicated locally, not imported, to keep this module import-independent of
# station_loop.py: station_loop.py imports THIS module, so the reverse import
# would be circular)
# --------------------------------------------------------------------------- #

def _parse_et_stamp(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        naive_et = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S ET")
    except ValueError:
        return None
    offset = et_offset_hours(naive_et.replace(tzinfo=timezone.utc))
    return (naive_et - timedelta(hours=offset)).replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# C9 -- deterministic grading (pure function, no I/O -- testable with a fake payload)
# --------------------------------------------------------------------------- #

def _recent_who(crew_rows: list, now_utc: datetime, window: timedelta) -> set:
    out: set = set()
    for r in crew_rows:
        if not isinstance(r, dict):
            continue
        dt = _parse_et_stamp(r.get("ts_et"))
        if dt is not None and timedelta(0) <= (now_utc - dt) <= window:
            who = r.get("who")
            if who:
                out.add(who)
    return out


_EXPECTED_TIME_RE = re.compile(r"\bexpected\s+(?:\w+\s+)?(\d{1,2}):(\d{2})\s*ET\b", re.I)
_STALE_TEXT_RE = re.compile(r"\boverdue\b|\bexpected\b.*\blast\b", re.I | re.S)


def _classify_persona(p: dict, recent_who: set, now_utc: datetime) -> "tuple[str, str, Optional[float]]":
    """Returns (bucket, why, age_min). bucket in {'live', 'stale', 'ghost'}.

    2026-09-14 coordinator correction: DERIVE from the dashboard's own `quietReason`
    text instead of re-deriving from `status`/`deliverable.exists` independently --
    those two re-derivations were WRONG twice over on real live data: Gamma (Manager)
    read status=YELLOW with quietReason 'yields — rth_window (...)' and got called
    'stale' for deliberately yielding by design; Analyst read deliverable.exists=False
    (analysis/eod/2026-09-14.md genuinely doesn't exist until its own 16:45 ET fire
    writes it) and got called a 'ghost' at noon, when its real quietReason already says
    'expected 16:45 ET weekdays via Gamma_AnalystEodReview, last digest 16:45 ET on a
    prior day' -- i.e. the dashboard already knows it isn't due yet.

    Prefix/pattern rule (matches dashboard/lib/personas.ts's own documented pill-
    derivation convention on PersonaState.quietReason: 'no producer for ' -> GHOST,
    'yields ' -> YIELDING (never a penalty), anything else -> WAITING):
      - 'no producer for ...'                         -> ghost
      - 'yields ...'                                   -> live (by design, no penalty)
      - 'expected HH:MM ET ... weekdays/Sun ...'        -> live BEFORE that time today,
                                                           stale AFTER it (a once-daily
                                                           persona's own due time, read
                                                           straight out of its own text --
                                                           no separate roster-cadence
                                                           lookup needed)
      - 'overdue ...' or another 'expected ... last ...' shape (Coach's continuous-
        cadence staleness message, e.g. 'expected every 30 min ..., last evidence
        HH:MM ET') -> stale directly, no due-time gate (a repeating cadence has no
        single 'not due yet' grace window)
      - anything else (a 'Gamma_X DISABLED' note, an '<X> is RED' note, or no
        quietReason at all) -> live -- a dashboard-explained footnote is not
        automatically a ghost or a stale, per the SAME WAITING-bucket philosophy.

    A persona with a genuine crew-events.jsonl row in the last 2h is promoted to
    'live' before any of the above -- real recent activity is stronger evidence than
    any text-derived heuristic."""
    if p.get("name") in recent_who:
        return "live", p.get("quietReason") or "recent crew-events activity", (p.get("deliverable") or {}).get("ageMin")

    deliverable = p.get("deliverable") or {}
    age_min = deliverable.get("ageMin") if isinstance(deliverable, dict) else None
    quiet = p.get("quietReason")
    if not isinstance(quiet, str) or not quiet.strip():
        return "live", "status ok", age_min
    q = quiet.strip()

    if q.startswith("no producer for"):
        return "ghost", q, age_min
    if q.startswith("yields "):
        return "live", q, age_min

    m = _EXPECTED_TIME_RE.search(q)
    if m:
        due_h, due_m = int(m.group(1)), int(m.group(2))
        now_et = et_now(now_utc=now_utc)
        if (now_et.hour, now_et.minute) < (due_h, due_m):
            return "live", q, age_min
        return "stale", q, age_min

    if _STALE_TEXT_RE.search(q):
        return "stale", q, age_min

    return "live", q, age_min


def _desks_stale_list(desks: Any) -> list:
    if not isinstance(desks, dict):
        return []
    return sorted(name for name, d in desks.items() if isinstance(d, dict) and d.get("stale") is True)


def _score(crew_live: int, crew_total: int, ghosts: list, desks_stale: list, trading_present: bool) -> int:
    """Deterministic, stated inline (not hidden): base = % of crew live, minus 10 per
    ghost, minus 5 per stale desk, minus 10 if the trading strip is absent. Clamped."""
    if crew_total <= 0:
        return 0
    base = 100.0 * crew_live / crew_total
    base -= 10 * len(ghosts)
    base -= 5 * len(desks_stale)
    if not trading_present:
        base -= 10
    return max(0, min(100, round(base)))


def grade_hq(payload: dict, crew_rows: list, now_utc: datetime) -> dict:
    """Pure grading function: no I/O, no network, deterministic, never raises. `payload`
    is an already-fetched /api/hq JSON body (or a fake one in tests); `crew_rows` is
    crew-events.jsonl's already-read rows. A malformed payload degrades to an honest
    all-zero review rather than crashing the caller."""
    try:
        company = payload.get("company") if isinstance(payload, dict) else None
        personas = (company or {}).get("personas") if isinstance(company, dict) else None
        personas = [p for p in personas if isinstance(p, dict)] if isinstance(personas, list) else []

        recent_who = _recent_who(crew_rows, now_utc, timedelta(hours=2))

        stale: list = []
        ghosts: list = []
        live_count = 0
        for p in personas:
            bucket, why, age_min = _classify_persona(p, recent_who, now_utc)
            name = p.get("name", "?")
            if bucket == "live":
                live_count += 1
            elif bucket == "stale":
                stale.append({"name": name, "age_min": age_min, "why": why})
            else:
                ghosts.append({"name": name, "why": why})

        desks = payload.get("desks") if isinstance(payload, dict) else None
        desks_stale = _desks_stale_list(desks)
        desks_total = len(desks) if isinstance(desks, dict) else 0
        trading_present = bool(payload.get("trading")) if isinstance(payload, dict) else False

        crew_total = len(personas)
        score = _score(live_count, crew_total, ghosts, desks_stale, trading_present)

        lines = [f"{live_count}/{crew_total} crew live"]
        if ghosts:
            lines.append("ghosts: " + ", ".join(g["name"] for g in ghosts))
        if stale:
            lines.append("stale: " + ", ".join(f"{s['name']} {_fmt_age(s['age_min'])}" for s in stale))
        if desks_total:
            lines.append(f"desks fresh {desks_total - len(desks_stale)}/{desks_total}")
        if not trading_present:
            lines.append("trading strip missing from /api/hq")

        return {"crew_live": live_count, "crew_total": crew_total, "stale": stale,
                "ghosts": ghosts, "desks_stale": desks_stale, "score_0_100": score,
                "lines": lines, "_desks_total": desks_total, "_trading_present": trading_present}
    except Exception as exc:  # noqa: BLE001 -- a grading bug must never crash the fire
        return {"crew_live": 0, "crew_total": 0, "stale": [], "ghosts": [], "desks_stale": [],
                "score_0_100": 0, "lines": [f"grade_hq raised {type(exc).__name__}: {exc}"],
                "_desks_total": 0, "_trading_present": False}


def _fmt_age(age_min) -> str:
    if age_min is None:
        return "?"
    try:
        age_min = float(age_min)
    except (TypeError, ValueError):
        return "?"
    return f"{age_min:.0f}m" if age_min < 60 else f"{age_min / 60:.0f}h"


def _ticker_line(review: dict) -> str:
    parts = [f"{review.get('crew_live', 0)}/{review.get('crew_total', 0)} crew live"]
    if review.get("stale"):
        parts.append("stale: " + ", ".join(f"{s['name']} {_fmt_age(s.get('age_min'))}" for s in review["stale"][:4]))
    if review.get("ghosts"):
        parts.append("ghosts: " + ", ".join(g["name"] for g in review["ghosts"][:4]))
    desks_total = review.get("_desks_total", 0)
    if desks_total:
        parts.append(f"desks fresh {desks_total - len(review.get('desks_stale', []))}/{desks_total}")
    return "Coach: HQ review — " + " · ".join(parts)


# --------------------------------------------------------------------------- #
# Optional real-screen capture (C9)
# --------------------------------------------------------------------------- #

def _captures_today(now_utc: datetime) -> int:
    today = et_now(now_utc=now_utc).strftime("%Y-%m-%d")
    rows = station_board.read_jsonl(CAPTURE_LOG_PATH)
    return sum(1 for r in rows if r.get("date") == today)


def should_capture(now_utc: datetime) -> "tuple[bool, str]":
    """(eligible, reason). Fails CLOSED (never captures) on any read error -- 'never
    while J is present' is a hard safety rule, so an unreadable presence.json must be
    treated as 'presence unknown, assume present', never as license to capture."""
    try:
        presence = station_board.read_json_or_none(PRESENCE_PATH)
        present = bool(presence.get("present", True)) if isinstance(presence, dict) else True
    except Exception:  # noqa: BLE001
        present = True
    if present:
        return False, "J present"
    if is_market_hours(now_utc=now_utc):
        return False, "RTH"
    n_today = _captures_today(now_utc)
    if n_today >= CAPTURE_MAX_PER_DAY:
        return False, f"daily cap reached ({n_today}/{CAPTURE_MAX_PER_DAY})"
    return True, "eligible"


def _run_capture(now_utc: datetime) -> Optional[dict]:
    """Runs hq_capture.ps1 for real (CREATE_NO_WINDOW), logs one row to
    hq-capture-log.jsonl (the daily-cap ledger), and returns {ts_et, date, path,
    nonblack, samples, returncode} -- or None if the capture PNG never landed."""
    ts_et = et_now(now_utc=now_utc).strftime("%Y-%m-%d %H:%M:%S ET")
    date = et_now(now_utc=now_utc).strftime("%Y-%m-%d")
    stamp = et_now(now_utc=now_utc).strftime("%Y%m%d-%H%M%S")
    out_path = CAPTURES_DIR / f"hq-review-{stamp}.png"
    ps1 = REPO / "setup" / "scripts" / "hq_capture.ps1"
    row: dict = {"ts_et": ts_et, "date": date, "path": str(out_path),
                "nonblack": None, "samples": None, "returncode": None}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), "-Out", str(out_path)],
            capture_output=True, text=True, timeout=CAPTURE_SUBPROCESS_TIMEOUT_S, creationflags=_CREATE_NO_WINDOW,
        )
        row["returncode"] = result.returncode
        m = _NONBLACK_RE.search(result.stdout or "")
        if m:
            row["nonblack"], row["samples"] = int(m.group(1)), int(m.group(2))
    except Exception as exc:  # noqa: BLE001 -- a failed capture is a logged row, never a crash
        row["error"] = f"{type(exc).__name__}: {exc}"
    try:
        station_board.append_jsonl(CAPTURE_LOG_PATH, [row])
    except Exception:  # noqa: BLE001
        pass
    return row if out_path.exists() else None


# --------------------------------------------------------------------------- #
# C10 -- optional vision note
# --------------------------------------------------------------------------- #

def _gpu_util_pct() -> Optional[float]:
    """Duplicated from station_loop._gpu_util_pct (not imported -- station_loop.py
    imports THIS module, so the reverse import would be circular). Fails open (None
    never blocks the vision look -- this is a courtesy GPU-contention check, not a
    safety gate)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=_CREATE_NO_WINDOW,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return float(out.stdout.strip().splitlines()[0].strip())
    except Exception:  # noqa: BLE001
        return None


def should_vision_look(capture_taken: bool, config: Optional[dict] = None) -> "tuple[bool, str]":
    """(eligible, reason). Only runs when a capture was ACTUALLY taken this fire, and
    the same yield gates the Station's own LLM step uses (station mode, GPU util)."""
    if not capture_taken:
        return False, "no capture this fire"
    try:
        mode_doc = station_board.read_json_or_none(MODE_PATH)
        mode = str(mode_doc.get("mode", "work")) if isinstance(mode_doc, dict) else "work"
    except Exception:  # noqa: BLE001
        mode = "work"
    if mode in ("gaming", "off"):
        return False, f"station_mode:{mode}"
    threshold = (config or {}).get("gpu_util_yield_pct", GPU_BUSY_PCT)
    util = _gpu_util_pct()
    if util is not None and util > threshold:
        return False, f"gpu_util {util:.0f}% > {threshold:.0f}%"
    return True, "eligible"


def _resize_for_vision(image_path: Path) -> Optional[bytes]:
    """JPEG bytes downscaled to 1280px wide (matches the coordinator's verified smoke
    test exactly). None if Pillow isn't importable or the image can't be read -- the
    caller MUST treat None as 'skip', never fall back to the raw PNG (C10 rule 2)."""
    try:
        from PIL import Image  # noqa: PLC0415 -- optional dependency, checked at call time
    except ImportError:
        return None
    try:
        im = Image.open(image_path).convert("RGB")
        w, h = im.size
        if w > 1280:
            im = im.resize((1280, int(h * 1280 / w)))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _call_vision_model(image_bytes: bytes, *, model: str = VISION_MODEL,
                       base_url: str = OLLAMA_BASE_URL, timeout: float = VISION_TIMEOUT_S) -> dict:
    """Request shape copied verbatim from the coordinator's verified smoke test."""
    payload = {
        "model": model, "prompt": VISION_PROMPT,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False, "options": {"temperature": 0.2, "num_predict": 400}, "keep_alive": "2m",
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- localhost only
        return json.loads(resp.read().decode("utf-8"))


def _vision_look(image_path: Path, ts_et: str, *,
                 resize_fn: Optional[Callable[[Path], Optional[bytes]]] = None,
                 call_fn: Optional[Callable[[bytes], dict]] = None) -> Optional[dict]:
    """Returns {ts_et, model, capture, lines} or None (PIL missing/image unreadable/
    model call failed/empty response -- every case a silent skip, per C10 rule 5)."""
    resize_fn = resize_fn or _resize_for_vision
    call_fn = call_fn or _call_vision_model
    try:
        image_bytes = resize_fn(image_path)
        if image_bytes is None:
            return None
        raw = call_fn(image_bytes)
        text = str((raw or {}).get("response") or "").strip()
        lines = [ln.strip(" -*•") for ln in text.splitlines() if ln.strip()]
        if not lines:
            return None
        return {"ts_et": ts_et, "model": VISION_MODEL, "capture": str(image_path), "lines": lines}
    except Exception:  # noqa: BLE001 -- fail-open, per C10 rule 5
        return None


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def review_once(ts_et: str, now_utc: datetime, config: Optional[dict] = None, *,
                hq_url: str = HQ_URL, hq_timeout: float = HQ_FETCH_TIMEOUT_S,
                fetch_fn: Optional[Callable] = None,
                capture_fn: Optional[Callable] = None,
                vision_fn: Optional[Callable] = None) -> dict:
    """The one entry point station_loop.py calls every fire. Writes hq-review.json,
    appends the Coach/Gamma crew-event rows on a real change, and returns the review
    dict written (or a {'skipped': ...} dict when the synthetic-clock guard fires)."""
    # Synthetic-clock guard -- mirrors station_loop._write_sectors_and_crew_events's own
    # (added 2026-09-14 after a real leak). See that function's docstring for the class
    # of bug this closes.
    try:
        real_review_path = REPO / "automation" / "state" / "station" / "hq-review.json"
        clock_drift_s = abs((datetime.now(timezone.utc) - now_utc).total_seconds())
        if clock_drift_s > 900 and REVIEW_PATH == real_review_path:
            return {"skipped": "synthetic clock + real path"}
    except Exception:  # noqa: BLE001
        pass

    fetch_fn = fetch_fn or _fetch_hq_payload
    payload, fetch_err = fetch_fn(hq_url, hq_timeout)
    crew_rows = station_board.read_jsonl(CREW_EVENTS_PATH)

    if payload is None:
        review = {"crew_live": 0, "crew_total": 0, "stale": [], "ghosts": [], "desks_stale": [],
                  "score_0_100": 0, "lines": [f"HQ review: dashboard unreachable ({fetch_err})"],
                  "_desks_total": 0, "_trading_present": False}
    else:
        review = grade_hq(payload, crew_rows, now_utc)

    old_doc = station_board.read_json_or_none(REVIEW_PATH)
    old_doc = old_doc if isinstance(old_doc, dict) else {}

    # ---- C9: optional real-screen capture ----
    capture_info: Optional[dict] = None
    capture_taken = False
    try:
        eligible, _reason = should_capture(now_utc)
        if eligible:
            capture_info = (capture_fn or _run_capture)(now_utc)
            capture_taken = bool(capture_info)
    except Exception:  # noqa: BLE001
        capture_info = None

    # ---- C10: optional vision look ----
    vision_notes: list = []
    try:
        eligible, _reason = should_vision_look(capture_taken, config)
        if eligible and capture_info and capture_info.get("path"):
            note = (vision_fn or _vision_look)(Path(capture_info["path"]), ts_et)
            if note:
                vision_notes = [note]
    except Exception:  # noqa: BLE001
        vision_notes = []

    public_review = {k: v for k, v in review.items() if not k.startswith("_")}
    doc = {"ts_et": ts_et, **public_review, "capture": capture_info}
    if vision_notes:
        doc["vision_notes"] = vision_notes

    try:
        station_board.atomic_write_text(REVIEW_PATH, json.dumps(doc, indent=2, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass

    # ---- Coach ticker: only on a real change (score or the stale-name-set) ----
    try:
        old_stale_names = {s.get("name") for s in (old_doc.get("stale") or []) if isinstance(s, dict)}
        new_stale_names = {s.get("name") for s in review.get("stale", []) if isinstance(s, dict)}
        changed = old_doc.get("score_0_100") != review.get("score_0_100") or old_stale_names != new_stale_names
        if changed:
            crew_events.append({"ts_et": ts_et, "who": "Coach", "kind": "hq_review", "to": "Gamma",
                                "line": _ticker_line(review), "ref": "automation/state/station/hq-review.json"},
                               path=CREW_EVENTS_PATH)
    except Exception:  # noqa: BLE001
        pass

    # ---- Gamma ticker: only when the vision look's first line changed ----
    try:
        if vision_notes:
            new_first = (vision_notes[0].get("lines") or [""])[0]
            old_vn = old_doc.get("vision_notes") or []
            old_first = ((old_vn[-1] or {}).get("lines") or [""])[0] if old_vn else None
            if new_first and new_first != old_first:
                crew_events.append({"ts_et": ts_et, "who": "Gamma", "kind": "hq_look",
                                    "line": f"Gamma looked at HQ: {new_first[:90]}",
                                    "ref": vision_notes[0].get("capture")}, path=CREW_EVENTS_PATH)
    except Exception:  # noqa: BLE001
        pass

    return doc


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Gamma's HQ self-review -- deterministic grade + optional vision note.")
    ap.add_argument("--once", action="store_true", help="run a single review (the only mode)")
    ap.parse_args(argv or [])
    now_utc = datetime.now(timezone.utc)
    ts_et = et_now(now_utc=now_utc).strftime("%Y-%m-%d %H:%M:%S ET")
    row = review_once(ts_et, now_utc)
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
