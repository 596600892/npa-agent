from __future__ import annotations

from collections import Counter
from statistics import median


AMOUNT_ORDER = ["0-5000", "5000-10000", "10000-30000", "30000-100000", "100000以上"]


def _pct(value: int | float, total: int | float) -> float:
    return round(value / total, 4) if total else 0.0


def analyze_profile(accounts: list[dict]) -> dict:
    principals = [float(account["principal"]) for account in accounts]
    interests = [float(account["interest"] or 0) for account in accounts]
    amount_counts = Counter(account["derived"]["amount_band"] for account in accounts)
    age_counts = Counter(account["derived"]["age_band"] for account in accounts)
    gender_counts = Counter(account["derived"]["gender"] for account in accounts)
    region_counts = Counter(account["derived"]["id_region"] or "未知" for account in accounts)
    court_counts = Counter((account.get("optional", {}).get("jurisdiction_court") or "未知") for account in accounts)
    top_principal_threshold = sorted(principals, reverse=True)[max(0, int(len(principals) * 0.05) - 1)] if principals else 0
    return {
        "basic": {
            "account_count": len(accounts),
            "principal_total": round(sum(principals), 2),
            "interest_total": round(sum(interests), 2),
            "total_claim": round(sum(principals) + sum(interests), 2),
            "average_principal": round(sum(principals) / len(principals), 2) if principals else 0,
            "median_principal": round(median(principals), 2) if principals else 0,
        },
        "amount_distribution": [
            {"band": band, "count": amount_counts.get(band, 0), "ratio": _pct(amount_counts.get(band, 0), len(accounts))}
            for band in AMOUNT_ORDER
        ],
        "age_distribution": [{"band": key, "count": value, "ratio": _pct(value, len(accounts))} for key, value in age_counts.most_common()],
        "gender_distribution": [{"gender": key, "count": value, "ratio": _pct(value, len(accounts))} for key, value in gender_counts.most_common()],
        "region_distribution": [{"region": key, "count": value, "ratio": _pct(value, len(accounts))} for key, value in region_counts.most_common(8)],
        "court_distribution": [{"court": key, "count": value, "ratio": _pct(value, len(accounts))} for key, value in court_counts.most_common(8)],
        "top_accounts": [
            account for account in sorted(accounts, key=lambda item: item["principal"], reverse=True)[: max(1, min(10, len(accounts)))]
        ],
        "top_principal_threshold": top_principal_threshold,
    }
