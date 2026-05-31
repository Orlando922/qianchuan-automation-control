#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest


APP_PATH = pathlib.Path(__file__).with_name("app.py")
SPEC = importlib.util.spec_from_file_location("qianchuan_oauth_app", APP_PATH)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


def plan(name, spend, gmv):
    return {
        "id": abs(hash(name)) % 1000000,
        "name": name,
        "spend": spend,
        "gmv": gmv,
        "orders": 1 if gmv else 0,
        "budget": 300,
    }


def typed_plan(name, spend, gmv, smart_bid_type):
    return {
        **plan(name, spend, gmv),
        "smartBidType": smart_bid_type,
    }


class PlanPrefixPermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db_path = app.DB_PATH
        app.DB_PATH = str(pathlib.Path(self.tmp.name) / "qianchuan-test.sqlite3")
        app.ensure_db()

    def tearDown(self):
        app.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def test_save_user_stores_plan_prefix_bindings(self):
        saved, error = app.save_user(
            {
                "username": "wushaocun",
                "displayName": "Operator A",
                "role": "operator",
                "password": "pw",
                "planPrefixes": ["SC"],
            }
        )

        self.assertIsNone(error)
        self.assertEqual(saved["planPrefixes"], ["SC"])
        self.assertEqual(saved["planAssignments"], [{"prefix": "SC", "ownerName": "Operator A", "label": "SC Operator A"}])
        self.assertEqual(saved["shopIds"], [])

    def test_plan_filter_uses_first_two_letters_of_plan_name(self):
        user = {
            "role": "operator",
            "planPrefixes": ["SC"],
        }
        plans = [
            app.annotate_plan_owner(plan("SC直播间冲量", 100, 250)),
            app.annotate_plan_owner(plan("CY商品卡测试", 80, 120)),
            app.annotate_plan_owner(plan("ST达人短视频", 60, 90)),
            app.annotate_plan_owner(plan("未知计划", 50, 70)),
        ]

        visible = app.filter_plans_for_user(plans, user)

        self.assertEqual([item["name"] for item in visible], ["SC直播间冲量"])
        self.assertEqual(visible[0]["ownerPrefix"], "SC")
        self.assertEqual(visible[0]["ownerName"], "Operator A")

    def test_save_user_allows_new_detected_plan_prefix(self):
        saved, error = app.save_user(
            {
                "username": "tq",
                "displayName": "唐青青",
                "role": "operator",
                "password": "pw",
                "planPrefixes": ["TQ"],
            }
        )

        self.assertIsNone(error)
        self.assertEqual(saved["planPrefixes"], ["TQ"])
        self.assertEqual(saved["planAssignments"], [{"prefix": "TQ", "ownerName": "唐青青", "label": "TQ 唐青青"}])

        plan_item = app.annotate_plan_owner(plan("TQ_全域推广_测试", 20, 30))
        self.assertEqual(plan_item["ownerPrefix"], "TQ")
        self.assertEqual(plan_item["ownerName"], "唐青青")
        self.assertEqual([item["name"] for item in app.filter_plans_for_user([plan_item], saved)], ["TQ_全域推广_测试"])

    def test_admin_dashboard_groups_by_operator_then_plans(self):
        app.save_user(
            {
                "username": "sc",
                "displayName": "Operator A",
                "role": "operator",
                "password": "pw",
                "planPrefixes": ["SC"],
            }
        )
        app.save_user(
            {
                "username": "cy",
                "displayName": "Operator B",
                "role": "operator",
                "password": "pw",
                "planPrefixes": ["CY"],
            }
        )
        admin = app.get_user_by_id(1)
        source_plans = [
            app.annotate_plan_owner(plan("SC直播间冲量", 100, 250)),
            app.annotate_plan_owner(plan("CY商品卡测试", 80, 120)),
            app.annotate_plan_owner(plan("ST达人短视频", 60, 90)),
        ]

        old_fetch = app.fetch_shop_plans_for_summary
        app.fetch_shop_plans_for_summary = lambda shop, start_time, end_time, marketing_goal, *args: (
            source_plans,
            len(source_plans),
            {"code": 0, "message": "ok"},
        )
        try:
            summary = app.dashboard_summary(admin, {})
        finally:
            app.fetch_shop_plans_for_summary = old_fetch

        users = {item["displayName"]: item for item in summary["users"]}
        self.assertEqual(summary["global"]["planCount"], 3)
        self.assertEqual(summary["global"]["spend"], 240)
        self.assertIn("Operator A", users)
        self.assertIn("Operator B", users)
        self.assertEqual(users["Operator A"]["planPrefixes"], ["SC"])
        self.assertEqual(users["Operator A"]["planCount"], 1)
        self.assertEqual(users["Operator A"]["plans"][0]["name"], "SC直播间冲量")
        self.assertEqual(users["Operator B"]["planPrefixes"], ["CY"])
        self.assertEqual(users["Operator B"]["plans"][0]["ownerPrefix"], "CY")

    def test_reset_visible_plan_budgets_batches_only_changed_plans(self):
        admin = app.get_user_by_id(1)
        source_plans = [
            app.annotate_plan_owner({**plan("SC_预算已归位", 10, 20), "budget": 300, "advertiserId": 11, "shopId": 1}),
            app.annotate_plan_owner({**plan("SC_预算需要归位", 20, 30), "budget": 500, "advertiserId": 11, "shopId": 1}),
            app.annotate_plan_owner({**plan("CY_预算需要归位", 30, 40), "budget": 100, "advertiserId": 12, "shopId": 1}),
        ]
        calls = []
        old_fetch = app.fetch_shop_plans_for_summary
        old_ocean_post = app.ocean_post
        app.fetch_shop_plans_for_summary = lambda shop, start_time, end_time, marketing_goal, *args: (
            source_plans,
            len(source_plans),
            {"code": 0, "message": "ok"},
        )
        app.ocean_post = lambda path, payload: calls.append((path, payload)) or {"code": 0, "message": "OK"}
        try:
            result, error = app.reset_visible_plan_budgets(admin, {"budget": 300, "planSmartBidTypes": ["SMART_BID_CUSTOM"]})
        finally:
            app.fetch_shop_plans_for_summary = old_fetch
            app.ocean_post = old_ocean_post

        self.assertIsNone(error)
        self.assertTrue(result["ok"])
        self.assertEqual(result["totalPlans"], 3)
        self.assertEqual(result["skippedCount"], 1)
        self.assertEqual(result["updateCount"], 2)
        self.assertEqual(len(calls), 2)
        updated_ids = [info["ad_id"] for _path, payload in calls for info in payload["update_budget_infos"]]
        self.assertNotIn(source_plans[0]["id"], updated_ids)
        self.assertIn(source_plans[1]["id"], updated_ids)
        self.assertIn(source_plans[2]["id"], updated_ids)

    def test_reset_visible_plan_budgets_defaults_to_both_types_and_batches_at_ten(self):
        admin = app.get_user_by_id(1)
        calls = []
        fetched_types = []

        def fake_fetch(shop, start_time, end_time, marketing_goal, smart_bid_type):
            fetched_types.append(smart_bid_type)
            return (
                [
                    app.annotate_plan_owner(
                        {
                            **typed_plan(f"SC_{smart_bid_type}_{index}", 10, 20, smart_bid_type),
                            "id": 1000 + len(fetched_types) * 100 + index,
                            "budget": 500,
                            "advertiserId": shop["advertiserId"],
                            "shopId": shop["shopId"],
                        }
                    )
                    for index in range(13)
                ],
                13,
                {"code": 0, "message": "ok"},
            )

        old_fetch = app.fetch_shop_plans_for_summary
        old_ocean_post = app.ocean_post
        app.fetch_shop_plans_for_summary = fake_fetch
        app.ocean_post = lambda path, payload: calls.append(payload) or {"code": 0, "message": "OK"}
        try:
            result, error = app.reset_visible_plan_budgets(admin, {"budget": 300})
        finally:
            app.fetch_shop_plans_for_summary = old_fetch
            app.ocean_post = old_ocean_post

        self.assertIsNone(error)
        self.assertTrue(result["ok"])
        self.assertEqual(fetched_types, ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"])
        self.assertEqual(result["planSmartBidTypes"], ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"])
        self.assertEqual(result["updateCount"], 26)
        self.assertEqual([len(call["update_budget_infos"]) for call in calls], [10, 10, 6])

    def test_reset_visible_plan_budgets_uses_type_targets_and_skips_small_delta(self):
        admin = app.get_user_by_id(1)
        calls = []
        fetched_types = []

        def fake_fetch(shop, start_time, end_time, marketing_goal, smart_bid_type):
            fetched_types.append(smart_bid_type)
            if smart_bid_type == "SMART_BID_CUSTOM":
                plans = [
                    {
                        **typed_plan("SC_控成本归位", 10, 20, smart_bid_type),
                        "id": 101,
                        "budget": 500,
                        "advertiserId": shop["advertiserId"],
                        "shopId": shop["shopId"],
                    }
                ]
            else:
                plans = [
                    {
                        **typed_plan("SC_放量可降", 10, 20, smart_bid_type),
                        "id": 201,
                        "budget": 300,
                        "advertiserId": shop["advertiserId"],
                        "shopId": shop["shopId"],
                    },
                    {
                        **typed_plan("SC_放量小幅差额", 10, 20, smart_bid_type),
                        "id": 202,
                        "budget": 50,
                        "advertiserId": shop["advertiserId"],
                        "shopId": shop["shopId"],
                    },
                ]
            return ([app.annotate_plan_owner(item) for item in plans], len(plans), {"code": 0, "message": "ok"})

        old_fetch = app.fetch_shop_plans_for_summary
        old_ocean_post = app.ocean_post
        app.fetch_shop_plans_for_summary = fake_fetch
        app.ocean_post = lambda path, payload: calls.append(payload) or {"code": 0, "message": "OK"}
        try:
            result, error = app.reset_visible_plan_budgets(
                admin,
                {
                    "budgetTargets": {
                        "SMART_BID_CUSTOM": 300,
                        "SMART_BID_CONSERVATIVE": 30,
                    },
                    "planSmartBidTypes": ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"],
                },
            )
        finally:
            app.fetch_shop_plans_for_summary = old_fetch
            app.ocean_post = old_ocean_post

        self.assertIsNone(error)
        self.assertTrue(result["ok"])
        self.assertEqual(fetched_types, ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"])
        self.assertEqual(result["budgetTargets"]["SMART_BID_CUSTOM"], 300)
        self.assertEqual(result["budgetTargets"]["SMART_BID_CONSERVATIVE"], 30)
        self.assertEqual(result["updateCount"], 2)
        self.assertEqual(result["skippedCount"], 1)
        self.assertEqual(result["limitedSkipCount"], 1)
        update_infos = [info for payload in calls for info in payload["update_budget_infos"]]
        self.assertEqual(
            [(info["ad_id"], info["budget"]) for info in update_infos],
            [(101, 300), (201, 30)],
        )

    def test_visible_plans_fetches_cost_control_and_volume_by_default(self):
        admin = app.get_user_by_id(1)
        calls = []

        def fake_fetch(shop, start_time, end_time, marketing_goal, smart_bid_type):
            calls.append(smart_bid_type)
            return (
                [
                    app.annotate_plan_owner(
                        {
                            **typed_plan(f"SC_{smart_bid_type}", 10, 20, smart_bid_type),
                            "advertiserId": shop["advertiserId"],
                            "shopId": shop["shopId"],
                        }
                    )
                ],
                1,
                {"code": 0, "message": "ok", "request_id": smart_bid_type},
            )

        old_fetch = app.fetch_shop_plans_for_summary
        app.fetch_shop_plans_for_summary = fake_fetch
        try:
            result = app.qianchuan_visible_plans({"page": ["1"], "page_size": ["20"]}, admin)
        finally:
            app.fetch_shop_plans_for_summary = old_fetch

        self.assertEqual(calls, ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"])
        self.assertEqual(result["page_info"]["total_num"], 2)
        self.assertEqual(
            [plan["smartBidType"] for plan in result["plans"]],
            ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"],
        )
        self.assertEqual(result["planSmartBidTypes"], ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"])

    def test_loaded_legacy_rules_default_to_cost_control_plan_type(self):
        legacy_rule = {
            "id": "legacy-stop",
            "enabled": True,
            "action": "DISABLE",
            "minSpend": 100,
            "roiBelow": 1.2,
        }

        app.save_rules([legacy_rule])
        loaded = app.load_rules()

        self.assertEqual(loaded[0]["planSmartBidTypes"], ["SMART_BID_CUSTOM"])

    def test_cost_control_rule_does_not_hit_volume_plan(self):
        rule = {
            "id": "cost-control-stop",
            "enabled": True,
            "action": "DISABLE",
            "minSpend": 100,
            "roiBelow": 1.2,
            "planSmartBidTypes": ["SMART_BID_CUSTOM"],
        }
        volume_plan = app.annotate_plan_owner(typed_plan("SC_放量低ROI", 150, 60, "SMART_BID_CONSERVATIVE"))
        cost_control_plan = app.annotate_plan_owner(typed_plan("SC_控成本低ROI", 150, 60, "SMART_BID_CUSTOM"))

        self.assertIsNone(app.evaluate_rule(volume_plan, rule))
        self.assertIsNotNone(app.evaluate_rule(cost_control_plan, rule))

    def test_low_roi_rule_respects_after_minutes_before_pausing(self):
        rule = {
            "id": "low-roi-after-minutes",
            "enabled": True,
            "action": "DISABLE",
            "afterMinutes": 60,
            "minSpend": 90,
            "roiBelow": 1.3,
            "planSmartBidTypes": ["SMART_BID_CUSTOM"],
        }
        early_plan = {
            **app.annotate_plan_owner(typed_plan("SC_低ROI未到时间", 120, 60, "SMART_BID_CUSTOM")),
            "elapsedMinutes": 45,
        }
        mature_plan = {**early_plan, "elapsedMinutes": 61}

        self.assertIsNone(app.evaluate_rule(early_plan, rule, now="2026-05-22T00:00:00+00:00"))
        self.assertIsNotNone(app.evaluate_rule(mature_plan, rule, now="2026-05-22T00:00:00+00:00"))

    def test_run_rules_fetches_all_visible_plan_pages(self):
        admin = app.get_user_by_id(1)
        rule = {
            "id": "second-page-low-roi",
            "enabled": True,
            "action": "DISABLE",
            "minSpend": 90,
            "roiBelow": 1.3,
            "planSmartBidTypes": ["SMART_BID_CUSTOM"],
        }
        second_page_plan = app.annotate_plan_owner(
            {**typed_plan("SC_第二页低ROI", 120, 60, "SMART_BID_CUSTOM"), "advertiserId": 11, "shopId": 1}
        )
        calls = []
        pages_seen = []
        old_visible = app.qianchuan_visible_plans
        old_load_rules = app.load_rules
        old_ocean_post = app.ocean_post

        def fake_visible(query, user):
            page = int((query.get("page") or ["1"])[0])
            pages_seen.append(page)
            return {
                "advertiser_id": 11,
                "page_info": {"page": page, "page_size": 500, "total_num": 501, "total_page": 2},
                "plans": [] if page == 1 else [second_page_plan],
            }

        app.qianchuan_visible_plans = fake_visible
        app.load_rules = lambda: [rule]
        app.ocean_post = lambda path, payload: calls.append((path, payload)) or {"code": 0, "message": "OK"}
        try:
            result = app.execute_rules_for_user(admin, {"ruleActions": ["DISABLE"], "page_size": 500})
        finally:
            app.qianchuan_visible_plans = old_visible
            app.load_rules = old_load_rules
            app.ocean_post = old_ocean_post

        self.assertEqual(pages_seen, [1, 2])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(calls[0][1]["ad_ids"], [second_page_plan["id"]])

    def test_pause_rule_wins_over_budget_rule_on_same_plan(self):
        admin = app.get_user_by_id(1)
        rules = [
            {
                "id": "add-budget-overlap",
                "enabled": True,
                "action": "ADD_BUDGET",
                "minSpend": 90,
                "roiAbove": 1.5,
                "budgetMode": "fixed",
                "budgetValue": 100,
                "planSmartBidTypes": ["SMART_BID_CUSTOM"],
            },
            {
                "id": "pause-overlap",
                "enabled": True,
                "action": "DISABLE",
                "minSpend": 90,
                "roiBelow": 1.8,
                "planSmartBidTypes": ["SMART_BID_CUSTOM"],
            },
        ]
        overlapped_plan = app.annotate_plan_owner(
            {**typed_plan("SC_同时命中暂停和加预算", 120, 192, "SMART_BID_CUSTOM"), "advertiserId": 11, "shopId": 1}
        )
        calls = []
        old_visible = app.qianchuan_visible_plans
        old_load_rules = app.load_rules
        old_ocean_post = app.ocean_post

        app.qianchuan_visible_plans = lambda query, user: {
            "advertiser_id": 11,
            "page_info": {"page": 1, "page_size": 500, "total_num": 1, "total_page": 1},
            "plans": [overlapped_plan],
        }
        app.load_rules = lambda: rules
        app.ocean_post = lambda path, payload: calls.append((path, payload)) or {"code": 0, "message": "OK"}
        try:
            result = app.execute_rules_for_user(admin, {"page_size": 500})
        finally:
            app.qianchuan_visible_plans = old_visible
            app.load_rules = old_load_rules
            app.ocean_post = old_ocean_post

        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["rule"]["id"], "pause-overlap")
        self.assertIn("/ad/status/update/", calls[0][0])
        self.assertEqual(calls[0][1]["opt_status"], "DISABLE")

    def test_auto_rules_skip_plans_that_are_already_paused(self):
        admin = app.get_user_by_id(1)
        rule = {
            "id": "paused-low-roi",
            "enabled": True,
            "action": "DISABLE",
            "minSpend": 90,
            "roiBelow": 1.3,
            "planSmartBidTypes": ["SMART_BID_CUSTOM"],
        }
        paused_plan = app.annotate_plan_owner(
            {**typed_plan("SC_已暂停低ROI", 120, 60, "SMART_BID_CUSTOM"), "advertiserId": 11, "shopId": 1, "optStatus": "DISABLE"}
        )
        calls = []
        old_visible = app.qianchuan_visible_plans
        old_load_rules = app.load_rules
        old_ocean_post = app.ocean_post

        app.qianchuan_visible_plans = lambda query, user: {
            "advertiser_id": 11,
            "page_info": {"page": 1, "page_size": 500, "total_num": 1, "total_page": 1},
            "plans": [paused_plan],
        }
        app.load_rules = lambda: [rule]
        app.ocean_post = lambda path, payload: calls.append((path, payload)) or {"code": 0, "message": "OK"}
        try:
            result = app.execute_rules_for_user(admin, {"page_size": 500})
        finally:
            app.qianchuan_visible_plans = old_visible
            app.load_rules = old_load_rules
            app.ocean_post = old_ocean_post

        self.assertEqual(result["actions"], [])
        self.assertEqual(calls, [])

    def test_cloud_auto_scheduler_covers_all_enabled_rule_actions(self):
        self.assertEqual(
            set(app.CLOUD_AUTO_RULE_ACTIONS),
            {
                "DISABLE",
                "SPEND_STEP_ROI_STOP",
                "NEAR_BUDGET_ROI_ADD_BUDGET",
                "HOURLY_SPEND_INCREASE_ROI_GOAL",
                "ADD_BUDGET",
                "NOTIFY",
            },
        )

    def test_spend_step_roi_rule_waits_then_hits_low_incremental_roi(self):
        rule = {
            "id": "step-roi",
            "enabled": True,
            "action": "SPEND_STEP_ROI_STOP",
            "spendStep": 100,
            "delayMinutes": 10,
            "roiBelow": 1.2,
        }
        base_plan = {
            **app.annotate_plan_owner(plan("SC_分段止损", 100, 200)),
            "advertiserId": 11,
            "realSettleGmv": 200,
        }

        first = app.evaluate_rule(base_plan, rule, now="2026-05-22T00:00:00+00:00")
        self.assertIsNone(first)

        crossed_plan = {**base_plan, "spend": 205, "gmv": 240, "realSettleGmv": 240}
        second = app.evaluate_rule(crossed_plan, rule, now="2026-05-22T00:05:00+00:00")
        self.assertIsNone(second)

        early_plan = {**base_plan, "spend": 215, "gmv": 245, "realSettleGmv": 245}
        early = app.evaluate_rule(early_plan, rule, now="2026-05-22T00:12:00+00:00")
        self.assertIsNone(early)

        due_plan = {**base_plan, "spend": 220, "gmv": 250, "realSettleGmv": 250}
        hit = app.evaluate_rule(due_plan, rule, now="2026-05-22T00:16:00+00:00")

        self.assertIsNotNone(hit)
        self.assertEqual(hit["rule"]["action"], "SPEND_STEP_ROI_STOP")
        self.assertEqual(hit["checkpoint"]["deltaSpend"], 105)
        self.assertAlmostEqual(hit["checkpoint"]["deltaRoi"], 50 / 105, places=4)
        self.assertIn("incremental net ROI", hit["reason"])

    def test_run_rule_action_filter_keeps_only_requested_actions(self):
        rules = [
            {"id": "old-stop", "action": "DISABLE"},
            {"id": "step-stop", "action": "SPEND_STEP_ROI_STOP"},
            {"id": "budget", "action": "ADD_BUDGET"},
        ]

        filtered = app.filter_rules_for_run_request(rules, {"ruleActions": ["SPEND_STEP_ROI_STOP"]})

        self.assertEqual([rule["id"] for rule in filtered], ["step-stop"])

    def test_deleted_rule_is_kept_for_restore_but_not_executed(self):
        admin = app.get_user_by_id(1)
        source_plans = [
            app.annotate_plan_owner(
                {**plan("SC_误删规则测试", 120, 60), "budget": 300, "advertiserId": 11, "shopId": 1}
            )
        ]
        deleted_rule = {
            "id": "deleted-stop-rule",
            "name": "已删暂停规则",
            "enabled": True,
            "action": "DISABLE",
            "minSpend": 90,
            "roiBelow": 1.3,
            "deletedAt": "2026-05-22T08:40:00+00:00",
        }
        calls = []
        old_visible = app.qianchuan_visible_plans
        old_load_rules = app.load_rules
        old_ocean_post = app.ocean_post
        app.qianchuan_visible_plans = lambda query, user: {
            "page_info": {"total_num": 1},
            "plans": source_plans,
        }
        app.load_rules = lambda: [deleted_rule]
        app.ocean_post = lambda path, payload: calls.append((path, payload)) or {"code": 0, "message": "OK"}
        try:
            hit = app.evaluate_rule(source_plans[0], deleted_rule)
            result = app.execute_rules_for_user(admin, {})
        finally:
            app.qianchuan_visible_plans = old_visible
            app.load_rules = old_load_rules
            app.ocean_post = old_ocean_post

        self.assertIsNone(hit)
        self.assertEqual(result["actions"], [])
        self.assertEqual(calls, [])

    def test_near_budget_roi_rule_hits_when_budget_is_nearly_spent(self):
        rule = {
            "id": "near-budget-scale",
            "enabled": True,
            "action": "NEAR_BUDGET_ROI_ADD_BUDGET",
            "budgetRemainingPercent": 15,
            "roiAbove": 2.2,
            "budgetValue": 100,
        }
        near_budget_plan = {
            **app.annotate_plan_owner(plan("SC_预算将尽高ROI", 270, 702)),
            "budget": 300,
            "advertiserId": 11,
        }

        hit = app.evaluate_rule(near_budget_plan, rule)

        self.assertIsNotNone(hit)
        self.assertEqual(hit["rule"]["action"], "NEAR_BUDGET_ROI_ADD_BUDGET")
        self.assertAlmostEqual(hit["budgetRemainingPercent"], 10)
        self.assertIn("daily budget remaining", hit["reason"])

    def test_near_budget_roi_rule_adds_fixed_budget_without_daily_limit(self):
        admin = app.get_user_by_id(1)
        source_plans = [
            app.annotate_plan_owner(
                {**plan("SC_预算将尽高ROI", 270, 702), "budget": 300, "advertiserId": 11, "shopId": 1}
            )
        ]
        rule = {
            "id": "near-budget-scale",
            "name": "预算将尽继续加",
            "enabled": True,
            "action": "NEAR_BUDGET_ROI_ADD_BUDGET",
            "budgetRemainingPercent": 15,
            "roiAbove": 2.2,
            "budgetMode": "fixed",
            "budgetValue": 100,
        }
        calls = []
        old_visible = app.qianchuan_visible_plans
        old_load_rules = app.load_rules
        old_ocean_post = app.ocean_post
        app.qianchuan_visible_plans = lambda query, user: {
            "page_info": {"total_num": 1},
            "plans": source_plans,
        }
        app.load_rules = lambda: [rule]
        app.ocean_post = lambda path, payload: calls.append((path, payload)) or {"code": 0, "message": "OK"}
        try:
            result = app.execute_rules_for_user(admin, {"ruleActions": ["NEAR_BUDGET_ROI_ADD_BUDGET"]})
        finally:
            app.qianchuan_visible_plans = old_visible
            app.load_rules = old_load_rules
            app.ocean_post = old_ocean_post

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(calls[0][0], "/open_api/v1.0/qianchuan/uni_promotion/ad/budget/update/")
        self.assertEqual(calls[0][1]["update_budget_infos"][0]["budget"], 400)

    def test_near_budget_roi_rule_notifies_when_account_month_budget_is_insufficient(self):
        admin = app.get_user_by_id(1)
        source_plans = [
            app.annotate_plan_owner(
                {**plan("SC_预算将尽高ROI", 270, 702), "budget": 300, "advertiserId": 11, "shopId": 1}
            )
        ]
        rule = {
            "id": "near-budget-scale",
            "name": "预算将尽继续加",
            "enabled": True,
            "action": "NEAR_BUDGET_ROI_ADD_BUDGET",
            "budgetRemainingPercent": 15,
            "roiAbove": 2.2,
            "budgetMode": "fixed",
            "budgetValue": 100,
        }
        old_visible = app.qianchuan_visible_plans
        old_load_rules = app.load_rules
        old_ocean_post = app.ocean_post
        app.qianchuan_visible_plans = lambda query, user: {
            "page_info": {"total_num": 1},
            "plans": source_plans,
        }
        app.load_rules = lambda: [rule]
        app.ocean_post = lambda path, payload: {"code": 40001, "message": "账户月预算不足"}
        try:
            result = app.execute_rules_for_user(admin, {"ruleActions": ["NEAR_BUDGET_ROI_ADD_BUDGET"]})
        finally:
            app.qianchuan_visible_plans = old_visible
            app.load_rules = old_load_rules
            app.ocean_post = old_ocean_post

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["actions"]), 2)
        self.assertEqual(result["actions"][0]["rule"]["action"], "NEAR_BUDGET_ROI_ADD_BUDGET")
        self.assertEqual(result["actions"][1]["rule"]["action"], "NOTIFY")
        self.assertEqual(result["actions"][1]["request"]["reason"], "account_month_budget_insufficient")

    def test_hourly_spend_rule_hits_and_caps_new_roi_goal(self):
        rule = {
            "id": "hourly-roi-goal",
            "enabled": True,
            "action": "HOURLY_SPEND_INCREASE_ROI_GOAL",
            "hourlySpendAbove": 100,
            "roiGoalIncrement": 0.2,
            "maxRoiGoal": 2.4,
        }
        fast_plan = {
            **app.annotate_plan_owner(plan("SC_小时消耗高", 260, 400)),
            "elapsedMinutes": 120,
            "roiGoal": 2.3,
            "advertiserId": 11,
        }

        hit = app.evaluate_rule(fast_plan, rule)

        self.assertIsNotNone(hit)
        self.assertEqual(hit["rule"]["action"], "HOURLY_SPEND_INCREASE_ROI_GOAL")
        self.assertAlmostEqual(hit["hourlySpend"], 130)
        self.assertAlmostEqual(hit["newRoiGoal"], 2.4)

    def test_hourly_spend_rule_updates_roi_goal_through_official_endpoint(self):
        admin = app.get_user_by_id(1)
        source_plans = [
            app.annotate_plan_owner(
                {**plan("SC_小时消耗高", 260, 400), "elapsedMinutes": 120, "roiGoal": 1.8, "advertiserId": 11, "shopId": 1}
            )
        ]
        rule = {
            "id": "hourly-roi-goal",
            "name": "小时消耗高调目标",
            "enabled": True,
            "action": "HOURLY_SPEND_INCREASE_ROI_GOAL",
            "hourlySpendAbove": 100,
            "roiGoalIncrement": 0.2,
            "maxRoiGoal": 2.4,
        }
        calls = []
        old_visible = app.qianchuan_visible_plans
        old_load_rules = app.load_rules
        old_ocean_post = app.ocean_post
        app.qianchuan_visible_plans = lambda query, user: {
            "page_info": {"total_num": 1},
            "plans": source_plans,
        }
        app.load_rules = lambda: [rule]
        app.ocean_post = lambda path, payload: calls.append((path, payload)) or {"code": 0, "message": "OK"}
        try:
            result = app.execute_rules_for_user(admin, {"ruleActions": ["HOURLY_SPEND_INCREASE_ROI_GOAL"]})
        finally:
            app.qianchuan_visible_plans = old_visible
            app.load_rules = old_load_rules
            app.ocean_post = old_ocean_post

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(calls[0][0], "/open_api/v1.0/qianchuan/roi/goal/update/")
        self.assertEqual(calls[0][1]["roi_goal_updates"][0]["roi_goal"], 2.0)

    def test_daily_budget_scheduler_claims_only_midnight_window_once(self):
        early = app.daily_budget_reset_run_key("2026-05-22T15:59:00+00:00")
        in_window = app.daily_budget_reset_run_key("2026-05-22T16:05:00+00:00")
        late = app.daily_budget_reset_run_key("2026-05-22T17:00:00+00:00")

        self.assertEqual(early, "")
        self.assertEqual(in_window, "2026-05-23")
        self.assertEqual(late, "")
        self.assertTrue(app.claim_scheduled_job("daily-budget-reset", in_window))
        self.assertFalse(app.claim_scheduled_job("daily-budget-reset", in_window))

    def test_daily_budget_scheduler_requests_both_plan_types(self):
        captured = {}

        old_bootstrap = app.bootstrap_admin_user
        old_reset = app.reset_visible_plan_budgets
        app.bootstrap_admin_user = lambda: app.get_user_by_id(1)

        def fake_reset(user, body):
            captured.update(body)
            return {"ok": True, "actions": []}, None

        app.reset_visible_plan_budgets = fake_reset
        try:
            result = app.run_cloud_budget_reset_once("2026-05-22T16:05:00+00:00")
        finally:
            app.bootstrap_admin_user = old_bootstrap
            app.reset_visible_plan_budgets = old_reset

        self.assertTrue(result["ok"])
        self.assertEqual(captured["planSmartBidTypes"], ["SMART_BID_CUSTOM", "SMART_BID_CONSERVATIVE"])
        self.assertEqual(captured["budgetTargets"]["SMART_BID_CUSTOM"], 300)
        self.assertEqual(captured["budgetTargets"]["SMART_BID_CONSERVATIVE"], 30)

    def test_operation_board_marks_auto_pauses_restored_after_enable(self):
        admin = app.get_user_by_id(1)
        action_response = {
            "ok": True,
            "actions": [
                {
                    "plan": {
                        "id": 101,
                        "name": "SC_止损暂停",
                        "product": "测试商品",
                        "ownerPrefix": "SC",
                        "ownerName": "Operator A",
                        "optStatus": "DISABLE",
                    },
                    "rule": {"id": "spend-step-roi-stop", "name": "每消耗一段后止损", "action": "SPEND_STEP_ROI_STOP"},
                    "request": {"advertiser_id": 11, "data": [{"ad_id": 101, "opt_status": "DISABLE"}]},
                    "response": {"code": 0, "message": "OK"},
                },
                {
                    "plan": {
                        "id": 102,
                        "name": "CY_止损暂停",
                        "product": "测试商品2",
                        "ownerPrefix": "CY",
                        "ownerName": "Operator B",
                        "optStatus": "DISABLE",
                    },
                    "rule": {"id": "spend-step-roi-stop", "name": "每消耗一段后止损", "action": "SPEND_STEP_ROI_STOP"},
                    "request": {"advertiser_id": 11, "data": [{"ad_id": 102, "opt_status": "DISABLE"}]},
                    "response": {"code": 0, "message": "OK"},
                },
            ],
        }
        with sqlite3.connect(app.DB_PATH) as conn:
            conn.execute(
                """
                insert into scheduled_job_runs(job_name, run_key, status, started_at, finished_at, request_json, response_json, error_text)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "step-roi-rules",
                    "2026-05-26T01:00:00+00:00",
                    "success",
                    "2026-05-26T01:00:00+00:00",
                    "2026-05-26T01:00:10+00:00",
                    "{}",
                    json.dumps(action_response, ensure_ascii=False),
                    "",
                ),
            )
        app.log_action(
            "enable",
            False,
            {"advertiser_id": 11, "data": [{"ad_id": 101, "opt_status": "ENABLE"}]},
            {"code": 0, "message": "OK"},
        )

        board = app.operation_board_summary(admin, {"date": ["2026-05-26"]}, now="2026-05-26T10:00:00+00:00")

        self.assertEqual(board["date"], "2026-05-26")
        self.assertEqual(board["autoPause"]["total"], 2)
        self.assertEqual(board["autoPause"]["restored"], 1)
        self.assertEqual(board["autoPause"]["pending"], 1)
        records = {item["planId"]: item for item in board["autoPause"]["records"]}
        self.assertTrue(records[101]["restored"])
        self.assertFalse(records[102]["restored"])
        self.assertEqual(records[102]["status"], "pending")

    def test_interval_scheduler_claims_five_minute_slots_once(self):
        slot = app.interval_run_key("2026-05-22T07:58:12+00:00", 300)

        self.assertEqual(slot, "2026-05-22T07:55:00+00:00")
        self.assertTrue(app.claim_scheduled_job("step-roi-rules", slot))
        self.assertFalse(app.claim_scheduled_job("step-roi-rules", slot))

    def test_bootstrap_admin_user_returns_public_dict_for_scheduler(self):
        user = app.bootstrap_admin_user()

        self.assertEqual(user["role"], "admin")
        self.assertEqual(user.get("username"), "admin")
        self.assertIn("planPrefixes", user)


if __name__ == "__main__":
    unittest.main()
