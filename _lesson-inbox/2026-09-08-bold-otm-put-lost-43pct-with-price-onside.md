# Bold OTM 0DTE put lost 43% while SPY sat 70c ON-SIDE (2026-09-08, live fill)

**Fact:** bold-2 ENTER_BEAR 11:01 ET, 5x SPY 766P @ 0.35, SPY 767.65 (strike ~1.65 OTM).
13:01 ET SPY 766.95 = 70c in the trade's favour; put marked 0.20 (-43%). HWM 0.45 (+29%) at ~11:15,
never reached the +50% pre-TP1 ladder arm. 13:02 premium catastrophe stop @0.17, filled 0.16, -$95.
safe-2's 13:31 entry was ATM-ish 767P and took a clean 5-min structure stop (-$21) -- different failure.

**Mechanism:** theta + IV bleed on an OTM strike over a 2h hold in a $3-range chop day (premarket bias:
no-trade/chop, correct). Direction was right for two hours and the option still hit the -50% cap.
Same shape as the June edge hunt (ITM+tight = edge, OTM+wide = bleed) and C3 (L58, L74, L100, L149).

**What this is evidence for (not a change -- freeze):** the 2026-09-29 checkpoint's kill-type list
should carry a prereg on Bold's OTM tier in chop regimes: either strike tier ATM in range-chop day-type,
or a theta budget that fires before the -50% cap when price is on-side (the tickers lane's
`theta_budget` exit fired today on tickers-3 QQQ at -40%; the SPY core has `theta_budget_hit` but it
stayed False for 121 minutes). Score it against the whole Bold fill set first, n disclosed.

**Theme:** C3, C29 (exit knobs do not transfer across strike tiers).
