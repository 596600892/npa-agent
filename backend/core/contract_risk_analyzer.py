from __future__ import annotations

import re
from collections import Counter


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "unknown": 1}


def analyze_contract_risk(text: str, metadata: dict | None = None) -> dict:
    metadata = metadata or {}
    clean_text = _compact(text)
    document_type = _detect_document_type(clean_text, metadata.get("filename", ""))
    judicial_analysis = _analyze_judicial_document(clean_text, document_type)
    sections = {
        "jurisdiction": _analyze_jurisdiction(clean_text),
        "service_clause": _analyze_service_clause(clean_text),
        "assignment_notice": _analyze_assignment_notice(clean_text),
        "limitation_period": _analyze_limitation_period(clean_text),
        "evidence_chain": _analyze_evidence_chain(clean_text),
        "interest_fee": _analyze_interest_fee(clean_text),
    }
    if judicial_analysis:
        sections["judicial_document"] = judicial_analysis["risk_section"]
    overall = _overall_risk(sections)
    confidence = _confidence(clean_text, sections, metadata)
    return {
        "analyzer_version": "contract_risk_analyzer_v0.3",
        "document_type": document_type,
        "overall_risk": overall,
        "confidence": confidence,
        "text_quality": metadata.get("text_quality") or _text_quality(clean_text),
        "document_id": metadata.get("document_id"),
        "filename": metadata.get("filename"),
        "parser_version": metadata.get("parser_version"),
        "warnings": metadata.get("warnings", []),
        "is_scanned_pdf": bool(metadata.get("is_scanned_pdf")),
        "extraction_method": metadata.get("extraction_method", "unknown"),
        "pages_used": metadata.get("pages_used", []),
        "ocr_status": metadata.get("ocr_status", "not_needed"),
        "ocr_confidence": metadata.get("ocr_confidence"),
        "attachments": metadata.get("attachments", []),
        "field_sources": metadata.get("field_sources", {}),
        "extracted": {
            "jurisdiction_courts": sections["jurisdiction"].get("courts", []),
            "arbitration_bodies": sections["jurisdiction"].get("arbitration_bodies", []),
            "dates": sections["limitation_period"].get("dates", []),
            "judicial_points": judicial_analysis.get("adjudication_points", []) if judicial_analysis else [],
            "execution_statuses": judicial_analysis.get("execution_statuses", []) if judicial_analysis else [],
            "mediation_terms": judicial_analysis.get("mediation_terms", []) if judicial_analysis else [],
            "legal_amounts": judicial_analysis.get("amounts", []) if judicial_analysis else [],
        },
        "judicial_analysis": judicial_analysis,
        "judicial_document_analysis": judicial_analysis,
        "strategy_impacts": _strategy_impacts(overall, confidence, document_type, judicial_analysis, metadata),
        "risks": sections,
        "next_actions": _next_actions(sections, metadata, document_type, judicial_analysis),
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


def _detect_document_type(text: str, filename: str = "") -> str:
    sample = f"{filename} {text[:1500]}"
    if re.search(r"民事判决书|刑事判决书|行政判决书|判决如下|本院认为|判决主文", sample):
        return "judgment"
    if re.search(r"执行裁定书|执行通知书|被执行人|申请执行人|终结本次执行|恢复执行|限制消费|纳入失信", sample):
        return "enforcement"
    if re.search(r"民事调解书|调解协议|经本院主持调解|分期履行|调解如下", sample):
        return "mediation"
    if re.search(r"借款合同|贷款合同|授信合同|保证合同|合同编号", sample):
        return "contract"
    return "unknown"


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


def _analyze_judicial_document(text: str, document_type: str) -> dict | None:
    if document_type not in {"judgment", "enforcement", "mediation"}:
        return None
    adjudication_points = _snippets(
        text,
        [
            r"本院认为.{0,120}",
            r"判决如下.{0,120}",
            r"判令.{0,120}",
            r"支持.{0,80}(?:本金|利息|违约金)",
            r"驳回.{0,80}(?:诉讼请求|其他请求)",
        ],
        limit=5,
    )
    execution_statuses = _snippets(
        text,
        [
            r"终结本次执行.{0,120}",
            r"恢复执行.{0,120}",
            r"未发现可供执行财产.{0,120}",
            r"限制消费.{0,100}",
            r"纳入失信.{0,100}",
            r"查封|冻结|扣划|拍卖|变卖",
        ],
        limit=5,
    )
    mediation_terms = _snippets(
        text,
        [
            r"分期.{0,120}",
            r"于20\d{2}.{0,80}(?:支付|偿还|给付)",
            r"调解协议.{0,120}",
            r"一次性.{0,80}(?:支付|结清)",
        ],
        limit=5,
    )
    amounts = _amount_snippets(text)
    if document_type == "judgment":
        risk = "low" if adjudication_points else "medium"
        conclusion = "已识别判决书裁判要点，可用于判断债权确认程度和诉讼请求支持情况。" if adjudication_points else "疑似判决书，但未识别清晰裁判主文，需要人工复核。"
    elif document_type == "enforcement":
        has_difficult = bool(execution_statuses and any("终结本次执行" in item or "未发现可供执行财产" in item for item in execution_statuses))
        risk = "high" if has_difficult else "medium"
        conclusion = "识别到终本或无财产线索，执行回收难度较高。" if has_difficult else "识别到执行文书线索，需进一步核对执行状态、财产线索和恢复执行可能。"
    else:
        risk = "medium" if mediation_terms else "low"
        conclusion = "已识别调解履行条款，建议跟踪履约期限和违约后处置路径。" if mediation_terms else "疑似调解文书，但未识别明确履行条款。"
    return {
        "document_type": document_type,
        "adjudication_points": adjudication_points,
        "execution_statuses": execution_statuses,
        "mediation_terms": mediation_terms,
        "amounts": amounts,
        "evidence_chain_suggestions": _judicial_evidence_suggestions(document_type, adjudication_points, execution_statuses, mediation_terms),
        "risk_section": {
            "label": "判决/执行/调解文书",
            "risk": risk,
            "confidence": "high" if adjudication_points or execution_statuses or mediation_terms else "medium",
            "conclusion": conclusion,
            "evidence_snippets": (adjudication_points + execution_statuses + mediation_terms)[:3],
        },
    }


def _amount_snippets(text: str) -> list[str]:
    pattern = r"(?<!\d)([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\s*(?:亿元|万元|元|亿|万))"
    return _unique(re.findall(pattern, text))[:8]


def _judicial_evidence_suggestions(document_type: str, adjudication_points: list[str], execution_statuses: list[str], mediation_terms: list[str]) -> list[str]:
    suggestions: list[str] = []
    if document_type == "judgment" and not adjudication_points:
        suggestions.append("补充判决主文、本院认为和生效证明。")
    if document_type == "enforcement":
        suggestions.append("补充执行裁定、财产查控反馈、终本裁定和恢复执行材料。")
        if not execution_statuses:
            suggestions.append("补充执行状态截图或执行法院反馈。")
    if document_type == "mediation":
        suggestions.append("补充调解协议、履行期限、付款凭证和违约条款。")
        if not mediation_terms:
            suggestions.append("核对调解金额、分期安排和违约后恢复执行路径。")
    return suggestions[:4]


def _strategy_impacts(overall: str, confidence: str, document_type: str, judicial_analysis: dict | None, metadata: dict) -> dict:
    impacts: list[str] = []
    execution_route = None
    pricing_direction = "neutral"
    if metadata.get("ocr_status") == "success":
        impacts.append("文书来自本地 OCR，关键金额、法院和日期需要人工抽样核对。")
    if confidence == "low":
        impacts.append("文本质量或识别可信度偏低，暂不建议据此大幅调整报价。")
    if document_type == "judgment" and judicial_analysis and judicial_analysis.get("adjudication_points"):
        pricing_direction = "up_with_review"
        execution_route = "litigation_or_enforcement_review"
        impacts.append("识别到判决主文线索，可提高债权确认程度判断，但需核对生效证明。")
    if document_type == "enforcement" and judicial_analysis:
        statuses = " ".join(judicial_analysis.get("execution_statuses", []))
        execution_route = "enforcement_recovery_or_asset_trace"
        if "终结本次执行" in statuses or "未发现可供执行财产" in statuses:
            pricing_direction = "down"
            impacts.append("识别到终本或无财产线索，报价和执行预期应谨慎下修。")
        else:
            impacts.append("识别到执行文书线索，建议进入恢复执行或财产线索补强。")
    if document_type == "mediation" and judicial_analysis and judicial_analysis.get("mediation_terms"):
        execution_route = "mediation_performance_check"
        impacts.append("识别到调解履行条款，建议优先核实履约期限、付款记录和违约后路径。")
    if overall == "high" and pricing_direction == "neutral":
        pricing_direction = "down"
        impacts.append("合同/文书整体风险较高，报价区间应谨慎。")
    return {
        "pricing_direction": pricing_direction,
        "execution_route": execution_route,
        "impacts": impacts or ["暂未识别足以改变处置策略的文书线索。"],
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


def _next_actions(sections: dict[str, dict], metadata: dict, document_type: str = "unknown", judicial_analysis: dict | None = None) -> list[str]:
    actions: list[str] = []
    warnings = set(metadata.get("warnings", []))
    if "ocr_applied" in warnings:
        actions.append("OCR 已提取扫描 PDF 文本，建议人工抽样核对关键金额、日期和法院名称。")
    elif "needs_ocr" in warnings or metadata.get("text_quality") == "empty":
        if "ocr_unavailable" in warnings:
            actions.append("当前环境未安装本地 OCR 依赖，请安装 pdf2image/pytesseract 或上传可复制文字版文件。")
        else:
            actions.append("上传可复制文字版合同，或先对扫描件做 OCR。")
    if document_type in {"judgment", "enforcement", "mediation"} and judicial_analysis:
        actions.extend(judicial_analysis.get("evidence_chain_suggestions", [])[:2])
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
