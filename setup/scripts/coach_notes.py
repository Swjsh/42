"""coach_notes.py -- deterministic coaching notes for Coach (GOAL-GAMMA-STATION
2026-09-14 CREW-RIG R2 build).

WHY THIS EXISTS: J's verdict (2026-09-14 16:50 ET), reading the HQ crew panel -- "Coach
-- why would Coach be WAITING? There should be a plethora of things for Coach to coach
the crypto on, or paper trading." Coach's sectors/task-health pass (station_loop.py's
_write_sectors_and_crew_events) already runs every fire, but it answers "is each lane
green" -- it never looks AT the trades themselves. This module is Coach's second job:
read what already exists (crypto twin fills, paper-arm autopsies with pre-computed
counterfactuals, sectors RED reasons), compute up to 6 one-line, dollar-ranked coaching
notes, $0, no LLM, every Station fire.

PERFORMANCE NOTE (read before touching the twin-journal reads below): automation/state/
crypto-twin/journal.jsonl is tens of MB and growing under a recent trading burst (verified
2026-09-14: ~21MB needed to cover a full 7-day window at today's history). This module
NEVER reads that file whole -- gather_twin_stats() does one bounded tail read (last
TAIL_BYTES_CAP bytes only) and reports the ACTUAL time span that read covers (never
silently claims a fixed 7d/24h window it did not really read). automation/state/
crypto-twin/decisions.jsonl (146MB, one row per twin tick) is never opened at all --
"current open position age" comes from the tiny live exit-state.json instead.

Fail-open throughout: any missing/garbled source degrades that ONE input to
"available": False (never a guess, never a crash) -- same discipline as
station_facts.py's own docstring: "never invents".
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import station_board  # noqa: E402 -- read_json_or_none / atomic_write_text / read_jsonl (shared, stdlib-only)
import crew_events  # noqa: E402 -- the crew ticker

# ---- Paths this module owns, all prefixed COACH_ so every Station test fixture can
# redirect them to tmp_path exactly like SECTORS_PATH/CREW_EVENTS_PATH already are (the
# build brief's own explicit requirement -- a test must never write/read live state). ----
COACH_TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
COACH_TWIN_JOURNAL_PATH = COACH_TWIN_DIR / "journal.jsonl"
COACH_TWIN_EXIT_STATE_PATH = COACH_TWIN_DIR / "exit-state.json"
COACH_TWIN_BREAKER_PATH = COACH_TWIN_DIR / "breaker.json"
COACH_AUTOPSY_DIR = REPO / "analysis" / "autopsies"
COACH_SECTORS_PATH = REPO / "automation" / "state" / "station" / "sectors.json"
COACH_NOTES_PATH = REPO / "automation" / "state" / "station" / "coach-notes.json"

TAIL_BYTES_CAP = 3_000_000   # bounded tail read of journal.jsonl -- see module docstring
MAX_NOTES = 6
N_SESSIONS = 5                # "each paper arm's last 5 sessions"
MAE_MFE_NOTE = ("not present in automation/state/crypto-twin journal.jsonl/exit-state.json "
                "schema as of the 2026-09-14 build -- reported null, never fabricated")


# --------------------------------------------------------------------------- #
# Small formatting/parsing helpers
# --------------------------------------------------------------------------- #

def _fmt_usd(v) -> str:
    if v is None:
        return "n/a"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "n/a"
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


def _parse_iso_utc(ts) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt_age(delta: timedelta) -> str:
    total_min = max(0, int(delta.total_seconds() // 60))
    h, m = divmod(total_min, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


# --------------------------------------------------------------------------- #
# Crypto twin -- bounded tail read of journal.jsonl, tiny live-state reads for
# the current position + day breaker.
# --------------------------------------------------------------------------- #

def _tail_jsonl_rows(path: Path, max_bytes: int) -> tuple:
    """Reads up to the last `max_bytes` of `path`, decodes utf-8 (errors replaced), and
    parses every complete JSON line found. Returns (rows, coverage_start_utc) where
    coverage_start_utc is the earliest ts_utc/ts_et seen among ALL parsed rows (any event
    type) -- the honest left edge of what this bounded read actually reached, so callers
    NEVER claim a fixed window (24h/7d) wider than what was really read. ([], None) on any
    missing file or total parse failure."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read = min(size, max_bytes)
            f.seek(size - read)
            raw = f.read()
    except OSError:
        return [], None
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if read < size:
        lines = lines[1:]  # the first line of a mid-file seek is very likely a partial record -- drop it
    rows = []
    earliest: Optional[datetime] = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        rows.append(row)
        ts = _parse_iso_utc(row.get("ts_utc"))
        if ts is not None and (earliest is None or ts < earliest):
            earliest = ts
    return rows, earliest


