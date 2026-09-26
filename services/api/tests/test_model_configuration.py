from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from vediogen_api import admin, gateway
from vediogen_api.config import get_settings
from vediogen_api.database import SessionLocal
from vediogen_api.models import ModelCooldownRow, ModelDeploymentRow, RoutingVersionRow
from vediogen_api.openai_compatible import StructuredCompletion


def configured(client):
    pid = "config-" + uuid4().hex[:8]
    assert client.post("/api/v1/admin/model-providers", json={"id": pid, "displayName": "Config", "adapterType": "fake", "baseUrl": "https://old.example/v1"}).status_code == 201
    key = client.post("/api/v1/admin/model-credentials", json={"providerId": pid, "alias": "Key", "secret": "original-test-key"}).json()
    model = client.post("/api/v1/admin/model-deployments", json={"displayName": "Model", "providerId": pid, "physicalModelId": "old-model", "credentialId": key["id"], "capabilities": ["text", "structured-output", "zh-CN"]}).json()
    assert client.post(f"/api/v1/admin/model-deployments/{model['id']}/probe").status_code == 200
    return pid, key["id"], model["id"]


def models(client):
    return {row["id"]: row for row in client.get("/api/v1/admin/model-deployments").json()["items"]}


def test_rename_preserves_readiness_but_connection_changes_invalidate(client):
    pid, kid, mid = configured(client)
    assert client.patch(f"/api/v1/admin/model-providers/{pid}", json={"displayName": "Renamed"}).status_code == 200
    assert client.patch(f"/api/v1/admin/model-deployments/{mid}", json={"displayName": "Renamed model"}).json()["status"] == "ready"
    assert client.patch(f"/api/v1/admin/model-credentials/{kid}", json={"alias": "Renamed key"}).status_code == 200
    assert models(client)[mid]["status"] == "ready"
    assert client.patch(f"/api/v1/admin/model-providers/{pid}", json={"baseUrl": "https://new.example/v1/"}).json()["baseUrl"] == "https://new.example/v1"
    assert models(client)[mid]["status"] == "draft"


def test_key_rotation_is_write_only_and_same_key_does_not_reset_cooldown(client):
    pid, kid, mid = configured(client)
    with SessionLocal() as session:
        session.add(ModelCooldownRow(credential_id=kid, error_code="RATE_LIMITED", blocked_until=datetime.now(UTC) + timedelta(seconds=90)))
        session.commit()
    response = client.patch(f"/api/v1/admin/model-credentials/{kid}", json={"secret": "original-test-key"})
    assert response.status_code == 200 and "original-test-key" not in response.text
    with SessionLocal() as session:
        assert session.get(ModelCooldownRow, kid)
    response = client.patch(f"/api/v1/admin/model-credentials/{kid}", json={"secret": "replacement-test-secret"})
    assert response.status_code == 200 and "replacement-test-secret" not in response.text
    assert models(client)[mid]["status"] == "draft"
    with SessionLocal() as session:
        assert not session.get(ModelCooldownRow, kid)


@pytest.mark.parametrize("payload", [{"timeoutSeconds": 0}, {"maxContextTokens": -1}, {"capabilities": []}, {"status": "ready"}, {"physicalModelId": ""}])
def test_invalid_model_edit_is_atomic(client, payload):
    _, _, mid = configured(client)
    before = models(client)[mid]
    assert client.patch(f"/api/v1/admin/model-deployments/{mid}", json=payload).status_code == 422
    assert models(client)[mid] == before


def test_model_can_switch_platform_only_with_matching_key(client):
    _, _, mid = configured(client)
    other, other_key, _ = configured(client)
    assert client.patch(f"/api/v1/admin/model-deployments/{mid}", json={"credentialId": other_key}).status_code == 422
    changed = client.patch(f"/api/v1/admin/model-deployments/{mid}", json={"providerId": other, "credentialId": other_key}).json()
    assert changed["providerId"] == other and changed["status"] == "draft"


def test_updated_address_key_and_model_reach_probe_and_gateway(client, monkeypatch):
    pid, kid, mid = configured(client)
    monkeypatch.setattr(get_settings(), "allow_external_models", True)
    client.patch(f"/api/v1/admin/model-providers/{pid}", json={"adapterType": "openai-compatible", "baseUrl": "https://changed.example/v1"})
    client.patch(f"/api/v1/admin/model-credentials/{kid}", json={"secret": "new-runtime-key"})
    client.patch(f"/api/v1/admin/model-deployments/{mid}", json={"physicalModelId": "new-runtime-model", "timeoutSeconds": 90})
    seen = []
    def listing(url, secret, timeout):
        assert (url, secret) == ("https://changed.example/v1", "new-runtime-key")
        return ["new-runtime-model"], 1
    def probe(url, secret, model, timeout):
        assert (url, secret, model, timeout) == ("https://changed.example/v1", "new-runtime-key", "new-runtime-model", 90)
        seen.append("probe")
        return StructuredCompletion({"ok": True}, "req", model, 1, 1, 1)
    monkeypatch.setattr(admin, "list_models", listing)
    monkeypatch.setattr(admin, "probe_structured_output", probe)
    assert client.post(f"/api/v1/admin/model-deployments/{mid}/probe").status_code == 200
    with SessionLocal() as session:
        route = session.scalar(select(RoutingVersionRow).where(RoutingVersionRow.status == "published"))
        route.bindings = [{"capabilityAlias": "creative-advisor", "primaryDeploymentId": mid}]
        session.commit()
        def real(provider, deployment, secret):
            assert (provider.base_url, deployment.physical_model_id, secret) == ("https://changed.example/v1", "new-runtime-model", "new-runtime-key")
            seen.append("gateway")
            return {"ok": True}, StructuredCompletion({"ok": True}, "request", deployment.physical_model_id, 1, 1, 1)
        assert gateway._invoke_routed(session, "creative-advisor", "test-project", "Test", lambda: pytest.fail("Wrong adapter"), real) == {"ok": True}
    assert seen == ["probe", "gateway"]


@pytest.mark.parametrize("url", ["file:///tmp/test", "https://user:pass@example.com/v1", "https://example.com/v1?key=test", "https://example.com/v1/chat/completions"])
def test_invalid_base_url_is_rejected(client, url):
    pid, _, _ = configured(client)
    assert client.patch(f"/api/v1/admin/model-providers/{pid}", json={"baseUrl": url}).status_code == 422
