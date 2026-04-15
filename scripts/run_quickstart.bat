@echo off
setlocal EnableDelayedExpansion
REM Quick startup via supervisor:
REM 1) RabbitMQ connectivity check
REM 2) Start monitor + nodes in batches
REM 3) Auto-restart stale/dead nodes
REM
REM Usage:
REM   scripts\run_quickstart.bat
REM   scripts\run_quickstart.bat 5 5000
REM   scripts\run_quickstart.bat 20 5000 5
REM   scripts\run_quickstart.bat 20 5000 5 4

set "NODES=%~1"
if "%NODES%"=="" set "NODES=3"

set "PORT=%~2"
if "%PORT%"=="" set "PORT=5000"

set "BATCH=%~3"
if "%BATCH%"=="" set "BATCH=5"

set "GROUPS=%~4"
if "%GROUPS%"=="" set "GROUPS=1"

cd /d "%~dp0.."

echo Cleaning old python processes...
taskkill /F /IM python.exe >nul 2>nul
timeout /t 1 /nobreak >nul

echo Installing required packages (if missing)...
python -m pip install -r "requirements.txt" >nul

echo Checking RabbitMQ...
python "src\test_rabbitmq.py" --host localhost --user guest --password guest
if errorlevel 1 (
  echo.
  echo RabbitMQ check failed. Start RabbitMQ first, then retry.
  exit /b 1
)

echo Starting supervisor (nodes=%NODES%, port=%PORT%, batch=%BATCH%, groups=%GROUPS%)...
python "scripts\supervisor.py" --nodes %NODES% --port %PORT% --batch-size %BATCH% --groups %GROUPS%
