import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from threading import RLock
from typing import Literal
from uuid import uuid4

from ddgs import DDGS
from ddgs.engines.bing_images import BingImages
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, get_session
from .fixtures import timestamp
from .gateway import ModelGatewayError, extract_asset_brief
from .media import MediaGenerationError, probe_media
from .manufacturer_catalog import manufacturer_images
from .models import AssetDiscoveryRow, ProjectRow
from .public_media import PublicMediaError, fetch_public_image, public_url
from .schemas import ApiModel


router = APIRouter()
lock = RLock()
executor: ThreadPoolExecutor | None = None


class DiscoveryInput(ApiModel):
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    focus: str = Field(default="", max_length=160)
    source: Literal["web", "manufacturer"] = "web"


class ImportCandidateInput(ApiModel):
    confirm_subject: bool = False
    confirm_variant: bool = False


def serialize(row) -> dict:
    return {"id": row.id, "projectId": row.project_id, "status": row.status,
            "result": row.result, "errorMessage": row.error_message}


def compact(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value).casefold()


def matches_subject(subject: str, title: str) -> bool:
    # Brand aliases are explicit; a matching model number alone must not merge manufacturers.
    aliases = {"春风": ("春风", "cfmoto", "cf-moto"), "张雪": ("张雪", "zxmoto", "zx moto")}
    for brand, names in aliases.items():
        if any(compact(name) in compact(subject) for name in names):
            remaining = compact(subject)
            for name in names:
                remaining = remaining.replace(compact(name), "")
            code = re.search(r"\d+[a-z0-9]*", remaining)
            if code:
                normalized_title = re.sub(r"(?<=\d)\s+(?=[a-z])", "", title.casefold())
                normalized_title = re.sub(r"(?<=[a-z0-9])[-_](?=[a-z0-9])", "", normalized_title)
                return any(compact(name) in compact(title) for name in names) and bool(re.search(re.escape(code[0]) + r"(?![a-z0-9])", normalized_title))
    return compact(subject) in compact(title)


def bing_http_images(query: str) -> list[dict]:
    if not get_settings().allow_external_search:
        raise PublicMediaError("当前环境禁止外部素材检索")
    # Reuse DDGS's parser when its impersonating TLS transport fails on this host.
    with httpx.Client(timeout=12, trust_env=False, follow_redirects=False) as client:
        with client.stream("GET", "https://cn.bing.com/images/async",
                           params={"q": query, "async": "1", "first": "1", "count": "35"}) as response:
            response.raise_for_status()
            if not response.headers.get("content-type", "").lower().startswith("text/html"):
                raise PublicMediaError("备用搜索返回了非网页内容")
            content = bytearray()
            for chunk in response.iter_bytes(65536):
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise PublicMediaError("备用搜索响应超过大小限制")
    return [asdict(item) for item in BingImages().extract_results(content.decode("utf-8", errors="replace"))]


def search_images(subject: str, focus: str = "") -> tuple[list[dict], list[str]]:
    if not get_settings().allow_external_search:
        raise PublicMediaError("当前环境禁止外部素材检索")
    queries = [subject]
    if "春风" in subject:
        queries.append(subject.replace("春风", "CFMOTO") + " motorcycle")
    if "张雪" in subject:
        queries.append(subject.replace("张雪", "ZXMOTO") + " motorcycle")
    if focus:
        queries = [f"{query} {focus}" for query in queries]
    candidates, seen, warnings = [], set(), []
    succeeded = False
    for query in queries[:2]:
        try:
            values = DDGS(timeout=12).images(query, max_results=8)
            succeeded = True
        except Exception:
            try:
                values = bing_http_images(query)
                succeeded = True
                warnings.append("默认搜索连接失败，本次使用备用连接；结果仍需确认")
            except Exception:
                warnings.append("部分搜索请求失败或被限流，可稍后重试")
                continue
        for item in values:
            title, image, source = item.get("title", ""), item.get("image", ""), item.get("url", "")
            if not all(isinstance(value, str) for value in (title, image, source)):
                continue
            if image in seen or not matches_subject(subject, title) or not public_url(image) or not public_url(source):
                continue
            seen.add(image)
            candidates.append({"id": str(uuid4()), "title": title[:250], "imageUrl": image,
                "sourceUrl": source, "thumbnailUrl": item.get("thumbnail") if public_url(item.get("thumbnail", "")) else image,
                "matchStatus": "name-match-only", "sceneMatchStatus": "unverified", "assetId": None})
    if not succeeded:
        raise PublicMediaError("素材搜索暂不可用，请稍后重试；没有使用替代图片")
    return candidates[:8], list(dict.fromkeys(warnings))


