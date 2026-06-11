from __future__ import annotations

import re
from collections import Counter


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "unknown": 1}


def analyze_contract_risk(text: str, metadata: dict | None = None) -> dict:
    metadata = metadata or {}
    clean_text = _compact(text)
    sections = {
        "jurisdiction": _analyze_jurisdiction(clean_text),
        "service_clause": _analyze_service_clause(clean_text),
        "assignment_notice": _analyze_assignment_notice(clean_text),
        "limitation_period": _analyze_limitation_period(clean_text),
        "evidence_chain": _analyze_evidence_chain(clean_text),
        "interest_fee": _analyze_interest_fee(clean_text),
    }
    overall = _overall_risk(sections)
    confidence = _confidence(clean_text, sections, metadata)
    return {
        "analyzer_version": "contract_risk_analyzer_v0.1",
        "overall_risk": overall,
        "confidence": confidence,
        "text_quality": metadata.get("text_quality") or _text_quality(clean_text),
        "document_id": metadata.get("document_id"),
        "filename": metadata.get("filename"),
        "parser_version": metadata.get("parser_version"),
        "warnings": metadata.get("warnings", []),
        "extracted": {
            "jurisdiction_courts": sections["jurisdiction"].get("courts", []),
            "arbitration_bodies": sections["jurisdiction"].get("arbitration_bodies", []),
            "dates": sections["limitation_period"].get("dates", []),
        },
        "risks": sections,
        "next_actions": _next_actions(sections, metadata),
    }


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _text_quality(text: str) -> str:
    if not text:
        return "empty"
    if len(text) < 100:
        return "low"
    if len(text) < 1000:
        return "medium"
    return "high"


def _snippet(text: str, pattern: str, window: int = 46) -> str | None:
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    return text[start:end].strip()


def _snippets(text: str, patterns: list[str], limit: int = 3) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        value = _snippet(text, pattern)
        if value and value not in found:
            found.append(value)
        if len(found) >= limit:
            break
    return found


def _analyze_jurisdiction(text: str) -> dict:
    court_pattern = r"([\u4e00-\u9fa5]{2,30}(?:人民法院|法院))"
    arbitration_pattern = r"([\u4e00-\u9fa5]{2,30}(?:仲裁委员会|仲裁院|仲裁中心))"
    courts = _unique(re.findall(court_pattern, text))
    arbitration_bodies = _unique(re.findall(arbitration_pattern, text))
    has_jurisdiction_terms = bool(re.search(r"管辖|争议解决|诉讼|起诉|法院|仲裁", text))
    is_fixed = len(courts) == 1 or len(arbitration_bodies) == 1
    is_conflicted = bool(courts and arbitration_bodies)
    if is_conflicted:
        risk = "medium"
        conclusion = "同时出现法院管辖和仲裁线索，需要人工核对争议解决条款是否冲突。"
    elif is_fixed:
        risk = "low"
        conclusion = "已识别相对明确的管辖/仲裁线索，可进一步评估批量处置便利度。"
    elif has_jurisdiction_terms:
        risk = "medium"
        conclusion = "出现争议解决相关表述，但未识别明确法院或仲裁机构。"
    else:
        risk = "high"
        conclusion = "未识别明确管辖或仲裁约定，诉讼路径和成本存在不确定性。"
    return {
        "label": "管辖/仲裁",
        "risk": risk,
        "confidence": "high" if courts or arbitration_bodies else "medium",
        "conclusion": conclusion,
        "courts": courts,
        "arbitration_bodies": arbitration_bodies,
        "is_fixed": is_fixed,
        "evidence_snippets": _snippets(text, [court_pattern, arbitration_pattern, r"管辖|争议解决|仲裁"]),
    }


def _analyze_service_clause(text: str) -> dict:
    patterns = [r"送达地址", r"电子送达", r"短信送达", r"邮箱送达", r"视为送达", r"公告送达", r"通讯地址"]
    snippets = _snippets(text, patterns)
    if snippets:
        risk = "low"
        conclusion = "已识别送达条款线索，有助于后续诉讼材料和送达路径判断。"
    else:
        risk = "medium"
        conclusion = "未识别送达条款，后续诉讼可能需要补充地址确认或送达证据。"
    return {
        "label": "送达条款",
        "risk": risk,
        "confidence": "high" if snippets else "medium",
        "conclusion": conclusion,
        "evidence_snippets": snippets,
    }


def _analyze_assignment_notice(text: str) -> dict:
    transfer_patterns = [r"债权转让", r"债权受让", r"转让通知", r"通知债务人", r"受让方", r"资产转让"]
    snippets = _snippets(text, transfer_patterns)
    if snippets:
        risk = "low"
        conclusion = "已识别债权转让/通知相关线索，仍需核对通知方式和留痕。"
    else:
        risk = "medium"
        conclusion = "未识别债权转让通知线索，收购后需重点核对债转通知材料。"
    return {
        "label": "债权转让通知",
        "risk": risk,
        "confidence": "high" if snippets else "medium",
        "conclusion": conclusion,
        "evidence_snippets": snippets,
    }


