from __future__ import annotations

import unittest

from backend.core.contract_risk_analyzer import analyze_contract_risk


class ContractRiskAnalyzerTests(unittest.TestCase):
    def test_extracts_core_contract_risk_signals(self):
        text = """
        个人借款合同 合同编号 A001。借款期限自2022年01月01日至2023年01月01日。
        借款发放日为2022年01月02日，借款人逾期后贷款人已于2023年03月01日催收。
        双方约定本合同争议由深圳市南山区人民法院管辖。借款人确认送达地址，短信送达视为送达。
        本债权可依法债权转让，贷款人将通过短信或书面方式通知债务人。
        附放款凭证、还款记录、还款流水。利率按年化12%计算，逾期收取罚息。
        """
        result = analyze_contract_risk(text, {"filename": "合同.txt", "text_quality": "high"})
        self.assertEqual(result["risks"]["jurisdiction"]["risk"], "low")
        self.assertIn("深圳市南山区人民法院", result["extracted"]["jurisdiction_courts"])
        self.assertEqual(result["risks"]["service_clause"]["risk"], "low")
        self.assertEqual(result["risks"]["assignment_notice"]["risk"], "low")
        self.assertEqual(result["risks"]["limitation_period"]["risk"], "low")
        self.assertIn("放款凭证", result["risks"]["evidence_chain"]["present_items"])
        self.assertTrue(result["risks"]["interest_fee"]["evidence_snippets"])

    def test_conflicting_court_and_arbitration_is_medium_risk(self):
        text = "争议由杭州市西湖区人民法院管辖，同时约定提交上海仲裁委员会仲裁。"
        result = analyze_contract_risk(text, {"text_quality": "medium"})
        self.assertEqual(result["risks"]["jurisdiction"]["risk"], "medium")
        self.assertIn("杭州市西湖区人民法院", result["extracted"]["jurisdiction_courts"])
        self.assertIn("上海仲裁委员会", result["extracted"]["arbitration_bodies"])

    def test_sparse_text_flags_high_or_medium_risks(self):
        result = analyze_contract_risk("借款人同意还款。", {"text_quality": "low"})
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["risks"]["jurisdiction"]["risk"], "high")
        self.assertEqual(result["risks"]["limitation_period"]["risk"], "high")
        self.assertIn("补充争议解决条款截图，确认法院管辖或仲裁机构。", result["next_actions"])

    def test_empty_pdf_warning_drives_ocr_next_action(self):
        result = analyze_contract_risk("", {"text_quality": "empty", "warnings": ["needs_ocr"]})
        self.assertEqual(result["confidence"], "low")
        self.assertIn("上传可复制文字版合同，或先对扫描件做 OCR。", result["next_actions"])


if __name__ == "__main__":
    unittest.main()
