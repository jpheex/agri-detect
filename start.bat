@echo off
cd /d %~dp0
set PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PY%" set PY=python
"%PY%" -m pip install -r requirements.txt -q
"%PY%" -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
pause
