import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import http_sse_server


class HttpSseTests(unittest.TestCase):
    def test_token_auth_accepts_bearer_and_explicit_header(self):
        token = "abc123"
        self.assertTrue(http_sse_server.is_authorized({"authorization": f"Bearer {token}"}, token))
        self.assertTrue(http_sse_server.is_authorized({"x-qianchuan-report-token": token}, token))
        self.assertFalse(http_sse_server.is_authorized({"authorization": "Bearer wrong"}, token))
        self.assertFalse(http_sse_server.is_authorized({}, token))

    def test_prefix_is_removed_for_local_routing(self):
        self.assertEqual(http_sse_server.normalize_path("/api/qianchuan-report-mcp/sse", "/api/qianchuan-report-mcp"), "/sse")
        self.assertEqual(http_sse_server.normalize_path("/api/qianchuan-report-mcp/messages", "/api/qianchuan-report-mcp"), "/messages")
        self.assertEqual(http_sse_server.normalize_path("/healthz", "/api/qianchuan-report-mcp"), "/healthz")

    def test_endpoint_uses_public_prefix(self):
        endpoint = http_sse_server.message_endpoint("sid-1", "/api/qianchuan-report-mcp")
        self.assertEqual(endpoint, "/api/qianchuan-report-mcp/messages?session_id=sid-1")


if __name__ == "__main__":
    unittest.main()
