import asyncio
import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4
from decimal import Decimal

from .fal_video import VideoProviderError
from .generation import worker_has_run
from .blender import validate_glb, matching_process

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, get_session
from .fixtures import build_brief, build_project_facts, build_storyboard, timestamp
from .gateway import ModelGatewayError, generate_storyboard
from .advisor import create_advice
from .generation import ACTIVE, build_plan, generation_lock, latest_shots, readiness, submit_run, live_blender_run
from .media import MediaGenerationError
from .models import AccountBriefRow, AdvisorRunRow, ArtifactRow, AssetDiscoveryRow, DocumentRow, GenerationRunRow, ModelDeploymentRow, ModelInvocationRow, ModelProviderRow, ProjectRow, RoutingVersionRow
from .schemas import AccountBriefInput, ApprovalRequest, AssetUploadIntentInput, CreateBriefRequest, CreateProjectRequest, GenerationRequest, MessageRequest, StoryboardUpdate
from .serializers import account_brief, advisor_run, artifact, document, generation_run, project


router = APIRouter()
upload_intents: dict[str, dict] = {}


@router.get("/account-brief")
def get_account_brief(session: Session = Depends(get_session)) -> dict:
    row = session.get(AccountBriefRow, "default")
    if not row:
        raise HTTPException(status_code=404, detail="Account brief not found")
    return account_brief(row)


@router.put("/account-brief")
def upsert_account_brief(payload: AccountBriefInput, session: Session = Depends(get_session)) -> dict:
    row = session.get(AccountBriefRow, "default")
    data = payload.model_dump(by_alias=True, exclude={"row_version"})
    if row:
        if payload.row_version is not None and payload.row_version != row.row_version:
            raise HTTPException(status_code=409, detail="Account brief changed; refresh before saving")
        row.data = data
        row.version += 1
        row.row_version += 1
    else:
        row = AccountBriefRow(id="default", data=data)
        session.add(row)
    session.commit()
    return account_brief(row)


def get_project_or_404(session: Session, project_id: str) -> ProjectRow:
    row = session.get(ProjectRow, project_id)
    if not row or row.status == "deleted":
        raise HTTPException(status_code=404, detail="Project not found")
    return row


def get_document_or_404(session: Session, document_id: str, kind: str, project_id: str | None = None) -> DocumentRow:
    row = session.get(DocumentRow, document_id)
    if not row or row.kind != kind or (project_id is not None and row.project_id != project_id):
        raise HTTPException(status_code=404, detail=f"{kind} not found")
    return row


@router.get("/projects")
def list_projects(
    status: str | None = None,
    query: str | None = None,
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    active = or_(
        select(GenerationRunRow.id).where(GenerationRunRow.project_id == ProjectRow.id, GenerationRunRow.status.in_(ACTIVE)).exists(),
        select(DocumentRow.id).where(DocumentRow.project_id == ProjectRow.id, DocumentRow.status.in_(["queued", "running"])).exists(),
        select(ModelInvocationRow.id).where(ModelInvocationRow.project_id == ProjectRow.id, ModelInvocationRow.status == "calling").exists(),
        select(AssetDiscoveryRow.id).where(AssetDiscoveryRow.project_id == ProjectRow.id, AssetDiscoveryRow.status.in_(["queued", "running"])).exists())
    statement = select(ProjectRow, active.label("activity_running"))
    if status != "deleted":
        statement = statement.where(ProjectRow.status != "deleted")
    if status == "pending":
        statement = statement.where(~active, ProjectRow.status.in_(["intake", "advising", "brief_draft", "brief_approved", "storyboard_draft", "storyboard_approved", "needs_attention"]))
    elif status == "generating":
        statement = statement.where(or_(active, ProjectRow.status == "generating"))
    elif status == "completed":
        statement = statement.where(~active, ProjectRow.status == "completed")
    elif status:
        statement = statement.where(ProjectRow.status == status)
    if query:
        statement = statement.where(func.lower(ProjectRow.title).contains(query.lower()))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.execute(statement.order_by(ProjectRow.updated_at.desc(), ProjectRow.id).offset(offset).limit(page_size))
    return {"items": [{**project(row), "activityRunning": running} for row, running in rows], "total": total, "nextCursor": offset + page_size if offset + page_size < total else None}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    from .advisor import _lock, _inflight
    from .storyboard_jobs import lock as script_lock
    from .asset_discovery import lock as discovery_lock
    with script_lock, discovery_lock, generation_lock, _lock:
        row = get_project_or_404(session, project_id)
        active = project_id in _inflight or session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.project_id == project_id, GenerationRunRow.status.in_(ACTIVE)))
        active = active or session.scalar(select(DocumentRow.id).where(DocumentRow.project_id == project_id, DocumentRow.status.in_(["queued", "running"])))
        active = active or session.scalar(select(ModelInvocationRow.id).where(ModelInvocationRow.project_id == project_id, ModelInvocationRow.status == "calling"))
        active = active or session.scalar(select(AssetDiscoveryRow.id).where(AssetDiscoveryRow.project_id == project_id, AssetDiscoveryRow.status.in_(["queued", "running", "searching"])))
        if active:
            raise HTTPException(409, "项目仍有任务执行中，请先等待完成或停止任务后再删除")
        session.add(DocumentRow(id=str(uuid4()), project_id=project_id, kind="project-deletion", version=1, status="completed",
            data={"previousStatus": row.status, "deletedAt": timestamp()}))
        row.status = "deleted"
        row.row_version += 1
        session.commit()
        return {"id": project_id, "status": "deleted"}


