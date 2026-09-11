from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import monotonic, sleep
from uuid import uuid4

from sqlalchemy import select

from .config import get_settings
from .comfy_video import ComfyVideoClient, workflow
from .database import SessionLocal
from .media import MediaGenerationError, compose_uploaded_shots, render_uploaded_shot, probe_media
from .models import ArtifactRow, GenerationRunRow, ProjectRow
from .fal_video import FalVideoClient, VideoProviderError, download_video, image_input
from .secret_store import LocalEncryptedSecretStore
from .speech import narration_plan, render_narration
from .video_settings import read_settings, resolve_deployment, video_plan
from .blender import blender_plan, validate_glb, render_blender_shot, matching_process, cancel_blender


ACTIVE = ("queued", "running", "composing")
generation_lock = RLock()
_executor: ThreadPoolExecutor | None = None
_in_flight: set[str] = set()


def build_plan(project, storyboard, quality="standard", audio_asset_id=None, narration=False, shot_id=None) -> dict:
    shots = deepcopy(storyboard.data.get("shots", []))
    if not 1 <= len(shots) <= 12:
        raise ValueError("需要 1 至 12 个镜头")
    shot_numbers = {shot.get("id"): index for index, shot in enumerate(shots, 1) if isinstance(shot, dict)}
    if shot_id is not None:
        shots = [shot for shot in shots if isinstance(shot, dict) and shot.get("id") == shot_id]
        if len(shots) != 1:
            raise ValueError("试片镜头不存在或 ID 重复")
        if narration or audio_asset_id:
            raise ValueError("单镜头试片不混入旁白或背景音频，请在整片合成时添加")
    assets = {item["id"]: item for item in project.asset_versions}
    selected_assets = {}
    ids = set()
    for index, shot in enumerate(shots, 1):
        if not isinstance(shot, dict) or not isinstance(shot.get("id"), str) or shot["id"] in ids:
            raise ValueError("镜头 ID 缺失或重复")
        ids.add(shot["id"])
        index = shot_numbers[shot["id"]]
        duration = shot.get("durationMs")
        start = shot.get("sourceStartMs", 0)
        if type(duration) is not int or not 500 <= duration <= 15000 or type(start) is not int or not 0 <= start <= 3600000:
            raise ValueError(f"镜头 {index} 时长或素材入点无效")
        if len(str(shot.get("caption") or "")) > 40:
            raise ValueError(f"镜头 {index} 字幕超过 40 字，请精简为两行")
        if shot.get("fit", "contain") not in {"contain", "cover"}:
            raise ValueError(f"镜头 {index} 构图方式无效")
        strategy = shot.get("sourceStrategy")
        if strategy not in {"image-motion", "user-video", "image-to-video", "blender-3d"}:
            raise ValueError(f"镜头 {index} 的 {strategy or '未知'} 能力尚未接入；需要视频 Provider 或 Blender，未自动替换来源")
        source = assets.get(shot.get("sourceAssetId"))
        kind = "model" if strategy == "blender-3d" else "video" if strategy == "user-video" else "image"
        if not source or source.get("kind") != kind or source.get("status") != "ready":
            raise ValueError(f"镜头 {index} 需要选择本项目的{'GLB 三维' if kind == 'model' else '图片' if kind == 'image' else '视频'}素材")
        if not Path(source["uri"]).is_file():
            raise ValueError(f"镜头 {index} 的素材文件丢失")
        selected_assets[source["id"]] = deepcopy(source)
        if strategy == "blender-3d":
            if not 1000 <= duration <= 10000 or duration % 1000:
                raise ValueError("Blender 环绕镜头需为 1 至 10 秒的整数秒")
            if shot.get("blenderTemplate") != "orbit-360":
                raise ValueError("请选择 Blender 完整 360 度环绕模板；驾驶动作不能用此模板替代")
            validate_glb(Path(source["uri"]).read_bytes())
        if strategy == "image-to-video":
            prompt = shot.get("videoPrompt", "")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2500:
                raise ValueError(f"镜头 {index} 需填写视频提示词（最多 2500 字）")
            image_input(source)
    if sum(shot["durationMs"] for shot in shots) > 60000:
        raise ValueError("MVP 成片最长 60 秒")
    audio = assets.get(audio_asset_id) if audio_asset_id else None
    if audio_asset_id and (not audio or audio.get("kind") != "audio" or audio.get("status") != "ready"):
        raise ValueError("背景音频必须来自本项目的已上传音频")
    width, height = (540, 960) if quality == "preview" else (1080, 1920)
    video_shots = [shot for shot in shots if shot["sourceStrategy"] == "image-to-video"]
    with SessionLocal() as session:
        video = video_plan(session, video_shots) if video_shots else None
        speech = narration_plan(read_settings(session), shots) if narration else None
        blender = blender_plan(read_settings(session)) if any(s["sourceStrategy"] == "blender-3d" for s in shots) else None
    return {"shots": shots, "assets": selected_assets, "audio": deepcopy(audio),
            "scope": "shot-preview" if shot_id is not None else "full-video",
            "narration": speech,
            "blender": blender,
            "video": video, "mode": ("local-ai-video" if video.get("backend") == "comfyui" else "ai-video") if video else "local-blender" if blender else "uploaded-media",
            "audioMode": ("narration-background-mix" if audio else "local-narration") if speech else ("background-mix" if audio else "source-audio-or-silence"),
            "output": {"width": width, "height": height, "fps": 30}, "quality": quality}


