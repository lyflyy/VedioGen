"""Local-only adapter for ComfyUI's core Wan 2.2 TI2V workflow."""

from math import ceil
import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx

from .fal_video import VideoProviderError, image_input
from .media import probe_media


DIFFUSION = "wan2.2_ti2v_5B_fp16.safetensors"
ENCODER = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE = "wan2.2_vae.safetensors"
NODES = {"UNETLoader", "CLIPLoader", "VAELoader", "LoadImage", "CLIPTextEncode",
         "ModelSamplingSD3", "Wan22ImageToVideoLatent", "KSampler", "VAEDecode", "CreateVideo", "SaveVideo", "ImageScale", "ImagePadForOutpaint"}


def local_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
                 and parsed.port and 1024 <= parsed.port <= 65535 and not parsed.username
                 and not parsed.password and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise VideoProviderError("本地 ComfyUI 地址需为 http://127.0.0.1:端口（1024 至 65535）")
    return value.rstrip("/")


def workflow(config: dict, shot: dict, image: str, prompt_id: str, seed: int, reference_size: tuple[int, int] | None = None) -> dict:
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}

    width, height = config["width"], config["height"]
    source_width, source_height = reference_size or (width, height)
    contain = shot.get("fit", "contain") == "contain"
    ratio = min(width / source_width, height / source_height)
    scaled_width, scaled_height = (max(1, round(source_width * ratio)), max(1, round(source_height * ratio))) if contain else (width, height)
    left, top = (width - scaled_width) // 2, (height - scaled_height) // 2
    legacy = config.get("physicalModelId") == "wan2.2-ti2v-5b-fp8-runtime"
    # Adapted from the official video_wan2_2_5B_ti2v template; only core, offline nodes.
    return {
        "1": node("UNETLoader", unet_name=DIFFUSION, weight_dtype="fp8_e4m3fn" if legacy else "default"),
        "2": node("CLIPLoader", clip_name=ENCODER, type="wan", device="default"),
        "3": node("VAELoader", vae_name=VAE),
        "4": node("LoadImage", image=image),
        "13": node("ImageScale", image=["4", 0], width=scaled_width, height=scaled_height,
                   upscale_method="lanczos", crop="disabled" if contain else "center"),
        "14": node("ImagePadForOutpaint", image=["13", 0], left=left, top=top,
                   right=width - scaled_width - left, bottom=height - scaled_height - top, feathering=0),
        "5": node("CLIPTextEncode", clip=["2", 0], text=shot["videoPrompt"]),
        "6": node("CLIPTextEncode", clip=["2", 0], text="static image, deformation, distorted wheels, extra wheels, flicker, text, watermark, low quality"),
        "7": node("ModelSamplingSD3", model=["1", 0], shift=8.0),
        "8": node("Wan22ImageToVideoLatent", vae=["3", 0], start_image=["14", 0],
                  width=config["width"], height=config["height"], length=ceil(shot["durationMs"] * 24 / 4000) * 4 + 1, batch_size=1),
        "9": node("KSampler", model=["7", 0], positive=["5", 0], negative=["6", 0], latent_image=["8", 0],
                  seed=seed, steps=config["steps"], cfg=5.0, sampler_name="uni_pc", scheduler="simple", denoise=1.0),
        "10": (node("VAEDecodeTiled", samples=["9", 0], vae=["3", 0], tile_size=256, overlap=64, temporal_size=16, temporal_overlap=4)
               if legacy else node("VAEDecode", samples=["9", 0], vae=["3", 0])),
        "11": node("CreateVideo", images=["10", 0], fps=24.0),
        "12": node("SaveVideo", video=["11", 0], filename_prefix=f"vediogen/{prompt_id}",
                   **{"format": "mp4", "format.codec": "h264"}),
    }


