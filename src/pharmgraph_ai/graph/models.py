from dataclasses import dataclass, field
from typing import Any

from pharmgraph_ai.domain.interactions import DocumentedInteraction
from pharmgraph_ai.domain.models import DrugLabel, DrugProduct


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphNode:
    id: int
    label: str
    key: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphEdge:
    id: int
    source: int
    target: int
    type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphSubgraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass(frozen=True, slots=True, kw_only=True)
class InteractionInvestigation:
    findings: list[DocumentedInteraction]
    graph: GraphSubgraph


@dataclass(frozen=True, slots=True, kw_only=True)
class RelatedDrug:
    key: str
    name: str
    generic_name: str
    dosage_form: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RelatedDrugsInvestigation:
    source_product_key: str
    products: list[RelatedDrug]
    graph: GraphSubgraph


@dataclass(frozen=True, slots=True, kw_only=True)
class DrugProfileInvestigation:
    product: DrugProduct
    labels: list[DrugLabel]
    graph: GraphSubgraph
