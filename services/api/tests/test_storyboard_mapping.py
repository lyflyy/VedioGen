from types import SimpleNamespace

from vediogen_api.gateway import _runtime_storyboard
from vediogen_api.model_contracts import STORYBOARD_WIRE_SCHEMA


def test_executable_storyboard_keeps_subject_action_scene_and_hard_constraints():
    shot = {"purpose": "环境冲击", "durationMs": 3000, "subject": "春风800MT-ES",
            "action": "骑行并扬起尘土", "scene": "沙漠沙丘", "description": "提高视觉冲击力",
            "shotSize": "wide", "angle": "低机位", "movement": "向后跟拍", "lensIntent": "展现路况",
            "voiceover": "向前", "caption": "向前", "soundDirection": "轮胎声音",
            "preferredStrategy": "image-to-video", "fallbackStrategies": [],
            "mustShow": ["两个车轮接地"], "mustAvoid": ["用城市道路替代沙漠"],
            "continuity": ["保留白色车身"], "origin": "user-required"}
    wire = {"title": "工程分镜", "voiceDirection": "自然", "continuityRules": [], "shots": [shot]}
    result = _runtime_storyboard(SimpleNamespace(id="project", target_platform="douyin", locale="zh-CN"),
                                 SimpleNamespace(id="brief"), 1, wire)["shots"][0]
    for key in ("subject", "action", "scene"):
        assert result[key] == shot[key]
        assert shot[key] in result["visual"]
        assert shot[key] in result["videoPrompt"]
    assert "两个车轮接地" in result["videoPrompt"]
    assert "避免：用城市道路替代沙漠" in result["videoPrompt"]
    assert "保留白色车身" in result["videoPrompt"]
    assert result["origin"] == "user-required"
    from jsonschema import Draft202012Validator
    Draft202012Validator(STORYBOARD_WIRE_SCHEMA).validate(wire)
    assert STORYBOARD_WIRE_SCHEMA["properties"]["shots"]["minItems"] == 1
    assert STORYBOARD_WIRE_SCHEMA["properties"]["shots"]["maxItems"] == 12
