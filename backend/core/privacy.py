from __future__ import annotations

import re


def mask_name(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.match(r"^[A-Za-z0-9_-]+$", text):
        return text
    if len(text) == 1:
        return "*"
    return f"{text[0]}*"


def mask_id_card(value: str | None) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    if len(text) < 8:
        return text
    return f"{text[:6]}{'*' * max(0, len(text) - 10)}{text[-4:]}"


def mask_phone(value: str | None) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) != 11:
        return text
    return f"{text[:3]}****{text[-4:]}"


def mask_address(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return f"{text[:3]}***"
    return f"{text[:10]}***"


def redact_text(text: str) -> str:
    redacted = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", lambda m: mask_id_card(m.group(0)), text)
    redacted = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", lambda m: mask_phone(m.group(0)), redacted)
    redacted = re.sub(
        r"[\u4e00-\u9fa5]{2,}(?:省|自治区|市|区|县)[\u4e00-\u9fa5A-Za-z0-9号栋室路街道镇乡村弄巷单元座园小区-]{4,}",
        lambda m: m.group(0) if re.search(r"(法院|法庭|仲裁|公证处|委员会|中心|银行|公司)", m.group(0)) else mask_address(m.group(0)),
        redacted,
    )
    return redacted
