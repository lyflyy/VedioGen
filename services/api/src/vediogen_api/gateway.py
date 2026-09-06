import json
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .fixtures import build_advisor_result, build_storyboard
from .model_contracts import ADVISOR_WIRE_SCHEMA, STORYBOARD_WIRE_SCHEMA, advisor_system_prompt, storyboard_system_prompt
from .models import DocumentRow, ModelCredentialRow, ModelDeploymentRow, ModelInvocationRow, ModelProviderRow, ProjectRow, RoutingVersionRow
from .openai_compatible import OpenAICompatibleError, StructuredCompletion, complete_json
from .secret_store import LocalEncryptedSecretStore


class ModelGatewayError(RuntimeError):
    pass


secret_store = LocalEncryptedSecretStore(get_settings().data_dir / "secrets")
spec_dir = Path(__file__).resolve().parents[4] / "docs" / "specs"


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
    if not binding and capability_alias == "storyboard-generator":
        binding = next((item for item in route.bindings if item.get("capabilityAlias") == "creative-advisor"), None)
    if not binding:
        raise ModelGatewayError(f"能力 {capability_alias} 尚未配置路由")

    deployment_ids = [binding.get("primaryDeploymentId"), *binding.get("fallbackDeploymentIds", [])]
    last_error = "没有可用的模型部署"
    for deployment_id in filter(None, deployment_ids):
        deployment = session.get(ModelDeploymentRow, deployment_id)
        provider = session.get(ModelProviderRow, deployment.provider_id) if deployment else None
        credential = session.get(ModelCredentialRow, deployment.credential_id) if deployment else None
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
            invocation.error_code = "DEPLOYMENT_NOT_READY"
            continue
        if not provider or not provider.enabled or provider.status != "active":
            last_error = f"部署 {deployment_id} 的平台不可用"
            invocation.error_code = "PROVIDER_UNAVAILABLE"
            continue
        if not credential or credential.status != "active":
            last_error = f"部署 {deployment_id} 的凭据不可用"
            invocation.error_code = "AUTH_FAILED"
            continue
        try:
            api_key = secret_store.get(credential.secret_ref)
            if provider.adapter_type == "fake":
                result = fake_call()
                completion = StructuredCompletion(result, f"fake-{invocation.id[:8]}", deployment.physical_model_id, 86, 214, 84)
            elif provider.adapter_type == "openai-compatible":
                result, completion = real_call(provider, deployment, api_key)
            else:
                raise OpenAICompatibleError(f"尚未实现适配器 {provider.adapter_type}", "ADAPTER_UNSUPPORTED")
        except (KeyError, ValueError):
            last_error = "凭据无法从加密存储读取"
            invocation.error_code = "AUTH_FAILED"
            continue
        except (OpenAICompatibleError, ValidationError) as error:
            code = error.code if isinstance(error, OpenAICompatibleError) else "SCHEMA_INVALID"
            last_error = str(error) if isinstance(error, OpenAICompatibleError) else "模型输出未通过本地 Schema 校验"
            invocation.error_code = code
            invocation.redacted_output = last_error[:500]
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
    raise ModelGatewayError(last_error)


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
                    "summary": "方案依据用户确认的信息与已上传素材生成。",
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
                "visual": item["description"][:500],
                "camera": f"{item['shotSize']}；{item['angle']}；{item['movement']}；{item['lensIntent']}"[:500],
                "voiceover": item["voiceover"][:300],
                "caption": item["caption"][:80],
                "sound": item["soundDirection"][:240],
                "sourceStrategy": item["preferredStrategy"],
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
        "output": {"aspectRatio": "9:16", "width": 1080, "height": 1920, "fps": 30},
        "totalDurationMs": cursor,
        "shots": shots,
    }


def _validate_spec(file_name: str, value: dict[str, Any]) -> None:
    schema = json.loads((spec_dir / file_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
