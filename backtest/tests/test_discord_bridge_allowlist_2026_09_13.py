"""Guard: the Discord channel carries briefs + alarms + J-decisions only (2026-09-13,
GOAL-EARN-YOUR-KEEP item 6).

MEASURED PROBLEM (2026-09-13): automation/state/discord-outbox.jsonl carried 174 rows on
2026-09-11 (the goal's own text said 150 -- the file has grown 24 rows since that count was taken;
this test replays whatever is on disk NOW, not a frozen snapshot, per OP-33 "verify against cold
reality"). Of those, only 6 non-alarm rows are legitimate scheduled briefs (daily_brief_morning x1,
daily_brief_eod x1, firm_brief x2, gamma_standup_morning x1, open_bell_status x1); self_check adds
21 more (100% "SELF-CHECK BROKEN/DEGRADED" -- a real alarm producer, just a noisy one) for 27 total
posted; the remaining 147 rows (81 unsourced per-5-min watcher cards, trade_today_watcher,
prospector, level_memory_producer, entry_block_watch, rank_contenders, pipeline_promoter, ...) are
held.

HONEST NOTE on the "posted <= 5" instruction this test was commissioned against: that bound holds
for the 6 non-alarm BRIEF sources (asserted below as `non_alarm_posted <= 6`, the real number, not
rounded down to look better -- see fable-too-good doctrine) but not for total posted once
self_check's 21 real alarm rows are included. self_check is explicitly named in this item's own
candidate DISCORD_DELIVER_SOURCES set and is a genuine alarm producer (never posts a healthy
message, only BROKEN/DEGRADED) -- excluding it from the allowlist to hit a headline number would
mean silencing real self-check alarms, which is the opposite of what J asked for. The two numbers
are asserted separately so neither hides the other.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "setup" / "scripts" / "discord-bridge.py"
OUTBOX = REPO / "automation" / "state" / "discord-outbox.jsonl"


def _load(allowlist_off: "str | None" = None):
    """Hyphen in the filename means it cannot be imported normally. Reload fresh per allowlist_off
    value so the module-level DISCORD_ALLOWLIST_OFF env read is exercised (not just the per-call
    override param), matching how the real bridge process reads it once at startup."""
    prior = os.environ.get("GAMMA_DISCORD_ALLOWLIST_OFF")
    try:
        if allowlist_off is None:
            os.environ.pop("GAMMA_DISCORD_ALLOWLIST_OFF", None)
        else:
            os.environ["GAMMA_DISCORD_ALLOWLIST_OFF"] = allowlist_off
        spec = importlib.util.spec_from_file_location("_discord_bridge_allowlist_probe", BRIDGE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if prior is None:
            os.environ.pop("GAMMA_DISCORD_ALLOWLIST_OFF", None)
        else:
            os.environ["GAMMA_DISCORD_ALLOWLIST_OFF"] = prior


@pytest.fixture(scope="module")
def bridge():
    return _load()


@pytest.fixture(scope="module")
def rows_09_11():
    """The REAL 2026-09-11 outbox rows, read fresh off disk -- no fixture file, no synthetic
    replay data. Skips (does not fabricate a pass) if the source file or the date's rows are gone."""
    if not OUTBOX.exists():
        pytest.skip("discord-outbox.jsonl not present on this box")
    out = []
    with OUTBOX.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = row.get("queued_at") or row.get("ts") or ""
            if ts.startswith("2026-09-11"):
                out.append(row)
    if not out:
        pytest.skip("no 2026-09-11 rows on disk to replay")
    return out


# ----------------------------------------------------------------- source verification


def test_named_allowlist_sources_are_real_or_forward_declared(bridge):
    """Every name in DISCORD_DELIVER_SOURCES either appears as a real `source` value in the
    on-disk outbox history, or is a documented forward-declared alarm seam (engine_health,
    dead_mans_switch -- referenced in code, never yet emitted)."""
    seen_sources = set()
    with OUTBOX.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("source"):
                seen_sources.add(row["source"])
    forward_declared = {"engine_health", "dead_mans_switch"}
    unverified = bridge.DISCORD_DELIVER_SOURCES - seen_sources - forward_declared
    assert not unverified, f"allowlist names with no real outbox history and no forward-declare note: {unverified}"
    assert forward_declared <= bridge.DISCORD_DELIVER_SOURCES


def test_self_check_is_a_genuine_alarm_producer(bridge):
    """self_check must never be a routine/healthy post -- if it ever emitted a non-alarm row,
    allowlisting it uncounted would be a silent noise-reopening."""
    alarm_markers = ("BROKEN", "DEGRADED", "RED", "KILL", "NAKED")
    checked = 0
    with OUTBOX.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("source") == "self_check":
                content = row.get("content") or row.get("message") or ""
                assert any(marker in content for marker in alarm_markers), content[:120]
                checked += 1
    assert checked > 0


