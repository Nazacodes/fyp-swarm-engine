<#
Runs all 50 swarm nodes in parallel.

Usage:
  .\run_50_nodes.ps1 [-Monitor] [-Visualize]

Defaults: monitor=yes, visualize=yes
#>

param(
    [switch]$Monitor,
    [switch]$Visualize
)

# Default to true if not specified
if (-not $PSBoundParameters.ContainsKey('Monitor')) { $Monitor = $true }
if (-not $PSBoundParameters.ContainsKey('Visualize')) { $Visualize = $true }

Set-Location "$PSScriptRoot\.."

Write-Host "Installing required packages (if missing)..."
python -m pip install -r "requirements.txt" -q

Write-Host "Starting 50 nodes..."

# Start all 50 nodes
for ($i = 1; $i -le 50; $i++) {
    $nodeId = "node$i"
    Write-Host "Starting $nodeId..."
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList "src\node.py", "--config", "config_node$i.json"
    Start-Sleep -Milliseconds 500
}

Write-Host "50 nodes started!"
Start-Sleep -Seconds 2

if ($Monitor) {
    Write-Host "Starting web monitor..."
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList "src\web_monitor.py", "--host", "0.0.0.0"
}

if ($Visualize) {
    Write-Host "Starting visualization..."
    Start-Process -FilePath "python" -ArgumentList "src\visualize.py"
}

Write-Host "All components started! Press Ctrl+C to stop."
Read-Host
