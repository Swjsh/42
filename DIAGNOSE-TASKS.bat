@echo off
REM Diagnose why the trading tasks stopped firing (writes a status file Claude can read).
cd /d "C:\Users\jackw\Desktop\42"
powershell -NoProfile -ExecutionPolicy Bypass -File "setup\scripts\fix-trading-tasks.ps1"
echo.
echo Status written to automation\state\trading-tasks-status.json
echo Tell Claude it's done, or re-run SETUP with -Fix to auto-enable. Press any key to close.
pause >nul
