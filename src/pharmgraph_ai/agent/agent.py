import os

from agents import (
    Agent,
    AsyncOpenAI,
    ModelSettings,
    OpenAIChatCompletionsModel,
    set_tracing_disabled,
)

from pharmgraph_ai.agent.context import AgentContext
from pharmgraph_ai.agent.instructions import AGENT_INSTRUCTIONS
from pharmgraph_ai.agent.tools import (
    find_documented_interactions,
    find_related_drugs,
    get_drug_profile,
    search_drugs,
)


def create_client():
    set_tracing_disabled(True)
    timeout = os.environ["OPENAI_TIMEOUT"]

    return AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        timeout=float(timeout),
        default_headers={
            "Request-Timeout": timeout,
        },
    )


def create_agent() -> Agent[AgentContext]:
    set_tracing_disabled(True)

    client = create_client()

    model = OpenAIChatCompletionsModel(
        model=os.environ["OPENAI_MODEL"],
        openai_client=client,
    )

    return Agent[AgentContext](
        name="PharmGraph AI",
        instructions=AGENT_INSTRUCTIONS,
        model=model,
        model_settings=ModelSettings(
            tool_choice="required",
            parallel_tool_calls=True,
        ),
        tools=[
            find_documented_interactions,
            find_related_drugs,
            get_drug_profile,
            search_drugs,
        ],
    )
