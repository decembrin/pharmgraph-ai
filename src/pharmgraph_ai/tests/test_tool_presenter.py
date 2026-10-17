import json

from pharmgraph_ai.ui.tool_presenter import (
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
