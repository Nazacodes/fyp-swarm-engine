@echo off
REM Runs the web monitor for the swarm system.
REM Usage: run_monitor.bat [host] [port]

set "HOST=%~1"
if "%HOST%"=="" set "HOST=0.0.0.0"

set "PORT=%~2"
if "%PORT%"=="" set "PORT=5000"

cd /d "%~dp0.."

echo Installing required packages (if missing)...
python -m pip install -r "requirements.txt"

echo Starting web monitor on http://%HOST%:%PORT% ...
python "src\web_monitor.py" --host %HOST% --port %PORT%
