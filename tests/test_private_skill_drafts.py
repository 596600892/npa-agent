from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import backend.app as app
from backend.core.private_skill_drafts import PrivateSkillDraftVault
from backend.storage import db


class PrivateSkillDraftCoreTests(unittest.TestCase):
    def test_generator_uses_only_confirmed_notes_and_redacts_sensitive_text(self):
        tmpdir = Path(tempfile.mkdtemp(prefix="npa-private-skill-core-"))
        try:
            notes = [
                {
                    "id": "note_confirmed",
                    "note_type": "company_preference",
                    "status": "confirmed",
                    "title": "深圳报价偏好",
                    "summary": "报价摘要",
                    "content_text": "报价摘要优先给老板看。手机号 13812345678，地址 广东省深圳市南山区科技园1栋101。",
                },
                {
                    "id": "note_pending",
                    "note_type": "company_preference",
                    "status": "pending_confirmation",
                    "title": "待确认规则",
                    "summary": "这条不应进入草稿",
                    "content_text": "待确认内容不应进入草稿。",
                },
            ]
            draft = PrivateSkillDraftVault(tmpdir).generate("draft_test", "company_pricing_rule", notes)
            self.assertEqual(draft["status"], "draft")
            self.assertEqual(draft["source_note_ids"], ["note_confirmed"])
            self.assertIn("network_access: false", draft["manifest_text"])
            self.assertIn("access_sensitive_data: false", draft["manifest_text"])
            self.assertIn("review_required: true", draft["manifest_text"])
            self.assertNotIn("note_pending", draft["markdown"])
            self.assertNotIn("13812345678", draft["markdown"])
            self.assertNotIn("广东省深圳市南山区科技园1栋101", draft["markdown"])
            self.assertTrue(Path(draft["path"]).exists())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_generator_keeps_court_name_readable(self):
        tmpdir = Path(tempfile.mkdtemp(prefix="npa-private-skill-court-"))
        try:
            notes = [
                {
                    "id": "court_note",
                    "note_type": "court_experience",
                    "status": "confirmed",
                    "title": "深圳市南山区人民法院经验",
                    "summary": "深圳市南山区人民法院批量立案体验较好。",
                    "content_text": "深圳市南山区人民法院批量立案体验较好，联系电话 13812345678。",
                }
            ]
            draft = PrivateSkillDraftVault(tmpdir).generate("draft_court", "court_disposition_experience", notes)
            self.assertIn("深圳市南山区人民法院", draft["markdown"])
            self.assertNotIn("深圳市南山区人民法院***", draft["markdown"])
            self.assertNotIn("13812345678", draft["markdown"])
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class PrivateSkillDraftApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="npa-private-skill-api-")
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

    def request_error(self, method, path, payload=None):
        data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        try:
            return json.loads(ctx.exception.read().decode("utf-8"))
        finally:
            ctx.exception.close()

    def test_00_no_confirmed_memory_returns_actionable_error(self):
        error = self.request_error("POST", "/api/skills/private-drafts/generate", {"draft_type": "company_pricing_rule"})
        self.assertEqual(error["code"], "no_confirmed_memory")
        self.assertIn("confirm_memory", error["next_actions"])

    def test_generate_list_detail_and_review_private_skill_draft(self):
        pending = self.request(
            "POST",
            "/api/knowledge/company-preferences",
            {"title": "待确认偏好", "preference_type": "报价规则", "content": "不应进入草稿。", "confirmed": False},
        )["note"]
        confirmed = self.request(
            "POST",
            "/api/knowledge/company-preferences",
            {
                "title": "已确认报价偏好",
                "preference_type": "报价规则",
                "content": "报告先给老板摘要，手机号 13812345678 不应明文保存。",
                "confirmed": True,
            },
        )["note"]
        self.request(
            "POST",
            f"/api/knowledge/court-notes/{urllib.parse.quote('深圳市南山区人民法院')}/experience",
            {"experience": "深圳市南山区人民法院批量立案体验较好。", "confirmed": True},
        )
        generated = self.request("POST", "/api/skills/private-drafts/generate", {"draft_type": "company_pricing_rule"})
        draft = generated["draft"]
        self.assertEqual(draft["status"], "draft")
        self.assertIn(confirmed["id"], draft["source_note_ids"])
        self.assertNotIn(pending["id"], draft["source_note_ids"])
        self.assertNotIn("13812345678", draft["markdown"])
        self.assertTrue(str(Path(draft["path"])).startswith(str(Path(self.tmpdir) / "private_skills")))

        listed = self.request("GET", "/api/skills/private-drafts")
        self.assertTrue(any(item["id"] == draft["id"] for item in listed["drafts"]))
        detail = self.request("GET", f"/api/skills/private-drafts/{draft['id']}")["draft"]
        self.assertIn("草稿 Manifest", detail["markdown"])

        invalid = self.request_error("POST", f"/api/skills/private-drafts/{draft['id']}/review", {"status": "enabled"})
        self.assertEqual(invalid["code"], "invalid_private_skill_status")
        reviewed = self.request("POST", f"/api/skills/private-drafts/{draft['id']}/review", {"status": "approved", "reviewer": "tester"})["draft"]
        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["review"]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
