"""Extract interactions for an existing graph product; dry-run unless --apply.

Does not create DrugProduct, Ingredient or DrugLabel nodes.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from falkordb.asyncio import FalkorDB

from pharmgraph_ai.agent.agent import create_client
from pharmgraph_ai.domain.interactions import InteractionEffect
from pharmgraph_ai.graph.repository import DrugGraphRepository
from pharmgraph_ai.ingestion.interactions import (
    EvidenceNotFoundError,
    extract_interaction,
)
from pharmgraph_ai.ingestion.openfda import OpenFDAClient

logger = logging.getLogger(__name__)
SOURCE_PRODUCT_NDC = "50090-1437"


@dataclass(frozen=True, slots=True, kw_only=True)
class InteractionSpec:
    ingredient_keys: tuple[str, str]
    effect: InteractionEffect


INTERACTIONS = (
    InteractionSpec(
        ingredient_keys=("name:APIXABAN", "name:ASPIRIN"),
        effect=InteractionEffect.INCREASED_BLEEDING_RISK,
    ),
    InteractionSpec(
        ingredient_keys=("name:APIXABAN", "name:KETOCONAZOLE"),
        effect=InteractionEffect.INCREASED_DRUG_EXPOSURE,
    ),
    InteractionSpec(
        ingredient_keys=("name:APIXABAN", "name:RIFAMPIN"),
        effect=InteractionEffect.DECREASED_DRUG_EXPOSURE,
    ),
)


async def fetch_label(client: OpenFDAClient, spl_id: str) -> dict[str, Any]:
    records = await client.search_labels(f'id:"{spl_id}"', limit=1)
    if not records or records[0].get("id") != spl_id:
        raise RuntimeError(f"Could not retrieve exact DrugLabel SPL ID {spl_id}")
    return records[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Persist reviewed extractions"
    )
    return parser.parse_args()


async def main(*, apply: bool = False) -> None:
    logging.basicConfig(level=logging.INFO)
    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "falkordb"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
    )
    try:
        repository = DrugGraphRepository(db)
        product = await repository.get_product(SOURCE_PRODUCT_NDC)
        if product is None or not product.spl_id:
            raise RuntimeError("Source product or its SPL ID is missing from graph")
        # DrugProduct in current models.py uses .key (not .id).
        logger.info("Source product=%s SPL=%s", product.key, product.spl_id)

        async with OpenFDAClient() as openfda:
            record = await fetch_label(openfda, product.spl_id)

        async with create_client() as llm:
            for spec in INTERACTIONS:
                try:
                    result = await extract_interaction(
                        record=record,
                        ingredient_keys=spec.ingredient_keys,
                        effect=spec.effect,
                        client=llm,
                        model=os.getenv("OLLAMA_MODEL", "pro-2026-12-01"),
                    )
                except EvidenceNotFoundError as exc:
                    logger.warning("SKIP %s: %s", spec.ingredient_keys, exc)
                    continue

                # Extraction checks do not replace human medical review.
                logger.info(
                    "CANDIDATE interaction=%s effect=%s evidence_count=%d",
                    result.interaction.key,
                    spec.effect.value,
                    len(result.evidence),
                )
                print(f"\nIngredients: {spec.ingredient_keys}")
                print(f"Effect: {spec.effect.value}")
                print(f"Conditions: {result.conditions}")
                print(f"Reasoning summary: {result.rationale}")
                for index, evidence in enumerate(result.evidence, start=1):
                    print(f"\nEvidence #{index}: {evidence.key}")
                    print(f"Citation: {evidence.text}")
                    print(f"Source: {evidence.source_url}")

                if apply:
                    # Run --apply only after reviewing all evidence and conditions.
                    # Referenced Ingredient and DrugLabel nodes must already exist.
                    await repository.save_interactions([result.interaction])
                    await repository.save_evidence(result.evidence)
                    logger.info(
                        "SAVED interaction=%s evidence_count=%d",
                        result.interaction.key,
                        len(result.evidence),
                    )
                else:
                    logger.info("DRY RUN: candidate was not saved")
    finally:
        await db.aclose()


if __name__ == "__main__":
    asyncio.run(main(apply=parse_args().apply))
