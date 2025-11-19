from strategies.base_strategy import BaseStrategy
from datetime import datetime
from typing import Dict, Any, List
from engine.event_engine import MarketEvent, FillEvent, SignalEvent, EventEngine
import logging

class EMACrossStrategy(BaseStrategy):
    def __init__(self, event_engine: EventEngine, logger: logging.Logger, executor_account_name: str, short_ema_period: int = 5, long_ema_period: int = 20):
        # The __init__ signature must match the way it's called in main.py,
        # and the super().__init__ call must match the BaseStrategy's __init__.
        super().__init__(event_engine, logger, executor_account_name)

        self.prices = {} # {symbol: [price1, price2, ...]}
        self.short_ema_period = short_ema_period
        self.long_ema_period = long_ema_period
        self.last_action = {} # {symbol: "BUY" or "SELL"} to prevent repeated signals

        if self.short_ema_period >= self.long_ema_period:
            raise ValueError("Short EMA period must be less than Long EMA period.")
        if self.short_ema_period <= 0 or self.long_ema_period <= 0:
            raise ValueError("EMA periods must be positive.")
        
        self.logger.info(f"[{self.strategy_name}] Initialized with Short EMA Period: {self.short_ema_period}, Long EMA Period: {self.long_ema_period}")

    async def handle_market_event(self, event: MarketEvent):
        """Handles market events by calculating EMAs and generating signals."""
        symbol = event.instrument_token
        price = event.ltp

        await self.on_tick({
            "symbol": symbol,
            "price": price,
            "timestamp": event.timestamp
        })

    async def on_tick(self, tick: Dict[str, Any]) -> None:
        symbol, price = tick.get("symbol"), tick.get("price")

        if symbol not in self.prices:
            self.prices[symbol] = []

        self.prices[symbol].append(price)

        # Keep only enough prices for the longest EMA period
        if len(self.prices[symbol]) > self.long_ema_period:
            self.prices[symbol].pop(0)

        # Need enough data for both EMAs to be calculated
        if len(self.prices[symbol]) < self.long_ema_period:
            return

        # Simple Moving Average calculation for now (as per earlier discussion)
        short_ema = sum(self.prices[symbol][-self.short_ema_period:]) / self.short_ema_period
        long_ema = sum(self.prices[symbol][-self.long_ema_period:]) / self.long_ema_period

        action = None
        current_crossover_signal = None

        if short_ema > long_ema:
            current_crossover_signal = "BUY"
        elif short_ema < long_ema:
            current_crossover_signal = "SELL"

        # Check for a *change* in crossover direction to generate a signal
        if current_crossover_signal and self.last_action.get(symbol) != current_crossover_signal:
            action = current_crossover_signal
            self.last_action[symbol] = current_crossover_signal # Update last action

        if action:
            self.logger.info(f"[{self.strategy_name}] {symbol}: Short EMA {short_ema:.2f}, Long EMA {long_ema:.2f}. Crossover -> {action} signal.")
            signal = SignalEvent(
                instrument_token=symbol,
                strategy_id=self.strategy_name,
                signal_type=action,
                quantity=10, # Example quantity
                price=price,
                order_type="MARKET"
            )
            await self.event_engine.put(signal)

    async def handle_fill_event(self, event: FillEvent):
        """Handles fill events for the EMACrossStrategy."""
        self.logger.info(f"[{self.strategy_name}] Received fill: {event.transaction_type} {event.quantity} of {event.instrument_token} @ {event.price}")
        # Update last_action based on fill if needed
        # For example, if a BUY is filled, you might want to wait for a SELL signal next.
        # self.last_action[event.instrument_token] = event.transaction_type