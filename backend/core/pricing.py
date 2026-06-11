from __future__ import annotations


def pricing_scenarios(quality: dict, profile: dict, calibration: dict | None = None, legal_risk: dict | None = None) -> dict:
    score = quality["score"]
    phone = quality["coverage"]["phone"]
    court = quality["coverage"]["court_or_contract"]
    modifier = 0.0
    if phone >= 0.8:
        modifier += 0.01
    if court >= 0.6:
        modifier += 0.005
    if score < 50:
        modifier -= 0.01
    if score >= 80:
        modifier += 0.005
    if calibration:
        modifier += calibration.get("adjustment", 0.0)
    legal_adjustment = 0.0
    legal_reasons: list[str] = []
    if legal_risk:
        strategy_impacts = legal_risk.get("strategy_impacts", {})
        if legal_risk.get("overall_risk") == "high":
            legal_adjustment = -0.01
            legal_reasons.append("合同/文书整体风险为高，报价区间小幅下修。")
        elif legal_risk.get("overall_risk") == "medium":
            legal_adjustment = -0.005
            legal_reasons.append("合同/文书整体风险为中，报价区间谨慎下修。")
        else:
            legal_reasons.append("合同/文书风险线索相对可控，报价不做额外下修。")
        if strategy_impacts.get("pricing_direction") == "down":
            legal_adjustment -= 0.005
            legal_reasons.append("文书策略影响提示下修，例如终本、无财产或核心请求风险。")
        elif strategy_impacts.get("pricing_direction") == "up_with_review" and legal_risk.get("confidence") != "low":
            legal_adjustment += 0.003
            legal_reasons.append("识别到判决/执行等确认债权线索，报价可信度可小幅上调但需人工复核。")
        if legal_risk.get("confidence") == "low":
            legal_reasons.append("合同文本质量或识别可信度偏低，法律风险修正仅作提示。")
    modifier += legal_adjustment

    def _range(low: float, high: float) -> str:
        return f"{max(0.0, low + modifier):.1%}-{max(0.0, high + modifier):.1%}"

    return {
        "disclaimer": "报价为模型假设下的初筛区间，不构成投资建议。实际报价需结合合同、债权真实性、诉讼时效、历史回款和外部尽调结果复核。",
        "calibration": calibration or {
            "matched_count": 0,
            "usable_recovery_count": 0,
            "average_recovery_rate": None,
            "average_recovery_months": None,
            "matched_records": [],
            "court_profiles": [],
            "adjustment": 0.0,
            "confidence": "none",
            "reasons": ["未导入公司历史处置数据，报价仍以规则区间为主。"],
        },
        "legal_adjustment": {
            "adjustment": legal_adjustment,
            "overall_risk": legal_risk.get("overall_risk") if legal_risk else "not_analyzed",
            "confidence": legal_risk.get("confidence") if legal_risk else "none",
            "reasons": legal_reasons or ["未上传或未分析合同/文书，报价未应用法律风险修正。"],
        },
        "scenarios": {
            "conservative": {"name": "保守", "expected_recovery_rate": _range(0.03, 0.06), "cycle_months": "18-36", "suggested_bid_rate": _range(0.01, 0.03)},
            "base": {"name": "基准", "expected_recovery_rate": _range(0.06, 0.12), "cycle_months": "12-24", "suggested_bid_rate": _range(0.03, 0.06)},
            "optimistic": {"name": "乐观", "expected_recovery_rate": _range(0.12, 0.20), "cycle_months": "6-18", "suggested_bid_rate": _range(0.06, 0.10)},
        },
    }
