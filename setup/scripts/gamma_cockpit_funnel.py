"""gamma_cockpit_funnel.py -- payload builder for the Routing Map (fill-funnel Sankey).

Workstream C (Routing map). Owns ONLY this module + gamma_cockpit_sankey_js.py.

Reads `fill_funnel.compute_funnel(day)` -- the day's per-account
ticks -> signals -> enter -> rule_blocked/attempted -> accepted -> filled -> exited
pipeline (see that module's docstring for the ground-truth story: OP-33e, the
instrument that retired "is it actually trading?") -- and reshapes its totals into
the FIXED six-column Sankey the routing-map panel draws: ticks, signals, enter,
accepted, filled, exited. `attempted` and `rule_blocked` are real fill_funnel
stages but are not columns here; their counts are folded into the "refused" link
leaving `enter` (see `_build_links`) so nothing is dropped, only reshaped.

CONSERVATION RULE (the Sankey panel's whole visual honesty): for every stage i,
the links LEAVING stage i sum to exactly stages[i].n. `_build_links` builds each
stage's outflow as flow + refused (where applicable) + quiet, with quiet always
computed as the remainder -- so a bug here would show up as ribbons that don't
add up, not as silently dropped ticks.

FALLBACK: when compute_funnel finds zero ticks for the day (core-decisions.jsonl
has nothing yet -- fresh boot, holiday, or a day not yet reached), autonomy-
metric.json's `function_latest` (enters/accepted/fills only -- no ticks/signals/
exited at that granularity) fills in what it can; the rest of the stages stay
n=None and are drawn as the panel's NO DATA state for those columns specifically.
When BOTH are empty, the whole payload comes back ok=False with stage ids still
present (n=None) and `say` naming exactly what was looked for -- never fabricated.

Never raises. STDLIB ONLY.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"

sys.path.insert(0, str(REPO / "setup" / "scripts"))

_STAGE_LABELS = [
    ("ticks", "Ticks"),
    ("signals", "Signals"),
    ("enter", "Enter"),
    ("accepted", "Accepted"),
    ("filled", "Filled"),
    ("exited", "Exited"),
]
_STAGE_IDS = [s for s, _ in _STAGE_LABELS]


def _posix(p) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO)).replace("\\", "/")
    except Exception:  # noqa: BLE001 -- outside repo, or bad path: show it verbatim
        return str(p).replace("\\", "/")


def _empty_stages() -> list:
    return [{"id": sid, "label": lbl, "n": None} for sid, lbl in _STAGE_LABELS]


def _no_data(day: str | None) -> dict:
    return {
        "ok": False,
        "path": "automation/state/core-decisions.jsonl",
        "stamp_et": None,
        "day": day,
        "live": False,
        "session_label": None,
        "verdict": "off",
        "say": "NO DATA, looked for core-decisions.jsonl and autonomy-metric.json",
        "stages": _empty_stages(),
        "links": [],
        "cause_counts": {},
        "accounts": {},
        "source": {"path": "automation/state/core-decisions.jsonl", "age_h": None, "last_write": None},
    }


def _clamp_nonneg(n) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _build_links(totals: dict) -> list:
    """Reshape 8 fill_funnel stages into the 6-column Sankey's links.

    Every source stage's outgoing links sum to exactly that stage's n -- see
    module docstring. `refused` only appears leaving `enter` (rule-gate denials
    + failed broker placements); every other stage's shortfall is `quiet`
    (no signal / no setup / not yet exited -- not a refusal, an absence).
    """
    t = {k: _clamp_nonneg(totals.get(k)) for k in
         ("ticks", "signals", "enter", "rule_blocked", "attempted", "accepted", "filled", "exited")}
    links: list = []

    def _leg(src: str, dst_flow: str, n_total: int, n_flow: int, flow_tone: str):
        flow = min(n_flow, n_total)
        links.append({"from": src, "to": dst_flow, "n": flow, "tone": flow_tone})
        return n_total - flow

    # ticks -> signals (remainder: no signal fired -- quiet tape)
    rem = _leg("ticks", "signals", t["ticks"], t["signals"], "flow")
    if rem:
        links.append({"from": "ticks", "to": "quiet", "n": rem, "tone": "quiet"})

    # signals -> enter (remainder: signal fired, no ENTER verdict -- quiet)
    rem = _leg("signals", "enter", t["signals"], t["enter"], "flow")
    if rem:
        links.append({"from": "signals", "to": "quiet", "n": rem, "tone": "quiet"})

    # enter -> accepted, refused (rule-blocked + failed placements), quiet (dark-arm skips)
    acc_flow = min(t["accepted"], t["enter"])
    links.append({"from": "enter", "to": "accepted", "n": acc_flow, "tone": "accepted"})
    fail = _clamp_nonneg(t["attempted"] - t["accepted"])
    refused = min(t["enter"] - acc_flow, t["rule_blocked"] + fail)
    if refused:
        links.append({"from": "enter", "to": "refused", "n": refused, "tone": "refused"})
    rem = t["enter"] - acc_flow - refused
    if rem:
        links.append({"from": "enter", "to": "quiet", "n": rem, "tone": "quiet"})

    # accepted -> filled (remainder: accepted, not yet showing a broker fill)
    rem = _leg("accepted", "filled", t["accepted"], t["filled"], "accepted")
    if rem:
        links.append({"from": "accepted", "to": "quiet", "n": rem, "tone": "quiet"})

    # filled -> exited (remainder: still open at time of read)
    rem = _leg("filled", "exited", t["filled"], t["exited"], "accepted")
    if rem:
        links.append({"from": "filled", "to": "quiet", "n": rem, "tone": "quiet"})

    return links


def _aggregate_cause_counts(accounts: dict) -> dict:
    total: Counter = Counter()
    for a in accounts.values():
        why = a.get("why") or {}
        for cause, n in (why.get("cause_counts") or {}).items():
            try:
                total[cause] += int(n)
            except (TypeError, ValueError):
                pass
    return dict(total)


def _last_trading_day_before(today: str | None) -> str | None:
    """The newest ET date strictly before `today` that has a row in
    core-decisions.jsonl -- read from the TAIL only (append-only ledger, so
    the newest rows are the last bytes in the file), never a full parse.
    Returns None (never raises) if the file is missing/empty/unreadable or
    every date found is not < today."""
    path = STATE / "core-decisions.jsonl"
    try:
        size = path.stat().st_size
        if size <= 0:
            return None
        with path.open("rb") as fh:
            block = min(size, 65536)
            fh.seek(size - block)
            data = fh.read()
        lines = data.split(b"\n")
    except OSError:
        return None
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        ts = row.get("ts_et") or ""
        if len(ts) < 10:
            continue
        day = ts[:10]
        if today is None or day < today:
            return day
    return None


def _fallback_from_autonomy_metric(day: str | None) -> dict | None:
    path = STATE / "autonomy-metric.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- fail-open, this is the last resort already
        return None
    fl = raw.get("function_latest") or {}
    enters = fl.get("enters_last_trading_day")
    accepted = fl.get("orders_accepted")
    fills = fl.get("fills")
    if not any(v not in (None, 0) for v in (enters, accepted, fills)):
        return None
    trading_day = fl.get("trading_day")
    stages = [
        {"id": "ticks", "label": "Ticks", "n": None},
        {"id": "signals", "label": "Signals", "n": None},
        {"id": "enter", "label": "Enter", "n": enters},
        {"id": "accepted", "label": "Accepted", "n": accepted},
        {"id": "filled", "label": "Filled", "n": fills},
        {"id": "exited", "label": "Exited", "n": None},
    ]
    links: list = []
    enters_n = _clamp_nonneg(enters)
    accepted_n = _clamp_nonneg(accepted)
    fills_n = _clamp_nonneg(fills)
    if enters is not None and accepted is not None:
        acc_flow = min(accepted_n, enters_n)
        links.append({"from": "enter", "to": "accepted", "n": acc_flow, "tone": "accepted"})
        rem = enters_n - acc_flow
        if rem:
            links.append({"from": "enter", "to": "refused", "n": rem, "tone": "refused"})
    if accepted is not None and fills is not None:
        fill_flow = min(fills_n, accepted_n) if accepted is not None else fills_n
        links.append({"from": "accepted", "to": "filled", "n": fill_flow, "tone": "accepted"})
        rem = accepted_n - fill_flow
        if rem > 0:
            links.append({"from": "accepted", "to": "quiet", "n": rem, "tone": "quiet"})
    verdict = "DEGRADED" if any(v not in (None, 0) for v in (enters, accepted, fills)) else "IDLE"
    say = (f"FALLBACK from autonomy-metric.json (trading day {trading_day or '?'}): "
           f"{enters or 0} entered, {accepted or 0} accepted, {fills or 0} filled -- "
           f"core-decisions.jsonl had nothing for {day or 'today'} yet, so ticks/signals/"
           f"exited are unknown at this granularity (drawn NO DATA)")
    return {
        "ok": True,
        "path": "automation/state/autonomy-metric.json",
        "stamp_et": raw.get("computed_at"),
        "day": day,
        "live": False,
        "session_label": None,
        "verdict": verdict,
        "say": say,
        "stages": stages,
        "links": links,
        "cause_counts": {},
        "accounts": {},
        "source": {"path": "automation/state/autonomy-metric.json", "age_h": None,
                    "last_write": raw.get("computed_at")},
    }


def build(day: str | None = None) -> dict:
    """Build the routing-map payload. Fail-open -- never raises."""
    try:
        return _build_inner(day)
    except Exception as exc:  # noqa: BLE001 -- a bad tile must never cost J the rest of the page
        out = _no_data(day)
        out["say"] = f"NO DATA, funnel builder raised: {exc}"[:200]
        return out


def _build_inner(day: str | None) -> dict:
    try:
        from et_clock import et_now, is_market_hours
        now = et_now()
        live = is_market_hours()
    except Exception:  # noqa: BLE001
        import datetime as _dt
        now = _dt.datetime.now()
        live = False

    the_day = day or now.strftime("%Y-%m-%d")

    import fill_funnel  # local import: keep this module importable even if the sibling
                         # ledger reader has a transient import error at build time

    funnel = fill_funnel.compute_funnel(the_day)
    totals = funnel.get("totals") or {}
    accounts_raw = funnel.get("accounts") or {}
    session_label = None

    # ROUND-2 FIX (2026-09-04): pre-market/holiday/fresh-boot reads land here with
    # 0 ticks for TODAY every time (the ledger simply has nothing yet), and used to
    # fall straight to autonomy-metric.json -- which only carries enter/accepted/
    # fills, so ticks/signals/exited drew "no data" even though the LAST closed
    # session has all six numbers sitting in core-decisions.jsonl already. Try the
    # newest day strictly before `the_day` that the ledger actually has rows for
    # FIRST; only fall to autonomy-metric (fewer stages) or NO DATA (none) if that
    # comes up empty too. `the_day`/verdict/say below all move to the found day
    # together so nothing here mixes two different days' numbers.
    if not totals.get("ticks"):
        last_day = _last_trading_day_before(the_day)
        if last_day:
            alt_funnel = fill_funnel.compute_funnel(last_day)
            alt_totals = alt_funnel.get("totals") or {}
            if alt_totals.get("ticks"):
                funnel, totals, accounts_raw = alt_funnel, alt_totals, alt_funnel.get("accounts") or {}
                the_day = last_day
                session_label = f"Last session {last_day}, closed"

    if not totals.get("ticks"):
        fb = _fallback_from_autonomy_metric(the_day)
        if fb is not None:
            fb["live"] = live
            return fb
        out = _no_data(the_day)
        out["say"] = ("NO DATA, looked for core-decisions.jsonl and autonomy-metric.json "
                       f"({the_day}: 0 ticks in the ledger, no usable function_latest)")
        return out

    stages = [{"id": sid, "label": lbl, "n": _clamp_nonneg(totals.get(sid))}
              for sid, lbl in _STAGE_LABELS]
    links = _build_links(totals)

    accounts = {}
    for name, a in accounts_raw.items():
        accounts[name] = {
            "ticks": _clamp_nonneg(a.get("ticks")),
            "signals": _clamp_nonneg(a.get("signals")),
            "enter": _clamp_nonneg(a.get("enter")),
            "accepted": _clamp_nonneg(a.get("accepted")),
            "filled": _clamp_nonneg(a.get("filled")),
            "exited": _clamp_nonneg(a.get("exited")),
        }

    verdict = str(funnel.get("verdict") or "off")
    flags = funnel.get("flags") or []
    say = (f"{verdict}: {stages[0]['n']} ticks -> {stages[1]['n']} signals -> "
           f"{stages[2]['n']} enter -> {stages[3]['n']} accepted -> "
           f"{stages[4]['n']} filled -> {stages[5]['n']} exited, {len(accounts)} account(s)")
    if session_label:
        say = f"{the_day} ({session_label}): " + say
    if flags:
        say += " | " + str(flags[0])[:160]

    core_path = (funnel.get("sources") or {}).get("core")
    age_h = None
    last_write = funnel.get("generated_at_et")
    try:
        import datetime as _dt
        if core_path and Path(core_path).exists():
            mtime = _dt.datetime.fromtimestamp(Path(core_path).stat().st_mtime)
            age_h = round((now - mtime).total_seconds() / 3600.0, 2)
    except Exception:  # noqa: BLE001
        age_h = None

    return {
        "ok": True,
        "path": _posix(core_path) if core_path else "automation/state/core-decisions.jsonl",
        "stamp_et": funnel.get("generated_at_et"),
        "day": the_day,
        "live": bool(live),
        "session_label": session_label,
        "verdict": verdict,
        "say": say,
        "stages": stages,
        "links": links,
        "cause_counts": _aggregate_cause_counts(accounts_raw),
        "accounts": accounts,
        "source": {"path": _posix(core_path) if core_path else "automation/state/core-decisions.jsonl",
                    "age_h": age_h, "last_write": last_write},
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, default=str))
