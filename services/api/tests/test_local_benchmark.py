import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("local_benchmark", ROOT / "scripts/local-video/benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.parametrize("source,moving", [("color=c=red:size=64x64:rate=8", False), ("testsrc2=size=64x64:rate=8", True)])
def test_frame_diagnostics_distinguish_static_from_changing_pixels(tmp_path, source, moving):
    target = tmp_path / "diagnostic.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source, "-t", "1", "-c:v", "libx264", str(target)],
                   capture_output=True, check=True, timeout=30)
    result = benchmark.inspect_frames(target)
    assert result["sampledFrames"] == 8
    assert (result["uniqueFrameHashes"] > 1) == moving
    assert (max(result["adjacentMeanAbsoluteDifference"]) > 0) == moving


def test_missing_weights_do_not_submit_or_create_benchmark(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark.ComfyVideoClient, "probe", lambda self: {"ready": False, "missing": ["weights"]})
    monkeypatch.setattr(sys, "argv", ["benchmark", "--reference", "unused.png", "--prompt", "test", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit, match="No job submitted"):
        benchmark.main()
    assert not list(tmp_path.iterdir())


def test_contact_sheet_includes_end_of_longer_video(tmp_path):
    source, sheet = tmp_path / "three-seconds.mp4", tmp_path / "contact.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:size=64x64:rate=8:duration=2",
                    "-f", "lavfi", "-i", "color=c=blue:size=64x64:rate=8:duration=1", "-filter_complex",
                    "[0:v][1:v]concat=n=2:v=1:a=0", "-c:v", "libx264", str(source)],
                   capture_output=True, check=True, timeout=30)
    benchmark.create_contact_sheet(source, sheet, 3000)
    pixel = subprocess.run(["ffmpeg", "-v", "error", "-i", str(sheet), "-vf", "crop=2:2:894:382,scale=1:1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, check=True, timeout=30).stdout
    assert len(pixel) == 3 and pixel[2] > pixel[0] + 100


@pytest.mark.parametrize("precision,decoder", [("default", "native"), ("fp8_e4m3fn", "tiled")])
def test_failed_download_remains_resumable_without_second_submission(monkeypatch, tmp_path, precision, decoder):
    calls = []
    monkeypatch.setattr(benchmark.ComfyVideoClient, "probe", lambda self: {"ready": True})
    monkeypatch.setattr(benchmark.ComfyVideoClient, "upload", lambda *args: "test.jpg")
    def submit(self, graph, job):
        assert graph["1"]["inputs"]["weight_dtype"] == precision
        assert graph["10"]["class_type"] == ("VAEDecode" if decoder == "native" else "VAEDecodeTiled")
        calls.append(job)
    monkeypatch.setattr(benchmark.ComfyVideoClient, "submit", submit)
    monkeypatch.setattr(benchmark.ComfyVideoClient, "status", lambda *args: ("COMPLETED", {}))
    monkeypatch.setattr(benchmark, "gpu_sample", lambda: None)
    monkeypatch.setattr(benchmark, "probe_media", lambda path: {"width": 256, "height": 448, "durationMs": 2000})
    def fail(*args):
        raise RuntimeError("download failed")
    monkeypatch.setattr(benchmark.ComfyVideoClient, "download", fail)
    reference = ROOT / "apps/web/public/images/motorcycle-studio.jpg"
    monkeypatch.setattr(sys, "argv", ["benchmark", "--reference", str(reference), "--prompt", "test", "--output-dir", str(tmp_path),
                                    "--weight-dtype", precision, "--vae-decode", decoder])
    with pytest.raises(RuntimeError, match="download failed"):
        benchmark.main()
    report_path = next(tmp_path.glob("*/report.json"))
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "downloading"
    def download(self, output, path):
        path.write_bytes(b"unit-test-only")
        return {"uri": str(path), "sha256": "sha256:" + hashlib.sha256(b"unit-test-only").hexdigest()}
    monkeypatch.setattr(benchmark.ComfyVideoClient, "download", download)
    monkeypatch.setattr(benchmark, "inspect_frames", lambda path: {"scope": "unit-test-only"})
    monkeypatch.setattr(benchmark.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["benchmark", "--resume", str(report_path)])
    benchmark.main()
    assert len(calls) == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "completed"
