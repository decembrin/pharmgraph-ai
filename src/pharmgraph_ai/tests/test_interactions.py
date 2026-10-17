from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from pharmgraph_ai.domain.interactions import (
    InteractionEffect,
)
from pharmgraph_ai.ingestion.interactions import extract_interaction


@pytest.fixture
def label_record() -> dict:
    return {
        "id": "test-label-revision",
        "set_id": "test-label-set",
        "version": "3",
        "drug_interactions": [],
    }


@pytest.fixture
def retrieved_at() -> datetime:
    return datetime(
        2026,
        10,
        16,
        tzinfo=timezone.utc,
    )


@pytest.mark.asyncio
async def test_extract_interaction_copies_conditions_to_each_evidence(
    label_record: dict,
    retrieved_at: datetime,
) -> None:
    quote = "Coadministration of aspirin increases the risk of bleeding."
    conditions = "Concomitant use of aspirin with apixaban."
    label_record["drug_interactions"] = [quote]

    class Completions:
        async def create(self, **kwargs: object) -> SimpleNamespace:
            content = (
                '{"found":true,"effect_supported":true,'
                f'"quotes":["{quote}"],"conditions":"{conditions}",'
                '"explanation":"The label directly supports the interaction."}'
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=Completions()),
    )

    result = await extract_interaction(
        record=label_record,
        ingredient_keys=("name:APIXABAN", "name:ASPIRIN"),
        effect=InteractionEffect.INCREASED_BLEEDING_RISK,
        client=client,  # type: ignore[arg-type]
        model="test-model",
        retrieved_at=retrieved_at,
    )

    assert result.conditions == conditions
    assert result.evidence
    assert all(item.conditions == conditions for item in result.evidence)
