#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "qianchuan-local.sqlite3"
DEFAULT_BASE = "http://127.0.0.1:5290"
LOG_PATH = ROOT / "backfill-reports.log"


def today_text():
    return dt.datetime.now().strftime("%Y-%m-%d")


def read_admin_credentials():
    text = (ROOT / "admin.local.txt").read_text(encoding="utf-8")
    username_match = re.search(r"账号[:：]\s*(\S+)", text)
    password_match = re.search(r"密码[:：]\s*(\S+)", text)
    if not username_match or not password_match:
        raise RuntimeError("admin.local.txt is missing username or password")
    return username_match.group(1), password_match.group(1)


def read_control_token():
    secrets = ROOT / "local.secrets.ps1"
    if not secrets.exists():
        return ""
    text = secrets.read_text(encoding="utf-8")
    match = re.search(r"QIANCHUAN_CONTROL_TOKEN\s*=\s*['\"]([^'\"]+)['\"]", text)
    return match.group(1) if match else ""


def request_json(url, method="GET", token="", payload=None, timeout=240, extra_headers=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {"error": raw.decode("utf-8", errors="replace")}
        return exc.code, body


def login(base_url):
    username, password = read_admin_credentials()
    status, data = request_json(f"{base_url}/api/auth/login", method="POST", payload={"username": username, "password": password})
    if status == 200 and data.get("token"):
        return data["token"]
    control_token = read_control_token()
    if control_token:
        status, data = request_json(
            f"{base_url}/api/auth/bootstrap",
            method="POST",
            payload={},
            extra_headers={"X-QC-Admin-Token": control_token},
        )
        if status == 200 and data.get("token"):
            return data["token"]
    raise RuntimeError(f"login failed: HTTP {status} {data.get('error') or data.get('message') or ''}".strip())


def daterange(start, end):
    current = dt.datetime.strptime(start, "%Y-%m-%d").date()
    final = dt.datetime.strptime(end, "%Y-%m-%d").date()
    while current <= final:
        yield current.strftime("%Y-%m-%d")
        current += dt.timedelta(days=1)


def existing_daily_dates(marketing_goal):
    if not DB_PATH.exists():
        return set()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            select distinct date(start_time)
            from report_runs
            where marketing_goal = ?
              and date(start_time) = date(end_time)
              and substr(start_time, 12, 8) = '00:00:00'
              and substr(end_time, 12, 8) = '23:59:59'
            """,
            (marketing_goal,),
        ).fetchall()
    return {row[0] for row in rows}


def append_log(record):
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def backfill_day(base_url, token, day, marketing_goal, force):
    params = {
        "date_from": day,
        "date_to": day,
        "marketing_goal": marketing_goal,
    }
    if force:
        params["force_refresh"] = "1"
    url = f"{base_url}/api/local/reports/qianchuan?{urllib.parse.urlencode(params)}"
    started = time.time()
    status, data = request_json(url, token=token, timeout=600)
    elapsed = round(time.time() - started, 2)
    ok = status == 200 and isinstance(data, dict) and (data.get("ok", True) is not False)
    record = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "day": day,
        "status": status,
        "ok": ok,
        "seconds": elapsed,
        "planCount": len(data.get("plans") or []) if isinstance(data, dict) else 0,
        "shopCount": len(data.get("shops") or []) if isinstance(data, dict) else 0,
        "cacheSource": (data.get("_cache") or {}).get("source") if isinstance(data, dict) else "",
        "error": "" if ok else (data.get("error") or data.get("message") or "request failed"),
    }
    append_log(record)
    return record


def main():
    parser = argparse.ArgumentParser(description="Backfill Qianchuan daily reports into the local SQLite database.")
    parser.add_argument("--start", default="2026-04-01")
    parser.add_argument("--end", default=today_text())
    parser.add_argument("--marketing-goal", default="VIDEO_PROM_GOODS")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--force", action="store_true", help="Refresh days even if a local daily report already exists.")
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()

    token = login(args.base_url.rstrip("/"))
    request_json(f"{args.base_url.rstrip('/')}/api/me", token=token, timeout=60)
    existing = existing_daily_dates(args.marketing_goal)
    days = list(daterange(args.start, args.end))
    summary = {"total": len(days), "done": 0, "skipped": 0, "failed": 0, "start": args.start, "end": args.end}
    print(json.dumps({"event": "start", **summary}, ensure_ascii=False))
    for day in days:
        if not args.force and day in existing:
            summary["skipped"] += 1
            record = {"time": dt.datetime.now().isoformat(timespec="seconds"), "day": day, "ok": True, "skipped": True}
            append_log(record)
            print(json.dumps(record, ensure_ascii=False))
            continue
        record = backfill_day(args.base_url.rstrip("/"), token, day, args.marketing_goal, args.force)
        if record["ok"]:
            summary["done"] += 1
        else:
            summary["failed"] += 1
        print(json.dumps(record, ensure_ascii=False))
        if args.sleep > 0:
            time.sleep(args.sleep)
    print(json.dumps({"event": "finish", **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
