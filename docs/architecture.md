# Architecture

## Components

### Static operations console

`qianchuan-control-frontend` is a static browser UI. It reads the current API base from `config.local.js` or from the current host, then calls the local control proxy. The UI covers login, plan tables, rules, operator assignment, reports, and action logs.

### Local control proxy

`qianchuan-local-control` is the local gateway. It stores plan snapshots, report snapshots, response caches, API journals, operation logs, local settings, and scheduler state in SQLite. It can mirror remote data into the local store, serve cached startup snapshots, and run scheduled ROI or budget rules.

### OAuth and API broker

`qianchuan-oauth-deploy` handles OceanEngine OAuth callbacks, token exchange, token refresh, user sessions, and proxied Qianchuan API calls. It keeps cloud-facing credentials away from the browser and gives the local control layer a narrow API surface.

### Read-only report MCP

`qianchuan-report-mcp` exposes saved report data to coding agents through a read-only MCP server. It only reads report tables and does not expose arbitrary SQL or campaign-control operations.

## Data flow

1. The browser UI talks to the local control proxy.
2. The local proxy reads cached state from SQLite for fast startup.
3. Manual sync or scheduled sync asks the OAuth broker for scoped Qianchuan data.
4. The OAuth broker calls OceanEngine APIs and returns normalized payloads.
5. The local proxy writes snapshots and audit rows.
6. Rule actions are logged locally and mirrored with remote action results.
7. The report MCP reads saved report rows for offline analysis.

## Design principles

- Keep live write APIs behind authentication.
- Keep browser code free of admin tokens.
- Make repeated dashboard and report reads local-first.
- Preserve an audit row for every API call and operator action.
- Let agents inspect reports through a read-only boundary.
- Treat production credentials and raw business data as local-only artifacts.

