from __future__ import annotations

import base64
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = ROOT / "data" / "uploads"
REPORT_DIR = ROOT / "data" / "reports"
COMPANY_HISTORY_DIR = ROOT / "data" / "company_history"
LEGAL_DOC_DIR = ROOT / "data" / "legal_docs"


def save_upload(project_id: str, file_id: str, filename: str, content_base64: str) -> dict:
    project_dir = UPLOAD_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix or ".xlsx"
    stored_path = project_dir / f"{file_id}{suffix}"
    content = base64.b64decode(content_base64)
    stored_path.write_bytes(content)
    return {
        "stored_path": str(stored_path),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def save_report(project_id: str, report_id: str, markdown: str) -> str:
    project_dir = REPORT_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / f"{report_id}.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def save_company_history_upload(file_id: str, filename: str, content_base64: str) -> dict:
    COMPANY_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix or ".xlsx"
    stored_path = COMPANY_HISTORY_DIR / f"{file_id}{suffix}"
    content = base64.b64decode(content_base64)
    stored_path.write_bytes(content)
    return {
        "stored_path": str(stored_path),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def save_legal_document_upload(project_id: str, document_id: str, filename: str, content_base64: str) -> dict:
    project_dir = LEGAL_DOC_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    stored_path = project_dir / f"{document_id}{suffix}"
    content = base64.b64decode(content_base64)
    stored_path.write_bytes(content)
    return {
        "stored_path": str(stored_path),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
