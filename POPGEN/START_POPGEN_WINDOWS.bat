@echo off
setlocal

set "APP_DIR=%~dp0"
set "APP_FILE=%APP_DIR%index.html"

if not exist "%APP_FILE%" (
  echo POPGEN could not start.
  echo.
  echo The file index.html was not found in:
  echo %APP_DIR%
  echo.
  echo Please copy the entire POPGEN folder, keeping index.html, styles.css, and app.js together.
  echo.
  pause
  exit /b 1
)

echo Starting Metapopulation Differentiation Lab...
echo Folder: %APP_DIR%
start "" "%APP_FILE%"
exit /b 0
