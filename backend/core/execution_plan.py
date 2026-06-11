from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .disposition import select_disposition


STATUS_LABELS = {
    "pending": "待处理",
    "contacted": "已接通",
    "no_answer": "未接",
    "unreachable": "失联",
    "willing": "有意愿",
    "promise_payment": "承诺还款",
    "dispute": "异议",
    "switch_to_litigation": "转诉讼评估",
    "outsourced": "建议分包",
    "closed": "已关闭",
}

BATCH_DEFINITIONS = {
    "phone_mediation_round1": {"name": "电话调解首轮", "tier": "A"},
    "key_account_workout": {"name": "重点户攻坚", "tier": "B"},
    "small_batch_contact": {"name": "小额批量触达", "tier": "C"},
    "missing_signal_enrichment": {"name": "补充线索", "tier": "D"},
    "litigation_review": {"name": "诉讼评估候选", "tier": "L"},
}

COMPLIANCE_WARNINGS = ["不得威胁、恐吓、侮辱", "不得高频骚扰", "不得冒充司法机关", "不得向无关第三人泄露债务信息"]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_execution_plan(
    project: dict,
    accounts: list[dict],
    quality: dict,
    profile: dict,
    legal_risk: dict | None = None,
    plan_id: str | None = None,
) -> dict:
    disposition = select_disposition(accounts, quality, profile)
    plan_id = plan_id or "plan_preview"
    batch_rows = _build_batches(project["id"], plan_id)
    batch_by_key = {batch["batch_key"]: batch for batch in batch_rows}
    tiers = _tier_lookup(disposition)
    tasks = []
    for account in accounts:
        tier = tiers.get(account["id"]) or _fallback_tier(account)
        batch_key = _batch_for(account, tier, legal_risk)
        batch = batch_by_key[batch_key]
        task = _task_for_account(project["id"], plan_id, batch["id"], batch_key, tier, account, legal_risk)
        tasks.append(task)
    tasks.sort(key=lambda item: (-item["priority_score"], item["batch_name"], item["principal"]))
    summary = summarize_execution(tasks, batch_rows)
    return {
        "plan": {
            "id": plan_id,
            "project_id": project["id"],
            "name": f"{project.get('name') or '资产包'} 处置执行计划",
            "version": "0.1",
            "status": "active",
            "summary": summary,
            "created_at": now_iso(),
        },
        "batches": batch_rows,
        "tasks": tasks,
        "summary": summary,
    }


def summarize_execution(tasks: list[dict], batches: list[dict] | None = None) -> dict:
    batch_counts = Counter(task["batch_key"] for task in tasks)
    status_counts = Counter(task.get("status", "pending") for task in tasks)
    high_priority = sum(1 for task in tasks if task["priority_score"] >= 80)
    missing_signal = batch_counts.get("missing_signal_enrichment", 0)
    litigation_candidates = batch_counts.get("litigation_review", 0)
    first_round = batch_counts.get("phone_mediation_round1", 0)
    return {
        "task_count": len(tasks),
        "batch_count": sum(1 for _key, count in batch_counts.items() if count > 0) if tasks else len(batches or []),
        "first_round_count": first_round,
        "high_priority_count": high_priority,
        "missing_signal_count": missing_signal,
        "litigation_candidate_count": litigation_candidates,
        "status_counts": dict(status_counts),
        "batch_counts": dict(batch_counts),
    }


def _build_batches(project_id: str, plan_id: str) -> list[dict]:
    rows = []
    for index, (key, definition) in enumerate(BATCH_DEFINITIONS.items(), start=1):
        rows.append(
            {
                "id": f"{plan_id}_batch_{index}",
                "project_id": project_id,
                "plan_id": plan_id,
                "batch_key": key,
                "name": definition["name"],
                "tier": definition["tier"],
                "description": _batch_description(key),
                "sort_order": index,
            }
        )
    return rows


def _batch_description(key: str) -> str:
    return {
        "phone_mediation_round1": "手机号完整、金额适中，先核实身份与还款意愿。",
        "key_account_workout": "金额较高或资料较完整，电话核验后制定重点户策略。",
        "small_batch_contact": "小额户批量触达，优先一次性结清或低成本和解。",
        "missing_signal_enrichment": "信息不足，先补手机号、地址、合同或法院线索。",
        "litigation_review": "法院/合同条件较好或法律风险提示需要诉讼路径复核。",
    }.get(key, "")


