import json
from types import SimpleNamespace

import pytest

from pharmgraph_ai.ui.tool_presenter import (
    LiveToolPresenter,
    _safe_step_name,
    _tool_title,
    format_result,
)


def test_step_name_is_safe_for_chainlit_avatar_route():
    title = "Retrieving drug profile: Eliquis — 00078-0699-44 (tablet/capsule)"

    assert _safe_step_name(title) == (
        "Retrieving drug profile Eliquis 00078-0699-44 tablet capsule"
    )


def test_search_title_includes_name_and_dosage_form():
    raw_item = {
        "arguments": json.dumps(
            {
                "name": "aspirin",
                "dosage_form": "TABLET",
                "limit": 10,
            }
        )
    }

    assert _tool_title("search_drugs", raw_item) == (
        "Searching for drugs: aspirin TABLET"
    )


def test_search_title_ignores_string_none_dosage_form():
    raw_item = {
        "arguments": json.dumps(
            {
                "name": "Eliquis",
                "dosage_form": "None",
            }
        )
    }

    assert _tool_title("search_drugs", raw_item) == "Searching for drugs: Eliquis"


def test_search_result_shows_only_first_three_products():
    products = [
        {
            "key": f"ndc-{index}",
            "name": f"Drug {index}",
            "dosage_form": "TABLET",
        }
        for index in range(1, 5)
    ]

    result = format_result("search_drugs", json.dumps(products))

    assert result == (
        "Drugs found: 4\n"
        "- Drug 1 — TABLET, ndc-1\n"
        "- Drug 2 — TABLET, ndc-2\n"
        "- Drug 3 — TABLET, ndc-3\n"
        "..."
    )
    assert "Drug 4" not in result


def test_empty_search_result_has_no_product_list():
    assert format_result("search_drugs", "[]") == "Drugs found: 0"


@pytest.mark.asyncio
async def test_tool_step_is_collapsed_and_hides_arguments(monkeypatch):
    created_steps = []

    class FakeStep:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.input = None
            self.output = None
            self.sent = False
            created_steps.append(self)

        async def send(self):
            self.sent = True

    monkeypatch.setattr(
        "pharmgraph_ai.ui.tool_presenter.cl.Step",
        FakeStep,
    )

    presenter = LiveToolPresenter()
    item = SimpleNamespace(
        call_id="call-1",
        tool_name="search_drugs",
        raw_item={
            "arguments": json.dumps(
                {
                    "name": "Eliquis",
                    "dosage_form": None,
                    "limit": 10,
                }
            )
        },
    )

    await presenter.on_tool_called(item)

    assert len(created_steps) == 1
    step = created_steps[0]
    assert step.kwargs["show_input"] is False
    assert step.kwargs["default_open"] is False
    assert step.input is None
    assert step.output == "Investigation in progress..."
    assert step.sent is True


@pytest.mark.asyncio
async def test_reconcile_does_not_repeat_streamed_tool_items(monkeypatch):
    from agents.items import ToolCallItem, ToolCallOutputItem

    created_steps = []

    class FakeStep:
        def __init__(self, **kwargs):
            self.input = None
            self.output = None
            self.update_count = 0
            created_steps.append(self)

        async def send(self):
            pass

        async def update(self):
            self.update_count += 1

    monkeypatch.setattr(
        "pharmgraph_ai.ui.tool_presenter.cl.Step",
        FakeStep,
    )

    class AgentStub:
        pass

    agent = AgentStub()
    call = ToolCallItem(
        agent=agent,
        raw_item={
            "call_id": "call-1",
            "name": "search_drugs",
            "arguments": json.dumps({"name": "Eliquis"}),
        },
    )
    output = ToolCallOutputItem(
        agent=agent,
        raw_item={"call_id": "call-1"},
        output="[]",
    )
    presenter = LiveToolPresenter()

    await presenter.reconcile([call, output])
    await presenter.reconcile([call, output])

    assert len(created_steps) == 1
    assert created_steps[0].update_count == 1
    assert created_steps[0].output == "Drugs found: 0"


def test_profile_title_uses_known_product_name_and_key():
    raw_item = {"arguments": json.dumps({"product_key": "00078-0699-44"})}

    assert (
        _tool_title(
            "get_drug_profile",
            raw_item,
            {"00078-0699-44": "Eliquis"},
        )
        == "Retrieving drug profile: Eliquis — 00078-0699-44"
    )


def test_related_drugs_title_uses_known_product_name_and_key():
    raw_item = {"arguments": json.dumps({"product_key": "00078-0699-44"})}

    assert (
        _tool_title(
            "find_related_drugs",
            raw_item,
            {"00078-0699-44": "Eliquis"},
        )
        == "Investigating related drugs: Eliquis — 00078-0699-44"
    )


def test_related_drugs_result_lists_first_three_products():
    result = format_result(
        "find_related_drugs",
        json.dumps(
            {
                "status": "found",
                "source_product_key": "00078-0699-44",
                "products": [
                    {
                        "key": f"ndc-{index}",
                        "name": f"Related drug {index}",
                        "generic_name": "apixaban",
                        "dosage_form": "TABLET",
                    }
                    for index in range(1, 5)
                ],
            }
        ),
    )

    assert result == (
        "Related drugs found: 4\n"
        "- Related drug 1 — TABLET, ndc-1\n"
        "- Related drug 2 — TABLET, ndc-2\n"
        "- Related drug 3 — TABLET, ndc-3\n"
        "..."
    )
    assert "Related drug 4" not in result


def test_interaction_title_uses_known_ingredient_names():
    raw_item = {
        "arguments": json.dumps(
            {
                "ingredient_keys": ["ingredient-apixaban", "ingredient-aspirin"],
            }
        )
    }

    assert (
        _tool_title(
            "find_documented_interactions",
            raw_item,
            ingredient_names={
                "ingredient-apixaban": "Apixaban",
                "ingredient-aspirin": "Aspirin",
            },
        )
        == "Checking drug interactions: Apixaban and Aspirin"
    )


def test_interaction_title_falls_back_to_ingredient_keys():
    raw_item = {
        "arguments": {
            "ingredient_keys": ["ingredient-apixaban", "ingredient-aspirin"],
        }
    }

    assert _tool_title("find_documented_interactions", raw_item) == (
        "Checking drug interactions: ingredient-apixaban and ingredient-aspirin"
    )


def test_profile_result_shows_only_first_three_ingredients():
    profile = {
        "status": "found",
        "product": {
            "key": "ndc-1",
            "name": "Combination drug",
            "composition": [
                {
                    "ingredient": {
                        "key": f"ingredient-{index}",
                        "name": f"API {index}",
                    },
                    "strength": f"{index} mg",
                }
                for index in range(1, 5)
            ],
        },
    }

    result = format_result("get_drug_profile", json.dumps(profile))

    assert result == (
        "Retrieved profile for Combination drug\n"
        "Active ingredients:\n"
        "- API 1 — 1 mg\n"
        "- API 2 — 2 mg\n"
        "- API 3 — 3 mg\n"
        "..."
    )
    assert "API 4" not in result
