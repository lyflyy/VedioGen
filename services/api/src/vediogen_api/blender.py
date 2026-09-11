import hashlib
import json
import struct
import subprocess
from pathlib import Path
from time import monotonic, sleep

import psutil

from .config import get_settings
from .media import MediaGenerationError, _encode, media_metadata


def validate_glb(content: bytes) -> dict:
    try:
        if len(content) < 28 or struct.unpack_from("<4sII", content) != (b"glTF", 2, len(content)):
            raise ValueError("header")
        length, kind = struct.unpack_from("<II", content, 12)
        if kind != 0x4E4F534A or length % 4 or length + 28 > len(content):
            raise ValueError("json chunk")
        data = json.loads(content[20:20 + length])
        binary_length, binary_type = struct.unpack_from("<II", content, 20 + length)
        if binary_type != 0x004E4942 or binary_length % 4 or 28 + length + binary_length != len(content):
            raise ValueError("binary chunk")
        if data["asset"]["version"] != "2.0" or not data.get("meshes"):
            raise ValueError("mesh")
        buffers = data.get("buffers", [])
        if len(buffers) != 1 or not 0 < buffers[0]["byteLength"] <= binary_length:
            raise ValueError("buffers")
        # GLB assets must be self-contained; Blender must not resolve external files or URLs.
        def check(value):
            if isinstance(value, dict):
                if "uri" in value:
                    raise ValueError("external reference")
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(data)
        return {"meshCount": len(data["meshes"]), "format": "glb-2.0", "subjectConfirmed": False}
    except (ValueError, TypeError, KeyError, IndexError, struct.error, RecursionError) as error:
        raise MediaGenerationError("需要带网格和内嵌纹理的 GLB 2.0 文件，不接受外部资源引用或损坏的文件") from error


def executable_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or path.name.lower() not in {"blender", "blender.exe"}:
        raise MediaGenerationError("请配置存在的 Blender 可执行文件绝对路径")
    return path.resolve()


def probe_blender(value: str) -> dict:
    if not get_settings().allow_local_models:
        raise MediaGenerationError("当前环境禁止本地 Blender 执行")
    try:
        result = subprocess.run([str(executable_path(value)), "--version"], capture_output=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        version = result.stdout.decode("utf-8", errors="replace").splitlines()[0]
        if result.returncode or not version.startswith("Blender "):
            raise ValueError("Unexpected executable response")
        return {"ready": True, "version": version[:120], "verification": "executable-only"}
    except (OSError, subprocess.TimeoutExpired, IndexError, ValueError) as error:
        raise MediaGenerationError("Blender 版本检查失败；未运行渲染") from error


def blender_plan(config: dict) -> dict:
    if not config["blenderEnabled"] or not get_settings().allow_local_models:
        raise MediaGenerationError("Blender 环绕未启用，请在管理后台配置本地 Blender")
    return {"executable": str(executable_path(config["blenderExecutable"])), "timeoutSeconds": config["blenderTimeoutSeconds"]}


def matching_process(handle):
    if not handle:
        return None
    try:
        process = psutil.Process(handle["pid"])
        return process if process.create_time() == handle["createdAt"] and process.is_running() and process.status() != psutil.STATUS_ZOMBIE else None
    except psutil.NoSuchProcess:
        return None
    except (psutil.Error, KeyError, TypeError) as error:
        raise MediaGenerationError("无法核对 Blender 进程身份；未重新提交或终止其他进程") from error


def cancel_blender(handle):
    process = matching_process(handle)
    if process:
        try:
            process.terminate()
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        except psutil.NoSuchProcess:
            pass


def render_blender_shot(asset, shot, output, config, target, directory, handle, started, record, cancelled, progress):
    if not get_settings().allow_local_models:
        raise MediaGenerationError("当前环境禁止本地 Blender 执行")
    content = Path(asset["uri"]).read_bytes()
    if "sha256:" + hashlib.sha256(content).hexdigest() != asset["sha256"]:
        raise MediaGenerationError("三维素材文件已改变，请重新导入")
    validate_glb(content)
    report_path = directory / "orbit.json"
    child = None
    if not started:
        if cancelled():
            return None
        directory.parent.mkdir(parents=True, exist_ok=True)
        record(None, True)
        try:
            with directory.with_suffix(".log").open("wb") as log:
                child = subprocess.Popen([str(executable_path(config["executable"])), "--background", "--factory-startup",
                    "--disable-autoexec", "--python-exit-code", "1", "--python", str(Path(__file__).with_name("blender_scene.py")),
                    "--", "--asset", asset["uri"], "--output", str(directory), "--width", str(output["width"]),
                    "--height", str(output["height"]), "--fps", str(output["fps"]), "--frames", str(round(shot["durationMs"] * output["fps"] / 1000))],
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
            handle = {"pid": child.pid, "createdAt": psutil.Process(child.pid).create_time()}
            record(handle, True)
        except Exception:
            if child and child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
            raise
    elif not handle and not report_path.is_file():
        raise MediaGenerationError("上次 Blender 启动结果不明，请核对本地进程；未自动重启渲染")
    deadline = monotonic() + config["timeoutSeconds"]
    previous = -1
    while matching_process(handle):
        if cancelled():
            cancel_blender(handle)
            if child:
                child.wait(timeout=10)
            return None
        if monotonic() >= deadline:
            cancel_blender(handle)
            if child:
                child.wait(timeout=10)
            raise MediaGenerationError("Blender 渲染超时，已停止对应进程；可按原参数重做")
        count = len(list(directory.glob("frame-*.png"))) if directory.exists() else 0
        if count != previous:
            progress(count)
            previous = count
        if child:
            child.poll()
        sleep(0.25)
    if child and child.wait(timeout=10) != 0:
        raise MediaGenerationError("Blender 渲染失败，请检查网格、纹理及本机渲染资源")
    if cancelled():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected = round(shot["durationMs"] * output["fps"] / 1000)
        if (report["calibrationOnly"] or report["assetSha256"] != asset["sha256"].removeprefix("sha256:")
                or report["frames"] != expected or report["width"] != output["width"] or report["height"] != output["height"]
                or report["fps"] != output["fps"] or report["orbitDegrees"] != 360
                or len(report["samples"]) != expected or not all(s["allBoundsInside"] for s in report["samples"])
                or any(not (directory / f"frame-{i:04d}.png").is_file() for i in range(1, expected + 1))):
            raise ValueError("Invalid render output")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise MediaGenerationError("Blender 输出不完整或不匹配镜头；未用占位素材替代") from error
    _encode(["-framerate", str(output["fps"]), "-i", str(directory / "frame-%04d.png"),
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(shot["durationMs"] / 1000),
             "-c:v", "libx264", "-threads", "2", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-movflags", "+faststart", str(target.resolve())], directory)
    progress(expected)
    return media_metadata(target, shot["durationMs"])
