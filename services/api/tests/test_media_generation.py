import hashlib
import io
import math
import struct
import threading
import subprocess
import wave
from pathlib import Path
from uuid import uuid4

import pytest

from vediogen_api import generation
from vediogen_api.database import SessionLocal
from vediogen_api.media import MediaGenerationError, create_preview_video, probe_media
from vediogen_api.models import DocumentRow, GenerationRunRow
from test_creator_flow import wait_generation


def test_transparent_source_is_composited_before_video_encoding(tmp_path):
    from PIL import Image, ImageDraw
    from vediogen_api.media import render_uploaded_shot
    source = tmp_path / "transparent.png"
    image = Image.new("RGBA", (100, 100), (255, 0, 255, 0))
    ImageDraw.Draw(image).rectangle((40, 40, 60, 60), fill=(240, 240, 240, 255))
    image.save(source)
    target = tmp_path / "alpha.mp4"
    asset = {"uri": str(source), "sha256": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()}
    render_uploaded_shot(asset, {"sourceStrategy": "image-motion", "durationMs": 1000},
                         {"width": 100, "height": 100, "fps": 30}, target)
    frame = subprocess.run(["ffmpeg", "-v", "error", "-i", str(target), "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                           capture_output=True, check=True, timeout=30).stdout
    assert len(frame) == 100 * 100 * 3
    assert all(abs(actual - expected) < 8 for actual, expected in zip(frame[:3], (20, 24, 28)))
    assert min(frame[(50 * 100 + 50) * 3:(50 * 100 + 50) * 3 + 3]) > 220
    assert not target.with_suffix(".source.png").exists()


def upload(client, project_id, content=None, name="reference.jpg", mime="image/jpeg"):
    if content is None:
        content = (Path(__file__).resolve().parents[3] / "apps/web/public/images/motorcycle-studio.jpg").read_bytes()
    intent = client.post("/api/v1/assets/upload-intents", json={"projectId": project_id, "fileName": name,
        "mimeType": mime, "sizeBytes": len(content), "sha256": "sha256:" + hashlib.sha256(content).hexdigest()}).json()
    response = client.put(intent["uploadUrl"], content=content)
    assert response.status_code == 201, response.text
    return response.json()


def prepared(client, invalid_image=False):
    project = client.post("/api/v1/projects", json={"title": "素材合成", "initialMessage": "图片与上传片段"}).json()
    asset = upload(client, project["id"], b"not-a-real-jpeg" if invalid_image else None)
    shots = [{"id": str(uuid4()), "purpose": f"镜头 {i}", "durationMs": 1000,
              "sourceStrategy": "image-motion", "sourceAssetId": asset["id"], "caption": "真实上传素材"} for i in range(2)]
    with SessionLocal() as session:
        doc = DocumentRow(id=str(uuid4()), project_id=project["id"], kind="storyboard", version=1, status="approved",
                          data={"shots": shots, "totalDurationMs": 2000})
        session.add(doc)
        session.commit()
        return project["id"], doc.id, shots


def start(client, project_id, storyboard_id):
    return client.post("/api/v1/generation-runs", json={"projectId": project_id, "storyboardVersionId": storyboard_id, "quality": "preview"})


def test_saved_shots_receive_draft_state_and_recomputed_timeline(client):
    project_id, storyboard_id, shots = prepared(client)
    shots[0].update(status="completed", order=9, startMs=7000)
    response = client.put(f"/api/v1/projects/{project_id}/storyboards/{storyboard_id}",
                          json={"shots": shots, "totalDurationMs": 9000})
    assert response.status_code == 200
    result = response.json()
    assert result["totalDurationMs"] == 2000
    assert [shot["status"] for shot in result["shots"]] == ["draft", "draft"]
    assert [shot["order"] for shot in result["shots"]] == [1, 2]
    assert [shot["startMs"] for shot in result["shots"]] == [0, 1000]


def test_real_uploaded_image_and_video_are_composed(client, tmp_path):
    project_id, storyboard_id, shots = prepared(client)
    clip = tmp_path / "input.mp4"
    create_preview_video(clip, 2)
    asset = upload(client, project_id, clip.read_bytes(), "input.mp4", "video/mp4")
    with SessionLocal() as session:
        doc = session.get(DocumentRow, storyboard_id)
        shots[1] = {**shots[1], "sourceStrategy": "user-video", "sourceAssetId": asset["id"], "sourceStartMs": 400}
        doc.data = {**doc.data, "shots": shots}
        session.commit()
    run = wait_generation(client, start(client, project_id, storyboard_id).json()["id"])
    assert run["mode"] == "uploaded-media"
    assert all(s["artifactId"] for s in run["shotRuns"])
    assert run["shotRuns"][1]["sourceAssetId"] == asset["id"]
    artifact = client.get(f"/api/v1/artifacts/{run['finalArtifactId']}").json()
    assert abs(artifact["durationMs"] - 2000) < 250
    assert artifact["width"] == 540
    for shot in run["shotRuns"]:
        assert client.get(f"/api/v1/artifacts/{shot['artifactId']}/content").status_code == 200


@pytest.mark.parametrize("change", [{"sourceStrategy": "generated-video"}, {"sourceAssetId": "unknown"}, {"durationMs": -1}, {"caption": "字" * 41}])
def test_missing_capability_or_invalid_source_is_not_fake_success(client, change):
    project_id, storyboard_id, shots = prepared(client)
    with SessionLocal() as session:
        row = session.get(DocumentRow, storyboard_id)
        row.data = {**row.data, "shots": [{**shots[0], **change}, shots[1]]}
        session.commit()
    response = start(client, project_id, storyboard_id)
    assert response.status_code == 422
    with SessionLocal() as session:
        assert session.query(GenerationRunRow).count() == 0


def test_task_returns_before_render_and_duplicate_reuses_run(client, monkeypatch):
    project_id, storyboard_id, shots = prepared(client)
    entered, release = threading.Event(), threading.Event()
    original = generation.render_uploaded_shot
    def delayed(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)
    monkeypatch.setattr(generation, "render_uploaded_shot", delayed)
    try:
        first = start(client, project_id, storyboard_id)
        assert first.status_code == 202
        assert first.json()["status"] == "queued"
        assert entered.wait(5)
        assert start(client, project_id, storyboard_id).json()["id"] == first.json()["id"]
        edit = client.put(f"/api/v1/projects/{project_id}/storyboards/{storyboard_id}", json={"shots": shots, "totalDurationMs": 2000})
        assert edit.status_code == 409
    finally:
        release.set()
    wait_generation(client, first.json()["id"])


def test_cancel_does_not_publish_late_artifact(client, monkeypatch):
    project_id, storyboard_id, _ = prepared(client)
    entered, release = threading.Event(), threading.Event()
    def delayed(*args):
        entered.set()
        assert release.wait(10)
        raise MediaGenerationError("late failure")
    monkeypatch.setattr(generation, "render_uploaded_shot", delayed)
    try:
        run = start(client, project_id, storyboard_id).json()
        assert entered.wait(5)
        cancelled = client.post(f"/api/v1/generation-runs/{run['id']}/cancellation").json()
        assert cancelled["status"] == "cancelled"
    finally:
        release.set()
    generation.stop_worker()
    latest = client.get(f"/api/v1/generation-runs/{run['id']}").json()
    assert latest["status"] == "cancelled"
    assert latest["finalArtifactId"] is None


def test_invalid_image_fails_with_actionable_status(client):
    import time
    project_id, storyboard_id, _ = prepared(client, invalid_image=True)
    run_id = start(client, project_id, storyboard_id).json()["id"]
    for _ in range(100):
        run = client.get(f"/api/v1/generation-runs/{run_id}").json()
        if run["status"] == "failed":
            break
        time.sleep(0.1)
    assert run["status"] == "failed"
    assert run["errorMessage"]
    assert run["finalArtifactId"] is None


def test_restart_marks_unfinished_runs_for_manual_resume(client):
    project_id, storyboard_id, shots = prepared(client)
    with SessionLocal() as session:
        from vediogen_api.models import ProjectRow
        plan = generation.build_plan(session.get(ProjectRow, project_id), session.get(DocumentRow, storyboard_id), "preview")
        row = GenerationRunRow(id=str(uuid4()), project_id=project_id, storyboard_version_id=storyboard_id,
            routing_policy_version_id="local-uploaded-media-v1", status="running", request_data=plan,
            shot_runs=[{"id": str(uuid4()), "shotId": shot["id"], "strategy": "image-motion", "status": "running", "attempt": 1} for shot in shots])
        session.add(row)
        session.commit()
        run_id = row.id
    generation.stop_worker()
    generation.start_worker()
    assert client.get(f"/api/v1/generation-runs/{run_id}").json()["status"] == "interrupted"
    assert client.post(f"/api/v1/generation-runs/{run_id}/resumption").status_code == 202
    wait_generation(client, run_id)


def test_uploaded_background_audio_is_mixed_at_standard_resolution(client):
    project_id, storyboard_id, _ = prepared(client)
    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"".join(struct.pack("<h", round(5000 * math.sin(2 * math.pi * 220 * i / 8000))) for i in range(8000)))
    asset = upload(client, project_id, data.getvalue(), "test-tone.wav", "audio/wav")
    response = client.post("/api/v1/generation-runs", json={"projectId": project_id, "storyboardVersionId": storyboard_id, "audioAssetId": asset["id"]})
    run = wait_generation(client, response.json()["id"])
    assert run["audioMode"] == "background-mix"
    with SessionLocal() as session:
        from vediogen_api.models import ArtifactRow
        artifact = session.get(ArtifactRow, run["finalArtifactId"])
        metadata = probe_media(Path(artifact.path))
        assert metadata["width"] == 1080
        assert metadata["hasAudio"] is True
        import subprocess
        audio_bytes = subprocess.run(["ffmpeg", "-v", "error", "-i", artifact.path, "-map", "0:a", "-f", "s16le", "-ac", "1", "pipe:1"], capture_output=True, check=True).stdout
        samples = struct.unpack(f"<{len(audio_bytes) // 2}h", audio_bytes)
        assert max(abs(value) for value in samples) > 100
