from datetime import UTC, datetime
from uuid import uuid4


def timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_project_facts(project_id: str, title: str, message: str, platform: str = "douyin") -> list[dict]:
    return [
        {
            "id": str(uuid4()),
            "key": "output.platform",
            "value": platform,
            "sourceType": "user-confirmation",
            "sourceId": project_id,
            "confidence": 1,
            "status": "confirmed",
        },
    ]


def build_advisor_result(project_id: str, title: str, fact_ids: list[str]) -> dict:
    common = {
        "audience": ["关注真实车型质感的摩托车用户"],
        "resourceEstimate": "medium",
        "estimatedDifficulty": "medium",
        "requiredAssets": ["车型正面与侧面参考", "发动机与仪表细节"],
    }
    proposals = [
        {
            **common,
            "proposalKey": "cinematic-reveal",
            "name": "机械电影感",
            "positioning": "用精确环绕和机械细节建立车型记忆，再以高速动态完成情绪释放。",
            "primaryGoal": "让观众在前三秒认出车型并记住力量感",
            "contentType": "产品电影",
            "hook": {"text": "不是介绍，是一次机械觉醒。", "visual": "暗场灯带扫过车身，进入 360 度环绕", "durationMs": 1800},
            "corePromise": "24 秒看清整车比例、核心机械细节与骑行姿态",
            "visualPayoffs": ["360 度整车环绕", "发动机与制动细节", "高速骑行压弯收尾"],
            "pacing": "前 3 秒建立车型，随后每 3 至 4 秒切换景别，最后 6 秒释放速度。",
            "emotionalPeak": "骑手进入高速路段，镜头贴近后轮后迅速拉远。",
            "close": "车型定格与账号识别同时收束。",
            "whyItFits": ["用户明确要求车辆聚焦与 360 环绕", "电影感适合强化真实车型识别"],
            "limitations": ["需要稳定的多角度车型参考以保持跨镜头一致"],
            "basis": [{"type": "project-fact", "refId": fact_ids[0], "summary": f"用户确认车型为 {title}"}],
        },
        {
            **common,
            "proposalKey": "performance-proof",
            "name": "性能证据链",
            "positioning": "用沙漠、涉水和山林三种环境连续证明车辆通过性。",
            "primaryGoal": "通过可见场景证明越野能力",
            "contentType": "性能证明",
            "hook": {"text": "路到这里结束，它才刚开始。", "visual": "前轮冲出沙尘并切入仪表特写", "durationMs": 1600},
            "corePromise": "不是口号，用连续地形变化展示车辆能力",
            "visualPayoffs": ["沙漠扬尘", "转速表拉升", "涉水抬头", "山林无人机远拉"],
            "pacing": "动作镜头与机械特写交替，保持每 2 至 3 秒一次视觉变化。",
            "emotionalPeak": "车辆冲出涉水路面抬头，无人机镜头接续展示路线尺度。",
            "close": "无人机远拉后保留车型与路线。",
            "whyItFits": ["场景变化能把抽象性能转为视觉证据", "适合日更账号建立明确观点"],
            "limitations": ["涉水动作需要控制真实性，不能夸大原车能力"],
            "basis": [{"type": "platform-method", "refId": None, "summary": "以画面证据兑现内容承诺"}],
        },
        {
            **common,
            "proposalKey": "detail-rhythm",
            "name": "细节节奏片",
            "positioning": "以灯组、悬挂、轮胎和仪表的微距节拍形成高完成度短片。",
            "primaryGoal": "强化机械审美与收藏价值",
            "contentType": "细节混剪",
            "hook": {"text": "真正的力量，藏在每一道结构里。", "visual": "大灯点亮与金属表面快速切换", "durationMs": 1400},
            "corePromise": "快速看完最值得关注的车辆细节",
            "visualPayoffs": ["灯组点亮", "悬挂压缩", "轮胎纹理", "仪表启动"],
            "pacing": "声音驱动剪辑，微距与整车交替。",
            "emotionalPeak": "细节快切后突然切换到整车高速通过。",
            "close": "熄灯黑场后留下车型名。",
            "whyItFits": ["素材需求可控，适合账号日更", "细节镜头能减少跨场景车型漂移"],
            "limitations": ["整体叙事弱于性能路线，需要声音设计支撑"],
            "basis": [{"type": "creative-assumption", "refId": None, "summary": "目标受众对机械细节具有兴趣"}],
        },
    ]
    return {
        "schemaVersion": "1.0.0",
        "projectId": project_id,
        "contentPack": {"id": "motorcycle", "version": "1.0.0"},
        "diagnosis": {
            "understoodGoal": f"为 {title} 制作适合抖音日更的真实车型短片",
            "audience": ["摩托车爱好者", "潜在购车用户"],
            "opportunity": "用整车识别、机械证据和动态高潮形成完整观看回报。",
            "primaryRisk": "缺少多角度参考时，AI 视频可能出现车型细节漂移。",
            "missingInformation": ["是否已有可用的多角度实拍素材"],
        },
        "proposals": proposals,
        "recommendedProposalKey": "cinematic-reveal",
        "basisSummary": {"projectFactIds": fact_ids, "evidenceItemIds": [], "assumptions": ["首期使用 AI 参考图与确定性运动预览"]},
        "blockingQuestion": None,
    }


