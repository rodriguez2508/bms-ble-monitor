from abc import ABC, abstractmethod
from typing import Optional, List
from src.modules.bms.domain.models.reading import BmsReading

class BmsRepository(ABC):
    @abstractmethod
    async def get_latest_reading(self) -> Optional[BmsReading]: pass
    @abstractmethod
    async def get_history(self, metric: str, limit: int) -> List[dict]: pass
    @abstractmethod
    async def connect(self) -> bool: pass
    @abstractmethod
    async def disconnect(self) -> None: pass
