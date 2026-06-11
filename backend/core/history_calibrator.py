from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .company_history import amount_bucket, history_amount_bucket


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


def _average_account_principal(accounts: list[dict]) -> float | None:
    principals = [account.get("principal") for account in accounts if account.get("principal") is not None]
    return mean(principals) if principals else None


def _project_context(project: dict, accounts: list[dict]) -> dict:
    average_principal = _average_account_principal(accounts)
    methods = set()
    for value in [project.get("disposal_method"), project.get("preferred_disposal_method")]:
        if value:
            methods.add(str(value))
    return {
        "asset_type": project.get("asset_type"),
        "regions": _account_regions(accounts),
        "courts": _account_courts(accounts),
        "average_principal": average_principal,
        "amount_bucket": amount_bucket(average_principal),
        "disposal_methods": methods,
    }


def _dimension_match(record: dict, context: dict) -> tuple[int, list[str], list[str], list[str]]:
    score = 0
    matched: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []

    if context["asset_type"] and record.get("asset_type"):
        if str(context["asset_type"]) in str(record["asset_type"]) or str(record["asset_type"]) in str(context["asset_type"]):
            score += 1
            matched.append("asset_type")
            reasons.append("资产类型相近")
        else:
            missing.append("asset_type")
    else:
        missing.append("asset_type")

    if record.get("court_name") and record["court_name"] in context["courts"]:
        score += 4
        matched.append("court")
        reasons.append(f"命中同法院：{record['court_name']}")
    elif context["courts"] or record.get("court_name"):
        missing.append("court")

    if record.get("region") and any(region and region in record["region"] for region in context["regions"]):
        score += 3
        matched.append("region")
        reasons.append(f"命中地区线索：{record['region']}")
    elif context["regions"] or record.get("region"):
        missing.append("region")

    record_bucket = history_amount_bucket(record)
    if record_bucket != "unknown" and context["amount_bucket"] != "unknown":
        if record_bucket == context["amount_bucket"]:
            score += 2
            matched.append("amount_bucket")
            reasons.append(f"命中金额段：{record_bucket}")
        else:
            missing.append("amount_bucket")
    else:
        missing.append("amount_bucket")

    record_method = record.get("disposal_method")
    if context["disposal_methods"] and record_method:
        if any(method in record_method or record_method in method for method in context["disposal_methods"]):
            score += 1
            matched.append("disposal_method")
            reasons.append(f"命中处置方式：{record_method}")
        else:
            missing.append("disposal_method")
    elif record_method:
        missing.append("disposal_method")

    return score, matched, sorted(set(missing)), reasons


def _match_records(project: dict, accounts: list[dict], records: list[dict]) -> tuple[list[dict], dict]:
    context = _project_context(project, accounts)
    matched = []
    for record in records:
        score, matched_dimensions, missing_dimensions, reasons = _dimension_match(record, context)
        if score > 0:
            matched.append(
                {
                    **record,
                    "match_score": score,
                    "matched_dimensions": matched_dimensions,
                    "missing_dimensions": missing_dimensions,
                    "match_reason": "；".join(reasons) if reasons else "存在弱匹配历史样本",
                }
            )
    return sorted(matched, key=lambda item: (-item["match_score"], item.get("project_name") or "")), context


