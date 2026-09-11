import json
import math
import struct
import subprocess
import time
import wave
from pathlib import Path

import pytest

from vediogen_api import generation, speech
from vediogen_api.config import get_settings
from vediogen_api.database import SessionLocal
from vediogen_api.media import MediaGenerationError
from vediogen_api.models import ArtifactRow, DocumentRow, GenerationRunRow
from test_creator_flow import wait_generation
from test_media_generation import prepared, upload


def tone(target, seconds=0.2, rate=22050):
    with wave.open(str(target), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"".join(struct.pack("<h", round(9000 * math.sin(2 * math.pi * 440 * i / rate)))
                                   for i in range(round(seconds * rate))))


@pytest.fixture
def voice(tmp_path, monkeypatch):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"test-model-not-real-inference")
    Path(str(model) + ".json").write_text(json.dumps({"phoneme_type": "espeak", "language": {"code": "zh_CN"}, "audio": {"sample_rate": 22050}}))
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    monkeypatch.setattr(speech.importlib.util, "find_spec", lambda _: object())
    return speech.voice_configuration(str(model))


def configure(client, voice):
    config = client.get("/api/v1/admin/video-settings").json()
    for key in ("externalCallsAllowed", "localCallsAllowed", "verification"):
        config.pop(key, None)
    return client.put("/api/v1/admin/video-settings", json={**config, "narrationEnabled": True, "narrationModelPath": voice["modelPath"]})


def request_run(client, project_id, storyboard_id, **extra):
    return client.post("/api/v1/generation-runs", json={"projectId": project_id, "storyboardVersionId": storyboard_id,
                       "narration": True, "quality": "preview", **extra})


def with_voiceover(storyboard_id, text="旁白测试"):
    with SessionLocal() as session:
        doc = session.get(DocumentRow, storyboard_id)
        doc.data = {**doc.data, "shots": [{**shot, "voiceover": text if index == 0 else ""} for index, shot in enumerate(doc.data["shots"])]}
        session.commit()


def test_settings_validate_local_voice_and_preserve_config(client, voice, monkeypatch):
    assert configure(client, voice).status_code == 200
    result = client.get("/api/v1/admin/video-settings").json()
    assert result["narrationEnabled"] is True
    assert result["narrationModelPath"] == voice["modelPath"]
    monkeypatch.setattr(get_settings(), "allow_local_models", False)
    assert configure(client, voice).status_code == 422
    monkeypatch.setattr(get_settings(), "allow_local_models", True)
    Path(voice["modelPath"]).unlink()
    assert configure(client, voice).status_code == 422


def test_unconfigured_or_empty_narration_is_rejected_before_queue(client, voice):
    pid, sid, _ = prepared(client)
    response = request_run(client, pid, sid)
    assert response.status_code == 422
    assert "未启用" in response.text
    assert configure(client, voice).status_code == 200
    response = request_run(client, pid, sid)
    assert response.status_code == 422
    assert "没有旁白" in response.text
    with SessionLocal() as session:
        assert session.query(GenerationRunRow).count() == 0


def test_malformed_voice_configuration_is_actionable(client, voice):
    Path(voice["modelPath"] + ".json").write_text("[]")
    response = configure(client, voice)
    assert response.status_code == 422
    assert "声音配置无效" in response.text


def test_narration_aligns_shots_without_truncation(voice, tmp_path, monkeypatch):
    monkeypatch.setattr(speech, "synthesize", lambda text, config, target: tone(target))
    result = speech.render_narration([{"id": "one", "voiceover": "测试", "durationMs": 1000},
                                      {"id": "two", "voiceover": "", "durationMs": 500}], voice, tmp_path)
    with wave.open(str(result)) as audio:
        assert audio.getnframes() == 33075
        raw = audio.readframes(audio.getnframes())
        assert any(raw[:8820])
        assert not any(raw[8820:])
    manifest = json.loads((tmp_path / "narration.json").read_text())
    assert manifest["segments"][1]["startMs"] == 1000
    assert manifest["segments"][0]["speechDurationMs"] == 200


def test_narration_overflow_and_changed_model_fail(voice, tmp_path, monkeypatch):
    monkeypatch.setattr(speech, "synthesize", lambda text, config, target: tone(target, 1.1))
    shots = [{"id": "one", "voiceover": "过长", "durationMs": 1000}]
    with pytest.raises(MediaGenerationError, match="未截断"):
        speech.render_narration(shots, voice, tmp_path)
    assert not (tmp_path / "narration.wav").exists()
    Path(voice["modelPath"]).write_bytes(b"changed")
    with pytest.raises(MediaGenerationError, match="已改变"):
        speech.render_narration(shots, voice, tmp_path)


