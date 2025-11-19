"""
MBVC (Momentum Breakout with Volume Confirmation) Strategy
Adapted for the paper trading engine with MBVC data format support.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from strategies.enhanced_base_strategy import EnhancedBaseStrategy
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, MACD


class MBVCStrategy(EnhancedBaseStrategy):
    """
    MBVC Strategy: Momentum Breakout with Volume Confirmation
    
    Entry Conditions:
    1. Price near 52-week high (within 10%)
    2. 3-day consolidation period
    3. RSI between 55-75
    4. EMA20 > EMA50 (momentum)
    5. MACD histogram rising
    6. Volume spike (1.5x average)
    7. Price above EMA20
    
    Exit Rules:
    - Target 1: 1.5R (exit 40% of position)
    - Target 2: 2.5R (exit 40% of position) 
    - Target 3: 3.5R (exit remaining 20%)
    - Stop Loss: 2% below swing low
    - Time Limit: 3 days maximum hold
    """
    
    def __init__(self, **kwargs):
        # Set MBVC-specific parameters
        mbvc_params = {
            'max_position_size': 1000,
            'max_drawdown': 0.05,
            'stop_loss_pct': 0.02,
            'take_profit_pct': 0.04,
            'data_window': 252,  # 1 year for 52-week high
            'rsi_period': 14,
            'ema_short': 20,
            'ema_long': 50,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'volume_lookback': 10,
            'volume_multiplier': 1.5,
            'consolidation_days': 3,
            'consolidation_threshold': 0.015,
            'near_high_threshold': 0.9,
            'rsi_min': 55,
            'rsi_max': 75,
            'max_positions': 4,
            'max_risk_per_trade': 0.0125,  # 1.25%
            'max_portfolio_risk': 0.05,    # 5%
            'hold_days': 3
        }
        
        # Merge with provided parameters
        mbvc_params.update(kwargs)
        
        super().__init__(**mbvc_params)
        
        # MBVC-specific state
        self.indicators_calculated = False
        self.last_signal_date = None
        self.position_targets = {}  # Track targets for each position
        
        self.logger.info(f"MBVC Strategy initialized with parameters: {self.params}")
    
    def preprocess_data(self, data: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """Preprocess data and calculate MBVC indicators"""
        if data.empty or len(data) < 50:  # Need enough data for indicators
            return data
        
        df = data.copy()
        
        # Ensure we have required columns
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required_cols):
            self.logger.warning(f"Missing required columns. Available: {df.columns.tolist()}")
            return data
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Calculate technical indicators
        df = self._calculate_indicators(df)
        
        # Calculate MBVC-specific features
        df = self._calculate_mbvc_features(df)
        
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for MBVC strategy"""
        try:
            # RSI
            df['rsi'] = RSIIndicator(df['close'], window=self.params['rsi_period']).rsi()
            
            # EMAs
            df['ema20'] = EMAIndicator(df['close'], window=self.params['ema_short']).ema_indicator()
            df['ema50'] = EMAIndicator(df['close'], window=self.params['ema_long']).ema_indicator()
            
            # MACD
            macd = MACD(
                df['close'], 
                window_slow=self.params['macd_slow'],
                window_fast=self.params['macd_fast'],
                window_sign=self.params['macd_signal']
            )
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            df['macd_hist'] = macd.macd_diff()
            
            # 52-week high
            df['52w_high'] = df['close'].rolling(252, min_periods=1).max()
            
            # Volume indicators
            df['10d_avg_vol'] = df['volume'].rolling(self.params['volume_lookback'], min_periods=1).mean()
            df['vol_ratio'] = df['volume'] / df['10d_avg_vol']
            
            # 3-day consolidation
            df['3d_consolidation'] = df['close'].rolling(self.params['consolidation_days']).apply(
                lambda x: np.std(x) < self.params['consolidation_threshold'] * x.mean() if len(x) == self.params['consolidation_days'] else False,
                raw=True
            )
            
            # Support and resistance
            df['swing_low_10d'] = df['low'].rolling(10, min_periods=1).min()
            df['swing_high_10d'] = df['high'].rolling(10, min_periods=1).max()
            
            self.indicators_calculated = True
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {e}")
        
        return df
    
    def _calculate_mbvc_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate MBVC-specific features"""
        try:
            # Price action patterns
            df['near_52w_high'] = df['close'] >= self.params['near_high_threshold'] * df['52w_high']
            df['above_ema20'] = df['close'] > df['ema20']
            df['ema20_above_ema50'] = df['ema20'] > df['ema50']
            df['macd_rising'] = df['macd_hist'] > df['macd_hist'].shift(1)
            
            # RSI in bullish zone
            df['rsi_bullish'] = (df['rsi'] >= self.params['rsi_min']) & (df['rsi'] <= self.params['rsi_max'])
            
            # Volume confirmation
            df['volume_spike'] = df['vol_ratio'] >= self.params['volume_multiplier']
            
        except Exception as e:
            self.logger.error(f"Error calculating MBVC features: {e}")
        
        return df
    
    def generate_signals(self, data: pd.DataFrame, context: Dict = None) -> pd.DataFrame:
        """Generate MBVC trading signals"""
        if data.empty or not self.indicators_calculated:
            return pd.DataFrame()
        
        df = data.copy()
        
        # MBVC Entry Conditions
        entry_conditions = (
            df['near_52w_high'] &  # Near 52-week high
            df['3d_consolidation'] &  # 3-day consolidation
            df['rsi_bullish'] &  # RSI in bullish zone
            df['ema20_above_ema50'] &  # EMA20 > EMA50
            df['macd_rising'] &  # MACD histogram rising
            df['volume_spike'] &  # Volume confirmation
            df['above_ema20']  # Price above EMA20
        )
        
        # Create signal column
        df['Signal'] = 0
        df.loc[entry_conditions, 'Signal'] = 1  # Buy signal
        
        # Add signal metadata
        df['signal_strength'] = df['Signal'] * (
            df['vol_ratio'] * 0.3 +  # Volume strength
            (df['rsi'] - 50) / 25 * 0.3 +  # RSI strength
            (df['close'] / df['52w_high']) * 0.4  # Proximity to high
        )
        
        return df
    
    def entry_rules(self, data: pd.DataFrame) -> pd.Series:
        """Define entry conditions for MBVC strategy"""
        return data.get('Signal', pd.Series(0, index=data.index))
    
    def exit_rules(self, data: pd.DataFrame) -> pd.Series:
        """Define exit conditions for MBVC strategy"""
        # For now, return zeros - exits will be handled by position management
        return pd.Series(0, index=data.index)
    
    def position_sizing(self, data: pd.DataFrame) -> pd.Series:
        """Calculate position size based on MBVC risk management"""
        if 'Signal' not in data.columns:
            return pd.Series(1, index=data.index)
        
        position_sizes = pd.Series(0, index=data.index)
        
        # Only size positions for buy signals
        buy_signals = data['Signal'] == 1
        
        if buy_signals.any():
            # Calculate risk-based position sizing
            for idx in data[buy_signals].index:
                try:
                    # Get current price and stop loss
                    current_price = data.loc[idx, 'close']
                    stop_loss = data.loc[idx, 'swing_low_10d'] * 0.98  # 2% below swing low
                    
                    # Calculate risk per share
                    risk_per_share = current_price - stop_loss
                    
                    if risk_per_share > 0:
                        # Position size based on 1.25% risk per trade
                        risk_amount = self.params.get('max_risk_per_trade', 0.0125) * 100000  # Assuming 100k capital
                        position_size = risk_amount / risk_per_share
                        
                        # Round down to whole shares
                        position_sizes.loc[idx] = max(1, int(position_size))
                    
                except Exception as e:
                    self.logger.error(f"Error calculating position size for index {idx}: {e}")
                    position_sizes.loc[idx] = 1
        
        return position_sizes
    
    def risk_management(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply MBVC risk management rules"""
        df = data.copy()
        
        # Add risk management columns
        df['stop_loss'] = df['swing_low_10d'] * 0.98
        df['target1'] = df['close'] + (df['close'] - df['stop_loss']) * 1.5  # 1.5R
        df['target2'] = df['close'] + (df['close'] - df['stop_loss']) * 2.5  # 2.5R
        df['target3'] = df['close'] + (df['close'] - df['stop_loss']) * 3.5  # 3.5R
        
        return df
    
    def description(self) -> str:
        """Return strategy description"""
        return """
        MBVC Strategy: Momentum Breakout with Volume Confirmation
        
        This strategy identifies stocks near their 52-week highs that are consolidating
        and ready for a breakout. It uses multiple technical indicators to confirm
        momentum and volume before entering positions.
        
        Entry Conditions:
        - Price within 10% of 52-week high
        - 3-day consolidation period
        - RSI between 55-75
        - EMA20 > EMA50
        - MACD histogram rising
        - Volume 1.5x average
        - Price above EMA20
        
        Exit Rules:
        - Target 1: 1.5R (exit 40%)
        - Target 2: 2.5R (exit 40%)
        - Target 3: 3.5R (exit 20%)
        - Stop Loss: 2% below swing low
        - Time Limit: 3 days
        """
    
    def parameter_schema(self) -> Dict[str, Dict]:
        """Define MBVC strategy parameters"""
        return {
            "max_position_size": {"type": "int", "min": 1, "max": 10000, "default": 1000},
            "max_drawdown": {"type": "float", "min": 0.01, "max": 0.5, "default": 0.05},
            "stop_loss_pct": {"type": "float", "min": 0.001, "max": 0.1, "default": 0.02},
            "take_profit_pct": {"type": "float", "min": 0.001, "max": 0.2, "default": 0.04},
            "data_window": {"type": "int", "min": 50, "max": 10000, "default": 252},
            "rsi_period": {"type": "int", "min": 5, "max": 50, "default": 14},
            "ema_short": {"type": "int", "min": 5, "max": 50, "default": 20},
            "ema_long": {"type": "int", "min": 20, "max": 200, "default": 50},
            "macd_fast": {"type": "int", "min": 5, "max": 20, "default": 12},
            "macd_slow": {"type": "int", "min": 20, "max": 50, "default": 26},
            "macd_signal": {"type": "int", "min": 5, "max": 20, "default": 9},
            "volume_lookback": {"type": "int", "min": 5, "max": 50, "default": 10},
            "volume_multiplier": {"type": "float", "min": 1.0, "max": 5.0, "default": 1.5},
            "consolidation_days": {"type": "int", "min": 2, "max": 10, "default": 3},
            "consolidation_threshold": {"type": "float", "min": 0.005, "max": 0.05, "default": 0.015},
            "near_high_threshold": {"type": "float", "min": 0.8, "max": 1.0, "default": 0.9},
            "rsi_min": {"type": "int", "min": 30, "max": 70, "default": 55},
            "rsi_max": {"type": "int", "min": 60, "max": 90, "default": 75},
            "max_positions": {"type": "int", "min": 1, "max": 20, "default": 4},
            "max_risk_per_trade": {"type": "float", "min": 0.001, "max": 0.05, "default": 0.0125},
            "max_portfolio_risk": {"type": "float", "min": 0.01, "max": 0.2, "default": 0.05},
            "hold_days": {"type": "int", "min": 1, "max": 10, "default": 3}
        }
    
    async def _update_positions(self, symbol: str, current_price: float, timestamp: datetime):
        """Enhanced position management for MBVC strategy"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        if position.quantity == 0:
            return
        
        # Update unrealized PnL
        position.unrealized_pnl = (current_price - position.avg_price) * position.quantity
        
        # Check MBVC exit conditions
        await self._check_mbvc_exits(symbol, current_price, timestamp)
    
    async def _check_mbvc_exits(self, symbol: str, current_price: float, timestamp: datetime):
        """Check MBVC-specific exit conditions"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        if position.quantity == 0:
            return
        
        # Get position targets
        if symbol not in self.position_targets:
            return
        
        targets = self.position_targets[symbol]
        
        # Check stop loss
        if current_price <= targets['stop_loss']:
            await self._create_exit_signal(symbol, "STOP_LOSS", current_price)
            return
        
        # Check targets
        if not targets['target1_hit'] and current_price >= targets['target1']:
            # Exit 40% of position
            exit_quantity = int(position.quantity * 0.4)
            if exit_quantity > 0:
                await self._create_partial_exit_signal(symbol, "TARGET1", current_price, exit_quantity)
                targets['target1_hit'] = True
                targets['trailing_stop'] = current_price * 0.98
        
        elif targets['target1_hit'] and not targets['target2_hit'] and current_price >= targets['target2']:
            # Exit 40% of original position
            exit_quantity = int(targets['original_quantity'] * 0.4)
            if exit_quantity > 0:
                await self._create_partial_exit_signal(symbol, "TARGET2", current_price, exit_quantity)
                targets['target2_hit'] = True
        
        elif targets['target2_hit'] and not targets['target3_hit'] and current_price >= targets['target3']:
            # Exit remaining position
            await self._create_exit_signal(symbol, "TARGET3", current_price)
            targets['target3_hit'] = True
        
        # Check trailing stop
        elif targets.get('trailing_stop') and current_price <= targets['trailing_stop']:
            await self._create_exit_signal(symbol, "TRAILING_STOP", current_price)
        
        # Check time limit
        elif (timestamp - position.entry_time).days >= self.params.get('hold_days', 3):
            await self._create_exit_signal(symbol, "TIME_LIMIT", current_price)
    
    async def _create_partial_exit_signal(self, symbol: str, reason: str, price: float, quantity: int):
        """Create a partial exit signal"""
        from engine.event_engine import SignalEvent
        
        signal_event = SignalEvent(
            instrument_token=symbol,
            strategy_id=self.strategy_id,
            signal_type="SELL",
            quantity=quantity,
            price=price,
            order_type="MARKET",
            product_type="MIS",
            validity="DAY",
            tag=f"{self.strategy_id}_{reason}"
        )
        
        await self.event_engine.put(signal_event)
        self.logger.info(f"Partial exit signal for {symbol}: {reason} - {quantity} units @ {price}")
    
    async def _process_signals(self, signals_df: pd.DataFrame, symbol: str, timestamp: datetime):
        """Process MBVC signals with position target tracking"""
        try:
            latest_signal = signals_df.iloc[-1]
            
            # Check for entry signals
            if latest_signal.get('Entry_Signal', 0) != 0:
                action = "BUY" if latest_signal['Entry_Signal'] > 0 else "SELL"
                quantity = abs(latest_signal.get('Position_Size', 1))
                
                # Create signal event
                from engine.event_engine import SignalEvent
                signal_event = SignalEvent(
                    instrument_token=symbol,
                    strategy_id=self.strategy_id,
                    signal_type=action,
                    quantity=int(quantity),
                    price=latest_signal.get('close', 0),
                    order_type="MARKET",
                    product_type="MIS",
                    validity="DAY",
                    tag=f"{self.strategy_id}_{action}"
                )
                
                await self.event_engine.put(signal_event)
                
                # Set up position targets
                if action == "BUY":
                    self.position_targets[symbol] = {
                        'stop_loss': latest_signal.get('stop_loss', 0),
                        'target1': latest_signal.get('target1', 0),
                        'target2': latest_signal.get('target2', 0),
                        'target3': latest_signal.get('target3', 0),
                        'original_quantity': quantity,
                        'target1_hit': False,
                        'target2_hit': False,
                        'target3_hit': False,
                        'trailing_stop': None
                    }
                
                self.logger.info(f"Generated {action} signal for {symbol}: {quantity} units")
            
        except Exception as e:
            self.logger.error(f"Error processing signals for {symbol}: {e}", exc_info=True)
