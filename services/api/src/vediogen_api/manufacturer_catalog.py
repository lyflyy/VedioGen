import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

from .config import get_settings
from .public_media import PublicMediaError, public_url


GLOBAL_MODELS = {
    "800mtsport": ("800MT SPORT", "/global/motorcycles/mult-touring/800mt_sport.html"),
    "800mtexplore": ("800MT EXPLORE", "/global/motorcycles/mult-touring/800mt_explore.html"),
}
ZXMOTO_MODELS = {"820rr": ("820RR", "/index.php?c=show&id=58")}


class ZxmotoProductParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.divs = []
        self.in_title = False
        self.title = []
        self.names = []
        self.images = []
        self.group = 0
        self.angle = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "div":
            classes = set(attrs.get("class", "").split())
            self.divs.append(classes)
            if "swiper-st" in classes and any("cp_ys" in value for value in self.divs):
                self.group += 1
                self.angle = 0
        if tag != "img":
            return
        classes = set().union(*self.divs) if self.divs else set()
        # Product galleries only: never navigation, color swatches or recommendations.
        if {"cp_xx", "cp_ys", "swiper-st", "swiper-slide"} <= classes:
            self.angle += 1
            self.images.append((attrs.get("src"), f"整车 / 配色组 {self.group} / 视角 {self.angle}"))
        elif {"cp_tc", "t_p"} <= classes:
            self.images.append((attrs.get("src"), "细节 / 官网展示"))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "div" and self.divs:
            self.divs.pop()

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.divs and "m_c" in self.divs[-1] and any("cp_xx" in value for value in self.divs):
            if data.strip():
                self.names.append(data.strip())


def zxmoto_catalog_from_html(page, source, expected_model):
    parser = ZxmotoProductParser()
    parser.feed(page)
    if "".join(parser.title).split("_", 1)[0].strip() != expected_model or parser.names != [expected_model]:
        raise ValueError("ZXMOTO product identity is missing or inconsistent")
    candidates, seen = [], set()
    for raw, context in parser.images:
        if not isinstance(raw, str):
            continue
        url = urljoin(source, raw)
        parts = urlsplit(url)
        if (not public_url(url) or parts.hostname != "www.zxmoto.com"
                or not re.fullmatch(r"/uploadfile/\d{6}/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg)", parts.path)
                or parts.query or parts.fragment or url in seen):
            continue
        seen.add(url)
        candidates.append({"index": len(candidates) + 1, "model": expected_model, "context": context,
            "imageUrl": url, "sourceUrl": source, "subjectConfirmed": False, "sceneConfirmed": False})
    return {"source": source, "model": expected_model, "candidates": candidates,
            "subjectConfirmed": False, "retrievedAt": datetime.now(timezone.utc).isoformat()}


def fetch_zxmoto_page(path):
    if path not in {value[1] for value in ZXMOTO_MODELS.values()}:
        raise PublicMediaError("张雪官网车型路径无效")
    return _fetch_official_html("https://www.zxmoto.com" + path)


def zxmoto_manufacturer_images(code, focus):
    if code not in ZXMOTO_MODELS:
        raise PublicMediaError("张雪官网当前仅支持 820RR；其他车型请使用网络图片检索")
    model, path = ZXMOTO_MODELS[code]
    source = "https://www.zxmoto.com" + path
    try:
        catalog = zxmoto_catalog_from_html(fetch_zxmoto_page(path), source, model)
    except (ValueError, KeyError, TypeError) as error:
        raise PublicMediaError("张雪官网车型数据无法解析；未生成占位候选") from error
    candidates = [{"id": str(uuid4()), "title": f"张雪 {model} · {item['context']} · {item['index']}",
        "imageUrl": item["imageUrl"], "thumbnailUrl": item["imageUrl"], "sourceUrl": source,
        "assetId": None, "sourceType": "manufacturer", "modelName": f"张雪 {model}",
        "requiresVariantConfirmation": False, "referenceIndex": item["index"], "context": item["context"],
        "matchStatus": "official-model-name", "sceneMatchStatus": "unverified",
        "retrievedAt": catalog["retrievedAt"]} for item in catalog["candidates"]]
    warnings = ["整车图按官网配色组分开；请保持同组外观一致。多角度图片不等于三维模型或连续 360 度视频"]
    if focus and candidates:
        matched = [item for item in candidates if focus.casefold() in item["context"].casefold()]
        if matched:
            candidates = matched
        else:
            warnings.append("官网图片说明未匹配镜头关键词，展示车型参考；不代表目标场景或动作已具备")
    return candidates[:36], warnings


class GlobalProductParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sections = []

    def handle_starttag(self, tag, attrs):
        # Navigation, recommendations and technical hotspots can contain other models.
        fields = {"productcategorycomponent": {"product", "variant"},
                  "productgallerycomponent": {"spicturelist", "lpicturelist"}}.get(tag, set())
        for key, value in attrs:
            if key in fields:
                self.sections.append((key, json.loads(value)))


