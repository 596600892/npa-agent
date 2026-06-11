from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from backend.core.analysis import run_analysis
from backend.core.excel_parser import parse_excel
from backend.core.field_mapping import preview_mapping
from backend.core.normalization import normalize_rows
from backend.core.privacy import redact_text

ROOT = Path(__file__).resolve().parents[1]


def pipeline(sample: str):
    raw = parse_excel(ROOT / "samples" / sample)
    preview = preview_mapping(raw.headers, raw.rows)
    mapping = {field: item["source_column"] for field, item in preview.items()}
    accounts, errors = normalize_rows(raw.rows, mapping, "test_project")
    result = run_analysis({"id": "test_project", "name": sample, "asset_type": "consumer_loan"}, accounts)
    return raw, preview, mapping, accounts, errors, result


class CorePipelineTests(unittest.TestCase):
    def test_level1_basic_reaches_level1_and_missing_prompts(self):
        raw, preview, mapping, accounts, errors, result = pipeline("level1_basic.xlsx")
        self.assertEqual(mapping["principal"], "本金")
        self.assertEqual(mapping["debtor_name_or_id"], "债务人编号")
        self.assertEqual(len(accounts), 12)
        self.assertEqual(result["quality"]["level"], "Level 1")
        missing_fields = {item["field"] for item in result["quality"]["missing_inputs"]}
        self.assertIn("身份证号", missing_fields)
        self.assertIn("手机号", missing_fields)
        self.assertIn("地址", missing_fields)

    def test_level2_profile_aliases_and_phone_strategy(self):
        raw, preview, mapping, accounts, errors, result = pipeline("level2_profile.xlsx")
        self.assertEqual(mapping["debtor_name_or_id"], "姓名")
        self.assertEqual(mapping["id_card"], "证件号码")
        self.assertEqual(mapping["phone"], "联系电话")
        self.assertEqual(mapping["principal"], "未偿本金")
        self.assertEqual(result["quality"]["level"], "Level 2")
        self.assertGreaterEqual(result["quality"]["coverage"]["phone"], 0.8)
        self.assertIn("电话调解", result["disposition"]["primary_strategy"])

    def test_level3_court_and_report_sections(self):
        raw, preview, mapping, accounts, errors, result = pipeline("level3_court.xlsx")
        self.assertEqual(mapping["contract_no"], "合同编号")
        self.assertEqual(mapping["jurisdiction_court"], "约定管辖法院")
        self.assertEqual(result["quality"]["level"], "Level 3")
        self.assertTrue(result["disposition"]["tiers"]["B"])
        report = result["report"]["markdown"]
        for heading in ["一、结论摘要", "二、资产包基础情况", "三、数据完整度", "五、处置模式建议", "七、合同/文书风险", "八、报价建议", "九、公司历史校准", "十、法院画像", "十一、数据来源说明"]:
            self.assertIn(heading, report)

    def test_legal_risk_section_and_pricing_adjustment(self):
        raw, preview, mapping, accounts, errors, result = pipeline("level1_basic.xlsx")
        legal_risk = {
            "overall_risk": "high",
            "confidence": "medium",
            "text_quality": "medium",
            "filename": "合同条款.txt",
            "warnings": [],
            "extracted": {"jurisdiction_courts": [], "arbitration_bodies": [], "dates": []},
            "risks": {
                "jurisdiction": {"label": "管辖/仲裁", "risk": "high", "conclusion": "未识别明确管辖。", "evidence_snippets": []},
                "service_clause": {"label": "送达条款", "risk": "medium", "conclusion": "未识别送达条款。", "evidence_snippets": []},
                "assignment_notice": {"label": "债权转让通知", "risk": "medium", "conclusion": "未识别债转通知。", "evidence_snippets": []},
                "limitation_period": {"label": "诉讼时效线索", "risk": "high", "conclusion": "未识别时效线索。", "evidence_snippets": []},
                "evidence_chain": {"label": "证据链", "risk": "high", "conclusion": "未识别证据链。", "evidence_snippets": []},
                "interest_fee": {"label": "利息/罚息/费用", "risk": "medium", "conclusion": "未识别息费条款。", "evidence_snippets": []},
            },
            "next_actions": ["补充争议解决条款截图，确认法院管辖或仲裁机构。"],
        }
        result = run_analysis({"id": "test_project", "name": "法律风险样例", "asset_type": "consumer_loan"}, accounts, legal_risk=legal_risk)
        report = result["report"]["markdown"]
        self.assertIn("七、合同/文书风险", report)
        self.assertIn("整体风险：高", report)
        self.assertEqual(result["pricing"]["legal_adjustment"]["adjustment"], -0.01)

    def test_report_redacts_sensitive_values(self):
        raw, preview, mapping, accounts, errors, result = pipeline("level2_profile.xlsx")
        report = result["report"]["markdown"]
        self.assertNotIn("440305199001011234", report)
        self.assertNotIn("13812345678", report)
        self.assertNotIn("广东省深圳市南山区科技园", report)

    def test_redaction_keeps_court_name_but_masks_detailed_address(self):
        text = "深圳市南山区人民法院，广东省深圳市南山区科技园1栋101，手机号13812345678。"
        redacted = redact_text(text)
        self.assertIn("深圳市南山区人民法院", redacted)
        self.assertNotIn("深圳市南山区人民法院***", redacted)
        self.assertNotIn("广东省深圳市南山区科技园1栋101", redacted)
        self.assertIn("138****5678", redacted)

    def test_missing_principal_returns_no_accounts(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "NoPrincipal"
        ws.append(["姓名", "手机号"])
        ws.append(["张三", "13812345678"])
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            wb.save(tmp_path)
            raw = parse_excel(tmp_path)
            preview = preview_mapping(raw.headers, raw.rows)
            mapping = {field: item["source_column"] for field, item in preview.items()}
            accounts, errors = normalize_rows(raw.rows, mapping, "missing_principal")
            self.assertFalse(accounts)
            self.assertTrue(errors)
            self.assertEqual(errors[0]["code"], "missing_principal")
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
