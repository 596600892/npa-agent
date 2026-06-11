from __future__ import annotations

from .privacy import redact_text


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _rating(score: int) -> str:
    if score >= 85:
        return "B"
    if score >= 65:
        return "B-"
    if score >= 40:
        return "C"
    return "C-"


def _maybe_percent(value: float | None) -> str:
    return "样本不足" if value is None else _percent(value)


def _maybe_number(value: float | None, suffix: str = "") -> str:
    return "样本不足" if value is None else f"{value:.1f}{suffix}"


def _risk_label(value: str | None) -> str:
    return {"low": "低", "medium": "中", "high": "高", "unknown": "未知", "not_analyzed": "未分析"}.get(value or "", value or "未分析")


def _document_type_label(value: str | None) -> str:
    return {
        "contract": "合同/条款",
        "judgment": "判决书",
        "enforcement": "执行文书",
        "mediation": "调解文书",
        "unknown": "未识别",
    }.get(value or "unknown", value or "未识别")


def _dimension_labels(values: list[str] | None) -> str:
    labels = {
        "asset_type": "资产类型",
        "court": "法院",
        "region": "地区",
        "amount_bucket": "金额段",
        "disposal_method": "处置方式",
    }
    if not values:
        return "-"
    return "、".join(labels.get(value, value) for value in values)


def _breakdown_table(title: str, rows: list[dict]) -> list[str]:
    lines = [f"**{title}**", "", "| 维度值 | 样本数 | 可算回收率 | 平均回收率 | 平均周期 |", "|---|---:|---:|---:|---:|"]
    if not rows:
        lines.append("| 无匹配 | 0 | 0 | 样本不足 | 样本不足 |")
        return lines
    for item in rows[:6]:
        lines.append(f"| {item.get('key') or '-'} | {item.get('sample_count', 0)} | {item.get('usable_recovery_count', 0)} | {_maybe_percent(item.get('average_recovery_rate'))} | {_maybe_number(item.get('average_recovery_months'), ' 月')} |")
    return lines


