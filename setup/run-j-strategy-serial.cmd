@echo off
REM ============================================================================
REM Run J-strategy phases SERIAL in ONE visible cmd window.
REM Workers=1 means NO multiprocessing.Pool. NO worker spawn. NO window flashes.
REM This window stays open and streams progress. Closing it kills the run.
REM ============================================================================

set REPO=C:\Users\jackw\Desktop\42
set PYTHON=%REPO%\backtest\.venv\Scripts\python.exe
set LOGFILE=%REPO%\backtest\autoresearch\_state\j_strategy\phases.log

if not exist "%REPO%\backtest\autoresearch\_state\j_strategy" mkdir "%REPO%\backtest\autoresearch\_state\j_strategy"

cd /d "%REPO%\backtest"
title J-Strategy Phases (serial, 1 window)

echo ============================================================================
echo J-STRATEGY PHASES — SERIAL MODE — ONE WINDOW ONLY
echo ============================================================================
echo Log file: %LOGFILE%
echo Closing this window will kill the run.
echo ============================================================================

"%PYTHON%" -m autoresearch.j_strategy_phases --workers 1 %*

echo.
echo ============================================================================
echo DONE. Check log file: %LOGFILE%
echo ============================================================================
pause