def start_worker():
    global executor
    with SessionLocal() as session:
        for row in session.scalars(select(AssetDiscoveryRow).where(AssetDiscoveryRow.status.in_(("queued", "running")))):
            row.status = "interrupted"
            row.error_message = "素材准备曾中断，可重新发起"
        session.commit()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="asset-discovery")


def stop_worker():
    global executor
    if executor:
        executor.shutdown(wait=True, cancel_futures=True)
        executor = None


def execute(run_id):
    try:
        with SessionLocal() as session:
            row = session.get(AssetDiscoveryRow, run_id)
            row.status = "running"
            session.commit()
            project = session.get(ProjectRow, row.project_id)
            brief = ({"subject": row.request_data["subject"], "requiredShots": [], "clarification": ""}
                     if row.request_data.get("subject") else extract_asset_brief(session, project, row.request_data["messages"]))
            subject = brief["subject"].strip()
            source_text = " ".join(item.get("text", "") for item in row.request_data["messages"])
            if not row.request_data.get("subject") and subject and compact(subject) not in compact(source_text):
                raise PublicMediaError("模型提取的名称未出现在用户描述中，请确认要搜索的主体")
            focus = row.request_data.get("focus", "")
            row.result = {**brief, "subject": subject, "searchFocus": focus, "source": row.request_data.get("source", "web"), "candidates": [], "warnings": [], "origin": "user-input" if row.request_data.get("subject") else "model-extraction"}
            if not subject or brief.get("clarification"):
                row.status = "needs_clarification"
                session.commit()
                return
            session.commit()
        if row.request_data.get("source", "web") == "manufacturer":
            candidates, warnings = manufacturer_images(subject, focus)
        else:
            candidates, warnings = search_images(subject, focus) if focus else search_images(subject)
        if focus and candidates:
            warnings.append("已按镜头关键词检索；场景、动作和车型版本仍需逐图确认")
        with SessionLocal() as session:
            row = session.get(AssetDiscoveryRow, run_id)
            row.result = {**row.result, "candidates": candidates, "warnings": warnings}
            row.status = "ready" if candidates else "empty"
            session.commit()
    except Exception as error:
        with SessionLocal() as session:
            row = session.get(AssetDiscoveryRow, run_id)
            row.status = "failed"
            row.error_message = str(error) if isinstance(error, (PublicMediaError, ModelGatewayError)) else "素材准备失败，请稍后重试"
            session.commit()


