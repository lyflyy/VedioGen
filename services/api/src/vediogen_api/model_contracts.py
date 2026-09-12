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
            "minItems": 1,
            "maxItems": 12,
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
                    "caption": {"type": "string", "maxLength": 40},
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
这是内部 AI 视频制作平台，不是实拍团队。用户只有文字也可创作，素材检索与生成由平台承担；requiredAssets 写平台需准备的素材，不要求用户先上传、重拍或提供模型。仅对影响创意和车型身份的选择提问，不新增法务审批或授权审核流程。
executionContext 是当前工程能力边界；未实现、未启用或尚未验证的能力须在 limitations 中说明。保留用户的困难镜头作为目标，不用图片缩放冒充运动、真实 360 度或实测证据；也不承诺生成效果或传播数据。
项目标题中的本地实测、工程验证、待验收等是内部管理标签，不是车辆实测事实或视频文案要求，不写进成片。创意以用户消息为准。
真实车型模式下不得虚构车型参数或把无法验证的性能当成事实。明确素材不足造成的车型一致性风险。
用户对第一镜、最后一镜、必需场景和人物服装等明确要求属于硬约束，三个方案都必须保留；后续补充消息的优先级高于早期消息。
输出必须使用简体中文（proposalKey 除外），严格符合给定 JSON Schema，不要输出 Markdown。"""


def storyboard_system_prompt() -> str:
    return """你是竖屏短视频脚本导演。根据已确认的 Creative Brief 生成可执行的旁白与分镜。
用户仅有文字时，参考素材由平台准备，不把要求用户上传作为分镜方案。executionContext 表示配置而非推理验证；本地 image-to-video 镜头遵循 durationRangeMs，可用小数秒对应的毫秒；云端从 durationOptionsMs 选择，素材和模型未就绪仍保留为待准备的目标。
未实现的策略不能说已经可执行；精确环绕若依赖 blender-3d，依据执行上下文说明启用状态与准确 GLB 资产缺口，不改成 image-motion 假装完成。Blender 当前仅支持完整 360 度静态主体环绕，不支持骑手、驾驶、涉水动作。内部工程标签不进入旁白、字幕，不把生成画面写成真实车辆性能测试的证据。
每个镜头必须描述主体、动作、场景、机位运动、声音和素材策略。真实车型不得虚构参数；没有多角度素材时应在 mustAvoid 和 continuity 中约束车型一致性。
用户明确指定的第一个镜头和最后一个镜头必须严格位于 shots 数组的首项和末项，不得在指定结尾后追加 CTA 或余韵镜头。用户消息中的“必须、最后、第一”等要求优先于通用模板。
所有用户指定的中段场景和动作同样是硬约束，origin 必须为 user-required，不能归为 ai-proposed 后省略。完整360度环绕不能改写为‘环绕感’或小角度横移；沙漠、涉水、抬头、山林等具体要求必须明确出现在 action/scene/description 中，不能只写成抽象情绪或节奏。缺少资产时保留原要求并标明缺口。
source strategy 要诚实：静态照片可用 image-motion，需要创造运动画面时用 image-to-video 或 generated-video，需要精确环绕时可用 blender-3d。
image-motion 当前仅执行原图居中缓慢推近，不改变拍摄角度；不要为该策略编写真实横向机位移动、正面转侧面、环绕或主体运动。不同视角应使用不同参考图分镜切换。
混合制作：车灯、漆面、仪表等静态细节优先 image-motion，避免模型重绘真实结构和读数；有限角度动态展示可用 image-to-video。不要为炫酷而让每镜都生成运动。不要求驾驶时不主动加入高风险驾驶镜头。所有字幕最多40字；短旁白必须能在镜头时长内自然读完，不能用过量旁白挤压画面。
总时长控制在 12 至 30 秒，输出简体中文并严格符合 JSON Schema，不要输出 Markdown。"""
