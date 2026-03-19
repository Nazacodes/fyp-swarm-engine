@echo off
REM Runs the swarm node.
REM Usage: run.bat [path\to\config.json]

set "CONFIG=%~1"
if "%CONFIG%"=="" set "CONFIG=%~dp0..\config.json"

cd /d "%~dp0.."

echo Installing required packages (if missing)...
python -m pip install -r "requirements.txt"

echo Starting node (config=%CONFIG%)...
python "src\node.py" --config "%CONFIG%"
