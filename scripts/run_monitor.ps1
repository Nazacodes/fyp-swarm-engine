<#
Runs the web monitor for the swarm system.

Usage:
  .\run_monitor.ps1 [-BindHost <host>] [-Port <port>]
#>

param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 5000
)

Set-Location "$PSScriptRoot\.."

Write-Host "Installing required packages (if missing)..."
python -m pip install -r "requirements.txt"

Write-Host "Starting web monitor on http://$BindHost`:$Port ..."
python "src\web_monitor.py" --host $BindHost --port $Port
