import socket
import time
import threading
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace

import httpx
import pytest

from vediogen_api import asset_discovery, gateway, public_media
from vediogen_api.config import get_settings
from vediogen_api.database import SessionLocal
from vediogen_api.models import DocumentRow, ModelProviderRow, ProjectRow
from vediogen_api.openai_compatible import StructuredCompletion
from test_creator_flow import wait_generation


def create(client, message="春风 800MT，先环绕，再沙漠，最后山林远拉"):
    return client.post("/api/v1/projects", json={"title": "最酷视频", "initialMessage": message}).json()["id"]


def test_ducati_alias_does_not_match_other_brands_or_explicit_families():
    assert asset_discovery.matches_subject("杜卡迪 V4", "Ducati Panigale V4 motorcycle")
    assert not asset_discovery.matches_subject("杜卡迪 V4", "Aprilia RSV4")
    assert not asset_discovery.matches_subject("杜卡迪 V4", "Ducati Panigale V4R")
    assert not asset_discovery.matches_subject("杜卡迪 Panigale V4", "Ducati Multistrada V4")


def wait_discovery(client, project_id):
    for _ in range(300):
        run = client.get(f"/api/v1/projects/{project_id}/asset-discoveries/latest").json()["run"]
        if run and run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.02)
    pytest.fail("discovery did not finish")


