@echo off
setlocal

cd /d "%~dp0"

set PORT=8765
set URL=http://127.0.0.1:%PORT%/

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  start "Ecosystem Guild Builder Server" /min python -m http.server %PORT% --bind 127.0.0.1
  timeout /t 1 /nobreak >nul
  start "" "%URL%"
  exit /b 0
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  start "Ecosystem Guild Builder Server" /min py -m http.server %PORT% --bind 127.0.0.1
  timeout /t 1 /nobreak >nul
  start "" "%URL%"
  exit /b 0
)

where powershell >nul 2>nul
if %ERRORLEVEL%==0 (
  start "Ecosystem Guild Builder Server" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ecosystem_server.ps1"
  timeout /t 2 /nobreak >nul
  start "" "%URL%"
  exit /b 0
)

echo Neither Python nor PowerShell was found. Opening index.html directly.
echo The app will open, but Load species.csv may require the local server.
pause
start "" "%~dp0index.html"
