Sweep tasks retired 2026-06-17 (consolidation step-back).
One-off research sweep scheduled tasks whose conclusions are already captured in
CHANGELOG.md (context-24/26/27/28) and markdown/doctrine/LESSONS-LEARNED.md (L132-135):
 - chandelier / chandelier params  -> chandelier ON = confirmed local optimum
 - runner_target / tp1_qty_fraction / tp1_premium -> dead knobs / production optimal
 - no_trade_after / trendline lookback -> baseline confirmed
Task XML exported here for reversibility. Re-register with:
  Register-ScheduledTask -Xml (Get-Content <name>.xml -Raw) -TaskName <name>
