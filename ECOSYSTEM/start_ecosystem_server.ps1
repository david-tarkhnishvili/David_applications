$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8765
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $port)

function Get-ContentType($path) {
  switch ([System.IO.Path]::GetExtension($path).ToLowerInvariant()) {
    ".html" { "text/html; charset=utf-8"; break }
    ".js" { "application/javascript; charset=utf-8"; break }
    ".css" { "text/css; charset=utf-8"; break }
    ".csv" { "text/csv; charset=utf-8"; break }
    ".json" { "application/json; charset=utf-8"; break }
    ".svg" { "image/svg+xml"; break }
    ".png" { "image/png"; break }
    ".jpg" { "image/jpeg"; break }
    ".jpeg" { "image/jpeg"; break }
    default { "application/octet-stream"; break }
  }
}

try {
  $listener.Start()
  Write-Host "Ecosystem Guild Builder running at http://127.0.0.1:$port/"
  Write-Host "Close this window to stop the local server."

  while ($true) {
    $client = $listener.AcceptTcpClient()
    try {
      $stream = $client.GetStream()
      $reader = [System.IO.StreamReader]::new($stream)
      $requestLine = $reader.ReadLine()
      if ([string]::IsNullOrWhiteSpace($requestLine)) {
        $client.Close()
        continue
      }

      while ($reader.Peek() -ge 0) {
        $line = $reader.ReadLine()
        if ([string]::IsNullOrEmpty($line)) { break }
      }

      $parts = $requestLine.Split(" ")
      $urlPath = if ($parts.Length -gt 1) { $parts[1] } else { "/" }
      $urlPath = [System.Uri]::UnescapeDataString($urlPath.Split("?")[0])
      if ($urlPath -eq "/") { $urlPath = "/index.html" }

      $relative = $urlPath.TrimStart("/") -replace "/", [System.IO.Path]::DirectorySeparatorChar
      $fullPath = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($root, $relative))
      $rootFull = [System.IO.Path]::GetFullPath($root)

      if (-not $fullPath.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        $body = [System.Text.Encoding]::UTF8.GetBytes("403 Forbidden")
        $header = "HTTP/1.1 403 Forbidden`r`nContent-Length: $($body.Length)`r`nConnection: close`r`n`r`n"
      } elseif (-not [System.IO.File]::Exists($fullPath)) {
        $body = [System.Text.Encoding]::UTF8.GetBytes("404 Not Found")
        $header = "HTTP/1.1 404 Not Found`r`nContent-Length: $($body.Length)`r`nConnection: close`r`n`r`n"
      } else {
        $body = [System.IO.File]::ReadAllBytes($fullPath)
        $type = Get-ContentType $fullPath
        $header = "HTTP/1.1 200 OK`r`nContent-Type: $type`r`nContent-Length: $($body.Length)`r`nCache-Control: no-store`r`nConnection: close`r`n`r`n"
      }

      $headerBytes = [System.Text.Encoding]::ASCII.GetBytes($header)
      $stream.Write($headerBytes, 0, $headerBytes.Length)
      $stream.Write($body, 0, $body.Length)
    } finally {
      $client.Close()
    }
  }
} finally {
  $listener.Stop()
}
