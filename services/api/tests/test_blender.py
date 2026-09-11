import hashlib
import json
import os
import struct
import subprocess
import sys
from types import SimpleNamespace

import psutil
import pytest

from vediogen_api import blender, generation
from vediogen_api.config import get_settings
from vediogen_api.database import SessionLocal
from vediogen_api.media import MediaGenerationError, create_preview_video, media_metadata
from vediogen_api.models import DocumentRow, GenerationRunRow, ProjectRow
from test_creator_flow import wait_generation
from test_media_generation import prepared, upload, start


def glb(extra=None):
    data = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4}], "meshes": [{"primitives": []}], **(extra or {})}
    payload = json.dumps(data).encode()
    payload += b" " * (-len(payload) % 4)
    return struct.pack("<4sIII", b"glTF", 2, len(payload) + 32, len(payload)) + b"JSON" + payload + struct.pack("<I4s", 4, b"BIN\0") + bytes(4)


@pytest.mark.parametrize("content", [b"not glb", glb({"images": [{"uri": "https://example.com/image.png"}]}),
                                     glb({"buffers": [{"uri": "../mesh.bin", "byteLength": 4}]}),
                                     glb({"meshes": []}), glb()[:-1]])
def test_reject_invalid_and_external_glb(content):
    with pytest.raises(MediaGenerationError):
        blender.validate_glb(content)


def test_glb_upload_and_bad_content_rejection(client):
    pid = client.post("/api/v1/projects", json={"title": "GLB test", "initialMessage": "engineering only"}).json()["id"]
    asset = upload(client, pid, glb(), "mesh.glb", "model/gltf-binary")
    assert asset["kind"] == "model" and not asset["subjectConfirmed"]
    assert asset["meshCount"] == 1
    content = b"invalid"
    intent = client.post("/api/v1/assets/upload-intents", json={"projectId": pid, "fileName": "bad.glb",
        "mimeType": "model/gltf-binary", "sizeBytes": len(content), "sha256": "sha256:" + hashlib.sha256(content).hexdigest()}).json()
    assert client.put(intent["uploadUrl"], content=content).status_code == 422
    assert len(client.get(f"/api/v1/projects/{pid}/workspace").json()["assetVersions"]) == 1


def enable(client, tmp_path, monkeypatch):
    executable = tmp_path / "blender.exe"
    executable.touch()
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    response = client.put("/api/v1/admin/video-settings", json={"blenderEnabled": True, "blenderExecutable": str(executable.resolve())})
    assert response.status_code == 200, response.text
    return executable


def model_project(client):
    pid, sid, shots = prepared(client)
    asset = upload(client, pid, glb(), "engineering.glb", "model/gltf-binary")
    shots[0].update(sourceStrategy="blender-3d", sourceAssetId=asset["id"], blenderTemplate="orbit-360", caption="")
    with SessionLocal() as session:
        doc = session.get(DocumentRow, sid)
        doc.data = {**doc.data, "shots": shots}
        session.get(ProjectRow, pid).current_storyboard_version_id = sid
        session.commit()
    return pid, sid, shots


def test_blender_settings_probe_never_runs_in_isolated_environment(client, monkeypatch):
    monkeypatch.setattr(blender.subprocess, "run", lambda *a, **k: pytest.fail("Must not execute"))
    response = client.post("/api/v1/admin/video-settings/blender-probe")
    assert response.status_code == 422 and "禁止" in response.text
    assert client.put("/api/v1/admin/video-settings", json={"blenderEnabled": True, "blenderExecutable": "missing"}).status_code == 422


def test_blender_probe_checks_version_without_rendering(client, tmp_path, monkeypatch):
    executable = enable(client, tmp_path, monkeypatch)
    def run(args, **kwargs):
        assert args == [str(executable), "--version"]
        return SimpleNamespace(returncode=0, stdout=b"Blender 4.5.13\n")
    monkeypatch.setattr(blender.subprocess, "run", run)
    result = client.post("/api/v1/admin/video-settings/blender-probe").json()
    assert result["verification"] == "executable-only"


def test_blender_plan_requires_enabled_config_and_model(client, tmp_path, monkeypatch):
    pid, sid, shots = model_project(client)
    assert start(client, pid, sid).status_code == 422
    assert not client.get(f"/api/v1/projects/{pid}/workspace").json()["generationReadiness"]["ready"]
    enable(client, tmp_path, monkeypatch)
    with SessionLocal() as session:
        project, storyboard = session.get(ProjectRow, pid), session.get(DocumentRow, sid)
        plan = generation.build_plan(project, storyboard)
        assert plan["mode"] == "local-blender" and plan["video"] is None
        for change in [{"sourceAssetId": "missing"}, {"durationMs": 1500}, {"blenderTemplate": "riding"}]:
            document = SimpleNamespace(data={"shots": [{**shots[0], **change}]})
            with pytest.raises(ValueError):
                generation.build_plan(project, document)


def test_blender_composition_and_manual_retry_use_existing_queue(client, tmp_path, monkeypatch):
    enable(client, tmp_path, monkeypatch)
    pid, sid, shots = model_project(client)
    calls = []
    def render(asset, shot, output, config, target, directory, handle, started, record, cancelled, progress):
        calls.append(shot["id"])
        assert asset["kind"] == "model" and not started
        # Isolated renderer substitute; actual Blender is verified separately in the live browser test.
        create_preview_video(target, 1)
        progress(30)
        return media_metadata(target, 1000)
    monkeypatch.setattr(generation, "render_blender_shot", render)
    run = wait_generation(client, start(client, pid, sid).json()["id"])
    assert run["mode"] == "local-blender" and run["finalArtifactId"]
    retained = run["shotRuns"][1]["artifactId"]
    retry = client.post(f"/api/v1/generation-runs/{run['id']}/shots/{shots[0]['id']}/retries")
    assert retry.status_code == 202
    rerun = wait_generation(client, run["id"])
    assert rerun["shotRuns"][-1]["renderedFrames"] == 30
    assert rerun["shotRuns"][1]["artifactId"] == retained
    assert calls == [shots[0]["id"], shots[0]["id"]]


