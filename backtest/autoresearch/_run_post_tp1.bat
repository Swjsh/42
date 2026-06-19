@echo off
"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe" -u "C:\Users\jackw\Desktop\42\backtest\autoresearch\tp1_subwindow.py" > "C:\Users\jackw\Desktop\42\backtest\autoresearch\_tp1_subwindow_out.txt" 2> "C:\Users\jackw\Desktop\42\backtest\autoresearch\_tp1_subwindow_err.txt"
echo [tp1_subwindow done] >> "C:\Users\jackw\Desktop\42\backtest\autoresearch\_post_tp1_status.txt"
"C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe" -u "C:\Users\jackw\Desktop\42\backtest\autoresearch\remaining_c14_sweep.py" > "C:\Users\jackw\Desktop\42\backtest\autoresearch\_remaining_c14_out.txt" 2> "C:\Users\jackw\Desktop\42\backtest\autoresearch\_remaining_c14_err.txt"
echo [remaining_c14 done] >> "C:\Users\jackw\Desktop\42\backtest\autoresearch\_post_tp1_status.txt"
