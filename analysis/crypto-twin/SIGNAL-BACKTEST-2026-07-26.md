# Crypto Twin Signal Backtest -- 2026-07-26

## Verdict

**NULL RESULT: 0 of 72 cells pass all four honesty gates.** No config here shows measured, statistically-survivable positive expectancy on real BTC history under this exit model + friction. This is the expected, useful answer -- reported plainly, not softened.

Section below ranks all cells by held-out avg-per-trade return (net of friction) regardless of pass/fail, so the least-bad config is identifiable even though nothing measured an edge.

## Top-5 cells (ranked by held-out avg-per-trade % net of friction)

| Rank | level_set | max_dist% | min_stack | exit | n(tune/hold) | tune avg%/trade | hold avg%/trade | hold WR | hold max_dd% | BH sig | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | 1.0 | 2 | lens_M40 | 252/91 | -5.4023 | 2.2495 | 0.4945 | 262.3894 | False | False |
| 2 | A | 0.25 | 2 | lens_M40 | 251/88 | -5.0908 | 1.4771 | 0.4886 | 262.3894 | False | False |
| 3 | A | 1.0 | 3 | lens_M40 | 250/91 | -6.3084 | 1.1773 | 0.4725 | 312.654 | False | False |
| 4 | A | 0.25 | 3 | lens_M40 | 249/87 | -6.0341 | 1.1201 | 0.4828 | 300.9968 | False | False |
| 5 | A | 0.5 | 2 | lens_M40 | 252/90 | -5.2434 | 0.6889 | 0.4778 | 262.3894 | False | False |

## Recommended config for tonight

**Label: NO MEASURED EDGE (least-bad only)**

- level_set = `A`, max_distance_pct = `1.0`, min_stack_bars = `2`, exit_variant = `lens_M40`
- Held-out: n=91, avg/trade=2.2495%, WR=0.4945, total_return=204.7061%, max_dd=262.3894%
- Tuning: n=252, avg/trade=-5.4023%, WR=0.3849
- BH-FDR: p=0.998089, threshold=0.041667, significant=False
- Bull-only (the ONLY side deployable tonight -- Alpaca crypto is cash/long-only, ENTER_BEAR is logged-but-skipped in production per crypto_twin_core.py): n=177, avg/trade=-3.8915%, WR=0.4011

## Friction-adjusted breakeven

- Spot breakeven move needed per trade (round-trip friction, independent of M): **0.09%**
- Lens-return hurdle by M: M=20: 1.8%, M=40: 3.6%, M=80: 7.2%
- Friction is charged in SPOT space before the leverage lens multiply, so the breakeven hurdle in the underlying BTC move is 0.09% round-trip REGARDLESS of M -- M only rescales wins/losses/friction together in lens-% space, it never creates edge that wasn't in the spot move itself.

## Data provenance

- **source**: alpaca_v1beta3_crypto_us_bars
- **symbol**: BTC/USD
- **granularity_seconds**: 300
- **requested_days**: 120
- **actual_bars**: 34558
- **date_range**: ['2026-03-29T04:15:00+00:00', '2026-07-27T04:05:00+00:00']
- **fetched_at_utc**: 2026-07-27T04:13:23.353434+00:00
- **gaps_gt_2x_granularity**: 0
- **auth**: twin_creds

## Methodology / pre-registration (frozen before any cell was scored)

