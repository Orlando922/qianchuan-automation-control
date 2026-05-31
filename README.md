# Qianchuan Automation Control

Local-first automation tools for OceanEngine Qianchuan ad operations.

This repository packages a production-tested control stack for operators who need safer ways to run Qianchuan campaigns, audit API effects, and automate routine budget and ROI rules. It contains a browser console, a local control proxy, an OAuth/API broker, and a read-only MCP server for report analysis.

## Why this exists

Qianchuan campaigns can involve hundreds of live promotion plans, multiple operators, and repeated daily decisions around ROI, budget pacing, pausing, and recovery. Manual work is slow and risky, while direct API automation needs careful access control and a clear audit trail.

This project focuses on:

- local-first storage for snapshots, reports, action logs, and API journals
- permission-scoped views for admins and operator accounts
- rule-driven actions such as low-ROI pause, high-ROI budget increase, and daily budget reset
- an OAuth broker for OceanEngine API authorization and token refresh
- a read-only MCP server that lets coding agents analyze stored reports without write access
- explicit separation between read-only analysis and live campaign actions

## Repository layout

```text
qianchuan-control-frontend/   Static operations console
qianchuan-local-control/      Local proxy, SQLite cache, rule scheduler, audit log
qianchuan-oauth-deploy/       OAuth callback and OceanEngine API broker
qianchuan-report-mcp/         Read-only MCP server for local report analysis
docs/                         Architecture, security notes, application draft
scripts/                      Local validation helpers
```

## Safety status

The public repository is a sanitized release. It does not include production databases, report exports, service logs, API keys, access tokens, refresh tokens, webhooks, local admin credentials, SSH keys, internal IP addresses, shop identifiers, advertiser identifiers, or employee names.

Run the safety scanner before publishing changes:

```powershell
python .\scripts\public_safety_scan.py .
```

## Quick start

The code intentionally uses the Python standard library and plain browser assets. No package manager install is required for the core checks.

```powershell
python -m py_compile .\qianchuan-local-control\local_control.py
python -m py_compile .\qianchuan-oauth-deploy\app.py
python -m py_compile .\qianchuan-report-mcp\server.py
node --check .\qianchuan-control-frontend\app.js
node .\qianchuan-control-frontend\test_rule_form_logic.cjs
```

For local development, copy the example files and fill them with your own values:

```powershell
Copy-Item .\qianchuan-local-control\local.secrets.example.ps1 .\qianchuan-local-control\local.secrets.ps1
Copy-Item .\qianchuan-local-control\admin.local.example.txt .\qianchuan-local-control\admin.local.txt
Copy-Item .\qianchuan-oauth-deploy\qianchuan-oauth.env.example .\qianchuan-oauth-deploy\qianchuan-oauth.env
```

## Security model

See [docs/security.md](docs/security.md). The short version:

- live campaign writes require authenticated control paths
- the MCP server is read-only and opens SQLite in read-only mode
- local secrets stay in ignored files or environment variables
- all public examples use placeholders
- operational logs should mask password, token, secret, webhook, and authorization fields

## OpenAI Codex use case

This codebase is a strong fit for Codex support because it combines security-sensitive automation, browser UI logic, Python HTTP services, local data stores, and regression tests. API credits would be used for automated test generation, security review, refactoring assistance, documentation upkeep, and agent-assisted report analysis against sanitized fixtures.

See [docs/codex-for-oss-application.md](docs/codex-for-oss-application.md) for the application draft.

