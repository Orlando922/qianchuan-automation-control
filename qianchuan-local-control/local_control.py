#!/usr/bin/env python3
import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("QIANCHUAN_LOCAL_DB_PATH", str(ROOT / "qianchuan-local.sqlite3")))
CLOUD_API_BASE = os.environ.get("QIANCHUAN_CLOUD_API_BASE", "http://127.0.0.1:18080").rstrip("/")
BIND_HOST = os.environ.get("QIANCHUAN_LOCAL_BIND_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("QIANCHUAN_LOCAL_BIND_PORT", "5290"))
LOCAL_DB_TIMEOUT_SECONDS = float(os.environ.get("QIANCHUAN_LOCAL_DB_TIMEOUT_SECONDS", "30"))
AUTO_SYNC_INTERVAL_SECONDS = int(os.environ.get("QIANCHUAN_AUTO_SYNC_INTERVAL_SECONDS", "300"))
MIRROR_PLAN_PAGE_SIZE = int(os.environ.get("QIANCHUAN_MIRROR_PLAN_PAGE_SIZE", "500"))
SYSTEM_SCHEDULER_ENABLED = os.environ.get("QIANCHUAN_SYSTEM_SCHEDULER_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
SYSTEM_SCHEDULER_START_DELAY_SECONDS = int(os.environ.get("QIANCHUAN_SYSTEM_SCHEDULER_START_DELAY_SECONDS", "20"))
SYSTEM_SCHEDULER_TICK_SECONDS = int(os.environ.get("QIANCHUAN_SYSTEM_SCHEDULER_TICK_SECONDS", "60"))
SYSTEM_STEP_ROI_INTERVAL_SECONDS = int(os.environ.get("QIANCHUAN_SYSTEM_STEP_ROI_INTERVAL_SECONDS", "600"))
SYSTEM_BUDGET_RESET_HOUR = int(os.environ.get("QIANCHUAN_SYSTEM_BUDGET_RESET_HOUR", "0"))
SYSTEM_BUDGET_RESET_MINUTE = int(os.environ.get("QIANCHUAN_SYSTEM_BUDGET_RESET_MINUTE", "0"))
SYSTEM_BUDGET_RESET_WINDOW_MINUTES = int(os.environ.get("QIANCHUAN_SYSTEM_BUDGET_RESET_WINDOW_MINUTES", "10"))
SYSTEM_BUDGET_RESET_CONTROL_BUDGET = float(os.environ.get("QIANCHUAN_SYSTEM_BUDGET_RESET_CONTROL_BUDGET", "300"))
SYSTEM_BUDGET_RESET_VOLUME_BUDGET = float(os.environ.get("QIANCHUAN_SYSTEM_BUDGET_RESET_VOLUME_BUDGET", "30"))
SYSTEM_BUDGET_RESET_BATCH_SIZE = int(os.environ.get("QIANCHUAN_SYSTEM_BUDGET_RESET_BATCH_SIZE", "10"))
SYSTEM_BUDGET_RESET_BATCH_SLEEP_SECONDS = float(os.environ.get("QIANCHUAN_SYSTEM_BUDGET_RESET_BATCH_SLEEP_SECONDS", "0.5"))
SYSTEM_BUDGET_RESET_LAST_DATE_KEY = "system_scheduler.budget_reset.last_date"
CURRENT_PLAN_SNAPSHOT_CAPTURED_AT_KEY = "plan_snapshots.current_captured_at"
BEIJING_TZ = dt.timezone(dt.timedelta(hours=8))

SECRET_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "app_secret",
    "authorization",
    "x-qc-admin-token",
    "webhook",
    "webhook_url",
    "webhookurl",
    "webhookUrl".lower(),
    "key",
}

WECOM_WEBHOOK_HOST = "qyapi.weixin.qq.com"
WECOM_WEBHOOK_PATH = "/cgi-bin/webhook/send"

ACTION_LABELS = {
    "/api/qianchuan/actions/pause": "暂停计划",
    "/api/qianchuan/actions/disable": "暂停计划",
    "/api/qianchuan/actions/enable": "启动计划",
    "/api/qianchuan/actions/budget": "调整预算",
    "/api/qianchuan/actions/reset-budgets": "每日预算归位",
    "/api/qianchuan/actions/run-rules": "执行规则",
}

RULE_ACTION_LABELS = {
    "DISABLE": "暂停计划",
    "SPEND_STEP_ROI_STOP": "分段ROI暂停计划",
    "NEAR_BUDGET_ROI_ADD_BUDGET": "预算将尽高ROI加预算",
    "HOURLY_SPEND_INCREASE_ROI_GOAL": "小时消耗高调ROI目标",
    "ADD_BUDGET": "增加预算",
    "NOTIFY": "只通知",
}

AUTO_RULE_ACTIONS = [
    "DISABLE",
    "SPEND_STEP_ROI_STOP",
    "NEAR_BUDGET_ROI_ADD_BUDGET",
    "HOURLY_SPEND_INCREASE_ROI_GOAL",
    "ADD_BUDGET",
    "NOTIFY",
]

PLAN_PREFIX_OWNERS = {
    "SC": "Operator A",
    "CY": "Operator B",
    "ST": "Operator C",
}
PLAN_SMART_BID_TYPES = ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"]
CONTROL_PLAN_SMART_BID_TYPES = ["SMART_BID_CUSTOM"]
ASSIGNMENT_CACHE = {"expires_at": 0, "users": [], "shops": [], "planPrefixOptions": []}
REFRESH_INFLIGHT = set()
REFRESH_LOCK = threading.Lock()


METRIC_COLUMNS = {
    "pay_gmv": "real",
    "pay_roi": "real",
    "settle_gmv": "real",
    "settle_roi": "real",
    "real_settle_gmv": "real",
    "refund_gmv": "real",
    "refund_orders": "integer",
    "roi_metric_json": "text",
}
PLAN_TYPE_COLUMNS = {
    "smart_bid_type": "text",
}
REPORT_TYPE_COLUMNS = {
    "plan_smart_bid_types": "text",
}


def ensure_columns(conn, table, columns):
    existing = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    for name, column_type in columns.items():
        if name not in existing:
            conn.execute(f"alter table {table} add column {name} {column_type}")


def flatten_values(values):
    if values is None:
        return []
    if not isinstance(values, list):
        values = [values]
    flattened = []
    for value in values:
        if isinstance(value, (list, tuple)):
            flattened.extend(flatten_values(list(value)))
            continue
        text = str(value or "").strip()
        if not text:
            continue
        for part in text.replace("，", ",").split(","):
            part = part.strip()
            if part:
                flattened.append(part)
    return flattened


def normalize_plan_smart_bid_type(value):
    text = str(value or "").strip().upper()
    if text in PLAN_SMART_BID_TYPES:
        return text
    if text in {"CUSTOM", "COST", "COST_CONTROL", "控成本"}:
        return "SMART_BID_CUSTOM"
    if text in {"CONSERVATIVE", "VOLUME", "VOLUME_SCALE", "放量"}:
        return "SMART_BID_CONSERVATIVE"
    return ""


def normalize_plan_smart_bid_types(values, default=None):
    raw_values = flatten_values(values)
    if not raw_values:
        return list(default or [])
    normalized = []
    seen = set()
    for value in raw_values:
        if str(value).strip().lower() in {"all", "*"}:
            source = PLAN_SMART_BID_TYPES
        else:
            item = normalize_plan_smart_bid_type(value)
            source = [item] if item else []
        for item in source:
            if item and item not in seen:
                normalized.append(item)
                seen.add(item)
    return normalized or list(default or [])


def query_plan_smart_bid_types(query, default=None):
    values = []
    if isinstance(query, dict):
        for name in ("planSmartBidTypes", "plan_smart_bid_types", "smartBidTypes", "smart_bid_types", "smartBidType", "smart_bid_type"):
            if name in query:
                values.extend(flatten_values(query.get(name)))
    return normalize_plan_smart_bid_types(values, default=default)


def plan_smart_bid_type(plan):
    if not isinstance(plan, dict):
        return CONTROL_PLAN_SMART_BID_TYPES[0]
    return normalize_plan_smart_bid_type(plan.get("smartBidType") or plan.get("smart_bid_type")) or CONTROL_PLAN_SMART_BID_TYPES[0]


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def is_loopback_address(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value in {"localhost"}


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=LOCAL_DB_TIMEOUT_SECONDS)
    conn.execute(f"pragma busy_timeout = {int(LOCAL_DB_TIMEOUT_SECONDS * 1000)}")
    return conn


def ensure_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as conn:
        conn.execute(
            """
            create table if not exists api_journal (
                id integer primary key autoincrement,
                created_at text not null,
                method text not null,
                path text not null,
                status_code integer not null,
                ok integer not null,
                operator text,
                request_json text,
                response_json text,
                error_text text
            )
            """
        )
        conn.execute(
            """
            create table if not exists operation_logs (
                id integer primary key autoincrement,
                created_at text not null,
                operator text,
                operation text not null,
                target_type text,
                target_id text,
                path text not null,
                ok integer not null,
                request_json text,
                response_json text
            )
            """
        )
        conn.execute(
            """
            create table if not exists plan_snapshots (
                id integer primary key autoincrement,
                captured_at text not null,
                shop_id integer,
                advertiser_id integer,
                plan_id integer,
                plan_name text,
                opt_status text,
                status text,
                spend real,
                gmv real,
                roi real,
                budget real,
                payload_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists shop_snapshots (
                id integer primary key autoincrement,
                captured_at text not null,
                shop_id integer,
                advertiser_id integer,
                shop_name text,
                payload_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists dashboard_snapshots (
                id integer primary key autoincrement,
                captured_at text not null,
                scope text,
                shop_count integer,
                spend real,
                gmv real,
                roi real,
                payload_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists remote_action_logs (
                id integer primary key autoincrement,
                captured_at text not null,
                remote_created_at text,
                action text,
                dry_run integer,
                request_json text,
                response_json text,
                unique(remote_created_at, action, request_json)
            )
            """
        )
        conn.execute(
            """
            create table if not exists report_runs (
                id integer primary key autoincrement,
                created_at text not null,
                scope text,
                start_time text not null,
                end_time text not null,
                marketing_goal text not null,
                shop_count integer,
                plan_count integer,
                spend real,
                gmv real,
                roi real,
                payload_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists report_shop_rows (
                id integer primary key autoincrement,
                report_id integer not null,
                shop_id integer,
                advertiser_id integer,
                shop_name text,
                spend real,
                gmv real,
                roi real,
                orders integer,
                plan_count integer,
                payload_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists report_plan_rows (
                id integer primary key autoincrement,
                report_id integer not null,
                shop_id integer,
                advertiser_id integer,
                plan_id integer,
                plan_name text,
                opt_status text,
                status text,
                spend real,
                gmv real,
                roi real,
                orders integer,
                budget real,
                payload_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists local_settings (
                key text primary key,
                value text not null,
                updated_at text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists product_shutdown_notifications (
                id integer primary key autoincrement,
                created_at text not null,
                notification_date text not null,
                product_name text not null,
                owner_prefixes text,
                plan_count integer,
                action_count integer,
                request_json text,
                response_json text,
                unique(notification_date, product_name)
            )
            """
        )
        conn.execute(
            """
            create table if not exists response_cache (
                cache_key text primary key,
                created_at text not null,
                expires_at real not null,
                method text not null,
                path text not null,
                status_code integer not null,
                response_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists report_response_cache (
                cache_key text primary key,
                created_at text not null,
                refreshed_at text not null,
                fingerprint text not null,
                start_time text not null,
                end_time text not null,
                marketing_goal text not null,
                status_code integer not null,
                response_json text not null
            )
            """
        )
        ensure_columns(conn, "plan_snapshots", METRIC_COLUMNS)
        ensure_columns(conn, "report_plan_rows", METRIC_COLUMNS)
        ensure_columns(conn, "plan_snapshots", PLAN_TYPE_COLUMNS)
        ensure_columns(conn, "report_plan_rows", PLAN_TYPE_COLUMNS)
        ensure_columns(conn, "report_runs", REPORT_TYPE_COLUMNS)
        ensure_columns(conn, "report_shop_rows", {key: value for key, value in METRIC_COLUMNS.items() if key != "roi_metric_json"})
        ensure_columns(conn, "dashboard_snapshots", {key: value for key, value in METRIC_COLUMNS.items() if key != "roi_metric_json"})
        ensure_columns(conn, "report_runs", {key: value for key, value in METRIC_COLUMNS.items() if key != "roi_metric_json"})
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass


def load_local_token():
    return os.environ.get("QIANCHUAN_CONTROL_TOKEN", "")


def redact(value):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if key.lower() in SECRET_KEYS:
                safe[key] = "[REDACTED]"
            else:
                safe[key] = redact(item)
        return safe
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def redact_sensitive_text(value):
    return re.sub(
        r"(https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=)[0-9A-Za-z-]+",
        r"\1[REDACTED]",
        value,
    )


def decode_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"raw": raw.decode("utf-8", errors="replace")}


