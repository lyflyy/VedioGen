"""Opt-in real local inference benchmark; not a product or vehicle acceptance test."""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from vediogen_api.comfy_video import ComfyVideoClient, workflow
from vediogen_api.media import probe_media


def write_report(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def gpu_sample():
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    result = subprocess.run([executable, "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        return None
    try:
        memory, utilization = result.stdout.splitlines()[0].split(",")
        return {"memoryUsedMiB": int(memory.strip()), "utilizationPercent": int(utilization.strip())}
    except (ValueError, IndexError):
        return None


def inspect_frames(video: Path) -> dict:
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "fps=8,scale=64:64",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, timeout=60, check=True)
    size = 64 * 64 * 3
    frames = [result.stdout[i:i + size] for i in range(0, len(result.stdout), size) if len(result.stdout[i:i + size]) == size]
    changes = [round(sum(abs(a - b) for a, b in zip(previous, current)) / size, 4) for previous, current in zip(frames, frames[1:])]
    return {"sampledFrames": len(frames), "uniqueFrameHashes": len({hashlib.sha256(frame).hexdigest() for frame in frames}),
            "adjacentMeanAbsoluteDifference": changes,
            "scope": "Pixel change is diagnostic only, not proof of good motion or identity preservation."}


def create_contact_sheet(video: Path, target: Path, duration_ms: int):
    seconds = max(1, duration_ms) / 1000
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    f"fps=8/{seconds:.3f},scale=256:-1,tile=4x2", "-frames:v", "1", str(target)],
                   capture_output=True, timeout=60, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--prompt")
    parser.add_argument("--resume", type=Path, help="Existing report; only query the stored job, never resubmit it.")
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--output-dir", type=Path, default=Path(".data/internal-mvp/local-benchmarks"))
    parser.add_argument("--width", type=int, default=832)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--duration", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--steps", type=int, choices=range(4, 31), default=20)
    parser.add_argument("--weight-dtype", choices=("default", "fp8_e4m3fn"), default="default",
                        help="Controlled precision comparison; does not change the admin configuration.")
    parser.add_argument("--vae-decode", choices=("tiled", "native"), default="native",
                        help="Controlled decoder comparison; does not change the admin configuration.")
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    if not 30 <= args.timeout <= 7200:
        parser.error("Timeout must be 30 to 7200 seconds.")
    if args.resume:
        report_path = args.resume.resolve()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") == "completed":
            video = Path(report["video"]["uri"])
            if video.is_file() and "sha256:" + hashlib.sha256(video.read_bytes()).hexdigest() == report["video"]["sha256"]:
                print(json.dumps(report, ensure_ascii=True))
                return
    else:
        if not args.reference or not args.prompt:
            parser.error("A reference and prompt are required for a new benchmark.")
        if any(value < 256 or value > 832 or value % 32 for value in (args.width, args.height)) or args.width * args.height > 480 * 832:
            parser.error("Use 32-aligned dimensions, at most 480 x 832 pixels.")
        client = ComfyVideoClient(args.url)
        check = client.probe()
        if not check["ready"]:
            print(json.dumps(check, ensure_ascii=True))
            raise SystemExit("Local models or nodes are not ready. No job submitted.")
        reference = args.reference.resolve()
        asset = {"uri": str(reference), "sha256": "sha256:" + hashlib.sha256(reference.read_bytes()).hexdigest()}
        size = probe_media(reference)
        job = str(uuid4())
        directory = args.output_dir.resolve() / job
        directory.mkdir(parents=True)
        report_path = directory / "report.json"
        report = {"jobId": job, "url": args.url, "status": "preparing", "reference": asset,
                  "prompt": args.prompt, "config": {"width": args.width, "height": args.height, "steps": args.steps,
                                                    "weightDtype": args.weight_dtype, "vaeDecode": args.vae_decode},
                  "durationMs": args.duration * 1000, "seed": args.seed, "startedAt": datetime.now(timezone.utc).isoformat(),
                  "gpuSamples": [], "scope": "Real inference experiment; not user-approved vehicle identity or final acceptance."}
        write_report(report_path, report)
        image = client.upload(asset, job)
        graph = workflow(report["config"], {"durationMs": report["durationMs"], "videoPrompt": args.prompt},
                         image, job, args.seed, (size["width"], size["height"]))
        graph["1"]["inputs"]["weight_dtype"] = args.weight_dtype
        if args.vae_decode == "tiled":
            graph["10"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["9", 0], "vae": ["3", 0],
                            "tile_size": 256, "overlap": 64, "temporal_size": 16, "temporal_overlap": 4}}
        report["workflow"] = graph
        report["status"] = "submitting"
        write_report(report_path, report)
        print(json.dumps({"report": str(report_path), "jobId": job}), flush=True)
        try:
            client.submit(graph, job)
        except Exception as error:
            report.update(status="submission-uncertain", error=str(error))
            write_report(report_path, report)
            raise
    client = ComfyVideoClient(report["url"])
    started = time.monotonic()
    try:
        while time.monotonic() - started < args.timeout:
            state, output = client.status(report["jobId"])
            sample = gpu_sample()
            if sample:
                report["gpuSamples"].append({"at": datetime.now(timezone.utc).isoformat(), **sample})
            report.update(status="downloading" if state == "COMPLETED" else state.lower(), waitSeconds=round(time.monotonic() - started, 2))
            write_report(report_path, report)
            print(json.dumps({"jobId": report["jobId"], "status": state, "waitSeconds": report["waitSeconds"], "gpu": sample}), flush=True)
            if state in {"FAILED", "MISSING"}:
                raise RuntimeError("Stored job failed or is missing. It was not resubmitted.")
            if state == "COMPLETED":
                target = report_path.parent / "native.mp4"
                video = client.download(output, target)
                report["video"] = {**video, **probe_media(target)}
                report["frameDiagnostics"] = inspect_frames(target)
                create_contact_sheet(target, report_path.parent / "contact-sheet.jpg", report["video"]["durationMs"])
                report["status"] = "completed"
                report.pop("error", None)
                report["completedAt"] = datetime.now(timezone.utc).isoformat()
                write_report(report_path, report)
                print(json.dumps({"report": str(report_path), "video": report["video"], "frames": report["frameDiagnostics"]}), flush=True)
                return
            time.sleep(5)
        report["status"] = "waiting-timeout"
        write_report(report_path, report)
        raise TimeoutError("Wait timed out; resume this report to query the same live job.")
    except Exception as error:
        report["error"] = str(error)
        write_report(report_path, report)
        raise


if __name__ == "__main__":
    main()
