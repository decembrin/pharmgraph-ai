import dataclasses

from pharmgraph_ai.graph.repository import DrugGraphRepository


@dataclasses.dataclass(slots=True, kw_only=True)
class AgentContext:
    repository: DrugGraphRepository
