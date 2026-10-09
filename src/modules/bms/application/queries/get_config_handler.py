from dataclasses import dataclass
from src.modules.bms.domain.ports.bms_repository import BmsRepository

@dataclass(frozen=True)
class GetBmsConfigQuery: pass

class GetBmsConfigHandler:
    def __init__(self, repository: BmsRepository):
        self.repository = repository

    async def execute(self, query: GetBmsConfigQuery):
        return await self.repository.get_config()
