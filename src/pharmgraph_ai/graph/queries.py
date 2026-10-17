UPSERT_PRODUCTS = """
UNWIND $products AS row
MERGE (p:DrugProduct {key: row.key})
SET
    p.name = row.name,
    p.generic_name = row.generic_name,
    p.labeler_name = row.labeler_name,
    p.dosage_form = row.dosage_form,
    p.spl_id = row.spl_id
"""

UPSERT_COMPOSITIONS = """
UNWIND $compositions AS row
MERGE (i:Ingredient {key: row.ingredient_key})
SET i.name = row.ingredient_name
WITH row, i
MATCH (p:DrugProduct {key: row.product_key})
MERGE (p)-[r:CONTAINS]->(i)
SET r.strength = row.strength
"""

UPSERT_LABELS = """
UNWIND $labels AS row
MERGE (l:DrugLabel {key: row.key})
SET
    l.set_id = row.set_id,
    l.version = row.version,
    l.source_url = row.source_url
"""

UPSERT_LABEL_MATCHES = """
UNWIND $matches AS row
MATCH (p:DrugProduct {key: row.product_key})
MATCH (l:DrugLabel {key: row.label_key})
MERGE (p)-[:HAS_LABEL]->(l)
"""

GET_PRODUCT = """
MATCH (p:DrugProduct {key: $product_key})
WITH p, exists((p)-[:HAS_LABEL]->(:DrugLabel)) AS has_label
OPTIONAL MATCH (p)-[r:CONTAINS]->(i:Ingredient)
RETURN
    p.key,
    p.name,
    p.generic_name,
    p.labeler_name,
    p.dosage_form,
    p.spl_id,
    collect(
        CASE
            WHEN i IS NOT NULL THEN {
                ingredient_key: i.key,
                ingredient_name: i.name,
                strength: r.strength
            }
            ELSE NULL
        END
    ) AS composition,
    has_label
"""

SEARCH_PRODUCTS = """
MATCH (p:DrugProduct)
WHERE (
    toLower(p.name) CONTAINS toLower($name) OR toLower(p.generic_name) CONTAINS toLower($name)
) AND (
    $dosage_form IS NULL OR toLower(p.dosage_form) CONTAINS toLower($dosage_form)
)
OPTIONAL MATCH (p)-[:HAS_LABEL]->(l:DrugLabel)
WITH p, exists(l) AS has_label
ORDER BY has_label DESC, p.name, p.key
LIMIT $limit
OPTIONAL MATCH (p)-[r:CONTAINS]->(i:Ingredient)
RETURN
    p.key,
    p.name,
    p.generic_name,
    p.labeler_name,
    p.dosage_form,
    p.spl_id,
    collect(
        CASE
            WHEN i IS NOT NULL THEN {
                ingredient_key: i.key,
                ingredient_name: i.name,
                strength: r.strength
            }
            ELSE NULL
        END
    ) AS composition,
    has_label
ORDER BY has_label DESC, p.name, p.key
"""

FIND_PRODUCTS_BY_INGREDIENT = """
MATCH (source:DrugProduct {key: $product_key})
      -[:CONTAINS]->(ingredient:Ingredient)
      <-[:CONTAINS]-(related:DrugProduct)
WHERE source.key <> related.key
WITH DISTINCT related AS p
ORDER BY p.key
LIMIT $limit
OPTIONAL MATCH (p)-[r:CONTAINS]->(i:Ingredient)
RETURN
    p.key,
    p.name,
    p.generic_name,
    p.labeler_name,
    p.dosage_form,
    p.spl_id,
    collect(
        CASE
            WHEN i IS NOT NULL THEN {
                ingredient_key: i.key,
                ingredient_name: i.name,
                strength: r.strength
            }
            ELSE NULL
        END
    ) AS composition
ORDER BY p.key
"""

FIND_EXISTING_INGREDIENT_KEYS = """
MATCH (i:Ingredient)
WHERE i.key IN $keys
RETURN i.key
"""

FIND_EXISTING_INTERACTION_KEYS = """
MATCH (i:DrugInteraction)
WHERE i.key IN $keys
RETURN i.key
"""

