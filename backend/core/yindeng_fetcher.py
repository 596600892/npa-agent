from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .document_ingestion import ingest_bytes


MAX_FETCH_BYTES = 5 * 1024 * 1024


class YindengFetchError(Exception):
    def __init__(self, code: str, message: str, next_actions: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_actions = next_actions or ["paste_notice_text", "upload_notice_file", "check_public_url"]


@dataclass
class FetchedSource:
    url: str
    content_type: str
    raw_bytes: bytes
    raw_text: str
    raw_sha256: str
    ingestion: dict | None = None


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise YindengFetchError("invalid_url", "请填写 http 或 https 开头的公开公告 URL。")
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise YindengFetchError("private_url_blocked", "为避免读取本机服务，银登抓取不支持 localhost 地址。")
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise YindengFetchError("private_url_blocked", "为避免内网访问风险，请使用公开可访问的公告 URL。")
    except YindengFetchError:
        raise
    except Exception:
        pass
    return url


def decode_bytes(raw: bytes, content_type: str) -> str:
    lowered = content_type.lower()
    for encoding in ["utf-8", "gb18030", "gbk"]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _filename_from_url(url: str, content_type: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix:
        return f"notice{suffix}"
    lowered = content_type.lower()
    if "pdf" in lowered:
        return "notice.pdf"
    if "png" in lowered:
        return "notice.png"
    if "jpeg" in lowered or "jpg" in lowered:
        return "notice.jpg"
    if "webp" in lowered:
        return "notice.webp"
    if "html" in lowered:
        return "notice.html"
    return "notice.txt"


def _is_document_binary(raw: bytes, content_type: str, url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    lowered = content_type.lower()
    return raw[:4] == b"%PDF" or suffix in {".pdf", ".png", ".jpg", ".jpeg", ".webp"} or any(token in lowered for token in ["pdf", "image/png", "image/jpeg", "image/webp"])


def fetch_public_url(url: str, timeout: int = 15) -> FetchedSource:
    url = validate_public_url(url)
    req = Request(
        url,
        headers={
            "User-Agent": "NPAAgent/0.1 public-notice-fetcher",
            "Accept": "text/html,application/pdf,text/plain,*/*;q=0.8",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_FETCH_BYTES + 1)
            if len(raw) > MAX_FETCH_BYTES:
                raise YindengFetchError("source_too_large", "公告文件超过 5MB，请改为上传或粘贴正文。")
            content_type = resp.headers.get("Content-Type", "text/plain")
    except YindengFetchError:
        raise
    except Exception as exc:
        raise YindengFetchError("fetch_failed", f"无法抓取该公开 URL：{exc}") from exc
    ingestion = None
    if _is_document_binary(raw, content_type, url):
        ingested = ingest_bytes(raw, _filename_from_url(url, content_type))
        text = ingested.text or "附件文件已抓取，但当前无法可靠提取正文。请粘贴公告正文、上传可复制文本文件，或配置本地 OCR 后重试。"
        ingestion = ingested.as_dict()
    else:
        text = decode_bytes(raw, content_type)
    return FetchedSource(
        url=url,
        content_type=content_type,
        raw_bytes=raw,
        raw_text=text,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        ingestion=ingestion,
    )
