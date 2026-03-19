@echo off
REM Runs the real-time visualization for the swarm ACO.
REM Usage: run_visualize.bat

cd /d "%~dp0.."

echo Installing required packages (if missing)...
python -m pip install -r "requirements.txt"

echo Starting visualization (close window to stop)...
python "src\visualize.py"
