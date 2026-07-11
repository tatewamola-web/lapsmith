@echo off
rem Lapsmith - double-click to start the engine + open the app.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lapsmith.ps1" %*
