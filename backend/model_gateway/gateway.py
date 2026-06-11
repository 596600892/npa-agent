from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.request import Request, urlopen

from backend.storage import db


PROVIDERS = {
    "deepseek": {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "requires_base_url": False,
    },
    "qwen": {
        "id": "qwen",
        "label": "Qwen / 阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "requires_base_url": False,
    },
    "custom_openai_compatible": {
        "id": "custom_openai_compatible",
        "label": "自定义 OpenAI 兼容接口",
        "base_url": "",
        "default_model": "",
        "requires_base_url": True,
    },
}


class ModelGatewayError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    prompt_chars: int
    response_chars: int
    redacted: bool
    purpose: str = "general"
    prompt_audit: dict | None = None
    recommended_model: dict | None = None


def provider_options() -> list[dict]:
    return [{**item, "recommended_purposes": recommended_purposes_for_provider(item["id"])} for item in PROVIDERS.values()]


def recommended_purposes_for_provider(provider_id: str) -> list[str]:
    if provider_id == "deepseek":
        return ["report_summary", "phone_script", "general"]
    if provider_id == "qwen":
        return ["yindeng_summary", "report_summary", "general"]
    return ["general", "report_summary", "phone_script", "yindeng_summary"]


def recommend_model_for_purpose(purpose: str, provider_id: str | None = None) -> dict:
    if provider_id and provider_id in PROVIDERS:
        provider = PROVIDERS[provider_id]
    elif purpose == "yindeng_summary":
        provider = PROVIDERS["qwen"]
    else:
        provider = PROVIDERS["deepseek"]
    return {
        "provider": provider["id"],
        "model": provider["default_model"] or "manual",
        "reason": "按用途推荐；用户配置优先，推荐仅作为默认选择。",
    }


def redact_sensitive_text(text: str) -> str:
    redacted = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号]", text)
    redacted = re.sub(r"(?<!\d)\d{6}(?:19|20)\d{2}\d{2}\d{2}\d{3}[\dXx](?!\d)", "[身份证]", redacted)
    redacted = re.sub(r"([\u4e00-\u9fa5]{2,4})(先生|女士|借款人|债务人)", r"[姓名]\2", redacted)
    redacted = re.sub(r"([\u4e00-\u9fa5]{2,}(?:省|市|区|县|镇|街道|路|号)[\u4e00-\u9fa50-9\-]*)", "[地址]", redacted)
    return redacted


def resolve_config(override: dict | None = None) -> dict:
    setting = db.get_setting(
        "model",
        {"mode": "redacted_cloud", "provider": "deepseek", "model": "auto", "base_url": "", "api_key_present": False, "allow_original_sensitive_data": False},
    )
    config = {**setting, **(override or {})}
    provider_id = config.get("provider") or "deepseek"
    provider = PROVIDERS.get(provider_id)
    if not provider:
        raise ModelGatewayError("unsupported_provider", "当前模型服务商暂不支持。")
    base_url = (config.get("base_url") or provider["base_url"]).rstrip("/")
    model = config.get("model") if config.get("model") and config.get("model") != "auto" else provider["default_model"]
    api_key = config.get("api_key") or db.get_secret("model", "api_key")
    if not api_key:
        raise ModelGatewayError("model_not_configured", "请先配置模型 API Key。")
    if provider["requires_base_url"] and not base_url:
        raise ModelGatewayError("base_url_required", "自定义兼容接口需要填写 Base URL。")
    if not model:
        raise ModelGatewayError("model_required", "请填写模型名称，或选择带默认模型的服务商。")
    return {
        **config,
        "provider": provider_id,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }


def purpose_prompt(purpose: str, content: str) -> str:
    prompts = {
        "yindeng_summary": "请把下面的银登/不良资产公告整理成结构化摘要，重点提取资产类型、金额、户数、地区、时间节点、核心风险和下一步动作。",
        "report_summary": "请把下面的不良资产初筛报告压缩成老板可快速阅读的摘要，保留机会、风险、报价假设和下一步动作。",
        "phone_script": "请基于下面资产包信息生成电话调解策略和合规话术，不得包含威胁、骚扰、冒充司法机关或向第三人泄露债务信息。",
    }
    instruction = prompts.get(purpose, "请基于下面内容给出专业、审慎、可执行的不良资产分析建议。")
    return f"{instruction}\n\n资料：\n{content}"


def prompt_audit_summary(purpose: str, original_content: str, safe_content: str, redacted: bool) -> dict:
    return {
        "purpose": purpose,
        "redacted": redacted,
        "original_chars": len(original_content),
        "sent_chars": len(safe_content),
        "contains_phone_after_redaction": bool(re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", safe_content)),
        "contains_id_card_after_redaction": bool(re.search(r"(?<!\d)\d{6}(?:19|20)\d{2}\d{2}\d{2}\d{3}[\dXx](?!\d)", safe_content)),
        "sensitive_policy": "redacted_cloud" if redacted else "original_cloud_confirmed",
    }


def chat_completion(config: dict, prompt: str, timeout: int = 40) -> str:
    endpoint = f"{config['base_url']}/chat/completions"
    body = json.dumps(
        {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": "你是服务 AMC、律所和不良资产投资人的本地优先分析助手。回答要审慎、可执行，并说明不确定性。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = Request(
        endpoint,
        data=body,
        headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise ModelGatewayError("model_call_failed", f"模型调用失败：{exc}") from exc
    text = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not text:
        raise ModelGatewayError("empty_model_response", "模型没有返回可用内容。")
    return text


def generate_text(purpose: str, content: str, safety_mode: str | None = None, project_id: str | None = None, override: dict | None = None) -> ModelResponse:
    config = resolve_config(override)
    mode = safety_mode or config.get("mode") or "redacted_cloud"
    if mode == "original_cloud" and not config.get("allow_original_sensitive_data"):
        raise ModelGatewayError("original_cloud_not_confirmed", "原文云端分析需要先明确确认。")
    redacted = mode != "original_cloud"
    safe_content = redact_sensitive_text(content) if redacted else content
    prompt = purpose_prompt(purpose, safe_content)
    text = chat_completion(config, prompt)
    return ModelResponse(
        text=text,
        provider=config["provider"],
        model=config["model"],
        prompt_chars=len(prompt),
        response_chars=len(text),
        redacted=redacted,
        purpose=purpose,
        prompt_audit=prompt_audit_summary(purpose, content, safe_content, redacted),
        recommended_model=recommend_model_for_purpose(purpose, config["provider"]),
    )


def test_model_config(override: dict | None = None) -> ModelResponse:
    return generate_text("health_check", "请只回复：模型连接成功。", safety_mode="redacted_cloud", override=override)
