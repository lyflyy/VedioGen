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
        return httpx.Response(401, json={"error": {"message": "invalid credential"}})

    install_transport(monkeypatch, handler)
    with pytest.raises(OpenAICompatibleError) as captured:
        list_models("https://relay.example/v1", "never-log-this-secret")
    assert captured.value.code == "AUTH_FAILED"
    assert "never-log-this-secret" not in str(captured.value)