@pytest.fixture
def search_sources(monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    monkeypatch.setattr(asset_discovery, "extract_asset_brief", lambda *args: {
        "subject": "春风 800MT", "requiredShots": ["环绕", "沙漠", "山林远拉"], "clarification": ""})
    monkeypatch.setattr(asset_discovery, "DDGS", lambda **kwargs: SimpleNamespace(images=lambda *args, **kwargs: [
        {"title": "CFMOTO 800MT motorcycle", "image": "https://media.example.test/800mt.jpg", "url": "https://source.example.test/800mt", "thumbnail": "https://media.example.test/thumb.jpg"},
        {"title": "KOVE 800X", "image": "https://media.example.test/wrong.jpg", "url": "https://source.example.test/kove"},
        {"title": "CFMOTO 800MTX", "image": "https://media.example.test/variant.jpg", "url": "https://source.example.test/mtx"},
    ]))
    image = (Path(__file__).resolve().parents[3] / "apps/web/public/images/motorcycle-studio.jpg").read_bytes()
    real_client = httpx.Client
    def handler(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "media.example.test"
        assert request.extensions["sni_hostname"] == "media.example.test"
        assert "authorization" not in request.headers
        return httpx.Response(200, content=image)
    monkeypatch.setattr(public_media.socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    monkeypatch.setattr(public_media.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def test_text_only_to_candidates_actual_import_and_composition(client, search_sources):
    project_id = create(client)
    path = f"/api/v1/projects/{project_id}/asset-discoveries"
    before = client.get(f"/api/v1/projects/{project_id}/workspace").json()
    assert not before["assetVersions"]
    assert not any(fact["key"] == "subject.vehicle.name" for fact in before["facts"])
    assert client.post(path, json={}).status_code == 202
    run = wait_discovery(client, project_id)
    assert run["status"] == "ready" and len(run["result"]["candidates"]) == 1
    assert run["result"]["requiredShots"] == ["环绕", "沙漠", "山林远拉"]
    candidate = run["result"]["candidates"][0]
    endpoint = f"{path}/{run['id']}/candidates/{candidate['id']}/import"
    assert client.post(endpoint, json={}).status_code == 422
    response = client.post(endpoint, json={"confirmSubject": True})
    assert response.status_code == 201, response.text
    asset_id = response.json()["assetId"]
    assert client.post(endpoint, json={"confirmSubject": True}).json()["assetId"] == asset_id
    workspace = client.get(f"/api/v1/projects/{project_id}/workspace").json()
    assert len(workspace["assetVersions"]) == 1
    asset = workspace["assetVersions"][0]
    assert asset["sourceType"] == "web-reference" and asset["subjectConfirmedByUser"] is True
    assert "uri" not in asset and client.get(asset["previewUrl"]).status_code == 200
    with SessionLocal() as session:
        doc = DocumentRow(id=str(uuid4()), project_id=project_id, kind="storyboard", version=1, status="approved",
            data={"shots": [{"id": str(uuid4()), "sourceStrategy": "image-motion", "sourceAssetId": asset_id, "durationMs": 1000, "caption": "参考素材链路测试"}]})
        session.add(doc)
        session.commit()
        storyboard_id = doc.id
    result = client.post("/api/v1/generation-runs", json={"projectId": project_id, "storyboardVersionId": storyboard_id, "quality": "preview"})
    final = wait_generation(client, result.json()["id"])
    assert final["mode"] == "uploaded-media"
    assert client.get(f"/api/v1/artifacts/{final['finalArtifactId']}/content").status_code == 200


def test_search_empty_does_not_invent_asset(client, monkeypatch, search_sources):
    monkeypatch.setattr(asset_discovery, "DDGS", lambda **kwargs: SimpleNamespace(images=lambda *args, **kwargs: [{"title": "KOVE 800X", "image": "https://media.test/x.jpg", "url": "https://source.test/x"}]))
    project_id = create(client, "张雪 800X 的环绕")
    client.post(f"/api/v1/projects/{project_id}/asset-discoveries", json={"subject": "张雪 800X"})
    run = wait_discovery(client, project_id)
    assert run["status"] == "empty" and not run["result"]["candidates"]
    assert not client.get(f"/api/v1/projects/{project_id}/workspace").json()["assetVersions"]


def test_focus_queries_keep_vehicle_identity_and_are_persisted(client, monkeypatch, search_sources):
    queries = []
    def images(query, **kwargs):
        queries.append(query)
        return [{"title": "CFMOTO 800MT instrument panel", "image": "https://media.example.test/dashboard.jpg", "url": "https://source.example.test/800mt"},
                {"title": "KOVE 800X instrument panel", "image": "https://media.example.test/wrong.jpg", "url": "https://source.example.test/kove"}]
    monkeypatch.setattr(asset_discovery, "DDGS", lambda **kwargs: SimpleNamespace(images=images))
    project_id = create(client)
    path = f"/api/v1/projects/{project_id}/asset-discoveries"
    assert client.post(path, json={"focus": " 仪表特写 "}).status_code == 202
    run = wait_discovery(client, project_id)
    assert queries == ["春风 800MT 仪表特写", "CFMOTO 800MT motorcycle 仪表特写"]
    assert run["result"]["subject"] == "春风 800MT"
    assert run["result"]["origin"] == "model-extraction"
    assert run["result"]["searchFocus"] == "仪表特写"
    candidates = run["result"]["candidates"]
    assert len(candidates) == 1 and candidates[0]["sceneMatchStatus"] == "unverified"
    assert any("逐图确认" in message for message in run["result"]["warnings"])
    response = client.post(f"{path}/{run['id']}/candidates/{candidates[0]['id']}/import", json={"confirmSubject": True})
    assert response.status_code == 201, response.text
    asset = client.get(f"/api/v1/projects/{project_id}/workspace").json()["assetVersions"][0]
    assert asset["searchFocus"] == "仪表特写"


def test_changing_focus_during_search_is_not_treated_as_same_request(client, monkeypatch, search_sources):
    entered, release = threading.Event(), threading.Event()
    def search(subject, focus=""):
        entered.set()
        assert release.wait(10)
        return [], []
    monkeypatch.setattr(asset_discovery, "search_images", search)
    project_id = create(client)
    path = f"/api/v1/projects/{project_id}/asset-discoveries"
    body = {"subject": "春风800MT", "focus": "仪表"}
    try:
        first = client.post(path, json=body)
        assert first.status_code == 202
        assert entered.wait(5)
        assert client.post(path, json=body).json()["id"] == first.json()["id"]
        assert client.post(path, json={**body, "focus": "涉水"}).status_code == 409
        assert client.post(path, json={**body, "source": "manufacturer"}).status_code == 409
    finally:
        release.set()
    assert wait_discovery(client, project_id)["status"] == "empty"


def test_focus_limit_rejects_before_search(client):
    project_id = create(client)
    response = client.post(f"/api/v1/projects/{project_id}/asset-discoveries", json={"focus": "x" * 161})
    assert response.status_code == 422
    assert client.get(f"/api/v1/projects/{project_id}/asset-discoveries/latest").json()["run"] is None


def test_model_cannot_silently_replace_user_subject(client, monkeypatch, search_sources):
    project_id = create(client, "张雪 800X 的环绕")
    client.post(f"/api/v1/projects/{project_id}/asset-discoveries", json={})
    run = wait_discovery(client, project_id)
    assert run["status"] == "failed" and "未出现在" in run["errorMessage"]


def test_stale_or_cross_project_candidate_cannot_be_imported(client, search_sources):
    project_id = create(client)
    client.post(f"/api/v1/projects/{project_id}/asset-discoveries", json={})
    run = wait_discovery(client, project_id)
    suffix = f"/asset-discoveries/{run['id']}/candidates/{run['result']['candidates'][0]['id']}/import"
    other = create(client)
    assert client.post(f"/api/v1/projects/{other}{suffix}", json={"confirmSubject": True}).status_code == 404
    with SessionLocal() as session:
        project = session.get(ProjectRow, project_id)
        project.messages = [*project.messages, {"role": "user", "text": "现在换一款车"}]
        session.commit()
    assert client.post(f"/api/v1/projects/{project_id}{suffix}", json={"confirmSubject": True}).status_code == 409


def test_search_errors_are_not_success_or_secret_echo(client, monkeypatch, search_sources):
    def unavailable(*args, **kwargs):
        raise RuntimeError("private-proxy-password")
    monkeypatch.setattr(asset_discovery, "DDGS", lambda **kwargs: SimpleNamespace(images=unavailable))
    project_id = create(client)
    client.post(f"/api/v1/projects/{project_id}/asset-discoveries", json={})
    run = wait_discovery(client, project_id)
    assert run["status"] == "failed" and "private-proxy" not in run["errorMessage"]


def test_tls_failure_uses_bounded_http_fallback_and_existing_name_filter(client, monkeypatch):
    import html
    import json
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    def fail(*args, **kwargs):
        raise RuntimeError("SelectedUnofferedKxGroup")
    monkeypatch.setattr(asset_discovery, "DDGS", lambda **kwargs: SimpleNamespace(images=fail))
    items = [{"t": "CFMOTO 800MT", "murl": "https://media.test/correct.jpg", "purl": "https://source.test/correct"},
             {"t": "KOVE 800X", "murl": "https://media.test/wrong.jpg", "purl": "https://source.test/wrong"}]
    page = "".join('<div><div class="imgpt"><a class="iusc" m="' + html.escape(json.dumps(item)) +
                   '"></a></div><div class="infopt"></div></div>' for item in items)
    original = httpx.Client
    def handler(request):
        assert request.url.host == "cn.bing.com"
        assert request.url.params["q"] in {"春风 800MT", "CFMOTO 800MT motorcycle"}
        assert "authorization" not in request.headers
        return httpx.Response(200, text=page, headers={"content-type": "text/html; charset=utf-8"})
    monkeypatch.setattr(asset_discovery.httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    candidates, warnings = asset_discovery.search_images("春风 800MT")
    assert len(candidates) == 1
    assert candidates[0]["imageUrl"] == "https://media.test/correct.jpg"
    assert candidates[0]["matchStatus"] == "name-match-only"
    assert any("备用连接" in message for message in warnings)


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"location": "http://127.0.0.1/"}),
                                    httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1), headers={"content-type": "text/html"}),
                                    httpx.Response(200, text="not html", headers={"content-type": "application/json"})])