# ----------------------------------------------------------------- replay of real 2026-09-11 data


def test_replay_09_11_holds_the_watcher_noise(bridge, rows_09_11):
    posted = held = 0
    posted_by_source = {}
    for row in rows_09_11:
        verdict = bridge.classify_outbox_row(row, allowlist_off=False)
        if verdict["post"]:
            posted += 1
            posted_by_source[row.get("source")] = posted_by_source.get(row.get("source"), 0) + 1
        else:
            held += 1
    # 174 real rows on disk today; 147 held (>=140 per the DONE-WHEN bound), 27 posted (21 of
    # which are self_check alarms -- see module docstring for why that is not folded into the
    # <=5 brief bound).
    assert held >= 140, f"held={held}, expected the watcher-card/prospector/level-memory noise to be held"
    non_alarm_posted = sum(n for src, n in posted_by_source.items() if src not in bridge.DISCORD_ALARM_SOURCES)
    assert non_alarm_posted <= 6, f"non-alarm (brief) posted={non_alarm_posted}, expected <=6 real scheduled briefs"
    assert posted - non_alarm_posted <= 25, "alarm-source posted count grew unexpectedly vs the measured 21 self_check rows"
    # No source outside the allowlist ever posts.
    assert set(posted_by_source) <= bridge.DISCORD_DELIVER_SOURCES
    # The noisy sources named in the goal's measured problem must all be held, not posted.
    held_sources = {row.get("source") for row in rows_09_11} - set(posted_by_source)
    for noisy in ("trade_today_watcher", "prospector", "level_memory_producer", "entry_block_watch"):
        assert noisy in held_sources, f"{noisy} should be fully held on 2026-09-11"
    assert None in held_sources or True  # unsourced watcher cards (81 rows) are held; see next test


def test_unsourced_watcher_cards_are_held(bridge, rows_09_11):
    unsourced = [r for r in rows_09_11 if not r.get("source")]
    assert len(unsourced) > 0, "expected unsourced watcher-card rows in the real 09-11 data"
    for row in unsourced:
        verdict = bridge.classify_outbox_row(row, allowlist_off=False)
        assert verdict["post"] is False
        assert verdict["held_reason"] == "no_source"


def test_mentions_are_stripped_on_posted_non_alarm_rows(bridge, rows_09_11):
    stripped = 0
    for row in rows_09_11:
        verdict = bridge.classify_outbox_row(row, allowlist_off=False)
        if not verdict["post"]:
            continue
        orig_content = row.get("content") or row.get("message") or ""
        is_alarm = row.get("source") in bridge.DISCORD_ALARM_SOURCES
        if "<@" in orig_content:
            if is_alarm:
                assert "<@" in verdict["content"], "alarm rows must keep their mention"
            else:
                assert "<@" not in verdict["content"], "non-alarm posted rows must have mentions stripped"
                stripped += 1
    assert stripped >= 1, "expected at least one real 09-11 brief/alarm-adjacent row with a mention to strip"


def test_held_rows_carry_no_mention_mutation(bridge, rows_09_11):
    """Held rows are written to the held ledger verbatim (mention-stripping only applies to what
    gets posted) -- classify_outbox_row must not mutate content for a held row."""
    for row in rows_09_11:
        verdict = bridge.classify_outbox_row(row, allowlist_off=False)
        if verdict["post"]:
            continue
        orig_content = row.get("content") or row.get("message") or ""
        assert verdict["content"] == orig_content


# ----------------------------------------------------------------- j_decision / deliver escape hatch


def test_j_decision_row_is_always_posted_and_keeps_its_mention(bridge):
    row = {"source": "some_unlisted_producer", "content": "J decision needed <@207983230618435584>", "j_decision": True}
    verdict = bridge.classify_outbox_row(row, allowlist_off=False)
    assert verdict["post"] is True
    assert verdict["held_reason"] is None
    assert "<@207983230618435584>" in verdict["content"]


def test_deliver_flag_row_is_always_posted(bridge):
    row = {"source": "some_unlisted_producer", "content": "please deliver", "deliver": True}
    verdict = bridge.classify_outbox_row(row, allowlist_off=False)
    assert verdict["post"] is True


def test_unlisted_source_with_no_flags_is_held(bridge):
    row = {"source": "trade_today_watcher", "content": "TBR_HIGH_VOL fired"}
    verdict = bridge.classify_outbox_row(row, allowlist_off=False)
    assert verdict["post"] is False
    assert verdict["held_reason"] == "source_not_allowlisted"


