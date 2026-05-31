param(
  [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Workspace = Split-Path -Parent $Root
$SecretsPath = Join-Path $Root "local.secrets.ps1"
$StartScript = Join-Path $Root "start-qianchuan-system.ps1"
$LogPath = Join-Path $Root "qianchuan-step-roi-rules.log"
$ApiPort = if ($env:QIANCHUAN_LOCAL_BIND_PORT) { [int]$env:QIANCHUAN_LOCAL_BIND_PORT } else { 5290 }
$HealthUri = "http://127.0.0.1:$ApiPort/healthz"
$RunRulesUri = "http://127.0.0.1:$ApiPort/api/qianchuan/actions/run-rules"

if (Test-Path $SecretsPath) {
  . $SecretsPath
}

function Write-StepLog {
  param([string]$Message)
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $LogPath -Encoding UTF8 -Value $line
  Write-Output $line
}

function Get-ControlToken {
  if ($env:QIANCHUAN_CONTROL_TOKEN) {
    return $env:QIANCHUAN_CONTROL_TOKEN
  }
  $variable = Get-Variable -Name "QIANCHUAN_CONTROL_TOKEN" -ErrorAction SilentlyContinue
  if ($variable -and $variable.Value) {
    return [string]$variable.Value
  }
  return ""
}

function Test-Health {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUri -TimeoutSec 5
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  } catch {
    return $false
  }
}

function Ensure-SystemReady {
  if (Test-Health) {
    return
  }
  Write-StepLog "local api not healthy, starting qianchuan system"
  & $StartScript | ForEach-Object { Write-StepLog $_ }
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline) {
    if (Test-Health) {
      return
    }
    Start-Sleep -Seconds 1
  }
  throw "local api health check failed: $HealthUri"
}

$Token = Get-ControlToken
if (-not $Token) {
  throw "QIANCHUAN_CONTROL_TOKEN is required in local.secrets.ps1 or environment"
}

Ensure-SystemReady

if ($ValidateOnly) {
  Write-StepLog "step roi rule runner validated"
  return
}

$body = @{
  marketing_goal = "VIDEO_PROM_GOODS"
  page = 1
  page_size = 500
  ruleActions = @("SPEND_STEP_ROI_STOP")
  source = "scheduled-step-roi-rules"
} | ConvertTo-Json -Depth 5

Write-StepLog "calling run-rules for SPEND_STEP_ROI_STOP"
$response = Invoke-RestMethod `
  -Method Post `
  -Uri $RunRulesUri `
  -ContentType "application/json" `
  -Headers @{ "X-QC-Admin-Token" = $Token } `
  -Body $body `
  -TimeoutSec 180

$summary = @{
  ok = $response.ok
  actionCount = @($response.actions).Count
  total = $response.plans.total
} | ConvertTo-Json -Compress -Depth 4

Write-StepLog $summary
