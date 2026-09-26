"""Explicit, non-destructive reference-photo cut using the existing renderer."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .creator import copy_project, create_generation, get_project_or_404, get_document_or_404
from .database import get_session
from .fixtures import timestamp
from .generation import ACTIVE, build_plan, generation_lock, live_blender_run
from .media import MediaGenerationError
from .models import DocumentRow, GenerationRunRow, ProjectRow
from .schemas import ApiModel, GenerationRequest
from .serializers import generation_run

router = APIRouter()


class ReferenceCutRequest(ApiModel):
    storyboard_version_id: str
    row_version: int = Field(ge=1)
    asset_ids: list[str] = Field(min_length=1, max_length=6)
    confirm_simplification: bool = False
    narration: bool = False


def display_data(board, asset_ids, narration):
    captions = ["初见轮廓", "线条之间", "光影质感", "换个角度", "定格这一刻", "欢迎你的到来"]
    shots = []
    for index, asset_id in enumerate(asset_ids):
        caption = captions[index] if index < len(asset_ids) - 1 else "欢迎你的到来"
        shots.append({"id": str(uuid4()), "order": index + 1, "purpose": f"参考画面 {index + 1}",
            "visual": "展示选定参考照片中的可见内容，不生成新场景或隐藏部件。",
            "camera": "原图居中缓慢推近，不改变拍摄角度。", "sourceStrategy": "image-motion",
            "sourceAssetId": asset_id, "selectionOwner": "user", "strategyOwner": "user",
            "startMs": index * 3000, "durationMs": 3000, "caption": caption,
            "voiceover": caption if narration else "", "fit": "contain", "backgroundFill": "soft",
            "status": "draft", "requiresPlanning": False})
    return {**board.data, "title": "参考图展示版", "shots": shots, "totalDurationMs": len(shots) * 3000,
        "executionVariant": "reference-display", "materialWarnings": [], "materialChanges": [],
        "script": {"voiceoverEnabled": narration}, "soundPlanConfirmed": True,
        "soundPlan": {"background": "local-pulse", "narration": narration}, "status": "approved",
        "approvedAt": timestamp()}


@router.post("/projects/{project_id}/reference-cuts", status_code=202)
def create_reference_cut(project_id: str, payload: ReferenceCutRequest, session: Session = Depends(get_session)):
    if not payload.confirm_simplification:
        raise HTTPException(422, "请确认制作独立的参考图展示版：不包含原脚本的人物动作、真实环绕或新场景")
    with generation_lock:
        source = get_project_or_404(session, project_id)
        board = get_document_or_404(session, payload.storyboard_version_id, "storyboard", project_id)
        if source.current_storyboard_version_id != board.id or board.row_version != payload.row_version:
            raise HTTPException(409, "分镜已变化，请刷新后重新确认展示版")
        asset_ids = list(dict.fromkeys(payload.asset_ids))
        assets = {a["id"]: a for a in source.asset_versions}
        if any(a not in assets or assets[a].get("kind") != "image" or assets[a].get("status") != "ready"
               or not Path(assets[a].get("uri", "")).is_file() for a in asset_ids):
            raise HTTPException(422, "展示版只能使用本项目中已下载的可用图片")
        request = {"storyboardId": board.id, "rowVersion": board.row_version,
                   "assetIds": asset_ids, "narration": payload.narration}
        for candidate in session.scalars(select(DocumentRow).where(DocumentRow.kind == "storyboard")):
            if candidate.data.get("referenceCutRequest") != request:
                continue
            project = session.get(ProjectRow, candidate.project_id)
            if not project or project.status == "deleted":
                continue
            prior = session.scalar(select(GenerationRunRow).where(GenerationRunRow.storyboard_version_id == candidate.id)
                                   .order_by(GenerationRunRow.created_at.desc()))
            if prior:
                return {"projectId": project.id, "run": generation_run(prior)}
        if session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.status.in_(ACTIVE))) or live_blender_run(session):
            raise HTTPException(409, "另一个视频任务正在执行，请等待完成后制作展示版")
        try:
            build_plan(source, SimpleNamespace(data=display_data(board, asset_ids, payload.narration)))
        except (ValueError, KeyError, TypeError, MediaGenerationError) as error:
            raise HTTPException(422, str(error)) from error
        copied = copy_project(source.id, session)
        project = session.get(ProjectRow, copied["id"])
        target = session.get(DocumentRow, project.current_storyboard_version_id)
        remap = {a["reusedFromAssetId"]: a["id"] for a in project.asset_versions}
        target.data = {**display_data(target, [remap[a] for a in asset_ids], payload.narration),
                       "referenceCutRequest": request}
        target.status = "approved"
        project.title = source.title[:100] + " · 参考图展示版"
        project.status = "storyboard_approved"
        session.commit()
        run = create_generation(GenerationRequest(projectId=project.id, storyboardVersionId=target.id), session)
        return {"projectId": project.id, "run": run}
