# Lesson draft: per-sell round-trip banding credits big-position exits to the small-size band

- **Symptom:** headline finding "J profitable at 1-2 lots (+$4,576), 3+ lots −$17,461" (C31,
  from the 2026-06-19 WeBull mining) reverses at the position-episode level: 1-2 lot episodes
  are −$4,420; 3+ episodes −$8,465.
- **Root cause:** the miner counted one round-trip per SELL fill and banded by *sell-fill*
  qty. Profitable partial exits (1-2 lot clips) of 3+ lot positions were credited to the
  "1-2" band (+$8,996 of misattributed P&L), while panic full-dumps landed in the 3+ bands.
  Trade-size stats MUST use max open contracts of the flat→flat episode, never per-exit qty.
- **Fix / evidence:** fresh reconstructor + exact replication of both methods in
  `analysis/j-webull/` (scripts + TRAITS-REPORT.md §1). Prior numbers reproduce to the
  dollar under the old method, so this is a definition artifact, not a parse bug.
- **Doctrine impact:** amend the C31 row wording — the sizing GRADIENT and Rule 4/Rule 6
  implications stand (per-contract expectancy degrades 4× with size; 94% of scale-ins are
  averaging-down, −$8,628); the claim that small-size J was net-profitable does not
  (bootstrap P(sum>0)=0.11). Related theme: C7 (audit outputs), C24.
- **Proposed theme:** extend C31 or new C-row: "Size/banding stats use flat→flat episode
  max-qty; per-exit banding is a known artifact."