def _analyze_limitation_period(text: str) -> dict:
    date_pattern = r"(20\d{2}|19\d{2})[年\-/\.](0?[1-9]|1[0-2])[月\-/\.](0?[1-9]|[12]\d|3[01])日?"
    dates = ["-".join(match) for match in re.findall(date_pattern, text)]
    terms = _snippets(text, [r"借款期限", r"到期日", r"还款日", r"逾期", r"催收", r"确认债务", r"诉讼时效", r"重新确认"])
    if len(dates) >= 2 and terms:
        risk = "low"
        conclusion = "已识别日期和时效相关线索，可据此进一步核算诉讼时效。"
    elif dates or terms:
        risk = "medium"
        conclusion = "识别到部分日期或时效线索，但不足以自动判断是否临近或超过时效。"
    else:
        risk = "high"
        conclusion = "未识别借款、到期、逾期或催收确认线索，诉讼时效需补充材料核验。"
    return {
        "label": "诉讼时效线索",
        "risk": risk,
        "confidence": "medium" if dates or terms else "low",
        "conclusion": conclusion,
        "dates": dates[:10],
        "evidence_snippets": terms[:3],
    }


def _analyze_evidence_chain(text: str) -> dict:
    items = {
        "合同": r"借款合同|贷款合同|授信合同|合同编号",
        "放款凭证": r"放款凭证|转账凭证|支付凭证|借款发放|放款日",
        "还款记录": r"还款记录|还款流水|扣款记录|还款计划|已还",
        "逾期/催收": r"逾期|催收|还款提醒|到期未还",
        "债转通知": r"债权转让|转让通知|通知债务人",
        "担保材料": r"保证合同|保证人|抵押|质押|担保",
    }
    present = [label for label, pattern in items.items() if re.search(pattern, text)]
    missing_core = [label for label in ["合同", "放款凭证", "还款记录"] if label not in present]
    if len(present) >= 4 and not missing_core:
        risk = "low"
        conclusion = "证据链线索较完整，仍需核对原件和附件一致性。"
    elif present:
        risk = "medium"
        conclusion = "识别到部分证据材料线索，但核心材料仍需补齐或人工核验。"
    else:
        risk = "high"
        conclusion = "未识别核心证据链线索，债权真实性和诉讼材料完整性风险较高。"
    return {
        "label": "证据链",
        "risk": risk,
        "confidence": "high" if present else "medium",
        "conclusion": conclusion,
        "present_items": present,
        "missing_core_items": missing_core,
        "evidence_snippets": _snippets(text, list(items.values())),
    }


def _analyze_interest_fee(text: str) -> dict:
    patterns = [r"利率", r"罚息", r"复利", r"违约金", r"服务费", r"管理费", r"咨询费", r"年化"]
    snippets = _snippets(text, patterns)
    high_terms = bool(re.search(r"复利|砍头息|服务费|咨询费|管理费", text))
    if high_terms:
        risk = "medium"
        conclusion = "识别到复利或费用类条款，需复核息费计算口径和可支持范围。"
    elif snippets:
        risk = "low"
        conclusion = "已识别息费条款线索，建议后续结合还款流水复算本息。"
    else:
        risk = "medium"
        conclusion = "未识别明确息费条款，报价和诉讼请求金额需谨慎。"
    return {
        "label": "利息/罚息/费用",
        "risk": risk,
        "confidence": "high" if snippets else "medium",
        "conclusion": conclusion,
        "evidence_snippets": snippets,
    }


def _overall_risk(sections: dict[str, dict]) -> str:
    risks = [item["risk"] for item in sections.values()]
    counts = Counter(risks)
    if counts["high"] >= 2:
        return "high"
    if counts["high"] == 1 or counts["medium"] >= 3:
        return "medium"
    return "low"


def _confidence(text: str, sections: dict[str, dict], metadata: dict) -> str:
    if metadata.get("text_quality") in {"empty", "needs_ocr"} or not text:
        return "low"
    high_count = sum(1 for item in sections.values() if item.get("confidence") == "high")
    if len(text) > 500 and high_count >= 4:
        return "high"
    if len(text) > 100 and high_count >= 2:
        return "medium"
    return "low"


def _next_actions(sections: dict[str, dict], metadata: dict) -> list[str]:
    actions: list[str] = []
    warnings = set(metadata.get("warnings", []))
    if "needs_ocr" in warnings or metadata.get("text_quality") == "empty":
        actions.append("上传可复制文字版合同，或先对扫描件做 OCR。")
    if sections["jurisdiction"]["risk"] != "low":
        actions.append("补充争议解决条款截图，确认法院管辖或仲裁机构。")
    if sections["limitation_period"]["risk"] != "low":
        actions.append("补充借款日、到期日、逾期日、催收确认或还款承诺材料。")
    if sections["evidence_chain"]["risk"] != "low":
        actions.append("补充放款凭证、还款流水、债权转让通知等证据链材料。")
    if sections["assignment_notice"]["risk"] != "low":
        actions.append("核对债权转让通知方式、送达对象和留痕。")
    return actions[:5] or ["合同风险线索较完整，建议律师抽样复核条款和证据原件。"]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = value.strip(" ，。；;:：")
        markers = ["本合同争议由", "争议由", "提交", "由", "向", "至", "约定"]
        positions = [(cleaned.rfind(marker), marker) for marker in markers if cleaned.rfind(marker) >= 0]
        if positions:
            index, marker = max(positions, key=lambda item: item[0])
            cleaned = cleaned[index + len(marker) :]
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result[:10]
