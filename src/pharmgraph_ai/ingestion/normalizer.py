from collections.abc import Iterable, Mapping
from typing import Any

from pharmgraph_ai.domain.models import (
    DrugComposition,
    DrugLabel,
    DrugLabelMatch,
    DrugProduct,
    Ingredient,
)

type JSON = Mapping[str, Any]


class NormalizationError(ValueError):
    """Invalid or incomplete openFDA record."""


def normalize_ingredient_name(name: str) -> str:
    return " ".join(name.upper().split())


class OpenFDANormalizer:
    def normalize_ndc(self, record: JSON) -> DrugProduct:
        try:
            product_key = record["product_ndc"]
            spl_id = record["spl_id"]
            active_ingredients = record["active_ingredients"]
        except KeyError as exc:
            raise NormalizationError(
                f"Missing required NDC field: {exc.args[0]}"
            ) from exc

        if not isinstance(product_key, str) or not product_key.strip():
            raise NormalizationError("Invalid product_ndc")

        if not isinstance(spl_id, str) or not spl_id.strip():
            raise NormalizationError("Invalid spl_id")

        if not isinstance(active_ingredients, list) or not active_ingredients:
            raise NormalizationError("active_ingredients must be a non-empty list")

        composition: list[DrugComposition] = []
        for item in active_ingredients:
            if not isinstance(item, dict):
                raise NormalizationError("Invalid active ingredient")

            name = item.get("name")
            strength = item.get("strength")

            if not isinstance(name, str) or not name.strip():
                raise NormalizationError("Missing active ingredient name")

            if not isinstance(strength, str) or not strength.strip():
                raise NormalizationError("Missing active ingredient strength")

            normalized_name = normalize_ingredient_name(name)

            composition.append(
                DrugComposition(
                    ingredient=Ingredient(
                        key=f"name:{normalized_name}",
                        name=normalized_name,
                    ),
                    strength=strength.strip(),
                )
            )

        return DrugProduct(
            key=product_key,
            name=str(record.get("brand_name") or ""),
            generic_name=str(record.get("generic_name") or ""),
            labeler_name=str(record.get("labeler_name") or ""),
            dosage_form=str(record.get("dosage_form") or ""),
            spl_id=spl_id,
            composition=composition,
            has_label=False,
        )

    def normalize_label(self, record: JSON) -> DrugLabel:
        try:
            label_key = record["id"]
            set_id = record["set_id"]
            version = int(record["version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise NormalizationError("Invalid Drug Label identifiers") from exc

        if not isinstance(label_key, str) or not label_key.strip():
            raise NormalizationError("Invalid label id")

        if not isinstance(set_id, str) or not set_id.strip():
            raise NormalizationError("Invalid label set_id")

        if version < 1:
            raise NormalizationError("Invalid label version")

        return DrugLabel(
            key=label_key,
            set_id=set_id,
            version=version,
            source_url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}",
        )


def match_labels(
    products: Iterable[DrugProduct],
    labels: Iterable[DrugLabel],
) -> list[DrugLabelMatch]:
    labels_by_key = {label.key: label for label in labels}

    return [
        DrugLabelMatch(
            product_key=product.key,
            label_key=product.spl_id,
        )
        for product in products
        if product.spl_id in labels_by_key
    ]
