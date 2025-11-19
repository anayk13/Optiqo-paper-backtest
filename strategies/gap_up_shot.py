# your_project_root/strategies/gap_up_shot.py

import asyncio
from .base_strategy import BaseStrategy
from datetime import datetime, time, date
from zoneinfo import ZoneInfo
import math
from typing import Dict, Any, List
# Ensure SignalEvent is imported if it's used within this file directly, e.g.,
from engine.event_engine import SignalEvent, MarketEvent, FillEvent, EventEngine # Assuming this path
import logging


class GapUpShot(BaseStrategy):
    """
    A simple gap-up shorting strategy.
    Generates a SELL signal if the stock gaps up by a certain threshold at open.
    """
    def __init__(self, event_engine: EventEngine, logger: logging.Logger, executor_account_name: str, threshold: float = 2.0, volume_limit: int = 1000000, top_n_stocks: int = 3):
        # The __init__ signature must match the way it's called in main.py,
        # and the super().__init__ call must match the BaseStrategy's __init__.
        super().__init__(event_engine, logger, executor_account_name)
        self.threshold = threshold
        self.volume_limit = volume_limit
        self.top_n_stocks = top_n_stocks

        self.logger.info(f"GapUpShot strategy initialized with threshold={self.threshold}%, volume_limit={self.volume_limit}, top_n_stocks={self.top_n_stocks}")
        
        # State for daily gap calculation and signal management
        self.today_date = None
        self.daily_gap_data: Dict[str, Dict[str, Any]] = {}
        self.signals_issued_today = set()
        self.top_stocks_identified = False

        self.timezone = ZoneInfo("Asia/Kolkata")
        self.pre_open_start = time(9, 0)
        self.pre_open_end = time(9, 7)
        self.morning_start = time(9, 8)
        self.morning_end = time(9, 25)
        self.signal_trigger_time = time(9, 8)

    async def handle_market_event(self, event: MarketEvent):
        """Handles market events by delegating to the on_tick method."""
        # This strategy was written with an 'on_tick' style handler.
        # We can adapt it by converting the MarketEvent to a dictionary.
        tick_data = event.__dict__
        await self.on_tick(tick_data)

    async def on_tick(self, data: dict) -> List[Dict[str, Any]]:
        """
        Processes incoming market data (ticks).
        Determines if a SELL signal should be generated based on gap-up conditions.
        """
        instrument_token = data.get("instrument_token")
        current_price = data.get("last_traded_price")
        open_price = data.get("open")
        prev_close_price = data.get("close")
        current_volume = data.get("volume")

        if not all([instrument_token, current_price is not None, open_price is not None, prev_close_price is not None, current_volume is not None]):
            self.logger.warning(f"[{self.strategy_name}] Missing data in tick for {instrument_token}. Skipping. Data: {data}")
            return

        try:
            tick_datetime = datetime.fromtimestamp(data.get("timestamp") / 1000, tz=self.timezone)
        except (TypeError, ValueError):
            self.logger.warning(f"[{self.strategy_name}] Invalid timestamp in tick for {instrument_token}. Using system time.")
            tick_datetime = datetime.now(self.timezone)
        
        current_date = tick_datetime.date()
        current_time = tick_datetime.time()

        if self.today_date is None or self.today_date != current_date:
            self.logger.info(f"[{self.strategy_name}] New day detected: {current_date}. Resetting daily data.")
            self.today_date = current_date
            self.daily_gap_data = {}
            self.signals_issued_today = set()
            self.top_stocks_identified = False

        if (self.pre_open_start <= current_time <= self.morning_end) and not self.top_stocks_identified:
            if instrument_token not in self.daily_gap_data:
                self.daily_gap_data[instrument_token] = {
                    "open_price": open_price,
                    "previous_close": prev_close_price,
                    "latest_volume": current_volume,
                    "last_tick_time": current_time
                }
            else:
                if current_time > self.daily_gap_data[instrument_token]["last_tick_time"]:
                    self.daily_gap_data[instrument_token]["latest_volume"] = current_volume
                    self.daily_gap_data[instrument_token]["last_tick_time"] = current_time
        
        if current_time >= self.signal_trigger_time and not self.top_stocks_identified:
            if current_time > self.morning_end:
                self.logger.warning(f"[{self.strategy_name}] Gap-up identification triggered too late at {current_time}. Skipping for today.")
                self.top_stocks_identified = True
                return []

            self.logger.info(f"[{self.strategy_name}] Triggering top {self.top_n_stocks} gap-up stock identification at {current_time}.")
            self.top_stocks_identified = True

            potential_signals = []
            for token, data_entry in self.daily_gap_data.items():
                open_price_candidate = data_entry.get("open_price")
                prev_close_candidate = data_entry.get("previous_close")
                latest_volume_candidate = data_entry.get("latest_volume", 0)

                if open_price_candidate is None or prev_close_candidate is None or prev_close_candidate == 0:
                    self.logger.warning(f"[{self.strategy_name}] Incomplete data for {token} during analysis. Skipping.")
                    continue

                gap_percentage = ((open_price_candidate - prev_close_candidate) / prev_close_candidate) * 100

                if gap_percentage >= self.threshold and latest_volume_candidate <= self.volume_limit:
                    potential_signals.append({
                        "instrument_token": token,
                        "gap_percentage": gap_percentage,
                        "open_price": open_price_candidate,
                        "volume": latest_volume_candidate
                    })
            
            potential_signals.sort(key=lambda x: x["gap_percentage"], reverse=True)
            top_n_gap_ups = potential_signals[:self.top_n_stocks]

            generated_signals = []
            for sig_data in top_n_gap_ups:
                if sig_data["instrument_token"] not in self.signals_issued_today:
                    self.logger.info(f"[{self.strategy_name}] Identified Top Gap-Up: {sig_data['instrument_token']} - Gap %: {sig_data['gap_percentage']:.2f}% (Open: {sig_data['open_price']:.2f}, Volume: {sig_data['volume']}) -> Generating SELL signal.")
                    
                    signal_event = SignalEvent(
                        instrument_token=sig_data["instrument_token"],
                        strategy_id=self.strategy_name,
                        signal_type="SELL",
                        quantity=100,
                        price=sig_data["open_price"],
                        order_type="MARKET",
                        product_type="MIS",
                        validity="DAY",
                        tag="GapUpShot"
                    )
                    self.event_engine.put(signal_event)
                    self.signals_issued_today.add(sig_data["instrument_token"])
            return generated_signals

        return []

    async def handle_fill_event(self, event: FillEvent):
        """Handles fill events for the GapUpShot strategy."""
        self.logger.info(f"[{self.strategy_name}] Received fill: {event.transaction_type} {event.quantity} of {event.instrument_token} @ {event.price}")
        # Add logic here to update position status if needed for this strategy