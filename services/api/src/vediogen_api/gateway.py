import json
import hashlib
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from . import model_backoff
from .fixtures import build_advisor_result, build_storyboard
from .model_contracts import ADVISOR_WIRE_SCHEMA, STORYBOARD_WIRE_SCHEMA, advisor_system_prompt, storyboard_system_prompt
from .models import DocumentRow, ModelCredentialRow, ModelDeploymentRow, ModelInvocationRow, ModelProviderRow, ProjectRow, RoutingVersionRow
from .openai_compatible import OpenAICompatibleError, StructuredCompletion, complete_json
from .secret_store import LocalEncryptedSecretStore
from .video_settings import read_settings


class ModelGatewayError(RuntimeError):
    def __init__(self, message, code="PROVIDER_ERROR", retry_after_seconds=None):
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


secret_store = LocalEncryptedSecretStore(get_settings().data_dir / "secrets")
spec_dir = Path(__file__).resolve().parents[4] / "docs" / "specs"


def _media_execution_context(session: Session, project: ProjectRow) -> dict[str, Any]:
    config = read_settings(session)
    local = config["backend"] == "comfyui"
    return {
        "inputMode": "with-assets" if project.asset_versions else "text-only",
        "assetPreparationOwner": "platform",
        "referenceSearchAllowed": get_settings().allow_external_search,
        "imageToVideo": {
            "backend": config["backend"],
            "enabled": config["enabled"],
            "callsAllowed": get_settings().allow_local_models if local else get_settings().allow_external_models,
            "durationOptionsMs": None if local else [5000, 10000],
            "durationRangeMs": {"min": 500, "max": 5000} if local else None,
            "durationAdaptation": "Editorial milliseconds are preserved; the platform rounds up model frames and trims output." if local else "Use one of durationOptionsMs.",
            "requiresConfirmedReference": True,
            "verification": "configuration-only; not proof of model readiness or output quality",
        },
        "implementedMediaStrategies": ["image-motion", "user-video", "image-to-video", "blender-3d"],
        "unimplementedMediaStrategies": ["generated-video", "stock-video"],
        "blender": {"enabled": config["blenderEnabled"], "callsAllowed": get_settings().allow_local_models,
                    "template": "orbit-360", "requires": "accurate self-contained GLB asset prepared by platform",
                    "durationOptionsMs": list(range(1000, 10001, 1000)), "subjectIdentityVerified": False},
    }


def extract_asset_brief(session: Session, project: ProjectRow, messages: list[dict]) -> dict[str, Any]:
    schema = {"type": "object", "additionalProperties": False, "required": ["subject", "requiredShots", "clarification"], "properties": {
        "subject": {"type": "string", "maxLength": 100},
        "requiredShots": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 500}},
        "clarification": {"type": "string", "maxLength": 300},
    }}

    def fake():
        return {"subject": "", "requiredShots": [], "clarification": "隔离测试未调用真实模型；请填写要检索的主体名称"}

    def real(provider, deployment, api_key):
        completion = complete_json(base_url=provider.base_url, api_key=api_key, model_id=deployment.physical_model_id,
            schema_name="vediogen_asset_brief", schema=schema,
            system_prompt="从用户描述提取素材主体与镜头要求。subject 必须是用户原文中的完整主体名称，不得用搜索联想替换品牌型号。不能把标题整句当车型。requiredShots 按用户指定顺序保留动作、细节和结尾。若有多款车或主体不明确，subject 留空并只提出一个消歧问题；其他情况 clarification 留空。只提取，不声称已经联网核实、找到图片或确认结构。",
            user_prompt=json.dumps({"messages": messages}, ensure_ascii=False), timeout_seconds=deployment.timeout_seconds)
        Draft202012Validator(schema).validate(completion.value)
        return completion.value, completion

    return _invoke_routed(session, "asset-planner", project.id, project.title, fake, real)


