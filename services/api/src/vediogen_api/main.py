from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .admin import router as admin_router
from . import asset_discovery
from . import storyboard_jobs
from .asset_preparation import router as asset_preparation_router
from .video_settings import router as video_settings_router
from .admin import secret_store
from .config import get_settings
from .creator import router as creator_router
from .reference_cut import router as reference_cut_router
from .database import Base, SessionLocal, engine, ensure_runtime_schema
from .models import ModelCredentialRow, ModelDeploymentRow, ModelProviderRow, RoutingDraftRow, RoutingVersionRow


def seed_local_provider() -> None:
    if not get_settings().allow_fake_provider:
        return
    with SessionLocal() as session:
        if session.get(ModelProviderRow, "local-fake"):
            return
        credential_id = str(uuid4())
        deployment_id = str(uuid4())
        secret_ref = f"credential/{credential_id}"
        secret_store.put(secret_ref, "local-fake-key")
        provider = ModelProviderRow(
            id="local-fake",
            display_name="Local Fake Provider",
            adapter_type="fake",
            base_url="http://localhost:8000/fake",
            region="local",
            enabled=True,
            status="active",
        )
        credential = ModelCredentialRow(
            id=credential_id,
            provider_id=provider.id,
            alias="Local development",
            secret_ref=secret_ref,
            last_four="-key",
            status="active",
        )
        deployment = ModelDeploymentRow(
            id=deployment_id,
            display_name="Deterministic Creative Model",
            provider_id=provider.id,
            physical_model_id="fixture-v1",
            credential_id=credential_id,
            capabilities=["text", "streaming", "tools", "structured-output", "zh-CN"],
            timeout_seconds=30,
            max_context_tokens=32000,
            status="ready",
        )
        bindings = [
            {
                "capabilityAlias": alias,
                "requirements": ["text", "structured-output", "zh-CN"],
                "primaryDeploymentId": deployment_id,
                "fallbackDeploymentIds": [],
                "timeoutSeconds": 60,
                "maxAttempts": 2,
                "budgetClass": "low",
                "fallbackOn": ["TIMEOUT", "PROVIDER_UNAVAILABLE", "SCHEMA_INVALID"],
            }
            for alias in ("creative-advisor", "storyboard-generator")
        ]
        draft = RoutingDraftRow(id=str(uuid4()), bindings=bindings, status="ready")
        version = RoutingVersionRow(id=str(uuid4()), version=1, bindings=bindings, status="published", change_note="P0 deterministic default")
        session.add_all([provider, credential, deployment, draft, version])
        session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    ensure_runtime_schema()
    from .model_backoff import recover_interrupted_calls
    with SessionLocal() as session:
        recover_interrupted_calls(session)
    seed_local_provider()
    from .generation import start_worker, stop_worker
    start_worker()
    asset_discovery.start_worker()
    storyboard_jobs.start_worker()
    try:
        yield
    finally:
        storyboard_jobs.stop_worker()
        asset_discovery.stop_worker()
        stop_worker()


app = FastAPI(title="VedioGen Control API", version="0.1.0", lifespan=lifespan)
app.include_router(storyboard_jobs.router, prefix="/api/v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(creator_router, prefix="/api/v1")
app.include_router(reference_cut_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(asset_discovery.router, prefix="/api/v1")
app.include_router(asset_preparation_router, prefix="/api/v1")
app.include_router(video_settings_router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["Health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
