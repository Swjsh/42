@echo off
set PYTHONPATH=C:\Users\jackw\Desktop\42\backtest\.venv\Lib\site-packages
set PY=C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe
set ROOT=C:\Users\jackw\Desktop\42
set OUT=%ROOT%\backtest\autoresearch\results

echo [%TIME%] Starting runner sweep...
"%PY%" "%ROOT%\backtest\autoresearch\aggressive_runner_sweep.py" > "%OUT%\runner_sweep.txt" 2> "%OUT%\runner_sweep_err.txt"
echo [%TIME%] Runner sweep done (exit %ERRORLEVEL%)

echo [%TIME%] Starting TP1 fraction sweep...
"%PY%" "%ROOT%\backtest\autoresearch\aggressive_tp1_fraction_sweep.py" > "%OUT%\tp1_sweep.txt" 2> "%OUT%\tp1_sweep_err.txt"
echo [%TIME%] TP1 sweep done (exit %ERRORLEVEL%)

echo [%TIME%] Starting VIX cap sweep...
"%PY%" "%ROOT%\backtest\autoresearch\aggressive_vix_bull_cap_sweep.py" > "%OUT%\vix_cap_sweep.txt" 2> "%OUT%\vix_cap_sweep_err.txt"
echo [%TIME%] VIX cap sweep done (exit %ERRORLEVEL%)

echo All sweeps complete.
