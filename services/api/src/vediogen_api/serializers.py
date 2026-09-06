from datetime import UTC, datetime

from . import models


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


def project(row: models.ProjectRow) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "contentPackId": row.content_pack_id,
        "contentPackVersion": row.content_pack_version,
        "mode": row.mode,
        "targetPlatform": row.target_platform,
        "locale": row.locale,
        "status": row.status,
        "currentBriefVersionId": row.current_brief_version_id,
        "currentStoryboardVersionId": row.current_storyboard_version_id,
        "rowVersion": row.row_version,
        "createdAt": iso(row.created_at),
        "updatedAt": iso(row.updated_at),
    }


def account_brief(row: models.AccountBriefRow) -> dict:
    return {
        "id": row.id,
        **row.data,
        "version": row.version,
        "rowVersion": row.row_version,
        "createdAt": iso(row.created_at),
        "updatedAt": iso(row.updated_at),
    }


def document(row: models.DocumentRow) -> dict:
    return {
        "id": row.id,
        **row.data,
        "version": row.version,
        "status": row.status,
        "rowVersion": row.row_version,
        "createdAt": iso(row.created_at),
    }


def advisor_run(row: models.AdvisorRunRow) -> dict:
    return {
        "id": row.id,
        "projectId": row.project_id,
        "status": row.status,
        "degraded": row.degraded,
        "result": row.result,
        "createdAt": iso(row.created_at),
    }


def generation_run(row: models.GenerationRunRow) -> dict:
    return {
        "id": row.id,
        "projectId": row.project_id,
        "storyboardVersionId": row.storyboard_version_id,
        "routingPolicyVersionId": row.routing_policy_version_id,
        "status": row.status,
        "shotRuns": row.shot_runs,
        "finalArtifactId": row.final_artifact_id,
        "costCny": row.cost_cny,
        "createdAt": iso(row.created_at),
        "updatedAt": iso(row.updated_at),
    }


def artifact(row: models.ArtifactRow) -> dict:
    return {
        "id": row.id,
        "projectId": row.project_id,
        "generationRunId": row.generation_run_id,
        "shotId": row.shot_id,
        "type": row.type,
        "status": row.status,
        "mimeType": row.mime_type,
        "sizeBytes": row.size_bytes,
        "sha256": row.sha256,
        "width": row.width,
        "height": row.height,
        "durationMs": row.duration_ms,
        "previewUrl": f"/api/v1/artifacts/{row.id}/content",
        "createdAt": iso(row.created_at),
    }


def provider(row: models.ModelProviderRow) -> dict:
    return {
        "id": row.id,
        "displayName": row.display_name,
        "adapterType": row.adapter_type,
        "baseUrl": row.base_url,
        "region": row.region,
        "enabled": row.enabled,
        "status": row.status,
        "rowVersion": row.row_version,
        "createdAt": iso(row.created_at),
        "updatedAt": iso(row.updated_at),
    }


def credential(row: models.ModelCredentialRow) -> dict:
    return {
        "id": row.id,
        "providerId": row.provider_id,
        "alias": row.alias,
        "lastFour": row.last_four,
        "status": row.status,
        "lastSuccessAt": iso(row.last_success_at),
        "createdAt": iso(row.created_at),
    }


def deployment(row: models.ModelDeploymentRow) -> dict:
    return {
        "id": row.id,
        "displayName": row.display_name,
        "providerId": row.provider_id,
        "physicalModelId": row.physical_model_id,
        "credentialId": row.credential_id,
        "capabilities": row.capabilities,
        "timeoutSeconds": row.timeout_seconds,
        "maxContextTokens": row.max_context_tokens,
        "status": row.status,
        "rowVersion": row.row_version,
        "createdAt": iso(row.created_at),
        "updatedAt": iso(row.updated_at),
    }


def routing_draft(row: models.RoutingDraftRow) -> dict:
    return {
        "id": row.id,
        "bindings": row.bindings,
        "status": row.status,
        "rowVersion": row.row_version,
        "createdAt": iso(row.created_at),
        "updatedAt": iso(row.updated_at),
    }


def routing_version(row: models.RoutingVersionRow) -> dict:
    return {
        "id": row.id,
        "version": row.version,
        "bindings": row.bindings,
        "status": row.status,
        "changeNote": row.change_note,
        "publishedAt": iso(row.published_at),
    }


def invocation(row: models.ModelInvocationRow, detail: bool = False) -> dict:
    value = {
        "id": row.id,
        "projectId": row.project_id,
        "generationRunId": row.generation_run_id,
        "capabilityAlias": row.capability_alias,
        "routingPolicyVersionId": row.routing_policy_version_id,
        "deploymentId": row.deployment_id,
        "credentialId": row.credential_id,
        "status": row.status,
        "inputTokens": row.input_tokens,
        "outputTokens": row.output_tokens,
        "durationMs": row.duration_ms,
        "costCny": row.cost_cny,
        "errorCode": row.error_code,
        "parentInvocationId": row.parent_invocation_id,
        "providerModelId": row.provider_model_id,
        "startedAt": iso(row.started_at),
    }
    if detail:
        value.update(
            {
                "redactedInput": row.redacted_input,
                "redactedOutput": row.redacted_output,
                "routeChain": [value.copy()],
                "traceId": f"trace-{row.id[:8]}",
                "providerRequestId": row.provider_request_id,
            }
        )
    return value
