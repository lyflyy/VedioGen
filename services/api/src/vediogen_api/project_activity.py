"""Project-scoped activity assembled from persisted execution records, not model thoughts."""
from sqlalchemy import select

from .models import AssetDiscoveryRow, ArtifactRow, DocumentRow, GenerationRunRow, ModelDeploymentRow, ModelInvocationRow, ModelProviderRow
from .openai_compatible import safe_error_text
from .serializers import iso


def activity(session, project):
    items = []
    def add(id, at, category, title, status, detail="", **fields):
        items.append({"id": id, "at": at, "category": category, "title": title, "status": status,
            "detail": safe_error_text(detail), **fields})
    for call in session.scalars(select(ModelInvocationRow).where(ModelInvocationRow.project_id == project.id)):
        deployment = session.get(ModelDeploymentRow, call.deployment_id)
        provider = session.get(ModelProviderRow, deployment.provider_id) if deployment else None
        add(call.id, iso(call.started_at), "model", call.capability_alias, call.status,
            call.redacted_output or "请求已提交，等待模型响应", model=call.provider_model_id or (deployment.physical_model_id if deployment else None),
            provider=provider.display_name if provider else None, requestId=call.provider_request_id,
            modelSource="调用记录" if call.provider_model_id else "当前部署配置（历史调用未记录模型快照）",
            errorCode=call.error_code, durationMs=call.duration_ms,
            inputTokens=call.input_tokens if call.status == "succeeded" else None,
            outputTokens=call.output_tokens if call.status == "succeeded" else None)
    for board in session.scalars(select(DocumentRow).where(DocumentRow.project_id == project.id, DocumentRow.kind == "storyboard")):
        add(board.id, iso(board.created_at), "output", "脚本文案", board.status,
            f"{board.data.get('title', '')}\n{len(board.data.get('shots', []))} 个镜头 · {board.data.get('totalDurationMs', 0) / 1000} 秒",
            previewUrl=f"/projects/{project.id}/storyboard",
            script=[{"order": shot.get("order"), "visual": safe_error_text(shot.get("visual") or ""),
                "caption": safe_error_text(shot.get("caption") or ""), "voiceover": safe_error_text(shot.get("voiceover") or ""),
                "strategy": shot.get("sourceStrategy"), "sourceAssetId": shot.get("sourceAssetId")} for shot in board.data.get("shots", [])],
            timestampKind="脚本文档创建时间；展开内容为该文档当前保存内容，不是逐次编辑历史")
    for run in session.scalars(select(DocumentRow).where(DocumentRow.project_id == project.id,
            DocumentRow.kind.in_(["storyboard-run", "material-run"]))):
        events = run.data.get("events") or [{"phase": run.data.get("phase", run.kind), "at": iso(run.created_at)}]
        for index, event in enumerate(events):
            last = index == len(events) - 1
            add(f"{run.id}:{index}", event["at"], "preparation", event["phase"], run.status if last else "completed",
                run.data.get("errorMessage") or "\n".join(run.data.get("warnings", [])) if last else "", runId=run.id)
    for run in session.scalars(select(AssetDiscoveryRow).where(AssetDiscoveryRow.project_id == project.id)):
        add(run.id, iso(run.created_at), "preparation", "素材检索", run.status, run.error_message or "检索任务记录", runId=run.id)
    for asset in project.asset_versions:
        add(asset["id"], asset.get("createdAt", iso(project.created_at)), "asset", asset.get("fileName", "素材"), asset.get("status", "ready"),
            "\n".join(str(asset.get(k) or "") for k in ("subject", "referenceContext")),
            sourceType=asset.get("sourceType"), sourceUrl=safe_error_text(asset.get("sourceUrl") or ""),
            previewUrl=f"/api/v1/projects/{project.id}/assets/{asset['id']}/content", reusedFromProjectId=asset.get("reusedFromProjectId"))
    for run in session.scalars(select(GenerationRunRow).where(GenerationRunRow.project_id == project.id)):
        request = run.request_data or {}
        video = request.get("video") or {}
        add(run.id, iso(run.created_at), "video", "整片合成" if request.get("scope") != "shot-preview" else "单镜头试片", run.status,
            run.error_message or f"执行方式：{request.get('mode', '历史未记录')}\n声音方案：{request.get('audioMode', '历史未记录')}", runId=run.id,
            model=video.get("physicalModelId"), provider=video.get("backend") or "本地 FFmpeg / Blender")
        for shot in run.shot_runs:
            snapshot = next((s for s in request.get("shots", []) if s.get("id") == shot.get("shotId")), {})
            add(shot["id"], iso(run.updated_at), "video", shot.get("purpose") or "镜头制作", shot["status"],
                shot.get("errorMessage") or "", runId=run.id, strategy=shot.get("strategy"), attempt=shot.get("attempt"),
                prompt=safe_error_text(snapshot.get("videoPrompt") or snapshot.get("visual") or ""),
                caption=safe_error_text(snapshot.get("caption") or ""), seed=shot.get("seed"), decodeMode=shot.get("decodeMode"),
                requestId=shot.get("providerRequestId"), sourceAssetId=shot.get("sourceAssetId"),
                nativeWidth=shot.get("nativeWidth"), nativeHeight=shot.get("nativeHeight"), elapsedSeconds=shot.get("elapsedSeconds"),
                timestampKind="任务最后更新时间（非镜头精确时间）")
    for artifact in session.scalars(select(ArtifactRow).where(ArtifactRow.project_id == project.id)):
        add(artifact.id, iso(artifact.created_at), "output", artifact.type, artifact.status,
            f"{artifact.mime_type} · {artifact.size_bytes} bytes", previewUrl=f"/api/v1/artifacts/{artifact.id}/content", runId=artifact.generation_run_id)
    return sorted(items, key=lambda item: (item["at"], item["id"]), reverse=True)