def _aggregate_matched(records: list[dict], field: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if field == "amount_bucket":
            key = history_amount_bucket(record)
        else:
            key = record.get(field) or "未填写"
        groups[str(key)].append(record)
    rows = []
    for key, items in groups.items():
        recovery_rates = [item.get("derived", {}).get("recovery_rate") for item in items if item.get("derived", {}).get("recovery_rate") is not None]
        recovery_months = [item.get("recovery_months") for item in items if item.get("recovery_months") is not None]
        rows.append(
            {
                "key": key,
                "sample_count": len(items),
                "usable_recovery_count": len(recovery_rates),
                "average_recovery_rate": mean(recovery_rates) if recovery_rates else None,
                "average_recovery_months": mean(recovery_months) if recovery_months else None,
            }
        )
    return sorted(rows, key=lambda item: (-item["sample_count"], item["key"]))


def _sample_confidence(matched: list[dict], usable: list[dict]) -> str:
    matched_dimension_counts = defaultdict(int)
    for item in matched:
        for dimension in item.get("matched_dimensions", []):
            matched_dimension_counts[dimension] += 1
    if len(usable) >= 5 and matched_dimension_counts["court"] >= 1 and matched_dimension_counts["region"] >= 2:
        return "high"
    if len(usable) >= 2 and (matched_dimension_counts["court"] >= 1 or matched_dimension_counts["region"] >= 1 or matched_dimension_counts["amount_bucket"] >= 1):
        return "medium"
    if matched:
        return "low"
    return "none"


def build_pricing_calibration(project: dict, accounts: list[dict], records: list[dict], court_profiles: list[dict]) -> dict:
    matched, context = _match_records(project, accounts, records)
    usable = [item for item in matched if item.get("derived", {}).get("recovery_rate") is not None]
    average_recovery_rate = mean([item["derived"]["recovery_rate"] for item in usable]) if usable else None
    average_recovery_months = mean([item["recovery_months"] for item in matched if item.get("recovery_months") is not None]) if matched else None
    court_names = _account_courts(accounts)
    matched_profiles = [profile for profile in court_profiles if profile["court_name"] in court_names]
    sample_confidence = _sample_confidence(matched, usable)

    adjustment = 0.0
    reasons = []
    if sample_confidence in {"medium", "high"} and average_recovery_rate is not None:
        if average_recovery_rate >= 0.14:
            adjustment += 0.015
            reasons.append("匹配历史回收率较好，报价区间小幅上修。")
        elif average_recovery_rate < 0.06:
            adjustment -= 0.015
            reasons.append("匹配历史回收率偏低，报价区间下修。")
        else:
            reasons.append("匹配历史回收率处于中性区间，报价区间保持谨慎。")
    elif matched:
        reasons.append("历史匹配样本不足或可计算回收率不足，规则报价为主，历史仅作参考。")
    for profile in matched_profiles:
        if profile["label"] == "efficient":
            adjustment += 0.005
            reasons.append(f"{profile['court_name']} 历史标签为 efficient，批量处置经验偏正面。")
        elif profile["label"] in {"cautious", "difficult"}:
            adjustment -= 0.005
            reasons.append(f"{profile['court_name']} 历史标签为 {profile['label']}，需降低诉讼/执行预期。")
    if not reasons:
        reasons.append("历史样本不足，规则报价为主，历史仅作参考。")
    breakdown = {
        "by_court": _aggregate_matched(matched, "court_name"),
        "by_region": _aggregate_matched(matched, "region"),
        "by_amount_bucket": _aggregate_matched(matched, "amount_bucket"),
        "by_disposal_method": _aggregate_matched(matched, "disposal_method"),
    }
    matched_dimension_summary = defaultdict(int)
    for item in matched:
        for dimension in item.get("matched_dimensions", []):
            matched_dimension_summary[dimension] += 1
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
                "amount_bucket": history_amount_bucket(item),
                "disposal_method": item.get("disposal_method"),
                "recovery_rate": item.get("derived", {}).get("recovery_rate"),
                "recovery_months": item.get("recovery_months"),
                "match_score": item.get("match_score"),
                "matched_dimensions": item.get("matched_dimensions", []),
                "missing_dimensions": item.get("missing_dimensions", []),
                "match_reason": item.get("match_reason"),
            }
            for item in matched[:8]
        ],
        "court_profiles": matched_profiles[:6],
        "breakdown": breakdown,
        "matched_dimension_summary": dict(matched_dimension_summary),
        "project_context": {
            "asset_type": context["asset_type"],
            "regions": sorted(context["regions"]),
            "courts": sorted(context["courts"]),
            "average_principal": context["average_principal"],
            "amount_bucket": context["amount_bucket"],
            "disposal_methods": sorted(context["disposal_methods"]),
        },
        "adjustment": max(-0.03, min(0.03, adjustment)),
        "confidence": sample_confidence,
        "sample_confidence": sample_confidence,
        "reasons": reasons,
    }