def build_brief(project_id: str, proposal: dict, version: int) -> dict:
    return {
        "schemaVersion": "1.0.0",
        "projectId": project_id,
        "version": version,
        "status": "draft",
        "sourceProposalKeys": [proposal["proposalKey"]],
        "audience": proposal["audience"],
        "primaryGoal": proposal["primaryGoal"],
        "contentType": proposal["contentType"],
        "hook": proposal["hook"],
        "corePromise": proposal["corePromise"],
        "visualPayoffs": proposal["visualPayoffs"],
        "tone": ["精确", "有力量", "克制"],
        "pacing": proposal["pacing"],
        "emotionalPeak": proposal["emotionalPeak"],
        "cta": "你最想看哪一个机械细节？",
        "mustKeep": proposal["visualPayoffs"][:2],
        "mustNotInvent": ["未确认的车辆参数", "不存在的品牌配置"],
        "targetPlatform": "douyin",
        "locale": "zh-CN",
        "aspectRatio": "9:16",
        "targetDurationMs": 12000,
        "resourceEstimate": proposal["resourceEstimate"],
    }


def build_storyboard(project_id: str, brief_id: str, title: str, version: int) -> dict:
    shots = [
        ("整车建立", "摄影棚灯带扫过车身，镜头完成 360 度环绕", "先看清它的轮廓。", 2400),
        ("机械细节", "发动机、前制动与灯组的三段微距特写", "力量不是口号，它写在结构里。", 2200),
        ("仪表响应", "仪表点亮，转速快速爬升后切向前轮", "响应，从这一刻开始。", 1800),
        ("环境证明", "车辆穿过沙土与浅水，后轮带起清晰轨迹", "路况在变，节奏不退。", 2800),
        ("高速收束", "皮衣骑手高速通过，低机位跟随后由无人机远拉", f"{title}，把终点留在身后。", 2800),
    ]
    cursor = 0
    result = []
    for index, (purpose, visual, voiceover, duration) in enumerate(shots, 1):
        shot_id = str(uuid4())
        result.append(
            {
                "id": shot_id,
                "order": index,
                "purpose": purpose,
                "startMs": cursor,
                "durationMs": duration,
                "visual": visual,
                "camera": "稳定运镜，主体保持在竖屏安全区",
                "voiceover": voiceover,
                "caption": voiceover,
                "sound": "发动机声与低频节拍",
                "sourceStrategy": "image-motion",
                "status": "draft",
            }
        )
        cursor += duration
    return {
        "schemaVersion": "1.0.0",
        "projectId": project_id,
        "creativeBriefVersionId": brief_id,
        "version": version,
        "status": "draft",
        "title": f"{title}｜机械觉醒",
        "targetPlatform": "douyin",
        "locale": "zh-CN",
        "output": {"aspectRatio": "9:16", "width": 1080, "height": 1920, "fps": 30},
        "totalDurationMs": cursor,
        "shots": result,
    }
