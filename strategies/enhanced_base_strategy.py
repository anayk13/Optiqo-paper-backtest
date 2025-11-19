"""
Enhanced Base Strategy for Production-Ready Multi-Strategy Execution
Bridges LLM-generated strategies with the production trading engine.
Supports complex strategies like MBVC (Multi-Broker, Multi-Venue, Multi-Strategy).
"""

import pandas as pd
import numpy as np
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json

from engine.event_engine import EventEngine, MarketEvent, SignalEvent, OrderEvent, FillEvent
from strategies.base_strategy import BaseStrategy


class AssetType(Enum):
    EQUITY = "equity"
    FUTURES = "futures"
    OPTIONS = "options"
    CURRENCY = "currency"
    COMMODITY = "commodity"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class Position:
    """Represents a trading position"""
    symbol: str
    quantity: float
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    entry_time: datetime = None
    asset_type: AssetType = AssetType.EQUITY


@dataclass
class Signal:
    """Enhanced signal with metadata for complex strategies"""
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    quantity: float
    price: float
    order_type: OrderType
    confidence: float = 1.0
    metadata: Dict[str, Any] = None
    timestamp: datetime = None


class EnhancedBaseStrategy(BaseStrategy):
    """
    Enhanced base strategy that supports complex multi-asset, multi-timeframe strategies.
    Compatible with LLM-generated strategy format while providing production features.
    """
    
    def __init__(self, 
                 event_engine: EventEngine,
                 logger: logging.Logger,
                 executor_account_name: str,
                 strategy_id: str = None,
                 strategy_manager=None,
                 **strategy_config_params):
        super().__init__(event_engine, logger, executor_account_name)
        
        # Enhanced properties for complex strategies
        self.strategy_id = strategy_id or f"strategy_{id(self)}"
        self.strategy_manager = strategy_manager
        self.params = strategy_config_params or {}
        
        # Multi-asset support
        self.tracked_symbols: List[str] = []
        self.positions: Dict[str, Position] = {}
        self.positions_history: List[Dict] = []
        
        # Data management for complex strategies
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.feature_cache: Dict[str, pd.DataFrame] = {}
        self.context_data: Dict[str, Any] = {}
        
        # Signal management
        self.pending_signals: List[Signal] = []
        self.signal_history: List[Signal] = []
        
        # Risk management
        self.max_position_size = self.params.get('max_position_size', 1000)
        self.max_drawdown = self.params.get('max_drawdown', 0.1)
        self.stop_loss_pct = self.params.get('stop_loss_pct', 0.02)
        self.take_profit_pct = self.params.get('take_profit_pct', 0.04)
        
        # Performance tracking
        self.performance_metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0
        }
        
        # Strategy state
        self.is_initialized = False
        self.last_update_time = None
        
        self.logger.info(f"Enhanced strategy {self.strategy_id} initialized with params: {self.params}")

    async def initialize(self):
        """Initialize the strategy with any required setup"""
        try:
            # Load initial data if needed
            await self._load_initial_data()
            
            # Initialize any ML models or indicators
            await self._initialize_indicators()
            
            self.is_initialized = True
            self.logger.info(f"Strategy {self.strategy_id} initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize strategy {self.strategy_id}: {e}", exc_info=True)
            raise

    async def cleanup(self):
        """Cleanup resources when strategy is stopped"""
        try:
            # Save final state
            await self._save_strategy_state()
            
            # Clear caches
            self.data_cache.clear()
            self.feature_cache.clear()
            
            self.logger.info(f"Strategy {self.strategy_id} cleaned up successfully")
            
        except Exception as e:
            self.logger.error(f"Error during strategy cleanup {self.strategy_id}: {e}", exc_info=True)

    async def handle_market_event(self, event: MarketEvent):
        """Enhanced market event handling for complex strategies"""
        try:
            if not self.is_initialized:
                return
            
            symbol = event.instrument_token
            current_time = datetime.fromtimestamp(event.timestamp)
            
            # Update data cache
            await self._update_data_cache(symbol, event.ltp, current_time)
            
            # Check if this symbol is tracked by strategy
            if symbol not in self.tracked_symbols:
                return
            
            # Get current data for analysis
            data = self._get_current_data(symbol)
            if data is None or len(data) < 2:
                return
            
            # Generate signals using the LLM-compatible interface
            signals_df = await self._generate_signals_async(data, symbol)
            
            # Process signals
            if signals_df is not None and not signals_df.empty:
                await self._process_signals(signals_df, symbol, current_time)
            
            # Update positions
            await self._update_positions(symbol, event.ltp, current_time)
            
            # Apply risk management
            await self._apply_risk_management(symbol, event.ltp, current_time)
            
            self.last_update_time = current_time
            
        except Exception as e:
            self.logger.error(f"Error handling market event for {event.instrument_token}: {e}", exc_info=True)

    async def handle_fill_event(self, event: FillEvent):
        """Handle fill events and update positions"""
        try:
            symbol = event.instrument_token
            quantity = event.quantity
            price = event.price
            action = event.transaction_type
            
            # Update position
            if symbol in self.positions:
                position = self.positions[symbol]
                
                if action == "BUY":
                    # Add to position
                    old_quantity = position.quantity
                    old_avg_price = position.avg_price
                    
                    new_quantity = old_quantity + quantity
                    if new_quantity != 0:
                        position.avg_price = ((old_quantity * old_avg_price) + (quantity * price)) / new_quantity
                    position.quantity = new_quantity
                    
                elif action == "SELL":
                    # Reduce position
                    position.quantity -= quantity
                    
                    # Calculate realized PnL
                    if quantity > 0:
                        realized_pnl = (price - position.avg_price) * quantity
                        position.realized_pnl += realized_pnl
                        self.performance_metrics['total_pnl'] += realized_pnl
                        
                        # Update trade statistics
                        self.performance_metrics['total_trades'] += 1
                        if realized_pnl > 0:
                            self.performance_metrics['winning_trades'] += 1
                        else:
                            self.performance_metrics['losing_trades'] += 1
                
                # Remove position if quantity becomes zero
                if abs(position.quantity) < 1e-6:
                    del self.positions[symbol]
                
                # Record position history
                self.positions_history.append({
                    'timestamp': datetime.now(),
                    'symbol': symbol,
                    'quantity': position.quantity,
                    'avg_price': position.avg_price,
                    'realized_pnl': position.realized_pnl,
                    'action': action
                })
            
            self.logger.info(f"Position updated for {symbol}: {action} {quantity} @ {price}")
            
        except Exception as e:
            self.logger.error(f"Error handling fill event: {e}", exc_info=True)

    async def _generate_signals_async(self, data: pd.DataFrame, symbol: str) -> Optional[pd.DataFrame]:
        """Generate signals using the LLM-compatible interface"""
        try:
            # Create context for complex strategies
            context = {
                'symbol': symbol,
                'positions': self.positions,
                'performance_metrics': self.performance_metrics,
                'strategy_params': self.params,
                'additional_data': self.context_data
            }
            
            # Preprocess data
            processed_data = self.preprocess_data(data, context)
            
            # Generate signals
            signals_df = self.generate_signals(processed_data, context)
            
            # Apply entry/exit rules
            if 'Signal' in signals_df.columns:
                entry_signals = self.entry_rules(signals_df)
                exit_signals = self.exit_rules(signals_df)
                
                # Combine signals
                signals_df['Entry_Signal'] = entry_signals
                signals_df['Exit_Signal'] = exit_signals
                
                # Apply position sizing
                position_sizes = self.position_sizing(signals_df)
                signals_df['Position_Size'] = position_sizes
                
                # Apply risk management
                signals_df = self.risk_management(signals_df)
            
            return signals_df
            
        except Exception as e:
            self.logger.error(f"Error generating signals for {symbol}: {e}", exc_info=True)
            return None

    async def _process_signals(self, signals_df: pd.DataFrame, symbol: str, timestamp: datetime):
        """Process generated signals and create orders"""
        try:
            latest_signal = signals_df.iloc[-1]
            
            # Check for entry signals
            if latest_signal.get('Entry_Signal', 0) != 0:
                action = "BUY" if latest_signal['Entry_Signal'] > 0 else "SELL"
                quantity = abs(latest_signal.get('Position_Size', 1))
                
                # Create signal event
                signal_event = SignalEvent(
                    instrument_token=symbol,
                    strategy_id=self.strategy_id,
                    signal_type=action,
                    quantity=int(quantity),
                    price=latest_signal.get('price', 0),
                    order_type="MARKET",
                    product_type="MIS",
                    validity="DAY",
                    tag=f"{self.strategy_id}_{action}"
                )
                
                await self.event_engine.put(signal_event)
                self.logger.info(f"Generated {action} signal for {symbol}: {quantity} units")
            
            # Check for exit signals
            elif latest_signal.get('Exit_Signal', 0) != 0 and symbol in self.positions:
                position = self.positions[symbol]
                if position.quantity != 0:
                    action = "SELL" if position.quantity > 0 else "BUY"
                    quantity = abs(position.quantity)
                    
                    signal_event = SignalEvent(
                        instrument_token=symbol,
                        strategy_id=self.strategy_id,
                        signal_type=action,
                        quantity=int(quantity),
                        price=latest_signal.get('price', 0),
                        order_type="MARKET",
                        product_type="MIS",
                        validity="DAY",
                        tag=f"{self.strategy_id}_EXIT"
                    )
                    
                    await self.event_engine.put(signal_event)
                    self.logger.info(f"Generated EXIT signal for {symbol}: {quantity} units")
            
        except Exception as e:
            self.logger.error(f"Error processing signals for {symbol}: {e}", exc_info=True)

    def _get_current_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get current data for symbol"""
        if symbol in self.data_cache:
            return self.data_cache[symbol]
        return None

    async def _update_data_cache(self, symbol: str, price: float, timestamp: datetime):
        """Update data cache with new price data"""
        if symbol not in self.data_cache:
            self.data_cache[symbol] = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Add new data point
        new_row = pd.DataFrame({
            'timestamp': [timestamp],
            'open': [price],
            'high': [price],
            'low': [price],
            'close': [price],
            'volume': [1]  # Default volume
        })
        
        self.data_cache[symbol] = pd.concat([self.data_cache[symbol], new_row], ignore_index=True)
        
        # Keep only recent data (configurable window)
        max_rows = self.params.get('data_window', 1000)
        if len(self.data_cache[symbol]) > max_rows:
            self.data_cache[symbol] = self.data_cache[symbol].tail(max_rows).reset_index(drop=True)

    async def _update_positions(self, symbol: str, current_price: float, timestamp: datetime):
        """Update position unrealized PnL"""
        if symbol in self.positions:
            position = self.positions[symbol]
            if position.quantity != 0:
                position.unrealized_pnl = (current_price - position.avg_price) * position.quantity

    async def _apply_risk_management(self, symbol: str, current_price: float, timestamp: datetime):
        """Apply risk management rules"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        if position.quantity == 0:
            return
        
        # Stop loss check
        if self.stop_loss_pct > 0:
            if position.quantity > 0:  # Long position
                stop_price = position.avg_price * (1 - self.stop_loss_pct)
                if current_price <= stop_price:
                    await self._create_exit_signal(symbol, "STOP_LOSS", current_price)
            else:  # Short position
                stop_price = position.avg_price * (1 + self.stop_loss_pct)
                if current_price >= stop_price:
                    await self._create_exit_signal(symbol, "STOP_LOSS", current_price)
        
        # Take profit check
        if self.take_profit_pct > 0:
            if position.quantity > 0:  # Long position
                profit_price = position.avg_price * (1 + self.take_profit_pct)
                if current_price >= profit_price:
                    await self._create_exit_signal(symbol, "TAKE_PROFIT", current_price)
            else:  # Short position
                profit_price = position.avg_price * (1 - self.take_profit_pct)
                if current_price <= profit_price:
                    await self._create_exit_signal(symbol, "TAKE_PROFIT", current_price)

    async def _create_exit_signal(self, symbol: str, reason: str, price: float):
        """Create an exit signal for risk management"""
        position = self.positions[symbol]
        action = "SELL" if position.quantity > 0 else "BUY"
        quantity = abs(position.quantity)
        
        signal_event = SignalEvent(
            instrument_token=symbol,
            strategy_id=self.strategy_id,
            signal_type=action,
            quantity=int(quantity),
            price=price,
            order_type="MARKET",
            product_type="MIS",
            validity="DAY",
            tag=f"{self.strategy_id}_{reason}"
        )
        
        await self.event_engine.put(signal_event)
        self.logger.info(f"Risk management exit signal for {symbol}: {reason}")

    async def _load_initial_data(self):
        """Load initial data if needed"""
        # Override in subclasses for specific data loading
        pass

    async def _initialize_indicators(self):
        """Initialize any technical indicators or ML models"""
        # Override in subclasses for specific initialization
        pass

    async def _save_strategy_state(self):
        """Save strategy state for persistence"""
        # Override in subclasses for specific state saving
        pass

    # LLM-Compatible Interface Methods (to be implemented by generated strategies)
    
    def preprocess_data(self, data: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """
        Preprocess input data before signal generation.
        Override in generated strategies.
        """
        return data

    def generate_signals(self, data: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """
        Core strategy logic: generate trading signals.
        Must be implemented by generated strategies.
        """
        raise NotImplementedError("generate_signals must be implemented by strategy")

    def description(self) -> str:
        """
        Text description of what the strategy does.
        """
        return f"Enhanced Strategy {self.strategy_id}"

    def parameter_schema(self) -> Dict[str, Dict]:
        """
        Define the parameters with metadata (for no-code UI).
        """
        return {
            "max_position_size": {"type": "int", "min": 1, "max": 10000, "default": 1000},
            "max_drawdown": {"type": "float", "min": 0.01, "max": 0.5, "default": 0.1},
            "stop_loss_pct": {"type": "float", "min": 0.001, "max": 0.1, "default": 0.02},
            "take_profit_pct": {"type": "float", "min": 0.001, "max": 0.2, "default": 0.04},
            "data_window": {"type": "int", "min": 50, "max": 10000, "default": 1000}
        }

    def entry_rules(self, data: pd.DataFrame) -> pd.Series:
        """
        Define conditions for entering trades.
        """
        return data.get("Signal", pd.Series(0, index=data.index))

    def exit_rules(self, data: pd.DataFrame) -> pd.Series:
        """
        Define conditions for exiting trades.
        """
        return pd.Series(0, index=data.index)

    def position_sizing(self, data: pd.DataFrame) -> pd.Series:
        """
        Define how much to allocate per trade.
        """
        return pd.Series(1, index=data.index)

    def risk_management(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Apply stop-loss, take-profit, or max drawdown rules.
        """
        return data

    def parameters(self) -> Dict[str, Any]:
        """
        Return the current parameter dictionary.
        """
        return self.params

    # Additional methods for complex strategies
    
    def add_tracked_symbol(self, symbol: str):
        """Add a symbol to track for this strategy"""
        if symbol not in self.tracked_symbols:
            self.tracked_symbols.append(symbol)
            self.logger.info(f"Added {symbol} to tracked symbols")

    def remove_tracked_symbol(self, symbol: str):
        """Remove a symbol from tracking"""
        if symbol in self.tracked_symbols:
            self.tracked_symbols.remove(symbol)
            self.logger.info(f"Removed {symbol} from tracked symbols")

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        return self.performance_metrics.copy()

    def get_positions(self) -> Dict[str, Position]:
        """Get current positions"""
        return self.positions.copy()

    def get_strategy_state(self) -> Dict[str, Any]:
        """Get complete strategy state for persistence"""
        return {
            'strategy_id': self.strategy_id,
            'params': self.params,
            'positions': {k: {
                'symbol': v.symbol,
                'quantity': v.quantity,
                'avg_price': v.avg_price,
                'unrealized_pnl': v.unrealized_pnl,
                'realized_pnl': v.realized_pnl
            } for k, v in self.positions.items()},
            'performance_metrics': self.performance_metrics,
            'tracked_symbols': self.tracked_symbols,
            'last_update_time': self.last_update_time.isoformat() if self.last_update_time else None
        }
