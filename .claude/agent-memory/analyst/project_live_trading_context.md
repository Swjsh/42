---
name: live-trading-context
description: Status of live paper trading accounts and what has happened in early live sessions
metadata:
  type: project
---

Two $1K paper accounts went live 2026-05-18 (Day 1).

**Why:** Both accounts are the new fresh $1K accounts (Safe: PA3PHRM47D1J, Bold: PA35NRWPGKD5). Goal: grow from $1K to $2K to $10K+ to test which risk profile compounds better.

**Day 1 (5/18):** Bold took 1 trade — BULLISH_RECLAIM at 09:57 on 738.10 Carry reclaim, stopped out at -$99 (9 min hold). Safe took 0 trades.

**Day 2 (5/19):** Zero trades in either account. Engine had 10/11 bull scores in the afternoon but F11 (HTF 15m BEAR) blocked all bull entries. Rate-limit gap (10:57-12:40 ET) caused a ghost ENTER_BEAR at 10:03 (logged, no order placed). Two J-quality bull setups at 12:20 and 12:35 ET missed due to rate-limit blackout.

**How to apply:** When reviewing future sessions, track the 2-day pattern: engine is reading setups correctly (10/11 scores) but filters F8 and F11 are systematically blocking on days with ambiguous VIX direction and HTF lag. This is the primary research thread (Chef items queued 5/19).
