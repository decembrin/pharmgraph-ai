import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import chainlit as cl
from agents.items import ToolCallItem, ToolCallOutputItem

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_LOG_ARGUMENT_CHARS = 2000
MAX_SEARCH_RESULTS_SHOWN = 3
MAX_STEP_NAME_CHARS = 120

TOOL_TITLES = {
    "search_drugs": "Searching for drugs",
    "get_drug_profile": "Retrieving drug profile",
    "find_related_drugs": "Investigating related drugs",
    "find_documented_interactions": "Checking drug interactions",
}


def _get_arguments(raw_item: Any) -> Any:
    if isinstance(raw_item, Mapping):
        return raw_item.get("arguments")

    arguments = getattr(raw_item, "arguments", None)

    if arguments is not None:
        return arguments

    function = getattr(raw_item, "function", None)
    return getattr(function, "arguments", None)


def _parse_arguments(raw_item: Any) -> Mapping[str, Any]:
    arguments = _get_arguments(raw_item)

    if isinstance(arguments, Mapping):
        return arguments

    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}

        if isinstance(parsed, Mapping):
            return parsed

    return {}


def _format_arguments(raw_item: Any) -> str:
    arguments = _get_arguments(raw_item)

    if arguments is None:
        return "{}"

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            formatted = arguments
        else:
            formatted = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
            )
    else:
        try:
            formatted = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        except (TypeError, ValueError):
            formatted = repr(arguments)

    if len(formatted) > MAX_LOG_ARGUMENT_CHARS:
        return formatted[:MAX_LOG_ARGUMENT_CHARS] + "... [truncated]"

    return formatted


def _display_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value or value.casefold() == "none":
        return None

    return value


def _safe_step_name(title: str) -> str:
    safe_title = re.sub(r"[^a-zA-Z0-9_ .-]+", " ", title)
    safe_title = " ".join(safe_title.split())

    if not safe_title:
        return "Investigating the knowledge graph"

    return safe_title[:MAX_STEP_NAME_CHARS].rstrip()


def _tool_title(
    tool_name: str,
    raw_item: Any,
    product_names: Mapping[str, str] | None = None,
    ingredient_names: Mapping[str, str] | None = None,
) -> str:
    title = TOOL_TITLES.get(
        tool_name,
        "Investigating the knowledge graph",
    )

    arguments = _parse_arguments(raw_item)

    if tool_name == "search_drugs":
        name = _display_text(arguments.get("name"))

        if name is None:
            return title

        dosage_form = _display_text(arguments.get("dosage_form"))
        search_description = " ".join(
            part for part in (name, dosage_form) if part is not None
        )

        return f"{title}: {search_description}"

    if tool_name == "get_drug_profile":
        product_key = _display_text(arguments.get("product_key"))

        if product_key is None:
            return title

        product_name = (product_names or {}).get(product_key)
        profile_description = " — ".join(
            part for part in (product_name, product_key) if part
        )

        return f"{title}: {profile_description}"

    if tool_name == "find_documented_interactions":
        ingredient_keys = arguments.get("ingredient_keys")

        if not isinstance(ingredient_keys, (list, tuple)):
            return title

        ingredients = []

        for ingredient_key in ingredient_keys:
            ingredient_key = _display_text(ingredient_key)

            if ingredient_key is None:
                continue

            ingredients.append(
                (ingredient_names or {}).get(ingredient_key, ingredient_key)
            )

        if not ingredients:
            return title

        return f"{title}: {' and '.join(ingredients)}"

    return title


def _parse_output(output: Any) -> Any:
    if not isinstance(output, str):
        return output

    try:
        return json.loads(output)
    except (TypeError, ValueError):
        return None


def _count(data: Any, field_name: str) -> int:
    if not isinstance(data, Mapping):
        return 0

    items = data.get(field_name)

    if isinstance(items, (list, tuple)):
        return len(items)

    return 0


def _format_drug(product: Any) -> str:
    if not isinstance(product, Mapping):
        return str(product)

    name = product.get("name") or product.get("generic_name") or "Unnamed drug"
    details = [
        _display_text(product.get("dosage_form")),
        _display_text(product.get("key")),
    ]
    details = [str(detail) for detail in details if detail]

    if not details:
        return str(name)

    return f"{name} — {', '.join(details)}"


def _format_drug_search_result(data: Mapping[str, Any] | list[Any]) -> str:
    products = data if isinstance(data, list) else data.get("products", [])

    if not isinstance(products, (list, tuple)):
        products = []

    count = len(products)

    if count == 0:
        return "Drugs found: 0"

    displayed_products = products[:MAX_SEARCH_RESULTS_SHOWN]
    result_lines = [f"Drugs found: {count}"]
    result_lines.extend(f"- {_format_drug(product)}" for product in displayed_products)

    if count > MAX_SEARCH_RESULTS_SHOWN:
        result_lines.append("...")

    return "\n".join(result_lines)


