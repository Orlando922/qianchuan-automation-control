import importlib.util
import json
import sqlite3
import tempfile
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("local_control.py")
SPEC = importlib.util.spec_from_file_location("local_control", MODULE_PATH)
local_control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(local_control)


class CacheBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        local_control.DB_PATH = Path(self.tmp.name) / "local.sqlite3"
        local_control.ensure_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_expired_api_cache_can_be_returned_as_stale(self):
        headers = {"Authorization": "Bearer user-a"}
        path = "/api/qianchuan/dashboard?marketing_goal=VIDEO_PROM_GOODS"
        local_control.set_cached_response("GET", path, headers, 200, {"ok": True, "value": 12})
        with sqlite3.connect(local_control.DB_PATH) as conn:
            conn.execute("update response_cache set expires_at = ?", (time.time() - 60,))

        self.assertIsNone(local_control.get_cached_response("GET", path, headers))
        cached = local_control.get_cached_response("GET", path, headers, allow_stale=True)

        self.assertIsNotNone(cached)
        status, data, meta = cached
        self.assertEqual(status, 200)
        self.assertEqual(data["value"], 12)
        self.assertTrue(meta["stale"])

    def test_report_cache_is_scoped_by_auth_and_date_range(self):
        query = {
            "date_from": ["2026-05-18"],
            "date_to": ["2026-05-19"],
            "marketing_goal": ["VIDEO_PROM_GOODS"],
        }
        report = {
            "global": {"spend": 1, "gmv": 2, "roi": 2},
            "range": {
                "startTime": "2026-05-18 00:00:00",
                "endTime": "2026-05-19 23:59:59",
                "marketingGoal": "VIDEO_PROM_GOODS",
            },
            "shops": [],
            "plans": [],
        }
        headers_a = {"Authorization": "Bearer user-a"}
        headers_b = {"Authorization": "Bearer user-b"}
        local_control.set_report_response_cache(headers_a, query, 200, report)

        cached = local_control.get_report_response_cache(headers_a, query)
        self.assertIsNotNone(cached)
        status, data, meta = cached
        self.assertEqual(status, 200)
        self.assertEqual(data["global"]["spend"], 1)
        self.assertEqual(meta["source"], "local-report-cache")

        self.assertIsNone(local_control.get_report_response_cache(headers_b, query))

        other_query = {
            "date_from": ["2026-05-17"],
            "date_to": ["2026-05-19"],
            "marketing_goal": ["VIDEO_PROM_GOODS"],
        }
        self.assertIsNone(local_control.get_report_response_cache(headers_a, other_query))

    def test_report_cache_is_scoped_by_plan_smart_bid_type(self):
        headers = {"Authorization": "Bearer user-a"}
        custom_query = {
            "date_from": ["2026-05-18"],
            "date_to": ["2026-05-18"],
            "marketing_goal": ["VIDEO_PROM_GOODS"],
            "smart_bid_type": ["SMART_BID_CUSTOM"],
        }
        volume_query = {
            "date_from": ["2026-05-18"],
            "date_to": ["2026-05-18"],
            "marketing_goal": ["VIDEO_PROM_GOODS"],
            "smart_bid_type": ["SMART_BID_CONSERVATIVE"],
        }
        local_control.set_report_response_cache(headers, custom_query, 200, {"global": {"planCount": 1}, "shops": [], "plans": []})

        self.assertIsNotNone(local_control.get_report_response_cache(headers, custom_query))
        self.assertIsNone(local_control.get_report_response_cache(headers, volume_query))

    def test_plan_snapshots_store_plan_smart_bid_type(self):
        local_control.persist_response(
            "/api/qianchuan/plans",
            {
                "plans": [
                    {
                        "id": 101,
                        "name": "SC_放量计划",
                        "smartBidType": "SMART_BID_CONSERVATIVE",
                        "spend": 10,
                        "gmv": 20,
                        "roi": 2,
                        "budget": 300,
                    }
                ]
            },
        )

        with sqlite3.connect(local_control.DB_PATH) as conn:
            row = conn.execute("select smart_bid_type from plan_snapshots where plan_id = 101").fetchone()

        self.assertEqual(row[0], "SMART_BID_CONSERVATIVE")

    def test_clear_response_cache_preserves_session_profile_and_clears_data_caches(self):
        headers = {"Authorization": "Bearer user-a"}
        query = {
            "date_from": ["2026-05-20"],
            "date_to": ["2026-05-20"],
            "marketing_goal": ["VIDEO_PROM_GOODS"],
        }
        local_control.set_cached_response("GET", "/api/me", headers, 200, {"ok": True})
        local_control.set_cached_response(
            "GET",
            "/api/qianchuan/dashboard?marketing_goal=VIDEO_PROM_GOODS",
            headers,
            200,
            {"ok": True, "global": {"spend": 1}},
        )
        local_control.set_report_response_cache(headers, query, 200, {"global": {}, "shops": [], "plans": []})

        local_control.clear_response_cache()

        self.assertIsNotNone(local_control.get_cached_response("GET", "/api/me", headers, allow_stale=True))
        self.assertIsNone(
            local_control.get_cached_response(
                "GET",
                "/api/qianchuan/dashboard?marketing_goal=VIDEO_PROM_GOODS",
                headers,
                allow_stale=True,
            )
        )
        self.assertIsNone(local_control.get_report_response_cache(headers, query))

    def test_stale_plan_get_schedules_background_refresh(self):
        headers = {"Authorization": "Bearer user-a"}
        full_path = "/api/qianchuan/plans?page=1&page_size=500"
        local_control.set_cached_response(
            "GET",
            full_path,
            headers,
            200,
            {"ok": True, "plans": [{"id": 1, "name": "SC_旧放量", "smartBidType": "SMART_BID_CONSERVATIVE"}]},
        )
        with sqlite3.connect(local_control.DB_PATH) as conn:
            conn.execute("update response_cache set expires_at = ?", (time.time() - 60,))

        refreshes = []
        original_schedule_cached_get_refresh = local_control.schedule_cached_get_refresh
        server = ThreadingHTTPServer(("127.0.0.1", 0), local_control.Handler)
        try:
            local_control.schedule_cached_get_refresh = lambda full_path, headers, path, operator: refreshes.append(
                {"fullPath": full_path, "path": path, "operator": operator}
            ) or True
            thread = local_control.threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{full_path}",
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            local_control.schedule_cached_get_refresh = original_schedule_cached_get_refresh

        self.assertEqual(payload["plans"][0]["smartBidType"], "SMART_BID_CONSERVATIVE")
        self.assertTrue(payload["_cache"]["stale"])
        self.assertTrue(payload["_cache"]["refreshing"])
        self.assertEqual(refreshes[0]["fullPath"], full_path)
        self.assertEqual(refreshes[0]["path"], "/api/qianchuan/plans")
        self.assertEqual(refreshes[0]["operator"], "session")

    def test_daily_reports_can_compose_a_range_locally(self):
        headers = {"Authorization": "Bearer user-a"}
        local_control.set_cached_response(
            "GET",
            "/api/me",
            headers,
            200,
            {
                "ok": True,
                "user": {"username": "admin", "displayName": "管理员", "role": "admin", "planPrefixes": ["SC", "CY"]},
                "shops": [{"shopId": 1, "shopName": "店铺A", "advertiserId": 11}],
            },
        )
        for day, spend, gmv in (("2026-05-18", 100, 250), ("2026-05-19", 200, 300)):
            report = {
                "ok": True,
                "global": {"shopCount": 1, "planCount": 1, "spend": spend, "gmv": gmv, "roi": gmv / spend},
                "range": {
                    "startTime": f"{day} 00:00:00",
                    "endTime": f"{day} 23:59:59",
                    "marketingGoal": "VIDEO_PROM_GOODS",
                },
                "shops": [
                    {
                        "shopId": 1,
                        "advertiserId": 11,
                        "shopName": "店铺A",
                        "spend": spend,
                        "gmv": gmv,
                        "roi": gmv / spend,
                        "orders": 1,
                        "planCount": 1,
                        "plans": [
                            {
                                "id": 99,
                                "shopId": 1,
                                "advertiserId": 11,
                                "shopName": "店铺A",
                                "name": "计划A",
                                "spend": spend,
                                "gmv": gmv,
                                "roi": gmv / spend,
                                "orders": 1,
                                "budget": 500,
                            }
                        ],
                    }
                ],
                "plans": [
                    {
                        "id": 99,
                        "shopId": 1,
                        "advertiserId": 11,
                        "shopName": "店铺A",
                        "name": "计划A",
                        "spend": spend,
                        "gmv": gmv,
                        "roi": gmv / spend,
                        "orders": 1,
                        "budget": 500,
                    }
                ],
            }
            local_control.persist_report(report)

        query = {
            "date_from": ["2026-05-18"],
            "date_to": ["2026-05-19"],
            "marketing_goal": ["VIDEO_PROM_GOODS"],
        }
        report = local_control.build_local_report_from_daily(headers, query)

        self.assertIsNotNone(report)
        self.assertEqual(report["global"]["spend"], 300)
        self.assertEqual(report["global"]["gmv"], 550)
        self.assertEqual(len(report["shops"]), 1)
        self.assertEqual(len(report["plans"]), 1)
        self.assertEqual(report["plans"][0]["spend"], 300)

    def test_daily_reports_filter_by_plan_prefix_for_operator(self):
        headers = {"Authorization": "Bearer user-a"}
        local_control.set_cached_response(
            "GET",
            "/api/me",
            headers,
            200,
            {
                "ok": True,
                "user": {"username": "staff", "displayName": "投手", "role": "operator", "planPrefixes": ["SC"]},
                "shops": [{"shopId": 1, "shopName": "店铺A", "advertiserId": 11}],
            },
        )
        report = {
            "ok": True,
            "global": {"shopCount": 1, "planCount": 2, "spend": 300, "gmv": 550, "roi": 1.83},
            "range": {
                "startTime": "2026-05-18 00:00:00",
                "endTime": "2026-05-18 23:59:59",
                "marketingGoal": "VIDEO_PROM_GOODS",
            },
            "shops": [
                {
                    "shopId": 1,
                    "advertiserId": 11,
                    "shopName": "店铺A",
                    "spend": 300,
                    "gmv": 550,
                    "roi": 1.83,
                    "orders": 2,
                    "planCount": 2,
                    "plans": [
                        {"id": 99, "name": "SC_计划A", "spend": 100, "gmv": 250, "roi": 2.5, "orders": 1, "budget": 500},
                        {"id": 100, "name": "CY_计划B", "spend": 200, "gmv": 300, "roi": 1.5, "orders": 1, "budget": 500},
                    ],
                }
            ],
            "plans": [],
        }
        local_control.persist_report(report)

        query = {
            "date_from": ["2026-05-18"],
            "date_to": ["2026-05-18"],
            "marketing_goal": ["VIDEO_PROM_GOODS"],
        }
        scoped = local_control.build_local_report_from_daily(headers, query)

        self.assertIsNotNone(scoped)
        self.assertEqual(scoped["global"]["spend"], 100)
        self.assertEqual(scoped["global"]["gmv"], 250)
        self.assertEqual(len(scoped["plans"]), 1)
        self.assertEqual(scoped["plans"][0]["ownerPrefix"], "SC")
        self.assertEqual(scoped["users"][0]["planPrefixes"], ["SC"])

    def test_startup_snapshot_uses_local_plan_cache_and_prefix_scope(self):
        headers = {"Authorization": "Bearer user-a"}
        local_control.set_cached_response(
            "GET",
            "/api/me",
            headers,
            200,
            {
                "ok": True,
                "user": {"username": "staff", "displayName": "投手", "role": "operator", "planPrefixes": ["SC"]},
                "shops": [{"shopId": 1, "shopName": "来源账户", "advertiserId": 11}],
                "planPrefixOptions": [{"prefix": "SC", "ownerName": "Operator A", "label": "SC Operator A"}],
            },
        )
        local_control.persist_response(
            "/api/qianchuan/plans",
            {
                "code": 0,
                "plans": [
                    {
                        "id": 1,
                        "name": "SC_计划A",
                        "ownerPrefix": "SC",
                        "ownerName": "Operator A",
                        "spend": 100,
                        "gmv": 250,
                        "roi": 2.5,
                        "budget": 500,
                        "shopId": 1,
                        "advertiserId": 11,
                    },
                    {
                        "id": 2,
                        "name": "CY_计划B",
                        "ownerPrefix": "CY",
                        "ownerName": "Operator B",
                        "spend": 200,
                        "gmv": 300,
                        "roi": 1.5,
                        "budget": 500,
                        "shopId": 1,
                        "advertiserId": 11,
                    },
                ],
                "page_info": {"total": 2},
            },
        )

        snapshot = local_control.local_startup_snapshot(headers)

        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["source"], "local-startup-snapshot")
        self.assertEqual(len(snapshot["plans"]), 1)
        self.assertEqual(snapshot["plans"][0]["ownerPrefix"], "SC")
        self.assertEqual(snapshot["dashboard"]["global"]["spend"], 100)

    def test_startup_snapshot_ignores_empty_short_plan_cache_when_snapshots_exist(self):
        headers = {"Authorization": "Bearer admin-a"}
        local_control.set_cached_response(
            "GET",
            "/api/me",
            headers,
            200,
            {
                "ok": True,
                "user": {"username": "admin", "displayName": "管理员", "role": "admin", "planPrefixes": []},
                "shops": [{"shopId": 1, "shopName": "来源账户", "advertiserId": 11}],
            },
        )
        local_control.set_cached_response(
            "GET",
            "/api/qianchuan/plans?marketing_goal=VIDEO_PROM_GOODS&page=1&page_size=500",
            headers,
            200,
            {"ok": True, "plans": [], "page_info": {"total": 0}},
        )
        local_control.set_cached_response(
            "GET",
            "/api/qianchuan/dashboard?marketing_goal=VIDEO_PROM_GOODS",
            headers,
            200,
            {"ok": True, "global": {"spend": 0, "gmv": 0, "roi": 0, "planCount": 0}, "plans": []},
        )
        local_control.persist_response(
            "/api/qianchuan/plans",
            {
                "code": 0,
                "plans": [
                    {
                        "id": 9,
                        "name": "SC_计划快照",
                        "spend": 88,
                        "gmv": 176,
                        "roi": 2,
                        "budget": 300,
                        "shopId": 1,
                        "advertiserId": 11,
                    }
                ],
                "page_info": {"total": 1},
            },
        )

        snapshot = local_control.local_startup_snapshot(headers)

        self.assertTrue(snapshot["ok"])
        self.assertEqual(len(snapshot["plans"]), 1)
        self.assertEqual(snapshot["plans"][0]["id"], 9)
        self.assertEqual(snapshot["dashboard"]["global"]["spend"], 88)

    def test_startup_snapshot_uses_snapshot_when_short_plan_cache_is_partial(self):
        headers = {"Authorization": "Bearer admin-a"}
        local_control.set_cached_response(
            "GET",
            "/api/me",
            headers,
            200,
            {
                "ok": True,
                "user": {"username": "admin", "displayName": "管理员", "role": "admin", "planPrefixes": []},
                "shops": [{"shopId": 1, "shopName": "来源账户", "advertiserId": 11}],
            },
        )
        local_control.set_cached_response(
            "GET",
            "/api/qianchuan/plans?marketing_goal=VIDEO_PROM_GOODS&page=1&page_size=500",
            headers,
            200,
            {
                "ok": True,
                "plans": [{"id": 1, "name": "SC_短缓存", "spend": 1, "gmv": 2, "shopId": 1}],
                "page_info": {"total": 1},
            },
        )
        local_control.persist_response(
            "/api/qianchuan/plans",
            {
                "code": 0,
                "plans": [
                    {"id": 1, "name": "SC_完整计划A", "spend": 10, "gmv": 20, "shopId": 1},
                    {"id": 2, "name": "CY_完整计划B", "spend": 30, "gmv": 60, "shopId": 1},
                ],
                "page_info": {"total": 2},
            },
        )

        snapshot = local_control.local_startup_snapshot(headers)

        self.assertEqual(len(snapshot["plans"]), 2)
        self.assertEqual(snapshot["dashboard"]["global"]["spend"], 40)

    def test_sync_core_cache_populates_local_startup_snapshot_from_cloud(self):
        headers = {"X-QC-Admin-Token": "admin-token"}
        calls = []
        original_cloud_proxy_request = local_control.cloud_proxy_request
        original_mirror_dashboard_plan_pages = local_control.mirror_dashboard_plan_pages

        def fake_cloud_proxy_request(method, full_path, request_headers, raw_body=None, timeout=180):
            calls.append((method, full_path))
            payloads = {
                "/api/me": {
                    "ok": True,
                    "user": {"username": "admin", "displayName": "管理员", "role": "admin"},
                    "shops": [{"shopId": 1, "shopName": "来源账户", "advertiserId": 11}],
                    "planPrefixOptions": [{"prefix": "SC", "ownerName": "Operator A", "label": "SC Operator A"}],
                },
                "/api/qianchuan/bootstrap": {
                    "ok": True,
                    "shops": [{"shopId": 1, "shopName": "来源账户", "advertiserId": 11}],
                    "default_shop_id": 1,
                    "planPrefixOptions": [{"prefix": "SC", "ownerName": "Operator A", "label": "SC Operator A"}],
                },
                "/api/qianchuan/dashboard": {
                    "ok": True,
                    "global": {"spend": 88, "gmv": 176, "roi": 2, "planCount": 1},
                    "plans": [],
                },
                "/api/qianchuan/plans?page=1&page_size=500": {
                    "code": 0,
                    "plans": [
                        {
                            "id": 9,
                            "name": "SC_同步计划",
                            "spend": 88,
                            "gmv": 176,
                            "roi": 2,
                            "budget": 300,
                            "shopId": 1,
                            "advertiserId": 11,
                        }
                    ],
                    "page_info": {"total": 1},
                },
                "/api/qianchuan/rules": {"ok": True, "rules": []},
                "/api/rule-groups": {"ok": True, "groups": []},
                "/api/qianchuan/logs": {"ok": True, "logs": []},
                "/api/qianchuan/operation-board": {
                    "ok": True,
                    "date": "2026-05-26",
                    "autoPause": {"total": 1, "pending": 1, "restored": 0, "records": [{"planId": 9}]},
                    "budgetReset": {"runs": []},
                },
                "/api/admin/users": {"ok": True, "users": []},
            }
            return 200, payloads.get(full_path, {"ok": True}), ""

        try:
            local_control.cloud_proxy_request = fake_cloud_proxy_request
            local_control.mirror_dashboard_plan_pages = lambda *args, **kwargs: None

            result = local_control.sync_core_cache(headers, operator="test-sync")
            snapshot = local_control.local_startup_snapshot(headers)
        finally:
            local_control.cloud_proxy_request = original_cloud_proxy_request
            local_control.mirror_dashboard_plan_pages = original_mirror_dashboard_plan_pages

        self.assertTrue(result["ok"])
        self.assertIn(("GET", "/api/me"), calls)
        self.assertIn(("GET", "/api/qianchuan/operation-board"), calls)
        self.assertEqual(snapshot["plans"][0]["name"], "SC_同步计划")
        self.assertEqual(snapshot["dashboard"]["global"]["spend"], 88)
        self.assertEqual(snapshot["operationBoard"]["source"], "local-operation-board")
        self.assertEqual(snapshot["operationBoard"]["autoPause"]["pending"], 0)

    def test_sync_core_cache_waits_for_plan_page_mirror_before_snapshot(self):
        headers = {"X-QC-Admin-Token": "admin-token"}
        calls = []
        deferred_threads = []
        original_cloud_proxy_request = local_control.cloud_proxy_request
        original_mirror_dashboard_plan_pages = local_control.mirror_dashboard_plan_pages
        original_thread = local_control.threading.Thread

        def fake_cloud_proxy_request(method, full_path, request_headers, raw_body=None, timeout=180):
            calls.append((method, full_path))
            payloads = {
                "/api/me": {
                    "ok": True,
                    "user": {"username": "admin", "displayName": "管理员", "role": "admin"},
                    "shops": [{"shopId": 1, "shopName": "来源账户", "advertiserId": 11}],
                    "planPrefixOptions": [{"prefix": "SC", "ownerName": "Operator A", "label": "SC Operator A"}],
                },
                "/api/qianchuan/bootstrap": {
                    "ok": True,
                    "shops": [{"shopId": 1, "shopName": "来源账户", "advertiserId": 11}],
                    "default_shop_id": 1,
                    "planPrefixOptions": [{"prefix": "SC", "ownerName": "Operator A", "label": "SC Operator A"}],
                },
                "/api/qianchuan/dashboard": {
                    "ok": True,
                    "global": {"spend": 0, "gmv": 0, "roi": 0, "planCount": 0},
                    "plans": [],
                    "range": {"planSmartBidTypes": ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"]},
                },
                "/api/qianchuan/plans?page=1&page_size=500": {
                    "code": 0,
                    "plans": [],
                    "page_info": {"total": 0},
                },
                "/api/qianchuan/rules": {"ok": True, "rules": []},
                "/api/rule-groups": {"ok": True, "groups": []},
                "/api/qianchuan/logs": {"ok": True, "logs": []},
                "/api/qianchuan/operation-board": {
                    "ok": True,
                    "date": "2026-05-28",
                    "autoPause": {"total": 0, "pending": 0, "restored": 0, "records": []},
                    "budgetReset": {"runs": []},
                },
                "/api/admin/users": {"ok": True, "users": []},
            }
            return 200, payloads.get(full_path, {"ok": True}), ""

        def fake_mirror_dashboard_plan_pages(request_headers, dashboard_data):
            local_control.persist_response(
                "/api/qianchuan/plans",
                {
                    "code": 0,
                    "plans": [
                        {
                            "id": 21,
                            "name": "SC_放量同步计划",
                            "smartBidType": "SMART_BID_CONSERVATIVE",
                            "spend": 19,
                            "gmv": 38,
                            "roi": 2,
                            "budget": 30,
                            "shopId": 1,
                            "advertiserId": 11,
                        }
                    ],
                    "page_info": {"total": 1},
                },
            )

        class DeferredThread:
            def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                self.target = target
                self.args = args
                self.kwargs = kwargs or {}
                self.daemon = daemon

            def start(self):
                deferred_threads.append(self)

        try:
            local_control.cloud_proxy_request = fake_cloud_proxy_request
            local_control.mirror_dashboard_plan_pages = fake_mirror_dashboard_plan_pages
            local_control.threading.Thread = DeferredThread

            result = local_control.sync_core_cache(headers, operator="test-sync")
            snapshot = local_control.local_startup_snapshot(headers)
        finally:
            local_control.cloud_proxy_request = original_cloud_proxy_request
            local_control.mirror_dashboard_plan_pages = original_mirror_dashboard_plan_pages
            local_control.threading.Thread = original_thread

        self.assertTrue(result["ok"])
        self.assertIn(("GET", "/api/qianchuan/dashboard"), calls)
        self.assertEqual(deferred_threads, [])
        self.assertEqual(snapshot["plans"][0]["name"], "SC_放量同步计划")
        self.assertEqual(snapshot["plans"][0]["smartBidType"], "SMART_BID_CONSERVATIVE")

    def test_latest_plan_snapshot_uses_current_full_mirror_batch(self):
        local_control.persist_response(
            "/api/qianchuan/plans",
            {
                "plans": [
                    {"id": 31, "name": "SC_历史放量计划", "smartBidType": "SMART_BID_CONSERVATIVE", "spend": 99},
                    {"id": 32, "name": "CY_历史控成本计划", "smartBidType": "SMART_BID_CUSTOM", "spend": 88},
                ]
            },
        )

        local_control.persist_current_plan_snapshot(
            [{"id": 31, "name": "SC_当前放量计划", "smartBidType": "SMART_BID_CONSERVATIVE", "spend": 11}]
        )

        plans = local_control.latest_plan_snapshot_payloads(limit=10)

        self.assertEqual([plan["name"] for plan in plans], ["SC_当前放量计划"])

    def test_system_scheduler_runs_all_auto_rule_actions(self):
        calls = []
        original_cloud_proxy_request = local_control.cloud_proxy_request
        original_notify_operation = local_control.notify_operation

        def fake_cloud_proxy_request(method, full_path, request_headers, raw_body=None, timeout=180):
            calls.append(
                {
                    "method": method,
                    "path": full_path,
                    "headers": dict(request_headers),
                    "body": local_control.decode_json(raw_body),
                    "timeout": timeout,
                }
            )
            return 200, {"ok": True, "actions": [], "plans": {"total": 0}}, ""

        try:
            local_control.cloud_proxy_request = fake_cloud_proxy_request
            local_control.notify_operation = lambda *args, **kwargs: {"ok": True, "skipped": True}

            result = local_control.run_system_step_roi_rules("system-token")
        finally:
            local_control.cloud_proxy_request = original_cloud_proxy_request
            local_control.notify_operation = original_notify_operation

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["path"], "/api/qianchuan/actions/run-rules")
        self.assertEqual(calls[0]["headers"]["X-QC-Admin-Token"], "system-token")
        self.assertEqual(calls[0]["body"]["ruleActions"], local_control.AUTO_RULE_ACTIONS)
        self.assertEqual(calls[0]["body"]["source"], "system-step-roi-rules")

        with sqlite3.connect(local_control.DB_PATH) as conn:
            row = conn.execute("select operator, operation, ok from operation_logs order by id desc limit 1").fetchone()

        self.assertEqual(row[0], "system-scheduler")
        self.assertEqual(row[1], "run-rules")
        self.assertEqual(row[2], 1)

    def test_system_scheduler_runs_budget_reset_once_in_midnight_window(self):
        calls = []
        original_cloud_proxy_request = local_control.cloud_proxy_request
        original_notify_operation = local_control.notify_operation

        def fake_cloud_proxy_request(method, full_path, request_headers, raw_body=None, timeout=180):
            calls.append(local_control.decode_json(raw_body))
            body = local_control.decode_json(raw_body)
            return (
                200,
                {
                    "ok": True,
                    "targetBudget": body["budget"],
                    "planSmartBidTypes": body["planSmartBidTypes"],
                    "updateCount": 2,
                    "skippedCount": 3,
                },
                "",
            )

        try:
            local_control.cloud_proxy_request = fake_cloud_proxy_request
            local_control.notify_operation = lambda *args, **kwargs: {"ok": True, "skipped": True}

            first = local_control.run_due_system_budget_reset(
                "system-token",
                now=local_control.beijing_datetime(2026, 5, 27, 0, 1),
            )
            second = local_control.run_due_system_budget_reset(
                "system-token",
                now=local_control.beijing_datetime(2026, 5, 27, 0, 2),
            )
            outside_window = local_control.run_due_system_budget_reset(
                "system-token",
                now=local_control.beijing_datetime(2026, 5, 28, 0, 30),
            )
        finally:
            local_control.cloud_proxy_request = original_cloud_proxy_request
            local_control.notify_operation = original_notify_operation

        self.assertTrue(first["ran"])
        self.assertFalse(second["ran"])
        self.assertFalse(outside_window["ran"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [(item["budget"], item["planSmartBidTypes"]) for item in calls],
            [
                (300, ["SMART_BID_CUSTOM"]),
                (30, ["SMART_BID_CONSERVATIVE"]),
            ],
        )
        self.assertTrue(all(item["source"] == "system-midnight-budget-reset" for item in calls))
        self.assertTrue(all(item["batchSize"] == 10 for item in calls))
        self.assertEqual(first["result"]["updateCount"], 4)
        self.assertEqual(first["result"]["skippedCount"], 6)
        self.assertEqual(first["result"]["budgetTargets"]["SMART_BID_CUSTOM"], 300)
        self.assertEqual(first["result"]["budgetTargets"]["SMART_BID_CONSERVATIVE"], 30)

    def test_system_budget_reset_sends_start_and_finish_reports_to_wecom(self):
        calls = []
        messages = []
        operation_notifications = []
        original_cloud_proxy_request = local_control.cloud_proxy_request
        original_send_wecom_message = local_control.send_wecom_message
        original_notify_operation = local_control.notify_operation

        def fake_cloud_proxy_request(method, full_path, request_headers, raw_body=None, timeout=180):
            body = local_control.decode_json(raw_body)
            calls.append(body)
            return (
                200,
                {
                    "ok": True,
                    "targetBudget": body["budget"],
                    "planSmartBidTypes": body["planSmartBidTypes"],
                    "totalPlans": 10 if body["budget"] == 300 else 5,
                    "updateCount": 4 if body["budget"] == 300 else 2,
                    "skippedCount": 6 if body["budget"] == 300 else 3,
                    "chunkCount": 1,
                },
                "",
            )

        def fake_send_wecom_message(content, msgtype="markdown", mentioned_mobiles=None):
            messages.append({"content": content, "msgtype": msgtype})
            return {"ok": True, "skipped": False, "status": 200, "response": {"errcode": 0}}

        try:
            local_control.cloud_proxy_request = fake_cloud_proxy_request
            local_control.send_wecom_message = fake_send_wecom_message
            local_control.notify_operation = lambda *args, **kwargs: operation_notifications.append(args) or {"ok": True}

            result = local_control.run_system_budget_reset("system-token")
        finally:
            local_control.cloud_proxy_request = original_cloud_proxy_request
            local_control.send_wecom_message = original_send_wecom_message
            local_control.notify_operation = original_notify_operation

        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(messages), 2)
        self.assertEqual(operation_notifications, [])
        self.assertIn("开始", messages[0]["content"])
        self.assertIn("0点预算归位", messages[0]["content"])
        self.assertIn("控成本", messages[0]["content"])
        self.assertIn("300", messages[0]["content"])
        self.assertIn("放量", messages[0]["content"])
        self.assertIn("30", messages[0]["content"])
        self.assertIn("结束", messages[1]["content"])
        self.assertIn("成功", messages[1]["content"])
        self.assertIn("调整计划：6", messages[1]["content"])
        self.assertIn("跳过计划：9", messages[1]["content"])

        with sqlite3.connect(local_control.DB_PATH) as conn:
            rows = conn.execute(
                """
                select path, request_json
                from api_journal
                where path = '/api/local/notifications/wecom#system-scheduler'
                order by id asc
                """
            ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertEqual(local_control.decode_json(rows[0][1].encode("utf-8"))["stage"], "start")
        self.assertEqual(local_control.decode_json(rows[1][1].encode("utf-8"))["stage"], "finish")

    def test_operation_board_reads_local_system_scheduler_pause_and_restore_logs(self):
        paused_at = "2026-05-27T16:03:00+00:00"
        restored_at = "2026-05-27T18:00:00+00:00"
        rule_response = {
            "ok": True,
            "actions": [
                {
                    "plan": {
                        "id": 9001,
                        "name": "SC_本地止损计划",
                        "product": "测试商品",
                        "ownerPrefix": "SC",
                        "smartBidType": "SMART_BID_CUSTOM",
                    },
                    "rule": {"id": "step-roi", "name": "分段ROI止损", "action": "SPEND_STEP_ROI_STOP"},
                    "request": {"advertiser_id": 0, "ad_ids": [9001], "opt_status": "DISABLE"},
                    "response": {"code": 0, "message": "OK", "data": {"results": [{"ad_id": 9001, "flag": True}]}},
                }
            ],
            "plans": {"total": 1},
        }
        with sqlite3.connect(local_control.DB_PATH) as conn:
            conn.execute(
                """
                insert into operation_logs(created_at, operator, operation, target_type, target_id, path, ok, request_json, response_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paused_at,
                    "system-scheduler",
                    "run-rules",
                    "plans",
                    "",
                    "/api/qianchuan/actions/run-rules",
                    1,
                    json.dumps({"source": "system-step-roi-rules"}, ensure_ascii=False),
                    json.dumps(rule_response, ensure_ascii=False),
                ),
            )
            conn.execute(
                """
                insert into operation_logs(created_at, operator, operation, target_type, target_id, path, ok, request_json, response_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    restored_at,
                    "session",
                    "start-plan",
                    "plan",
                    "9001",
                    "/api/qianchuan/actions/enable",
                    1,
                    json.dumps({"ad_id": 9001}, ensure_ascii=False),
                    json.dumps({"ok": True, "response": {"code": 0}}, ensure_ascii=False),
                ),
            )

        board = local_control.local_operation_board_summary({}, {"date": ["2026-05-28"]})

        self.assertTrue(board["ok"])
        self.assertEqual(board["source"], "local-operation-board")
        self.assertEqual(board["autoPause"]["total"], 1)
        self.assertEqual(board["autoPause"]["pending"], 0)
        self.assertEqual(board["autoPause"]["restored"], 1)
        record = board["autoPause"]["records"][0]
        self.assertEqual(record["planId"], 9001)
        self.assertEqual(record["planName"], "SC_本地止损计划")
        self.assertEqual(record["status"], "restored")
        self.assertEqual(record["restoredAt"], restored_at)

    def test_operation_board_aggregates_local_budget_reset_logs(self):
        with sqlite3.connect(local_control.DB_PATH) as conn:
            for created_at, budget, smart_bid_types, update_count, skipped_count in (
                ("2026-05-27T16:01:00+00:00", 300, ["SMART_BID_CUSTOM"], 4, 6),
                ("2026-05-27T16:02:00+00:00", 30, ["SMART_BID_CONSERVATIVE"], 2, 3),
            ):
                request_data = {
                    "source": "system-midnight-budget-reset",
                    "budget": budget,
                    "planSmartBidTypes": smart_bid_types,
                }
                response_data = {
                    "ok": True,
                    "targetBudget": budget,
                    "planSmartBidTypes": smart_bid_types,
                    "totalPlans": update_count + skipped_count,
                    "updateCount": update_count,
                    "skippedCount": skipped_count,
                    "chunkCount": 1,
                }
                conn.execute(
                    """
                    insert into operation_logs(created_at, operator, operation, target_type, target_id, path, ok, request_json, response_json)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created_at,
                        "system-scheduler",
                        "reset-budgets",
                        "plans",
                        "daily-budget-reset",
                        "/api/qianchuan/actions/reset-budgets",
                        1,
                        json.dumps(request_data, ensure_ascii=False),
                        json.dumps(response_data, ensure_ascii=False),
                    ),
                )

        board = local_control.local_operation_board_summary({}, {"date": ["2026-05-28"]})

        self.assertEqual(len(board["budgetReset"]["runs"]), 2)
        self.assertEqual(board["budgetReset"]["latest"]["updateCount"], 6)
        self.assertEqual(board["budgetReset"]["latest"]["skippedCount"], 9)
        self.assertEqual(board["budgetReset"]["latest"]["budgetTargets"]["SMART_BID_CUSTOM"], 300)
        self.assertEqual(board["budgetReset"]["latest"]["budgetTargets"]["SMART_BID_CONSERVATIVE"], 30)

    def test_system_scheduler_error_logging_does_not_raise_when_db_is_locked(self):
        original_record_api = local_control.record_api
        try:
            def locked_record_api(*_args, **_kwargs):
                raise sqlite3.OperationalError("database is locked")

            local_control.record_api = locked_record_api
            local_control.record_system_scheduler_error("step-roi-rules", RuntimeError("boom"))
        finally:
            local_control.record_api = original_record_api

    def test_product_full_pause_notification_when_product_becomes_all_paused(self):
        messages = []
        original_send_wecom_message = local_control.send_wecom_message
        original_load_assignment_data = local_control.load_assignment_data

        def fake_send_wecom_message(content, msgtype="markdown", mentioned_mobiles=None):
            messages.append({"content": content, "msgtype": msgtype, "mentioned_mobiles": mentioned_mobiles or []})
            return {"ok": True, "skipped": False, "status": 200, "response": {"errcode": 0}}

        try:
            local_control.send_wecom_message = fake_send_wecom_message
            local_control.load_assignment_data = lambda: {
                "users": [
                    {
                        "id": 1,
                        "username": "13800138000",
                        "displayName": "Operator C",
                        "role": "operator",
                        "status": "active",
                        "planPrefixes": ["ST"],
                    }
                ],
                "shops": [],
                "planPrefixOptions": [{"prefix": "ST", "ownerName": "Operator C", "label": "ST Operator C"}],
            }
            response = {
                "ok": True,
                "plans": [
                    {
                        "id": 1001,
                        "name": "ST_测试计划A",
                        "product": "同一个测试商品",
                        "ownerPrefix": "ST",
                        "optStatus": "ENABLE",
                        "spend": 100,
                        "gmv": 80,
                    },
                    {
                        "id": 1002,
                        "name": "ST_测试计划B",
                        "product": "同一个测试商品",
                        "ownerPrefix": "ST",
                        "optStatus": "DISABLE",
                        "spend": 20,
                        "gmv": 0,
                    },
                ],
                "actions": [
                    {
                        "plan": {
                            "id": 1001,
                            "name": "ST_测试计划A",
                            "product": "同一个测试商品",
                            "ownerPrefix": "ST",
                            "optStatus": "ENABLE",
                            "spend": 100,
                            "gmv": 80,
                        },
                        "rule": {"id": "low-roi-stop", "name": "低 ROI 自动暂停", "action": "DISABLE"},
                        "request": {"ad_ids": [1001], "opt_status": "DISABLE"},
                        "response": {"code": 0, "message": "OK", "data": {"results": [{"ad_id": 1001, "flag": True}]}},
                    }
                ],
            }

            notifications = local_control.notify_product_full_pauses({"marketing_goal": "VIDEO_PROM_GOODS"}, response)
            duplicate = local_control.notify_product_full_pauses({"marketing_goal": "VIDEO_PROM_GOODS"}, response)
        finally:
            local_control.send_wecom_message = original_send_wecom_message
            local_control.load_assignment_data = original_load_assignment_data

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["productName"], "同一个测试商品")
        self.assertEqual(notifications[0]["planCount"], 2)
        self.assertIn("千川商品全停提醒", messages[0]["content"])
        self.assertEqual(messages[0]["mentioned_mobiles"], ["13800138000"])
        self.assertTrue(duplicate[0]["notification"]["skipped"])
        self.assertEqual(len(messages), 1)


if __name__ == "__main__":
    unittest.main()
