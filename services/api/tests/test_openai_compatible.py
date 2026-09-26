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


def test_html_502_preserves_gateway_diagnostics_without_echoing_private_data():
    request = httpx.Request('POST', 'https://relay.test/v1/chat/completions?key=private-query',
        headers={'Authorization': 'Bearer private-key'},
        json={'messages': [{'role': 'user', 'content': 'private customer prompt'}]})
    response = httpx.Response(502, request=request,
        headers={'content-type': 'text/html', 'server': 'cloudflare', 'cf-ray': 'ray-test', 'x-request-id': 'req-502', 'set-cookie': 'private-cookie'},
        text='<html><head><title>502 Bad Gateway</title><style>private-style</style></head>'
             '<body>Upstream connection reset. private-key private customer prompt'
             '<script>private-script</script><img src="data:image/png;base64,cHJpdmF0ZQ=="></body></html>')
    with pytest.raises(OpenAICompatibleError) as caught:
        openai_compatible._raise_for_status(response)
    message = str(caught.value)
    assert '502 Bad Gateway' in message and 'Upstream connection reset' in message
    assert 'POST https://relay.test/v1/chat/completions' in message
    assert 'cf-ray：ray-test' in message and '响应体字节数' in message
    assert caught.value.request_id == 'req-502'
    assert not any(secret in message for secret in ['private-query', 'private-key', 'private customer prompt', 'private-style', 'private-script', 'private-cookie', 'cHJpdmF0ZQ=='])


@pytest.mark.parametrize('content_type,body,expected', [
    ('text/plain', 'upstream reset', 'upstream reset'),
    ('', 'Bad Gateway', 'Bad Gateway'),
    ('application/json', '{"detail":"upstream timeout"}', 'upstream timeout'),
    ('application/json', '"service unavailable"', 'service unavailable'),
    ('application/json', '{"private":"not-whitelisted"}', '响应体未包含可展示的错误字段'),
    ('text/html', '', '空响应体'),
])
def test_nonstandard_gateway_error_body_is_not_silently_dropped(content_type, body, expected):
    response = httpx.Response(502, headers={'content-type': content_type}, text=body)
    with pytest.raises(OpenAICompatibleError) as caught:
        openai_compatible._raise_for_status(response)
    assert expected in str(caught.value)
    assert '响应诊断' in str(caught.value)
    assert 'not-whitelisted' not in str(caught.value)


def test_html_error_text_is_bounded_and_redacts_embedded_data():
    response = httpx.Response(502, headers={'content-type': 'text/html'},
        text='<p>data:image/png;base64,cHJpdmF0ZQ== ' + 'A' * 10000 + '</p>')
    with pytest.raises(OpenAICompatibleError) as caught:
        openai_compatible._raise_for_status(response)
    assert len(str(caught.value)) < 1600
    assert 'cHJpdmF0ZQ==' not in str(caught.value)


@pytest.mark.parametrize('error_type,stage,limit', [
    (httpx.ReadTimeout, '等待响应数据', 300),
    (httpx.ConnectTimeout, '建立连接', 20),
    (httpx.WriteTimeout, '发送请求数据', 60),
    (httpx.PoolTimeout, '等待连接池', 20),
])
def test_timeout_diagnostics_identify_stage_without_retry_or_secret_leak(monkeypatch, error_type, stage, limit):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.extensions['timeout'] == {'connect': 20, 'read': 300, 'write': 60, 'pool': 20}
        raise error_type('private-provider-detail api-key-private', request=request)
    install_transport(monkeypatch, handler)
    with pytest.raises(OpenAICompatibleError) as caught:
        complete_json(base_url='https://relay.test/v1', api_key='api-key-private', model_id='gpt-test',
            schema_name='test', schema={'type': 'object'}, system_prompt='private-system', user_prompt='private-user', timeout_seconds=300)
    assert caught.value.code == 'TIMEOUT'
    assert f'{stage}超过 {limit} 秒' in str(caught.value)
    assert error_type.__name__ in str(caught.value)
    assert 'POST https://relay.test/v1/chat/completions' in str(caught.value)
    assert 'private' not in str(caught.value)
    assert len(calls) == 1


def stream_completion(monkeypatch, chunks, done=True):
    def handler(request):
        body = json.loads(request.content)
        assert body['stream'] is True and body['stream_options']['include_usage'] is True
        assert body['response_format']['json_schema']['strict'] is True
        text = ': heartbeat\n\n' + ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks)
        if done:
            text += 'data: [DONE]\n\n'
        return httpx.Response(200, headers={'content-type': 'text/event-stream', 'x-request-id': 'stream-request'}, text=text)
    install_transport(monkeypatch, handler)
    return complete_json(base_url='https://relay.test/v1', api_key='private-key', model_id='gpt-test',
        schema_name='test', schema={'type': 'object'}, system_prompt='private-system', user_prompt='private-user', stream=True)


def test_streaming_assembles_only_answer_and_records_usage(monkeypatch):
    result = stream_completion(monkeypatch, [
        {'id': 'completion-stream', 'model': 'gpt-actual', 'choices': [{'index': 0, 'delta': {'reasoning_content': 'do not expose thoughts'}}]},
        {'choices': [{'index': 0, 'delta': {'content': '{"answer":'}}]},
        {'choices': [{'index': 0, 'delta': {'content': '"ok"}'}, 'finish_reason': 'stop'}]},
        {'choices': [], 'usage': {'prompt_tokens': 12, 'completion_tokens': 20}},
    ])
    assert result.value == {'answer': 'ok'}
    assert result.model_id == 'gpt-actual' and result.request_id == 'stream-request'
    assert (result.input_tokens, result.output_tokens) == (12, 20)


@pytest.mark.parametrize('reason,done', [('stop', False), ('length', True), (None, True)])
def test_streaming_never_accepts_partial_or_truncated_script(monkeypatch, reason, done):
    with pytest.raises(OpenAICompatibleError) as caught:
        stream_completion(monkeypatch, [{'choices': [{'delta': {'content': '{"ok":true}'}, 'finish_reason': reason}]}], done)
    assert caught.value.code == 'SCHEMA_INVALID'
    assert caught.value.request_id == 'stream-request'


def test_streaming_error_redacts_inputs_and_preserves_rate_limit(monkeypatch):
    with pytest.raises(OpenAICompatibleError) as caught:
        stream_completion(monkeypatch, [{'error': {'type': 'rate_limit_error', 'message': 'Limited: private-key private-system private-user'}}])
    assert caught.value.code == 'RATE_LIMITED' and caught.value.retry_after_seconds == 60
    assert 'private' not in str(caught.value)


def test_stream_budget_also_checks_heartbeat_only_data(monkeypatch):
    ticks = iter([0, 61])
    monkeypatch.setattr(openai_compatible, 'monotonic', lambda: next(ticks))
    with pytest.raises(OpenAICompatibleError) as caught:
        stream_completion(monkeypatch, [], done=False)
    assert caught.value.code == 'TIMEOUT'
