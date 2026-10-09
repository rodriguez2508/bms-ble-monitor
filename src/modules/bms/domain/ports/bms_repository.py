from abc import ABC, abstractmethod
from typing import Optional, List
from src.modules.bms.domain.models.reading import BmsReading
from src.modules.bms.domain.models.config import BmsConfig

class BmsRepository(ABC):
    @abstractmethod
    async def get_latest_reading(self) -> Optional[BmsReading]: pass
    @abstractmethod
    async def get_history(self, metric: str, limit: int) -> List[dict]: pass
    @abstractmethod
    async def connect(self) -> bool: pass
    @abstractmethod
    async def disconnect(self) -> None: pass

    async def get_config(self) -> Optional[BmsConfig]:
        # Non-abstract: repositories without a parameter block simply return None.
        return None

    async def get_balance_log(self, limit: int) -> List[dict]:
        # Non-abstract: repositories without a balance log return nothing.
        return []
