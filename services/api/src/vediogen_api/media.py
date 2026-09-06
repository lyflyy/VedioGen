import hashlib
import shutil
import subprocess
from pathlib import Path


class MediaGenerationError(RuntimeError):
    pass


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
