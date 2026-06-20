@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "%~dp0..\\lizard_ai_env\\Scripts\\python.exe" set "PYTHON_EXE=%~dp0..\\lizard_ai_env\\Scripts\\python.exe"
if not defined PYTHON_EXE if exist "%~dp0.venv\\Scripts\\python.exe" set "PYTHON_EXE=%~dp0.venv\\Scripts\\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

"%PYTHON_EXE%" "%~dp0darevskia_web_app.py"
endlocal
