from __future__ import annotations


def select_disposition(accounts: list[dict], quality: dict, profile: dict) -> dict:
    coverage = quality["coverage"]
    basic = profile["basic"]
    account_count = basic["account_count"]
    avg_principal = basic["average_principal"]
    court_distribution = [item for item in profile["court_distribution"] if item["court"] != "未知"]
    top3_court_ratio = sum(item["ratio"] for item in court_distribution[:3])
    contract_coverage = sum(1 for account in accounts if account.get("optional", {}).get("contract_no")) / len(accounts) if accounts else 0
    reasons = []
    strategies = []

    phone_first = coverage["phone"] >= 0.60 and avg_principal <= 30000 and top3_court_ratio < 0.70
    litigation = coverage["court_or_contract"] >= 0.60 and top3_court_ratio >= 0.70 and avg_principal >= 30000 and contract_coverage >= 0.50
    outsource = account_count >= 500 and avg_principal <= 20000 and 0.30 <= coverage["phone"] <= 0.60
    cautious = quality["score"] < 35 or coverage["phone"] < 0.20

    if phone_first:
        strategies.append("电话调解优先")
        reasons.append("手机号覆盖率较高、户均本金处于中低区间，且管辖不高度集中。")
    if litigation:
        strategies.append("批量诉讼评估")
        reasons.append("管辖和合同字段较完整，法院集中度达到批量诉讼默认阈值。")
    if outsource:
        strategies.append("分包清收")
        reasons.append("户数多、金额小、触达信息一般，适合低成本分包。")
    if cautious:
        strategies.append("低价清收/谨慎")
        reasons.append("数据完整度或触达信息不足，不宜投入高成本处置。")
    if not strategies:
        strategies.append("电话调解 + 重点户攻坚")
        reasons.append("当前数据适合先以柔性触达筛选还款意愿，同时处理高金额户。")

    tiers = {"A": [], "B": [], "C": [], "D": []}
    for account in accounts:
        complete_signals = sum(1 for field in ["id_card", "phone", "address"] if account.get(field))
        principal = account["principal"]
        item = {
            "id": account["id"],
            "debtor": account["derived"]["masked_name"],
            "principal": principal,
            "reason": "",
        }
        if account.get("phone") and 5000 <= principal <= 30000:
            item["reason"] = "金额适中且手机号完整，适合第一轮电话调解。"
            tiers["A"].append(item)
        elif principal >= 30000 and complete_signals >= 2:
            item["reason"] = "金额较高且资料较完整，电话核验后转重点户攻坚。"
            tiers["B"].append(item)
        elif principal < 10000 and complete_signals >= 1:
            item["reason"] = "金额较低，适合批量触达或一次性结清方案。"
            tiers["C"].append(item)
        else:
            item["reason"] = "关键信息不足，先补充触达线索。"
            tiers["D"].append(item)

    return {
        "primary_strategy": " + ".join(strategies[:2]),
        "strategies": strategies,
        "reasons": reasons,
        "tiers": tiers,
        "compliance_forbidden": ["威胁、恐吓、侮辱", "高频骚扰", "冒充司法机关", "向无关第三人泄露债务信息", "承诺未经授权的减免结果"],
        "script": {
            "first_contact": "您好，我们这边是受相关债权处置流程委托，和您核实一笔历史借款信息。为了保护您的个人信息，我先确认一下是否方便沟通。我们这次沟通主要是核实债权事实和了解您的还款意愿。",
            "settlement": "如果您有一次性结清或分期处理的意愿，我们可以根据您的实际情况登记协商方案。具体金额和期限需要经过内部审核确认，不会在电话中强迫您立即决定。",
        },
    }
