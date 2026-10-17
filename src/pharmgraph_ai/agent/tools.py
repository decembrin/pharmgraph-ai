import dataclasses
import json
from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import Field

from pharmgraph_ai.agent.context import AgentContext

ResultLimit = Annotated[int, Field(ge=1, le=100)]


@function_tool
async def search_drugs(
    ctx: RunContextWrapper[AgentContext],
    name: str,
    dosage_form: str | None = None,
    limit: ResultLimit = 10,
) -> str:
    """Search drug products by name and optional dosage form.

    Args:
        name: Drug name.
        dosage_form: Optional dosage form filter.
            Use only when the user explicitly specifies a dosage form.
            Never infer it from general medical knowledge.
            Leave unset otherwise.
        limit: Maximum number of products (1-20).
    """
    products = await ctx.context.repository.search_products(
        name=name,
        dosage_form=dosage_form,
        limit=limit,
    )

    return json.dumps(
        [dataclasses.asdict(product) for product in products],
        ensure_ascii=False,
    )


@function_tool
async def get_drug_profile(
    ctx: RunContextWrapper[AgentContext],
    product_key: str,
) -> str:
    """Retrieve a drug product profile and verified graph relationships.

    Returns:
    - product: drug information and active ingredient composition.
    - labels: associated FDA Drug Label metadata.
    - graph.nodes: actual FalkorDB nodes.
    - graph.edges: actual CONTAINS and HAS_LABEL relationships.

    The graph relationships describe product composition and
    labeling only. They do not establish therapeutic equivalence
    or independently validate clinical conclusions.

    Args:
        product_key: Product NDC domain key obtained from the graph.
    """
    investigation = await ctx.context.repository.get_drug_profile(
        product_key=product_key,
    )

    if investigation is None:
        return json.dumps(
            {
                "status": "not_found",
                "product_key": product_key,
            }
        )

    return json.dumps(
        {
            "status": "found",
            **dataclasses.asdict(investigation),
        },
        ensure_ascii=False,
        default=str,
    )


@function_tool
async def find_related_drugs(
    ctx: RunContextWrapper[AgentContext],
    product_key: str,
    limit: ResultLimit = 10,
) -> str:
    """Find NDC drug products sharing active ingredients with a product.

    Each returned item is an individual DrugProduct identified by its NDC. The
    result establishes only that the products share at least one active
    ingredient in the knowledge graph. It does not identify confirmed
    therapeutic alternatives and does not establish therapeutic equivalence,
    bioequivalence, or interchangeability.

    Returns:
    - products: NDC-identified products sharing an active ingredient.
    - graph.nodes: actual nodes matched in FalkorDB.
    - graph.edges: actual CONTAINS relationships with directions.

    Args:
        product_key: NDC product domain key obtained from the graph.
        limit: Maximum number of matching graph rows, from 1 to 100.
    """
    investigation = await ctx.context.repository.find_related_drugs_graph(
        product_key=product_key,
        limit=limit,
    )

    return json.dumps(
        {
            "status": ("found" if investigation.products else "not_found"),
            **dataclasses.asdict(investigation),
        },
        ensure_ascii=False,
        default=str,
    )


@function_tool
async def find_documented_interactions(
    ctx: RunContextWrapper[AgentContext],
    ingredient_keys: list[str],
) -> str:
    """Investigate documented interactions between two ingredients.

    Returns:
    - findings: documented interactions and supporting evidence.
    - graph.nodes: entities actually matched in FalkorDB.
    - graph.edges: actual graph relationships and their directions.

    Graph edges must be used when explaining connectivity.
    An empty result does not establish that combining drugs is safe.

    Args:
        ingredient_keys: Exactly two ingredient domain keys obtained
            from the knowledge graph.
    """
    investigation = await ctx.context.repository.find_documented_interactions(
        ingredient_keys=ingredient_keys,
        limit=10,
    )

    return json.dumps(
        {
            "status": ("found" if investigation.findings else "not_found"),
            **dataclasses.asdict(investigation),
        },
        ensure_ascii=False,
        default=str,
    )
