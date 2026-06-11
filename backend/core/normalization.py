from __future__ import annotations

import hashlib
from typing import Any

from .field_mapping import parse_number
from .id_card import parse_id_card
from .privacy import mask_address, mask_id_card, mask_name, mask_phone


AMOUNT_BANDS = [
    (0, 5000, "0-5000"),
    (5000, 10000, "5000-10000"),
    (10000, 30000, "10000-30000"),
    (30000, 100000, "30000-100000"),
    (100000, float("inf"), "100000以上"),
]


def amount_band(value: float) -> str:
    for lower, upper, label in AMOUNT_BANDS:
        if lower <= value <= upper if lower == 0 else lower < value <= upper:
            return label
    return "未知"


def _value(row: dict[str, Any], mapping: dict[str, str | None], field: str) -> Any:
    column = mapping.get(field)
    return row.get(column) if column else None


def normalize_rows(rows: list[dict[str, Any]], mapping: dict[str, str | None], project_id: str) -> tuple[list[dict], list[dict]]:
    accounts: list[dict] = []
    errors: list[dict] = []
    for index, row in enumerate(rows, start=2):
        principal = parse_number(_value(row, mapping, "principal"))
        if principal is None:
            errors.append({"row_number": index, "code": "missing_principal", "message": "本金为空或无法解析"})
            continue
        interest = parse_number(_value(row, mapping, "interest"))
        debtor = str(_value(row, mapping, "debtor_name_or_id") or "").strip() or f"ROW-{index}"
        id_card = str(_value(row, mapping, "id_card") or "").strip()
        phone = str(_value(row, mapping, "phone") or "").strip()
        address = str(_value(row, mapping, "address") or "").strip()
        parsed_id = parse_id_card(id_card)
        account_id = "acct_" + hashlib.sha1(f"{project_id}:{index}:{debtor}:{principal}".encode("utf-8")).hexdigest()[:12]
        optional = {
            "contract_no": str(_value(row, mapping, "contract_no") or "").strip() or None,
            "overdue_days": parse_number(_value(row, mapping, "overdue_days")),
            "jurisdiction_court": str(_value(row, mapping, "jurisdiction_court") or "").strip() or None,
            "remark": str(_value(row, mapping, "remark") or "").strip() or None,
        }
        accounts.append(
            {
                "id": account_id,
                "project_id": project_id,
                "row_number": index,
                "debtor_name_or_id": debtor,
                "id_card": id_card or None,
                "phone": phone or None,
                "address": address or None,
                "principal": principal,
                "interest": interest,
                "optional": optional,
                "derived": {
                    "masked_name": mask_name(debtor),
                    "masked_id_card": mask_id_card(id_card) if id_card else None,
                    "masked_phone": mask_phone(phone) if phone else None,
                    "masked_address": mask_address(address) if address else None,
                    "age": parsed_id["age"],
                    "age_band": parsed_id["age_band"],
                    "gender": parsed_id["gender"],
                    "id_region": parsed_id["id_region"],
                    "region_confidence": parsed_id["region_confidence"],
                    "amount_band": amount_band(principal),
                },
            }
        )
    return accounts, errors
