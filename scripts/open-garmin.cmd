@echo off
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
if not exist "uv.lock" (
    echo JARVIS repository lockfile missing.
    exit /b 1
)

echo JARVIS local checkout: %CD%
setlocal
set "JARVIS_RUNTIME_PROFILE=private-garmin"
set "JARVIS_OLLAMA_MODEL=qwen3:1.7b"
echo Private Garmin: local daily text plus scoped read-only Garmin.
echo Existing Core must be stopped by its owner before starting another writer.
echo Existing health scope required. No login, import or enrollment occurs at startup.
if "%~1"=="" (
    rtk proxy uv run --locked python -m jarvis serve
) else (
    rtk proxy uv run --locked python -m jarvis %*
)
exit /b %errorlevel%
