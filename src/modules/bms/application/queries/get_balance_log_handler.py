from dataclasses import dataclass

from src.modules.bms.domain.ports.bms_repository import BmsRepository

MAX_BALANCE_LIMIT = 5000


@dataclass(frozen=True)
class GetBalanceLogQuery:
    limit: int = 200


class GetBalanceLogHandler:
    def __init__(self, repository: BmsRepository):
        self.repository = repository

    async def execute(self, query: GetBalanceLogQuery):
        limit = min(max(query.limit, 0), MAX_BALANCE_LIMIT)
        return await self.repository.get_balance_log(limit)