@router.post("/projects/{project_id}/restoration")
def restore_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    with generation_lock:
        row = session.get(ProjectRow, project_id)
        if not row or row.status != "deleted":
            raise HTTPException(404, "回收站项目不存在")
        record = session.scalar(select(DocumentRow).where(DocumentRow.project_id == project_id, DocumentRow.kind == "project-deletion").order_by(DocumentRow.created_at.desc()))
        row.status = record.data["previousStatus"] if record else "intake"
        row.row_version += 1
        session.commit()
        return project(row)


@router.get("/projects/{project_id}/activity")
def get_activity(project_id: str, category: str | None = None, offset: int = Query(0, ge=0),
        page_size: int = Query(50, alias="pageSize", ge=1, le=100), session: Session = Depends(get_session)) -> dict:
    from .project_activity import activity
    items = activity(session, get_project_or_404(session, project_id))
    if category:
        items = [item for item in items if item["category"] == category]
    return {"items": items[offset:offset + page_size], "total": len(items),
        "nextCursor": offset + page_size if offset + page_size < len(items) else None}


@router.post("/projects", status_code=201)
def create_project(payload: CreateProjectRequest, session: Session = Depends(get_session)) -> dict:
    project_id = str(uuid4())
    message_id = str(uuid4())
    row = ProjectRow(
        id=project_id,
        title=payload.title,
        content_pack_id=payload.content_pack_id,
        mode=payload.mode,
        target_platform=payload.target_platform,
        locale=payload.locale,
        messages=[
            {
                "id": message_id,
                "projectId": project_id,
                "role": "user",
                "text": payload.initial_message,
                "assetVersionIds": payload.asset_version_ids,
                "createdAt": timestamp(),
            }
        ],
        facts=build_project_facts(project_id, payload.title, payload.initial_message, payload.target_platform),
    )
    session.add(row)
    session.commit()
    return project(row)


@router.post("/projects/{project_id}/copies", status_code=201)
def copy_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    with generation_lock:
        source = get_project_or_404(session, project_id)
        if not source.current_storyboard_version_id or not source.current_brief_version_id:
            raise HTTPException(422, "需要已保存的脚本和创意方案才能复用")
        board = get_document_or_404(session, source.current_storyboard_version_id, "storyboard", source.id)
        brief = get_document_or_404(session, source.current_brief_version_id, "brief", source.id)
        pid, sid, bid = str(uuid4()), str(uuid4()), str(uuid4())
        id_map = {source.id: pid, board.id: sid, brief.id: bid}
        for item in [*source.asset_versions, *board.data["shots"], *source.messages, *source.facts]:
            if item.get("id"):
                id_map[item["id"]] = str(uuid4())
        def remap(value):
            if isinstance(value, dict):
                return {key: remap(item) for key, item in value.items() if key not in {"approvedAt", "previewRunId"}}
            if isinstance(value, list):
                return [remap(item) for item in value]
            return id_map.get(value, value) if isinstance(value, str) else value
        assets = remap(deepcopy(source.asset_versions))
        for original, asset in zip(source.asset_versions, assets):
            asset.update(reusedFromProjectId=source.id, reusedFromAssetId=original["id"])
        data = remap(deepcopy(board.data))
        for shot in data["shots"]:
            if shot.get("sourceStrategy") in {"image-motion", "image-to-video"}:
                shot.setdefault("backgroundFill", "soft")
                shot.setdefault("referenceFraming", "portrait-soft")
        data.update(status="draft", version=1, reusedFromProjectId=source.id, reusedFromStoryboardId=board.id)
        row = ProjectRow(id=pid, title=(source.title[:110] + " · 副本"), content_pack_id=source.content_pack_id,
            mode=source.mode, target_platform=source.target_platform, locale=source.locale,
            messages=remap(deepcopy(source.messages)), facts=remap(deepcopy(source.facts)), asset_versions=assets,
            status="storyboard_draft", current_storyboard_version_id=sid, current_brief_version_id=bid)
        session.add(row)
        session.add(DocumentRow(id=bid, project_id=pid, kind="brief", version=1, status="draft",
            data={**remap(deepcopy(brief.data)), "status": "draft", "version": 1}))
        session.add(DocumentRow(id=sid, project_id=pid, kind="storyboard", version=1, status="draft", data=data))
        session.commit()
        return project(row)


