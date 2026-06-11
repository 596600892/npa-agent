from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.analysis import run_analysis
from backend.core.company_history import build_company_history_analytics, build_court_profiles, normalize_history_rows
from backend.core.company_history_mapping import preview_history_mapping
from backend.core.contract_risk_analyzer import analyze_contract_risk
from backend.core.document_ingestion import ingest_bytes, parser_status
from backend.core.document_text_extractor import DocumentExtractionError, extract_document_text
from backend.core.data_quality import data_quality
from backend.core.execution_plan import build_execution_plan
from backend.core.execution_export import build_execution_export
from backend.core.excel_parser import parse_excel
from backend.core.field_mapping import preview_mapping, unmapped_columns
from backend.core.knowledge_base import KnowledgeVault
from backend.core.normalization import normalize_rows
from backend.core.private_skill_drafts import PrivateSkillDraftVault, REVIEW_STATUSES, VALID_DRAFT_TYPES
from backend.core.privacy import mask_address, mask_id_card, mask_name, mask_phone
from backend.core.profile_analyzer import analyze_profile
from backend.core.yindeng_fetcher import YindengFetchError, fetch_public_url
from backend.core.yindeng_parser import parse_yindeng_notice
from backend.model_gateway import ModelGatewayError, generate_text, provider_options, test_model_config
from backend.storage import db
from backend.storage.files import save_company_history_upload, save_legal_document_upload, save_report, save_upload
from backend.voice_gateway import VoiceGatewayError, synthesize_speech, voice_provider_options

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
TEMPLATE_PATH = ROOT / "templates" / "个贷资产包标准模板.xlsx"
COMPANY_HISTORY_TEMPLATE_PATH = ROOT / "templates" / "公司历史处置数据模板.xlsx"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def make_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{stamp}"


def json_safe(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


def mapping_to_simple(mapping: dict[str, dict]) -> dict[str, str | None]:
    return {key: value.get("source_column") for key, value in mapping.items()}


def preview_rows(raw_rows: list[dict], mapping: dict[str, dict], limit: int = 5) -> list[dict]:
    simple = mapping_to_simple(mapping)
    rows = []
    for row in raw_rows[:limit]:
        item = {}
        for field, column in simple.items():
            if not column:
                continue
            value = row.get(column)
            if field == "id_card":
                value = mask_id_card(str(value or ""))
            elif field == "phone":
                value = mask_phone(str(value or ""))
            elif field == "address":
                value = mask_address(str(value or ""))
            elif field == "debtor_name_or_id":
                value = mask_name(str(value or ""))
            item[field] = value
        rows.append(item)
    return rows


def preview_history_rows(raw_rows: list[dict], mapping: dict[str, dict], limit: int = 5) -> list[dict]:
    simple = mapping_to_simple(mapping)
    rows = []
    for row in raw_rows[:limit]:
        item = {}
        for field, column in simple.items():
            if column:
                item[field] = row.get(column)
        rows.append(item)
    return rows


def yindeng_notice_record(parsed, raw_text: str, source_id: str | None, source_url: str | None) -> dict:
    return {
        "id": make_id("ynd"),
        "source_id": source_id,
        "source_url": source_url,
        "title": parsed.title,
        "transferor": parsed.transferor,
        "asset_type": parsed.asset_type,
        "debtor_count": parsed.debtor_count,
        "principal": parsed.principal,
        "interest": parsed.interest,
        "total_claim": parsed.total_claim,
        "regions": parsed.regions,
        "dates": parsed.dates,
        "attachments": parsed.attachments,
        "raw_text": raw_text,
        "parsed": parsed.parsed,
        "confidence": parsed.confidence,
        "created_at": now_iso(),
    }


def save_yindeng_notice_with_alerts(preliminary, raw_text: str, source_id: str, source_url: str | None, raw_sha256: str) -> tuple[dict, bool, list[dict]]:
    existing = db.find_yindeng_notice_by_raw_sha(raw_sha256)
    if existing:
        return existing, True, []
    notice = yindeng_notice_record(preliminary, raw_text, source_id, source_url)
    db.insert_yindeng_notice(notice)
    alerts = create_yindeng_alerts(notice)
    return notice, False, alerts


def enrich_yindeng_with_public_attachments(preliminary, fetched) -> tuple[object, str, str, list[dict]]:
    combined_text = fetched.raw_text
    sha_parts = [fetched.raw_sha256]
    enriched = []
    used_any = False
    for attachment in preliminary.attachments[:3]:
        url = attachment.get("url") or ""
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".html", ".htm", ".docx"}:
            enriched.append({**attachment, "parse_status": "skipped_unsupported_attachment"})
            continue
        try:
            attached = fetch_public_url(url)
        except YindengFetchError as exc:
            enriched.append({**attachment, "parse_status": exc.code, "message": exc.message})
            continue
        sha_parts.append(attached.raw_sha256)
        if attached.raw_text.strip():
            used_any = True
            combined_text += f"\n\n[银登附件解析: {attachment.get('label') or url}]\n{attached.raw_text}"
        enriched.append(
            {
                **attachment,
                "parse_status": "parsed" if attached.raw_text.strip() else "empty",
                "sha256": attached.raw_sha256,
                "content_type": attached.content_type,
                "extraction": attached.ingestion or {"extraction_method": "text", "text_quality": "unknown"},
            }
        )
    if not enriched:
        return preliminary, combined_text, fetched.raw_sha256, []
    parsed = parse_yindeng_notice(combined_text, fetched.url, fetched.content_type, fetched.ingestion)
    parsed.attachments = enriched
    parsed.parsed["attachments"] = enriched
    parsed.parsed["attachment_extractions"] = enriched
    parsed.parsed["source_mix"] = "网页正文+公开附件" if used_any else "网页正文"
    raw_sha = hashlib.sha256("|".join(sha_parts).encode("utf-8")).hexdigest()
    return parsed, combined_text, raw_sha, enriched


def create_yindeng_alerts(notice: dict) -> list[dict]:
    text = " ".join(
        [
            notice.get("title") or "",
            notice.get("transferor") or "",
            notice.get("asset_type") or "",
            " ".join(notice.get("regions") or []),
            notice.get("raw_text") or "",
        ]
    )
    alerts: list[dict] = []
    for subscription in db.list_yindeng_subscriptions(enabled_only=True):
        keyword = subscription.get("keyword", "").strip()
        if keyword and keyword in text:
            alert = {
                "id": make_id("yndalert"),
                "subscription_id": subscription["id"],
                "notice_id": notice["id"],
                "keyword": keyword,
                "created_at": now_iso(),
            }
            db.insert_yindeng_alert(alert)
            alerts.append(alert)
    return alerts


def default_model_setting() -> dict:
    return {
        "mode": "redacted_cloud",
        "provider": "deepseek",
        "model": "auto",
        "base_url": "",
        "api_key_present": False,
        "allow_original_sensitive_data": False,
    }


def default_voice_setting() -> dict:
    return {
        "mode": "builtin_fallback",
        "enhanced_enabled": False,
        "asr_provider": "builtin_browser",
        "tts_provider": "builtin_browser",
        "tts_base_url": "",
        "tts_model": "tts-1",
        "tts_voice": "nova",
        "sensitive_data_readout": "masked_only",
        "tts_api_key_present": False,
    }


