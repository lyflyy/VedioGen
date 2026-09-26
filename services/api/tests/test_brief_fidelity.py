from copy import deepcopy
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, ValidationError

from vediogen_api.fixtures import build_advisor_result, build_brief
from vediogen_api.gateway import _validate_spec
from vediogen_api.model_contracts import ADVISOR_WIRE_SCHEMA


def proposal():
    item = build_advisor_result(str(uuid4()), "Ducati V4", [str(uuid4())])["proposals"][0]
    item.update(
        targetDurationMs=30000,
        hook={"text": "红色锋芒", "visual": "成年中国女车主与红色杜卡迪在车库同框", "durationMs": 1200},
        visualPayoffs=["整车展示", "机械细节", "女车主抚过油箱并上车", "公路远景", "朋友聚会"],
        pacing="0-7秒车库；7-13秒公路；13-18秒聚会；18-30秒细节",
    )
    return item


def test_brief_retains_duration_opening_and_every_visual_payoff():
    item = proposal()
    original = deepcopy(item)
    brief = build_brief("project", item, 1)
    assert brief["targetDurationMs"] == 30000
    assert brief["mustKeep"] == [item["hook"]["visual"], *item["visualPayoffs"]]
    assert brief["pacing"] == item["pacing"]
    assert item == original


def test_legacy_proposal_does_not_silently_become_twelve_seconds():
    item = proposal()
    del item["targetDurationMs"]
    assert build_brief("project", item, 1)["targetDurationMs"] is None


def test_new_wire_requires_duration_but_stored_legacy_advisor_remains_readable():
    result = build_advisor_result(str(uuid4()), "Ducati V4", [str(uuid4())])
    wire = {key: value for key, value in proposal().items() if key != "basis"}
    schema = ADVISOR_WIRE_SCHEMA["properties"]["proposals"]["items"]
    Draft202012Validator(schema).validate(wire)
    del wire["targetDurationMs"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(wire)
    _validate_spec("creative-advisor.schema.json", result)
    for item in result["proposals"]:
        del item["targetDurationMs"]
    _validate_spec("creative-advisor.schema.json", result)
