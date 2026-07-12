# Lapsmith one-click launcher — no dev tools, just the app.
# Starts the engine (which also serves the UI) and opens the browser.
#
#   scripts\lapsmith.ps1            # Le Mans Ultimate (default)
#   scripts\lapsmith.ps1 -Adapter sim   # demo mode without a game
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
    # Windows App Control sometimes blocks the venv's python.exe copy;
    # fall back to the base interpreter with the venv's packages on path.
    $base = Get-ChildItem "$env:APPDATA\uv\python\cpython-3.12*\python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    try {
        Start-Process -FilePath $python `
            -ArgumentList "-m", "apex_engine", "--adapter", $Adapter `
            -WorkingDirectory $root -WindowStyle Minimized -ErrorAction Stop
    } catch {
        if ($base) {
            $env:PYTHONPATH = "$root\engine;$root\engine\.venv\Lib\site-packages"
            Start-Process -FilePath $base.FullName `
                -ArgumentList "-m", "apex_engine", "--adapter", $Adapter `
                -WorkingDirectory $root -WindowStyle Minimized
        } else {
            Write-Host "Could not start the engine: $_"
        }
    }
}

# wait for the engine to actually answer before opening the browser
$ready = $false
for ($i = 0; $i -lt 25; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/status" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Host "Engine did not start within 25s - check that Python is not blocked by Windows security."
    Read-Host "Press Enter to close"
    exit 1
}

Start-Process "http://localhost:8000"
Write-Host "Lapsmith running at http://localhost:8000 (engine adapter: $Adapter)"
Write-Host "Close the minimized python window to stop the engine."
