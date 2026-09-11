import json

import httpx
import pytest

from vediogen_api import openai_compatible
from vediogen_api.openai_compatible import OpenAICompatibleError, complete_json, list_models


def install_transport(monkeypatch, handler):
    original_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(openai_compatible.httpx, "Client", lambda *args, **kwargs: original_client(transport=transport, timeout=kwargs.get("timeout")))


def test_openai_compatible_lists_models_and_sends_bearer_auth(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://relay.example/v1/models"
        assert request.headers["authorization"] == "Bearer secret-value"
        return httpx.Response(200, json={"data": [{"id": "creative-model"}, {"id": "image-model"}]})

    install_transport(monkeypatch, handler)
    models, duration_ms = list_models("https://relay.example/v1", "secret-value")
    assert models == ["creative-model", "image-model"]
    assert duration_ms >= 0


def test_structured_completion_sends_schema_and_image_and_records_usage(monkeypatch, tmp_path):
    image = tmp_path / "reference.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer"],
        "properties": {"answer": {"type": "string"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://relay.example/v1/chat/completions"
        body = json.loads(request.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["response_format"]["json_schema"]["schema"] == schema
        image_part = body["messages"][1]["content"][1]
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            headers={"x-request-id": "request-real-123"},
            json={
                "id": "completion-1",
                "model": "creative-model-actual",
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": 17, "completion_tokens": 5},
            },
        )

    install_transport(monkeypatch, handler)
    result = complete_json(
        base_url="https://relay.example/v1",
        api_key="secret-value",
        model_id="creative-model",
        schema_name="test_schema",
        schema=schema,
        system_prompt="system",
        user_prompt="user",
        image_assets=[{"mimeType": "image/png", "uri": str(image)}],
    )
    assert result.value == {"answer": "ok"}
    assert result.request_id == "request-real-123"
    assert result.model_id == "creative-model-actual"
    assert (result.input_tokens, result.output_tokens) == (17, 5)


def test_provider_error_is_sanitized_without_credential(monkeypatch):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid credential: Authorization Bearer never-log-this-secret"}})

    install_transport(monkeypatch, handler)
    with pytest.raises(OpenAICompatibleError) as captured:
        list_models("https://relay.example/v1", "never-log-this-secret")
    assert captured.value.code == "AUTH_FAILED"
    assert "never-log-this-secret" not in str(captured.value)


@pytest.mark.parametrize("header,expected", [("120", 120), ("1.5", 2), (None, 60), ("invalid", 60), ("NaN", 60), ("-10", 1)])
def test_429_is_classified_without_retries_or_error_body_leak(monkeypatch, header, expected):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": header} if header else {},
                              json={"error": {"message": "never-log-this-secret", "code": "rate_limit_exceeded"}})
    install_transport(monkeypatch, handler)
    with pytest.raises(OpenAICompatibleError) as caught:
        list_models("https://relay.example/v1", "never-log-this-secret")
    assert caught.value.code == "RATE_LIMITED"
    assert caught.value.retry_after_seconds == expected
    assert "never-log-this-secret" not in str(caught.value)
    assert len(calls) == 1


def test_retry_after_http_date():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime
    header = format_datetime(datetime.now(UTC) + timedelta(seconds=90), usegmt=True)
    assert 89 <= openai_compatible._retry_after(header) <= 90


@pytest.mark.parametrize("code", ["insufficient_quota", "credit_balance_exhausted", "project_spend_limit_exceeded"])
def test_quota_exhaustion_does_not_promise_time_based_recovery(code):
    with pytest.raises(OpenAICompatibleError) as caught:
        openai_compatible._raise_for_status(httpx.Response(429, json={"error": {"code": code}}))
    assert caught.value.code == "QUOTA_EXCEEDED"
    assert caught.value.retry_after_seconds is None
