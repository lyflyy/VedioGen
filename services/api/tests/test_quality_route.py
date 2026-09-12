import hashlib
import math
import wave
import time
from array import array
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from vediogen_api import gateway, storyboard_jobs as jobs
from vediogen_api.database import SessionLocal
from vediogen_api.generation import build_plan
from vediogen_api.media import prepare_portrait_reference, render_soundtrack
from vediogen_api.models import DocumentRow, ProjectRow
from test_storyboard_jobs import setup_brief, upload
from test_storyboard_jobs import wait as wait_script


def test_observation_covers_all_candidates_and_reuses_cache(client, monkeypatch):
    pid = setup_brief(client)
    upload(client, pid)
    calls = []
    original = gateway._invoke_routed
    def record(*args):
        calls.append(args[1])
        return original(*args)
    monkeypatch.setattr(gateway, "_invoke_routed", record)
    with SessionLocal() as session:
        project = session.get(ProjectRow, pid)
        assets = [{**project.asset_versions[0], "id": f"ref-{i}"} for i in range(9)]
        observations = gateway.observe_reference_images(session, project, assets)
        assert [o["assetId"] for o in observations] == [a["id"] for a in assets]
        assert len(calls) == 3
        assert gateway.observe_reference_images(session, project, assets) == observations
        assert len(calls) == 3
        assets[-1]["subject"] = "changed identity"
        gateway.observe_reference_images(session, project, assets)
        assert len(calls) == 4


def test_existing_unrelated_image_does_not_stop_discovery(client, monkeypatch):
    pid = setup_brief(client)
    upload(client, pid)
    monkeypatch.setattr(jobs.get_settings(), "allow_external_search", True)
    monkeypatch.setattr(jobs, "extract_asset_brief", lambda *args: {"subject": "张雪820RR", "clarification": ""})
    searched = []
    def search(subject):
        searched.append(subject)
        return [], []
    monkeypatch.setattr(jobs, "manufacturer_images", search)
    with SessionLocal() as session:
        jobs.prepare_images(session, session.get(ProjectRow, pid))
    assert searched == ["张雪820RR"]


@pytest.mark.parametrize("owner", ["platform", "user"])
def test_recommended_reference_can_change_but_user_pin_cannot(client, monkeypatch, owner):
    pid = setup_brief(client)
    first, second = upload(client, pid), upload(client, pid)
    monkeypatch.setattr(jobs, "match_storyboard_assets", lambda *args: {"assignments": [{"shotId": "s", "assetId": second["id"],
        "reason": "同车红色细节", "strategy": "image-motion", "needsPreview": False, "blocker": "", "exactOrbit": False}]})
    with SessionLocal() as session:
        data = jobs.assign_assets(session, session.get(ProjectRow, pid), {"shots": [{"id": "s", "sourceStrategy": "image-to-video",
            "sourceAssetId": first["id"], "selectionOwner": owner, "strategyOwner": "platform", "durationMs": 3000}]})
    shot = data["shots"][0]
    assert shot["sourceAssetId"] == (second["id"] if owner == "platform" else first["id"])
    assert bool(shot["productionPlan"]["blocker"]) == (owner == "user")
    if owner == "platform":
        assert shot["sourceStrategy"] == "image-motion"
        assert shot["referenceFraming"] == "portrait-soft"


def test_exact_orbit_does_not_route_to_image_motion(client):
    pid = setup_brief(client)
    asset = upload(client, pid)
    with SessionLocal() as session:
        project = session.get(ProjectRow, pid)
        board = SimpleNamespace(data={"shots": [{"id": "s", "durationMs": 3000, "sourceStrategy": "image-motion",
            "sourceAssetId": asset["id"], "productionPlan": {"exactOrbit": True}}]})
        with pytest.raises(ValueError, match="准确完整 360"):
            build_plan(project, board)


def test_critical_preview_blocks_full_but_not_single_shot(client):
    pid = setup_brief(client)
    asset = upload(client, pid)
    with SessionLocal() as session:
        project = session.get(ProjectRow, pid)
        board = SimpleNamespace(data={"shots": [{"id": "s", "durationMs": 3000, "sourceStrategy": "image-motion",
            "sourceAssetId": asset["id"], "productionPlan": {"needsPreview": True}}]})
        with pytest.raises(ValueError, match="先生成试片"):
            build_plan(project, board)
        assert build_plan(project, board, shot_id="s")["scope"] == "shot-preview"


