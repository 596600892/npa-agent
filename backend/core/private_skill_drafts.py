from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from .privacy import redact_text


VALID_DRAFT_TYPES = {
    "company_pricing_rule": {
        "display": "公司报价规则",
        "note_types": {"company_preference", "project"},
        "scenario": "根据公司已确认偏好和项目复盘，辅助生成报价假设与报价复核提示。",
        "outputs": ["pricing_rule_summary", "assumption_checklist", "risk_boundary"],
    },
    "court_disposition_experience": {
        "display": "法院处置经验",
        "note_types": {"court", "court_experience", "project"},
        "scenario": "根据已确认法院画像、法院经验和项目复盘，辅助识别处置路径和诉讼/执行关注点。",
        "outputs": ["court_experience_summary", "disposition_hints", "case_handling_warnings"],
    },
    "report_style_preference": {
        "display": "报告风格偏好",
        "note_types": {"company_preference", "project"},
        "scenario": "根据已确认公司偏好和项目复盘，辅助统一报告结构、摘要顺序和表达边界。",
        "outputs": ["report_style_rules", "summary_format", "wording_boundaries"],
    },
}

REVIEW_STATUSES = {"draft", "needs_revision", "approved", "archived"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class PrivateSkillDraftVault:
    def __init__(self, root: Path):
        self.root = Path(root)

    def generate(self, draft_id: str, draft_type: str, notes: list[dict], title: str | None = None) -> dict:
        if draft_type not in VALID_DRAFT_TYPES:
            raise ValueError("unsupported_private_skill_type")
        spec = VALID_DRAFT_TYPES[draft_type]
        selected_notes = [note for note in notes if note.get("status") == "confirmed" and note.get("note_type") in spec["note_types"]]
        if not selected_notes:
            raise ValueError("no_confirmed_memory")
        name = title or f"{spec['display']}私有 Skill 草稿"
        source_note_ids = [note["id"] for note in selected_notes]
        evidence = _evidence_lines(selected_notes)
        manifest_text = _manifest_text(draft_type, name, spec, selected_notes)
        markdown = _markdown_text(name, draft_type, spec, selected_notes, manifest_text, evidence)
        content = redact_text(markdown)
        manifest_text = redact_text(manifest_text)
        path = self._write(Path(f"{_safe_slug(draft_type)}-{draft_id}.md"), content)
        stamp = now_iso()
        return {
            "id": draft_id,
            "draft_type": draft_type,
            "name": name,
            "status": "draft",
            "risk_level": "medium",
            "manifest_text": manifest_text,
            "markdown": content,
            "path": path,
            "source_note_ids": source_note_ids,
            "review": {
                "status": "draft",
                "reviewer": None,
                "review_note": "本阶段只生成草稿，不自动启用或参与分析。",
                "reviewed_at": None,
            },
            "created_at": stamp,
            "updated_at": stamp,
        }

    def rewrite_file(self, draft: dict) -> dict:
        path = Path(draft["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = redact_text(draft.get("markdown") or "")
        path.write_text(content, encoding="utf-8")
        draft["markdown"] = content
        return draft

    def _write(self, relative_path: Path, content: str) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)


def _manifest_text(draft_type: str, name: str, spec: dict, notes: list[dict]) -> str:
    sources = ", ".join(note["id"] for note in notes[:12])
    outputs = "\n".join(f"  - {item}" for item in spec["outputs"])
    return f"""name: private_{draft_type}
display_name: {name}
risk_level: medium
status: draft
description: {spec["scenario"]}
required_inputs:
  - confirmed_memory
optional_inputs:
  - current_project_context
  - court_profile
permissions:
  read_local_files: false
  write_project_record: false
  network_access: false
  read_memory: true
  write_memory: false
  access_sensitive_data: false
outputs:
{outputs}
source_note_ids: [{sources}]
disabled_boundaries:
  - 本阶段不自动启用
  - 不参与资产包分析链路
  - 不读取或输出完整债务人敏感信息
  - 不联网、不安装外部 skill
review_required: true
"""


def _markdown_text(name: str, draft_type: str, spec: dict, notes: list[dict], manifest_text: str, evidence: list[str]) -> str:
    lines = [
        "---",
        "type: private_skill_draft",
        f"draft_type: {draft_type}",
        "status: draft",
        "---",
        "",
        f"# {name}",
        "",
        "## 适用场景",
        "",
        spec["scenario"],
        "",
        "## 草稿 Manifest",
        "",
        "```yaml",
        manifest_text.strip(),
        "```",
        "",
        "## 依据来源",
        "",
        *evidence,
        "",
        "## 权限与风险",
        "",
        "- 风险等级：medium",
        "- 联网权限：false",
        "- 敏感数据访问：false",
        "- 写项目记录：false",
        "- 读取记忆：true，仅限 confirmed 本地记忆",
        "",
        "## 禁用边界",
        "",
        "- 不自动启用。",
        "- 不参与当前资产包分析链路。",
        "- 不替代人工投资判断、法律意见或处置决策。",
        "- 不保存完整身份证、手机号、详细地址或完整资产清单。",
        "",
        "## 人工审核提示",
        "",
        "- 审核通过只代表可作为公司知识沉淀。",
        "- 后续如要启用调用，必须另行做沙箱、版本锁定、权限审计和回归测试。",
        "",
    ]
    return redact_text("\n".join(lines))


def _evidence_lines(notes: list[dict]) -> list[str]:
    lines = []
    for note in notes[:12]:
        summary = _compact(note.get("summary") or note.get("content_text") or "")
        lines.append(f"- `{note['id']}`：{note.get('title')}；类型 {note.get('note_type')}；摘要：{summary}")
    return lines or ["- 暂无依据。"]


def _compact(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", redact_text(value or "")).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _safe_slug(value: str | None) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fa5-]+", "-", str(value or "draft")).strip("-_")
    return text[:80] or "draft"


def content_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
