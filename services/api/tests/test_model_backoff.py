from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from vediogen_api import gateway
from vediogen_api.database import SessionLocal
from vediogen_api.models import ModelCooldownRow, ModelDeploymentRow, ModelInvocationRow, RoutingVersionRow
from vediogen_api.openai_compatible import OpenAICompatibleError


def configure(fallback_on, max_attempts=2):
    with SessionLocal() as session:
        route = session.scalar(select(RoutingVersionRow))
        primary = session.get(ModelDeploymentRow, route.bindings[0]["primaryDeploymentId"])
        fallback = ModelDeploymentRow(id=str(uuid4()), display_name="Backup", provider_id=primary.provider_id,
            physical_model_id="fixture-backup", credential_id=primary.credential_id, capabilities=primary.capabilities, status="ready")
        session.add(fallback)
        route.bindings = [{**route.bindings[0], "fallbackDeploymentIds": [fallback.id],
                           "fallbackOn": fallback_on, "maxAttempts": max_attempts}]
        session.commit()
        return primary.credential_id


def invoke(call, capability="creative-advisor"):
    with SessionLocal() as session:
        result = gateway._invoke_routed(session, capability, "isolated-project", "Isolated", call, None)
        session.commit()
        return result


def test_rate_limit_stops_fallback_and_cooldown_covers_other_capabilities(client):
    credential_id = configure(["RATE_LIMITED", "PROVIDER_UNAVAILABLE"])
    calls = []
    def limited():
        calls.append(1)
        raise OpenAICompatibleError("HTTP 429", "RATE_LIMITED", 90)
    with pytest.raises(gateway.ModelGatewayError) as first:
        invoke(limited)
    assert first.value.code == "RATE_LIMITED"
    with pytest.raises(gateway.ModelGatewayError, match="未发送请求"):
        invoke(limited, "asset-planner")
    with SessionLocal() as session:
        rows = list(session.scalars(select(ModelInvocationRow)))
        assert len(rows) == 1 and rows[0].status == "failed" and rows[0].error_code == "RATE_LIMITED"
        cooldown = session.get(ModelCooldownRow, credential_id)
        assert cooldown is not None
        cooldown.blocked_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert calls == [1]
    assert invoke(lambda: {"recovered": True}) == {"recovered": True}


@pytest.mark.parametrize("fallback_on,max_attempts,expected", [([], 2, 1), (["PROVIDER_UNAVAILABLE"], 1, 1), (["PROVIDER_UNAVAILABLE"], 2, 2)])
def test_routing_honors_fallback_policy_and_attempt_limit(client, fallback_on, max_attempts, expected):
    configure(fallback_on, max_attempts)
    calls = []
    def fail_once():
        calls.append(1)
        if len(calls) == 1:
            raise OpenAICompatibleError("HTTP 503", "PROVIDER_UNAVAILABLE")
        return {"ok": True}
    if expected == 1:
        with pytest.raises(gateway.ModelGatewayError):
            invoke(fail_once)
    else:
        assert invoke(fail_once) == {"ok": True}
    assert len(calls) == expected


def test_quota_pause_persists_until_credential_rotation(client):
    cid = configure(["QUOTA_EXCEEDED"])
    def quota():
        raise OpenAICompatibleError("Quota exhausted", "QUOTA_EXCEEDED")
    with pytest.raises(gateway.ModelGatewayError):
        invoke(quota)
    with pytest.raises(gateway.ModelGatewayError, match="额度"):
        invoke(lambda: pytest.fail("No upstream calls while quota is exhausted"))
    with SessionLocal() as session:
        assert session.get(ModelCooldownRow, cid).blocked_until is None
    assert client.post(f"/api/v1/admin/model-credentials/{cid}/rotation", json={"secret": "isolated-new-test-key"}).status_code == 200
    assert invoke(lambda: {"ok": True}) == {"ok": True}