def readiness(project, storyboard) -> dict:
    if not storyboard:
        return {"ready": False, "mode": "uploaded-media", "reason": "尚未生成分镜"}
    try:
        plan = build_plan(project, storyboard)
    except (ValueError, KeyError, TypeError, VideoProviderError, MediaGenerationError) as error:
        return {"ready": False, "mode": "capability-or-asset-missing", "reason": str(error)}
    return {"ready": True, "mode": plan["mode"], "reason": None,
            "estimatedUsd": plan["video"]["estimatedUsd"] if plan["video"] else None}


def start_worker() -> None:
    global _executor
    with generation_lock:
        with SessionLocal() as session:
            for run in session.scalars(select(GenerationRunRow).where(GenerationRunRow.status.in_(ACTIVE))):
                run.status = "interrupted"
                run.error_message = "服务曾中断，可恢复未完成镜头；已有上游任务会继续查询，不自动重复提交"
                project = session.get(ProjectRow, run.project_id)
                if project and (run.request_data or {}).get("scope") != "shot-preview":
                    project.status = "needs_attention"
            session.commit()
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="media-worker")


def stop_worker() -> None:
    global _executor
    if _executor:
        _executor.shutdown(wait=True, cancel_futures=True)
        _executor = None


def submit_run(run_id: str) -> None:
    if not _executor:
        raise RuntimeError("Media worker is not started")
    _in_flight.add(run_id)
    future = _executor.submit(_execute, run_id)
    future.add_done_callback(lambda _: _release_run(run_id))


def _release_run(run_id: str) -> None:
    with generation_lock:
        _in_flight.discard(run_id)


def worker_has_run(run_id: str) -> bool:
    return run_id in _in_flight


def latest_shots(run) -> list[dict]:
    latest = {shot["shotId"]: shot for shot in run.shot_runs}
    return [latest[shot["id"]] for shot in run.request_data["shots"]]


def live_blender_run(session, exclude=None):
    for run in session.scalars(select(GenerationRunRow)):
        if run.id != exclude and (run.request_data or {}).get("blender"):
            if any(matching_process(shot.get("blenderHandle")) for shot in run.shot_runs):
                return run.id
    return None


def _render_blender(run_id, attempt_id, request, shot, target):
    with generation_lock, SessionLocal() as session:
        run = session.get(GenerationRunRow, run_id)
        current = next(s for s in run.shot_runs if s["id"] == attempt_id)
        handle, started = current.get("blenderHandle"), current.get("blenderStarted", False)
        directory = Path(current.get("blenderDirectory") or target.parent / f"blender-{attempt_id}").resolve()
        if not started and not read_settings(session)["blenderEnabled"]:
            raise MediaGenerationError("Blender 已停用，未启动新渲染")
    def record(handle, started):
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            _update_shot(run, attempt_id, blenderHandle=handle, blenderStarted=started, blenderDirectory=str(directory))
            session.commit()
    def cancelled():
        with SessionLocal() as session:
            return session.get(GenerationRunRow, run_id).status == "cancelled"
    def progress(count):
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            _update_shot(run, attempt_id, renderedFrames=count, totalFrames=round(shot["durationMs"] * request["output"]["fps"] / 1000))
            session.commit()
    try:
        return render_blender_shot(request["assets"][shot["sourceAssetId"]], shot, request["output"], request["blender"],
                                   target, directory, handle, started, record, cancelled, progress)
    except Exception:
        with SessionLocal() as session:
            current = next(s for s in session.get(GenerationRunRow, run_id).shot_runs if s["id"] == attempt_id)
            cancel_blender(current.get("blenderHandle"))
        raise


