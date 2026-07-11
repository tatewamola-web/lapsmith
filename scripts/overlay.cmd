@echo off
rem Lapsmith overlay - double-click to run (engine must be running).
rem Ctrl+Alt+O = click-through, Ctrl+Alt+H = hide.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0overlay.ps1"
