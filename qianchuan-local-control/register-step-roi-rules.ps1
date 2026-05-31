$ErrorActionPreference = "Stop"

Write-Error @"
Windows Task Scheduler is disabled for Qianchuan step ROI rules.

The active scheduler is inside qianchuan-local-control\local_control.py.
When the 5290 backend is running, it executes SPEND_STEP_ROI_STOP every 10 minutes.
"@
