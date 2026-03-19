<#
Runs the real-time visualization for the swarm ACO.

Usage:
  .\run_visualize.ps1
#>

param()

Set-Location "$PSScriptRoot\.."

Write-Host "Installing required packages (if missing)..."
python -m pip install -r "requirements.txt"

Write-Host "Starting visualization (close window to stop)..."
python "src\visualize.py"
