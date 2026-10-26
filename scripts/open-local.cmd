@echo off
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
if not exist "uv.lock" (
    echo JARVIS repository lockfile missing.
    exit /b 1
)
echo JARVIS local checkout: %CD%
setlocal
set "JARVIS_RUNTIME_PROFILE=prototype-text"
set "JARVIS_OLLAMA_MODEL=qwen3:1.7b"
echo Text prototype: local Ollama qwen3:1.7b; Chat and Settings.
echo Existing Core must be stopped by its owner before starting another writer.
if "%~1"=="" (
    rtk proxy uv run --locked python -m jarvis serve
) else (
    rtk proxy uv run --locked python -m jarvis %*
)
exit /b %errorlevel%