def generate_creative_advice(session: Session, project: ProjectRow) -> dict[str, Any]:
    fact_ids = [item["id"] for item in project.facts]

    def fake() -> dict[str, Any]:
        return build_advisor_result(project.id, project.title, fact_ids)

    def real(provider: ModelProviderRow, deployment: ModelDeploymentRow, api_key: str) -> tuple[dict[str, Any], StructuredCompletion]:
        prompt = "请为以下项目提出三个可比较的创意方向。不要照抄用户，而要给出专业判断。\n" + json.dumps(
            {
                "projectId": project.id,
                "title": project.title,
                "mode": project.mode,
                "targetPlatform": project.target_platform,
                "locale": project.locale,
                "executionContext": _media_execution_context(session, project),
                "facts": [{"key": item.get("key"), "value": item.get("value"), "status": item.get("status")} for item in project.facts],
                "messages": [{"role": item.get("role"), "text": item.get("text")} for item in project.messages],
                "uploadedAssets": [
                    {"fileName": item.get("fileName"), "mimeType": item.get("mimeType"), "kind": item.get("kind")}
                    for item in project.asset_versions
                ],
            },
            ensure_ascii=False,
        )
        completion = complete_json(
            base_url=provider.base_url,
            api_key=api_key,
            model_id=deployment.physical_model_id,
            schema_name="vediogen_creative_advisor",
            schema=ADVISOR_WIRE_SCHEMA,
            system_prompt=advisor_system_prompt(),
            user_prompt=prompt,
            image_assets=project.asset_versions,
            timeout_seconds=deployment.timeout_seconds,
        )
        result = _canonical_advisor(project, completion.value)
        _validate_spec("creative-advisor.schema.json", result)
        return result, completion

    return _invoke_routed(session, "creative-advisor", project.id, project.title, fake, real)


def generate_storyboard(session: Session, project: ProjectRow, brief: DocumentRow, version: int) -> dict[str, Any]:
    def fake() -> dict[str, Any]:
        return build_storyboard(project.id, brief.id, project.title, version)

    def real(provider: ModelProviderRow, deployment: ModelDeploymentRow, api_key: str) -> tuple[dict[str, Any], StructuredCompletion]:
        prompt = "请把已确认的 Creative Brief 转换为完整旁白和可执行分镜。\n" + json.dumps(
            {
                "project": {"id": project.id, "title": project.title, "mode": project.mode, "platform": project.target_platform},
                "creativeBrief": brief.data,
                "executionContext": _media_execution_context(session, project),
                "userMessages": [{"text": item.get("text")} for item in project.messages],
                "assets": [{"fileName": item.get("fileName"), "mimeType": item.get("mimeType")} for item in project.asset_versions],
            },
            ensure_ascii=False,
        )
        completion = complete_json(
            base_url=provider.base_url,
            api_key=api_key,
            model_id=deployment.physical_model_id,
            schema_name="vediogen_storyboard",
            schema=STORYBOARD_WIRE_SCHEMA,
            system_prompt=storyboard_system_prompt(),
            user_prompt=prompt,
            image_assets=project.asset_versions,
            timeout_seconds=deployment.timeout_seconds,
        )
        Draft202012Validator(STORYBOARD_WIRE_SCHEMA).validate(completion.value)
        return _runtime_storyboard(project, brief, version, completion.value), completion

    return _invoke_routed(session, "storyboard-generator", project.id, project.title, fake, real)


