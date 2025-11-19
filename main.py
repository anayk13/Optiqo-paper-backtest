import asyncio
import yaml
from pathlib import Path
import os
import datetime
import logging
import importlib
import re
import argparse # Import argparse

import sys
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
logging.basicConfig(level=logging.DEBUG) 

def pascal_to_snake_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

from engine.logger import get_logger
from engine.event_engine import EventEngine, MarketEvent, SignalEvent, OrderEvent, FillEvent
from engine.broker import SimulatedBroker
from engine.trade_executor import TradeExecutor
from engine.portfolio import PortfolioManager
from engine.risk_manager import RiskManager
from engine.live_data_feed import LiveDataFeed
from engine.data_feed import CSVDataFeed 
from engine.strategy_adapter import StrategyAdapter

def load_config(config_path: Path) -> dict:
    """Loads the YAML configuration file."""
    if not config_path.exists():
        logger.critical(f"Configuration file not found at {config_path}")
        raise FileNotFoundError(f"Configuration file not found at {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config

async def initialize_components(config: dict, event_engine: EventEngine, logger: logging.Logger, account_name: str, strategy_class_name: str):
    """Initializes all core trading system components."""
    broker_config = config["broker"]
    initial_cash = config.get("initial_cash", 1000000)
    
    broker_name = broker_config.get("name", "SimulatedBroker")
    # account_name and strategy_class_name are now passed as arguments

    # --- COMPONENTS ---
    # Initialize Broker
    simulated_broker = SimulatedBroker(
        account_name=account_name,
        slippage_percent=broker_config.get("slippage_percent", 0.0),
        fill_chance=broker_config.get("fill_chance", 1.0)
    )
    await simulated_broker.initialize()
    logger.info(f"✅ {broker_name} initialized.")

    # Initialize Portfolio Manager
    portfolio_manager = PortfolioManager(
        broker_name=broker_name,
        account_name=account_name,
        strategy_name=strategy_class_name,
        broker=simulated_broker,
        initial_cash=initial_cash
    )
    await portfolio_manager.initialize()
    logger.info("✅ PortfolioManager initialized.")

    # Initialize Risk Manager
    risk_manager = RiskManager(broker=simulated_broker)
    logger.info("✅ RiskManager initialized.")

    # Initialize Trade Executor
    trade_executor = TradeExecutor(
        broker_name=broker_name,
        account_name=account_name,
        strategy_name=strategy_class_name,
        broker=simulated_broker,
        event_engine=event_engine
    )
    logger.info("✅ TradeExecutor initialized.")

    # --- STRATEGY ---
    strategy_config_params = config["strategy"].get("params", {})
    strategy_module_name = f"strategies.{pascal_to_snake_case(strategy_class_name)}" 
    
    try:
        strategy_module = importlib.import_module(strategy_module_name)
        StrategyClass = getattr(strategy_module, strategy_class_name)
    except (ImportError, AttributeError) as e:
        logger.critical(f"Failed to load strategy '{strategy_class_name}' from '{strategy_module_name}': {e}", exc_info=True)
        raise

    strategy_logger = get_logger(
        main_folder_name="strategies", 
        broker_name=broker_name, 
        account_name=account_name, 
        strategy_name=strategy_class_name, 
        level=logging.DEBUG # <--- CRITICAL: Set strategy logger to DEBUG
    )

    strategy_instance = StrategyClass(
        event_engine=event_engine,
        logger=strategy_logger,
        executor_account_name=account_name,
        **strategy_config_params
    )
    logger.info(f"✅ Strategy '{strategy_class_name}' initialized.")

    # --- ADAPTER ---
    strategy_adapter_logger = get_logger(
        main_folder_name="strategy_adapter", 
        broker_name=broker_name, 
        account_name=account_name,
        strategy_name=strategy_class_name, # Pass strategy_name to adapter logger
        level=logging.DEBUG # <--- CRITICAL: Set adapter logger to DEBUG
    )
    strategy_adapter = StrategyAdapter(
        event_engine=event_engine,
        strategy=strategy_instance,
        portfolio_manager=portfolio_manager,
        trade_executor=trade_executor,
        risk_manager=risk_manager,
        logger=strategy_adapter_logger
    )
    logger.info("✅ StrategyAdapter initialized.")

    # --- DATAFEED ---
    datafeed = None
    mode = config["mode"]
    data_config = config["data"]
    if mode == "backtest":
        csv_file_path = Path(data_config.get("csv_file", "data/mock_ticks.csv"))
        if not csv_file_path.exists():
            logger.critical(f"Backtest CSV file not found at {csv_file_path}")
            return
        datafeed = CSVDataFeed(
            csv_file=csv_file_path,
            delay=data_config.get("delay", 0.01),
            event_engine=event_engine,
            logger=get_logger(main_folder_name="datafeed", broker_name="BACKTEST", account_name=account_name, strategy_name=strategy_class_name, level=logging.DEBUG) # Set CSV datafeed logger to DEBUG
        )
        logger.info(f"✅ Using CSVDataFeed for backtesting from {csv_file_path}")
    elif mode == "live_ip":
        live_ip_config = data_config.get("live_config", {})
        datafeed = LiveDataFeed(
            config=live_ip_config,
            event_engine=event_engine
        )
        logger.info(f"✅ Using LiveDataFeed for live IP streaming from {live_ip_config.get('uri')}")
    else:
        logger.critical(f"Unknown mode: {mode}. Must be 'backtest' or 'live_ip'.")
        raise ValueError(f"Unknown mode: {mode}")

    return portfolio_manager, trade_executor, risk_manager, strategy_adapter, datafeed

def register_handlers(
    event_engine: EventEngine, 
    strategy_adapter: StrategyAdapter, 
    trade_executor: TradeExecutor, 
    portfolio_manager: PortfolioManager
):
    """Registers event handlers with the event engine."""
    event_engine.register_handler(MarketEvent, strategy_adapter.on_market_event)
    event_engine.register_handler(SignalEvent, strategy_adapter.on_signal_event)
    event_engine.register_handler(OrderEvent, trade_executor.on_order_event)
    event_engine.register_handler(FillEvent, strategy_adapter.on_fill_event) # New: StrategyAdapter handles fills
    event_engine.register_handler(FillEvent, portfolio_manager.on_fill_event)


async def main(account_name: str, strategy_class_name: str): # Add arguments to main
    # Set main logger to DEBUG to see all initialization and flow logs
    logger = get_logger("main", broker_name="SYSTEM", account_name=account_name, strategy_name=strategy_class_name, level=logging.DEBUG)
    logger.info("Main application started.")

    try:
        config = load_config(Path("config/strategy_config.yaml"))
        logger.info("Configuration loaded successfully.")
    except (FileNotFoundError, yaml.YAMLError) as e:
        logger.critical(f"Failed to load or parse config: {e}", exc_info=True)
        return

    # Override config values with command-line arguments
    config["broker"]["account"] = account_name
    config["strategy"]["class"] = strategy_class_name
    # config["mode"] and config["data"]["mode"] are now read directly from config file

    # Initialize Event Engine
    event_engine = EventEngine(queue_maxsize=1000, logger_level=logging.DEBUG) # Set EventEngine logger to DEBUG
    logger.info("✅ EventEngine initialized.")

    # Initialize all other components
    portfolio_manager, trade_executor, risk_manager, strategy_adapter, datafeed = await initialize_components(config, event_engine, logger, account_name, strategy_class_name)
    register_handlers(event_engine, strategy_adapter, trade_executor, portfolio_manager)
    logger.info("✅ Event handlers registered.")

    # Start EventEngine and DataFeed as concurrent tasks
    event_engine_task = asyncio.create_task(event_engine.run()) # <--- CRITICAL: Start EventEngine's loop as a task
    logger.info("Starting data feed...")
    data_feed_task = None
    if datafeed:
        data_feed_task = asyncio.create_task(datafeed.generate_ticks())
    else:
        logger.critical("No data feed initialized. Exiting.")
        event_engine_task.cancel() # Clean up event engine task if no data feed
        return

    logger.info("Application is running. Press Ctrl+C to stop.")
    try:
        # Keep the main loop alive, allowing tasks to run
        while True:
            await asyncio.sleep(1) 
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Stopping application.")
    finally:
        logger.info("Initiating graceful shutdown and report generation...")
        
        # Cancel tasks gracefully
        if data_feed_task:
            data_feed_task.cancel()
        if event_engine_task:
            event_engine_task.cancel()
        
        # Await their completion to ensure cleanup
        try:
            if data_feed_task:
                await data_feed_task
            if event_engine_task:
                await event_engine_task
        except asyncio.CancelledError:
            logger.info("Background tasks successfully cancelled.")
        except Exception as e:
            logger.error(f"Error awaiting background tasks: {e}", exc_info=True)
        
        reports_output_dir = Path(f"logs/{account_name}/{strategy_class_name}/reports") # Dynamic reports path
        reports_output_dir.mkdir(parents=True, exist_ok=True)

        await portfolio_manager.generate_performance_report(reports_output_dir)
        await trade_executor.save_trade_history(str(reports_output_dir / "trades_log.parquet"))
        portfolio_manager.log_current_state()

        # Call stop methods on components (they primarily set internal flags)
        await event_engine.stop() 
        if datafeed:
            await datafeed.stop()
        
        logger.info("Application stopped cleanly.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the trading system.")
    parser.add_argument("--account", type=str, default="PaperAccount", help="Account name for the trading system.")
    parser.add_argument("--strategy", type=str, default="SimpleTestStrategy", help="Strategy class name to use.")

    args = parser.parse_args()

    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    asyncio.run(main(account_name=args.account, strategy_class_name=args.strategy))