@router.post("/projects/{project_id}/asset-discoveries", status_code=202)
def create_discovery(project_id: str, payload: DiscoveryInput, session: Session = Depends(get_session)):
    with lock:
        project = session.get(ProjectRow, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        active = session.scalar(select(AssetDiscoveryRow).where(AssetDiscoveryRow.status.in_(("queued", "running"))))
        if active:
            if (active.project_id == project_id
                    and active.request_data.get("subject") == (payload.subject.strip() if payload.subject else None)
                    and active.request_data.get("focus", "") == payload.focus.strip()
                    and active.request_data.get("source", "web") == payload.source):
                return serialize(active)
            raise HTTPException(409, "另一个素材准备任务正在执行，请等待完成后再更换检索条件")
        if not executor:
            raise HTTPException(503, "素材准备服务未启动")
        row = AssetDiscoveryRow(id=str(uuid4()), project_id=project_id, status="queued", result={"searchFocus": payload.focus.strip(), "source": payload.source},
            request_data={"subject": payload.subject.strip() if payload.subject else None,
                          "source": payload.source,
                          "focus": payload.focus.strip(),
                          "messages": deepcopy([m for m in project.messages if m.get("role") == "user"])})
        session.add(row)
        session.commit()
        result = serialize(row)
        executor.submit(execute, row.id)
        return result


@router.get("/projects/{project_id}/asset-discoveries/latest")
def latest_discovery(project_id: str, session: Session = Depends(get_session)):
    if not session.get(ProjectRow, project_id):
        raise HTTPException(404, "Project not found")
    row = session.scalar(select(AssetDiscoveryRow).where(AssetDiscoveryRow.project_id == project_id).order_by(AssetDiscoveryRow.created_at.desc()))
    return {"run": serialize(row) if row else None}


@router.post("/projects/{project_id}/asset-discoveries/{run_id}/candidates/{candidate_id}/import", status_code=201)
def import_candidate(project_id: str, run_id: str, candidate_id: str, payload: ImportCandidateInput, session: Session = Depends(get_session)):
    if not payload.confirm_subject:
        raise HTTPException(422, "请确认图片中的主体与所需车型及版本一致")
    with lock:
        row = session.get(AssetDiscoveryRow, run_id)
        if not row or row.project_id != project_id:
            raise HTTPException(404, "素材准备任务不存在")
        candidate = next((item for item in row.result.get("candidates", []) if item["id"] == candidate_id), None)
        if not candidate:
            raise HTTPException(404, "候选素材不存在")
        if candidate.get("requiresVariantConfirmation") and not payload.confirm_variant:
            raise HTTPException(422, f"此素材为 {candidate['modelName']}，请明确确认采用该车型版本")
        project = session.get(ProjectRow, project_id)
        if [m.get("text") for m in project.messages if m.get("role") == "user"] != [m.get("text") for m in row.request_data["messages"]]:
            raise HTTPException(409, "项目描述已改变，请重新准备素材后确认")
        existing = next((asset for asset in project.asset_versions if asset["id"] == candidate.get("assetId")), None)
        if existing:
            return {"assetId": existing["id"], "status": "ready"}
        if not get_settings().allow_external_search:
            raise HTTPException(409, "当前环境禁止外部素材下载")
        target = None
        try:
            content = fetch_public_image(candidate["imageUrl"])
            mime, suffix = ("image/jpeg", ".jpg") if content.startswith(b"\xff\xd8\xff") else ("image/png", ".png") if content.startswith(b"\x89PNG\r\n\x1a\n") else ("", "")
            if not mime:
                raise PublicMediaError("当前只接收 JPEG/PNG 候选，请选择其他图片")
            asset_id = str(uuid4())
            target = get_settings().data_dir / "assets" / project_id / f"{asset_id}{suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            info = probe_media(target)
            if not info["width"] or not info["height"]:
                raise PublicMediaError("候选图片无法解码")
            confirmed_subject = candidate.get("modelName") or row.result["subject"]
            asset = {"id": asset_id, "assetId": str(uuid4()), "version": 1, "kind": "image", "sourceType": "web-reference",
                "fileName": f"{confirmed_subject}-{candidate['referenceIndex']}{suffix}" if candidate.get("referenceIndex") else f"{confirmed_subject}{suffix}", "mimeType": mime, "sizeBytes": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(), "uri": str(target.resolve()),
                "status": "ready", "createdAt": timestamp(), "sourceUrl": candidate["sourceUrl"],
                "sourceImageUrl": candidate["imageUrl"], "subject": confirmed_subject, "subjectConfirmedByUser": True}
            asset["searchFocus"] = row.result.get("searchFocus", "")
            if candidate.get("sourceType") == "manufacturer":
                asset.update(referenceSource="manufacturer", requestedSubject=row.result["subject"],
                             modelName=confirmed_subject, variantConfirmedByUser=payload.confirm_variant,
                             referenceContext=candidate.get("context", ""))
            session.refresh(project)
            project.asset_versions = [*project.asset_versions, asset]
            row.result = {**row.result, "candidates": [{**item, "assetId": asset_id} if item["id"] == candidate_id else item for item in row.result["candidates"]]}
            project.facts = [item for item in project.facts if item.get("key") != "subject.vehicle.name"] + [{
                "id": str(uuid4()), "key": "subject.vehicle.name", "value": confirmed_subject,
                "sourceType": "user-confirmation", "sourceId": asset_id, "status": "confirmed", "confidence": 1}]
            session.commit()
            return {"assetId": asset_id, "status": "ready"}
        except (PublicMediaError, MediaGenerationError) as error:
            if target:
                target.unlink(missing_ok=True)
            raise HTTPException(422, str(error)) from error