def json_loads(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    try:
        return json.loads(value)
    except Exception:
        return default


def encode_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def beijing_datetime(*args):
    if args:
        return dt.datetime(*args, tzinfo=BEIJING_TZ)
    return dt.datetime.now(BEIJING_TZ)


def as_beijing_datetime(value=None):
    if value is None:
        return beijing_datetime()
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def beijing_now_text():
    return beijing_datetime().strftime("%Y-%m-%d %H:%M:%S")


def beijing_today_text():
    return beijing_datetime().strftime("%Y-%m-%d")


def number(value, default=0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def metric_values(item, include_roi_metric=False):
    item = item if isinstance(item, dict) else {}
    values = [
        number(item.get("payGmv")),
        number(item.get("payRoi")),
        number(item.get("settleGmv")),
        number(item.get("settleRoi")),
        number(item.get("realSettleGmv")),
        number(item.get("refundGmv")),
        int(number(item.get("refundOrders"))),
    ]
    if include_roi_metric:
        values.append(encode_json(redact(item.get("roiMetric") or {})))
    return values


def cache_ttl(path):
    if path in {"/api/me", "/api/shops", "/api/rule-groups", "/api/admin/users", "/api/qianchuan/rules"}:
        return 300
    if path == "/api/qianchuan/bootstrap":
        return 300
    if path == "/api/qianchuan/dashboard":
        return 180
    if path == "/api/qianchuan/plans":
        return 120
    if path == "/api/qianchuan/operation-board":
        return 30
    if path == "/api/qianchuan/logs":
        return 30
    return 0


def cache_fingerprint(headers):
    value = headers.get("Authorization") or headers.get("X-QC-Admin-Token") or ""
    if not value:
        return "anonymous"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def cache_key_for(method, full_path, headers):
    parsed = urllib.parse.urlparse(full_path)
    return hashlib.sha256(
        f"{method}\n{parsed.path}\n{parsed.query}\n{cache_fingerprint(headers)}".encode("utf-8")
    ).hexdigest()


def attach_cache_meta(response_data, meta):
    if not isinstance(response_data, dict):
        return response_data
    data = dict(response_data)
    data["_cache"] = meta
    return data


def get_cached_response(method, full_path, headers, allow_stale=False):
    parsed = urllib.parse.urlparse(full_path)
    ttl = cache_ttl(parsed.path)
    if method != "GET" or ttl <= 0:
        return None
    key = cache_key_for(method, full_path, headers)
    now = time.time()
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            select created_at, expires_at, status_code, response_json
            from response_cache
            where cache_key = ? and (? = 1 or expires_at > ?)
            """,
            (key, 1 if allow_stale else 0, now),
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["response_json"])
    except json.JSONDecodeError:
        return None
    meta = {
        "source": "response-cache",
        "createdAt": row["created_at"],
        "expiresAt": row["expires_at"],
        "stale": float(row["expires_at"]) <= now,
    }
    return int(row["status_code"]), data, meta


def set_cached_response(method, full_path, headers, status_code, response_data):
    parsed = urllib.parse.urlparse(full_path)
    ttl = cache_ttl(parsed.path)
    if method != "GET" or ttl <= 0 or not (200 <= int(status_code) < 300) or not isinstance(response_data, dict):
        return
    key = cache_key_for(method, full_path, headers)
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into response_cache(cache_key, created_at, expires_at, method, path, status_code, response_json)
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(cache_key) do update set
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                status_code = excluded.status_code,
                response_json = excluded.response_json
            """,
            (
                key,
                utc_now(),
                time.time() + ttl,
                method,
                parsed.path,
                int(status_code),
                encode_json(redact(response_data)),
            ),
        )


def clear_response_cache():
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("delete from response_cache where path != '/api/me'")
        conn.execute("delete from report_response_cache")


def report_cache_key(headers, query):
    start_time, end_time = report_time_range(query)
    marketing_goal = query_value(query, "marketing_goal", "VIDEO_PROM_GOODS")
    smart_bid_types = query_plan_smart_bid_types(query, default=PLAN_SMART_BID_TYPES)
    fingerprint = cache_fingerprint(headers)
    smart_bid_key = ",".join(smart_bid_types)
    raw = f"{fingerprint}\n{start_time}\n{end_time}\n{marketing_goal}\n{smart_bid_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), fingerprint, start_time, end_time, marketing_goal


def set_report_response_cache(headers, query, status_code, response_data):
    if not (200 <= int(status_code) < 300) or not isinstance(response_data, dict):
        return
    key, fingerprint, start_time, end_time, marketing_goal = report_cache_key(headers, query)
    now = utc_now()
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into report_response_cache(
                cache_key, created_at, refreshed_at, fingerprint, start_time,
                end_time, marketing_goal, status_code, response_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(cache_key) do update set
                refreshed_at = excluded.refreshed_at,
                status_code = excluded.status_code,
                response_json = excluded.response_json
            """,
            (
                key,
                now,
                now,
                fingerprint,
                start_time,
                end_time,
                marketing_goal,
                int(status_code),
                encode_json(redact(response_data)),
            ),
        )


def get_report_response_cache(headers, query):
    key, _, _, _, _ = report_cache_key(headers, query)
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            select created_at, refreshed_at, status_code, response_json
            from report_response_cache
            where cache_key = ?
            """,
            (key,),
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["response_json"])
    except json.JSONDecodeError:
        return None
    meta = {
        "source": "local-report-cache",
        "createdAt": row["created_at"],
        "refreshedAt": row["refreshed_at"],
        "stale": True,
        "refreshing": True,
    }
    return int(row["status_code"]), data, meta


def operator_from_headers(headers):
    auth = headers.get("Authorization") or ""
    if auth:
        return "session"
    if headers.get("X-QC-Admin-Token"):
        return "control-token"
    return ""


def operation_name(path, method):
    if method == "GET":
        return ""
    if path == "/api/auth/login":
        return "login"
    if path == "/api/auth/bootstrap":
        return "bootstrap-login"
    if path == "/api/auth/logout":
        return "logout"
    if path.startswith("/api/admin/users/delete"):
        return "delete-user"
    if path.startswith("/api/admin/users"):
        return "save-user"
    if path.startswith("/api/shops/delete"):
        return "delete-shop"
    if path.startswith("/api/shops"):
        return "save-shop"
    if path.startswith("/api/rule-groups/delete"):
        return "delete-rule-group"
    if path.startswith("/api/rule-groups"):
        return "save-rule-group"
    if path == "/api/qianchuan/rules":
        return "save-rules"
    if path.endswith("/actions/pause") or path.endswith("/actions/disable"):
        return "pause-plan"
    if path.endswith("/actions/enable"):
        return "start-plan"
    if path.endswith("/actions/budget"):
        return "update-budget"
    if path.endswith("/actions/reset-budgets"):
        return "reset-budgets"
    if path.endswith("/actions/run-rules"):
        return "run-rules"
    if path == "/api/local/notifications/wecom/config":
        return "save-wecom-bot"
    if path == "/api/local/notifications/wecom/test":
        return "test-wecom-bot"
    return "post"


def target_from_request(path, request_data):
    if not isinstance(request_data, dict):
        return "", ""
    if "/users" in path:
        return "user", str(request_data.get("id") or request_data.get("username") or "")
    if "/shops" in path:
        return "shop", str(request_data.get("shopId") or request_data.get("shop_id") or "")
    if "/rule-groups" in path:
        return "rule_group", str(request_data.get("id") or "")
    if path.endswith("/actions/reset-budgets"):
        return "plans", "daily-budget-reset"
    if "/actions/" in path:
        return "plan", str(request_data.get("ad_id") or "")
    if "/notifications/wecom" in path:
        return "notification", "wecom"
    return "", ""


def get_setting_row(key):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select key, value, updated_at from local_settings where key = ?", (key,)).fetchone()
    return dict(row) if row else None


def get_setting(key, default=""):
    row = get_setting_row(key)
    return row["value"] if row else default


def set_setting(key, value):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into local_settings(key, value, updated_at)
            values (?, ?, ?)
            on conflict(key) do update set value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, utc_now()),
        )


def setting_enabled(value):
    return str(value).lower() not in {"0", "false", "no", "off", ""}


def mobile_like(value):
    text = re.sub(r"\D", "", str(value or ""))
    return text if 5 <= len(text) <= 20 else ""


def yuan_text(value):
    amount = number(value)
    if amount == int(amount):
        return f"{int(amount)}元"
    return f"{amount:.2f}元"


def mask_webhook(webhook):
    if not webhook:
        return ""
    parsed = urllib.parse.urlparse(webhook)
    query = urllib.parse.parse_qs(parsed.query)
    key = query.get("key", [""])[0]
    if key:
        masked = f"{key[:4]}...{key[-4:]}" if len(key) >= 12 else "[REDACTED]"
        query["key"] = [masked]
    masked_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", masked_query, ""))


def validate_wecom_webhook(webhook):
    parsed = urllib.parse.urlparse(webhook)
    key = urllib.parse.parse_qs(parsed.query).get("key", [""])[0]
    return parsed.scheme == "https" and parsed.netloc == WECOM_WEBHOOK_HOST and parsed.path == WECOM_WEBHOOK_PATH and bool(key)


def wecom_config_summary():
    webhook_row = get_setting_row("wecom_webhook_url")
    enabled_row = get_setting_row("wecom_enabled")
    webhook = webhook_row["value"] if webhook_row else ""
    enabled = setting_enabled(enabled_row["value"] if enabled_row else "1")
    return {
        "configured": bool(webhook),
        "enabled": enabled,
        "maskedWebhook": mask_webhook(webhook),
        "updatedAt": webhook_row["updated_at"] if webhook_row else "",
    }


def save_wecom_config(request_data):
    if not isinstance(request_data, dict):
        return 400, {"ok": False, "error": "json body required"}
    webhook = str(request_data.get("webhookUrl") or request_data.get("webhook") or "").strip()
    if webhook:
        if not validate_wecom_webhook(webhook):
            return 400, {"ok": False, "error": "invalid wecom webhook"}
        set_setting("wecom_webhook_url", webhook)
    enabled = request_data.get("enabled")
    if enabled is not None:
        set_setting("wecom_enabled", "1" if bool(enabled) else "0")
    elif webhook:
        set_setting("wecom_enabled", "1")
    config = wecom_config_summary()
    if not config["configured"]:
        return 400, {"ok": False, "error": "wecom webhook is not configured", **config}
    return 200, {"ok": True, **config}


