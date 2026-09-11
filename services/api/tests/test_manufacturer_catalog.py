import json
from html import escape
from pathlib import Path

import httpx
import pytest

from vediogen_api import manufacturer_catalog as catalog, asset_discovery
from vediogen_api.config import get_settings
from test_asset_discovery import create, wait_discovery

parse = catalog.catalog_from_html


def image(name="detail.jpg", host="cfimages.cfmoto.com"):
    return {"name": name, "mime": "image/jpeg", "url": f"https://{host}/{name}", "width": 1920, "height": 1280}


def test_official_catalog_preserves_version_and_ignores_unrelated_sections():
    document = {"props": {"pageProps": {"vehicleData": {"name": "800MT-ES", "block": [
        {"__component": "vehicle.vehicle-safe", "title": "仪表", "img": image()},
        {"__component": "vehicle.vehicle-recommend", "title": "其他车型", "img": image("wrong.jpg")},
        {"__component": "vehicle.find-store", "img": image("shop.jpg")},
        {"title": "重复", "img": image()},
        {"title": "外部广告", "img": image("ad.jpg", "example.com")},
    ]}}}}
    page = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(document) + '</script><script>{"other":true}</script>'
    result = parse(page, "https://www.cfmoto.com/motorcycles/800mt-es")
    assert result["model"] == "800MT-ES"
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["context"] == "仪表"
    assert result["candidates"][0]["subjectConfirmed"] is False
    assert result["candidates"][0]["sceneConfirmed"] is False


@pytest.mark.parametrize("page", ["<html>Access denied</html>", '<script id="__NEXT_DATA__">{"props":{}}</script>'])
def test_missing_official_data_never_produces_placeholder_success(page):
    with pytest.raises((ValueError, KeyError)):
        parse(page, "https://www.cfmoto.com/motorcycles/missing")


def page(data):
    return '<script id="__NEXT_DATA__">' + json.dumps(data) + '</script>'


