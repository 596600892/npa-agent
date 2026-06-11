from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen

from backend.model_gateway.gateway import redact_sensitive_text
from backend.storage import db


VOICE_PROVIDERS = [
    {
        "id": "builtin_browser",
        "label": "浏览器自带语音",
        "needs_key": False,
        "mode": "fallback",
    },
    {
        "id": "openai_compatible_tts",
        "label": "增强 TTS（OpenAI 语音兼容）",
        "needs_key": True,
        "mode": "enhanced",
        "default_base_url": "https://api.openai.com",
        "default_model": "tts-1",
        "default_voice": "nova",
    },
    {
        "id": "reserved_qwen_tts",
        "label": "Qwen/百炼语音（预留）",
        "needs_key": True,
        "mode": "reserved",
    },
    {
        "id": "reserved_doubao_tts",
        "label": "豆包/火山语音（预留）",
        "needs_key": True,
        "mode": "reserved",
    },
]


class VoiceGatewayError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class TTSResponse:
    audio: bytes
    content_type: str
    provider: str
    voice: str


def voice_provider_options() -> list[dict]:
    return VOICE_PROVIDERS


def resolve_voice_config(override: dict | None = None) -> dict:
    setting = db.get_setting(
        "voice",
        {
            "mode": "builtin_fallback",
            "enhanced_enabled": False,
            "tts_provider": "builtin_browser",
            "tts_base_url": "",
            "tts_model": "tts-1",
            "tts_voice": "nova",
            "sensitive_data_readout": "masked_only",
            "tts_api_key_present": False,
        },
    )
    config = {**setting, **(override or {})}
    provider = config.get("tts_provider") or "builtin_browser"
    if provider != "openai_compatible_tts":
        raise VoiceGatewayError("enhanced_tts_not_available", "增强 TTS 暂只支持 OpenAI 语音兼容接口；请使用浏览器自带语音或配置兼容接口。")
    api_key = config.get("tts_api_key") or config.get("voice_api_key") or db.get_secret("voice", "tts_api_key") or db.get_secret("voice", "voice_api_key")
    if not api_key:
        raise VoiceGatewayError("voice_not_configured", "请先配置增强语音 API Key，或使用浏览器自带语音。")
    base_url = (config.get("tts_base_url") or "https://api.openai.com").rstrip("/")
    return {
        **config,
        "tts_provider": provider,
        "tts_base_url": base_url,
        "tts_model": config.get("tts_model") or "tts-1",
        "tts_voice": config.get("tts_voice") or "nova",
        "tts_api_key": api_key,
    }


def synthesize_speech(text: str, override: dict | None = None, timeout: int = 40) -> TTSResponse:
    config = resolve_voice_config(override)
    if config.get("sensitive_data_readout", "masked_only") == "masked_only":
        text = redact_sensitive_text(text)
    if len(text) > 1800:
        text = text[:1800] + "……"
    body = json.dumps(
        {
            "model": config["tts_model"],
            "input": text,
            "voice": config["tts_voice"],
            "response_format": "mp3",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = Request(
        f"{config['tts_base_url']}/v1/audio/speech",
        data=body,
        headers={"Authorization": f"Bearer {config['tts_api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            audio = resp.read()
            content_type = resp.headers.get("Content-Type", "audio/mpeg")
    except Exception as exc:
        raise VoiceGatewayError("tts_call_failed", f"语音合成失败：{exc}") from exc
    return TTSResponse(audio=audio, content_type=content_type, provider=config["tts_provider"], voice=config["tts_voice"])