def _tier_lookup(disposition: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for tier, items in disposition.get("tiers", {}).items():
        for item in items:
            result[item["id"]] = tier
    return result


def _fallback_tier(account: dict) -> str:
    if account.get("phone") and 5000 <= account["principal"] <= 30000:
        return "A"
    if account["principal"] >= 30000:
        return "B"
    if account["principal"] < 10000:
        return "C"
    return "D"


def _batch_for(account: dict, tier: str, legal_risk: dict | None) -> str:
    court = account.get("optional", {}).get("jurisdiction_court")
    contract_no = account.get("optional", {}).get("contract_no")
    route = (legal_risk or {}).get("strategy_impacts", {}).get("execution_route")
    if route in {"enforcement_recovery_or_asset_trace", "litigation_or_enforcement_review"}:
        return "litigation_review"
    if route == "mediation_performance_check" and account.get("phone"):
        return "phone_mediation_round1"
    if tier == "B" and (court or contract_no) and legal_risk and legal_risk.get("overall_risk") != "high":
        return "litigation_review"
    return {"A": "phone_mediation_round1", "B": "key_account_workout", "C": "small_batch_contact", "D": "missing_signal_enrichment"}.get(tier, "missing_signal_enrichment")


def _task_for_account(project_id: str, plan_id: str, batch_id: str, batch_key: str, tier: str, account: dict, legal_risk: dict | None) -> dict:
    priority = _priority_score(account, tier, batch_key, legal_risk)
    suggested_action, next_action = _actions(batch_key, tier)
    route = (legal_risk or {}).get("strategy_impacts", {}).get("execution_route")
    if route == "enforcement_recovery_or_asset_trace":
        suggested_action, next_action = "执行恢复/财产线索补强", "核验终本、查控反馈和恢复执行材料"
    elif route == "mediation_performance_check":
        suggested_action, next_action = "调解履约核实", "核实履行期限、付款记录和违约责任"
    elif route == "litigation_or_enforcement_review":
        suggested_action, next_action = "判决生效与执行条件复核", "核验生效证明、判决主文和可执行金额"
    return {
        "id": f"{plan_id}_task_{account['id']}",
        "task_id": f"{plan_id}_task_{account['id']}",
        "project_id": project_id,
        "plan_id": plan_id,
        "account_id": account["id"],
        "batch_id": batch_id,
        "batch_key": batch_key,
        "batch_name": BATCH_DEFINITIONS[batch_key]["name"],
        "tier": tier,
        "priority_score": priority,
        "masked_debtor": account["derived"]["masked_name"],
        "principal": account["principal"],
        "phone_present": bool(account.get("phone")),
        "address_present": bool(account.get("address")),
        "id_card_present": bool(account.get("id_card")),
        "region": account["derived"].get("id_region") or "未知",
        "court": account.get("optional", {}).get("jurisdiction_court") or "未知",
        "suggested_action": suggested_action,
        "script": _script_for(batch_key, account),
        "compliance_warnings": COMPLIANCE_WARNINGS,
        "risk_tip": _risk_tip(account, legal_risk),
        "status": "pending",
        "latest_result": None,
        "latest_note": None,
        "next_action": next_action,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def _priority_score(account: dict, tier: str, batch_key: str, legal_risk: dict | None) -> int:
    score = {"A": 68, "B": 76, "C": 52, "D": 38}.get(tier, 45)
    principal = float(account["principal"])
    if principal >= 100000:
        score += 14
    elif principal >= 30000:
        score += 10
    elif 5000 <= principal <= 30000:
        score += 8
    if account.get("phone"):
        score += 10
    if account.get("address"):
        score += 4
    if account.get("id_card"):
        score += 4
    if account.get("optional", {}).get("jurisdiction_court"):
        score += 4
    if batch_key == "litigation_review":
        score += 5
    if legal_risk and legal_risk.get("overall_risk") == "high":
        score -= 8
    return max(1, min(100, int(score)))


def _actions(batch_key: str, tier: str) -> tuple[str, str]:
    if batch_key == "phone_mediation_round1":
        return "第一轮电话调解", "电话核实还款意愿"
    if batch_key == "key_account_workout":
        return "重点户电话核验", "确认收入、争议和可承受方案"
    if batch_key == "small_batch_contact":
        return "小额批量触达", "尝试一次性结清或低成本分期"
    if batch_key == "litigation_review":
        return "诉讼可行性复核", "核验合同、管辖、送达和证据链"
    return "补充触达线索", "补手机号、地址、合同或法院字段"


def _script_for(batch_key: str, account: dict) -> str:
    base = "您好，我们这边和您核实一笔历史借款信息。为保护您的个人信息，请先确认现在是否方便沟通。"
    if batch_key == "phone_mediation_round1":
        return base + " 这次沟通主要了解您的还款意愿，如您有一次性结清或分期处理想法，我们可以先登记方案。"
    if batch_key == "key_account_workout":
        return base + " 这笔金额相对较高，我们希望先核实债权事实、争议点和您可承受的处理方式。"
    if batch_key == "small_batch_contact":
        return base + " 如果您希望尽快处理，我们可以登记一次性结清或短期分期意向，后续以审核结果为准。"
    if batch_key == "litigation_review":
        return "先由处置/法务人员核验合同、管辖、送达和证据链，再决定是否进入诉讼评估，不建议直接外呼施压。"
    return "当前触达线索不足，先补充手机号、地址或合同信息；联系第三方时不得泄露债务信息。"


def _risk_tip(account: dict, legal_risk: dict | None) -> str:
    tips = []
    if not account.get("phone"):
        tips.append("缺少手机号")
    if not account.get("address"):
        tips.append("缺少地址")
    if account.get("optional", {}).get("jurisdiction_court"):
        tips.append("有法院线索")
    if legal_risk:
        tips.append(f"合同风险{legal_risk.get('overall_risk')}")
    return "；".join(tips) or "基础线索可用"
