import json
import threading
import time

import httpx
import pytest

from vediogen_api import fal_video, generation
from vediogen_api.config import get_settings
from vediogen_api.database import SessionLocal
from vediogen_api.media import create_preview_video
from vediogen_api.models import DocumentRow, GenerationRunRow
from test_creator_flow import wait_generation
from test_media_generation import prepared


def configure(client, budget="2"):
    assert client.post("/api/v1/admin/model-providers", json={"id": "fal-test", "displayName": "fal test",
        "adapterType": "fal-video", "baseUrl": fal_video.BASE_URL}).status_code == 201
    credential = client.post("/api/v1/admin/model-credentials", json={"providerId": "fal-test", "alias": "test",
        "secret": "test-only-not-a-real-key"}).json()
    deployment = client.post("/api/v1/admin/model-deployments", json={"providerId": "fal-test", "displayName": "Kling test",
        "credentialId": credential["id"], "physicalModelId": fal_video.MODEL_ID, "capabilities": ["image-to-video"]}).json()
    response = client.put("/api/v1/admin/video-settings", json={"enabled": True, "deploymentId": deployment["id"],
        "estimatedUsdPerSecond": "0.1", "maxRunUsd": budget})
    assert response.status_code == 200, response.text
    return deployment, credential


def prepare_video(client):
    project_id, storyboard_id, shots = prepared(client)
    shots[0].update(sourceStrategy="image-to-video", durationMs=5000, videoPrompt="缓慢侧向环绕，保持车型外观，不更换车标")
    with SessionLocal() as session:
        row = session.get(DocumentRow, storyboard_id)
        row.data = {**row.data, "shots": shots}
        session.commit()
    return {"projectId": project_id, "storyboardVersionId": storyboard_id, "quality": "preview", "confirmVideoCost": True}, shots


def wait_idle(run_id):
    for _ in range(200):
        if not generation.worker_has_run(run_id):
            return
        time.sleep(0.025)
    pytest.fail("worker did not finish")


