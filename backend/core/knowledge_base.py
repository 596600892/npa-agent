from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from .privacy import redact_text


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class KnowledgeVault:
    def __init__(self, root: Path):
        self.root = Path(root)

    def write_project_note(
        self,
        project: dict,
        report: dict | None,
        legal_risk: dict | None,
        execution_plan: dict | None,
        execution_tasks: list[dict],
        execution_events: list[dict],
    ) -> dict:
        title = f"{project['name']} 项目复盘"
        note_id = f"project_{project['id']}"
        relative_path = Path("projects") / f"{_safe_slug(project['name'])}-{project['id']}.md"
        lines = [
            "---",
            f"type: project",
            f"project_id: {project['id']}",
            f"status: confirmed",
            "---",
            "",
            f"# {title}",
            "",
            "## 项目摘要",
            "",
            f"- 资产类型：{project.get('asset_type') or '未知'}",
            f"- 项目状态：{project.get('status') or '未知'}",
            f"- 最近报告：{report.get('id') if report else '未生成'}",
            "",
        ]
        if report:
            summary = report.get("data", {}).get("summary", {})
            metrics = report.get("data", {}).get("metrics", {})
            quality = report.get("data", {}).get("quality", {})
            lines.extend(
                [
                    "## 报告结论",
                    "",
                    f"- 推荐等级：{summary.get('rating', '未识别')}",
                    f"- 建议动作：{summary.get('recommendation', '未识别')}",
                    f"- 主路径：{summary.get('primary_strategy', '未识别')}",
                    f"- 户数：{metrics.get('account_count', '未识别')}",
                    f"- 本金合计：{metrics.get('principal_total', '未识别')}",
                    f"- 数据完整度：{quality.get('score', '未识别')}",
                    "",
                    "## 报告正文摘要",
                    "",
                    _trim_markdown(report.get("markdown", ""), 1800),
                    "",
                ]
            )
        if legal_risk:
            lines.extend(
                [
                    "## 合同/文书风险",
                    "",
                    f"- 整体风险：{legal_risk.get('overall_risk', '未分析')}",
                    f"- 可信度：{legal_risk.get('confidence', 'unknown')}",
                    f"- 来源文件：{legal_risk.get('filename', '合同/文书')}",
                    "",
                ]
            )
            for key, item in (legal_risk.get("risks") or {}).items():
                lines.append(f"- {item.get('label', key)}：{item.get('risk', 'unknown')}，{item.get('conclusion', '')}")
            lines.append("")
        if execution_plan:
            summary = execution_plan.get("summary", {})
            lines.extend(
                [
                    "## 处置执行计划",
                    "",
                    f"- 执行任务：{summary.get('task_count', 0)}",
                    f"- 首轮调解：{summary.get('first_round_count', 0)}",
                    f"- 高优先级：{summary.get('high_priority_count', 0)}",
                    f"- 补线索：{summary.get('missing_signal_count', 0)}",
                    f"- 诉讼候选：{summary.get('litigation_candidate_count', 0)}",
                    "",
                    "| 批次 | 层级 | 优先级 | 债务人 | 本金 | 状态 | 下一步 |",
                    "|---|---:|---:|---|---:|---|---|",
                ]
            )
            for task in execution_tasks[:20]:
                lines.append(
                    f"| {task.get('batch_name')} | {task.get('tier')} | {task.get('priority_score')} | {task.get('masked_debtor')} | {task.get('principal')} | {task.get('status')} | {task.get('next_action')} |"
                )
            lines.append("")
        if execution_events:
            lines.extend(["## 跟进记录摘要", ""])
            for event in execution_events[:20]:
                lines.append(f"- {event.get('created_at')}：{event.get('result') or event.get('event_type')}；{event.get('note') or ''}；下一步：{event.get('next_action') or ''}")
            lines.append("")
        lines.extend(["## 待确认记忆", "", "- 法院主观评价、公司定价规则、处置偏好需人工确认后再沉淀为长期偏好。", ""])
        content = redact_text("\n".join(lines))
        path = self._write(relative_path, content)
        return _record(note_id, "project", project["id"], title, path, content, ["项目复盘", project.get("asset_type") or "资产包"], {"project_id": project["id"]}, "confirmed")

    def write_court_note(self, profile: dict, status: str = "confirmed") -> dict:
        court_name = profile["court_name"]
        title = f"{court_name} 法院经验"
        note_id = f"court_{_safe_slug(court_name)}"
        relative_path = Path("courts") / f"{_safe_slug(court_name)}.md"
        failures = "、".join(profile.get("common_failure_reasons", [])) or "暂无"
        lines = [
            "---",
            "type: court",
            f"court_name: {court_name}",
            f"status: {status}",
            "---",
            "",
            f"# {title}",
            "",
            "## 法院画像",
            "",
            f"- 标签：{profile.get('label', 'normal')}",
            f"- 地区：{profile.get('region') or '未知'}",
            f"- 样本数：{profile.get('sample_count', 0)}",
            f"- 历史本金：{profile.get('principal_total', 0)}",
            f"- 平均回收率：{_fmt(profile.get('average_recovery_rate'))}",
            f"- 平均回款周期：{_fmt(profile.get('average_recovery_months'), ' 月')}",
            f"- 调解成功率：{_fmt(profile.get('mediation_success_rate'))}",
            f"- 诉讼成功率：{_fmt(profile.get('litigation_success_rate'))}",
            f"- 常见失败原因：{failures}",
            "",
            "## 待确认经验",
            "",
            "- 受理体验、执行效率、批量立案便利度等主观评价需人工确认后写入长期偏好。",
            "",
        ]
        content = redact_text("\n".join(lines))
        path = self._write(relative_path, content)
        return _record(note_id, "court", court_name, title, path, content, ["法院画像", court_name], {"court_name": court_name}, status)

    def write_company_preference_note(self, payload: dict) -> dict:
        title = payload.get("title") or "公司偏好待确认"
        status = "confirmed" if payload.get("confirmed") else "pending_confirmation"
        status_label = "已确认" if status == "confirmed" else "待确认"
        note_id = f"company_preference_{_safe_slug(title)}"
        relative_path = Path("company") / f"{_safe_slug(title)}.md"
        lines = [
            "---",
            "type: company_preference",
            f"status: {status}",
            "---",
            "",
            f"# {title}",
            "",
            f"- 状态：{status_label}（{status}）",
            f"- 偏好类型：{payload.get('preference_type') or '未分类'}",
            "",
            "## 内容",
            "",
            redact_text(payload.get("content") or ""),
            "",
            "## 来源",
            "",
            f"- {payload.get('source') or '用户输入'}",
            "",
        ]
        content = redact_text("\n".join(lines))
        path = self._write(relative_path, content)
        return _record(note_id, "company_preference", payload.get("preference_type"), title, path, content, ["公司偏好", status], {"source": payload.get("source") or "user"}, status)

    def write_court_experience_note(self, court_name: str, payload: dict, profile: dict | None = None) -> dict:
        status = "confirmed" if payload.get("confirmed") else "pending_confirmation"
        status_label = "已确认" if status == "confirmed" else "待确认"
        title = payload.get("title") or f"{court_name} 人工经验"
        note_id = f"court_experience_{_safe_slug(court_name)}_{_safe_slug(title)}"
        relative_path = Path("courts") / f"{_safe_slug(court_name)}-experience-{_safe_slug(title)}.md"
        lines = [
            "---",
            "type: court_experience",
            f"court_name: {court_name}",
            f"status: {status}",
            "---",
            "",
            f"# {title}",
            "",
            f"- 法院：{court_name}",
            f"- 状态：{status_label}（{status}）",
            f"- 画像标签：{(profile or {}).get('label', '未生成画像')}",
            f"- 地区：{(profile or {}).get('region') or payload.get('region') or '未知'}",
            "",
            "## 经验内容",
            "",
            redact_text(payload.get("experience") or payload.get("content") or ""),
            "",
            "## 适用边界",
            "",
            payload.get("scope") or "仅作为公司内部经验复盘，后续报价和诉讼策略需要结合最新项目数据。",
            "",
        ]
        content = redact_text("\n".join(lines))
        path = self._write(relative_path, content)
        tags = ["法院经验", court_name, status]
        return _record(note_id, "court_experience", court_name, title, path, content, tags, {"court_name": court_name, "source": payload.get("source") or "user"}, status)

    def confirm_note(self, note: dict, confirmation_note: str | None = None) -> dict:
        content = note.get("content_text") or ""
        content = re.sub(r"status:\s*\w+", "status: confirmed", content, count=1)
        content = re.sub(r"- 状态：.*", "- 状态：已确认（confirmed）", content, count=1)
        lines = [content.rstrip(), "", "## 确认记录", "", f"- 确认时间：{now_iso()}"]
        if confirmation_note:
            lines.append(f"- 确认说明：{redact_text(confirmation_note)}")
        lines.append("")
        content = redact_text("\n".join(lines))
        path = Path(note["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _record(
            note["id"],
            note["note_type"],
            note.get("scope_id"),
            note["title"],
            str(path),
            content,
            note.get("tags", []),
            note.get("source", {}),
            "confirmed",
        )

    def _write(self, relative_path: Path, content: str) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)


def _record(note_id: str, note_type: str, scope_id: str | None, title: str, path: str, content: str, tags: list[str], source: dict, status: str) -> dict:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    stamp = now_iso()
    return {
        "id": note_id,
        "note_type": note_type,
        "scope_id": scope_id,
        "title": title,
        "path": path,
        "summary": _summary(content),
        "tags": tags,
        "source": source,
        "status": status,
        "content_text": content,
        "content_sha256": digest,
        "created_at": stamp,
        "updated_at": stamp,
    }


def _safe_slug(value: str | None) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fa5-]+", "-", str(value or "note")).strip("-_")
    return text[:80] or "note"


def _summary(content: str) -> str:
    lines = [line.strip("#- >| ") for line in content.splitlines() if line.strip() and not line.startswith("---")]
    return "；".join(lines[:4])[:240]


def _trim_markdown(markdown: str, limit: int) -> str:
    text = redact_text(markdown or "")
    return text[:limit] + ("\n\n...（已截断，完整报告见项目报告记录）" if len(text) > limit else "")


def _fmt(value, suffix: str = "") -> str:
    if value is None:
        return "样本不足"
    if isinstance(value, float) and value <= 1:
        return f"{value:.1%}"
    return f"{value}{suffix}"
