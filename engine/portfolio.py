import os
import json # <--- ADDED THIS IMPORT
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .logger import get_logger
from .broker import BaseBroker
from .event_engine import FillEvent
POSITIONS_FILE="logs/reports/positions.json"

class PortfolioManager:
    """
    A manager class for handling portfolio operations across multiple brokers and strategies.
    It tracks positions, cash, PnL, processes fill events, and can generate performance reports.
    """

    def __init__(self,
                 broker_name: str,
                 account_name: str,
                 strategy_name: str,
                 broker: BaseBroker,
                 initial_cash: float):
        self.broker_name = broker_name
        self.account_name = account_name
        self.strategy_name = strategy_name
        self.broker = broker
        self.logger = get_logger(
            main_folder_name="portfolio",
            broker_name=broker_name,
            account_name=account_name,
            strategy_name=strategy_name
        )
        self.initial_cash = initial_cash
        self.current_cash = initial_cash

        # Positions: {instrument_token: {'quantity': X, 'avg_price': Y, 'last_known_price': Z}}
        self.positions: Dict[str, Dict[str, Any]] = {}


        self.equity_curve: List[Dict[str, Any]] = []
        self.portfolio_trades: List[Dict[str, Any]] = []

        self._load_positions()

        self.logger.info(f"PortfolioManager initialized with {self.initial_cash} cash.")

    async def initialize(self):
        """
        Asynchronously initializes PortfolioManager, including recording the initial equity snapshot.
        This method should be called after instantiation in an async context (e.g., main()).
        """
        current_time = datetime.now(ZoneInfo("Asia/Kolkata")) # Use timezone-aware time
        await self._record_equity_snapshot(self.current_cash, current_time)
        self.logger.info(f"Initial equity snapshot recorded for {self.account_name}.")

    def _load_positions(self):
        """Loads positions from the JSON file if it exists."""
        try:
            if os.path.exists(POSITIONS_FILE):
                with open(POSITIONS_FILE, 'r') as f:
                    data = json.load(f)
                    broker_key = f"{self.broker_name.upper()}_ACCOUNTS"
                    if broker_key in data and \
                       self.account_name in data[broker_key] and \
                       self.strategy_name in data[broker_key][self.account_name] and \
                       "positions" in data[broker_key][self.account_name][self.strategy_name]:

                        loaded_positions_list = data[broker_key][self.account_name][self.strategy_name]["positions"]
                        self.positions = {p['instrument_token']: p for p in loaded_positions_list}
                        self.current_cash = data[broker_key][self.account_name][self.strategy_name].get("current_cash", self.initial_cash)
                        self.logger.info(f"Loaded {len(self.positions)} positions for {self.strategy_name}.")
                        self.logger.info(f"Loaded cash: {self.current_cash:.2f}")
        except Exception as e:
            self.logger.error(f"Failed to load positions from {POSITIONS_FILE}: {e}", exc_info=True)
            self.positions = {} # Reset to empty if loading fails
            self.current_cash = self.initial_cash # Reset cash if loading fails

    def _save_positions(self):
        """Saves current positions and cash to the JSON file."""
        try:
            os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)

            data = {}
            if os.path.exists(POSITIONS_FILE):
                with open(POSITIONS_FILE, 'r') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {} # Handle empty or malformed JSON

            broker_key = f"{self.broker_name.upper()}_ACCOUNTS"
            data.setdefault(broker_key, {})
            data[broker_key].setdefault(self.account_name, {})
            data[broker_key][self.account_name].setdefault(self.strategy_name, {})

            data[broker_key][self.account_name][self.strategy_name]["positions"] = list(self.positions.values())
            data[broker_key][self.account_name][self.strategy_name]["current_cash"] = self.current_cash

            with open(POSITIONS_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            self.logger.info(f"Positions and cash saved to {POSITIONS_FILE} for strategy: {self.strategy_name}. Current Cash: {self.current_cash:.2f}")
        except Exception as e:
            self.logger.error(f"Failed to save positions to {POSITIONS_FILE}: {e}", exc_info=True)

    async def on_fill_event(self, event: FillEvent):
        """
        Processes a FillEvent to update portfolio positions and cash.
        """
        self.logger.info(f"[{self.strategy_name}] PortfolioManager received FillEvent for Order ID: {event.order_id}, Instrument: {event.instrument_token}")

        instrument_token = event.instrument_token
        quantity = event.quantity
        price = event.price
        transaction_type = event.transaction_type # BUY or SELL
        brokerage = event.brokerage # Brokerage from the fill event

        # Update cash
        if transaction_type == "BUY":
            cost = (quantity * price) + brokerage
            self.current_cash -= cost
            self.logger.info(f"BUY fill: {quantity}@{price:.2f}. Cost: {cost:.2f}. Current Cash: {self.current_cash:.2f}")
        elif transaction_type == "SELL":
            revenue = (quantity * price) - brokerage
            self.current_cash += revenue
            self.logger.info(f"SELL fill: {quantity}@{price:.2f}. Revenue: {revenue:.2f}. Current Cash: {self.current_cash:.2f}")

        # Update positions
        if instrument_token not in self.positions:
            self.positions[instrument_token] = {
                "instrument_token": instrument_token,
                "quantity": 0,
                "avg_price": 0.0,
                "last_known_price": price
            }

        current_pos = self.positions[instrument_token]

        if transaction_type == "BUY":
            # For BUYs, calculate new average price for long position
            old_total_value = current_pos["quantity"] * current_pos["avg_price"]
            new_quantity = current_pos["quantity"] + quantity
            if new_quantity == 0: # Should not happen on buy unless covering short
                 current_pos["avg_price"] = 0.0
            else:
                 current_pos["avg_price"] = (old_total_value + (quantity * price)) / new_quantity
            current_pos["quantity"] = new_quantity

        elif transaction_type == "SELL":
            # For SELLs, if covering a long, calculate realized PnL. If opening a short, set avg_price.
            # Simplified:
            new_quantity = current_pos["quantity"] - quantity
            if new_quantity == 0:
                # If position is completely closed, calculate realized PnL here
                # (sell_price - avg_buy_price) * quantity_closed_long
                # (avg_sell_price - buy_price) * quantity_closed_short
                # For now, relying on cash change for overall PnL.
                current_pos["avg_price"] = 0.0
            elif (current_pos["quantity"] > 0 and new_quantity < 0) or \
                 (current_pos["quantity"] < 0 and new_quantity > 0):
                # This implies reversing position (long to short or vice-versa)
                # This is a more complex PnL calculation scenario, simplified for now
                current_pos["avg_price"] = price # New average price for the new direction

            current_pos["quantity"] = new_quantity

        # Remove position if quantity becomes zero
        if current_pos["quantity"] == 0:
            del self.positions[instrument_token]
            self.logger.info(f"Position for {instrument_token} closed. Remaining positions: {self.positions.keys()}")

        # Record the fill event in internal trade log
        self.portfolio_trades.append({
            "timestamp": datetime.fromtimestamp(event.fill_timestamp, tz=ZoneInfo("Asia/Kolkata")), # Convert timestamp to datetime object
            "instrument_token": event.instrument_token,
            "order_id": event.order_id,
            "exchange_order_id": event.exchange_order_id,
            "transaction_type": event.transaction_type,
            "quantity": event.quantity,
            "price": event.price, # The price from the fill event
            "brokerage": event.brokerage,
            "current_cash_after_trade": self.current_cash
        })

        self._save_positions() # Save updated positions and cash after each fill

        # --- Record Equity Snapshot after each fill ---
        current_time_for_snapshot = datetime.fromtimestamp(event.fill_timestamp, tz=ZoneInfo("Asia/Kolkata"))
        await self._record_equity_snapshot(self.current_cash, current_time_for_snapshot)

    async def _record_equity_snapshot(self, current_cash: float, timestamp: datetime):
        """Records a snapshot of the portfolio's total value at a given time."""

        # To calculate total_value including positions, you need last known prices for instruments.
        # For simplicity, if you don't have a market_prices dict here, total_value might just be cash.
        # If you have a way to get last_known_price for each instrument, you'd calculate:
        # total_value = current_cash + sum(pos['quantity'] * pos['last_known_price'] for pos in self.positions.values())
        # For now, keeping it as just cash as per previous code, but note this for future enhancement.
        total_value = current_cash # Simplified: total value is just current cash

        self.equity_curve.append({
            "timestamp": timestamp,
            "cash": current_cash,
            # Convert positions dictionary to a JSON string here to ensure consistent schema for Parquet
            "positions": json.dumps({k: v['quantity'] for k, v in self.positions.items()}), # <--- MODIFIED HERE
            "total_value": total_value
        })
        self.logger.debug(f"Equity snapshot recorded: {total_value:.2f} at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")


    def log_current_state(self):
        """Logs the final state of the portfolio to the console."""
        self.logger.info("-" * 50)
        self.logger.info(f"[{self.strategy_name}] Final Portfolio Summary for {self.account_name}:")
        self.logger.info(f"  Initial Cash: {self.initial_cash:.2f}")
        self.logger.info(f"  Final Cash: {self.current_cash:.2f}")
        self.logger.info(f"  Current Positions: {self.positions}")

        # Realized PnL is typically final cash - initial cash (excluding unrealized for open positions)
        realized_pnl = self.current_cash - self.initial_cash
        self.logger.info(f"  Realized PnL: {realized_pnl:.2f}")
        self.logger.info("-" * 50)

    async def generate_performance_report(self, report_dir: Path):
        """
        Generates and saves performance reports (equity curve, detailed trades, summary metrics).
        """
        self.logger.info(f"[{self.strategy_name}] Generating performance report in {report_dir}...")
        report_dir.mkdir(parents=True, exist_ok=True) # Ensure report directory exists
        report_timestamp = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d_%H%M%S") # Timezone-aware timestamp

        # 1. Save Equity Curve to Parquet
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve)
            equity_file = report_dir / f"equity_curve_{report_timestamp}.parquet"
            try:
                equity_df.to_parquet(equity_file, index=False)
                self.logger.info(f"Equity curve saved to {equity_file}")
            except Exception as e:
                self.logger.error(f"Error saving equity curve to {equity_file}: {e}", exc_info=True)
        else:
            self.logger.warning("No equity curve data to save.")

        # 2. Save Detailed Trade Log (fills processed by PortfolioManager) to Parquet
        if self.portfolio_trades:
            trades_df = pd.DataFrame(self.portfolio_trades)
            trades_file = report_dir / f"portfolio_fills_{report_timestamp}.parquet" # Differentiate from TradeExecutor's log
            try:
                trades_df.to_parquet(trades_file, index=False)
                self.logger.info(f"Detailed portfolio fills saved to {trades_file}")
            except Exception as e:
                self.logger.error(f"Error saving detailed portfolio fills to {trades_file}: {e}", exc_info=True)
        else:
            self.logger.warning("No detailed portfolio fills to save.")

        # 3. Calculate and Log Summary Metrics
        if self.equity_curve:
            initial_value = self.equity_curve[0]['total_value']
            final_value = self.equity_curve[-1]['total_value']
            total_return = (final_value - initial_value) / initial_value if initial_value != 0 else 0

            self.logger.info(f"Performance Summary: Total Return = {total_return:.2%}")
            self.logger.info(f"Number of fills processed: {len(self.portfolio_trades)}")