def test_edit_invalidates_plan_and_sound_plan_is_saved(client):
    pid = setup_brief(client)
    upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    with SessionLocal() as session:
        row = session.get(DocumentRow, sid)
        data = deepcopy(row.data)
        data["shots"][0]["productionPlan"] = {"reason": "inspected"}
        row.data = data
        session.commit()
    data["shots"][0]["visual"] = "different vehicle"
    saved = client.put(f"/api/v1/projects/{pid}/storyboards/{sid}", json={"shots": data["shots"],
        "totalDurationMs": data["totalDurationMs"], "soundPlan": {"background": "local-pulse", "narration": False}})
    assert saved.status_code == 200
    assert saved.json()["shots"][0]["requiresPlanning"]
    assert "productionPlan" not in saved.json()["shots"][0]
    assert saved.json()["soundPlan"]["background"] == "local-pulse"


def test_portrait_reference_retains_center_and_no_gray_padding(tmp_path):
    source = tmp_path / "wide.png"
    Image.new("RGB", (300, 100), (220, 32, 40)).save(source)
    asset = {"uri": str(source), "sha256": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()}
    prepared = prepare_portrait_reference(asset, {"width": 120, "height": 200}, tmp_path / "portrait.png")
    with Image.open(prepared["uri"]) as image:
        assert image.size == (120, 200)
        assert image.getpixel((60, 100)) == (220, 32, 40)
        assert image.getpixel((60, 0)) == (220, 32, 40)


def test_switch_to_explicit_video_clears_image_replanning_gate(client):
    pid = setup_brief(client)
    upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    with SessionLocal() as session:
        row = session.get(DocumentRow, sid)
        data = deepcopy(row.data)
        data["shots"][0]["requiresPlanning"] = True
        row.data = data
        session.commit()
    data["shots"][0]["sourceStrategy"] = "user-video"
    response = client.put(f"/api/v1/projects/{pid}/storyboards/{sid}", json={"shots": data["shots"], "totalDurationMs": data["totalDurationMs"]})
    assert response.status_code == 200
    assert not response.json()["shots"][0]["requiresPlanning"]
    with SessionLocal() as session:
        # Technical validation still rejects an image passed as a rendered video.
        with pytest.raises(ValueError, match="视频素材"):
            build_plan(session.get(ProjectRow, pid), session.get(DocumentRow, sid))


def test_discovery_samples_color_groups_and_deduplicates_downloads(client, monkeypatch):
    pid = setup_brief(client)
    asset = upload(client, pid)
    monkeypatch.setattr(jobs.get_settings(), "allow_external_search", True)
    monkeypatch.setattr(jobs, "extract_asset_brief", lambda *args: {"subject": "张雪820RR", "clarification": ""})
    candidates = [{"context": f"整车 / 配色组 {group} / 视角 {view}", "imageUrl": f"https://example.com/{group}-{view}.png",
        "sourceUrl": "https://example.com", "modelName": "820RR", "referenceIndex": group * 10 + view}
        for group in range(1, 4) for view in range(1, 5)]
    monkeypatch.setattr(jobs, "manufacturer_images", lambda *args: (candidates, []))
    fetched = []
    with SessionLocal() as session:
        project = session.get(ProjectRow, pid)
        content = Path(next(a for a in project.asset_versions if a["id"] == asset["id"])["uri"]).read_bytes()
        monkeypatch.setattr(jobs, "fetch_public_image", lambda url: fetched.append(url) or content)
        jobs.prepare_images(session, project)
        jobs.prepare_images(session, project)
    assert fetched == [f"https://example.com/{group}-{view}.png" for group in range(1, 4) for view in (1, 2)]


def test_soundtrack_has_actual_nonclipping_audio(tmp_path):
    target = tmp_path / "soundtrack.wav"
    render_soundtrack(2000, target)
    with wave.open(str(target), "rb") as audio:
        assert abs(audio.getnframes() / audio.getframerate() - 2) < .05
        samples = array("h", audio.readframes(audio.getnframes()))
    assert math.sqrt(sum(s * s for s in samples) / len(samples)) > 100
    assert max(abs(s) for s in samples) < 32700


