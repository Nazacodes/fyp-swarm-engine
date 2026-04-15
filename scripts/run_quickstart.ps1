<#
Quickly starts the local swarm stack via supervisor:
1) Verifies RabbitMQ connectivity
2) Starts web monitor + N nodes
3) Auto-restarts stale/dead nodes

Usage:
  .\scripts\run_quickstart.ps1
  .\scripts\run_quickstart.ps1 -Nodes 5 -MonitorPort 5000
  .\scripts\run_quickstart.ps1 -Nodes 20 -MonitorPort 5000 -BatchSize 5
  .\scripts\run_quickstart.ps1 -Nodes 20 -MonitorPort 5000 -BatchSize 5 -Groups 4
#>

param(
    [int]$Nodes = 3,
    [int]$MonitorPort = 5000,
    [int]$BatchSize = 5,
    [int]$Groups = 1
)

Set-Location "$PSScriptRoot\.."

Write-Host "Cleaning old python processes..."
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "Installing required packages (if missing)..."
python -m pip install -r "requirements.txt" | Out-Null

Write-Host "Checking RabbitMQ..."
python "src\test_rabbitmq.py" --host localhost --user guest --password guest
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "RabbitMQ check failed. Start RabbitMQ first, then retry."
    exit $LASTEXITCODE
}

Write-Host "Starting supervisor (nodes=$Nodes, port=$MonitorPort, batch=$BatchSize, groups=$Groups)..."
python "scripts\supervisor.py" --nodes $Nodes --port $MonitorPort --batch-size $BatchSize --groups $Groups
