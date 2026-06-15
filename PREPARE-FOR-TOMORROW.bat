@echo off
REM ===================================================================
REM  Gamma - Prepare For Tomorrow.  Double-click this.
REM  Validates config, runs engine self-tests, checks freshness +
REM  scheduled tasks, and snapshots to git. Safe to run every evening.
REM ===================================================================
cd /d "C:\Users\jackw\Desktop\42"
powershell -NoProfile -ExecutionPolicy Bypass -File "setup\scripts\prepare-for-tomorrow.ps1"
echo.
echo Done. Review any [!!] lines above. Press any key to close.
pause >nul