def test_subprocess_is_bounded_and_failure_not_silent(voice, tmp_path, monkeypatch):
    def fail(command, **kwargs):
        assert kwargs["timeout"] == 60
        assert "--cuda" not in command
        assert "--input-file" in command
        raise subprocess.TimeoutExpired(command, 60)
    monkeypatch.setattr(speech.subprocess, "run", fail)
    with pytest.raises(MediaGenerationError, match="超时"):
        speech.synthesize("测试", voice, tmp_path / "test.wav")


@pytest.mark.parametrize("background", [False, True])
def test_narration_reaches_real_ffmpeg_output(client, voice, tmp_path, monkeypatch, background):
    assert configure(client, voice).status_code == 200
    pid, sid, _ = prepared(client)
    with_voiceover(sid)
    monkeypatch.setattr(speech, "synthesize", lambda text, config, target: tone(target))
    extra = {}
    if background:
        path = tmp_path / "bg.wav"
        tone(path)
        extra["audioAssetId"] = upload(client, pid, path.read_bytes(), "bg.wav", "audio/wav")["id"]
    response = request_run(client, pid, sid, **extra)
    assert response.status_code == 202, response.text
    run = wait_generation(client, response.json()["id"])
    assert run["audioMode"] == ("narration-background-mix" if background else "local-narration")
    with SessionLocal() as session:
        row = session.get(GenerationRunRow, run["id"])
        assert row.request_data["narration"]["modelSha256"] == voice["modelSha256"]
        artifact = session.get(ArtifactRow, run["finalArtifactId"])
        payload = subprocess.run(["ffmpeg", "-v", "error", "-i", artifact.path, "-map", "0:a", "-f", "s16le", "-ac", "1", "-ar", "22050", "pipe:1"], capture_output=True, check=True).stdout
        samples = struct.unpack(f"<{len(payload) // 2}h", payload)
        assert max(abs(value) for value in samples[:4410]) > 1000
        if not background:
            assert max(abs(value) for value in samples[22050:33075]) < 100
    assert client.get(f"/api/v1/artifacts/{run['finalArtifactId']}/content").status_code == 200


def test_overflow_fails_before_expensive_video_render(client, voice, monkeypatch):
    configure(client, voice)
    pid, sid, _ = prepared(client)
    with_voiceover(sid)
    monkeypatch.setattr(speech, "synthesize", lambda text, config, target: tone(target, 1.1))
    def forbidden(*args):
        raise AssertionError("Video must not render after speech overflow")
    monkeypatch.setattr(generation, "render_uploaded_shot", forbidden)
    run_id = request_run(client, pid, sid).json()["id"]
    for _ in range(100):
        run = client.get(f"/api/v1/generation-runs/{run_id}").json()
        if run["status"] == "failed":
            break
        time.sleep(0.1)
    assert "未截断" in run["errorMessage"]
    assert run["finalArtifactId"] is None
    assert all(shot["artifactId"] is None for shot in run["shotRuns"])


def test_composition_retry_reuses_succeeded_video_shots(client, voice, monkeypatch):
    configure(client, voice)
    pid, sid, _ = prepared(client)
    with_voiceover(sid)
    monkeypatch.setattr(speech, "synthesize", lambda text, config, target: tone(target))
    compose = generation.compose_uploaded_shots
    def fail(*args):
        raise MediaGenerationError("composition failure")
    monkeypatch.setattr(generation, "compose_uploaded_shots", fail)
    run_id = request_run(client, pid, sid).json()["id"]
    for _ in range(100):
        run = client.get(f"/api/v1/generation-runs/{run_id}").json()
        if run["status"] == "failed" and not generation.worker_has_run(run_id):
            break
        time.sleep(0.1)
    assert run["errorMessage"] == "composition failure"
    assert all(shot["status"] == "succeeded" for shot in run["shotRuns"])
    shot_ids = [shot["artifactId"] for shot in run["shotRuns"]]
    def forbidden(*args):
        raise AssertionError("Succeeded video must not be regenerated")
    monkeypatch.setattr(generation, "render_uploaded_shot", forbidden)
    monkeypatch.setattr(generation, "compose_uploaded_shots", compose)
    assert client.post(f"/api/v1/generation-runs/{run_id}/resumption").status_code == 202
    run = wait_generation(client, run_id)
    assert [shot["artifactId"] for shot in run["shotRuns"]] == shot_ids