def observe_reference_images(session, project, assets):
    route = session.scalar(select(RoutingVersionRow).where(RoutingVersionRow.status == "published").order_by(RoutingVersionRow.version.desc()))
    deployments = [(d.id, d.physical_model_id, d.provider_id) for d in session.scalars(select(ModelDeploymentRow))]
    observations = []
    for offset in range(0, len(assets), 4):
        batch = assets[offset:offset + 4]
        if any(a.get("mimeType") not in {"image/jpeg", "image/png", "image/webp", "image/gif"}
               or not Path(a["uri"]).is_file() or Path(a["uri"]).stat().st_size > 20 * 1024 * 1024 for a in batch):
            raise ModelGatewayError("候选图片无法提交视觉检查，请准备 20 MB 以内的受支持图片", "REFERENCE_INVALID")
        fingerprint = {"revision": "visual-reference-v1", "route": route.bindings if route else None,
            "deployments": deployments, "assets": [{"id": a["id"], "digest": hashlib.sha256(Path(a["uri"]).read_bytes()).hexdigest(),
                "subject": a.get("subject"), "context": a.get("referenceContext")} for a in batch]}
        cache_key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cached = next((r for r in session.scalars(select(DocumentRow).where(DocumentRow.project_id == project.id,
            DocumentRow.kind == "reference-observation")) if r.data.get("cacheKey") == cache_key), None)
        if cached:
            observations.extend(cached.data["observations"])
            continue
        schema = {"type": "object", "additionalProperties": False, "required": ["observations"], "properties": {
            "observations": {"type": "array", "minItems": len(batch), "maxItems": len(batch), "items": {
                "type": "object", "additionalProperties": False, "required": ["assetId", "description", "limitations"], "properties": {
                    "assetId": {"type": "string", "enum": [a["id"] for a in batch]},
                    "description": {"type": "string"}, "limitations": {"type": "string"}}}}}}
        def fake():
            return {"observations": [{"assetId": a["id"], "description": "隔离测试参考图", "limitations": "非真实视觉检查"} for a in batch]}
        def real(provider, deployment, key):
            completion = complete_json(base_url=provider.base_url, api_key=key, model_id=deployment.physical_model_id,
                schema_name="vediogen_reference_observation", schema=schema,
                system_prompt="逐张观察附图，按输入ID返回且不重复。描述真实可见的主体、配色、视角、部件、人物服装、构图与运动空间。声明模糊、裁切、文字不可读等限制。名称和来源是参考信息而非视觉证据；不能由相似外观认证精确型号、生成看不见的背面或把照片当视频。用简体中文，不确定内容标未知。",
                user_prompt=json.dumps([{k: a.get(k) for k in ("id", "subject", "referenceContext")} for a in batch], ensure_ascii=False),
                image_assets=batch, timeout_seconds=deployment.timeout_seconds)
            Draft202012Validator(schema).validate(completion.value)
            if {o["assetId"] for o in completion.value["observations"]} != {a["id"] for a in batch}:
                raise ValidationError("参考图检查未覆盖本批全部素材")
            return completion.value, completion
        result = _invoke_routed(session, "asset-matcher", project.id, project.title, fake, real)
        session.add(DocumentRow(id=str(uuid4()), project_id=project.id, kind="reference-observation", version=1,
            status="completed", data={"cacheKey": cache_key, "observations": result["observations"]}))
        session.commit()
        observations.extend(result["observations"])
    return observations


