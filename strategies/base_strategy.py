# Assuming this is in engine/base_strategy.py or strategies/base_strategy.py
from abc import ABC, abstractmethod
import logging
from engine.event_engine import EventEngine, MarketEvent, FillEvent # Import FillEvent

class BaseStrategy(ABC):
    def __init__(self, event_engine: EventEngine, logger: logging.Logger, executor_account_name: str):
        self.event_engine = event_engine
        self.logger = logger
        self.executor_account_name = executor_account_name
        self.strategy_name = self.__class__.__name__

    @abstractmethod
    async def handle_market_event(self, event: MarketEvent):
        """Handle incoming market data."""
        pass

    @abstractmethod
    async def handle_fill_event(self, event: FillEvent):
        """Handle incoming fill events."""
        pass
