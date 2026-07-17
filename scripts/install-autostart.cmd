@echo off
rem Double-click me ONCE to make the Lapsmith engine start automatically
rem with Windows (silently, no browser popup). After this you never run
rem a script again - the engine is simply always on, recording whenever
rem the game runs. Open http://localhost:8000 anytime to see your data.
rem To undo: delete "Lapsmith Engine" from shell:startup.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = New-Object -ComObject WScript.Shell; $lnk = $s.CreateShortcut([IO.Path]::Combine($s.SpecialFolders('Startup'), 'Lapsmith Engine.lnk')); $lnk.TargetPath = '%~dp0lapsmith.cmd'; $lnk.Arguments = '-NoBrowser'; $lnk.WindowStyle = 7; $lnk.Save(); Write-Host 'Installed: Lapsmith engine will start with Windows.'"
pause
