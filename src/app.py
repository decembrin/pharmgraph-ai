import json
import logging
import os
from collections.abc import Mapping

import chainlit as cl
from agents import (
    MaxTurnsExceeded,
    Runner,
    ToolCallItem,
    ToolCallOutputItem,
)
from falkordb.asyncio import FalkorDB

from pharmgraph_ai.agent.agent import create_agent
from pharmgraph_ai.agent.context import AgentContext
from pharmgraph_ai.graph.repository import DrugGraphRepository
from pharmgraph_ai.ui.tool_presenter import LiveToolPresenter

logger = logging.getLogger(__name__)

MAX_AGENT_TURNS = 8
MAX_TOOL_OUTPUT_CHARS = 3000
SESSION_HISTORY_KEY = "agent_history"


logging.getLogger("chainlit").setLevel(logging.INFO)


@cl.on_chat_start
async def on_chat_start() -> None:
    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "falkordb"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
    )

    repository = DrugGraphRepository(db)

    context = AgentContext(
        repository=repository,
    )

    cl.user_session.set("db", db)
    cl.user_session.set("context", context)
    cl.user_session.set("agent", create_agent())
    cl.user_session.set("history", [])

    await cl.Message(
        content=(
            "Welcome to **PharmGraph AI** — an AI agent for exploring "
            "drug relationships using FalkorDB.\n\n"
            "**Available drugs:** Eliquis, Aspirin, Advil, Motrin IB, "
            "PediaCare, Claritin, and Tylenol.\n\n"
            "I can investigate active ingredients, discover related drugs, "
            "identify documented interactions, and explain findings "
            "using medical evidence.\n\n"
            "Ask me about a drug or a potential interaction!\n\n"
            "*For medical research only. Not medical advice.*"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Process user messages using the PharmGraph AI agent."""

    db = cl.user_session.get("db")

    history: list[dict] = (
        cl.user_session.get(
            SESSION_HISTORY_KEY,
        )
        or []
    )

    agent_input = [
        *history,
        {
            "role": "user",
            "content": message.content,
        },
    ]

    repository = cl.user_session.get("repository")

    if repository is None:
        repository = DrugGraphRepository(db)
        cl.user_session.set("repository", repository)

    context = AgentContext(repository=repository)

    agent = cl.user_session.get("agent")

    if agent is None:
        agent = create_agent()
        cl.user_session.set("agent", agent)

    presenter = LiveToolPresenter()

    try:
        result = Runner.run_streamed(
            agent,
            input=agent_input,
            context=context,
            max_turns=MAX_AGENT_TURNS,
        )

        async for event in result.stream_events():
            if event.type != "run_item_stream_event":
                continue

            if event.name == "tool_called" and isinstance(event.item, ToolCallItem):
                await presenter.on_tool_called(event.item)

            elif event.name == "tool_output" and isinstance(
                event.item, ToolCallOutputItem
            ):
                await presenter.on_tool_output(event.item)

        final_output = result.final_output

        if final_output is None:
            await cl.Message(
                content="The agent completed the investigation but did not produce a final response.",
            ).send()

            return

        await cl.Message(
            content=str(final_output),
        ).send()

        cl.user_session.set(
            SESSION_HISTORY_KEY,
            result.to_input_list(),
        )

    except MaxTurnsExceeded:
        logger.warning(
            "Agent exceeded maximum turns: %s",
            MAX_AGENT_TURNS,
        )

        await cl.Message(
            content=(
                "The investigation stopped because the agent reached the maximum "
                "number of steps. Try refining your question."
            ),
        ).send()

    except Exception:
        logger.exception("PharmGraph AI agent execution failed")

        await cl.Message(
            content="An error occurred during the investigation. Please try again.",
        ).send()


@cl.on_chat_end
async def on_chat_end() -> None:
    db = cl.user_session.get("db")

    if db is not None:
        await db.aclose()


def format_arguments(raw_item: object) -> str:
    if isinstance(raw_item, Mapping):
        arguments = raw_item.get("arguments")
    else:
        arguments = getattr(raw_item, "arguments", None)

    if arguments is None:
        return "{}"

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return arguments

    return json.dumps(
        arguments,
        indent=2,
        ensure_ascii=False,
    )


class ToolCallStreamHandler:
    def __init__(self) -> None:
        self._steps: dict[str, cl.Step] = {}

    async def on_tool_called(
        self,
        item: ToolCallItem,
    ) -> None:
        step = cl.Step(
            name=item.tool_name,
            type="tool",
            show_input=True,
        )

        step.input = format_arguments(item.raw_item)
        step.output = "Executing..."

        await step.send()

        self._steps[item.call_id] = step

    async def on_tool_output(
        self,
        item: ToolCallOutputItem,
    ) -> None:
        step = self._steps.get(item.call_id)

        if step is None:
            return

        output = str(item.output)

        if len(output) > MAX_TOOL_OUTPUT_CHARS:
            output = output[:MAX_TOOL_OUTPUT_CHARS] + "\n... [truncated for display]"

        step.output = output

        await step.update()
