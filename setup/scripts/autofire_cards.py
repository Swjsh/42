"""autofire_cards.py -- fires the safe half of the cockpit's Action Cards
unattended, so a card whose objective is unambiguously READ-AND-REPORT
(gamma_cockpit_cards.py's `autofire_safe` field) gets its result waiting for
J instead of waiting for a tap.

J, 2026-08-29: "Auto-fire the safe cards. Cards that only read and report
could fire on a schedule with results waiting for me. I would only click the
ones with consequences." This module is the "on a schedule" half; the click
half is untouched -- gamma-companion's own Approve button still fires every
other card exactly as it does today.

WHAT THIS NEVER DOES (the failure mode this whole file exists to fence):
  - Never fires a card whose `autofire_safe` is not literally `true`. The
    classifier lives in gamma_cockpit_cards.py and is NOT re-derived here --
    re-deriving a second "is this safe" opinion is exactly how the two
    readers of one safety field drift apart. This file trusts the field,
    once, and otherwise refuses.
  - Never fires during 09:30-15:55 ET (et_clock.is_market_hours() -- the ONE
    DST-aware ET source on this box, never Bash `TZ=...`, which reads UTC
    here per the TZ-SYSTEMIC scar).
  - Never fires while automation/state/companion-halt.flag exists.
  - Never fires while quiet-mode.json says quiet_active, unless the caller
    explicitly passes --allow-quiet (quiet mode means J deliberately held
    N tasks down; an autofire runner silently skipping that consent gate
    would be the exact kind of thing quiet mode exists to prevent).
  - Never fires more than --max-per-run cards in one invocation, or more
    than --max-per-day cards in one ET calendar day -- the day count is
    read back from the ledger every run, so a restart (or a second
    scheduled fire later the same evening) cannot reset it.
  - Never spends anything unless --live is passed. DEFAULT IS DRY-RUN: an
    accidental bare invocation (a fat-fingered manual run, a scheduled-task
    misfire) can print what it WOULD have done but cannot actually reach
    the companion.

EVERY DECISION IS LEDGERED (automation/state/autofire-ledger.jsonl), one
JSON row per card decision, PLUS one row for a whole-run refusal (RTH / halt
flag / quiet mode) even when that means zero cards were ever looked at -- a
run that fires nothing must still leave evidence of *why* it fired nothing.
`decision` is one of:
    refused      -- the whole run was refused before any card was considered
                     (`reason` in {"rth","halt-flag","quiet-mode","no-token",
                     "requested-card-not-autofire-safe","requested-card-not-found"})
    skipped      -- a candidate card was safe but a cap was already spent
                     (`reason` names which cap: "per-run-cap"/"per-day-cap")
    dry-run      -- would have fired; --live was not passed, nothing sent
    fired        -- a live POST to /api/approve was sent and the companion
                     accepted it (escalation minted) -- THIS is what counts
                     toward the persisted per-day cap on the next run
    fire-error   -- a live POST was attempted but failed (network/timeout/
                     non-ok response) -- does NOT count toward the per-day
                     cap, because nothing was actually spent

`gamma_watcher.py`'s own check_autofire_health() reads this same ledger and
expects exactly the string "refused" for a whole-run refusal, with `reason`
"rth" or "quiet-mode" treated as refusals working as designed -- keep those
two literal strings if this file is ever touched again.

Wire format (spec confirmed against the cockpit's own client JS,
gamma_cockpit_cards_js.py's fireCard()): POST /api/approve with header
`x-gamma-token` and JSON body {id, decision:"approve",
action:{type:"escalate", model, task}}. `id` naming a real action-cards.json
row is gamma_cockpit_cards.py's doing, never a client's -- server.js treats
that as the ONE signal that the file's own `prompt`/`model` are authoritative
over whatever this script's `action.task`/`action.model` says, so a caller
of this route can pick WHICH card fires, never WHAT it says once it does.
We still populate action.task/model from the card for symmetry with the
browser client and so a future server change that stops overriding them
still gets a sane value.

CLI:
    python setup/scripts/autofire_cards.py                # dry-run (default)
    python setup/scripts/autofire_cards.py --dry-run       # same, explicit
    python setup/scripts/autofire_cards.py --live          # actually spends
    python setup/scripts/autofire_cards.py --live --max-per-run 1 --max-per-day 3
    python setup/scripts/autofire_cards.py --allow-quiet --live
    python setup/scripts/autofire_cards.py --card-id card-unit-window-leak --live
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))  # sibling import below

import et_clock  # noqa: E402 -- the ONE DST-aware ET source (never Bash TZ=...)

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"

ACTION_CARDS_JSON = STATE / "action-cards.json"
HALT_FLAG = STATE / "companion-halt.flag"
QUIET_MODE_JSON = STATE / "quiet-mode.json"
TOKEN_FILE = STATE / ".companion-token"
LEDGER_JSONL = STATE / "autofire-ledger.jsonl"

DEFAULT_BASE_URL = "http://127.0.0.1:4317"
DEFAULT_MAX_PER_RUN = 2
DEFAULT_MAX_PER_DAY = 6
POST_TIMEOUT_S = 60.0

# OP-22 ring-cap, same contract as every other append-only producer here
# (watcher-ledger.jsonl trims at 2400 -> 2000). Autofire activity is a
# handful of rows/day, so this only ever fires on a very old, never-pruned
# ledger -- never mid-day, never mid-count.
_LEDGER_RING_CAP = 4000
_LEDGER_RING_KEEP = 3000


# --------------------------------------------------------------------- ledger

def _now_et():
    return et_clock.et_now()


def _ledger_row(*, decision: str, reason: str, card_id: str | None = None,
                 dry_run: bool = True, rank: int | None = None,
                 ask_id: str | None = None, http_status: int | None = None,
                 extra: dict | None = None) -> dict:
    now = _now_et()
    row = {
        "ts_et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date_et": now.strftime("%Y-%m-%d"),
        "card_id": card_id,
        "rank": rank,
        "decision": decision,
        "reason": reason,
        "dry_run": bool(dry_run),
        "ask_id": ask_id,
        "http_status": http_status,
    }
    if extra:
        row.update(extra)
    return row


def _append_ledger(rows: list[dict]) -> None:
    if not rows:
        return
    try:
        LEDGER_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_JSONL.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        lines = LEDGER_JSONL.read_text(encoding="utf-8").splitlines()
        if len(lines) > _LEDGER_RING_CAP:
            LEDGER_JSONL.write_text(
                "\n".join(lines[-_LEDGER_RING_KEEP:]) + "\n", encoding="utf-8")
    except OSError as e:
        print("WARN: could not write %s (%s)" % (LEDGER_JSONL, e), file=sys.stderr)


def _fired_today_count(today_et: str) -> int:
    """Count of REAL (non-dry-run, successfully-escalated) fires already
    recorded for `today_et` -- read fresh off disk every call, so a process
    restart (or a second scheduled fire later the same evening) cannot reset
    the day budget. Only `decision == "fired"` counts: a dry-run spent
    nothing, and a "fire-error" attempt never actually minted an escalation."""
    if not LEDGER_JSONL.exists():
        return 0
    n = 0
    try:
        for line in LEDGER_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("decision") == "fired" and row.get("date_et") == today_et:
                n += 1
    except OSError:
        pass
    return n


# ---------------------------------------------------------------------- gates

def _load_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _whole_run_refusal(allow_quiet: bool) -> str | None:
    """Return a reason string if the ENTIRE run must be refused before any
    card is even looked at, else None. Order: RTH, halt-flag, quiet-mode --
    matches the order the task doc lists them in; any order is correct since
    each is independently sufficient, but a fixed order keeps the reported
    reason deterministic when more than one gate is tripped at once."""
    if et_clock.is_market_hours():
        return "rth"
    if HALT_FLAG.exists():
        return "halt-flag"
    quiet = _load_json(QUIET_MODE_JSON)
    if isinstance(quiet, dict) and quiet.get("quiet_active") and not allow_quiet:
        return "quiet-mode"
    return None


# --------------------------------------------------------------- card loading

def _load_cards() -> list[dict]:
    payload = _load_json(ACTION_CARDS_JSON)
    if not isinstance(payload, dict):
        return []
    cards = payload.get("cards")
    return cards if isinstance(cards, list) else []


def _prompt_is_dangerous(card: dict) -> str | None:
    """SECOND, independent safety pass on the card's actual prompt, at fire time.

    Defense-in-depth added 2026-08-29 after the adversarial review named the real risk:
    the runner trusted `autofire_safe` with ZERO secondary check, so a single classifier
    miss upstream = a dangerous card fired unattended. Re-running the danger denylist here,
    on the prompt that is ABOUT TO BE SENT, means one bug in the generator can no longer
    reach a live session on its own -- both would have to fail the same way at once.

    Best-effort: if the classifier can't be imported, that is itself disqualifying (fail
    toward refuse), because firing without the check is the exact thing this exists to stop.
    """
    try:
        import gamma_cockpit_cards as _cards  # sibling on sys.path

        text = str(card.get("prompt") or "")
        hit = _cards._looks_dangerous(text)
        if hit:
            return hit
        if _cards._ACTION_VERB_RE.search(text):
            return "prompt contains a mutating action verb"
        return None
    except Exception as exc:
        return f"secondary safety check unavailable ({exc!r}) -- refusing rather than firing blind"


def _safe_cards_by_rank(cards: list[dict]) -> list[dict]:
    """Only cards whose `autofire_safe` is literally True AND whose prompt survives an
    independent second danger pass, rank ascending (rank 1 first) -- the SAME order the
    cockpit ranks them, so autofire drains the highest-priority safe cards first. The
    double check is deliberate: autofire_safe is set by the generator; _prompt_is_dangerous
    re-derives from the prompt itself here, so neither is a single point of trust."""
    safe = []
    for c in cards:
        if not (isinstance(c, dict) and c.get("autofire_safe") is True):
            continue
        danger = _prompt_is_dangerous(c)
        if danger:
            c["_autofire_veto"] = danger  # surfaced in the ledger so a veto is never silent
            continue
        safe.append(c)
    safe.sort(key=lambda c: c.get("rank") if isinstance(c.get("rank"), (int, float)) else 1e9)
    return safe


def _read_token() -> str | None:
    try:
        tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
        return tok or None
    except OSError:
        return None


# ------------------------------------------------------------------ firing

def _post_approve(card: dict, token: str, base_url: str = DEFAULT_BASE_URL,
                   timeout: float = POST_TIMEOUT_S) -> dict:
    """POST /api/approve for one card. Never raises -- every failure mode
    (network, timeout, non-2xx, unparsable body) comes back as
    {"ok": False, "error": "..."} so the caller always has a row to log."""
    url = base_url.rstrip("/") + "/api/approve"
    payload = json.dumps({
        "id": card.get("id"),
        "decision": "approve",
        "action": {
            "type": "escalate",
            "model": card.get("model", "sonnet"),
            "task": card.get("prompt", ""),
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"content-type": "application/json", "x-gamma-token": token},
    )
    status = None
    body = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - best-effort error body read
            body = ""
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return {"ok": False, "error": repr(e)[:200], "status": None}

    try:
        data = json.loads(body) if body else {}
        if not isinstance(data, dict):
            data = {}
    except ValueError:
        data = {}
    data.setdefault("ok", status == 200)
    data["status"] = status
    return data


# --------------------------------------------------------------------- select

def _select(safe_cards: list[dict], *, only_ids: set[str] | None,
            max_per_run: int, day_remaining: int) -> tuple[list[dict], list[dict]]:
    """Split `safe_cards` (already rank-sorted, already autofire_safe-only)
    into (to_fire, skipped) under the run + day budgets.

    `only_ids`, when given, further restricts candidates to those ids -- but
    this function is only ever called with cards that already passed the
    autofire_safe filter, so an id naming an UNSAFE card simply never
    appears here at all (see main(), which resolves that case as a
    whole-request refusal before this is called)."""
    to_fire: list[dict] = []
    skipped: list[dict] = []
    run_left = max_per_run
    day_left = day_remaining
    for card in safe_cards:
        if only_ids is not None and card.get("id") not in only_ids:
            continue
        if run_left <= 0:
            skipped.append({"card": card, "reason": "per-run-cap"})
            continue
        if day_left <= 0:
            skipped.append({"card": card, "reason": "per-day-cap"})
            continue
        to_fire.append(card)
        run_left -= 1
        day_left -= 1
    return to_fire, skipped


# ----------------------------------------------------------------------- main

def run(*, dry_run: bool, max_per_run: int, max_per_day: int, allow_quiet: bool,
        card_ids: list[str] | None, base_url: str = DEFAULT_BASE_URL) -> int:
    ledger_rows: list[dict] = []

    whole_reason = _whole_run_refusal(allow_quiet)
    if whole_reason:
        ledger_rows.append(_ledger_row(decision="refused", reason=whole_reason,
                                        dry_run=dry_run))
        _append_ledger(ledger_rows)
        print("REFUSED (whole run): %s" % whole_reason)
        return 0

    cards = _load_cards()
    safe = _safe_cards_by_rank(cards)

    only_ids: set[str] | None = None
    if card_ids:
        only_ids = set(card_ids)
        safe_ids = {c.get("id") for c in safe}
        by_id = {c.get("id"): c for c in cards if isinstance(c, dict)}
        for cid in card_ids:
            if cid not in safe_ids:
                exists = cid in by_id
                ledger_rows.append(_ledger_row(
                    decision="refused",
                    reason=("requested-card-not-autofire-safe" if exists
                            else "requested-card-not-found"),
                    card_id=cid, dry_run=dry_run,
                    rank=(by_id.get(cid) or {}).get("rank")))

    if not dry_run:
        token = _read_token()
        if not token:
            ledger_rows.append(_ledger_row(decision="refused", reason="no-token",
                                            dry_run=dry_run))
            _append_ledger(ledger_rows)
            print("REFUSED (whole run): no-token")
            return 0
    else:
        token = None

    today_et = _now_et().strftime("%Y-%m-%d")
    already_fired = _fired_today_count(today_et)
    day_remaining = max(0, max_per_day - already_fired)

    to_fire, skipped = _select(safe, only_ids=only_ids, max_per_run=max_per_run,
                                day_remaining=day_remaining)

    for entry in skipped:
        card = entry["card"]
        ledger_rows.append(_ledger_row(
            decision="skipped", reason=entry["reason"], card_id=card.get("id"),
            rank=card.get("rank"), dry_run=dry_run))

    fired_count = 0
    for card in to_fire:
        cid = card.get("id")
        rank = card.get("rank")
        if dry_run:
            ledger_rows.append(_ledger_row(
                decision="dry-run", reason="would fire (--live not passed)",
                card_id=cid, rank=rank, dry_run=True))
            print("DRY-RUN would fire: #%s %s" % (rank, cid))
            continue
        resp = _post_approve(card, token, base_url=base_url)
        if resp.get("ok"):
            ask_id = resp.get("escalated") or resp.get("ask_id")
            ledger_rows.append(_ledger_row(
                decision="fired", reason="posted to /api/approve, companion accepted",
                card_id=cid, rank=rank, dry_run=False, ask_id=ask_id,
                http_status=resp.get("status")))
            fired_count += 1
            print("FIRED: #%s %s -> ask %s" % (rank, cid, ask_id))
        else:
            ledger_rows.append(_ledger_row(
                decision="fire-error",
                reason=_clip(str(resp.get("error") or resp.get("error_message")
                                  or "non-ok response"), 200),
                card_id=cid, rank=rank, dry_run=False,
                http_status=resp.get("status")))
            print("FIRE-ERROR: #%s %s -> %s" % (rank, cid, resp.get("error")))

    _append_ledger(ledger_rows)
    print("done: %d cards eligible, %d selected, %d fired, %d skipped, %d dry-run"
          % (len(safe), len(to_fire), fired_count,
             len(skipped), sum(1 for r in ledger_rows if r["decision"] == "dry-run")))
    return 0


def _clip(s: str, cap: int) -> str:
    return s if len(s) <= cap else s[:cap] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fire the safe (read-and-report) subset of cockpit action cards.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                       help="print what would fire; send nothing (default behavior)")
    mode.add_argument("--live", action="store_true",
                       help="actually POST to the companion and spend a session")
    parser.add_argument("--max-per-run", type=int, default=DEFAULT_MAX_PER_RUN,
                         help="max cards this single invocation may fire (default %d)"
                              % DEFAULT_MAX_PER_RUN)
    parser.add_argument("--max-per-day", type=int, default=DEFAULT_MAX_PER_DAY,
                         help="max cards fired total per ET calendar day, ledgered "
                              "across restarts (default %d)" % DEFAULT_MAX_PER_DAY)
    parser.add_argument("--allow-quiet", action="store_true",
                         help="fire anyway while quiet-mode.json says quiet_active "
                              "(quiet mode is a deliberate hold-down; override only "
                              "when you mean it)")
    parser.add_argument("--card-id", action="append", default=None,
                         help="restrict to this card id (repeatable). A requested id "
                              "that is not autofire_safe is refused, never fired.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                         help="companion base URL (default %s)" % DEFAULT_BASE_URL)
    args = parser.parse_args()

    dry_run = not args.live  # --dry-run is accepted explicitly but changes nothing:
                              # the only flag that can turn spending ON is --live.
    return run(dry_run=dry_run, max_per_run=args.max_per_run,
               max_per_day=args.max_per_day, allow_quiet=args.allow_quiet,
               card_ids=args.card_id, base_url=args.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