def _artifact(run, target, metadata, shot_id=None) -> ArtifactRow:
    return ArtifactRow(id=target.stem, project_id=run.project_id, generation_run_id=run.id,
                       shot_id=shot_id, type="shot-video" if shot_id else "final-video", mime_type="video/mp4",
                       path=str(target.resolve()), size_bytes=metadata["sizeBytes"], sha256=metadata["sha256"],
                       width=metadata["width"], height=metadata["height"], duration_ms=metadata["durationMs"])


def _update_shot(run, attempt_id, **fields) -> None:
    run.shot_runs = [{**shot, **fields} if shot["id"] == attempt_id else shot for shot in run.shot_runs]


def _render_video(run_id, attempt_id, request, shot, target):
    if request["video"].get("backend") == "comfyui":
        return _render_local_video(run_id, attempt_id, request, shot, target)
    with generation_lock, SessionLocal() as session:
        run = session.get(GenerationRunRow, run_id)
        current = next(s for s in run.shot_runs if s["id"] == attempt_id)
        handle = current.get("providerHandle")
        if not get_settings().allow_external_models:
            raise VideoProviderError("当前环境禁止外部模型调用")
        deployment, credential = resolve_deployment(session, request["video"]["deploymentId"])
        if deployment.physical_model_id != request["video"]["physicalModelId"] or credential.id != request["video"]["credentialId"]:
            raise VideoProviderError("视频部署配置已改变，请恢复原配置后继续任务")
        key = LocalEncryptedSecretStore(get_settings().data_dir / "secrets").get(credential.secret_ref)
        client = FalVideoClient(key)
        if not handle:
            if current.get("submissionState") in {"submitting", "unknown"}:
                raise VideoProviderError("上次提交结果不明，需在供应商后台核对；当前任务禁止自动重提", "SUBMISSION_UNKNOWN")
            if not read_settings(session)["enabled"]:
                raise VideoProviderError("视频执行已停用，不再提交新镜头")
            if run.status == "cancelled":
                return None
            # Persist intent before the billable POST; a crash cannot trigger a blind resubmit.
            _update_shot(run, attempt_id, submissionState="submitting")
            session.commit()
    if not handle:
        try:
            handle = client.submit(image_input(request["assets"][shot["sourceAssetId"]]), shot["videoPrompt"], shot["durationMs"] // 1000)
        except VideoProviderError as error:
            with generation_lock, SessionLocal() as session:
                run = session.get(GenerationRunRow, run_id)
                _update_shot(run, attempt_id, submissionState="rejected" if error.code == "REQUEST_REJECTED" else "unknown")
                session.commit()
            raise
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            _update_shot(run, attempt_id, providerHandle=handle, providerRequestId=handle["requestId"], submissionState="submitted")
            session.commit()
    deadline = monotonic() + 600
    while monotonic() < deadline:
        with generation_lock, SessionLocal() as session:
            if session.get(GenerationRunRow, run_id).status == "cancelled":
                return None
        try:
            status = client.status(handle)
        except VideoProviderError as error:
            if error.code == "GENERATION_FAILED":
                with generation_lock, SessionLocal() as session:
                    run = session.get(GenerationRunRow, run_id)
                    _update_shot(run, attempt_id, providerStatus="FAILED")
                    session.commit()
            raise
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            _update_shot(run, attempt_id, providerStatus=status)
            session.commit()
        if status == "COMPLETED":
            break
        sleep(2)
    else:
        raise VideoProviderError("等待视频超过 10 分钟，可恢复任务继续查询；未重复提交", "POLL_TIMEOUT")
    asset = download_video(client.result_url(handle), target.with_suffix(".source.mp4"))
    return render_uploaded_shot(asset, {**shot, "sourceStrategy": "user-video", "sourceStartMs": 0}, request["output"], target)


def _render_local_video(run_id, attempt_id, request, shot, target):
    config = request["video"]
    if not get_settings().allow_local_models:
        raise VideoProviderError("当前环境禁止本地模型访问")
    client = ComfyVideoClient(config["localUrl"])
    with generation_lock, SessionLocal() as session:
        run = session.get(GenerationRunRow, run_id)
        current = next(s for s in run.shot_runs if s["id"] == attempt_id)
        handle = current.get("providerHandle")
        if run.status == "cancelled":
            return None
        if not handle:
            live = read_settings(session)
            if not live["enabled"] or live["backend"] != "comfyui" or live["localUrl"] != config["localUrl"]:
                raise VideoProviderError("本地执行已关闭或地址改变，请恢复原配置后继续")
    if not handle:
        check = client.probe()
        if not check["ready"]:
            raise VideoProviderError("本地节点或模型缺失：" + ", ".join(check["missing"]))
        prompt_id = str(uuid4())
        seed = int(uuid4().hex[:12], 16)
        image = client.upload(request["assets"][shot["sourceAssetId"]], prompt_id)
        reference = probe_media(Path(request["assets"][shot["sourceAssetId"]]["uri"]))
        graph = workflow(config, shot, image, prompt_id, seed, (reference["width"], reference["height"]))
        handle = {"requestId": prompt_id, "baseUrl": config["localUrl"]}
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            if run.status == "cancelled":
                return None
            # A known id is stored before submission, so even an ambiguous POST can be queried.
            _update_shot(run, attempt_id, providerHandle=handle, providerRequestId=prompt_id,
                         submissionState="submitting", seed=seed, nativeWidth=config["width"], nativeHeight=config["height"])
            session.commit()
        try:
            client.submit(graph, prompt_id)
        except VideoProviderError as error:
            with generation_lock, SessionLocal() as session:
                run = session.get(GenerationRunRow, run_id)
                _update_shot(run, attempt_id, submissionState="rejected" if error.code == "REQUEST_REJECTED" else "unknown",
                             providerStatus="FAILED" if error.code == "REQUEST_REJECTED" else "UNKNOWN")
                session.commit()
            raise
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            _update_shot(run, attempt_id, submissionState="submitted")
            session.commit()
    started = monotonic()
    while monotonic() - started < config["timeoutSeconds"]:
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            cancelled = run.status == "cancelled"
        if cancelled:
            if request.get("blender"):
                with SessionLocal() as session:
                    for shot in session.get(GenerationRunRow, run_id).shot_runs:
                        cancel_blender(shot.get("blenderHandle"))
            client.cancel(handle["requestId"])
            with generation_lock, SessionLocal() as session:
                run = session.get(GenerationRunRow, run_id)
                run.error_message = "已向本地服务发送定向取消请求；恢复任务会查询原任务状态。"
                session.commit()
            return None
        state, output = client.status(handle["requestId"])
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            _update_shot(run, attempt_id, providerStatus=state, elapsedSeconds=round(monotonic() - started))
            session.commit()
        if state == "FAILED":
            raise VideoProviderError("本地模型生成失败或已中断，请检查 ComfyUI 日志、显存和权重后重做镜头")
        if state == "MISSING":
            raise VideoProviderError("本地服务未找到原任务，可能曾重启或清理历史；未自动重提，请核对后手动重做镜头")
        if state == "COMPLETED":
            asset = client.download(output, target.with_suffix(".source.mp4"))
            if asset["durationMs"] + 100 < shot["durationMs"]:
                raise VideoProviderError("本地片段短于分镜要求，未使用静帧补足")
            return render_uploaded_shot(asset, local_composition_shot(request, shot), request["output"], target)
        sleep(2)
    raise VideoProviderError("本地生成等待超时，可继续任务查询原结果，未自动重复提交")


def local_composition_shot(request, shot):
    result = {**shot, "sourceStrategy": "user-video", "sourceStartMs": 0}
    if shot.get("fit", "contain") != "contain":
        return result
    info = probe_media(Path(request["assets"][shot["sourceAssetId"]]["uri"]))
    width, height = request["video"]["width"], request["video"]["height"]
    ratio = min(width / info["width"], height / info["height"])
    w, h = max(1, round(info["width"] * ratio)), max(1, round(info["height"] * ratio))
    if w != width or h != height:
        result.update(sourceCrop=[(width - w) // 2, (height - h) // 2, w, h], backgroundFill="soft")
    return result


def _execute(run_id: str) -> None:
    attempt_id = None
    try:
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            if not run or run.status not in {"queued", "cancelled"}:
                return
            request = deepcopy(run.request_data)
            cancelled = run.status == "cancelled"
            handles = [s["providerHandle"] for s in latest_shots(run) if s["status"] == "cancelled" and s.get("providerHandle")]
            if not cancelled:
                run.status = "running"
            session.commit()
        if cancelled:
            if (request.get("video") or {}).get("backend") == "comfyui" and get_settings().allow_local_models:
                client = ComfyVideoClient(request["video"]["localUrl"])
                for handle in handles:
                    client.cancel(handle["requestId"])
            return
        directory = get_settings().data_dir / "artifacts" / run_id
        narration = render_narration(request["shots"], request["narration"], directory) if request.get("narration") else None
        paths = []
        for shot in request["shots"]:
            with generation_lock, SessionLocal() as session:
                run = session.get(GenerationRunRow, run_id)
                if run.status == "cancelled":
                    return
                current = next(item for item in latest_shots(run) if item["shotId"] == shot["id"])
                prior = session.get(ArtifactRow, current.get("artifactId")) if current.get("artifactId") else None
                if current["status"] == "succeeded" and prior and Path(prior.path).is_file():
                    paths.append(Path(prior.path))
                    continue
                attempt_id = current["id"]
                _update_shot(run, attempt_id, status="running", errorMessage=None)
                session.commit()
            target = directory / f"{uuid4()}.mp4"
            if shot["sourceStrategy"] == "image-to-video":
                metadata = _render_video(run_id, attempt_id, request, shot, target)
                if metadata is None:
                    return
            elif shot["sourceStrategy"] == "blender-3d":
                metadata = _render_blender(run_id, attempt_id, request, shot, target)
                if metadata is None:
                    return
            else:
                metadata = render_uploaded_shot(request["assets"][shot["sourceAssetId"]], shot, request["output"], target)
            with generation_lock, SessionLocal() as session:
                run = session.get(GenerationRunRow, run_id)
                if run.status == "cancelled":
                    return
                session.add(_artifact(run, target, metadata, shot["id"]))
                _update_shot(run, attempt_id, status="succeeded", artifactId=target.stem)
                session.commit()
            paths.append(target)
        if request.get("scope") == "shot-preview":
            with generation_lock, SessionLocal() as session:
                run = session.get(GenerationRunRow, run_id)
                if run.status != "cancelled":
                    run.status = "completed"
                    run.error_message = None
                    session.commit()
            return
        attempt_id = None
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            if run.status == "cancelled":
                return
            run.status = "composing"
            session.commit()
        target = directory / f"{uuid4()}.mp4"
        metadata = compose_uploaded_shots(paths, request["shots"], request["output"], target, request.get("audio"), narration)
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            if run.status == "cancelled":
                return
            session.add(_artifact(run, target, metadata))
            run.status = "completed"
            run.final_artifact_id = target.stem
            run.error_message = None
            session.get(ProjectRow, run.project_id).status = "completed"
            session.commit()
    except Exception as error:
        message = str(error) if isinstance(error, MediaGenerationError) else "媒体任务失败，请检查素材后重试"
        with generation_lock, SessionLocal() as session:
            run = session.get(GenerationRunRow, run_id)
            if run and run.status != "cancelled":
                run.status = "failed"
                run.error_message = message
                if attempt_id:
                    _update_shot(run, attempt_id, status="failed", errorMessage=message)
                if (run.request_data or {}).get("scope") != "shot-preview":
                    session.get(ProjectRow, run.project_id).status = "needs_attention"
                session.commit()
