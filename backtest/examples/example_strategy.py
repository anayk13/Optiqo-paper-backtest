import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))

# Import the Strategy base class
from strat2_base import Strategy

class ModelAStrategy(Strategy):
    """
    Intermediate Trend-Following Strategy using Long-only Simple Moving Average (SMA) Crossover
    """

    def __init__(self, params=None):
        super().__init__(params)
        self.params = params or {
            "short_window": 20,
            "long_window": 50,
            "risk_pct": 0.01,
            "profit_target": 0.05,
            "stoploss": 0.04
        }

    def description(self):
        """
        Text description of what the strategy does.
        """
        return "Intermediate Trend-Following Strategy using Long-only Simple Moving Average (SMA) Crossover"

    def parameter_schema(self):
        """
        Defines the parameters with metadata.
        """
        return {
            "short_window": {"type": "int", "min": 5, "max": 200, "default": 20},
            "long_window": {"type": "int", "min": 5, "max": 200, "default": 50},
            "risk_pct": {"type": "float", "min": 0.001, "max": 0.1, "default": 0.01},
            "profit_target": {"type": "float", "min": 0.01, "max": 0.1, "default": 0.05},
            "stoploss": {"type": "float", "min": 0.01, "max": 0.1, "default": 0.04}
        }

    def preprocess_data(self, data):
        """
        Clean and prepare the data for signal generation.
        """
        # Normalize column names (handle both lowercase and capitalized)
        if 'Close' in data.columns and 'close' not in data.columns:
            data['close'] = data['Close']
        if 'Open' in data.columns and 'open' not in data.columns:
            data['open'] = data['Open']
        if 'High' in data.columns and 'high' not in data.columns:
            data['high'] = data['High']
        if 'Low' in data.columns and 'low' not in data.columns:
            data['low'] = data['Low']
        if 'Volume' in data.columns and 'volume' not in data.columns:
            data['volume'] = data['Volume']
            
        # Ensure date column exists
        if 'date' not in data.columns and 'Date' in data.columns:
            data['date'] = data['Date']
            
        return data
    
    def generate_signals(self, data):
        """
        Core strategy logic: generate trading signals.
        """
        short_window = self.params["short_window"]
        long_window = self.params["long_window"]

        # Calculate SMAs - use lowercase 'close' now
        data = data.copy()
        data["SMA_short"] = data["close"].rolling(window=short_window).mean()
        data["SMA_long"] = data["close"].rolling(window=long_window).mean()

        # Generate signals
        data["Signal"] = 0
        # Golden cross: buy when short crosses above long
        data.loc[(data["SMA_short"] > data["SMA_long"]) & (data["SMA_short"].shift(1) <= data["SMA_long"].shift(1)), "Signal"] = 1
        # Death cross: sell when short crosses below long
        data.loc[(data["SMA_short"] < data["SMA_long"]) & (data["SMA_short"].shift(1) >= data["SMA_long"].shift(1)), "Signal"] = -1

        return data[["Signal"]]

    def position_sizing(self, data):
        """
        Define how much to allocate per trade.
        """
        risk_pct = self.params["risk_pct"]
        return pd.Series(risk_pct, index=data.index)

    def risk_management(self, data):
        """
        Apply stop-loss, take-profit rules.
        """
        profit_target = self.params["profit_target"]
        stoploss = self.params["stoploss"]

        # Ensure 'close' column exists (use lowercase)
        close_col = 'close' if 'close' in data.columns else 'Close'
        
        # Calculate stop-loss and take-profit prices
        data["Stoploss"] = data[close_col] * (1 - stoploss)
        data["Takeprofit"] = data[close_col] * (1 + profit_target)

        return data

# Example usage
if __name__ == "__main__":
    strategy = ModelAStrategy()
    print("Strategy:", strategy.description())
    print("\nParameter Schema:")
    for param, info in strategy.parameter_schema().items():
        print(f"  {param}: {info}")
    
    print("\n✅ Example Strategy ready to plug-and-play with backtesting engine!")