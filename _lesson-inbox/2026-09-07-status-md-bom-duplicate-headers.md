# Lesson inbox: a BOM in STATUS.md made every writer prepend its own "## Known broken" header

**Date:** 2026-09-07 (Sunday), found while reading Known-broken for the day's work

**Symptom:** `automation/overnight/STATUS.md` had THREE `## Known broken` sections: the real one at byte 0, one at byte 1550 whose header began with an invisible U+FEFF, and one at byte 1828 beginning with `ï»¿` (a UTF-8 BOM re-encoded as cp1252 → UTF-8). Monitors that scan "the" Known-broken section (conductor_wake_watch, engine_health, guard runners) therefore saw only the newest fragment — the visibility surface J wakes to was silently split.

**Root cause (one sentence):** something wrote STATUS.md with a UTF-8 BOM once (no repo script does — an editor or a `Set-Content` outside the repo), and every Python writer reads it with plain `utf-8`, so the first line became `﻿## Known broken`, failed the header match, and the writer prepended a fresh header + block above the old file; a later reader using the cp1252 default re-encoded that BOM into `ï»¿` and repeated the split.

**Fix applied:** one-time normalize (strip embedded BOMs, merge the three sections under the single header; 18 bullets preserved) — commit e-series 2026-09-07.

**Durable fix (queued, not applied):** every STATUS.md reader/writer must `read_text(encoding="utf-8-sig")` and `write_text(..., encoding="utf-8")`, and the section-scanning helper should self-heal (collapse duplicate headers, strip BOMs) on read. 8+ scripts implement their own STATUS I/O; the right home is one shared helper. Guard candidate: `test_graduated_guards.py` — assert no U+FEFF anywhere in STATUS.md and exactly one line-start `## Known broken`.
