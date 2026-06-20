@echo off
setlocal
cd /d "%~dp0"

set "DAREVSKIA_PROJECT_DIR=E:\Darevskia_ID"
set "DAREVSKIA_HOST=127.0.0.1"
set "DAREVSKIA_PORT=8094"

set "PYTHON_EXE="
if exist "%~dp0..\lizard_ai_env\Scripts\python.exe" set "PYTHON_EXE=%~dp0..\lizard_ai_env\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

echo Starting Darevskia ID local app...
echo.
echo After the server starts, open:
echo http://127.0.0.1:8094/
echo.
"%PYTHON_EXE%" "%~dp0darevskia_web_app.py" --host %DAREVSKIA_HOST% --port %DAREVSKIA_PORT% --project-dir "%DAREVSKIA_PROJECT_DIR%"

endlocal
