from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class InteractionEffect(StrEnum):
    INCREASED_BLEEDING_RISK = "increased_bleeding_risk"
    INCREASED_DRUG_EXPOSURE = "increased_drug_exposure"
    DECREASED_DRUG_EXPOSURE = "decreased_drug_exposure"


class EvidenceType(StrEnum):
    DOCUMENTED = "documented"


@dataclass(frozen=True, slots=True, kw_only=True)
class DrugInteraction:
    key: str
    ingredient_keys: tuple[str, str]
    effect: InteractionEffect


@dataclass(frozen=True, slots=True, kw_only=True)
class MedicalEvidence:
    key: str
    interaction_key: str

    source: str
    source_record_id: str
    source_url: str

    label_key: str
    label_set_id: str
    label_version: int

    section: str
    text: str

    evidence_type: EvidenceType
    retrieved_at: datetime

    conditions: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractedInteraction:
    interaction: DrugInteraction
    evidence: MedicalEvidence


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentedInteraction:
    interaction: DrugInteraction
    evidence: list[MedicalEvidence]


def make_interaction_key(
    ingredient_keys: tuple[str, str],
    effect: InteractionEffect,
) -> str:
    ingredients = sorted(
        ingredient.removeprefix("name:").lower() for ingredient in ingredient_keys
    )

    return f"interaction:{ingredients[0]}:{ingredients[1]}:{effect.value}"
