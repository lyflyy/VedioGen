import hashlib
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from threading import Event
import time

from sqlalchemy import select
from PIL import Image

from vediogen_api import storyboard_jobs as jobs
from vediogen_api.database import SessionLocal
from vediogen_api.models import DocumentRow, ProjectRow, ModelInvocationRow
from test_asset_discovery import create


def wait_materials(client, pid):
    for _ in range(300):
        run = client.get(f"/api/v1/projects/{pid}/material-runs/latest").json()["run"]
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(.03)
    raise AssertionError("Material preparation did not terminate")


def test_unsupported_manufacturer_uses_web_and_keeps_partial_downloads(client, monkeypatch):
    pid = setup_brief(client)
    monkeypatch.setattr(jobs.get_settings(), "allow_external_search", True)
    monkeypatch.setattr(jobs, "extract_asset_brief", lambda *args: {"subject": "Ducati V4"})
    def unsupported(*args):
        raise jobs.PublicMediaError("官网暂不支持此品牌")
    monkeypatch.setattr(jobs, "manufacturer_images", unsupported)
    monkeypatch.setattr(jobs, "search_images", lambda subject: ([{
        "title": f"Ducati V4 {i}", "imageUrl": f"https://example.com/{i}.jpg", "sourceUrl": "https://example.com/v4"}
        for i in range(2)], []))
    buffer = BytesIO()
    Image.new("RGB", (64, 64), "red").save(buffer, format="WEBP")
    content = buffer.getvalue()
    def download(url):
        if url.endswith("0.jpg"):
            raise jobs.PublicMediaError("HTTP 403")
        return content
    monkeypatch.setattr(jobs, "fetch_public_image", download)
    events = []
    with SessionLocal() as session:
        project = session.get(ProjectRow, pid)
        warnings = jobs.prepare_images(session, project, lambda phase, **fields: events.append(phase))
        assert len(project.asset_versions) == 1
        assert project.asset_versions[0]["referenceSource"] == "web"
        assert project.asset_versions[0]["mimeType"] == "image/webp"
        assert project.asset_versions[0]["subjectConfirmedByUser"] is False
        assert any("403" in warning for warning in warnings)
    assert "searching-web" in events and "downloading-assets" in events


def test_single_shot_preparation_preserves_other_shots_and_reports_original_order(client, monkeypatch):
    pid = setup_brief(client)
    asset = upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    with SessionLocal() as session:
        board = session.get(DocumentRow, sid)
        before = deepcopy(board.data)
    target = before["shots"][1]["id"]
    def match(session, project, data, progress=None):
        assert [s["id"] for s in data["shots"]] == [target]
        return {**data, "shots": [{**data["shots"][0], "sourceAssetId": asset["id"], "sourceStrategy": "image-motion"}],
                "soundPlan": {"background": "none", "narration": True},
                "materialChanges": [{"shotId": target, "order": 1, "message": "已匹配"}]}
    monkeypatch.setattr(jobs, "assign_assets", match)
    root = f"/api/v1/projects/{pid}/storyboards/{sid}/material-runs"
    assert client.post(root + "?shot_id=missing").status_code == 404
    assert client.post(root + f"?shot_id={target}&generate=true").status_code == 422
    response = client.post(root + f"?shot_id={target}")
    assert response.status_code == 202
    run = wait_materials(client, pid)
    assert run["status"] == "completed", run
    assert run["changes"][0]["order"] == run["checks"][0]["order"] == 2
    assert len(run["checks"]) == 1
    assert "matching-assets" in [e["phase"] for e in run["events"]]
    with SessionLocal() as session:
        after = session.get(DocumentRow, sid).data
        assert after.get("soundPlan") == before.get("soundPlan")
        assert [s for s in after["shots"] if s["id"] != target] == [s for s in before["shots"] if s["id"] != target]


def test_material_failure_retains_input_scope_and_completed_time(client, monkeypatch):
    pid = setup_brief(client)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    def fail(*args):
        raise jobs.ModelGatewayError("平台：测试模型，HTTP 429")
    monkeypatch.setattr(jobs, "assign_assets", fail)
    response = client.post(f"/api/v1/projects/{pid}/storyboards/{sid}/material-runs")
    run = wait_materials(client, pid)
    assert run["id"] == response.json()["id"]
    assert run["status"] == "failed" and "429" in run["errorMessage"]
    assert run["inputVersion"] and run["completedAt"] and not run.get("resultVersion")
    assert run["events"][-1]["phase"] == "failed"


def setup_brief(client):
    pid = create(client, "张雪820RR，简单图片展示")
    advice = client.post(f"/api/v1/projects/{pid}/advisor-runs").json()
    brief = client.post(f"/api/v1/projects/{pid}/creative-briefs", json={
        "advisorRunId": advice["id"], "proposalKey": advice["result"]["proposals"][0]["proposalKey"], "overrides": {}}).json()
    client.post(f"/api/v1/projects/{pid}/creative-briefs/{brief['id']}/approval", json={})
    return pid


