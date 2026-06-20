@echo off
setlocal
cd /d "%~dp0"

rem Run this on the stationary computer that stores the Darevskia_ID project folder.
rem Change the password before exposing the app through a tunnel.
set "DAREVSKIA_PROJECT_DIR=E:\Darevskia_ID"
set "DAREVSKIA_HOST=0.0.0.0"
set "DAREVSKIA_PORT=8094"
set "DAREVSKIA_USER=darevskia"
set "DAREVSKIA_PASSWORD=change-this-password"

set "PYTHON_EXE="
if exist "%~dp0..\lizard_ai_env\Scripts\python.exe" set "PYTHON_EXE=%~dp0..\lizard_ai_env\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

"%PYTHON_EXE%" "%~dp0darevskia_web_app.py" --host %DAREVSKIA_HOST% --port %DAREVSKIA_PORT% --project-dir "%DAREVSKIA_PROJECT_DIR%" --no-browser
endlocal
