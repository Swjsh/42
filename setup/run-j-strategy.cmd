@echo off
REM ============================================================================
REM Run J-strategy phases SILENTLY (no console window, no focus theft).
REM
REM Uses pythonw.exe (no console allocation) + start /B (background, no new window).
REM Multiprocessing workers inherit pythonw -> NO console flashes.
REM
REM Output goes to:
REM   backtest/autoresearch/_state/j_strategy/phases.log
REM ============================================================================

set REPO=C:\Users\jackw\Desktop\42
set PYTHONW=%REPO%\backtest\.venv\Scripts\pythonw.exe
set LOGFILE=%REPO%\backtest\autoresearch\_state\j_strategy\launcher.log

if not exist "%REPO%\backtest\autoresearch\_state\j_strategy" mkdir "%REPO%\backtest\autoresearch\_state\j_strategy"

cd /d "%REPO%\backtest"

REM start /B detaches without spawning a new console window.
REM "" is the (empty) window title required by start when first arg has spaces.
start "" /B "%PYTHONW%" -m autoresearch.j_strategy_phases %* > "%LOGFILE%" 2>&1

echo Launched J-strategy phases silently. Log: %LOGFILE%
exit /b 0
