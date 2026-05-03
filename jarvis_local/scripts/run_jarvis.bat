@echo off
setlocal
set "PROJECT_DIR=%~dp0.."
set "PYTHON=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"
if not exist "%PYTHON%" set "PYTHON=pythonw.exe"
cd /d "%PROJECT_DIR%"
start "" /min "%PYTHON%" "%PROJECT_DIR%\main.py"
