import base64
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from httpx_sse import EventSource


class OpenAICompatibleError(RuntimeError):
    def __init__(self, message: str, code: str = "PROVIDER_ERROR", retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.request_id = None


def safe_error_text(value: object, secrets: tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)bearer\s+[^\s\"'<>]+|sk-[a-zA-Z0-9_-]+", "[REDACTED]", text)
    text = re.sub(r"data:[^\s,]+;base64,[a-zA-Z0-9+/=]+", "[REDACTED DATA]", text)
    text = re.sub(r"(?i)(api[_-]?key|authorization|access[_-]?token|password|secret)([\s\"']*[:=][\s\"']*)[^\s,;\"'<>]+", r"\1\2[REDACTED]", text)
    text = re.sub(r"https?://[^\s<>\"]+", lambda m: m[0].split("?", 1)[0].split("#", 1)[0] if "@" not in m[0] else "[REDACTED URL]", text)
    return "".join(c for c in text if c in "\n\t" or ord(c) >= 32)[:1200]


@dataclass(frozen=True)
class StructuredCompletion:
    value: dict[str, Any]
    request_id: str | None
    model_id: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


def list_models(base_url: str, api_key: str, timeout_seconds: int = 20) -> tuple[list[str], int]:
    started = monotonic()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(_url(base_url, "models"), headers=_headers(api_key))
            _raise_for_status(response)
            payload = response.json()
    except OpenAICompatibleError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise OpenAICompatibleError(f"模型平台连接失败：{type(error).__name__}", "PROVIDER_UNAVAILABLE") from error
    models = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    return models, round((monotonic() - started) * 1000)


def complete_json(
    *,
    base_url: str,
    api_key: str,
    model_id: str,
    schema_name: str,
    schema: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    image_assets: list[dict[str, Any]] | None = None,
    timeout_seconds: int = 60,
    stream: bool = False,
) -> StructuredCompletion:
    content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for asset in (image_assets or [])[:4]:
        data_url = _asset_data_url(asset)
        if data_url:
            content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    if stream:
        body.update(stream=True, stream_options={"include_usage": True})
    started = monotonic()
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 20),
        write=min(timeout_seconds, 60), pool=min(timeout_seconds, 20))
    response = None
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", _url(base_url, "chat/completions"), headers=_headers(api_key), json=body) as response:
                if not response.is_success or "text/event-stream" not in response.headers.get("content-type", ""):
                    response.read()
                    _raise_for_status(response)
                    payload = response.json()
                else:
                    payload = _collect_chat_stream(response, started, timeout_seconds, (api_key, system_prompt, user_prompt))
    except OpenAICompatibleError as error:
        if response is not None and not error.request_id:
            request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
            error.request_id = safe_error_text(request_id, (api_key,))[:200] if request_id else None
        raise
    except httpx.TimeoutException as error:
        stage, limit = "等待响应数据", timeout.read
        if isinstance(error, httpx.ConnectTimeout):
            stage, limit = "建立连接", timeout.connect
        elif isinstance(error, httpx.WriteTimeout):
            stage, limit = "发送请求数据", timeout.write
        elif isinstance(error, httpx.PoolTimeout):
            stage, limit = "等待连接池", timeout.pool
        endpoint = str(httpx.URL(_url(base_url, "chat/completions")).copy_with(query=None, fragment=None, username=None, password=None))
        message = (f"模型调用超时：{stage}超过 {limit:g} 秒的等待上限。\n"
            f"超时阶段：{type(error).__name__}\n实际耗时：{monotonic() - started:.1f} 秒\n"
            f"请求接口：POST {safe_error_text(endpoint, (api_key,))}\n"
            "未收到完整模型结果，未在本次请求内自动重试；可在模型配置中调整超时后手动重试。")
        raise OpenAICompatibleError(message, "TIMEOUT") from error
    except (httpx.HTTPError, ValueError) as error:
        raise OpenAICompatibleError(f"模型平台调用失败：{type(error).__name__}", "PROVIDER_UNAVAILABLE") from error

    try:
        raw_content = payload["choices"][0]["message"]["content"]
        if isinstance(raw_content, list):
            raw_content = "".join(item.get("text", "") for item in raw_content if isinstance(item, dict))
        value = json.loads(raw_content)
        if not isinstance(value, dict):
            raise TypeError("structured response is not an object")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise OpenAICompatibleError("模型没有返回有效的结构化 JSON", "SCHEMA_INVALID") from error

    usage = payload.get("usage") or {}
    request_id = response.headers.get("x-request-id") or payload.get("id")
    return StructuredCompletion(
        value=value,
        request_id=request_id if isinstance(request_id, str) else None,
        model_id=str(payload.get("model") or model_id),
        input_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        duration_ms=round((monotonic() - started) * 1000),
    )


