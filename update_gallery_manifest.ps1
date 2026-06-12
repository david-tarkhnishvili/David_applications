$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$autoRegister = Join-Path $root "auto_register_gallery.mjs"

if (-not (Test-Path $autoRegister)) {
  throw "Cannot find auto_register_gallery.mjs in $root"
}

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
  throw "Node.js is required for automatic taxonomy registration. Install Node.js, then rerun this script."
}

& $node.Source $autoRegister $root
