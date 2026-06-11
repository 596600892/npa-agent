from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


STANDARD_FIELDS = [
    "debtor_name_or_id",
    "id_card",
    "phone",
    "address",
    "principal",
    "interest",
    "overdue_days",
    "contract_no",
    "jurisdiction_court",
    "remark",
]

FIELD_LABELS = {
    "debtor_name_or_id": "债务人名称/编号",
    "id_card": "身份证号",
    "phone": "手机号",
    "address": "地址",
    "principal": "本金",
    "interest": "利息",
    "overdue_days": "逾期天数",
    "contract_no": "合同编号",
    "jurisdiction_court": "管辖法院",
    "remark": "备注",
}

ALIASES = {
    "debtor_name_or_id": ["债务人名称", "债务人姓名", "客户名称", "客户姓名", "姓名", "借款人", "借款人姓名", "主借人", "借据人", "债务人编号", "客户编号", "借款人编号", "资产编号", "案件编号", "借据编号", "账户编号"],
    "id_card": ["身份证", "身份证号", "身份证号码", "证件号码", "证件号", "证件编号", "身份证件号"],
    "phone": ["手机号", "手机号码", "联系电话", "联系方式", "电话", "移动电话", "借款人电话"],
    "address": ["地址", "户籍地址", "居住地址", "通讯地址", "联系地址", "家庭住址", "现住址"],
    "principal": ["本金", "本金余额", "未偿本金", "剩余本金", "债权本金", "贷款本金", "逾期本金", "本金合计"],
    "interest": ["利息", "欠息", "罚息", "利息余额", "逾期利息", "利罚息", "息费", "费用"],
    "overdue_days": ["逾期天数", "逾期日数", "逾期时间", "逾期"],
    "contract_no": ["合同编号", "合同号", "借款合同编号", "协议编号"],
    "jurisdiction_court": ["管辖法院", "约定管辖法院", "执行法院", "法院", "受理法院"],
    "remark": ["备注", "说明", "催收备注", "资产备注"],
}


@dataclass
class MappingChoice:
    source_column: str | None
    confidence: float
    needs_confirmation: bool


def normalize_header(value: str) -> str:
    return re.sub(r"[\s_()（）【】\\/\\-]+", "", str(value or "")).lower()


def _header_score(header: str, field: str) -> float:
    normalized = normalize_header(header)
    for alias in ALIASES[field]:
        candidate = normalize_header(alias)
        if normalized == candidate:
            return 0.92
        if candidate and candidate in normalized:
            return 0.78
    return 0.0


def _nonempty_ratio(values: list[Any]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if str(value or "").strip()) / len(values)


def _content_score(values: list[Any], field: str) -> float:
    nonempty = [str(v).strip() for v in values if str(v or "").strip()]
    if not nonempty:
        return 0.0
    if field == "id_card":
        return sum(1 for v in nonempty if re.fullmatch(r"\d{17}[\dXx]|\d{15}", re.sub(r"\s+", "", v))) / len(nonempty) * 0.35
    if field == "phone":
        return sum(1 for v in nonempty if re.fullmatch(r"1[3-9]\d{9}", re.sub(r"\D", "", v))) / len(nonempty) * 0.35
    if field in {"principal", "interest", "overdue_days"}:
        return sum(1 for v in nonempty if parse_number(v) is not None) / len(nonempty) * 0.30
    if field == "address":
        return sum(1 for v in nonempty if re.search(r"省|市|区|县|路|街道|小区|镇|村", v)) / len(nonempty) * 0.25
    if field == "jurisdiction_court":
        return sum(1 for v in nonempty if "法院" in v) / len(nonempty) * 0.30
    if field == "contract_no":
        return min(_nonempty_ratio(nonempty) * 0.15, 0.15)
    return min(_nonempty_ratio(nonempty) * 0.10, 0.10)


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("，", "").replace("￥", "").replace("元", "").replace("%", "")
    multiplier = 1.0
    if text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def preview_mapping(headers: list[str], rows: list[dict[str, Any]]) -> dict[str, dict]:
    used_columns: set[str] = set()
    mapping: dict[str, dict] = {}
    for field in STANDARD_FIELDS:
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
        if best_header and best_score >= 0.55:
            used_columns.add(best_header)
            mapping[field] = {
                "source_column": best_header,
                "confidence": round(best_score, 2),
                "needs_confirmation": best_score < 0.80,
                "label": FIELD_LABELS[field],
            }
        else:
            mapping[field] = {
                "source_column": None,
                "confidence": 0.0,
                "needs_confirmation": field == "principal",
                "label": FIELD_LABELS[field],
            }
    return mapping


def unmapped_columns(headers: list[str], mapping: dict[str, dict]) -> list[str]:
    mapped = {item["source_column"] for item in mapping.values() if item.get("source_column")}
    return [header for header in headers if header not in mapped]
