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
REM System pythonw.exe -- the venv's own pythonw.exe stub resolves to the CONSOLE
REM python.exe and opens a terminal window per fire (GOAL-SILENT-RIG R6a).
set PYTHONW=C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe
set PYTHONPATH=%REPO%\backtest\.venv\Lib\site-packages
set VIRTUAL_ENV=%REPO%\backtest\.venv
set LOGFILE=%REPO%\backtest\autoresearch\_state\j_strategy\launcher.log

if not exist "%REPO%\backtest\autoresearch\_state\j_strategy" mkdir "%REPO%\backtest\autoresearch\_state\j_strategy"

cd /d "%REPO%\backtest"

REM start /B detaches without spawning a new console window.
REM "" is the (empty) window title required by start when first arg has spaces.
start "" /B "%PYTHONW%" -m autoresearch.j_strategy_phases %* > "%LOGFILE%" 2>&1

echo Launched J-strategy phases silently. Log: %LOGFILE%
exit /b 0
