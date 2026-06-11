from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import backend.app as app
from backend.storage import db

ROOT = Path(__file__).resolve().parents[1]


class ApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="npa-agent-test-")
        cls.old_db = db.DB_PATH
        db.DB_PATH = Path(cls.tmpdir) / "app.sqlite"
        db.DATA_DIR = Path(cls.tmpdir)
        db.init_db()
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)
        cls.server.server_close()
        db.DB_PATH = cls.old_db
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post_error(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        try:
            return json.loads(ctx.exception.read().decode("utf-8"))
        finally:
            ctx.exception.close()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_health_identifies_npa_agent_service(self):
        health = self.get("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["app_name"], "NPA Agent")
        self.assertEqual(health["port_hint"], self.port)
        self.assertIn(str(ROOT), health["cwd"])
        self.assertTrue(health["data_dir_present"])

    def test_excel_to_report_api_flow(self):
        project = self.post("/api/projects", {"name": "API 样例", "asset_type": "consumer_loan"})["project"]
        content = base64.b64encode((ROOT / "samples" / "level3_court.xlsx").read_bytes()).decode("ascii")
        uploaded = self.post(f"/api/projects/{project['id']}/files", {"filename": "level3_court.xlsx", "file_type": "asset_package_excel", "content_base64": content})
        self.assertTrue(uploaded["ok"])
        preview = self.post(f"/api/projects/{project['id']}/field-mapping/preview", {"file_id": uploaded["file"]["id"]})
        self.assertEqual(preview["mapping"]["principal"]["source_column"], "本金余额")
        mapping = {field: item["source_column"] for field, item in preview["mapping"].items()}
        confirmed = self.post(f"/api/projects/{project['id']}/field-mapping/confirm", {"file_id": uploaded["file"]["id"], "mapping": mapping, "confidence": preview["mapping"]})
        self.assertEqual(confirmed["normalized_count"], 12)
        contract = "个人借款合同。双方约定由深圳市南山区人民法院管辖。送达地址以合同载明为准。"
        legal_content = base64.b64encode(contract.encode("utf-8")).decode("ascii")
        legal_doc = self.post(f"/api/projects/{project['id']}/legal-documents", {"filename": "合同条款.txt", "content_base64": legal_content})["document"]
        self.post(f"/api/projects/{project['id']}/legal-documents/{legal_doc['id']}/analyze", {})
        analysis = self.post(f"/api/projects/{project['id']}/analysis/run", {"analysis_type": "consumer_loan_initial_screening", "safety_mode": "local_rules_only"})
        self.assertTrue(analysis["ok"])
        report = self.get(f"/api/projects/{project['id']}/reports/latest")["report"]
        self.assertIn("结论摘要", report["markdown"])
        self.assertIn("合同/文书风险", report["markdown"])
        self.assertIn("合同条款.txt", report["markdown"])
        self.assertIn("数据来源说明", report["markdown"])

    def test_settings_do_not_return_plain_api_key(self):
        saved = self.post("/api/settings/model", {"mode": "redacted_cloud", "provider": "auto", "model": "auto", "api_key": "sk-secret"})
        self.assertTrue(saved["model"]["api_key_present"])
        self.assertNotIn("api_key", saved["model"])
        loaded = self.get("/api/settings/model")
        self.assertTrue(loaded["model"]["api_key_present"])
        self.assertNotIn("sk-secret", json.dumps(loaded, ensure_ascii=False))

    def test_legal_document_upload_analyze_and_latest_api_flow(self):
        project = self.post("/api/projects", {"name": "合同风险样例", "asset_type": "consumer_loan"})["project"]
        contract = """
        个人借款合同。借款期限自2022年01月01日至2023年01月01日。
        双方约定由深圳市南山区人民法院管辖。借款人确认送达地址，电子送达视为有效送达。
        债权转让后通过书面方式通知债务人。附放款凭证、还款记录。利率按年化12%计算。
        """
        content = base64.b64encode(contract.encode("utf-8")).decode("ascii")
        uploaded = self.post(f"/api/projects/{project['id']}/legal-documents", {"filename": "合同条款.txt", "content_base64": content})
        self.assertTrue(uploaded["ok"])
        self.assertEqual(uploaded["document"]["text_quality"], "medium")
        self.assertNotIn("extracted_text", uploaded["document"])
        analyzed = self.post(f"/api/projects/{project['id']}/legal-documents/{uploaded['document']['id']}/analyze", {})
        self.assertEqual(analyzed["legal_risk"]["risk"]["risks"]["jurisdiction"]["risk"], "low")
        latest = self.get(f"/api/projects/{project['id']}/legal-risk/latest")
        self.assertEqual(latest["legal_risk"]["document_id"], uploaded["document"]["id"])
        self.assertIn("深圳市南山区人民法院", latest["legal_risk"]["risk"]["extracted"]["jurisdiction_courts"])

    def test_legal_document_unsupported_type_returns_actionable_error(self):
        project = self.post("/api/projects", {"name": "错误合同样例", "asset_type": "consumer_loan"})["project"]
        content = base64.b64encode(b"not a contract").decode("ascii")
        error = self.post_error(f"/api/projects/{project['id']}/legal-documents", {"filename": "scan.exe", "content_base64": content})
        self.assertFalse(error["ok"])
        self.assertEqual(error["code"], "unsupported_legal_document_type")
        self.assertIn("upload_pdf_image_docx_txt_html", error["next_actions"])


if __name__ == "__main__":
    unittest.main()
