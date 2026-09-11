import json
from types import SimpleNamespace

import pytest

from vediogen_api import gateway
from vediogen_api.database import SessionLocal
from vediogen_api.models import ProjectRow


def test_context_exposes_limits_without_credentials_or_service_url(client):
    project_id = client.post("/api/v1/projects", json={"title": "text only", "initialMessage": "motorcycle"}).json()["id"]
    client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "enabled": False})
    with SessionLocal() as session:
        context = gateway._media_execution_context(session, session.get(ProjectRow, project_id))
    assert context["inputMode"] == "text-only"
    assert context["assetPreparationOwner"] == "platform"
    assert context["imageToVideo"]["durationOptionsMs"] is None
    assert context["imageToVideo"]["durationRangeMs"] == {"min": 500, "max": 5000}
    assert context["imageToVideo"]["enabled"] is False
    assert context["imageToVideo"]["callsAllowed"] is False
    assert "blender-3d" in context["implementedMediaStrategies"]
    assert not context["blender"]["enabled"] and not context["blender"]["callsAllowed"]
    assert context["blender"]["template"] == "orbit-360"
    assert "blenderExecutable" not in json.dumps(context)
    assert "localUrl" not in json.dumps(context)
    assert "credential" not in json.dumps(context)
    client.put("/api/v1/admin/video-settings", json={"backend": "fal", "enabled": False})
    with SessionLocal() as session:
        context = gateway._media_execution_context(session, session.get(ProjectRow, project_id))
    assert context["imageToVideo"]["durationOptionsMs"] == [5000, 10000]


@pytest.mark.parametrize("capability", ["advisor", "storyboard"])
def test_real_model_prompt_includes_execution_context(client, monkeypatch, capability):
    project_id = client.post("/api/v1/projects", json={"title": "text only", "initialMessage": "motorcycle"}).json()["id"]
    client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "enabled": False})
    captured = {}

    class CapturedPrompt(Exception):
        pass

    def capture(**kwargs):
        captured.update(kwargs)
        raise CapturedPrompt()

    def invoke(session, alias, project_id, title, fake, real):
        return real(SimpleNamespace(base_url="https://invalid.example/v1"),
                    SimpleNamespace(physical_model_id="test", timeout_seconds=30), "fixture-only")

    monkeypatch.setattr(gateway, "complete_json", capture)
    monkeypatch.setattr(gateway, "_invoke_routed", invoke)
    with SessionLocal() as session, pytest.raises(CapturedPrompt):
        project = session.get(ProjectRow, project_id)
        if capability == "advisor":
            gateway.generate_creative_advice(session, project)
        else:
            gateway.generate_storyboard(session, project, SimpleNamespace(data={}, id="test-brief"), 1)
    body = json.loads(captured["user_prompt"].split("\n", 1)[1])
    assert body["executionContext"]["assetPreparationOwner"] == "platform"
    assert body["executionContext"]["imageToVideo"]["backend"] == "comfyui"
    assert "平台" in captured["system_prompt"]
