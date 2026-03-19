<#
Launches two node instances for swarm demo.
Requires RabbitMQ to be running.
#>

Set-Location "$PSScriptRoot\.."

Write-Host "Installing required packages (if missing)..."
python -m pip install -r "requirements.txt"

Write-Host "Starting node1 (default)..."
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "src\node.py"

Start-Sleep -Seconds 2

Write-Host "Starting node2..."
$env:NODE_ID = "node2"
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "src\node.py"

Write-Host "Both nodes started. Press Ctrl+C to stop."
Read-Host
