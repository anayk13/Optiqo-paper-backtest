import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Import base strategy class
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from strat2_base import Strategy

class HighBreakoutStrategy(Strategy):
    """
    Buy stock when it closes above 52-week high, hold for 20 days or 5% stop loss
    """
    
    def __init__(self, params=None, data_config=None):
        super().__init__(params, data_config)
        self.entry_price = None
        self.entry_date = None
        self.position_active = False
        
    def description(self):
        return "Buy stock when it closes above 52-week high, hold for 20 days or 5% stop loss"
    
    def parameter_schema(self):
        return {
            "lookback": {"type": "int", "min": 50, "max": 500, "default": 252},
            "hold_days": {"type": "int", "min": 1, "max": 100, "default": 20},
            "stop_pct": {"type": "float", "min": 0.1, "max": 20.0, "default": 5.0}
        }
    
    def generate_signals(self, data, context=None):
        """
        Core strategy logic: generate trading signals based on 52-week high breakout
        """
        # Get parameters with defaults
        lookback = self.params.get("lookback", 252)
        hold_days = self.params.get("hold_days", 20)
        stop_pct = self.params.get("stop_pct", 5.0)
        
        # Initialize signals dataframe
        signals = data.copy()
        signals['Signal'] = 0
        signals['52_week_high'] = signals['Close'].rolling(window=lookback).max()
        signals['Hold_days'] = 0
        signals['Entry_price'] = np.nan
        signals['Exit_price'] = np.nan
        
        # Track position state
        position_active = False
        entry_price = 0
        entry_index = 0
        
        for i in range(lookback, len(signals)):
            current_close = signals['Close'].iloc[i]
            current_52_week_high = signals['52_week_high'].iloc[i-1]  # Use previous day's 52-week high
            
            if not position_active:
                # Entry condition: close above 52-week high
                if current_close > current_52_week_high:
                    signals.loc[signals.index[i], 'Signal'] = 1
                    signals.loc[signals.index[i], 'Entry_price'] = current_close
                    position_active = True
                    entry_price = current_close
                    entry_index = i
                    
            else:
                # Calculate days held
                days_held = i - entry_index
                signals.loc[signals.index[i], 'Hold_days'] = days_held
                
                # Exit condition 1: Time-based (hold for 20 days)
                if days_held >= hold_days:
                    signals.loc[signals.index[i], 'Signal'] = -1
                    signals.loc[signals.index[i], 'Exit_price'] = current_close
                    position_active = False
                    
                # Exit condition 2: Stop loss (5% below entry)
                elif current_close <= entry_price * (1 - stop_pct/100):
                    signals.loc[signals.index[i], 'Signal'] = -1
                    signals.loc[signals.index[i], 'Exit_price'] = current_close
                    position_active = False
                    
                else:
                    # Continue holding
                    signals.loc[signals.index[i], 'Signal'] = 0
                    signals.loc[signals.index[i], 'Entry_price'] = entry_price
        
        # Ensure Signal column is properly formatted
        signals['Signal'] = signals['Signal'].fillna(0).astype(int)
        
        self.signals = signals
        return signals
    
    def entry_rules(self, data):
        """
        Entry condition: close price above 52-week high
        """
        return data["Signal"] == 1
    
    def exit_rules(self, data):
        """
        Exit conditions: time-based (20 days) or stop loss (5%)
        """
        exit_signals = pd.Series(0, index=data.index)
        
        if 'Hold_days' in data.columns and 'Entry_price' in data.columns:
            # Time-based exit
            time_exit = data['Hold_days'] >= self.params.get("hold_days", 20)
            
            # Stop loss exit
            stop_exit = data['Close'] <= data['Entry_price'] * (1 - self.params.get("stop_pct", 5.0)/100)
            
            exit_signals = (time_exit | stop_exit).astype(int)
        
        return exit_signals
    
    def position_sizing(self, data):
        """
        Full allocation position sizing
        """
        return pd.Series(1, index=data.index)
    
    def risk_management(self, data):
        """
        Apply stop-loss and time-based exit rules
        """
        # Risk management is already implemented in generate_signals
        return data
    
    def preprocess_data(self, data, context=None):
        """
        Preprocess input data before signal generation
        """
        data = super().preprocess_data(data, context)
        
        # Ensure required columns are present and properly named
        if 'close' in data.columns and 'Close' not in data.columns:
            data['Close'] = data['close']
        if 'open' in data.columns and 'Open' not in data.columns:
            data['Open'] = data['open']
        if 'high' in data.columns and 'High' not in data.columns:
            data['High'] = data['high']
        if 'low' in data.columns and 'Low' not in data.columns:
            data['Low'] = data['low']
        if 'volume' in data.columns and 'Volume' not in data.columns:
            data['Volume'] = data['volume']
            
        return data