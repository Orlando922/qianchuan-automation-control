$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Workspace = Split-Path -Parent $Root
$Frontend = Join-Path $Workspace "qianchuan-control-frontend"
$Python = if (Test-Path "D:\ComfyUI\python\python.exe") { "D:\ComfyUI\python\python.exe" } else { "python" }
$ApiHost = if ($env:QIANCHUAN_LOCAL_BIND_HOST) { $env:QIANCHUAN_LOCAL_BIND_HOST } else { "0.0.0.0" }
$ApiPort = if ($env:QIANCHUAN_LOCAL_BIND_PORT) { [int]$env:QIANCHUAN_LOCAL_BIND_PORT } else { 5290 }
$FrontendHost = if ($env:QIANCHUAN_FRONTEND_BIND_HOST) { $env:QIANCHUAN_FRONTEND_BIND_HOST } else { "0.0.0.0" }
$FrontendPort = if ($env:QIANCHUAN_FRONTEND_PORT) { [int]$env:QIANCHUAN_FRONTEND_PORT } else { 5288 }
$SecretsPath = Join-Path $Root "local.secrets.ps1"
$StatusLog = Join-Path $Root "qianchuan-system-start.log"

if (Test-Path $SecretsPath) {
  . $SecretsPath
}

$env:QIANCHUAN_LOCAL_BIND_HOST = $ApiHost
$env:QIANCHUAN_LOCAL_BIND_PORT = [string]$ApiPort

function Write-Status {
  param([string]$Message)
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $StatusLog -Encoding UTF8 -Value $line
  Write-Output $line
}

function Test-Listening {
  param([int]$Port)
  $allowed = @("0.0.0.0", "::")
  if ($Port -eq $FrontendPort) {
    $allowed += $FrontendHost
  } else {
    $allowed += $ApiHost
  }
  $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -in $allowed }
  return [bool]$connection
}

function Wait-Http {
  param([string]$Uri, [int]$Seconds = 20)
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 700
    }
  }
  return $false
}

if (-not (Test-Listening -Port $ApiPort)) {
  Write-Status "starting qianchuan local api on $ApiHost`:$ApiPort"
  Start-Process -FilePath $Python `
    -ArgumentList @((Join-Path $Root "local_control.py")) `
    -WorkingDirectory $Root `
    -RedirectStandardOutput (Join-Path $Root "qianchuan-local-control.out.log") `
    -RedirectStandardError (Join-Path $Root "qianchuan-local-control.err.log") `
    -WindowStyle Hidden
} else {
  Write-Status "qianchuan local api already listening on port $ApiPort"
}

if (-not (Wait-Http -Uri "http://127.0.0.1:$ApiPort/healthz" -Seconds 20)) {
  throw "qianchuan local api health check failed"
}
Write-Status "qianchuan local api health ok"

if (-not (Test-Listening -Port $FrontendPort)) {
  Write-Status "starting qianchuan frontend on $FrontendHost`:$FrontendPort"
  Start-Process -FilePath $Python `
    -ArgumentList @("-m", "http.server", [string]$FrontendPort, "--bind", $FrontendHost) `
    -WorkingDirectory $Frontend `
    -RedirectStandardOutput (Join-Path $Root "frontend-http.out.log") `
    -RedirectStandardError (Join-Path $Root "frontend-http.err.log") `
    -WindowStyle Hidden
} else {
  Write-Status "qianchuan frontend already listening on port $FrontendPort"
}

if (-not (Wait-Http -Uri "http://127.0.0.1:$FrontendPort/" -Seconds 20)) {
  throw "qianchuan frontend health check failed"
}
Write-Status "qianchuan frontend health ok"
Write-Status "qianchuan system ready"
