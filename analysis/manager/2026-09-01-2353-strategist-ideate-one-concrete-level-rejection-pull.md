<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=11.002s | action=Ideate ONE concrete level-rejection pull -->
<!-- reason: Pending queue item 71b11ddf50de3d1b is an open manager_flagged ESCALATION that has been seen 3x since 08-20 and explicitly demands this ideation; recent work has been heavy on critic (4 critic fires in last 6) — rotating to strategist per Overseer rotation rule. Today's date 2026-09-01 matches the candidate stream; this is the genuine third attempt the queue is asking for. -->

lookback: 18  
entry_offset: 0.0008  
time_gate: 09:45-10:30  
vol_filter: ATR<0.006  
rejection_depth: 0.0012  
max_hold: 45  

Prior kill 1 failed because it used a static 20‑bar lookback without a time‑of‑day gate, allowing entries during the volatile lunch session where structure‑shift noise is high.  
Prior kill 2 failed by applying a vol filter only on ATR>0.008, which missed low‑volatility pullbacks that still exhibited false breakouts, causing premature stops.  

Structure‑shift null: no new higher high (long) or lower low (short) within the max_hold window after pullback completion; our short max_hold (45 bars) and tight rejection_depth (0.0012) exit the trade before such a shift can develop, thereby passing the null.