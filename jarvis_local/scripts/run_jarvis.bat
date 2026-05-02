@echo off
setlocal
set "PROJECT_DIR=%~dp0.."
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python.exe"
cd /d "%PROJECT_DIR%"
start "" /min "%PYTHON%" "%PROJECT_DIR%\main.py"
