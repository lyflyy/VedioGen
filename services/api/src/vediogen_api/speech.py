import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import wave
from array import array
from pathlib import Path

from .config import get_settings
from .media import MediaGenerationError


def voice_configuration(model_path: str) -> dict:
    if not get_settings().allow_local_models:
        raise MediaGenerationError("当前环境禁止本地模型访问")
    if importlib.util.find_spec("piper") is None:
        raise MediaGenerationError("未安装本地配音依赖，请运行 uv sync --project services/api --extra speech")
    model = Path(model_path)
    config = Path(str(model) + ".json")
    if not model_path or not model.is_file() or model.suffix != ".onnx" or not config.is_file():
        raise MediaGenerationError("本地声音文件缺失，需要 ONNX 模型及同名 .onnx.json 配置")
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("language"), dict) or not isinstance(data.get("audio"), dict):
            raise ValueError("invalid voice configuration")
        if data.get("phoneme_type") != "espeak" or data.get("language", {}).get("code") != "zh_CN":
            raise ValueError("unsupported voice")
        rate = data["audio"]["sample_rate"]
        if type(rate) is not int or not 8000 <= rate <= 48000:
            raise ValueError("unsupported rate")
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise MediaGenerationError("声音配置无效；当前仅支持 espeak 中文 Piper 声音") from error
    return {"modelPath": str(model.resolve()), "sampleRate": rate,
            "modelSha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "configSha256": hashlib.sha256(config.read_bytes()).hexdigest()}


def narration_plan(settings: dict, shots: list[dict]) -> dict:
    if not settings["narrationEnabled"]:
        raise MediaGenerationError("本地旁白未启用，请在管理后台配置中文声音")
    if not any(str(shot.get("voiceover") or "").strip() for shot in shots):
        raise MediaGenerationError("分镜没有旁白文本，请填写旁白或关闭本地旁白")
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot.get("voiceover", ""), str) or len(shot.get("voiceover", "")) > 300:
            raise MediaGenerationError(f"镜头 {index} 旁白需为文本且不超过 300 字")
    return voice_configuration(settings["narrationModelPath"])


def synthesize(text: str, config: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source = target.with_suffix(".txt")
    source.write_text(text, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "piper", "-m", config["modelPath"],
             "--input-file", str(source.resolve()), "-f", str(target.resolve())],
            capture_output=True, timeout=60, check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaGenerationError("本地旁白合成超时或无法启动；未调用云端替代") from error
    if result.returncode or not target.is_file():
        raise MediaGenerationError("Piper 配音失败，请检查声音模型与本地依赖；未生成静音替代")


def render_narration(shots: list[dict], config: dict, directory: Path) -> Path:
    current = voice_configuration(config["modelPath"])
    if current != config:
        raise MediaGenerationError("本地声音模型已改变，请恢复原文件或创建新任务")
    directory.mkdir(parents=True, exist_ok=True)
    rate = config["sampleRate"]
    timeline = bytearray()
    segments = []
    cursor_ms = 0
    for index, shot in enumerate(shots, 1):
        text = str(shot.get("voiceover") or "").strip()
        # Absolute boundaries avoid accumulated fractional-sample rounding drift.
        frames = round((cursor_ms + shot["durationMs"]) * rate / 1000) - round(cursor_ms * rate / 1000)
        samples = b""
        if text:
            target = directory / f"narration-{index}.wav"
            synthesize(text, config, target)
            try:
                with wave.open(str(target), "rb") as audio:
                    if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, rate):
                        raise ValueError("unexpected PCM format")
                    count = audio.getnframes()
                    samples = audio.readframes(count)
                    if len(samples) != count * 2:
                        raise ValueError("truncated PCM data")
                values = array("h", samples)
                if sys.byteorder != "little":
                    values.byteswap()
                if not values or max(abs(value) for value in values) < 100:
                    raise ValueError("silent output")
            except (OSError, ValueError, wave.Error, EOFError) as error:
                raise MediaGenerationError(f"镜头 {index} 旁白音频无效或静音") from error
            if count > frames:
                raise MediaGenerationError(
                    f"镜头 {index} 旁白需要 {count / rate:.2f} 秒，镜头仅 {frames / rate:.2f} 秒；"
                    "请缩短旁白或增加镜头时长后重新确认分镜。未截断旁白。"
                )
        timeline.extend(samples)
        timeline.extend(bytes(frames * 2 - len(samples)))
        segments.append({"shotId": shot["id"], "startMs": cursor_ms,
                         "speechDurationMs": round(len(samples) / 2 / rate * 1000), "durationMs": shot["durationMs"]})
        cursor_ms += shot["durationMs"]
    target = directory / "narration.wav"
    with wave.open(str(target), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(timeline)
    (directory / "narration.json").write_text(json.dumps({"engine": "piper", **config, "segments": segments}, indent=2), encoding="utf-8")
    return target