def global_catalog_from_html(page, source, expected_model):
    parser = GlobalProductParser()
    parser.feed(page)
    names = [value.get("title") for key, value in parser.sections if key == "product" and isinstance(value, dict)]
    if names != [expected_model]:
        raise ValueError("Global product identity is missing or inconsistent")
    candidates, seen = [], set()

    def add(raw, context):
        if not isinstance(raw, str):
            return
        url = urljoin(source, raw)
        parts = urlsplit(url)
        if (not public_url(url) or parts.hostname != "www.cfmoto.com"
                or not parts.path.startswith("/content/dam/cfmoto/site/global/product/motorcycle/")
                or not parts.path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) or url in seen):
            return
        seen.add(url)
        candidates.append({"index": len(candidates) + 1, "model": expected_model, "context": context,
                           "imageUrl": url, "sourceUrl": source, "subjectConfirmed": False, "sceneConfirmed": False})

    for key, value in parser.sections:
        if key == "variant" and isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    add(item.get("image"), "配色 / " + str(item.get("title") or "未标注"))
        elif key in {"spicturelist", "lpicturelist"} and isinstance(value, dict):
            images = value.get("imageList", [])
            if not isinstance(images, list):
                raise ValueError("Invalid official gallery")
            for image in images:
                add(image, "棚拍 / Studio" if key == "spicturelist" else "实景 / Lifestyle")
    return {"source": source, "model": expected_model, "candidates": candidates,
            "subjectConfirmed": False, "retrievedAt": datetime.now(timezone.utc).isoformat()}


def global_manufacturer_images(model, path, focus):
    source = "https://www.cfmoto.com" + path
    catalog = global_catalog_from_html(fetch_official_page(path), source, model)
    candidates = [{"id": str(uuid4()), "title": f"CFMOTO {model} · {item['context']} · {item['index']}",
                   "imageUrl": item["imageUrl"], "thumbnailUrl": item["imageUrl"], "sourceUrl": source,
                   "assetId": None, "sourceType": "manufacturer", "modelName": f"春风 {model}",
                   "requiresVariantConfirmation": False, "referenceIndex": item["index"], "context": item["context"],
                   "matchStatus": "official-model-name", "sceneMatchStatus": "unverified",
                   "retrievedAt": catalog["retrievedAt"]} for item in catalog["candidates"]]
    warnings = ["国际站同页可能包含不同年份或配置；采用前请核对外观、配色与目标市场。棚拍照片不是完整 360 度或三维模型"]
    if focus and candidates:
        matched = [item for item in candidates if focus.casefold() in item["context"].casefold()]
        if matched:
            candidates = matched
        else:
            warnings.append("官网画廊未匹配镜头关键词，展示车型参考；不代表目标场景或动作已具备")
    return candidates[:36], warnings


class NextDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.collecting = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.collecting = dict(attrs).get("id") == "__NEXT_DATA__"

    def handle_endtag(self, tag):
        if tag == "script":
            self.collecting = False

    def handle_data(self, data):
        if self.collecting:
            self.parts.append(data)


def next_data(page):
    parser = NextDataParser()
    parser.feed(page)
    return json.loads("".join(parser.parts))


def catalog_from_html(page, source):
    vehicle = next_data(page)["props"]["pageProps"]["vehicleData"]
    model = vehicle["name"]
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Missing official model name")
    candidates, seen = [], set()

    def collect(value, context):
        if isinstance(value, list):
            for item in value:
                collect(item, context)
        elif isinstance(value, dict):
            if value.get("__component") in {"vehicle.vehicle-recommend", "vehicle.find-store", "common.disclaimer-text"}:
                return
            context = value.get("title") if isinstance(value.get("title"), str) and value["title"] else context
            url = value.get("url")
            if str(value.get("mime", "")).startswith("image/") and isinstance(url, str):
                if public_url(url) and urlsplit(url).hostname == "cfimages.cfmoto.com" and url not in seen:
                    seen.add(url)
                    candidates.append({"index": len(candidates) + 1, "model": model,
                                       "context": context, "fileName": value.get("name"),
                                       "imageUrl": url, "sourceUrl": source,
                                       "width": value.get("width"), "height": value.get("height"),
                                       "subjectConfirmed": False, "sceneConfirmed": False})
                return
            for key, item in value.items():
                if key not in {"compatibleProducts", "formats", "series"}:
                    collect(item, context)

    collect(vehicle, model)
    return {"source": source, "model": model, "candidates": candidates,
            "subjectConfirmed": False, "retrievedAt": datetime.now(timezone.utc).isoformat()}


