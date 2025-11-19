import asyncio
import websockets
import json
import time # Used for time.time()
from datetime import datetime # Used for converting timestamp if needed
import logging # Added for clarity

from .event_engine import EventEngine, MarketEvent
from .logger import get_logger # Ensure get_logger is imported

class LiveDataFeed:
    def __init__(self, config: dict, event_engine: EventEngine):
        self.uri = config.get("uri")
        self.instruments = config.get("instruments", [])
        # CRITICAL CHANGE: Pass the logging level here, if you want it to be DEBUG by default for live_data_feed
        # Or, let main.py override it when calling get_logger if you prefer central control.
        # For now, I'll assume main.py will set it.
        self.logger = get_logger(main_folder_name="live_data_feed", level=logging.INFO) # Keep INFO here for default, main.py will set to DEBUG
        self.event_engine = event_engine
        self.websocket = None
        self.is_connected = False
        self._running = False
        self.logger.info(f"LiveDataFeed initialized for URI: {self.uri} with instruments: {self.instruments}")

    async def _connect(self):
        """Attempts to establish a WebSocket connection."""
        while not self.is_connected and self._running:
            try:
                self.logger.info(f"Attempting to connect to WebSocket at {self.uri}...")
                self.websocket = await websockets.connect(self.uri, ping_interval=20, ping_timeout=20)
                self.is_connected = True
                self.logger.info("Successfully connected to WebSocket.")

                if self.instruments:
                    subscription_message = json.dumps({"type": "subscribe", "instruments": self.instruments})
                    await self.websocket.send(subscription_message)
                    self.logger.info(f"Sent subscription for instruments: {self.instruments}")

            except websockets.exceptions.WebSocketException as e:
                self.logger.error(f"WebSocket connection failed: {e}. Retrying in 5 seconds...", exc_info=True)
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"An unexpected error occurred during connection: {e}. Retrying in 5 seconds...", exc_info=True)
                await asyncio.sleep(5)

    async def generate_ticks(self):
        """Generates market data ticks from the live feed."""
        self._running = True
        await self._connect()

        while self._running:
            if not self.is_connected:
                await self._connect()
                if not self.is_connected:
                    await asyncio.sleep(1)
                    continue

            try:
                message = await self.websocket.recv()
                # self.logger.debug(f"Received raw message: {message[:100]}...") # Enable for detailed debugging

                data = json.loads(message)

                instrument_token = data.get("instrument_token")
                last_traded_price = data.get("last_traded_price")
                timestamp_ms = data.get("timestamp")

                if instrument_token and last_traded_price is not None:
                    timestamp_seconds = timestamp_ms / 1000 if timestamp_ms else time.time()

                    market_event = MarketEvent(
                        instrument_token=instrument_token,
                        ltp=last_traded_price,
                        timestamp=timestamp_seconds
                    )
                    await self.event_engine.put(market_event)
                    self.logger.info(f"Processed tick for {market_event.instrument_token}: LTP={market_event.ltp}")
                else:
                    self.logger.warning(f"Received unexpected or incomplete data format: {message}")

            except websockets.exceptions.ConnectionClosed as e:
                self.logger.error(f"WebSocket connection closed unexpectedly: {e}. Attempting to reconnect...", exc_info=True)
                self.is_connected = False
                self.websocket = None
                await asyncio.sleep(1)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode JSON message: {message}. Error: {e}", exc_info=True)
            except Exception as e:
                self.logger.error(f"Error receiving or processing tick: {e}", exc_info=True)

    async def stop(self):
        """Gracefully stops the live data feed."""
        self.logger.info("Stopping LiveDataFeed...")
        self._running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.is_connected = False
        self.logger.info("LiveDataFeed stopped.")