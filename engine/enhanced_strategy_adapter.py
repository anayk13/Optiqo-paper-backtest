"""
Enhanced Strategy Adapter for Production Multi-Strategy Execution
Handles both original and LLM-generated strategies with advanced features.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import json

from .event_engine import EventEngine, MarketEvent, SignalEvent, OrderEvent, FillEvent
from .portfolio import PortfolioManager
from .trade_executor import TradeExecutor
from .risk_manager import RiskManager
from .logger import get_logger
from strategies.base_strategy import BaseStrategy
from strategies.enhanced_base_strategy import EnhancedBaseStrategy


class EnhancedStrategyAdapter:
    """
    Enhanced adapter that can handle both original and LLM-generated strategies.
    Provides advanced features for complex multi-strategy execution.
    """
    
    def __init__(self,
                 event_engine: EventEngine,
                 strategy: Union[BaseStrategy, EnhancedBaseStrategy],
                 portfolio_manager: PortfolioManager,
                 trade_executor: TradeExecutor,
                 risk_manager: RiskManager,
                 logger: logging.Logger,
                 strategy_id: str = None):
        self.event_engine = event_engine
        self.strategy = strategy
        self.portfolio_manager = portfolio_manager
        self.trade_executor = trade_executor
        self.risk_manager = risk_manager
        self.logger = logger
        self.strategy_id = strategy_id or getattr(strategy, 'strategy_id', 'unknown')
        
        # Enhanced features
        self.is_enhanced = isinstance(strategy, EnhancedBaseStrategy)
        self.signal_history: List[Dict] = []
        self.performance_tracker = PerformanceTracker()
        
        # Strategy-specific configuration
        self.max_signals_per_minute = 10
        self.signal_rate_limiter = {}
        
        self.logger.info(f"Enhanced StrategyAdapter initialized for {self.strategy_id} (Enhanced: {self.is_enhanced})")

    async def on_market_event(self, event: MarketEvent):
        """
        Enhanced market event processing with rate limiting and error handling.
        """
        try:
            # Rate limiting check
            if not self._check_rate_limit(event.instrument_token):
                self.logger.debug(f"Rate limited for {event.instrument_token}, skipping")
                return
            
            # Enhanced strategies handle their own data management
            if self.is_enhanced:
                await self.strategy.handle_market_event(event)
            else:
                # Original strategy handling
                await self.strategy.handle_market_event(event)
            
            # Track performance
            self.performance_tracker.record_market_event(event)
            
        except Exception as e:
            self.logger.error(f"Error in market event processing for {event.instrument_token}: {e}", exc_info=True)

    async def on_signal_event(self, event: SignalEvent):
        """
        Enhanced signal processing with validation and tracking.
        """
        try:
            # Validate signal
            if not self._validate_signal(event):
                self.logger.warning(f"Invalid signal rejected: {event}")
                return
            
            # Record signal
            self._record_signal(event)
            
            # Enhanced risk management for complex strategies
            if self.is_enhanced:
                await self._process_enhanced_signal(event)
            else:
                await self._process_original_signal(event)
            
        except Exception as e:
            self.logger.error(f"Error processing signal event: {e}", exc_info=True)

    async def on_fill_event(self, event: FillEvent):
        """
        Enhanced fill event processing with performance tracking.
        """
        try:
            # Pass to strategy
            await self.strategy.handle_fill_event(event)
            
            # Track performance
            self.performance_tracker.record_fill_event(event)
            
            # Update signal history with fill status
            self._update_signal_with_fill(event)
            
        except Exception as e:
            self.logger.error(f"Error processing fill event: {e}", exc_info=True)

    async def _process_enhanced_signal(self, event: SignalEvent):
        """Process signals for enhanced strategies with advanced features"""
        try:
            # Get strategy context
            if hasattr(self.strategy, 'get_strategy_state'):
                strategy_state = self.strategy.get_strategy_state()
                
                # Check portfolio-level risk limits
                if not await self._check_portfolio_risk_limits(event, strategy_state):
                    self.logger.warning(f"Portfolio risk limit exceeded for signal: {event}")
                    return
            
            # Enhanced risk validation
            is_valid, margin_req, brokerage_req = await self.risk_manager.validate_order(
                exchange_token=event.instrument_token,
                quantity=event.quantity,
                product=event.product_type,
                transaction_type=event.signal_type,
                trade_type="entry",
                price=event.price
            )
            
            if is_valid:
                # Create order with enhanced metadata
                order_event = OrderEvent(
                    instrument_token=event.instrument_token,
                    transaction_type=event.signal_type,
                    quantity=event.quantity,
                    product=event.product_type,
                    validity=event.validity,
                    order_type=event.order_type,
                    price=event.price,
                    tag=f"{self.strategy_id}_{event.tag}"
                )
                
                await self.event_engine.put(order_event)
                self.logger.info(f"Enhanced signal processed: {event.signal_type} {event.quantity} of {event.instrument_token}")
            else:
                self.logger.warning(f"Enhanced signal rejected by risk manager: {event}")
                
        except Exception as e:
            self.logger.error(f"Error processing enhanced signal: {e}", exc_info=True)

    async def _process_original_signal(self, event: SignalEvent):
        """Process signals for original strategies (backward compatibility)"""
        try:
            # Standard risk validation
            is_valid, margin_req, brokerage_req = await self.risk_manager.validate_order(
                exchange_token=event.instrument_token,
                quantity=event.quantity,
                product=event.product_type,
                transaction_type=event.signal_type,
                trade_type="entry",
                price=event.price
            )
            
            if is_valid:
                order_event = OrderEvent(
                    instrument_token=event.instrument_token,
                    transaction_type=event.signal_type,
                    quantity=event.quantity,
                    product=event.product_type,
                    validity=event.validity,
                    order_type=event.order_type,
                    price=event.price,
                    tag=event.tag
                )
                
                await self.event_engine.put(order_event)
                self.logger.info(f"Original signal processed: {event.signal_type} {event.quantity} of {event.instrument_token}")
            else:
                self.logger.warning(f"Original signal rejected by risk manager: {event}")
                
        except Exception as e:
            self.logger.error(f"Error processing original signal: {e}", exc_info=True)

    def _validate_signal(self, event: SignalEvent) -> bool:
        """Validate signal before processing"""
        try:
            # Basic validation
            if not event.instrument_token or not event.signal_type or event.quantity <= 0:
                return False
            
            # Signal type validation
            if event.signal_type not in ['BUY', 'SELL']:
                return False
            
            # Quantity validation
            if event.quantity > 10000:  # Reasonable upper limit
                self.logger.warning(f"Signal quantity too large: {event.quantity}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating signal: {e}")
            return False

    def _record_signal(self, event: SignalEvent):
        """Record signal for tracking and analysis"""
        signal_record = {
            'timestamp': datetime.now(),
            'strategy_id': self.strategy_id,
            'instrument_token': event.instrument_token,
            'signal_type': event.signal_type,
            'quantity': event.quantity,
            'price': event.price,
            'order_type': event.order_type,
            'status': 'pending'
        }
        
        self.signal_history.append(signal_record)
        
        # Keep only recent signals (configurable limit)
        max_history = 1000
        if len(self.signal_history) > max_history:
            self.signal_history = self.signal_history[-max_history:]

    def _update_signal_with_fill(self, event: FillEvent):
        """Update signal history with fill information"""
        # Find matching signal (simplified matching by instrument and recent timestamp)
        for signal in reversed(self.signal_history[-10:]):  # Check last 10 signals
            if (signal['instrument_token'] == event.instrument_token and 
                signal['status'] == 'pending' and
                (datetime.now() - signal['timestamp']).seconds < 300):  # Within 5 minutes
                signal['status'] = 'filled'
                signal['fill_price'] = event.price
                signal['fill_timestamp'] = datetime.fromtimestamp(event.fill_timestamp)
                break

    def _check_rate_limit(self, instrument_token: str) -> bool:
        """Check if signal rate limit is exceeded"""
        current_time = datetime.now()
        minute_key = current_time.strftime('%Y-%m-%d %H:%M')
        
        if minute_key not in self.signal_rate_limiter:
            self.signal_rate_limiter[minute_key] = {}
        
        if instrument_token not in self.signal_rate_limiter[minute_key]:
            self.signal_rate_limiter[minute_key][instrument_token] = 0
        
        # Check limit
        if self.signal_rate_limiter[minute_key][instrument_token] >= self.max_signals_per_minute:
            return False
        
        # Increment counter
        self.signal_rate_limiter[minute_key][instrument_token] += 1
        
        # Cleanup old entries
        self._cleanup_rate_limiter()
        
        return True

    def _cleanup_rate_limiter(self):
        """Cleanup old rate limiter entries"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(hours=1)
        cutoff_key = cutoff_time.strftime('%Y-%m-%d %H:%M')
        
        # Remove old entries
        keys_to_remove = [k for k in self.signal_rate_limiter.keys() if k < cutoff_key]
        for key in keys_to_remove:
            del self.signal_rate_limiter[key]

    async def _check_portfolio_risk_limits(self, event: SignalEvent, strategy_state: Dict) -> bool:
        """Check portfolio-level risk limits for enhanced strategies"""
        try:
            # Get current positions
            positions = strategy_state.get('positions', {})
            
            # Check position concentration
            total_exposure = sum(abs(pos['quantity'] * pos['avg_price']) for pos in positions.values())
            new_exposure = event.quantity * event.price
            
            # Simple concentration limit (can be enhanced)
            max_concentration = 0.3  # 30% of portfolio
            if new_exposure > total_exposure * max_concentration:
                self.logger.warning(f"Position concentration limit exceeded for {event.instrument_token}")
                return False
            
            # Check drawdown limits
            performance_metrics = strategy_state.get('performance_metrics', {})
            current_drawdown = abs(performance_metrics.get('max_drawdown', 0))
            max_drawdown_limit = 0.15  # 15% max drawdown
            
            if current_drawdown > max_drawdown_limit:
                self.logger.warning(f"Max drawdown limit exceeded: {current_drawdown}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking portfolio risk limits: {e}")
            return False

    def get_signal_history(self, limit: int = 100) -> List[Dict]:
        """Get recent signal history"""
        return self.signal_history[-limit:] if self.signal_history else []

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for this strategy"""
        return self.performance_tracker.get_metrics()

    def get_strategy_info(self) -> Dict[str, Any]:
        """Get comprehensive strategy information"""
        info = {
            'strategy_id': self.strategy_id,
            'is_enhanced': self.is_enhanced,
            'signal_count': len(self.signal_history),
            'performance_metrics': self.get_performance_metrics()
        }
        
        if self.is_enhanced and hasattr(self.strategy, 'get_strategy_state'):
            info['strategy_state'] = self.strategy.get_strategy_state()
        
        return info


class PerformanceTracker:
    """Tracks performance metrics for strategies"""
    
    def __init__(self):
        self.market_events_count = 0
        self.fill_events_count = 0
        self.total_volume = 0
        self.start_time = datetime.now()
    
    def record_market_event(self, event: MarketEvent):
        """Record market event"""
        self.market_events_count += 1
    
    def record_fill_event(self, event: FillEvent):
        """Record fill event"""
        self.fill_events_count += 1
        self.total_volume += event.quantity
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        runtime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            'market_events_processed': self.market_events_count,
            'fills_executed': self.fill_events_count,
            'total_volume': self.total_volume,
            'runtime_seconds': runtime,
            'events_per_second': self.market_events_count / runtime if runtime > 0 else 0
        }