def test_advisor_returns_429_and_refresh_does_not_call_provider_again(client, monkeypatch):
    configure([])
    calls = []
    def limited(*args):
        calls.append(1)
        raise OpenAICompatibleError("HTTP 429: wait 120 seconds", "RATE_LIMITED", 120)
    monkeypatch.setattr(gateway, "build_advisor_result", limited)
    pid = client.post("/api/v1/projects", json={"title": "Rate limit", "initialMessage": "Motorcycle"}).json()["id"]
    url = f"/api/v1/projects/{pid}/advisor-runs"
    first = client.post(url)
    assert first.status_code == 429 and first.headers["retry-after"] == "120"
    second = client.post(url)
    assert second.status_code == 429 and "未发送请求" in second.json()["detail"]
    assert calls == [1]


def test_admin_displays_pause_and_probes_cannot_bypass_it(client, monkeypatch):
    from vediogen_api import admin
    cid = configure([])
    def quota():
        raise OpenAICompatibleError("Quota exhausted", "QUOTA_EXCEEDED")
    with pytest.raises(gateway.ModelGatewayError):
        invoke(quota)
    credentials = client.get("/api/v1/admin/model-credentials").json()["items"]
    assert credentials[0]["cooldown"]["errorCode"] == "QUOTA_EXCEEDED"
    deployments = client.get("/api/v1/admin/model-deployments").json()["items"]
    assert all(row["cooldown"]["errorCode"] == "QUOTA_EXCEEDED" for row in deployments)
    monkeypatch.setattr(admin, "_probe_deployment", lambda *args: pytest.fail("A probe bypassed cooldown"))
    assert client.post(f"/api/v1/admin/model-deployments/{deployments[0]['id']}/probe").status_code == 429
    assert client.post(f"/api/v1/admin/model-credentials/{cid}/probe").status_code == 429
    assert client.post(f"/api/v1/admin/model-credentials/{cid}/cooldown-reset").status_code == 200
    assert invoke(lambda: {"ok": True}) == {"ok": True}


def test_manual_reset_does_not_shorten_rate_limit_retry_after(client):
    cid = configure([])
    with SessionLocal() as session:
        session.add(ModelCooldownRow(credential_id=cid, error_code="RATE_LIMITED", blocked_until=datetime.now(UTC) + timedelta(seconds=120)))
        session.commit()
    response = client.post(f"/api/v1/admin/model-credentials/{cid}/cooldown-reset")
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


def test_background_script_stops_on_429_without_scheduling_matcher(client, monkeypatch):
    from test_storyboard_jobs import setup_brief, wait
    from vediogen_api import storyboard_jobs
    pid = setup_brief(client)
    calls = []
    def limited(*args):
        calls.append(1)
        raise OpenAICompatibleError("HTTP 429", "RATE_LIMITED", 120)
    monkeypatch.setattr(gateway, "build_storyboard", limited)
    monkeypatch.setattr(storyboard_jobs, "assign_assets", lambda *args: pytest.fail("A downstream stage ran after HTTP 429"))
    url = f"/api/v1/projects/{pid}/storyboard-runs?background=true"
    assert client.post(url).status_code == 202
    run = wait(client, pid)
    assert run["status"] == "failed" and run["errorCode"] == "RATE_LIMITED"
    assert run["storyboardVersionId"] is None
    assert "matching-assets" not in [event["phase"] for event in run["events"]]
    client.post(url)
    assert wait(client, pid)["status"] == "failed"
    assert calls == [1]


def test_restart_marks_unfinished_invocations_terminal_without_clearing_cooldowns(client):
    from vediogen_api.model_backoff import recover_interrupted_calls
    cid = configure([])
    with SessionLocal() as session:
        row = ModelInvocationRow(id=str(uuid4()), capability_alias="creative-advisor", routing_policy_version_id="test",
            deployment_id="test", credential_id=cid, status="calling")
        session.add(row)
        session.add(ModelCooldownRow(credential_id=cid, error_code="QUOTA_EXCEEDED", blocked_until=None))
        session.commit()
        recover_interrupted_calls(session)
        assert row.status == "failed" and row.error_code == "SERVICE_INTERRUPTED"
        assert session.get(ModelCooldownRow, cid).error_code == "QUOTA_EXCEEDED"