def match_storyboard_assets(session, project, shots, assets):
    observations = observe_reference_images(session, project, assets)
    schema = {"type": "object", "additionalProperties": False, "required": ["assignments", "soundPlan"], "properties": {
        "soundPlan": {"type": "object", "additionalProperties": False, "required": ["background", "narration"], "properties": {
            "background": {"type": "string", "enum": ["none", "local-pulse"]}, "narration": {"type": "boolean"}}},
        "assignments": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["shotId", "assetId", "reason", "strategy", "needsPreview", "blocker", "exactOrbit"], "properties": {
                "shotId": {"type": "string", "enum": [s["id"] for s in shots]},
                "assetId": {"type": ["string", "null"], "enum": [None, *[a["id"] for a in assets]]},
                "reason": {"type": "string"}, "strategy": {"type": "string", "enum": ["image-motion", "image-to-video", "blender-3d"]},
                "needsPreview": {"type": "boolean"}, "blocker": {"type": "string"}, "exactOrbit": {"type": "boolean"}}}}}}
    def fake():
        return {"assignments": [{"shotId": shot["id"], "assetId": shot.get("sourceAssetId") if shot.get("selectionOwner") == "user" else assets[i % len(assets)]["id"],
            "reason": "隔离测试素材匹配"} for i, shot in enumerate(shots)]}
    def real(provider, deployment, key):
        completion = complete_json(base_url=provider.base_url, api_key=key, model_id=deployment.physical_model_id,
            schema_name="vediogen_asset_matching", schema=schema,
            system_prompt="根据逐张视觉观察和项目目标，为每个镜头选择参考与制作方式。只返回已有ID，每镜一项。品牌型号以明确来源为依据、视觉观察用于排除错配；同主体同配色优先。无匹配素材返回null，不拿其他车辆或骑手图片填空。细节、仪表读数与静态展示优先image-motion保真；实际动作需要image-to-video并needsPreview=true；准确完整360度必须exactOrbit=true及blender-3d，blocker说明需准确GLB或真实环绕视频。有限角度不算精确360度。用户明确只用图片则保留，不升级模型；不得改变镜头要求。用户固定的素材只要适合当前镜头就返回原ID，不能因为有更优候选就当作冲突；确实不匹配时blocker描述冲突。无阻断时blocker留空，不把普通风险全部当阻断。理由简洁中文，说明选路与风险。声音计划：摩托车宣传展示推荐local-pulse本地电子节奏，它不是车型真实引擎录音；用户要求无音乐则none。仅当脚本有旁白且用户希望配音时narration=true。",
            user_prompt=json.dumps({"messages": project.messages, "shots": shots, "executionContext": _media_execution_context(session, project),
                "observations": observations, "assets": [{k: a.get(k) for k in
                ("id", "fileName", "subject", "referenceContext")} for a in assets]}, ensure_ascii=False),
            timeout_seconds=deployment.timeout_seconds)
        Draft202012Validator(schema).validate(completion.value)
        if len(completion.value["assignments"]) != len(shots) or {a["shotId"] for a in completion.value["assignments"]} != {s["id"] for s in shots}:
            raise ValidationError("镜头计划未覆盖全部镜头")
        return completion.value, completion
    return _invoke_routed(session, "asset-matcher", project.id, project.title, fake, real)


