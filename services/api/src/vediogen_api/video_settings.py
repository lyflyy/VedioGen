from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from .config import get_settings
from .comfy_video import ComfyVideoClient, local_url
from .database import get_session
from .fal_video import VideoProviderError, validate_configuration
from .models import ModelCredentialRow, ModelDeploymentRow, ModelProviderRow, VideoSettingsRow
from .schemas import ApiModel


router = APIRouter(prefix="/admin")


class VideoSettingsInput(ApiModel):
    enabled: bool = False
    backend: Literal["fal", "comfyui"] = "fal"
    local_url: str = "http://127.0.0.1:8188"
    width: int = Field(default=832, ge=256, le=832, multiple_of=32)
    height: int = Field(default=480, ge=256, le=832, multiple_of=32)
    steps: int = Field(default=20, ge=4, le=30)
    timeout_seconds: int = Field(default=3600, ge=300, le=7200)
    deployment_id: str | None = None
    estimated_usd_per_second: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=4)
    max_run_usd: Decimal = Field(default=Decimal("0"), ge=0, le=1000, decimal_places=4)
    narration_enabled: bool = False
    narration_model_path: str = Field(default="", max_length=1024)
    blender_enabled: bool = False
    blender_executable: str = Field(default="", max_length=1024)
    blender_timeout_seconds: int = Field(default=1800, ge=60, le=7200)

    @model_validator(mode="after")
    def validate_local(self):
        if self.width * self.height > 480 * 832:
            raise ValueError("本机实验分辨率最多 480 × 832 像素")
        if self.backend == "comfyui":
            try:
                local_url(self.local_url)
            except VideoProviderError as error:
                raise ValueError(str(error)) from error
        return self


def read_settings(session: Session) -> dict:
    row = session.get(VideoSettingsRow, "default")
    return VideoSettingsInput(**(row.data if row else {})).model_dump(mode="json", by_alias=True)


def resolve_deployment(session: Session, deployment_id: str):
    deployment = session.get(ModelDeploymentRow, deployment_id)
    provider = session.get(ModelProviderRow, deployment.provider_id) if deployment else None
    credential = session.get(ModelCredentialRow, deployment.credential_id) if deployment else None
    if (not deployment or deployment.status not in {"draft", "ready"} or not provider or not provider.enabled
            or provider.adapter_type != "fal-video" or not credential or credential.status != "active"
            or credential.provider_id != provider.id or "image-to-video" not in deployment.capabilities):
        raise VideoProviderError("请选择启用的 fal-video 平台、有效凭据和 image-to-video 部署")
    validate_configuration(provider.base_url, deployment.physical_model_id)
    return deployment, credential


def video_plan(session: Session, shots: list[dict]) -> dict:
    config = read_settings(session)
    if config["backend"] == "comfyui":
        if not config["enabled"] or not get_settings().allow_local_models:
            raise VideoProviderError("本地图生视频未启用，请在视频执行页配置 ComfyUI")
        if any(not 500 <= shot["durationMs"] <= 5000 for shot in shots):
            raise VideoProviderError("本地视频单镜头最长 5 秒，请缩短该镜头或拆为多个镜头；小数秒会自动适配")
        return {**config, "physicalModelId": "wan2.2-ti2v-5b-fp16", "estimatedUsd": None, "reservedUsd": None}
    if not config["enabled"] or not get_settings().allow_external_models:
        raise VideoProviderError("真实图生视频尚未启用，请先在管理后台配置视频执行与预算")
    if any(shot["durationMs"] not in (5000, 10000) for shot in shots):
        raise VideoProviderError("云端图生视频镜头需为 5 或 10 秒")
    deployment, credential = resolve_deployment(session, config["deploymentId"])
    cost = sum(Decimal(shot["durationMs"]) / 1000 for shot in shots) * Decimal(config["estimatedUsdPerSecond"])
    if cost > Decimal(config["maxRunUsd"]):
        raise VideoProviderError("本次视频生成估算超过单任务预算，请减少镜头或调整预算")
    return {**config, "physicalModelId": deployment.physical_model_id, "credentialId": credential.id,
            "estimatedUsd": str(cost), "reservedUsd": str(cost)}


@router.get("/video-settings")
def get_video_settings(session: Session = Depends(get_session)) -> dict:
    return {**read_settings(session), "externalCallsAllowed": get_settings().allow_external_models,
            "localCallsAllowed": get_settings().allow_local_models,
            "verification": "configuration-only"}


@router.put("/video-settings")
def save_video_settings(payload: VideoSettingsInput, session: Session = Depends(get_session)) -> dict:
    if payload.blender_enabled:
        from .blender import executable_path
        from .media import MediaGenerationError
        try:
            executable_path(payload.blender_executable)
        except MediaGenerationError as error:
            raise HTTPException(422, str(error)) from error
    if payload.narration_enabled:
        from .media import MediaGenerationError
        from .speech import voice_configuration
        try:
            voice_configuration(payload.narration_model_path)
        except MediaGenerationError as error:
            raise HTTPException(422, str(error)) from error
    if payload.enabled and payload.backend == "fal":
        if not payload.deployment_id or payload.estimated_usd_per_second <= 0 or payload.max_run_usd <= 0:
            raise HTTPException(422, "启用前需选择部署并填写参考单价与单任务预算")
        try:
            resolve_deployment(session, payload.deployment_id)
        except VideoProviderError as error:
            raise HTTPException(422, str(error)) from error
    row = session.get(VideoSettingsRow, "default") or VideoSettingsRow(id="default")
    row.data = payload.model_dump(mode="json", by_alias=True)
    session.add(row)
    session.commit()
    return get_video_settings(session)


@router.post("/video-settings/local-probe")
def probe_local_video(session: Session = Depends(get_session)) -> dict:
    if not get_settings().allow_local_models:
        raise HTTPException(422, "当前环境禁止本地模型访问")
    config = read_settings(session)
    try:
        return ComfyVideoClient(config["localUrl"]).probe()
    except VideoProviderError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/video-settings/blender-probe")
def check_blender(session: Session = Depends(get_session)) -> dict:
    from .blender import probe_blender
    from .media import MediaGenerationError
    try:
        return probe_blender(read_settings(session)["blenderExecutable"])
    except MediaGenerationError as error:
        raise HTTPException(422, str(error)) from error
