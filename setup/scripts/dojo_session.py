"""dojo_session.py -- THE one-command dojo session harness (WS10, built 2026-08-01).

J sits down, one command starts everything; one command per call; one command closes the
books. Wraps the existing dojo package (setup/scripts/dojo/ -- session spine, engine_step,
sim_executor, scorecard) -- REUSES it, never re-implements scoring/filling/exits.

    python dojo_session.py --start                  # picks an unreviewed day, opens session
    python dojo_session.py --start --day 2026-07-17 # explicit day (still logged)
    python dojo_session.py --step --cursor <epoch>  # per-bar passthrough to dojo.session
    python dojo_session.py --call "long 737.7 stop under 737.2 wick reject at PDH"
    python dojo_session.py --finish                 # counterfactual + OPRA card + harvest
    python dojo_session.py --fake                   # end-to-end smoke, no TV, no J
    python dojo_session.py --show-status            # where am I

DAY PICKER (seeded, no repeats): population = trading days with >= MIN_RTH_ROWS_PER_DAY
RTH bars in the CANONICAL spy_5m two-file lineage (filter5_ribbon_fate's
load_extended_data rule: full-history file + strictly-later tail of the newest file),
restricted HARD to [2025-01-02, 2026-07-31]. Measured 2026-08-01: 393 replayable days =
394 raw lineage days minus the broken 2026-06-15 session (12 RTH bars). The "391"
figure quoted by studies additionally excludes short sessions -- per
build_day_archetypes.py's convention, JOIN ON DATE, NOT ORDINAL; every pick row carries
population_n + sha1 so any drift is auditable. The 2024 backfill range is excluded
until analysis/deep-research/OPRA-BACKFILL-2026-07-31.md exists and declares
completion. Days J already reviewed (sessions.jsonl real rows + legacy
sessions/*.state.json) are excluded. Pick is random.Random(f"{BASE_SEED}:{pick_index}")
over the sorted eligible list -- fully reproducible from the log. FAKE-mode sessions
never consume a day from J's population.

TV DRIVE: the deterministic script does NOT speak CDP -- the session agent is THE HANDS
(DOJO-ARCHITECTURE-DECISION.md split). --start emits the exact MCP calls
(replay_start/step/status/stop -- ALL FOUR empirically verified working 2026-08-01
against live TV desktop: replay_start(date=2026-07-17) -> cursor 2026-07-16T19:59:59 ET,
each replay_step advances exactly one 5-min chart bar, replay_status carries
current_date as epoch seconds). J alone can equally click TV's own replay UI; the
capture CLI works either way.

WHAT --finish PRODUCES:
  1. Engine counterfactual for the replay day: every RTH 5-min bar close not already
     stepped in the session ledger is run through dojo.engine_step.step (the REAL live
     decision path -- heartbeat_core._build_payload + _engine_verdict + the real fleet
     pass). Ledger rows are REUSED, never recomputed.
  2. J's captured calls and the engine's would-place entries are BOTH valued on real
     OPRA 5-min data via dojo.sim_executor (fill at bar-at-or-after the call bar,
     entry+1 exit walk through the REAL exit_manager core -- the canonical convention
     per markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md). BS-synthetic
     fallback rows are FLAGGED and EXCLUDED from headline totals (disclosed, never
     silently pooled).
  3. A comparison card (<session>-comparison.md/.json): J's calls vs engine decisions
     vs what real OPRA paid for each, plus divergences.
  4. Harvest append: LANE A / LANE B candidate items appended to the session harvest doc
     (two-lane split per DOJO-REPLAY-TRAINING-SPEC.md). This script NEVER writes
     queue.md or analysis/recommendations/ itself -- lane routing to those surfaces is
     the human/agent step documented in the runbook (queue.md's per-line parser is a
     known-fragile shared surface, L245/L246).

DISCLOSED APPROXIMATIONS (inherited, not introduced): engine_step reconstructs levels
from the CURRENT key-levels.json restricted to entries knowable as of the replay day --
level-tied triggers on old days are approximate (engine_step.py module docstring). The
comparison card carries this caveat verbatim.

HARD FENCE (same as the whole dojo package): every write goes through
dojo.session._assert_under_dojo -- nothing outside automation/state/dojo/ is ever
written; no broker import; no git operation. Guard: backtest/tests/
test_dojo_session_oneshot.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# --- path bootstrap (mirror dojo/session.py) ---
_HERE = Path(__file__).resolve().parent            # .../setup/scripts
_ROOT = _HERE.parents[1]                            # .../42
for _p in ("backtest", "setup/scripts", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import clock  # noqa: E402  (pure, cheap)
from dojo import session as spine  # noqa: E402  (cheap: stdlib + clock only)

ET = ZoneInfo("America/New_York")
DOJO_DIR = _ROOT / "automation" / "state" / "dojo"
SESSIONS_DIR = DOJO_DIR / "sessions"
SESSIONS_LOG = DOJO_DIR / "sessions.jsonl"          # the WS10 pick/review ledger
CURRENT_PTR = DOJO_DIR / "current-session.json"
DATA_DIR = _ROOT / "backtest" / "data"

POPULATION_START = date(2025, 1, 2)
POPULATION_END = date(2026, 7, 31)
BACKFILL_DECL = _ROOT / "analysis" / "deep-research" / "OPRA-BACKFILL-2026-07-31.md"
BASE_SEED = "GAMMA-DOJO-V1"
MIN_RTH_ROWS_PER_DAY = 30      # keeps half-days (~42 RTH bars), drops holiday stubs
DEFAULT_QTY = 3                # Rule 6 minimum (2 TP + 1 runner)
RTH_CLOSES_FIRST = dtime(9, 35)
RTH_CLOSES_LAST = dtime(16, 0)

# Engine arm name (DojoDecision.arm) -> sim_executor arm id (CORE_ARM_ALIASES / accounts.json)
ARM_TO_SIM_ID = {
    "safe": "safe", "bold": "bold",
    "fleet_safe_3": "safe-3", "fleet_risky_1": "risky-1", "fleet_risky_3": "risky-3",
}

_LONG_WORDS = ("long", "call", "calls", "bull", "bullish", "c")
_SHORT_WORDS = ("short", "put", "puts", "bear", "bearish", "p")


# --------------------------------------------------------------------------- tiny io
def _fenced_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    spine._assert_under_dojo(path).write_text(text, encoding="utf-8")
    return path


def _fenced_append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(spine._assert_under_dojo(path), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # one corrupt line never kills the harness (C7)
    return rows


def _now_et() -> datetime:
    return datetime.now(ET)


# --------------------------------------------------------------------------- population
def _rth_dates_in_csv(path: Path) -> set[date]:
    """Dates with >= MIN_RTH_ROWS_PER_DAY RTH rows in one spy_5m cache file. String-sliced
    (no datetime parse) -- timestamp_et starts 'YYYY-MM-DD HH:MM' or ISO with offset; the
    HH:MM at chars 11:16 is ET wall-clock in every cache format (see engine_step._tz_aware
    for the three formats; all carry ET wall-clock digits at that position)."""
    counts: dict[str, int] = {}
    with open(path, encoding="utf-8") as fh:
        header = fh.readline()
        cols = [c.strip() for c in header.split(",")]
        try:
            ts_idx = cols.index("timestamp_et")
        except ValueError:
            return set()
        for line in fh:
            parts = line.split(",", ts_idx + 1)
            if len(parts) <= ts_idx:
                continue
            ts = parts[ts_idx]
            if len(ts) < 16:
                continue
            hhmm = ts[11:16]
            if "09:30" <= hhmm <= "15:59":
                counts[ts[:10]] = counts.get(ts[:10], 0) + 1
    out: set[date] = set()
    for d_str, n in counts.items():
        if n < MIN_RTH_ROWS_PER_DAY:
            continue
        try:
            out.add(date.fromisoformat(d_str))
        except ValueError:
            continue
    return out


def _vix_covered(day: date) -> bool:
    """True iff at least one vix_5m cache file's filename RANGE covers `day` (exactly the
    check that keeps engine_step._load_vix_cache from raising FileNotFoundError)."""
    rx = re.compile(r"^vix_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")
    for p in DATA_DIR.glob("vix_5m_*.csv"):
        m = rx.match(p.name)
        if not m:
            continue
        if date.fromisoformat(m.group(1)) <= day <= date.fromisoformat(m.group(2)):
            return True
    return False


CANON_OLD_SPY = "spy_5m_2025-01-01_2026-07-22.csv"   # filter5's OLD_SPY, verbatim
CANON_TAIL_AFTER = date(2026, 7, 22)                  # filter5's OLD_WINDOW_END


def _newest_spy_file() -> Path | None:
    """Newest end-dated spy_5m_<start>_<end>.csv (the rolling lineage tail)."""
    rx = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")
    best: tuple[date, Path] | None = None
    for p in DATA_DIR.glob("spy_5m_*.csv"):
        m = rx.match(p.name)
        if not m:
            continue
        start = date.fromisoformat(m.group(1))
        if start < POPULATION_START:  # never let a 2024-lineage master become the tail
            if p.name != CANON_OLD_SPY and start.year <= 2024:
                continue
        end = date.fromisoformat(m.group(2))
        if best is None or end > best[0]:
            best = (end, p)
    return best[1] if best else None


def population_days() -> list[date]:
    """Sorted replayable trading days in [POPULATION_START, POPULATION_END], enumerated
    from the SAME two-file lineage filter5_ribbon_fate.load_extended_data() reads (old
    full-history file + strictly-later tail of the newest file), each day requiring
    >= MIN_RTH_ROWS_PER_DAY RTH bars (drops broken sessions like 2026-06-15's 12-bar tape;
    keeps 46-47-bar half days and the 66-69-bar thin-feed 2025 stratum) AND vix cache
    range coverage. The 2024 stratum stays excluded until the backfill completion doc
    exists (checked by the window bounds, not assumed)."""
    old = DATA_DIR / CANON_OLD_SPY
    days: set[date] = set()
    if old.exists():
        days |= _rth_dates_in_csv(old)
        newest = _newest_spy_file()
        if newest is not None and newest != old:
            days |= {d for d in _rth_dates_in_csv(newest) if d > CANON_TAIL_AFTER}
    else:  # disclosed fallback: union of every in-window cache file
        rx = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")
        for p in sorted(DATA_DIR.glob("spy_5m_*.csv")):
            m = rx.match(p.name)
            if not m:
                continue
            if date.fromisoformat(m.group(2)) < POPULATION_START:
                continue
            if date.fromisoformat(m.group(1)) > POPULATION_END:
                continue
            days |= _rth_dates_in_csv(p)
    days = {d for d in days
            if POPULATION_START <= d <= POPULATION_END and d.weekday() < 5 and _vix_covered(d)}
    return sorted(days)


def _population_sha1(days: list[date]) -> str:
    return hashlib.sha1(",".join(d.isoformat() for d in days).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- pick ledger
def _fake_session_ids(log_rows: list[dict]) -> set[str]:
    return {r.get("session_id") for r in log_rows if r.get("mode") == "fake" and r.get("session_id")}


def reviewed_days() -> set[date]:
    """Days J has already reviewed: real (non-fake) rows in sessions.jsonl UNION replay_day
    of every legacy sessions/*.state.json not created by a fake run."""
    log_rows = _read_jsonl(SESSIONS_LOG)
    fake_ids = _fake_session_ids(log_rows)
    out: set[date] = set()
    for r in log_rows:
        if r.get("mode") == "fake":
            continue
        day = r.get("replay_day")
        if day:
            try:
                out.add(date.fromisoformat(str(day)))
            except ValueError:
                continue
    for p in SESSIONS_DIR.glob("*.state.json"):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if st.get("session_id") in fake_ids:
            continue
        day = st.get("replay_day")
        if day:
            try:
                out.add(date.fromisoformat(str(day)))
            except ValueError:
                continue
    return out


def pick_day(explicit: str | None = None, mode: str = "real") -> dict:
    """Deterministic-under-the-log seeded pick. Returns the pick row (also appended to
    sessions.jsonl by cmd_start, not here -- caller owns the write so a failed session
    start never burns a day)."""
    pop = population_days()
    if not pop:
        raise RuntimeError("day-picker population is EMPTY -- spy_5m/vix_5m caches missing?")
    pop_sha = _population_sha1(pop)
    already = reviewed_days()
    log_rows = _read_jsonl(SESSIONS_LOG)
    pick_index = sum(1 for r in log_rows if r.get("event") == "pick")

    if explicit:
        day = date.fromisoformat(explicit)
        if not (POPULATION_START <= day <= POPULATION_END):
            raise ValueError(
                f"--day {explicit} is outside the verified population window "
                f"[{POPULATION_START}..{POPULATION_END}] (2024 stratum locked until "
                f"{BACKFILL_DECL.name} declares completion)")
        if day not in pop:
            raise ValueError(f"--day {explicit} has no RTH bars in the spy_5m cache "
                             f"(holiday/weekend/uncached day)")
        return {"event": "pick", "picked_et": _now_et().isoformat(), "mode": mode,
                "replay_day": day.isoformat(), "pick_index": pick_index, "seed": "explicit",
                "population_n": len(pop), "population_sha1": pop_sha,
                "re_review": day in already}

    eligible = [d for d in pop if d not in already]
    if not eligible:
        raise RuntimeError(f"every one of the {len(pop)} population days is already "
                           f"reviewed -- expand the population window or re-review "
                           f"explicitly with --day")
    seed = f"{BASE_SEED}:{pick_index}"
    day = random.Random(seed).choice(eligible)
    return {"event": "pick", "picked_et": _now_et().isoformat(), "mode": mode,
            "replay_day": day.isoformat(), "pick_index": pick_index, "seed": seed,
            "population_n": len(pop), "eligible_n": len(eligible),
            "population_sha1": pop_sha, "re_review": False}


# --------------------------------------------------------------------------- session ptr
def _write_current_ptr(session_id: str, replay_day: str, mode: str) -> None:
    _fenced_write_text(CURRENT_PTR, json.dumps(
        {"session_id": session_id, "replay_day": replay_day, "mode": mode,
         "updated_et": _now_et().isoformat()}, indent=2))


def _resolve_session(explicit: str | None) -> str:
    if explicit:
        return explicit
    if CURRENT_PTR.exists():
        try:
            sid = json.loads(CURRENT_PTR.read_text(encoding="utf-8")).get("session_id")
            if sid:  # a finished session clears the pointer to None -- not a session id
                return str(sid)
        except (OSError, json.JSONDecodeError):
            pass
    raise SystemExit(json.dumps({"ok": False, "error": "no --session and no current "
                                 "session pointer -- run --start first"}))


def _capture_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}-capture.jsonl"


# --------------------------------------------------------------------------- call parsing
def parse_call_text(text: str) -> dict:
    """'long 737.7 stop under 737.2 wick reject at PDH' -> {direction:'C', price:737.7,
    stop:737.2, rationale:<full text>}. Direction word + a price are REQUIRED (fail loud,
    never guess); stop is optional. Numbers accept 737 / 737.7 / $737.70."""
    t = text.strip()
    if not t:
        raise ValueError("empty call text")
    tokens = re.findall(r"[a-zA-Z]+|\$?\d+(?:\.\d+)?", t.lower())
    direction: str | None = None
    for tok in tokens:
        if tok in _LONG_WORDS:
            direction = "C"
            break
        if tok in _SHORT_WORDS:
            direction = "P"
            break
    if direction is None:
        raise ValueError(f"no direction word in call text {text!r} -- say long/short/"
                         f"calls/puts (or pass --direction)")
    nums = [float(x.lstrip("$")) for x in re.findall(r"\$?\d+(?:\.\d+)?", t)]
    if not nums:
        raise ValueError(f"no price in call text {text!r} (or pass --price)")
    stop: float | None = None
    # clause-bounded: the first number after 'stop' within the same comma/period clause
    # ("stop under the wick at 737.2" works; "stop it, target 750" does not false-match)
    m_stop = re.search(r"stop[^,;.0-9]{0,40}?(\d+(?:\.\d+)?)", t.lower())
    if m_stop:
        stop = float(m_stop.group(1))
    price = next((n for n in nums if stop is None or n != stop), nums[0])
    return {"direction": direction, "price": price, "stop": stop, "rationale": text.strip()}


# --------------------------------------------------------------------------- commands
def cmd_start(day: str | None, mode: str = "real") -> dict:
    pick = pick_day(day, mode=mode)
    replay_day = pick["replay_day"]
    started = spine.cmd_start(replay_day)
    if not started.get("ok"):
        return started
    sid = started["session_id"]
    pick["session_id"] = sid
    _fenced_append_jsonl(SESSIONS_LOG, pick)
    cap = _capture_path(sid)
    _fenced_append_jsonl(cap, {"event": "capture_open", "session_id": sid,
                               "replay_day": replay_day, "opened_et": _now_et().isoformat(),
                               "mode": mode})
    _write_current_ptr(sid, replay_day, mode)
    return {
        "ok": True, "session_id": sid, "replay_day": replay_day, "mode": mode,
        "pick": {k: pick[k] for k in ("seed", "pick_index", "population_n",
                                       "population_sha1") if k in pick},
        "capture_file": str(cap),
        "session_ledger": started["ledger"],
        "tv_drive": {
            "1_start_replay": f"mcp__tradingview__replay_start(date=\"{replay_day}\")",
            "2_fast_forward": "premarket bars are 5-min ETH bars -- replay_step ~66x or "
                              "mcp__tradingview__replay_autoplay to reach 09:30, then pause",
            "3_per_bar_loop": "replay_step() -> replay_status().current_date -> "
                              f"python dojo_session.py --step --cursor <epoch>",
            "4_on_a_call": "python dojo_session.py --call \"<J's words>\" --cursor <epoch>",
            "5_close": f"replay_stop() then: python dojo_session.py --finish",
        },
        "note": "TV drive verified working 2026-08-01 (replay_start/step/status/stop). "
                "J without an agent: use TV's own replay UI; --call still captures.",
    }


def cmd_step(session_id: str | None, cursor_epoch: int) -> dict:
    sid = _resolve_session(session_id)
    return spine.cmd_step(sid, cursor_epoch)


def cmd_call(session_id: str | None, text: str, cursor_epoch: int | None,
             price: float | None, direction: str | None, stop: float | None) -> dict:
    sid = _resolve_session(session_id)
    st = spine._load_state(sid)
    if st.phase == spine.PHASE_CLOSED:
        return {"ok": False, "error": f"session {sid} is CLOSED"}
    try:
        parsed = parse_call_text(text)
    except ValueError as e:
        if price is None or direction is None:
            return {"ok": False, "error": f"call rejected: {e}"}
        parsed = {"direction": None, "price": None, "stop": None, "rationale": text.strip()}
    if direction:
        d = direction.strip().upper()
        parsed["direction"] = {"LONG": "C", "C": "C", "CALL": "C",
                               "SHORT": "P", "P": "P", "PUT": "P"}.get(d)
        if parsed["direction"] is None:
            return {"ok": False, "error": f"--direction {direction!r} not long/short/C/P"}
    if price is not None:
        parsed["price"] = float(price)
    if stop is not None:
        parsed["stop"] = float(stop)

    bar_et = None
    cursor_iso = None
    if cursor_epoch:
        cur = clock.resolve_cursor(cursor_epoch)
        cursor_iso = cur.isoformat()
        b = clock.latest_closed_5m_bar_et(cur)
        bar_et = b.isoformat() if b else None
    elif st.last_bar_et:
        bar_et = st.last_bar_et
        cursor_iso = f"epoch:{st.last_cursor_epoch}"
    row = {
        "event": "j_call", "session_id": sid, "ts_et": _now_et().isoformat(),
        "cursor": cursor_iso, "bar_et": bar_et, "bar_index": st.step_count,
        "direction": parsed["direction"], "price": parsed["price"], "stop": parsed["stop"],
        "rationale": parsed["rationale"],
        "anchored": bar_et is not None,
    }
    _fenced_append_jsonl(_capture_path(sid), row)
    return {"ok": True, "captured": row,
            "warning": None if bar_et else "UNANCHORED call (no cursor, no prior step) -- "
                                            "will be EXCLUDED from OPRA valuation at --finish"}


# ------------------------------------------------------------------ finish: counterfactual
def _rth_bar_closes(replay_day: str) -> list[datetime]:
    day = date.fromisoformat(replay_day)
    out = []
    t = datetime.combine(day, RTH_CLOSES_FIRST, tzinfo=ET)
    last = datetime.combine(day, RTH_CLOSES_LAST, tzinfo=ET)
    while t <= last:
        out.append(t)
        t += timedelta(minutes=5)
    return out


def _ledger_decisions_by_bar(ledger_rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in ledger_rows:
        if r.get("event") in ("step", "cf_step") and r.get("bar_et") and r.get("decisions"):
            out[str(r["bar_et"])] = r["decisions"]
    return out


def _dec_get(d, name, default=None):
    if isinstance(d, dict):
        return d.get(name, default)
    return getattr(d, name, default)


def _naive_iso(bar_et_iso: str) -> str:
    """tz-aware ET iso -> naive ET wall-clock iso (sim_executor's directive convention)."""
    return bar_et_iso[:19]


def _sim_positions(session_key: str) -> dict:
    p = SESSIONS_DIR / f"{session_key}-positions.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("positions", {})
    except (OSError, json.JSONDecodeError):
        return {}


def cmd_finish(session_id: str | None, max_cf_bars: int | None = None) -> dict:
    sid = _resolve_session(session_id)
    st = spine._load_state(sid)
    if st.phase == spine.PHASE_CLOSED:
        return {"ok": False, "error": f"session {sid} already CLOSED -- card at "
                f"{SESSIONS_DIR / (sid + '-comparison.md')}"}
    replay_day = st.replay_day
    mode = "real"
    if CURRENT_PTR.exists():
        try:
            ptr = json.loads(CURRENT_PTR.read_text(encoding="utf-8"))
            if ptr.get("session_id") == sid:
                mode = ptr.get("mode", "real")
        except (OSError, json.JSONDecodeError):
            pass

    # heavy imports only here (call/step paths stay snappy)
    from dojo import engine_step, sim_executor  # noqa: PLC0415

    bars_df = engine_step.load_day_bars(replay_day)
    sim_bars = bars_df.assign(timestamp_et=bars_df["timestamp"])
    ledger_rows = _read_jsonl(st.ledger_path)
    by_bar = _ledger_decisions_by_bar(ledger_rows)

    # 1) engine counterfactual for bars the sitting didn't step
    all_bars = _rth_bar_closes(replay_day)
    missing = [b for b in all_bars if b.isoformat() not in by_bar]
    computed = 0
    skipped_budget = 0
    for b in missing:
        if max_cf_bars is not None and computed >= max_cf_bars:
            skipped_budget += 1
            continue
        decisions = engine_step.step(replay_day, b, bars_df)
        rows = [spine._decision_row(d) for d in decisions]
        by_bar[b.isoformat()] = rows
        spine._append_ledger(st, {"event": "cf_step", "bar_et": b.isoformat(),
                                  "decisions": rows})
        computed += 1

    # 2) engine trades: per-arm sequential occupancy over would_place bars, valued via sim
    eod = datetime.combine(date.fromisoformat(replay_day), dtime(16, 0), tzinfo=ET)
    eng_key = f"{sid}-engine"
    busy_until: dict[str, str] = {}
    n_eng = 0
    for bar_iso in sorted(by_bar):
        for dec in by_bar[bar_iso]:
            arm = _dec_get(dec, "arm")
            if not _dec_get(dec, "would_place") or arm not in ARM_TO_SIM_ID:
                continue
            naive_bar = _naive_iso(bar_iso)
            if arm in busy_until and naive_bar <= busy_until[arm]:
                continue
            n_eng += 1
            directive = {
                "id": f"eng-{arm}-{n_eng:02d}", "arms": [ARM_TO_SIM_ID[arm]],
                "side": _dec_get(dec, "side") or "P", "cursor_et": naive_bar,
                "trigger": {"tag_level": _dec_get(dec, "trigger_level")},
                "sizing": {"qty": DEFAULT_QTY},
                "note": f"engine {_dec_get(dec, 'verdict')} setup={_dec_get(dec, 'setup')}",
            }
            sim_executor.arm_directive(eng_key, directive, dojo_dir=DOJO_DIR)
            sim_executor.advance_session(eng_key, eod, sim_bars, dojo_dir=DOJO_DIR)
            pos = _sim_positions(eng_key).get(f"eng-{arm}-{n_eng:02d}-{ARM_TO_SIM_ID[arm]}", {})
            busy_until[arm] = pos.get("exit_time_et") or _naive_iso(eod.isoformat())

    # 3) J's calls valued the same way
    call_rows = [r for r in _read_jsonl(_capture_path(sid)) if r.get("event") == "j_call"]
    jcall_key = f"{sid}-jcalls"
    excluded_calls: list[dict] = []
    for i, c in enumerate(call_rows, 1):
        if not c.get("anchored") or not c.get("bar_et"):
            excluded_calls.append({**c, "excluded_reason": "UNANCHORED (no bar cursor)"})
            continue
        if not c.get("direction") or c.get("price") is None:
            excluded_calls.append({**c, "excluded_reason": "UNPARSEABLE (missing "
                                   "direction/price)"})
            continue
        directive = {
            "id": f"jcall-{i:02d}", "arms": ["safe"], "side": c["direction"],
            "cursor_et": _naive_iso(str(c["bar_et"])),
            "trigger": {"tag_level": c.get("stop")},
            "exits": {"stop_mode": "structure"} if c.get("stop") is not None else {},
            "sizing": {"qty": DEFAULT_QTY}, "note": c.get("rationale"),
        }
        sim_executor.arm_directive(jcall_key, directive, dojo_dir=DOJO_DIR)
    if call_rows:
        sim_executor.advance_session(jcall_key, eod, sim_bars, dojo_dir=DOJO_DIR)

    # 4) close the spine session (scorecard + harvest stub)
    closed = spine.cmd_close(sid)

    # 5) comparison card + harvest append + review mark
    card = _build_card(sid, replay_day, mode, by_bar, call_rows, excluded_calls,
                       _sim_positions(jcall_key), _sim_positions(eng_key),
                       computed, len(all_bars), skipped_budget, closed)
    card_json = SESSIONS_DIR / f"{sid}-comparison.json"
    card_md = SESSIONS_DIR / f"{sid}-comparison.md"
    _fenced_write_text(card_json, json.dumps(card, indent=2, default=str))
    _fenced_write_text(card_md, _render_card_md(card))
    _append_harvest(sid, card)
    _fenced_append_jsonl(SESSIONS_LOG, {
        "event": "reviewed", "session_id": sid, "replay_day": replay_day, "mode": mode,
        "finished_et": _now_et().isoformat(), "n_calls": len(call_rows),
        "n_engine_trades": len(_sim_positions(eng_key)),
        "card": str(card_md)})
    if CURRENT_PTR.exists():
        try:
            if json.loads(CURRENT_PTR.read_text(encoding="utf-8")).get("session_id") == sid:
                _fenced_write_text(CURRENT_PTR, json.dumps(
                    {"session_id": None, "note": f"last finished: {sid}"}, indent=2))
        except (OSError, json.JSONDecodeError):
            pass
    return {"ok": True, "session_id": sid, "replay_day": replay_day, "mode": mode,
            "comparison_md": str(card_md), "comparison_json": str(card_json),
            "harvest": closed.get("harvest_stub"),
            "totals": card["totals"], "caveats": card["caveats"]}


# ------------------------------------------------------------------ card building
def _pos_summary(pos: dict) -> dict:
    return {
        "id": pos.get("position_id"), "arm": pos.get("arm"), "symbol": pos.get("symbol"),
        "side": pos.get("side"), "strike": pos.get("strike"), "qty": pos.get("qty"),
        "status": pos.get("status"), "entry_time_et": pos.get("entry_time_et"),
        "entry_premium": pos.get("entry_premium"), "exit_time_et": pos.get("exit_time_et"),
        "exit_reason": pos.get("exit_reason"), "realized_pnl": pos.get("realized_pnl"),
        "unrealized_pnl": pos.get("unrealized_pnl"),
        "price_source": pos.get("price_source"), "is_synthetic": bool(pos.get("is_synthetic")),
        "note": pos.get("note"),
    }


def _lane_totals(positions: dict) -> dict:
    real = [p for p in positions.values()
            if not p.get("is_synthetic") and p.get("status") in ("OPEN", "CLOSED")]
    synth = [p for p in positions.values()
             if p.get("is_synthetic") and p.get("status") in ("OPEN", "CLOSED")]
    other = [p for p in positions.values() if p.get("status") not in ("OPEN", "CLOSED")]
    return {
        "real_opra_pnl": round(sum(float(p.get("realized_pnl") or 0)
                                   + float(p.get("unrealized_pnl") or 0) for p in real), 2),
        "n_real": len(real),
        "synthetic_pnl_EXCLUDED": round(sum(float(p.get("realized_pnl") or 0)
                                            + float(p.get("unrealized_pnl") or 0)
                                            for p in synth), 2),
        "n_synthetic_EXCLUDED": len(synth),
        "n_no_fill_or_error": len(other),
    }


def _build_card(sid: str, replay_day: str, mode: str, by_bar: dict,
                call_rows: list[dict], excluded_calls: list[dict],
                j_positions: dict, eng_positions: dict,
                cf_computed: int, n_all_bars: int, cf_skipped: int, closed: dict) -> dict:
    j_lane = [_pos_summary(p) for p in j_positions.values()]
    e_lane = [_pos_summary(p) for p in eng_positions.values()]

    # divergences: bars where J called but engine (all arms) held; engine entries with no J call
    call_bars = {str(c.get("bar_et"))[:19] for c in call_rows if c.get("bar_et")}
    eng_entry_bars = set()
    for p in eng_positions.values():
        if p.get("entry_time_et"):
            eng_entry_bars.add(str(p["entry_time_et"])[:16])
    divergences = []
    for c in call_rows:
        if not c.get("bar_et"):
            continue
        bar = str(c["bar_et"])
        decs = by_bar.get(bar) or by_bar.get(bar[:19]) or []
        placed = [_dec_get(d, "arm") for d in decs if _dec_get(d, "would_place")]
        if not placed:
            verdicts = {_dec_get(d, "arm"): _dec_get(d, "verdict") for d in decs}
            divergences.append({"type": "J_CALLED_ENGINE_HELD", "bar_et": bar,
                                "j_call": c.get("rationale"), "engine_verdicts": verdicts})
    for p in eng_positions.values():
        ent = str(p.get("entry_time_et") or "")[:16]
        if ent and not any(cb.startswith(ent[:16]) for cb in call_bars):
            divergences.append({"type": "ENGINE_ENTERED_J_SILENT",
                                "bar_et": p.get("entry_time_et"), "arm": p.get("arm"),
                                "symbol": p.get("symbol"),
                                "realized_pnl": p.get("realized_pnl"),
                                "is_synthetic": bool(p.get("is_synthetic"))})

    caveats = [
        "Engine counterfactual levels are reconstructed from the CURRENT key-levels.json "
        "restricted to entries knowable as of the replay day -- level-tied triggers on old "
        "days are an approximation (dojo/engine_step.py docstring).",
        "Option fills: real OPRA 5-min cache where present; BS-synthetic rows are FLAGGED "
        "and EXCLUDED from headline totals (Free-Kitchen-Plan-B rule).",
        "Exits walk the REAL exit_manager core at entry+1 convention "
        "(ENTRY-BAR-CONVENTION-RULING-2026-07-25). ~4-min live-cadence under-coverage "
        "residual disclosed there applies here too.",
        "J-call valuation assumes core-Safe strike tier (ATM) + qty 3 + structure stop at "
        "J's stated stop when given; engine-lane trades use each arm's own tier/exit shape.",
    ]
    if cf_skipped:
        caveats.append(f"PARTIAL COUNTERFACTUAL: {cf_skipped} RTH bars NOT computed "
                       f"(--max-cf-bars budget; fake/smoke mode only).")
    return {
        "session_id": sid, "replay_day": replay_day, "mode": mode,
        "generated_et": _now_et().isoformat(),
        "coverage": {"rth_bars_total": n_all_bars,
                     "bars_with_decisions": len(by_bar),
                     "cf_bars_computed_at_finish": cf_computed,
                     "cf_bars_skipped_budget": cf_skipped},
        "j_calls": {"n_captured": len(call_rows), "n_excluded": len(excluded_calls),
                    "excluded": excluded_calls, "positions": j_lane,
                    "totals": _lane_totals(j_positions)},
        "engine": {"positions": e_lane, "totals": _lane_totals(eng_positions)},
        "divergences": divergences,
        "directive_lane_scorecard": closed.get("scorecard") if isinstance(
            closed.get("scorecard"), dict) else None,
        "totals": {
            "j_real_opra_pnl": _lane_totals(j_positions)["real_opra_pnl"],
            "engine_real_opra_pnl": _lane_totals(eng_positions)["real_opra_pnl"],
            "j_minus_engine": round(_lane_totals(j_positions)["real_opra_pnl"]
                                    - _lane_totals(eng_positions)["real_opra_pnl"], 2),
        },
        "caveats": caveats,
    }


def _render_card_md(card: dict) -> str:
    L: list[str] = []
    t = card["totals"]
    L.append(f"# DOJO comparison card -- {card['replay_day']} "
             f"(session {card['session_id']}, mode={card['mode']})")
    L.append("")
    L.append(f"**J (real OPRA): ${t['j_real_opra_pnl']:+.2f}** vs "
             f"**engine (real OPRA): ${t['engine_real_opra_pnl']:+.2f}** "
             f"-> J-minus-engine **${t['j_minus_engine']:+.2f}** "
             f"(n=1 day -- a scoreboard, NEVER ship evidence; Lane B pre-reg is the path)")
    L.append("")
    cov = card["coverage"]
    L.append(f"Coverage: {cov['bars_with_decisions']}/{cov['rth_bars_total']} RTH bars with "
             f"engine decisions ({cov['cf_bars_computed_at_finish']} computed at finish"
             + (f", {cov['cf_bars_skipped_budget']} SKIPPED -- PARTIAL" if
                cov["cf_bars_skipped_budget"] else "") + ")")
    L.append("")
    L.append("## J's calls")
    L.append("")
    jc = card["j_calls"]
    if not jc["positions"] and not jc["excluded"]:
        L.append("(none captured)")
    else:
        L.append("| # | bar | side | symbol | fill | exit | reason | P&L | source |")
        L.append("|---|-----|------|--------|------|------|--------|-----|--------|")
        for p in jc["positions"]:
            pnl = (p.get("realized_pnl") or 0) + (p.get("unrealized_pnl") or 0)
            src = "SYNTH-EXCLUDED" if p["is_synthetic"] else p.get("price_source", "-")
            L.append(f"| {p['id']} | {str(p.get('entry_time_et'))[11:16]} | {p['side']} | "
                     f"{p['symbol']} | {p.get('entry_premium')} | "
                     f"{str(p.get('exit_time_et') or '-')[11:16]} | "
                     f"{p.get('exit_reason') or p['status']} | {pnl:+.2f} | {src} |")
        for x in jc["excluded"]:
            L.append(f"| - | {str(x.get('bar_et') or '?')[11:16]} | "
                     f"{x.get('direction') or '?'} | - | - | - | "
                     f"{x['excluded_reason']} | EXCLUDED | - |")
    L.append("")
    L.append("## Engine trades (would-place, per-arm occupancy, same OPRA valuation)")
    L.append("")
    ep = card["engine"]["positions"]
    if not ep:
        L.append("(engine placed nothing this day)")
    else:
        L.append("| # | arm | bar | side | symbol | fill | exit | reason | P&L | source |")
        L.append("|---|-----|-----|------|--------|------|------|--------|-----|--------|")
        for p in ep:
            pnl = (p.get("realized_pnl") or 0) + (p.get("unrealized_pnl") or 0)
            src = "SYNTH-EXCLUDED" if p["is_synthetic"] else p.get("price_source", "-")
            L.append(f"| {p['id']} | {p['arm']} | {str(p.get('entry_time_et'))[11:16]} | "
                     f"{p['side']} | {p['symbol']} | {p.get('entry_premium')} | "
                     f"{str(p.get('exit_time_et') or '-')[11:16]} | "
                     f"{p.get('exit_reason') or p['status']} | {pnl:+.2f} | {src} |")
    L.append("")
    L.append("## Divergences")
    L.append("")
    if not card["divergences"]:
        L.append("(none)")
    for d in card["divergences"]:
        if d["type"] == "J_CALLED_ENGINE_HELD":
            L.append(f"- **{str(d['bar_et'])[11:16]}** J called ({d['j_call']!r}) -- engine "
                     f"held: {d['engine_verdicts']}")
        else:
            L.append(f"- **{str(d['bar_et'])[11:16]}** engine entered ({d['arm']} "
                     f"{d['symbol']}, P&L {d.get('realized_pnl')}) -- J was silent"
                     + (" [SYNTHETIC-EXCLUDED]" if d.get("is_synthetic") else ""))
    L.append("")
    L.append("## Caveats (read before quoting any number)")
    L.append("")
    for c in card["caveats"]:
        L.append(f"- {c}")
    L.append("")
    return "\n".join(L)


def _append_harvest(sid: str, card: dict) -> None:
    p = SESSIONS_DIR / f"{sid}-harvest.md"
    lane_a: list[str] = []
    for x in card["j_calls"]["excluded"]:
        lane_a.append(f"- [ ] AUTO-SEEDED CANDIDATE (capture gap): call at "
                      f"{x.get('bar_et') or x.get('ts_et')} excluded -- "
                      f"{x['excluded_reason']}; raw: {x.get('rationale')!r}. If J's words "
                      f"could not be expressed, that is a Lane-A plumbing item.")
    lane_b: list[str] = []
    for d in card["divergences"]:
        if d["type"] == "J_CALLED_ENGINE_HELD":
            lane_b.append(f"- [ ] AUTO-SEEDED CANDIDATE (policy): {str(d['bar_et'])[:16]} "
                          f"J called {d['j_call']!r}, engine held. If J's call paid, "
                          f"pre-reg the pattern (anchor day {card['replay_day']}) -- "
                          f"file analysis/recommendations/<slug>.json per runbook 4.")
    lines = ["", f"## ONE-COMMAND HARNESS APPEND ({card['generated_et'][:16]})", "",
             f"Comparison card: `{sid}-comparison.md` -- J ${card['totals']['j_real_opra_pnl']:+.2f} "
             f"vs engine ${card['totals']['engine_real_opra_pnl']:+.2f} (real-OPRA-only).", ""]
    lines += ["### LANE A candidates (auto-seeded -- human routes to queue.md)", ""]
    lines += lane_a or ["- (none auto-seeded)"]
    lines += ["", "### LANE B candidates (auto-seeded -- human routes to pre-reg)", ""]
    lines += lane_b or ["- (none auto-seeded)"]
    lines.append("")
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    _fenced_write_text(p, existing + "\n".join(lines))


# --------------------------------------------------------------------------- fake session
def cmd_fake(day: str | None) -> dict:
    """End-to-end smoke WITHOUT TV or J: start (fake mode -- never burns a population day),
    step ~10 bars via synthesized cursors, capture 2 calls, finish with a small
    counterfactual budget. Proves the whole pipe (pick->spine->capture->cf->OPRA card)."""
    replay_day = day or "2026-07-17"
    started = cmd_start(replay_day, mode="fake")
    if not started.get("ok"):
        return started
    sid = started["session_id"]
    d = date.fromisoformat(replay_day)
    # cursors mid-bar 10:31..11:20 ET -> closed bars 10:30..11:15
    steps = []
    for k in range(10):
        cur = datetime.combine(d, dtime(10, 31), tzinfo=ET) + timedelta(minutes=5 * k)
        r = spine.cmd_step(sid, int(cur.timestamp()))
        steps.append({"cursor_et": cur.isoformat(), "bar_et": r.get("bar_et"),
                      "ok": r.get("ok")})
        if not r.get("ok"):
            return {"ok": False, "error": f"fake step failed: {r}", "steps": steps}
    c1_cur = int(datetime.combine(d, dtime(10, 46), tzinfo=ET).timestamp())
    c1 = cmd_call(sid, "long 746.5 here stop under 745.9, reclaim of the level held",
                  c1_cur, None, None, None)
    c2_cur = int(datetime.combine(d, dtime(11, 6), tzinfo=ET).timestamp())
    c2 = cmd_call(sid, "puts 746.9, momentum gone", c2_cur, None, None, None)
    if not (c1.get("ok") and c2.get("ok")):
        return {"ok": False, "error": "fake calls failed", "c1": c1, "c2": c2}
    fin = cmd_finish(sid, max_cf_bars=4)
    return {"ok": bool(fin.get("ok")), "fake_session": sid, "replay_day": replay_day,
            "n_steps": len(steps), "calls": [c1["captured"], c2["captured"]],
            "finish": fin}


def cmd_show_status(session_id: str | None) -> dict:
    out: dict = {"ok": True, "sessions_log": str(SESSIONS_LOG)}
    if CURRENT_PTR.exists():
        try:
            out["current"] = json.loads(CURRENT_PTR.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            out["current"] = None
    try:
        sid = _resolve_session(session_id)
        out["session"] = spine.cmd_status(sid)
        cap = _capture_path(sid)
        out["n_calls"] = sum(1 for r in _read_jsonl(cap) if r.get("event") == "j_call")
    except (SystemExit, FileNotFoundError):
        out["session"] = None
    log_rows = _read_jsonl(SESSIONS_LOG)
    out["days_reviewed"] = sorted({r["replay_day"] for r in log_rows
                                   if r.get("event") == "reviewed" and r.get("mode") != "fake"
                                   and r.get("replay_day")})
    return out


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="dojo_session", description="ONE-command dojo session harness (WS10)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--start", action="store_true")
    g.add_argument("--step", action="store_true")
    g.add_argument("--call", metavar="TEXT")
    g.add_argument("--finish", action="store_true")
    g.add_argument("--fake", action="store_true")
    g.add_argument("--show-status", action="store_true")
    ap.add_argument("--day", help="explicit replay day YYYY-MM-DD (--start/--fake)")
    ap.add_argument("--session", help="session id (default: current pointer)")
    ap.add_argument("--cursor", type=int, help="TV replay_status().current_date epoch")
    ap.add_argument("--price", type=float, help="override parsed call price")
    ap.add_argument("--direction", help="override parsed call direction (long/short/C/P)")
    ap.add_argument("--stop", type=float, help="override parsed call stop")
    ap.add_argument("--max-cf-bars", type=int, default=None,
                    help="cap counterfactual bars computed at --finish (smoke only)")
    a = ap.parse_args(argv)

    if a.start:
        out = cmd_start(a.day)
    elif a.step:
        if a.cursor is None:
            out = {"ok": False, "error": "--step requires --cursor <epoch>"}
        else:
            out = cmd_step(a.session, a.cursor)
    elif a.call is not None:
        out = cmd_call(a.session, a.call, a.cursor, a.price, a.direction, a.stop)
    elif a.finish:
        out = cmd_finish(a.session, a.max_cf_bars)
    elif a.fake:
        out = cmd_fake(a.day)
    else:
        out = cmd_show_status(a.session)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
