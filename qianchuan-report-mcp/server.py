#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


SERVER_NAME = "qianchuan-report-mcp"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "qianchuan-local-control" / "qianchuan-local.sqlite3"
PLAN_PREFIX_OWNERS = {
    "SC": "Operator A",
    "CY": "Operator B",
    "ST": "Operator C",
}

REPORT_RUN_COLUMNS = {
    "id",
    "created_at",
    "scope",
    "start_time",
    "end_time",
    "marketing_goal",
    "shop_count",
    "plan_count",
    "spend",
    "gmv",
    "roi",
}
PLAN_SORT_COLUMNS = {
    "plan_id",
    "plan_name",
    "shop_id",
    "spend",
    "gmv",
    "roi",
    "orders",
    "budget",
    "opt_status",
    "status",
    "owner_prefix",
}


class McpError(Exception):
    def __init__(self, message, code=-32000):
        super().__init__(message)
        self.code = code


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def json_dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_json(value, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def bounded_int(value, default, min_value=0, max_value=500):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(number, max_value))


def as_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise McpError(f"invalid number: {value}") from exc


def row_to_dict(row, include_payload=False):
    result = dict(row)
    payload = result.pop("payload_json", None)
    if include_payload:
        result["payload"] = parse_json(payload, {})
    return result


def normalize_plan_prefix(value):
    prefix = str(value or "").strip().upper()[:2]
    if len(prefix) == 2 and prefix.isalpha() and prefix.isascii():
        return prefix
    return ""


def plan_prefix_for_name(name):
    raw = str(name or "").strip().upper()
    letters = []
    for ch in raw:
        if "A" <= ch <= "Z":
            letters.append(ch)
            if len(letters) == 2:
                return normalize_plan_prefix("".join(letters))
            continue
        if letters:
            break
        if ch in {" ", "_", "-", "【", "】", "[", "]", "(", ")", "（", "）"}:
            continue
        break
    return ""


def plan_row_to_dict(row, include_payload=False):
    result = dict(row)
    payload = parse_json(result.pop("payload_json", None), {})
    prefix = normalize_plan_prefix(payload.get("ownerPrefix")) or plan_prefix_for_name(result.get("plan_name") or payload.get("name"))
    result["owner_prefix"] = prefix
    result["owner_name"] = payload.get("ownerName") or PLAN_PREFIX_OWNERS.get(prefix, "未分配")
    if include_payload:
        result["payload"] = payload
    return result


def owner_summaries_from_plan_rows(rows):
    groups = {}
    for row in rows:
        item = plan_row_to_dict(row)
        prefix = item.get("owner_prefix") or "-"
        group = groups.setdefault(
            prefix,
            {
                "owner_prefix": item.get("owner_prefix"),
                "owner_name": item.get("owner_name"),
                "plan_count": 0,
                "spend": 0,
                "gmv": 0,
                "orders": 0,
                "roi": 0,
            },
        )
        group["plan_count"] += 1
        group["spend"] += float(item.get("spend") or 0)
        group["gmv"] += float(item.get("gmv") or 0)
        group["orders"] += int(item.get("orders") or 0)
    for group in groups.values():
        group["spend"] = round(group["spend"], 2)
        group["gmv"] = round(group["gmv"], 2)
        group["roi"] = round(group["gmv"] / group["spend"], 4) if group["spend"] > 0 else 0
    return sorted(groups.values(), key=lambda item: (-float(item.get("spend") or 0), item.get("owner_prefix") or ""))


def day_start(value):
    return f"{str(value)[:10]} 00:00:00" if value else None


def day_end(value):
    return f"{str(value)[:10]} 23:59:59" if value else None