def _collect_chat_stream(response: httpx.Response, started: float, timeout_seconds: int, secrets: tuple[str, ...]) -> dict:
    fragments = []
    size = 0
    finish_reason = None
    done = False
    payload = {}
    def checked_bytes():
        for block in response.iter_bytes():
            if monotonic() - started > timeout_seconds:
                raise OpenAICompatibleError(f"模型流式生成超过 {timeout_seconds} 秒预算，未保存不完整脚本", "TIMEOUT")
            yield block
    source = httpx.Response(200, headers={"content-type": "text/event-stream"}, content=checked_bytes())
    # SSE framing is handled by the library; reasoning deltas are never collected.
    for event in EventSource(source).iter_sse():
        if event.data == "[DONE]":
            done = True
            break
        if not event.data:
            continue
        try:
            chunk = json.loads(event.data)
        except ValueError as error:
            raise OpenAICompatibleError("模型流式响应不是有效 JSON", "SCHEMA_INVALID") from error
        if not isinstance(chunk, dict):
            raise OpenAICompatibleError("模型流式响应格式无效", "SCHEMA_INVALID")
        if chunk.get("error"):
            error = chunk["error"]
            message = error.get("message", "模型流式响应失败") if isinstance(error, dict) else "模型流式响应失败"
            limited = isinstance(error, dict) and error.get("type") == "rate_limit_error"
            raise OpenAICompatibleError("模型在流式响应中报告错误：" + safe_error_text(message, secrets),
                "RATE_LIMITED" if limited else "PROVIDER_ERROR", 60 if limited else None)
        for name in ("id", "model", "usage"):
            if chunk.get(name):
                payload[name] = chunk[name]
        for choice in chunk.get("choices", []):
            if choice.get("index", 0) != 0:
                continue
            content = choice.get("delta", {}).get("content")
            if isinstance(content, str):
                size += len(content)
                if size > 1_000_000:
                    raise OpenAICompatibleError("模型脚本输出超过大小上限，未保存结果", "SCHEMA_INVALID")
                fragments.append(content)
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
    if not done or finish_reason != "stop":
        reason = "输出长度受限" if finish_reason == "length" else "响应未完整结束"
        raise OpenAICompatibleError(f"模型流式生成中断：{reason}，未保存不完整脚本", "SCHEMA_INVALID")
    payload["choices"] = [{"message": {"content": "".join(fragments)}}]
    return payload


def probe_structured_output(base_url: str, api_key: str, model_id: str, timeout_seconds: int) -> StructuredCompletion:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["ok", "locale"],
        "properties": {"ok": {"type": "boolean"}, "locale": {"type": "string"}},
    }
    return complete_json(
        base_url=base_url,
        api_key=api_key,
        model_id=model_id,
        schema_name="vediogen_deployment_probe",
        schema=schema,
        system_prompt="Return only the requested schema. This is a connectivity check.",
        user_prompt="Set ok to true and locale to zh-CN.",
        timeout_seconds=timeout_seconds,
    )


def _asset_data_url(asset: dict[str, Any]) -> str | None:
    mime_type = str(asset.get("mimeType") or "")
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        return None
    path = Path(str(asset.get("uri") or ""))
    if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        return None
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


