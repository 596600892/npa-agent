from __future__ import annotations


def _coverage(accounts: list[dict], getter) -> float:
    if not accounts:
        return 0.0
    return sum(1 for account in accounts if getter(account)) / len(accounts)


def data_quality(accounts: list[dict]) -> dict:
    count = len(accounts)
    principal_coverage = _coverage(accounts, lambda a: a.get("principal") is not None)
    identifier_coverage = _coverage(accounts, lambda a: a.get("debtor_name_or_id"))
    id_coverage = _coverage(accounts, lambda a: a.get("id_card"))
    phone_coverage = _coverage(accounts, lambda a: a.get("phone"))
    address_coverage = _coverage(accounts, lambda a: a.get("address"))
    interest_coverage = _coverage(accounts, lambda a: a.get("interest") is not None)
    court_or_contract_coverage = _coverage(accounts, lambda a: a.get("optional", {}).get("jurisdiction_court") or a.get("optional", {}).get("contract_no"))
    score = 0.0
    score += 30 if principal_coverage >= 0.9 else 30 * principal_coverage
    score += 10 if identifier_coverage >= 0.9 else 10 * identifier_coverage
    score += 20 * id_coverage
    score += 20 * phone_coverage
    score += 10 * address_coverage
    score += 5 * interest_coverage
    score += 5 if court_or_contract_coverage >= 0.5 else 5 * court_or_contract_coverage
    score_int = round(score)
    has_profile_signal = max(id_coverage, phone_coverage, address_coverage) > 0
    has_jurisdiction_signal = court_or_contract_coverage >= 0.5
    if not has_profile_signal or score_int <= 35:
        level = "Level 1"
        suitable = ["基础金额初筛", "粗略处置模式判断"]
    elif not has_jurisdiction_signal:
        level = "Level 2"
        suitable = ["资产包初筛", "人群画像", "电话调解初判"]
    else:
        level = "Level 3"
        suitable = ["较完整处置策略", "管辖初判"]
    missing = []
    if id_coverage < 0.8:
        missing.append({"field": "身份证号", "impact": "无法准确分析年龄、性别、户籍地"})
    if phone_coverage < 0.8:
        missing.append({"field": "手机号", "impact": "电话调解触达率可信度下降"})
    if address_coverage < 0.8:
        missing.append({"field": "地址", "impact": "地区集中度和跨区域成本判断受限"})
    if court_or_contract_coverage < 0.5:
        missing.append({"field": "合同编号/管辖法院", "impact": "无法判断诉讼集中度和批量诉讼可行性"})
    return {
        "account_count": count,
        "score": score_int,
        "level": level,
        "suitable_for": suitable,
        "coverage": {
            "principal": principal_coverage,
            "debtor_identifier": identifier_coverage,
            "id_card": id_coverage,
            "phone": phone_coverage,
            "address": address_coverage,
            "interest": interest_coverage,
            "court_or_contract": court_or_contract_coverage,
        },
        "missing_inputs": missing,
    }