class ReportRepository:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path or os.environ.get("QIANCHUAN_REPORT_DB_PATH") or DEFAULT_DB_PATH).resolve()

    def connect(self):
        if not self.db_path.exists():
            raise McpError(f"report database not found: {self.db_path}")
        uri = self.db_path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma query_only = on")
        return conn

    def _table_count(self, conn, table):
        try:
            return int(conn.execute(f"select count(*) from {table}").fetchone()[0])
        except sqlite3.Error:
            return 0

    def status(self):
        with self.connect() as conn:
            latest = conn.execute(
                """
                select id, created_at, scope, start_time, end_time, marketing_goal,
                       shop_count, plan_count, spend, gmv, roi
                from report_runs
                order by id desc
                limit 1
                """
            ).fetchone()
            return {
                "server": SERVER_NAME,
                "mode": "read-only",
                "dbPath": str(self.db_path),
                "tables": {
                    "report_runs": self._table_count(conn, "report_runs"),
                    "report_shop_rows": self._table_count(conn, "report_shop_rows"),
                    "report_plan_rows": self._table_count(conn, "report_plan_rows"),
                },
                "latestRun": row_to_dict(latest) if latest else None,
                "allowedTables": ["report_runs", "report_shop_rows", "report_plan_rows"],
                "writeAccess": False,
            }

    def _run_filters(self, args):
        where = []
        params = []
        if args.get("report_id"):
            where.append("id = ?")
            params.append(int(args["report_id"]))
        if args.get("date_from"):
            where.append("start_time >= ?")
            params.append(day_start(args["date_from"]))
        if args.get("date_to"):
            where.append("end_time <= ?")
            params.append(day_end(args["date_to"]))
        if args.get("scope"):
            where.append("scope = ?")
            params.append(str(args["scope"]))
        if args.get("marketing_goal"):
            where.append("marketing_goal = ?")
            params.append(str(args["marketing_goal"]))
        clause = f" where {' and '.join(where)}" if where else ""
        return clause, params

    def list_runs(self, args):
        limit = bounded_int(args.get("limit"), 20, 1, 200)
        offset = bounded_int(args.get("offset"), 0, 0, 100000)
        clause, params = self._run_filters(args)
        with self.connect() as conn:
            total = conn.execute(f"select count(*) from report_runs{clause}", params).fetchone()[0]
            rows = conn.execute(
                f"""
                select id, created_at, scope, start_time, end_time, marketing_goal,
                       shop_count, plan_count, spend, gmv, roi
                from report_runs
                {clause}
                order by id desc
                limit ? offset ?
                """,
                [*params, limit, offset],
            ).fetchall()
            return {"total": total, "limit": limit, "offset": offset, "items": [row_to_dict(row) for row in rows]}

    def resolve_report_id(self, args):
        if args.get("report_id"):
            return int(args["report_id"])
        clause, params = self._run_filters(args)
        with self.connect() as conn:
            row = conn.execute(f"select id from report_runs{clause} order by id desc limit 1", params).fetchone()
            if not row:
                raise McpError("no report run matched the filters")
            return int(row["id"])

    def summary(self, args):
        report_id = self.resolve_report_id(args)
        with self.connect() as conn:
            run = conn.execute(
                """
                select id, created_at, scope, start_time, end_time, marketing_goal,
                       shop_count, plan_count, spend, gmv, roi
                from report_runs
                where id = ?
                """,
                (report_id,),
            ).fetchone()
            if not run:
                raise McpError(f"report run not found: {report_id}")
            shops = conn.execute(
                """
                select shop_id, advertiser_id, shop_name, spend, gmv, roi, orders, plan_count
                from report_shop_rows
                where report_id = ?
                order by spend desc, shop_id
                """,
                (report_id,),
            ).fetchall()
            plan_rows = conn.execute(
                """
                select id, report_id, shop_id, advertiser_id, plan_id, plan_name,
                       opt_status, status, spend, gmv, roi, orders, budget, payload_json
                from report_plan_rows
                where report_id = ?
                """,
                (report_id,),
            ).fetchall()
            return {
                "run": row_to_dict(run),
                "shops": [row_to_dict(row) for row in shops],
                "owners": owner_summaries_from_plan_rows(plan_rows),
            }

    def shops(self, args):
        report_id = self.resolve_report_id(args)
        where = ["report_id = ?"]
        params = [report_id]
        if args.get("shop_id"):
            where.append("shop_id = ?")
            params.append(int(args["shop_id"]))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select id, report_id, shop_id, advertiser_id, shop_name,
                       spend, gmv, roi, orders, plan_count, payload_json
                from report_shop_rows
                where {' and '.join(where)}
                order by spend desc, shop_id
                """,
                params,
            ).fetchall()
        return {"reportId": report_id, "items": [row_to_dict(row, as_bool(args.get("include_payload"))) for row in rows]}

    def plans(self, args):
        report_id = self.resolve_report_id(args)
        limit = bounded_int(args.get("limit"), 100, 1, 1000)
        offset = bounded_int(args.get("offset"), 0, 0, 100000)
        sort_by = str(args.get("sort_by") or "spend")
        if sort_by not in PLAN_SORT_COLUMNS:
            raise McpError(f"unsupported sort_by: {sort_by}")
        sort_dir = str(args.get("sort_dir") or "desc").lower()
        sort_dir = "asc" if sort_dir == "asc" else "desc"
        where = ["report_id = ?"]
        params = [report_id]
        if args.get("shop_id"):
            where.append("shop_id = ?")
            params.append(int(args["shop_id"]))
        if args.get("plan_id"):
            where.append("plan_id = ?")
            params.append(int(args["plan_id"]))
        if args.get("keyword"):
            where.append("(plan_name like ? or cast(plan_id as text) like ?)")
            keyword = f"%{args['keyword']}%"
            params.extend([keyword, keyword])
        if args.get("status"):
            where.append("status = ?")
            params.append(str(args["status"]))
        if args.get("opt_status"):
            where.append("opt_status = ?")
            params.append(str(args["opt_status"]))
        min_roi = as_float(args.get("min_roi"))
        if min_roi is not None:
            where.append("roi >= ?")
            params.append(min_roi)
        max_roi = as_float(args.get("max_roi"))
        if max_roi is not None:
            where.append("roi <= ?")
            params.append(max_roi)
        min_spend = as_float(args.get("min_spend"))
        if min_spend is not None:
            where.append("spend >= ?")
            params.append(min_spend)
        max_spend = as_float(args.get("max_spend"))
        if max_spend is not None:
            where.append("spend <= ?")
            params.append(max_spend)
        clause = " and ".join(where)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select id, report_id, shop_id, advertiser_id, plan_id, plan_name,
                       opt_status, status, spend, gmv, roi, orders, budget, payload_json
                from report_plan_rows
                where {clause}
                """,
                params,
            ).fetchall()
        items = [plan_row_to_dict(row, as_bool(args.get("include_payload"))) for row in rows]
        if args.get("owner_prefix"):
            owner_prefix = normalize_plan_prefix(args.get("owner_prefix"))
            items = [item for item in items if normalize_plan_prefix(item.get("owner_prefix")) == owner_prefix]
        reverse = sort_dir == "desc"

        def sort_value(item):
            value = item.get(sort_by)
            if sort_by in {"plan_name", "opt_status", "status", "owner_prefix"}:
                return str(value or "")
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0

        items.sort(key=lambda item: int(item.get("id") or 0))
        items.sort(key=sort_value, reverse=reverse)
        total = len(items)
        page_items = items[offset : offset + limit]
        return {
            "reportId": report_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "sortBy": sort_by,
            "sortDir": sort_dir,
            "items": page_items,
        }

    def payload(self, args):
        report_id = self.resolve_report_id(args)
        with self.connect() as conn:
            row = conn.execute("select payload_json from report_runs where id = ?", (report_id,)).fetchone()
        if not row:
            raise McpError(f"report run not found: {report_id}")
        return {"reportId": report_id, "payload": parse_json(row["payload_json"], {})}


