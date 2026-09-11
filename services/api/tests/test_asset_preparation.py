import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image

from vediogen_api.database import SessionLocal
from vediogen_api.models import DocumentRow, ProjectRow
from test_media_generation import prepared, start, upload
from test_creator_flow import wait_generation


def image_bytes(orientation=None):
    image = Image.new("RGB", (256, 128), "red")
    image.paste("blue", (128, 0, 256, 128))
    output = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(output, format="PNG", exif=exif)
    return output.getvalue()


def project_asset(client, **kwargs):
    project = client.post("/api/v1/projects", json={"title": "裁剪测试", "initialMessage": "只有文字"}).json()
    asset = upload(client, project["id"], image_bytes(**kwargs), "reference.png", "image/png")
    return project["id"], asset


def test_crop_is_exact_preserves_original_and_provenance(client):
    project_id, source = project_asset(client)
    with SessionLocal() as session:
        project = session.get(ProjectRow, project_id)
        project.asset_versions = [{**source, "sourceType": "web-reference", "subject": "春风800MT",
                                   "sourceUrl": "https://example.com/reference", "subjectConfirmedByUser": False}]
        session.commit()
    response = client.post(f"/api/v1/projects/{project_id}/assets/{source['id']}/crops",
                           json={"x": 50, "y": 0, "width": 50, "height": 100})
    assert response.status_code == 201, response.text
    crop = response.json()
    assert "uri" not in crop
    assert crop["sourceAssetId"] == source["id"]
    assert crop["sourceType"] == "prepared-reference"
    assert crop["subjectConfirmedByUser"] is False
    assert crop["sourceUrl"] == "https://example.com/reference"
    assert crop["cropPixels"] == {"x": 128, "y": 0, "width": 128, "height": 128}
    content = client.get(crop["previewUrl"]).content
    assert crop["sha256"] == "sha256:" + hashlib.sha256(content).hexdigest()
    with Image.open(io.BytesIO(content)) as image:
        assert image.size == (128, 128)
        assert image.getpixel((64, 64)) == (0, 0, 255)
    assert Path(source["uri"]).read_bytes() == image_bytes()
    workspace = client.get(f"/api/v1/projects/{project_id}/workspace").json()
    assert len(workspace["assetVersions"]) == 2


def test_crop_coordinates_follow_displayed_exif_orientation(client):
    project_id, source = project_asset(client, orientation=6)
    response = client.post(f"/api/v1/projects/{project_id}/assets/{source['id']}/crops",
                           json={"x": 0, "y": 50, "width": 100, "height": 50})
    assert response.status_code == 201, response.text
    with Image.open(io.BytesIO(client.get(response.json()["previewUrl"]).content)) as image:
        assert image.size == (128, 128)
        assert image.getpixel((64, 64)) == (0, 0, 255)
        assert image.getexif().get(274, 1) == 1


def test_half_pixel_rounding_matches_browser(client):
    project_id, source = project_asset(client)
    response = client.post(f"/api/v1/projects/{project_id}/assets/{source['id']}/crops",
                           json={"x": 32.5 / 256 * 100, "y": 0, "width": 50, "height": 100})
    assert response.status_code == 201
    assert response.json()["cropPixels"] == {"x": 33, "y": 0, "width": 128, "height": 128}


@pytest.mark.parametrize("bounds", [
    {"x": -1, "y": 0, "width": 50, "height": 100},
    {"x": 75, "y": 0, "width": 50, "height": 100},
    {"x": 0, "y": 80, "width": 50, "height": 30},
    {"x": 0, "y": 0, "width": 0, "height": 100},
    {"x": "NaN", "y": 0, "width": 50, "height": 100},
    {"x": 0, "y": 0, "width": 1, "height": 100},
])
def test_invalid_crop_does_not_create_an_asset(client, bounds):
    project_id, source = project_asset(client)
    response = client.post(f"/api/v1/projects/{project_id}/assets/{source['id']}/crops", json=bounds)
    assert response.status_code == 422
    assert len(client.get(f"/api/v1/projects/{project_id}/workspace").json()["assetVersions"]) == 1


def test_foreign_asset_and_changed_source_are_rejected(client):
    project_id, source = project_asset(client)
    other, _ = project_asset(client)
    bounds = {"x": 50, "y": 0, "width": 50, "height": 100}
    assert client.post(f"/api/v1/projects/{other}/assets/{source['id']}/crops", json=bounds).status_code == 404
    Path(source["uri"]).write_bytes(b"changed")
    assert client.post(f"/api/v1/projects/{project_id}/assets/{source['id']}/crops", json=bounds).status_code == 422


def test_crop_flows_into_actual_generation_without_changing_other_shots(client):
    project_id, storyboard_id, shots = prepared(client)
    source = upload(client, project_id, image_bytes(), "reference.png", "image/png")
    crop = client.post(f"/api/v1/projects/{project_id}/assets/{source['id']}/crops",
                       json={"x": 50, "y": 0, "width": 50, "height": 100}).json()
    shots[0]["sourceAssetId"] = crop["id"]
    with SessionLocal() as session:
        document = session.get(DocumentRow, storyboard_id)
        document.data = {**document.data, "shots": shots}
        session.commit()
    run = wait_generation(client, start(client, project_id, storyboard_id).json()["id"])
    assert run["shotRuns"][0]["sourceAssetId"] == crop["id"]
    assert run["shotRuns"][1]["sourceAssetId"] == shots[1]["sourceAssetId"]
    assert client.get(f"/api/v1/artifacts/{run['finalArtifactId']}/content").status_code == 200
