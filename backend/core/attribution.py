from __future__ import annotations


def build_attributions(quality: dict, profile: dict, disposition: dict, legal_risk: dict | None = None) -> list[dict]:
    items = [
        {"claim": f"本金合计 {profile['basic']['principal_total']:,.2f} 元", "source_type": "excel", "source_detail": "Excel 本金字段", "confidence": "high"},
        {"claim": f"手机号覆盖率 {quality['coverage']['phone']:.1%}", "source_type": "excel", "source_detail": "Excel 手机号字段", "confidence": "high"},
        {"claim": f"数据完整度 {quality['score']}/100", "source_type": "rule_calculation", "source_detail": "PRD V0.1 数据完整度权重", "confidence": "high"},
        {"claim": f"推荐处置模式：{disposition['primary_strategy']}", "source_type": "model_inference", "source_detail": "手机号覆盖率、户均本金、法院集中度规则推断", "confidence": "medium"},
        {"claim": "报价区间以初筛规则为基线", "source_type": "model_inference", "source_detail": "MVP 三情景报价规则；如有历史样本则另行校准", "confidence": "low"},
    ]
    if legal_risk:
        items.append(
            {
                "claim": f"合同/文书整体风险：{legal_risk.get('overall_risk')}",
                "source_type": "legal_document",
                "source_detail": f"{legal_risk.get('filename') or '合同/文书'}；解析方式：本地规则；文本质量：{legal_risk.get('text_quality')}",
                "confidence": legal_risk.get("confidence", "low"),
            }
        )
    else:
        items.append({"claim": "合同/文书风险未分析", "source_type": "missing_input", "source_detail": "未上传或未分析合同/条款文件", "confidence": "none"})
    return items
