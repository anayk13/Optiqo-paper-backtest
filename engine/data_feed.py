import asyncio
import csv
import os
import datetime
import time # You'll need to import time for time.time()
from zoneinfo import ZoneInfo # Import ZoneInfo for timezone awareness
from .event_engine import EventEngine, MarketEvent 
from .logger import get_logger 
from pathlib import Path

class CSVDataFeed:
    """
    Simulates a data feed by reading market data from a CSV file.
    It dispatches MarketEvent objects to the EventEngine.
    """
    def __init__(self, csv_file: Path, delay: float, event_engine: EventEngine, logger):
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        self.csv_file = csv_file
        self.delay = delay
        self.event_engine = event_engine
        self.logger = logger
        self.logger.info(f"CSVDataFeed initialized with file: {self.csv_file}, delay: {self.delay}s")

    async def generate_ticks(self):
        """Reads the CSV file line by line and dispatches MarketEvents."""
        self.logger.info(f"Starting to generate ticks from {self.csv_file}")
        with open(self.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert relevant fields to appropriate types
                try:
                    # Assuming CSV columns match expected tick data format
                    tick_data = {
                        "instrument_token": row.get("instrument_token", row.get("symbol")), 
                        # Assuming timestamp is already epoch milliseconds (as a string)
                        "timestamp": int(row["timestamp"]) if "timestamp" in row else int(time.time() * 1000), 
                        "last_traded_price": float(row["last_traded_price"]),
                        "volume": int(row.get("volume", 0)), # Corrected: use 'volume' column from CSV
                        "open": float(row.get("open", 0.0)), # Changed fallback from row["price"] to 0.0
                        "high": float(row.get("high", 0.0)), # Changed fallback
                        "low": float(row.get("low", 0.0)),   # Changed fallback
                        "close": float(row.get("close", 0.0)), # Changed fallback
                        "oi": int(row.get("oi", 0)), # 'oi' might not be in mock_ticks.csv, default to 0
                        # For bid/ask, use default 0.0 if specific bid/ask price columns are missing
                        "bid": {"price": float(row.get("bid_price", 0.0)), "quantity": int(row.get("bid_quantity", 0))},
                        "ask": {"price": float(row.get("ask_price", 0.0)), "quantity": int(row.get("ask_quantity", 0))},
                        "average_price": float(row.get("average_price", 0.0)) # Changed fallback
                    }
                    market_event = MarketEvent(
                        instrument_token=tick_data["instrument_token"],
                        ltp=tick_data["last_traded_price"],
                        timestamp=tick_data["timestamp"] / 1000.0 # Convert ms to seconds
                    )
                    await self.event_engine.put(market_event)
                    self.logger.info(f"CSV processed tick for {tick_data.get('instrument_token')}: LTP={tick_data.get('last_traded_price')}")
                except ValueError as e:
                    self.logger.error(f"Error parsing CSV row: {row}. Error: {e}")
                except KeyError as e:
                    self.logger.error(f"Missing expected column in CSV row: {row}. Error: {e}")
                await asyncio.sleep(self.delay) # Simulate delay between ticks
        self.logger.info(f"Finished generating ticks from {self.csv_file}")