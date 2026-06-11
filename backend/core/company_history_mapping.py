from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .field_mapping import normalize_header, parse_number


HISTORY_FIELDS = [
    "project_name",
    "asset_type",
    "region",
    "court_name",
    "account_count",
    "principal_total",
    "purchase_price",
    "recovered_amount",
    "recovery_months",
    "disposal_method",
    "mediation_success_rate",
    "litigation_success_rate",
    "execution_result",
    "failure_reason",
    "notes",
]

HISTORY_LABELS = {
    "project_name": "项目名称",
    "asset_type": "资产类型",
    "region": "地区",
    "court_name": "法院",
    "account_count": "户数",
    "principal_total": "本金总额",
    "purchase_price": "成交价",
    "recovered_amount": "回款金额",
    "recovery_months": "回款周期（月）",
    "disposal_method": "处置方式",
    "mediation_success_rate": "调解成功率",
    "litigation_success_rate": "诉讼成功率",
    "execution_result": "执行结果",
    "failure_reason": "失败原因",
    "notes": "备注",
}

HISTORY_ALIASES = {
    "project_name": ["项目名称", "项目", "资产包名称", "历史项目", "包名"],
    "asset_type": ["资产类型", "类型", "债权类型", "贷款类型", "产品类型"],
    "region": ["地区", "区域", "省份", "城市", "处置地区", "所在地"],
    "court_name": ["法院", "管辖法院", "执行法院", "处置法院", "受理法院", "主要法院"],
    "account_count": ["户数", "户数合计", "债务人户数", "客户数", "案件数", "笔数"],
    "principal_total": ["本金总额", "本金合计", "本金", "未偿本金", "债权本金", "本金余额"],
    "purchase_price": ["成交价", "收购价", "买包价格", "购买价", "对价", "投资金额"],
    "recovered_amount": ["回款金额", "实收金额", "回收金额", "累计回款", "回款总额", "清收回款"],
    "recovery_months": ["回款周期（月）", "回款周期", "处置周期", "周期（月）", "回收周期（月）"],
    "disposal_method": ["处置方式", "处置模式", "清收方式", "策略", "主要方式"],
    "mediation_success_rate": ["调解成功率", "调解率", "电话调解成功率", "和解率"],
    "litigation_success_rate": ["诉讼成功率", "胜诉率", "立案成功率", "诉讼回款率"],
    "execution_result": ["执行结果", "执行情况", "终本情况", "执行反馈"],
    "failure_reason": ["失败原因", "失败因素", "未回款原因", "难点", "问题"],
    "notes": ["备注", "说明", "经验", "法院反馈", "处置备注"],
}


@dataclass
class HistoryMappingChoice:
    source_column: str | None
    confidence: float
    needs_confirmation: bool
    label: str


def _header_score(header: str, field: str) -> float:
    normalized = normalize_header(header)
    for alias in HISTORY_ALIASES[field]:
        candidate = normalize_header(alias)
        if normalized == candidate:
            return 0.93
        if candidate and candidate in normalized:
            return 0.78
    return 0.0


def _content_score(values: list[Any], field: str) -> float:
    nonempty = [str(value).strip() for value in values if str(value or "").strip()]
    if not nonempty:
        return 0.0
    if field in {"account_count", "principal_total", "purchase_price", "recovered_amount", "recovery_months", "mediation_success_rate", "litigation_success_rate"}:
        return sum(1 for value in nonempty if parse_number(value) is not None) / len(nonempty) * 0.28
    if field == "court_name":
        return sum(1 for value in nonempty if "法院" in value) / len(nonempty) * 0.30
    if field == "asset_type":
        return sum(1 for value in nonempty if any(token in value for token in ["个贷", "消费", "房抵", "企业", "信用卡"])) / len(nonempty) * 0.18
    if field == "disposal_method":
        return sum(1 for value in nonempty if any(token in value for token in ["调解", "诉讼", "执行", "分包", "清收"])) / len(nonempty) * 0.18
    return min(len(nonempty) / max(len(values), 1) * 0.10, 0.10)


def preview_history_mapping(headers: list[str], rows: list[dict[str, Any]]) -> dict[str, dict]:
    used_columns: set[str] = set()
    mapping: dict[str, dict] = {}
    for field in HISTORY_FIELDS:
        best_header = None
        best_score = 0.0
        for header in headers:
            if header in used_columns:
                continue
            values = [row.get(header) for row in rows]
            score = min(0.99, _header_score(header, field) + _content_score(values, field))
            if score > best_score:
                best_header = header
                best_score = score
        if best_header and best_score >= 0.52:
            used_columns.add(best_header)
            mapping[field] = {
                "source_column": best_header,
                "confidence": round(best_score, 2),
                "needs_confirmation": best_score < 0.80,
                "label": HISTORY_LABELS[field],
            }
        else:
            mapping[field] = {
                "source_column": None,
                "confidence": 0.0,
                "needs_confirmation": field in {"principal_total", "recovered_amount"},
                "label": HISTORY_LABELS[field],
            }
    return mapping