def write_report(
    project: dict,
    quality: dict,
    profile: dict,
    disposition: dict,
    pricing: dict,
    attributions: list[dict],
    legal_risk: dict | None = None,
    execution_summary: dict | None = None,
) -> dict:
    basic = profile["basic"]
    rating = _rating(quality["score"])
    recommendation = "进入初步尽调" if quality["score"] >= 60 else "先补充关键字段后再报价"
    lines: list[str] = []
    lines.append(f"# {project['name']} 初筛报告")
    lines.append("")
    lines.append("> 本报告由 NPA Agent MVP 本地规则引擎生成；不构成投资建议或法律意见。")
    lines.append("")
    lines.append("## 一、结论摘要")
    lines.append("")
    lines.append(f"**推荐等级：{rating}**")
    lines.append("")
    lines.append(f"**建议动作：{recommendation}。主路径为 {disposition['primary_strategy']}。**")
    lines.append("")
    lines.append("核心机会：")
    lines.append(f"1. 本金合计 {_money(basic['principal_total'])} 元，户均本金 {_money(basic['average_principal'])} 元。")
    lines.append(f"2. 手机号覆盖率 {_percent(quality['coverage']['phone'])}，可作为电话调解可行性基础。")
    if quality["coverage"]["court_or_contract"] >= 0.5:
        lines.append("3. 已识别合同/法院字段，可做初步管辖集中度分析。")
    else:
        lines.append("3. 当前可先做金额、触达和人群画像初筛。")
    lines.append("")
    lines.append("核心风险：")
    for idx, missing in enumerate(quality["missing_inputs"][:3], start=1):
        lines.append(f"{idx}. 缺少或覆盖不足：{missing['field']}，{missing['impact']}。")
    if not quality["missing_inputs"]:
        lines.append("1. 当前基础字段较完整，但仍需合同原文和公司历史数据复核。")
    lines.append("")
    lines.append("## 二、资产包基础情况")
    lines.append("")
    lines.append("| 指标 | 数值 | 来源 | 可信度 |")
    lines.append("|---|---:|---|---|")
    lines.append(f"| 户数 | {basic['account_count']} 户 | Excel 行数据 | 高 |")
    lines.append(f"| 本金合计 | {_money(basic['principal_total'])} 元 | Excel 本金字段 | 高 |")
    lines.append(f"| 利息合计 | {_money(basic['interest_total'])} 元 | Excel 利息字段 | 高 |")
    lines.append(f"| 本息合计 | {_money(basic['total_claim'])} 元 | 本金 + 利息计算 | 高 |")
    lines.append(f"| 户均本金 | {_money(basic['average_principal'])} 元 | 规则计算 | 高 |")
    lines.append(f"| 中位数本金 | {_money(basic['median_principal'])} 元 | 规则计算 | 高 |")
    lines.append("")
    lines.append("金额分布：")
    lines.append("")
    lines.append("| 金额区间 | 户数 | 占比 |")
    lines.append("|---|---:|---:|")
    for item in profile["amount_distribution"]:
        lines.append(f"| {item['band']} | {item['count']} | {_percent(item['ratio'])} |")
    lines.append("")
    lines.append("## 三、数据完整度")
    lines.append("")
    lines.append(f"**数据完整度：{quality['score']}/100**")
    lines.append(f"**当前等级：{quality['level']}**")
    lines.append("")
    lines.append("| 字段 | 覆盖率 |")
    lines.append("|---|---:|")
    for key, label in [("principal", "本金"), ("debtor_identifier", "债务人名称/编号"), ("id_card", "身份证"), ("phone", "手机号"), ("address", "地址"), ("interest", "利息"), ("court_or_contract", "合同/法院")]:
        lines.append(f"| {label} | {_percent(quality['coverage'][key])} |")
    lines.append("")
    lines.append("## 四、债务人画像")
    lines.append("")
    lines.append("年龄结构：")
    for item in profile["age_distribution"]:
        lines.append(f"- {item['band']}：{item['count']} 户，占 {_percent(item['ratio'])}。")
    lines.append("")
    lines.append("地区线索：")
    for item in profile["region_distribution"][:6]:
        lines.append(f"- {item['region']}：{item['count']} 户，占 {_percent(item['ratio'])}。")
    lines.append("")
    lines.append("## 五、处置模式建议")
    lines.append("")
    lines.append(f"推荐主路径：`{disposition['primary_strategy']}`")
    lines.append("")
    for reason in disposition["reasons"]:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("| 层级 | 户数 | 建议 |")
    lines.append("|---|---:|---|")
    tier_labels = {"A": "电话调解优先", "B": "重点户攻坚", "C": "批量触达/分包", "D": "补充信息"}
    for tier, items in disposition["tiers"].items():
        lines.append(f"| {tier} 类 | {len(items)} | {tier_labels[tier]} |")
    lines.append("")
    lines.append("处置执行计划：")
    if execution_summary:
        lines.append(f"- 已生成执行任务 {execution_summary.get('task_count', 0)} 户，覆盖 {execution_summary.get('batch_count', 0)} 个批次。")
        lines.append(f"- 首轮电话调解 {execution_summary.get('first_round_count', 0)} 户，高优先级 {execution_summary.get('high_priority_count', 0)} 户。")
        lines.append(f"- 需补线索 {execution_summary.get('missing_signal_count', 0)} 户，诉讼评估候选 {execution_summary.get('litigation_candidate_count', 0)} 户。")
    else:
        lines.append("- 尚未生成执行计划；完成初筛后可在执行工作台一键生成批次、话术和跟进清单。")
    lines.append("")
    lines.append("电话调解第一轮话术：")
    lines.append("")
    lines.append(f"> {disposition['script']['first_contact']}")
    lines.append("")
    lines.append("合规禁区：")
    for item in disposition["compliance_forbidden"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 六、法院/管辖分析")
    lines.append("")
    lines.append("| 法院 | 户数 | 占比 |")
    lines.append("|---|---:|---:|")
    for item in profile["court_distribution"][:8]:
        lines.append(f"| {item['court']} | {item['count']} | {_percent(item['ratio'])} |")
    lines.append("")
    lines.append("## 七、合同/文书风险")
    lines.append("")
    if legal_risk:
        lines.append(f"**整体风险：{_risk_label(legal_risk.get('overall_risk'))}；可信度：{legal_risk.get('confidence', 'low')}；文本质量：{legal_risk.get('text_quality', 'unknown')}。**")
        lines.append("")
        lines.append(f"来源文件：{legal_risk.get('filename') or '合同/文书'}")
        lines.append(f"文书类型：{_document_type_label(legal_risk.get('document_type'))}")
        lines.append(f"解析方式：{legal_risk.get('extraction_method', 'unknown')}；OCR 状态：{legal_risk.get('ocr_status', 'not_needed')}；使用页码：{', '.join(str(item) for item in legal_risk.get('pages_used', [])) or '未记录'}。")
        warnings = "、".join(legal_risk.get("warnings", [])) or "无"
        lines.append(f"解析提示：{warnings}")
        lines.append("")
        field_sources = legal_risk.get("field_sources", {})
        if field_sources:
            lines.append("字段来源：")
            for field, source in list(field_sources.items())[:6]:
                if isinstance(source, dict):
                    lines.append(f"- {field}：{source.get('source', '-')}; 可信度 {source.get('confidence', '-')}")
                else:
                    lines.append(f"- {field}：{source}")
            lines.append("")
        lines.append("合同/条款风险：")
        lines.append("")
        lines.append("| 风险项 | 风险等级 | 结论 | 证据片段 |")
        lines.append("|---|---|---|---|")
        for key in ["jurisdiction", "service_clause", "assignment_notice", "limitation_period", "evidence_chain", "interest_fee"]:
            item = legal_risk.get("risks", {}).get(key, {})
            snippets = "；".join(item.get("evidence_snippets", [])[:2]) or "-"
            lines.append(f"| {item.get('label', key)} | {_risk_label(item.get('risk'))} | {item.get('conclusion', '-')} | {snippets} |")
        extracted = legal_risk.get("extracted", {})
        courts = "、".join(extracted.get("jurisdiction_courts", [])) or "未识别"
        arbitration = "、".join(extracted.get("arbitration_bodies", [])) or "未识别"
        dates = "、".join(extracted.get("dates", [])[:6]) or "未识别"
        lines.append("")
        lines.append(f"- 管辖法院：{courts}。")
        lines.append(f"- 仲裁机构：{arbitration}。")
        lines.append(f"- 日期线索：{dates}。")
        judicial = legal_risk.get("judicial_analysis") or {}
        if judicial:
            lines.append("")
            lines.append("判决/执行/调解文书线索：")
            points = "；".join(judicial.get("adjudication_points", [])[:2]) or "未识别"
            statuses = "；".join(judicial.get("execution_statuses", [])[:2]) or "未识别"
            terms = "；".join(judicial.get("mediation_terms", [])[:2]) or "未识别"
            amounts = "、".join(judicial.get("amounts", [])[:6]) or "未识别"
            lines.append(f"- 裁判要点：{points}。")
            lines.append(f"- 执行状态：{statuses}。")
            lines.append(f"- 调解履行：{terms}。")
            lines.append(f"- 金额线索：{amounts}。")
        impacts = legal_risk.get("strategy_impacts", {})
        if impacts:
            lines.append("")
            lines.append("文书对策略的影响：")
            lines.append(f"- 报价方向：{impacts.get('pricing_direction', 'neutral')}。")
            lines.append(f"- 执行分流：{impacts.get('execution_route') or '未触发专项分流'}。")
            for impact in impacts.get("impacts", [])[:3]:
                lines.append(f"- {impact}")
        lines.append("")
        lines.append("合同/文书下一步：")
        for action in legal_risk.get("next_actions", [])[:5]:
            lines.append(f"- {action}")
    else:
        lines.append("尚未上传或分析合同/条款文件；当前报告只基于 Excel、历史数据和规则引擎生成。")
        lines.append("")
        lines.append("- 建议补充可复制文字版合同、争议解决条款、债权转让通知和放款/还款证据。")
        lines.append("- 补充后可重新生成报告，系统会把法律风险并入报价和下一步动作。")
    lines.append("")
    lines.append("## 八、报价建议")
    lines.append("")
    lines.append("| 情景 | 预计回收率 | 周期 | 建议报价率 |")
    lines.append("|---|---:|---|---:|")
    for scenario in pricing["scenarios"].values():
        lines.append(f"| {scenario['name']} | {scenario['expected_recovery_rate']} | {scenario['cycle_months']} 个月 | {scenario['suggested_bid_rate']} |")
    lines.append("")
    lines.append(pricing["disclaimer"])
    lines.append("")
    legal_adjustment = pricing.get("legal_adjustment", {})
    lines.append("法律风险修正：")
    lines.append(f"- 风险等级：{_risk_label(legal_adjustment.get('overall_risk'))}；修正幅度：{legal_adjustment.get('adjustment', 0.0):+.1%}；可信度：{legal_adjustment.get('confidence', 'none')}。")
    for reason in legal_adjustment.get("reasons", []):
        lines.append(f"- {reason}")
    lines.append("")
    calibration = pricing.get("calibration", {})
    lines.append("## 九、公司历史校准")
    lines.append("")
    sample_confidence = calibration.get("sample_confidence", calibration.get("confidence", "none"))
    context = calibration.get("project_context", {})
    lines.append(f"**匹配历史样本：{calibration.get('matched_count', 0)} 条；可计算回收率样本：{calibration.get('usable_recovery_count', 0)} 条；样本可信度：{sample_confidence}。**")
    lines.append("")
    lines.append(f"- 当前资产包金额段：{context.get('amount_bucket', 'unknown')}；户均本金：{_maybe_number(context.get('average_principal'), ' 元')}。")
    if context.get("courts"):
        lines.append(f"- 当前法院线索：{'、'.join(context.get('courts', []))}。")
    if context.get("regions"):
        lines.append(f"- 当前地区线索：{'、'.join(context.get('regions', []))}。")
    lines.append(f"- 匹配历史平均回收率：{_maybe_percent(calibration.get('average_recovery_rate'))}。")
    lines.append(f"- 匹配历史平均回款周期：{_maybe_number(calibration.get('average_recovery_months'), ' 个月')}。")
    lines.append(f"- 报价区间修正：{calibration.get('adjustment', 0.0):+.1%}。")
    for reason in calibration.get("reasons", []):
        lines.append(f"- {reason}")
    if calibration.get("matched_records"):
        lines.append("")
        lines.append("**匹配维度解释**")
        lines.append("")
        lines.append("| 历史项目 | 法院 | 地区 | 金额段 | 命中维度 | 缺失/未命中 | 回收率 | 匹配分 |")
        lines.append("|---|---|---|---|---|---|---:|---:|")
        for item in calibration["matched_records"][:6]:
            lines.append(f"| {item.get('project_name') or '-'} | {item.get('court_name') or '-'} | {item.get('region') or '-'} | {item.get('amount_bucket') or '-'} | {_dimension_labels(item.get('matched_dimensions'))} | {_dimension_labels(item.get('missing_dimensions'))} | {_maybe_percent(item.get('recovery_rate'))} | {item.get('match_score', 0)} |")
        lines.append("")
        lines.append("分维度对比：")
        breakdown = calibration.get("breakdown", {})
        lines.extend(_breakdown_table("按法院", breakdown.get("by_court", [])))
        lines.append("")
        lines.extend(_breakdown_table("按地区", breakdown.get("by_region", [])))
        lines.append("")
        lines.extend(_breakdown_table("按金额段", breakdown.get("by_amount_bucket", [])))
        lines.append("")
        lines.extend(_breakdown_table("按处置方式", breakdown.get("by_disposal_method", [])))
    else:
        lines.append("")
        lines.append("匹配维度解释：暂无命中历史样本，规则报价为主，历史仅作参考。")
    lines.append("")
    lines.append("## 十、法院画像")
    lines.append("")
    if calibration.get("court_profiles"):
        lines.append("| 法院 | 标签 | 样本数 | 平均回收率 | 平均周期 | 常见失败原因 |")
        lines.append("|---|---|---:|---:|---:|---|")
        for item in calibration["court_profiles"][:8]:
            failures = "、".join(item.get("common_failure_reasons", [])) or "-"
            lines.append(f"| {item['court_name']} | {item['label']} | {item['sample_count']} | {_maybe_percent(item.get('average_recovery_rate'))} | {_maybe_number(item.get('average_recovery_months'), ' 月')} | {failures} |")
    else:
        lines.append("当前项目未匹配到已沉淀的法院画像；建议上传同地区或同法院历史处置数据。")
    lines.append("")
    lines.append("## 十一、数据来源说明")
    lines.append("")
    lines.append("| 结论 | 来源 | 可信度 |")
    lines.append("|---|---|---|")
    for item in attributions:
        lines.append(f"| {item['claim']} | {item['source_detail']} | {item['confidence']} |")
    lines.append(f"| 报价校准 | 公司历史处置数据匹配 {calibration.get('matched_count', 0)} 条，修正 {calibration.get('adjustment', 0.0):+.1%} | {calibration.get('confidence', 'none')} |")
    lines.append("")
    lines.append("## 十二、下一步")
    lines.append("")
    next_actions = ["补充合同样本或管辖条款截图。", "上传公司历史个贷处置数据。", "对高金额户生成重点户清单。", "生成电话调解批次和话术。"]
    if legal_risk and legal_risk.get("next_actions"):
        next_actions = legal_risk["next_actions"][:2] + next_actions
    for idx, action in enumerate(next_actions, start=1):
        lines.append(f"{idx}. {action}")
    markdown = redact_text("\n".join(lines))
    return {
        "summary": {"rating": rating, "recommendation": recommendation, "primary_strategy": disposition["primary_strategy"]},
        "markdown": markdown,
    }
