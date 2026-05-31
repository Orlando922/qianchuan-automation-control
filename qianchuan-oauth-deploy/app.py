#!/usr/bin/env python3
import datetime as dt
import hmac
import hashlib
import html
import json
import os
import secrets
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


APP_ID = os.environ.get("OCEANENGINE_APP_ID", "0")
APP_SECRET = os.environ.get("OCEANENGINE_APP_SECRET", "")
REDIRECT_URI = os.environ.get(
    "OCEANENGINE_REDIRECT_URI",
    "http://YOUR_PUBLIC_HOST/api/oceanengine/oauth/callback",
)
STATE_SECRET = os.environ.get("OCEANENGINE_STATE_SECRET", "change-me")
ADMIN_TOKEN = os.environ.get("OCEANENGINE_ADMIN_TOKEN", "")
CONTROL_TOKEN = os.environ.get("QIANCHUAN_CONTROL_TOKEN", ADMIN_TOKEN)
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("QIANCHUAN_BOOTSTRAP_ADMIN_USERNAME", "admin")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("QIANCHUAN_BOOTSTRAP_ADMIN_PASSWORD", "replace-with-a-strong-password")
SESSION_DAYS = int(os.environ.get("QIANCHUAN_SESSION_DAYS", "14"))
DB_PATH = os.environ.get(
    "OCEANENGINE_DB_PATH",
    "/var/lib/qianchuan-oauth/qianchuan-oauth.sqlite3",
)
TOKEN_URL = "https://api.oceanengine.com/open_api/oauth2/access_token/"
REFRESH_URL = "https://api.oceanengine.com/open_api/oauth2/refresh_token/"
API_BASE = "https://api.oceanengine.com"
DEFAULT_ADVERTISER_ID = int(os.environ.get("QIANCHUAN_DEFAULT_ADVERTISER_ID", "11"))
DEFAULT_SHOP_ID = int(os.environ.get("QIANCHUAN_DEFAULT_SHOP_ID", "1"))
DEFAULT_SHOP_NAME = os.environ.get("QIANCHUAN_DEFAULT_SHOP_NAME", "Demo Shop")
CLOUD_SCHEDULER_ENABLED = os.environ.get("QIANCHUAN_CLOUD_SCHEDULER_ENABLED", "1").lower() not in {"0", "false", "no", "off"}
CLOUD_SCHEDULER_POLL_SECONDS = int(os.environ.get("QIANCHUAN_CLOUD_SCHEDULER_POLL_SECONDS", "60"))
CLOUD_BUDGET_RESET_TARGET = float(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_TARGET", "300"))
CLOUD_BUDGET_RESET_CONTROL_BUDGET = float(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_CONTROL_BUDGET", str(CLOUD_BUDGET_RESET_TARGET)))
CLOUD_BUDGET_RESET_VOLUME_BUDGET = float(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_VOLUME_BUDGET", "30"))
CLOUD_BUDGET_RESET_MIN_CHANGE_AMOUNT = float(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_MIN_CHANGE_AMOUNT", "100"))
CLOUD_BUDGET_RESET_WINDOW_MINUTES = int(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_WINDOW_MINUTES", "30"))
CLOUD_BUDGET_RESET_BATCH_SIZE = min(10, max(1, int(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_BATCH_SIZE", "10"))))
CLOUD_BUDGET_RESET_BATCH_SLEEP_SECONDS = float(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_BATCH_SLEEP_SECONDS", "0.5"))
CLOUD_BUDGET_RESET_MAX_RETRIES = max(1, int(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_MAX_RETRIES", "3")))
CLOUD_BUDGET_RESET_RETRY_SLEEP_SECONDS = float(os.environ.get("QIANCHUAN_CLOUD_BUDGET_RESET_RETRY_SLEEP_SECONDS", "3"))
CLOUD_STEP_ROI_INTERVAL_SECONDS = int(os.environ.get("QIANCHUAN_CLOUD_STEP_ROI_INTERVAL_SECONDS", "300"))
PLAN_PREFIX_OWNERS = {
    "SC": "Operator A",
    "CY": "Operator B",
    "ST": "Operator C",
}
PREFIX_OWNER_CACHE = {"expires_at": 0, "owners": {}}
PLAN_SMART_BID_TYPES = ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"]
CONTROL_PLAN_SMART_BID_TYPES = ["SMART_BID_CUSTOM"]
PLAN_SMART_BID_LABELS = {
    "SMART_BID_CUSTOM": "控成本",
    "SMART_BID_CONSERVATIVE": "放量",
}
PLAN_SMART_BID_ALIASES = {
    "CUSTOM": "SMART_BID_CUSTOM",
    "COST": "SMART_BID_CUSTOM",
    "COST_CONTROL": "SMART_BID_CUSTOM",
    "控成本": "SMART_BID_CUSTOM",
    "CONSERVATIVE": "SMART_BID_CONSERVATIVE",
    "VOLUME": "SMART_BID_CONSERVATIVE",
    "VOLUME_SCALE": "SMART_BID_CONSERVATIVE",
    "放量": "SMART_BID_CONSERVATIVE",
}
CONTROL_FIELDS = [
    "stat_cost",
    "stat_cost_for_overall_roi2",
    "shop_estimated_comission_cost",
    "total_pay_order_gmv_for_roi2",
    "total_pay_order_gmv_include_coupon_for_roi2",
    "total_pay_order_coupon_amount_for_roi2",
    "total_pay_order_count_for_roi2",
    "total_cost_per_pay_order_for_roi2",
    "total_prepay_and_pay_order_roi2",
    "total_prepay_and_pay_settle_roi2_1h",
    "total_prepay_and_pay_settle_overall_roi2_1h",
    "total_order_settle_amount_for_roi2_1h",
    "total_order_real_settle_amount_for_roi2_1h",
    "total_order_settle_count_for_roi2_1h",
    "total_order_settle_amount_rate_for_roi2_1h",
    "total_order_settle_count_rate_for_roi2_1h",
    "total_cost_per_pay_order_settle_for_roi2_1h",
    "total_cost_per_pay_order_settle_for_overall_roi2_1h",
    "total_refund_order_count_for_roi2_1h",
    "total_refund_order_gmv_for_roi2_1h_all",
    "total_refund_order_gmv_for_roi2_1h_rate",
    "total_ecom_platform_subsidy_amount_for_roi2",
    "total_unfinished_estimate_order_gmv_for_roi2",
    "no_refund_ecom_coupon_amount_for_roi2",
    "no_refund_ecom_platform_subsidy_amount_for_roi2",
]
DEFAULT_RULES = [
    {
        "id": "low-roi-stop",
        "groupId": "risk-stop",
        "name": "低 ROI 自动暂停",
        "enabled": True,
        "action": "DISABLE",
        "afterMinutes": 60,
        "minSpend": 120,
        "roiBelow": 1.2,
        "roiAbove": 0,
        "holdMinutes": 30,
        "cooldown": 45,
        "budgetMode": "percent",
        "budgetValue": 0,
        "dailyCap": 0,
        "notify": "all",
        "shopIds": [],
        "planPrefixes": [],
        "planSmartBidTypes": CONTROL_PLAN_SMART_BID_TYPES,
    },
    {
        "id": "high-roi-budget",
        "groupId": "scale-budget",
        "name": "高 ROI 加预算",
        "enabled": True,
        "action": "ADD_BUDGET",
        "afterMinutes": 120,
        "minSpend": 200,
        "roiBelow": 0,
        "roiAbove": 2.2,
        "holdMinutes": 60,
        "cooldown": 60,
        "budgetMode": "percent",
        "budgetValue": 20,
        "dailyCap": 800,
        "notify": "wechat",
        "shopIds": [],
        "planPrefixes": [],
        "planSmartBidTypes": CONTROL_PLAN_SMART_BID_TYPES,
    },
    {
        "id": "spend-step-roi-stop",
        "groupId": "risk-stop",
        "name": "分段净成交ROI自动暂停",
        "enabled": False,
        "action": "SPEND_STEP_ROI_STOP",
        "afterMinutes": 0,
        "minSpend": 0,
        "spendStep": 100,
        "delayMinutes": 10,
        "roiBelow": 1.2,
        "roiAbove": 0,
        "holdMinutes": 10,
        "cooldown": 30,
        "budgetMode": "fixed",
        "budgetValue": 0,
        "dailyCap": 0,
        "notify": "wechat",
        "shopIds": [],
        "planPrefixes": [],
        "planSmartBidTypes": CONTROL_PLAN_SMART_BID_TYPES,
    },
    {
        "id": "near-budget-roi-add-budget",
        "groupId": "scale-budget",
        "name": "预算将尽高 ROI 继续加",
        "enabled": False,
        "action": "NEAR_BUDGET_ROI_ADD_BUDGET",
        "afterMinutes": 0,
        "minSpend": 0,
        "spendStep": 0,
        "delayMinutes": 0,
        "budgetRemainingPercent": 10,
        "roiBelow": 0,
        "roiAbove": 2.2,
        "holdMinutes": 0,
        "cooldown": 0,
        "budgetMode": "fixed",
        "budgetValue": 100,
        "dailyCap": 0,
        "notify": "wechat",
        "shopIds": [],
        "planPrefixes": [],
        "planSmartBidTypes": CONTROL_PLAN_SMART_BID_TYPES,
    },
    {
        "id": "hourly-spend-increase-roi-goal",
        "groupId": "scale-budget",
        "name": "小时消耗高调 ROI 目标",
        "enabled": False,
        "action": "HOURLY_SPEND_INCREASE_ROI_GOAL",
        "afterMinutes": 0,
        "minSpend": 0,
        "spendStep": 0,
        "delayMinutes": 0,
        "hourlySpendAbove": 100,
        "roiGoalIncrement": 0.2,
        "maxRoiGoal": 2.4,
        "budgetRemainingPercent": 0,
        "roiBelow": 0,
        "roiAbove": 0,
        "holdMinutes": 0,
        "cooldown": 0,
        "budgetMode": "fixed",
        "budgetValue": 0,
        "dailyCap": 0,
        "notify": "wechat",
        "shopIds": [],
        "planPrefixes": [],
        "planSmartBidTypes": CONTROL_PLAN_SMART_BID_TYPES,
    },
    {
        "id": "zero-order-watch",
        "groupId": "watch-notify",
        "name": "零成交提醒",
        "enabled": True,
        "action": "NOTIFY",
        "afterMinutes": 90,
        "minSpend": 180,
        "roiBelow": 0.1,
        "roiAbove": 0,
        "holdMinutes": 20,
        "cooldown": 30,
        "budgetMode": "fixed",
        "budgetValue": 0,
        "dailyCap": 0,
        "notify": "wechat",
        "shopIds": [],
        "planPrefixes": [],
        "planSmartBidTypes": CONTROL_PLAN_SMART_BID_TYPES,
    },
]
ENSURED_DEFAULT_RULE_IDS = {"spend-step-roi-stop", "near-budget-roi-add-budget", "hourly-spend-increase-roi-goal"}
CLOUD_AUTO_RULE_ACTIONS = [
    "DISABLE",
    "SPEND_STEP_ROI_STOP",
    "NEAR_BUDGET_ROI_ADD_BUDGET",
    "HOURLY_SPEND_INCREASE_ROI_GOAL",
    "ADD_BUDGET",
    "NOTIFY",
]

DEFAULT_RULE_GROUPS = [
    {"id": "risk-stop", "name": "止损规则组", "description": "低 ROI、高消耗、零成交等暂停和提醒规则", "shop_id": None},
    {"id": "scale-budget", "name": "放量规则组", "description": "ROI 达标后的预算递增规则", "shop_id": None},
    {"id": "watch-notify", "name": "观察提醒组", "description": "先通知投手确认的规则", "shop_id": None},
]


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def utc_now_dt():
    return dt.datetime.now(dt.timezone.utc)


def parse_utc_datetime(value):
    if isinstance(value, dt.datetime):
        parsed = value
    elif value:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        parsed = utc_now_dt()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def beijing_datetime(value=None):
    return parse_utc_datetime(value).astimezone(dt.timezone(dt.timedelta(hours=8)))


def utc_from_now(days=0, seconds=0):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days, seconds=seconds)).isoformat()


def hash_password(password):
    salt = secrets.token_hex(16)
    iterations = 200000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password, stored_hash):
    try:
        scheme, iterations, salt, digest = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        calculated = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
        return hmac.compare_digest(calculated, digest)
    except Exception:
        return False


def parse_iso(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def json_loads(value, default):
    if not value:
        return default
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return default
    return data


def normalize_plan_prefix(value):
    prefix = str(value or "").strip().upper()[:2]
    if len(prefix) == 2 and prefix.isalpha() and prefix.isascii():
        return prefix
    return ""


def normalize_plan_prefixes(values):
    if not isinstance(values, list):
        return []
    normalized = []
    seen = set()
    for value in values:
        prefix = normalize_plan_prefix(value)
        if prefix and prefix not in seen:
            normalized.append(prefix)
            seen.add(prefix)
    return normalized


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
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if upper in PLAN_SMART_BID_TYPES:
        return upper
    return PLAN_SMART_BID_ALIASES.get(upper) or PLAN_SMART_BID_ALIASES.get(text) or ""


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


def query_values(query, *names):
    values = []
    if not isinstance(query, dict):
        return values
    for name in names:
        if name in query:
            values.extend(flatten_values(query.get(name)))
    return values


def body_plan_smart_bid_types(body, default=None):
    if not isinstance(body, dict):
        return list(default or [])
    values = []
    for name in ("planSmartBidTypes", "plan_smart_bid_types", "smartBidTypes", "smart_bid_types", "smartBidType", "smart_bid_type"):
        if name in body:
            values.extend(flatten_values(body.get(name)))
    return normalize_plan_smart_bid_types(values, default=default)


def query_plan_smart_bid_types(query, default=None):
    values = query_values(query, "planSmartBidTypes", "plan_smart_bid_types", "smartBidTypes", "smart_bid_types", "smartBidType", "smart_bid_type")
    return normalize_plan_smart_bid_types(values, default=default)


def plan_smart_bid_type(plan):
    if not isinstance(plan, dict):
        return CONTROL_PLAN_SMART_BID_TYPES[0]
    item = normalize_plan_smart_bid_type(plan.get("smartBidType") or plan.get("smart_bid_type"))
    if item:
        return item
    raw = plan.get("raw") if isinstance(plan.get("raw"), dict) else {}
    ad = raw.get("ad_info") if isinstance(raw.get("ad_info"), dict) else {}
    return normalize_plan_smart_bid_type(ad.get("smart_bid_type")) or CONTROL_PLAN_SMART_BID_TYPES[0]


def plan_smart_bid_label(value):
    return PLAN_SMART_BID_LABELS.get(normalize_plan_smart_bid_type(value), str(value or "未知"))


def plan_prefix_options(prefixes=None):
    owner_map = plan_prefix_owner_map()
    if prefixes is not None:
        source = normalize_plan_prefixes(prefixes)
    else:
        source = normalize_plan_prefixes(list(PLAN_PREFIX_OWNERS.keys()) + list(owner_map.keys()))
    return [
        {
            "prefix": prefix,
            "ownerName": owner_map.get(prefix) or "未绑定",
            "label": f"{prefix} {owner_map.get(prefix) or '未绑定'}",
        }
        for prefix in source
    ]


def clear_prefix_owner_cache():
    PREFIX_OWNER_CACHE["expires_at"] = 0
    PREFIX_OWNER_CACHE["owners"] = {}


def plan_prefix_owner_map():
    now = time.time()
    if PREFIX_OWNER_CACHE["expires_at"] > now:
        return dict(PREFIX_OWNER_CACHE["owners"])
    owners = dict(PLAN_PREFIX_OWNERS)
    try:
        if os.path.exists(DB_PATH):
            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute(
                    """
                    select b.plan_prefix, u.display_name
                    from user_plan_prefix_bindings b
                    join users u on u.id = b.user_id
                    where u.role != 'admin' and u.status = 'active'
                    order by b.plan_prefix, u.id
                    """
                ).fetchall()
            for prefix, display_name in rows:
                normalized = normalize_plan_prefix(prefix)
                if normalized:
                    owners[normalized] = display_name
    except sqlite3.Error:
        pass
    PREFIX_OWNER_CACHE["owners"] = owners
    PREFIX_OWNER_CACHE["expires_at"] = now + 30
    return dict(owners)


def plan_prefix_for_owner_name(name):
    clean_name = str(name or "").strip()
    for prefix, owner_name in PLAN_PREFIX_OWNERS.items():
        if clean_name == owner_name:
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


def annotate_plan_owner(plan):
    item = dict(plan)
    prefix = normalize_plan_prefix(item.get("ownerPrefix")) or plan_prefix_for_name(item.get("name"))
    item["ownerPrefix"] = prefix
    item["ownerName"] = plan_prefix_owner_map().get(prefix, "未绑定" if prefix else "未分配")
    return item


def ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), mode=0o700, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            create table if not exists callbacks (
                id integer primary key autoincrement,
                created_at text not null,
                remote_addr text,
                state text,
                auth_code text,
                query_json text,
                exchange_status text,
                exchange_response_json text
            )
            """
        )
        conn.execute(
            """
            create table if not exists tokens (
                id integer primary key autoincrement,
                created_at text not null,
                request_id text,
                advertiser_ids_json text,
                response_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists control_rules (
                id text primary key,
                updated_at text not null,
                rule_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists control_action_logs (
                id integer primary key autoincrement,
                created_at text not null,
                action text not null,
                dry_run integer not null,
                request_json text not null,
                response_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists rule_plan_spend_cursors (
                rule_id text not null,
                advertiser_id integer not null,
                plan_id integer not null,
                last_spend real not null,
                last_gmv real not null,
                updated_at text not null,
                primary key (rule_id, advertiser_id, plan_id)
            )
            """
        )
        conn.execute(
            """
            create table if not exists rule_plan_spend_checks (
                rule_id text not null,
                advertiser_id integer not null,
                plan_id integer not null,
                bucket_index integer not null,
                status text not null,
                triggered_at text not null,
                due_at text not null,
                start_spend real not null,
                start_gmv real not null,
                trigger_spend real not null,
                trigger_gmv real not null,
                evaluated_at text,
                delta_spend real,
                delta_gmv real,
                delta_roi real,
                response_json text,
                primary key (rule_id, advertiser_id, plan_id, bucket_index)
            )
            """
        )
        conn.execute(
            """
            create table if not exists scheduled_job_runs (
                job_name text not null,
                run_key text not null,
                status text not null,
                started_at text not null,
                finished_at text,
                request_json text,
                response_json text,
                error_text text,
                primary key (job_name, run_key)
            )
            """
        )
        conn.execute(
            """
            create table if not exists users (
                id integer primary key autoincrement,
                username text not null unique,
                display_name text not null,
                role text not null,
                password_hash text not null,
                status text not null,
                permissions_json text not null,
                created_at text not null,
                updated_at text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists sessions (
                token text primary key,
                user_id integer not null,
                created_at text not null,
                expires_at text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists shops (
                shop_id integer primary key,
                shop_name text not null,
                advertiser_id integer not null,
                status text not null,
                created_at text not null,
                updated_at text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists user_shop_bindings (
                user_id integer not null,
                shop_id integer not null,
                primary key (user_id, shop_id)
            )
            """
        )
        conn.execute(
            """
            create table if not exists user_plan_prefix_bindings (
                user_id integer not null,
                plan_prefix text not null,
                primary key (user_id, plan_prefix)
            )
            """
        )
        conn.execute(
            """
            create table if not exists rule_groups (
                id text primary key,
                name text not null,
                description text not null,
                shop_id integer,
                created_at text not null,
                updated_at text not null
            )
            """
        )
        now = utc_now()
        admin_count = conn.execute("select count(*) from users where role = 'admin'").fetchone()[0]
        if admin_count == 0:
            conn.execute(
                """
                insert into users(username, display_name, role, password_hash, status, permissions_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    BOOTSTRAP_ADMIN_USERNAME,
                    "管理员",
                    "admin",
                    hash_password(BOOTSTRAP_ADMIN_PASSWORD),
                    "active",
                    json.dumps({"view_plans": True, "control_plans": True, "manage_rules": True, "manage_users": True}),
                    now,
                    now,
                ),
            )
        shop_row = conn.execute("select shop_id from shops where shop_id = ?", (DEFAULT_SHOP_ID,)).fetchone()
        if shop_row:
            conn.execute(
                """
                update shops
                set shop_name = ?, advertiser_id = ?, status = 'active', updated_at = ?
                where shop_id = ?
                """,
                (DEFAULT_SHOP_NAME, DEFAULT_ADVERTISER_ID, now, DEFAULT_SHOP_ID),
            )
        else:
            conn.execute(
                """
                insert into shops(shop_id, shop_name, advertiser_id, status, created_at, updated_at)
                values (?, ?, ?, 'active', ?, ?)
                """,
                (DEFAULT_SHOP_ID, DEFAULT_SHOP_NAME, DEFAULT_ADVERTISER_ID, now, now),
            )
        admin_rows = conn.execute("select id from users where role = 'admin'").fetchall()
        for (admin_id,) in admin_rows:
            conn.execute(
                "insert or ignore into user_shop_bindings(user_id, shop_id) values (?, ?)",
                (admin_id, DEFAULT_SHOP_ID),
            )
            for prefix in PLAN_PREFIX_OWNERS:
                conn.execute(
                    "insert or ignore into user_plan_prefix_bindings(user_id, plan_prefix) values (?, ?)",
                    (admin_id, prefix),
                )
        user_rows = conn.execute("select id, display_name, role from users").fetchall()
        for user_id, display_name, role in user_rows:
            if role == "admin":
                continue
            bound_count = conn.execute(
                "select count(*) from user_plan_prefix_bindings where user_id = ?",
                (user_id,),
            ).fetchone()[0]
            if bound_count:
                continue
            prefix = plan_prefix_for_owner_name(display_name)
            if prefix:
                conn.execute(
                    "insert or ignore into user_plan_prefix_bindings(user_id, plan_prefix) values (?, ?)",
                    (user_id, prefix),
                )
        for group in DEFAULT_RULE_GROUPS:
            conn.execute(
                """
                insert or ignore into rule_groups(id, name, description, shop_id, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (group["id"], group["name"], group["description"], group["shop_id"], now, now),
            )
        conn.execute(
            """
            update rule_groups
            set description = replace(description, ?, ?), updated_at = ?
            where description like ?
            """,
            ("\u5173\u505c", "暂停", now, "%\u5173\u505c%"),
        )
        count = conn.execute("select count(*) from control_rules").fetchone()[0]
        if count == 0:
            for rule in DEFAULT_RULES:
                conn.execute(
                    """
                    insert into control_rules(id, updated_at, rule_json)
                    values (?, ?, ?)
                    """,
                    (rule["id"], utc_now(), json.dumps(rule, ensure_ascii=False)),
                )
        else:
            for rule in DEFAULT_RULES:
                if rule["id"] not in ENSURED_DEFAULT_RULE_IDS:
                    continue
                conn.execute(
                    """
                    insert or ignore into control_rules(id, updated_at, rule_json)
                    values (?, ?, ?)
                    """,
                    (rule["id"], utc_now(), json.dumps(rule, ensure_ascii=False)),
                )
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass


def sign_state(payload):
    mac = hmac.new(
        STATE_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]
    return f"{payload}.{mac}"


def make_state():
    payload = f"qc-{int(time.time())}"
    return sign_state(payload)


def state_is_valid(state):
    if not state or "." not in state:
        return False
    payload, mac = state.rsplit(".", 1)
    return hmac.compare_digest(sign_state(payload), state)


def auth_url():
    params = {
        "app_id": APP_ID,
        "state": make_state(),
        "material_auth": "1",
    }
    return "https://qianchuan.jinritemai.com/openapi/qc/audit/oauth.html?" + urllib.parse.urlencode(params)


def exchange_token(auth_code):
    if not APP_SECRET:
        return "missing_secret", {"message": "OCEANENGINE_APP_SECRET is not configured"}
    body = json.dumps(
        {
            "app_id": APP_ID,
            "secret": APP_SECRET,
            "auth_code": auth_code,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return "exchange_error", {"message": str(exc)}
    request_id = ""
    advertiser_ids = []
    if isinstance(data, dict):
        request_id = str(data.get("request_id") or "")
        payload = data.get("data") or {}
        if isinstance(payload, dict):
            advertiser_ids = payload.get("advertiser_ids") or []
    ok = (
        isinstance(data, dict)
        and data.get("code") == 0
        and isinstance(data.get("data"), dict)
        and bool(data["data"].get("access_token"))
    )
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into tokens(created_at, request_id, advertiser_ids_json, response_json)
            values (?, ?, ?, ?)
            """,
            (utc_now(), request_id, json.dumps(advertiser_ids), json.dumps(data)),
        )
    return ("exchanged" if ok else "exchange_failed"), data


def response_is_ok(data):
    return (
        isinstance(data, dict)
        and data.get("code") == 0
        and isinstance(data.get("data"), dict)
        and bool(data["data"].get("access_token"))
    )


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


def insert_token_response(data):
    request_id = ""
    advertiser_ids = []
    if isinstance(data, dict):
        request_id = str(data.get("request_id") or "")
        payload = data.get("data") or {}
        if isinstance(payload, dict):
            advertiser_ids = payload.get("advertiser_ids") or []
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into tokens(created_at, request_id, advertiser_ids_json, response_json)
            values (?, ?, ?, ?)
            """,
            (utc_now(), request_id, json.dumps(advertiser_ids), json.dumps(data)),
        )


def latest_refresh_token():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "select response_json from tokens order by id desc limit 50"
        ).fetchall()
    for (response_json,) in rows:
        try:
            data = json.loads(response_json)
        except json.JSONDecodeError:
            continue
        payload = data.get("data") if isinstance(data, dict) else None
        if isinstance(payload, dict) and payload.get("refresh_token"):
            return payload["refresh_token"]
    return ""


def refresh_latest_token():
    if not APP_SECRET:
        return "missing_secret", {"message": "OCEANENGINE_APP_SECRET is not configured"}
    refresh_token = latest_refresh_token()
    if not refresh_token:
        return "missing_refresh_token", {"message": "No refresh_token found in token store"}
    body = json.dumps(
        {
            "app_id": APP_ID,
            "secret": APP_SECRET,
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        REFRESH_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return "refresh_error", {"message": str(exc)}
    insert_token_response(data)
    return ("refreshed" if response_is_ok(data) else "refresh_failed"), data


def token_response_summary(status, data):
    payload = data.get("data") if isinstance(data, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "status": status,
        "code": data.get("code") if isinstance(data, dict) else None,
        "message": data.get("message") if isinstance(data, dict) else None,
        "request_id": data.get("request_id") if isinstance(data, dict) else None,
        "advertiser_ids": payload.get("advertiser_ids") or [],
        "expires_in": payload.get("expires_in"),
        "refresh_token_expires_in": payload.get("refresh_token_expires_in"),
    }


def latest_access_token():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "select response_json from tokens order by id desc limit 50"
        ).fetchall()
    for (response_json,) in rows:
        try:
            data = json.loads(response_json)
        except json.JSONDecodeError:
            continue
        payload = data.get("data") if isinstance(data, dict) else None
        if isinstance(payload, dict) and payload.get("access_token"):
            return payload["access_token"]
    return ""


def ocean_request(method, path, params=None, body=None):
    token = latest_access_token()
    if not token:
        return {"code": -1, "message": "missing access token"}
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    headers = {"Access-Token": token}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"code": exc.code, "message": raw[:500]}
    except Exception as exc:
        return {"code": -1, "message": str(exc)}


def ocean_get(path, params=None):
    return ocean_request("GET", path, params=params)


def ocean_post(path, body):
    return ocean_request("POST", path, body=body)


def ocean_response_rate_limited(data):
    if not isinstance(data, dict):
        return False
    if int(number(data.get("code"), 0)) == 40100:
        return True
    message = str(data.get("message") or "")
    return "频率" in message or "限流" in message or "rate" in message.lower()


def ocean_post_with_retry(path, body, max_retries=None, sleep_seconds=None):
    attempts = max(1, int(max_retries or CLOUD_BUDGET_RESET_MAX_RETRIES))
    delay = max(0, float(CLOUD_BUDGET_RESET_RETRY_SLEEP_SECONDS if sleep_seconds is None else sleep_seconds))
    response = None
    for attempt in range(attempts):
        response = ocean_post(path, body)
        if not ocean_response_rate_limited(response) or attempt >= attempts - 1:
            return response
        time.sleep(delay * (attempt + 1))
    return response or {"code": -1, "message": "empty response"}


def number(value, default=0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def normalized_budget_value(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def default_budget_reset_targets():
    return {
        "SMART_BID_CUSTOM": normalized_budget_value(CLOUD_BUDGET_RESET_CONTROL_BUDGET),
        "SMART_BID_CONSERVATIVE": normalized_budget_value(CLOUD_BUDGET_RESET_VOLUME_BUDGET),
    }


def budget_reset_targets_from_body(body, smart_bid_types):
    smart_bid_types = smart_bid_types or PLAN_SMART_BID_TYPES
    raw_targets = body.get("budgetTargets") or body.get("budget_targets")
    if isinstance(raw_targets, dict):
        targets = default_budget_reset_targets()
        for key, value in raw_targets.items():
            smart_bid_type = normalize_plan_smart_bid_type(key)
            if smart_bid_type:
                targets[smart_bid_type] = normalized_budget_value(number(value))
    elif "budget" in body:
        target_budget = normalized_budget_value(number(body.get("budget"), CLOUD_BUDGET_RESET_TARGET))
        targets = {smart_bid_type: target_budget for smart_bid_type in smart_bid_types}
    else:
        targets = default_budget_reset_targets()
    for smart_bid_type in smart_bid_types:
        if number(targets.get(smart_bid_type)) <= 0:
            return None, f"budget target for {smart_bid_type} must be greater than 0"
    return {smart_bid_type: targets[smart_bid_type] for smart_bid_type in smart_bid_types}, None


def stat_money(value):
    return number(value) / 100000


def has_stat(stats, name):
    if not isinstance(stats, dict):
        return False
    value = stats.get(name)
    return value is not None and str(value) != ""


def first_stat_number(stats, *names):
    for name in names:
        if has_stat(stats, name):
            return number(stats.get(name)), name
    return 0, ""


def first_stat_money(stats, *names):
    value, name = first_stat_number(stats, *names)
    return stat_money(value), name


def int_param(query, name, default):
    value = (query.get(name) or [default])[0]
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def str_param(query, name, default):
    return (query.get(name) or [default])[0]


def bj_today_range():
    now = dt.datetime.utcnow() + dt.timedelta(hours=8)
    day = now.strftime("%Y-%m-%d")
    return f"{day} 00:00:00", f"{day} 23:59:59"


def load_rules():
    ensure_db()
    rules = []
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("select rule_json from control_rules order by id").fetchall()
    for (rule_json,) in rows:
        try:
            rule = json.loads(rule_json)
        except json.JSONDecodeError:
            continue
        if "groupId" not in rule:
            if rule.get("action") == "ADD_BUDGET":
                rule["groupId"] = "scale-budget"
            elif rule.get("action") == "DISABLE":
                rule["groupId"] = "risk-stop"
            else:
                rule["groupId"] = "watch-notify"
        if "shopIds" not in rule:
            rule["shopIds"] = []
        if "planPrefixes" not in rule or not isinstance(rule.get("planPrefixes"), list):
            rule["planPrefixes"] = []
        rule["planPrefixes"] = normalize_plan_prefixes(rule.get("planPrefixes"))
        rule["planSmartBidTypes"] = normalize_plan_smart_bid_types(
            rule.get("planSmartBidTypes") or rule.get("smartBidTypes") or rule.get("smart_bid_types"),
            default=CONTROL_PLAN_SMART_BID_TYPES,
        )
        if rule.get("id") == "low-roi-stop" and rule.get("name", "").endswith("\u5173\u505c"):
            rule["name"] = "低 ROI 自动暂停"
        rules.append(rule)
    return rules


def save_rules(rules):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("delete from control_rules")
        for rule in rules:
            rule_id = str(rule.get("id") or f"rule-{int(time.time() * 1000)}")
            rule["id"] = rule_id
            if "groupId" not in rule:
                rule["groupId"] = "watch-notify"
            if "shopIds" not in rule or not isinstance(rule.get("shopIds"), list):
                rule["shopIds"] = []
            if "planPrefixes" not in rule or not isinstance(rule.get("planPrefixes"), list):
                rule["planPrefixes"] = []
            rule["planPrefixes"] = normalize_plan_prefixes(rule.get("planPrefixes"))
            rule["planSmartBidTypes"] = normalize_plan_smart_bid_types(
                rule.get("planSmartBidTypes") or rule.get("smartBidTypes") or rule.get("smart_bid_types"),
                default=CONTROL_PLAN_SMART_BID_TYPES,
            )
            conn.execute(
                """
                insert into control_rules(id, updated_at, rule_json)
                values (?, ?, ?)
                """,
                (rule_id, utc_now(), json.dumps(rule, ensure_ascii=False)),
            )


def public_user(row, shop_ids=None, plan_prefixes=None):
    if not row:
        return None
    permissions = json_loads(row["permissions_json"], {})
    if row["role"] == "admin":
        plan_prefixes = [item["prefix"] for item in plan_prefix_options()]
    else:
        plan_prefixes = normalize_plan_prefixes(plan_prefixes or [])
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "role": row["role"],
        "status": row["status"],
        "permissions": permissions,
        "shopIds": shop_ids or [],
        "planPrefixes": plan_prefixes,
        "planAssignments": plan_prefix_options(plan_prefixes),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def user_shop_ids(conn, user_id):
    rows = conn.execute(
        "select shop_id from user_shop_bindings where user_id = ? order by shop_id",
        (user_id,),
    ).fetchall()
    return [int(row[0]) for row in rows]


def user_plan_prefixes(conn, user_id, row=None):
    if row and row["role"] == "admin":
        return list(PLAN_PREFIX_OWNERS.keys())
    rows = conn.execute(
        "select plan_prefix from user_plan_prefix_bindings where user_id = ? order by plan_prefix",
        (user_id,),
    ).fetchall()
    prefixes = normalize_plan_prefixes([row[0] for row in rows])
    if prefixes:
        return prefixes
    if row:
        inferred = plan_prefix_for_owner_name(row["display_name"])
        if inferred:
            return [inferred]
    return []


def get_user_by_username(username):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from users where username = ?", (username,)).fetchone()
        return row


def get_user_by_id(user_id):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return public_user(row, [], user_plan_prefixes(conn, user_id, row))


def create_session(user_id):
    ensure_db()
    token = secrets.token_urlsafe(36)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into sessions(token, user_id, created_at, expires_at)
            values (?, ?, ?, ?)
            """,
            (token, user_id, utc_now(), utc_from_now(days=SESSION_DAYS)),
        )
    return token


def user_from_session(token):
    if not token:
        return None
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            select u.*
            from sessions s
            join users u on u.id = s.user_id
            where s.token = ?
            """,
            (token,),
        ).fetchone()
        session = conn.execute("select expires_at from sessions where token = ?", (token,)).fetchone()
        if not row or not session:
            return None
        expires_at = parse_iso(session["expires_at"])
        if not expires_at or expires_at <= dt.datetime.now(dt.timezone.utc):
            conn.execute("delete from sessions where token = ?", (token,))
            return None
        if row["status"] != "active":
            return None
        return public_user(row, [], user_plan_prefixes(conn, row["id"], row))


def list_users():
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("select * from users order by role, id").fetchall()
        return [public_user(row, [], user_plan_prefixes(conn, row["id"], row)) for row in rows]


def role_permissions(role):
    if role == "admin":
        return {"view_plans": True, "control_plans": True, "manage_rules": True, "manage_users": True}
    if role == "operator":
        return {"view_plans": True, "control_plans": True, "manage_rules": False, "manage_users": False}
    return {"view_plans": True, "control_plans": False, "manage_rules": False, "manage_users": False}


def save_user(body):
    ensure_db()
    now = utc_now()
    user_id = int(body.get("id") or 0)
    username = str(body.get("username") or "").strip()
    display_name = str(body.get("displayName") or body.get("display_name") or username or "未命名").strip()
    role = str(body.get("role") or "operator").strip()
    status = str(body.get("status") or "active").strip()
    password = str(body.get("password") or "")
    plan_prefixes = normalize_plan_prefixes(body.get("planPrefixes") if isinstance(body.get("planPrefixes"), list) else [])
    if role not in {"admin", "operator", "viewer"}:
        role = "operator"
    if status not in {"active", "disabled"}:
        status = "active"
    if not username:
        return None, "username is required"
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if user_id > 0:
            existing = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
            if not existing:
                return None, "user not found"
            params = [username, display_name, role, status, json.dumps(role_permissions(role)), now, user_id]
            sql = """
                update users
                set username = ?, display_name = ?, role = ?, status = ?, permissions_json = ?, updated_at = ?
                where id = ?
            """
            conn.execute(sql, params)
            if password:
                conn.execute(
                    "update users set password_hash = ?, updated_at = ? where id = ?",
                    (hash_password(password), now, user_id),
                )
        else:
            if not password:
                password = secrets.token_urlsafe(12)
            cur = conn.execute(
                """
                insert into users(username, display_name, role, password_hash, status, permissions_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    display_name,
                    role,
                    hash_password(password),
                    status,
                    json.dumps(role_permissions(role)),
                    now,
                    now,
                ),
            )
            user_id = cur.lastrowid
        if role != "admin" and not plan_prefixes:
            inferred_prefix = plan_prefix_for_owner_name(display_name)
            if inferred_prefix:
                plan_prefixes = [inferred_prefix]
        conn.execute("delete from user_plan_prefix_bindings where user_id = ?", (user_id,))
        for prefix in (list(PLAN_PREFIX_OWNERS.keys()) if role == "admin" else plan_prefixes):
            conn.execute(
                "insert or ignore into user_plan_prefix_bindings(user_id, plan_prefix) values (?, ?)",
                (user_id, prefix),
            )
    clear_prefix_owner_cache()
    return get_user_by_id(user_id), None


def delete_user(user_id):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        admin_count = conn.execute("select count(*) from users where role = 'admin' and id != ?", (user_id,)).fetchone()[0]
        role_row = conn.execute("select role from users where id = ?", (user_id,)).fetchone()
        if not role_row:
            return False, "user not found"
        if role_row[0] == "admin" and admin_count <= 0:
            return False, "cannot delete the last admin"
        conn.execute("delete from sessions where user_id = ?", (user_id,))
        conn.execute("delete from user_shop_bindings where user_id = ?", (user_id,))
        conn.execute("delete from user_plan_prefix_bindings where user_id = ?", (user_id,))
        conn.execute("delete from users where id = ?", (user_id,))
    clear_prefix_owner_cache()
    return True, None


def list_shops(include_disabled=False):
    ensure_db()
    sql = "select shop_id, shop_name, advertiser_id, status, created_at, updated_at from shops"
    params = []
    if not include_disabled:
        sql += " where status = ?"
        params.append("active")
    sql += " order by shop_name, shop_id"
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "shopId": int(row[0]),
            "shopName": row[1],
            "advertiserId": int(row[2]),
            "status": row[3],
            "createdAt": row[4],
            "updatedAt": row[5],
        }
        for row in rows
    ]


def save_shop(body):
    ensure_db()
    try:
        shop_id = int(body.get("shopId") or body.get("shop_id") or 0)
        advertiser_id = int(body.get("advertiserId") or body.get("advertiser_id") or 0)
    except (TypeError, ValueError):
        return None, "shopId and advertiserId must be numbers"
    shop_name = str(body.get("shopName") or body.get("shop_name") or "").strip()
    status = str(body.get("status") or "active").strip()
    if status not in {"active", "disabled"}:
        status = "active"
    if shop_id <= 0 or advertiser_id <= 0 or not shop_name:
        return None, "shopId, shopName and advertiserId are required"
    now = utc_now()
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("select shop_id from shops where shop_id = ?", (shop_id,)).fetchone()
        if existing:
            conn.execute(
                """
                update shops set shop_name = ?, advertiser_id = ?, status = ?, updated_at = ?
                where shop_id = ?
                """,
                (shop_name, advertiser_id, status, now, shop_id),
            )
        else:
            conn.execute(
                """
                insert into shops(shop_id, shop_name, advertiser_id, status, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (shop_id, shop_name, advertiser_id, status, now, now),
            )
    return next((shop for shop in list_shops(include_disabled=True) if shop["shopId"] == shop_id), None), None


def delete_shop(shop_id):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("update shops set status = 'disabled', updated_at = ? where shop_id = ?", (utc_now(), shop_id))
        conn.execute("delete from user_shop_bindings where shop_id = ?", (shop_id,))
    return True


def list_rule_groups():
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "select id, name, description, shop_id, created_at, updated_at from rule_groups order by created_at, id"
        ).fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "shopId": row[3],
            "createdAt": row[4],
            "updatedAt": row[5],
        }
        for row in rows
    ]


def save_rule_group(body):
    ensure_db()
    group_id = str(body.get("id") or f"group-{int(time.time() * 1000)}").strip()
    name = str(body.get("name") or "").strip()
    description = str(body.get("description") or "").strip()
    shop_id = body.get("shopId")
    if shop_id in ("", 0):
        shop_id = None
    if shop_id is not None:
        try:
            shop_id = int(shop_id)
        except (TypeError, ValueError):
            shop_id = None
    if not name:
        return None, "name is required"
    now = utc_now()
    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute("select id from rule_groups where id = ?", (group_id,)).fetchone()
        if exists:
            conn.execute(
                """
                update rule_groups set name = ?, description = ?, shop_id = ?, updated_at = ?
                where id = ?
                """,
                (name, description, shop_id, now, group_id),
            )
        else:
            conn.execute(
                """
                insert into rule_groups(id, name, description, shop_id, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (group_id, name, description, shop_id, now, now),
            )
    return next((group for group in list_rule_groups() if group["id"] == group_id), None), None


def delete_rule_group(group_id):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("delete from rule_groups where id = ?", (group_id,))
    rules = load_rules()
    for rule in rules:
        if rule.get("groupId") == group_id:
            rule["groupId"] = "watch-notify"
    save_rules(rules)
    return True


def allowed_shops_for_user(user):
    shops = list_shops()
    if not user:
        return []
    return shops


def allowed_prefixes_for_user(user):
    if not user:
        return []
    if user.get("role") == "admin":
        return [item["prefix"] for item in plan_prefix_options()]
    return normalize_plan_prefixes(user.get("planPrefixes") or [])


def plan_belongs_to_user(plan, user):
    if user and user.get("role") == "admin":
        return True
    prefix = normalize_plan_prefix(plan.get("ownerPrefix")) or plan_prefix_for_name(plan.get("name"))
    allowed = set(allowed_prefixes_for_user(user))
    return bool(prefix and prefix in allowed)


def filter_plans_for_user(plans, user):
    annotated = [annotate_plan_owner(plan) for plan in plans if isinstance(plan, dict)]
    if user and user.get("role") == "admin":
        return annotated
    return [plan for plan in annotated if plan_belongs_to_user(plan, user)]


def dedupe_plans(plans):
    deduped = []
    seen = set()
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        key = (
            str(plan.get("advertiserId") or plan.get("advertiser_id") or ""),
            str(plan.get("id") or ""),
        )
        if key[1] and key in seen:
            continue
        if key[1]:
            seen.add(key)
        deduped.append(plan)
    return deduped


def select_shop_for_request(user, advertiser_id=None, shop_id=None):
    shops = allowed_shops_for_user(user)
    if not shops:
        return None
    try:
        advertiser_id = int(advertiser_id) if advertiser_id not in (None, "") else None
    except (TypeError, ValueError):
        advertiser_id = None
    try:
        shop_id = int(shop_id) if shop_id not in (None, "") else None
    except (TypeError, ValueError):
        shop_id = None
    for shop in shops:
        if shop_id and int(shop["shopId"]) == shop_id:
            return shop
    for shop in shops:
        if advertiser_id and int(shop["advertiserId"]) == advertiser_id:
            return shop
    return shops[0]


def filter_rules_for_user(rules, user):
    if user and user.get("role") == "admin":
        return rules
    allowed = set(allowed_prefixes_for_user(user))
    filtered = []
    for rule in rules:
        prefixes = normalize_plan_prefixes(rule.get("planPrefixes") or [])
        if not prefixes:
            filtered.append(rule)
            continue
        if set(prefixes) & allowed:
            filtered.append(rule)
    return filtered


def filter_rules_for_run_request(rules, body):
    body = body if isinstance(body, dict) else {}
    requested_actions = body.get("ruleActions") or body.get("rule_actions") or []
    if isinstance(requested_actions, str):
        requested_actions = [requested_actions]
    requested_actions = {str(action).strip() for action in requested_actions if str(action).strip()}
    requested_smart_bid_types = body_plan_smart_bid_types(body, default=[])
    filtered = rules
    if requested_actions:
        filtered = [rule for rule in filtered if str(rule.get("action") or "") in requested_actions]
    if requested_smart_bid_types:
        requested = set(requested_smart_bid_types)
        filtered = [
            rule
            for rule in filtered
            if requested & set(normalize_plan_smart_bid_types(rule.get("planSmartBidTypes"), default=CONTROL_PLAN_SMART_BID_TYPES))
        ]
    return filtered


def rule_plan_smart_bid_types(rule):
    return normalize_plan_smart_bid_types(
        rule.get("planSmartBidTypes") or rule.get("smartBidTypes") or rule.get("smart_bid_types") if isinstance(rule, dict) else [],
        default=CONTROL_PLAN_SMART_BID_TYPES,
    )


def rule_applies_to_plan_smart_bid_type(plan, rule):
    return plan_smart_bid_type(plan) in set(rule_plan_smart_bid_types(rule))


def plan_smart_bid_types_for_rules(rules):
    values = []
    for rule in rules:
        for item in rule_plan_smart_bid_types(rule):
            if item not in values:
                values.append(item)
    return values or list(CONTROL_PLAN_SMART_BID_TYPES)


def rule_is_deleted(rule):
    return bool(isinstance(rule, dict) and rule.get("deletedAt"))


def can_manage_admin(user):
    return bool(user and user.get("role") == "admin")


def can_control_plans(user):
    return bool(user and user.get("role") in {"admin", "operator"})


def log_action(action, dry_run, request_data, response_data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            insert into control_action_logs(created_at, action, dry_run, request_json, response_json)
            values (?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                action,
                1 if dry_run else 0,
                json.dumps(request_data, ensure_ascii=False),
                json.dumps(response_data, ensure_ascii=False),
            ),
        )


def daily_budget_reset_run_key(now=None):
    bj_now = beijing_datetime(now)
    window_start = bj_now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = window_start + dt.timedelta(minutes=CLOUD_BUDGET_RESET_WINDOW_MINUTES)
    if window_start <= bj_now < window_end:
        return bj_now.strftime("%Y-%m-%d")
    return ""


def interval_run_key(now=None, interval_seconds=300):
    current = parse_utc_datetime(now)
    interval_seconds = max(1, int(interval_seconds or 1))
    timestamp = int(current.timestamp())
    slot = timestamp - (timestamp % interval_seconds)
    return dt.datetime.fromtimestamp(slot, tz=dt.timezone.utc).replace(microsecond=0).isoformat()


def claim_scheduled_job(job_name, run_key, request_data=None):
    if not job_name or not run_key:
        return False
    ensure_db()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                insert into scheduled_job_runs(job_name, run_key, status, started_at, request_json)
                values (?, ?, 'running', ?, ?)
                """,
                (job_name, run_key, utc_now(), json.dumps(request_data or {}, ensure_ascii=False)),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def finish_scheduled_job(job_name, run_key, status, response_data=None, error_text=""):
    ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            update scheduled_job_runs
            set status = ?, finished_at = ?, response_json = ?, error_text = ?
            where job_name = ? and run_key = ?
            """,
            (
                status,
                utc_now(),
                json.dumps(response_data or {}, ensure_ascii=False),
                error_text,
                job_name,
                run_key,
            ),
        )


def normalize_uni_plan(item, selected_shop=None):
    ad = item.get("ad_info") or {}
    stats = item.get("stats_info") or {}
    products = item.get("product_info") or []
    rooms = item.get("room_info") or []
    product = products[0] if products else {}
    room = rooms[0] if rooms else {}
    stat_cost = stat_money(stats.get("stat_cost"))
    pay_gmv = stat_money(stats.get("total_pay_order_gmv_for_roi2"))
    pay_gmv_with_coupon = stat_money(stats.get("total_pay_order_gmv_include_coupon_for_roi2"))
    pay_roi = number(stats.get("total_prepay_and_pay_order_roi2"))
    if not has_stat(stats, "total_prepay_and_pay_order_roi2") and stat_cost > 0:
        pay_roi = pay_gmv / stat_cost
    settle_roi, settle_roi_field = first_stat_number(
        stats,
        "total_prepay_and_pay_settle_roi2_1h",
        "total_prepay_and_pay_settle_overall_roi2_1h",
    )
    settle_gmv, settle_gmv_field = first_stat_money(
        stats,
        "total_order_settle_amount_for_roi2_1h",
        "total_order_real_settle_amount_for_roi2_1h",
    )
    real_settle_gmv = stat_money(stats.get("total_order_real_settle_amount_for_roi2_1h"))
    has_settle_metric = bool(settle_roi_field or settle_gmv_field)
    roi = settle_roi
    if not settle_roi_field and stat_cost > 0 and settle_gmv_field:
        roi = settle_gmv / stat_cost
    if not has_settle_metric:
        roi = pay_roi
    gmv = settle_gmv if settle_gmv_field else pay_gmv
    smart_bid_type = normalize_plan_smart_bid_type(ad.get("smart_bid_type")) or CONTROL_PLAN_SMART_BID_TYPES[0]
    plan = {
        "id": ad.get("id"),
        "name": ad.get("name") or "",
        "product": product.get("product_name") or "",
        "productId": product.get("product_id"),
        "image": product.get("product_image") or "",
        "anchor": room.get("anchor_name") or "",
        "anchorId": room.get("anchor_id"),
        "planType": "UNI_PROMOTION",
        "marketingGoal": ad.get("marketing_goal"),
        "adlabScene": ad.get("adlab_scene"),
        "optStatus": ad.get("opt_status"),
        "status": ad.get("status"),
        "smartBidType": smart_bid_type,
        "smartBidLabel": plan_smart_bid_label(smart_bid_type),
        "elapsedMinutes": 0,
        "spend": stat_cost,
        "gmv": gmv,
        "payGmv": pay_gmv,
        "payGmvWithCoupon": pay_gmv_with_coupon,
        "settleGmv": settle_gmv,
        "realSettleGmv": real_settle_gmv,
        "orders": int(number(stats.get("total_pay_order_count_for_roi2"))),
        "roi": roi,
        "payRoi": pay_roi,
        "settleRoi": settle_roi,
        "settleOverallRoi": number(stats.get("total_prepay_and_pay_settle_overall_roi2_1h")),
        "roiMetric": {
            "active": "settle" if has_settle_metric else "pay",
            "roiField": settle_roi_field or "total_prepay_and_pay_order_roi2",
            "gmvField": settle_gmv_field or "total_pay_order_gmv_for_roi2",
        },
        "refundGmv": stat_money(stats.get("total_refund_order_gmv_for_roi2_1h_all")),
        "refundOrders": int(number(stats.get("total_refund_order_count_for_roi2_1h"))),
        "refundRate": number(stats.get("total_refund_order_gmv_for_roi2_1h_rate")) / 100000,
        "settleRate": number(stats.get("total_order_settle_amount_rate_for_roi2_1h")) / 100000,
        "settleOrders": int(number(stats.get("total_order_settle_count_for_roi2_1h"))),
        "settleOrderRate": number(stats.get("total_order_settle_count_rate_for_roi2_1h")) / 100000,
        "costPerPayOrder": stat_money(stats.get("total_cost_per_pay_order_for_roi2")),
        "costPerSettleOrder": stat_money(stats.get("total_cost_per_pay_order_settle_for_roi2_1h")),
        "costPerOverallSettleOrder": stat_money(stats.get("total_cost_per_pay_order_settle_for_overall_roi2_1h")),
        "payCouponAmount": stat_money(stats.get("total_pay_order_coupon_amount_for_roi2")),
        "platformSubsidyAmount": stat_money(stats.get("total_ecom_platform_subsidy_amount_for_roi2")),
        "shopEstimatedCommissionCost": stat_money(stats.get("shop_estimated_comission_cost")),
        "unfinishedEstimateGmv": stat_money(stats.get("total_unfinished_estimate_order_gmv_for_roi2")),
        "noRefundCouponAmount": stat_money(stats.get("no_refund_ecom_coupon_amount_for_roi2")),
        "noRefundPlatformSubsidyAmount": stat_money(stats.get("no_refund_ecom_platform_subsidy_amount_for_roi2")),
        "budget": number(ad.get("budget")),
        "budgetMode": ad.get("budget_mode"),
        "roiGoal": number(ad.get("roi2_goal")),
        "createTime": ad.get("create_time"),
        "startTime": ad.get("start_time"),
        "endTime": ad.get("end_time"),
        "modifyTime": ad.get("modify_time"),
        "raw": item,
    }
    if selected_shop:
        plan["shopId"] = selected_shop.get("shopId")
        plan["shopName"] = selected_shop.get("shopName")
        plan["advertiserId"] = selected_shop.get("advertiserId")
    return annotate_plan_owner(plan)


def qianchuan_plans(query, selected_shop=None):
    start_default, end_default = bj_today_range()
    advertiser_id = int(selected_shop["advertiserId"]) if selected_shop else int_param(query, "advertiser_id", DEFAULT_ADVERTISER_ID)
    marketing_goal = str_param(query, "marketing_goal", "VIDEO_PROM_GOODS")
    smart_bid_type = normalize_plan_smart_bid_type(str_param(query, "smart_bid_type", CONTROL_PLAN_SMART_BID_TYPES[0])) or CONTROL_PLAN_SMART_BID_TYPES[0]
    page = int_param(query, "page", 1)
    page_size = int_param(query, "page_size", 100)
    start_time = str_param(query, "start_time", start_default)
    end_time = str_param(query, "end_time", end_default)
    data = ocean_get(
        "/open_api/v1.0/qianchuan/uni_promotion/list/",
        {
            "advertiser_id": advertiser_id,
            "start_time": start_time,
            "end_time": end_time,
            "marketing_goal": marketing_goal,
            "fields": json.dumps(CONTROL_FIELDS),
            "filtering": json.dumps({"smart_bid_type": smart_bid_type}),
            "page": page,
            "page_size": page_size,
        },
    )
    payload = data.get("data") if isinstance(data, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    ad_list = payload.get("ad_list") or []
    return {
        "code": data.get("code") if isinstance(data, dict) else None,
        "message": data.get("message") if isinstance(data, dict) else None,
        "request_id": data.get("request_id") if isinstance(data, dict) else None,
        "advertiser_id": advertiser_id,
        "shop": selected_shop,
        "marketing_goal": marketing_goal,
        "smart_bid_type": smart_bid_type,
        "planSmartBidTypes": [smart_bid_type],
        "page_info": payload.get("page_info") or {},
        "plans": [normalize_uni_plan(item, selected_shop=selected_shop) for item in ad_list],
        "raw": data,
    }


def qianchuan_visible_plans(query, user):
    start_default, end_default = bj_today_range()
    marketing_goal = str_param(query, "marketing_goal", "VIDEO_PROM_GOODS")
    smart_bid_types = query_plan_smart_bid_types(query, default=PLAN_SMART_BID_TYPES)
    page = max(1, int_param(query, "page", 1))
    page_size = max(1, min(500, int_param(query, "page_size", 100)))
    start_time = str_param(query, "start_time", start_default)
    end_time = str_param(query, "end_time", end_default)
    selected_shop = select_shop_for_request(
        user,
        advertiser_id=str_param(query, "advertiser_id", ""),
        shop_id=str_param(query, "shop_id", ""),
    )
    source_shops = [selected_shop] if selected_shop and (query.get("shop_id") or query.get("advertiser_id")) else allowed_shops_for_user(user)
    all_plans = []
    request_ids = []
    api_code = 0
    api_message = "OK"
    for shop in source_shops:
        for smart_bid_type in smart_bid_types:
            plans, total, result = fetch_shop_plans_for_summary(shop, start_time, end_time, marketing_goal, smart_bid_type)
            all_plans.extend(plans)
            if isinstance(result, dict):
                if result.get("request_id"):
                    request_ids.append(result.get("request_id"))
                if result.get("code") not in (0, None):
                    api_code = result.get("code")
                    api_message = result.get("message")
    all_plans = dedupe_plans(all_plans)
    visible = filter_plans_for_user(all_plans, user)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "code": api_code,
        "message": api_message,
        "request_id": ",".join(str(item) for item in request_ids if item),
        "advertiser_id": source_shops[0]["advertiserId"] if source_shops else DEFAULT_ADVERTISER_ID,
        "shop": source_shops[0] if len(source_shops) == 1 else None,
        "shops": source_shops,
        "marketing_goal": marketing_goal,
        "planSmartBidTypes": smart_bid_types,
        "page_info": {
            "page": page,
            "page_size": page_size,
            "total_num": len(visible),
            "total_page": max(1, (len(visible) + page_size - 1) // page_size),
        },
        "plans": visible[start:end],
        "raw": {"source_plan_count": len(all_plans), "visible_plan_count": len(visible), "planSmartBidTypes": smart_bid_types},
    }


def qianchuan_visible_plan_pages(query, user):
    result = qianchuan_visible_plans(query, user)
    page_info = dict(result.get("page_info") or {})
    plans = list(result.get("plans") or [])
    current_page = int(number(page_info.get("page"), number((query.get("page") or [1])[0], 1)) or 1)
    page_size = int(number(page_info.get("page_size"), number((query.get("page_size") or [500])[0], 500)) or 500)
    total_page = int(number(page_info.get("total_page"), 0) or 0)
    total_num = int(number(page_info.get("total_num"), len(plans)) or len(plans))
    if total_page <= 0 and page_size > 0:
        total_page = max(1, (total_num + page_size - 1) // page_size)
    for page in range(current_page + 1, total_page + 1):
        next_query = {key: list(value) if isinstance(value, list) else value for key, value in query.items()}
        next_query["page"] = [str(page)]
        next_result = qianchuan_visible_plans(next_query, user)
        plans.extend(next_result.get("plans") or [])
    merged = dict(result)
    merged["plans"] = plans
    merged["page_info"] = {
        **page_info,
        "page": current_page,
        "page_size": page_size,
        "total_num": total_num,
        "total_page": total_page,
        "fetched_pages": total_page - current_page + 1 if total_page >= current_page else 1,
        "fetched_plan_count": len(plans),
    }
    return merged


def page_total(page_info):
    if not isinstance(page_info, dict):
        return 0
    for key in ("total_num", "total_number", "total_count", "total"):
        value = page_info.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def fetch_shop_plans_for_summary(shop, start_time, end_time, marketing_goal="VIDEO_PROM_GOODS", smart_bid_type="SMART_BID_CUSTOM"):
    smart_bid_type = normalize_plan_smart_bid_type(smart_bid_type) or CONTROL_PLAN_SMART_BID_TYPES[0]
    plans = []
    page = 1
    page_size = 100
    total = 0
    last_result = None
    while page <= 20:
        query = {
            "advertiser_id": [str(shop["advertiserId"])],
            "marketing_goal": [marketing_goal],
            "smart_bid_type": [smart_bid_type],
            "page": [str(page)],
            "page_size": [str(page_size)],
            "start_time": [start_time],
            "end_time": [end_time],
        }
        result = qianchuan_plans(query, selected_shop=shop)
        last_result = result
        if result.get("code") != 0:
            break
        batch = result.get("plans") or []
        plans.extend(batch)
        total = page_total(result.get("page_info"))
        if not batch or (total and len(plans) >= total):
            break
        page += 1
    return plans, total or len(plans), last_result


def ensure_plan_action_allowed(user, shop, ad_id, marketing_goal="VIDEO_PROM_GOODS", plan_smart_bid_types=None):
    if user and user.get("role") == "admin":
        return True, None, None
    start_time, end_time = bj_today_range()
    smart_bid_types = normalize_plan_smart_bid_types(plan_smart_bid_types, default=PLAN_SMART_BID_TYPES)
    for smart_bid_type in smart_bid_types:
        plans, _total, _result = fetch_shop_plans_for_summary(shop, start_time, end_time, marketing_goal, smart_bid_type)
        for plan in plans:
            try:
                if int(plan.get("id") or 0) != int(ad_id):
                    continue
            except (TypeError, ValueError):
                continue
            if plan_belongs_to_user(plan, user):
                return True, None, plan
            return False, "no plan permission", plan
    return False, "plan not found or no plan permission", None


def truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def batched(items, size):
    size = max(1, int(size or 1))
    for index in range(0, len(items), size):
        yield items[index:index + size]


def reset_visible_plan_budgets(user, body):
    body = body if isinstance(body, dict) else {}
    marketing_goal = str(body.get("marketing_goal") or "VIDEO_PROM_GOODS")
    smart_bid_types = body_plan_smart_bid_types(body, default=PLAN_SMART_BID_TYPES)
    budget_targets, target_error = budget_reset_targets_from_body(body, smart_bid_types)
    if target_error:
        return None, target_error
    uniform_target = len({number(value) for value in budget_targets.values()}) == 1
    target_budget = next(iter(budget_targets.values())) if uniform_target else None
    dry_run = truthy(body.get("dryRun"))
    batch_size = min(10, max(1, int(number(body.get("batchSize"), CLOUD_BUDGET_RESET_BATCH_SIZE))))
    batch_sleep = max(0, number(body.get("batchSleepSeconds"), CLOUD_BUDGET_RESET_BATCH_SLEEP_SECONDS))
    start_time = str(body.get("start_time") or "")
    end_time = str(body.get("end_time") or "")
    if not start_time or not end_time:
        start_time, end_time = bj_today_range()

    all_plans = []
    source_errors = []
    for shop in allowed_shops_for_user(user):
        for smart_bid_type in smart_bid_types:
            plans, _total, result = [], 0, {}
            for attempt in range(CLOUD_BUDGET_RESET_MAX_RETRIES):
                plans, _total, result = fetch_shop_plans_for_summary(shop, start_time, end_time, marketing_goal, smart_bid_type)
                if not ocean_response_rate_limited(result) or attempt >= CLOUD_BUDGET_RESET_MAX_RETRIES - 1:
                    break
                time.sleep(CLOUD_BUDGET_RESET_RETRY_SLEEP_SECONDS * (attempt + 1))
            if isinstance(result, dict) and result.get("code") not in (None, 0):
                source_errors.append(
                    {
                        "shopId": shop.get("shopId"),
                        "advertiserId": shop.get("advertiserId"),
                        "smartBidType": smart_bid_type,
                        "response": result,
                    }
                )
                continue
            for plan in plans:
                item = annotate_plan_owner(plan)
                item.setdefault("shopId", shop.get("shopId"))
                item.setdefault("shopName", shop.get("shopName"))
                item.setdefault("advertiserId", shop.get("advertiserId"))
                all_plans.append(item)

    visible = filter_plans_for_user(all_plans, user)
    to_update_by_advertiser = {}
    skipped_count = 0
    limited_skip_count = 0
    missing_count = 0
    skipped_plans = []
    for plan in visible:
        ad_id = int(number(plan.get("id")))
        advertiser_id = int(number(plan.get("advertiserId")))
        if ad_id <= 0 or advertiser_id <= 0:
            missing_count += 1
            continue
        smart_bid_type = plan_smart_bid_type(plan)
        plan_target_budget = budget_targets.get(smart_bid_type)
        current_budget = number(plan.get("budget"))
        budget_delta = abs(current_budget - number(plan_target_budget))
        if budget_delta < 0.01:
            skipped_count += 1
            continue
        if budget_delta < CLOUD_BUDGET_RESET_MIN_CHANGE_AMOUNT:
            skipped_count += 1
            limited_skip_count += 1
            skipped_plans.append(
                {
                    "ad_id": ad_id,
                    "planName": plan.get("name") or "",
                    "smartBidType": smart_bid_type,
                    "currentBudget": current_budget,
                    "targetBudget": plan_target_budget,
                    "reason": "budget delta below minimum change amount",
                }
            )
            continue
        to_update_by_advertiser.setdefault(advertiser_id, []).append(
            {
                "ad_id": ad_id,
                "budget": plan_target_budget,
                "planName": plan.get("name") or "",
                "ownerPrefix": normalize_plan_prefix(plan.get("ownerPrefix")),
                "smartBidType": smart_bid_type,
                "currentBudget": current_budget,
            }
        )

    actions = []
    update_count = 0
    chunk_count = 0
    ok = not source_errors
    for advertiser_id, infos in sorted(to_update_by_advertiser.items()):
        for chunk in batched(infos, batch_size):
            chunk_count += 1
            update_infos = [{"ad_id": item["ad_id"], "budget": item["budget"]} for item in chunk]
            payload = {
                "advertiser_id": advertiser_id,
                "update_budget_infos": update_infos,
                "source": body.get("source") or "budget-reset",
            }
            if dry_run:
                response = {"code": 0, "message": "dry run"}
            else:
                response = ocean_post_with_retry("/open_api/v1.0/qianchuan/uni_promotion/ad/budget/update/", payload)
            response_ok = ocean_update_ok(response)
            ok = ok and response_ok
            update_count += len(update_infos)
            action = {
                "advertiserId": advertiser_id,
                "count": len(update_infos),
                "planIds": [item["ad_id"] for item in chunk],
                "planNames": [item["planName"] for item in chunk],
                "request": payload,
                "response": response,
                "ok": response_ok,
            }
            actions.append(action)
            log_action("reset-budgets", dry_run, payload, response)
            if not dry_run and batch_sleep > 0:
                time.sleep(batch_sleep)

    if not actions:
        log_action(
            "reset-budgets",
            dry_run,
            {"targetBudget": target_budget, "budgetTargets": budget_targets, "source": body.get("source") or "budget-reset"},
            {"code": 0 if ok else -1, "message": "no budget updates required", "sourceErrors": source_errors},
        )

    result = {
        "ok": ok,
        "dryRun": dry_run,
        "marketingGoal": marketing_goal,
        "planSmartBidTypes": smart_bid_types,
        "budgetTargets": budget_targets,
        "batchSize": batch_size,
        "totalPlans": len(visible),
        "updateCount": update_count,
        "skippedCount": skipped_count,
        "limitedSkipCount": limited_skip_count,
        "missingCount": missing_count,
        "chunkCount": chunk_count,
        "sourceErrors": source_errors,
        "skippedPlans": skipped_plans,
        "actions": actions,
    }
    if target_budget is not None:
        result["targetBudget"] = target_budget
    return result, None


def summarize_plans(plans):
    spend = round(sum(number(plan.get("spend")) for plan in plans), 2)
    gmv = round(sum(number(plan.get("gmv")) for plan in plans), 2)
    pay_gmv = round(sum(number(plan.get("payGmv")) for plan in plans), 2)
    settle_gmv = round(sum(number(plan.get("settleGmv")) for plan in plans), 2)
    real_settle_gmv = round(sum(number(plan.get("realSettleGmv")) for plan in plans), 2)
    refund_gmv = round(sum(number(plan.get("refundGmv")) for plan in plans), 2)
    orders = sum(int(number(plan.get("orders"))) for plan in plans)
    refund_orders = sum(int(number(plan.get("refundOrders"))) for plan in plans)
    budget = round(sum(number(plan.get("budget")) for plan in plans), 2)
    roi = round(gmv / spend, 4) if spend > 0 else 0
    return {
        "spend": spend,
        "gmv": gmv,
        "roi": roi,
        "payGmv": pay_gmv,
        "payRoi": round(pay_gmv / spend, 4) if spend > 0 else 0,
        "settleGmv": settle_gmv,
        "settleRoi": round(settle_gmv / spend, 4) if spend > 0 else 0,
        "realSettleGmv": real_settle_gmv,
        "refundGmv": refund_gmv,
        "refundOrders": refund_orders,
        "orders": orders,
        "budget": budget,
        "planCount": len(plans),
    }


def dashboard_summary(user, query):
    start_default, end_default = bj_today_range()
    start_time = str_param(query, "start_time", start_default)
    end_time = str_param(query, "end_time", end_default)
    marketing_goal = str_param(query, "marketing_goal", "VIDEO_PROM_GOODS")
    smart_bid_types = query_plan_smart_bid_types(query, default=PLAN_SMART_BID_TYPES)
    shops = allowed_shops_for_user(user)
    shop_summaries = []
    source_plans = []
    visible_plans = []
    for shop in shops:
        shop_plans = []
        total = 0
        api_code = None
        api_message = None
        for smart_bid_type in smart_bid_types:
            plans, type_total, result = fetch_shop_plans_for_summary(shop, start_time, end_time, marketing_goal, smart_bid_type)
            shop_plans.extend(plans)
            total += type_total
            if isinstance(result, dict):
                api_code = result.get("code") if result.get("code") is not None else api_code
                api_message = result.get("message") or api_message
        shop_plans = dedupe_plans(shop_plans)
        source_plans.extend(shop_plans)
        shop_visible_plans = filter_plans_for_user(shop_plans, user)
        visible_plans.extend(shop_visible_plans)
        summary = summarize_plans(shop_visible_plans)
        shop_summaries.append(
            {
                **summary,
                "shopId": shop["shopId"],
                "shopName": shop["shopName"],
                "advertiserId": shop["advertiserId"],
                "status": shop.get("status"),
                "totalPlans": total,
                "apiCode": api_code,
                "apiMessage": api_message,
            }
        )
    global_summary = summarize_plans(visible_plans)
    user_summaries = []
    if user.get("role") == "admin":
        for item in list_users():
            if item.get("role") == "admin":
                continue
            user_plans = filter_plans_for_user(source_plans, item)
            aggregate = summarize_plans(user_plans)
            user_summaries.append(
                {
                    **aggregate,
                    "userId": item["id"],
                    "username": item["username"],
                    "displayName": item["displayName"],
                    "role": item["role"],
                    "status": item["status"],
                    "planPrefixes": item.get("planPrefixes") or [],
                    "planAssignments": item.get("planAssignments") or [],
                    "shopCount": len({int(plan.get("shopId")) for plan in user_plans if plan.get("shopId")}),
                    "plans": user_plans,
                }
            )
    else:
        user_summaries.append(
            {
                **global_summary,
                "userId": user["id"],
                "username": user["username"],
                "displayName": user["displayName"],
                "role": user["role"],
                "status": user["status"],
                "planPrefixes": user.get("planPrefixes") or [],
                "planAssignments": user.get("planAssignments") or [],
                "plans": visible_plans,
            }
        )
    return {
        "range": {"startTime": start_time, "endTime": end_time, "marketingGoal": marketing_goal, "planSmartBidTypes": smart_bid_types},
        "scope": "all" if user.get("role") == "admin" else "plan-prefix",
        "global": {
            **global_summary,
            "shopCount": len([shop for shop in shop_summaries if (shop.get("planCount") or 0) > 0]),
            "ownerCount": len({plan.get("ownerPrefix") for plan in visible_plans if plan.get("ownerPrefix")}),
        },
        "shops": shop_summaries,
        "users": user_summaries,
        "plans": visible_plans,
        "planPrefixOptions": plan_prefix_options(),
    }


def plan_net_gmv(plan):
    if not isinstance(plan, dict):
        return 0
    for key in ("realSettleGmv", "settleGmv", "gmv"):
        if key in plan and plan.get(key) not in (None, ""):
            return number(plan.get(key))
    return 0


def plan_net_roi(plan):
    if not isinstance(plan, dict):
        return 0
    if plan.get("roi") not in (None, ""):
        return number(plan.get("roi"))
    spend = number(plan.get("spend"))
    net_gmv = plan_net_gmv(plan)
    return net_gmv / spend if spend > 0 else 0


def plan_identity_for_rule(plan):
    try:
        plan_id = int(number(plan.get("id")))
    except (TypeError, ValueError):
        plan_id = 0
    try:
        advertiser_id = int(number(plan.get("advertiserId") or plan.get("advertiser_id") or DEFAULT_ADVERTISER_ID))
    except (TypeError, ValueError):
        advertiser_id = 0
    return advertiser_id, plan_id


def evaluate_spend_step_roi_rule(plan, rule, now=None):
    spend_step = number(rule.get("spendStep") or rule.get("minSpend"))
    roi_below = number(rule.get("roiBelow"))
    if spend_step <= 0 or roi_below <= 0:
        return None
    spend = number(plan.get("spend"))
    if spend < spend_step:
        return None
    advertiser_id, plan_id = plan_identity_for_rule(plan)
    if advertiser_id <= 0 or plan_id <= 0:
        return None

    ensure_db()
    now_dt = parse_utc_datetime(now)
    now_text = now_dt.isoformat()
    net_gmv = plan_net_gmv(plan)
    rule_id = str(rule.get("id") or "")
    delay_minutes = max(0, number(rule.get("delayMinutes"), 10))

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            select last_spend, last_gmv from rule_plan_spend_cursors
            where rule_id = ? and advertiser_id = ? and plan_id = ?
            """,
            (rule_id, advertiser_id, plan_id),
        ).fetchone()
        if not cursor:
            conn.execute(
                """
                insert into rule_plan_spend_cursors(rule_id, advertiser_id, plan_id, last_spend, last_gmv, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (rule_id, advertiser_id, plan_id, spend, net_gmv, now_text),
            )
            return None

        pending = conn.execute(
            """
            select * from rule_plan_spend_checks
            where rule_id = ? and advertiser_id = ? and plan_id = ? and status = 'pending'
            order by due_at limit 1
            """,
            (rule_id, advertiser_id, plan_id),
        ).fetchone()
        if pending:
            due_dt = parse_utc_datetime(pending["due_at"])
            if now_dt < due_dt:
                return None
            delta_spend = max(0, number(pending["trigger_spend"]) - number(pending["start_spend"]))
            delta_gmv = max(0, net_gmv - number(pending["start_gmv"]))
            delta_roi = delta_gmv / delta_spend if delta_spend > 0 else 0
            checkpoint = {
                "bucketIndex": pending["bucket_index"],
                "startSpend": number(pending["start_spend"]),
                "triggerSpend": number(pending["trigger_spend"]),
                "deltaSpend": round(delta_spend, 4),
                "deltaGmv": round(delta_gmv, 4),
                "deltaRoi": round(delta_roi, 4),
                "dueAt": pending["due_at"],
            }
            conn.execute(
                """
                update rule_plan_spend_checks
                set status = 'evaluated', evaluated_at = ?, delta_spend = ?, delta_gmv = ?, delta_roi = ?, response_json = ?
                where rule_id = ? and advertiser_id = ? and plan_id = ? and bucket_index = ?
                """,
                (
                    now_text,
                    delta_spend,
                    delta_gmv,
                    delta_roi,
                    json.dumps(checkpoint, ensure_ascii=False),
                    rule_id,
                    advertiser_id,
                    plan_id,
                    pending["bucket_index"],
                ),
            )
            if delta_roi < roi_below:
                return {
                    "plan": plan,
                    "rule": rule,
                    "checkpoint": checkpoint,
                    "reason": f"incremental net ROI {delta_roi:.2f} below {roi_below:.2f} after {delta_spend:.2f} spend",
                }
            return None

        last_spend = number(cursor["last_spend"])
        last_gmv = number(cursor["last_gmv"])
        if spend < last_spend:
            conn.execute(
                """
                update rule_plan_spend_cursors set last_spend = ?, last_gmv = ?, updated_at = ?
                where rule_id = ? and advertiser_id = ? and plan_id = ?
                """,
                (spend, net_gmv, now_text, rule_id, advertiser_id, plan_id),
            )
            return None

        if spend - last_spend < spend_step:
            conn.execute(
                """
                update rule_plan_spend_cursors set last_gmv = ?, updated_at = ?
                where rule_id = ? and advertiser_id = ? and plan_id = ?
                """,
                (net_gmv, now_text, rule_id, advertiser_id, plan_id),
            )
            return None

        next_bucket = conn.execute(
            """
            select coalesce(max(bucket_index), 0) + 1 from rule_plan_spend_checks
            where rule_id = ? and advertiser_id = ? and plan_id = ?
            """,
            (rule_id, advertiser_id, plan_id),
        ).fetchone()[0]
        due_at = (now_dt + dt.timedelta(minutes=delay_minutes)).isoformat()
        conn.execute(
            """
            insert into rule_plan_spend_checks(
                rule_id, advertiser_id, plan_id, bucket_index, status, triggered_at, due_at,
                start_spend, start_gmv, trigger_spend, trigger_gmv
            )
            values (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (rule_id, advertiser_id, plan_id, next_bucket, now_text, due_at, last_spend, last_gmv, spend, net_gmv),
        )
        conn.execute(
            """
            update rule_plan_spend_cursors set last_spend = ?, last_gmv = ?, updated_at = ?
            where rule_id = ? and advertiser_id = ? and plan_id = ?
            """,
            (spend, net_gmv, now_text, rule_id, advertiser_id, plan_id),
        )
    return None


def daily_budget_remaining_percent(plan):
    budget = number(plan.get("budget"))
    if budget <= 0:
        return None
    spend = max(0, number(plan.get("spend")))
    remaining = max(0, budget - spend)
    return remaining / budget * 100


def evaluate_near_budget_roi_add_budget_rule(plan, rule):
    threshold = number(rule.get("budgetRemainingPercent"))
    roi_threshold = number(rule.get("roiAbove"))
    increment = number(rule.get("budgetValue"))
    if threshold <= 0 or roi_threshold <= 0 or increment <= 0:
        return None
    remaining_percent = daily_budget_remaining_percent(plan)
    if remaining_percent is None or remaining_percent > threshold:
        return None
    roi = plan_net_roi(plan)
    if roi <= roi_threshold:
        return None
    return {
        "plan": plan,
        "rule": rule,
        "budgetRemainingPercent": remaining_percent,
        "reason": (
            f"daily budget remaining {remaining_percent:.2f}% <= {threshold:.2f}%, "
            f"net settle ROI {roi:.2f} above {roi_threshold:.2f}"
        ),
    }


def plan_elapsed_minutes(plan, now=None):
    elapsed = number(plan.get("elapsedMinutes"), -1)
    if elapsed > 0:
        return elapsed
    create_time = plan.get("createTime") or plan.get("startTime")
    if not create_time:
        return 0
    try:
        created = parse_utc_datetime(str(create_time).replace(" ", "T"))
    except (TypeError, ValueError):
        return 0
    now_dt = parse_utc_datetime(now)
    return max(0, (now_dt - created).total_seconds() / 60)


def plan_hourly_spend(plan, now=None):
    elapsed = plan_elapsed_minutes(plan, now=now)
    if elapsed <= 0:
        return None
    return number(plan.get("spend")) / (elapsed / 60)


def next_roi_goal_for_rule(plan, rule):
    current_goal = number(plan.get("roiGoal"))
    increment = number(rule.get("roiGoalIncrement"))
    max_goal = number(rule.get("maxRoiGoal"), 2.4) or 2.4
    if current_goal <= 0 or increment <= 0:
        return None
    if current_goal >= max_goal:
        return None
    return round(min(max_goal, current_goal + increment), 4)


def evaluate_hourly_spend_increase_roi_goal_rule(plan, rule, now=None):
    threshold = number(rule.get("hourlySpendAbove"))
    new_goal = next_roi_goal_for_rule(plan, rule)
    if threshold <= 0 or new_goal is None:
        return None
    hourly_spend = plan_hourly_spend(plan, now=now)
    if hourly_spend is None or hourly_spend <= threshold:
        return None
    current_goal = number(plan.get("roiGoal"))
    return {
        "plan": plan,
        "rule": rule,
        "hourlySpend": hourly_spend,
        "currentRoiGoal": current_goal,
        "newRoiGoal": new_goal,
        "reason": (
            f"hourly spend {hourly_spend:.2f} above {threshold:.2f}, "
            f"ROI goal {current_goal:.2f} -> {new_goal:.2f}"
        ),
    }


def next_budget_for_rule(plan, rule):
    current_budget = number(plan.get("budget"))
    amount = number(rule.get("budgetValue"))
    if rule.get("budgetMode") == "percent":
        return round(current_budget * (1 + amount / 100), 2)
    return round(current_budget + amount, 2)


def response_contains_any(data, keywords):
    text = json.dumps(data, ensure_ascii=False).lower()
    return any(keyword.lower() in text for keyword in keywords)


def account_month_budget_insufficient_response(response):
    return response_contains_any(
        response,
        ["账户月预算不足", "月预算不足", "账户预算不足", "余额不足", "预算不足", "insufficient"],
    )


def budget_insufficient_notify_action(plan, rule, payload, response):
    notify_rule = dict(rule)
    notify_rule["id"] = f"{rule.get('id') or 'rule'}-budget-insufficient"
    notify_rule["name"] = f"{rule.get('name') or '预算规则'} 账户月预算提醒"
    notify_rule["action"] = "NOTIFY"
    notify_payload = {
        "plan_id": plan.get("id"),
        "rule_id": rule.get("id"),
        "action": "NOTIFY",
        "reason": "account_month_budget_insufficient",
        "failed_request": payload,
        "failed_response": response,
    }
    notify_response = {"code": 0, "message": "account month budget insufficient notification queued"}
    return {"plan": plan, "rule": notify_rule, "request": notify_payload, "response": notify_response}


def evaluate_rule(plan, rule, now=None):
    if rule_is_deleted(rule):
        return None
    if not rule.get("enabled"):
        return None
    if not rule_applies_to_plan_smart_bid_type(plan, rule):
        return None
    if rule.get("action") == "SPEND_STEP_ROI_STOP":
        return evaluate_spend_step_roi_rule(plan, rule, now=now)
    if rule.get("action") == "NEAR_BUDGET_ROI_ADD_BUDGET":
        return evaluate_near_budget_roi_add_budget_rule(plan, rule)
    if rule.get("action") == "HOURLY_SPEND_INCREASE_ROI_GOAL":
        return evaluate_hourly_spend_increase_roi_goal_rule(plan, rule, now=now)
    after_minutes = number(rule.get("afterMinutes"))
    if after_minutes > 0 and plan_elapsed_minutes(plan, now=now) < after_minutes:
        return None
    if number(plan.get("spend")) < number(rule.get("minSpend")):
        return None
    roi = plan_net_roi(plan)
    if number(rule.get("roiBelow")) > 0 and roi < number(rule.get("roiBelow")):
        return {"plan": plan, "rule": rule, "reason": f"net settle ROI {roi:.2f} below {number(rule.get('roiBelow')):.2f}"}
    if number(rule.get("roiAbove")) > 0 and roi > number(rule.get("roiAbove")):
        return {"plan": plan, "rule": rule, "reason": f"net settle ROI {roi:.2f} above {number(rule.get('roiAbove')):.2f}"}
    return None


def rule_is_pause_action(rule):
    return (rule.get("action") or "") in {"DISABLE", "SPEND_STEP_ROI_STOP"}


def operation_board_date(query=None, now=None):
    values = query_values(query or {}, "date", "day")
    if values:
        try:
            return dt.date.fromisoformat(str(values[0])[:10]).isoformat()
        except ValueError:
            pass
    return beijing_datetime(now).date().isoformat()


def beijing_date_utc_range(day):
    bj_tz = dt.timezone(dt.timedelta(hours=8))
    start_bj = dt.datetime.fromisoformat(day).replace(tzinfo=bj_tz)
    end_bj = start_bj + dt.timedelta(days=1)
    return start_bj.astimezone(dt.timezone.utc).isoformat(), end_bj.astimezone(dt.timezone.utc).isoformat()


def request_plan_ids(payload):
    payload = payload if isinstance(payload, dict) else {}
    ids = []
    for key in ("ad_id", "plan_id", "id"):
        value = int(number(payload.get(key), 0))
        if value > 0:
            ids.append(value)
    for key in ("ad_ids", "plan_ids"):
        value = payload.get(key)
        if isinstance(value, list):
            ids.extend(int(number(item, 0)) for item in value if int(number(item, 0)) > 0)
    for key in ("data", "update_infos", "update_budget_infos", "roi_goal_updates"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for field in ("ad_id", "plan_id", "id"):
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


def action_response_ok(response):
    response = response if isinstance(response, dict) else {}
    if "ok" in response:
        return bool(response.get("ok"))
    return ocean_update_ok(response)


def action_is_auto_pause(action):
    action = action if isinstance(action, dict) else {}
    rule = action.get("rule") if isinstance(action.get("rule"), dict) else {}
    request_data = action.get("request") if isinstance(action.get("request"), dict) else {}
    if rule_is_pause_action(rule):
        return True
    if str(request_data.get("opt_status") or "").upper() == "DISABLE":
        return True
    data = request_data.get("data")
    if isinstance(data, list):
        return any(str(item.get("opt_status") or "").upper() == "DISABLE" for item in data if isinstance(item, dict))
    return False


def successful_enable_events_since(start_utc):
    events = []
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            select created_at, request_json, response_json
            from control_action_logs
            where action = 'enable' and created_at >= ?
            order by created_at asc
            """,
            (start_utc,),
        ).fetchall()
    for created_at, request_json, response_json in rows:
        request_data = json_loads(request_json, {})
        response = json_loads(response_json, {})
        if not action_response_ok(response):
            continue
        for plan_id in request_plan_ids(request_data):
            events.append({"planId": plan_id, "createdAt": created_at, "request": request_data, "response": response})
    return events


def operation_board_summary(user, query=None, now=None):
    day = operation_board_date(query, now)
    start_utc, end_utc = beijing_date_utc_range(day)
    restore_events = successful_enable_events_since(start_utc)
    records = []

    with sqlite3.connect(DB_PATH) as conn:
        job_rows = conn.execute(
            """
            select started_at, finished_at, request_json, response_json
            from scheduled_job_runs
            where job_name = 'step-roi-rules' and started_at >= ? and started_at < ?
            order by started_at desc
            """,
            (start_utc, end_utc),
        ).fetchall()
        reset_rows = conn.execute(
            """
            select run_key, status, started_at, finished_at, request_json, response_json, error_text
            from scheduled_job_runs
            where job_name = 'daily-budget-reset' and (run_key = ? or (started_at >= ? and started_at < ?))
            order by started_at desc
            """,
            (day, start_utc, end_utc),
        ).fetchall()

    for started_at, finished_at, _request_json, response_json in job_rows:
        response_data = json_loads(response_json, {})
        for action in response_data.get("actions") or []:
            if not isinstance(action, dict) or not action_is_auto_pause(action):
                continue
            if not action_response_ok(action.get("response")):
                continue
            plan = action.get("plan") if isinstance(action.get("plan"), dict) else {}
            plan = annotate_plan_owner(dict(plan))
            plan_ids = action_plan_ids(action)
            plan_id = int(number(plan.get("id"), plan_ids[0] if plan_ids else 0))
            if plan_id <= 0:
                continue
            plan["id"] = plan_id
            if not filter_plans_for_user([plan], user):
                continue
            restored_event = next(
                (item for item in restore_events if item["planId"] == plan_id and item["createdAt"] >= started_at),
                None,
            )
            rule = action.get("rule") if isinstance(action.get("rule"), dict) else {}
            request_data = action.get("request") if isinstance(action.get("request"), dict) else {}
            smart_bid_type = plan_smart_bid_type(plan)
            record = {
                "key": f"{plan_id}-{started_at}",
                "planId": plan_id,
                "planName": plan.get("name") or f"计划 {plan_id}",
                "product": plan.get("product") or "",
                "ownerPrefix": normalize_plan_prefix(plan.get("ownerPrefix")),
                "ownerName": plan.get("ownerName") or "",
                "shopId": plan.get("shopId"),
                "advertiserId": plan.get("advertiserId") or request_data.get("advertiser_id"),
                "marketingGoal": plan.get("marketingGoal") or request_data.get("marketing_goal") or "VIDEO_PROM_GOODS",
                "smartBidType": smart_bid_type,
                "smartBidLabel": plan_smart_bid_label(smart_bid_type),
                "ruleId": rule.get("id") or "",
                "ruleName": rule.get("name") or rule.get("action") or "自动止损",
                "ruleAction": rule.get("action") or "",
                "pausedAt": started_at,
                "finishedAt": finished_at,
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

    budget_runs = []
    for run_key, status, started_at, finished_at, request_json, response_json, error_text in reset_rows:
        request_data = json_loads(request_json, {})
        response_data = json_loads(response_json, {})
        budget_runs.append(
            {
                "runKey": run_key,
                "status": status,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "targetBudget": response_data.get("targetBudget") or request_data.get("budget"),
                "budgetTargets": response_data.get("budgetTargets") or request_data.get("budgetTargets") or {},
                "planSmartBidTypes": response_data.get("planSmartBidTypes") or request_data.get("planSmartBidTypes") or [],
                "totalPlans": response_data.get("totalPlans", 0),
                "updateCount": response_data.get("updateCount", 0),
                "skippedCount": response_data.get("skippedCount", 0),
                "limitedSkipCount": response_data.get("limitedSkipCount", 0),
                "chunkCount": response_data.get("chunkCount", 0),
                "sourceErrors": response_data.get("sourceErrors") or [],
                "ok": bool(response_data.get("ok")) if isinstance(response_data, dict) and "ok" in response_data else status == "success",
                "error": error_text or response_data.get("error") or "",
            }
        )

    return {
        "ok": True,
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
            "latest": budget_runs[0] if budget_runs else None,
        },
    }


def rule_execution_priority(rule):
    action = rule.get("action") or ""
    if action in {"DISABLE", "SPEND_STEP_ROI_STOP"}:
        return 0
    if action in {"ADD_BUDGET", "NEAR_BUDGET_ROI_ADD_BUDGET"}:
        return 20
    if action == "HOURLY_SPEND_INCREASE_ROI_GOAL":
        return 30
    if action == "NOTIFY":
        return 40
    return 50


def plan_is_enabled_for_rule_execution(plan):
    status = str(plan.get("optStatus") or plan.get("opt_status") or "").upper()
    if not status:
        return True
    return status == "ENABLE"


def html_page(title, body):
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:Arial,sans-serif;max-width:760px;margin:48px auto;line-height:1.6}"
        "code{background:#f3f4f6;padding:2px 5px;border-radius:4px}</style>"
        "</head><body>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    ).encode("utf-8")


def bootstrap_admin_user():
    ensure_db()
    admin_row = get_user_by_username(BOOTSTRAP_ADMIN_USERNAME)
    if admin_row:
        with sqlite3.connect(DB_PATH) as conn:
            return public_user(admin_row, [], user_plan_prefixes(conn, admin_row["id"], admin_row))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from users where role = 'admin' order by id limit 1").fetchone()
        if row:
            return public_user(row, [], user_plan_prefixes(conn, row["id"], row))
    return None


def execute_rules_for_user(user, body):
    body = body if isinstance(body, dict) else {}
    rules = [
        rule
        for rule in filter_rules_for_run_request(filter_rules_for_user(load_rules(), user), body)
        if not rule_is_deleted(rule)
    ]
    rules = sorted(rules, key=rule_execution_priority)
    if not rules:
        return {"ok": True, "plans": {"total": 0}, "actions": []}
    smart_bid_types = body_plan_smart_bid_types(body, default=plan_smart_bid_types_for_rules(rules))
    query_like = {
        "marketing_goal": [body.get("marketing_goal") or "VIDEO_PROM_GOODS"],
        "plan_smart_bid_types": smart_bid_types,
        "page": [str(body.get("page") or 1)],
        "page_size": [str(body.get("page_size") or 500)],
    }
    if body.get("start_time"):
        query_like["start_time"] = [body["start_time"]]
    if body.get("end_time"):
        query_like["end_time"] = [body["end_time"]]
    plans_result = qianchuan_visible_plan_pages(query_like, user)
    actions = []
    for plan in plans_result.get("plans") or []:
        if not plan_is_enabled_for_rule_execution(plan):
            continue
        for rule in rules:
            scoped_prefixes = normalize_plan_prefixes(rule.get("planPrefixes") or [])
            if scoped_prefixes and normalize_plan_prefix(plan.get("ownerPrefix")) not in scoped_prefixes:
                continue
            hit = evaluate_rule(plan, rule)
            if not hit:
                continue
            advertiser_id = int(plan.get("advertiserId") or plans_result.get("advertiser_id") or DEFAULT_ADVERTISER_ID)
            if rule.get("action") in {"DISABLE", "SPEND_STEP_ROI_STOP"}:
                payload = {
                    "advertiser_id": advertiser_id,
                    "ad_ids": [int(plan["id"])],
                    "opt_status": "DISABLE",
                }
                response = ocean_post("/open_api/v1.0/qianchuan/uni_promotion/ad/status/update/", payload)
            elif rule.get("action") in {"ADD_BUDGET", "NEAR_BUDGET_ROI_ADD_BUDGET"}:
                new_budget = next_budget_for_rule(plan, rule)
                payload = {
                    "advertiser_id": advertiser_id,
                    "update_budget_infos": [{"ad_id": int(plan["id"]), "budget": new_budget}],
                }
                response = ocean_post("/open_api/v1.0/qianchuan/uni_promotion/ad/budget/update/", payload)
            elif rule.get("action") == "HOURLY_SPEND_INCREASE_ROI_GOAL":
                new_roi_goal = hit.get("newRoiGoal") or next_roi_goal_for_rule(plan, rule)
                payload = {
                    "advertiser_id": advertiser_id,
                    "roi_goal_updates": [{"ad_id": int(plan["id"]), "roi_goal": new_roi_goal}],
                }
                response = ocean_post("/open_api/v1.0/qianchuan/roi/goal/update/", payload)
            else:
                payload = {"plan_id": plan.get("id"), "rule_id": rule.get("id"), "action": "NOTIFY"}
                response = {"code": 0, "message": "notification queued in action log"}
            log_action("pause" if rule.get("action") in {"DISABLE", "SPEND_STEP_ROI_STOP"} else (rule.get("action") or "rule"), False, payload, response)
            actions.append({"plan": plan, "rule": rule, "request": payload, "response": response})
            if rule.get("action") == "NEAR_BUDGET_ROI_ADD_BUDGET" and account_month_budget_insufficient_response(response):
                notify_action = budget_insufficient_notify_action(plan, rule, payload, response)
                log_action("notify", False, notify_action["request"], notify_action["response"])
                actions.append(notify_action)
            if rule_is_pause_action(rule):
                break
    return {"ok": True, "plans": plans_result.get("page_info"), "actions": actions}


def run_cloud_budget_reset_once(now=None):
    run_key = daily_budget_reset_run_key(now)
    budget_targets = default_budget_reset_targets()
    request_data = {
        "budgetTargets": budget_targets,
        "source": "cloud-scheduler-daily-budget-reset",
        "planSmartBidTypes": list(budget_targets.keys()),
        "batchSize": CLOUD_BUDGET_RESET_BATCH_SIZE,
        "batchSleepSeconds": CLOUD_BUDGET_RESET_BATCH_SLEEP_SECONDS,
    }
    if not run_key:
        return {"ok": True, "skipped": True, "reason": "outside midnight window"}
    if not claim_scheduled_job("daily-budget-reset", run_key, request_data):
        return {"ok": True, "skipped": True, "reason": "already claimed", "runKey": run_key}
    try:
        user = bootstrap_admin_user()
        if not user:
            raise RuntimeError("admin user not available")
        result, error = reset_visible_plan_budgets(user, request_data)
        if error:
            raise RuntimeError(error)
        finish_scheduled_job("daily-budget-reset", run_key, "success" if result.get("ok") else "failed", result)
        return result
    except Exception as exc:
        error_text = str(exc)
        finish_scheduled_job("daily-budget-reset", run_key, "failed", {}, error_text)
        log_action("scheduler-error", False, request_data, {"job": "daily-budget-reset", "error": error_text})
        return {"ok": False, "error": error_text, "runKey": run_key}


def run_cloud_step_roi_rules_once(now=None):
    run_key = interval_run_key(now, CLOUD_STEP_ROI_INTERVAL_SECONDS)
    request_data = {
        "marketing_goal": "VIDEO_PROM_GOODS",
        "page": 1,
        "page_size": 500,
        "ruleActions": CLOUD_AUTO_RULE_ACTIONS,
        "source": "cloud-scheduler-step-roi-rules",
    }
    if not claim_scheduled_job("step-roi-rules", run_key, request_data):
        return {"ok": True, "skipped": True, "reason": "already claimed", "runKey": run_key}
    try:
        user = bootstrap_admin_user()
        if not user:
            raise RuntimeError("admin user not available")
        result = execute_rules_for_user(user, request_data)
        finish_scheduled_job("step-roi-rules", run_key, "success" if result.get("ok") else "failed", result)
        return result
    except Exception as exc:
        error_text = str(exc)
        finish_scheduled_job("step-roi-rules", run_key, "failed", {}, error_text)
        log_action("scheduler-error", False, request_data, {"job": "step-roi-rules", "error": error_text})
        return {"ok": False, "error": error_text, "runKey": run_key}


def cloud_scheduler_loop():
    while True:
        try:
            run_cloud_budget_reset_once()
            run_cloud_step_roi_rules_once()
        except Exception as exc:
            log_action("scheduler-error", False, {"loop": "cloud-scheduler"}, {"error": str(exc)})
        time.sleep(max(10, CLOUD_SCHEDULER_POLL_SECONDS))


def start_cloud_scheduler():
    if not CLOUD_SCHEDULER_ENABLED:
        print("qianchuan cloud scheduler disabled", flush=True)
        return None
    thread = threading.Thread(target=cloud_scheduler_loop, name="qianchuan-cloud-scheduler", daemon=True)
    thread.start()
    print("qianchuan cloud scheduler started", flush=True)
    return thread


class Handler(BaseHTTPRequestHandler):
    server_version = "qianchuan-oauth/1.0"

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
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_OPTIONS(self):
        self.send_bytes(204, b"")

    def read_json_body(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def require_control_auth(self):
        if not CONTROL_TOKEN:
            return True
        return hmac.compare_digest(self.headers.get("X-QC-Admin-Token") or "", CONTROL_TOKEN)

    def bearer_token(self):
        value = self.headers.get("Authorization") or ""
        if value.lower().startswith("bearer "):
            return value.split(" ", 1)[1].strip()
        return ""

    def current_user(self):
        user = user_from_session(self.bearer_token())
        if user:
            return user
        if self.require_control_auth():
            admin = get_user_by_username(BOOTSTRAP_ADMIN_USERNAME)
            if admin:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("select * from users where id = ?", (admin["id"],)).fetchone()
                    return public_user(row, [], user_plan_prefixes(conn, row["id"], row))
            return {
                "id": 0,
                "username": "token-admin",
                "displayName": "本地管理员",
                "role": "admin",
                "status": "active",
                "permissions": role_permissions("admin"),
                "shopIds": [],
                "planPrefixes": list(PLAN_PREFIX_OWNERS.keys()),
                "planAssignments": plan_prefix_options(),
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        return None

    def require_user(self):
        user = self.current_user()
        if not user:
            self.send_forbidden()
            return None
        return user

    def require_admin_user(self):
        user = self.require_user()
        if not user:
            return None
        if not can_manage_admin(user):
            self.send_forbidden()
            return None
        return user

    def selected_shop(self, user, query=None, body=None):
        query = query or {}
        body = body or {}
        advertiser_id = body.get("advertiser_id") or body.get("advertiserId")
        shop_id = body.get("shop_id") or body.get("shopId")
        if query:
            advertiser_id = (query.get("advertiser_id") or query.get("advertiserId") or [advertiser_id])[0]
            shop_id = (query.get("shop_id") or query.get("shopId") or [shop_id])[0]
        shop = select_shop_for_request(user, advertiser_id=advertiser_id, shop_id=shop_id)
        if not shop:
            self.send_json(403, {"error": "no source account available"})
            return None
        return shop

    def send_forbidden(self):
        return self.send_json(403, {"error": "forbidden"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/healthz":
            return self.send_bytes(200, b"qianchuan-oauth ok\n")
        if parsed.path == "/api/oceanengine/oauth/auth-url":
            return self.send_json(200, {"app_id": APP_ID, "redirect_uri": REDIRECT_URI, "auth_url": auth_url()})
        if parsed.path == "/api/oceanengine/oauth/latest":
            if not ADMIN_TOKEN or self.headers.get("X-QC-Admin-Token") != ADMIN_TOKEN:
                return self.send_json(403, {"error": "forbidden"})
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "select id, created_at, state, exchange_status, exchange_response_json from callbacks order by id desc limit 1"
                ).fetchone()
            return self.send_json(200, {"latest": row})
        if parsed.path == "/api/me":
            user = self.require_user()
            if not user:
                return
            return self.send_json(
                200,
                {"user": user, "shops": allowed_shops_for_user(user), "planPrefixOptions": plan_prefix_options()},
            )
        if parsed.path == "/api/shops":
            user = self.require_user()
            if not user:
                return
            return self.send_json(200, {"shops": allowed_shops_for_user(user), "planPrefixOptions": plan_prefix_options()})
        if parsed.path == "/api/rule-groups":
            user = self.require_user()
            if not user:
                return
            groups = list_rule_groups()
            return self.send_json(200, {"groups": groups})
        if parsed.path == "/api/admin/users":
            user = self.require_admin_user()
            if not user:
                return
            return self.send_json(200, {"users": list_users()})
        if parsed.path.startswith("/api/qianchuan/"):
            user = self.require_user()
            if not user:
                return
            if parsed.path == "/api/qianchuan/bootstrap":
                shop = self.selected_shop(user, query=query)
                if not shop:
                    return
                advertiser_id = int(shop["advertiserId"])
                return self.send_json(
                    200,
                    {
                        "app_id": APP_ID,
                        "user": user,
                        "shops_local": allowed_shops_for_user(user),
                        "planPrefixOptions": plan_prefix_options(),
                        "default_advertiser_id": advertiser_id,
                        "default_shop_id": shop["shopId"],
                        "default_shop_name": shop["shopName"],
                        "authorized_accounts": ocean_get("/open_api/oauth2/advertiser/get/"),
                        "shops": ocean_get(
                            "/open_api/v1.0/qianchuan/shop/authorized/get/",
                            {"advertiser_id": advertiser_id, "page": 1, "page_size": 100},
                        ),
                        "authorizable_shops": ocean_get(
                            "/open_api/v1.0/qianchuan/uni_promotion/authorizable_shop/list/",
                            {"advertiser_id": advertiser_id, "page": 1, "page_size": 100},
                        ),
                        "advertiser_type": ocean_get(
                            "/open_api/v1.0/qianchuan/advertiser/type/get/",
                            {"advertiser_ids": json.dumps([advertiser_id])},
                        ),
                        "account_budget": ocean_get(
                            "/open_api/v1.0/qianchuan/account/budget/get/",
                            {"advertiser_id": advertiser_id},
                        ),
                        "account_balance": ocean_get(
                            "/open_api/v1.0/qianchuan/account/balance/get/",
                            {"advertiser_id": advertiser_id},
                        ),
                    },
                )
            if parsed.path == "/api/qianchuan/dashboard":
                return self.send_json(200, dashboard_summary(user, query))
            if parsed.path == "/api/qianchuan/plans":
                return self.send_json(200, qianchuan_visible_plans(query, user))
            if parsed.path == "/api/qianchuan/rules":
                return self.send_json(200, {"rules": filter_rules_for_user(load_rules(), user)})
            if parsed.path == "/api/qianchuan/operation-board":
                return self.send_json(200, operation_board_summary(user, query))
            if parsed.path == "/api/qianchuan/logs":
                with sqlite3.connect(DB_PATH) as conn:
                    rows = conn.execute(
                        """
                        select created_at, action, dry_run, request_json, response_json
                        from control_action_logs
                        order by id desc
                        limit 100
                        """
                    ).fetchall()
                logs = [
                    {
                        "created_at": row[0],
                        "action": row[1],
                        "dry_run": bool(row[2]),
                        "request": json.loads(row[3]),
                        "response": json.loads(row[4]),
                    }
                    for row in rows
                ]
                return self.send_json(200, {"logs": logs})
            return self.send_bytes(404, b"not found\n")
        if parsed.path != "/api/oceanengine/oauth/callback":
            return self.send_bytes(404, b"not found\n")

        auth_code = (query.get("auth_code") or query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        if not auth_code:
            return self.send_bytes(
                400,
                html_page(
                    "Qianchuan OAuth callback",
                    "<p>Missing <code>auth_code</code>.</p>",
                ),
                "text/html; charset=utf-8",
            )
        state_status = "valid" if state_is_valid(state) else "unchecked"
        status, exchange_response = exchange_token(auth_code)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                insert into callbacks(
                    created_at, remote_addr, state, auth_code, query_json,
                    exchange_status, exchange_response_json
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    self.client_address[0],
                    state,
                    auth_code,
                    json.dumps(query),
                    status,
                    json.dumps(exchange_response),
                ),
            )
        safe_status = html.escape(status)
        safe_state = html.escape(state_status)
        return self.send_bytes(
            200,
            html_page(
                "Qianchuan OAuth callback received",
                f"<p>Callback has been stored.</p><p>State: <code>{safe_state}</code></p><p>Token exchange: <code>{safe_status}</code></p>",
            ),
            "text/html; charset=utf-8",
        )

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        body = self.read_json_body()
        if parsed.path == "/api/auth/login":
            username = str(body.get("username") or "").strip()
            password = str(body.get("password") or "")
            row = get_user_by_username(username)
            if not row or row["status"] != "active" or not verify_password(password, row["password_hash"]):
                return self.send_json(401, {"error": "用户名或密码不正确"})
            token = create_session(row["id"])
            user = get_user_by_id(row["id"])
            return self.send_json(
                200,
                {"token": token, "user": user, "shops": allowed_shops_for_user(user), "planPrefixOptions": plan_prefix_options()},
            )
        if parsed.path == "/api/auth/bootstrap":
            if not self.require_control_auth():
                return self.send_forbidden()
            row = get_user_by_username(BOOTSTRAP_ADMIN_USERNAME)
            if not row:
                ensure_db()
                row = get_user_by_username(BOOTSTRAP_ADMIN_USERNAME)
            token = create_session(row["id"])
            user = get_user_by_id(row["id"])
            return self.send_json(
                200,
                {"token": token, "user": user, "shops": allowed_shops_for_user(user), "planPrefixOptions": plan_prefix_options()},
            )
        if parsed.path == "/api/auth/logout":
            token = self.bearer_token()
            if token:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("delete from sessions where token = ?", (token,))
            return self.send_json(200, {"ok": True})
        if parsed.path == "/api/admin/users":
            user = self.require_admin_user()
            if not user:
                return
            saved, error = save_user(body)
            if error:
                return self.send_json(400, {"error": error})
            return self.send_json(200, {"ok": True, "user": saved, "users": list_users()})
        if parsed.path == "/api/admin/users/delete":
            user = self.require_admin_user()
            if not user:
                return
            try:
                user_id = int(body.get("id") or 0)
            except (TypeError, ValueError):
                user_id = 0
            ok, error = delete_user(user_id)
            if not ok:
                return self.send_json(400, {"error": error})
            return self.send_json(200, {"ok": True, "users": list_users()})
        if parsed.path == "/api/shops":
            user = self.require_admin_user()
            if not user:
                return
            saved, error = save_shop(body)
            if error:
                return self.send_json(400, {"error": error})
            return self.send_json(200, {"ok": True, "shop": saved, "shops": list_shops()})
        if parsed.path == "/api/shops/delete":
            user = self.require_admin_user()
            if not user:
                return
            try:
                shop_id = int(body.get("shopId") or body.get("shop_id") or 0)
            except (TypeError, ValueError):
                shop_id = 0
            delete_shop(shop_id)
            return self.send_json(200, {"ok": True, "shops": list_shops()})
        if parsed.path == "/api/rule-groups":
            user = self.require_admin_user()
            if not user:
                return
            saved, error = save_rule_group(body)
            if error:
                return self.send_json(400, {"error": error})
            return self.send_json(200, {"ok": True, "group": saved, "groups": list_rule_groups()})
        if parsed.path == "/api/rule-groups/delete":
            user = self.require_admin_user()
            if not user:
                return
            group_id = str(body.get("id") or "").strip()
            if not group_id:
                return self.send_json(400, {"error": "id is required"})
            delete_rule_group(group_id)
            return self.send_json(200, {"ok": True, "groups": list_rule_groups(), "rules": load_rules()})
        if parsed.path == "/api/oceanengine/oauth/refresh":
            if not ADMIN_TOKEN or self.headers.get("X-QC-Admin-Token") != ADMIN_TOKEN:
                return self.send_json(403, {"error": "forbidden"})
            status, data = refresh_latest_token()
            return self.send_json(200 if status == "refreshed" else 500, token_response_summary(status, data))

        if not parsed.path.startswith("/api/qianchuan/"):
            return self.send_bytes(404, b"not found\n")
        user = self.require_user()
        if not user:
            return
        if parsed.path == "/api/qianchuan/rules":
            if not can_manage_admin(user):
                return self.send_forbidden()
            rules = body.get("rules") if isinstance(body, dict) else None
            if not isinstance(rules, list):
                return self.send_json(400, {"error": "rules must be a list"})
            save_rules(rules)
            return self.send_json(200, {"ok": True, "rules": load_rules()})

        if parsed.path in {"/api/qianchuan/actions/pause", "/api/qianchuan/actions/disable"}:
            if not can_control_plans(user):
                return self.send_forbidden()
            shop = self.selected_shop(user, body=body)
            if not shop:
                return
            advertiser_id = int(shop["advertiserId"])
            ad_id = int(body.get("ad_id") or 0)
            if ad_id <= 0:
                return self.send_json(400, {"error": "ad_id is required"})
            allowed, error, _plan = ensure_plan_action_allowed(
                user,
                shop,
                ad_id,
                body.get("marketing_goal") or "VIDEO_PROM_GOODS",
                body_plan_smart_bid_types(body, default=PLAN_SMART_BID_TYPES),
            )
            if not allowed:
                return self.send_json(403, {"error": error})
            payload = {
                "advertiser_id": advertiser_id,
                "ad_ids": [ad_id],
                "opt_status": "DISABLE",
            }
            response = ocean_post("/open_api/v1.0/qianchuan/uni_promotion/ad/status/update/", payload)
            log_action("pause", False, payload, response)
            return self.send_json(200, {"ok": ocean_update_ok(response), "request": payload, "response": response})

        if parsed.path == "/api/qianchuan/actions/enable":
            if not can_control_plans(user):
                return self.send_forbidden()
            shop = self.selected_shop(user, body=body)
            if not shop:
                return
            advertiser_id = int(shop["advertiserId"])
            ad_id = int(body.get("ad_id") or 0)
            if ad_id <= 0:
                return self.send_json(400, {"error": "ad_id is required"})
            allowed, error, _plan = ensure_plan_action_allowed(
                user,
                shop,
                ad_id,
                body.get("marketing_goal") or "VIDEO_PROM_GOODS",
                body_plan_smart_bid_types(body, default=PLAN_SMART_BID_TYPES),
            )
            if not allowed:
                return self.send_json(403, {"error": error})
            payload = {
                "advertiser_id": advertiser_id,
                "ad_ids": [ad_id],
                "opt_status": "ENABLE",
            }
            response = ocean_post("/open_api/v1.0/qianchuan/uni_promotion/ad/status/update/", payload)
            log_action("enable", False, payload, response)
            return self.send_json(200, {"ok": ocean_update_ok(response), "request": payload, "response": response})

        if parsed.path == "/api/qianchuan/actions/budget":
            if not can_control_plans(user):
                return self.send_forbidden()
            shop = self.selected_shop(user, body=body)
            if not shop:
                return
            advertiser_id = int(shop["advertiserId"])
            ad_id = int(body.get("ad_id") or 0)
            budget = number(body.get("budget"))
            if ad_id <= 0:
                return self.send_json(400, {"error": "ad_id is required"})
            if budget <= 0:
                return self.send_json(400, {"error": "budget must be greater than 0"})
            allowed, error, _plan = ensure_plan_action_allowed(
                user,
                shop,
                ad_id,
                body.get("marketing_goal") or "VIDEO_PROM_GOODS",
                body_plan_smart_bid_types(body, default=PLAN_SMART_BID_TYPES),
            )
            if not allowed:
                return self.send_json(403, {"error": error})
            payload = {
                "advertiser_id": advertiser_id,
                "update_budget_infos": [{"ad_id": ad_id, "budget": budget}],
            }
            response = ocean_post("/open_api/v1.0/qianchuan/uni_promotion/ad/budget/update/", payload)
            log_action("budget", False, payload, response)
            return self.send_json(200, {"ok": ocean_update_ok(response), "request": payload, "response": response})

        if parsed.path == "/api/qianchuan/actions/reset-budgets":
            if not can_control_plans(user):
                return self.send_forbidden()
            result, error = reset_visible_plan_budgets(user, body)
            if error:
                return self.send_json(400, {"error": error})
            return self.send_json(200 if result.get("ok") else 502, result)

        if parsed.path == "/api/qianchuan/actions/run-rules":
            if not can_control_plans(user):
                return self.send_forbidden()
            return self.send_json(200, execute_rules_for_user(user, body))

        return self.send_bytes(404, b"not found\n")

    def log_message(self, fmt, *args):
        print(f"{utc_now()} {self.client_address[0]} {fmt % args}", flush=True)


def run_refresh_command():
    ensure_db()
    status, data = refresh_latest_token()
    print(json.dumps(token_response_summary(status, data), ensure_ascii=False))
    return 0 if status == "refreshed" else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        sys.exit(run_refresh_command())

    ensure_db()
    start_cloud_scheduler()
    host = os.environ.get("OCEANENGINE_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("OCEANENGINE_BIND_PORT", "18080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"qianchuan-oauth listening on {host}:{port}", flush=True)
    server.serve_forever()
