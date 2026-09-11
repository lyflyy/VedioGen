"""Bounded REST adapter for the documented fal Kling image-to-video endpoint."""

import base64
import hashlib
import re
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

import httpx

from .media import MediaGenerationError, probe_media


MODEL_ID = "fal-ai/kling-video/v2.1/standard/image-to-video"
BASE_URL = "https://queue.fal.run"
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


class VideoProviderError(MediaGenerationError):
    def __init__(self, message: str, code: str = "VIDEO_PROVIDER_ERROR"):
        super().__init__(message)
        self.code = code


def validate_configuration(base_url: str, model_id: str) -> None:
    if base_url.rstrip("/") != BASE_URL or model_id != MODEL_ID:
        raise VideoProviderError("当前 fal 适配器仅支持官方队列地址和 Kling 2.1 Standard 图生视频接口")


def image_input(asset: dict) -> str:
    path = Path(asset["uri"])
    if not path.is_file() or not 0 < path.stat().st_size <= 10 * 1024 * 1024:
        raise VideoProviderError("图生视频参考图需为 10 MB 以内的本地图片")
    content = path.read_bytes()
    if "sha256:" + hashlib.sha256(content).hexdigest() != asset["sha256"]:
        raise VideoProviderError("参考图已改变，请重新上传")
    mime = "image/jpeg" if content.startswith(b"\xff\xd8\xff") else "image/png" if content.startswith(b"\x89PNG\r\n\x1a\n") else None
    if not mime:
        raise VideoProviderError("图生视频参考图需为可解码的 JPEG 或 PNG")
    try:
        if not probe_media(path)["width"]:
            raise MediaGenerationError("missing image track")
    except MediaGenerationError as error:
        raise VideoProviderError("图生视频参考图无法解码，请重新上传 JPEG 或 PNG") from error
    return f"data:{mime};base64," + base64.b64encode(content).decode("ascii")


def queue_url(value: str, request_id: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != "queue.fal.run" or parsed.query or parsed.fragment
            or not parsed.path.startswith("/fal-ai/kling-video/") or ".." in parsed.path
            or not re.fullmatch(r"[A-Za-z0-9-]{1,128}", request_id)
            or not re.search(r"/requests/" + re.escape(request_id) + r"(?:/status|/response|/cancel)?$", parsed.path)):
        raise VideoProviderError("视频平台返回了无效的任务地址", "INVALID_RESPONSE")
    return value


class FalVideoClient:
    def __init__(self, key: str):
        self.key = key

    def _request(self, method: str, url: str, payload=None, submitting=False) -> dict:
        try:
            with httpx.Client(timeout=60, follow_redirects=False) as client:
                response = client.request(method, url, json=payload, headers={"Authorization": f"Key {self.key}"})
            if response.status_code >= 500 or response.status_code == 408:
                raise VideoProviderError("视频平台暂不可用，请保留任务后查询", "SUBMISSION_UNKNOWN" if submitting else "UPSTREAM_UNAVAILABLE")
            if not 200 <= response.status_code < 300:
                raise VideoProviderError(f"视频平台请求被拒绝（HTTP {response.status_code}）", "REQUEST_REJECTED")
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (httpx.HTTPError, ValueError) as error:
            raise VideoProviderError("视频平台响应中断或无效；请勿盲目重复提交", "SUBMISSION_UNKNOWN" if submitting else "INVALID_RESPONSE") from error

    def submit(self, image: str, prompt: str, duration: int) -> dict:
        if not prompt.strip() or len(prompt) > 2500 or duration not in (5, 10):
            raise VideoProviderError("图生视频需要 1 至 2500 字提示词以及 5 秒或 10 秒时长")
        value = self._request("POST", f"{BASE_URL}/{MODEL_ID}", {
            "prompt": prompt, "image_url": image, "duration": str(duration),
        }, submitting=True)
        request_id = value.get("request_id")
        try:
            if not isinstance(request_id, str):
                raise ValueError()
            return {"requestId": request_id, **{name: queue_url(value[key], request_id) for name, key in (
                ("statusUrl", "status_url"), ("resultUrl", "response_url"), ("cancelUrl", "cancel_url"))}}
        except (KeyError, TypeError, ValueError, VideoProviderError) as error:
            raise VideoProviderError("提交结果不完整，需在视频平台核对任务，禁止自动重提", "SUBMISSION_UNKNOWN") from error

    def status(self, handle: dict) -> str:
        value = self._request("GET", queue_url(handle["statusUrl"], handle["requestId"]))
        if value.get("error") or value.get("error_type"):
            raise VideoProviderError("视频平台生成失败，请在供应商后台核对原因", "GENERATION_FAILED")
        status = value.get("status")
        if status not in {"IN_QUEUE", "IN_PROGRESS", "COMPLETED"}:
            raise VideoProviderError("视频平台返回未知任务状态", "INVALID_RESPONSE")
        return status

    def result_url(self, handle: dict) -> str:
        value = self._request("GET", queue_url(handle["resultUrl"], handle["requestId"]))
        video = value.get("video")
        if not isinstance(video, dict) or not isinstance(video.get("url"), str):
            raise VideoProviderError("视频平台未返回视频文件", "INVALID_RESPONSE")
        return video["url"]

    def cancel(self, handle: dict) -> dict:
        return self._request("PUT", queue_url(handle["cancelUrl"], handle["requestId"]))


def download_video(url: str, target: Path) -> dict:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not (host == "fal.media" or host.endswith(".fal.media"))
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise VideoProviderError("视频下载地址不在 fal 媒体域名范围内", "INVALID_DOWNLOAD")
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".part")
    deadline = monotonic() + 180
    try:
        # Credentials never leave the queue host; CDN redirects are not followed.
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise VideoProviderError("视频下载失败，请稍后恢复任务", "DOWNLOAD_FAILED")
                count = 0
                digest = hashlib.sha256()
                with part.open("wb") as output:
                    for chunk in response.iter_bytes():
                        count += len(chunk)
                        if monotonic() > deadline:
                            raise VideoProviderError("视频下载超过 3 分钟，请稍后恢复", "DOWNLOAD_FAILED")
                        if count > MAX_DOWNLOAD_BYTES:
                            raise VideoProviderError("视频文件超过 100 MB", "DOWNLOAD_TOO_LARGE")
                        digest.update(chunk)
                        output.write(chunk)
        metadata = probe_media(part)
        if not metadata["width"] or not metadata["durationMs"]:
            raise VideoProviderError("下载结果不是有效视频", "INVALID_DOWNLOAD")
        part.replace(target)
        return {"uri": str(target), "sha256": "sha256:" + digest.hexdigest(), "kind": "video"}
    except httpx.HTTPError as error:
        raise VideoProviderError("视频下载连接中断，请恢复任务重试下载", "DOWNLOAD_FAILED") from error
    finally:
        part.unlink(missing_ok=True)
