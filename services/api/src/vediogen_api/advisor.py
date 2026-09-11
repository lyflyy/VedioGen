from concurrent.futures import Future
from copy import deepcopy
import hashlib
import json
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .gateway import ModelGatewayError, _media_execution_context, generate_creative_advice
from .models import AdvisorRunRow, ProjectRow, RoutingVersionRow
from .serializers import advisor_run


# The internal MVP runs one API process. Do not hold a database write lock
# across provider I/O; duplicate HTTP requests share the same outcome instead.
_lock = Lock()
_inflight: dict[str, tuple[str, Future]] = {}
_input_fields = (
    "id", "title", "content_pack_id", "content_pack_version", "mode",
    "target_platform", "locale", "messages", "facts", "asset_versions",
)


def _fingerprint(session: Session, project: ProjectRow) -> str:
    route = session.scalar(select(RoutingVersionRow).where(
        RoutingVersionRow.status == "published").order_by(RoutingVersionRow.version.desc()))
    data = {field: getattr(project, field) for field in _input_fields}
    data["executionContext"] = _media_execution_context(session, project)
    data["routingVersionId"] = route.id if route else None
    data["contractVersion"] = 1
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _unwrap(outcome: tuple[int, dict]) -> dict:
    status, body = outcome
    if status != 202:
        headers = {"Retry-After": str(body["retryAfter"])} if body.get("retryAfter") else None
        raise HTTPException(status, body["detail"], headers=headers)
    return deepcopy(body)


def create_advice(session: Session, project_id: str) -> dict:
    with _lock:
        project = session.get(ProjectRow, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        session.refresh(project)
        fingerprint = _fingerprint(session, project)
        active = _inflight.get(project_id)
        if active:
            if active[0] != fingerprint:
                raise HTTPException(409, "上一轮创意建议仍在生成，请等待结束后再提交新要求")
            future = active[1]
            owner = False
        else:
            previous = session.get(AdvisorRunRow, project.latest_advisor_run_id) if project.latest_advisor_run_id else None
            if previous and previous.status == "completed" and previous.input_fingerprint == fingerprint:
                return advisor_run(previous)
            future = Future()
            _inflight[project_id] = (fingerprint, future)
            owner = True
            snapshot = ProjectRow(**{field: deepcopy(getattr(project, field)) for field in _input_fields})
    # Release the read transaction while waiting for another request/provider.
    session.rollback()
    if not owner:
        return _unwrap(future.result())

    outcome = (500, {"detail": "创意建议执行失败，请重试"})
    try:
        result = generate_creative_advice(session, snapshot)
        run = AdvisorRunRow(id=str(uuid4()), project_id=project_id, result=result,
                            status="completed", input_fingerprint=fingerprint)
        session.add(run)
        project = session.get(ProjectRow, project_id)
        session.refresh(project)
        unchanged = _fingerprint(session, project) == fingerprint
        if unchanged:
            project.latest_advisor_run_id = run.id
            project.status = "advising"
        # Preserve the billed result even when new input makes it obsolete.
        session.commit()
        outcome = (202, advisor_run(run)) if unchanged else (
            409, {"detail": "生成期间项目输入或模型配置已变化，旧结果已保留，请按最新输入重新生成"})
    except ModelGatewayError as error:
        session.rollback()
        outcome = (429 if error.code in {"RATE_LIMITED", "QUOTA_EXCEEDED"} else 502,
                   {"detail": str(error), "retryAfter": error.retry_after_seconds})
    finally:
        with _lock:
            future.set_result(outcome)
            _inflight.pop(project_id, None)
    return _unwrap(outcome)
