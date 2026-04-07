@echo off
REM Runs 5 swarm nodes in parallel.
REM Usage: run_5_nodes.bat [monitor] [visualize]
REM Defaults: monitor=yes, visualize=yes

setlocal enabledelayedexpansion

set "MONITOR=%~1"
if "%MONITOR%"=="" set "MONITOR=yes"

set "VISUALIZE=%~2"
if "%VISUALIZE%"=="" set "VISUALIZE=yes"

cd /d "%~dp0.."

echo Installing required packages (if missing)...
python -m pip install -r "requirements.txt" >nul 2>&1

echo Starting 5 nodes...

for /l %%i in (1,1,5) do (
    set "nodeId=node%%i"
    echo Starting !nodeId!...
    start "!nodeId!" cmd /c "python src\node.py --config config_node%%i.json"
    timeout /t 1 /nobreak >nul
)

timeout /t 2 /nobreak >nul

if "%MONITOR%"=="yes" (
    echo Starting web monitor...
    start "Monitor" cmd /c "python src\web_monitor.py --host 0.0.0.0"
)

if "%VISUALIZE%"=="yes" (
    echo Starting visualization...
    start "Visualize" python "src\visualize.py"
)

echo All 5 nodes started! Close the windows to stop.
pause