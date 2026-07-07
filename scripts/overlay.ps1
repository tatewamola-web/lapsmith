# Lapsmith in-game overlay. Needs the engine running (scripts\lapsmith.ps1)
# and the game in borderless-windowed mode.
# Ctrl+Alt+O toggles click-through, Ctrl+Alt+H hides.
$root = Split-Path $PSScriptRoot -Parent
$env:Path = "C:\Program Files\nodejs;$env:Path"
Set-Location (Join-Path $root "ui")
npx electron electron\overlay-main.cjs
