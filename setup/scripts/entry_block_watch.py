"""entry_block_watch.py -- THE ESCALATION CORD (WS4, 2026-07-27 night build).

THE INCIDENT: 2026-07-27 09:46-09:50 ET the engine scored J's setup 9/10 with real
detections (level_rejection + confluence @744.9, bear) and was blocked by ONE filter
(5, ribbon not BEAR-stacked). J found out hours later, after an $8 move. Commit
3ced7457 ("make a no-trade tick explain itself") added bear_triggers_raw /
bull_triggers_raw / bear_blockers / bull_blockers / levels_active to every
core-decisions.jsonl row -- rows from 2026-07-28 onward carry them; older rows don't.
This module closes the loop those fields opened: it WATCHES the ledger live and tells
J the moment a high-quality, missed setup shows up -- not hours later.

DETERMINISTIC, $0/tick, NO LLM anywhere in the detection path. Pure stdlib.

TRIPWIRE (per side, independently):
  bear: bear_score >= 8  AND  bear_triggers_raw intersects {level_rejection,
        fhh_level_rejection, confluence}  AND  verdict != "ENTER_BEAR"
  bull: bull_score >= 9  AND  bull_triggers_raw intersects {level_reclaim,
        confluence, sequence_reclaim}  AND  verdict != "ENTER_BULL"
  (bull threshold is higher and its trigger set differs from bear's -- bull is less
  validated, per CLAUDE.md OP-16; a row missing the *_triggers_raw key at all -- i.e.
  every row before 2026-07-28 -- can never satisfy the trigger check and therefore
  never qualifies. This is not a special case, it falls straight out of `_qualifies`'s
  isinstance(triggers_raw, list) guard -- the COMPATIBILITY TEST this module ships with.)

A row's `account` field is "safe" or "bold" -- both tick roughly once a minute, wired
independently since Safe/Bold run different params.json (different filter thresholds
are possible even on the same underlying tape), so episodes are tracked PER
(account, side), not merged. Worst case a genuine miss that both accounts see burns
2 of the 3 daily alerts -- disclosed, not hidden; see the module report this shipped
with for the alternative considered (minute-level cross-account dedup) and why it was
rejected as needless complexity for a v1.

DEBOUNCE / EPISODE LIFECYCLE (per account+side key):
  - >=2 CONSECUTIVE qualifying ticks required before firing (a single qualifying tick
    resets to 0 on the very next non-qualifying tick -- kills one-bar noise).
  - Exactly ONE alert (or ONE suppression) per episode, at the moment the 2nd
    consecutive qualifying tick lands.
  - An alerted (or suppressed) episode stays "resolved" -- no re-fire -- until the
    condition clears for >=5 CONSECUTIVE ticks, at which point the episode resets and
    a fresh future run can fire again.
  - Max 3 real alerts per ET calendar day (global across all account+side keys) --
    alert fatigue is L189. A 4th-episode trigger point logs one SUPPRESSED line
    instead of firing.

DELIVERY: ONE spoken line via the EXISTING Kokoro TTS pipeline -- REUSED verbatim from
daily_brief.py's render_voice() (setup/.tts-venv + gamma_speak.py --text-file) and
discord-bridge.py's outbox `file`-attachment convention (queue_discord_delivery's exact
row shape: {queued_at, content, source, file}). No new TTS stack, no new Discord path.
Also best-effort (fail-open, never blocking) appends a `entry_block_watch` key under
dashboard-dialogue.json's existing `agents` dict IF that file exists -- additive only,
never touches any other producer's keys (that file has multiple concurrent writers;
this is deliberately the smallest possible footprint on it).

LEVEL TEXT CAVEAT (found during build, see report): core-decisions.jsonl's
`trigger_level_exact` is ONLY populated for the WINNING routed side (engine_cli.py's
_derive_routing returns (None, [], None) when NEITHER side passes) -- so for exactly
the ticks this watcher cares about (a side that detected but did NOT win/route), that
field is always None or belongs to the OTHER side. Using it here would misattribute a
price. Per heartbeat_core.py's own documented contract ("fall back to the proximity
heuristic exit_manager.nearest_active_level, never guess"), this module reuses that
EXACT function (automation/state/fleet/exit_manager.py) against levels_active + spy to
describe "at $X" -- imported, not reimplemented.

FILTER NUMBER -> NAME (verified against backtest/lib/filters.py, NOT guessed):
  BEAR numbering (score_bearish_setup, lines ~1406-1671): 5=ribbon, 6=spread,
    7=volume divergence, 8=VIX, 9=volume (breakdown_bar_bearish, vol-gated), 10=triggers
    (HTF+trigger-count), 11=sweep.
  BULL numbering is SHIFTED (score_bullish_setup, lines ~1142-1259): 5=ribbon, 8=VIX
    (soft), 9=VIX (hard cap), 10=volume (buyer_pressure_bar_v11), 11=triggers, 12=sweep.
  The orchestrator's brief gave bear's numbers (5/8/9/10/11=ribbon/VIX/volume/triggers/
  sweep) -- verified to match bear exactly. Bull's own numbers were derived from the
  live filters.py source (not assumed to be the same scale) so a bull alert never
  mislabels a blocker. Both maps live in FILTER_LABELS below.

WATERMARK: automation/state/.entry-block-watch.json -- BYTE-OFFSET tail (not a full
re-read / not a line-count re-scan) because core-decisions.jsonl is already 20+MB and
growing daily; re-reading the whole file every 2 minutes would get slower every month.
`byte_offset` persists ACROSS calendar-day rollovers (only `alerts_today` + the
per-episode debounce state reset at ET midnight) -- resetting the offset too would
silently re-scan the entire multi-month ledger every morning.

CLI:
  python entry_block_watch.py             # normal fire (every 2 min, 09:30-16:00 ET)
  python entry_block_watch.py --dry-run   # detect + print, fire/deliver/persist nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
WATERMARK = STATE / ".entry-block-watch.json"
OUTBOX = STATE / "discord-outbox.jsonl"
DASHBOARD_DIALOGUE = STATE / "dashboard-dialogue.json"
TTS_VENV_PY = REPO / "setup" / ".tts-venv" / "Scripts" / "python.exe"
SPEAK_SCRIPT = REPO / "setup" / "scripts" / "gamma_speak.py"

sys.path.insert(0, str(REPO / "setup" / "scripts"))
try:
    from et_clock import et_now as _et_now, ET_TZ as _ET_TZ
except Exception:  # noqa: BLE001 -- fail-open fallback, mirrors conductor_wake_watch.py
    def _et_now():
        return dt.datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)
    _ET_TZ = None

# Reuse the SAME proximity-fallback level lookup exit_manager already documents as the
# canonical answer for "no exact trigger level available" -- not reimplemented (see
# module docstring's LEVEL TEXT CAVEAT).
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))
try:
    from exit_manager import nearest_active_level as _nearest_active_level
except Exception:  # noqa: BLE001 -- fail-open: alert still fires, just with a plainer level phrase
    def _nearest_active_level(prices, spot, side, max_distance: float = 2.0):
        return None

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

DEBOUNCE_TICKS = 2      # consecutive qualifying ticks required before firing
CLEAR_TICKS = 5         # consecutive non-qualifying ticks required to close an episode
MAX_ALERTS_PER_DAY = 3  # global cap across every (account, side) key -- L189

# Verified against backtest/lib/filters.py's score_bearish_setup / score_bullish_setup
# (see module docstring FILTER NUMBER -> NAME section). Bear matches the orchestrator's
# brief verbatim; bull is independently derived from the live source, NOT copy-pasted.
FILTER_LABELS: dict[str, dict[int, str]] = {
    "bear": {
        1: "time gate", 2: "news", 3: "budget", 4: "day-trades", 5: "ribbon",
        6: "spread", 7: "volume divergence", 8: "VIX", 9: "volume",
        10: "triggers", 11: "sweep",
    },
    "bull": {
        1: "time gate", 2: "news", 3: "budget", 4: "day-trades", 5: "ribbon",
        6: "spread", 7: "volume divergence", 8: "VIX (soft)", 9: "VIX (hard cap)",
        10: "volume", 11: "triggers", 12: "sweep",
    },
}

SIDE_CONFIG: dict[str, dict] = {
    "bear": {
        "score_field": "bear_score", "triggers_field": "bear_triggers_raw",
        "blockers_field": "bear_blockers", "threshold": 8, "max_score": 10,
        "verdict_ok": "ENTER_BEAR", "occ_side": "P",
        "level_tied_triggers": frozenset({"level_rejection", "fhh_level_rejection", "confluence"}),
    },
    "bull": {
        "score_field": "bull_score", "triggers_field": "bull_triggers_raw",
        "blockers_field": "bull_blockers", "threshold": 9, "max_score": 11,
        "verdict_ok": "ENTER_BULL", "occ_side": "C",
        "level_tied_triggers": frozenset({"level_reclaim", "confluence", "sequence_reclaim"}),
    },
}

ACCOUNT_LABEL = {"safe": "Safe", "bold": "Bold"}


def _safe_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# watermark
# --------------------------------------------------------------------------- #
def _default_watermark() -> dict:
    return {"schema": "entry-block-watch-v1", "byte_offset": 0, "date_et": None,
            "alerts_today": 0, "episodes": {}}


def _load_watermark(path: Path) -> dict:
    default = _default_watermark()
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    if not isinstance(data, dict):
        return default
    for k, v in default.items():
        data.setdefault(k, v)
    if not isinstance(data.get("episodes"), dict):
        data["episodes"] = {}
    return data


def _save_watermark(path: Path, wm: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(wm, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _fresh_episode() -> dict:
    return {"consecutive_qualify": 0, "consecutive_clear": 0, "resolved": False}


# --------------------------------------------------------------------------- #
# byte-offset tail read (fast on a large, ever-growing append-only ledger)
# --------------------------------------------------------------------------- #
def _read_new_rows(path: Path, byte_offset: int) -> tuple[list[dict], int, int]:
    """Returns (parsed_dict_rows, new_byte_offset, malformed_count).
    Never raises -- missing file / shrunk file (rotation) / decode errors all degrade
    to a safe no-op or a from-scratch tail, never a crash. A trailing line with no
    newline yet (mid-write) is held back untouched for the next tick."""
    if not path.exists():
        return [], byte_offset, 0
    try:
        size = path.stat().st_size
    except OSError:
        return [], byte_offset, 0
    if size < byte_offset:
        byte_offset = 0  # rotated/truncated shorter than our watermark -- restart tail
    if size == byte_offset:
        return [], byte_offset, 0  # fast path: nothing new, zero bytes read

    try:
        with path.open("rb") as fh:
            fh.seek(byte_offset)
            chunk = fh.read()
    except OSError:
        return [], byte_offset, 0

    text = chunk.decode("utf-8", errors="replace")
    ends_clean = text.endswith("\n")
    lines = text.split("\n")
    if ends_clean:
        if lines and lines[-1] == "":
            lines.pop()
    else:
        lines.pop()  # partial trailing line -- not yet fully flushed, hold it back

    rows: list[dict] = []
    malformed = 0
    consumed_bytes = 0
    for raw in lines:
        consumed_bytes += len(raw.encode("utf-8")) + 1  # +1 for the '\n'
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except (ValueError, TypeError):
            malformed += 1
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        else:
            malformed += 1

    return rows, byte_offset + consumed_bytes, malformed


# --------------------------------------------------------------------------- #
# tripwire
# --------------------------------------------------------------------------- #
def _risk_gate_denied(row: dict) -> bool:
    """D8 (2026-08-06): True when this row's ENTER verdict was refused by the risk gate --
    the order NEVER reached the broker even though the engine formed the verdict. Read from
    both surfaces the engine writes it to (top-level `action` and `exec.status`; the real
    2026-08-04 rows carry it on both)."""
    if str(row.get("action") or "").startswith("RISK_DENY"):
        return True
    ex = row.get("exec")
    return isinstance(ex, dict) and str(ex.get("status") or "").startswith("RISK_DENY")


def _qualifies(row: dict, side: str) -> bool:
    """True iff `row` is a high-quality, level-tied `side` setup that the engine did
    NOT enter this tick. Old-shape rows (no *_triggers_raw key -- everything before
    2026-07-28) fall straight through the isinstance guard to False: THE
    COMPATIBILITY TEST this module ships with, not a special case.

    D8 FIX (2026-08-06): a row whose verdict IS ENTER_* but whose `action`/`exec.status`
    is a RISK_DENY_* now QUALIFIES. The old bare verdict check read "verdict==ENTER_BULL"
    as "the engine took it" -- but a risk-gate denial means NO order reached the broker,
    which is exactly the missed-high-quality-setup class this watcher exists to alarm on.
    Real cost of the blindness: 2026-08-04, 21 consecutive RISK_DENY_PDT rows on bold
    (verdict=ENTER_BULL, bull_score 11/11 tier ELITE, level_reclaim+confluence -- passing
    every other check in this function) were structurally invisible; J learned from the
    EOD, not from the escalation cord. Guard: test_entry_block_watch_risk_deny_2026_08_06.py."""
    cfg = SIDE_CONFIG[side]
    score = row.get(cfg["score_field"])
    if not isinstance(score, (int, float)) or score < cfg["threshold"]:
        return False
    triggers_raw = row.get(cfg["triggers_field"])
    if not isinstance(triggers_raw, list):
        return False
    if not any(t in cfg["level_tied_triggers"] for t in triggers_raw):
        return False
    if row.get("verdict") == cfg["verdict_ok"] and not _risk_gate_denied(row):
        return False  # the engine DID take it (order actually attempted) -- not a miss
    return True


def _level_phrase(row: dict, side: str) -> str:
    """"at $X" using the SAME proximity fallback exit_manager already documents as
    correct for "no exact trigger level available" (see module docstring). Never
    trusts trigger_level_exact here -- that field belongs to the WINNING side only,
    and the side this module alerts on is, by definition, the side that did NOT win
    routing this tick."""
    spy = row.get("spy")
    levels_active = row.get("levels_active")
    level = None
    if isinstance(spy, (int, float)) and isinstance(levels_active, list) and levels_active:
        try:
            level = _nearest_active_level(levels_active, spy, SIDE_CONFIG[side]["occ_side"])
        except Exception:  # noqa: BLE001 -- fail-open, fall back to spot below
            level = None
    if isinstance(level, (int, float)):
        return f"at {level:.2f}"
    if isinstance(spy, (int, float)):
        return f"near {spy:.2f}"
    return ""


def _blocker_phrase(row: dict, side: str) -> str:
    # D8 (2026-08-06): a risk-gate denial must name ITSELF, not fall through to the
    # "other side won" phrase (the 08-04 PDT rows were verdict=ENTER_BULL with no filter
    # blockers -- the old fallthrough would have voiced a false routing story).
    if _risk_gate_denied(row):
        ex = row.get("exec") if isinstance(row.get("exec"), dict) else {}
        code = str(row.get("action") or ex.get("status") or "RISK_DENY")
        why = str(ex.get("reason") or "").strip()
        return f"Risk gate refused the order ({code})" + (f": {why}." if why else ".")
    cfg = SIDE_CONFIG[side]
    labels = FILTER_LABELS[side]
    blockers = row.get(cfg["blockers_field"])
    names = [labels.get(b, f"filter {b}") for b in blockers] if isinstance(blockers, list) else []
    if names:
        return "Blocker: " + " and ".join(names) + "."
    verdict = str(row.get("verdict") or "")
    if verdict.startswith("ENTER_"):
        other = "bull" if side == "bear" else "bear"
        return f"The {other} side won the tick instead."
    return "No structural blocker logged this tick -- lost routing."


def compose_alert_text(row: dict, side: str) -> str:
    cfg = SIDE_CONFIG[side]
    score = row.get(cfg["score_field"])
    triggers_raw = row.get(cfg["triggers_field"]) or []
    trig_phrase = " plus ".join(t.replace("_", " ") for t in triggers_raw) or "an unnamed trigger"
    account = ACCOUNT_LABEL.get(row.get("account"), str(row.get("account") or "?"))
    return (
        f"Gamma here. The engine sees a {score} out of {cfg['max_score']} {side} setup "
        f"{_level_phrase(row, side)} on {account} -- {trig_phrase} -- and is not taking it. "
        f"{_blocker_phrase(row, side)} "
        # FORBIDDEN FRAMING FIX (J 2026-08-31): this string used to read
        # "J, say the word to arm it." -- a permission-question on PAPER work, which is
        # the exact anti-pattern OP-0 / OP-11 ban. Paper gates are Gamma's call to change
        # via the eval-first ladder (OP-11), never J's to authorise by voice; the only
        # things that route to J are live-money arming, secrets, irreversible external
        # actions, and genuine doctrine forks. The alert's job is to REPORT a refusal and
        # its cost, not to solicit an override.
        "Logged for gate review; no action needed from you."
    ).strip()


# --------------------------------------------------------------------------- #
# delivery -- reused verbatim from daily_brief.py / discord-bridge.py's existing
# outbox+voice pipeline (module docstring DELIVERY section). Module-level functions
# (not default-arg bindings) so tests can monkeypatch them directly, same idiom as
# conductor_wake_watch.py's `fire_task`.
# --------------------------------------------------------------------------- #
def _default_speak(text: str, out_wav: Path) -> tuple[bool, str]:
    if not TTS_VENV_PY.exists() or not SPEAK_SCRIPT.exists():
        return False, f"TTS venv or script missing ({TTS_VENV_PY} / {SPEAK_SCRIPT})"
    tmp_txt = out_wav.with_suffix(".txt")
    try:
        tmp_txt.write_text(text, encoding="utf-8")
    except OSError as exc:
        return False, f"could not write temp text file: {exc}"
    try:
        r = subprocess.run(
            [str(TTS_VENV_PY), str(SPEAK_SCRIPT), "--text-file", str(tmp_txt), "--out", str(out_wav)],
            capture_output=True, text=True, timeout=120,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"tts subprocess failed: {exc}"
    finally:
        try:
            tmp_txt.unlink()
        except OSError:
            pass
    ok = r.returncode == 0 and out_wav.exists()
    return ok, (r.stdout or r.stderr or "").strip()


def _default_deliver(content: str, wav_path: Optional[Path], *, source: str = "entry_block_watch") -> dict:
    """SAME row shape as daily_brief.py's queue_discord_delivery -- discord-bridge.py's
    drain_outbox already knows how to send `file` as a multipart attachment."""
    row = {"queued_at": dt.datetime.now().isoformat(timespec="seconds"), "content": content, "source": source}
    if wav_path is not None:
        row["file"] = str(wav_path)
    try:
        OUTBOX.parent.mkdir(parents=True, exist_ok=True)
        with OUTBOX.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"queued": True}
    except OSError as exc:
        return {"queued": False, "error": str(exc)}


def _default_dashboard_update(text: str, side: str, account: str) -> None:
    """Best-effort, additive-only. dashboard-dialogue.json has several concurrent
    writers; this ONLY ever touches its own `agents.entry_block_watch` key, and any
    failure here (including a lost-update race) never blocks the voice/Discord
    delivery above, which already carries the alert."""
    try:
        if DASHBOARD_DIALOGUE.exists():
            data = json.loads(DASHBOARD_DIALOGUE.read_text(encoding="utf-8"))
        else:
            data = {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    agents = data.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    now_et_iso = (dt.datetime.now(_ET_TZ).isoformat(timespec="seconds") if _ET_TZ is not None
                  else _et_now().strftime("%Y-%m-%dT%H:%M:%S"))
    agents["entry_block_watch"] = {
        "active": True, "speech": text, "side": side, "account": account,
        "last_active_at": now_et_iso,
    }
    data["agents"] = agents
    try:
        DASHBOARD_DIALOGUE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run_once(*, core_decisions_path: Path = CORE_DECISIONS, watermark_path: Path = WATERMARK,
             now_et: Optional[dt.datetime] = None, dry_run: bool = False) -> dict:
    now_et = now_et or _et_now()
    today = now_et.strftime("%Y-%m-%d")

    wm = _load_watermark(watermark_path)
    if wm.get("date_et") != today:
        wm["date_et"] = today
        wm["alerts_today"] = 0
        wm["episodes"] = {}  # fresh debounce state each ET day; byte_offset untouched

    rows, new_offset, malformed = _read_new_rows(core_decisions_path, wm.get("byte_offset", 0))
    wm["byte_offset"] = new_offset
    episodes: dict = wm["episodes"]

    alerts_fired: list[dict] = []
    suppressed: list[dict] = []

    for row in rows:
        account = row.get("account")
        if account not in ("safe", "bold"):
            continue
        for side in ("bear", "bull"):
            key = f"{account}:{side}"
            ep = episodes.setdefault(key, _fresh_episode())
            qualifies = _qualifies(row, side)

            if qualifies:
                ep["consecutive_clear"] = 0
                if not ep["resolved"]:
                    ep["consecutive_qualify"] += 1
                    if ep["consecutive_qualify"] >= DEBOUNCE_TICKS:
                        if wm["alerts_today"] < MAX_ALERTS_PER_DAY:
                            text = compose_alert_text(row, side)
                            wm["alerts_today"] += 1
                            entry = {"account": account, "side": side, "text": text,
                                     "row_ts": row.get("ts_et")}
                            alerts_fired.append(entry)
                            if not dry_run:
                                try:
                                    wav_path = STATE / f"entry-block-alert-{today}-{wm['alerts_today']}.wav"
                                    ok, msg = _default_speak(text, wav_path)
                                    if not ok:
                                        print(f"[entry-block-watch] TTS failed ({msg}) -- text-only delivery")
                                    _default_deliver(text, wav_path if ok else None)
                                    _default_dashboard_update(text, side, account)
                                except Exception as exc:  # noqa: BLE001 -- delivery never blocks the tick
                                    print(f"[entry-block-watch] delivery error (non-fatal): {exc}")
                            print(f"[entry-block-watch] ALERT {account}/{side} @ {row.get('ts_et')} "
                                  f"score={row.get(SIDE_CONFIG[side]['score_field'])}")
                        else:
                            suppressed.append({"account": account, "side": side, "row_ts": row.get("ts_et")})
                            print(f"[entry-block-watch] SUPPRESSED {account}/{side} @ {row.get('ts_et')} "
                                  f"-- daily cap ({MAX_ALERTS_PER_DAY}) already reached")
                        ep["resolved"] = True
            else:
                if ep["resolved"]:
                    ep["consecutive_clear"] += 1
                    if ep["consecutive_clear"] >= CLEAR_TICKS:
                        episodes[key] = _fresh_episode()
                else:
                    ep["consecutive_qualify"] = 0

    if not dry_run:
        _save_watermark(watermark_path, wm)

    return {
        "rows_scanned": len(rows), "malformed_skipped": malformed,
        "alerts_fired": alerts_fired, "suppressed": suppressed,
        "byte_offset": new_offset,
    }


def main(argv: Optional[list[str]] = None) -> int:
    _safe_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="detect + print, deliver/persist nothing")
    args = ap.parse_args(argv)

    try:
        summary = run_once(dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 -- absolute fail-open, this is a 2-min scheduled tick
        print(f"[entry-block-watch] ERROR (fail-open, no-op): {exc}")
        return 0

    tag = "(dry-run) " if args.dry_run else ""
    print(f"[entry-block-watch] {tag}rows={summary['rows_scanned']} "
          f"malformed_skipped={summary['malformed_skipped']} "
          f"alerts={len(summary['alerts_fired'])} suppressed={len(summary['suppressed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
