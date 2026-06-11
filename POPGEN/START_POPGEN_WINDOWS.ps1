$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appFile = Join-Path $appDir "index.html"

if (-not (Test-Path -LiteralPath $appFile)) {
    Write-Host "POPGEN could not start." -ForegroundColor Red
    Write-Host ""
    Write-Host "The file index.html was not found in:"
    Write-Host $appDir
    Write-Host ""
    Write-Host "Please copy the entire POPGEN folder, keeping index.html, styles.css, and app.js together."
    Read-Host "Press Enter to close"
    exit 1
}

Start-Process -FilePath $appFile
