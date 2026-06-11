from __future__ import annotations

import base64
import json
import shutil
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

import backend.app as app
from backend.storage import db

ROOT = Path(__file__).resolve().parents[1]


class KnowledgeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="npa-knowledge-api-")
        cls.old_db = db.DB_PATH
        cls.old_data = db.DATA_DIR
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
        db.DATA_DIR = cls.old_data
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def request(self, method, path, payload=None):
        data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def post(self, path, payload):
        return self.request("POST", path, payload)

    def get(self, path):
        return self.request("GET", path)

    def create_analyzed_project_with_execution(self):
        project = self.post("/api/projects", {"name": "知识库 API 样例", "asset_type": "consumer_loan"})["project"]
        content = base64.b64encode((ROOT / "samples" / "level3_court.xlsx").read_bytes()).decode("ascii")
        uploaded = self.post(f"/api/projects/{project['id']}/files", {"filename": "level3_court.xlsx", "file_type": "asset_package_excel", "content_base64": content})
        preview = self.post(f"/api/projects/{project['id']}/field-mapping/preview", {"file_id": uploaded["file"]["id"]})
        mapping = {field: item["source_column"] for field, item in preview["mapping"].items()}
        self.post(f"/api/projects/{project['id']}/field-mapping/confirm", {"file_id": uploaded["file"]["id"], "mapping": mapping, "confidence": preview["mapping"]})
        self.post(f"/api/projects/{project['id']}/analysis/run", {"analysis_type": "consumer_loan_initial_screening"})
        generated = self.post(f"/api/projects/{project['id']}/execution/plan", {})
        task = generated["tasks"][0]
        self.post(
            f"/api/projects/{project['id']}/execution/tasks/{task['id']}/events",
            {"event_type": "contact_result", "result": "willing", "note": "愿意协商分期", "next_action": "生成分期协商方案"},
        )
        return project

    def test_project_sync_court_note_search_and_redaction(self):
        project = self.create_analyzed_project_with_execution()
        db.replace_court_profiles(
            [
                {
                    "court_name": "深圳市南山区人民法院",
                    "region": "广东深圳",
                    "sample_count": 3,
                    "principal_total": 1200000,
                    "average_recovery_rate": 0.26,
                    "average_recovery_months": 7.5,
                    "mediation_success_rate": 0.31,
                    "litigation_success_rate": 0.64,
                    "common_failure_reasons": ["执行财产线索不足"],
                    "label": "efficient",
                }
            ]
        )
        synced = self.post(f"/api/projects/{project['id']}/knowledge/sync", {})
        self.assertTrue(synced["ok"])
        self.assertEqual(synced["project_note"]["note_type"], "project")
        self.assertEqual(len(synced["court_notes"]), 1)
        project_note_path = Path(synced["project_note"]["path"])
        self.assertTrue(project_note_path.exists())
        self.assertTrue(str(project_note_path).startswith(str(Path(self.tmpdir) / "knowledge")))

        note = self.get(f"/api/knowledge/notes/{synced['project_note']['id']}")["note"]
        self.assertIn("处置执行计划", note["content_text"])
        self.assertIn("跟进记录摘要", note["content_text"])
        self.assertIn("愿意协商分期", note["content_text"])
        self.assertNotIn("440305199001011234", note["content_text"])
        self.assertNotIn("13812345678", note["content_text"])
        self.assertNotIn("广东省深圳市南山区科技园", note["content_text"])

        searched = self.post("/api/knowledge/search", {"query": "深圳市南山区人民法院"})
        self.assertTrue(any(item["note_type"] == "court" for item in searched["notes"]))

    def test_company_preference_defaults_to_pending_and_redacts_sensitive_text(self):
        payload = {
            "title": "深圳报价偏好",
            "preference_type": "报价规则",
            "content": "手机号 13812345678，身份证 440305199001011234，地址 广东省深圳市南山区科技园1栋101，可作为测试。",
            "confirmed": False,
        }
        saved = self.post("/api/knowledge/company-preferences", payload)
        self.assertEqual(saved["note"]["status"], "pending_confirmation")
        note_id = urllib.parse.quote(saved["note"]["id"])
        note = self.get(f"/api/knowledge/notes/{note_id}")["note"]
        self.assertIn("待确认", note["content_text"])
        self.assertNotIn("13812345678", note["content_text"])
        self.assertNotIn("440305199001011234", note["content_text"])
        self.assertNotIn("广东省深圳市南山区科技园1栋101", note["content_text"])
        confirmed = self.post(f"/api/knowledge/notes/{note_id}/confirm", {"confirmation_note": "负责人确认，联系电话 13812345678 不应明文保存。"})
        self.assertEqual(confirmed["note"]["status"], "confirmed")
        confirmed_note = self.get(f"/api/knowledge/notes/{note_id}")["note"]
        self.assertIn("确认记录", confirmed_note["content_text"])
        self.assertIn("已确认", confirmed_note["content_text"])
        self.assertNotIn("13812345678", confirmed_note["content_text"])

    def test_court_experience_note_can_be_pending_or_confirmed_and_searchable(self):
        court_name = "深圳市南山区人民法院"
        payload = {
            "experience": "批量立案沟通顺畅，但执行线索要提前准备。手机号 13812345678，地址 广东省深圳市南山区科技园1栋101。",
            "confirmed": True,
            "source": "人工复盘",
        }
        saved = self.post(f"/api/knowledge/court-notes/{urllib.parse.quote(court_name)}/experience", payload)
        self.assertEqual(saved["note"]["status"], "confirmed")
        note = self.get(f"/api/knowledge/notes/{urllib.parse.quote(saved['note']['id'])}")["note"]
        self.assertIn("批量立案沟通顺畅", note["content_text"])
        self.assertIn("已确认", note["content_text"])
        self.assertNotIn("13812345678", note["content_text"])
        self.assertNotIn("广东省深圳市南山区科技园1栋101", note["content_text"])
        searched = self.post("/api/knowledge/search", {"query": "执行线索"})
        self.assertTrue(any(item["note_type"] == "court_experience" for item in searched["notes"]))


if __name__ == "__main__":
    unittest.main()