class _ErrorPageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        payload = response.json()
    except ValueError:
        payload = None
    upstream = payload.get("error", payload) if isinstance(payload, dict) else payload
    secrets = []
    try:
        authorization = response.request.headers.get("authorization", "")
        secrets.extend([authorization, authorization.removeprefix("Bearer ")])
        request_body = json.loads(response.request.content or b"{}")
        for message in request_body.get("messages", []):
            content = message.get("content")
            if isinstance(content, str):
                secrets.append(content)
            elif isinstance(content, list):
                secrets.extend(item["text"] for item in content if isinstance(item, dict) and isinstance(item.get("text"), str))
    except (RuntimeError, ValueError, AttributeError, TypeError):
        pass
    details = []
    if isinstance(upstream, dict):
        for key in ("message", "type", "code", "detail", "title", "error_description"):
            if isinstance(upstream.get(key), (str, int)):
                details.append(f"{key}: {safe_error_text(upstream[key], tuple(secrets))}")
    elif isinstance(upstream, str):
        details.append(safe_error_text(upstream, tuple(secrets)))
    content_type = response.headers.get("content-type", "").lower()
    if payload is None and response.content:
        raw = response.text
        if "html" in content_type or raw.lstrip().lower().startswith(("<!doctype html", "<html")):
            parser = _ErrorPageText()
            parser.feed(raw)
            details.append(safe_error_text(" ".join(parser.parts), tuple(secrets)))
        elif not content_type or content_type.startswith("text/"):
            details.append(safe_error_text(raw, tuple(secrets)))
    details = [item for item in details if item.strip()]
    request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    request_id = safe_error_text(request_id, tuple(secrets))[:200] if request_id else None
    diagnostics = [f"响应类型：{safe_error_text(content_type or '未提供', tuple(secrets))}", f"响应体字节数：{len(response.content)}"]
    try:
        request = response.request
        endpoint = str(request.url.copy_with(query=None, fragment=None, username=None, password=None))
        diagnostics.insert(0, f"请求接口：{request.method} {safe_error_text(endpoint, tuple(secrets))}")
    except RuntimeError:
        pass
    for header in ("server", "via", "cf-ray"):
        if response.headers.get(header):
            diagnostics.append(f"{header}：{safe_error_text(response.headers[header], tuple(secrets))[:200]}")
    def failure(message, code, seconds=None):
        if details:
            suffix = "\n上游返回（已脱敏）：\n" + "\n".join(details)
        else:
            suffix = "\n上游返回：空响应体。" if not response.content else "\n上游返回：响应体未包含可展示的错误字段。"
        suffix += "\n响应诊断：\n" + "\n".join(diagnostics)
        if request_id:
            suffix += f"\n请求 ID：{request_id}"
        error = OpenAICompatibleError(message + suffix, code, seconds)
        error.request_id = request_id
        return error
    if response.status_code == 429:
        try:
            error = response.json().get("error", {})
            quota = {"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached",
                     "organization_spend_limit_exceeded", "project_spend_limit_exceeded", "organization_usage_limit_exceeded"}
            exhausted = isinstance(error, dict) and any(error.get(key) in quota for key in ("code", "type") if isinstance(error.get(key), str))
        except (ValueError, AttributeError):
            exhausted = False
        if exhausted:
            raise failure("模型平台返回 HTTP 429：额度或余额不足，已暂停此凭据；请检查中转站额度并在管理后台更新凭据后重试", "QUOTA_EXCEEDED")
        seconds = _retry_after(response.headers.get("retry-after"))
        raise failure(f"模型平台返回 HTTP 429：请求受限，已暂停此凭据 {seconds} 秒；稍后手动重试", "RATE_LIMITED", seconds)
    code = "AUTH_FAILED" if response.status_code in {401, 403} else "PROVIDER_UNAVAILABLE"
    # Providers may echo Authorization or private request text in their errors.
    raise failure(f"模型平台返回 HTTP {response.status_code}", code)


def _retry_after(value: str | None) -> int:
    if not value:
        return 60
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            seconds = (date.replace(tzinfo=date.tzinfo or UTC) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return 60
    return max(1, math.ceil(seconds)) if math.isfinite(seconds) and seconds <= 31536000 else 60
