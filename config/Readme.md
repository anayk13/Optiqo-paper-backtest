---
title: Event-Driven Trading System
author: Anay Kumar
---

# Event-Driven Trading System

This is a modular, event-driven trading system designed for both backtesting and paper trading (simulated live trading). It provides a flexible framework for developing and deploying algorithmic trading strategies, managing portfolios, and simulating trade execution.

## Features

-   **Event-Driven Architecture:** Centralized `EventEngine` for efficient and decoupled component interaction.
-   **Backtesting:** Test strategies using historical CSV data.
-   **Paper Trading:** Simulate live trading with real-time data feeds (e.g., WebSocket) without risking actual capital.
-   **Configurable Broker Simulation:** Adjust slippage and fill chance for realistic trade execution simulation.
-   **Modular Design:** Easily extend or replace components like data feeds, brokers, and risk managers.
-   **Custom Strategy Deployment:** Define and integrate your own trading logic.
-   **Comprehensive Logging:** Structured logging for all components, aiding in debugging and analysis.
-   **Performance Reporting:** Automatic generation of trade logs and performance metrics upon shutdown.

## System Architecture

The system operates on an event-driven paradigm, where various components communicate by publishing and subscribing to events.

*   **`EventEngine`**: The core dispatcher, routing events (Market, Signal, Order, Fill) to registered handlers.
*   **`Data Feeds`**:
    *   `CSVDataFeed`: Reads historical market data from CSV files for backtesting.
    *   `LiveDataFeed`: Connects to external real-time data sources (e.g., WebSocket) for live simulation.
*   **`Strategy`**: Contains your trading logic. It consumes market data, generates trading signals, and issues orders.
*   **`StrategyAdapter`**: Acts as an intermediary, translating strategy signals into executable orders and relaying fill events back to the strategy.
*   **`TradeExecutor`**: Receives `OrderEvent`s and interacts with the `SimulatedBroker` to "execute" trades.
*   **`SimulatedBroker`**: The paper trading engine. It simulates order matching, fills, and manages the simulated account balance, incorporating configurable slippage and fill chance.
*   **`PortfolioManager`**: Tracks the current state of the portfolio (cash, positions) and calculates performance metrics.
*   **`RiskManager`**: (Placeholder/Extensible) Intended for enforcing risk limits and managing overall exposure.
*   **`Logger`**: A custom logging utility (`engine.logger`) for structured, component-specific logging.

## Getting Started

### Prerequisites

-   Python 3.8+
-   `pip` (Python package installer)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd trading-system
    ```
2.  **Install dependencies:**
    It's recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows: `venv\Scripts\activate`
    pip install -r requirements.txt # Assuming a requirements.txt exists or create one
    ```
    *If `requirements.txt` does not exist, you'll need to install `pyyaml`, `pandas`, `pyarrow`, `websockets` (for live data), etc. based on the imports in `main.py` and other modules.*

## Configuration (`config/strategy_config.yaml`)

The `config/strategy_config.yaml` file is crucial for setting up the system's behavior.

```yaml
# Define the operational mode: 'backtest' or 'live_ip'
mode: live_ip # <--- System-wide operational mode

strategy:
  module: strategies.simple_test_strategy # Python module path (e.g., strategies/simple_test_strategy.py)
  class: SimpleTestStrategy # Class name within the module
  params: # Parameters passed to the strategy's __init__ method
    trigger_price: 1500.0
    instrument_to_trade: "NSE_EQ_INFY"
    trade_quantity: 100

broker:
  slippage_percent: 0.1 # Simulated slippage for fills (e.g., 0.1% deviation)
  fill_chance: 1.0 # Probability of an order being filled (1.0 means always filled)
  name: SimulatedBroker # Name of the broker (for logging/identification)
  account: paper123 # Account name for the broker (can be overridden by CLI)

data:
  mode: live_ip # <--- Data feed specific mode (should match system-wide mode)
  csv_file: data/mock_ticks.csv # Path to CSV for backtest mode
  delay: 0.01 # Delay between tick processing in backtest mode (in seconds)

  live_config: # Configuration for live_ip mode (WebSocket endpoint)
    uri: "ws://127.0.0.1:8888" # WebSocket URI for live data source
    instruments: ["NSE_FO_5210_1", "NSE_EQ_INFY", "BSE_EQ_TCS"] # Instruments to subscribe to

logging:
  enabled: true # Enable/disable logging
  path: logs/orders.parquet # Path for trade logs (Parquet format)

initial_cash: 1000000 # Starting cash for the portfolio
snapshot:
  portfolio: data/portfolio_snapshot.parquet # Path to save/load portfolio snapshots
```

**Key Fields:**

-   **`mode`**: Sets the overall system operation (`backtest` or `live_ip`).
-   **`strategy.module`**: The Python module containing your strategy class (e.g., `strategies.my_strategy` points to `strategies/my_strategy.py`).
-   **`strategy.class`**: The name of the strategy class within the specified module.
-   **`strategy.params`**: A dictionary of custom parameters passed directly to your strategy's `__init__` method.
-   **`broker.slippage_percent`**: Simulates a percentage deviation from the requested price during order fills.
-   **`broker.fill_chance`**: The probability (0.0 to 1.0) that an order will be filled.
-   **`data.csv_file`**: Used only in `backtest` mode.
-   **`data.live_config`**: Used only in `live_ip` mode, specifies the WebSocket URI and instruments to subscribe to.
-   **`initial_cash`**: The starting capital for the simulated trading account.