@pytest.fixture
def vendor(monkeypatch, tmp_path):
    clip = tmp_path / "provider-result.mp4"
    create_preview_video(clip, 5)
    content = clip.read_bytes()
    state = {"posts": 0, "polls": 0, "timeoutSubmit": False, "failPoll": False, "reject": False}
    real_client = httpx.Client
    def handler(request):
        if request.url.host == "v3.fal.media":
            assert "authorization" not in request.headers
            return httpx.Response(200, content=content)
        assert request.url.host == "queue.fal.run"
        assert request.headers["authorization"] == "Key test-only-not-a-real-key"
        if request.method == "POST":
            state["posts"] += 1
            if state["timeoutSubmit"]:
                raise httpx.ReadTimeout("test-only-not-a-real-key", request=request)
            if state["reject"]:
                return httpx.Response(422, json={"error": "test-only-not-a-real-key"})
            body = json.loads(request.content)
            assert body["image_url"].startswith("data:image/jpeg;base64,")
            assert body["duration"] == "5"
            request_id = f"request-{state['posts']}"
            base = f"{fal_video.BASE_URL}/fal-ai/kling-video/requests/{request_id}"
            return httpx.Response(200, json={"request_id": request_id, "status_url": base + "/status",
                "response_url": base, "cancel_url": base + "/cancel"})
        if request.url.path.endswith("/status"):
            state["polls"] += 1
            if state["failPoll"]:
                raise httpx.ReadTimeout("not safe to echo", request=request)
            return httpx.Response(200, json={"status": "COMPLETED"})
        return httpx.Response(200, json={"video": {"url": "https://v3.fal.media/files/result.mp4"}})
    monkeypatch.setattr(fal_video.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(get_settings(), "allow_external_models", True)
    return state


def test_video_configuration_does_not_bill_or_claim_probe_passed(client):
    deployment, credential = configure(client)
    assert client.post(f"/api/v1/admin/model-credentials/{credential['id']}/probe").json()["status"] == "not-run"
    assert client.post(f"/api/v1/admin/model-deployments/{deployment['id']}/probe").json()["status"] == "configuration-only"
    assert client.get("/api/v1/admin/video-settings").json()["externalCallsAllowed"] is False
    payload, _ = prepare_video(client)
    assert client.post("/api/v1/generation-runs", json=payload).status_code == 422


def test_documented_adapter_to_real_composition_download_and_retry(client, vendor):
    configure(client, "1")
    payload, shots = prepare_video(client)
    response = client.post("/api/v1/generation-runs", json={**payload, "confirmVideoCost": False})
    assert response.status_code == 422 and vendor["posts"] == 0
    run = wait_generation(client, client.post("/api/v1/generation-runs", json=payload).json()["id"])
    wait_idle(run["id"])
    assert run["mode"] == "ai-video" and run["estimatedUsd"] == "0.5"
    assert run["shotRuns"][0]["providerRequestId"] == "request-1"
    assert "providerHandle" not in run["shotRuns"][0]
    assert run["costCny"] is None and vendor["posts"] == 1
    assert client.get(f"/api/v1/artifacts/{run['finalArtifactId']}/content").status_code == 200
    retry = f"/api/v1/generation-runs/{run['id']}/shots/{shots[0]['id']}/retries"
    assert client.post(retry).status_code == 422
    assert client.post(retry + "?confirmVideoCost=true").status_code == 202
    result = wait_generation(client, run["id"])
    wait_idle(run["id"])
    assert vendor["posts"] == 2 and result["estimatedUsd"] == "1.0"
    assert result["shotRuns"][1]["artifactId"] == run["shotRuns"][1]["artifactId"]
    assert client.post(retry + "?confirmVideoCost=true").status_code == 422
    assert vendor["posts"] == 2


def test_poll_failure_resumes_original_request_without_billing_again(client, vendor):
    configure(client)
    payload, _ = prepare_video(client)
    vendor["failPoll"] = True
    run_id = client.post("/api/v1/generation-runs", json=payload).json()["id"]
    wait_idle(run_id)
    run = client.get(f"/api/v1/generation-runs/{run_id}").json()
    assert run["status"] == "failed" and vendor["posts"] == 1
    assert client.post("/api/v1/generation-runs", json=payload).status_code == 409
    vendor["failPoll"] = False
    assert client.post(f"/api/v1/generation-runs/{run_id}/resumption").status_code == 202
    run = wait_generation(client, run_id)
    assert vendor["posts"] == 1 and run["shotRuns"][-2]["providerRequestId"] == "request-1"


def test_uncertain_submission_never_blindly_retries_or_echoes_key(client, vendor):
    configure(client)
    payload, shots = prepare_video(client)
    vendor["timeoutSubmit"] = True
    run_id = client.post("/api/v1/generation-runs", json=payload).json()["id"]
    wait_idle(run_id)
    response = client.get(f"/api/v1/generation-runs/{run_id}")
    assert response.json()["status"] == "failed"
    assert "test-only-not-a-real-key" not in response.text
    assert client.post(f"/api/v1/generation-runs/{run_id}/resumption").status_code == 409
    assert client.post(f"/api/v1/generation-runs/{run_id}/shots/{shots[0]['id']}/retries?confirmVideoCost=true").status_code == 409
    assert client.post("/api/v1/generation-runs", json=payload).status_code == 409
    assert vendor["posts"] == 1


def test_budget_checked_before_any_submission(client, vendor):
    configure(client, "0.1")
    payload, _ = prepare_video(client)
    assert client.post("/api/v1/generation-runs", json=payload).status_code == 422
    assert vendor["posts"] == 0


def test_cancel_during_submit_persists_handle_and_resume_reuses_it(client, vendor, monkeypatch):
    configure(client)
    payload, _ = prepare_video(client)
    entered, release = threading.Event(), threading.Event()
    original = fal_video.FalVideoClient.submit
    def delayed(self, *args):
        result = original(self, *args)
        entered.set()
        assert release.wait(10)
        return result
    monkeypatch.setattr(fal_video.FalVideoClient, "submit", delayed)
    try:
        run_id = client.post("/api/v1/generation-runs", json=payload).json()["id"]
        assert entered.wait(5)
        assert client.post(f"/api/v1/generation-runs/{run_id}/cancellation").status_code == 202
        assert client.post(f"/api/v1/generation-runs/{run_id}/resumption").status_code == 409
    finally:
        release.set()
    wait_idle(run_id)
    assert client.post(f"/api/v1/generation-runs/{run_id}/resumption").status_code == 202
    wait_generation(client, run_id)
    assert vendor["posts"] == 1


@pytest.mark.parametrize("url", ["http://v3.fal.media/x", "https://localhost/x", "https://fal.media.evil.test/x", "https://key@v3.fal.media/x", "https://v3.fal.media:444/x"])
def test_download_rejects_untrusted_urls(tmp_path, url):
    with pytest.raises(fal_video.VideoProviderError):
        fal_video.download_video(url, tmp_path / "result.mp4")


def test_invalid_submit_handle_does_not_forward_key(monkeypatch):
    monkeypatch.setattr(fal_video.FalVideoClient, "_request", lambda *args, **kwargs: {
        "request_id": "id", "status_url": "https://other.test/requests/id/status"})
    with pytest.raises(fal_video.VideoProviderError) as error:
        fal_video.FalVideoClient("not-a-key").submit("data:image/png;base64,x", "prompt", 5)
    assert error.value.code == "SUBMISSION_UNKNOWN"