- Grid: level_set in ['A', 'B', 'C'], max_distance_pct in [0.25, 0.5, 1.0], min_stack_bars in [2, 3], exit_variant in lens_M[20, 40, 80] + fixed_control = 72 cells.
- Split: 70%/30% tuning/held-out by calendar UTC date (held-out = most recent 36 days: 2026-06-22 to 2026-07-27), touched once.
- Pass gate: positive mean tuning return AND positive mean held-out return AND n_trades>=30 AND BH-FDR significant at q<=0.1 across all 72 p-values at once.
- Exit shape sourced from automation/state/params.json (read-only): catastrophe=-0.5, tp1_target=0.5, tp1_qty_fraction=0.667 (task-specified), runner_target=1.5, profit_lock_arm=0.05, profit_lock_trail=0.125, runner_be_floor_after_tp1=True.
- Fixed control: TP=0.5% / stop=-0.5% of spot, single-lot, no lens.
- Friction: 0.09% round-trip, charged in spot space before the M multiply.
- max_hold_bars = 48 (4h @ 5m, fixed, not swept).
- DEPLOYABILITY: Alpaca crypto is cash/long-only. ENTER_BEAR triggers are scored in this grid for completeness but are NOT executable on the twin's account without margin/short capability -- see crypto_twin_core.py's own docstring ("BUY-only... ENTER_BEAR is logged-but-skipped").
- max_distance_pct is not a parameter crypto_twin_signal.evaluate() exposes directly -- it's the default baked into crypto_twin_levels.nearest_directional_level(). This tool temporarily monkeypatches that function's default in-process (restored immediately after) to make the grid axis testable while still running evaluate()'s real code verbatim. See patched_max_distance() in this script.

## Full 72-cell grid