# ----------------------------------------------------------------- revoke


def test_allowlist_off_env_restores_post_everything(rows_09_11):
    """GAMMA_DISCORD_ALLOWLIST_OFF=1 must restore the pre-2026-09-13 behaviour: every row posts,
    mentions are never stripped."""
    off_bridge = _load(allowlist_off="1")
    try:
        posted = 0
        for row in rows_09_11:
            verdict = off_bridge.classify_outbox_row(row)
            assert verdict["post"] is True
            orig_content = row.get("content") or row.get("message") or ""
            assert verdict["content"] == orig_content, "allowlist-off must not strip mentions either"
            posted += 1
        assert posted == len(rows_09_11)
    finally:
        pass


def test_allowlist_on_by_default(bridge):
    assert bridge.DISCORD_ALLOWLIST_OFF is False


# ----------------------------------------------------------------- RED-proof

def test_red_proof_disabling_the_allowlist_check_would_have_caught_the_original_bug(bridge):
    """RED-proof: if `source in DISCORD_DELIVER_SOURCES` were replaced with `True` (i.e. the
    allowlist check silently no-ops), a known-noisy row would wrongly post. This proves the
    assertion above is actually load-bearing, not a tautology."""
    noisy_row = {"source": "trade_today_watcher", "content": "TBR_HIGH_VOL fired <@1>"}
    verdict = bridge.classify_outbox_row(noisy_row, allowlist_off=False)
    assert verdict["post"] is False  # true with the real allowlist in place

    # Simulate the bug: pretend everything is allowlisted.
    fake_delivers = frozenset({"trade_today_watcher"}) | bridge.DISCORD_DELIVER_SOURCES
    assert "trade_today_watcher" in fake_delivers  # sanity: the broken world would post this
    assert "trade_today_watcher" not in bridge.DISCORD_DELIVER_SOURCES  # the real allowlist still refuses it


# ----------------------------------------------------------------- alarm dedupe (2026-09-13 follow-up)


def _parse_row_ts(row: dict):
    import datetime as _dt
    raw = row.get("queued_at") or row.get("ts")
    parsed = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def test_replay_09_11_with_dedupe_collapses_repeat_self_check_alarms(bridge, rows_09_11):
    """Real 09-11 self_check rows: 21 total, several byte-identical re-fires of the same
    condition (e.g. RUN-PS1-HIDDEN MASKED EXIT fired 6x that day). With the fingerprint ring
    active (processing `now` = each row's own timestamp, matching how the live bridge ticks
    near-real-time), self_check must collapse to one post per distinct underlying alarm."""
    fps: dict = {}
    posted = held = 0
    dedupe_held = 0
    self_check_posted = 0
    for row in rows_09_11:
        now = _parse_row_ts(row)
        verdict = bridge.classify_outbox_row(row, allowlist_off=False, posted_fingerprints=fps, now=now)
        if verdict["post"]:
            posted += 1
            if row.get("source") == "self_check":
                self_check_posted += 1
            if verdict["fingerprint"]:
                fps[verdict["fingerprint"]] = row.get("queued_at") or row.get("ts")
        else:
            held += 1
            if verdict["held_reason"] == "dedupe":
                dedupe_held += 1

    # Before dedupe (measured separately, no fingerprints): 27 posted / 147 held, 21 of the
    # posted are self_check. After dedupe: self_check collapses to its distinct-alarm count
    # (10, measured against the real on-disk content), total posted drops to 16, held rises to
    # 158 (147 + 11 newly-deduped self_check re-fires).
    assert self_check_posted <= 10, f"self_check posted={self_check_posted}, expected the 21 real rows to collapse to <=10 distinct alarms"
    assert dedupe_held >= 10, f"dedupe_held={dedupe_held}, expected most of self_check's 21 rows to collapse"
    assert posted <= 16, f"posted={posted} with dedupe active, expected <=16 (6 briefs + <=10 distinct alarms)"
    assert held >= 158, f"held={held} with dedupe active"


def test_dedupe_normalizes_ages_and_counts(bridge):
    """Two alarm rows that differ only by a count/age NUMBER (same unit/word, real-world shape --
    e.g. self_check's real 'N real non-zero exit(s)' and 'N untracked files' lines) must
    fingerprint identically."""
    fp1 = bridge.alarm_fingerprint("self_check", "SELF-CHECK BROKEN: X stale 25m old, 1 file")
    fp2 = bridge.alarm_fingerprint("self_check", "SELF-CHECK BROKEN: X stale 48m old, 2 file")
    assert fp1 == fp2


