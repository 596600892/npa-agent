from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urljoin


PROVINCES = [
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
]


@dataclass
class ParsedNotice:
    title: str
    transferor: str | None
    asset_type: str
    debtor_count: int | None
    principal: float | None
    interest: float | None
    total_claim: float | None
    regions: list[str]
    dates: dict
    attachments: list[dict]
    confidence: str
    parsed: dict


def html_to_text(raw: str) -> tuple[str, list[dict]]:
    attachments = []
    for match in re.finditer(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", raw, re.I | re.S):
        label = clean_text(match.group(2))[:80] or "附件"
        attachments.append({"label": label, "url": html.unescape(match.group(1))})
    without_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "\n", without_scripts)
    return clean_text(html.unescape(text)), attachments


def clean_text(value: str) -> str:
    value = re.sub(r"&nbsp;", " ", value)
    value = re.sub(r"\r", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{2,}", "\n", value)
    return value.strip()


def normalize_attachment_urls(attachments: list[dict], base_url: str | None) -> list[dict]:
    if not base_url:
        return attachments
    normalized = []
    for item in attachments:
        normalized.append({**item, "url": urljoin(base_url, item.get("url", ""))})
    return normalized


def extract_title(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:12]:
        if len(line) >= 8 and any(token in line for token in ["公告", "转让", "资产包", "不良贷款"]):
            return line[:120]
    return (lines[0] if lines else "银登公告")[:120]


def extract_transferor(text: str) -> str | None:
    patterns = [
        r"(?:转让方|出让方|卖方|委托方)[:：\s]+([^\n，。,；;]{4,80})",
        r"([^\n，。,；;]{4,80}(?:银行|资产管理有限公司|信托有限公司|消费金融有限公司)).{0,8}(?:拟|将)?(?:转让|处置)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return clean_text(match.group(1))
    return None


def amount_to_yuan(raw: str, unit: str | None) -> float:
    amount = float(raw.replace(",", ""))
    unit = unit or "元"
    if "亿" in unit:
        return amount * 100000000
    if "万" in unit:
        return amount * 10000
    return amount


def extract_amount(text: str, labels: list[str]) -> float | None:
    joined = "|".join(re.escape(label) for label in labels)
    pattern = rf"(?:{joined})[^\d\-]{{0,16}}([0-9]+(?:,[0-9]{{3}})*(?:\.[0-9]+)?)(\s*(?:亿元|万元|元|亿|万))?"
    match = re.search(pattern, text)
    if match:
        return amount_to_yuan(match.group(1), match.group(2))
    return None


def extract_debtor_count(text: str) -> int | None:
    patterns = [
        r"(?:债务人|借款人|客户|户数)[^\d]{0,8}([0-9,]+)\s*(?:户|名|人)",
        r"([0-9,]+)\s*(?:户|名|人)(?:债务人|借款人|客户)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def extract_dates(text: str) -> dict:
    dates = {}
    first_date = re.search(r"(20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}日?)", text)
    if first_date:
        dates["announcement_date"] = first_date.group(1)
    for key, labels in {
        "registration_deadline": ["报名截止", "受让登记截止", "意向受让方登记截止"],
        "bidding_date": ["竞价时间", "拍卖时间", "挂牌截止", "报价时间"],
        "payment_deadline": ["保证金缴纳", "保证金到账", "付款截止"],
    }.items():
        pattern = rf"(?:{'|'.join(labels)}).*?(20\d{{2}}[年\-/.]\d{{1,2}}[月\-/.]\d{{1,2}}日?)"
        match = re.search(pattern, text)
        if match:
            dates[key] = match.group(1)
    return dates


def extract_regions(text: str) -> list[str]:
    return [province for province in PROVINCES if province in text]


def infer_asset_type(text: str) -> str:
    if "个人" in text or "消费" in text or "信用卡" in text:
        return "consumer_loan"
    if "企业" in text or "公司" in text or "对公" in text:
        return "corporate_loan"
    if "不良" in text:
        return "nonperforming_loan"
    return "unknown"


def confidence_for(parsed: dict) -> str:
    score = 0
    for key in ["title", "transferor", "principal", "debtor_count", "regions"]:
        if parsed.get(key):
            score += 1
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def parse_yindeng_notice(raw: str, source_url: str | None = None, content_type: str | None = None) -> ParsedNotice:
    if content_type and "html" in content_type.lower():
        text, attachments = html_to_text(raw)
    else:
        text, attachments = clean_text(raw), []
    attachments = normalize_attachment_urls(attachments, source_url)
    title = extract_title(text)
    principal = extract_amount(text, ["本金", "本金余额", "未偿本金", "债权本金"])
    interest = extract_amount(text, ["利息", "欠息", "利息余额"])
    total_claim = extract_amount(text, ["债权总额", "本息合计", "债权余额", "资产总额", "未偿本息"])
    if total_claim is None and principal is not None and interest is not None:
        total_claim = principal + interest
    fields = {
        "title": title,
        "transferor": extract_transferor(text),
        "asset_type": infer_asset_type(text),
        "debtor_count": extract_debtor_count(text),
        "principal": principal,
        "interest": interest,
        "total_claim": total_claim,
        "regions": extract_regions(text),
        "dates": extract_dates(text),
        "attachments": attachments,
    }
    parsed = {
        **fields,
        "text_preview": text[:1200],
        "parser_version": "0.1",
    }
    return ParsedNotice(confidence=confidence_for(fields), parsed=parsed, **fields)
