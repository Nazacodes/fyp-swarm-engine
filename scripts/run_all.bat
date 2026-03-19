@echo off
REM Runs the complete swarm demo: multiple nodes, web monitor, and visualization.
REM Usage: run_all.bat [nodes] [monitor] [visualize]
REM Defaults: 3 nodes, monitor=yes, visualize=yes

set "NODES=%~1"
if "%NODES%"=="" set "NODES=3"

set "MONITOR=%~2"
if "%MONITOR%"=="" set "MONITOR=yes"

set "VISUALIZE=%~3"
if "%VISUALIZE%"=="" set "VISUALIZE=yes"

cd /d "%~dp0.."

echo Installing required packages (if missing)...
python -m pip install -r "requirements.txt"

echo Starting %NODES% nodes...

for /l %%i in (1,1,%NODES%) do (
    echo Starting node%%i...
    start "Node%%i" cmd /c "set NODE_ID=node%%i && python src\node.py"
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

echo All components started! Close the windows to stop.
pause
