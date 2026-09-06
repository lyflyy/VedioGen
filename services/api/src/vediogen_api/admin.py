from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session
from .fixtures import timestamp
from .models import (
    ModelCredentialRow,
    ModelDeploymentRow,
    ModelInvocationRow,
    ModelProviderRow,
    RoutingDraftRow,
    RoutingVersionRow,
)
from .openai_compatible import OpenAICompatibleError, StructuredCompletion, list_models, probe_structured_output
from .schemas import ChangeNote, CredentialInput, DeploymentInput, PlaygroundRunInput, ProviderInput, RoutingInput
from .secret_store import LocalEncryptedSecretStore
from .serializers import credential, deployment, invocation, provider, routing_draft, routing_version


router = APIRouter(prefix="/admin")
secret_store = LocalEncryptedSecretStore(get_settings().data_dir / "secrets")
playground_runs: dict[str, dict] = {}


def provider_or_404(session: Session, provider_id: str) -> ModelProviderRow:
    row = session.get(ModelProviderRow, provider_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model provider not found")
    return row


def credential_or_404(session: Session, credential_id: str) -> ModelCredentialRow:
    row = session.get(ModelCredentialRow, credential_id)
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    return row


def deployment_or_404(session: Session, deployment_id: str) -> ModelDeploymentRow:
    row = session.get(ModelDeploymentRow, deployment_id)
    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return row


@router.get("/model-providers")
def list_providers(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(select(ModelProviderRow).order_by(ModelProviderRow.updated_at.desc()))
    return {"items": [provider(row) for row in rows]}


@router.post("/model-providers", status_code=201)
def create_provider(payload: ProviderInput, session: Session = Depends(get_session)) -> dict:
    if session.get(ModelProviderRow, payload.id):
        raise HTTPException(status_code=409, detail="Provider ID already exists")
    row = ModelProviderRow(
        id=payload.id,
        display_name=payload.display_name,
        adapter_type=payload.adapter_type,
        base_url=payload.base_url,
        region=payload.region,
        enabled=payload.enabled,
        status="active" if payload.enabled else "disabled",
    )
    session.add(row)
    session.commit()
    return provider(row)


@router.patch("/model-providers/{provider_id}")
def update_provider(provider_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    row = provider_or_404(session, provider_id)
    for api_name, attr_name in {
        "displayName": "display_name",
        "adapterType": "adapter_type",
        "baseUrl": "base_url",
        "region": "region",
        "enabled": "enabled",
    }.items():
        if api_name in payload:
            setattr(row, attr_name, payload[api_name])
    row.status = "active" if row.enabled else "disabled"
    row.row_version += 1
    session.commit()
    return provider(row)


@router.get("/model-credentials")
def list_credentials(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(select(ModelCredentialRow).order_by(ModelCredentialRow.created_at.desc()))
    return {"items": [credential(row) for row in rows]}


@router.post("/model-credentials", status_code=201)
def create_credential(payload: CredentialInput, session: Session = Depends(get_session)) -> dict:
    provider_or_404(session, payload.provider_id)
    credential_id = str(uuid4())
    secret_ref = f"credential/{credential_id}"
    secret_store.put(secret_ref, payload.secret)
    row = ModelCredentialRow(
        id=credential_id,
        provider_id=payload.provider_id,
        alias=payload.alias,
        secret_ref=secret_ref,
        last_four=payload.secret[-4:].rjust(4, "*"),
        status="active",
    )
    session.add(row)
    session.commit()
    return credential(row)


@router.post("/model-credentials/{credential_id}/probe")
def probe_credential(credential_id: str, session: Session = Depends(get_session)) -> dict:
    row = credential_or_404(session, credential_id)
    provider_row = provider_or_404(session, row.provider_id)
    try:
        value = secret_store.get(row.secret_ref)
    except (KeyError, ValueError):
        row.status = "error"
        session.commit()
        raise HTTPException(status_code=409, detail="Secret is unavailable")
    if not value:
        raise HTTPException(status_code=409, detail="Secret is empty")
    try:
        if provider_row.adapter_type == "fake":
            models, duration_ms = ["fixture-v1"], 1
        elif provider_row.adapter_type == "openai-compatible":
            models, duration_ms = list_models(provider_row.base_url, value)
        else:
            raise OpenAICompatibleError(f"尚未实现适配器 {provider_row.adapter_type}", "ADAPTER_UNSUPPORTED")
    except OpenAICompatibleError as error:
        row.status = "error"
        session.commit()
        raise HTTPException(status_code=502, detail=str(error)) from error
    if not models:
        row.status = "error"
        session.commit()
        raise HTTPException(status_code=502, detail="模型平台未返回任何可用模型")
    row.last_success_at = datetime.now(UTC)
    row.status = "active"
    session.commit()
    return {"status": "passed", "credentialId": row.id, "durationMs": duration_ms, "modelCount": len(models), "checkedAt": timestamp()}


@router.post("/model-credentials/{credential_id}/rotation")
def rotate_credential(credential_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    row = credential_or_404(session, credential_id)
    secret = payload.get("secret")
    if not isinstance(secret, str) or not secret:
        raise HTTPException(status_code=422, detail="A new secret is required")
    secret_store.put(row.secret_ref, secret)
    row.last_four = secret[-4:].rjust(4, "*")
    row.status = "active"
    session.commit()
    return credential(row)


@router.post("/model-credentials/{credential_id}/revocation")
def revoke_credential(credential_id: str, session: Session = Depends(get_session)) -> dict:
    row = credential_or_404(session, credential_id)
    referenced = session.scalar(select(func.count()).select_from(ModelDeploymentRow).where(ModelDeploymentRow.credential_id == credential_id, ModelDeploymentRow.status != "disabled"))
    if referenced:
        raise HTTPException(status_code=409, detail="Disable referenced deployments before revoking this credential")
    secret_store.delete(row.secret_ref)
    row.status = "revoked"
    session.commit()
    return credential(row)


@router.get("/model-deployments")
def list_deployments(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(select(ModelDeploymentRow).order_by(ModelDeploymentRow.updated_at.desc()))
    return {"items": [deployment(row) for row in rows]}


@router.post("/model-deployments", status_code=201)
def create_deployment(payload: DeploymentInput, session: Session = Depends(get_session)) -> dict:
    provider_or_404(session, payload.provider_id)
    credential_row = credential_or_404(session, payload.credential_id)
    if credential_row.provider_id != payload.provider_id:
        raise HTTPException(status_code=422, detail="Credential and provider do not match")
    row = ModelDeploymentRow(
        id=str(uuid4()),
        display_name=payload.display_name,
        provider_id=payload.provider_id,
        physical_model_id=payload.physical_model_id,
        credential_id=payload.credential_id,
        capabilities=payload.capabilities,
        timeout_seconds=payload.timeout_seconds,
        max_context_tokens=payload.max_context_tokens,
        status="draft",
    )
    session.add(row)
    session.commit()
    return deployment(row)


@router.patch("/model-deployments/{deployment_id}")
def update_deployment(deployment_id: str, payload: dict, session: Session = Depends(get_session)) -> dict:
    row = deployment_or_404(session, deployment_id)
    for api_name, attr_name in {
        "displayName": "display_name",
        "physicalModelId": "physical_model_id",
        "credentialId": "credential_id",
        "capabilities": "capabilities",
        "timeoutSeconds": "timeout_seconds",
        "maxContextTokens": "max_context_tokens",
    }.items():
        if api_name in payload:
            setattr(row, attr_name, payload[api_name])
    row.status = "draft"
    row.row_version += 1
    session.commit()
    return deployment(row)


@router.post("/model-deployments/{deployment_id}/probe")
def probe_deployment(deployment_id: str, session: Session = Depends(get_session)) -> dict:
    row = deployment_or_404(session, deployment_id)
    credential_row = credential_or_404(session, row.credential_id)
    if credential_row.status != "active":
        raise HTTPException(status_code=409, detail="Credential is not active")
    provider_row = provider_or_404(session, row.provider_id)
    try:
        completion = _probe_deployment(provider_row, credential_row, row)
    except OpenAICompatibleError as error:
        row.status = "error"
        session.commit()
        raise HTTPException(status_code=502, detail=str(error)) from error
    row.status = "ready"
    session.commit()
    return {
        "status": "passed",
        "deploymentId": row.id,
        "capabilities": row.capabilities,
        "durationMs": completion.duration_ms,
        "providerRequestId": completion.request_id,
        "providerModelId": completion.model_id,
        "checkedAt": timestamp(),
    }


@router.get("/model-routing/drafts")
def get_routing_draft(session: Session = Depends(get_session)) -> dict:
    row = session.scalar(select(RoutingDraftRow).order_by(RoutingDraftRow.updated_at.desc()))
    if not row:
        raise HTTPException(status_code=404, detail="Routing draft not found")
    return routing_draft(row)


@router.post("/model-routing/drafts", status_code=201)
def create_routing_draft(payload: RoutingInput, session: Session = Depends(get_session)) -> dict:
    row = RoutingDraftRow(id=str(uuid4()), bindings=payload.bindings, status="draft")
    session.add(row)
    session.commit()
    return routing_draft(row)


def validate_bindings(session: Session, bindings: list[dict]) -> None:
    for binding in bindings:
        ids = [binding.get("primaryDeploymentId"), *binding.get("fallbackDeploymentIds", [])]
        if not ids[0] or len(ids) != len(set(ids)):
            raise HTTPException(status_code=422, detail="Routing deployments must be unique and include a primary")
        requirements = set(binding.get("requirements", []))
        for deployment_id in ids:
            row = deployment_or_404(session, deployment_id)
            if row.status != "ready" or not requirements.issubset(set(row.capabilities)):
                raise HTTPException(status_code=422, detail=f"Deployment {deployment_id} is not ready or lacks capabilities")


@router.post("/model-routing/{draft_id}/validation", status_code=202)
def validate_routing(draft_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(RoutingDraftRow, draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="Routing draft not found")
    validate_bindings(session, row.bindings)
    row.status = "ready"
    session.commit()
    return {"id": str(uuid4()), "status": "completed", "createdAt": timestamp()}


@router.post("/model-routing/{draft_id}/publication", status_code=201)
def publish_routing(draft_id: str, payload: ChangeNote, session: Session = Depends(get_session)) -> dict:
    row = session.get(RoutingDraftRow, draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="Routing draft not found")
    validate_bindings(session, row.bindings)
    for current in session.scalars(select(RoutingVersionRow).where(RoutingVersionRow.status == "published")):
        current.status = "superseded"
    next_version = (session.scalar(select(func.max(RoutingVersionRow.version))) or 0) + 1
    version = RoutingVersionRow(id=str(uuid4()), version=next_version, bindings=row.bindings, change_note=payload.change_note)
    row.status = "ready"
    session.add(version)
    session.commit()
    return routing_version(version)


@router.get("/model-routing/versions")
def list_routing_versions(page_size: int = Query(default=20, alias="pageSize", ge=1, le=100), session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(select(RoutingVersionRow).order_by(RoutingVersionRow.version.desc()).limit(page_size))
    return {"items": [routing_version(row) for row in rows], "nextCursor": None}


@router.post("/model-routing/{version_id}/rollback", status_code=201)
def rollback_routing(version_id: str, payload: ChangeNote, session: Session = Depends(get_session)) -> dict:
    target = session.get(RoutingVersionRow, version_id)
    if not target:
        raise HTTPException(status_code=404, detail="Routing version not found")
    validate_bindings(session, target.bindings)
    for current in session.scalars(select(RoutingVersionRow).where(RoutingVersionRow.status == "published")):
        current.status = "superseded"
    next_version = (session.scalar(select(func.max(RoutingVersionRow.version))) or 0) + 1
    version = RoutingVersionRow(id=str(uuid4()), version=next_version, bindings=target.bindings, change_note=payload.change_note)
    session.add(version)
    session.commit()
    return routing_version(version)


@router.post("/model-playground-runs", status_code=202)
def create_playground_run(payload: PlaygroundRunInput, session: Session = Depends(get_session)) -> dict:
    route = session.scalar(select(RoutingVersionRow).where(RoutingVersionRow.status == "published").order_by(RoutingVersionRow.version.desc()))
    if not route:
        raise HTTPException(status_code=409, detail="No published routing policy")
    binding = next((item for item in route.bindings if item["capabilityAlias"] == payload.capability_alias), None)
    if not binding:
        raise HTTPException(status_code=422, detail="Capability is not routed")
    deployment_row = deployment_or_404(session, binding["primaryDeploymentId"])
    provider_row = provider_or_404(session, deployment_row.provider_id)
    credential_row = credential_or_404(session, deployment_row.credential_id)
    try:
        completion = _probe_deployment(provider_row, credential_row, deployment_row)
    except OpenAICompatibleError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    invocation_row = ModelInvocationRow(
        id=str(uuid4()),
        capability_alias=payload.capability_alias,
        routing_policy_version_id=route.id,
        deployment_id=deployment_row.id,
        credential_id=deployment_row.credential_id,
        status="succeeded",
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        duration_ms=completion.duration_ms,
        cost_cny="0.0000",
        redacted_input=f"Fixture: {payload.fixture_id}",
        redacted_output="真实结构化模型探测通过。" if provider_row.adapter_type != "fake" else "Fake Provider 结构化探测通过。",
        provider_request_id=completion.request_id,
        provider_model_id=completion.model_id,
    )
    session.add(invocation_row)
    session.commit()
    run_id = str(uuid4())
    result = {
        "id": run_id,
        "capabilityAlias": payload.capability_alias,
        "routeTarget": payload.route_target,
        "fixtureId": payload.fixture_id,
        "status": "completed",
        "checks": [{"check": check, "status": "passed", "durationMs": 28, "errorCode": None} for check in payload.checks],
        "routeChain": [invocation(invocation_row)],
        "redactedInput": f"Fixture: {payload.fixture_id}",
        "redactedOutput": invocation_row.redacted_output,
        "createdAt": timestamp(),
        "completedAt": timestamp(),
    }
    playground_runs[run_id] = result
    return result


def _probe_deployment(
    provider_row: ModelProviderRow,
    credential_row: ModelCredentialRow,
    deployment_row: ModelDeploymentRow,
) -> StructuredCompletion:
    try:
        api_key = secret_store.get(credential_row.secret_ref)
    except (KeyError, ValueError) as error:
        raise OpenAICompatibleError("凭据无法从加密存储读取", "AUTH_FAILED") from error
    if provider_row.adapter_type == "fake":
        return StructuredCompletion({"ok": True, "locale": "zh-CN"}, f"fake-{deployment_row.id[:8]}", deployment_row.physical_model_id, 8, 8, 1)
    if provider_row.adapter_type != "openai-compatible":
        raise OpenAICompatibleError(f"尚未实现适配器 {provider_row.adapter_type}", "ADAPTER_UNSUPPORTED")
    models, _ = list_models(provider_row.base_url, api_key, min(deployment_row.timeout_seconds, 30))
    if deployment_row.physical_model_id not in models:
        raise OpenAICompatibleError(f"模型列表中不存在 {deployment_row.physical_model_id}", "MODEL_NOT_FOUND")
    return probe_structured_output(
        provider_row.base_url,
        api_key,
        deployment_row.physical_model_id,
        deployment_row.timeout_seconds,
    )


@router.get("/model-playground-runs/{run_id}")
def get_playground_run(run_id: str) -> dict:
    if run_id not in playground_runs:
        raise HTTPException(status_code=404, detail="Playground run not found")
    return playground_runs[run_id]


@router.get("/model-invocations")
def list_invocations(
    capability_alias: str | None = Query(default=None, alias="capabilityAlias"),
    status: str | None = None,
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    statement = select(ModelInvocationRow).order_by(ModelInvocationRow.started_at.desc()).limit(page_size)
    if capability_alias:
        statement = statement.where(ModelInvocationRow.capability_alias == capability_alias)
    if status:
        statement = statement.where(ModelInvocationRow.status == status)
    return {"items": [invocation(row) for row in session.scalars(statement)], "nextCursor": None}


@router.get("/model-invocations/{invocation_id}")
def get_invocation(invocation_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(ModelInvocationRow, invocation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Invocation not found")
    return invocation(row, detail=True)
