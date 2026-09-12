import hashlib
import subprocess
from uuid import uuid4

import httpx
import pytest

from vediogen_api import generation
from vediogen_api.comfy_video import ComfyVideoClient, DIFFUSION, ENCODER, NODES, VAE, local_url, workflow
from vediogen_api.config import get_settings
from vediogen_api.database import SessionLocal
from vediogen_api.fal_video import VideoProviderError
from vediogen_api.media import create_preview_video
from vediogen_api.models import DocumentRow, GenerationRunRow
from test_creator_flow import wait_generation
from test_media_generation import prepared, start


def local_setup(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    project, storyboard, shots = prepared(client)
    shots = [{**shots[0], "sourceStrategy": "image-to-video", "videoPrompt": "Slow motorcycle tracking shot"}]
    with SessionLocal() as session:
        row = session.get(DocumentRow, storyboard)
        row.data = {**row.data, "shots": shots, "totalDurationMs": 1000}
        session.commit()
    response = client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "enabled": True})
    assert response.status_code == 200, response.text
    return project, storyboard, shots[0]


@pytest.mark.parametrize("address", ["https://example.com", "http://localhost:8188", "http://127.0.0.1:80", "http://user@127.0.0.1:8188", "http://127.0.0.1:8188/path", "http://127.0.0.1:99999"])
def test_only_explicit_loopback_services(address):
    with pytest.raises(VideoProviderError):
        local_url(address)


def test_local_settings_validate_without_calling_service(client):
    response = client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "enabled": True})
    assert response.status_code == 200
    assert response.json()["localCallsAllowed"] is False
    assert client.post("/api/v1/admin/video-settings/local-probe").status_code == 422
    assert client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "localUrl": "https://example.com"}).status_code == 422
    assert client.put("/api/v1/admin/video-settings", json={"width": 832, "height": 832}).status_code == 422


def test_offline_workflow_preserves_prompt_duration_and_id():
    prompt_id = str(uuid4())
    graph = workflow({"width": 384, "height": 640, "steps": 20}, {"durationMs": 2000, "videoPrompt": "specific motion"}, "vediogen/test.png", prompt_id, 42)
    assert {n["class_type"] for n in graph.values()} == NODES
    assert graph["8"]["inputs"]["length"] == 49
    assert graph["5"]["inputs"]["text"] == "specific motion"
    assert graph["12"]["inputs"]["filename_prefix"] == f"vediogen/{prompt_id}"
    assert graph["9"]["inputs"]["seed"] == 42
    assert graph["12"]["inputs"]["format"] == "mp4"
    assert graph["12"]["inputs"]["format.codec"] == "h264"
    assert graph["1"]["inputs"]["weight_dtype"] == "default"
    assert graph["10"]["class_type"] == "VAEDecode"


def test_existing_fp8_snapshot_keeps_its_original_workflow():
    graph = workflow({"width": 256, "height": 448, "steps": 20, "physicalModelId": "wan2.2-ti2v-5b-fp8-runtime"},
                     {"durationMs": 1000, "videoPrompt": "tracking"}, "image.png", str(uuid4()), 1)
    assert graph["1"]["inputs"]["weight_dtype"] == "fp8_e4m3fn"
    assert graph["10"]["class_type"] == "VAEDecodeTiled"


@pytest.mark.parametrize("duration", [500, 1200, 1600, 1800, 2800, 5000])
def test_editorial_duration_adapts_to_wan_frames(client, monkeypatch, duration):
    from vediogen_api.video_settings import video_plan
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "enabled": True})
    shot = {"durationMs": duration, "videoPrompt": "tracking"}
    with SessionLocal() as session:
        config = video_plan(session, [shot])
    graph = workflow(config, shot, "ref.png", str(uuid4()), 1)
    frames = graph["8"]["inputs"]["length"]
    assert (frames - 1) % 4 == 0
    assert frames / 24 * 1000 >= duration
    assert shot["durationMs"] == duration


def test_probe_checks_model_files_and_minimum_server_version(monkeypatch):
    info = {name: {} for name in {*NODES, "VAEDecodeTiled"}}
    for kind, field, model in [("UNETLoader", "unet_name", DIFFUSION), ("CLIPLoader", "clip_name", ENCODER), ("VAELoader", "vae_name", VAE)]:
        info[kind] = {"input": {"required": {field: [[model]]}}}
    client = ComfyVideoClient("http://127.0.0.1:8188")
    monkeypatch.setattr(client, "request", lambda method, path: info if path == "/object_info" else {"system": {"comfyui_version": "0.34.0"}})
    assert client.probe()["ready"] is True
    info["VAELoader"] = {}
    assert VAE in client.probe()["missing"]


