from typing import Any


STRING = {"type": "string"}
STRING_LIST = {"type": "array", "items": STRING}


def strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


ADVISOR_WIRE_SCHEMA = strict_object(
    {
        "diagnosis": strict_object(
            {
                "understoodGoal": STRING,
                "audience": STRING_LIST,
                "opportunity": STRING,
                "primaryRisk": STRING,
                "missingInformation": STRING_LIST,
            }
        ),
        "proposals": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": strict_object(
                {
                    "proposalKey": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,63}$"},
                    "name": STRING,
                    "positioning": STRING,
                    "audience": STRING_LIST,
                    "primaryGoal": STRING,
                    "contentType": STRING,
                    "hook": strict_object(
                        {"text": STRING, "visual": STRING, "durationMs": {"type": "integer", "minimum": 500, "maximum": 3000}}
                    ),
                    "corePromise": STRING,
                    "visualPayoffs": STRING_LIST,
                    "pacing": STRING,
                    "emotionalPeak": STRING,
                    "close": STRING,
                    "requiredAssets": STRING_LIST,
                    "resourceEstimate": {"type": "string", "enum": ["low", "medium", "high"]},
                    "estimatedDifficulty": {"type": "string", "enum": ["low", "medium", "high"]},
                    "whyItFits": STRING_LIST,
                    "limitations": STRING_LIST,
                }
            ),
        },
        "recommendedProposalKey": STRING,
        "assumptions": STRING_LIST,
    }
)


STORYBOARD_WIRE_SCHEMA = strict_object(
    {
        "title": STRING,
        "voiceDirection": STRING,
        "continuityRules": STRING_LIST,
        "shots": {
            "type": "array",
            "minItems": 5,
            "maxItems": 8,
            "items": strict_object(
                {
                    "purpose": STRING,
                    "durationMs": {"type": "integer", "minimum": 500, "maximum": 10000},
                    "subject": STRING,
                    "action": STRING,
                    "scene": STRING,
                    "description": STRING,
                    "mustShow": STRING_LIST,
                    "mustAvoid": STRING_LIST,
                    "shotSize": {"type": "string", "enum": ["extreme-close-up", "close-up", "medium", "wide", "aerial", "pov"]},
                    "angle": STRING,
                    "movement": STRING,
                    "lensIntent": STRING,
                    "voiceover": STRING,
                    "caption": STRING,
                    "soundDirection": STRING,
                    "preferredStrategy": {
                        "type": "string",
                        "enum": ["user-video", "image-to-video", "generated-video", "image-motion", "blender-3d", "stock-video"],
                    },
                    "fallbackStrategies": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["user-video", "image-to-video", "generated-video", "image-motion", "blender-3d", "stock-video"],
                        },
                    },
                    "continuity": STRING_LIST,
                    "origin": {"type": "string", "enum": ["user-required", "ai-proposed"]},
                }
            ),
        },
    }
)


def advisor_system_prompt() -> str:
    return """你是短视频平台的资深创意策略师和摩托车广告导演。先判断用户目标，再给出三个机制明显不同、可比较的方案。
真实车型模式下不得虚构车型参数或把无法验证的性能当成事实。明确素材不足造成的车型一致性风险。
用户对第一镜、最后一镜、必需场景和人物服装等明确要求属于硬约束，三个方案都必须保留；后续补充消息的优先级高于早期消息。
输出必须使用简体中文（proposalKey 除外），严格符合给定 JSON Schema，不要输出 Markdown。"""


def storyboard_system_prompt() -> str:
    return """你是竖屏短视频脚本导演。根据已确认的 Creative Brief 生成可执行的旁白与分镜。
每个镜头必须描述主体、动作、场景、机位运动、声音和素材策略。真实车型不得虚构参数；没有多角度素材时应在 mustAvoid 和 continuity 中约束车型一致性。
用户明确指定的第一个镜头和最后一个镜头必须严格位于 shots 数组的首项和末项，不得在指定结尾后追加 CTA 或余韵镜头。用户消息中的“必须、最后、第一”等要求优先于通用模板。
source strategy 要诚实：静态照片可用 image-motion，需要创造运动画面时用 image-to-video 或 generated-video，需要精确环绕时可用 blender-3d。
总时长控制在 12 至 30 秒，输出简体中文并严格符合 JSON Schema，不要输出 Markdown。"""
