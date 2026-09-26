from copy import deepcopy

from vediogen_api.database import SessionLocal
from vediogen_api.models import DocumentRow
from test_creator_flow import wait_generation
from test_storyboard_jobs import setup_brief, upload


def test_reference_cut_requires_confirmation_preserves_original_and_renders(client):
    pid = setup_brief(client)
    assets = [upload(client, pid), upload(client, pid)]
    sid = client.post(f"/api/v1/projects/{pid}/storyboard-runs").json()["storyboardVersionId"]
    with SessionLocal() as session:
        board = session.get(DocumentRow, sid)
        data = deepcopy(board.data)
        data["shots"][0].update(sourceStrategy="blender-3d", sourceAssetId=None,
                                productionPlan={"blocker": "Missing accurate geometry", "exactOrbit": True})
        board.data = data
        session.commit()
    endpoint = f"/api/v1/projects/{pid}/reference-cuts"
    before = client.get(f"/api/v1/projects/{pid}/storyboards/{sid}").json()
    request = {"storyboardVersionId": sid, "rowVersion": before["rowVersion"], "assetIds": [a["id"] for a in assets]}
    assert client.post(endpoint, json=request).status_code == 422
    request["confirmSimplification"] = True
    assert client.post(endpoint, json={**request, "rowVersion": before["rowVersion"] + 1}).status_code == 409
    assert client.post(endpoint, json={**request, "assetIds": ["foreign-asset"]}).status_code == 422
    response = client.post(endpoint, json=request)
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["projectId"] != pid
    copied = result["run"]["storyboardVersionId"]
    after = client.get(f"/api/v1/projects/{result['projectId']}/storyboards/{copied}").json()
    assert after["executionVariant"] == "reference-display"
    assert after["totalDurationMs"] == 6000
    assert all(s["sourceStrategy"] == "image-motion" and not s.get("productionPlan") for s in after["shots"])
    run = wait_generation(client, result["run"]["id"])
    assert run["status"] == "completed", run
    assert run["audioMode"] == "local-soundtrack"
    assert client.get(f"/api/v1/artifacts/{run['finalArtifactId']}/content").status_code == 200
    assert client.get(f"/api/v1/projects/{pid}/storyboards/{sid}").json() == before
    repeated = client.post(endpoint, json=request).json()
    assert repeated["projectId"] == result["projectId"] and repeated["run"]["id"] == run["id"]
