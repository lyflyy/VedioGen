"""Persistent script preparation using the internal MVP's single-process worker."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, get_session
from .fixtures import timestamp
from .gateway import generate_storyboard, extract_asset_brief, match_storyboard_assets, ModelGatewayError
from .generation import ACTIVE, generation_lock, readiness, build_plan
from .manufacturer_catalog import manufacturer_images
from .media import probe_media, MediaGenerationError
from .models import DocumentRow, ProjectRow, GenerationRunRow
from .public_media import fetch_public_image, PublicMediaError
from .serializers import document
from .video_settings import read_settings

router = APIRouter()
lock = RLock()
executor = None


def serialize(row):
    return {"id": row.id, "projectId": row.project_id, "status": row.status, **row.data}


def latest(session, project_id):
    return session.scalar(select(DocumentRow).where(DocumentRow.project_id == project_id,
        DocumentRow.kind == "storyboard-run").order_by(DocumentRow.created_at.desc()))


def enqueue(session, project):
    with lock:
        previous = latest(session, project.id)
        if previous and previous.status in ("queued", "running"):
            return serialize(previous)
        brief = session.get(DocumentRow, project.current_brief_version_id) if project.current_brief_version_id else None
        if not brief or brief.status != "approved":
            raise HTTPException(409, "请先确认创意方向")
        if not executor:
            raise HTTPException(503, "脚本服务未启动")
        row = DocumentRow(id=str(uuid4()), project_id=project.id, kind="storyboard-run", version=1,
            status="queued", data={"phase": "queued", "createdAt": timestamp(), "events": [],
            "briefId": brief.id, "messages": deepcopy(project.messages),
            "storyboardVersionId": None, "errorMessage": None, "warnings": []})
        session.add(row)
        session.commit()
        executor.submit(execute, row.id)
        return serialize(row)


def update(run_id, phase=None, **fields):
    with SessionLocal() as session:
        row = session.get(DocumentRow, run_id)
        events = row.data.get("events", [])
        if phase:
            events = [*events, {"phase": phase, "at": timestamp()}]
        row.data = {**row.data, **fields, "phase": phase or row.data["phase"], "events": events}
        row.status = fields.get("status", "running")
        session.commit()


def prepare_images(session, project):
    if any(a.get("kind") == "image" and a.get("status") == "ready" and Path(a.get("uri", "")).is_file() for a in project.asset_versions):
        return []
    if not get_settings().allow_external_search:
        return ["当前环境未启用素材检索，保留待准备镜头"]
    brief = extract_asset_brief(session, project, project.messages)
    session.commit()
    if not brief["subject"] or brief.get("clarification"):
        return [brief.get("clarification") or "主体尚未明确，未自动采用其他车型"]
    candidates, warnings = manufacturer_images(brief["subject"])
    exact = [c for c in candidates if not c.get("requiresVariantConfirmation")]
    if not exact:
        return [*warnings, "未找到精确车型的官网图片，请在资料页确认候选版本"]
    # Keep the first official gallery group together rather than mixing colorways.
    group = exact[0].get("context", "").split(" / 视角", 1)[0]
    chosen = [c for c in exact if c.get("context", "").startswith(group)][:3]
    warnings = [*warnings, f"自动采用候选：{group}。配色和视角尚未由用户确认"]
    for candidate in chosen:
        content = fetch_public_image(candidate["imageUrl"])
        suffix, mime = (".png", "image/png") if content.startswith(b"\x89PNG\r\n\x1a\n") else (".jpg", "image/jpeg")
        asset_id = str(uuid4())
        target = get_settings().data_dir / "assets" / project.id / (asset_id + suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(content)
            info = probe_media(target)
            if not info.get("width") or not info.get("height"):
                raise PublicMediaError("官网素材无法解码")
            asset = {"id": asset_id, "assetId": str(uuid4()), "version": 1, "kind": "image",
                "status": "ready", "sourceType": "web-reference", "referenceSource": "manufacturer",
                "preparedBy": "platform", "subjectConfirmedByUser": False,
                "subject": candidate["modelName"], "referenceContext": candidate.get("context", ""),
                "sourceUrl": candidate["sourceUrl"], "sourceImageUrl": candidate["imageUrl"],
                "fileName": f"{candidate['modelName']}-{candidate['referenceIndex']}{suffix}",
                "uri": str(target.resolve()), "mimeType": mime, "sizeBytes": len(content),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(), "createdAt": timestamp()}
            session.refresh(project)
            project.asset_versions = [*project.asset_versions, asset]
            project.row_version += 1
            session.commit()
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return warnings


def assign_assets(session, project, data):
    shots = deepcopy(data["shots"])
    assets = {a["id"]: a for a in project.asset_versions if a.get("status") == "ready" and Path(a.get("uri", "")).is_file()}
    images = [a for a in assets.values() if a.get("kind") == "image"]
    config = read_settings(session)
    video_enabled = config["enabled"] and (get_settings().allow_local_models if config["backend"] == "comfyui" else get_settings().allow_external_models)
    changes = []
    for index, shot in enumerate(shots, 1):
        source = assets.get(shot.get("sourceAssetId"))
        strategy = shot.get("sourceStrategy")
        if shot.get("sourceAssetId") and not source:
            shot["sourceAssetId"] = None
            changes.append({"shotId": shot["id"], "order": index, "message": "原素材不可用，重新匹配参考图"})
        # An uploaded image is a video reference, not an already rendered video.
        if strategy == "user-video" and video_enabled and ((source and source.get("kind") == "image") or
                (not source and "image-to-video" in shot.get("fallbackStrategies", []))):
            shot.update(sourceStrategy="image-to-video", sourceStartMs=0)
            changes.append({"shotId": shot["id"], "order": index, "message": "已安排参考图生成动态视频，无需上传视频"})
        if shot.get("sourceStrategy") == "image-to-video" and not str(shot.get("videoPrompt") or "").strip():
            shot["videoPrompt"] = "\n".join(str(shot.get(key) or "") for key in ("visual", "camera", "purpose"))[:2500]
            changes.append({"shotId": shot["id"], "order": index, "message": "已根据画面与运镜补齐生成描述"})
    pending = [s for s in shots if not s.get("sourceAssetId") and s.get("sourceStrategy") in {"image-motion", "image-to-video"}]
    if images and pending:
        choices = match_storyboard_assets(session, project, pending, images)
        allowed = {a["id"] for a in images}
        for shot in pending:
            choice = next((c for c in choices["assignments"] if c["shotId"] == shot["id"]), None)
            if choice and choice["assetId"] in allowed:
                shot.update(sourceAssetId=choice["assetId"], fit="contain", materialNote=choice["reason"])
                changes.append({"shotId": shot["id"], "order": shots.index(shot) + 1, "message": "已匹配参考图：" + choice["reason"]})
    return {**data, "shots": shots, "materialChanges": changes}


def execute(run_id):
    try:
        update(run_id, "preparing-assets")
        with SessionLocal() as session:
            run = session.get(DocumentRow, run_id)
            project = session.get(ProjectRow, run.project_id)
            messages, brief_id = deepcopy(run.data["messages"]), run.data["briefId"]
            warnings = []
            try:
                warnings = prepare_images(session, project)
            except (PublicMediaError, MediaGenerationError) as error:
                warnings = [str(error)]
            session.refresh(project)
            if project.messages != messages or project.current_brief_version_id != brief_id:
                raise ValueError("项目输入已变化，请按最新方向重新生成")
            brief = session.get(DocumentRow, brief_id)
            version = (session.scalar(select(func.count()).select_from(DocumentRow).where(
                DocumentRow.project_id == project.id, DocumentRow.kind == "storyboard")) or 0) + 1
            update(run_id, "writing-script", warnings=warnings)
            data = generate_storyboard(session, project, brief, version)
            session.commit()
            update(run_id, "matching-assets")
            data = assign_assets(session, project, data)
            data["materialWarnings"] = warnings
            session.commit()
            update(run_id, "checking-shots")
            session.refresh(project)
            if project.messages != messages or project.current_brief_version_id != brief_id:
                raise ValueError("生成期间项目输入已变化，请按最新方向重新生成")
            storyboard = DocumentRow(id=str(uuid4()), project_id=project.id, kind="storyboard",
                version=version, status="draft", data=data)
            session.add(storyboard)
            project.current_storyboard_version_id = storyboard.id
            project.status = "storyboard_draft"
            session.commit()
            update(run_id, "completed", status="completed", storyboardVersionId=storyboard.id,
                   completedAt=timestamp(), readiness=readiness(project, storyboard))
    except Exception as error:
        message = str(error) if isinstance(error, (ValueError, ModelGatewayError, PublicMediaError, MediaGenerationError)) else "脚本准备失败，请重试"
        update(run_id, "failed", status="failed", errorMessage=message,
               errorCode=getattr(error, "code", None), retryAfterSeconds=getattr(error, "retry_after_seconds", None))


@router.get("/projects/{project_id}/storyboard-runs/latest")
def get_latest(project_id: str, session: Session = Depends(get_session)):
    if not session.get(ProjectRow, project_id):
        raise HTTPException(404, "项目不存在")
    row = latest(session, project_id)
    return {"run": serialize(row) if row else None}


@router.post("/projects/{project_id}/storyboards/{storyboard_id}/auto-materials")
def auto_materials(project_id: str, storyboard_id: str, session: Session = Depends(get_session)):
    with generation_lock:
        project = session.get(ProjectRow, project_id)
        row = session.get(DocumentRow, storyboard_id)
        if not project or not row or row.project_id != project_id or row.kind != "storyboard":
            raise HTTPException(404, "分镜不存在")
        if session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.project_id == project_id,
            GenerationRunRow.status.in_(ACTIVE))):
            raise HTTPException(409, "生成期间暂不能修改分镜")
        original_version = row.row_version
        original_data = deepcopy(row.data)
    try:
        warnings = prepare_images(session, project)
        data = assign_assets(session, project, original_data)
        session.commit()
    except (PublicMediaError, MediaGenerationError, ModelGatewayError) as error:
        raise HTTPException(422, str(error)) from error
    with generation_lock:
        session.refresh(project)
        session.refresh(row)
        if row.row_version != original_version or row.data != original_data:
            raise HTTPException(409, "素材准备期间分镜已修改，请按最新分镜重试")
        if session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.project_id == project_id,
            GenerationRunRow.status.in_(ACTIVE))):
            raise HTTPException(409, "生成期间暂不能修改分镜")
        row.data = {**data, "status": "draft", "materialWarnings": warnings}
        row.status = "draft"
        row.row_version += 1
        project.status = "storyboard_draft"
        session.commit()
        return document(row)


@router.post("/projects/{project_id}/storyboards/{storyboard_id}/material-runs", status_code=202)
def enqueue_materials(project_id: str, storyboard_id: str, generate: bool = False,
                      session: Session = Depends(get_session)):
    with lock, generation_lock:
        project = session.get(ProjectRow, project_id)
        board = session.get(DocumentRow, storyboard_id)
        if not project or not board or board.kind != "storyboard" or board.project_id != project_id:
            raise HTTPException(404, "分镜不存在")
        previous = latest_materials(session, project_id)
        if previous and previous.status in ("queued", "running"):
            return serialize(previous)
        if session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.project_id == project_id, GenerationRunRow.status.in_(ACTIVE))):
            raise HTTPException(409, "视频正在生成，请在生成页查看进度")
        if not executor:
            raise HTTPException(503, "素材准备服务未启动")
        if generate and read_settings(session)["backend"] != "comfyui" and any(s.get("sourceStrategy") in {"image-to-video", "user-video"} for s in board.data["shots"]):
            raise HTTPException(422, "云端视频需先准备素材，再到生成页确认费用")
        run = DocumentRow(id=str(uuid4()), project_id=project_id, kind="material-run", version=1,
            status="queued", data={"phase": "queued", "createdAt": timestamp(), "events": [],
            "storyboardVersionId": board.id, "inputVersion": board.row_version, "generate": generate,
            "errorMessage": None, "changes": [], "checks": [], "generationRunId": None})
        session.add(run)
        session.commit()
        executor.submit(execute_materials, run.id)
        return serialize(run)


def latest_materials(session, project_id):
    return session.scalar(select(DocumentRow).where(DocumentRow.project_id == project_id,
        DocumentRow.kind == "material-run").order_by(DocumentRow.created_at.desc()))


@router.get("/projects/{project_id}/material-runs/latest")
def get_latest_materials(project_id: str, session: Session = Depends(get_session)):
    if not session.get(ProjectRow, project_id):
        raise HTTPException(404, "项目不存在")
    row = latest_materials(session, project_id)
    return {"run": serialize(row) if row else None}


def execute_materials(run_id):
    try:
        update(run_id, "preparing-assets")
        with SessionLocal() as session:
            run = session.get(DocumentRow, run_id)
            board = session.get(DocumentRow, run.data["storyboardVersionId"])
            if board.row_version != run.data["inputVersion"]:
                raise ValueError("分镜已修改，请重新准备最新分镜")
            project_id, board_id = run.project_id, board.id
            auto_materials(project_id, board_id, session)
            prepared_version = board.row_version
            update(run_id, "checking-shots", resultVersion=prepared_version,
                changes=board.data.get("materialChanges", []), warnings=board.data.get("materialWarnings", []))
            checks = shot_readiness(project_id, board_id, session)
            generation_id = None
            if checks["ready"] and run.data["generate"]:
                update(run_id, "starting-video", checks=checks["shots"])
                from .creator import approve_storyboard, create_generation
                from .schemas import ApprovalRequest, GenerationRequest
                with generation_lock:
                    session.refresh(board)
                    if board.row_version != prepared_version:
                        raise ValueError("分镜已修改，未启动旧分镜的视频，请重新准备")
                    approve_storyboard(project_id, board_id, ApprovalRequest(), session)
                    generation = create_generation(GenerationRequest(projectId=project_id, storyboardVersionId=board_id, quality="standard"), session)
                    generation_id = generation["id"]
            update(run_id, "completed" if checks["ready"] else "needs-attention",
                status="completed" if checks["ready"] else "needs_attention", checks=checks["shots"],
                generationRunId=generation_id, completedAt=timestamp())
    except Exception as error:
        message = str(error.detail) if isinstance(error, HTTPException) else str(error) if isinstance(error, (ValueError, ModelGatewayError, MediaGenerationError)) else "素材准备失败，请重试"
        update(run_id, "failed", status="failed", errorMessage=message)


@router.get("/projects/{project_id}/storyboards/{storyboard_id}/readiness")
def shot_readiness(project_id: str, storyboard_id: str, session: Session = Depends(get_session)):
    project = session.get(ProjectRow, project_id)
    row = session.get(DocumentRow, storyboard_id)
    if not project or not row or row.project_id != project_id or row.kind != "storyboard":
        raise HTTPException(404, "分镜不存在")
    checks = []
    for index, shot in enumerate(row.data["shots"], 1):
        try:
            build_plan(project, row, shot_id=shot["id"])
            reason = None
        except (ValueError, KeyError, TypeError, MediaGenerationError, RuntimeError) as error:
            reason = str(error)
        checks.append({"shotId": shot["id"], "order": index, "ready": reason is None, "reason": reason})
    return {"shots": checks, "ready": all(c["ready"] for c in checks)}


def start_worker():
    global executor
    with SessionLocal() as session:
        for row in session.scalars(select(DocumentRow).where(DocumentRow.kind.in_(("storyboard-run", "material-run")),
                DocumentRow.status.in_(("queued", "running")))):
            row.status = "interrupted"
            row.data = {**row.data, "errorMessage": "服务曾中断，请手动重试；未自动重复调用模型"}
        session.commit()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="script-preparation")


def stop_worker():
    global executor
    if executor:
        executor.shutdown(wait=True, cancel_futures=True)
        executor = None
