# APEX one-click launcher — no dev tools, no Claude, just the app.
# Starts the engine (which also serves the UI) and opens the browser.
#
#   scripts\apex.ps1            # Le Mans Ultimate (default)
#   scripts\apex.ps1 -Adapter sim   # demo mode without a game
param([string]$Adapter = "lmu")

$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root "engine\.venv\Scripts\python.exe"

# Reuse a running engine if one is already listening.
$up = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/status" -TimeoutSec 2 -UseBasicParsing
    $up = $r.StatusCode -eq 200
} catch {}

if (-not $up) {
    Start-Process -FilePath $python `
        -ArgumentList "-m", "apex_engine", "--adapter", $Adapter `
        -WorkingDirectory $root -WindowStyle Minimized
    Start-Sleep -Seconds 3
}

Start-Process "http://localhost:8000"
Write-Host "APEX running at http://localhost:8000 (engine adapter: $Adapter)"
Write-Host "Close the minimized python window to stop the engine."