def test_new_low_memory_plan_uses_tiled_decode_without_changing_weights(client, monkeypatch):
    from vediogen_api.video_settings import video_plan
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "enabled": True})
    shot = {"durationMs": 3000, "videoPrompt": "stationary motorcycle"}
    with SessionLocal() as session:
        config = video_plan(session, [shot])
    graph = workflow(config, shot, "ref.png", str(uuid4()), 1)
    assert graph["1"]["inputs"]["weight_dtype"] == "default"
    assert graph["10"]["class_type"] == "VAEDecodeTiled"
    assert graph["10"]["inputs"]["temporal_size"] == 16


def test_adapter_uses_real_comfy_wire_format_and_targeted_cancel(monkeypatch):
    prompt_id = str(uuid4())
    seen = []
    original = httpx.Client
    def handler(request):
        import json
        seen.append((request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": prompt_id})
        if request.url.path.startswith("/history/"):
            return httpx.Response(200, json={prompt_id: {"status": {"completed": True, "status_str": "success"}, "outputs": {"12": {"images": [{"filename": "result.mp4", "subfolder": "vediogen", "type": "output"}]}}}})
        return httpx.Response(200, json={})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    client = ComfyVideoClient("http://127.0.0.1:8188")
    client.submit({}, prompt_id)
    assert client.status(prompt_id)[0] == "COMPLETED"
    client.cancel(prompt_id)
    assert seen[-2:] == [("/queue", {"delete": [prompt_id]}), ("/interrupt", {"prompt_id": prompt_id})]


def test_local_job_persists_handle_then_composes_real_clip_without_cloud_cost(client, monkeypatch, tmp_path):
    project, storyboard, shot = local_setup(client, monkeypatch)
    clip = tmp_path / "local-contract-fixture.mp4"
    create_preview_video(clip, 1)
    native = tmp_path / "native.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", "scale=832:480", str(native)], check=True, capture_output=True, timeout=30)
    clip = native
    submits = []
    monkeypatch.setattr(ComfyVideoClient, "probe", lambda self: {"ready": True})
    monkeypatch.setattr(ComfyVideoClient, "upload", lambda self, asset, name: "vediogen/test.jpg")
    def submit(self, graph, prompt_id):
        with SessionLocal() as session:
            run = session.query(GenerationRunRow).filter_by(status="running").one()
            assert run.shot_runs[-1]["providerRequestId"] == prompt_id
            assert run.shot_runs[-1]["submissionState"] == "submitting"
        submits.append(prompt_id)
    monkeypatch.setattr(ComfyVideoClient, "submit", submit)
    monkeypatch.setattr(ComfyVideoClient, "status", lambda self, prompt_id: ("COMPLETED", {}))
    def download(self, output, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(clip.read_bytes())
        return {"uri": str(path), "kind": "video", "durationMs": 1000, "sha256": "sha256:" + hashlib.sha256(clip.read_bytes()).hexdigest()}
    monkeypatch.setattr(ComfyVideoClient, "download", download)
    run = wait_generation(client, start(client, project, storyboard).json()["id"])
    assert run["mode"] == "local-ai-video"
    assert run["estimatedUsd"] is None
    assert run["shotRuns"][0]["nativeWidth"] == 832
    assert client.get(f"/api/v1/artifacts/{run['finalArtifactId']}/content").status_code == 200
    assert run["canRecompose"] is True
    recomposed = client.post(f"/api/v1/generation-runs/{run['id']}/recomposition")
    assert recomposed.status_code == 202, recomposed.text
    reused = wait_generation(client, recomposed.json()["id"])
    assert reused["finalArtifactId"] != run["finalArtifactId"]
    assert reused["canRecompose"] is False
    assert len(submits) == 1
    assert client.get(f"/api/v1/artifacts/{run['finalArtifactId']}/content").status_code == 200
    retry = client.post(f"/api/v1/generation-runs/{run['id']}/shots/{shot['id']}/retries")
    assert retry.status_code == 202, retry.text
    wait_generation(client, run["id"])
    assert len(set(submits)) == 2


def test_missing_models_fail_without_fake_output(client, monkeypatch):
    project, storyboard, _ = local_setup(client, monkeypatch)
    monkeypatch.setattr(ComfyVideoClient, "probe", lambda self: {"ready": False, "missing": [DIFFUSION]})
    run_id = start(client, project, storyboard).json()["id"]
    generation.stop_worker()
    run = client.get(f"/api/v1/generation-runs/{run_id}").json()
    assert run["status"] == "failed"
    assert DIFFUSION in run["errorMessage"]
    assert run["finalArtifactId"] is None


def test_uncertain_local_submission_is_queried_not_resubmitted(client, monkeypatch):
    project, storyboard, shot = local_setup(client, monkeypatch)
    monkeypatch.setattr(ComfyVideoClient, "probe", lambda self: {"ready": True})
    monkeypatch.setattr(ComfyVideoClient, "upload", lambda *args: "vediogen/test.jpg")
    submits = []
    def uncertain(self, graph, prompt_id):
        submits.append(prompt_id)
        raise VideoProviderError("connection lost", "LOCAL_UNAVAILABLE")
    monkeypatch.setattr(ComfyVideoClient, "submit", uncertain)
    run_id = start(client, project, storyboard).json()["id"]
    generation.stop_worker()
    monkeypatch.setattr(ComfyVideoClient, "status", lambda *args: ("MISSING", None))
    generation.start_worker()
    assert client.post(f"/api/v1/generation-runs/{run_id}/resumption").status_code == 202
    generation.stop_worker()
    run = client.get(f"/api/v1/generation-runs/{run_id}").json()
    assert run["status"] == "failed"
    assert "未找到原任务" in run["errorMessage"]
    assert len(submits) == 1


def test_local_download_validates_actual_video_and_hash(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    create_preview_video(source, 1)
    content = source.read_bytes()
    original = httpx.Client
    def handler(request):
        assert request.url.path == "/view"
        assert request.url.params["type"] == "output"
        return httpx.Response(200, content=content)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    client = ComfyVideoClient("http://127.0.0.1:8188")
    asset = client.download({"filename": "clip.mp4", "subfolder": "vediogen", "type": "output"}, tmp_path / "result.mp4")
    assert asset["sha256"] == "sha256:" + hashlib.sha256(content).hexdigest()
    assert asset["durationMs"] >= 1000
    with pytest.raises(VideoProviderError):
        client.download({"filename": "../clip.mp4", "type": "output"}, tmp_path / "bad.mp4")


def test_job_finishing_between_history_and_queue_is_not_missing(monkeypatch):
    client = ComfyVideoClient("http://127.0.0.1:8188")
    job = str(uuid4())
    responses = iter([{}, {"queue_running": [], "queue_pending": []}, {job: {"status": {"status_str": "error"}}}])
    monkeypatch.setattr(client, "request", lambda *args: next(responses))
    assert client.status(job)[0] == "FAILED"


def test_portrait_reference_preserves_full_landscape_vehicle_by_default():
    config = {"width": 256, "height": 448, "steps": 20}
    shot = {"durationMs": 1000, "videoPrompt": "tracking shot"}
    graph = workflow(config, shot, "test.png", str(uuid4()), 1, (1280, 720))
    assert graph["13"]["inputs"]["width"] == 256
    assert graph["13"]["inputs"]["height"] == 144
    assert graph["14"]["inputs"]["top"] == 152
    assert graph["8"]["inputs"]["start_image"] == ["14", 0]
    cropped = workflow(config, {**shot, "fit": "cover"}, "test.png", str(uuid4()), 1, (1280, 720))
    assert cropped["13"]["inputs"]["crop"] == "center"
    assert cropped["14"]["inputs"]["top"] == 0


def test_cancelled_resumption_still_cancels_its_existing_local_job(client, monkeypatch):
    project, storyboard, shot = local_setup(client, monkeypatch)
    from vediogen_api.models import ProjectRow
    upstream = str(uuid4())
    with SessionLocal() as session:
        plan = generation.build_plan(session.get(ProjectRow, project), session.get(DocumentRow, storyboard))
        run = GenerationRunRow(id=str(uuid4()), project_id=project, storyboard_version_id=storyboard,
            routing_policy_version_id="video-execution-v1", status="cancelled", request_data=plan,
            shot_runs=[{"id": str(uuid4()), "shotId": shot["id"], "status": "cancelled", "providerHandle": {"requestId": upstream}}])
        session.add(run)
        session.commit()
        run_id = run.id
    cancellations = []
    monkeypatch.setattr(ComfyVideoClient, "cancel", lambda self, job: cancellations.append(job))
    generation._execute(run_id)
    assert cancellations == [upstream]
