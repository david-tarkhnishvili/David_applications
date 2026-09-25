@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

echo Starting ARRDP locally at http://127.0.0.1:8094/
echo No account or password is required.
"%PYTHON_EXE%" "%~dp0arrdp_web_app.py" --host 127.0.0.1 --port 8094
endlocal
