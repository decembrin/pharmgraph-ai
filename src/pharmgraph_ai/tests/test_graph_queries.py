import pytest
from falkordb.asyncio import FalkorDB

from pharmgraph_ai.domain.interactions import EvidenceType, InteractionEffect
from pharmgraph_ai.graph.repository import DrugGraphRepository


@pytest.fixture
def repository() -> DrugGraphRepository:
    db = FalkorDB(
        host="falkordb",
        port=6379,
    )

    return DrugGraphRepository(db)


@pytest.mark.asyncio
async def test_search_products(repository: DrugGraphRepository) -> None:
    products = await repository.search_products(
        "Eliquis",
        limit=5,
    )

    assert len(products) == 5

    assert all(product.name.upper() == "ELIQUIS" for product in products)


@pytest.mark.asyncio
async def test_get_product(repository: DrugGraphRepository) -> None:
    product = await repository.get_product("50090-1437")

    assert product is not None
    assert product.name == "ELIQUIS"
    assert len(product.composition) == 1

    ingredient = product.composition[0].ingredient

    assert ingredient.name == "APIXABAN"
    assert product.composition[0].strength == "5 mg/1"
    assert product.has_label is True


@pytest.mark.asyncio
async def test_query_limit(repository: DrugGraphRepository) -> None:
    with pytest.raises(ValueError):
        await repository.search_products(
            "Eliquis",
            limit=1000,
        )


@pytest.mark.asyncio
async def test_interaction_returns_actual_graph_edges(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.find_documented_interactions(
        ["name:APIXABAN", "name:ASPIRIN"]
    )

    assert len(result.findings) == 1

    interaction_key = "interaction:apixaban:aspirin:increased_bleeding_risk"
    finding = result.findings[0]

    assert finding.interaction.key == interaction_key
    assert finding.interaction.effect is InteractionEffect.INCREASED_BLEEDING_RISK
    assert finding.evidence
    assert all(
        item.evidence_type is EvidenceType.DOCUMENTED for item in finding.evidence
    )

    # Map domain identifiers to FalkorDB internal IDs.
    nodes = {node.key: node.id for node in result.graph.nodes}

    assert "name:APIXABAN" in nodes
    assert "name:ASPIRIN" in nodes
    assert interaction_key in nodes

    edges = {(edge.source, edge.type, edge.target) for edge in result.graph.edges}

    assert (
        nodes["name:APIXABAN"],
        "PARTICIPATES_IN",
        nodes[interaction_key],
    ) in edges

    assert (
        nodes["name:ASPIRIN"],
        "PARTICIPATES_IN",
        nodes[interaction_key],
    ) in edges

    # Ingredients must not have a direct relationship.
    assert not any(
        source == nodes["name:APIXABAN"]
        and target == nodes["name:ASPIRIN"]
        or source == nodes["name:ASPIRIN"]
        and target == nodes["name:APIXABAN"]
        for source, _, target in edges
    )


@pytest.mark.asyncio
async def test_interactions_are_symmetric(
    repository: DrugGraphRepository,
) -> None:
    forward = await repository.find_documented_interactions(
        ["name:APIXABAN", "name:ASPIRIN"]
    )

    backward = await repository.find_documented_interactions(
        ["name:ASPIRIN", "name:APIXABAN"]
    )

    assert forward.findings
    assert backward.findings
    assert {item.interaction.key for item in forward.findings} == {
        item.interaction.key for item in backward.findings
    }


@pytest.mark.asyncio
async def test_unknown_interaction_returns_empty_graph(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.find_documented_interactions(
        ["name:APIXABAN", "name:UNKNOWN"]
    )

    assert result.findings == []
    assert result.graph.nodes == []
    assert result.graph.edges == []


@pytest.mark.asyncio
async def test_related_drugs_returns_actual_graph_edges(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.find_related_drugs_graph(
        product_key="50090-1436",
    )

    assert result.products

    nodes = {node.key: node.id for node in result.graph.nodes}

    edges = {(edge.source, edge.type, edge.target) for edge in result.graph.edges}

    assert "50090-1436" in nodes
    assert "50090-1437" in nodes
    assert "name:APIXABAN" in nodes

    assert (
        nodes["50090-1436"],
        "CONTAINS",
        nodes["name:APIXABAN"],
    ) in edges

    assert (
        nodes["50090-1437"],
        "CONTAINS",
        nodes["name:APIXABAN"],
    ) in edges

    # There must be no direct edge between the products.
    assert not any(
        (source, target)
        in {
            (nodes["50090-1436"], nodes["50090-1437"]),
            (nodes["50090-1437"], nodes["50090-1436"]),
        }
        for source, _, target in edges
    )


@pytest.mark.asyncio
async def test_related_drugs_graph_integrity(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.find_related_drugs_graph(
        product_key="50090-1436",
    )

    nodes = {node.id: node for node in result.graph.nodes}

    edges = {edge.id: edge for edge in result.graph.edges}

    assert len(nodes) == len(result.graph.nodes)
    assert len(edges) == len(result.graph.edges)

    assert all(
        edge.source in nodes and edge.target in nodes for edge in result.graph.edges
    )

    assert all(edge.type == "CONTAINS" for edge in result.graph.edges)

    assert all(
        nodes[edge.source].label == "DrugProduct"
        and nodes[edge.target].label == "Ingredient"
        for edge in result.graph.edges
    )


@pytest.mark.asyncio
async def test_drug_profile_returns_graph_edges(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.get_drug_profile("50090-1437")

    assert result is not None
    assert result.product.key == "50090-1437"

    nodes = {node.key: node.id for node in result.graph.nodes}

    edges = {(edge.source, edge.type, edge.target) for edge in result.graph.edges}

    assert (
        nodes["50090-1437"],
        "CONTAINS",
        nodes["name:APIXABAN"],
    ) in edges

    assert (
        nodes["50090-1437"],
        "HAS_LABEL",
        nodes["76e8efee-ea1e-460e-8027-443facf02ee9"],
    ) in edges


@pytest.mark.asyncio
async def test_drug_profile_graph_integrity(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.get_drug_profile("50090-1437")

    assert result is not None

    nodes = {node.id: node for node in result.graph.nodes}

    edges = {edge.id: edge for edge in result.graph.edges}

    assert len(nodes) == len(result.graph.nodes)
    assert len(edges) == len(result.graph.edges)

    assert all(
        edge.source in nodes and edge.target in nodes for edge in result.graph.edges
    )

    assert all(edge.type in {"CONTAINS", "HAS_LABEL"} for edge in result.graph.edges)

    assert len(result.product.composition) == len(
        {item.ingredient.key for item in result.product.composition}
    )


@pytest.mark.asyncio
async def test_drug_profile_not_found(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.get_drug_profile(
        "UNKNOWN-PRODUCT",
    )

    assert result is None


@pytest.mark.asyncio
async def test_drug_profile_has_label_relationship(
    repository: DrugGraphRepository,
) -> None:
    result = await repository.get_drug_profile("50090-1437")

    assert result is not None

    nodes = {node.key: node for node in result.graph.nodes}

    product = nodes["50090-1437"]
    label = nodes["76e8efee-ea1e-460e-8027-443facf02ee9"]

    assert label.label == "DrugLabel"

    assert any(
        edge.source == product.id
        and edge.target == label.id
        and edge.type == "HAS_LABEL"
        for edge in result.graph.edges
    )

    assert any(item.key == label.key for item in result.labels)
    assert result.product.has_label is True
