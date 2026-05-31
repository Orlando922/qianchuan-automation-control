param(
  [switch]$ValidateOnly,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Workspace = Split-Path -Parent $Root
$SecretsPath = Join-Path $Root "local.secrets.ps1"
$StartScript = Join-Path $Root "start-qianchuan-system.ps1"
$LogPath = Join-Path $Root "qianchuan-daily-budget-reset.log"
$ApiPort = if ($env:QIANCHUAN_LOCAL_BIND_PORT) { [int]$env:QIANCHUAN_LOCAL_BIND_PORT } else { 5290 }
$HealthUri = "http://127.0.0.1:$ApiPort/healthz"
$ResetUri = "http://127.0.0.1:$ApiPort/api/qianchuan/actions/reset-budgets"

if (Test-Path $SecretsPath) {
  . $SecretsPath
}

function Write-ResetLog {
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
  $legacy = Get-Variable -Name "QC_CONTROL_TOKEN" -ErrorAction SilentlyContinue
  if ($legacy -and $legacy.Value) {
    return [string]$legacy.Value
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
  Write-ResetLog "local api not healthy, starting qianchuan system"
  & $StartScript | ForEach-Object { Write-ResetLog $_ }
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
  Write-ResetLog "daily budget reset runner validated"
  return
}

$targets = @(
  @{ smartBidType = "SMART_BID_CUSTOM"; budget = 300 },
  @{ smartBidType = "SMART_BID_CONSERVATIVE"; budget = 30 }
)

$responses = @()
foreach ($target in $targets) {
  $body = @{
    budget = $target.budget
    marketing_goal = "VIDEO_PROM_GOODS"
    planSmartBidTypes = @($target.smartBidType)
    batchSize = 10
    batchSleepSeconds = 0.5
    source = "daily-midnight-budget-reset"
    dryRun = [bool]$DryRun
  } | ConvertTo-Json -Depth 4

  Write-ResetLog ("calling reset-budgets type={0} budget={1} dryRun={2}" -f $target.smartBidType, $target.budget, ([bool]$DryRun))
  $responses += Invoke-RestMethod `
    -Method Post `
    -Uri $ResetUri `
    -ContentType "application/json" `
    -Headers @{ "X-QC-Admin-Token" = $Token } `
    -Body $body `
    -TimeoutSec 180
}

$summary = @{
  ok = -not (@($responses) | Where-Object { -not $_.ok })
  dryRun = [bool]$DryRun
  budgetTargets = @{
    SMART_BID_CUSTOM = 300
    SMART_BID_CONSERVATIVE = 30
  }
  totalPlans = (@($responses) | Measure-Object -Property totalPlans -Sum).Sum
  updateCount = (@($responses) | Measure-Object -Property updateCount -Sum).Sum
  skippedCount = (@($responses) | Measure-Object -Property skippedCount -Sum).Sum
  missingCount = (@($responses) | Measure-Object -Property missingCount -Sum).Sum
  chunkCount = (@($responses) | Measure-Object -Property chunkCount -Sum).Sum
  runs = $responses
} | ConvertTo-Json -Compress -Depth 6

Write-ResetLog $summary