@router.post("/assets/upload-intents", status_code=201)
def create_asset_upload_intent(payload: AssetUploadIntentInput, session: Session = Depends(get_session)) -> dict:
    get_project_or_404(session, payload.project_id)
    asset_version_id = str(uuid4())
    upload_token = str(uuid4())
    upload_intents[upload_token] = {
        "assetVersionId": asset_version_id,
        **payload.model_dump(by_alias=True),
    }
    return {
        "assetVersionId": asset_version_id,
        "uploadUrl": f"/api/v1/assets/uploads/{upload_token}",
        "expiresAt": "2099-01-01T00:00:00Z",
    }


@router.put("/assets/uploads/{upload_token}", status_code=201, include_in_schema=False)
async def upload_asset_content(upload_token: str, request: Request, session: Session = Depends(get_session)) -> dict:
    intent = upload_intents.pop(upload_token, None)
    if not intent:
        raise HTTPException(status_code=404, detail="Upload intent not found or already used")
    content = await request.body()
    if len(content) != intent["sizeBytes"]:
        raise HTTPException(status_code=422, detail="Uploaded file size does not match intent")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if digest != intent["sha256"]:
        raise HTTPException(status_code=422, detail="Uploaded file hash does not match intent")

    project_row = get_project_or_404(session, intent["projectId"])
    suffix = Path(intent["fileName"]).suffix.lower()[:10]
    model_metadata = {}
    if intent["mimeType"] == "model/gltf-binary":
        if suffix != ".glb":
            raise HTTPException(422, "三维素材仅支持 .glb")
        try:
            model_metadata = validate_glb(content)
        except MediaGenerationError as error:
            raise HTTPException(422, str(error)) from error
    target = get_settings().data_dir / "assets" / project_row.id / f"{intent['assetVersionId']}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    asset_version = {
        "id": intent["assetVersionId"],
        "assetId": str(uuid4()),
        "version": 1,
        "kind": intent["mimeType"].split("/", 1)[0],
        "sourceType": "user-upload",
        "fileName": intent["fileName"],
        "mimeType": intent["mimeType"],
        "sizeBytes": len(content),
        "sha256": digest,
        "uri": str(target.resolve()),
        "status": "ready",
        "createdAt": timestamp(),
        **model_metadata,
    }
    project_row.asset_versions = [*project_row.asset_versions, asset_version]
    if project_row.messages:
        messages = [dict(message) for message in project_row.messages]
        messages[0]["assetVersionIds"] = [*messages[0].get("assetVersionIds", []), asset_version["id"]]
        project_row.messages = messages
    project_row.row_version += 1
    session.commit()
    return asset_version