def _invoke_routed(
    session: Session,
    capability_alias: str,
    project_id: str,
    title: str,
    fake_call: Callable[[], dict[str, Any]],
    real_call: Callable[[ModelProviderRow, ModelDeploymentRow, str], tuple[dict[str, Any], StructuredCompletion]],
) -> dict[str, Any]:
    route = session.scalar(select(RoutingVersionRow).where(RoutingVersionRow.status == "published").order_by(RoutingVersionRow.version.desc()))
    if not route:
        raise ModelGatewayError("没有已发布的模型路由策略")
    binding = next((item for item in route.bindings if item.get("capabilityAlias") == capability_alias), None)
    if not binding and capability_alias in {"storyboard-generator", "asset-planner", "asset-matcher"}:
        binding = next((item for item in route.bindings if item.get("capabilityAlias") == "creative-advisor"), None)
    if not binding:
        raise ModelGatewayError(f"能力 {capability_alias} 尚未配置路由")

    deployment_ids = list(dict.fromkeys(filter(None, [binding.get("primaryDeploymentId"), *binding.get("fallbackDeploymentIds", [])])))
    max_attempts = binding.get("maxAttempts", 1)
    if type(max_attempts) is not int or max_attempts < 1:
        raise ModelGatewayError("模型路由 maxAttempts 必须是正整数")
    fallback_on = set(binding.get("fallbackOn", []))
    last_error = "没有可用的模型部署"
    last_code = None
    for deployment_id in deployment_ids[:max_attempts]:
        if last_code and last_code not in fallback_on:
            break
        deployment = session.get(ModelDeploymentRow, deployment_id)
        provider = session.get(ModelProviderRow, deployment.provider_id) if deployment else None
        credential = session.get(ModelCredentialRow, deployment.credential_id) if deployment else None
        if credential:
            try:
                model_backoff.check(session, credential.id)
            except OpenAICompatibleError as error:
                session.commit()
                context = f"平台：{provider.display_name if provider else '未知'} · 模型：{deployment.physical_model_id if deployment else '未知'}"
                raise ModelGatewayError(context + "\n" + str(error), error.code, error.retry_after_seconds) from error
        invocation = ModelInvocationRow(
            id=str(uuid4()),
            project_id=project_id,
            capability_alias=capability_alias,
            routing_policy_version_id=route.id,
            deployment_id=str(deployment_id),
            credential_id=deployment.credential_id if deployment else "unavailable",
            status="failed",
            redacted_input=f"Project {project_id}: {title[:80]}",
        )
        session.add(invocation)

        if not deployment or deployment.status != "ready":
            last_error = f"部署 {deployment_id} 未就绪"
            invocation.error_code = last_code = "DEPLOYMENT_NOT_READY"
            continue
        if not provider or not provider.enabled or provider.status != "active":
            last_error = f"部署 {deployment_id} 的平台不可用"
            invocation.error_code = last_code = "PROVIDER_UNAVAILABLE"
            continue
        if not credential or credential.status != "active":
            last_error = f"部署 {deployment_id} 的凭据不可用"
            invocation.error_code = last_code = "AUTH_FAILED"
            continue
        invocation.status = "calling"
        invocation.provider_model_id = deployment.physical_model_id
        session.commit()
        started = monotonic()
        try:
            api_key = secret_store.get(credential.secret_ref)
            if provider.adapter_type == "fake":
                if not get_settings().allow_fake_provider:
                    raise OpenAICompatibleError("测试模型未启用", "ADAPTER_UNSUPPORTED")
                result = fake_call()
                completion = StructuredCompletion(result, f"fake-{invocation.id[:8]}", deployment.physical_model_id, 86, 214, 84)
            elif provider.adapter_type == "openai-compatible":
                if not get_settings().allow_external_models:
                    raise OpenAICompatibleError("当前环境禁止外部模型调用", "ADAPTER_UNSUPPORTED")
                result, completion = real_call(provider, deployment, api_key)
            else:
                raise OpenAICompatibleError(f"尚未实现适配器 {provider.adapter_type}", "ADAPTER_UNSUPPORTED")
        except (KeyError, ValueError):
            last_error = "凭据无法从加密存储读取"
            invocation.status = "failed"
            invocation.duration_ms = round((monotonic() - started) * 1000)
            invocation.error_code = last_code = "AUTH_FAILED"
            session.commit()
            continue
        except (OpenAICompatibleError, ValidationError) as error:
            code = error.code if isinstance(error, OpenAICompatibleError) else "SCHEMA_INVALID"
            last_error = str(error) if isinstance(error, OpenAICompatibleError) else "模型输出未通过本地 Schema 校验"
            last_error = f"平台：{provider.display_name} · 模型：{deployment.physical_model_id}\n" + last_error
            invocation.status = "failed"
            invocation.duration_ms = round((monotonic() - started) * 1000)
            invocation.error_code = last_code = code
            invocation.redacted_output = last_error
            invocation.provider_request_id = getattr(error, "request_id", None)
            if code in {"RATE_LIMITED", "QUOTA_EXCEEDED"}:
                model_backoff.record(session, credential.id, error)
                session.commit()
                raise ModelGatewayError(last_error, code, error.retry_after_seconds) from error
            session.commit()
            continue

        invocation.status = "succeeded"
        invocation.input_tokens = completion.input_tokens
        invocation.output_tokens = completion.output_tokens
        invocation.duration_ms = completion.duration_ms
        invocation.provider_request_id = completion.request_id
        invocation.provider_model_id = completion.model_id
        invocation.redacted_output = "结构化输出已通过本地 Schema 校验。"
        return result

    session.commit()
    raise ModelGatewayError(last_error, last_code or "PROVIDER_ERROR")


