from __future__ import annotations

import unittest
from pathlib import Path

from backend.core.data_quality import data_quality
from backend.core.excel_parser import parse_excel
from backend.core.execution_plan import build_execution_plan
from backend.core.field_mapping import preview_mapping
from backend.core.normalization import normalize_rows
from backend.core.profile_analyzer import analyze_profile

ROOT = Path(__file__).resolve().parents[1]


def sample_accounts(name: str = "level3_court.xlsx"):
    raw = parse_excel(ROOT / "samples" / name)
    preview = preview_mapping(raw.headers, raw.rows)
    mapping = {field: item["source_column"] for field, item in preview.items()}
    accounts, errors = normalize_rows(raw.rows, mapping, "exec_test")
    return accounts


class ExecutionPlanTests(unittest.TestCase):
    def test_builds_default_batches_and_tasks_from_tiers(self):
        accounts = sample_accounts()
        quality = data_quality(accounts)
        profile = analyze_profile(accounts)
        result = build_execution_plan({"id": "exec_test", "name": "执行样例"}, accounts, quality, profile, plan_id="plan_test")
        self.assertEqual(len(result["tasks"]), len(accounts))
        batch_names = {task["batch_name"] for task in result["tasks"]}
        self.assertTrue({"电话调解首轮", "重点户攻坚"} & batch_names)
        self.assertGreaterEqual(result["summary"]["task_count"], 12)
        self.assertGreater(result["summary"]["high_priority_count"], 0)

    def test_priority_rewards_phone_amount_and_court(self):
        accounts = sample_accounts()
        quality = data_quality(accounts)
        profile = analyze_profile(accounts)
        result = build_execution_plan({"id": "exec_test", "name": "执行样例"}, accounts, quality, profile, plan_id="plan_test")
        sorted_tasks = sorted(result["tasks"], key=lambda item: item["priority_score"], reverse=True)
        self.assertGreaterEqual(sorted_tasks[0]["priority_score"], sorted_tasks[-1]["priority_score"])
        self.assertTrue(any(task["phone_present"] and task["priority_score"] >= 80 for task in result["tasks"]))

    def test_missing_phone_goes_to_signal_enrichment_or_low_cost_batch(self):
        accounts = sample_accounts("level1_basic.xlsx")
        quality = data_quality(accounts)
        profile = analyze_profile(accounts)
        result = build_execution_plan({"id": "exec_l1", "name": "Level1"}, accounts, quality, profile, plan_id="plan_l1")
        batch_keys = {task["batch_key"] for task in result["tasks"]}
        self.assertIn("missing_signal_enrichment", batch_keys)
        self.assertGreater(result["summary"]["missing_signal_count"], 0)
        self.assertTrue(all(not task["phone_present"] for task in result["tasks"]))


if __name__ == "__main__":
    unittest.main()
