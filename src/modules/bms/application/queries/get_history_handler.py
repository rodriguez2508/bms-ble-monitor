from dataclasses import dataclass
from src.modules.bms.domain.ports.bms_repository import BmsRepository

@dataclass(frozen=True)
class GetBmsHistoryQuery:
    metric: str
    limit: int = 200

class GetBmsHistoryHandler:
    def __init__(self, repository: BmsRepository):
        self.repository = repository

    async def execute(self, query: GetBmsHistoryQuery):
        return await self.repository.get_history(query.metric, query.limit)
