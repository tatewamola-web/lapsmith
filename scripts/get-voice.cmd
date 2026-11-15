@echo off
rem Downloads Lapsmith's engineer voices (Piper neural TTS) into data\voices.
rem Only needed once, on a fresh install.
if not exist "%~dp0..\data\voices" mkdir "%~dp0..\data\voices"
set B=https://huggingface.co/rhasspy/piper-voices/resolve/main/en
set D=%~dp0..\data\voices
for %%V in (en_US/ryan/high/en_US-ryan-high en_GB/alan/medium/en_GB-alan-medium en_GB/northern_english_male/medium/en_GB-northern_english_male-medium) do (
  for %%F in (%%~nxV) do (
    curl -L -o "%D%\%%F.onnx" %B%/%%V.onnx
    curl -L -o "%D%\%%F.onnx.json" %B%/%%V.onnx.json
  )
)
echo Voices installed.
pause
