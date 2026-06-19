import sys, os
os.environ['PYTHONPATH'] = r'C:\Users\jackw\Desktop\42\backtest\.venv\Lib\site-packages'
sys.path.insert(0, r'C:\Users\jackw\Desktop\42\backtest\.venv\Lib\site-packages')
sys.path.insert(0, r'C:\Users\jackw\Desktop\42\backtest')
exec(open(r'C:\Users\jackw\Desktop\42\backtest\autoresearch\aggressive_runner_sweep.py').read())
