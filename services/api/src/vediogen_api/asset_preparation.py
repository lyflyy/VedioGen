"""Prepare reusable image references without modifying the original asset."""

import hashlib
import warnings
from math import floor
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session
from .fixtures import timestamp
from .models import ProjectRow
from .schemas import ApiModel

router = APIRouter()


class ImageCropInput(ApiModel):
    x: float = Field(ge=0, le=100, allow_inf_nan=False)
    y: float = Field(ge=0, le=100, allow_inf_nan=False)
    width: float = Field(gt=0, le=100, allow_inf_nan=False)
    height: float = Field(gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def within_image(self):
        if self.x + self.width > 100.000001 or self.y + self.height > 100.000001:
            raise ValueError("裁剪区域超出原图")
        return self


def crop_image(source: dict, crop: ImageCropInput, target: Path) -> dict:
    path = Path(source["uri"])
    if not path.is_file() or "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("原图丢失或已改变，请重新准备素材")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                raise ValueError("裁剪仅支持静态 JPEG、PNG、WebP 图片")
            if max(image.size) > 8192 or image.width * image.height > 24_000_000:
                raise ValueError("原图超过 8192 像素或 2400 万像素限制")
            # Match browsers' EXIF orientation before converting percentage coordinates.
            oriented = ImageOps.exif_transpose(image)
            # Match JavaScript Math.round at half-pixel boundaries as well.
            left = floor(oriented.width * crop.x / 100 + 0.5)
            top = floor(oriented.height * crop.y / 100 + 0.5)
            right = min(oriented.width, floor(oriented.width * (crop.x + crop.width) / 100 + 0.5))
            bottom = min(oriented.height, floor(oriented.height * (crop.y + crop.height) / 100 + 0.5))
            if right - left < 32 or bottom - top < 32:
                raise ValueError("裁剪结果宽高至少为 32 像素")
            result = oriented.crop((left, top, right, bottom)).convert("RGB")
            target.parent.mkdir(parents=True, exist_ok=True)
            result.save(target, format="PNG")
    return {"width": result.width, "height": result.height,
            "cropPixels": {"x": left, "y": top, "width": result.width, "height": result.height}}


@router.post("/projects/{project_id}/assets/{asset_id}/crops", status_code=201)
def create_crop(project_id: str, asset_id: str, payload: ImageCropInput, session: Session = Depends(get_session)):
    project = session.get(ProjectRow, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    source = next((asset for asset in project.asset_versions if asset["id"] == asset_id), None)
    if not source:
        raise HTTPException(404, "素材不属于本项目")
    if source.get("kind") != "image" or source.get("status") != "ready":
        raise HTTPException(422, "请选择已准备好的图片素材")
    new_id = str(uuid4())
    target = get_settings().data_dir / "assets" / project_id / f"{new_id}.png"
    try:
        metadata = crop_image(source, payload, target)
        asset = {"id": new_id, "assetId": str(uuid4()), "version": 1, "kind": "image",
                 "sourceType": "prepared-reference", "sourceAssetId": source["id"],
                 "fileName": f"{Path(source['fileName']).stem[:80]}-crop-{new_id[:8]}.png",
                 "mimeType": "image/png", "sizeBytes": target.stat().st_size,
                 "sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest(),
                 "uri": str(target.resolve()), "status": "ready", "createdAt": timestamp(),
                 "cropPercent": payload.model_dump(), **metadata,
                 **{key: source[key] for key in ("subject", "sourceUrl", "sourceImageUrl", "subjectConfirmedByUser") if key in source}}
        session.refresh(project)
        project.asset_versions = [*project.asset_versions, asset]
        project.row_version += 1
        session.commit()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        target.unlink(missing_ok=True)
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else "图片无法裁剪，请重新准备素材") from error
    return {key: value for key, value in asset.items() if key != "uri"} | {
        "previewUrl": f"/api/v1/projects/{project_id}/assets/{new_id}/content"}
