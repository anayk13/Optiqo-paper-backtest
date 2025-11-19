from engine.event_engine import MarketEvent, SignalEvent, EventEngine, FillEvent
from strategies.base_strategy import BaseStrategy
import logging

class SimpleTestStrategy(BaseStrategy):
    """
    A simple strategy that generates a SELL signal for a specific instrument
    when its price drops below a predefined trigger price. This is for
    testing the sell-side flow of the trading system in isolation.
    """
    def __init__(self,
                 event_engine: EventEngine,
                 logger: logging.Logger,
                 executor_account_name: str,
                 # These parameters are passed from the strategy_config.yaml
                 trigger_price: float, # This will now act as the SELL trigger
                 instrument_to_trade: str,
                 trade_quantity: int
                ):
        super().__init__(
            event_engine=event_engine,
            logger=logger,
            executor_account_name=executor_account_name
        )
        # Parameters are now dynamically loaded from the config file
        self.instrument = instrument_to_trade
        self.sell_trigger_price = trigger_price # Renamed for clarity, using the config's trigger_price
        self.trade_quantity = trade_quantity

        # Internal state management for the strategy
        # IMPORTANT: Initialized as "LONG" to allow immediate testing of sell logic
        # since there's no buy logic to initiate a position.
        self.position_status = "LONG" # Changed from "FLAT" to "LONG" for sell-only test

        self.logger.info(f"[{self.strategy_name}] Initialized for SELL-ONLY testing with "
                         f"instrument={self.instrument}, "
                         f"sell_trigger_price={self.sell_trigger_price}, "
                         f"trade_quantity={self.trade_quantity}. Starting in {self.position_status} state.")

    async def handle_market_event(self, event: MarketEvent):
        """
        Handles incoming market data (ticks) and generates trading signals.
        This method is called by the StrategyAdapter.
        """
        if event.instrument_token == self.instrument:
            current_ltp = event.ltp
            self.logger.debug(f"[{self.strategy_name}] Received tick for {self.instrument}: LTP={current_ltp}")

            # --- SELL Logic (Only) ---
            # If we are in a LONG position, sell if the price drops below the sell trigger.
            if self.position_status == "LONG" and current_ltp < self.sell_trigger_price:
                self.logger.info(f"[{self.strategy_name}] TRIGGER: LTP {current_ltp} < sell_trigger_price {self.sell_trigger_price}. Sending SELL signal for {self.instrument}.")
                signal_event = SignalEvent(
                    instrument_token=self.instrument,
                    signal_type="SELL",
                    quantity=self.trade_quantity, # Sell the quantity we are theoretically holding
                    price=current_ltp,
                    order_type="MARKET",
                    strategy_id=self.strategy_name
                )
                await self.event_engine.put(signal_event)
                self.position_status = "PENDING_FLAT_FROM_LONG" # Update state to prevent repeated signals
                self.logger.info(f"[{self.strategy_name}] Position status changed to {self.position_status}")

    async def handle_fill_event(self, event: FillEvent):
        """
        Handles incoming fill events to update the strategy's internal position status.
        This method is called by the StrategyAdapter.
        """
        self.logger.info(f"[{self.strategy_name}] Received FillEvent for Order ID: {event.order_id}, Type: {event.transaction_type}, Qty: {event.quantity}@{event.price:.2f}")

        if event.instrument_token == self.instrument:
            # Removed BUY fill logic entirely
            
            # Handling SELL fill events
            if event.transaction_type == "SELL":
                # This handles flattening a LONG position
                if self.position_status == "PENDING_FLAT_FROM_LONG":
                    self.position_status = "FLAT"
                    self.logger.info(f"[{self.strategy_name}] Position is now FLAT. Status: {self.position_status}")