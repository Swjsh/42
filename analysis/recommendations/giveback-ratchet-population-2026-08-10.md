# GIVEBACK-RATCHET population kill-check (2026-08-10)

Population: 256/257 engine positions priced on real OPRA (1 skipped, no bars). Gate cohort EXCLUDES 2026-08-10 (in-sample). Full disclosures in the runner header.

| cell | d vs control (paired) | d vs actual | flips L->W | runner d | dropbest | halves | p | BH |
|---|--:|--:|--:|--:|--:|---|--:|---|
| GIVEBACK_20 | +30903 | +7777 | 16/20 | +7343 | +22607 | +9145/+21758 | 0.0001 | PASS |
| GIVEBACK_25 | +30198 | +7072 | 16/20 | +7085 | +21959 | +8918/+21280 | 0.0001 | PASS |
| GIVEBACK_33 | +29069 | +5943 | 15/20 | +6673 | +20922 | +8555/+20514 | 0.0001 | PASS |
| GIVEBACK_50 | +26671 | +3545 | 15/20 | +5796 | +18718 | +7784/+18887 | 0.0001 | PASS |
| RATCHET_a90_f80 | +19518 | -3608 | 3/20 | +8918 | +9451 | +4816/+14702 | 0.0001 | PASS |
| RATCHET_a70_f60 | +18403 | -4723 | 2/20 | +9140 | +8574 | +4612/+13792 | 0.0001 | PASS |
| SHIPPED | +17195 | -5931 | 4/20 | +6904 | +10736 | +4226/+12969 | 0.0001 | PASS |
| J_TRAIL_40 | +14544 | -8582 | 4/20 | +5080 | +9934 | +3522/+11022 | 0.0001 | PASS |
| RATCHET_a70_f50 | +14504 | -8622 | 2/20 | +7600 | +7271 | +3926/+10578 | 0.0001 | PASS |
| RATCHET_a90_f70 | +13701 | -9425 | 2/20 | +4923 | +7960 | +4010/+9691 | 0.0001 | PASS |
| J_SPEC_RATCHET | +11393 | -11733 | 2/20 | +3656 | +6050 | +3294/+8099 | 0.0001 | PASS |
| RATCHET_a90_f60 | +9832 | -13294 | 2/20 | +2669 | +4886 | +3044/+6788 | 0.0001 | PASS |
| RATCHET_a90_f50 | +6782 | -16344 | 1/20 | +1671 | +3654 | +2306/+4477 | 0.0001 | PASS |

## VERDICT: PASS -- ladder stays live (decided on the binding slice, not the table above)

The table above is harness-inflated: CONTROL replays ~$23k worse than live actuals because the
harness has no SPY feed (structure/ribbon exits never fire), so every floor beats a strawman. The
GIVEBACK rows contradict the measured pre-TP1 %-trail G_RUNNER failure (-$7,759) and are exactly
what 5m intra-bar optimism flatters -- caught by /fable-too-good, reported, NOT quoted as wins.

**The honest cut -- positions where the ladder BINDS (replay MFE >= +50%; below that it is
guard-tested inert and production behavior is unchanged), OOS ex-2026-08-10:**

| cohort | n | ladder replay | actual | delta |
|---|--:|--:|--:|--:|
| A: live TP1'd (already banking) | 40 | +$5,442 | +$9,201 | **-$3,759 clip cost** |
| B: live NOT TP1'd (the give-back class) | 73 | +$7,158 | -$3,056 | **+$10,214 rescue** |
| total | 113 (21 days) | +$12,599 | +$6,145 | **+$6,454** |

Gates: better on 15/21 days - drop-best +$4,375 - halves +2,441/+4,014 sign-consistent -
bootstrap p=0.0073 (day-clustered). Kill criterion (runner-cohort clip like the trail's -$7,759):
clip is -$3,759 against a 2.7x rescue -> NOT killed. Forward live evidence supersedes this replay.
