from __future__ import annotations

from statistics import mean


def _account_regions(accounts: list[dict]) -> set[str]:
    regions = set()
    for account in accounts:
        derived = account.get("derived", {})
        for key in ["id_region", "masked_address"]:
            value = derived.get(key)
            if value:
                regions.add(str(value)[:2])
        address = account.get("address")
        if address:
            regions.add(str(address)[:2])
    return {region for region in regions if region and region != "未知"}


def _account_courts(accounts: list[dict]) -> set[str]:
    return {account.get("optional", {}).get("jurisdiction_court") for account in accounts if account.get("optional", {}).get("jurisdiction_court")}


def _match_records(project: dict, accounts: list[dict], records: list[dict]) -> list[dict]:
    asset_type = project.get("asset_type")
    courts = _account_courts(accounts)
    regions = _account_regions(accounts)
    matched = []
    for record in records:
        score = 0
        if asset_type and record.get("asset_type") and asset_type in str(record["asset_type"]):
            score += 1
        if record.get("court_name") and record["court_name"] in courts:
            score += 3
        if record.get("region") and any(region and region in record["region"] for region in regions):
            score += 2
        if record.get("disposal_method") and any(token in record["disposal_method"] for token in ["调解", "诉讼", "执行", "分包"]):
            score += 1
        if score > 0:
            matched.append({**record, "match_score": score})
    return sorted(matched, key=lambda item: (-item["match_score"], item.get("project_name") or ""))


def build_pricing_calibration(project: dict, accounts: list[dict], records: list[dict], court_profiles: list[dict]) -> dict:
    matched = _match_records(project, accounts, records)
    usable = [item for item in matched if item.get("derived", {}).get("recovery_rate") is not None]
    average_recovery_rate = mean([item["derived"]["recovery_rate"] for item in usable]) if usable else None
    average_recovery_months = mean([item["recovery_months"] for item in matched if item.get("recovery_months") is not None]) if matched else None
    court_names = _account_courts(accounts)
    matched_profiles = [profile for profile in court_profiles if profile["court_name"] in court_names]
    confidence = "none"
    if len(usable) >= 5:
        confidence = "high"
    elif len(usable) >= 2:
        confidence = "medium"
    elif len(matched) >= 1:
        confidence = "low"

    adjustment = 0.0
    reasons = []
    if average_recovery_rate is not None:
        if average_recovery_rate >= 0.14:
            adjustment += 0.015
            reasons.append("匹配历史回收率较好，报价区间小幅上修。")
        elif average_recovery_rate < 0.06:
            adjustment -= 0.015
            reasons.append("匹配历史回收率偏低，报价区间下修。")
        else:
            reasons.append("匹配历史回收率处于中性区间，报价区间保持谨慎。")
    for profile in matched_profiles:
        if profile["label"] == "efficient":
            adjustment += 0.005
            reasons.append(f"{profile['court_name']} 历史标签为 efficient，批量处置经验偏正面。")
        elif profile["label"] in {"cautious", "difficult"}:
            adjustment -= 0.005
            reasons.append(f"{profile['court_name']} 历史标签为 {profile['label']}，需降低诉讼/执行预期。")
    if not reasons:
        reasons.append("历史样本不足，报价仍以规则区间为主。")
    return {
        "matched_count": len(matched),
        "usable_recovery_count": len(usable),
        "average_recovery_rate": average_recovery_rate,
        "average_recovery_months": average_recovery_months,
        "matched_records": [
            {
                "id": item["id"],
                "project_name": item.get("project_name"),
                "court_name": item.get("court_name"),
                "region": item.get("region"),
                "recovery_rate": item.get("derived", {}).get("recovery_rate"),
                "recovery_months": item.get("recovery_months"),
                "match_score": item.get("match_score"),
            }
            for item in matched[:8]
        ],
        "court_profiles": matched_profiles[:6],
        "adjustment": max(-0.03, min(0.03, adjustment)),
        "confidence": confidence,
        "reasons": reasons,
    }
