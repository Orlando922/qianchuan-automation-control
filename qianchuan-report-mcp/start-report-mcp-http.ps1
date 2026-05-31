$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:QIANCHUAN_REPORT_MCP_PYTHON) { $env:QIANCHUAN_REPORT_MCP_PYTHON } else { "python" }
$HostName = if ($env:QIANCHUAN_REPORT_MCP_HOST) { $env:QIANCHUAN_REPORT_MCP_HOST } else { "127.0.0.1" }
$Port = if ($env:QIANCHUAN_REPORT_MCP_PORT) { [int]$env:QIANCHUAN_REPORT_MCP_PORT } else { 5291 }
$Prefix = if ($env:QIANCHUAN_REPORT_MCP_PREFIX) { $env:QIANCHUAN_REPORT_MCP_PREFIX } else { "/api/qianchuan-report-mcp" }
$DbPath = if ($env:QIANCHUAN_REPORT_DB_PATH) {
  $env:QIANCHUAN_REPORT_DB_PATH
} else {
  Join-Path (Split-Path -Parent $Root) "qianchuan-local-control\qianchuan-local.sqlite3"
}
$TokenPath = Join-Path $Root ".report-mcp-token"
$OutLogPath = Join-Path $Root "qianchuan-report-mcp-http.out.log"
$ErrLogPath = Join-Path $Root "qianchuan-report-mcp-http.err.log"

if (-not (Test-Path $TokenPath)) {
  throw "Missing report MCP token file: $TokenPath"
}

$existing = Get-NetTCPConnection -LocalAddress $HostName -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
  Write-Output "qianchuan-report-mcp http already listening on $HostName`:$Port"
  exit 0
}

$envBlock = @{
  PYTHONUTF8 = "1"
  PYTHONIOENCODING = "utf-8"
  QIANCHUAN_REPORT_MCP_TOKEN = (Get-Content -Path $TokenPath -Raw).Trim()
  QIANCHUAN_REPORT_MCP_PREFIX = $Prefix
  QIANCHUAN_REPORT_DB_PATH = $DbPath
}

$old = @{}
foreach ($key in $envBlock.Keys) {
  $old[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
  [Environment]::SetEnvironmentVariable($key, $envBlock[$key], "Process")
}
try {
  Start-Process -FilePath $Python `
    -ArgumentList @((Join-Path $Root "http_sse_server.py"), "--host", $HostName, "--port", "$Port", "--db", $DbPath, "--prefix", $Prefix) `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $OutLogPath `
    -RedirectStandardError $ErrLogPath `
    -WindowStyle Hidden
} finally {
  foreach ($key in $old.Keys) {
    [Environment]::SetEnvironmentVariable($key, $old[$key], "Process")
  }
}

Start-Sleep -Seconds 2
$health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port$Prefix/healthz" -TimeoutSec 5
Write-Output ($health | ConvertTo-Json -Compress)
