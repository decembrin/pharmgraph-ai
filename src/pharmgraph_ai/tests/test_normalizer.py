import json
from pathlib import Path

from pharmgraph_ai.ingestion.normalizer import (
    OpenFDANormalizer,
    match_labels,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_normalize_real_ndc_records() -> None:
    normalizer = OpenFDANormalizer()

    payload = load_fixture("ndc.json")

    products = [normalizer.normalize_ndc(record) for record in payload["results"]]

    assert len(products) == 13

    assert all(product.composition for product in products)

    assert all(product.has_label is False for product in products)


def test_match_real_labels() -> None:
    normalizer = OpenFDANormalizer()

    ndc_payload = load_fixture("ndc.json")
    label_payload = load_fixture("label.json")

    products = [normalizer.normalize_ndc(record) for record in ndc_payload["results"]]

    labels = [normalizer.normalize_label(record) for record in label_payload["results"]]

    matches = match_labels(products, labels)

    assert len(products) == 13
    assert len(labels) == 6
    assert len(matches) == 8

    matched_keys = {match.product_key for match in matches}

    assert "50090-1436" in matched_keys
    assert "50090-1437" in matched_keys

    assert "0003-0893" not in matched_keys


def test_different_strengths_share_ingredient() -> None:
    normalizer = OpenFDANormalizer()

    payload = load_fixture("ndc.json")

    products = {
        product.key: product
        for record in payload["results"]
        if (product := normalizer.normalize_ndc(record))
    }

    first = products["50090-1436"]
    second = products["50090-1437"]

    assert first.composition[0].ingredient.key == second.composition[0].ingredient.key

    assert first.composition[0].strength == "2.5 mg/1"
    assert second.composition[0].strength == "5 mg/1"
