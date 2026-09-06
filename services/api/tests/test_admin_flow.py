from uuid import uuid4


def test_admin_can_configure_probe_publish_and_trace_without_secret_echo(client):
    provider_id = f"provider-{uuid4().hex[:8]}"
    provider = client.post(
        "/api/v1/admin/model-providers",
        json={
            "id": provider_id,
            "displayName": "OpenAI compatible test",
            "adapterType": "fake",
            "baseUrl": "https://models.example.test/v1",
            "region": "cn-test",
            "enabled": True,
        },
    )
    assert provider.status_code == 201

    secret = "sk-test-never-return-4829"
    credential = client.post(
        "/api/v1/admin/model-credentials",
        json={"providerId": provider_id, "alias": "E2E test key", "secret": secret},
    )
    assert credential.status_code == 201
    assert secret not in credential.text
    credential_body = credential.json()
    assert credential_body["lastFour"] == "4829"
    assert client.post(f"/api/v1/admin/model-credentials/{credential_body['id']}/probe").status_code == 200

    deployment = client.post(
        "/api/v1/admin/model-deployments",
        json={
            "displayName": "Creative model test",
            "providerId": provider_id,
            "physicalModelId": "creative-v1",
            "credentialId": credential_body["id"],
            "capabilities": ["text", "structured-output", "zh-CN"],
            "timeoutSeconds": 60,
            "maxContextTokens": 32000,
        },
    )
    assert deployment.status_code == 201
    deployment_id = deployment.json()["id"]
    assert client.post(f"/api/v1/admin/model-deployments/{deployment_id}/probe").json()["status"] == "passed"

    binding = {
        "capabilityAlias": "creative-advisor",
        "requirements": ["text", "structured-output", "zh-CN"],
        "primaryDeploymentId": deployment_id,
        "fallbackDeploymentIds": [],
        "timeoutSeconds": 60,
        "maxAttempts": 2,
        "budgetClass": "low",
        "fallbackOn": ["TIMEOUT", "PROVIDER_UNAVAILABLE"],
    }
    draft = client.post("/api/v1/admin/model-routing/drafts", json={"bindings": [binding]})
    assert draft.status_code == 201
    draft_id = draft.json()["id"]
    assert client.post(f"/api/v1/admin/model-routing/{draft_id}/validation").json()["status"] == "completed"
    published = client.post(
        f"/api/v1/admin/model-routing/{draft_id}/publication",
        json={"changeNote": "E2E provider switch"},
    )
    assert published.status_code == 201

    run = client.post(
        "/api/v1/admin/model-playground-runs",
        json={
            "capabilityAlias": "creative-advisor",
            "routeTarget": "published",
            "fixtureId": "zhangxue-800x",
            "checks": ["authentication", "structured-output", "zh-CN"],
        },
    )
    assert run.status_code == 202
    assert all(item["status"] == "passed" for item in run.json()["checks"])

    invocations = client.get("/api/v1/admin/model-invocations?capabilityAlias=creative-advisor").json()["items"]
    assert invocations
    detail = client.get(f"/api/v1/admin/model-invocations/{invocations[0]['id']}")
    assert detail.status_code == 200
    assert secret not in detail.text
    assert detail.json()["routeChain"]