def _trip_usd(row: dict) -> Optional[float]:
    """Realized $ for one EXIT_FILLED row -- prefers the wired `realized_usd` field
    (present on every twin exit since the 2026-07-26 TWIN-PNL wiring), falls back to
    (fill_price - entry_price) * btc_qty for the rare older/unwired row, else None
    (excluded from $ aggregates rather than guessed)."""
    usd = row.get("realized_usd")
    if isinstance(usd, (int, float)):
        return float(usd)
    ep, xp, qty = row.get("entry_price"), row.get("fill_price"), row.get("btc_qty")
    if isinstance(ep, (int, float)) and isinstance(xp, (int, float)) and isinstance(qty, (int, float)):
        return (float(xp) - float(ep)) * float(qty)
    return None


def _window_stats(exits: list, now_utc: datetime, window: timedelta) -> dict:
    """Aggregate stats over EXIT_FILLED rows whose ts_utc falls within `window` of
    now_utc. `exits` must already be the full candidate set (this function only
    filters/aggregates, never re-reads a file)."""
    cutoff = now_utc - window
    in_window = []
    for r in exits:
        ts = _parse_iso_utc(r.get("ts_utc"))
        if ts is not None and ts >= cutoff:
            in_window.append((ts, r))
    trips = []
    n_unpriced = 0
    for ts, r in in_window:
        usd = _trip_usd(r)
        if usd is None:
            n_unpriced += 1
            continue
        trips.append({
            "ts_utc": ts, "usd": usd,
            "reason": (r.get("reason") or "").split(" @")[0] or None,
            "scenario": r.get("scenario"),
        })
    wins = [t for t in trips if t["usd"] > 0]
    losses = [t for t in trips if t["usd"] < 0]
    net = sum(t["usd"] for t in trips)
    worst = min(trips, key=lambda t: t["usd"]) if trips else None
    return {
        "n": len(trips), "n_unpriced": n_unpriced,
        "wins": len(wins), "losses": len(losses),
        "net": round(net, 2) if trips else None,
        "avg_win": round(sum(t["usd"] for t in wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(t["usd"] for t in losses) / len(losses), 2) if losses else None,
        "worst": ({"usd": round(worst["usd"], 2), "reason": worst["reason"], "scenario": worst["scenario"],
                   "ts_utc": worst["ts_utc"].isoformat()} if worst else None),
    }


def gather_twin_stats(now_utc: datetime, *,
                      journal_path: Optional[Path] = None,
                      exit_state_path: Optional[Path] = None,
                      breaker_path: Optional[Path] = None,
                      tail_bytes: int = TAIL_BYTES_CAP) -> dict:
    journal_path = journal_path or COACH_TWIN_JOURNAL_PATH
    exit_state_path = exit_state_path or COACH_TWIN_EXIT_STATE_PATH
    breaker_path = breaker_path or COACH_TWIN_BREAKER_PATH

    rows, coverage_start = _tail_jsonl_rows(journal_path, tail_bytes)
    if not rows:
        return {"available": False, "source": str(journal_path)}

    exits = [r for r in rows if r.get("event") == "EXIT_FILLED"]
    coverage_hours = ((now_utc - coverage_start).total_seconds() / 3600.0) if coverage_start else 0.0
    window_7d = min(timedelta(days=7), timedelta(hours=coverage_hours)) if coverage_hours > 0 else timedelta(0)
    window_7d_days = round(window_7d.total_seconds() / 86400.0, 1)

    stats_24h = _window_stats(exits, now_utc, timedelta(hours=24))
    stats_window = _window_stats(exits, now_utc, window_7d) if window_7d > timedelta(0) else dict(stats_24h)

    open_position = None
    exit_state = station_board.read_json_or_none(exit_state_path)
    if isinstance(exit_state, dict) and exit_state:
        symbol, pos = next(iter(exit_state.items()))
        if isinstance(pos, dict):
            entered = _parse_iso_utc(pos.get("entered_at_utc"))
            open_position = {
                "symbol": symbol, "side": pos.get("side"),
                "entered_at_utc": pos.get("entered_at_utc"),
                "age_minutes": round((now_utc - entered).total_seconds() / 60.0, 1) if entered else None,
                "entry_premium": (pos.get("exit_state") or {}).get("entry_premium"),
            }

    day_pnl = None
    breaker = station_board.read_json_or_none(breaker_path)
    if isinstance(breaker, dict):
        cur, start = breaker.get("current_equity"), breaker.get("start_of_day_equity")
        if isinstance(cur, (int, float)) and isinstance(start, (int, float)):
            day_pnl = round(cur - start, 2)

    return {
        "available": True,
        "source": str(journal_path),
        "tail_bytes_read": min(tail_bytes, journal_path.stat().st_size) if journal_path.exists() else 0,
        "coverage_hours": round(coverage_hours, 1),
        "window_7d_days_actual": window_7d_days,
        "stats_24h": stats_24h,
        "stats_window": stats_window,
        "open_position": open_position,
        "day_pnl": day_pnl,
        "mae_mfe": None,
        "mae_mfe_note": MAE_MFE_NOTE,
    }


# --------------------------------------------------------------------------- #
# Paper arms -- last N session files under analysis/autopsies/*.jsonl (one file
# per trading day, small; NOT the analysis/autopsies/twin/ subdir).
# --------------------------------------------------------------------------- #

def gather_arm_session_stats(*, autopsy_dir: Optional[Path] = None, n_sessions: int = N_SESSIONS) -> dict:
    autopsy_dir = autopsy_dir or COACH_AUTOPSY_DIR
    if not autopsy_dir.is_dir():
        return {"available": False, "sessions_covered": [], "arms": {}}

    files = sorted((f for f in autopsy_dir.glob("*.jsonl") if f.is_file()), key=lambda f: f.name, reverse=True)
    files = files[:n_sessions]
    if not files:
        return {"available": False, "sessions_covered": [], "arms": {}}

    rows_by_arm: dict = defaultdict(list)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            arm = row.get("arm")
            if arm:
                rows_by_arm[arm].append(row)

    arms = {}
    for arm, rows in rows_by_arm.items():
        pnls = [r.get("actual_pnl") for r in rows if isinstance(r.get("actual_pnl"), (int, float))]
        losers = [r for r in rows if isinstance(r.get("actual_pnl"), (int, float)) and r["actual_pnl"] < 0]
        cf_counter: Counter = Counter()
        cf_delta_sum: dict = defaultdict(float)
        for r in losers:
            bc = r.get("best_counterfactual")
            delta = r.get("stop_cost_vs_best")
            if bc:
                cf_counter[bc] += 1
                if isinstance(delta, (int, float)):
                    cf_delta_sum[bc] += delta
        top = cf_counter.most_common(1)
        best_cf, best_cf_n = (top[0][0], top[0][1]) if top else (None, 0)
        # stop_cost_vs_best is the (actual - best) delta, i.e. negative when the actual
        # trade underperformed the hypothetical best exit -- negate it to report the $
        # improvement that counterfactual WOULD have delivered, matching the note's own
        # "wide_stop_-50 would be +$63" phrasing.
        best_cf_delta = round(-cf_delta_sum[best_cf], 2) if best_cf else None
        arms[arm] = {
            "n": len(rows), "net": round(sum(pnls), 2) if pnls else 0.0, "losers": len(losers),
            "best_counterfactual": best_cf, "best_counterfactual_loser_count": best_cf_n,
            "best_counterfactual_delta_usd": best_cf_delta,
        }
    return {"available": True, "sessions_covered": [f.stem for f in files], "arms": arms}


# --------------------------------------------------------------------------- #
# Sectors RED reasons -- sectors.json is already written earlier this SAME fire
# by station_loop._write_sectors_and_crew_events, so this is a fresh read.
# --------------------------------------------------------------------------- #

def gather_sectors_red(*, sectors_path: Optional[Path] = None) -> list:
    sectors_path = sectors_path or COACH_SECTORS_PATH
    doc = station_board.read_json_or_none(sectors_path)
    if not isinstance(doc, dict):
        return []
    rows = doc.get("rows") or []
    return [{"lane": r.get("lane"), "evidence": r.get("evidence"), "window_pnl": r.get("window_pnl")}
            for r in rows if isinstance(r, dict) and r.get("health") == "red"]


# --------------------------------------------------------------------------- #
# Ranking + assembly
# --------------------------------------------------------------------------- #

def _rank_key(note: dict) -> tuple:
    d = note.get("delta")
    return (0, -abs(d)) if isinstance(d, (int, float)) else (1, 0)


def build_notes(twin_stats: dict, arm_stats: dict, red_lanes: list) -> list:
    candidates: list = []

    if twin_stats.get("available"):
        s24 = twin_stats["stats_24h"]
        if s24["n"] > 0:
            worst = s24.get("worst")
            worst_txt = (f" · worst: {worst['reason'] or '?'}"
                         + (f" ({worst['scenario']})" if worst.get("scenario") else "")
                         + f" {_fmt_usd(worst['usd'])}") if worst else ""
            line = (f"Coach: crypto twin 24h — {s24['n']} trades {s24['wins']}W/{s24['losses']}L "
                    f"{_fmt_usd(s24['net'])} · avg win {_fmt_usd(s24['avg_win'])} / "
                    f"avg loss {_fmt_usd(s24['avg_loss'])}{worst_txt}")
            candidates.append({"lane": "crypto_twin", "stat": "24h_pnl", "line": line, "delta": s24["net"]})

        days = twin_stats.get("window_7d_days_actual") or 0
        sw = twin_stats["stats_window"]
        if sw["n"] > 0 and days >= 1.5:
            worst = sw.get("worst")
            worst_txt = (f" · worst: {worst['reason'] or '?'}"
                         + (f" ({worst['scenario']})" if worst.get("scenario") else "")
                         + f" {_fmt_usd(worst['usd'])}") if worst else ""
            line = (f"Coach: crypto twin last {days:g}d (tail-window, not always a full 7d) — "
                    f"{sw['n']} trades {sw['wins']}W/{sw['losses']}L {_fmt_usd(sw['net'])} · "
                    f"avg win {_fmt_usd(sw['avg_win'])} / avg loss {_fmt_usd(sw['avg_loss'])}{worst_txt}")
            candidates.append({"lane": "crypto_twin", "stat": f"{days:g}d_pnl", "line": line, "delta": sw["net"]})

        pos = twin_stats.get("open_position")
        if pos and pos.get("age_minutes") is not None:
            age_txt = _fmt_age(timedelta(minutes=pos["age_minutes"]))
            entry = pos.get("entry_premium")
            entry_txt = f" @ entry {entry:,.2f}" if isinstance(entry, (int, float)) else ""
            line = (f"Coach: crypto twin position open {age_txt} — {pos.get('symbol', '?')} "
                    f"{pos.get('side', '?')}{entry_txt}")
            candidates.append({"lane": "crypto_twin", "stat": "open_position", "line": line, "delta": None})

    if arm_stats.get("available"):
        for arm, a in sorted(arm_stats["arms"].items()):
            n_sess = len(arm_stats.get("sessions_covered") or [])
            if a["n"] == 0:
                continue
            if a["best_counterfactual"] and a["best_counterfactual_delta_usd"]:
                line = (f"Coach: {arm} last {n_sess} sessions — {a['n']} trades, net {_fmt_usd(a['net'])}, "
                        f"{a['losers']} losers · stops inside noise on "
                        f"{a['best_counterfactual_loser_count']}/{a['losers']} losers "
                        f"({a['best_counterfactual']} would be {_fmt_usd(a['best_counterfactual_delta_usd'])})")
                delta = a["best_counterfactual_delta_usd"]
            else:
                line = (f"Coach: {arm} last {n_sess} sessions — {a['n']} trades, net {_fmt_usd(a['net'])}, "
                        f"{a['losers']} losers")
                delta = a["net"]
            candidates.append({"lane": arm, "stat": "counterfactual", "line": line, "delta": delta})

    for red in red_lanes:
        wp = red.get("window_pnl")
        delta = wp if isinstance(wp, (int, float)) else None
        line = f"Coach: {red.get('lane', '?')} RED — {str(red.get('evidence', ''))[:110]}"
        candidates.append({"lane": f"sector:{red.get('lane')}", "stat": "red", "line": line, "delta": delta})

    candidates.sort(key=_rank_key)
    return candidates[:MAX_NOTES]


# --------------------------------------------------------------------------- #
# The Station's every-fire entrypoint
# --------------------------------------------------------------------------- #

def run_once(ts_et: str, now_utc: datetime, *,
            journal_path: Optional[Path] = None, exit_state_path: Optional[Path] = None,
            breaker_path: Optional[Path] = None, autopsy_dir: Optional[Path] = None,
            sectors_path: Optional[Path] = None, notes_path: Optional[Path] = None,
            crew_events_path: Optional[Path] = None) -> dict:
    """Computes and writes coach-notes.json, then emits ONE crew-event only when the
    top note's line actually changed since the last one Coach posted. NEVER RAISES --
    wrapped exactly like scout_feed.run_scan so a bug here can only ever degrade Coach's
    own notes, never take the Station fire down with it (the call site's try/except in
    station_loop.py is defense in depth, not the only guard)."""
    notes_path = notes_path or COACH_NOTES_PATH
    try:
        twin_stats = gather_twin_stats(now_utc, journal_path=journal_path,
                                       exit_state_path=exit_state_path, breaker_path=breaker_path)
        arm_stats = gather_arm_session_stats(autopsy_dir=autopsy_dir)
        red_lanes = gather_sectors_red(sectors_path=sectors_path)
        notes = build_notes(twin_stats, arm_stats, red_lanes)

        doc = {
            "ts_et": ts_et,
            "notes": notes,
            "inputs": {
                "files": [str(journal_path or COACH_TWIN_JOURNAL_PATH), str(exit_state_path or COACH_TWIN_EXIT_STATE_PATH),
                         str(breaker_path or COACH_TWIN_BREAKER_PATH), str(autopsy_dir or COACH_AUTOPSY_DIR),
                         str(sectors_path or COACH_SECTORS_PATH)],
                "rows": {
                    "twin_available": twin_stats.get("available", False),
                    "twin_coverage_hours": twin_stats.get("coverage_hours"),
                    "arm_sessions_covered": len(arm_stats.get("sessions_covered") or []),
                    "arms_seen": len(arm_stats.get("arms") or {}),
                    "sectors_red": len(red_lanes),
                },
            },
        }
        station_board.atomic_write_text(notes_path, json.dumps(doc, indent=2, ensure_ascii=False))

        top_line = notes[0]["line"] if notes else None
        if top_line:
            try:
                prev = crew_events.last_row(kind="coaching", who="Coach", path=crew_events_path or crew_events.DEFAULT_PATH)
                if prev is None or prev.get("line") != top_line:
                    crew_events.append(
                        {"ts_et": ts_et, "who": "Coach", "kind": "coaching", "to": "Gamma",
                         "line": top_line, "ref": str(notes_path)},
                        path=crew_events_path or crew_events.DEFAULT_PATH,
                    )
            except Exception:  # noqa: BLE001 -- a ticker glitch must never break the notes write itself
                pass
        return doc
    except Exception as exc:  # noqa: BLE001 -- the Station fire must never die on a coaching-notes bug
        return {"ts_et": ts_et, "error": f"{type(exc).__name__}: {exc}"[:300], "notes": []}
