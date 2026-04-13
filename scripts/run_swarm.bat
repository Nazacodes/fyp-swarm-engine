@echo off
REM Launches two node instances for swarm demo.
REM Requires RabbitMQ to be running.

cd /d "%~dp0.."

echo Installing required packages (if missing)...
python -m pip install -r "requirements.txt"

echo Starting node1 in zone_1...
start "Node1" cmd /c "set NODE_ID=node1 && set GROUP_ID=zone_1 && python src\node.py"

timeout /t 2 /nobreak >nul

echo Starting node2 in zone_2...
start "Node2" cmd /c "set NODE_ID=node2 && set GROUP_ID=zone_2 && python src\node.py"

echo Both nodes started. Close the windows to stop them.
pause