def tool_definitions():
    return [
        {
            "name": "qianchuan_report_status",
            "description": "只读查看本地千川报表库状态，只返回 report_* 表计数和最新报表。",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "qianchuan_report_runs",
            "description": "只读列出本地已保存的报表批次，可按日期、权限范围和营销目标筛选。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer"},
                    "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                    "scope": {"type": "string"},
                    "marketing_goal": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    "offset": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "qianchuan_report_summary",
            "description": "只读读取一个报表批次的总览、来源账户汇总和投手/计划前缀汇总；不返回计划明细。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "scope": {"type": "string"},
                    "marketing_goal": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "qianchuan_report_shops",
            "description": "只读读取报表中的来源账户层级数据，可选择返回来源账户原始载荷。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "shop_id": {"type": "integer"},
                    "include_payload": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "qianchuan_report_plans",
            "description": "只读读取报表中的计划层级数据，支持按投手前缀筛选、排序、分页和按需返回计划原始载荷。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "shop_id": {"type": "integer"},
                    "owner_prefix": {"type": "string", "description": "计划名前缀/投手归属，例如 SC、CY、ST。"},
                    "plan_id": {"type": "integer"},
                    "keyword": {"type": "string"},
                    "status": {"type": "string"},
                    "opt_status": {"type": "string"},
                    "min_roi": {"type": "number"},
                    "max_roi": {"type": "number"},
                    "min_spend": {"type": "number"},
                    "max_spend": {"type": "number"},
                    "sort_by": {"type": "string", "enum": sorted(PLAN_SORT_COLUMNS)},
                    "sort_dir": {"type": "string", "enum": ["asc", "desc"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                    "offset": {"type": "integer", "minimum": 0},
                    "include_payload": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "qianchuan_report_payload",
            "description": "只读读取一个报表批次的完整原始报表载荷。数据可能较大。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    ]


def tool_result(value):
    return {"content": [{"type": "text", "text": json_dumps(value)}]}


def call_tool(name, args, repo):
    args = args or {}
    if name == "qianchuan_report_status":
        return repo.status()
    if name == "qianchuan_report_runs":
        return repo.list_runs(args)
    if name == "qianchuan_report_summary":
        return repo.summary(args)
    if name == "qianchuan_report_shops":
        return repo.shops(args)
    if name == "qianchuan_report_plans":
        return repo.plans(args)
    if name == "qianchuan_report_payload":
        return repo.payload(args)
    raise McpError(f"unknown tool: {name}", -32601)


def resources_list(repo):
    status = repo.status()
    resources = [
        {
            "uri": "qianchuan-report://status",
            "name": "千川本地报表库状态",
            "mimeType": "application/json",
            "description": "只读状态资源，包含 report_* 表计数和最新报表。",
        }
    ]
    latest = status.get("latestRun")
    if latest:
        resources.append(
            {
                "uri": f"qianchuan-report://runs/{latest['id']}",
                "name": f"最新千川报表 #{latest['id']}",
                "mimeType": "application/json",
                "description": "只读最新报表总览和店铺汇总。",
            }
        )
    return resources


def resources_read(uri, repo):
    if uri == "qianchuan-report://status":
        return repo.status()
    prefix = "qianchuan-report://runs/"
    if uri.startswith(prefix):
        return repo.summary({"report_id": int(uri[len(prefix):])})
    raise McpError(f"unknown resource: {uri}", -32602)


def success_response(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(request, repo):
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "initialize":
            return success_response(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return success_response(request_id, {})
        if method == "tools/list":
            return success_response(request_id, {"tools": tool_definitions()})
        if method == "tools/call":
            result = call_tool(params.get("name"), params.get("arguments") or {}, repo)
            return success_response(request_id, tool_result(result))
        if method == "resources/list":
            return success_response(request_id, {"resources": resources_list(repo)})
        if method == "resources/read":
            uri = params.get("uri") or ""
            return success_response(
                request_id,
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json_dumps(resources_read(uri, repo)),
                        }
                    ]
                },
            )
        raise McpError(f"unknown method: {method}", -32601)
    except McpError as exc:
        return error_response(request_id, exc.code, str(exc))
    except Exception as exc:
        return error_response(request_id, -32000, str(exc))


def serve_stdio(repo):
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = error_response(None, -32700, f"parse error: {exc}")
        else:
            response = handle_request(request, repo)
        if response is not None:
            sys.stdout.write(json_dumps(response) + "\n")
            sys.stdout.flush()


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Read-only MCP server for local Qianchuan reports.")
    parser.add_argument("--db", default=None, help="Path to qianchuan-local.sqlite3. Defaults to the local-control database.")
    parser.add_argument("--status", action="store_true", help="Print read-only report database status and exit.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    repo = ReportRepository(args.db)
    if args.status:
        print(json.dumps(repo.status(), ensure_ascii=False, indent=2))
        return 0
    serve_stdio(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
