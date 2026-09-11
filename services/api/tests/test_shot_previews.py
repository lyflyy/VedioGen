import threading
from copy import deepcopy
from pathlib import Path

import pytest

from vediogen_api import generation
from vediogen_api.database import SessionLocal
from vediogen_api.media import MediaGenerationError
from vediogen_api.models import ArtifactRow, DocumentRow, GenerationRunRow, ProjectRow
from test_creator_flow import wait_generation
from test_media_generation import prepared, start


def setup_preview(client):
    project_id, storyboard_id, shots = prepared(client)
    shots[1] = {**shots[1], "sourceStrategy": "blender-3d", "sourceAssetId": ""}
    with SessionLocal() as session:
        doc = session.get(DocumentRow, storyboard_id)
        doc.status = "draft"
        doc.data = {**doc.data, "shots": shots}
        project = session.get(ProjectRow, project_id)
        project.current_storyboard_version_id = storyboard_id
        project.status = "storyboard_draft"
        session.commit()
    return project_id, storyboard_id, shots


def preview(client, project, storyboard, shot, **options):
    return client.post("/api/v1/generation-runs", json={"projectId": project, "storyboardVersionId": storyboard,
                       "shotId": shot, "quality": "preview", **options})


def test_preview_works_with_incomplete_draft_without_composing_or_completing_project(client, monkeypatch):
    project, storyboard, shots = setup_preview(client)
    monkeypatch.setattr(generation, "compose_uploaded_shots", lambda *args: pytest.fail("Preview must not compose"))
    before = client.get(f"/api/v1/projects/{project}/storyboards/{storyboard}").json()
    state = client.get(f"/api/v1/projects/{project}/storyboards/{storyboard}/shots/{shots[0]['id']}/preview").json()
    assert state["readiness"]["ready"] and state["run"] is None
    missing = client.get(f"/api/v1/projects/{project}/storyboards/{storyboard}/shots/{shots[1]['id']}/preview").json()
    assert not missing["readiness"]["ready"]
    assert start(client, project, storyboard).status_code == 409
    response = preview(client, project, storyboard, shots[0]["id"])
    assert response.status_code == 202, response.text
    run = wait_generation(client, response.json()["id"])
    assert run["scope"] == "shot-preview"
    assert run["finalArtifactId"] is None and len(run["shotRuns"]) == 1
    assert client.get(f"/api/v1/artifacts/{run['shotRuns'][0]['artifactId']}/content").status_code == 200
    workspace = client.get(f"/api/v1/projects/{project}/workspace").json()
    assert workspace["project"]["status"] == "storyboard_draft"
    assert workspace["activeGenerationRunId"] is None
    assert not workspace["generationReadiness"]["ready"]
    assert client.get(f"/api/v1/projects/{project}/storyboards/{storyboard}").json() == before
    state = client.get(f"/api/v1/projects/{project}/storyboards/{storyboard}/shots/{shots[0]['id']}/preview").json()
    assert state["run"]["id"] == run["id"]


def test_adoption_reuses_file_and_only_changes_selected_shot(client):
    project, storyboard, shots = setup_preview(client)
    run = wait_generation(client, preview(client, project, storyboard, shots[0]["id"]).json()["id"])
    adopted = client.post(f"/api/v1/generation-runs/{run['id']}/adoption")
    assert adopted.status_code == 200, adopted.text
    result = adopted.json()
    assert "uri" not in result["assetVersion"]
    assert result["assetVersion"]["id"] == run["shotRuns"][0]["artifactId"]
    assert result["storyboard"]["shots"][0]["sourceStrategy"] == "user-video"
    assert result["storyboard"]["shots"][1] == shots[1]
    assert result["storyboard"]["totalDurationMs"] == 2000
    second = client.post(f"/api/v1/generation-runs/{run['id']}/adoption")
    assert second.status_code == 200
    assert len(client.get(f"/api/v1/projects/{project}/workspace").json()["assetVersions"]) == 2
    with SessionLocal() as session:
        assert session.query(GenerationRunRow).count() == 1
        asset = session.get(ProjectRow, project).asset_versions[-1]
        assert asset["uri"] == session.get(ArtifactRow, asset["id"]).path


@pytest.mark.parametrize("change", [{"durationMs": 1500}, {"videoPrompt": "different motion"}, {"sourceAssetId": "missing"}])
def test_changed_shot_rejects_stale_adoption_without_overwriting(client, change):
    project, storyboard, shots = setup_preview(client)
    run = wait_generation(client, preview(client, project, storyboard, shots[0]["id"]).json()["id"])
    shots[0].update(change)
    updated = client.put(f"/api/v1/projects/{project}/storyboards/{storyboard}", json={"shots": shots, "totalDurationMs": 2000}).json()
    assert client.post(f"/api/v1/generation-runs/{run['id']}/adoption").status_code == 409
    assert client.get(f"/api/v1/projects/{project}/storyboards/{storyboard}").json() == updated


