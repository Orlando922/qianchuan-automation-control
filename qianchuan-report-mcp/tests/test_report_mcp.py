import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


def make_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            create table report_runs (
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
            );
            create table report_shop_rows (
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
            );
            create table report_plan_rows (
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
            );
            """
        )
        conn.execute(
            """
            insert into report_runs(
                id, created_at, scope, start_time, end_time, marketing_goal,
                shop_count, plan_count, spend, gmv, roi, payload_json
            ) values (1, ?, 'all', ?, ?, 'VIDEO_PROM_GOODS', 1, 2, 100, 250, 2.5, ?)
            """,
            (
                "2026-05-20T00:00:00+08:00",
                "2026-05-19 00:00:00",
                "2026-05-19 23:59:59",
                json.dumps({"global": {"spend": 100, "gmv": 250, "roi": 2.5}}, ensure_ascii=False),
            ),
        )
        conn.execute(
            """
            insert into report_shop_rows(
                report_id, shop_id, advertiser_id, shop_name, spend, gmv, roi,
                orders, plan_count, payload_json
            ) values (1, 0, 0, 'Demo Shop', 100, 250, 2.5, 8, 2, ?)
            """,
            (json.dumps({"shopName": "Demo Shop"}, ensure_ascii=False),),
        )
        conn.execute(
            """
            insert into report_plan_rows(
                report_id, shop_id, advertiser_id, plan_id, plan_name,
                opt_status, status, spend, gmv, roi, orders, budget, payload_json
            ) values (1, 0, 0, 101, 'SC_高ROI计划',
                'ENABLE', 'DELIVERY_OK', 80, 240, 3, 6, 411, ?)
            """,
            (json.dumps({"name": "SC_高ROI计划", "ownerPrefix": "SC", "ownerName": "Operator A", "extraField": "kept"}, ensure_ascii=False),),
        )
        conn.execute(
            """
            insert into report_plan_rows(
                report_id, shop_id, advertiser_id, plan_id, plan_name,
                opt_status, status, spend, gmv, roi, orders, budget, payload_json
            ) values (1, 0, 0, 102, 'CY_低ROI计划',
                'DISABLE', 'DELIVERY_OK', 20, 10, 0.5, 2, 511, ?)
            """,
            (json.dumps({"name": "CY_低ROI计划", "ownerPrefix": "CY", "ownerName": "Operator B"}, ensure_ascii=False),),
        )
        conn.commit()
    finally:
        conn.close()


class ReportMcpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "reports.sqlite3"
        make_db(self.db_path)
        self.repo = server.ReportRepository(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tools_are_report_only_and_no_sql_tool_exists(self):
        names = [tool["name"] for tool in server.tool_definitions()]
        self.assertTrue(names)
        self.assertTrue(all("report" in name for name in names))
        blocked_terms = ("sql", "write", "action", "pause", "enable", "budget", "user", "shop_update")
        self.assertFalse(any(term in name for name in names for term in blocked_terms))

    def test_status_and_runs_read_report_tables(self):
        status = self.repo.status()
        self.assertEqual(status["tables"]["report_runs"], 1)
        self.assertEqual(status["tables"]["report_plan_rows"], 2)
        runs = self.repo.list_runs({"date_from": "2026-05-19", "date_to": "2026-05-19"})
        self.assertEqual(runs["items"][0]["id"], 1)
        self.assertEqual(runs["items"][0]["roi"], 2.5)

    def test_plan_query_filters_sorts_and_can_include_payload(self):
        plans = self.repo.plans({"report_id": 1, "min_roi": 1, "sort_by": "roi", "sort_dir": "desc", "include_payload": True})
        self.assertEqual(plans["total"], 1)
        self.assertEqual(plans["items"][0]["plan_name"], "SC_高ROI计划")
        self.assertEqual(plans["items"][0]["owner_prefix"], "SC")
        self.assertEqual(plans["items"][0]["payload"]["extraField"], "kept")

    def test_plan_query_can_filter_by_owner_prefix(self):
        plans = self.repo.plans({"report_id": 1, "owner_prefix": "CY", "sort_by": "spend", "sort_dir": "desc"})
        self.assertEqual(plans["total"], 1)
        self.assertEqual(plans["items"][0]["owner_name"], "Operator B")

    def test_summary_includes_owner_aggregates(self):
        summary = self.repo.summary({"report_id": 1})
        self.assertEqual(summary["owners"][0]["owner_prefix"], "SC")
        self.assertEqual(summary["owners"][0]["spend"], 80)

    def test_database_connection_is_query_only(self):
        with self.repo.connect() as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("insert into report_runs(created_at, start_time, end_time, marketing_goal, payload_json) values('x','x','x','x','{}')")

    def test_json_rpc_tool_call_returns_text_content(self):
        response = server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "qianchuan_report_status", "arguments": {}}},
            self.repo,
        )
        self.assertEqual(response["id"], 1)
        self.assertIn("content", response["result"])
        body = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(body["tables"]["report_runs"], 1)


if __name__ == "__main__":
    unittest.main()