def fetch_official_page(path):
    if not get_settings().allow_external_search:
        raise PublicMediaError("当前环境禁止外部素材检索")
    if (path != "/" and not re.fullmatch(r"/motorcycles/[a-zA-Z0-9-]{1,50}", path)
            and path not in {value[1] for value in GLOBAL_MODELS.values()}):
        raise PublicMediaError("官网车型路径无效")
    return _fetch_official_html("https://www.cfmoto.com" + path)


def _fetch_official_html(source):
    if not get_settings().allow_external_search:
        raise PublicMediaError("当前环境禁止外部素材检索")
    try:
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", source) as response:
                response.raise_for_status()
                if not response.headers.get("content-type", "").lower().startswith("text/html"):
                    raise PublicMediaError("官网返回了非网页内容")
                content = bytearray()
                for chunk in response.iter_bytes(65536):
                    content.extend(chunk)
                    if len(content) > 4 * 1024 * 1024:
                        raise PublicMediaError("官网内容超过读取上限")
                return content.decode("utf-8")
    except (httpx.HTTPError, UnicodeError) as error:
        raise PublicMediaError("官网暂时无法访问；未使用缓存素材替代本次结果") from error


def manufacturer_images(subject: str, focus: str = ""):
    if not get_settings().allow_external_search:
        raise PublicMediaError("当前环境禁止外部素材检索")
    compact = re.sub(r"\s+", "", subject).lower()
    if compact.startswith(("张雪", "zxmoto")):
        code = re.sub(r"^(?:(?:张雪(?:机车)?|zxmoto)[/·()（）-]*)+", "", compact).replace("-", "")
        return zxmoto_manufacturer_images(code, focus)
    if not any(brand in compact for brand in ("春风", "cfmoto", "cf-moto")):
        raise PublicMediaError("当前官网适配仅支持春风 CFMOTO 与张雪 820RR，其他品牌请使用网络图片检索")
    explicit_model = re.sub(r"^(?:春风|cf-?moto)", "", compact).replace("-", "")
    if explicit_model in GLOBAL_MODELS:
        try:
            return global_manufacturer_images(*GLOBAL_MODELS[explicit_model], focus)
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise PublicMediaError("国际站车型数据无法解析；未生成占位候选") from error
    match = re.search(r"\d+[a-z0-9-]*", compact)
    if not match:
        raise PublicMediaError("请填写具体车型名称后查询官网素材")
    requested = match[0]
    try:
        homepage = next_data(fetch_official_page("/"))
        models = {}

        def collect_models(value):
            if isinstance(value, list):
                for item in value:
                    collect_models(item)
            elif isinstance(value, dict):
                model = value.get("relModel")
                if isinstance(model, dict) and isinstance(model.get("name"), str) and isinstance(model.get("slug"), str):
                    code = re.sub(r"\s+", "", model["name"]).lower()
                    if code == requested or code.startswith(requested + "-"):
                        models[model["slug"]] = model["name"]
                for item in value.values():
                    collect_models(item)

        collect_models(homepage["props"]["pageProps"]["homeData"])
        exact = {slug: name for slug, name in models.items() if re.sub(r"\s+", "", name).lower() == requested}
        selected = exact or models
        candidates, warnings = [], []
        for slug, model in list(selected.items())[:3]:
            path = "/motorcycles/" + slug
            source = "https://www.cfmoto.com" + path
            catalog = catalog_from_html(fetch_official_page(path), source)
            if catalog["model"] != model:
                raise PublicMediaError("官网目录与车型页面名称不一致，未自动采用")
            variant = re.sub(r"\s+", "", model).lower() != requested
            for item in catalog["candidates"]:
                if not isinstance(item["width"], int) or not isinstance(item["height"], int) or min(item["width"], item["height"]) < 500:
                    continue
                candidates.append({"id": str(uuid4()), "title": f"CFMOTO {model} · {item['context']} · {item['index']}",
                    "imageUrl": item["imageUrl"], "thumbnailUrl": item["imageUrl"], "sourceUrl": source,
                    "assetId": None, "sourceType": "manufacturer", "modelName": f"春风 {model}",
                    "requiresVariantConfirmation": variant, "referenceIndex": item["index"], "context": item["context"],
                    "matchStatus": "variant-needs-confirmation" if variant else "official-model-name",
                    "sceneMatchStatus": "unverified", "retrievedAt": catalog["retrievedAt"]})
        if any(c["requiresVariantConfirmation"] for c in candidates):
            warnings.append("官网未返回同名精确车型；以下为相关版本候选，采用前需明确确认版本")
        if focus and candidates:
            matched = [c for c in candidates if focus.casefold() in (c["context"] + " " + c["title"]).casefold()]
            if matched:
                candidates = matched
            else:
                warnings.append("官网图片说明未匹配镜头关键词，展示车型参考；不代表目标场景或动作已具备")
        return candidates[:36], warnings
    except (ValueError, KeyError, TypeError, RecursionError) as error:
        raise PublicMediaError("官网车型数据无法解析；未生成占位候选") from error