def validate_confirmation(confirmation_id: str | None, action_type: str, project_id: str | None = None) -> dict | None:
    if not confirmation_id:
        return None
    confirmation = db.get_security_confirmation(confirmation_id)
    if not confirmation or confirmation.get("action_type") != action_type:
        return None
    if project_id and confirmation.get("project_id") and confirmation.get("project_id") != project_id:
        return None
    return confirmation


def knowledge_vault() -> KnowledgeVault:
    return KnowledgeVault(db.DATA_DIR / "knowledge")


def private_skill_vault() -> PrivateSkillDraftVault:
    return PrivateSkillDraftVault(db.DATA_DIR / "private_skills")


class Handler(BaseHTTPRequestHandler):
    server_version = "NPAAgent/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[NPA] " + fmt % args + "\n")

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        data = self.rfile.read(length)
        return json.loads(data.decode("utf-8"))

    def _not_found(self):
        self._send_json(404, {"ok": False, "code": "not_found", "message": "接口不存在"})

    def _error(self, status: int, code: str, message: str, next_actions: list[str] | None = None):
        self._send_json(status, {"ok": False, "code": code, "message": message, "next_actions": next_actions or []})

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                port = self.server.server_address[1]
                address = os.environ.get("PUBLIC_URL") or f"http://127.0.0.1:{port}"
                return self._send_json(
                    200,
                    {
                        "ok": True,
                        "app_name": "NPA Agent",
                        "version": "0.1-local-alpha",
                        "cwd": str(ROOT),
                        "port_hint": port,
                        "address": address,
                        "data_dir_present": db.DATA_DIR.exists(),
                    },
                )
            if parsed.path == "/api/projects":
                return self._send_json(200, {"ok": True, "projects": db.list_projects()})
            match = re.fullmatch(r"/api/projects/([^/]+)", parsed.path)
            if match:
                project = db.get_project(match.group(1))
                if not project:
                    return self._error(404, "project_not_found", "项目不存在")
                return self._send_json(200, {"ok": True, "project": project})
            match = re.fullmatch(r"/api/projects/([^/]+)/legal-documents", parsed.path)
            if match:
                project_id = match.group(1)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                return self._send_json(200, {"ok": True, "documents": db.list_legal_documents(project_id)})
            match = re.fullmatch(r"/api/projects/([^/]+)/legal-risk/latest", parsed.path)
            if match:
                project_id = match.group(1)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                risk = db.latest_legal_risk(project_id)
                if not risk:
                    return self._error(404, "legal_risk_not_found", "尚未分析合同/文书风险。", ["upload_legal_document", "analyze_legal_document"])
                return self._send_json(200, {"ok": True, "legal_risk": risk})
            match = re.fullmatch(r"/api/projects/([^/]+)/reports/latest", parsed.path)
            if match:
                report = db.latest_report(match.group(1))
                if not report:
                    return self._error(404, "report_not_found", "报告不存在")
                return self._send_json(200, {"ok": True, "report": report})
            match = re.fullmatch(r"/api/projects/([^/]+)/execution/batches", parsed.path)
            if match:
                project_id = match.group(1)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                plan = db.latest_execution_plan(project_id)
                return self._send_json(200, {"ok": True, "plan": plan, "batches": db.list_execution_batches(project_id)})
            match = re.fullmatch(r"/api/projects/([^/]+)/execution/tasks", parsed.path)
            if match:
                project_id = match.group(1)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                query = parse_qs(parsed.query)
                filters = {key: values[0] for key, values in query.items() if values and key in {"batch_id", "status", "tier"}}
                plan = db.latest_execution_plan(project_id)
                tasks = db.list_execution_tasks(project_id, filters=filters)
                return self._send_json(200, {"ok": True, "plan": plan, "tasks": tasks})
            match = re.fullmatch(r"/api/projects/([^/]+)/execution/export\.xlsx", parsed.path)
            if match:
                project_id = match.group(1)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                tasks = db.list_execution_tasks(project_id)
                if not tasks:
                    return self._error(404, "execution_plan_not_found", "请先生成处置执行计划。", ["generate_execution_plan"])
                query = parse_qs(parsed.query)
                export_mode = (query.get("mode") or ["redacted"])[0]
                confirmation_id = (query.get("confirmation_id") or [None])[0]
                if export_mode not in {"redacted", "original_sensitive"}:
                    return self._error(400, "invalid_export_mode", "导出模式只支持 redacted 或 original_sensitive。", ["select_redacted_export"])
                if export_mode == "original_sensitive" and not validate_confirmation(confirmation_id, "original_sensitive_export", project_id):
                    db.audit(project_id, "execution_export_denied", {"export_mode": export_mode, "sensitive_data_access": True, "confirmation_id": confirmation_id})
                    return self._error(403, "sensitive_export_not_confirmed", "原文敏感导出需要先完成二次确认。", ["create_sensitive_export_confirmation", "use_redacted_export"])
                body = build_execution_export(tasks, mode=export_mode)
                db.audit(project_id, "execution_exported", {"export_mode": export_mode, "sensitive_data_access": export_mode == "original_sensitive", "confirmation_id": confirmation_id})
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''execution-plan.xlsx")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/settings/model":
                return self._send_json(200, {"ok": True, "model": db.get_setting("model", default_model_setting())})
            if parsed.path == "/api/settings/model/providers":
                return self._send_json(200, {"ok": True, "providers": provider_options()})
            if parsed.path == "/api/settings/voice":
                return self._send_json(200, {"ok": True, "voice": db.get_setting("voice", default_voice_setting())})
            if parsed.path == "/api/settings/voice/providers":
                return self._send_json(200, {"ok": True, "providers": voice_provider_options()})
            if parsed.path == "/api/settings/document-parser":
                return self._send_json(200, parser_status())
            if parsed.path == "/api/audit/logs":
                query = parse_qs(parsed.query)
                project_id = (query.get("project_id") or [None])[0]
                limit = int((query.get("limit") or [100])[0])
                return self._send_json(200, {"ok": True, "logs": db.list_audit_logs(project_id=project_id, limit=limit)})
            if parsed.path == "/api/audit/summary":
                return self._send_json(200, {"ok": True, "summary": db.audit_summary()})
            match = re.fullmatch(r"/api/security/confirmations/([^/]+)", parsed.path)
            if match:
                confirmation = db.get_security_confirmation(unquote(match.group(1)))
                if not confirmation:
                    return self._error(404, "confirmation_not_found", "安全确认记录不存在")
                return self._send_json(200, {"ok": True, "confirmation": confirmation})
            if parsed.path == "/api/intelligence/yindeng/notices":
                return self._send_json(200, {"ok": True, "notices": db.list_yindeng_notices()})
            if parsed.path == "/api/intelligence/yindeng/subscriptions":
                return self._send_json(200, {"ok": True, "subscriptions": db.list_yindeng_subscriptions()})
            if parsed.path == "/api/intelligence/yindeng/alerts":
                return self._send_json(200, {"ok": True, "alerts": db.list_yindeng_alerts()})
            if parsed.path == "/api/company-history/records":
                return self._send_json(200, {"ok": True, "records": db.list_company_history_records()})
            if parsed.path == "/api/company-history/analytics":
                records = db.list_company_history_records()
                return self._send_json(200, {"ok": True, "analytics": build_company_history_analytics(records), "next_actions": ["upload_company_history_excel"] if not records else ["review_history_breakdown", "rerun_project_analysis"]})
            if parsed.path == "/api/courts/profiles":
                records = db.list_company_history_records()
                profiles = build_court_profiles(records) if records else db.list_court_profiles()
                return self._send_json(200, {"ok": True, "profiles": profiles})
            match = re.fullmatch(r"/api/courts/profiles/(.+)", parsed.path)
            if match:
                court_name = unquote(match.group(1))
                records = db.list_company_history_records()
                profiles = build_court_profiles(records) if records else db.list_court_profiles()
                profile = next((item for item in profiles if item.get("court_name") == court_name), None) or db.get_court_profile(court_name)
                if not profile:
                    return self._error(404, "court_profile_not_found", "法院画像不存在")
                return self._send_json(200, {"ok": True, "profile": profile})
            match = re.fullmatch(r"/api/projects/([^/]+)/calibration/latest", parsed.path)
            if match:
                project_id = match.group(1)
                calibration = db.latest_pricing_calibration(project_id)
                if not calibration:
                    return self._error(404, "calibration_not_found", "这个项目还没有历史校准结果，请先生成分析报告。", ["run_analysis"])
                return self._send_json(200, {"ok": True, "calibration": calibration})
            if parsed.path == "/api/knowledge/notes":
                query = parse_qs(parsed.query)
                note_type = (query.get("note_type") or [None])[0]
                return self._send_json(200, {"ok": True, "notes": db.list_knowledge_notes(note_type=note_type)})
            match = re.fullmatch(r"/api/knowledge/notes/([^/]+)", parsed.path)
            if match:
                note = db.get_knowledge_note(unquote(match.group(1)))
                if not note:
                    return self._error(404, "knowledge_note_not_found", "知识库笔记不存在")
                return self._send_json(200, {"ok": True, "note": note})
            if parsed.path == "/api/skills/private-drafts":
                query = parse_qs(parsed.query)
                status = (query.get("status") or [None])[0]
                draft_type = (query.get("draft_type") or [None])[0]
                return self._send_json(200, {"ok": True, "drafts": db.list_private_skill_drafts(status=status, draft_type=draft_type), "types": list(VALID_DRAFT_TYPES)})
            match = re.fullmatch(r"/api/skills/private-drafts/([^/]+)", parsed.path)
            if match:
                draft = db.get_private_skill_draft(unquote(match.group(1)))
                if not draft:
                    return self._error(404, "private_skill_draft_not_found", "私有 skill 草稿不存在")
                return self._send_json(200, {"ok": True, "draft": draft})
            if parsed.path == "/templates/consumer-loan-template.xlsx":
                return self._send_file(TEMPLATE_PATH)
            if parsed.path == "/templates/company-history-template.xlsx":
                return self._send_file(COMPANY_HISTORY_TEMPLATE_PATH)
            return self._serve_static(parsed.path)
        except Exception as exc:
            return self._error(500, "server_error", str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/projects":
                payload = self._read_json()
                project = {
                    "id": make_id("prj"),
                    "name": payload.get("name") or "未命名资产包",
                    "asset_type": payload.get("asset_type") or "consumer_loan",
                    "status": "draft",
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "latest_report_id": None,
                }
                db.insert_project(project)
                db.audit(project["id"], "project_created", {"name": project["name"]})
                return self._send_json(200, {"ok": True, "project": project})

            match = re.fullmatch(r"/api/projects/([^/]+)/files", parsed.path)
            if match:
                project_id = match.group(1)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                payload = self._read_json()
                file_id = make_id("file")
                saved = save_upload(project_id, file_id, payload["filename"], payload["content_base64"])
                record = {
                    "id": file_id,
                    "project_id": project_id,
                    "filename": payload["filename"],
                    "file_type": payload.get("file_type", "asset_package_excel"),
                    "stored_path": saved["stored_path"],
                    "sha256": saved["sha256"],
                    "created_at": now_iso(),
                }
                db.insert_file(record)
                db.audit(project_id, "file_uploaded", {"file_id": file_id, "filename": record["filename"], "sha256": record["sha256"]})
                return self._send_json(200, {"ok": True, "file": record})

            match = re.fullmatch(r"/api/projects/([^/]+)/legal-documents", parsed.path)
            if match:
                project_id = match.group(1)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                payload = self._read_json()
                document_id = make_id("ldoc")
                saved = save_legal_document_upload(project_id, document_id, payload["filename"], payload["content_base64"])
                extracted = extract_document_text(saved["stored_path"], payload["filename"])
                record = {
                    "id": document_id,
                    "project_id": project_id,
                    "filename": payload["filename"],
                    "file_type": extracted.file_type,
                    "stored_path": saved["stored_path"],
                    "sha256": saved["sha256"],
                    "extracted_text": extracted.text,
                    "parser_version": extracted.parser_version,
                    "text_quality": extracted.text_quality,
                    "warnings": extracted.warnings,
                    "page_count": extracted.page_count,
                    "is_scanned_pdf": extracted.is_scanned_pdf,
                    "extraction_method": extracted.extraction_method,
                    "pages_used": extracted.pages_used,
                    "ocr_status": extracted.ocr_status,
                    "ocr_confidence": extracted.ocr_confidence,
                    "attachments": extracted.attachments,
                    "field_sources": extracted.field_sources,
                    "created_at": now_iso(),
                }
                db.insert_legal_document(record)
                db.audit(project_id, "legal_document_uploaded", {"document_id": document_id, "filename": record["filename"], "sha256": record["sha256"], "text_quality": record["text_quality"], "warnings": record["warnings"], "sensitive_data_access": True, "extraction_method": record.get("extraction_method"), "ocr_status": record.get("ocr_status"), "pages_used": record.get("pages_used", [])})
                response_record = {key: value for key, value in record.items() if key != "extracted_text"}
                return self._send_json(200, {"ok": True, "document": response_record, "next_actions": ["analyze_legal_document", "upload_text_version_if_needs_ocr"]})

            match = re.fullmatch(r"/api/projects/([^/]+)/legal-documents/([^/]+)/analyze", parsed.path)
            if match:
                project_id, document_id = match.group(1), match.group(2)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                document = db.get_legal_document(document_id, include_text=True)
                if not document or document["project_id"] != project_id:
                    return self._error(404, "legal_document_not_found", "合同/文书不存在")
                risk = analyze_contract_risk(
                    document.get("extracted_text", ""),
                    {
                        "document_id": document_id,
                        "filename": document["filename"],
                        "text_quality": document["text_quality"],
                        "parser_version": document["parser_version"],
                        "warnings": document["warnings"],
                        "is_scanned_pdf": document.get("is_scanned_pdf"),
                        "extraction_method": document.get("extraction_method"),
                        "pages_used": document.get("pages_used", []),
                        "ocr_status": document.get("ocr_status"),
                        "ocr_confidence": document.get("ocr_confidence"),
                        "attachments": document.get("attachments", []),
                        "field_sources": document.get("field_sources", {}),
                    },
                )
                analysis_record = {"id": make_id("lrisk"), "project_id": project_id, "document_id": document_id, "risk": risk, "created_at": now_iso()}
                db.insert_legal_risk_analysis(analysis_record)
                db.audit(project_id, "legal_document_analyzed", {"document_id": document_id, "overall_risk": risk["overall_risk"], "confidence": risk["confidence"], "sensitive_data_access": True, "extraction_method": risk.get("extraction_method"), "ocr_status": risk.get("ocr_status"), "pages_used": risk.get("pages_used", [])})
                return self._send_json(200, {"ok": True, "legal_risk": analysis_record, "next_actions": ["rerun_project_analysis", "review_legal_risk"]})

            match = re.fullmatch(r"/api/projects/([^/]+)/field-mapping/preview", parsed.path)
            if match:
                project_id = match.group(1)
                payload = self._read_json()
                file_record = db.get_file(payload.get("file_id")) if payload.get("file_id") else db.latest_file(project_id)
                if not file_record:
                    return self._error(404, "file_not_found", "请先上传资产包 Excel", ["upload_excel"])
                raw = parse_excel(file_record["stored_path"], payload.get("sheet_name"))
                mapping = preview_mapping(raw.headers, raw.rows)
                return self._send_json(
                    200,
                    {
                        "ok": True,
                        "sheet_name": raw.sheet_name,
                        "headers": raw.headers,
                        "mapping": mapping,
                        "unmapped_columns": unmapped_columns(raw.headers, mapping),
                        "preview_rows": preview_rows(raw.rows, mapping),
                        "next_actions": ["confirm_field_mapping"],
                    },
                )

            match = re.fullmatch(r"/api/projects/([^/]+)/field-mapping/confirm", parsed.path)
            if match:
                project_id = match.group(1)
                payload = self._read_json()
                file_record = db.get_file(payload.get("file_id")) if payload.get("file_id") else db.latest_file(project_id)
                if not file_record:
                    return self._error(404, "file_not_found", "请先上传资产包 Excel")
                raw = parse_excel(file_record["stored_path"], payload.get("sheet_name"))
                mapping = payload.get("mapping") or {}
                accounts, errors = normalize_rows(raw.rows, mapping, project_id)
                if not accounts:
                    return self._error(400, "missing_required_field", "缺少本金字段，无法完成资产包金额分析。", ["confirm_field_mapping", "download_template"])
                db.save_mapping({"id": make_id("map"), "project_id": project_id, "file_id": file_record["id"], "mapping": mapping, "confidence": payload.get("confidence", {}), "created_at": now_iso()})
                db.replace_accounts(project_id, accounts)
                db.audit(project_id, "field_mapping_confirmed", {"file_id": file_record["id"], "normalized_count": len(accounts), "error_count": len(errors)})
                return self._send_json(200, {"ok": True, "normalized_count": len(accounts), "errors": errors, "next_actions": ["run_analysis"]})

            match = re.fullmatch(r"/api/projects/([^/]+)/analysis/run", parsed.path)
            if match:
                project_id = match.group(1)
                project = db.get_project(project_id)
                if not project:
                    return self._error(404, "project_not_found", "项目不存在")
                accounts = db.get_accounts(project_id)
                if not accounts:
                    return self._error(400, "no_normalized_accounts", "请先确认字段映射并生成标准化数据。", ["confirm_field_mapping"])
                history_records = db.list_company_history_records()
                court_profiles = db.list_court_profiles()
                latest_legal = db.latest_legal_risk(project_id)
                legal_risk = latest_legal["risk"] if latest_legal else None
                latest_execution = db.latest_execution_plan(project_id)
                execution_summary = latest_execution["summary"] if latest_execution else None
                result = run_analysis(project, accounts, history_records, court_profiles, legal_risk, execution_summary)
                report_id = make_id("rpt")
                save_report(project_id, report_id, result["report"]["markdown"])
                db.insert_pricing_calibration({"id": make_id("cal"), "project_id": project_id, "calibration": result["calibration"], "created_at": now_iso()})
                report_record = {
                    "id": report_id,
                    "project_id": project_id,
                    "version": "0.1",
                    "markdown": result["report"]["markdown"],
                    "data": {
                        "summary": result["report"]["summary"],
                        "metrics": result["profile"]["basic"],
                        "quality": result["quality"],
                        "disposition": result["disposition"],
                        "pricing": result["pricing"],
                        "calibration": result["calibration"],
                        "legal_risk": result["legal_risk"],
                        "execution_summary": result["execution_summary"],
                        "source_attributions": result["attributions"],
                    },
                    "created_at": now_iso(),
                }
                db.insert_report(report_record)
                db.audit(project_id, "analysis_completed", {"report_id": report_id, "account_count": len(accounts)})
                return self._send_json(200, {"ok": True, "job": {"id": make_id("job"), "status": "completed"}, "report_id": report_id, "report": report_record})

            match = re.fullmatch(r"/api/projects/([^/]+)/execution/plan", parsed.path)
            if match:
                project_id = match.group(1)
                project = db.get_project(project_id)
                if not project:
                    return self._error(404, "project_not_found", "项目不存在")
                accounts = db.get_accounts(project_id)
                if not accounts:
                    return self._error(400, "no_normalized_accounts", "请先上传资产包 Excel 并确认字段映射。", ["confirm_field_mapping"])
                quality = data_quality(accounts)
                profile = analyze_profile(accounts)
                latest_legal = db.latest_legal_risk(project_id)
                legal_risk = latest_legal["risk"] if latest_legal else None
                plan_id = make_id("exec")
                bundle = build_execution_plan(project, accounts, quality, profile, legal_risk, plan_id)
                db.save_execution_plan(bundle)
                db.audit(project_id, "execution_plan_created", {"plan_id": plan_id, "task_count": len(bundle["tasks"]), "summary": bundle["summary"]})
                return self._send_json(200, {"ok": True, "plan": bundle["plan"], "batches": bundle["batches"], "tasks": bundle["tasks"], "summary": bundle["summary"]})

            match = re.fullmatch(r"/api/projects/([^/]+)/execution/tasks/([^/]+)", parsed.path)
            if match:
                project_id, task_id = match.group(1), match.group(2)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                payload = self._read_json()
                task = db.update_execution_task(project_id, task_id, payload)
                if not task:
                    return self._error(404, "execution_task_not_found", "执行任务不存在")
                db.audit(project_id, "execution_task_updated", {"task_id": task_id, "status": task.get("status"), "latest_result": task.get("latest_result")})
                return self._send_json(200, {"ok": True, "task": task})

            match = re.fullmatch(r"/api/projects/([^/]+)/execution/tasks/([^/]+)/events", parsed.path)
            if match:
                project_id, task_id = match.group(1), match.group(2)
                task = db.get_execution_task(project_id, task_id)
                if not task:
                    return self._error(404, "execution_task_not_found", "执行任务不存在")
                payload = self._read_json()
                event = {
                    "id": make_id("evt"),
                    "project_id": project_id,
                    "task_id": task_id,
                    "event_type": payload.get("event_type") or "contact_result",
                    "result": payload.get("result"),
                    "note": payload.get("note"),
                    "next_action": payload.get("next_action") or task.get("next_action"),
                    "created_at": now_iso(),
                }
                db.insert_execution_event(event)
                updates = {
                    "latest_result": event.get("result"),
                    "latest_note": event.get("note"),
                    "next_action": event.get("next_action") or task.get("next_action"),
                }
                if event.get("result"):
                    updates["status"] = event["result"]
                updated = db.update_execution_task(project_id, task_id, updates)
                db.audit(project_id, "execution_event_created", {"task_id": task_id, "event_type": event["event_type"], "result": event.get("result")})
                return self._send_json(200, {"ok": True, "event": event, "task": updated})

            match = re.fullmatch(r"/api/projects/([^/]+)/knowledge/sync", parsed.path)
            if match:
                project_id = match.group(1)
                project = db.get_project(project_id)
                if not project:
                    return self._error(404, "project_not_found", "项目不存在")
                vault = knowledge_vault()
                latest_legal = db.latest_legal_risk(project_id)
                plan = db.latest_execution_plan(project_id)
                project_note = vault.write_project_note(
                    project,
                    db.latest_report(project_id),
                    latest_legal["risk"] if latest_legal else None,
                    plan,
                    db.list_execution_tasks(project_id),
                    db.list_execution_events(project_id),
                )
                db.upsert_knowledge_note(project_note)
                court_notes = []
                for profile in db.list_court_profiles():
                    note = vault.write_court_note(profile)
                    db.upsert_knowledge_note(note)
                    court_notes.append(note)
                notes = [project_note, *court_notes]
                db.audit(project_id, "knowledge_synced", {"note_ids": [note["id"] for note in notes], "court_note_count": len(court_notes), "memory_write": True})
                return self._send_json(200, {"ok": True, "project_note": project_note, "court_notes": court_notes, "notes": notes})

            if parsed.path == "/api/knowledge/search":
                payload = self._read_json()
                query = (payload.get("query") or "").strip()
                if not query:
                    return self._error(400, "missing_search_query", "请输入要搜索的项目、法院、标签或关键词。", ["enter_keyword"])
                return self._send_json(200, {"ok": True, "notes": db.search_knowledge_notes(query)})

            match = re.fullmatch(r"/api/knowledge/notes/([^/]+)/confirm", parsed.path)
            if match:
                note_id = unquote(match.group(1))
                note = db.get_knowledge_note(note_id)
                if not note:
                    return self._error(404, "knowledge_note_not_found", "知识库笔记不存在")
                payload = self._read_json()
                updated = knowledge_vault().confirm_note(note, payload.get("confirmation_note"))
                db.upsert_knowledge_note(updated)
                db.audit(payload.get("project_id"), "knowledge_note_confirmed", {"note_id": note_id, "note_type": updated["note_type"], "memory_write": True})
                return self._send_json(200, {"ok": True, "note": updated})

            if parsed.path == "/api/knowledge/company-preferences":
                payload = self._read_json()
                if not (payload.get("title") or "").strip() or not (payload.get("content") or "").strip():
                    return self._error(400, "missing_company_preference", "请填写偏好标题和内容。", ["fill_preference_title", "fill_preference_content"])
                note = knowledge_vault().write_company_preference_note(payload)
                db.upsert_knowledge_note(note)
                db.audit(None, "company_preference_note_saved", {"note_id": note["id"], "status": note["status"], "preference_type": payload.get("preference_type"), "memory_write": True})
                return self._send_json(200, {"ok": True, "note": note})

            match = re.fullmatch(r"/api/knowledge/court-notes/(.+)/experience", parsed.path)
            if match:
                court_name = unquote(match.group(1))
                payload = self._read_json()
                experience = (payload.get("experience") or payload.get("content") or "").strip()
                if not experience:
                    return self._error(400, "missing_court_experience", "请填写法院经验或复盘内容。", ["fill_court_experience"])
                profile = db.get_court_profile(court_name)
                note = knowledge_vault().write_court_experience_note(court_name, payload, profile)
                db.upsert_knowledge_note(note)
                db.audit(None, "court_experience_note_saved", {"note_id": note["id"], "court_name": court_name, "status": note["status"], "memory_write": True})
                return self._send_json(200, {"ok": True, "note": note})

            match = re.fullmatch(r"/api/knowledge/court-notes/(.+)", parsed.path)
            if match:
                court_name = unquote(match.group(1))
                profile = db.get_court_profile(court_name)
                if not profile:
                    payload = self._read_json()
                    if not payload:
                        return self._error(404, "court_profile_not_found", "请先上传历史处置数据生成法院画像，或提交人工法院经验。", ["upload_company_history", "submit_manual_court_note"])
                    profile = {
                        "court_name": court_name,
                        "region": payload.get("region"),
                        "label": payload.get("label", "normal"),
                        "sample_count": payload.get("sample_count", 0),
                        "principal_total": payload.get("principal_total", 0),
                        "average_recovery_rate": payload.get("average_recovery_rate"),
                        "average_recovery_months": payload.get("average_recovery_months"),
                        "mediation_success_rate": payload.get("mediation_success_rate"),
                        "litigation_success_rate": payload.get("litigation_success_rate"),
                        "common_failure_reasons": payload.get("common_failure_reasons", []),
                    }
                note = knowledge_vault().write_court_note(profile, status="pending_confirmation" if not db.get_court_profile(court_name) else "confirmed")
                db.upsert_knowledge_note(note)
                db.audit(None, "court_note_saved", {"note_id": note["id"], "court_name": court_name, "status": note["status"], "memory_write": True})
                return self._send_json(200, {"ok": True, "note": note})

            if parsed.path == "/api/skills/private-drafts/generate":
                payload = self._read_json()
                draft_type = payload.get("draft_type") or "company_pricing_rule"
                if draft_type not in VALID_DRAFT_TYPES:
                    return self._error(400, "unsupported_private_skill_type", "不支持的私有 skill 草稿类型。", ["select_supported_draft_type"])
                spec = VALID_DRAFT_TYPES[draft_type]
                notes = db.list_confirmed_knowledge_notes(note_types=spec["note_types"])
                if not notes:
                    return self._error(400, "no_confirmed_memory", "没有可用于生成草稿的已确认记忆，请先确认公司偏好、法院经验或项目复盘。", ["confirm_memory", "save_company_preference", "save_court_experience"])
                draft_id = make_id("skdraft")
                try:
                    draft = private_skill_vault().generate(draft_id, draft_type, notes, payload.get("title"))
                except ValueError as exc:
                    return self._error(400, str(exc), "无法生成私有 skill 草稿。", ["confirm_memory"])
                db.insert_private_skill_draft(draft)
                db.audit(None, "private_skill_draft_generated", {"draft_id": draft_id, "draft_type": draft_type, "source_note_count": len(draft["source_note_ids"]), "status": draft["status"], "memory_write": True})
                return self._send_json(200, {"ok": True, "draft": draft, "next_actions": ["review_private_skill_draft", "keep_disabled_until_approved"]})

            match = re.fullmatch(r"/api/skills/private-drafts/([^/]+)/review", parsed.path)
            if match:
                draft_id = unquote(match.group(1))
                draft = db.get_private_skill_draft(draft_id)
                if not draft:
                    return self._error(404, "private_skill_draft_not_found", "私有 skill 草稿不存在")
                payload = self._read_json()
                status = payload.get("status") or "needs_revision"
                if status not in REVIEW_STATUSES:
                    return self._error(400, "invalid_private_skill_status", "审核状态只允许 draft、needs_revision、approved、archived。", ["select_valid_review_status"])
                review = {
                    "status": status,
                    "reviewer": payload.get("reviewer") or "local_user",
                    "review_note": payload.get("review_note") or ("审核通过，仅作为公司知识沉淀。" if status == "approved" else ""),
                    "reviewed_at": now_iso(),
                }
                updated = db.update_private_skill_draft(draft_id, {"status": status, "review": review})
                db.audit(None, "private_skill_draft_reviewed", {"draft_id": draft_id, "status": status, "reviewer": review["reviewer"], "memory_write": True})
                return self._send_json(200, {"ok": True, "draft": updated, "enabled": False, "message": "本阶段只审核草稿，不自动启用或调用。"})

            if parsed.path == "/api/settings/model":
                payload = self._read_json()
                stored = db.set_setting("model", payload)
                return self._send_json(200, {"ok": True, "model": stored})
            if parsed.path == "/api/security/confirmations":
                payload = self._read_json()
                action_type = payload.get("action_type")
                if action_type not in {"original_cloud_ai", "original_sensitive_export"}:
                    return self._error(400, "unsupported_confirmation_action", "安全确认类型只支持 original_cloud_ai 或 original_sensitive_export。", ["select_supported_confirmation"])
                confirmation_text = (payload.get("confirmation_text") or "").strip()
                if len(confirmation_text) < 6:
                    return self._error(400, "missing_confirmation_text", "请填写确认说明，例如：我确认本次原文云端分析。", ["enter_confirmation_text"])
                record = {
                    "id": make_id("confirm"),
                    "project_id": payload.get("project_id"),
                    "action_type": action_type,
                    "confirmation_text": confirmation_text,
                    "payload": {
                        "purpose": payload.get("purpose"),
                        "export_mode": payload.get("export_mode"),
                        "safety_mode": payload.get("safety_mode"),
                    },
                    "created_at": now_iso(),
                }
                db.insert_security_confirmation(record)
                db.audit(record.get("project_id"), "security_confirmation_created", {"confirmation_id": record["id"], "action_type": action_type, "safety_mode": payload.get("safety_mode"), "export_mode": payload.get("export_mode"), "sensitive_data_access": True})
                return self._send_json(200, {"ok": True, "confirmation": db.get_security_confirmation(record["id"]), "next_actions": ["continue_high_risk_action"]})
            if parsed.path == "/api/settings/document-parser/test":
                return self._send_json(200, parser_status())
            if parsed.path == "/api/documents/inspect":
                payload = self._read_json()
                filename = payload.get("filename") or "document.pdf"
                content = payload.get("content_base64") or ""
                if not content:
                    return self._error(400, "missing_document_content", "请上传需要检测的 PDF、图片、DOCX、TXT 或 HTML 文件。", ["upload_document"])
                ingested = ingest_bytes(base64.b64decode(content), filename)
                result = ingested.as_dict()
                result["text_preview"] = ingested.text[:1200]
                result.pop("text", None)
                return self._send_json(200, {"ok": True, "document": result, "next_actions": ["upload_to_project", "configure_ocr_if_needed"]})
            if parsed.path == "/api/settings/model/test":
                payload = self._read_json()
                result = test_model_config(payload or None)
                return self._send_json(200, {"ok": True, "result": {"text": result.text, "provider": result.provider, "model": result.model, "redacted": result.redacted, "prompt_audit": result.prompt_audit, "recommended_model": result.recommended_model, "next_actions": ["save_model_config", "use_for_ai_assist"]}})
            if parsed.path == "/api/settings/voice":
                payload = self._read_json()
                stored = db.set_setting("voice", payload)
                return self._send_json(200, {"ok": True, "voice": stored})
            if parsed.path == "/api/settings/voice/test":
                payload = self._read_json()
                sample = "这是 NPA Agent 的脱敏语音测试。"
                result = synthesize_speech(sample, payload or None)
                db.insert_voice_call({"id": make_id("vcall"), "provider": result.provider, "voice": result.voice, "text_chars": len(sample), "status": "success", "created_at": now_iso()})
                return self._send_json(200, {"ok": True, "audio_base64": base64.b64encode(result.audio).decode("ascii"), "content_type": result.content_type, "provider": result.provider, "voice": result.voice})

            if parsed.path == "/api/company-history/files":
                payload = self._read_json()
                file_id = make_id("histfile")
                saved = save_company_history_upload(file_id, payload["filename"], payload["content_base64"])
                record = {
                    "id": file_id,
                    "filename": payload["filename"],
                    "stored_path": saved["stored_path"],
                    "sha256": saved["sha256"],
                    "created_at": now_iso(),
                }
                db.insert_company_history_file(record)
                db.audit(None, "company_history_file_uploaded", {"file_id": file_id, "filename": record["filename"], "sha256": record["sha256"]})
                return self._send_json(200, {"ok": True, "file": record})

            if parsed.path == "/api/company-history/field-mapping/preview":
                payload = self._read_json()
                file_record = db.get_company_history_file(payload.get("file_id")) if payload.get("file_id") else db.latest_company_history_file()
                if not file_record:
                    return self._error(404, "history_file_not_found", "请先上传公司历史处置 Excel", ["upload_company_history_excel"])
                raw = parse_excel(file_record["stored_path"], payload.get("sheet_name"))
                mapping = preview_history_mapping(raw.headers, raw.rows)
                return self._send_json(
                    200,
                    {
                        "ok": True,
                        "sheet_name": raw.sheet_name,
                        "headers": raw.headers,
                        "mapping": mapping,
                        "unmapped_columns": unmapped_columns(raw.headers, mapping),
                        "preview_rows": preview_history_rows(raw.rows, mapping),
                        "next_actions": ["confirm_company_history_mapping"],
                    },
                )

            if parsed.path == "/api/company-history/field-mapping/confirm":
                payload = self._read_json()
                file_record = db.get_company_history_file(payload.get("file_id")) if payload.get("file_id") else db.latest_company_history_file()
                if not file_record:
                    return self._error(404, "history_file_not_found", "请先上传公司历史处置 Excel")
                raw = parse_excel(file_record["stored_path"], payload.get("sheet_name"))
                mapping = payload.get("mapping") or {}
                records, errors = normalize_history_rows(raw.rows, mapping, file_record["id"])
                if not records:
                    return self._error(400, "missing_history_amount_basis", "历史数据至少需要本金总额或回款金额，才能用于校准。", ["confirm_company_history_mapping", "download_company_history_template"])
                db.save_company_history_mapping({"id": make_id("histmap"), "file_id": file_record["id"], "mapping": mapping, "confidence": payload.get("confidence", {}), "created_at": now_iso()})
                db.replace_company_history_records(file_record["id"], records)
                profiles = build_court_profiles(db.list_company_history_records())
                db.replace_court_profiles(profiles)
                db.audit(None, "company_history_imported", {"file_id": file_record["id"], "record_count": len(records), "error_count": len(errors), "court_profile_count": len(profiles)})
                return self._send_json(200, {"ok": True, "normalized_count": len(records), "errors": errors, "court_profile_count": len(profiles), "next_actions": ["review_court_profiles", "rerun_project_analysis"]})

            if parsed.path == "/api/intelligence/yindeng/fetch":
                payload = self._read_json()
                fetched = fetch_public_url(payload["url"])
                source_id = make_id("src")
                preliminary = parse_yindeng_notice(fetched.raw_text, fetched.url, fetched.content_type, fetched.ingestion)
                preliminary, notice_raw_text, notice_raw_sha, attachment_extractions = enrich_yindeng_with_public_attachments(preliminary, fetched)
                db.insert_intelligence_source(
                    {
                        "id": source_id,
                        "source_type": payload.get("source_type", "public_url"),
                        "url": fetched.url,
                        "title": preliminary.title,
                        "raw_text": notice_raw_text,
                        "raw_sha256": notice_raw_sha,
                        "fetched_at": now_iso(),
                        "created_at": now_iso(),
                    }
                )
                notice, duplicate, alerts = save_yindeng_notice_with_alerts(preliminary, notice_raw_text, source_id, fetched.url, notice_raw_sha)
                db.audit(None, "yindeng_notice_fetched", {"notice_id": notice["id"], "source_url": fetched.url, "sha256": notice_raw_sha, "confidence": notice["confidence"], "duplicate": duplicate, "alert_count": len(alerts), "attachment_count": len(attachment_extractions), "network_access": True})
                return self._send_json(200, {"ok": True, "source_id": source_id, "notice": json_safe(notice), "duplicate": duplicate, "alerts": alerts, "attachment_extractions": attachment_extractions, "next_actions": ["review_notice", "create_project", "paste_notice_text_if_low_confidence"]})

            if parsed.path == "/api/intelligence/yindeng/parse":
                payload = self._read_json()
                raw_text = payload.get("text") or payload.get("content") or ""
                ingestion = None
                if not raw_text.strip() and payload.get("content_base64"):
                    filename = payload.get("filename") or "notice.pdf"
                    ingested = ingest_bytes(base64.b64decode(payload["content_base64"]), filename)
                    raw_text = ingested.text
                    ingestion = ingested.as_dict()
                if not raw_text.strip():
                    return self._error(400, "missing_notice_text", "请粘贴银登公告正文、上传公告 PDF/图片，或先使用公开 URL 抓取。", ["paste_notice_text", "upload_notice_pdf_or_image", "fetch_public_url"])
                source_id = make_id("src")
                raw_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                preliminary = parse_yindeng_notice(raw_text, payload.get("source_url"), payload.get("content_type"), ingestion)
                if ingestion and ingestion.get("attachments"):
                    preliminary.attachments = ingestion["attachments"]
                    preliminary.parsed["attachments"] = ingestion["attachments"]
                db.insert_intelligence_source(
                    {
                        "id": source_id,
                        "source_type": payload.get("source_type", "manual_text"),
                        "url": payload.get("source_url"),
                        "title": preliminary.title,
                        "raw_text": raw_text,
                        "raw_sha256": raw_sha256,
                        "fetched_at": now_iso(),
                        "created_at": now_iso(),
                    }
                )
                notice, duplicate, alerts = save_yindeng_notice_with_alerts(preliminary, raw_text, source_id, payload.get("source_url"), raw_sha256)
                db.audit(None, "yindeng_notice_parsed", {"notice_id": notice["id"], "source_url": payload.get("source_url"), "sha256": raw_sha256, "confidence": notice["confidence"], "duplicate": duplicate, "alert_count": len(alerts), "sensitive_data_access": False})
                return self._send_json(200, {"ok": True, "source_id": source_id, "notice": json_safe(notice), "duplicate": duplicate, "alerts": alerts, "next_actions": ["review_notice", "create_project"]})

            if parsed.path == "/api/intelligence/yindeng/subscriptions":
                payload = self._read_json()
                keyword = (payload.get("keyword") or "").strip()
                if not keyword:
                    return self._error(400, "missing_keyword", "请填写订阅关键词。", ["enter_keyword"])
                record = {"id": make_id("yndsub"), "keyword": keyword, "enabled": payload.get("enabled", True), "created_at": now_iso()}
                db.insert_yindeng_subscription(record)
                db.audit(None, "yindeng_subscription_created", {"subscription_id": record["id"], "keyword": keyword, "enabled": record["enabled"]})
                return self._send_json(200, {"ok": True, "subscription": record, "next_actions": ["parse_yindeng_notice", "review_yindeng_alerts"]})

            match = re.fullmatch(r"/api/intelligence/yindeng/notices/([^/]+)/create-project", parsed.path)
            if match:
                notice = db.get_yindeng_notice(match.group(1))
                if not notice:
                    return self._error(404, "notice_not_found", "银登公告不存在")
                project = {
                    "id": make_id("prj"),
                    "name": f"银登机会 - {notice['title'][:42]}",
                    "asset_type": notice.get("asset_type") or "nonperforming_loan",
                    "status": "draft",
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "latest_report_id": None,
                }
                db.insert_project(project)
                db.audit(project["id"], "project_created_from_yindeng", {"notice_id": notice["id"], "source_url": notice.get("source_url")})
                return self._send_json(200, {"ok": True, "project": project, "notice": notice, "next_actions": ["upload_asset_package_excel", "review_yindeng_notice"]})

            if parsed.path == "/api/ai/generate":
                payload = self._read_json()
                purpose = payload.get("purpose") or "general"
                content = payload.get("content") or ""
                if not content.strip():
                    return self._error(400, "missing_content", "请先提供需要 AI 分析的内容。", ["paste_content", "select_report"])
                model_setting = db.get_setting("model", default_model_setting())
                requested_mode = payload.get("safety_mode") or model_setting.get("mode") or "redacted_cloud"
                confirmation_id = payload.get("confirmation_id")
                if requested_mode == "original_cloud" and (not payload.get("confirm_original_cloud") or not validate_confirmation(confirmation_id, "original_cloud_ai", payload.get("project_id"))):
                    db.audit(payload.get("project_id"), "ai_original_cloud_denied", {"purpose": purpose, "safety_mode": requested_mode, "sensitive_data_access": True, "network_access": True, "confirmation_id": confirmation_id})
                    return self._error(403, "original_cloud_not_confirmed", "原文云端分析需要先完成二次确认。", ["create_original_cloud_confirmation", "switch_to_redacted_cloud"])
                try:
                    override = payload.get("model_override") or {}
                    if requested_mode == "original_cloud":
                        override = {**override, "allow_original_sensitive_data": True}
                    result = generate_text(purpose, content, requested_mode, payload.get("project_id"), override)
                    db.insert_model_call(
                        {
                            "id": make_id("mcall"),
                            "project_id": payload.get("project_id"),
                            "provider": result.provider,
                            "model": result.model,
                            "purpose": purpose,
                            "safety_mode": requested_mode,
                            "prompt_chars": result.prompt_chars,
                            "response_chars": result.response_chars,
                            "status": "success",
                            "created_at": now_iso(),
                        }
                    )
                    db.audit(payload.get("project_id"), "ai_generated", {"provider": result.provider, "model": result.model, "purpose": purpose, "safety_mode": requested_mode, "sensitive_data_access": requested_mode == "original_cloud", "network_access": True, "confirmation_id": confirmation_id, "prompt_chars": result.prompt_chars, "response_chars": result.response_chars, "redacted": result.redacted})
                    return self._send_json(200, {"ok": True, "result": {"text": result.text, "provider": result.provider, "model": result.model, "redacted": result.redacted, "prompt_audit": result.prompt_audit, "recommended_model": result.recommended_model, "next_actions": ["review_prompt_audit", "save_result_if_useful"]}})
                except ModelGatewayError as exc:
                    db.insert_model_call(
                        {
                            "id": make_id("mcall"),
                            "project_id": payload.get("project_id"),
                            "provider": "unknown",
                            "model": "unknown",
                            "purpose": purpose,
                            "safety_mode": requested_mode,
                            "prompt_chars": len(content),
                            "response_chars": 0,
                            "status": "error",
                            "error": exc.code,
                            "created_at": now_iso(),
                        }
                    )
                    db.audit(payload.get("project_id"), "ai_generate_failed", {"purpose": purpose, "safety_mode": requested_mode, "network_access": True, "error": exc.code})
                    return self._error(400, exc.code, exc.message, ["configure_model", "check_provider_base_url", "use_local_rules"])

            if parsed.path == "/api/voice/tts":
                payload = self._read_json()
                text = payload.get("text") or ""
                if not text.strip():
                    return self._error(400, "missing_tts_text", "请提供需要播报的文本。")
                try:
                    result = synthesize_speech(text, payload.get("voice_override"))
                    db.insert_voice_call({"id": make_id("vcall"), "provider": result.provider, "voice": result.voice, "text_chars": len(text), "status": "success", "created_at": now_iso()})
                    db.audit(None, "voice_tts_generated", {"provider": result.provider, "voice": result.voice, "text_chars": len(text), "network_access": result.provider != "builtin_browser", "sensitive_data_access": False})
                    return self._send_json(200, {"ok": True, "audio_base64": base64.b64encode(result.audio).decode("ascii"), "content_type": result.content_type, "provider": result.provider, "voice": result.voice})
                except VoiceGatewayError as exc:
                    db.insert_voice_call({"id": make_id("vcall"), "provider": "unknown", "voice": None, "text_chars": len(text), "status": "error", "error": exc.code, "created_at": now_iso()})
                    db.audit(None, "voice_tts_failed", {"provider": "unknown", "text_chars": len(text), "network_access": True, "error": exc.code})
                    return self._error(400, exc.code, exc.message, ["configure_voice", "use_builtin_browser_voice"])
            return self._not_found()
        except YindengFetchError as exc:
            return self._error(400, exc.code, exc.message, exc.next_actions)
        except DocumentExtractionError as exc:
            return self._error(400, exc.code, exc.message, ["upload_pdf_image_docx_txt_html", "paste_text_version", "configure_local_ocr"])
        except ModelGatewayError as exc:
            return self._error(400, exc.code, exc.message, ["configure_model", "use_local_rules"])
        except VoiceGatewayError as exc:
            return self._error(400, exc.code, exc.message, ["configure_voice", "use_builtin_browser_voice"])
        except KeyError as exc:
            return self._error(400, "bad_request", f"缺少字段: {exc}")
        except Exception as exc:
            return self._error(500, "server_error", str(exc))

    def do_PATCH(self):
        parsed = urlparse(self.path)
        try:
            match = re.fullmatch(r"/api/projects/([^/]+)/execution/tasks/([^/]+)", parsed.path)
            if match:
                project_id, task_id = match.group(1), match.group(2)
                if not db.get_project(project_id):
                    return self._error(404, "project_not_found", "项目不存在")
                payload = self._read_json()
                task = db.update_execution_task(project_id, task_id, payload)
                if not task:
                    return self._error(404, "execution_task_not_found", "执行任务不存在")
                db.audit(project_id, "execution_task_updated", {"task_id": task_id, "status": task.get("status"), "latest_result": task.get("latest_result")})
                return self._send_json(200, {"ok": True, "task": task})
            match = re.fullmatch(r"/api/skills/private-drafts/([^/]+)", parsed.path)
            if match:
                draft_id = unquote(match.group(1))
                draft = db.get_private_skill_draft(draft_id)
                if not draft:
                    return self._error(404, "private_skill_draft_not_found", "私有 skill 草稿不存在")
                payload = self._read_json()
                updates = {}
                if "name" in payload:
                    updates["name"] = payload["name"]
                if "manifest_text" in payload:
                    updates["manifest_text"] = payload["manifest_text"]
                if "markdown" in payload:
                    updates["markdown"] = payload["markdown"]
                if "status" in payload:
                    if payload["status"] not in REVIEW_STATUSES:
                        return self._error(400, "invalid_private_skill_status", "审核状态只允许 draft、needs_revision、approved、archived。", ["select_valid_review_status"])
                    updates["status"] = payload["status"]
                updated = db.update_private_skill_draft(draft_id, updates)
                if updated and "markdown" in updates:
                    updated = private_skill_vault().rewrite_file(updated)
                    db.update_private_skill_draft(draft_id, {"markdown": updated["markdown"]})
                db.audit(None, "private_skill_draft_updated", {"draft_id": draft_id, "fields": sorted(updates)})
                return self._send_json(200, {"ok": True, "draft": db.get_private_skill_draft(draft_id)})
            return self._not_found()
        except KeyError as exc:
            return self._error(400, "bad_request", f"缺少字段: {exc}")
        except Exception as exc:
            return self._error(500, "server_error", str(exc))

    def _send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            return self._error(404, "file_not_found", "文件不存在")
        body = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        encoded_name = quote(path.name)
        fallback_name = f"download{path.suffix or '.bin'}"
        self.send_header("Content-Disposition", f"attachment; filename=\"{fallback_name}\"; filename*=UTF-8''{encoded_name}")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, request_path: str):
        if request_path in {"", "/"}:
            target = FRONTEND_DIR / "index.html"
        else:
            target = (FRONTEND_DIR / request_path.lstrip("/")).resolve()
            if not str(target).startswith(str(FRONTEND_DIR.resolve())):
                return self._error(403, "forbidden", "禁止访问")
        if not target.exists() or not target.is_file():
            target = FRONTEND_DIR / "index.html"
        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "text/html"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    db.init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    print(f"NPA Agent running at http://{display_host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping NPA Agent")


if __name__ == "__main__":
    main()
