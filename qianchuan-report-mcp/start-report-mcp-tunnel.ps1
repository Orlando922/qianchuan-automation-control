$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ssh = "ssh.exe"
$KeyPath = "<SSH_KEY_PATH>"
$RemoteUser = "<ssh-user>"
$RemoteHost = "127.0.0.1:18080"
$RemotePort = 18091
$LocalHost = "127.0.0.1"
$LocalPort = 5291
$OutLogPath = Join-Path $Root "qianchuan-report-mcp-tunnel.out.log"
$ErrLogPath = Join-Path $Root "qianchuan-report-mcp-tunnel.err.log"

& (Join-Path $Root "start-report-mcp-http.ps1") | Out-Null

$pattern = "$RemotePort`:$LocalHost`:$LocalPort"
$existing = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like "ssh*" -and $_.CommandLine -like "*$pattern*" -and $_.CommandLine -like "*$RemoteHost*" }
if ($existing) {
  Write-Output "qianchuan-report-mcp tunnel already running"
  exit 0
}

$args = @(
  "-N",
  "-T",
  "-i", $KeyPath,
  "-o", "BatchMode=yes",
  "-o", "ExitOnForwardFailure=yes",
  "-o", "ServerAliveInterval=30",
  "-o", "ServerAliveCountMax=3",
  "-R", "127.0.0.1:$RemotePort`:$LocalHost`:$LocalPort",
  "$RemoteUser@$RemoteHost"
)

Start-Process -FilePath $Ssh `
  -ArgumentList $args `
  -WorkingDirectory $Root `
  -RedirectStandardOutput $OutLogPath `
  -RedirectStandardError $ErrLogPath `
  -WindowStyle Hidden

Start-Sleep -Seconds 2
$remoteCheck = & $Ssh -i $KeyPath -o BatchMode=yes "$RemoteUser@$RemoteHost" "ss -ltn sport = :$RemotePort | tail -n +2 | wc -l"
Write-Output "remote tunnel listeners on $RemotePort`: $($remoteCheck.Trim())"
