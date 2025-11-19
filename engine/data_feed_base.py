from abc import ABC, abstractmethod

class BaseDataFeed(ABC):
    @abstractmethod
    async def generate_ticks(self):
        """Abstract method to generate ticks."""
        pass