def upload(client, pid):
    content = (Path(__file__).resolve().parents[3] / "apps/web/public/images/motorcycle-studio.jpg").read_bytes()
    intent = client.post("/api/v1/assets/upload-intents", json={"projectId": pid, "fileName": "reference.jpg",
        "mimeType": "image/jpeg", "sizeBytes": len(content), "sha256": "sha256:" + hashlib.sha256(content).hexdigest()}).json()
    return client.put(intent["uploadUrl"], content=content).json()


def wait(client, pid):
    for _ in range(200):
        run = client.get(f"/api/v1/projects/{pid}/storyboard-runs/latest").json()["run"]
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(.03)
    raise AssertionError("Preparation did not terminate")


def test_background_script_returns_before_model_and_survives_refresh(client, monkeypatch):
    pid = setup_brief(client)
    asset = upload(client, pid)
    entered, release = Event(), Event()
    original = jobs.generate_storyboard
    def generate(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)
    monkeypatch.setattr(jobs, "generate_storyboard", generate)
    root = f"/api/v1/projects/{pid}"
    try:
        result = client.post(root + "/storyboard-runs?background=true")
        assert result.status_code == 202
        assert entered.wait(5)
        run = client.get(root + "/storyboard-runs/latest").json()["run"]
        assert run["phase"] == "writing-script" and run["status"] == "running"
        assert client.post(root + "/storyboard-runs?background=true").json()["id"] == run["id"]
    finally:
        release.set()
    done = wait(client, pid)
    assert done["status"] == "completed", done
    assert [event["phase"] for event in done["events"]] == ["preparing-assets", "writing-script", "matching-assets", "checking-shots", "completed"]
    storyboard = client.get(root + f"/storyboards/{done['storyboardVersionId']}").json()
    eligible = [shot for shot in storyboard["shots"] if shot["sourceStrategy"] in {"image-motion", "image-to-video"}]
    assert eligible and all(shot["sourceAssetId"] == asset["id"] for shot in eligible)


def test_background_failure_can_be_explicitly_retried(client, monkeypatch):
    pid = setup_brief(client)
    original = jobs.generate_storyboard
    def fail(*args):
        raise jobs.ModelGatewayError("Test provider failed")
    monkeypatch.setattr(jobs, "generate_storyboard", fail)
    url = f"/api/v1/projects/{pid}/storyboard-runs?background=true"
    first = client.post(url).json()
    failed = wait(client, pid)
    assert failed["status"] == "failed"
    assert failed["errorMessage"] == "Test provider failed"
    monkeypatch.setattr(jobs, "generate_storyboard", original)
    second = client.post(url).json()
    assert second["id"] != first["id"]
    assert wait(client, pid)["status"] == "completed"


def test_auto_matching_preserves_bound_assets_and_complex_shots(client):
    pid = setup_brief(client)
    asset = upload(client, pid)
    run = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()
    sid = run["storyboardVersionId"]
    with SessionLocal() as session:
        row = session.get(DocumentRow, sid)
        first = {**row.data["shots"][0], "sourceAssetId": asset["id"], "sourceStrategy": "image-motion"}
        second = {**row.data["shots"][1], "sourceStrategy": "blender-3d", "blenderTemplate": "orbit-360"}
        second.pop("sourceAssetId", None)
        third = {**row.data["shots"][2], "sourceStrategy": "image-motion"}
        third.pop("sourceAssetId", None)
        row.data = {**row.data, "shots": [first, second, third]}
        session.commit()
    response = client.post(f"/api/v1/projects/{pid}/storyboards/{sid}/auto-materials")
    assert response.status_code == 200, response.text
    shots = response.json()["shots"]
    assert shots[0]["sourceAssetId"] == shots[2]["sourceAssetId"] == asset["id"]
    assert shots[1]["sourceStrategy"] == "blender-3d" and not shots[1].get("sourceAssetId")
    checks = client.get(f"/api/v1/projects/{pid}/storyboards/{sid}/readiness").json()
    assert [c["ready"] for c in checks["shots"]] == [True, False, True]


def test_text_only_preparation_downloads_without_user_upload(client, monkeypatch):
    pid = setup_brief(client)
    monkeypatch.setattr(jobs.get_settings(), "allow_external_search", True)
    monkeypatch.setattr(jobs, "extract_asset_brief", lambda *args: {"subject": "张雪820RR", "clarification": ""})
    monkeypatch.setattr(jobs, "manufacturer_images", lambda _: ([{
        "modelName": "张雪 820RR", "context": "整车 / 配色组 1 / 视角 1", "referenceIndex": 1,
        "sourceUrl": "https://www.zxmoto.com/index.php?c=show&id=58", "imageUrl": "https://www.zxmoto.com/uploadfile/202603/reference.png",
        "requiresVariantConfirmation": False}], []))
    content = (Path(__file__).resolve().parents[3] / "apps/web/public/images/motorcycle-studio.jpg").read_bytes()
    monkeypatch.setattr(jobs, "fetch_public_image", lambda _: content)
    client.post(f"/api/v1/projects/{pid}/storyboard-runs?background=true")
    assert wait(client, pid)["status"] == "completed"
    with SessionLocal() as session:
        assets = session.get(ProjectRow, pid).asset_versions
        assert len(assets) == 1 and assets[0]["preparedBy"] == "platform"
        assert assets[0]["subjectConfirmedByUser"] is False
        assert Path(assets[0]["uri"]).read_bytes() == content


