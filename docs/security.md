# Security

## Public release guarantees

This repository is designed to be safe for public review. It excludes:

- SQLite databases and report payloads
- access tokens and refresh tokens
- API keys and app secrets
- webhook URLs
- local admin passwords
- SSH hosts, usernames, and key paths
- production shop, advertiser, and employee identifiers
- service logs and browser capture artifacts

## Local secrets

Use environment variables or ignored local files:

- `qianchuan-local-control/local.secrets.ps1`
- `qianchuan-local-control/admin.local.txt`
- `qianchuan-oauth-deploy/qianchuan-oauth.env`
- `qianchuan-control-frontend/config.local.js`

Example files are included with placeholder values.

## Agent access boundary

The report MCP server is intentionally read-only. It opens SQLite with `mode=ro`, sets query-only behavior, and exposes fixed report tools instead of arbitrary SQL. It does not include plan pause, plan enable, budget update, user management, rule mutation, token access, or webhook access.

## Before pushing

Run:

```powershell
python .\scripts\public_safety_scan.py .
git status --short
```

Review any finding before publishing. The scanner is conservative and may flag placeholder names or code paths. Production-looking identifiers, IP addresses, credentials, local paths, or raw report data should block a public push.

