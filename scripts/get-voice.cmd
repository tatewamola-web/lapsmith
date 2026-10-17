@echo off
rem Downloads Lapsmith's race-engineer voice (Piper "Ryan", ~120 MB) into
rem data\voices. Only needed once, on a fresh install.
if not exist "%~dp0..\data\voices" mkdir "%~dp0..\data\voices"
set BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high
curl -L -o "%~dp0..\data\voices\en_US-ryan-high.onnx" %BASE%/en_US-ryan-high.onnx
curl -L -o "%~dp0..\data\voices\en_US-ryan-high.onnx.json" %BASE%/en_US-ryan-high.onnx.json
echo Voice installed.
pause
