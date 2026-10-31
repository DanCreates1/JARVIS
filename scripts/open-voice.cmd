@echo off
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
if not exist "uv.lock" (
    echo JARVIS repository lockfile missing.
    exit /b 1
)

echo JARVIS local checkout: %CD%
setlocal
set "JARVIS_RUNTIME_PROFILE=foreground-voice"
set "JARVIS_OLLAMA_MODEL=qwen3:1.7b"
echo Foreground voice: local transcription, reviewed draft, explicit Send, text replies.
echo Host configuration and software voice control must already be enabled; no automatic capture.
echo Existing Core must be stopped by its owner before starting another writer.
if "%~1"=="" (
    rtk proxy uv run --locked --extra voice python -m jarvis serve
) else (
    rtk proxy uv run --locked --extra voice python -m jarvis %*
)
exit /b %errorlevel%
