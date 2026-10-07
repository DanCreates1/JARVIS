@echo off
cd /d "%~dp0.."
if errorlevel 1 exit /b 1
if not exist "uv.lock" (
    echo JARVIS repository lockfile missing.
    exit /b 1
)
echo JARVIS local checkout: %CD%
echo Chat: uv run jarvis chat
echo Doctor: uv run jarvis doctor
echo Garmin report: uv run python scripts/garmin_report.py
