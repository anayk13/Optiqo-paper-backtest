"""
Production-Ready Multi-Strategy Trading Engine
Supports complex strategies like MBVC with enhanced monitoring and management.
"""

import asyncio
import yaml
import logging
import argparse
import signal
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

# Add project root to path
import os
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from engine.logger import get_logger
from engine.event_engine import EventEngine, MarketEvent, SignalEvent, OrderEvent, FillEvent
from engine.broker import SimulatedBroker
from engine.trade_executor import TradeExecutor
from engine.portfolio import PortfolioManager
from engine.risk_manager import RiskManager
from engine.live_data_feed import LiveDataFeed
from engine.data_feed import CSVDataFeed
from engine.strategy_manager import StrategyManager
from engine.enhanced_strategy_adapter import EnhancedStrategyAdapter
from strategies.enhanced_base_strategy import EnhancedBaseStrategy


class ProductionTradingEngine:
    """
    Production-ready trading engine that can handle multiple complex strategies.
    Supports both backtesting and live trading with advanced monitoring.
    """
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Core components
        self.event_engine = None
        self.broker = None
        self.portfolio_manager = None
        self.trade_executor = None
        self.risk_manager = None
        self.data_feed = None
        self.strategy_manager = None
        
        # Strategy adapters
        self.strategy_adapters: Dict[str, EnhancedStrategyAdapter] = {}
        
        # System state
        self.is_running = False
        self.start_time = None
        self.logger = None
        
        # Performance monitoring
        self.performance_metrics = {
            'total_strategies': 0,
            'active_strategies': 0,
            'total_signals': 0,
            'total_fills': 0,
            'system_uptime': 0
        }

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"Failed to load config: {e}")
            sys.exit(1)

    async def initialize(self):
        """Initialize all system components"""
        try:
            # Setup logging
            self.logger = get_logger(
                main_folder_name="production_engine",
                broker_name="SYSTEM",
                account_name="PRODUCTION",
                strategy_name="ENGINE",
                level=logging.DEBUG
            )
            
            self.logger.info("Initializing Production Trading Engine...")
            
            # Initialize Event Engine
            self.event_engine = EventEngine(
                queue_maxsize=self.config.get('event_engine', {}).get('queue_size', 10000),
                logger_level=logging.DEBUG
            )
            self.logger.info("✅ EventEngine initialized")
            
            # Initialize Broker
            broker_config = self.config.get('broker', {})
            self.broker = SimulatedBroker(
                account_name=broker_config.get('account', 'production_account'),
                slippage_percent=broker_config.get('slippage_percent', 0.1),
                fill_chance=broker_config.get('fill_chance', 1.0)
            )
            await self.broker.initialize()
            self.logger.info("✅ SimulatedBroker initialized")
            
            # Initialize Portfolio Manager
            self.portfolio_manager = PortfolioManager(
                broker_name=broker_config.get('name', 'SimulatedBroker'),
                account_name=broker_config.get('account', 'production_account'),
                strategy_name='MULTI_STRATEGY',
                broker=self.broker,
                initial_cash=self.config.get('initial_cash', 1000000)
            )
            await self.portfolio_manager.initialize()
            self.logger.info("✅ PortfolioManager initialized")
            
            # Initialize Risk Manager
            self.risk_manager = RiskManager(broker=self.broker)
            self.logger.info("✅ RiskManager initialized")
            
            # Initialize Trade Executor
            self.trade_executor = TradeExecutor(
                broker_name=broker_config.get('name', 'SimulatedBroker'),
                account_name=broker_config.get('account', 'production_account'),
                strategy_name='MULTI_STRATEGY',
                broker=self.broker,
                event_engine=self.event_engine
            )
            self.logger.info("✅ TradeExecutor initialized")
            
            # Initialize Strategy Manager
            self.strategy_manager = StrategyManager(
                event_engine=self.event_engine,
                max_concurrent_strategies=self.config.get('strategy_manager', {}).get('max_strategies', 10)
            )
            await self.strategy_manager.start()
            self.logger.info("✅ StrategyManager initialized")
            
            # Initialize Data Feed
            await self._initialize_data_feed()
            
            # Register event handlers
            self._register_event_handlers()
            
            self.logger.info("🚀 Production Trading Engine initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize engine: {e}", exc_info=True)
            raise

    async def _initialize_data_feed(self):
        """Initialize data feed based on configuration"""
        data_config = self.config.get('data', {})
        mode = data_config.get('mode', 'backtest')
        
        if mode == 'backtest':
            csv_file = Path(data_config.get('csv_file', 'data/mock_ticks.csv'))
            if not csv_file.exists():
                raise FileNotFoundError(f"CSV file not found: {csv_file}")
            
            self.data_feed = CSVDataFeed(
                csv_file=csv_file,
                delay=data_config.get('delay', 0.01),
                event_engine=self.event_engine,
                logger=get_logger(
                    main_folder_name="datafeed",
                    broker_name="BACKTEST",
                    account_name="PRODUCTION",
                    strategy_name="ENGINE",
                    level=logging.DEBUG
                )
            )
            self.logger.info(f"✅ CSVDataFeed initialized: {csv_file}")
            
        elif mode == 'live_ip':
            live_config = data_config.get('live_config', {})
            self.data_feed = LiveDataFeed(
                config=live_config,
                event_engine=self.event_engine
            )
            self.logger.info(f"✅ LiveDataFeed initialized: {live_config.get('uri')}")
            
        else:
            raise ValueError(f"Unknown data mode: {mode}")

    def _register_event_handlers(self):
        """Register event handlers with the event engine"""
        # Market events go to strategy manager for routing
        self.event_engine.register_handler(MarketEvent, self._handle_market_event)
        
        # Signal events go to strategy adapters
        self.event_engine.register_handler(SignalEvent, self._handle_signal_event)
        
        # Order events go to trade executor
        self.event_engine.register_handler(OrderEvent, self.trade_executor.on_order_event)
        
        # Fill events go to portfolio manager and strategy adapters
        self.event_engine.register_handler(FillEvent, self.portfolio_manager.on_fill_event)
        self.event_engine.register_handler(FillEvent, self._handle_fill_event)
        
        self.logger.info("✅ Event handlers registered")

    async def _handle_market_event(self, event: MarketEvent):
        """Route market events to strategy manager"""
        try:
            await self.strategy_manager.route_market_event(event)
            self.performance_metrics['total_signals'] += 1
        except Exception as e:
            self.logger.error(f"Error routing market event: {e}", exc_info=True)

    async def _handle_signal_event(self, event: SignalEvent):
        """Route signal events to appropriate strategy adapter"""
        try:
            strategy_id = event.strategy_id
            if strategy_id in self.strategy_adapters:
                await self.strategy_adapters[strategy_id].on_signal_event(event)
            else:
                self.logger.warning(f"No adapter found for strategy: {strategy_id}")
        except Exception as e:
            self.logger.error(f"Error handling signal event: {e}", exc_info=True)

    async def _handle_fill_event(self, event: FillEvent):
        """Route fill events to strategy adapters"""
        try:
            # Find strategy adapter by strategy_id (extracted from order tag)
            for adapter in self.strategy_adapters.values():
                await adapter.on_fill_event(event)
            
            self.performance_metrics['total_fills'] += 1
        except Exception as e:
            self.logger.error(f"Error handling fill event: {e}", exc_info=True)

    async def add_strategy(self, strategy_class: type, strategy_name: str, 
                          config: Dict[str, Any], strategy_type: str = 'enhanced') -> str:
        """Add a new strategy to the engine"""
        try:
            # Add strategy to manager
            strategy_id = await self.strategy_manager.add_strategy(
                strategy_class=strategy_class,
                strategy_name=strategy_name,
                config=config
            )
            
            # Get strategy instance
            strategy_instance = self.strategy_manager.strategies[strategy_id].instance
            
            # Create enhanced adapter
            adapter = EnhancedStrategyAdapter(
                event_engine=self.event_engine,
                strategy=strategy_instance,
                portfolio_manager=self.portfolio_manager,
                trade_executor=self.trade_executor,
                risk_manager=self.risk_manager,
                logger=get_logger(
                    main_folder_name="strategy_adapter",
                    broker_name="MULTI_STRATEGY",
                    account_name=strategy_name,
                    strategy_name=strategy_class.__name__,
                    level=logging.DEBUG
                ),
                strategy_id=strategy_id
            )
            
            self.strategy_adapters[strategy_id] = adapter
            self.performance_metrics['total_strategies'] += 1
            self.performance_metrics['active_strategies'] += 1
            
            self.logger.info(f"✅ Strategy '{strategy_name}' added with ID: {strategy_id}")
            return strategy_id
            
        except Exception as e:
            self.logger.error(f"Failed to add strategy '{strategy_name}': {e}", exc_info=True)
            raise

    async def remove_strategy(self, strategy_id: str):
        """Remove a strategy from the engine"""
        try:
            # Remove from strategy manager
            await self.strategy_manager.remove_strategy(strategy_id)
            
            # Remove adapter
            if strategy_id in self.strategy_adapters:
                del self.strategy_adapters[strategy_id]
            
            self.performance_metrics['active_strategies'] -= 1
            
            self.logger.info(f"✅ Strategy {strategy_id} removed")
            
        except Exception as e:
            self.logger.error(f"Failed to remove strategy {strategy_id}: {e}", exc_info=True)

    async def get_strategy_status(self, strategy_id: str = None) -> Dict[str, Any]:
        """Get status of specific strategy or all strategies"""
        if strategy_id:
            return await self.strategy_manager.get_strategy_status(strategy_id)
        else:
            return await self.strategy_manager.get_all_strategies_status()

    async def run(self):
        """Run the production trading engine"""
        try:
            self.is_running = True
            self.start_time = datetime.now()
            
            self.logger.info("🚀 Starting Production Trading Engine...")
            
            # Start event engine
            event_engine_task = asyncio.create_task(self.event_engine.run())
            
            # Start data feed
            data_feed_task = None
            if self.data_feed:
                data_feed_task = asyncio.create_task(self.data_feed.generate_ticks())
            
            # Start monitoring task
            monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            self.logger.info("✅ All systems running. Press Ctrl+C to stop.")
            
            # Keep running until interrupted
            try:
                while self.is_running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("🛑 Shutdown signal received")
            
        except Exception as e:
            self.logger.error(f"Error in main run loop: {e}", exc_info=True)
        finally:
            await self.shutdown(event_engine_task, data_feed_task, monitoring_task)

    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.is_running:
            try:
                await asyncio.sleep(30)  # Monitor every 30 seconds
                
                # Update performance metrics
                self.performance_metrics['system_uptime'] = (
                    datetime.now() - self.start_time
                ).total_seconds()
                
                # Log system status
                self.logger.info(f"System Status: {self.performance_metrics}")
                
                # Check strategy health
                for strategy_id, adapter in self.strategy_adapters.items():
                    strategy_info = adapter.get_strategy_info()
                    self.logger.debug(f"Strategy {strategy_id}: {strategy_info}")
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)

    async def shutdown(self, event_engine_task, data_feed_task, monitoring_task):
        """Gracefully shutdown the engine"""
        try:
            self.logger.info("🛑 Initiating graceful shutdown...")
            
            # Stop data feed
            if data_feed_task:
                data_feed_task.cancel()
                try:
                    await data_feed_task
                except asyncio.CancelledError:
                    pass
            
            # Stop event engine
            if event_engine_task:
                event_engine_task.cancel()
                try:
                    await event_engine_task
                except asyncio.CancelledError:
                    pass
            
            # Stop monitoring
            if monitoring_task:
                monitoring_task.cancel()
                try:
                    await monitoring_task
                except asyncio.CancelledError:
                    pass
            
            # Stop strategy manager
            if self.strategy_manager:
                await self.strategy_manager.stop()
            
            # Generate final reports
            await self._generate_final_reports()
            
            self.logger.info("✅ Shutdown completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)

    async def _generate_final_reports(self):
        """Generate final performance reports"""
        try:
            reports_dir = Path("logs/production_reports")
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Generate portfolio report
            await self.portfolio_manager.generate_performance_report(reports_dir)
            
            # Generate trade history
            await self.trade_executor.save_trade_history(str(reports_dir / "trades_log.parquet"))
            
            # Generate strategy performance report
            strategy_performance = {}
            for strategy_id, adapter in self.strategy_adapters.items():
                strategy_performance[strategy_id] = adapter.get_strategy_info()
            
            with open(reports_dir / f"strategy_performance_{timestamp}.json", 'w') as f:
                json.dump(strategy_performance, f, indent=2, default=str)
            
            # Generate system performance report
            system_report = {
                'performance_metrics': self.performance_metrics,
                'shutdown_time': datetime.now().isoformat(),
                'total_runtime': (datetime.now() - self.start_time).total_seconds()
            }
            
            with open(reports_dir / f"system_performance_{timestamp}.json", 'w') as f:
                json.dump(system_report, f, indent=2, default=str)
            
            self.logger.info(f"📊 Final reports generated in {reports_dir}")
            
        except Exception as e:
            self.logger.error(f"Error generating final reports: {e}", exc_info=True)


async def main():
    """Main entry point for production trading engine"""
    parser = argparse.ArgumentParser(description="Production Multi-Strategy Trading Engine")
    parser.add_argument("--config", type=str, default="config/production_config.yaml",
                       help="Path to configuration file")
    parser.add_argument("--strategy", type=str, nargs='+',
                       help="Strategy classes to load (e.g., MyStrategy1 MyStrategy2)")
    
    args = parser.parse_args()
    
    # Create engine
    engine = ProductionTradingEngine(args.config)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, initiating shutdown...")
        engine.is_running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize engine
        await engine.initialize()
        
        # Add strategies if specified
        if args.strategy:
            for strategy_name in args.strategy:
                # This would need to be implemented based on your strategy loading mechanism
                print(f"Loading strategy: {strategy_name}")
                # await engine.add_strategy(strategy_class, strategy_name, config)
        
        # Run engine
        await engine.run()
        
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
