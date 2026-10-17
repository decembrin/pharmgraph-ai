from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Ingredient:
    key: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DrugComposition:
    ingredient: Ingredient
    strength: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DrugProduct:
    key: str
    name: str
    generic_name: str
    labeler_name: str
    dosage_form: str
    spl_id: str
    composition: list[DrugComposition]
    has_label: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class DrugLabel:
    key: str
    set_id: str
    version: int
    source_url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DrugLabelMatch:
    product_key: str
    label_key: str