class ComfyVideoClient:
    def __init__(self, base_url: str):
        self.base_url = local_url(base_url)

    def request(self, method: str, path: str, **kwargs):
        try:
            with httpx.Client(base_url=self.base_url, timeout=30, trust_env=False, follow_redirects=False) as client:
                response = client.request(method, path, **kwargs)
            if response.status_code != 200:
                code = "REQUEST_REJECTED" if response.status_code == 400 else "LOCAL_HTTP_ERROR"
                raise VideoProviderError(f"本地 ComfyUI 请求失败（HTTP {response.status_code}），请检查服务日志", code)
            return response.json() if response.content else {}
        except (httpx.HTTPError, ValueError) as error:
            raise VideoProviderError("无法连接本地 ComfyUI 或响应无效，请检查服务和端口", "LOCAL_UNAVAILABLE") from error

    def probe(self) -> dict:
        stats = self.request("GET", "/system_stats")
        info = self.request("GET", "/object_info")
        missing = sorted(NODES - info.keys())
        version = stats.get("system", {}).get("comfyui_version", "")
        try:
            supported = tuple(int(part) for part in version.split(".")[:3]) >= (0, 34, 0)
        except ValueError:
            supported = False
        if not supported:
            missing.append("ComfyUI >= 0.34.0 (定向取消与客户端任务 ID)")
        for kind, field, model in [("UNETLoader", "unet_name", DIFFUSION), ("CLIPLoader", "clip_name", ENCODER), ("VAELoader", "vae_name", VAE)]:
            options = info.get(kind, {}).get("input", {}).get("required", {}).get(field, [[]])[0]
            if model not in options:
                missing.append(model)
        return {"ready": not missing, "missing": missing, "devices": stats.get("devices", []),
                "version": stats.get("system", {}).get("comfyui_version"), "verification": "service-and-model-list-only"}

    def upload(self, asset: dict, name: str) -> str:
        image_input(asset)
        path = Path(asset["uri"])
        result = self.request("POST", "/upload/image", files={"image": (name + path.suffix.lower(), path.read_bytes())},
                              data={"type": "input", "subfolder": "vediogen", "overwrite": "true"})
        filename, folder = result.get("name", ""), result.get("subfolder", "")
        if not filename or PurePosixPath(filename).name != filename or "\\" in filename or ".." in PurePosixPath(folder).parts or folder.startswith(("/", "\\")):
            raise VideoProviderError("本地服务返回了无效素材路径")
        return str(PurePosixPath(folder) / filename)

    def submit(self, graph: dict, prompt_id: str):
        result = self.request("POST", "/prompt", json={"prompt": graph, "prompt_id": prompt_id, "client_id": "vediogen-local"})
        if result.get("prompt_id") != prompt_id:
            raise VideoProviderError("ComfyUI 未接受指定任务 ID，请升级到受支持版本", "SUBMISSION_UNKNOWN")

    def status(self, prompt_id: str) -> tuple[str, dict | None]:
        # The job can finish between history and queue reads; re-read history before declaring it missing.
        for attempt in range(2):
            history = self.request("GET", f"/history/{prompt_id}").get(prompt_id)
            if history:
                state = history.get("status", {})
                if state.get("status_str") == "error":
                    return "FAILED", None
                if state.get("completed"):
                    outputs = history.get("outputs", {}).get("12", {}).get("images", [])
                    if len(outputs) != 1 or not outputs[0].get("filename", "").endswith(".mp4"):
                        raise VideoProviderError("本地工作流完成但没有预期 MP4 输出")
                    return "COMPLETED", outputs[0]
            if attempt == 0:
                queue = self.request("GET", "/queue")
                for key, state in [("queue_running", "RUNNING"), ("queue_pending", "QUEUED")]:
                    if any(item[1] == prompt_id for item in queue.get(key, [])):
                        return state, None
        return "MISSING", None

    def cancel(self, prompt_id: str):
        self.request("POST", "/queue", json={"delete": [prompt_id]})
        self.request("POST", "/interrupt", json={"prompt_id": prompt_id})

    def download(self, output: dict, target: Path) -> dict:
        filename, folder = output.get("filename", ""), output.get("subfolder", "")
        if (output.get("type") != "output" or not filename.endswith(".mp4") or PurePosixPath(filename).name != filename
                or "\\" in filename or ".." in PurePosixPath(folder).parts or "\\" in folder or folder.startswith("/")):
            raise VideoProviderError("本地工作流返回了无效视频路径")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(base_url=self.base_url, timeout=60, trust_env=False, follow_redirects=False) as client:
                with client.stream("GET", "/view", params={"filename": filename, "subfolder": folder, "type": "output"}) as response:
                    response.raise_for_status()
                    size = 0
                    digest = hashlib.sha256()
                    with target.open("wb") as file:
                        for chunk in response.iter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > 200 * 1024 * 1024:
                                raise VideoProviderError("本地视频超过 200 MB 限制")
                            file.write(chunk)
                            digest.update(chunk)
            info = probe_media(target)
            if not info["width"] or info["durationMs"] <= 0:
                raise VideoProviderError("本地输出不是可解码的视频")
            return {"uri": str(target), "kind": "video", "durationMs": info["durationMs"], "sha256": "sha256:" + digest.hexdigest()}
        except httpx.HTTPError as error:
            raise VideoProviderError("本地视频下载失败，可恢复任务重新获取") from error
