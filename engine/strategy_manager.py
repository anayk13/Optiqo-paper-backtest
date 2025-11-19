"""
Multi-Strategy Manager for Production-Ready Trading Engine
Handles concurrent execution of multiple strategies with isolation and resource management.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import uuid
import traceback
from concurrent.futures import ThreadPoolExecutor
import psutil
import threading

from .event_engine import EventEngine, MarketEvent, SignalEvent, OrderEvent, FillEvent
from .logger import get_logger
from strategies.base_strategy import BaseStrategy


class StrategyStatus(Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class StrategyInstance:
    """Container for strategy instance with metadata"""
    id: str
    name: str
    strategy_class: type
    instance: BaseStrategy
    status: StrategyStatus
    created_at: datetime
    last_heartbeat: datetime
    error_count: int = 0
    max_errors: int = 5
    resource_usage: Dict[str, float] = None
    config: Dict[str, Any] = None


class StrategyManager:
    """
    Manages multiple strategy instances with isolation, resource management, and monitoring.
    Supports complex strategies like MBVC (Multi-Broker, Multi-Venue, Multi-Strategy).
    """
    
    def __init__(self, event_engine: EventEngine, max_concurrent_strategies: int = 10):
        self.event_engine = event_engine
        self.max_concurrent_strategies = max_concurrent_strategies
        self.strategies: Dict[str, StrategyInstance] = {}
        self.strategy_adapters: Dict[str, 'StrategyAdapter'] = {}
        
        # Resource management
        self.cpu_limit_per_strategy = 20.0  # CPU percentage
        self.memory_limit_per_strategy = 512 * 1024 * 1024  # 512MB
        self.thread_pool = ThreadPoolExecutor(max_workers=max_concurrent_strategies * 2)
        
        # Monitoring
        self.logger = get_logger("strategy_manager", level=logging.INFO)
        self.heartbeat_interval = 30  # seconds
        self.health_check_task = None
        self.is_running = False
        
        # Strategy isolation
        self.strategy_queues: Dict[str, asyncio.Queue] = {}
        self.strategy_events: Dict[str, Dict[str, Any]] = {}
        
        self.logger.info("StrategyManager initialized for production multi-strategy execution")

    async def start(self):
        """Start the strategy manager and health monitoring"""
        self.is_running = True
        self.health_check_task = asyncio.create_task(self._health_monitor())
        self.logger.info("StrategyManager started with health monitoring")

    async def stop(self):
        """Stop all strategies and cleanup resources"""
        self.is_running = False
        
        # Stop all strategies gracefully
        for strategy_id, strategy_instance in self.strategies.items():
            await self._stop_strategy(strategy_id)
        
        # Cancel health monitoring
        if self.health_check_task:
            self.health_check_task.cancel()
        
        # Cleanup thread pool
        self.thread_pool.shutdown(wait=True)
        
        self.logger.info("StrategyManager stopped and resources cleaned up")

    async def add_strategy(self, 
                          strategy_class: type, 
                          strategy_name: str,
                          config: Dict[str, Any],
                          priority: int = 1) -> str:
        """
        Add a new strategy instance with isolation and resource management.
        
        Args:
            strategy_class: The strategy class to instantiate
            strategy_name: Unique name for the strategy
            config: Strategy configuration parameters
            priority: Execution priority (1=highest, 10=lowest)
        """
        if len(self.strategies) >= self.max_concurrent_strategies:
            raise RuntimeError(f"Maximum concurrent strategies ({self.max_concurrent_strategies}) reached")
        
        strategy_id = f"{strategy_name}_{uuid.uuid4().hex[:8]}"
        
        try:
            # Create isolated event queue for strategy
            strategy_queue = asyncio.Queue(maxsize=1000)
            self.strategy_queues[strategy_id] = strategy_queue
            
            # Create strategy logger with isolation
            strategy_logger = get_logger(
                main_folder_name="strategies",
                broker_name="MULTI_STRATEGY",
                account_name=strategy_name,
                strategy_name=strategy_class.__name__,
                level=logging.DEBUG
            )
            
            # Instantiate strategy with enhanced context
            strategy_instance = strategy_class(
                event_engine=self.event_engine,
                logger=strategy_logger,
                executor_account_name=strategy_name,
                strategy_id=strategy_id,
                strategy_manager=self,
                **config
            )
            
            # Create strategy instance metadata
            strategy_meta = StrategyInstance(
                id=strategy_id,
                name=strategy_name,
                strategy_class=strategy_class,
                instance=strategy_instance,
                status=StrategyStatus.INITIALIZING,
                created_at=datetime.now(),
                last_heartbeat=datetime.now(),
                config=config
            )
            
            self.strategies[strategy_id] = strategy_meta
            self.strategy_events[strategy_id] = {}
            
            # Initialize strategy
            await self._initialize_strategy(strategy_id)
            
            self.logger.info(f"Strategy '{strategy_name}' added with ID: {strategy_id}")
            return strategy_id
            
        except Exception as e:
            self.logger.error(f"Failed to add strategy '{strategy_name}': {e}", exc_info=True)
            # Cleanup on failure
            if strategy_id in self.strategy_queues:
                del self.strategy_queues[strategy_id]
            raise

    async def remove_strategy(self, strategy_id: str):
        """Remove and stop a strategy instance"""
        if strategy_id not in self.strategies:
            self.logger.warning(f"Strategy {strategy_id} not found for removal")
            return
        
        await self._stop_strategy(strategy_id)
        
        # Cleanup
        del self.strategies[strategy_id]
        if strategy_id in self.strategy_queues:
            del self.strategy_queues[strategy_id]
        if strategy_id in self.strategy_events:
            del self.strategy_events[strategy_id]
        
        self.logger.info(f"Strategy {strategy_id} removed successfully")

    async def pause_strategy(self, strategy_id: str):
        """Pause a running strategy"""
        if strategy_id in self.strategies:
            self.strategies[strategy_id].status = StrategyStatus.PAUSED
            self.logger.info(f"Strategy {strategy_id} paused")

    async def resume_strategy(self, strategy_id: str):
        """Resume a paused strategy"""
        if strategy_id in self.strategies:
            self.strategies[strategy_id].status = StrategyStatus.RUNNING
            self.logger.info(f"Strategy {strategy_id} resumed")

    async def get_strategy_status(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed status of a strategy"""
        if strategy_id not in self.strategies:
            return None
        
        strategy = self.strategies[strategy_id]
        return {
            "id": strategy.id,
            "name": strategy.name,
            "status": strategy.status.value,
            "created_at": strategy.created_at.isoformat(),
            "last_heartbeat": strategy.last_heartbeat.isoformat(),
            "error_count": strategy.error_count,
            "resource_usage": strategy.resource_usage or {},
            "config": strategy.config
        }

    async def get_all_strategies_status(self) -> List[Dict[str, Any]]:
        """Get status of all strategies"""
        return [await self.get_strategy_status(sid) for sid in self.strategies.keys()]

    async def _initialize_strategy(self, strategy_id: str):
        """Initialize a strategy with proper error handling"""
        strategy = self.strategies[strategy_id]
        
        try:
            # Call strategy initialization if it exists
            if hasattr(strategy.instance, 'initialize'):
                await strategy.instance.initialize()
            
            strategy.status = StrategyStatus.RUNNING
            self.logger.info(f"Strategy {strategy_id} initialized successfully")
            
        except Exception as e:
            strategy.status = StrategyStatus.ERROR
            strategy.error_count += 1
            self.logger.error(f"Failed to initialize strategy {strategy_id}: {e}", exc_info=True)
            raise

    async def _stop_strategy(self, strategy_id: str):
        """Stop a strategy gracefully"""
        strategy = self.strategies[strategy_id]
        
        try:
            # Call strategy cleanup if it exists
            if hasattr(strategy.instance, 'cleanup'):
                await strategy.instance.cleanup()
            
            strategy.status = StrategyStatus.STOPPED
            self.logger.info(f"Strategy {strategy_id} stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping strategy {strategy_id}: {e}", exc_info=True)

    async def _health_monitor(self):
        """Monitor strategy health and resource usage"""
        while self.is_running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                for strategy_id, strategy in self.strategies.items():
                    if strategy.status == StrategyStatus.RUNNING:
                        # Update heartbeat
                        strategy.last_heartbeat = datetime.now()
                        
                        # Check resource usage
                        await self._check_strategy_resources(strategy_id)
                        
                        # Check for stale strategies
                        if (datetime.now() - strategy.last_heartbeat).seconds > 300:  # 5 minutes
                            self.logger.warning(f"Strategy {strategy_id} appears stale, marking as error")
                            strategy.status = StrategyStatus.ERROR
                            strategy.error_count += 1
                
            except Exception as e:
                self.logger.error(f"Error in health monitor: {e}", exc_info=True)

    async def _check_strategy_resources(self, strategy_id: str):
        """Check and log resource usage for a strategy"""
        try:
            # Get process resource usage
            process = psutil.Process()
            cpu_percent = process.cpu_percent()
            memory_info = process.memory_info()
            
            resource_usage = {
                "cpu_percent": cpu_percent,
                "memory_mb": memory_info.rss / 1024 / 1024,
                "memory_percent": process.memory_percent()
            }
            
            self.strategies[strategy_id].resource_usage = resource_usage
            
            # Check limits
            if cpu_percent > self.cpu_limit_per_strategy:
                self.logger.warning(f"Strategy {strategy_id} CPU usage {cpu_percent}% exceeds limit {self.cpu_limit_per_strategy}%")
            
            if memory_info.rss > self.memory_limit_per_strategy:
                self.logger.warning(f"Strategy {strategy_id} memory usage {memory_info.rss} exceeds limit {self.memory_limit_per_strategy}")
                
        except Exception as e:
            self.logger.error(f"Error checking resources for strategy {strategy_id}: {e}")

    async def route_market_event(self, event: MarketEvent, strategy_id: str = None):
        """Route market events to specific strategy or all strategies"""
        if strategy_id:
            # Route to specific strategy
            if strategy_id in self.strategies and self.strategies[strategy_id].status == StrategyStatus.RUNNING:
                await self._send_event_to_strategy(strategy_id, event)
        else:
            # Route to all running strategies
            for sid, strategy in self.strategies.items():
                if strategy.status == StrategyStatus.RUNNING:
                    await self._send_event_to_strategy(sid, event)

    async def _send_event_to_strategy(self, strategy_id: str, event: MarketEvent):
        """Send event to specific strategy with error handling"""
        try:
            strategy = self.strategies[strategy_id]
            await strategy.instance.handle_market_event(event)
        except Exception as e:
            strategy.error_count += 1
            self.logger.error(f"Error in strategy {strategy_id} handling market event: {e}", exc_info=True)
            
            if strategy.error_count >= strategy.max_errors:
                strategy.status = StrategyStatus.ERROR
                self.logger.critical(f"Strategy {strategy_id} exceeded max errors, stopping")

    def get_strategy_by_name(self, name: str) -> Optional[StrategyInstance]:
        """Get strategy instance by name"""
        for strategy in self.strategies.values():
            if strategy.name == name:
                return strategy
        return None

    def get_strategies_by_status(self, status: StrategyStatus) -> List[StrategyInstance]:
        """Get all strategies with specific status"""
        return [s for s in self.strategies.values() if s.status == status]
