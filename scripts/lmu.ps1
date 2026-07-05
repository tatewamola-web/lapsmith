# Start engine (Le Mans Ultimate adapter) + UI dev server.
# LMU must have Settings -> Gameplay -> Enable Plugins: ON.
$root = Split-Path $PSScriptRoot -Parent
$env:Path = "C:\Program Files\nodejs;$env:Path"

Start-Process -FilePath (Join-Path $root "engine\.venv\Scripts\python.exe") `
    -ArgumentList "-m", "apex_engine", "--adapter", "lmu" `
    -WorkingDirectory $root -WindowStyle Minimized

Set-Location (Join-Path $root "ui")
npm run dev