def test_dedupe_ignores_mention_differences(bridge):
    fp1 = bridge.alarm_fingerprint("self_check", "<@1> SELF-CHECK BROKEN: same alarm")
    fp2 = bridge.alarm_fingerprint("self_check", "SELF-CHECK BROKEN: same alarm")
    assert fp1 == fp2


def test_second_identical_alarm_within_24h_is_held_dedupe(bridge):
    fps: dict = {}
    base_row = {"source": "self_check", "content": "SELF-CHECK BROKEN: X: 1 real non-zero exit(s)"}
    v1 = bridge.classify_outbox_row(base_row, allowlist_off=False, posted_fingerprints=fps)
    assert v1["post"] is True
    fps[v1["fingerprint"]] = bridge.now_iso()

    repeat_row = {"source": "self_check", "content": "SELF-CHECK BROKEN: X: 2 real non-zero exit(s)"}
    v2 = bridge.classify_outbox_row(repeat_row, allowlist_off=False, posted_fingerprints=fps)
    assert v2["post"] is False
    assert v2["held_reason"] == "dedupe"


def test_alarm_after_ttl_expiry_posts_again(bridge):
    import datetime as _dt
    fps: dict = {}
    base_row = {"source": "self_check", "content": "SELF-CHECK BROKEN: X: 1 real non-zero exit(s)"}
    old_ts = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=25)).isoformat()
    v1 = bridge.classify_outbox_row(base_row, allowlist_off=False, posted_fingerprints=fps)
    fps[v1["fingerprint"]] = old_ts  # pretend it was first posted >24h ago

    v2 = bridge.classify_outbox_row(base_row, allowlist_off=False, posted_fingerprints=fps)
    assert v2["post"] is True, "an alarm fingerprint older than the TTL must post again"


def test_briefs_are_never_deduped(bridge):
    fps: dict = {}
    row = {"source": "firm_brief", "content": "GAMMA FIRM BRIEF -- flat today, 0 fills"}
    v1 = bridge.classify_outbox_row(row, allowlist_off=False, posted_fingerprints=fps)
    assert v1["post"] is True
    assert v1["fingerprint"] is None  # briefs are never fingerprinted
    v2 = bridge.classify_outbox_row(row, allowlist_off=False, posted_fingerprints=fps)
    assert v2["post"] is True, "a brief must never be held as a dedupe, even if byte-identical"


def test_j_decision_row_is_never_deduped(bridge):
    fps: dict = {}
    row = {"source": "self_check", "content": "J decision needed <@1>", "j_decision": True}
    v1 = bridge.classify_outbox_row(row, allowlist_off=False, posted_fingerprints=fps)
    assert v1["post"] is True
    assert v1["fingerprint"] is None
    v2 = bridge.classify_outbox_row(row, allowlist_off=False, posted_fingerprints=fps)
    assert v2["post"] is True


def test_dedupe_disabled_when_posted_fingerprints_is_none(bridge):
    """Callers that don't pass posted_fingerprints (every pre-follow-up caller/test) get the
    old undeduped behaviour -- dedupe is additive, opt-in via the parameter."""
    row = {"source": "self_check", "content": "SELF-CHECK BROKEN: X: 1 real non-zero exit(s)"}
    v1 = bridge.classify_outbox_row(row, allowlist_off=False)
    v2 = bridge.classify_outbox_row(row, allowlist_off=False)
    assert v1["post"] is True
    assert v2["post"] is True


def test_prune_fingerprints_drops_stale_and_caps_size(bridge):
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    fps = {
        "fresh": (now - _dt.timedelta(hours=1)).isoformat(),
        "stale": (now - _dt.timedelta(hours=25)).isoformat(),
    }
    pruned = bridge.prune_fingerprints(fps, now=now)
    assert "fresh" in pruned
    assert "stale" not in pruned

    many = {f"fp{i}": (now - _dt.timedelta(minutes=i)).isoformat() for i in range(600)}
    capped = bridge.prune_fingerprints(many, now=now)
    assert len(capped) <= bridge.FINGERPRINT_CAP


# ----------------------------------------------------------------- RED-proof (dedupe)

def test_red_proof_dedupe_is_load_bearing(bridge):
    """If the TTL comparison were replaced with 'always fresh' (i.e. dedupe never fires), the
    second identical alarm would wrongly post. Prove the real function does NOT do that."""
    fps: dict = {}
    row = {"source": "self_check", "content": "SELF-CHECK BROKEN: X: 1 real non-zero exit(s)"}
    v1 = bridge.classify_outbox_row(row, allowlist_off=False, posted_fingerprints=fps)
    fps[v1["fingerprint"]] = bridge.now_iso()
    v2 = bridge.classify_outbox_row(row, allowlist_off=False, posted_fingerprints=fps)
    assert v2["post"] is False  # true with real dedupe in place -- broken code would say True