@pytest.fixture
def official(monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    home = page({"props": {"pageProps": {"homeData": {"block": [
        {"relModel": {"name": "800MT-ES", "slug": "800mt-es"}},
        {"relModel": {"name": "450MT", "slug": "450mt"}},
    ]}}}})
    vehicle = page({"props": {"pageProps": {"vehicleData": {"name": "800MT-ES", "block": [
        {"title": "仪表", "img": image("dashboard.jpg")},
        {"title": "骑行", "img": image("riding.jpg")},
    ]}}}})
    calls = []
    def fetch(path):
        calls.append(path)
        assert path in {"/", "/motorcycles/800mt-es"}
        return home if path == "/" else vehicle
    monkeypatch.setattr(catalog, "fetch_official_page", fetch)
    return calls


@pytest.mark.parametrize("subject,variant", [("春风 800MT", True), ("CFMOTO 800MT-ES", False)])
def test_official_exact_and_related_version_are_distinguished(official, subject, variant):
    items, warnings = catalog.manufacturer_images(subject, "仪表")
    assert len(items) == 1
    assert items[0]["modelName"] == "春风 800MT-ES"
    assert items[0]["requiresVariantConfirmation"] is variant
    assert items[0]["sceneMatchStatus"] == "unverified"
    assert bool(warnings) is variant
    assert official == ["/", "/motorcycles/800mt-es"]


def test_unmatched_focus_does_not_claim_scene_match(official):
    items, warnings = catalog.manufacturer_images("春风800MT-ES", "涉水")
    assert len(items) == 2
    assert any("不代表目标场景" in warning for warning in warnings)
    assert all(item["sceneMatchStatus"] == "unverified" for item in items)


def test_unknown_or_wrong_brand_does_not_get_official_substitute(official):
    with pytest.raises(catalog.PublicMediaError, match="仅支持"):
        catalog.manufacturer_images("张雪800X")
    assert official == []
    items, _ = catalog.manufacturer_images("春风800MT-X")
    assert items == []
    assert official == ["/"]


def test_import_requires_explicit_version_confirmation_and_records_exact_model(client, official, monkeypatch):
    pid = create(client)
    root = f"/api/v1/projects/{pid}"
    endpoint = root + "/asset-discoveries"
    result = client.post(endpoint, json={"subject": "春风800MT", "source": "manufacturer", "focus": "仪表"})
    assert result.status_code == 202
    run = wait_discovery(client, pid)
    assert run["status"] == "ready"
    assert run["result"]["source"] == "manufacturer"
    item = run["result"]["candidates"][0]
    adopted = f"{endpoint}/{run['id']}/candidates/{item['id']}/import"
    response = client.post(adopted, json={"confirmSubject": True})
    assert response.status_code == 422 and "800MT-ES" in response.text
    assert not client.get(root + "/workspace").json()["assetVersions"]
    content = (Path(__file__).resolve().parents[3] / "apps/web/public/images/motorcycle-studio.jpg").read_bytes()
    monkeypatch.setattr(asset_discovery, "fetch_public_image", lambda _: content)
    response = client.post(adopted, json={"confirmSubject": True, "confirmVariant": True})
    assert response.status_code == 201, response.text
    workspace = client.get(root + "/workspace").json()
    asset = workspace["assetVersions"][0]
    assert asset["subject"] == "春风 800MT-ES"
    assert asset["requestedSubject"] == "春风800MT"
    assert asset["variantConfirmedByUser"] is True
    assert asset["referenceSource"] == "manufacturer"
    assert asset["sourceUrl"].endswith("/motorcycles/800mt-es")
    assert any(f["value"] == "春风 800MT-ES" for f in workspace["facts"])
    assert client.get(asset["previewUrl"]).status_code == 200


@pytest.mark.parametrize("response", [
    httpx.Response(302, headers={"location": "http://127.0.0.1/"}),
    httpx.Response(200, text="blocked", headers={"content-type": "application/json"}),
    httpx.Response(200, content=b"x" * (4 * 1024 * 1024 + 1), headers={"content-type": "text/html"}),
])
def test_official_reader_limits_transport(client, monkeypatch, response):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    original = httpx.Client
    calls = []
    def handle(request):
        calls.append(request)
        assert request.url.host == "www.cfmoto.com"
        assert "authorization" not in request.headers
        return response
    monkeypatch.setattr(catalog.httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    with pytest.raises(catalog.PublicMediaError):
        catalog.fetch_official_page("/")
    assert len(calls) == 1


def test_official_reader_respects_isolation_and_path_constraints(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Must not access network")
    monkeypatch.setattr(catalog.httpx, "Client", forbidden)
    with pytest.raises(catalog.PublicMediaError, match="禁止"):
        catalog.manufacturer_images("春风800MT")
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    with pytest.raises(catalog.PublicMediaError, match="路径无效"):
        catalog.fetch_official_page("/motorcycles/../../admin")


def global_page(model="800MT SPORT"):
    base = "/content/dam/cfmoto/site/global/product/motorcycle/mt----mult-touring/800mt-sport/"
    def component(tag, **attrs):
        return f"<{tag} " + " ".join(f'{key}="{escape(json.dumps(value))}"' for key, value in attrs.items()) + f"></{tag}>"
    return "".join([
        component("headercomponent", product={"title": "450MT", "image": base + "nav.jpg"}),
        component("productcategorycomponent", product={"title": model},
                  variant=[{"title": "Blue", "image": base + "blue.png"}],
                  category={"pointData": [{"img": base + "touring.jpg"}]}),
        component("productgallerycomponent", spicturelist={"imageList": [base + "side.jpg", base + "side.jpg",
                  "https://example.com/ad.jpg", "/etc/designs/icon.png", base + "orbit.glb"]},
                  lpicturelist={"imageList": [base + "riding.jpg"]}),
        component("productrecommendcomponent", product={"title": "800MT-ES", "image": base + "es.jpg"}),
    ])


def test_global_gallery_excludes_recommendations_hotspots_and_non_images():
    result = catalog.global_catalog_from_html(global_page(), "https://www.cfmoto.com/global/test.html", "800MT SPORT")
    assert [item["imageUrl"].split("/")[-1] for item in result["candidates"]] == ["blue.png", "side.jpg", "riding.jpg"]
    assert result["candidates"][1]["context"] == "棚拍 / Studio"
    assert all(not item["subjectConfirmed"] and not item["sceneConfirmed"] for item in result["candidates"])


@pytest.mark.parametrize("html", ["<html>unavailable</html>", global_page("800MT-ES"),
                                   '<productcategorycomponent product="invalid"></productcategorycomponent>'])
def test_global_missing_or_wrong_model_is_not_a_match(html):
    with pytest.raises(ValueError):
        catalog.global_catalog_from_html(html, "https://www.cfmoto.com/global/test.html", "800MT SPORT")


@pytest.mark.parametrize("subject", ["春风 800MT SPORT", "CFMOTO 800MT-SPORT"])
def test_global_explicit_version_uses_its_own_page(client, monkeypatch, subject):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    calls = []
    def fetch(path):
        calls.append(path)
        return global_page()
    monkeypatch.setattr(catalog, "fetch_official_page", fetch)
    items, warnings = catalog.manufacturer_images(subject, "棚拍")
    assert calls == ["/global/motorcycles/mult-touring/800mt_sport.html"]
    assert len(items) == 1 and items[0]["modelName"] == "春风 800MT SPORT"
    assert items[0]["sceneMatchStatus"] == "unverified"
    assert "不是完整 360" in warnings[0]


def test_global_search_endpoint_does_not_import_or_replace_assets(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    monkeypatch.setattr(catalog, "fetch_official_page", lambda _: global_page("800MT EXPLORE"))
    pid = create(client)
    root = f"/api/v1/projects/{pid}"
    response = client.post(root + "/asset-discoveries", json={"subject": "春风 800MT EXPLORE", "source": "manufacturer", "focus": "棚拍"})
    assert response.status_code == 202
    run = wait_discovery(client, pid)
    assert run["status"] == "ready"
    assert run["result"]["candidates"][0]["modelName"] == "春风 800MT EXPLORE"
    assert client.get(root + "/workspace").json()["assetVersions"] == []


def zxmoto_page(model="820RR"):
    return f'''<html><title>{model}_产品世界_ZXMOTO张雪机车</title>
    <div class="header"><img src="/uploadfile/202603/other.png"></div>
    <div class="cp_xx"><div class="cp_ys">
      <div class="swiper-st"><div class="swiper-slide"><img src="/uploadfile/202603/front.png"></div>
        <div class="swiper-slide"><img src="/uploadfile/202603/rear.png"></div></div>
      <div class="swiper-st"><div class="swiper-slide"><img src="/uploadfile/202603/othercolor.png"></div></div>
    </div><div class="ys_xz"><img src="/uploadfile/202603/swatch.png"></div>
    <div class="m_c">{model}</div></div>
    <div class="cp_tc"><div class="t_p"><img src="/uploadfile/202603/detail.jpg">
      <img src="https://example.com/uploadfile/202603/ad.jpg">
      <img src="/static/default/images/icon.png"><img src="/uploadfile/202603/orbit.glb">
      <img src="/uploadfile/202603/detail.jpg"></div></div>
    <div class="cp_tj"><div class="t_p"><img src="/uploadfile/202603/wrongbike.png"></div></div></html>'''


def test_zxmoto_preserves_color_groups_and_excludes_other_models():
    result = catalog.zxmoto_catalog_from_html(zxmoto_page(), "https://www.zxmoto.com/index.php?c=show&id=58", "820RR")
    assert [item["imageUrl"].split("/")[-1] for item in result["candidates"]] == ["front.png", "rear.png", "othercolor.png", "detail.jpg"]
    assert "配色组 1 / 视角 2" in result["candidates"][1]["context"]
    assert "配色组 2 / 视角 1" in result["candidates"][2]["context"]
    assert all(not item["subjectConfirmed"] and not item["sceneConfirmed"] for item in result["candidates"])


@pytest.mark.parametrize("html", ["<html>blocked</html>", zxmoto_page("500RR"),
    zxmoto_page().replace('<div class="m_c">820RR</div>', '<div class="m_c">500RR</div>')])
def test_zxmoto_requires_matching_title_and_product_identity(html):
    with pytest.raises(ValueError):
        catalog.zxmoto_catalog_from_html(html, "https://www.zxmoto.com/index.php?c=show&id=58", "820RR")


@pytest.mark.parametrize("subject", ["张雪 820RR", "张雪机车820RR", "ZX MOTO 820-RR", "张雪机车 ZXMOTO 820RR", "ZXMOTO 张雪 820RR"])
def test_zxmoto_model_dispatch_and_focus(client, monkeypatch, subject):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    calls = []
    def fetch(path):
        calls.append(path)
        return zxmoto_page()
    monkeypatch.setattr(catalog, "fetch_zxmoto_page", fetch)
    items, warnings = catalog.manufacturer_images(subject, "配色组 1")
    assert calls == ["/index.php?c=show&id=58"]
    assert len(items) == 2
    assert items[0]["modelName"] == "张雪 820RR"
    assert not items[0]["requiresVariantConfirmation"]
    assert items[0]["sceneMatchStatus"] == "unverified"
    assert warnings


def test_zxmoto_reader_enforces_fixed_path_isolation_and_limits(client, monkeypatch):
    original = httpx.Client
    calls = []
    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://www.zxmoto.com/index.php?c=show&id=58"
        assert "authorization" not in request.headers
        return httpx.Response(302, headers={"location": "http://127.0.0.1/"})
    monkeypatch.setattr(catalog.httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    with pytest.raises(catalog.PublicMediaError, match="禁止"):
        catalog.fetch_zxmoto_page("/index.php?c=show&id=58")
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    with pytest.raises(catalog.PublicMediaError, match="路径无效"):
        catalog.fetch_zxmoto_page("/index.php?c=show&id=56")
    assert not calls
    with pytest.raises(catalog.PublicMediaError):
        catalog.fetch_zxmoto_page("/index.php?c=show&id=58")
    assert len(calls) == 1


def test_zxmoto_search_and_import_stays_in_selected_brand(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_external_search", True)
    monkeypatch.setattr(catalog, "fetch_zxmoto_page", lambda _: zxmoto_page())
    pid = create(client, "张雪机车任选一辆，保留完整环绕及皮衣骑手结尾。本次选择820RR。")
    root = f"/api/v1/projects/{pid}"
    response = client.post(root + "/asset-discoveries", json={"subject": "张雪820RR", "source": "manufacturer", "focus": "配色组 1"})
    assert response.status_code == 202
    run = wait_discovery(client, pid)
    assert run["status"] == "ready"
    assert len(run["result"]["candidates"]) == 2
    assert client.get(root + "/workspace").json()["assetVersions"] == []
    content = (Path(__file__).resolve().parents[3] / "apps/web/public/images/motorcycle-studio.jpg").read_bytes()
    monkeypatch.setattr(asset_discovery, "fetch_public_image", lambda _: content)
    item = run["result"]["candidates"][0]
    endpoint = f"{root}/asset-discoveries/{run['id']}/candidates/{item['id']}/import"
    assert client.post(endpoint, json={"confirmSubject": True}).status_code == 201
    asset = client.get(root + "/workspace").json()["assetVersions"][0]
    assert asset["subject"] == "张雪 820RR"
    assert asset["referenceContext"] == "整车 / 配色组 1 / 视角 1"
    assert asset["sourceUrl"] == "https://www.zxmoto.com/index.php?c=show&id=58"