def _canonical_advisor(project: ProjectRow, wire: dict[str, Any]) -> dict[str, Any]:
    Draft202012Validator(ADVISOR_WIRE_SCHEMA).validate(wire)
    keys = {item["proposalKey"] for item in wire["proposals"]}
    if len(keys) != len(wire["proposals"]) or wire["recommendedProposalKey"] not in keys:
        raise ValidationError("proposal keys must be unique and recommendation must reference one proposal")
    fact_ids = [item["id"] for item in project.facts]
    proposals = [
        {
            **item,
            "basis": [
                {
                    "type": "project-fact",
                    "refId": fact_ids[0] if fact_ids else None,
                    "summary": "方案依据用户输入与当前素材信息生成，不代表已完成车型核验。",
                }
            ],
        }
        for item in wire["proposals"]
    ]
    return {
        "schemaVersion": "1.0.0",
        "projectId": project.id,
        "contentPack": {"id": project.content_pack_id, "version": project.content_pack_version},
        "diagnosis": wire["diagnosis"],
        "proposals": proposals,
        "recommendedProposalKey": wire["recommendedProposalKey"],
        "basisSummary": {"projectFactIds": fact_ids, "evidenceItemIds": [], "assumptions": wire["assumptions"]},
        "blockingQuestion": None,
    }


def _runtime_storyboard(project: ProjectRow, brief: DocumentRow, version: int, wire: dict[str, Any]) -> dict[str, Any]:
    cursor = 0
    shots = []
    for index, item in enumerate(wire["shots"], 1):
        duration = int(item["durationMs"])
        shots.append(
            {
                "id": str(uuid4()),
                "order": index,
                "purpose": item["purpose"][:200],
                "startMs": cursor,
                "durationMs": duration,
                "subject": item["subject"],
                "action": item["action"],
                "scene": item["scene"],
                "visual": "\n".join([item["subject"], item["action"], item["scene"], item["description"]]),
                "camera": f"{item['shotSize']}；{item['angle']}；{item['movement']}；{item['lensIntent']}"[:500],
                "voiceover": item["voiceover"][:300],
                "caption": item["caption"][:80],
                "sound": item["soundDirection"][:240],
                "sourceStrategy": item["preferredStrategy"],
                "selectionOwner": "platform",
                "strategyOwner": "platform",
                "videoPrompt": "\n".join([f"主体：{item['subject']}", f"动作：{item['action']}", f"场景：{item['scene']}",
                    item["description"], item["movement"], "必须呈现：" + "；".join(item["mustShow"]),
                    "避免：" + "；".join(item["mustAvoid"]), *item["continuity"]]),
                "fallbackStrategies": item["fallbackStrategies"][:3],
                "continuity": item["continuity"][:10],
                "mustShow": item["mustShow"][:10],
                "mustAvoid": item["mustAvoid"][:10],
                "origin": item["origin"],
                "status": "draft",
            }
        )
        cursor += duration
    return {
        "schemaVersion": "1.0.0",
        "projectId": project.id,
        "creativeBriefVersionId": brief.id,
        "version": version,
        "status": "draft",
        "title": wire["title"][:120],
        "targetPlatform": project.target_platform,
        "locale": project.locale,
        "script": {
            "voiceoverEnabled": any(item["voiceover"] for item in wire["shots"]),
            "voiceDirection": wire["voiceDirection"][:300],
            "segments": [{"segmentKey": f"segment-{index:02d}", "text": item["voiceover"][:300]} for index, item in enumerate(wire["shots"], 1)],
        },
        "continuityRules": wire["continuityRules"][:20],
        "soundPlan": {"background": "none", "narration": any(item["voiceover"].strip() for item in wire["shots"])},
        "output": {"aspectRatio": "9:16", "width": 1080, "height": 1920, "fps": 30},
        "totalDurationMs": cursor,
        "shots": shots,
    }


def _validate_spec(file_name: str, value: dict[str, Any]) -> None:
    schema = json.loads((spec_dir / file_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
