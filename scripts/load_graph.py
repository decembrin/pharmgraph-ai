import asyncio

from falkordb.asyncio import FalkorDB

from pharmgraph_ai.graph.repository import DrugGraphRepository
from pharmgraph_ai.ingestion.normalizer import OpenFDANormalizer, match_labels
from pharmgraph_ai.ingestion.openfda import OpenFDAClient


async def load_drug_products(repository: DrugGraphRepository, query: str):
    print("Load DrugProducts: ", query)
    normalizer = OpenFDANormalizer()

    drug_products = []
    batch_size, skip = 100, 0
    while True:
        async with OpenFDAClient() as client:
            records = await client.search_ndc(
                query=query,
                limit=batch_size,
                skip=skip,
            )

        drug_products.extend([normalizer.normalize_ndc(record) for record in records])

        if len(records) < batch_size:
            break

        skip += batch_size

    await repository.save_products(drug_products)

    return drug_products


async def load_labels(repository: DrugGraphRepository, query: str) -> list:
    print("Load Labels: ", query)
    normalizer = OpenFDANormalizer()

    labels = []
    batch_size, skip = 100, 0
    while True:
        async with OpenFDAClient() as client:
            records = await client.search_labels(
                query=query,
                limit=batch_size,
                skip=skip,
            )

        labels.extend([normalizer.normalize_label(record) for record in records])

        if len(records) < batch_size:
            break

        skip += batch_size

    await repository.save_labels(labels)

    return labels


async def main() -> None:
    db = FalkorDB(host="falkordb", port=6379)
    repository = DrugGraphRepository(db)

    queries = [
        ("generic_name.exact:APIXABAN", "openfda.generic_name.exact:ASPIRIN"),
        ("generic_name.exact:ASPIRIN", "openfda.generic_name.exact:ASPIRIN"),
        ("brand_name.exact:ASPIRIN", "openfda.brand_name.exact:ASPIRIN"),
        ("generic_name.exact:ELIQUIS", "openfda.generic_name.exact:ELIQUIS"),
        ("brand_name.exact:ELIQUIS", "openfda.brand_name.exact:ELIQUIS"),
        ("generic_name.exact:KETOCONAZOLE", "openfda.generic_name.exact:KETOCONAZOLE"),
        ("brand_name.exact:KETOCONAZOLE", "openfda.brand_name.exact:KETOCONAZOLE"),
        ("generic_name.exact:RIFAMPIN", "openfda.generic_name.exact:RIFAMPIN"),
        ("brand_name.exact:RIFAMPIN", "openfda.brand_name.exact:RIFAMPIN"),
        ("brand_name.exact:Advil", "openfda.brand_name.exact:Advil"),
        ('brand_name.exact:"MOTRIN IB"', 'openfda.brand_name.exact:"MOTRIN IB"'),
        (
            'brand_name.exact:"Pediacare Childrens Ibuprofen Berry"',
            'openfda.brand_name.exact:"Pediacare Childrens Ibuprofen Berry"',
        ),
        (
            'brand_name.exact:"Claritin"',
            'openfda.brand_name.exact:"Claritin"',
        ),
        (
            'brand_name.exact:"TYLENOL EXTRA STRENGTH"',
            'openfda.brand_name.exact:"TYLENOL EXTRA STRENGTH"',
        ),
    ]

    for ndc_query, label_query in queries:
        drug_products, labels = await asyncio.gather(
            load_drug_products(repository, query=ndc_query),
            load_labels(repository, query=label_query),
        )

        matches = match_labels(drug_products, labels)

        await repository.save_matches(matches)


if __name__ == "__main__":
    asyncio.run(main())
