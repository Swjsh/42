@echo off
REM Relaunch TradingView with the CDP debug port (9222) so the heartbeat MCP bridge connects.
REM Use after a restart or when the heartbeat logs ERROR_TV / "MCP bridge unavailable".
cd /d "C:\Users\jackw\Desktop\42"
powershell -NoProfile -ExecutionPolicy Bypass -File "setup\launch_tv_debug.ps1"
echo.
echo TradingView relaunched with --remote-debugging-port=9222. The heartbeat should reconnect on its next 3-min tick.
pause >nul