def send_wecom_message(content, msgtype="markdown", mentioned_mobiles=None):
    webhook = get_setting("wecom_webhook_url")
    enabled = setting_enabled(get_setting("wecom_enabled", "1"))
    if not webhook:
        return {"ok": False, "skipped": True, "reason": "wecom webhook is not configured"}
    if not enabled:
        return {"ok": False, "skipped": True, "reason": "wecom notification disabled"}
    if not validate_wecom_webhook(webhook):
        return {"ok": False, "skipped": True, "reason": "invalid wecom webhook"}
    text = str(content or "").strip()[:3900]
    if not text:
        text = "千川控制中心测试消息"
    mentioned_mobiles = [mobile for mobile in (mentioned_mobiles or []) if mobile_like(mobile)]
    if msgtype == "text" or mentioned_mobiles:
        text_payload = {"content": text}
        if mentioned_mobiles:
            text_payload["mentioned_mobile_list"] = list(dict.fromkeys(mentioned_mobiles))
        payload = {"msgtype": "text", "text": text_payload}
    else:
        payload = {"msgtype": "markdown", "markdown": {"content": text}}
    status = 502
    response_data = {}
    error_text = ""
    try:
        req = urllib.request.Request(
            webhook,
            data=encode_json(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            response_data = decode_json(resp.read())
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_data = decode_json(exc.read())
    except Exception as exc:
        error_text = str(exc)
        response_data = {"error": error_text}
    ok = 200 <= int(status) < 300 and isinstance(response_data, dict) and response_data.get("errcode") == 0
    return {"ok": ok, "skipped": False, "status": status, "response": response_data, "error": error_text}


def cloud_admin_get(path):
    token = load_local_token()
    if not token:
        return {}
    url = f"{CLOUD_API_BASE}{path}"
    try:
        req = urllib.request.Request(url, headers={"X-QC-Admin-Token": token}, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = decode_json(resp.read())
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def normalize_plan_prefix(value):
    prefix = str(value or "").strip().upper()[:2]
    if len(prefix) == 2 and prefix.isalpha() and prefix.isascii():
        return prefix
    return ""


def normalize_plan_prefixes(values):
    if not isinstance(values, list):
        return []
    prefixes = []
    seen = set()
    for value in values:
        prefix = normalize_plan_prefix(value)
        if prefix and prefix not in seen:
            prefixes.append(prefix)
            seen.add(prefix)
    return prefixes


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


def plan_prefix_label(prefix):
    prefix = normalize_plan_prefix(prefix)
    if not prefix:
        return "未分配"
    data = load_assignment_data()
    for option in data.get("planPrefixOptions") or []:
        if normalize_plan_prefix(option.get("prefix")) == prefix:
            return option.get("label") or f"{prefix} {option.get('ownerName') or '未绑定'}"
    return f"{prefix} {PLAN_PREFIX_OWNERS.get(prefix) or '未绑定'}"


def annotate_report_plan_owner(plan):
    if not isinstance(plan, dict):
        return {}
    item = dict(plan)
    prefix = normalize_plan_prefix(item.get("ownerPrefix")) or plan_prefix_for_name(item.get("name"))
    item["ownerPrefix"] = prefix
    item["ownerName"] = item.get("ownerName") or PLAN_PREFIX_OWNERS.get(prefix, "未分配")
    return item


def cached_report_scope(headers):
    cached = get_cached_response("GET", "/api/me", headers, allow_stale=True)
    data = cached[1] if cached else None
    if not data:
        status, data, error_text = cloud_get_json("/api/me", {}, headers, "/api/me#report-scope", "local-report")
        if not (200 <= int(status) < 300) or error_text or not isinstance(data, dict):
            return None
        persist_response("/api/me", data)
        set_cached_response("GET", "/api/me", headers, status, data)
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    shops = data.get("shops") if isinstance(data.get("shops"), list) else []
    return {
        "user": user,
        "shops": shops,
        "planPrefixOptions": data.get("planPrefixOptions") if isinstance(data.get("planPrefixOptions"), list) else [],
        "shopIds": {int(shop.get("shopId")) for shop in shops if isinstance(shop, dict) and shop.get("shopId")},
        "planPrefixes": normalize_plan_prefixes(user.get("planPrefixes") or []),
        "isAdmin": user.get("role") == "admin" or not user.get("role"),
    }


def build_report_user_summaries(plan_list, scope):
    if not scope:
        return []
    user = scope.get("user") or {}
    if user.get("role") != "admin":
        spend = round(sum(number(plan.get("spend")) for plan in plan_list), 2)
        gmv = round(sum(number(plan.get("gmv")) for plan in plan_list), 2)
        pay_gmv = round(sum(number(plan.get("payGmv")) for plan in plan_list), 2)
        settle_gmv = round(sum(number(plan.get("settleGmv")) for plan in plan_list), 2)
        real_settle_gmv = round(sum(number(plan.get("realSettleGmv")) for plan in plan_list), 2)
        refund_gmv = round(sum(number(plan.get("refundGmv")) for plan in plan_list), 2)
        orders = sum(int(number(plan.get("orders"))) for plan in plan_list)
        refund_orders = sum(int(number(plan.get("refundOrders"))) for plan in plan_list)
        return [
            {
                "userId": user.get("id"),
                "username": user.get("username"),
                "displayName": user.get("displayName") or user.get("username"),
                "role": user.get("role"),
                "status": user.get("status"),
                "planPrefixes": user.get("planPrefixes") or [],
                "planAssignments": user.get("planAssignments") or [],
                "shopCount": len({int(plan.get("shopId")) for plan in plan_list if plan.get("shopId")}),
                "planCount": len(plan_list),
                "orders": orders,
                "spend": spend,
                "gmv": gmv,
                "roi": round(gmv / spend, 4) if spend > 0 else 0,
                "payGmv": pay_gmv,
                "payRoi": round(pay_gmv / spend, 4) if spend > 0 else 0,
                "settleGmv": settle_gmv,
                "settleRoi": round(settle_gmv / spend, 4) if spend > 0 else 0,
                "realSettleGmv": real_settle_gmv,
                "refundGmv": refund_gmv,
                "refundOrders": refund_orders,
                "plans": plan_list,
            }
        ]
    groups = {}
    for plan in plan_list:
        prefix = normalize_plan_prefix(plan.get("ownerPrefix"))
        key = prefix or "-"
        item = groups.setdefault(
            key,
            {
                "userId": None,
                "username": key,
                "displayName": PLAN_PREFIX_OWNERS.get(prefix, "未分配"),
                "role": "operator",
                "status": "active" if prefix else "unassigned",
                "planPrefixes": [prefix] if prefix else [],
                "planAssignments": [],
                "shopCount": 0,
                "planCount": 0,
                "orders": 0,
                "spend": 0,
                "gmv": 0,
                "roi": 0,
                "payGmv": 0,
                "payRoi": 0,
                "settleGmv": 0,
                "settleRoi": 0,
                "realSettleGmv": 0,
                "refundGmv": 0,
                "refundOrders": 0,
                "plans": [],
            },
        )
        item["plans"].append(plan)
        item["planCount"] += 1
        item["orders"] += int(number(plan.get("orders")))
        item["spend"] += number(plan.get("spend"))
        item["gmv"] += number(plan.get("gmv"))
        item["payGmv"] += number(plan.get("payGmv"))
        item["settleGmv"] += number(plan.get("settleGmv"))
        item["realSettleGmv"] += number(plan.get("realSettleGmv"))
        item["refundGmv"] += number(plan.get("refundGmv"))
        item["refundOrders"] += int(number(plan.get("refundOrders")))
    for item in groups.values():
        item["spend"] = round(item["spend"], 2)
        item["gmv"] = round(item["gmv"], 2)
        item["payGmv"] = round(item["payGmv"], 2)
        item["settleGmv"] = round(item["settleGmv"], 2)
        item["realSettleGmv"] = round(item["realSettleGmv"], 2)
        item["refundGmv"] = round(item["refundGmv"], 2)
        item["roi"] = round(item["gmv"] / item["spend"], 4) if item["spend"] > 0 else 0
        item["payRoi"] = round(item["payGmv"] / item["spend"], 4) if item["spend"] > 0 else 0
        item["settleRoi"] = round(item["settleGmv"] / item["spend"], 4) if item["spend"] > 0 else 0
        item["shopCount"] = len({int(plan.get("shopId")) for plan in item["plans"] if plan.get("shopId")})
    return sorted(groups.values(), key=lambda item: (-number(item.get("spend")), item.get("username") or ""))


def load_assignment_data():
    now = time.time()
    if ASSIGNMENT_CACHE["expires_at"] > now:
        return ASSIGNMENT_CACHE
    users_data = cloud_admin_get("/api/admin/users")
    shops_data = cloud_admin_get("/api/shops")
    ASSIGNMENT_CACHE.update(
        {
            "expires_at": now + 60,
            "users": users_data.get("users") if isinstance(users_data.get("users"), list) else [],
            "shops": shops_data.get("shops") if isinstance(shops_data.get("shops"), list) else [],
            "planPrefixOptions": shops_data.get("planPrefixOptions") if isinstance(shops_data.get("planPrefixOptions"), list) else [],
        }
    )
    return ASSIGNMENT_CACHE


def assignees_for_plan_prefix(prefix):
    data = load_assignment_data()
    prefix = normalize_plan_prefix(prefix)
    users = data.get("users") or []
    assigned = [
        user
        for user in users
        if user.get("status") == "active"
        and user.get("role") != "admin"
        and prefix in normalize_plan_prefixes(user.get("planPrefixes") or [])
    ]
    if assigned:
        return assigned, False
    fallback = next((user for user in users if (user.get("displayName") or user.get("username")) == "Default Operator"), None)
    if fallback:
        return [fallback], True
    return [{"displayName": "Default Operator", "username": ""}], True


def rule_action_label(rule, request_data):
    action = rule.get("action")
    if action in {"ADD_BUDGET", "NEAR_BUDGET_ROI_ADD_BUDGET"}:
        infos = request_data.get("update_budget_infos") if isinstance(request_data, dict) else None
        new_budget = infos[0].get("budget") if isinstance(infos, list) and infos else None
        return f"增加预算到 {yuan_text(new_budget)}" if new_budget is not None else "增加预算"
    if action == "HOURLY_SPEND_INCREASE_ROI_GOAL":
        updates = request_data.get("roi_goal_updates") if isinstance(request_data, dict) else None
        new_goal = updates[0].get("roi_goal") if isinstance(updates, list) and updates else None
        return f"目标ROI调到 {number(new_goal):.2f}" if new_goal is not None else "提高目标ROI"
    return RULE_ACTION_LABELS.get(action, action or "执行规则")


def rule_reason(plan, rule):
    roi = number(plan.get("roi"))
    spend = number(plan.get("spend"))
    if rule.get("action") == "SPEND_STEP_ROI_STOP":
        step = number(rule.get("spendStep") or rule.get("minSpend"))
        delay = number(rule.get("delayMinutes"), 10)
        return f"每消耗 {yuan_text(step)} 后等待 {delay:.0f} 分钟，分段净成交ROI低于 {number(rule.get('roiBelow')):.2f}，当前累计消耗 {yuan_text(spend)}"
    if rule.get("action") == "NEAR_BUDGET_ROI_ADD_BUDGET":
        budget = number(plan.get("budget"))
        remaining_percent = 100
        if budget > 0:
            remaining_percent = max(0, budget - spend) / budget * 100
        return (
            f"剩余日预算 {remaining_percent:.1f}% 低于 {number(rule.get('budgetRemainingPercent')):.1f}%，"
            f"全天净成交ROI {roi:.2f} 高于 {number(rule.get('roiAbove')):.2f}"
        )
    if rule.get("action") == "HOURLY_SPEND_INCREASE_ROI_GOAL":
        elapsed = number(plan.get("elapsedMinutes"))
        hourly_spend = spend / (elapsed / 60) if elapsed > 0 else 0
        current_goal = number(plan.get("roiGoal"))
        return (
            f"每小时消耗 {yuan_text(hourly_spend)} 高于 {yuan_text(rule.get('hourlySpendAbove'))}，"
            f"当前目标ROI {current_goal:.2f}，增量 {number(rule.get('roiGoalIncrement')):.2f}，"
            f"封顶 {number(rule.get('maxRoiGoal'), 2.4):.2f}"
        )
    parts = [f"净成交ROI {roi:.2f}", f"消耗 {yuan_text(spend)}"]
    if number(rule.get("roiBelow")) > 0:
        parts.append(f"低于 {number(rule.get('roiBelow')):.2f}")
    if number(rule.get("roiAbove")) > 0:
        parts.append(f"高于 {number(rule.get('roiAbove')):.2f}")
    if number(rule.get("minSpend")) > 0:
        parts.append(f"最低消耗门槛 {yuan_text(rule.get('minSpend'))}")
    return "，".join(parts)


def integer_id(value):
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        return int(match.group(0)) if match else 0


def plan_id_value(plan):
    plan = plan if isinstance(plan, dict) else {}
    return integer_id(plan.get("id") or plan.get("ad_id") or plan.get("adId") or plan.get("plan_id") or plan.get("planId"))


def plan_product_name(plan):
    plan = plan if isinstance(plan, dict) else {}
    for key in ("product", "productName", "product_name", "goodsName", "goods_name"):
        value = str(plan.get(key) or "").strip()
        if value and value != "未返回商品名":
            return value
    raw = plan.get("raw") if isinstance(plan.get("raw"), dict) else {}
    for key in ("product", "productName", "product_name", "goodsName", "goods_name"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def action_plan_ids(action):
    action = action if isinstance(action, dict) else {}
    ids = set()
    plan_id = plan_id_value(action.get("plan") if isinstance(action.get("plan"), dict) else {})
    if plan_id:
        ids.add(plan_id)
    request_data = action.get("request") if isinstance(action.get("request"), dict) else {}
    for key in ("ad_ids", "adIds", "plan_ids", "planIds"):
        values = request_data.get(key)
        if isinstance(values, list):
            ids.update(integer_id(value) for value in values if integer_id(value))
    for key in ("ad_id", "adId", "plan_id", "planId"):
        value = integer_id(request_data.get(key))
        if value:
            ids.add(value)
    return ids


def action_is_successful(action):
    response = action.get("response") if isinstance(action, dict) and isinstance(action.get("response"), dict) else {}
    if response.get("ok") is True:
        return True
    if str(response.get("code")) != "0":
        return False
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    results = data.get("results")
    if isinstance(results, list) and results:
        return any(isinstance(item, dict) and item.get("flag") is True and not item.get("error") for item in results)
    return True


def action_is_auto_pause(action):
    action = action if isinstance(action, dict) else {}
    rule = action.get("rule") if isinstance(action.get("rule"), dict) else {}
    request_data = action.get("request") if isinstance(action.get("request"), dict) else {}
    return rule.get("action") in {"DISABLE", "SPEND_STEP_ROI_STOP"} or str(request_data.get("opt_status") or "").upper() in {"DISABLE", "PAUSED"}


def plan_is_paused_after_actions(plan, paused_plan_ids):
    plan_id = plan_id_value(plan)
    if plan_id and plan_id in paused_plan_ids:
        return True
    plan = plan if isinstance(plan, dict) else {}
    opt_status = str(plan.get("optStatus") or plan.get("opt_status") or plan.get("status") or "").upper()
    return opt_status in {"PAUSED", "DISABLE", "DISABLED"}


def product_shutdown_candidates(response_data):
    response_data = response_data if isinstance(response_data, dict) else {}
    actions = [item for item in (response_data.get("actions") or []) if isinstance(item, dict)]
    successful_pause_actions = [item for item in actions if action_is_auto_pause(item) and action_is_successful(item)]
    if not successful_pause_actions:
        return []

    paused_plan_ids = set()
    action_counts_by_product = {}
    action_plans_by_product = {}
    for action in successful_pause_actions:
        paused_plan_ids.update(action_plan_ids(action))
        plan = action.get("plan") if isinstance(action.get("plan"), dict) else {}
        product_name = plan_product_name(plan)
        if not product_name:
            continue
        action_counts_by_product[product_name] = action_counts_by_product.get(product_name, 0) + 1
        action_plans_by_product.setdefault(product_name, []).append(plan)

    if not action_counts_by_product:
        return []

    plans = [plan for plan in (response_data.get("plans") or []) if isinstance(plan, dict)]
    plans_by_product = {}
    for plan in plans:
        product_name = plan_product_name(plan)
        if product_name in action_counts_by_product:
            plans_by_product.setdefault(product_name, []).append(plan)
    for product_name, action_plans in action_plans_by_product.items():
        if not plans_by_product.get(product_name):
            plans_by_product[product_name] = action_plans

    candidates = []
    for product_name, action_count in action_counts_by_product.items():
        product_plans = plans_by_product.get(product_name) or []
        if not product_plans:
            continue
        if not all(plan_is_paused_after_actions(plan, paused_plan_ids) for plan in product_plans):
            continue
        prefixes = normalize_plan_prefixes(
            [
                normalize_plan_prefix(plan.get("ownerPrefix")) or plan_prefix_for_name(plan.get("name"))
                for plan in product_plans
            ]
        )
        spend = round(sum(number(plan.get("spend")) for plan in product_plans), 2)
        gmv = round(sum(number(plan.get("gmv")) for plan in product_plans), 2)
        candidates.append(
            {
                "productName": product_name,
                "productId": next((plan.get("productId") for plan in product_plans if plan.get("productId")), None),
                "ownerPrefixes": prefixes,
                "ownerLabels": [plan_prefix_label(prefix) for prefix in prefixes],
                "planCount": len(product_plans),
                "actionCount": action_count,
                "spend": spend,
                "gmv": gmv,
                "roi": round(gmv / spend, 4) if spend > 0 else 0,
                "plans": product_plans,
            }
        )
    return candidates


def product_shutdown_notification_exists(notification_date, product_name):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            select id from product_shutdown_notifications
            where notification_date = ? and product_name = ?
            limit 1
            """,
            (notification_date, product_name),
        ).fetchone()
    return row is not None


def record_product_shutdown_notification(notification_date, item, request_data, result):
    ensure_db()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                insert into product_shutdown_notifications(
                    created_at, notification_date, product_name, owner_prefixes,
                    plan_count, action_count, request_json, response_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    notification_date,
                    item.get("productName") or "",
                    ",".join(item.get("ownerPrefixes") or []),
                    int(number(item.get("planCount"))),
                    int(number(item.get("actionCount"))),
                    encode_json(redact(request_data)),
                    encode_json(redact(result)),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def format_product_shutdown_notification(item, names, fallback):
    mention_line = " ".join(f"@{name}" for name in names)
    prefixes = "、".join(item.get("ownerLabels") or []) or "未分配"
    lines = [
        mention_line,
        "千川商品全停提醒",
        f"商品：{item.get('productName') or '-'}",
        f"投手：{prefixes}",
        f"结果：该商品今天触发自动暂停后，当前可见计划已全部暂停",
        f"计划数：{item.get('planCount') or 0}，本次自动暂停：{item.get('actionCount') or 0}",
        f"今日消耗：{yuan_text(item.get('spend'))}，净成交ROI：{number(item.get('roi')):.2f}",
    ]
    if fallback:
        lines.append("提醒：部分计划没有绑定投手，已按默认规则通知Default Operator。")
    for index, plan in enumerate((item.get("plans") or [])[:10], 1):
        lines.append(f"{index}. {plan.get('name') or plan.get('id') or '-'}")
    if len(item.get("plans") or []) > 10:
        lines.append(f"还有 {len(item.get('plans') or []) - 10} 条计划，请到控制台商品页查看。")
    lines.append(f"时间：{beijing_now_text()}")
    return "\n".join(lines)


def notify_product_full_pauses(request_data, response_data):
    request_data = request_data if isinstance(request_data, dict) else {}
    response_data = response_data if isinstance(response_data, dict) else {}
    notification_date = beijing_today_text()
    notifications = []
    for item in product_shutdown_candidates(response_data):
        if product_shutdown_notification_exists(notification_date, item.get("productName") or ""):
            item["notification"] = {"ok": False, "skipped": True, "reason": "already-notified-today"}
            notifications.append(item)
            continue
        names, mobiles, fallback = notification_recipients_for_prefixes(item.get("ownerPrefixes") or [])
        message = format_product_shutdown_notification(item, names, fallback)
        result = send_wecom_message(message, "text", mentioned_mobiles=mobiles)
        item["mentionNames"] = names
        item["notification"] = result
        record_api(
            "POST",
            "/api/local/notifications/wecom#product-full-pause",
            200 if result.get("ok") or result.get("skipped") else 502,
            result.get("ok", False),
            "local-notifier",
            {
                "sourcePath": "/api/qianchuan/actions/run-rules",
                "productName": item.get("productName"),
                "ownerPrefixes": item.get("ownerPrefixes"),
                "message": message,
            },
            result,
        )
        if result.get("ok"):
            record_product_shutdown_notification(notification_date, item, request_data, result)
        notifications.append(item)
    return notifications


def notification_recipients_for_prefixes(prefixes):
    prefixes = normalize_plan_prefixes(prefixes)
    users_by_key = {}
    fallback = False
    for prefix in prefixes:
        users, used_fallback = assignees_for_plan_prefix(prefix)
        fallback = fallback or used_fallback
        for user in users:
            key = user.get("id") or user.get("username") or user.get("displayName")
            users_by_key[key] = user
    if not prefixes:
        users_by_key["fallback"] = {"displayName": "Default Operator", "username": ""}
        fallback = True
    names = []
    mobiles = []
    for user in users_by_key.values():
        name = str(user.get("displayName") or user.get("username") or "").strip()
        if name:
            names.append(name)
        mobile = mobile_like(user.get("username"))
        if mobile:
            mobiles.append(mobile)
    if not names:
        names = ["Default Operator"]
    return names, mobiles, fallback


def format_rule_actions_notification(request_data, response_data):
    request_data = request_data if isinstance(request_data, dict) else {}
    actions = response_data.get("actions") if isinstance(response_data, dict) else []
    actions = [item for item in (actions or []) if isinstance(item, dict)]
    prefixes = []
    for item in actions:
        plan = item.get("plan") if isinstance(item.get("plan"), dict) else {}
        prefix = normalize_plan_prefix(plan.get("ownerPrefix")) or plan_prefix_for_name(plan.get("name"))
        if prefix:
            prefixes.append(prefix)
    names, mobiles, fallback = notification_recipients_for_prefixes(prefixes)
    prefix_labels = "、".join(plan_prefix_label(prefix) for prefix in normalize_plan_prefixes(prefixes)) or "未分配"
    mention_line = " ".join(f"@{name}" for name in names)
    lines = [
        f"{mention_line}",
        "千川规则触发通知",
        f"计划归属：{prefix_labels}",
    ]
    if fallback:
        lines.append("提醒：部分计划没有绑定投手，已按默认规则通知Default Operator。")
    lines.append(f"命中数量：{len(actions)}")
    for index, item in enumerate(actions[:20], 1):
        plan = item.get("plan") if isinstance(item.get("plan"), dict) else {}
        rule = item.get("rule") if isinstance(item.get("rule"), dict) else {}
        response = item.get("response") if isinstance(item.get("response"), dict) else {}
        req = item.get("request") if isinstance(item.get("request"), dict) else {}
        ok = response.get("code") == 0 or response.get("ok") is True
        plan_name = str(plan.get("name") or plan.get("id") or "-").strip()
        rule_name = str(rule.get("name") or rule.get("id") or "-").strip()
        lines.extend(
            [
                "",
                f"{index}. 计划：{plan_name}",
                f"计划ID：{plan.get('id') or req.get('plan_id') or '-'}",
                f"触发规则：{rule_name}",
                f"触发条件：{rule_reason(plan, rule)}",
                f"执行操作：{rule_action_label(rule, req)}",
                f"执行结果：{'成功' if ok else '失败'}",
            ]
        )
        message = response.get("message") or response.get("error")
        if message:
            lines.append(f"接口返回：{message}")
    if len(actions) > 20:
        lines.append("")
        lines.append(f"还有 {len(actions) - 20} 条命中没有在本条消息展开，请到控制台查看日志。")
    lines.append("")
    lines.append(f"时间：{beijing_now_text()}")
    return "\n".join(lines), names, mobiles, normalize_plan_prefixes(prefixes)


def notify_rule_actions(request_data, response_data):
    actions = response_data.get("actions") if isinstance(response_data, dict) else []
    if not actions:
        return {"ok": False, "skipped": True, "reason": "no rule actions"}
    message, names, mobiles, prefixes = format_rule_actions_notification(request_data, response_data)
    result = send_wecom_message(message, "text", mentioned_mobiles=mobiles)
    product_notifications = notify_product_full_pauses(request_data, response_data)
    if isinstance(response_data, dict):
        response_data["productShutdownNotifications"] = product_notifications
    journal_request = {
        "sourcePath": "/api/qianchuan/actions/run-rules",
        "planPrefixes": prefixes,
        "actionCount": len(actions),
        "mentionNames": names,
        "message": message,
    }
    record_api(
        "POST",
        "/api/local/notifications/wecom#rules",
        200 if result.get("ok") or result.get("skipped") else 502,
        result.get("ok", False),
        "local-notifier",
        journal_request,
        result,
    )
    return {**result, "productShutdownNotifications": product_notifications}


def format_operation_notification(path, operator, request_data, response_data):
    request_data = request_data if isinstance(request_data, dict) else {}
    response_data = response_data if isinstance(response_data, dict) else {}
    label = ACTION_LABELS.get(path, "投放操作")
    shop_id = request_data.get("shopId") or request_data.get("shop_id")
    advertiser_id = request_data.get("advertiser_id") or request_data.get("advertiserId")
    plan_id = request_data.get("ad_id") or request_data.get("adId")
    plan_name = request_data.get("planName") or request_data.get("plan_name")
    owner_prefix = normalize_plan_prefix(request_data.get("ownerPrefix")) or plan_prefix_for_name(plan_name)
    budget = request_data.get("budget")
    result = "成功" if response_data.get("ok", True) else "失败"
    lines = [
        "### 千川投放操作通知",
        f"> 操作：{label}",
        f"> 结果：{result}",
        f"> 操作人：{operator or 'unknown'}",
        f"> 时间：{beijing_now_text()}",
    ]
    if shop_id:
        lines.append(f"> 店铺ID：{shop_id}")
    if advertiser_id:
        lines.append(f"> 广告账户：{advertiser_id}")
    if plan_id:
        lines.append(f"> 计划ID：{plan_id}")
    if plan_name:
        lines.append(f"> 计划：{plan_name}")
    if owner_prefix:
        lines.append(f"> 投手：{plan_prefix_label(owner_prefix)}")
    if budget is not None:
        lines.append(f"> 新预算：{budget}")
    if path == "/api/qianchuan/actions/reset-budgets":
        target_budget = response_data.get("targetBudget") or budget
        if target_budget is not None:
            lines.append(f"> 归位预算：{target_budget}")
        lines.append(f"> 覆盖计划数：{response_data.get('totalPlans', 0)}")
        lines.append(f"> 需调整计划：{response_data.get('updateCount', 0)}")
        lines.append(f"> 已是目标预算：{response_data.get('skippedCount', 0)}")
        if response_data.get("dryRun"):
            lines.append("> 模式：Dry Run")
    message = response_data.get("message") or response_data.get("error")
    if message:
        lines.append(f"> 返回：{message}")
    return "\n".join(lines)


def notify_operation(path, operator, request_data, response_data):
    if path not in ACTION_LABELS:
        return {"ok": False, "skipped": True, "reason": "not a notification action"}
    if path == "/api/qianchuan/actions/run-rules":
        return notify_rule_actions(request_data if isinstance(request_data, dict) else {}, response_data if isinstance(response_data, dict) else {})
    message = format_operation_notification(path, operator, request_data, response_data)
    result = send_wecom_message(message, "markdown")
    record_api("POST", "/api/local/notifications/wecom#auto", 200 if result.get("ok") or result.get("skipped") else 502, result.get("ok", False), "local-notifier", {"sourcePath": path, "message": message}, result)
    return result


def record_api(method, path, status_code, ok, operator, request_data, response_data, error_text=""):
    ensure_db()
    with connect_db() as conn:
        conn.execute(
            """
            insert into api_journal(created_at, method, path, status_code, ok, operator, request_json, response_json, error_text)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                method,
                path,
                int(status_code),
                1 if ok else 0,
                operator,
                encode_json(redact(request_data)),
                encode_json(redact(response_data)),
                error_text,
            ),
        )


def record_operation(method, path, operator, request_data, response_data, ok):
    operation = operation_name(path, method)
    if not operation:
        return
    target_type, target_id = target_from_request(path, request_data)
    ensure_db()
    with connect_db() as conn:
        conn.execute(
            """
            insert into operation_logs(created_at, operator, operation, target_type, target_id, path, ok, request_json, response_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                operator,
                operation,
                target_type,
                target_id,
                path,
                1 if ok else 0,
                encode_json(redact(request_data)),
                encode_json(redact(response_data)),
            ),
        )


def persist_response(path, response_data):
    if not isinstance(response_data, dict):
        return
    ensure_db()
    captured_at = utc_now()
    with sqlite3.connect(DB_PATH) as conn:
        if path == "/api/qianchuan/plans":
            store_plan_snapshot_rows(conn, captured_at, response_data)
        elif path == "/api/qianchuan/dashboard":
            summary = response_data.get("global") or {}
            conn.execute(
                """
                insert into dashboard_snapshots(
                    captured_at, scope, shop_count, spend, gmv, roi,
                    pay_gmv, pay_roi, settle_gmv, settle_roi, real_settle_gmv,
                    refund_gmv, refund_orders, payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    captured_at,
                    response_data.get("scope"),
                    summary.get("shopCount"),
                    number(summary.get("spend")),
                    number(summary.get("gmv")),
                    number(summary.get("roi")),
                    *metric_values(summary),
                    encode_json(redact(response_data)),
                ),
            )
            for shop in response_data.get("shops") or []:
                if isinstance(shop, dict):
                    conn.execute(
                        """
                        insert into shop_snapshots(captured_at, shop_id, advertiser_id, shop_name, payload_json)
                        values (?, ?, ?, ?, ?)
                        """,
                        (
                            captured_at,
                            shop.get("shopId"),
                            shop.get("advertiserId"),
                            shop.get("shopName"),
                encode_json(redact(shop)),
            ),
        )
        elif path in {"/api/shops", "/api/me"}:
            for shop in response_data.get("shops") or []:
                if isinstance(shop, dict):
                    conn.execute(
                        """
                        insert into shop_snapshots(captured_at, shop_id, advertiser_id, shop_name, payload_json)
                        values (?, ?, ?, ?, ?)
                        """,
                        (
                            captured_at,
                            shop.get("shopId"),
                            shop.get("advertiserId"),
                            shop.get("shopName"),
                            encode_json(redact(shop)),
                        ),
                    )
        elif path == "/api/qianchuan/logs":
            for item in response_data.get("logs") or []:
                if not isinstance(item, dict):
                    continue
                conn.execute(
                    """
                    insert or ignore into remote_action_logs(
                        captured_at, remote_created_at, action, dry_run, request_json, response_json
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        captured_at,
                        item.get("created_at"),
                        item.get("action"),
                        1 if item.get("dry_run") else 0,
                        encode_json(redact(item.get("request"))),
                        encode_json(redact(item.get("response"))),
                    ),
                    )


def store_plan_snapshot_rows(conn, captured_at, response_data):
    count = 0
    shop = response_data.get("shop") or {}
    for plan in response_data.get("plans") or []:
        if not isinstance(plan, dict):
            continue
        conn.execute(
            """
            insert into plan_snapshots(
                captured_at, shop_id, advertiser_id, plan_id, plan_name, opt_status, status,
                spend, gmv, roi, budget, pay_gmv, pay_roi, settle_gmv, settle_roi,
                real_settle_gmv, refund_gmv, refund_orders, roi_metric_json, smart_bid_type, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                captured_at,
                plan.get("shopId") or shop.get("shopId"),
                plan.get("advertiserId") or response_data.get("advertiser_id") or shop.get("advertiserId"),
                plan.get("id"),
                plan.get("name"),
                plan.get("optStatus"),
                plan.get("status"),
                number(plan.get("spend")),
                number(plan.get("gmv")),
                number(plan.get("roi")),
                number(plan.get("budget")),
                *metric_values(plan, include_roi_metric=True),
                plan_smart_bid_type(plan),
                encode_json(redact(plan)),
            ),
        )
        count += 1
    return count


def persist_current_plan_snapshot(plans):
    captured_at = utc_now()
    ensure_db()
    with connect_db() as conn:
        count = store_plan_snapshot_rows(conn, captured_at, {"plans": plans if isinstance(plans, list) else []})
    set_setting(CURRENT_PLAN_SNAPSHOT_CAPTURED_AT_KEY, captured_at)
    return count


def page_total(page_info):
    if not isinstance(page_info, dict):
        return 0
    for key in ("total_num", "total_number", "total_count", "total"):
        try:
            value = page_info.get(key)
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def query_value(query, name, default=""):
    value = query.get(name)
    if isinstance(value, list) and value:
        return value[0]
    return default


def report_time_range(query):
    now = dt.datetime.utcnow() + dt.timedelta(hours=8)
    today = now.strftime("%Y-%m-%d")
    start_time = query_value(query, "start_time")
    end_time = query_value(query, "end_time")
    if start_time and end_time:
        return start_time, end_time
    date_from = query_value(query, "date_from", today)
    date_to = query_value(query, "date_to", date_from)
    return f"{date_from} 00:00:00", f"{date_to} 23:59:59"


def parse_report_date(value):
    return dt.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def report_dates_between(start_time, end_time):
    start_date = parse_report_date(start_time)
    end_date = parse_report_date(end_time)
    if end_date < start_date:
        return []
    days = []
    current = start_date
    while current <= end_date:
        days.append(current.strftime("%Y-%m-%d"))
        current += dt.timedelta(days=1)
    return days


def cached_visible_shop_ids(headers):
    cached = get_cached_response("GET", "/api/me", headers, allow_stale=True)
    if not cached:
        return None
    _, data, _ = cached
    shops = data.get("shops") if isinstance(data, dict) else None
    if not isinstance(shops, list):
        return None
    return {int(shop.get("shopId")) for shop in shops if isinstance(shop, dict) and shop.get("shopId")}


def cached_response_data(full_path, headers):
    cached = get_cached_response("GET", full_path, headers, allow_stale=True)
    if not cached:
        return None
    _, data, _ = cached
    return data if isinstance(data, dict) else None


def local_plan_prefix_options(me_data):
    options = me_data.get("planPrefixOptions") if isinstance(me_data, dict) else None
    if isinstance(options, list) and options:
        return options
    return [
        {"prefix": prefix, "ownerName": owner, "label": f"{prefix} {owner}"}
        for prefix, owner in PLAN_PREFIX_OWNERS.items()
    ]


def owner_name_for_prefix(prefix, options):
    prefix = normalize_plan_prefix(prefix)
    for option in options or []:
        if normalize_plan_prefix(option.get("prefix")) == prefix:
            return option.get("ownerName") or str(option.get("label") or "").replace(prefix, "").strip() or PLAN_PREFIX_OWNERS.get(prefix, "")
    return PLAN_PREFIX_OWNERS.get(prefix, "")


def latest_plan_snapshot_payloads(limit=1000):
    ensure_db()
    current_captured_at = get_setting(CURRENT_PLAN_SNAPSHOT_CAPTURED_AT_KEY, "")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if current_captured_at:
            rows = conn.execute(
                """
                select payload_json
                from plan_snapshots
                where captured_at = ?
                order by spend desc, id desc
                limit ?
                """,
                (current_captured_at, int(limit)),
            ).fetchall()
            return decode_plan_snapshot_rows(rows)
        rows = conn.execute(
            """
            select ps.payload_json
            from plan_snapshots ps
            join (
                select plan_id, max(id) as id
                from plan_snapshots
                where plan_id is not null
                group by plan_id
            ) latest on latest.id = ps.id
            order by ps.spend desc, ps.id desc
            limit ?
            """,
            (int(limit),),
        ).fetchall()
    return decode_plan_snapshot_rows(rows)


def decode_plan_snapshot_rows(rows):
    plans = []
    for row in rows:
        try:
            plan = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(plan, dict):
            plans.append(plan)
    return plans


def normalize_local_plan(plan, options):
    item = dict(plan)
    prefix = normalize_plan_prefix(item.get("ownerPrefix")) or plan_prefix_for_name(item.get("name"))
    item["ownerPrefix"] = prefix
    item["ownerName"] = item.get("ownerName") or owner_name_for_prefix(prefix, options)
    item["spend"] = number(item.get("spend"))
    item["gmv"] = number(item.get("gmv"))
    item["roi"] = number(item.get("roi"), item["gmv"] / item["spend"] if item["spend"] > 0 else 0)
    item["budget"] = number(item.get("budget"))
    item["orders"] = int(number(item.get("orders")))
    return item


def filter_plans_for_user(plans, user):
    if not isinstance(user, dict) or user.get("role") == "admin":
        return plans
    allowed = set(normalize_plan_prefixes(user.get("planPrefixes") or []))
    if not allowed:
        return []
    return [plan for plan in plans if normalize_plan_prefix(plan.get("ownerPrefix")) in allowed]


def operation_board_date(query=None, now=None):
    query = query if isinstance(query, dict) else {}
    for name in ("date", "day"):
        value = query_value(query, name, "")
        if value:
            try:
                return dt.date.fromisoformat(str(value)[:10]).isoformat()
            except ValueError:
                continue
    return as_beijing_datetime(now).date().isoformat()


def beijing_date_utc_range(day):
    start_bj = dt.datetime.fromisoformat(day).replace(tzinfo=BEIJING_TZ)
    end_bj = start_bj + dt.timedelta(days=1)
    return start_bj.astimezone(dt.timezone.utc).isoformat(), end_bj.astimezone(dt.timezone.utc).isoformat()


def request_plan_ids(payload):
    payload = payload if isinstance(payload, dict) else {}
    ids = []
    for key in ("ad_id", "adId", "plan_id", "planId", "id"):
        value = int(number(payload.get(key), 0))
        if value > 0:
            ids.append(value)
    for key in ("ad_ids", "adIds", "plan_ids", "planIds"):
        values = payload.get(key)
        if isinstance(values, list):
            ids.extend(int(number(item, 0)) for item in values if int(number(item, 0)) > 0)
    for key in ("data", "update_infos", "update_budget_infos", "roi_goal_updates"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for field in ("ad_id", "adId", "plan_id", "planId", "id"):
                value = int(number(item.get(field), 0))
                if value > 0:
                    ids.append(value)
    seen = set()
    result = []
    for item in ids:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def action_plan_ids(action):
    action = action if isinstance(action, dict) else {}
    ids = []
    plan = action.get("plan") if isinstance(action.get("plan"), dict) else {}
    plan_id = int(number(plan.get("id"), 0))
    if plan_id > 0:
        ids.append(plan_id)
    ids.extend(request_plan_ids(action.get("request")))
    seen = set()
    result = []
    for item in ids:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def ocean_update_ok(data):
    if not isinstance(data, dict) or data.get("code") != 0:
        return False
    payload = data.get("data")
    if not isinstance(payload, dict):
        return True
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return True
    for item in results:
        if not isinstance(item, dict):
            return False
        if item.get("status") and item.get("status") != "SUCCESS":
            return False
        if "flag" in item and item.get("flag") is not True:
            return False
        if item.get("error") or item.get("error_message"):
            return False
    return True


def action_response_ok(response):
    response = response if isinstance(response, dict) else {}
    if response.get("ok") is False:
        return False
    nested = response.get("response")
    if isinstance(nested, dict):
        return action_response_ok(nested)
    if "code" in response:
        return ocean_update_ok(response)
    if "ok" in response:
        return bool(response.get("ok"))
    return True


def action_is_auto_pause(action):
    action = action if isinstance(action, dict) else {}
    rule = action.get("rule") if isinstance(action.get("rule"), dict) else {}
    request_data = action.get("request") if isinstance(action.get("request"), dict) else {}
    if rule.get("action") in {"DISABLE", "SPEND_STEP_ROI_STOP"}:
        return True
    if str(request_data.get("opt_status") or "").upper() == "DISABLE":
        return True
    data = request_data.get("data")
    if isinstance(data, list):
        return any(str(item.get("opt_status") or "").upper() == "DISABLE" for item in data if isinstance(item, dict))
    return False


def successful_local_enable_events_since(start_utc):
    ensure_db()
    events = []
    with connect_db() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select created_at, request_json, response_json
            from operation_logs
            where operation = 'start-plan' and ok = 1 and created_at >= ?
            order by created_at asc
            """,
            (start_utc,),
        ).fetchall()
    for row in rows:
        request_data = json_loads(row["request_json"], {}) or {}
        response_data = json_loads(row["response_json"], {}) or {}
        if not action_response_ok(response_data):
            continue
        for plan_id in request_plan_ids(request_data):
            events.append(
                {
                    "planId": plan_id,
                    "createdAt": row["created_at"],
                    "request": request_data,
                    "response": response_data,
                }
            )
    return events


def operation_board_user_and_options(headers):
    me_data = cached_response_data("/api/me", headers or {}) or {}
    user = me_data.get("user") if isinstance(me_data, dict) and isinstance(me_data.get("user"), dict) else {"role": "admin"}
    options = local_plan_prefix_options(me_data if isinstance(me_data, dict) else {})
    return user, options


def operation_board_plan(plan, options):
    item = dict(plan) if isinstance(plan, dict) else {}
    prefix = normalize_plan_prefix(item.get("ownerPrefix")) or plan_prefix_for_name(item.get("name"))
    smart_bid_type = plan_smart_bid_type(item)
    item["ownerPrefix"] = prefix
    item["ownerName"] = item.get("ownerName") or owner_name_for_prefix(prefix, options)
    item["smartBidType"] = smart_bid_type
    item["smartBidLabel"] = "放量" if smart_bid_type == "SMART_BID_CONSERVATIVE" else "控成本"
    return item


def local_budget_reset_run(row):
    request_data = json_loads(row["request_json"], {}) or {}
    response_data = json_loads(row["response_json"], {}) or {}
    smart_bid_types = normalize_plan_smart_bid_types(
        response_data.get("planSmartBidTypes") or request_data.get("planSmartBidTypes"),
        default=[],
    )
    target_budget = response_data.get("targetBudget")
    if target_budget is None:
        target_budget = request_data.get("budget")
    budget_targets = response_data.get("budgetTargets") if isinstance(response_data.get("budgetTargets"), dict) else {}
    if not budget_targets and target_budget is not None:
        budget_targets = {smart_bid_type: target_budget for smart_bid_type in smart_bid_types}
    ok = bool(row["ok"]) and action_response_ok(response_data)
    return {
        "runKey": f"{operation_board_date({'date': [row['created_at'][:10]]})}-{row['id']}",
        "status": "success" if ok else "failed",
        "startedAt": row["created_at"],
        "finishedAt": row["created_at"],
        "targetBudget": target_budget,
        "budgetTargets": budget_targets,
        "planSmartBidTypes": smart_bid_types,
        "totalPlans": int(number(response_data.get("totalPlans"), 0)),
        "updateCount": int(number(response_data.get("updateCount"), 0)),
        "skippedCount": int(number(response_data.get("skippedCount"), 0)),
        "limitedSkipCount": int(number(response_data.get("limitedSkipCount"), 0)),
        "missingCount": int(number(response_data.get("missingCount"), 0)),
        "chunkCount": int(number(response_data.get("chunkCount"), 0)),
        "source": request_data.get("source") or response_data.get("source") or "",
        "sourceErrors": response_data.get("sourceErrors") or [],
        "ok": ok,
        "error": response_data.get("error") or "",
    }


def aggregate_budget_reset_runs(day, runs):
    runs = runs if isinstance(runs, list) else []
    if not runs:
        return None
    totals = {
        "totalPlans": 0,
        "updateCount": 0,
        "skippedCount": 0,
        "limitedSkipCount": 0,
        "missingCount": 0,
        "chunkCount": 0,
    }
    budget_targets = {}
    smart_bid_types = []
    errors = []
    for run in runs:
        for key in totals:
            totals[key] += int(number(run.get(key), 0))
        for key, value in (run.get("budgetTargets") or {}).items():
            budget_targets[key] = value
        for smart_bid_type in run.get("planSmartBidTypes") or []:
            if smart_bid_type not in smart_bid_types:
                smart_bid_types.append(smart_bid_type)
        if run.get("error"):
            errors.append(run["error"])
        errors.extend(run.get("sourceErrors") or [])
    ok = all(bool(run.get("ok")) for run in runs)
    return {
        "runKey": day,
        "status": "success" if ok else "failed",
        "startedAt": min((run.get("startedAt") or "" for run in runs), default=""),
        "finishedAt": max((run.get("finishedAt") or "" for run in runs), default=""),
        "budgetTargets": budget_targets,
        "planSmartBidTypes": smart_bid_types,
        "ok": ok,
        "error": "；".join(str(item) for item in errors if item),
        **totals,
    }


def local_operation_board_summary(headers=None, query=None, now=None):
    day = operation_board_date(query, now)
    start_utc, end_utc = beijing_date_utc_range(day)
    user, options = operation_board_user_and_options(headers or {})
    restore_events = successful_local_enable_events_since(start_utc)
    records = []

    ensure_db()
    with connect_db() as conn:
        conn.row_factory = sqlite3.Row
        rule_rows = conn.execute(
            """
            select id, created_at, request_json, response_json
            from operation_logs
            where operation = 'run-rules' and ok = 1 and created_at >= ? and created_at < ?
            order by created_at desc, id desc
            """,
            (start_utc, end_utc),
        ).fetchall()
        reset_rows = conn.execute(
            """
            select id, created_at, ok, request_json, response_json
            from operation_logs
            where operation = 'reset-budgets' and created_at >= ? and created_at < ?
            order by created_at desc, id desc
            """,
            (start_utc, end_utc),
        ).fetchall()

    for row in rule_rows:
        response_data = json_loads(row["response_json"], {}) or {}
        for action in response_data.get("actions") or []:
            if not isinstance(action, dict) or not action_is_auto_pause(action):
                continue
            if not action_response_ok(action.get("response")):
                continue
            plan = operation_board_plan(action.get("plan"), options)
            plan_ids = action_plan_ids(action)
            plan_id = int(number(plan.get("id"), plan_ids[0] if plan_ids else 0))
            if plan_id <= 0:
                continue
            plan["id"] = plan_id
            if not filter_plans_for_user([plan], user):
                continue
            restored_event = next(
                (item for item in restore_events if item["planId"] == plan_id and item["createdAt"] >= row["created_at"]),
                None,
            )
            rule = action.get("rule") if isinstance(action.get("rule"), dict) else {}
            request_data = action.get("request") if isinstance(action.get("request"), dict) else {}
            record = {
                "key": f"{plan_id}-{row['created_at']}-{rule.get('id') or rule.get('action') or 'auto'}",
                "planId": plan_id,
                "planName": plan.get("name") or f"计划 {plan_id}",
                "product": plan.get("product") or "",
                "ownerPrefix": normalize_plan_prefix(plan.get("ownerPrefix")),
                "ownerName": plan.get("ownerName") or "",
                "shopId": plan.get("shopId"),
                "advertiserId": plan.get("advertiserId") or request_data.get("advertiser_id"),
                "marketingGoal": plan.get("marketingGoal") or request_data.get("marketing_goal") or "VIDEO_PROM_GOODS",
                "smartBidType": plan.get("smartBidType") or CONTROL_PLAN_SMART_BID_TYPES[0],
                "smartBidLabel": plan.get("smartBidLabel") or "控成本",
                "ruleId": rule.get("id") or "",
                "ruleName": rule.get("name") or rule.get("action") or "自动止损",
                "ruleAction": rule.get("action") or "",
                "pausedAt": row["created_at"],
                "finishedAt": row["created_at"],
                "restored": bool(restored_event),
                "restoredAt": restored_event.get("createdAt") if restored_event else "",
            }
            record["status"] = "restored" if record["restored"] else "pending"
            records.append(record)

    deduped = {}
    for record in sorted(records, key=lambda item: item["pausedAt"], reverse=True):
        deduped.setdefault(record["key"], record)
    records = list(deduped.values())
    pending = sum(1 for item in records if item["status"] == "pending")
    restored = sum(1 for item in records if item["status"] == "restored")

    budget_runs = [local_budget_reset_run(row) for row in reset_rows]
    budget_runs = sorted(budget_runs, key=lambda item: item.get("startedAt") or "", reverse=True)

    return {
        "ok": True,
        "source": "local-operation-board",
        "date": day,
        "range": {"startUtc": start_utc, "endUtc": end_utc},
        "autoPause": {
            "total": len(records),
            "pending": pending,
            "restored": restored,
            "records": records,
        },
        "budgetReset": {
            "runs": budget_runs,
            "latest": aggregate_budget_reset_runs(day, budget_runs),
        },
    }


def local_dashboard_from_plans(plans, users=None):
    spend = sum(number(plan.get("spend")) for plan in plans)
    gmv = sum(number(plan.get("gmv")) for plan in plans)
    prefix_rows = {}
    for plan in plans:
        prefix = normalize_plan_prefix(plan.get("ownerPrefix")) or "-"
        row = prefix_rows.setdefault(
            prefix,
            {
                "username": prefix,
                "displayName": plan.get("ownerName") or plan_prefix_label(prefix),
                "role": "operator",
                "planPrefixes": [prefix] if prefix != "-" else [],
                "spend": 0,
                "gmv": 0,
                "orders": 0,
                "planCount": 0,
            },
        )
        row["spend"] += number(plan.get("spend"))
        row["gmv"] += number(plan.get("gmv"))
        row["orders"] += int(number(plan.get("orders")))
        row["planCount"] += 1
    user_rows = []
    for row in prefix_rows.values():
        row["roi"] = row["gmv"] / row["spend"] if row["spend"] > 0 else 0
        user_rows.append(row)
    visible_users = [user for user in users if isinstance(user, dict) and user.get("role") != "admin"] if isinstance(users, list) else []
    return {
        "ok": True,
        "scope": "local-startup",
        "global": {
            "shopCount": len({plan.get("shopId") for plan in plans if plan.get("shopId")}),
            "planCount": len(plans),
            "spend": spend,
            "gmv": gmv,
            "roi": gmv / spend if spend > 0 else 0,
            "orders": sum(int(number(plan.get("orders"))) for plan in plans),
        },
        "plans": plans[:50],
        "users": visible_users if visible_users else sorted(user_rows, key=lambda row: row.get("spend", 0), reverse=True),
    }


def local_startup_snapshot(headers):
    me_data = cached_response_data("/api/me", headers)
    if not me_data or not isinstance(me_data.get("user"), dict):
        return {"ok": False, "error": "local startup snapshot requires cached user"}
    options = local_plan_prefix_options(me_data)
    cached_plans = cached_response_data("/api/qianchuan/plans?page=1&page_size=500", headers)
    raw_plans = cached_plans.get("plans") if isinstance(cached_plans, dict) and isinstance(cached_plans.get("plans"), list) else []
    cached_total = page_total(cached_plans.get("page_info")) if isinstance(cached_plans, dict) else 0
    snapshot_plans = latest_plan_snapshot_payloads(limit=max(2000, cached_total or len(raw_plans)))
    if snapshot_plans and (not raw_plans or len(snapshot_plans) > len(raw_plans) or (cached_total and len(raw_plans) < cached_total)):
        raw_plans = snapshot_plans
    plans = [normalize_local_plan(plan, options) for plan in raw_plans if isinstance(plan, dict)]
    plans = filter_plans_for_user(plans, me_data.get("user") or {})
    plans = sorted(plans, key=lambda plan: number(plan.get("spend")), reverse=True)
    cached_dashboard = cached_response_data("/api/qianchuan/dashboard", headers)
    users_data = cached_response_data("/api/admin/users", headers)
    cached_global = cached_dashboard.get("global") if isinstance(cached_dashboard, dict) else None
    cached_has_data = bool(
        isinstance(cached_global, dict)
        and (
            number(cached_global.get("spend")) > 0
            or number(cached_global.get("gmv")) > 0
            or int(number(cached_global.get("planCount"))) > 0
            or int(number(cached_global.get("totalPlans"))) > 0
        )
    )
    dashboard = cached_dashboard if cached_has_data or not plans else local_dashboard_from_plans(plans, (users_data or {}).get("users"))
    dashboard = dict(dashboard)
    if isinstance(dashboard.get("users"), list):
        dashboard["users"] = [user for user in dashboard["users"] if isinstance(user, dict) and user.get("role") != "admin"]
    if not isinstance(dashboard.get("plans"), list) or not dashboard.get("plans"):
        dashboard["plans"] = plans[:50]
    rules = cached_response_data("/api/qianchuan/rules", headers) or {}
    groups = cached_response_data("/api/rule-groups", headers) or {}
    operation_board = local_operation_board_summary(headers, {"date": [beijing_today_text()]})
    logs = cached_response_data("/api/qianchuan/logs", headers) or {}
    return {
        "ok": True,
        "source": "local-startup-snapshot",
        "_cache": {"source": "local-startup-snapshot", "stale": True, "refreshing": False},
        "user": me_data.get("user"),
        "shops": me_data.get("shops") or [],
        "planPrefixOptions": options,
        "dashboard": dashboard,
        "plans": plans[:2000],
        "page_info": {"total": len(plans)},
        "rules": rules.get("rules") or [],
        "groups": groups.get("groups") or [],
        "operationBoard": operation_board if isinstance(operation_board, dict) else {},
        "users": (users_data or {}).get("users") or [],
        "logs": logs.get("logs") or [],
    }


def latest_daily_report_ids(days, marketing_goal, smart_bid_types=None):
    if not days:
        return {}
    placeholders = ",".join("?" for _ in days)
    smart_bid_key = ",".join(normalize_plan_smart_bid_types(smart_bid_types, default=PLAN_SMART_BID_TYPES))
    legacy_smart_bid_key = ",".join(CONTROL_PLAN_SMART_BID_TYPES)
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            select date(start_time) as day, max(id) as report_id
            from report_runs
            where marketing_goal = ?
              and coalesce(plan_smart_bid_types, ?) = ?
              and date(start_time) = date(end_time)
              and substr(start_time, 12, 8) = '00:00:00'
              and substr(end_time, 12, 8) = '23:59:59'
              and date(start_time) in ({placeholders})
            group by date(start_time)
            """,
            (marketing_goal, legacy_smart_bid_key, smart_bid_key, *days),
        ).fetchall()
    return {row["day"]: int(row["report_id"]) for row in rows}


def build_local_report_from_daily(headers, query):
    start_time, end_time = report_time_range(query)
    marketing_goal = query_value(query, "marketing_goal", "VIDEO_PROM_GOODS")
    smart_bid_types = query_plan_smart_bid_types(query, default=PLAN_SMART_BID_TYPES)
    days = report_dates_between(start_time, end_time)
    if not days:
        return None
    scope = cached_report_scope(headers)
    if not scope:
        return None
    allowed_shop_ids = scope.get("shopIds") or set()
    allowed_prefixes = set(scope.get("planPrefixes") or [])
    is_admin = bool(scope.get("isAdmin"))
    daily_ids = latest_daily_report_ids(days, marketing_goal, smart_bid_types)
    if len(daily_ids) != len(days):
        return None
    report_ids = [daily_ids[day] for day in days]
    placeholders = ",".join("?" for _ in report_ids)
    shop_meta = {}
    plans = {}
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        shop_rows = conn.execute(
            f"""
            select *
            from report_shop_rows
            where report_id in ({placeholders})
            order by report_id, shop_id
            """,
            report_ids,
        ).fetchall()
        plan_rows = conn.execute(
            f"""
            select *
            from report_plan_rows
            where report_id in ({placeholders})
            order by report_id, shop_id, plan_id
            """,
            report_ids,
        ).fetchall()
    for row in shop_rows:
        shop_id = row["shop_id"]
        if shop_id is None or int(shop_id) not in allowed_shop_ids:
            continue
        meta = shop_meta.setdefault(
            int(shop_id),
            {"shopId": int(shop_id), "advertiserId": row["advertiser_id"], "shopName": row["shop_name"] or ""},
        )
        meta["advertiserId"] = row["advertiser_id"] or meta["advertiserId"]
        meta["shopName"] = row["shop_name"] or meta["shopName"]
    for row in plan_rows:
        shop_id = row["shop_id"]
        plan_id = row["plan_id"]
        if shop_id is None or plan_id is None or int(shop_id) not in allowed_shop_ids:
            continue
        key = (int(shop_id), int(plan_id))
        payload = {}
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        payload = annotate_report_plan_owner(
            {
                **payload,
                "id": int(plan_id),
                "shopId": int(shop_id),
                "advertiserId": row["advertiser_id"],
                "shopName": shop_meta.get(int(shop_id), {}).get("shopName", payload.get("shopName") or ""),
                "name": row["plan_name"] or payload.get("name") or str(plan_id),
                "optStatus": row["opt_status"] or payload.get("optStatus"),
                "status": row["status"] or payload.get("status"),
                "smartBidType": row["smart_bid_type"] or payload.get("smartBidType"),
            }
        )
        if not is_admin and normalize_plan_prefix(payload.get("ownerPrefix")) not in allowed_prefixes:
            continue
        item = plans.setdefault(
            key,
            {
                **payload,
                "id": int(plan_id),
                "shopId": int(shop_id),
                "advertiserId": row["advertiser_id"],
                "shopName": shop_meta.get(int(shop_id), {}).get("shopName", payload.get("shopName") or ""),
                "name": row["plan_name"] or payload.get("name") or str(plan_id),
                "optStatus": row["opt_status"] or payload.get("optStatus"),
                "status": row["status"] or payload.get("status"),
                "smartBidType": row["smart_bid_type"] or payload.get("smartBidType"),
                "spend": 0,
                "gmv": 0,
                "orders": 0,
                "budget": 0,
                "payGmv": 0,
                "payRoi": 0,
                "settleGmv": 0,
                "settleRoi": 0,
                "realSettleGmv": 0,
                "refundGmv": 0,
                "refundOrders": 0,
            },
        )
        item["name"] = row["plan_name"] or item.get("name") or str(plan_id)
        item["optStatus"] = row["opt_status"] or item.get("optStatus")
        item["status"] = row["status"] or item.get("status")
        item["ownerPrefix"] = normalize_plan_prefix(item.get("ownerPrefix")) or plan_prefix_for_name(item.get("name"))
        item["ownerName"] = item.get("ownerName") or PLAN_PREFIX_OWNERS.get(item.get("ownerPrefix"), "未分配")
        item["budget"] = number(row["budget"], item.get("budget") or 0)
        item["spend"] += number(row["spend"])
        item["gmv"] += number(row["gmv"])
        item["orders"] += int(number(row["orders"]))
        item["payGmv"] += number(row["pay_gmv"])
        item["settleGmv"] += number(row["settle_gmv"])
        item["realSettleGmv"] += number(row["real_settle_gmv"])
        item["refundGmv"] += number(row["refund_gmv"])
        item["refundOrders"] += int(number(row["refund_orders"]))
    shops = {}
    for item in plans.values():
        shop_id = int(number(item.get("shopId")))
        if not shop_id:
            continue
        shop = shops.setdefault(
            shop_id,
            {
                "shopId": shop_id,
                "advertiserId": item.get("advertiserId") or shop_meta.get(shop_id, {}).get("advertiserId"),
                "shopName": item.get("shopName") or shop_meta.get(shop_id, {}).get("shopName", ""),
                "spend": 0,
                "gmv": 0,
                "orders": 0,
                "payGmv": 0,
                "payRoi": 0,
                "settleGmv": 0,
                "settleRoi": 0,
                "realSettleGmv": 0,
                "refundGmv": 0,
                "refundOrders": 0,
                "planIds": set(),
            },
        )
        shop["advertiserId"] = item.get("advertiserId") or shop["advertiserId"]
        shop["shopName"] = item.get("shopName") or shop["shopName"]
        shop["spend"] += number(item.get("spend"))
        shop["gmv"] += number(item.get("gmv"))
        shop["orders"] += int(number(item.get("orders")))
        shop["payGmv"] += number(item.get("payGmv"))
        shop["settleGmv"] += number(item.get("settleGmv"))
        shop["realSettleGmv"] += number(item.get("realSettleGmv"))
        shop["refundGmv"] += number(item.get("refundGmv"))
        shop["refundOrders"] += int(number(item.get("refundOrders")))
        shop["planIds"].add(int(number(item.get("id"))))
    shop_list = []
    for item in shops.values():
        item["roi"] = item["gmv"] / item["spend"] if item["spend"] > 0 else 0
        item["payRoi"] = item["payGmv"] / item["spend"] if item["spend"] > 0 else 0
        item["settleRoi"] = item["settleGmv"] / item["spend"] if item["spend"] > 0 else 0
        item["planCount"] = len(item.pop("planIds"))
        item["totalPlans"] = item["planCount"]
        shop_list.append(item)
    plan_list = []
    for item in plans.values():
        item["roi"] = item["gmv"] / item["spend"] if item["spend"] > 0 else 0
        item["payRoi"] = item["payGmv"] / item["spend"] if item["spend"] > 0 else 0
        item["settleRoi"] = item["settleGmv"] / item["spend"] if item["spend"] > 0 else 0
        plan_list.append(item)
    spend = sum(number(shop.get("spend")) for shop in shop_list)
    gmv = sum(number(shop.get("gmv")) for shop in shop_list)
    pay_gmv = sum(number(shop.get("payGmv")) for shop in shop_list)
    settle_gmv = sum(number(shop.get("settleGmv")) for shop in shop_list)
    real_settle_gmv = sum(number(shop.get("realSettleGmv")) for shop in shop_list)
    refund_gmv = sum(number(shop.get("refundGmv")) for shop in shop_list)
    return {
        "ok": True,
        "scope": "local-daily",
        "global": {
            "shopCount": len(shop_list),
            "planCount": len(plan_list),
            "spend": spend,
            "gmv": gmv,
            "roi": gmv / spend if spend > 0 else 0,
            "payGmv": pay_gmv,
            "payRoi": pay_gmv / spend if spend > 0 else 0,
            "settleGmv": settle_gmv,
            "settleRoi": settle_gmv / spend if spend > 0 else 0,
            "realSettleGmv": real_settle_gmv,
            "refundGmv": refund_gmv,
            "refundOrders": sum(int(number(shop.get("refundOrders"))) for shop in shop_list),
            "orders": sum(int(number(shop.get("orders"))) for shop in shop_list),
        },
        "range": {"startTime": start_time, "endTime": end_time, "marketingGoal": marketing_goal, "planSmartBidTypes": smart_bid_types},
        "shops": sorted(shop_list, key=lambda item: item.get("shopId") or 0),
        "users": build_report_user_summaries(plan_list, scope),
        "planPrefixOptions": scope.get("planPrefixOptions") or [],
        "plans": sorted(plan_list, key=lambda item: (item.get("shopId") or 0, item.get("id") or 0)),
        "localDailyDays": days,
    }


def cloud_get_json(path, params, headers, journal_path, operator):
    url = f"{CLOUD_API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    status = 502
    data = {}
    error_text = ""
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=180) as resp:
            status = resp.status
            data = decode_json(resp.read())
    except urllib.error.HTTPError as exc:
        status = exc.code
        data = decode_json(exc.read())
    except Exception as exc:
        error_text = str(exc)
        data = {"error": "local report error", "message": error_text}
    ok = 200 <= int(status) < 300 and not error_text
    record_api("GET", journal_path, status, ok, operator, params, data, error_text)
    return status, data, error_text


def cloud_proxy_request(method, full_path, headers, raw_body=None, timeout=180):
    url = CLOUD_API_BASE + full_path
    data = raw_body if raw_body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    status = 502
    response_data = {}
    error_text = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            response_data = decode_json(resp.read())
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_data = decode_json(exc.read())
    except Exception as exc:
        error_text = str(exc)
        response_data = {"error": "local proxy error", "message": error_text}
    return status, response_data, error_text


def system_scheduler_headers(token=None):
    token = token if token is not None else load_local_token()
    return {"X-QC-Admin-Token": token} if token else {}


def proxy_system_action(path, payload, token=None, operator="system-scheduler", timeout=180, notify=True):
    payload = payload if isinstance(payload, dict) else {}
    headers = system_scheduler_headers(token)
    if not headers.get("X-QC-Admin-Token"):
        response_data = {"ok": False, "error": "QIANCHUAN_CONTROL_TOKEN is required"}
        record_api("POST", f"{path}#system-scheduler", 503, False, operator, payload, response_data, response_data["error"])
        record_operation("POST", path, operator, payload, response_data, False)
        return response_data

    raw_body = encode_json(payload).encode("utf-8")
    status, response_data, error_text = cloud_proxy_request("POST", path, headers, raw_body, timeout=timeout)
    ok = 200 <= int(status) < 300 and not error_text
    operation_ok = bool(response_data.get("ok", ok)) if isinstance(response_data, dict) else ok
    record_api("POST", path, status, ok, operator, payload, response_data, error_text)
    record_operation("POST", path, operator, payload, response_data, operation_ok)
    if ok:
        persist_response(path, response_data)
        if operation_ok:
            clear_response_cache()
            if notify and path in ACTION_LABELS:
                notify_operation(path, operator, payload, response_data)
    result = dict(response_data) if isinstance(response_data, dict) else {"response": response_data}
    if not isinstance(result, dict):
        result = {"response": result}
    result["ok"] = operation_ok
    result.setdefault("status", status)
    if error_text:
        result.setdefault("error", error_text)
    return result


def send_system_scheduler_report(stage, title, lines, payload=None):
    payload = payload if isinstance(payload, dict) else {}
    stage_text = "开始" if stage == "start" else "结束"
    message_lines = [
        f"### 千川自动调整{stage_text}报告",
        f"> 任务：{title}",
        f"> 操作人：system-scheduler",
        f"> 时间：{beijing_now_text()}",
    ]
    message_lines.extend(lines or [])
    message = "\n".join(str(line) for line in message_lines if str(line) != "")
    result = send_wecom_message(message, "markdown")
    record_api(
        "POST",
        "/api/local/notifications/wecom#system-scheduler",
        200 if result.get("ok") or result.get("skipped") else 502,
        result.get("ok", False),
        "system-scheduler",
        {"stage": stage, "title": title, "message": message, **payload},
        result,
    )
    return result


def budget_target_lines():
    labels = {
        "SMART_BID_CUSTOM": "控成本",
        "SMART_BID_CONSERVATIVE": "放量",
    }
    return [f"> {labels.get(smart_bid_type, smart_bid_type)}：{budget}" for smart_bid_type, budget in system_budget_reset_targets()]


def send_budget_reset_start_report():
    return send_system_scheduler_report(
        "start",
        "0点预算归位",
        [
            "> 调整目标：",
            *budget_target_lines(),
        ],
        {"budgetTargets": dict(system_budget_reset_targets())},
    )


def send_budget_reset_finish_report(result):
    result = result if isinstance(result, dict) else {}
    status_text = "成功" if result.get("ok") else "失败"
    lines = [
        f"> 结果：{status_text}",
        f"> 覆盖计划：{int(number(result.get('totalPlans'), 0))}",
        f"> 调整计划：{int(number(result.get('updateCount'), 0))}",
        f"> 跳过计划：{int(number(result.get('skippedCount'), 0))}",
        f"> 缺失计划：{int(number(result.get('missingCount'), 0))}",
        f"> 请求批次：{int(number(result.get('chunkCount'), 0))}",
        "> 调整目标：",
        *budget_target_lines(),
    ]
    errors = result.get("errors") if isinstance(result.get("errors"), list) else []
    if errors:
        lines.append(f"> 错误：{'；'.join(str(item) for item in errors if item)}")
    return send_system_scheduler_report("finish", "0点预算归位", lines, {"summary": result})


def run_system_step_roi_rules(token=None):
    payload = {
        "marketing_goal": "VIDEO_PROM_GOODS",
        "page": 1,
        "page_size": 500,
        "ruleActions": AUTO_RULE_ACTIONS,
        "source": "system-step-roi-rules",
    }
    return proxy_system_action("/api/qianchuan/actions/run-rules", payload, token=token, operator="system-scheduler", timeout=180)


def in_budget_reset_window(now=None):
    current = as_beijing_datetime(now)
    start = current.replace(
        hour=SYSTEM_BUDGET_RESET_HOUR,
        minute=SYSTEM_BUDGET_RESET_MINUTE,
        second=0,
        microsecond=0,
    )
    end = start + dt.timedelta(minutes=max(1, SYSTEM_BUDGET_RESET_WINDOW_MINUTES))
    return start <= current < end


def normalized_budget_value(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def system_budget_reset_targets():
    return [
        ("SMART_BID_CUSTOM", normalized_budget_value(SYSTEM_BUDGET_RESET_CONTROL_BUDGET)),
        ("SMART_BID_CONSERVATIVE", normalized_budget_value(SYSTEM_BUDGET_RESET_VOLUME_BUDGET)),
    ]


def merge_budget_reset_results(runs):
    runs = runs if isinstance(runs, list) else []
    ok = bool(runs) and all(bool(item.get("ok")) for item in runs)
    totals = {
        "totalPlans": 0,
        "updateCount": 0,
        "skippedCount": 0,
        "missingCount": 0,
        "chunkCount": 0,
    }
    for item in runs:
        for key in totals:
            totals[key] += int(number(item.get(key), 0))
    budget_targets = {}
    for item in runs:
        smart_bid_types = normalize_plan_smart_bid_types(item.get("planSmartBidTypes"), default=[])
        target_budget = item.get("targetBudget")
        for smart_bid_type in smart_bid_types:
            budget_targets[smart_bid_type] = target_budget
    errors = [item.get("error") or item.get("message") for item in runs if item.get("error") or item.get("message")]
    return {
        "ok": ok,
        "source": "system-midnight-budget-reset",
        "budgetTargets": budget_targets,
        "runs": runs,
        "errors": errors,
        **totals,
    }


def run_system_budget_reset(token=None):
    send_budget_reset_start_report()
    runs = []
    for smart_bid_type, target_budget in system_budget_reset_targets():
        payload = {
            "budget": target_budget,
            "marketing_goal": "VIDEO_PROM_GOODS",
            "planSmartBidTypes": [smart_bid_type],
            "batchSize": max(1, min(10, SYSTEM_BUDGET_RESET_BATCH_SIZE)),
            "batchSleepSeconds": max(0, SYSTEM_BUDGET_RESET_BATCH_SLEEP_SECONDS),
            "source": "system-midnight-budget-reset",
            "dryRun": False,
        }
        runs.append(
            proxy_system_action(
                "/api/qianchuan/actions/reset-budgets",
                payload,
                token=token,
                operator="system-scheduler",
                timeout=180,
                notify=False,
            )
        )
    result = merge_budget_reset_results(runs)
    send_budget_reset_finish_report(result)
    return result


def run_due_system_budget_reset(token=None, now=None):
    current = as_beijing_datetime(now)
    date_key = current.strftime("%Y-%m-%d")
    if not in_budget_reset_window(current):
        return {"ok": True, "ran": False, "reason": "outside-window", "date": date_key}
    if get_setting(SYSTEM_BUDGET_RESET_LAST_DATE_KEY, "") == date_key:
        return {"ok": True, "ran": False, "reason": "already-ran", "date": date_key}
    result = run_system_budget_reset(token=token)
    if result.get("ok"):
        set_setting(SYSTEM_BUDGET_RESET_LAST_DATE_KEY, date_key)
    return {"ok": bool(result.get("ok")), "ran": True, "date": date_key, "result": result}


def record_system_scheduler_error(stage, exc):
    response_data = {"ok": False, "error": str(exc), "stage": stage}
    try:
        record_api("POST", "/api/local/system-scheduler#error", 502, False, "system-scheduler", {"stage": stage}, response_data, str(exc))
    except Exception as log_exc:
        print(f"qianchuan system scheduler error log failed: {log_exc}", flush=True)


def start_system_action_scheduler():
    if not SYSTEM_SCHEDULER_ENABLED:
        print("qianchuan system action scheduler disabled", flush=True)
        return False
    token = load_local_token()
    if not token:
        record_api(
            "POST",
            "/api/local/system-scheduler#startup",
            503,
            False,
            "system-scheduler",
            {},
            {"ok": False, "error": "QIANCHUAN_CONTROL_TOKEN is required"},
            "QIANCHUAN_CONTROL_TOKEN is required",
        )
        print("qianchuan system action scheduler missing QIANCHUAN_CONTROL_TOKEN", flush=True)
        return False

    def worker():
        time.sleep(max(0, SYSTEM_SCHEDULER_START_DELAY_SECONDS))
        next_step_roi_at = 0
        while True:
            now_ts = time.time()
            try:
                if now_ts >= next_step_roi_at:
                    run_system_step_roi_rules(token=token)
                    next_step_roi_at = now_ts + max(60, SYSTEM_STEP_ROI_INTERVAL_SECONDS)
            except Exception as exc:
                record_system_scheduler_error("step-roi-rules", exc)
                next_step_roi_at = now_ts + max(60, SYSTEM_STEP_ROI_INTERVAL_SECONDS)
            try:
                run_due_system_budget_reset(token=token)
            except Exception as exc:
                record_system_scheduler_error("budget-reset", exc)
            time.sleep(max(5, SYSTEM_SCHEDULER_TICK_SECONDS))

    threading.Thread(target=worker, daemon=True).start()
    print("qianchuan system action scheduler started", flush=True)
    return True


def refresh_lock_key(kind, key):
    return f"{kind}:{key}"


def start_refresh_once(kind, key, target, args):
    lock_key = refresh_lock_key(kind, key)
    with REFRESH_LOCK:
        if lock_key in REFRESH_INFLIGHT:
            return False
        REFRESH_INFLIGHT.add(lock_key)

    def runner():
        try:
            target(*args)
        finally:
            with REFRESH_LOCK:
                REFRESH_INFLIGHT.discard(lock_key)

    threading.Thread(target=runner, daemon=True).start()
    return True


def refresh_cached_get(full_path, headers, path, operator):
    parsed = urllib.parse.urlparse(full_path)
    params = urllib.parse.parse_qs(parsed.query)
    status, response_data, error_text = cloud_proxy_request("GET", full_path, headers)
    ok = 200 <= int(status) < 300 and not error_text
    record_api("GET", f"{path}#refresh", status, ok, operator, params, response_data, error_text)
    if not ok:
        return
    persist_response(path, response_data)
    set_cached_response("GET", full_path, headers, status, response_data)
    if path == "/api/qianchuan/dashboard":
        mirror_dashboard_plan_pages(dict(headers), response_data)


def schedule_cached_get_refresh(full_path, headers, path, operator):
    key = cache_key_for("GET", full_path, headers)
    return start_refresh_once("api", key, refresh_cached_get, (full_path, dict(headers), path, operator))


def refresh_report_cache(headers, query):
    status, report, error_text = build_report(headers, query)
    ok = 200 <= int(status) < 300 and not error_text
    if ok:
        set_report_response_cache(headers, query, status, report)
    record_api("GET", "/api/local/reports/qianchuan#refresh", status, ok, operator_from_headers(headers), query, report, error_text)


def schedule_report_refresh(headers, query):
    key, _, _, _, _ = report_cache_key(headers, query)
    return start_refresh_once("report", key, refresh_report_cache, (dict(headers), dict(query)))


CORE_SYNC_PATHS = [
    "/api/me",
    "/api/qianchuan/bootstrap",
    "/api/qianchuan/dashboard",
    "/api/qianchuan/plans?page=1&page_size=500",
    "/api/qianchuan/rules",
    "/api/rule-groups",
    "/api/qianchuan/operation-board",
    "/api/qianchuan/logs",
    "/api/admin/users",
]


def sync_core_cache(headers, operator="local-sync"):
    results = []
    ok_count = 0
    for full_path in CORE_SYNC_PATHS:
        parsed = urllib.parse.urlparse(full_path)
        params = urllib.parse.parse_qs(parsed.query)
        status, response_data, error_text = cloud_proxy_request("GET", full_path, headers)
        ok = 200 <= int(status) < 300 and not error_text
        record_api("GET", f"{parsed.path}#sync", status, ok, operator, params, response_data, error_text)
        results.append(
            {
                "path": full_path,
                "status": status,
                "ok": ok,
                "error": error_text or (response_data.get("error") if isinstance(response_data, dict) else ""),
            }
        )
        if not ok:
            continue
        ok_count += 1
        persist_response(parsed.path, response_data)
        set_cached_response("GET", full_path, headers, status, response_data)
        if parsed.path == "/api/qianchuan/dashboard":
            mirror_dashboard_plan_pages(dict(headers), response_data)
    return {
        "ok": ok_count > 0,
        "source": "cloud-sync",
        "syncedAt": utc_now(),
        "successCount": ok_count,
        "totalCount": len(CORE_SYNC_PATHS),
        "results": results,
    }


def start_periodic_cloud_sync():
    token = load_local_token()
    if not token or AUTO_SYNC_INTERVAL_SECONDS <= 0:
        return False

    def worker():
        time.sleep(10)
        while True:
            try:
                sync_core_cache({"X-QC-Admin-Token": token}, operator="scheduled-sync")
            except Exception as exc:
                record_api(
                    "GET",
                    "/api/local/sync-now#scheduled",
                    502,
                    False,
                    "scheduled-sync",
                    {},
                    {"error": "scheduled sync failed", "message": str(exc)},
                    str(exc),
                )
            time.sleep(AUTO_SYNC_INTERVAL_SECONDS)

    threading.Thread(target=worker, daemon=True).start()
    return True


def fetch_all_plan_pages(headers, shop, start_time, end_time, marketing_goal, smart_bid_types=None, journal_suffix="report"):
    smart_bid_types = normalize_plan_smart_bid_types(smart_bid_types, default=PLAN_SMART_BID_TYPES)
    all_plans = []
    total = 0
    last_status = 200
    last_error = ""
    for page in range(1, 21):
        params = {
            "shop_id": shop.get("shopId"),
            "marketing_goal": marketing_goal,
            "plan_smart_bid_types": ",".join(smart_bid_types),
            "page": page,
            "page_size": 100,
            "start_time": start_time,
            "end_time": end_time,
        }
        status, data, error_text = cloud_get_json(
            "/api/qianchuan/plans",
            params,
            headers,
            f"/api/qianchuan/plans#{journal_suffix}",
            "local-report",
        )
        last_status = status
        last_error = error_text
        if not (200 <= int(status) < 300) or not isinstance(data, dict) or data.get("code") != 0:
            break
        persist_response("/api/qianchuan/plans", data)
        batch = data.get("plans") or []
        all_plans.extend(batch)
        total = total or page_total(data.get("page_info"))
        if not batch or (total and len(all_plans) >= total):
            break
    return all_plans, total or len(all_plans), last_status, last_error


def persist_report(report):
    ensure_db()
    summary = report.get("global") or {}
    ranges = report.get("range") or {}
    smart_bid_types = normalize_plan_smart_bid_types(ranges.get("planSmartBidTypes"), default=PLAN_SMART_BID_TYPES)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            insert into report_runs(
                created_at, scope, start_time, end_time, marketing_goal, shop_count,
                plan_count, spend, gmv, roi, pay_gmv, pay_roi, settle_gmv, settle_roi,
                real_settle_gmv, refund_gmv, refund_orders, plan_smart_bid_types, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                report.get("scope"),
                ranges.get("startTime") or "",
                ranges.get("endTime") or "",
                ranges.get("marketingGoal") or "",
                summary.get("shopCount"),
                summary.get("planCount"),
                number(summary.get("spend")),
                number(summary.get("gmv")),
                number(summary.get("roi")),
                *metric_values(summary),
                ",".join(smart_bid_types),
                encode_json(redact(report)),
            ),
        )
        report_id = cur.lastrowid
        for shop in report.get("shops") or []:
            if not isinstance(shop, dict):
                continue
            conn.execute(
                """
                insert into report_shop_rows(
                    report_id, shop_id, advertiser_id, shop_name, spend, gmv, roi,
                    orders, plan_count, pay_gmv, pay_roi, settle_gmv, settle_roi,
                    real_settle_gmv, refund_gmv, refund_orders, payload_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    shop.get("shopId"),
                    shop.get("advertiserId"),
                    shop.get("shopName"),
                    number(shop.get("spend")),
                    number(shop.get("gmv")),
                    number(shop.get("roi")),
                    int(number(shop.get("orders"))),
                    int(number(shop.get("planCount"))),
                    *metric_values(shop),
                    encode_json(redact(shop)),
                ),
            )
            for plan in shop.get("plans") or []:
                if not isinstance(plan, dict):
                    continue
                conn.execute(
                    """
                    insert into report_plan_rows(
                        report_id, shop_id, advertiser_id, plan_id, plan_name,
                        opt_status, status, spend, gmv, roi, orders, budget,
                        pay_gmv, pay_roi, settle_gmv, settle_roi, real_settle_gmv,
                        refund_gmv, refund_orders, roi_metric_json, smart_bid_type, payload_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        shop.get("shopId"),
                        shop.get("advertiserId"),
                        plan.get("id"),
                        plan.get("name"),
                        plan.get("optStatus"),
                        plan.get("status"),
                        number(plan.get("spend")),
                        number(plan.get("gmv")),
                        number(plan.get("roi")),
                        int(number(plan.get("orders"))),
                        number(plan.get("budget")),
                        *metric_values(plan, include_roi_metric=True),
                        plan_smart_bid_type(plan),
                        encode_json(redact(plan)),
                    ),
                )
    return report_id


def build_report(headers, query):
    start_time, end_time = report_time_range(query)
    marketing_goal = query_value(query, "marketing_goal", "VIDEO_PROM_GOODS")
    smart_bid_types = query_plan_smart_bid_types(query, default=PLAN_SMART_BID_TYPES)
    dashboard_params = {
        "start_time": start_time,
        "end_time": end_time,
        "marketing_goal": marketing_goal,
        "plan_smart_bid_types": ",".join(smart_bid_types),
    }
    status, dashboard, error_text = cloud_get_json(
        "/api/qianchuan/dashboard",
        dashboard_params,
        headers,
        "/api/qianchuan/dashboard#report",
        "local-report",
    )
    if not (200 <= int(status) < 300) or not isinstance(dashboard, dict):
        return status, dashboard, error_text
    persist_response("/api/qianchuan/dashboard", dashboard)
    shops = []
    all_plans = []
    if isinstance(dashboard.get("plans"), list):
        all_plans = [dict(plan) for plan in dashboard.get("plans") if isinstance(plan, dict)]
        for shop in dashboard.get("shops") or []:
            if not isinstance(shop, dict):
                continue
            shop_id = int(number(shop.get("shopId")))
            shop_copy = dict(shop)
            shop_copy["plans"] = [plan for plan in all_plans if int(number(plan.get("shopId"))) == shop_id]
            shop_copy["totalPlans"] = shop.get("totalPlans") or len(shop_copy["plans"])
            shop_copy["planCount"] = len(shop_copy["plans"])
            shops.append(shop_copy)
    else:
        for shop in dashboard.get("shops") or []:
            if not isinstance(shop, dict):
                continue
            plans, total, _, _ = fetch_all_plan_pages(headers, shop, start_time, end_time, marketing_goal, smart_bid_types, journal_suffix="report")
            annotated_plans = []
            for plan in plans:
                if not isinstance(plan, dict):
                    continue
                item = dict(plan)
                item["shopId"] = shop.get("shopId")
                item["shopName"] = shop.get("shopName")
                item["advertiserId"] = shop.get("advertiserId")
                annotated_plans.append(item)
            shop_copy = dict(shop)
            shop_copy["plans"] = annotated_plans
            shop_copy["totalPlans"] = total
            shop_copy["planCount"] = len(annotated_plans)
            shops.append(shop_copy)
            all_plans.extend(annotated_plans)
    report = {
        **dashboard,
        "range": {"startTime": start_time, "endTime": end_time, "marketingGoal": marketing_goal, "planSmartBidTypes": smart_bid_types},
        "shops": shops,
        "plans": all_plans,
    }
    report["reportId"] = persist_report(report)
    return 200, report, ""


def mirror_dashboard_plan_pages(headers, dashboard_data):
    if not isinstance(dashboard_data, dict):
        return
    ranges = dashboard_data.get("range") or {}
    marketing_goal = ranges.get("marketingGoal") or "VIDEO_PROM_GOODS"
    smart_bid_types = normalize_plan_smart_bid_types(ranges.get("planSmartBidTypes"), default=PLAN_SMART_BID_TYPES)
    start_time = ranges.get("startTime")
    end_time = ranges.get("endTime")
    mirrored_plans = {}
    all_ok = True
    for shop in dashboard_data.get("shops") or []:
        if not isinstance(shop, dict) or not shop.get("shopId"):
            continue
        collected = 0
        total = 0
        for page in range(1, 21):
            params = {
                "shop_id": shop.get("shopId"),
                "marketing_goal": marketing_goal,
                "plan_smart_bid_types": ",".join(smart_bid_types),
                "page": page,
                "page_size": MIRROR_PLAN_PAGE_SIZE,
            }
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time
            query = urllib.parse.urlencode(params)
            url = f"{CLOUD_API_BASE}/api/qianchuan/plans?{query}"
            status = 502
            data = {}
            error_text = ""
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=180) as resp:
                    status = resp.status
                    data = decode_json(resp.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                data = decode_json(exc.read())
            except Exception as exc:
                error_text = str(exc)
                data = {"error": "local mirror error", "message": error_text}
            ok = 200 <= int(status) < 300 and not error_text and isinstance(data, dict) and data.get("code") == 0
            record_api("GET", "/api/qianchuan/plans#mirror", status, ok, "local-mirror", params, data, error_text)
            if not ok:
                all_ok = False
                break
            batch = data.get("plans") or []
            for plan in batch:
                if not isinstance(plan, dict):
                    continue
                item = dict(plan)
                item.setdefault("shopId", shop.get("shopId"))
                item.setdefault("shopName", shop.get("shopName"))
                item.setdefault("advertiserId", shop.get("advertiserId"))
                plan_id = item.get("id")
                key = (shop.get("shopId"), plan_id) if plan_id is not None else (shop.get("shopId"), item.get("name"), len(mirrored_plans))
                mirrored_plans[key] = item
            collected += len(batch)
            total = total or page_total(data.get("page_info"))
            if not batch or (total and collected >= total):
                break
    if all_ok:
        persist_current_plan_snapshot(list(mirrored_plans.values()))


def local_summary():
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        tables = {}
        for table in (
            "api_journal",
            "operation_logs",
            "plan_snapshots",
            "shop_snapshots",
            "dashboard_snapshots",
            "remote_action_logs",
            "response_cache",
            "report_response_cache",
            "report_runs",
            "report_shop_rows",
            "report_plan_rows",
            "local_settings",
            "product_shutdown_notifications",
        ):
            tables[table] = conn.execute(f"select count(*) as c from {table}").fetchone()["c"]
        latest = conn.execute(
            "select created_at, method, path, status_code, ok from api_journal order by id desc limit 10"
        ).fetchall()
    return {
        "dbPath": str(DB_PATH),
        "tables": tables,
        "notifications": {"wecom": wecom_config_summary()},
        "latest": [dict(row) for row in latest],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "qianchuan-local-control/1.0"

    def send_bytes(self, status, data, content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-QC-Admin-Token, Authorization")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        self.send_bytes(status, encode_json(data).encode("utf-8"), "application/json; charset=utf-8")

    def do_OPTIONS(self):
        self.send_bytes(204, b"")

    def read_raw_body(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def forwarded_headers(self):
        headers = {"Content-Type": self.headers.get("Content-Type") or "application/json"}
        auth = self.headers.get("Authorization")
        admin = self.headers.get("X-QC-Admin-Token")
        if auth:
            headers["Authorization"] = auth
        elif admin:
            headers["X-QC-Admin-Token"] = admin
        return headers

    def request_has_login(self):
        return bool(self.headers.get("Authorization") or self.headers.get("X-QC-Admin-Token"))

    def require_login(self):
        if self.request_has_login():
            return True
        self.send_json(401, {"ok": False, "error": "login required"})
        return False

    def require_valid_cloud_login(self):
        headers = self.forwarded_headers()
        if "Authorization" not in headers and "X-QC-Admin-Token" not in headers:
            self.send_json(401, {"ok": False, "error": "login required"})
            return False
        try:
            req = urllib.request.Request(f"{CLOUD_API_BASE}/api/me", headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return 200 <= int(resp.status) < 300
        except urllib.error.HTTPError as exc:
            status = exc.code if exc.code in {401, 403} else 502
            self.send_json(status, {"ok": False, "error": "login validation failed"})
            return False
        except Exception as exc:
            self.send_json(502, {"ok": False, "error": "login validation failed", "message": str(exc)})
            return False

    def proxy(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        method = self.command
        if path == "/healthz":
            return self.send_bytes(200, b"qianchuan-local-control ok\n")
        if path == "/api/local/startup-snapshot":
            if method != "GET":
                return self.send_json(405, {"ok": False, "error": "method not allowed"})
            if not self.require_login():
                return
            headers = self.forwarded_headers()
            query = urllib.parse.parse_qs(parsed.query)
            snapshot = local_startup_snapshot(headers)
            ok = bool(snapshot.get("ok"))
            status = 200 if ok else 404
            error_text = "" if ok else snapshot.get("error", "")
            record_api(method, path, status, ok, operator_from_headers(headers), query, snapshot, error_text)
            return self.send_json(status, snapshot)
        if path == "/api/local/sync-now":
            if method != "POST":
                return self.send_json(405, {"ok": False, "error": "method not allowed"})
            if not self.require_valid_cloud_login():
                return
            headers = self.forwarded_headers()
            request_data = decode_json(self.read_raw_body())
            sync_result = sync_core_cache(headers, operator_from_headers(headers) or "manual-sync")
            snapshot = local_startup_snapshot(headers)
            response_data = {**snapshot, "sync": sync_result}
            status = 200 if sync_result.get("ok") and snapshot.get("ok") else 502
            record_operation(method, path, operator_from_headers(headers), request_data, response_data, status == 200)
            return self.send_json(status, response_data)
        if path == "/api/local/reports/qianchuan":
            if method != "GET":
                return self.send_json(405, {"ok": False, "error": "method not allowed"})
            if not self.require_login():
                return
            headers = self.forwarded_headers()
            query = urllib.parse.parse_qs(parsed.query)
            force_refresh = str(query_value(query, "force_refresh", query_value(query, "force", ""))).lower() in {"1", "true", "yes"}
            if not force_refresh:
                cached = get_report_response_cache(headers, query)
                if cached:
                    status, report, meta = cached
                    response_data = attach_cache_meta(report, meta)
                    record_api(method, path, status, True, operator_from_headers(headers), query, response_data, "report-cache-hit")
                    return self.send_json(status, response_data)
                local_report = build_local_report_from_daily(headers, query)
                if local_report:
                    set_report_response_cache(headers, query, 200, local_report)
                    response_data = attach_cache_meta(
                        local_report,
                        {"source": "local-daily-report", "stale": True, "refreshing": False},
                    )
                    record_api(method, path, 200, True, operator_from_headers(headers), query, response_data, "daily-report-cache-hit")
                    return self.send_json(200, response_data)
                response_data = {"ok": False, "error": "local report cache missing", "message": "本地还没有这个时间段的报表，请先手动更新或等待后台定时同步。"}
                record_api(method, path, 404, False, operator_from_headers(headers), query, response_data, "local-report-cache-miss")
                return self.send_json(404, response_data)
            if not self.require_valid_cloud_login():
                return
            status, report, error_text = build_report(headers, query)
            ok = 200 <= int(status) < 300 and not error_text
            if ok:
                set_report_response_cache(headers, query, status, report)
            record_api(method, path, status, ok, operator_from_headers(headers), query, report, error_text)
            return self.send_json(status, report)
        if path.startswith("/api/local/") and not self.require_valid_cloud_login():
            return
        if path == "/api/local/audit/summary":
            return self.send_json(200, local_summary())
        if path == "/api/local/notifications/wecom/config":
            if method == "GET":
                return self.send_json(200, {"ok": True, **wecom_config_summary()})
            if not is_loopback_address(self.client_address[0]):
                return self.send_json(403, {"ok": False, "error": "local notification config is loopback only"})
            raw_body = self.read_raw_body()
            request_data = decode_json(raw_body)
            status, response_data = save_wecom_config(request_data)
            ok = 200 <= int(status) < 300 and bool(response_data.get("ok"))
            record_api(method, path, status, ok, "local-config", request_data, response_data)
            record_operation(method, path, "local-config", request_data, response_data, ok)
            return self.send_json(status, response_data)
        if path == "/api/local/notifications/wecom/test":
            if method != "POST":
                return self.send_json(405, {"ok": False, "error": "method not allowed"})
            if not is_loopback_address(self.client_address[0]):
                return self.send_json(403, {"ok": False, "error": "local notification test is loopback only"})
            raw_body = self.read_raw_body()
            request_data = decode_json(raw_body)
            request_data = request_data if isinstance(request_data, dict) else {}
            message = request_data.get("message") or f"### 千川控制中心测试消息\n> 时间：{beijing_now_text()}\n> 来源：本地电脑"
            result = send_wecom_message(message, request_data.get("msgtype") or "markdown")
            status = 200 if result.get("ok") else 502
            response_data = {"ok": bool(result.get("ok")), "wecom": result, "config": wecom_config_summary()}
            record_api(method, path, status, response_data["ok"], "local-config", request_data, response_data)
            record_operation(method, path, "local-config", request_data, response_data, response_data["ok"])
            return self.send_json(status, response_data)
        if not path.startswith("/api/"):
            return self.send_bytes(404, b"not found\n")
        if path == "/api/auth/bootstrap" and not self.headers.get("X-QC-Admin-Token"):
            return self.send_json(403, {"ok": False, "error": "bootstrap requires admin token"})
        if path != "/api/auth/login" and not self.require_login():
            return

        if path == "/api/qianchuan/operation-board":
            if method != "GET":
                return self.send_json(405, {"ok": False, "error": "method not allowed"})
            headers = self.forwarded_headers()
            query = urllib.parse.parse_qs(parsed.query)
            response_data = local_operation_board_summary(headers, query)
            record_api(method, path, 200, True, operator_from_headers(headers), query, response_data, "local-operation-board")
            return self.send_json(200, response_data)

        raw_body = self.read_raw_body()
        request_data = decode_json(raw_body)
        url = CLOUD_API_BASE + self.path
        headers = self.forwarded_headers()
        operator = operator_from_headers(headers)
        if method == "GET":
            cached = get_cached_response(method, self.path, headers, allow_stale=True)
            if cached:
                status, response_data, meta = cached
                refreshing = False
                if meta.get("stale"):
                    try:
                        refreshing = schedule_cached_get_refresh(self.path, headers, path, operator) or True
                    except Exception as exc:
                        record_api(
                            method,
                            f"{path}#refresh-schedule",
                            502,
                            False,
                            operator,
                            urllib.parse.parse_qs(parsed.query),
                            {"error": "refresh schedule failed", "message": str(exc)},
                            str(exc),
                        )
                meta["refreshing"] = refreshing
                response_data = attach_cache_meta(response_data, meta)
                record_api(
                    method,
                    path,
                    status,
                    True,
                    operator,
                    urllib.parse.parse_qs(parsed.query),
                    response_data,
                    "cache-hit-stale" if meta.get("stale") else "cache-hit",
                )
                return self.send_json(status, response_data)
        status, response_data, error_text = cloud_proxy_request(method, self.path, headers, raw_body)

        ok = 200 <= int(status) < 300 and not error_text
        operation_ok = bool(response_data.get("ok", ok)) if isinstance(response_data, dict) else ok
        record_api(method, path, status, ok, operator, request_data, response_data, error_text)
        record_operation(method, path, operator, request_data, response_data, operation_ok)
        if ok:
            persist_response(path, response_data)
            set_cached_response(method, self.path, headers, status, response_data)
            if path == "/api/qianchuan/dashboard":
                threading.Thread(
                    target=mirror_dashboard_plan_pages,
                    args=(dict(headers), response_data),
                    daemon=True,
                ).start()
            if operation_ok and path in ACTION_LABELS:
                notify_operation(path, operator, request_data, response_data)
        if method != "GET" and operation_ok:
            clear_response_cache()
        return self.send_json(status, response_data)

    def do_GET(self):
        return self.proxy()

    def do_POST(self):
        return self.proxy()

    def log_message(self, fmt, *args):
        print(f"{utc_now()} {self.client_address[0]} {fmt % args}", flush=True)


def main():
    ensure_db()
    start_periodic_cloud_sync()
    start_system_action_scheduler()
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print(f"qianchuan-local-control listening on {BIND_HOST}:{BIND_PORT}", flush=True)
    print(f"local db: {DB_PATH}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        ensure_db()
        print(encode_json(local_summary()))
        raise SystemExit(0)
    main()
