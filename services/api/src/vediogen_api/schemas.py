from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class AccountBriefInput(ApiModel):
    content_pack_id: str = "motorcycle"
    account_goal: str = "建立有辨识度的摩托车日更账号"
    audience: list[str] = Field(default_factory=lambda: ["摩托车爱好者", "潜在购车用户"])
    tone: list[str] = Field(default_factory=lambda: ["专业", "有冲击力", "不浮夸"])
    publishing_cadence: Literal["daily", "weekdays", "weekly", "custom"] = "daily"
    preferences: dict[str, Any] = Field(default_factory=lambda: {"durationSeconds": 24, "voiceover": True})
    row_version: int | None = None


class CreateProjectRequest(ApiModel):
    title: str = Field(min_length=1, max_length=120)
    content_pack_id: str = "motorcycle"
    mode: Literal["real-subject", "concept"] = "real-subject"
    target_platform: Literal["douyin", "other"] = "douyin"
    locale: str = "zh-CN"
    initial_message: str = Field(min_length=1, max_length=10_000)
    asset_version_ids: list[str] = Field(default_factory=list)


class MessageRequest(ApiModel):
    text: str = Field(min_length=1, max_length=10_000)
    asset_version_ids: list[str] = Field(default_factory=list)


class CreateBriefRequest(ApiModel):
    proposal_key: str
    advisor_run_id: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(ApiModel):
    comment: str | None = Field(default=None, max_length=1000)


class StoryboardUpdate(ApiModel):
    shots: list[dict[str, Any]]
    total_duration_ms: int


class GenerationRequest(ApiModel):
    project_id: str
    storyboard_version_id: str
    shot_id: str | None = Field(default=None, min_length=1)
    audio_asset_id: str | None = None
    narration: bool = False
    quality: Literal["preview", "standard"] = "standard"
    confirm_video_cost: bool = False


class AssetUploadIntentInput(ApiModel):
    project_id: str
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(pattern=r"^(?:(?:image|video|audio)/.+|model/gltf-binary)$")
    size_bytes: int = Field(ge=1, le=50 * 1024 * 1024)
    sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class RetryShotRequest(ApiModel):
    strategy: str | None = None


class ProviderInput(ApiModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    display_name: str
    adapter_type: str
    base_url: str
    region: str = "global"
    enabled: bool = True


class CredentialInput(ApiModel):
    provider_id: str
    alias: str
    secret: str = Field(min_length=1)


class DeploymentInput(ApiModel):
    display_name: str
    provider_id: str
    physical_model_id: str
    credential_id: str
    capabilities: list[str]
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    max_context_tokens: int | None = Field(default=None, ge=1)


class RoutingInput(ApiModel):
    bindings: list[dict[str, Any]]


class ChangeNote(ApiModel):
    change_note: str = Field(min_length=1, max_length=500)


class PlaygroundRunInput(ApiModel):
    capability_alias: str
    route_target: Literal["draft", "published"]
    fixture_id: str
    routing_draft_id: str | None = None
    checks: list[str] = Field(default_factory=lambda: ["authentication", "structured-output", "zh-CN"])
