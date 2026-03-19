<#
Runs the swarm node.

Usage:
  .\run.ps1 [-Config <path>]

By default it will use a config file at the repo root named "config.json".
#>

param(
    [string]$Config = "$PSScriptRoot\..\config.json"
)

Set-Location "$PSScriptRoot\.."

Write-Host "Installing required packages (if missing)..."
python -m pip install -r "requirements.txt"

Write-Host "Starting node (config=$Config)..."
python "src\node.py" --config $Config
