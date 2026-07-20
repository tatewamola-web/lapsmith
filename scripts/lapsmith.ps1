# Lapsmith one-click launcher — no dev tools, just the app.
# Starts the engine (which also serves the UI) and opens the browser.
#
#   scripts\lapsmith.ps1                 # Le Mans Ultimate (default)
#   scripts\lapsmith.ps1 -Adapter sim    # demo mode without a game
#   scripts\lapsmith.ps1 -NoBrowser      # start engine only (autostart)
param([string]$Adapter = "lmu", [switch]$NoBrowser)

$root = Split-Path $PSScriptRoot -Parent

# Reuse a running engine if one is already listening.
$up = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/status" -TimeoutSec 2 -UseBasicParsing
    $up = $r.StatusCode -eq 200
} catch {}

if (-not $up) {
    # Same environment for any interpreter: the venv's packages ride on
    # PYTHONPATH, so any working CPython 3.12 can run the engine.
    $env:PYTHONPATH = "$root\engine;$root\engine\.venv\Lib\site-packages"
    New-Item -ItemType Directory -Force -Path "$root\data" | Out-Null
    # interpreter-level failures land here; the engine's own log is engine.log
    $log = "$root\data\engine.out.log"
    $errlog = "$root\data\engine.err.log"

    # Candidates: the venv python, then every uv-managed 3.12 (uv upgrades
    # relocate these dirs, which silently breaks the venv's pointer).
    $candidates = @(Join-Path $root "engine\.venv\Scripts\python.exe")
    $candidates += Get-ChildItem "$env:APPDATA\uv\python\cpython-3.12*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -ExpandProperty FullName

    # Never trust a python — PROVE it can import the engine before using it.
    # (A venv whose base interpreter moved "starts" and instantly dies.)
    $exe = $null
    foreach ($c in $candidates) {
        if (-not (Test-Path $c)) { continue }
        & $c -c "import apex_engine, numpy, fastapi" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $exe = $c; break }
    }

    if ($null -eq $exe) {
        Write-Host "No working Python found. Candidates tried:"
        $candidates | ForEach-Object { Write-Host "  $_" }
        Write-Host "Fix: install uv, then run: uv venv engine\.venv --python 3.12 ; uv pip install -e engine --python engine\.venv"
        Read-Host "Press Enter to close"
        exit 1
    }

    Start-Process -FilePath $exe `
        -ArgumentList "-m", "apex_engine", "--adapter", $Adapter `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $log -RedirectStandardError $errlog
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
    Write-Host "Engine did not start within 25s. Last lines of data\engine.err.log:"
    Get-Content "$root\data\engine.err.log" -Tail 5 -ErrorAction SilentlyContinue
    Read-Host "Press Enter to close"
    exit 1
}

if (-not $NoBrowser) {
    Start-Process "http://localhost:8000"
}
Write-Host "Lapsmith running at http://localhost:8000 (engine adapter: $Adapter)"
