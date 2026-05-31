$ErrorActionPreference = "Stop"

Write-Error @"
Windows Task Scheduler is disabled for the Qianchuan daily budget reset.

The active scheduler is inside qianchuan-local-control\local_control.py.
When the 5290 backend is running, it resets visible plan budgets during the Beijing midnight window.
"@