def test_matching_does_not_overwrite_edits_made_while_model_runs(client, monkeypatch):
    pid = setup_brief(client)
    upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    original = jobs.assign_assets
    def concurrent_edit(session, project, data):
        with SessionLocal() as other:
            row = other.get(DocumentRow, sid)
            row.data = {**row.data, "userEdit": "keep this"}
            row.row_version += 1
            other.commit()
        return original(session, project, data)
    monkeypatch.setattr(jobs, "assign_assets", concurrent_edit)
    result = client.post(f"/api/v1/projects/{pid}/storyboards/{sid}/auto-materials")
    assert result.status_code == 409
    with SessionLocal() as session:
        assert session.get(DocumentRow, sid).data["userEdit"] == "keep this"


def test_material_repair_preserves_timing_and_reference_without_model(client, monkeypatch):
    pid = setup_brief(client)
    asset = upload(client, pid)
    monkeypatch.setattr(jobs.get_settings(), "allow_local_models", True)
    client.put("/api/v1/admin/video-settings", json={"backend": "comfyui", "enabled": True})
    def unexpected(*args):
        raise AssertionError("Bound reference does not require another model call")
    monkeypatch.setattr(jobs, "match_storyboard_assets", unexpected)
    with SessionLocal() as session:
        data = jobs.assign_assets(session, session.get(ProjectRow, pid), {"shots": [
            {"id": "six", "sourceStrategy": "user-video", "sourceAssetId": asset["id"], "durationMs": 2800,
             "visual": "Leather rider driving at speed", "camera": "tracking", "purpose": "ending"}]})
    shot = data["shots"][0]
    assert shot["sourceStrategy"] == "image-to-video"
    assert shot["sourceAssetId"] == asset["id"] and shot["durationMs"] == 2800
    assert "Leather rider" in shot["videoPrompt"]
    assert len(data["materialChanges"]) == 2


def test_background_materials_deduplicate_report_and_preserve_shot_numbers(client, monkeypatch):
    pid = setup_brief(client)
    upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    entered, release = Event(), Event()
    original = jobs.assign_assets
    def slow(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)
    monkeypatch.setattr(jobs, "assign_assets", slow)
    root = f"/api/v1/projects/{pid}"
    try:
        first = client.post(root + f"/storyboards/{sid}/material-runs")
        assert first.status_code == 202
        assert entered.wait(5)
        second = client.post(root + f"/storyboards/{sid}/material-runs")
        assert first.json()["id"] == second.json()["id"]
        with SessionLocal() as session:
            shot_id = session.get(DocumentRow, sid).data["shots"][0]["id"]
        assert client.post(root + f"/storyboards/{sid}/material-runs?shot_id={shot_id}").status_code == 409
    finally:
        release.set()
    for _ in range(200):
        run = client.get(root + "/material-runs/latest").json()["run"]
        if run["status"] not in {"queued", "running"}:
            break
        time.sleep(.03)
    assert run["status"] in {"completed", "needs_attention"}, run
    assert [c["order"] for c in run["checks"]] == list(range(1, len(run["checks"]) + 1))
    for check in run["checks"]:
        if check["reason"] and "需要选择本项目" in check["reason"]:
            assert check["reason"].startswith(f"镜头 {check['order']} ")


def test_prepare_and_generate_starts_ready_preview_despite_other_blocked_shots(client):
    from test_creator_flow import wait_generation
    pid = setup_brief(client)
    asset = upload(client, pid)
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    with SessionLocal() as session:
        board = session.get(DocumentRow, sid)
        shots = deepcopy(board.data["shots"][:2])
        shots[0].update(sourceStrategy="blender-3d", sourceAssetId=None)
        shots[1].update(sourceStrategy="image-motion", sourceAssetId=asset["id"], requiresPlanning=False,
                        selectionOwner="platform", productionPlan={"referenceChecked": True, "needsPreview": True})
        board.data = {**board.data, "shots": shots}
        session.commit()
    response = client.post(f"/api/v1/projects/{pid}/storyboards/{sid}/material-runs?generate=true")
    assert response.status_code == 202, response.text
    run = wait_materials(client, pid)
    assert run["phase"] == "reviewing-preview", run
    assert run["previewShotId"] == shots[1]["id"]
    assert run["checks"][0]["technicalReady"] is False
    preview = wait_generation(client, run["previewGenerationRunId"])
    assert preview["status"] == "completed", preview
    assert preview["scope"] == "shot-preview"
    with SessionLocal() as session:
        current = session.get(DocumentRow, sid)
        assert not current.data["shots"][1].get("previewRunId")
        assert current.data["shots"][0]["sourceStrategy"] == "blender-3d"
