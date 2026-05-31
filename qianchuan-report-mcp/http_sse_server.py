#!/usr/bin/env python3
import argparse
import os
import queue
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import server as mcp_server


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5291
DEFAULT_PREFIX = "/api/qianchuan-report-mcp"
TOKEN_FILE = Path(__file__).resolve().parent / ".report-mcp-token"

SESSIONS = {}
SESSIONS_LOCK = threading.Lock()


def load_token(explicit=None):
    if explicit:
        return explicit.strip()
    env_token = os.environ.get("QIANCHUAN_REPORT_MCP_TOKEN", "").strip()
    if env_token:
        return env_token
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def normalize_headers(headers):
    return {str(key).lower(): str(value) for key, value in headers.items()}


def is_authorized(headers, token):
    if not token:
        return False
    normalized = normalize_headers(headers)
    auth = normalized.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() == token
    if auth and auth == token:
        return True
    return normalized.get("x-qianchuan-report-token", "").strip() == token


def normalize_path(path, prefix):
    prefix = (prefix or "").rstrip("/")
    if prefix and path == prefix:
        return "/"
    if prefix and path.startswith(prefix + "/"):
        return path[len(prefix):] or "/"
    return path


def message_endpoint(session_id, prefix):
    prefix = (prefix or "").rstrip("/")
    return f"{prefix}/messages?session_id={urllib.parse.quote(session_id)}"


class SseSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.queue = queue.Queue()
        self.created_at = time.time()


def get_session(session_id):
    with SESSIONS_LOCK:
        return SESSIONS.get(session_id)


def create_session():
    session_id = uuid.uuid4().hex
    session = SseSession(session_id)
    with SESSIONS_LOCK:
        SESSIONS[session_id] = session
    return session


def remove_session(session_id):
    with SESSIONS_LOCK:
        SESSIONS.pop(session_id, None)


class Handler(BaseHTTPRequestHandler):
    server_version = "QianchuanReportMCP/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), fmt % args))
        sys.stderr.flush()

    @property
    def config(self):
        return self.server.config

    @property
    def repo(self):
        return self.server.repo

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, X-Qianchuan-Report-Token, Content-Type")

    def send_text(self, status, body, content_type="text/plain; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_cors()
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, value):
        self.send_text(status, mcp_server.json_dumps(value), "application/json; charset=utf-8")

    def require_auth(self):
        if is_authorized(self.headers, self.config["token"]):
            return True
        self.send_json(401, {"error": "unauthorized"})
        return False

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = normalize_path(parsed.path, self.config["prefix"])
        if path == "/healthz":
            return self.send_json(
                200,
                {
                    "ok": True,
                    "server": mcp_server.SERVER_NAME,
                    "transport": "sse",
                    "mode": "read-only",
                    "auth": "required",
                },
            )
        if path == "/sse":
            if not self.require_auth():
                return
            return self.handle_sse()
        return self.send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = normalize_path(parsed.path, self.config["prefix"])
        if path != "/messages":
            return self.send_json(404, {"error": "not found"})
        if not self.require_auth():
            return
        query = urllib.parse.parse_qs(parsed.query)
        session_id = (query.get("session_id") or [""])[0]
        session = get_session(session_id)
        if not session:
            return self.send_json(404, {"error": "session not found"})
        try:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length).decode("utf-8")
            request = mcp_server.json.loads(raw)
        except Exception as exc:
            return self.send_json(400, {"error": f"invalid json: {exc}"})
        response = mcp_server.handle_request(request, self.repo)
        if response is not None:
            session.queue.put(response)
        return self.send_json(202, {"ok": True})

    def write_sse(self, event, data):
        payload = mcp_server.json_dumps(data) if not isinstance(data, str) else data
        self.wfile.write(f"event: {event}\n".encode("utf-8"))
        for line in payload.splitlines() or [""]:
            self.wfile.write(f"data: {line}\n".encode("utf-8"))
        self.wfile.write(b"\n")
        self.wfile.flush()

    def write_comment(self, text):
        self.wfile.write(f": {text}\n\n".encode("utf-8"))
        self.wfile.flush()

    def handle_sse(self):
        session = create_session()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_cors()
        self.end_headers()
        try:
            self.write_sse("endpoint", message_endpoint(session.session_id, self.config["prefix"]))
            while True:
                try:
                    response = session.queue.get(timeout=15)
                except queue.Empty:
                    self.write_comment("keepalive")
                    continue
                self.write_sse("message", response)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            remove_session(session.session_id)


class ReportHttpServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, repo, config):
        super().__init__(server_address, handler_class)
        self.repo = repo
        self.config = config


def parse_args(argv):
    parser = argparse.ArgumentParser(description="HTTP/SSE transport for the read-only Qianchuan report MCP.")
    parser.add_argument("--host", default=os.environ.get("QIANCHUAN_REPORT_MCP_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("QIANCHUAN_REPORT_MCP_PORT", DEFAULT_PORT)))
    parser.add_argument("--db", default=os.environ.get("QIANCHUAN_REPORT_DB_PATH"))
    parser.add_argument("--prefix", default=os.environ.get("QIANCHUAN_REPORT_MCP_PREFIX", DEFAULT_PREFIX))
    parser.add_argument("--token", default=None)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    token = load_token(args.token)
    if not token:
        print("missing QIANCHUAN_REPORT_MCP_TOKEN or .report-mcp-token", file=sys.stderr)
        return 2
    repo = mcp_server.ReportRepository(args.db)
    config = {"token": token, "prefix": args.prefix.rstrip("/")}
    httpd = ReportHttpServer((args.host, args.port), Handler, repo, config)
    print(f"qianchuan-report-mcp http/sse listening on {args.host}:{args.port}{config['prefix']}/sse", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
