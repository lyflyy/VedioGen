import hashlib
from pathlib import Path

from vediogen_api.media import create_preview_video


def test_creator_flow_generates_downloadable_vertical_video(client):
    brief = client.put(
        "/api/v1/account-brief",
        json={
            "contentPackId": "motorcycle",
            "accountGoal": "摩托车账号日更",
            "audience": ["摩托车爱好者"],
            "tone": ["专业", "有冲击力"],
            "publishingCadence": "daily",
            "preferences": {"durationSeconds": 24},
            "rowVersion": None,
        },
    )
    assert brief.status_code == 200
    assert brief.json()["publishingCadence"] == "daily"

    created = client.post(
        "/api/v1/projects",
        json={
            "title": "张雪 800X 最酷视频",
            "contentPackId": "motorcycle",
            "mode": "real-subject",
            "targetPlatform": "douyin",
            "locale": "zh-CN",
            "initialMessage": "360 度环绕、车辆细节，最后皮衣骑手高速驾驶。",
            "assetVersionIds": [],
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    asset_content = b"deterministic-motorcycle-reference"
    upload_intent = client.post(
        "/api/v1/assets/upload-intents",
        json={
            "projectId": project_id,
            "fileName": "reference.jpg",
            "mimeType": "image/jpeg",
            "sizeBytes": len(asset_content),
            "sha256": "sha256:" + hashlib.sha256(asset_content).hexdigest(),
        },
    )
    assert upload_intent.status_code == 201
    uploaded = client.put(upload_intent.json()["uploadUrl"], content=asset_content, headers={"Content-Type": "image/jpeg"})
    assert uploaded.status_code == 201
    assert uploaded.json()["status"] == "ready"

    workspace = client.get(f"/api/v1/projects/{project_id}/workspace")
    assert workspace.status_code == 200
    assert workspace.json()["facts"][0]["status"] == "confirmed"
    assert workspace.json()["assetVersions"][0]["sha256"] == "sha256:" + hashlib.sha256(asset_content).hexdigest()

    advisor = client.post(f"/api/v1/projects/{project_id}/advisor-runs")
    assert advisor.status_code == 202
    advisor_body = advisor.json()
    assert len(advisor_body["result"]["proposals"]) == 3
    invocations = client.get("/api/v1/admin/model-invocations?capabilityAlias=creative-advisor").json()["items"]
    assert any(item["projectId"] == project_id and item["status"] == "succeeded" for item in invocations)

    brief = client.post(
        f"/api/v1/projects/{project_id}/creative-briefs",
        json={"advisorRunId": advisor_body["id"], "proposalKey": "cinematic-reveal", "overrides": {}},
    )
    assert brief.status_code == 201
    brief_id = brief.json()["id"]
    assert client.post(f"/api/v1/projects/{project_id}/creative-briefs/{brief_id}/approval", json={}).status_code == 201

    storyboard_run = client.post(f"/api/v1/projects/{project_id}/storyboard-runs")
    assert storyboard_run.status_code == 202
    storyboard_id = storyboard_run.json()["storyboardVersionId"]
    storyboard = client.get(f"/api/v1/projects/{project_id}/storyboards/{storyboard_id}").json()
    assert len(storyboard["shots"]) == 5
    assert storyboard["totalDurationMs"] == 12000
    assert client.post(f"/api/v1/projects/{project_id}/storyboards/{storyboard_id}/approval", json={}).status_code == 201

    generation = client.post(
        "/api/v1/generation-runs",
        json={"projectId": project_id, "storyboardVersionId": storyboard_id},
    )
    assert generation.status_code == 202, generation.text
    generation_body = generation.json()
    assert generation_body["status"] == "completed"
    assert len(generation_body["shotRuns"]) == 5

    artifact_id = generation_body["finalArtifactId"]
    artifact = client.get(f"/api/v1/artifacts/{artifact_id}").json()
    assert artifact["width"] == 540
    assert artifact["height"] == 960
    assert artifact["durationMs"] == 6000
    assert artifact["sha256"].startswith("sha256:")

    media = client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("video/mp4")
    assert len(media.content) > 10_000


def test_retry_only_adds_attempt_for_selected_shot(client):
    projects = client.get("/api/v1/projects").json()["items"]
    project = next(item for item in projects if item["title"] == "张雪 800X 最酷视频")
    workspace = client.get(f"/api/v1/projects/{project['id']}/workspace").json()
    run = client.get(f"/api/v1/generation-runs/{workspace['activeGenerationRunId']}").json()
    original_count = len(run["shotRuns"])
    selected = run["shotRuns"][1]
    retried = client.post(f"/api/v1/generation-runs/{run['id']}/shots/{selected['shotId']}/retries")
    assert retried.status_code == 202
    after = client.get(f"/api/v1/generation-runs/{run['id']}").json()
    assert len(after["shotRuns"]) == original_count + 1
    assert after["shotRuns"][-1]["shotId"] == selected["shotId"]
    assert after["shotRuns"][-1]["attempt"] == 2


def test_preview_media_is_deterministic(tmp_path):
    first = create_preview_video(tmp_path / "first.mp4")
    second = create_preview_video(tmp_path / "second.mp4")
    assert first["sha256"] == second["sha256"]
    assert first["width"] == 540
    assert first["height"] == 960
    assert first["durationMs"] == 6000
