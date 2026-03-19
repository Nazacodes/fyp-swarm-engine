<#
Runs the complete swarm demo: multiple nodes, web monitor, and visualization.

Usage:
  .\run_all.ps1 [-Nodes <count>] [-Monitor] [-Visualize]

Defaults: 3 nodes, monitor=yes, visualize=yes
#>

param(
    [int]$Nodes = 3,
    [switch]$Monitor,
    [switch]$Visualize
)

# Default to true if not specified
if (-not $PSBoundParameters.ContainsKey('Monitor')) { $Monitor = $true }
if (-not $PSBoundParameters.ContainsKey('Visualize')) { $Visualize = $true }

Set-Location "$PSScriptRoot\.."

Write-Host "Installing required packages (if missing)..."
python -m pip install -r "requirements.txt"

Write-Host "Starting $Nodes nodes..."

# Start nodes
for ($i = 1; $i -le $Nodes; $i++) {
    $nodeId = "node$i"
    Write-Host "Starting $nodeId..."
    Start-Process -NoNewWindow -FilePath "cmd" -ArgumentList "/c", "set NODE_ID=$nodeId && python src\node.py"
    Start-Sleep -Seconds 1
}

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
