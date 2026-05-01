from dataclasses import dataclass
from src.modules.bms.domain.ports.bms_repository import BmsRepository

@dataclass(frozen=True)
class GetBmsStatusQuery: pass

class GetBmsStatusHandler:
    def __init__(self, repository: BmsRepository):
        self.repository = repository

    async def execute(self, query: GetBmsStatusQuery):
        return await self.repository.get_latest_reading()
