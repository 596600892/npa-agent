from __future__ import annotations

import json
import base64
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import backend.app as app
from backend.core.yindeng_parser import parse_yindeng_notice
from backend.storage import db


NOTICE_TEXT = """
中国东方资产管理股份有限公司拟通过银行业信贷资产登记流转中心转让个人不良贷款资产包。
本资产包债务人 128 户，债权本金 1234.56 万元，利息 234.50 万元，本息合计 1469.06 万元。
借款人主要分布于广东、湖南，报名截止时间为 2026年6月18日，竞价时间为 2026年6月20日。
"""


class FakeModelHandler(BaseHTTPRequestHandler):
    captured = ""

    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        FakeModelHandler.captured = body.decode("utf-8")
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "模型连接成功。已生成脱敏建议。",
                    }
                }
            ]
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class NextStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="npa-agent-next-")
        cls.old_db = db.DB_PATH
        cls.old_data = db.DATA_DIR
        db.DB_PATH = Path(cls.tmpdir) / "app.sqlite"
        db.DATA_DIR = Path(cls.tmpdir)
        db.init_db()
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.fake_model = ThreadingHTTPServer(("127.0.0.1", 0), FakeModelHandler)
        cls.fake_model_port = cls.fake_model.server_address[1]
        cls.fake_thread = threading.Thread(target=cls.fake_model.serve_forever, daemon=True)
        cls.fake_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=3)
        cls.server.server_close()
        cls.fake_model.shutdown()
        cls.fake_thread.join(timeout=3)
        cls.fake_model.server_close()
        db.DB_PATH = cls.old_db
        db.DATA_DIR = cls.old_data
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def post(self, path, payload, allow_error=False):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if not allow_error:
                raise
            try:
                return json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_yindeng_parser_extracts_core_fields(self):
        parsed = parse_yindeng_notice(NOTICE_TEXT)
        self.assertEqual(parsed.asset_type, "consumer_loan")
        self.assertEqual(parsed.debtor_count, 128)
        self.assertAlmostEqual(parsed.principal or 0, 12345600)
        self.assertIn("广东", parsed.regions)
        self.assertIn("湖南", parsed.regions)
        self.assertIn("announcement_date", parsed.dates)
        self.assertIn(parsed.confidence, {"medium", "high"})
        self.assertIn("field_sources", parsed.parsed)
        self.assertIn("principal", parsed.parsed["field_sources"])

    def test_document_parser_status_and_inspect_html_notice(self):
        status = self.get("/api/settings/document-parser")
        self.assertTrue(status["ok"])
        self.assertIn(".pdf", status["supported_formats"])
        raw = "<html><body>银登中心个人不良贷款转让公告 本金 100 万元 <a href='a.pdf'>附件</a></body></html>"
        inspected = self.post(
            "/api/documents/inspect",
            {"filename": "公告.html", "content_base64": base64.b64encode(raw.encode("utf-8")).decode("ascii")},
        )
        self.assertTrue(inspected["ok"])
        self.assertEqual(inspected["document"]["file_type"], "html")
        self.assertEqual(inspected["document"]["extraction_method"], "html_text")
        self.assertEqual(inspected["document"]["attachments"][0]["url"], "a.pdf")

    def test_yindeng_parse_api_can_create_project(self):
        parsed = self.post("/api/intelligence/yindeng/parse", {"text": NOTICE_TEXT, "source_type": "manual_text"})
        self.assertTrue(parsed["ok"])
        notice_id = parsed["notice"]["id"]
        created = self.post(f"/api/intelligence/yindeng/notices/{notice_id}/create-project", {})
        self.assertTrue(created["ok"])
        self.assertTrue(created["project"]["name"].startswith("银登机会"))
        notices = self.get("/api/intelligence/yindeng/notices")
        self.assertGreaterEqual(len(notices["notices"]), 1)

    def test_yindeng_keyword_subscription_alert_and_duplicate_detection(self):
        subscription = self.post("/api/intelligence/yindeng/subscriptions", {"keyword": "广东"})
        self.assertTrue(subscription["ok"])
        parsed = self.post("/api/intelligence/yindeng/parse", {"text": NOTICE_TEXT, "source_type": "manual_text"})
        self.assertTrue(parsed["ok"])
        self.assertFalse(parsed["duplicate"])
        self.assertGreaterEqual(len(parsed["alerts"]), 1)
        duplicate = self.post("/api/intelligence/yindeng/parse", {"text": NOTICE_TEXT, "source_type": "manual_text"})
        self.assertTrue(duplicate["ok"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["notice"]["id"], parsed["notice"]["id"])
        alerts = self.get("/api/intelligence/yindeng/alerts")
        self.assertGreaterEqual(len(alerts["alerts"]), 1)
        self.assertIn("广东", [item["keyword"] for item in alerts["alerts"]])

    def test_yindeng_parse_accepts_uploaded_html_notice(self):
        raw = "中国东方资产管理股份有限公司个人不良贷款资产包公告，债务人 8 户，债权本金 320 万元，地区广东。"
        parsed = self.post(
            "/api/intelligence/yindeng/parse",
            {
                "filename": "银登公告.html",
                "content_base64": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
                "source_type": "manual_file",
            },
        )
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["notice"]["debtor_count"], 8)
        self.assertAlmostEqual(parsed["notice"]["principal"] or 0, 3200000)
        self.assertIn("field_sources", parsed["notice"]["parsed"])

    def test_model_gateway_redacts_sensitive_prompt_and_hides_key(self):
        saved = self.post(
            "/api/settings/model",
            {
                "mode": "redacted_cloud",
                "provider": "custom_openai_compatible",
                "base_url": f"http://127.0.0.1:{self.fake_model_port}/v1",
                "model": "fake-chat",
                "api_key": "sk-local-secret",
            },
        )
        self.assertTrue(saved["model"]["api_key_present"])
        generated = self.post(
            "/api/ai/generate",
            {
                "purpose": "phone_script",
                "content": "债务人张三，身份证440305199001011234，手机号13812345678，地址广东省深圳市南山区科技园。",
                "safety_mode": "redacted_cloud",
            },
        )
        self.assertTrue(generated["ok"])
        self.assertIn("脱敏", generated["result"]["text"])
        self.assertIn("prompt_audit", generated["result"])
        self.assertTrue(generated["result"]["prompt_audit"]["redacted"])
        self.assertFalse(generated["result"]["prompt_audit"]["contains_phone_after_redaction"])
        self.assertIn("recommended_model", generated["result"])
        self.assertNotIn("440305199001011234", FakeModelHandler.captured)
        self.assertNotIn("13812345678", FakeModelHandler.captured)
        loaded = self.get("/api/settings/model")
        self.assertNotIn("sk-local-secret", json.dumps(loaded, ensure_ascii=False))

    def test_model_provider_options_include_recommendation_metadata(self):
        providers = self.get("/api/settings/model/providers")
        self.assertTrue(providers["ok"])
        deepseek = next(item for item in providers["providers"] if item["id"] == "deepseek")
        self.assertIn("report_summary", deepseek["recommended_purposes"])

    def test_voice_tts_without_key_returns_actionable_error(self):
        db.set_setting("voice", {"mode": "enhanced", "enhanced_enabled": True, "tts_provider": "openai_compatible_tts"})
        result = self.post("/api/voice/tts", {"text": "朗读当前报告摘要"}, allow_error=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "voice_not_configured")
        self.assertIn("use_builtin_browser_voice", result["next_actions"])

    def test_voice_providers_include_fallback_status(self):
        providers = self.get("/api/settings/voice/providers")
        self.assertTrue(providers["ok"])
        browser = next(item for item in providers["providers"] if item["id"] == "builtin_browser")
        enhanced = next(item for item in providers["providers"] if item["id"] == "openai_compatible_tts")
        self.assertEqual(browser["status"], "available")
        self.assertIn(enhanced["status"], {"needs_key", "configured"})


if __name__ == "__main__":
    unittest.main()
