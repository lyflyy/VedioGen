"""Explicit relay diagnostic respecting cooldown; never print secrets or raw upstream messages."""
import os
import re
import json
import sys

os.environ["VEDIOGEN_DATABASE_URL"] = "sqlite:///./.data/internal-mvp/vediogen.db"
os.environ["VEDIOGEN_DATA_DIR"] = "./.data/internal-mvp"

import httpx
from vediogen_api.database import SessionLocal
from vediogen_api.models import ModelDeploymentRow, ModelProviderRow, ModelCredentialRow
from vediogen_api.gateway import secret_store
from vediogen_api import model_backoff
from vediogen_api.openai_compatible import _raise_for_status, OpenAICompatibleError

with SessionLocal() as session:
    deployment = session.get(ModelDeploymentRow, "217777e3-04d4-475e-83bf-162078197acc")
    provider = session.get(ModelProviderRow, deployment.provider_id)
    credential = session.get(ModelCredentialRow, deployment.credential_id)
    model_backoff.check(session, credential.id)
    headers = {"Authorization": "Bearer " + secret_store.get(credential.secret_ref)}
    if "--completion" in sys.argv:
        response = httpx.post(provider.base_url.rstrip("/") + "/chat/completions", headers=headers,
            json={"model": deployment.physical_model_id, "messages": [{"role": "user", "content": "Reply OK."}], "max_completion_tokens": 32}, timeout=60)
    else:
        response = httpx.get(provider.base_url.rstrip("/") + "/models", headers=headers, timeout=30)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error", {})
    error = error if isinstance(error, dict) else {}
    tags = {key: value for key in ("code", "type") if isinstance(value := error.get(key), str)
        and re.fullmatch(r"[a-zA-Z0-9_.-]{1,70}", value)}
    message = str(error.get("message", ""))
    categories = [word for word in ("quota", "balance", "rate", "limit", "额度", "余额", "渠道", "频率") if word in message.lower()]
    print(json.dumps({"httpStatus": response.status_code, "isJson": bool(payload), "errorTags": tags,
        "errorCategories": categories, "modelPresent": any(m.get("id") == deployment.physical_model_id for m in payload.get("data", []))}, ensure_ascii=False))
    try:
        _raise_for_status(response)
    except OpenAICompatibleError as exc:
        if exc.code in {"RATE_LIMITED", "QUOTA_EXCEEDED"}:
            model_backoff.record(session, credential.id, exc)
