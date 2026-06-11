from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from .field_mapping import parse_number


def _value(row: dict[str, Any], mapping: dict[str, str | None], field: str) -> Any:
    column = mapping.get(field)
    return row.get(column) if column else None


def _text(row: dict[str, Any], mapping: dict[str, str | None], field: str) -> str | None:
    value = _value(row, mapping, field)
    text = str(value or "").strip()
    return text or None


def _rate(value: Any) -> float | None:
    parsed = parse_number(value)
    if parsed is None:
        return None
    if parsed > 1:
        return parsed / 100
    return parsed


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def amount_bucket(value: float | int | None) -> str:
    if value is None:
        return "unknown"
    amount = float(value)
    if amount < 5000:
        return "0-5k"
    if amount < 20000:
        return "5k-2w"
    if amount < 100000:
        return "2w-10w"
    return "10w+"


def _history_avg_principal(record: dict) -> float | None:
    account_count = record.get("account_count")
    principal_total = record.get("principal_total")
    if principal_total is None:
        return None
    if account_count not in (None, 0):
        return principal_total / account_count
    return principal_total


def history_amount_bucket(record: dict) -> str:
    existing = record.get("derived", {}).get("amount_bucket")
    if existing:
        return existing
    return amount_bucket(_history_avg_principal(record))


def normalize_history_rows(rows: list[dict[str, Any]], mapping: dict[str, str | None], batch_id: str) -> tuple[list[dict], list[dict]]:
    records = []
    errors = []
    for index, row in enumerate(rows, start=2):
        principal_total = parse_number(_value(row, mapping, "principal_total"))
        recovered_amount = parse_number(_value(row, mapping, "recovered_amount"))
        if principal_total is None and recovered_amount is None:
            errors.append({"row_number": index, "code": "missing_amount_basis", "message": "本金总额和回款金额至少需要一个"})
            continue
        purchase_price = parse_number(_value(row, mapping, "purchase_price"))
        record_id = "hist_" + hashlib.sha1(f"{batch_id}:{index}:{principal_total}:{recovered_amount}".encode("utf-8")).hexdigest()[:12]
        derived = {
            "purchase_rate": _safe_div(purchase_price, principal_total),
            "recovery_rate": _safe_div(recovered_amount, principal_total),
            "roi_multiple": _safe_div(recovered_amount, purchase_price),
            "calibration_confidence": "low",
        }
        known_metrics = sum(1 for item in [principal_total, recovered_amount, purchase_price, _text(row, mapping, "court_name"), _text(row, mapping, "region")] if item not in (None, ""))
        if known_metrics >= 5:
            derived["calibration_confidence"] = "high"
        elif known_metrics >= 3:
            derived["calibration_confidence"] = "medium"
        records.append(
            {
                "id": record_id,
                "batch_id": batch_id,
                "row_number": index,
                "project_name": _text(row, mapping, "project_name") or f"历史记录-{index}",
                "asset_type": _text(row, mapping, "asset_type"),
                "region": _text(row, mapping, "region"),
                "court_name": _text(row, mapping, "court_name"),
                "account_count": parse_number(_value(row, mapping, "account_count")),
                "principal_total": principal_total,
                "purchase_price": purchase_price,
                "recovered_amount": recovered_amount,
                "recovery_months": parse_number(_value(row, mapping, "recovery_months")),
                "disposal_method": _text(row, mapping, "disposal_method"),
                "mediation_success_rate": _rate(_value(row, mapping, "mediation_success_rate")),
                "litigation_success_rate": _rate(_value(row, mapping, "litigation_success_rate")),
                "execution_result": _text(row, mapping, "execution_result"),
                "failure_reason": _text(row, mapping, "failure_reason"),
                "notes": _text(row, mapping, "notes"),
                "derived": derived,
            }
        )
        records[-1]["derived"]["average_principal"] = _history_avg_principal(records[-1])
        records[-1]["derived"]["amount_bucket"] = amount_bucket(records[-1]["derived"]["average_principal"])
    return records, errors


