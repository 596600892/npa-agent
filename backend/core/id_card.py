from __future__ import annotations

import re
from datetime import date


PROVINCE_CODES = {
    "11": "北京市",
    "12": "天津市",
    "13": "河北省",
    "14": "山西省",
    "15": "内蒙古自治区",
    "21": "辽宁省",
    "22": "吉林省",
    "23": "黑龙江省",
    "31": "上海市",
    "32": "江苏省",
    "33": "浙江省",
    "34": "安徽省",
    "35": "福建省",
    "36": "江西省",
    "37": "山东省",
    "41": "河南省",
    "42": "湖北省",
    "43": "湖南省",
    "44": "广东省",
    "45": "广西壮族自治区",
    "46": "海南省",
    "50": "重庆市",
    "51": "四川省",
    "52": "贵州省",
    "53": "云南省",
    "54": "西藏自治区",
    "61": "陕西省",
    "62": "甘肃省",
    "63": "青海省",
    "64": "宁夏回族自治区",
    "65": "新疆维吾尔自治区",
}

CITY_HINTS = {
    "4403": "广东省深圳市",
    "4401": "广东省广州市",
    "4301": "湖南省长沙市",
    "4201": "湖北省武汉市",
    "5101": "四川省成都市",
    "3201": "江苏省南京市",
    "3301": "浙江省杭州市",
    "4501": "广西壮族自治区南宁市",
    "6101": "陕西省西安市",
    "3701": "山东省济南市",
    "1101": "北京市",
    "3501": "福建省福州市",
}


def age_band(age: int | None) -> str:
    if age is None:
        return "未知"
    if age <= 25:
        return "18-25"
    if age <= 35:
        return "26-35"
    if age <= 45:
        return "36-45"
    if age <= 55:
        return "46-55"
    if age <= 65:
        return "56-65"
    return "65+"


def parse_id_card(value: str | None, today: date | None = None) -> dict:
    text = re.sub(r"\s+", "", str(value or ""))
    result = {
        "valid": False,
        "age": None,
        "age_band": "未知",
        "gender": "unknown",
        "id_region": None,
        "region_confidence": "low",
    }
    if not re.fullmatch(r"\d{17}[\dXx]|\d{15}", text):
        return result

    if len(text) == 18:
        birth = text[6:14]
        gender_digit = text[16]
        region_code = text[:6]
    else:
        birth = f"19{text[6:12]}"
        gender_digit = text[14]
        region_code = text[:6]

    try:
        year = int(birth[:4])
        month = int(birth[4:6])
        day = int(birth[6:8])
        born = date(year, month, day)
        today = today or date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except ValueError:
        return result

    city = CITY_HINTS.get(region_code[:4])
    province = PROVINCE_CODES.get(region_code[:2])
    result.update(
        {
            "valid": True,
            "age": age,
            "age_band": age_band(age),
            "gender": "male" if int(gender_digit) % 2 == 1 else "female",
            "id_region": city or province,
            "region_confidence": "medium" if city else ("low" if province else "low"),
        }
    )
    return result
