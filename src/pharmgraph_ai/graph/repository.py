import typing
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from falkordb.asyncio import FalkorDB

from pharmgraph_ai.domain.interactions import (
    DocumentedInteraction,
    DrugInteraction,
    EvidenceType,
    InteractionEffect,
    MedicalEvidence,
)
from pharmgraph_ai.domain.models import (
    DrugComposition,
    DrugLabel,
    DrugLabelMatch,
    DrugProduct,
    Ingredient,
)
from pharmgraph_ai.graph import queries
from pharmgraph_ai.graph.models import (
    DrugProfileInvestigation,
    GraphEdge,
    GraphNode,
    GraphSubgraph,
    InteractionInvestigation,
    RelatedDrug,
    RelatedDrugsInvestigation,
)

MAX_QUERY_LIMIT = 20


class DrugGraphRepository:
    def __init__(self, db: FalkorDB, *, graph_name: str = "pharmgraph") -> None:
        self._graph = db.select_graph(graph_name)

    async def save_products(self, products: list[DrugProduct]) -> None:
        if not products:
            return

        product_rows = [
            {
                "key": product.key,
                "name": product.name,
                "generic_name": product.generic_name,
                "labeler_name": product.labeler_name,
                "dosage_form": product.dosage_form,
                "spl_id": product.spl_id,
            }
            for product in products
        ]

        composition_rows = [
            {
                "product_key": product.key,
                "ingredient_key": item.ingredient.key,
                "ingredient_name": item.ingredient.name,
                "strength": item.strength,
            }
            for product in products
            for item in product.composition
        ]

        await self._graph.query(
            queries.UPSERT_PRODUCTS,
            params={"products": product_rows},
        )

        if composition_rows:
            await self._graph.query(
                queries.UPSERT_COMPOSITIONS,
                params={"compositions": composition_rows},
            )

    async def save_labels(self, labels: Sequence[DrugLabel]) -> None:
        if not labels:
            return

        rows = [
            {
                "key": label.key,
                "set_id": label.set_id,
                "version": label.version,
                "source_url": label.source_url,
            }
            for label in labels
        ]

        await self._graph.query(
            queries.UPSERT_LABELS,
            params={"labels": rows},
        )

    async def save_matches(self, matches: Sequence[DrugLabelMatch]) -> None:
        if not matches:
            return

        rows = [
            {
                "product_key": match.product_key,
                "label_key": match.label_key,
            }
            for match in matches
        ]

        await self._graph.query(
            queries.UPSERT_LABEL_MATCHES,
            params={"matches": rows},
        )

    async def get_product(self, product_key: str) -> DrugProduct | None:
        if not product_key.strip():
            raise ValueError("product_key must not be empty")

        result = await self._graph.ro_query(
            queries.GET_PRODUCT,
            params={"product_key": product_key},
        )

        if not result.result_set:
            return None

        return _map_product(result.result_set[0])

    async def get_drug_profile(
        self,
        product_key: str,
    ) -> DrugProfileInvestigation | None:
        result = await self._graph.ro_query(
            queries.GET_DRUG_PROFILE_GRAPH,
            params={"product_key": product_key},
        )

        if not result.result_set:
            return None

        nodes: dict[int, GraphNode] = {}
        edges: dict[int, GraphEdge] = {}

        ingredients: dict[int, DrugComposition] = {}
        labels: dict[int, DrugLabel] = {}

        product: DrugProduct | None = None

        for row in result.result_set:
            (
                product_graph_id,
                product_key,
                product_name,
                generic_name,
                labeler_name,
                dosage_form,
                spl_id,
                ingredient_graph_id,
                ingredient_key,
                ingredient_name,
                contains_edge_id,
                contains_relation,
                strength,
                label_graph_id,
                label_key,
                label_set_id,
                label_version,
                label_source_url,
                has_label_edge_id,
                has_label_relation,
            ) = row

            if product is None:
                product = DrugProduct(
                    key=product_key,
                    name=product_name or "",
                    generic_name=generic_name or "",
                    labeler_name=labeler_name or "",
                    dosage_form=dosage_form or "",
                    spl_id=spl_id or "",
                    composition=[],
                    has_label=has_label_edge_id is not None,
                )

            nodes[product_graph_id] = GraphNode(
                id=product_graph_id,
                label="DrugProduct",
                key=product_key,
            )

            # DrugProduct -[:CONTAINS]-> Ingredient
            if ingredient_graph_id is not None:
                ingredients[ingredient_graph_id] = DrugComposition(
                    ingredient=Ingredient(
                        key=ingredient_key,
                        name=ingredient_name,
                    ),
                    strength=strength,
                )

                nodes[ingredient_graph_id] = GraphNode(
                    id=ingredient_graph_id,
                    label="Ingredient",
                    key=ingredient_key,
                )

                edges[contains_edge_id] = GraphEdge(
                    id=contains_edge_id,
                    source=product_graph_id,
                    target=ingredient_graph_id,
                    type=contains_relation,
                )

            # DrugProduct -[:HAS_LABEL]-> DrugLabel
            if label_graph_id is not None:
                labels[label_graph_id] = DrugLabel(
                    key=label_key,
                    set_id=label_set_id,
                    version=int(label_version),
                    source_url=label_source_url,
                )

                nodes[label_graph_id] = GraphNode(
                    id=label_graph_id,
                    label="DrugLabel",
                    key=label_key,
                )

                edges[has_label_edge_id] = GraphEdge(
                    id=has_label_edge_id,
                    source=product_graph_id,
                    target=label_graph_id,
                    type=has_label_relation,
                )

        assert product is not None

        product = replace(
            product,
            composition=[ingredient for _, ingredient in sorted(ingredients.items())],
        )

        return DrugProfileInvestigation(
            product=product,
            labels=[label for _, label in sorted(labels.items())],
            graph=GraphSubgraph(
                nodes=[node for _, node in sorted(nodes.items())],
                edges=[edge for _, edge in sorted(edges.items())],
            ),
        )

    async def search_products(
        self,
        name: str,
        dosage_form: str | None = None,
        limit: int = 10,
    ) -> list[DrugProduct]:
        if not name.strip():
            raise ValueError("name must not be empty")

        _validate_limit(limit)

        if dosage_form == "None":
            dosage_form = None

        result = await self._graph.ro_query(
            queries.SEARCH_PRODUCTS,
            params={
                "name": name.strip(),
                "dosage_form": dosage_form.strip() if dosage_form else None,
                "limit": limit,
            },
        )

        return [_map_product(row) for row in result.result_set]

    async def find_related_drugs_graph(
        self,
        product_key: str,
        limit: int = 20,
    ) -> RelatedDrugsInvestigation:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")

        result = await self._graph.ro_query(
            queries.FIND_RELATED_DRUGS_GRAPH,
            params={
                "product_key": product_key,
                "limit": limit,
            },
        )

        products: dict[str, RelatedDrug] = {}
        nodes: dict[int, GraphNode] = {}
        edges: dict[int, GraphEdge] = {}

        for row in result.result_set:
            (
                source_graph_id,
                source_key,
                source_edge_id,
                source_relation,
                ingredient_graph_id,
                ingredient_key,
                related_edge_id,
                related_relation,
                related_graph_id,
                related_key,
                related_name,
                related_generic_name,
                related_dosage_form,
            ) = row

            products[related_key] = RelatedDrug(
                key=related_key,
                name=related_name or "",
                generic_name=related_generic_name or "",
                dosage_form=related_dosage_form or "",
            )

            for node in (
                GraphNode(
                    id=source_graph_id,
                    label="DrugProduct",
                    key=source_key,
                ),
                GraphNode(
                    id=ingredient_graph_id,
                    label="Ingredient",
                    key=ingredient_key,
                ),
                GraphNode(
                    id=related_graph_id,
                    label="DrugProduct",
                    key=related_key,
                ),
            ):
                nodes[node.id] = node

            for edge in (
                GraphEdge(
                    id=source_edge_id,
                    source=source_graph_id,
                    target=ingredient_graph_id,
                    type=source_relation,
                ),
                GraphEdge(
                    id=related_edge_id,
                    source=related_graph_id,
                    target=ingredient_graph_id,
                    type=related_relation,
                ),
            ):
                edges[edge.id] = edge

        return RelatedDrugsInvestigation(
            source_product_key=product_key,
            products=list(products.values()),
            graph=GraphSubgraph(
                nodes=[node for _, node in sorted(nodes.items())],
                edges=[edge for _, edge in sorted(edges.items())],
            ),
        )

    async def _require_existing_keys(
        self,
        *,
        query: str,
        keys: set[str],
        entity_name: str,
    ) -> None:
        if not keys:
            return

        result = await self._graph.ro_query(
            query,
            params={"keys": sorted(keys)},
        )

        existing = {row[0] for row in result.result_set}

        missing = keys - existing

        if missing:
            raise ValueError(f"Missing {entity_name}: {', '.join(sorted(missing))}")

    async def save_interactions(
        self,
        interactions: Sequence[DrugInteraction],
    ) -> None:
        if not interactions:
            return

        ingredient_keys = {
            ingredient_key
            for interaction in interactions
            for ingredient_key in interaction.ingredient_keys
        }

        await self._require_existing_keys(
            query=queries.FIND_EXISTING_INGREDIENT_KEYS,
            keys=ingredient_keys,
            entity_name="ingredients",
        )

        rows = []

        for interaction in interactions:
            ingredient_a_key, ingredient_b_key = interaction.ingredient_keys

            if ingredient_a_key == ingredient_b_key:
                raise ValueError(
                    f"Interaction {interaction.key} requires two distinct ingredients"
                )

            rows.append(
                {
                    "key": interaction.key,
                    "ingredient_a_key": ingredient_a_key,
                    "ingredient_b_key": ingredient_b_key,
                    "effect": interaction.effect.value,
                }
            )

        await self._graph.query(
            queries.UPSERT_INTERACTIONS,
            params={"interactions": rows},
        )

    async def save_evidence(
        self,
        evidence: Sequence[MedicalEvidence],
    ) -> None:
        if not evidence:
            return

        interaction_keys = {item.interaction_key for item in evidence}

        label_keys = {item.label_key for item in evidence}

        await self._require_existing_keys(
            query=queries.FIND_EXISTING_INTERACTION_KEYS,
            keys=interaction_keys,
            entity_name="interactions",
        )

        await self._require_existing_keys(
            query=queries.FIND_EXISTING_LABEL_KEYS,
            keys=label_keys,
            entity_name="drug labels",
        )

        rows = [
            {
                "key": item.key,
                "interaction_key": item.interaction_key,
                "source": item.source,
                "source_record_id": item.source_record_id,
                "source_url": item.source_url,
                "label_key": item.label_key,
                "label_set_id": item.label_set_id,
                "label_version": item.label_version,
                "section": item.section,
                "text": item.text,
                "evidence_type": item.evidence_type.value,
                "retrieved_at": item.retrieved_at.isoformat(),
                "conditions": item.conditions,
            }
            for item in evidence
        ]

        await self._graph.query(
            queries.UPSERT_EVIDENCE,
            params={"evidence": rows},
        )

    async def find_documented_interactions(
        self,
        ingredient_keys: Sequence[str],
        limit: int = 20,
    ) -> InteractionInvestigation:
        if len(ingredient_keys) != 2:
            raise ValueError("Exactly two ingredient keys are required")

        ingredient_a_key, ingredient_b_key = ingredient_keys

        if ingredient_a_key == ingredient_b_key:
            raise ValueError("Ingredient keys must be different")

        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")

        result = await self._graph.ro_query(
            queries.FIND_DOCUMENTED_INTERACTIONS,
            params={
                "ingredient_a_key": ingredient_a_key,
                "ingredient_b_key": ingredient_b_key,
                "limit": limit,
            },
        )

        interactions: dict[str, DrugInteraction] = {}
        evidence_by_interaction: dict[
            str,
            dict[str, MedicalEvidence],
        ] = {}

        nodes: dict[int, GraphNode] = {}
        edges: dict[int, GraphEdge] = {}

        for row in result.result_set:
            (
                ingredient_a_graph_id,
                ingredient_a_key,
                ingredient_b_graph_id,
                ingredient_b_key,
                interaction_graph_id,
                interaction_key,
                effect,
                evidence_graph_id,
                evidence_key,
                source,
                source_record_id,
                source_url,
                label_key,
                label_set_id,
                label_version,
                section,
                evidence_text,
                evidence_type,
                retrieved_at,
                conditions,
                label_graph_id,
                source_label_key,
                source_label_set_id,
                source_label_version,
                ingredient_a_edge_id,
                ingredient_a_relation,
                ingredient_b_edge_id,
                ingredient_b_relation,
                evidence_edge_id,
                evidence_relation,
                label_edge_id,
                label_relation,
            ) = row

            # Validate the evidence's reference to its source label.
            if (
                label_key != source_label_key
                or label_set_id != source_label_set_id
                or int(label_version) != int(source_label_version)
            ):
                raise ValueError(f"Inconsistent label provenance for {evidence_key}")

            if interaction_key not in interactions:
                interactions[interaction_key] = DrugInteraction(
                    key=interaction_key,
                    ingredient_keys=(
                        ingredient_a_key,
                        ingredient_b_key,
                    ),
                    effect=InteractionEffect(effect),
                )
                evidence_by_interaction[interaction_key] = {}

            evidence_by_interaction[interaction_key][evidence_key] = MedicalEvidence(
                key=evidence_key,
                interaction_key=interaction_key,
                source=source,
                source_record_id=source_record_id,
                source_url=source_url,
                label_key=label_key,
                label_set_id=label_set_id,
                label_version=int(label_version),
                section=section,
                text=evidence_text,
                evidence_type=EvidenceType(evidence_type),
                retrieved_at=datetime.fromisoformat(retrieved_at),
                conditions=conditions,
            )

            # Deduplicate graph nodes by FalkorDB internal ID.
            for node in (
                GraphNode(
                    id=ingredient_a_graph_id,
                    label="Ingredient",
                    key=ingredient_a_key,
                ),
                GraphNode(
                    id=ingredient_b_graph_id,
                    label="Ingredient",
                    key=ingredient_b_key,
                ),
                GraphNode(
                    id=interaction_graph_id,
                    label="DrugInteraction",
                    key=interaction_key,
                ),
                GraphNode(
                    id=evidence_graph_id,
                    label="MedicalEvidence",
                    key=evidence_key,
                ),
                GraphNode(
                    id=label_graph_id,
                    label="DrugLabel",
                    key=source_label_key,
                ),
            ):
                nodes[node.id] = node

            # Deduplicate graph edges by FalkorDB internal ID.
            for edge in (
                GraphEdge(
                    id=ingredient_a_edge_id,
                    source=ingredient_a_graph_id,
                    target=interaction_graph_id,
                    type=ingredient_a_relation,
                ),
                GraphEdge(
                    id=ingredient_b_edge_id,
                    source=ingredient_b_graph_id,
                    target=interaction_graph_id,
                    type=ingredient_b_relation,
                ),
                GraphEdge(
                    id=evidence_edge_id,
                    source=interaction_graph_id,
                    target=evidence_graph_id,
                    type=evidence_relation,
                ),
                GraphEdge(
                    id=label_edge_id,
                    source=evidence_graph_id,
                    target=label_graph_id,
                    type=label_relation,
                ),
            ):
                edges[edge.id] = edge

        findings = [
            DocumentedInteraction(
                interaction=interaction,
                evidence=list(evidence_by_interaction[interaction_key].values()),
            )
            for interaction_key, interaction in interactions.items()
        ]

        return InteractionInvestigation(
            findings=findings,
            graph=GraphSubgraph(
                nodes=[node for _, node in sorted(nodes.items())],
                edges=[edge for _, edge in sorted(edges.items())],
            ),
        )


def _validate_limit(limit: int) -> None:
    if type(limit) is not int or not 1 <= limit <= MAX_QUERY_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_LIMIT}")


def _map_product(row: Sequence[typing.Any]) -> DrugProduct:
    (
        product_key,
        name,
        generic_name,
        labeler_name,
        dosage_form,
        spl_id,
        composition_data,
        has_label,
    ) = row

    composition = [
        DrugComposition(
            ingredient=Ingredient(
                key=item["ingredient_key"],
                name=item["ingredient_name"],
            ),
            strength=item["strength"],
        )
        for item in composition_data
        if item is not None
    ]

    return DrugProduct(
        key=product_key,
        name=name,
        generic_name=generic_name,
        labeler_name=labeler_name,
        dosage_form=dosage_form,
        spl_id=spl_id,
        composition=composition,
        has_label=has_label,
    )