def _format_composition(composition: Any) -> str:
    if not isinstance(composition, Mapping):
        return str(composition)

    ingredient = composition.get("ingredient")
    ingredient_name = None

    if isinstance(ingredient, Mapping):
        ingredient_name = ingredient.get("name") or ingredient.get("key")

    ingredient_name = ingredient_name or "Unnamed ingredient"
    strength = _display_text(composition.get("strength"))

    if strength is None:
        return str(ingredient_name)

    return f"{ingredient_name} — {strength}"


def _format_drug_profile(data: Mapping[str, Any]) -> str:
    product = data.get("product")

    if not isinstance(product, Mapping):
        return "Drug profile retrieved"

    name = product.get("name") or product.get("key")
    summary = f"Retrieved profile for {name}" if name else "Drug profile retrieved"
    composition = product.get("composition")

    if not isinstance(composition, (list, tuple)) or not composition:
        return summary

    displayed_composition = composition[:MAX_SEARCH_RESULTS_SHOWN]
    result_lines = [summary, "Active ingredients:"]
    result_lines.extend(
        f"- {_format_composition(item)}" for item in displayed_composition
    )

    if len(composition) > MAX_SEARCH_RESULTS_SHOWN:
        result_lines.append("...")

    return "\n".join(result_lines)


def format_result(tool_name: str, output: Any) -> str:
    data = _parse_output(output)

    if not isinstance(data, (Mapping, list)):
        return "Unable to interpret the result"

    if isinstance(data, Mapping):
        status = data.get("status")

        if status == "error":
            return "The investigation failed"

        if status == "not_found":
            return "No records were found in the investigated data"

    if tool_name == "search_drugs":
        return _format_drug_search_result(data)

    if tool_name == "get_drug_profile":
        return _format_drug_profile(data)

    if tool_name == "find_related_drugs":
        count = _count(data, "products")
        return f"Related drugs found: {count}"

    if tool_name == "find_documented_interactions":
        count = _count(data, "findings")
        return f"Documented interactions found: {count}"

    return "Investigation completed"


@dataclass(slots=True)
class LiveToolPresenter:
    steps: dict[str, cl.Step] = field(default_factory=dict)
    tool_names: dict[str, str] = field(default_factory=dict)
    product_names: dict[str, str] = field(default_factory=dict)
    ingredient_names: dict[str, str] = field(default_factory=dict)

    async def on_tool_called(self, item: ToolCallItem) -> None:
        call_id = item.call_id

        if not call_id:
            return

        tool_name = item.tool_name or "unknown_tool"
        arguments = _format_arguments(item.raw_item)

        logger.info(
            "Tool call started: tool=%s call_id=%s arguments=%s",
            tool_name,
            call_id,
            arguments,
        )

        title = _tool_title(
            tool_name,
            item.raw_item,
            self.product_names,
            self.ingredient_names,
        )

        step = cl.Step(
            name=_safe_step_name(title),
            type="tool",
            show_input=False,
            default_open=False,
        )

        step.output = "Investigation in progress..."

        await step.send()

        self.steps[call_id] = step
        self.tool_names[call_id] = tool_name

    async def on_tool_output(self, item: ToolCallOutputItem) -> None:
        call_id = item.call_id

        if not call_id:
            return

        step = self.steps.pop(call_id, None)
        tool_name = self.tool_names.pop(call_id, None)

        if tool_name is None:
            logger.warning(
                "Tool output received without a matching call: call_id=%s",
                call_id,
            )
            return

        result_summary = format_result(
            tool_name=tool_name,
            output=item.output,
        )

        if tool_name == "search_drugs":
            data = _parse_output(item.output)
            products = data if isinstance(data, list) else []

            for product in products:
                if not isinstance(product, Mapping):
                    continue

                product_key = _display_text(product.get("key"))
                product_name = _display_text(product.get("name"))

                if product_key and product_name:
                    self.product_names[product_key] = product_name

        elif tool_name == "get_drug_profile":
            data = _parse_output(item.output)
            product = data.get("product") if isinstance(data, Mapping) else None
            composition = (
                product.get("composition") if isinstance(product, Mapping) else None
            )

            if isinstance(composition, (list, tuple)):
                for item_composition in composition:
                    if not isinstance(item_composition, Mapping):
                        continue

                    ingredient = item_composition.get("ingredient")

                    if not isinstance(ingredient, Mapping):
                        continue

                    ingredient_key = _display_text(ingredient.get("key"))
                    ingredient_name = _display_text(ingredient.get("name"))

                    if ingredient_key and ingredient_name:
                        self.ingredient_names[ingredient_key] = ingredient_name

        logger.info(
            "Tool call completed: tool=%s call_id=%s result=%s",
            tool_name,
            call_id,
            result_summary,
        )

        if step is None:
            return

        step.output = result_summary

        await step.update()