def test_search_fallback_rejects_redirects_oversized_and_non_html(client, monkeypatch, response):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    original = httpx.Client
    calls = []
    def handler(request):
        calls.append(request.url)
        return response
    monkeypatch.setattr(asset_discovery.httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    with pytest.raises((httpx.HTTPStatusError, public_media.PublicMediaError)):
        asset_discovery.bing_http_images("CFMOTO 800MT")
    assert len(calls) == 1


def test_asset_extraction_uses_existing_gpt_route_and_strict_schema(client, monkeypatch):
    project_id = create(client)
    monkeypatch.setattr(get_settings(), "allow_external_models", True)
    result = {"subject": "春风 800MT", "requiredShots": ["环绕", "沙漠", "最后山林远拉"], "clarification": ""}
    def complete(**kwargs):
        assert kwargs["schema_name"] == "vediogen_asset_brief"
        assert kwargs["schema"]["additionalProperties"] is False
        assert "春风 800MT" in kwargs["user_prompt"]
        return StructuredCompletion(result, "test-extraction", "test-model", 1, 1, 1)
    monkeypatch.setattr(gateway, "complete_json", complete)
    with SessionLocal() as session:
        provider = session.get(ModelProviderRow, "local-fake")
        provider.adapter_type = "openai-compatible"
        session.commit()
        project = session.get(ProjectRow, project_id)
        assert gateway.extract_asset_brief(session, project, project.messages) == result


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"])
def test_public_media_blocks_internal_dns(monkeypatch, address):
    monkeypatch.setattr(public_media.socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(public_media.PublicMediaError, match="非公开"):
        public_media.fetch_public_image("https://media.test/x.jpg")


@pytest.mark.parametrize("subject,title,match", [("张雪 800X", "KOVE 800X", False), ("春风 800MT", "CFMOTO 800MTX", False), ("春风 800MT", "CFMOTO 800MT-X", False), ("春风 800MT-X", "CFMOTO 800MT-X", True), ("春风 800MT", "CFMOTO 800MT Explore", True), ("张雪 800X", "ZXMOTO 800X", True)])
def test_brand_and_model_matching(subject, title, match):
    assert asset_discovery.matches_subject(subject, title) is match
