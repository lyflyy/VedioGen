from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from vediogen_api.database import SessionLocal
from vediogen_api.models import DocumentRow, ModelDeploymentRow, ModelInvocationRow, ProjectRow
from vediogen_api.openai_compatible import OpenAICompatibleError, _raise_for_status


def create(client, title="Management test"):
    return client.post("/api/v1/projects", json={"title": title, "initialMessage": "展示摩托车"}).json()["id"]


def test_filters_search_and_pagination_include_old_records(client):
    ids = [create(client, f"FilterTest-{i:02}") for i in range(23)]
    with SessionLocal() as session:
        session.get(ProjectRow, ids[0]).status = "completed"
        session.get(ProjectRow, ids[1]).status = "generating"
        session.commit()
    page = client.get("/api/v1/projects?query=FilterTest&pageSize=20").json()
    assert page["total"] == 23 and len(page["items"]) == 20 and page["nextCursor"] == 20
    assert len(client.get("/api/v1/projects?query=FilterTest&offset=20").json()["items"]) == 3
    assert client.get("/api/v1/projects?query=FilterTest&status=pending").json()["total"] == 21
    assert client.get("/api/v1/projects?query=FilterTest&status=generating").json()["items"][0]["id"] == ids[1]
    assert client.get("/api/v1/projects?query=FilterTest&status=completed").json()["items"][0]["id"] == ids[0]


def test_delete_restore_preserves_records_and_blocks_workspace(client):
    pid = create(client)
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 200
    assert pid not in [row["id"] for row in client.get("/api/v1/projects").json()["items"]]
    assert pid in [row["id"] for row in client.get("/api/v1/projects?status=deleted").json()["items"]]
    assert client.get(f"/api/v1/projects/{pid}/workspace").status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/advisor-runs").status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/restoration").json()["status"] == "intake"
    assert client.get(f"/api/v1/projects/{pid}/workspace").json()["messages"]


def test_delete_refuses_active_model_or_preparation(client):
    pid = create(client)
    with SessionLocal() as session:
        session.add(DocumentRow(id=str(uuid4()), project_id=pid, kind="storyboard-run", version=1, status="running", data={}))
        session.commit()
    assert client.delete(f"/api/v1/projects/{pid}").status_code == 409
    assert client.get(f"/api/v1/projects/{pid}").status_code == 200
    assert pid in [row["id"] for row in client.get("/api/v1/projects?status=generating").json()["items"]]
    assert pid not in [row["id"] for row in client.get("/api/v1/projects?status=pending").json()["items"]]


def test_activity_is_project_scoped_and_omits_private_payload(client):
    pid, other = create(client), create(client)
    with SessionLocal() as session:
        deployment = session.scalar(select(ModelDeploymentRow))
        for project_id in (pid, other):
            session.add(ModelInvocationRow(id=str(uuid4()), project_id=project_id, capability_alias="creative-advisor",
                routing_policy_version_id="route", deployment_id=deployment.id, credential_id="secret-ref-should-not-return",
                status="failed", error_code="RATE_LIMITED", redacted_input="private-input-should-not-return",
                redacted_output="HTTP 429: request limit reached", provider_request_id="req-test", provider_model_id="test-gpt"))
        session.commit()
    response = client.get(f"/api/v1/projects/{pid}/activity?category=model")
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["model"] == "test-gpt"
    assert data["items"][0]["requestId"] == "req-test"
    assert "private-input" not in response.text and "secret-ref" not in response.text


def test_upstream_error_keeps_reason_and_request_id_but_redacts_secrets():
    request = httpx.Request("POST", "https://relay.test/v1/chat/completions", headers={"Authorization": "Bearer actual-private-key"},
        json={"messages": [{"role": "user", "content": "private customer input"}]})
    response = httpx.Response(429, request=request, headers={"x-request-id": "req-429", "retry-after": "75"},
        json={"error": {"message": "Rate limit for gpt-test; actual-private-key; private customer input; sk-leaked-token", "code": "rpm_limit", "type": "rate_limit_error"}, "extra": "not-whitelisted"})
    with pytest.raises(OpenAICompatibleError) as caught:
        _raise_for_status(response)
    message = str(caught.value)
    assert "Rate limit for gpt-test" in message and "rpm_limit" in message and "rate_limit_error" in message
    assert caught.value.request_id == "req-429" and caught.value.retry_after_seconds == 75
    assert not any(text in message for text in ("actual-private-key", "private customer input", "sk-leaked-token", "not-whitelisted"))


def test_activity_capability_filter_runs_before_pagination(client):
    pid = create(client)
    assert client.post(f"/api/v1/projects/{pid}/advisor-runs").status_code == 202
    with SessionLocal() as session:
        deployment = session.scalar(select(ModelDeploymentRow))
        session.add(ModelInvocationRow(id=str(uuid4()), project_id=pid, capability_alias="storyboard-generator",
            routing_policy_version_id="route", deployment_id=deployment.id, credential_id="private-key-ref", status="calling"))
        session.commit()
    data = client.get(f"/api/v1/projects/{pid}/activity?category=model&capabilityAlias=creative-advisor&pageSize=1").json()
    assert data["total"] == 1 and data["items"][0]["title"] == "creative-advisor"
    assert data["items"][0]["status"] == "succeeded"


@pytest.mark.parametrize("body", [[], None, "error"])
def test_unstructured_error_payload_does_not_crash(body):
    with pytest.raises(OpenAICompatibleError, match="HTTP 429"):
        _raise_for_status(httpx.Response(429, json=body))
