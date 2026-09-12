import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError


class MediaGenerationError(RuntimeError):
    pass


def probe_media(path: Path) -> dict:
    probe = shutil.which("ffprobe")
    if not probe:
        raise MediaGenerationError("未找到 ffprobe")
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(path.resolve())],
            capture_output=True, timeout=30, check=False,
        )
        value = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise MediaGenerationError("素材无法读取或解析超时") from error
    streams = value.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    duration = float(value.get("format", {}).get("duration") or video.get("duration") or 0)
    if not streams or not math.isfinite(duration):
        raise MediaGenerationError("素材不是可解码的图片、视频或音频")
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if width > 8192 or height > 8192:
        raise MediaGenerationError("素材尺寸超过 8192 像素，请先缩小")
    return {"width": width, "height": height, "durationMs": round(duration * 1000),
            "hasAudio": any(s.get("codec_type") == "audio" for s in streams)}


def _encode(arguments: list[str], cwd: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise MediaGenerationError("未找到 FFmpeg")
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *arguments],
            cwd=cwd, capture_output=True, timeout=180, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaGenerationError("媒体处理超时或 FFmpeg 无法启动") from error
    if result.returncode:
        # Raw decoder output may contain private paths or metadata from uploads.
        raise MediaGenerationError("FFmpeg 处理失败，请检查输入素材、时长和字幕字体")


def media_metadata(target: Path, expected_duration_ms: int) -> dict:
    value = probe_media(target)
    if not value["width"] or abs(value["durationMs"] - expected_duration_ms) > 250:
        raise MediaGenerationError("输出时长或视频轨道不符合镜头计划")
    value.update(sizeBytes=target.stat().st_size, sha256="sha256:" + hashlib.sha256(target.read_bytes()).hexdigest())
    return value


