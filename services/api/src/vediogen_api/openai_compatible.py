import base64
import json
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

import httpx


class OpenAICompatibleError(RuntimeError):
    def __init__(self, message: str, code: str = "PROVIDER_ERROR") -> None:
        super().__init__(message)
        self.code = code


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
    started = monotonic()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(_url(base_url, "chat/completions"), headers=_headers(api_key), json=body)
            _raise_for_status(response)
            payload = response.json()
    except OpenAICompatibleError:
        raise
    except httpx.TimeoutException as error:
        raise OpenAICompatibleError("模型调用超时", "TIMEOUT") from error
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


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    code = "AUTH_FAILED" if response.status_code in {401, 403} else "PROVIDER_UNAVAILABLE"
    detail = ""
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
        elif error:
            detail = str(error)
    except ValueError:
        pass
    suffix = f"：{detail[:240]}" if detail else ""
    raise OpenAICompatibleError(f"模型平台返回 HTTP {response.status_code}{suffix}", code)
