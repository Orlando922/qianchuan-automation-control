$ErrorActionPreference = "Stop"

Write-Error @"
Windows Task Scheduler is disabled for the Qianchuan control system.

Qianchuan scheduled work now runs inside the local 5290 backend process:
- step ROI rules run every 10 minutes from local_control.py
- midnight budget reset runs inside local_control.py

Start the system with qianchuan-local-control\start-qianchuan-system.ps1 when needed.
"@