def prepare_portrait_reference(asset: dict, output: dict, target: Path) -> dict:
    source = Path(asset["uri"])
    if not source.is_file() or "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest() != asset["sha256"]:
        raise MediaGenerationError("参考图片丢失或内容已改变")
    size = (output["width"], output["height"])
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        rgba = ImageOps.exif_transpose(original).convert("RGBA")
        opaque = Image.new("RGBA", rgba.size, (24, 26, 28, 255))
        picture = Image.alpha_composite(opaque, rgba).convert("RGB")
        background = (Image.new("RGB", size, (24, 26, 28)) if rgba.getextrema()[3][0] < 255
            else ImageOps.fit(picture, size, method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(24)))
        foreground = ImageOps.contain(picture, size, method=Image.Resampling.LANCZOS)
        background.paste(foreground, ((size[0] - foreground.width) // 2, (size[1] - foreground.height) // 2))
        background.save(target, "PNG")
    return {**asset, "uri": str(target.resolve()), "mimeType": "image/png", "width": size[0], "height": size[1],
        "sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()}


def render_uploaded_shot(asset: dict, shot: dict, output: dict, target: Path) -> dict:
    source = Path(asset["uri"])
    if not source.is_file() or "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest() != asset["sha256"]:
        raise MediaGenerationError("镜头源素材丢失或已改变，请重新上传")
    metadata = probe_media(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    width, height, fps = output["width"], output["height"], output["fps"]
    seconds = shot["durationMs"] / 1000
    start = shot.get("sourceStartMs", 0) / 1000
    image = shot["sourceStrategy"] == "image-motion"
    if not metadata["width"]:
        raise MediaGenerationError("所选镜头素材没有画面")
    if not image and start * 1000 + shot["durationMs"] > metadata["durationMs"] + 80:
        raise MediaGenerationError("源视频剩余时长不足，请调整入点或缩短镜头")
    flattened = None
    if image:
        try:
            with Image.open(source) as picture:
                if picture.mode in {"RGBA", "LA"} or "transparency" in picture.info:
                    # Composite alpha before YUV encoding; invisible RGB may contain arbitrary pixels.
                    flattened = target.with_suffix(".source.png")
                    rgba = picture.convert("RGBA")
                    base = Image.new("RGBA", rgba.size, (20, 24, 28, 255))
                    Image.alpha_composite(base, rgba).convert("RGB").save(flattened)
                    source = flattened
        except (OSError, UnidentifiedImageError) as error:
            if flattened:
                flattened.unlink(missing_ok=True)
            raise MediaGenerationError("图片透明背景处理失败") from error
    source_args = ["-loop", "1", "-framerate", str(fps)] if image else ["-ss", str(start)]
    args = [*source_args, "-protocol_whitelist", "file,pipe", "-i", str(source.resolve())]
    has_audio = not image and metadata["hasAudio"]
    if not has_audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    crop = shot.get("sourceCrop")
    prefix = ""
    if crop is not None:
        if (not isinstance(crop, list) or len(crop) != 4 or any(type(value) is not int for value in crop)
                or min(crop[:2]) < 0 or min(crop[2:]) < 2 or crop[0] + crop[2] > metadata["width"] or crop[1] + crop[3] > metadata["height"]):
            raise MediaGenerationError("生成片段的画幅信息无效")
        prefix = f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},"
    if shot.get("fit", "contain") == "cover":
        filters = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
    else:
        filters = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x14181c,setsar=1"
    if image:
        frames = max(1, round(seconds * fps))
        filters += f",zoompan=z='1+0.06*on/{frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps={fps}"
    filters = prefix + filters + f",fps={fps},setpts=PTS-STARTPTS"
    if shot.get("backgroundFill") == "soft" and flattened is None:
        # Preserve the entire subject; the extended backdrop is not a second sharp image.
        filters = (f"[0:v]{prefix}split[fg][bg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=30:2,eq=brightness=-0.12[back];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];"
            f"[back][front]overlay=(W-w)/2:(H-h)/2,setsar=1"
            + (f",zoompan=z='1+0.04*on/{max(1, round(seconds * fps))}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps={fps}" if image else "")
            + f",fps={fps},setpts=PTS-STARTPTS[out]")
        args += ["-filter_complex_threads", "1", "-filter_complex", filters, "-map", "[out]"]
    else:
        args += ["-map", "0:v:0", "-vf", filters]
    args += ["-t", str(seconds), "-map", "0:a:0" if has_audio else "1:a:0",
             "-af", "aresample=48000,apad", "-ac", "2", "-c:v", "libx264", "-threads", "2",
             "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(target.resolve())]
    try:
        _encode(args, target.parent)
    finally:
        if flattened:
            flattened.unlink(missing_ok=True)
    return media_metadata(target, shot["durationMs"])


def _ass_time(milliseconds: int) -> str:
    centiseconds = milliseconds // 10
    return f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"


def render_soundtrack(duration_ms: int, target: Path) -> dict:
    """A local electronic rhythm bed, not a recording of a particular vehicle."""
    target.parent.mkdir(parents=True, exist_ok=True)
    seconds = duration_ms / 1000
    # 120 BPM: decaying kick, offbeat bass and a quiet sustained minor chord.
    expression = ("0.42*sin(2*PI*(52*t-2.5*exp(-35*mod(t,0.5))))*exp(-18*mod(t,0.5))"
        "+0.12*sin(2*PI*65.406*t)*exp(-9*mod(t+0.25,0.5))"
        "+0.035*(sin(2*PI*130.813*t)+sin(2*PI*155.563*t)+sin(2*PI*195.998*t))"
        "+0.025*sin(2*PI*6100*t)*sin(2*PI*4313*t)*exp(-65*mod(t,0.25))")
    _encode(["-f", "lavfi", "-i", f"aevalsrc='{expression}':s=48000:d={seconds}",
        "-af", f"afade=t=in:d=0.12,afade=t=out:st={max(0, seconds - .7)}:d=0.7,loudnorm=I=-18:TP=-2:LRA=7",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(target.resolve())], target.parent)
    if not probe_media(target)["hasAudio"]:
        raise MediaGenerationError("本地节奏音轨生成失败")
    return {"uri": str(target.resolve()), "sha256": "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()}


def compose_uploaded_shots(paths: list[Path], shots: list[dict], output: dict, target: Path, audio: dict | None = None, narration: Path | None = None) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Only generated UUID filenames from this run enter the concat manifest.
    if any(path.parent.resolve() != target.parent.resolve() for path in paths):
        raise MediaGenerationError("片段不属于本次运行目录")
    (target.parent / "concat.txt").write_text("".join(f"file '{path.name}'\n" for path in paths), encoding="utf-8")
    width, height = output["width"], output["height"]
    font_size = round(width * 0.042)
    subtitle_lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H00101010,1,2,0,2,{width // 12},{width // 12},{height // 9},1",
        "[Events]", "Format: Layer, Start, End, Style, Text"]
    cursor = 0
    for shot in shots:
        text = str(shot.get("caption") or "").replace("\\", " ").replace("{", "(").replace("}", ")").replace("\r", "").replace("\n", " ")
        text = "\\N".join(text[i:i + 20] for i in range(0, len(text), 20))
        if text:
            subtitle_lines.append(f"Dialogue: 0,{_ass_time(cursor)},{_ass_time(cursor + shot['durationMs'])},Default,{text}")
        cursor += shot["durationMs"]
    (target.parent / "timeline.ass").write_text("\n".join(subtitle_lines), encoding="utf-8")
    args = ["-protocol_whitelist", "file,pipe", "-f", "concat", "-safe", "1", "-i", "concat.txt"]
    filters = ["[0:a]volume=0.2[src]"] if narration else []
    tracks = ["[src]" if narration else "[0:a]"]
    if audio:
        audio_path = Path(audio["uri"])
        if not audio_path.is_file() or "sha256:" + hashlib.sha256(audio_path.read_bytes()).hexdigest() != audio["sha256"]:
            raise MediaGenerationError("所选背景音频丢失或已改变")
        if not probe_media(audio_path)["hasAudio"]:
            raise MediaGenerationError("所选背景文件没有音轨")
        args += ["-stream_loop", "-1", "-protocol_whitelist", "file,pipe", "-i", str(audio_path.resolve())]
        filters.append(f"[1:a]volume={0.22 if narration else 0.7},afade=t=out:st={max(0, cursor / 1000 - .5)}:d=0.5[bg]")
        tracks.append("[bg]")
    if narration:
        args += ["-protocol_whitelist", "file,pipe", "-i", str(narration.resolve())]
        tracks.append(f"[{2 if audio else 1}:a]")
    if len(tracks) > 1:
        filters.append("".join(tracks) + f"amix=inputs={len(tracks)}:duration=first:normalize=0,alimiter=limit=0.95:latency=1[a]")
        args += ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[a]"]
    else:
        args += ["-map", "0:v:0", "-map", "0:a:0"]
    args += ["-vf", "subtitles=timeline.ass", "-t", str(cursor / 1000), "-r", str(output["fps"]),
             "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(target.resolve())]
    _encode(args, target.parent)
    return media_metadata(target, cursor)


def create_preview_video(target: Path, duration_seconds: int = 6) -> dict[str, int | str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise MediaGenerationError("FFmpeg is not installed or not available on PATH")

    repo_root = Path(__file__).resolve().parents[4]
    studio_image = repo_root / "apps" / "web" / "public" / "images" / "motorcycle-studio.jpg"
    riding_image = repo_root / "apps" / "web" / "public" / "images" / "motorcycle-road.jpg"
    if studio_image.exists() and riding_image.exists():
        segment_duration = duration_seconds / 2
        command = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-t",
            str(segment_duration),
            "-i",
            str(studio_image),
            "-loop",
            "1",
            "-t",
            str(segment_duration),
            "-i",
            str(riding_image),
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=72:sample_rate=48000:duration={duration_seconds}",
            "-filter_complex",
            "[0:v]scale=540:960:force_original_aspect_ratio=increase,crop=540:960,setsar=1,fps=30[v0];"
            "[1:v]scale=540:960:force_original_aspect_ratio=increase,crop=540:960,setsar=1,fps=30[v1];"
            "[v0][v1]concat=n=2:v=1:a=0,vignette=PI/8[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(target),
        ]
    else:
        command = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x10161c:s=540x960:r=30:d={duration_seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=72:sample_rate=48000:duration={duration_seconds}",
            "-vf",
            "drawgrid=w=90:h=90:t=1:c=0x2b3c42@0.5,vignette=PI/5",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(target),
        ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    if completed.returncode != 0:
        raise MediaGenerationError(completed.stderr[-2000:])

    payload = target.read_bytes()
    return {
        "sizeBytes": len(payload),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "width": 540,
        "height": 960,
        "durationMs": duration_seconds * 1000,
    }
