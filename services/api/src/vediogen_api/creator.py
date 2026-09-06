import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal, get_session
from .fixtures import build_brief, build_project_facts, build_storyboard, timestamp
from .gateway import ModelGatewayError, generate_creative_advice, generate_storyboard
from .media import MediaGenerationError, create_preview_video
from .models import AccountBriefRow, AdvisorRunRow, ArtifactRow, DocumentRow, GenerationRunRow, ModelDeploymentRow, ModelProviderRow, ProjectRow, RoutingVersionRow
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
    if not row:
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
    session: Session = Depends(get_session),
) -> dict:
    statement = select(ProjectRow).order_by(ProjectRow.updated_at.desc()).limit(page_size)
    if status:
        statement = statement.where(ProjectRow.status == status)
    if query:
        statement = statement.where(func.lower(ProjectRow.title).contains(query.lower()))
    return {"items": [project(row) for row in session.scalars(statement)] , "nextCursor": None}


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
        facts=build_project_facts(project_id, payload.title, payload.initial_message),
    )
    session.add(row)
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
        "assetVersions": row.asset_versions,
        "latestAdvisorRunId": row.latest_advisor_run_id,
        "activeGenerationRunId": row.active_generation_run_id,
        "generationReadiness": generation_readiness(session),
    }


def generation_readiness(session: Session) -> dict:
    route = session.scalar(select(RoutingVersionRow).where(RoutingVersionRow.status == "published").order_by(RoutingVersionRow.version.desc()))
    if not route:
        return {"ready": False, "mode": "unavailable", "reason": "没有已发布的模型路由。"}
    creative = next((item for item in route.bindings if item.get("capabilityAlias") == "creative-advisor"), None)
    creative_deployment = session.get(ModelDeploymentRow, creative.get("primaryDeploymentId")) if creative else None
    creative_provider = session.get(ModelProviderRow, creative_deployment.provider_id) if creative_deployment else None
    if creative_provider and creative_provider.adapter_type == "fake":
        return {"ready": True, "mode": "deterministic-test-preview", "reason": None}
    video = next((item for item in route.bindings if item.get("capabilityAlias") == "video-generation"), None)
    if not video:
        return {"ready": False, "mode": "missing-video-provider", "reason": "脚本分镜已就绪，但尚未配置视频生成模型，不能生成真实动态镜头。"}
    return {"ready": False, "mode": "video-adapter-pending", "reason": "视频模型路由已配置，但对应生成适配器尚未实现。"}


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
    row = get_project_or_404(session, project_id)
    run_id = str(uuid4())
    try:
        result = generate_creative_advice(session, row)
    except ModelGatewayError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    run = AdvisorRunRow(id=run_id, project_id=project_id, result=result, status="completed")
    row.latest_advisor_run_id = run_id
    row.status = "advising"
    session.add(run)
    session.commit()
    return advisor_run(run)


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
def create_storyboard(project_id: str, session: Session = Depends(get_session)) -> dict:
    project_row = get_project_or_404(session, project_id)
    if not project_row.current_brief_version_id:
        raise HTTPException(status_code=409, detail="Approve a brief before generating a storyboard")
    version = (session.scalar(select(func.count()).select_from(DocumentRow).where(DocumentRow.project_id == project_id, DocumentRow.kind == "storyboard")) or 0) + 1
    brief = get_document_or_404(session, project_row.current_brief_version_id, "brief", project_id)
    try:
        storyboard_data = generate_storyboard(session, project_row, brief, version)
    except ModelGatewayError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
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
    get_project_or_404(session, project_id)
    row = get_document_or_404(session, storyboard_id, "storyboard", project_id)
    row.data = {**row.data, "shots": payload.shots, "totalDurationMs": payload.total_duration_ms}
    row.row_version += 1
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
    project_row = get_project_or_404(session, payload.project_id)
    storyboard = get_document_or_404(session, payload.storyboard_version_id, "storyboard", payload.project_id)
    if storyboard.status != "approved":
        raise HTTPException(status_code=409, detail="Approve the storyboard before generation")
    readiness = generation_readiness(session)
    if not readiness["ready"]:
        raise HTTPException(status_code=409, detail=readiness["reason"])
    route = session.scalar(select(RoutingVersionRow).where(RoutingVersionRow.status == "published").order_by(RoutingVersionRow.version.desc()))
    route_id = route.id if route else "00000000-0000-0000-0000-000000000001"
    run_id = str(uuid4())
    run = GenerationRunRow(
        id=run_id,
        project_id=payload.project_id,
        storyboard_version_id=storyboard.id,
        routing_policy_version_id=route_id,
        status="running",
        shot_runs=[
            {
                "id": str(uuid4()),
                "generationRunId": run_id,
                "shotId": shot["id"],
                "attempt": 1,
                "strategy": shot.get("sourceStrategy", "image-motion"),
                "status": "succeeded",
            }
            for shot in storyboard.data["shots"]
        ],
    )
    project_row.status = "generating"
    project_row.active_generation_run_id = run_id
    session.add(run)
    session.flush()

    artifact_id = str(uuid4())
    target = get_settings().data_dir / "artifacts" / f"{artifact_id}.mp4"
    try:
        metadata = create_preview_video(target)
    except MediaGenerationError as error:
        run.status = "failed"
        project_row.status = "needs_attention"
        session.commit()
        raise HTTPException(status_code=502, detail=str(error)) from error
    artifact_row = ArtifactRow(
        id=artifact_id,
        project_id=payload.project_id,
        generation_run_id=run_id,
        type="final-video",
        mime_type="video/mp4",
        path=str(target.resolve()),
        **{
            "size_bytes": metadata["sizeBytes"],
            "sha256": metadata["sha256"],
            "width": metadata["width"],
            "height": metadata["height"],
            "duration_ms": metadata["durationMs"],
        },
    )
    run.final_artifact_id = artifact_id
    run.status = "completed"
    run.cost_cny = "0.0180"
    project_row.status = "completed"
    session.add(artifact_row)
    session.commit()
    return generation_run(run)


@router.get("/generation-runs/{run_id}")
def get_generation(run_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(GenerationRunRow, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return generation_run(row)


@router.post("/generation-runs/{run_id}/cancellation", status_code=202)
def cancel_generation(run_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(GenerationRunRow, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Generation run not found")
    if row.status == "completed":
        raise HTTPException(status_code=409, detail="Completed runs cannot be cancelled")
    row.status = "cancelled"
    session.commit()
    return generation_run(row)


@router.post("/generation-runs/{run_id}/shots/{shot_id}/retries", status_code=202)
def retry_shot(run_id: str, shot_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(GenerationRunRow, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Generation run not found")
    current = next((shot for shot in row.shot_runs if shot["shotId"] == shot_id), None)
    if not current:
        raise HTTPException(status_code=404, detail="Shot run not found")
    retry = {**current, "id": str(uuid4()), "attempt": current["attempt"] + 1, "status": "succeeded"}
    row.shot_runs = [*row.shot_runs, retry]
    session.commit()
    return retry


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
