"""Shared, persisted credential cooldowns for the single-process internal MVP."""

from datetime import UTC, datetime, timedelta
from math import ceil
from threading import RLock

from sqlalchemy import select

from .models import ModelCooldownRow, ModelInvocationRow
from .openai_compatible import OpenAICompatibleError

lock = RLock()


def check(session, credential_id):
    row = session.get(ModelCooldownRow, credential_id, populate_existing=True)
    if not row:
        return
    if row.error_code == "QUOTA_EXCEEDED":
        raise OpenAICompatibleError("模型凭据因 HTTP 429 额度不足已暂停，未发送请求；请处理额度并在管理后台更新凭据后重试", "QUOTA_EXCEEDED")
    until = row.blocked_until.replace(tzinfo=row.blocked_until.tzinfo or UTC)
    remaining = ceil((until - datetime.now(UTC)).total_seconds())
    if remaining > 0:
        raise OpenAICompatibleError(f"模型凭据仍在 HTTP 429 冷却期，未发送请求；请在 {remaining} 秒后手动重试", "RATE_LIMITED", remaining)


def record(session, credential_id, error):
    with lock:
        row = session.get(ModelCooldownRow, credential_id, populate_existing=True)
        until = None if error.code == "QUOTA_EXCEEDED" else datetime.now(UTC) + timedelta(seconds=error.retry_after_seconds or 60)
        if row:
            if row.error_code == "QUOTA_EXCEEDED":
                return
            if until and row.blocked_until:
                until = max(until, row.blocked_until.replace(tzinfo=row.blocked_until.tzinfo or UTC))
            row.error_code, row.blocked_until = error.code, until
        else:
            session.add(ModelCooldownRow(credential_id=credential_id, error_code=error.code, blocked_until=until))
        session.commit()


def info(session, credential_id):
    try:
        check(session, credential_id)
    except OpenAICompatibleError as error:
        return {"errorCode": error.code, "message": str(error), "retryAfterSeconds": error.retry_after_seconds}
    return None


def recover_interrupted_calls(session):
    for row in session.scalars(select(ModelInvocationRow).where(ModelInvocationRow.status == "calling")):
        row.status = "failed"
        row.error_code = "SERVICE_INTERRUPTED"
        row.redacted_output = "服务重启前的模型请求未完成，未自动重新发送"
    session.commit()