FIND_EXISTING_LABEL_KEYS = """
MATCH (l:DrugLabel)
WHERE l.key IN $keys
RETURN l.key
"""

UPSERT_INTERACTIONS = """
UNWIND $interactions AS item
MATCH (a:Ingredient {key: item.ingredient_a_key})
MATCH (b:Ingredient {key: item.ingredient_b_key})
MERGE (interaction:DrugInteraction {key: item.key})
SET interaction.effect = item.effect
MERGE (a)-[:PARTICIPATES_IN]->(interaction)
MERGE (b)-[:PARTICIPATES_IN]->(interaction)
"""


UPSERT_EVIDENCE = """
UNWIND $evidence AS row
MATCH (interaction:DrugInteraction {key: row.interaction_key})
MATCH (label:DrugLabel {key: row.label_key})
MERGE (e:MedicalEvidence {key: row.key})
ON CREATE SET
    e.source = row.source,
    e.source_record_id = row.source_record_id,
    e.source_url = row.source_url,
    e.label_key = row.label_key,
    e.label_set_id = row.label_set_id,
    e.label_version = row.label_version,
    e.section = row.section,
    e.text = row.text,
    e.evidence_type = row.evidence_type,
    e.retrieved_at = row.retrieved_at,
    e.conditions = row.conditions
ON MATCH SET
    e.conditions = row.conditions
MERGE (interaction)-[:SUPPORTED_BY]->(e)
MERGE (e)-[:EXTRACTED_FROM]->(label)
"""

FIND_DOCUMENTED_INTERACTIONS = """
MATCH (a:Ingredient {key: $ingredient_a_key})
MATCH (b:Ingredient {key: $ingredient_b_key})
MATCH (a)-[ra:PARTICIPATES_IN]->(interaction:DrugInteraction)<-[rb:PARTICIPATES_IN]-(b)
MATCH (interaction)-[re:SUPPORTED_BY]->(e:MedicalEvidence)
MATCH (e)-[rl:EXTRACTED_FROM]->(label:DrugLabel)
RETURN
    id(a),
    a.key,
    id(b),
    b.key,
    id(interaction),
    interaction.key,
    interaction.effect,
    id(e),
    e.key,
    e.source,
    e.source_record_id,
    e.source_url,
    e.label_key,
    e.label_set_id,
    e.label_version,
    e.section,
    e.text,
    e.evidence_type,
    e.retrieved_at,
    e.conditions,
    id(label),
    label.key,
    label.set_id,
    label.version,
    id(ra),
    type(ra),
    id(rb),
    type(rb),
    id(re),
    type(re),
    id(rl),
    type(rl)
ORDER BY interaction.key, e.key
LIMIT $limit
"""

FIND_RELATED_DRUGS_GRAPH = """
MATCH (source:DrugProduct {key: $product_key})
      -[source_edge:CONTAINS]->
      (ingredient:Ingredient)
      <-[related_edge:CONTAINS]-
      (related:DrugProduct)
WHERE source <> related
RETURN
    id(source),
    source.key,
    id(source_edge),
    type(source_edge),
    id(ingredient),
    ingredient.key,
    id(related_edge),
    type(related_edge),
    id(related),
    related.key,
    related.name,
    related.generic_name,
    related.dosage_form
ORDER BY related.key, ingredient.key
LIMIT $limit
"""


GET_DRUG_PROFILE_GRAPH = """
MATCH (p:DrugProduct {key: $product_key})
OPTIONAL MATCH (p)-[contains:CONTAINS]->(i:Ingredient)
OPTIONAL MATCH (p)-[has_label:HAS_LABEL]->(l:DrugLabel)
RETURN
    id(p),
    p.key,
    p.name,
    p.generic_name,
    p.labeler_name,
    p.dosage_form,
    p.spl_id,
    id(i),
    i.key,
    i.name,
    id(contains),
    type(contains),
    contains.strength,
    id(l),
    l.key,
    l.set_id,
    l.version,
    l.source_url,
    id(has_label),
    type(has_label)
ORDER BY i.key, l.key
"""
