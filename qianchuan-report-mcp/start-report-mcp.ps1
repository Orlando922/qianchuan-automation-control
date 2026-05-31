$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:QIANCHUAN_REPORT_MCP_PYTHON) { $env:QIANCHUAN_REPORT_MCP_PYTHON } else { "python" }
$DbPath = if ($env:QIANCHUAN_REPORT_DB_PATH) {
  $env:QIANCHUAN_REPORT_DB_PATH
} else {
  Join-Path (Split-Path -Parent $Root) "qianchuan-local-control\qianchuan-local.sqlite3"
}

& $Python (Join-Path $Root "server.py") --db $DbPath