def test_reuse_saved_script_is_independent_and_does_not_call_model(client, monkeypatch):
    pid = setup_brief(client)
    upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    before = client.get(f"/api/v1/projects/{pid}/storyboards/{sid}").json()
    def forbidden(*args, **kwargs):
        raise AssertionError("Copy must not call a model")
    monkeypatch.setattr(gateway, "complete_json", forbidden)
    response = client.post(f"/api/v1/projects/{pid}/copies")
    assert response.status_code == 201, response.text
    copied = response.json()
    assert copied["id"] != pid and copied["currentStoryboardVersionId"] != sid
    state = client.get(f"/api/v1/projects/{copied['id']}/workspace").json()
    assert state["latestAdvisorRunId"] is None and state["activeGenerationRunId"] is None
    after = client.get(f"/api/v1/projects/{copied['id']}/storyboards/{copied['currentStoryboardVersionId']}").json()
    assert after["reusedFromStoryboardId"] == sid
    assert after["status"] == "draft" and after["projectId"] == copied["id"]
    assert after["shots"][0]["id"] != before["shots"][0]["id"]
    assert client.get(f"/api/v1/projects/{pid}/storyboards/{sid}").json() == before


def test_successful_script_survives_matching_failure_and_retry(client, monkeypatch):
    pid = setup_brief(client)
    upload(client, pid)
    original = jobs.assign_assets
    def fail(*args):
        raise gateway.ModelGatewayError("429 reference matching", "RATE_LIMITED", 60)
    monkeypatch.setattr(jobs, "assign_assets", fail)
    client.post(f"/api/v1/projects/{pid}/storyboard-runs?background=true")
    failed = wait_script(client, pid)
    assert failed["status"] == "failed" and failed["draftScript"]["shots"]
    def forbidden(*args):
        raise AssertionError("Successful script must not be regenerated on matching retry")
    monkeypatch.setattr(jobs, "generate_storyboard", forbidden)
    monkeypatch.setattr(jobs, "assign_assets", original)
    client.post(f"/api/v1/projects/{pid}/storyboard-runs?background=true")
    assert wait_script(client, pid)["status"] == "completed"


def test_checked_references_do_not_call_model_again(client, monkeypatch):
    pid = setup_brief(client)
    asset = upload(client, pid)
    def forbidden(*args):
        raise AssertionError("Unchanged verified reference must be reused")
    monkeypatch.setattr(jobs, "match_storyboard_assets", forbidden)
    with SessionLocal() as session:
        project = session.get(ProjectRow, pid)
        data = {"shots": [{"id": "s", "durationMs": 3000, "sourceStrategy": "image-motion", "sourceAssetId": asset["id"],
            "selectionOwner": "platform", "productionPlan": {"referenceChecked": True, "blocker": ""}}]}
        result = jobs.assign_assets(session, project, data)
        assert result["shots"][0]["sourceAssetId"] == asset["id"]


def test_one_click_starts_critical_preview_instead_of_full_film(client):
    pid = setup_brief(client)
    asset = upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    with SessionLocal() as session:
        row = session.get(DocumentRow, sid)
        row.data = {**row.data, "totalDurationMs": 1000, "shots": [{"id": "critical", "durationMs": 1000,
            "sourceAssetId": asset["id"], "sourceStrategy": "image-motion", "selectionOwner": "platform",
            "productionPlan": {"referenceChecked": True, "needsPreview": True, "blocker": ""}}]}
        session.commit()
    url = f"/api/v1/projects/{pid}/storyboards/{sid}/material-runs?generate=true"
    assert client.post(url).status_code == 202
    for _ in range(200):
        material = client.get(f"/api/v1/projects/{pid}/material-runs/latest").json()["run"]
        if material["status"] not in {"queued", "running"}:
            break
        time.sleep(.03)
    assert material["phase"] == "reviewing-preview", material
    assert material["generationRunId"] is None
    assert material["previewShotId"] == "critical"
    preview = client.get(f"/api/v1/generation-runs/{material['previewGenerationRunId']}").json()
    assert preview["scope"] == "shot-preview"