def label_court(profile: dict) -> str:
    recovery = profile.get("average_recovery_rate")
    months = profile.get("average_recovery_months")
    failure_text = " ".join(profile.get("common_failure_reasons", []))
    if recovery is not None and recovery >= 0.16 and (months is None or months <= 18):
        return "efficient"
    if recovery is not None and recovery < 0.05:
        return "difficult"
    if months is not None and months >= 30:
        return "cautious"
    if any(token in failure_text for token in ["慢", "终本", "无财产", "证据不足", "失联"]):
        return "cautious"
    return "normal"


def build_court_profiles(records: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        court = (record.get("court_name") or "").strip()
        if court:
            groups[court].append(record)
    profiles = []
    for court, items in groups.items():
        recovery_rates = [item["derived"]["recovery_rate"] for item in items if item.get("derived", {}).get("recovery_rate") is not None]
        recovery_months = [item["recovery_months"] for item in items if item.get("recovery_months") is not None]
        mediation_rates = [item["mediation_success_rate"] for item in items if item.get("mediation_success_rate") is not None]
        litigation_rates = [item["litigation_success_rate"] for item in items if item.get("litigation_success_rate") is not None]
        failures = Counter(item.get("failure_reason") for item in items if item.get("failure_reason"))
        regions = Counter(item.get("region") for item in items if item.get("region"))
        amount_buckets = Counter(history_amount_bucket(item) for item in items if history_amount_bucket(item) != "unknown")
        methods = Counter(item.get("disposal_method") for item in items if item.get("disposal_method"))
        profile = {
            "court_name": court,
            "region": regions.most_common(1)[0][0] if regions else None,
            "sample_count": len(items),
            "principal_total": sum(item.get("principal_total") or 0 for item in items),
            "average_recovery_rate": mean(recovery_rates) if recovery_rates else None,
            "average_recovery_months": mean(recovery_months) if recovery_months else None,
            "recovery_rate_range": [min(recovery_rates), max(recovery_rates)] if recovery_rates else None,
            "recovery_months_range": [min(recovery_months), max(recovery_months)] if recovery_months else None,
            "mediation_success_rate": mean(mediation_rates) if mediation_rates else None,
            "litigation_success_rate": mean(litigation_rates) if litigation_rates else None,
            "amount_bucket_distribution": dict(amount_buckets),
            "primary_amount_bucket": amount_buckets.most_common(1)[0][0] if amount_buckets else "unknown",
            "disposal_method_distribution": dict(methods),
            "primary_disposal_method": methods.most_common(1)[0][0] if methods else None,
            "sample_confidence": "high" if len(items) >= 5 and len(recovery_rates) >= 3 else "medium" if len(items) >= 2 and recovery_rates else "low",
            "common_failure_reasons": [reason for reason, _count in failures.most_common(3)],
            "source_record_ids": [item["id"] for item in items],
        }
        profile["label"] = label_court(profile)
        profiles.append(profile)
    return sorted(profiles, key=lambda item: (-item["sample_count"], item["court_name"]))


def _aggregate_records(records: list[dict], field: str) -> list[dict]:
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
                "principal_total": sum(item.get("principal_total") or 0 for item in items),
                "average_recovery_rate": mean(recovery_rates) if recovery_rates else None,
                "average_recovery_months": mean(recovery_months) if recovery_months else None,
            }
        )
    return sorted(rows, key=lambda item: (-item["sample_count"], item["key"]))


def build_company_history_analytics(records: list[dict]) -> dict:
    recovery_rates = [item.get("derived", {}).get("recovery_rate") for item in records if item.get("derived", {}).get("recovery_rate") is not None]
    recovery_months = [item.get("recovery_months") for item in records if item.get("recovery_months") is not None]
    return {
        "total_records": len(records),
        "usable_recovery_count": len(recovery_rates),
        "principal_total": sum(item.get("principal_total") or 0 for item in records),
        "average_recovery_rate": mean(recovery_rates) if recovery_rates else None,
        "average_recovery_months": mean(recovery_months) if recovery_months else None,
        "by_region": _aggregate_records(records, "region"),
        "by_court": _aggregate_records(records, "court_name"),
        "by_amount_bucket": _aggregate_records(records, "amount_bucket"),
        "by_disposal_method": _aggregate_records(records, "disposal_method"),
    }
