#!/usr/bin/env pwsh
# RETIRED 2026-06-29 -- replaced by setup/scripts/preopen_readiness.py
#
# This script was a STALE time-bomb: it verified `Gamma_Heartbeat` (the LLM
# heartbeat RETIRED 2026-06-25) as "the heartbeat", omitted the actual live
# engine `Gamma_HeartbeatCore` + the never-blind eye `Gamma_SightBeacon`,
# hardcoded a "5/14" date, and had NO broker-auth check. A readiness audit that
# verifies a DEAD task reports a false-GREEN while the real engine is unverified
# (C7: a stale audit masks live state).
#
# The replacement `preopen_readiness.py` checks the LIVE chain (HeartbeatCore +
# SightBeacon + EodFlatten) AND broker auth (both accounts: ACTIVE / not blocked
# / options level / PDT headroom), emits a machine-readable GREEN/YELLOW/RED
# verdict to automation/state/preopen-readiness.json, and is pytest-guarded
# (backtest/tests/test_preopen_readiness.py) so it cannot silently go stale again.
Write-Output "preflight-readiness-audit.ps1 is RETIRED. Use: python setup/scripts/preopen_readiness.py"
exit 1
