import re
from datetime import datetime, timezone

import pytest

from pharmgraph_ai.domain.interactions import (
    DrugInteraction,
    EvidenceType,
    InteractionEffect,
    MedicalEvidence,
)
from pharmgraph_ai.graph import queries
from pharmgraph_ai.graph.repository import DrugGraphRepository


class QueryResult:
    def __init__(self, result_set: list[list[str]]) -> None:
        self.result_set = result_set


class FakeGraph:
    def __init__(self) -> None:
        self.last_query: str | None = None
        self.last_params: dict | None = None

    async def ro_query(self, query: str, *, params: dict) -> QueryResult:
        return QueryResult([[key] for key in params["keys"]])

    async def query(self, query: str, *, params: dict) -> QueryResult:
        self.last_query = query
        self.last_params = params

        if "interactions" in params:
            rows = params["interactions"]
            referenced_fields = set(re.findall(r"item\.([a-z_]+)", query))

            assert rows
            assert referenced_fields <= rows[0].keys()

        return QueryResult([])


class FakeDB:
    def __init__(self) -> None:
        self.graph = FakeGraph()

    def select_graph(self, graph_name: str) -> FakeGraph:
        return self.graph


@pytest.mark.asyncio
async def test_save_interactions_query_uses_serialized_row_fields() -> None:
    database = FakeDB()
    repository = DrugGraphRepository(database)  # type: ignore[arg-type]
    interaction = DrugInteraction(
        key="interaction:apixaban:aspirin:increased_bleeding_risk",
        ingredient_keys=("name:APIXABAN", "name:ASPIRIN"),
        effect=InteractionEffect.INCREASED_BLEEDING_RISK,
    )

    await repository.save_interactions([interaction])


@pytest.mark.asyncio
async def test_save_evidence_persists_and_updates_conditions() -> None:
    database = FakeDB()
    repository = DrugGraphRepository(database)  # type: ignore[arg-type]
    evidence = MedicalEvidence(
        key="evidence:test",
        interaction_key="interaction:apixaban:aspirin:increased_bleeding_risk",
        source="openFDA Drug Label",
        source_record_id="label-revision",
        source_url="https://example.test/label",
        label_key="label-revision",
        label_set_id="label-set",
        label_version=1,
        section="drug_interactions",
        text="Aspirin increases the risk of bleeding.",
        evidence_type=EvidenceType.DOCUMENTED,
        retrieved_at=datetime(2026, 10, 17, tzinfo=timezone.utc),
        conditions="Concomitant use of aspirin with apixaban.",
    )

    await repository.save_evidence([evidence])

    assert database.graph.last_query == queries.UPSERT_EVIDENCE
    assert database.graph.last_params is not None
    assert database.graph.last_params["evidence"][0]["conditions"] == (
        "Concomitant use of aspirin with apixaban."
    )
    assert "ON MATCH SET" in queries.UPSERT_EVIDENCE
    assert "e.conditions = row.conditions" in queries.UPSERT_EVIDENCE.split(
        "ON MATCH SET", maxsplit=1
    )[1]