def test_pid_reuse_does_not_match_or_terminate_other_process():
    current = psutil.Process(os.getpid())
    handle = {"pid": current.pid, "createdAt": current.create_time() - 1}
    assert blender.matching_process(handle) is None
    blender.cancel_blender(handle)


def test_live_orphan_blocks_new_work_and_retry_but_resume_retains_handle(client, tmp_path, monkeypatch):
    enable(client, tmp_path, monkeypatch)
    pid, sid, shots = model_project(client)
    with SessionLocal() as session:
        plan = generation.build_plan(session.get(ProjectRow, pid), session.get(DocumentRow, sid), shot_id=shots[0]["id"])
        run = GenerationRunRow(id="orphan-test", project_id=pid, storyboard_version_id=sid, routing_policy_version_id="test", status="interrupted", request_data=plan,
            shot_runs=[{"id": "attempt-old", "shotId": shots[0]["id"], "status": "running", "strategy": "blender-3d", "attempt": 1,
                        "blenderHandle": {"pid": 123, "createdAt": 1}, "blenderStarted": True, "blenderDirectory": "old-directory"}])
        session.add(run)
        session.commit()
    monkeypatch.setattr(generation, "matching_process", lambda handle: object() if handle else None)
    from vediogen_api import creator
    monkeypatch.setattr(creator, "matching_process", lambda handle: object() if handle else None)
    assert start(client, pid, sid).status_code == 409
    assert client.post(f"/api/v1/generation-runs/orphan-test/shots/{shots[0]['id']}/retries").status_code == 409
    monkeypatch.setattr(creator, "submit_run", lambda _: None)
    response = client.post("/api/v1/generation-runs/orphan-test/resumption")
    assert response.status_code == 202
    latest = response.json()["shotRuns"][-1]
    assert latest["blenderHandle"]["pid"] == 123 and latest["blenderDirectory"] == "old-directory"


def test_unknown_start_is_not_automatically_relaunched(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    content = glb()
    asset = tmp_path / "source.glb"
    asset.write_bytes(content)
    monkeypatch.setattr(blender.subprocess, "Popen", lambda *a, **k: pytest.fail("No resubmission"))
    with pytest.raises(MediaGenerationError, match="启动结果不明"):
        blender.render_blender_shot({"uri": str(asset), "sha256": "sha256:" + hashlib.sha256(content).hexdigest()},
            {"durationMs": 1000}, {"fps": 30}, {"timeoutSeconds": 60}, tmp_path / "out.mp4", tmp_path / "frames", None, True,
            lambda *a: None, lambda: False, lambda _: None)


@pytest.mark.parametrize("cancel", [True, False])
def test_recovered_process_is_stopped_on_cancellation_or_timeout(client, tmp_path, monkeypatch, cancel):
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    content = glb()
    asset = tmp_path / "source.glb"
    asset.write_bytes(content)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
    try:
        handle = {"pid": child.pid, "createdAt": psutil.Process(child.pid).create_time()}
        args = ({"uri": str(asset), "sha256": "sha256:" + hashlib.sha256(content).hexdigest()},
                {"durationMs": 1000}, {"fps": 30}, {"timeoutSeconds": 0}, tmp_path / "out.mp4", tmp_path / "frames",
                handle, True, lambda *a: pytest.fail("Must not restart process"), lambda: cancel, lambda _: None)
        if cancel:
            assert blender.render_blender_shot(*args) is None
        else:
            with pytest.raises(MediaGenerationError, match="超时"):
                blender.render_blender_shot(*args)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=10)


def test_completed_render_resume_reuses_matching_frames_without_new_process(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    content = glb()
    source = tmp_path / "source.glb"
    source.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    frames = tmp_path / "frames"
    frames.mkdir()
    report = {"calibrationOnly": False, "assetSha256": digest, "frames": 30, "width": 540, "height": 960,
              "fps": 30, "orbitDegrees": 360, "samples": [{"allBoundsInside": True}] * 30}
    (frames / "orbit.json").write_text(json.dumps(report))
    for i in range(1, 31):
        (frames / f"frame-{i:04d}.png").touch()
    monkeypatch.setattr(blender.subprocess, "Popen", lambda *a, **k: pytest.fail("Must not rerender"))
    encoded = []
    monkeypatch.setattr(blender, "_encode", lambda *a: encoded.append(a))
    monkeypatch.setattr(blender, "media_metadata", lambda *a: {"verified": True})
    args = ({"uri": str(source), "sha256": "sha256:" + digest}, {"durationMs": 1000}, {"fps": 30, "width": 540, "height": 960},
            {"timeoutSeconds": 60}, tmp_path / "out.mp4", frames, None, True, lambda *a: None, lambda: False, lambda _: None)
    assert blender.render_blender_shot(*args) == {"verified": True}
    assert len(encoded) == 1
    report["assetSha256"] = "changed"
    (frames / "orbit.json").write_text(json.dumps(report))
    with pytest.raises(MediaGenerationError, match="输出不完整"):
        blender.render_blender_shot(*args)
    assert len(encoded) == 1
