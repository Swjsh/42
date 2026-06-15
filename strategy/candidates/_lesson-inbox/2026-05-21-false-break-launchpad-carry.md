# Lesson: False-break-launchpad at ★★★ Carry on RTH open bar

## Symptom
Bear entry placed after a ★★★ Carry level break — level had 9 touches, 7 historical holds. Session closed +$4 in the opposite direction. Loss −$204.

## Root cause
The 09:35 open bar printed low 737.53 (−$0.57 below 738.10 ★★★ Carry). By the 09:40 bar, SPY had recovered above 738.10. This is the single-bar version of L59 floor_hold: trapped shorts from the false break became the fuel for a +$5 squeeze. The premarket evaluation framework had no branch for "Carry breaks at open bar and immediately recovers" — it only evaluated the level as either holding or breaking definitively.

## Fix
Add the following check to the premarket morning checklist for any ★★★ level within $1.00 of the expected open:

> **False-break-launchpad check:** If the first RTH bar (09:35) prints a low more than $0.25 BELOW a ★★★ named level AND the same bar (or next closed bar) closes ABOVE that level — suspend bear entries on this level for 30 min. Write "FALSE_BREAK_DETECTED: [level]" to journal. Watch for bull ribbon trigger.

For the general rule: a single-bar false-break at RTH open is structurally MORE dangerous than a mid-session test because (a) overnight shorts and early bears are all trapped simultaneously, (b) gap-open dynamics amplify the squeeze, (c) the Carry's historical holds create maximum short positioning.

## Encoded in
- `journal/mistakes.md` — append if this causes a rule-adjacent cost in future
- This lesson file (L-pending, next available L## after L67)
- `automation/prompts/heartbeat.md` premarket section (when next ratification window opens per Rule 9)

## Related
- L59: close-ceiling distribution (N≥3 bar version, bull analog — distribution at resistance)  
- L51: violent initial bounce on VIX≥20 level-break entries
- `crypto/lib/chart_patterns.py::detect_floor_hold()` — n_min=1 variant covers this case
