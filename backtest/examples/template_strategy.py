"""
Template for creating your own strategy in strat2_base format

1. Copy this file and rename it (e.g., my_strategy.py)
2. Implement the generate_signals method with your trading logic
3. Add any other optional methods you need
4. Import it in run_backtest.py
"""

import pandas as pd
import numpy as np
from strat2_base import Strategy


class YourStrategy(Strategy):
    """
    Your strategy description here
    """
    
    def __init__(self, params=None):
        super().__init__(params)
        # Set your default parameters
        self.params = params or {
            "param1": 20,
            "param2": 50
        }
    
    def description(self):
        """
        Text description of what the strategy does.
        """
        return "Your strategy description here"
    
    def parameter_schema(self):
        """
        Defines the parameters with metadata.
        """
        return {
            "param1": {"type": "int", "min": 5, "max": 200, "default": 20},
            "param2": {"type": "int", "min": 5, "max": 200, "default": 50}
        }
    
    def preprocess_data(self, data):
        """
        Optional: Clean and prepare the data for signal generation.
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
        
        Returns:
            DataFrame with 'Signal' column where:
            - 1  = Buy/Enter position
            - -1 = Sell/Exit position
            - 0  = Hold/Do nothing
        """
        # Get your parameters
        param1 = self.params["param1"]
        param2 = self.params["param2"]
        
        # Copy data to avoid modifying original
        data = data.copy()
        
        # Calculate indicators (example)
        data["indicator1"] = data["close"].rolling(window=param1).mean()
        data["indicator2"] = data["close"].rolling(window=param2).mean()
        
        # Initialize signals
        data["Signal"] = 0
        
        # Your trading logic here
        # Example: Buy when indicator1 crosses above indicator2
        data.loc[data["indicator1"] > data["indicator2"], "Signal"] = 1
        
        # Example: Sell when indicator1 crosses below indicator2
        data.loc[data["indicator1"] < data["indicator2"], "Signal"] = -1
        
        return data[["Signal"]]
    
    def position_sizing(self, data):
        """
        Optional: Define how much to allocate per trade.
        """
        # Default position size (1.0 = 100% of capital per trade)
        return pd.Series(1.0, index=data.index)
    
    def risk_management(self, data):
        """
        Optional: Apply stop-loss, take-profit rules.
        """
        # Calculate stop-loss and take-profit prices
        if 'close' in data.columns:
            data["Stoploss"] = data["close"] * 0.95  # 5% stop loss
            data["Takeprofit"] = data["close"] * 1.05  # 5% take profit
        return data


# Example usage
if __name__ == "__main__":
    strategy = YourStrategy()
    print("Strategy:", strategy.description())
    print("\nParameter Schema:")
    for param, info in strategy.parameter_schema().items():
        print(f"  {param}: {info}")

