$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "python"
$BindHost = if ($env:QIANCHUAN_LOCAL_BIND_HOST) { $env:QIANCHUAN_LOCAL_BIND_HOST } else { "0.0.0.0" }
$Port = if ($env:QIANCHUAN_LOCAL_BIND_PORT) { $env:QIANCHUAN_LOCAL_BIND_PORT } else { "5290" }
$OutLogPath = Join-Path $Root "qianchuan-local-control.out.log"
$ErrLogPath = Join-Path $Root "qianchuan-local-control.err.log"
$SecretsPath = Join-Path $Root "local.secrets.ps1"

if (Test-Path $SecretsPath) {
  . $SecretsPath
}

$env:QIANCHUAN_LOCAL_BIND_HOST = $BindHost
$env:QIANCHUAN_LOCAL_BIND_PORT = [string]$Port

$allowed = @($BindHost)
if ($BindHost -eq "0.0.0.0") {
  $allowed = @("0.0.0.0", "::")
} elseif ($BindHost -in @("127.0.0.1", "localhost")) {
  $allowed = @("127.0.0.1", "::1")
}
$existing = Get-NetTCPConnection -LocalPort ([int]$Port) -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalAddress -in $allowed }
if ($existing) {
  Write-Output "qianchuan-local-control already listening on $BindHost`:$Port"
  exit 0
}

Start-Process -FilePath $Python `
  -ArgumentList @((Join-Path $Root "local_control.py")) `
  -WorkingDirectory $Root `
  -RedirectStandardOutput $OutLogPath `
  -RedirectStandardError $ErrLogPath `
  -WindowStyle Hidden

Start-Sleep -Seconds 2
$health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 5
Write-Output $health.Content.Trim()
