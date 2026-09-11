from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now() -> datetime:
    return datetime.now(UTC)


class AccountBriefRow(Base):
    __tablename__ = "account_briefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    content_pack_id: Mapped[str] = mapped_column(String(100), default="motorcycle")
    content_pack_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    mode: Mapped[str] = mapped_column(String(30), default="real-subject")
    target_platform: Mapped[str] = mapped_column(String(30), default="douyin")
    locale: Mapped[str] = mapped_column(String(20), default="zh-CN")
    status: Mapped[str] = mapped_column(String(40), default="intake")
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    asset_versions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    latest_advisor_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_brief_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_storyboard_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active_generation_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AdvisorRunRow(Base):
    __tablename__ = "advisor_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GenerationRunRow(Base):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    storyboard_version_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    routing_policy_version_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    shot_runs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    final_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cost_cny: Mapped[str] = mapped_column(String(20), default="0.0000")
    request_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    generation_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    shot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="ready")
    mime_type: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(80))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelProviderRow(Base):
    __tablename__ = "model_providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    adapter_type: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(String(500))
    region: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class VideoSettingsRow(Base):
    __tablename__ = "video_settings"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class AssetDiscoveryRow(Base):
    __tablename__ = "asset_discoveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    request_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelCredentialRow(Base):
    __tablename__ = "model_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("model_providers.id"), index=True)
    alias: Mapped[str] = mapped_column(String(100))
    secret_ref: Mapped[str] = mapped_column(String(100), unique=True)
    last_four: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(30), default="active")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelCooldownRow(Base):
    __tablename__ = "model_cooldowns"

    credential_id: Mapped[str] = mapped_column(ForeignKey("model_credentials.id"), primary_key=True)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str] = mapped_column(String(40))


class ModelDeploymentRow(Base):
    __tablename__ = "model_deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    provider_id: Mapped[str] = mapped_column(ForeignKey("model_providers.id"), index=True)
    physical_model_id: Mapped[str] = mapped_column(String(200))
    credential_id: Mapped[str] = mapped_column(ForeignKey("model_credentials.id"))
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    max_context_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class RoutingDraftRow(Base):
    __tablename__ = "routing_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    bindings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class RoutingVersionRow(Base):
    __tablename__ = "routing_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    bindings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="published")
    change_note: Mapped[str] = mapped_column(String(500))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelInvocationRow(Base):
    __tablename__ = "model_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    generation_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    capability_alias: Mapped[str] = mapped_column(String(64), index=True)
    routing_policy_version_id: Mapped[str] = mapped_column(String(36))
    deployment_id: Mapped[str] = mapped_column(String(36))
    credential_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(30))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_cny: Mapped[str] = mapped_column(String(20), default="0.0000")
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_invocation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    redacted_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    redacted_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
