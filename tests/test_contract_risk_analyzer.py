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
        result = analyze_contract_risk("", {"text_quality": "empty", "warnings": ["needs_ocr", "ocr_unavailable"]})
        self.assertEqual(result["confidence"], "low")
        self.assertIn("当前环境未安装本地 OCR 依赖，请安装 pdf2image/pytesseract 或上传可复制文字版文件。", result["next_actions"])

    def test_judgment_document_extracts_adjudication_points(self):
        text = """
        广东省深圳市南山区人民法院 民事判决书。
        本院认为，借款合同合法有效，被告应偿还本金100000元及利息。
        判决如下：被告于本判决生效后十日内向原告支付本金100000元。
        """
        result = analyze_contract_risk(text, {"filename": "民事判决书.txt", "text_quality": "medium"})
        self.assertEqual(result["document_type"], "judgment")
        self.assertTrue(result["judicial_analysis"]["adjudication_points"])
        self.assertIn("100000元", result["extracted"]["legal_amounts"])
        self.assertIn("judicial_document", result["risks"])

    def test_enforcement_document_extracts_terminal_status(self):
        text = """
        执行裁定书。申请执行人某银行，被执行人张某。
        经财产调查，未发现可供执行财产，本院裁定终结本次执行程序。
        申请执行人发现财产线索后可以申请恢复执行。
        """
        result = analyze_contract_risk(text, {"filename": "执行裁定书.txt", "text_quality": "medium"})
        self.assertEqual(result["document_type"], "enforcement")
        self.assertEqual(result["risks"]["judicial_document"]["risk"], "high")
        self.assertTrue(result["extracted"]["execution_statuses"])
        self.assertIn("补充执行裁定、财产查控反馈、终本裁定和恢复执行材料。", result["next_actions"])

    def test_mediation_document_extracts_payment_terms(self):
        text = """
        民事调解书。经本院主持调解，双方达成调解协议：
        被告分期履行，于2026年7月1日前支付50000元，剩余款项于2026年8月1日前结清。
        """
        result = analyze_contract_risk(text, {"filename": "民事调解书.txt", "text_quality": "medium"})
        self.assertEqual(result["document_type"], "mediation")
        self.assertTrue(result["judicial_analysis"]["mediation_terms"])
        self.assertIn("50000元", result["extracted"]["legal_amounts"])


if __name__ == "__main__":
    unittest.main()