@router.get("/projects/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict:
    return project(get_project_or_404(session, project_id))


@router.patch("/projects/{project_id}")
def update_project(project_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    row = get_project_or_404(session, project_id)
    if title := payload.get("title"):
        row.title = title[:120]
    row.row_version += 1
    session.commit()
    return project(row)


@router.get("/projects/{project_id}/workspace")
def get_workspace(project_id: str, session: Session = Depends(get_session)) -> dict:
    row = get_project_or_404(session, project_id)
    return {
        "project": project(row),
        "messages": row.messages,
        "facts": row.facts,
        "evidenceItems": row.evidence_items,
        "assetVersions": [{key: value for key, value in asset.items() if key != "uri"} | {"previewUrl": f"/api/v1/projects/{project_id}/assets/{asset['id']}/content"} for asset in row.asset_versions],
        "latestAdvisorRunId": row.latest_advisor_run_id,
        "activeGenerationRunId": row.active_generation_run_id,
        "generationReadiness": readiness(row, session.get(DocumentRow, row.current_storyboard_version_id) if row.current_storyboard_version_id else None),
    }


@router.get("/projects/{project_id}/assets/{asset_id}/content", include_in_schema=False)
def get_asset_content(project_id: str, asset_id: str, session: Session = Depends(get_session)) -> FileResponse:
    row = get_project_or_404(session, project_id)
    asset = next((item for item in row.asset_versions if item["id"] == asset_id), None)
    if not asset or not Path(asset["uri"]).is_file():
        raise HTTPException(status_code=404, detail="素材不存在")
    return FileResponse(asset["uri"], media_type=asset["mimeType"])


@router.post("/projects/{project_id}/messages", status_code=201)
def add_message(project_id: str, payload: MessageRequest, session: Session = Depends(get_session)) -> dict:
    row = get_project_or_404(session, project_id)
    message = {
        "id": str(uuid4()),
        "projectId": project_id,
        "role": "user",
        "text": payload.text,
        "assetVersionIds": payload.asset_version_ids,
        "createdAt": timestamp(),
    }
    row.messages = [*row.messages, message]
    row.row_version += 1
    session.commit()
    return message


@router.get("/projects/{project_id}/events")
async def stream_events(project_id: str) -> StreamingResponse:
    with SessionLocal() as session:
        get_project_or_404(session, project_id)

    async def events():
        event_id = str(uuid4())
        yield f"id: {event_id}\nevent: workspace.snapshot\ndata: {{\"projectId\":\"{project_id}\"}}\n\n"
        while True:
            await asyncio.sleep(15)
            yield ": heartbeat\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/projects/{project_id}/advisor-runs", status_code=202)
def create_advisor_run(project_id: str, session: Session = Depends(get_session)) -> dict:
    return create_advice(session, project_id)


@router.get("/advisor-runs/{advisor_run_id}")
def get_advisor_run(advisor_run_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(AdvisorRunRow, advisor_run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Advisor run not found")
    return advisor_run(row)


@router.post("/projects/{project_id}/creative-briefs", status_code=201)
def create_creative_brief(project_id: str, payload: CreateBriefRequest, session: Session = Depends(get_session)) -> dict:
    project_row = get_project_or_404(session, project_id)
    advisor = session.get(AdvisorRunRow, payload.advisor_run_id)
    if not advisor or advisor.project_id != project_id:
        raise HTTPException(status_code=404, detail="Advisor run not found")
    proposal = next((item for item in advisor.result["proposals"] if item["proposalKey"] == payload.proposal_key), None)
    if not proposal:
        raise HTTPException(status_code=422, detail="Proposal not found")
    version = (session.scalar(select(func.count()).select_from(DocumentRow).where(DocumentRow.project_id == project_id, DocumentRow.kind == "brief")) or 0) + 1
    row = DocumentRow(id=str(uuid4()), project_id=project_id, kind="brief", version=version, data={**build_brief(project_id, proposal, version), **payload.overrides})
    project_row.current_brief_version_id = row.id
    project_row.status = "brief_draft"
    session.add(row)
    session.commit()
    return document(row)


@router.get("/projects/{project_id}/creative-briefs/{brief_id}")
def get_creative_brief(project_id: str, brief_id: str, session: Session = Depends(get_session)) -> dict:
    get_project_or_404(session, project_id)
    return document(get_document_or_404(session, brief_id, "brief", project_id))


@router.post("/projects/{project_id}/creative-briefs/{brief_id}/approval", status_code=201)
def approve_brief(project_id: str, brief_id: str, payload: ApprovalRequest, session: Session = Depends(get_session)) -> dict:
    project_row = get_project_or_404(session, project_id)
    row = get_document_or_404(session, brief_id, "brief", project_id)
    row.status = "approved"
    row.data = {**row.data, "status": "approved", "approvedAt": timestamp()}
    project_row.current_brief_version_id = row.id
    project_row.status = "brief_approved"
    session.commit()
    return {"id": str(uuid4()), "targetType": "creative-brief", "targetVersionId": row.id, "decision": "approved", "comment": payload.comment, "createdAt": timestamp()}


@router.post("/projects/{project_id}/storyboard-runs", status_code=202)
def create_storyboard(project_id: str, background: bool = False, session: Session = Depends(get_session)) -> dict:
    project_row = get_project_or_404(session, project_id)
    if background:
        from .storyboard_jobs import enqueue
        return enqueue(session, project_row)
    if not project_row.current_brief_version_id:
        raise HTTPException(status_code=409, detail="Approve a brief before generating a storyboard")
    version = (session.scalar(select(func.count()).select_from(DocumentRow).where(DocumentRow.project_id == project_id, DocumentRow.kind == "storyboard")) or 0) + 1
    brief = get_document_or_404(session, project_row.current_brief_version_id, "brief", project_id)
    try:
        storyboard_data = generate_storyboard(session, project_row, brief, version)
    except ModelGatewayError as error:
        headers = {"Retry-After": str(error.retry_after_seconds)} if error.retry_after_seconds else None
        raise HTTPException(status_code=429 if error.code in {"RATE_LIMITED", "QUOTA_EXCEEDED"} else 502,
                            detail=str(error), headers=headers) from error
    storyboard = DocumentRow(
        id=str(uuid4()),
        project_id=project_id,
        kind="storyboard",
        version=version,
        data=storyboard_data,
    )
    project_row.current_storyboard_version_id = storyboard.id
    project_row.status = "storyboard_draft"
    session.add(storyboard)
    session.commit()
    return {"id": str(uuid4()), "status": "completed", "storyboardVersionId": storyboard.id, "createdAt": timestamp()}


@router.get("/projects/{project_id}/storyboards/{storyboard_id}")
def get_storyboard(project_id: str, storyboard_id: str, session: Session = Depends(get_session)) -> dict:
    get_project_or_404(session, project_id)
    return document(get_document_or_404(session, storyboard_id, "storyboard", project_id))


@router.put("/projects/{project_id}/storyboards/{storyboard_id}")
def replace_storyboard(project_id: str, storyboard_id: str, payload: StoryboardUpdate, session: Session = Depends(get_session)) -> dict:
    with generation_lock:
        project_row = get_project_or_404(session, project_id)
        if session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.project_id == project_id, GenerationRunRow.status.in_(ACTIVE))):
            raise HTTPException(status_code=409, detail="生成期间暂不能修改分镜")
        row = get_document_or_404(session, storyboard_id, "storyboard", project_id)
        if not payload.shots or any(type(s.get("durationMs")) is not int or not 500 <= s["durationMs"] <= 15000 for s in payload.shots):
            raise HTTPException(status_code=422, detail="需要有效镜头和 500 至 15000 毫秒的时长")
        ids = [s.get("id") for s in payload.shots]
        if any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
            raise HTTPException(status_code=422, detail="镜头 ID 缺失或重复")
        total = sum(s["durationMs"] for s in payload.shots)
        if total > 60000 or len(payload.shots) > 12:
            raise HTTPException(status_code=422, detail="最多 12 个镜头，成片最长 60 秒")
        shots, cursor = [], 0
        for index, shot in enumerate(payload.shots, 1):
            old = next((s for s in row.data["shots"] if s["id"] == shot["id"]), {})
            if shot.get("sourceAssetId") != old.get("sourceAssetId"):
                shot["selectionOwner"] = "user" if shot.get("sourceAssetId") else "platform"
            if shot.get("sourceStrategy") != old.get("sourceStrategy"):
                shot["strategyOwner"] = "user"
            if any(shot.get(key) != old.get(key) for key in ("visual", "camera", "sourceAssetId", "sourceStrategy")):
                shot.pop("productionPlan", None)
                shot.pop("previewRunId", None)
                if old.get("productionPlan") or old.get("requiresPlanning"):
                    shot["requiresPlanning"] = shot.get("sourceStrategy") in {"image-motion", "image-to-video"}
            shots.append({**shot, "order": index, "startMs": cursor, "status": "draft"})
            cursor += shot["durationMs"]
        row.data = {**row.data, "shots": shots, "totalDurationMs": total, "status": "draft"}
        if payload.sound_plan is not None:
            row.data = {**row.data, "soundPlan": payload.sound_plan.model_dump(), "soundPlanConfirmed": True}
        row.status = "draft"
        row.row_version += 1
        project_row.status = "storyboard_draft"
        session.commit()
        return document(row)


@router.post("/projects/{project_id}/storyboards/{storyboard_id}/approval", status_code=201)
def approve_storyboard(project_id: str, storyboard_id: str, payload: ApprovalRequest, session: Session = Depends(get_session)) -> dict:
    project_row = get_project_or_404(session, project_id)
    row = get_document_or_404(session, storyboard_id, "storyboard", project_id)
    row.status = "approved"
    row.data = {**row.data, "status": "approved", "approvedAt": timestamp()}
    project_row.status = "storyboard_approved"
    session.commit()
    return {"id": str(uuid4()), "targetType": "storyboard", "targetVersionId": row.id, "decision": "approved", "comment": payload.comment, "createdAt": timestamp()}


@router.post("/generation-runs", status_code=202)
def create_generation(payload: GenerationRequest, session: Session = Depends(get_session)) -> dict:
    with generation_lock:
        project_row = get_project_or_404(session, payload.project_id)
        active = session.scalar(select(GenerationRunRow).where(GenerationRunRow.status.in_(ACTIVE)))
        if active:
            scope = "shot-preview" if payload.shot_id is not None else "full-video"
            if (active.project_id == payload.project_id and active.storyboard_version_id == payload.storyboard_version_id
                    and (active.request_data or {}).get("scope", "full-video") == scope
                    and (payload.shot_id is None or active.request_data["shots"][0]["id"] == payload.shot_id)):
                return generation_run(active)
            raise HTTPException(status_code=409, detail="另一个生成任务正在执行，请稍后再试")
        if live_blender_run(session):
            raise HTTPException(409, "此前 Blender 进程仍在渲染，请恢复或停止原任务")
        storyboard = get_document_or_404(session, payload.storyboard_version_id, "storyboard", payload.project_id)
        for previous in session.scalars(select(GenerationRunRow).where(GenerationRunRow.project_id == payload.project_id)):
            if previous.request_data and previous.request_data.get("video"):
                for shot in latest_shots(previous):
                    if shot.get("submissionState") in {"submitting", "unknown"} or (shot.get("providerHandle") and shot.get("providerStatus") not in {"COMPLETED", "FAILED"}):
                        raise HTTPException(409, "项目存在未确认的上游视频任务，请先恢复原任务或在供应商后台核对")
        if storyboard.status != "approved" and payload.shot_id is None:
            raise HTTPException(status_code=409, detail="请先确认当前分镜")
        try:
            plan = build_plan(project_row, storyboard, payload.quality, payload.audio_asset_id, payload.narration, payload.shot_id)
        except (ValueError, KeyError, TypeError, VideoProviderError, MediaGenerationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if plan.get("video") and plan["video"].get("backend") != "comfyui" and not payload.confirm_video_cost:
            raise HTTPException(status_code=422, detail="请先确认本次视频模型调用及估算费用")
        run_id = str(uuid4())
        run = GenerationRunRow(id=run_id, project_id=payload.project_id, storyboard_version_id=storyboard.id,
            routing_policy_version_id="video-execution-v1" if plan.get("video") else "local-uploaded-media-v1", status="queued", request_data=plan,
            shot_runs=[{"id": str(uuid4()), "shotId": shot["id"], "generationRunId": run_id,
                        "purpose": shot.get("purpose", ""), "sourceAssetId": shot["sourceAssetId"],
                        "strategy": shot["sourceStrategy"], "attempt": 1, "status": "queued", "artifactId": None}
                       for shot in plan["shots"]])
        if payload.shot_id is None:
            project_row.active_generation_run_id = run.id
            project_row.status = "generating"
        session.add(run)
        session.commit()
        result = generation_run(run)
        submit_run(run.id)
        return result


@router.get("/generation-runs/{run_id}")
def get_generation(run_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(GenerationRunRow, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return generation_run(row)


@router.post("/generation-runs/{run_id}/recomposition", status_code=202)
def recompose_generation(run_id: str, session: Session = Depends(get_session)):
    from .generation import local_composition_shot
    from .media import probe_media
    with generation_lock:
        prior = session.get(GenerationRunRow, run_id)
        if not prior:
            raise HTTPException(404, "生成任务不存在")
        active = session.scalar(select(GenerationRunRow).where(GenerationRunRow.status.in_(ACTIVE)))
        if active:
            if (active.request_data or {}).get("sourceGenerationRunId") == run_id:
                return generation_run(active)
            raise HTTPException(409, "已有任务执行中，请等待完成")
        if prior.status != "completed" or (prior.request_data or {}).get("scope") == "shot-preview" or ((prior.request_data or {}).get("video") or {}).get("backend") != "comfyui":
            raise HTTPException(422, "需要已完成的本地 AI 视频任务")
        request = deepcopy(prior.request_data)
        shots, assets = [], {}
        try:
            for shot in request["shots"]:
                attempt = next(s for s in latest_shots(prior) if s["shotId"] == shot["id"])
                artifact_row = session.get(ArtifactRow, attempt["artifactId"])
                if not artifact_row:
                    raise MediaGenerationError("原镜头文件记录不存在，无法重新合成")
                path = Path(artifact_row.path)
                if shot["sourceStrategy"] == "image-to-video":
                    path = path.with_suffix(".source.mp4")
                    normalized = local_composition_shot(request, shot)
                else:
                    normalized = {**shot, "sourceStrategy": "user-video", "sourceStartMs": 0}
                if not path.is_file():
                    raise MediaGenerationError("原始生成片段已丢失，无法直接重新合成")
                info = probe_media(path)
                asset_id = str(uuid4())
                assets[asset_id] = {"id": asset_id, "kind": "video", "uri": str(path), "status": "ready",
                    "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                    "durationMs": info["durationMs"], "sourceArtifactId": artifact_row.id}
                shots.append({**normalized, "sourceAssetId": asset_id})
        except (MediaGenerationError, OSError, KeyError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
        request.update(shots=shots, assets=assets, video=None, blender=None, sourceGenerationRunId=run_id)
        new_id = str(uuid4())
        row = GenerationRunRow(id=new_id, project_id=prior.project_id, storyboard_version_id=prior.storyboard_version_id,
            routing_policy_version_id="local-recomposition-v1", status="queued", request_data=request,
            shot_runs=[{"id": str(uuid4()), "shotId": shot["id"], "generationRunId": new_id,
                "purpose": shot.get("purpose", ""), "sourceAssetId": shot["sourceAssetId"], "strategy": "user-video",
                "attempt": 1, "status": "queued", "artifactId": None} for shot in shots])
        session.add(row)
        project_row = session.get(ProjectRow, prior.project_id)
        project_row.active_generation_run_id = row.id
        project_row.status = "generating"
        session.commit()
        result = generation_run(row)
        submit_run(row.id)
        return result


@router.get("/projects/{project_id}/storyboards/{storyboard_id}/shots/{shot_id}/preview")
def get_shot_preview(project_id: str, storyboard_id: str, shot_id: str, session: Session = Depends(get_session)) -> dict:
    project_row = get_project_or_404(session, project_id)
    storyboard = get_document_or_404(session, storyboard_id, "storyboard", project_id)
    if not any(shot.get("id") == shot_id for shot in storyboard.data.get("shots", [])):
        raise HTTPException(404, "镜头不存在")
    previous = next((row for row in session.scalars(select(GenerationRunRow).where(
        GenerationRunRow.project_id == project_id, GenerationRunRow.storyboard_version_id == storyboard_id
    ).order_by(GenerationRunRow.created_at.desc())) if (row.request_data or {}).get("scope") == "shot-preview"
        and row.request_data["shots"][0]["id"] == shot_id), None)
    try:
        plan = build_plan(project_row, storyboard, "preview", shot_id=shot_id)
        ready = {"ready": True, "mode": plan["mode"], "reason": None,
                 "estimatedUsd": plan["video"]["estimatedUsd"] if plan.get("video") else None}
    except (ValueError, KeyError, TypeError, VideoProviderError, MediaGenerationError) as error:
        ready = {"ready": False, "mode": "capability-or-asset-missing", "reason": str(error)}
    return {"run": generation_run(previous) if previous else None, "readiness": ready}


@router.post("/generation-runs/{run_id}/adoption")
def adopt_shot_preview(run_id: str, session: Session = Depends(get_session)) -> dict:
    with generation_lock:
        run = session.get(GenerationRunRow, run_id)
        if not run:
            raise HTTPException(404, "试片任务不存在")
        if (run.request_data or {}).get("scope") != "shot-preview" or run.status != "completed":
            raise HTTPException(409, "只能采用已完成的单镜头试片")
        if session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.project_id == run.project_id, GenerationRunRow.status.in_(ACTIVE))):
            raise HTTPException(409, "生成期间暂不能采用试片")
        project_row = get_project_or_404(session, run.project_id)
        if project_row.current_storyboard_version_id != run.storyboard_version_id:
            raise HTTPException(409, "当前分镜已更换，请在当前分镜重新试片")
        storyboard = get_document_or_404(session, run.storyboard_version_id, "storyboard", run.project_id)
        source = run.request_data["shots"][0]
        current = next((shot for shot in storyboard.data["shots"] if shot["id"] == source["id"]), None)
        result = latest_shots(run)[0]
        media = session.get(ArtifactRow, result.get("artifactId"))
        if not media or media.generation_run_id != run.id or media.shot_id != source["id"] or not Path(media.path).is_file():
            raise HTTPException(409, "试片文件不存在")
        if "sha256:" + hashlib.sha256(Path(media.path).read_bytes()).hexdigest() != media.sha256:
            raise HTTPException(409, "试片文件已改变，请重新生成")
        ignored = {"status", "order", "startMs"}
        already = current and current.get("previewRunId") == run.id and current.get("sourceAssetId") == media.id
        if not already and (not current or {k: v for k, v in current.items() if k not in ignored} != {k: v for k, v in source.items() if k not in ignored}):
            raise HTTPException(409, "试片对应镜头已改变，请恢复原参数或重新试片；未覆盖当前编辑")
        asset = next((asset for asset in project_row.asset_versions if asset["id"] == media.id), None)
        if not asset:
            asset = {"id": media.id, "projectId": run.project_id, "kind": "video", "fileName": f"shot-preview-{media.id}.mp4",
                     "mimeType": "video/mp4", "sizeBytes": media.size_bytes, "sha256": media.sha256,
                     "uri": media.path, "status": "ready", "width": media.width, "height": media.height,
                     "durationMs": media.duration_ms, "referenceSource": "shot-preview", "generationRunId": run.id,
                     "sourceAssetId": source["sourceAssetId"], "createdAt": timestamp()}
            project_row.asset_versions = [*project_row.asset_versions, asset]
        if not already:
            storyboard.data = {**storyboard.data, "status": "draft", "shots": [
                {**shot, "sourceStrategy": "user-video", "sourceAssetId": media.id, "sourceStartMs": 0,
                 "fit": "contain", "previewRunId": run.id, "status": "draft"} if shot["id"] == source["id"] else shot
                for shot in storyboard.data["shots"]]}
            storyboard.status = "draft"
            storyboard.row_version += 1
            project_row.status = "storyboard_draft"
            project_row.row_version += 1
        session.commit()
        return {"storyboard": document(storyboard), "assetVersion": {k: v for k, v in asset.items() if k != "uri"}
                | {"previewUrl": f"/api/v1/projects/{run.project_id}/assets/{media.id}/content"}}


@router.post("/generation-runs/{run_id}/cancellation", status_code=202)
def cancel_generation(run_id: str, session: Session = Depends(get_session)) -> dict:
    with generation_lock:
        row = session.get(GenerationRunRow, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Generation run not found")
        if row.status not in ACTIVE and not (row.status == "interrupted" and (row.request_data or {}).get("blender")):
            raise HTTPException(status_code=409, detail="任务已结束")
        row.status = "cancelled"
        if (row.request_data or {}).get("blender"):
            row.error_message = "已请求停止对应 Blender 进程，已完成的片段保留"
        if row.request_data and row.request_data.get("video"):
            row.error_message = ("已请求停止，后台将向本地服务发送定向取消；不会取消其他任务。"
                                 if row.request_data["video"].get("backend") == "comfyui" else
                                 "已停止本地等待；上游视频可能继续生成和计费。恢复任务将查询原任务，不重新提交。")
        row.shot_runs = [{**shot, "status": "cancelled"} if shot["status"] in ACTIVE else shot for shot in row.shot_runs]
        if (row.request_data or {}).get("scope") != "shot-preview":
            session.get(ProjectRow, row.project_id).status = "needs_attention"
        session.commit()
        if (row.request_data or {}).get("blender") and not worker_has_run(row.id):
            submit_run(row.id)
        return generation_run(row)


@router.post("/generation-runs/{run_id}/shots/{shot_id}/retries", status_code=202)
def retry_shot(run_id: str, shot_id: str, confirm_video_cost: bool = Query(False, alias="confirmVideoCost"), session: Session = Depends(get_session)) -> dict:
    return _resume_generation(session, run_id, shot_id, confirm_video_cost)


@router.post("/generation-runs/{run_id}/resumption", status_code=202)
def resume_generation(run_id: str, session: Session = Depends(get_session)) -> dict:
    return _resume_generation(session, run_id)


def _resume_generation(session, run_id, shot_id=None, confirm_video_cost=False):
    with generation_lock:
        row = session.get(GenerationRunRow, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Generation run not found")
        if not row.request_data:
            raise HTTPException(status_code=409, detail="旧测试任务不能重做，请从分镜创建素材任务")
        if worker_has_run(run_id):
            raise HTTPException(status_code=409, detail="后台操作正在收尾，请稍后恢复")
        if session.scalar(select(GenerationRunRow.id).where(GenerationRunRow.status.in_(ACTIVE))):
            raise HTTPException(status_code=409, detail="已有任务执行中")
        if live_blender_run(session, exclude=run_id):
            raise HTTPException(409, "另一个 Blender 进程仍在执行，请先恢复或停止它")
        if shot_id and not any(s["shotId"] == shot_id for s in row.shot_runs):
            raise HTTPException(status_code=404, detail="Shot run not found")
        if not shot_id and row.status == "completed":
            raise HTTPException(status_code=409, detail="已完成任务无需恢复")
        retries = []
        for shot in latest_shots(row):
            if shot["shotId"] != shot_id and shot["status"] == "succeeded":
                continue
            if shot["strategy"] == "blender-3d" and shot_id == shot["shotId"]:
                if matching_process(shot.get("blenderHandle")):
                    raise HTTPException(409, "原 Blender 进程仍在执行，请恢复或先停止，不重复渲染")
                shot = {key: value for key, value in shot.items() if key not in {"blenderHandle", "blenderStarted", "blenderDirectory", "renderedFrames", "totalFrames"}}
            if shot["strategy"] == "image-to-video" and row.request_data["video"].get("backend") == "comfyui":
                if not get_settings().allow_local_models:
                    raise HTTPException(422, "当前环境禁止本地模型访问")
                if shot_id == shot["shotId"]:
                    if shot.get("providerHandle"):
                        from .comfy_video import ComfyVideoClient
                        try:
                            state, _ = ComfyVideoClient(row.request_data["video"]["localUrl"]).status(shot["providerHandle"]["requestId"])
                        except VideoProviderError as error:
                            raise HTTPException(422, str(error)) from error
                        if state in {"RUNNING", "QUEUED"}:
                            raise HTTPException(409, "本地原任务仍在执行，请继续查询或先取消")
                    shot = {key: value for key, value in shot.items() if key not in {"providerHandle", "providerRequestId", "providerStatus", "submissionState", "seed", "elapsedSeconds"}}
            elif shot["strategy"] == "image-to-video":
                if shot.get("submissionState") in {"submitting", "unknown"} and not shot.get("providerHandle"):
                    raise HTTPException(409, "提交结果不明，请先在供应商后台核对，不允许自动重提")
                if shot_id == shot["shotId"] and shot.get("providerHandle") and shot.get("providerStatus") not in {"COMPLETED", "FAILED"}:
                    raise HTTPException(409, "上游任务尚未完成，请使用继续任务查询原结果")
                if shot_id == shot["shotId"] or shot.get("submissionState") == "rejected":
                    if not confirm_video_cost:
                        raise HTTPException(422, "重提视频镜头需再次确认费用，请点击该镜头重做")
                    video = row.request_data["video"]
                    source = next(s for s in row.request_data["shots"] if s["id"] == shot["shotId"])
                    reserved = Decimal(video["reservedUsd"]) + Decimal(source["durationMs"]) / 1000 * Decimal(video["estimatedUsdPerSecond"])
                    if reserved > Decimal(video["maxRunUsd"]):
                        raise HTTPException(422, "重做后累计估算超过该任务预算，未提交新请求")
                    row.request_data = {**row.request_data, "video": {**video, "reservedUsd": str(reserved)}}
                    shot = {key: value for key, value in shot.items() if key not in {"providerHandle", "providerRequestId", "providerStatus", "submissionState"}}
            retries.append({**shot, "id": str(uuid4()), "attempt": shot["attempt"] + 1, "status": "queued", "artifactId": None, "errorMessage": None})
        row.shot_runs = [*row.shot_runs, *retries]
        row.status = "queued"
        row.final_artifact_id = None
        row.error_message = None
        project_row = session.get(ProjectRow, row.project_id)
        if row.request_data.get("scope") != "shot-preview":
            project_row.active_generation_run_id = row.id
            project_row.status = "generating"
        session.commit()
        result = generation_run(row)
        submit_run(row.id)
        return result


@router.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(ArtifactRow, artifact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact(row)


@router.get("/artifacts/{artifact_id}/content", include_in_schema=False)
def get_artifact_content(artifact_id: str, download: bool = False, session: Session = Depends(get_session)) -> FileResponse:
    row = session.get(ArtifactRow, artifact_id)
    if not row or not Path(row.path).exists():
        raise HTTPException(status_code=404, detail="Artifact content not found")
    return FileResponse(row.path, media_type=row.mime_type, filename=f"vediogen-{artifact_id}.mp4" if download else None)


@router.post("/artifacts/{artifact_id}/download-grants", status_code=201)
def create_download_grant(artifact_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(ArtifactRow, artifact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"artifactId": artifact_id, "downloadUrl": f"/api/v1/artifacts/{artifact_id}/content?download=true", "expiresAt": "2099-01-01T00:00:00Z"}
