# db/models.py
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from datetime import datetime

class EventType(Enum):
    TICK = 'TICK'
    SIGNAL = 'SIGNAL'
    ORDER = 'ORDER'
    ORDER_FILLED = 'ORDER_FILLED'
    PNL_UPDATE = 'PNL_UPDATE'
    SNAPSHOT = 'SNAPSHOT'

@dataclass
class Event:
    type: EventType
    data: object

@dataclass
class Signal:
    symbol: str
    signal_type: str  # 'BUY' or 'SELL'
    confidence: float
    timestamp: datetime

@dataclass
class Order:
    symbol: str
    order_type: str  # 'MARKET'
    quantity: int
    side: str  # 'BUY' or 'SELL'
    timestamp: datetime

@dataclass
class Trade:
    symbol: str
    side: str
    quantity: int
    price: float
    timestamp: datetime