## Running the System

Execute the `main.py` script from your terminal. You can specify the account name and the strategy class name using command-line arguments:

```bash
python main.py --account <YOUR_ACCOUNT_NAME> --strategy <YOUR_STRATEGY_CLASS_NAME>
```

**Example:**

```bash
python main.py --account MyPaperAccount --strategy SimpleTestStrategy
```

The system will load the configuration, initialize components, and start processing events. Press `Ctrl+C` to gracefully shut down the application. Upon shutdown, performance reports and trade logs will be generated in the `logs/` directory.

## Paper Trading Engine (`SimulatedBroker`)

The `SimulatedBroker` is the heart of the paper trading functionality. It simulates real-world trading conditions:

-   **Slippage (`slippage_percent`)**: When an order is "filled," the actual price will deviate from your requested price by a random amount within the specified percentage. This adds realism, as perfect fills are rare in live trading.
-   **Fill Chance (`fill_chance`)**: This parameter determines the probability of an order being filled. A value less than 1.0 means some orders might not be filled, simulating illiquid markets or missed opportunities.
-   **Account Management**: It tracks your `initial_cash`, updates balances based on simulated fills, and manages your simulated positions.

## Strategy Development & Deployment

### Strategy Structure Format

To deploy a new strategy, create a Python file in the `strategies/` directory (e.g., `strategies/my_custom_strategy.py`). The class name should be in PascalCase (e.g., `MyCustomStrategy`), and the system will automatically derive the module name (e.g., `my_custom_strategy`).

Your strategy class must adhere to the following structure:

```python
# strategies/my_custom_strategy.py

import logging
from engine.event_engine import EventEngine, MarketEvent, SignalEvent, OrderEvent, FillEvent
# Assuming get_logger is imported or accessible

class MyCustomStrategy:
    """
    A template for a custom trading strategy.
    """

    def __init__(
        self,
        event_engine: EventEngine,
        logger: logging.Logger,
        executor_account_name: str,
        **strategy_config_params # Parameters from strategy.params in config.yaml
    ):
        self.event_engine = event_engine
        self.logger = logger
        self.executor_account_name = executor_account_name

        # Access strategy-specific parameters from config.yaml
        self.trigger_price = strategy_config_params.get("trigger_price")
        self.instrument = strategy_config_params.get("instrument_to_trade")
        self.quantity = strategy_config_params.get("trade_quantity")

        self.logger.info(f"MyCustomStrategy initialized for instrument: {self.instrument}")
        self.position = 0 # Example: internal state for current position

    async def on_market_event(self, event: MarketEvent):
        """
        Handles incoming market data (ticks). This is where your core logic resides.
        """
        if event.instrument == self.instrument:
            self.current_price = event.price
            self.logger.debug(f"Received market event for {event.instrument}: {event.price}")

            # Example: Buy if price is below trigger and no position
            if self.current_price < self.trigger_price and self.position == 0:
                self.logger.info(f"Price {self.current_price} below trigger {self.trigger_price}. Sending BUY order.")
                order_event = OrderEvent(
                    instrument=self.instrument,
                    order_type="MARKET",
                    quantity=self.quantity,
                    direction="BUY",
                    price=self.current_price # Indicative price for MARKET order
                )
                await self.event_engine.put(order_event)

            # Example: Sell if price is significantly above trigger and holding a position
            elif self.current_price > self.trigger_price * 1.05 and self.position > 0:
                self.logger.info(f"Price {self.current_price} above sell trigger. Sending SELL order.")
                order_event = OrderEvent(
                    instrument=self.instrument,
                    order_type="MARKET",
                    quantity=self.quantity,
                    direction="SELL",
                    price=self.current_price
                )
                await self.event_engine.put(order_event)

    async def on_signal_event(self, event: SignalEvent):
        """
        Handles incoming signal events (if your strategy generates/uses them).
        """
        self.logger.info(f"Received signal event: {event.signal_type} for {event.instrument}")
        # Logic to convert signals to orders or other actions

    async def on_fill_event(self, event: FillEvent):
        """
        Handles incoming fill events (executed orders). Update internal position here.
        """
        self.logger.info(f"Received fill event: {event.instrument} {event.direction} {event.quantity} @ {event.price}")
        if event.instrument == self.instrument:
            if event.direction == "BUY":
                self.position += event.quantity
            elif event.direction == "SELL":
                self.position -= event.quantity
            self.logger.info(f"Updated position for {self.instrument}: {self.position}")
```

### Steps to Deploy:

1.  Create your strategy file in `strategies/`.
2.  Implement the `__init__` and event handler methods (`on_market_event`, `on_fill_event`, etc.).
3.  Update `config/strategy_config.yaml` to point to your new strategy's `module` and `class` name, and add any `params` it requires.
4.  Run `main.py` with your strategy's class name.

## Logging and Reporting

All system components log their activities to the `logs/` directory, organized by `account_name`, `strategy_class_name`, and component type. This structured logging is invaluable for debugging and understanding the system's behavior.

Upon graceful shutdown (`Ctrl+C`), the system generates:

-   **Performance Report**: A CSV file (`performance_report.csv`) summarizing key metrics like P&L, drawdown, etc.
-   **Trade Log**: A Parquet file (`trades_log.parquet`) detailing every executed trade.

These reports are saved in `logs/<account_name>/<strategy_class_name>/reports/`.