def test_preview_dedup_does_not_return_different_shot_or_full_run(client, monkeypatch):
    project, storyboard, shots = setup_preview(client)
    entered, release = threading.Event(), threading.Event()
    original = generation.render_uploaded_shot
    def delayed(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)
    monkeypatch.setattr(generation, "render_uploaded_shot", delayed)
    try:
        run = preview(client, project, storyboard, shots[0]["id"]).json()
        assert entered.wait(5)
        assert preview(client, project, storyboard, shots[0]["id"]).json()["id"] == run["id"]
        assert preview(client, project, storyboard, shots[1]["id"]).status_code == 409
        assert start(client, project, storyboard).status_code == 409
        assert client.put(f"/api/v1/projects/{project}/storyboards/{storyboard}", json={"shots": shots, "totalDurationMs": 2000}).status_code == 409
    finally:
        release.set()
    wait_generation(client, run["id"])


@pytest.mark.parametrize("options", [{"shotId": "missing"}, {"narration": True}, {"audioAssetId": "missing"}])
def test_invalid_preview_is_not_queued(client, options):
    project, storyboard, shots = setup_preview(client)
    assert preview(client, project, storyboard, shots[0]["id"], **options).status_code == 422
    with SessionLocal() as session:
        assert session.query(GenerationRunRow).count() == 0


def test_preview_failure_and_retry_leave_existing_final_pointer_intact(client, monkeypatch):
    project, storyboard, shots = prepared(client)
    full = wait_generation(client, start(client, project, storyboard).json()["id"])
    original = generation.render_uploaded_shot
    def fail(*args):
        raise MediaGenerationError("Test rendering failure")
    monkeypatch.setattr(generation, "render_uploaded_shot", fail)
    run = preview(client, project, storyboard, shots[0]["id"]).json()
    generation.stop_worker()
    state = client.get(f"/api/v1/generation-runs/{run['id']}").json()
    assert state["status"] == "failed"
    assert client.get(f"/api/v1/projects/{project}/workspace").json()["activeGenerationRunId"] == full["id"]
    monkeypatch.setattr(generation, "render_uploaded_shot", original)
    generation.start_worker()
    assert client.post(f"/api/v1/generation-runs/{run['id']}/shots/{shots[0]['id']}/retries").status_code == 202
    retried = wait_generation(client, run["id"])
    assert retried["finalArtifactId"] is None and len(retried["shotRuns"]) == 2
    assert client.get(f"/api/v1/projects/{project}/workspace").json()["activeGenerationRunId"] == full["id"]
    assert client.get(f"/api/v1/projects/{project}").json()["status"] == "completed"


def test_adopted_preview_can_be_composed_without_regeneration(client, monkeypatch):
    project, storyboard, shots = setup_preview(client)
    run = wait_generation(client, preview(client, project, storyboard, shots[0]["id"]).json()["id"])
    adopted = client.post(f"/api/v1/generation-runs/{run['id']}/adoption").json()["storyboard"]
    complete = deepcopy(adopted["shots"])
    complete[1] = {**complete[1], "sourceStrategy": "image-motion", "sourceAssetId": shots[0]["sourceAssetId"]}
    client.put(f"/api/v1/projects/{project}/storyboards/{storyboard}", json={"shots": complete, "totalDurationMs": 2000})
    client.post(f"/api/v1/projects/{project}/storyboards/{storyboard}/approval", json={})
    monkeypatch.setattr(generation, "_render_video", lambda *args: pytest.fail("Adopted clip must not invoke a model"))
    full = wait_generation(client, start(client, project, storyboard).json()["id"])
    assert full["scope"] == "full-video" and full["finalArtifactId"]
    assert full["shotRuns"][0]["sourceAssetId"] == run["shotRuns"][0]["artifactId"]


def test_changed_file_cannot_be_adopted(client):
    project, storyboard, shots = setup_preview(client)
    run = wait_generation(client, preview(client, project, storyboard, shots[0]["id"]).json()["id"])
    with SessionLocal() as session:
        artifact = session.get(ArtifactRow, run["shotRuns"][0]["artifactId"])
        Path(artifact.path).write_bytes(b"altered-test-video")
    result = client.post(f"/api/v1/generation-runs/{run['id']}/adoption")
    assert result.status_code == 409 and "文件已改变" in result.text
    assert len(client.get(f"/api/v1/projects/{project}/workspace").json()["assetVersions"]) == 1


def test_preview_keeps_paid_confirmation_gate(client, monkeypatch):
    project, storyboard, shots = setup_preview(client)
    with SessionLocal() as session:
        doc = session.get(DocumentRow, storyboard)
        shots[0].update(sourceStrategy="image-to-video", videoPrompt="Test-only motion", durationMs=5000)
        doc.data = {**doc.data, "shots": shots}
        session.commit()
    monkeypatch.setattr(generation, "video_plan", lambda *args: {"backend": "fal", "estimatedUsd": "0.5"})
    response = preview(client, project, storyboard, shots[0]["id"])
    assert response.status_code == 422 and "确认" in response.text
    with SessionLocal() as session:
        assert session.query(GenerationRunRow).count() == 0
