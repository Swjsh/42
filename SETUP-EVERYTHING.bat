@echo off
REM ===================================================================
REM  Gamma - Setup Everything.  Double-click this ONCE.
REM  Runs every manual action-item from the deep-review session:
REM    1. Git: repair/init + commit + push (your rollback safety net)
REM    2. Freshness watchdog (staleness becomes loud)
REM    3. Prune the 1.6 GB crypto hoard (reversible / quarantined)
REM    4. Wire the freshness check into Task Scheduler (hourly)
REM  Safe to re-run any time.
REM ===================================================================
cd /d "C:\Users\jackw\Desktop\42"
powershell -NoProfile -ExecutionPolicy Bypass -File "setup\scripts\setup-all.ps1"
echo.
echo Finished. Review the output above. Press any key to close.
pause >nul