| level_set | max_dist% | min_stack | exit | n_tune | tune avg% | n_hold | hold avg% | hold WR | p(tune) | BH sig | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.25 | 2 | fixed_control | 251 | -0.1232 | 88 | -0.0609 | 0.4886 | 0.999993 | False | False |
| A | 0.25 | 2 | lens_M20 | 251 | -2.4478 | 88 | -1.1553 | 0.4545 | 0.988152 | False | False |
| A | 0.25 | 2 | lens_M40 | 251 | -5.0908 | 88 | 1.4771 | 0.4886 | 0.996903 | False | False |
| A | 0.25 | 2 | lens_M80 | 251 | -7.0609 | 88 | -6.6483 | 0.4545 | 0.995915 | False | False |
| A | 0.25 | 3 | fixed_control | 249 | -0.1445 | 87 | -0.0665 | 0.4828 | 1.0 | False | False |
| A | 0.25 | 3 | lens_M20 | 249 | -2.9289 | 87 | -1.1764 | 0.4483 | 0.996833 | False | False |
| A | 0.25 | 3 | lens_M40 | 249 | -6.0341 | 87 | 1.1201 | 0.4828 | 0.999427 | False | False |
| A | 0.25 | 3 | lens_M80 | 249 | -9.6814 | 87 | -7.2309 | 0.4483 | 0.999869 | False | False |
| A | 0.5 | 2 | fixed_control | 252 | -0.1249 | 90 | -0.0726 | 0.4778 | 0.999995 | False | False |
| A | 0.5 | 2 | lens_M20 | 252 | -2.4965 | 90 | -1.8346 | 0.4333 | 0.98964 | False | False |
| A | 0.5 | 2 | lens_M40 | 252 | -5.2434 | 90 | 0.6889 | 0.4778 | 0.997614 | False | False |
| A | 0.5 | 2 | lens_M80 | 252 | -7.2082 | 90 | -7.7716 | 0.4444 | 0.996658 | False | False |
| A | 0.5 | 3 | fixed_control | 250 | -0.1421 | 90 | -0.0728 | 0.4778 | 1.0 | False | False |
| A | 0.5 | 3 | lens_M20 | 250 | -2.9561 | 90 | -1.907 | 0.4222 | 0.997119 | False | False |
| A | 0.5 | 3 | lens_M40 | 250 | -6.1482 | 90 | 0.1979 | 0.4667 | 0.999539 | False | False |
| A | 0.5 | 3 | lens_M80 | 250 | -9.7757 | 90 | -7.8317 | 0.4444 | 0.999891 | False | False |
| A | 1.0 | 2 | fixed_control | 252 | -0.1288 | 91 | -0.0673 | 0.4835 | 0.999998 | False | False |
| A | 1.0 | 2 | lens_M20 | 252 | -2.5525 | 91 | -0.4673 | 0.4505 | 0.990856 | False | False |
| A | 1.0 | 2 | lens_M40 | 252 | -5.4023 | 91 | 2.2495 | 0.4945 | 0.998089 | False | False |
| A | 1.0 | 2 | lens_M80 | 252 | -7.6061 | 91 | -6.1548 | 0.4615 | 0.997896 | False | False |
| A | 1.0 | 3 | fixed_control | 250 | -0.1461 | 91 | -0.0675 | 0.4835 | 1.0 | False | False |
| A | 1.0 | 3 | lens_M20 | 250 | -3.0125 | 91 | -0.8865 | 0.4286 | 0.997505 | False | False |
| A | 1.0 | 3 | lens_M40 | 250 | -6.3084 | 91 | 1.1773 | 0.4725 | 0.999641 | False | False |
| A | 1.0 | 3 | lens_M80 | 250 | -10.1769 | 91 | -6.9094 | 0.4505 | 0.999942 | False | False |
| B | 0.25 | 2 | fixed_control | 366 | -0.1259 | 146 | -0.081 | 0.4589 | 1.0 | False | False |
| B | 0.25 | 2 | lens_M20 | 366 | -2.0327 | 146 | -3.0955 | 0.3836 | 0.988158 | False | False |
| B | 0.25 | 2 | lens_M40 | 366 | -4.7256 | 146 | -3.3713 | 0.4041 | 0.99907 | False | False |
| B | 0.25 | 2 | lens_M80 | 366 | -8.632 | 146 | -10.5799 | 0.3904 | 0.999944 | False | False |
| B | 0.25 | 3 | fixed_control | 365 | -0.1155 | 145 | -0.0763 | 0.4621 | 0.999999 | False | False |
| B | 0.25 | 3 | lens_M20 | 365 | -2.0297 | 145 | -4.0652 | 0.3655 | 0.988288 | False | False |
| B | 0.25 | 3 | lens_M40 | 365 | -4.6344 | 145 | -5.2654 | 0.3793 | 0.998855 | False | False |
| B | 0.25 | 3 | lens_M80 | 365 | -8.2211 | 145 | -12.0999 | 0.3724 | 0.999887 | False | False |
| B | 0.5 | 2 | fixed_control | 368 | -0.1334 | 146 | -0.0879 | 0.4521 | 1.0 | False | False |
| B | 0.5 | 2 | lens_M20 | 368 | -2.67 | 146 | -3.1586 | 0.3836 | 0.998189 | False | False |
| B | 0.5 | 2 | lens_M40 | 368 | -4.824 | 146 | -4.5398 | 0.3973 | 0.999136 | False | False |
| B | 0.5 | 2 | lens_M80 | 368 | -8.624 | 146 | -11.1644 | 0.3836 | 0.999946 | False | False |
| B | 0.5 | 3 | fixed_control | 368 | -0.1208 | 145 | -0.0763 | 0.4621 | 1.0 | False | False |
| B | 0.5 | 3 | lens_M20 | 368 | -2.4431 | 145 | -4.2848 | 0.3655 | 0.996298 | False | False |
| B | 0.5 | 3 | lens_M40 | 368 | -4.4921 | 145 | -5.2097 | 0.3862 | 0.998167 | False | False |
| B | 0.5 | 3 | lens_M80 | 368 | -7.7894 | 145 | -11.3834 | 0.3793 | 0.999772 | False | False |
| B | 1.0 | 2 | fixed_control | 368 | -0.1334 | 147 | -0.0913 | 0.449 | 1.0 | False | False |
| B | 1.0 | 2 | lens_M20 | 368 | -2.6886 | 147 | -3.2087 | 0.381 | 0.998298 | False | False |
| B | 1.0 | 2 | lens_M40 | 368 | -4.9105 | 147 | -4.7355 | 0.3946 | 0.99929 | False | False |
| B | 1.0 | 2 | lens_M80 | 368 | -8.9059 | 147 | -11.4537 | 0.381 | 0.999969 | False | False |
| B | 1.0 | 3 | fixed_control | 368 | -0.1208 | 146 | -0.0798 | 0.4589 | 1.0 | False | False |
| B | 1.0 | 3 | lens_M20 | 368 | -2.4617 | 146 | -4.3173 | 0.3699 | 0.996509 | False | False |
| B | 1.0 | 3 | lens_M40 | 368 | -4.5786 | 146 | -5.3817 | 0.3904 | 0.998473 | False | False |
| B | 1.0 | 3 | lens_M80 | 368 | -8.0713 | 146 | -11.6323 | 0.3836 | 0.99986 | False | False |
| C | 0.25 | 2 | fixed_control | 318 | -0.1025 | 123 | -0.0573 | 0.4797 | 0.999974 | False | False |
| C | 0.25 | 2 | lens_M20 | 318 | -1.3564 | 123 | -3.0829 | 0.374 | 0.921755 | False | False |
| C | 0.25 | 2 | lens_M40 | 318 | -3.5721 | 123 | -4.0766 | 0.3902 | 0.986903 | False | False |
| C | 0.25 | 2 | lens_M80 | 318 | -6.5177 | 123 | -8.4366 | 0.4146 | 0.997177 | False | False |
| C | 0.25 | 3 | fixed_control | 314 | -0.1168 | 122 | -0.0668 | 0.4672 | 0.999998 | False | False |
| C | 0.25 | 3 | lens_M20 | 314 | -1.6639 | 122 | -3.2408 | 0.3607 | 0.959183 | False | False |
| C | 0.25 | 3 | lens_M40 | 314 | -4.1707 | 122 | -4.4161 | 0.3852 | 0.995297 | False | False |
| C | 0.25 | 3 | lens_M80 | 314 | -8.1124 | 122 | -9.8737 | 0.4016 | 0.999681 | False | False |
| C | 0.5 | 2 | fixed_control | 319 | -0.0981 | 125 | -0.0418 | 0.496 | 0.999946 | False | False |
| C | 0.5 | 2 | lens_M20 | 319 | -1.6493 | 125 | -2.9084 | 0.384 | 0.959061 | False | False |
| C | 0.5 | 2 | lens_M40 | 319 | -3.7004 | 125 | -2.8864 | 0.408 | 0.989242 | False | False |
| C | 0.5 | 2 | lens_M80 | 319 | -6.6703 | 125 | -6.9227 | 0.432 | 0.997722 | False | False |
| C | 0.5 | 3 | fixed_control | 316 | -0.1071 | 125 | -0.0633 | 0.472 | 0.999987 | False | False |
| C | 0.5 | 3 | lens_M20 | 316 | -1.9047 | 125 | -3.5736 | 0.352 | 0.97821 | False | False |
| C | 0.5 | 3 | lens_M40 | 316 | -4.1093 | 125 | -3.7384 | 0.392 | 0.994592 | False | False |
| C | 0.5 | 3 | lens_M80 | 316 | -7.698 | 125 | -9.6451 | 0.408 | 0.999425 | False | False |
| C | 1.0 | 2 | fixed_control | 322 | -0.1027 | 126 | -0.0382 | 0.5 | 0.999976 | False | False |
| C | 1.0 | 2 | lens_M20 | 322 | -1.7116 | 126 | -2.8777 | 0.3889 | 0.963693 | False | False |
| C | 1.0 | 2 | lens_M40 | 322 | -4.133 | 126 | -2.8483 | 0.4127 | 0.994961 | False | False |
| C | 1.0 | 2 | lens_M80 | 322 | -7.1666 | 126 | -6.8372 | 0.4365 | 0.998919 | False | False |
| C | 1.0 | 3 | fixed_control | 319 | -0.1116 | 126 | -0.0596 | 0.4762 | 0.999994 | False | False |
| C | 1.0 | 3 | lens_M20 | 319 | -1.9652 | 126 | -3.5376 | 0.3571 | 0.980758 | False | False |
| C | 1.0 | 3 | lens_M40 | 319 | -4.5421 | 126 | -3.6935 | 0.3968 | 0.997626 | False | False |
| C | 1.0 | 3 | lens_M80 | 319 | -8.1894 | 126 | -9.538 | 0.4127 | 0.999751 | False | False |
