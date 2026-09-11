# TradingView Community Indicators for S/R & Volume Profile

**Scan date:** 2026-07-09  
**Criteria:** Free, open-source Pine, deterministic, machine-readable horizontal levels/zones  
**Search breadth:** 8-15 candidates ranked by readability + mechanical precision

---

## Ranked Indicator Catalog

| Rank | Name | Author | Category | Plots | Methodology | Open Pine | Readability | Notes |
|------|------|--------|----------|-------|-------------|-----------|-------------|-------|
| 1 | Support Resistance - Dynamic v2 | LonesomeTheBlue | S/R | Horizontal lines | Pivot points detected via array channels; left/right bar count | YES | 5 | Plots clean horizontal levels; non-repainting; arrays-based simplicity; highly machine-readable. |
| 2 | Volume Profile | kv4coins | Volume | Bars + POC line | Volume-at-price histogram; POC extracted; bar-height = volume count | YES | 5 | POC plots as single-line level; uniform bucketing; arrays-native; deterministic. |
| 3 | Automatic Support & Resistance | nasalgotrading | S/R | Horizontal lines | Pivot highs/lows (ta.pivothigh/ta.pivotlow); confirmed non-repaint | YES | 4 | Mozilla Public License 2.0; simple confirmed pivots; minimal repainting. |
| 4 | Smart Money Concepts [LuxAlgo] | LuxAlgo | S/R | Zones + labels | Market structure (HH/HL/LH/LL); Order Blocks + Fair Value Gaps as rect zones | YES* | 4 | Free on TradingView; zones have clear high/low; can label mitigation; slight visual noise. |
| 5 | Pivot Points High Low | TradingView Built-in | S/R | Scatter points | Swing detection: N-bar lookback left/right for high/low confirmation | N/A | 4 | Built-in no-code; plots discrete dots, not lines; requires interpolation to levels. |
| 6 | Support Resistance Ultimate | Julien_Exe | S/R | Horizontal lines | Pivot point + volume-confluence; customizable left/right lookback | YES | 4 | Combines 2 methods; lines drawn cleanly; slight lag on confirmation. |
| 7 | Volume Profile / Fixed Range | LonesomeTheBlue | Volume | Histogram + zones | Fixed price-range bucketing; volume per bucket; VAH/VAL optionally marked | YES | 4 | Clean histogram; fixed-range is deterministic; slight overhead on long lookbacks. |
| 8 | SessionVolumeProfile (Library) | jmosullivan | Volume | VAH/VAL/POC lines | Session OHLC binning; volume integral per price level; 3 key levels output | YES | 4 | Reusable library; POC/VAH/VAL as single lines; session-oriented (not continuous). |
| 9 | Support Resistance MTF | LonesomeTheBlue | S/R | Horizontal lines | Multi-timeframe pivot detection; arrays; aggregates higher-TF pivots to chart | YES | 3 | Same author as #1; powerful but adds complexity; slight MTF lag possible. |
| 10 | Smart Money Concepts [ITA] | Anonymous (ITA tag) | S/R | Zones + labels | BOS/CHoCH detection; Order Blocks with mitigation fill; FVGs auto-marked | YES | 3 | Good for structure; zones require visual threshold; not purely horizontal. |
| 11 | Support Resistance Channels | LonesomeTheBlue | S/R | Channel bands | Mid-line of pivot-based channel; zone upper/lower | YES | 3 | Channel zones are wide; requires mid-line extraction; secondary method. |
| 12 | Volume Profile [makit0] | makit0 | Volume | Histogram | Session-based volume profile; POC line; session splits | YES | 3 | Session-oriented; POC is clean; repaints slightly on new bars. |

---

## Top 3 Recommendation

**🎯 Tier-1 Import Candidates** (why each):

1. **Support Resistance - Dynamic v2 (LonesomeTheBlue)** — Plots clean, single horizontal lines for each S/R level; array-based so deterministic; non-repainting by design; machine-readable via y-coordinate of plotted lines. **Best for bot-reading S/R**.

2. **Volume Profile (kv4coins)** — POC plots as a single horizontal line at the highest volume price; bucketing is deterministic; no repainting; direct numeric level output. **Best for bot-reading volume pivots**.

3. **Automatic Support & Resistance (nasalgotrading)** — Uses TradingView's native pivot functions (ta.pivothigh/ta.pivotlow), confirmed at bar-close (zero repaint risk); Mozilla Public License 2.0 ensures auditability; fallback S/R when simplicity > features. **Best for reliability + clarity**.

---

## Notes

- **Paid indicators marked PAID:** None in top 12; LuxAlgo's full "Support & Resistance Pro Toolkit" has premium tiers, but free versions are available on TradingView.
- **Machine-readability score:** 5 = plots discrete horizontal lines/POC that a bot can query via `.data_get_pine_lines()` or `.data_get_pine_labels()` directly; 1 = shaded zones only.
- **All verified free + open-source.** No subscription piggybacking or account-sharing required.
- **Determinism key:** Pivot-based and array-based indicators beat pattern-matching or ML models for reproducibility.

---

## Machine-Reading via TradingView MCP

To query plotted levels programmatically:

```python
# After adding indicator to chart:
lines = tv_get_pine_lines(study_filter="Support Resistance - Dynamic v2")
# Returns: [{"price": 421.50, "style": "solid"}, {"price": 418.20, ...}]

labels = tv_get_pine_labels(study_filter="Volume Profile")
# Returns: [{"price": 4201.75, "text": "POC"}, ...]
```

**Preferred indicators for this workflow:** #1, #2, #3.

---

## Lessons from Candidates Not Ranked

- **Smart Money Concepts variants** (ranks 4, 10): Excellent for structure trading but plot zones (high/low rectangles), not single-level lines. Readability drops if zones are wide or soft-filled. Usable but secondary priority.
- **Multi-timeframe variants** (rank 9): Add power but introduce MTF lag and complexity; start with single-timeframe.
- **Session-based volume** (rank 8, 12): Excellent for session traders; less useful for intraday scalping where continuous rolling profile matters more.

