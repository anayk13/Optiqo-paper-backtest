"""
Simple Template Strategy for Backtesting

Just copy-paste your strategy code here and it will work!

1. Edit this file
2. Implement your logic in generate_signals()
3. Update the import in run_backtest.py (line 20)
4. Run: cd backtest && python run_backtest.py
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))

# Import base class
from strat2_base import Strategy


class MyStrategy(Strategy):
    """
    Intermediate Trend-Following Strategy using Long-only Simple Moving Average (SMA) Crossover
    """

    def __init__(self, params=None, data_config=None):
        """
        Initialize the strategy with parameters and data configuration.
        Args:
            params (dict): Dictionary of strategy parameters.
            data_config (dict): Dictionary containing dataset info.
        """
        super().__init__(params, data_config)
        self.strategy_name = "Model A"
        # Don't set self.description here, use description() method instead
        self.instrument_type = "equity"
        self.assets = "INFY.NS"
        self.data_frequency = "1D"
        self.timezone = "Asia/Kolkata"
        self.start_date = "2018-01-01"
        self.end_date = "2024-12-31"
        self.price_columns = ["Close"]
        self.execution = {
            "order_on": "next_candle_open",
            "default_order_type": "Market",
            "brokerage_pct": 0.0001,
            "slippage_pct": 0.0005
        }
        self.entry_rules = [
            {
                "id": "entry_1",
                "type": "indicator",
                "indicator": "SMA Crossover",
                "params": {
                    "short_window": 20,
                    "long_window": 50
                },
                "logic": "SMA(20) crosses above SMA(50) at 9:15 am"
            }
        ]
        self.exit_rules = [
            {
                "id": "exit_1",
                "type": "indicator",
                "indicator": "SMA Crossover",
                "params": {
                    "short_window": 20,
                    "long_window": 50
                },
                "logic": "SMA(20) crosses below SMA(50)"
            }
        ]
        self.position_sizing_config = {
            "type": "percent_risk",
            "params": {
                "risk_pct": 0.01
            }
        }
        self.leverage = {
            "allowed": True,
            "max": 1
        }
        self.capital = {
            "currency": "INR",
            "initial_capital": 1000000
        }
        self.max_simultaneous_positions = None
        self.shorting_allowed = False
        self.lot_size = 1
        self.confidence = 0.9
        self.profit_target = "5%"
        self.stoploss = "4%"

    def description(self):
        """
        Text description of what the strategy does.
        Useful for UI or LLM explanations.
        """
        return "Intermediate Trend-Following Strategy using Long-only Simple Moving Average (SMA) Crossover"

    def parameter_schema(self):
        """
        Define the parameters with metadata (for no-code UI).
        
        Returns:
            dict: Example format:
                {
                    "lookback": {"type": "int", "min": 5, "max": 200, "default": 20},
                    "threshold": {"type": "float", "min": 0.1, "max": 5.0, "default": 2.0}
                }
        """
        return {
            "short_window": {"type": "int", "min": 5, "max": 200, "default": 20},
            "long_window": {"type": "int", "min": 5, "max": 200, "default": 50},
            "risk_pct": {"type": "float", "min": 0.001, "max": 0.1, "default": 0.01}
        }

    def generate_signals(self, data, context=None):
        """
        Core strategy logic: generate trading signals.
        
        Args:
            data (pd.DataFrame): Input OHLCV (and optionally other features).
            context (dict, optional): Additional datasets (pairs, options, ML predictions).
        
        Returns:
            pd.DataFrame: Must include a 'Signal' column 
                          (1=long, -1=short, 0=flat, or fractional weights).
        """
        # Calculate short and long window SMAs
        data['SMA_short'] = data['close'].rolling(window=self.entry_rules[0]['params']['short_window']).mean()
        data['SMA_long'] = data['close'].rolling(window=self.entry_rules[0]['params']['long_window']).mean()

        # Generate signals based on SMA crossover
        data['Signal'] = 0
        data.loc[(data['SMA_short'] > data['SMA_long']) & (data['SMA_short'].shift(1) <= data['SMA_long'].shift(1)), 'Signal'] = 1
        data.loc[(data['SMA_short'] < data['SMA_long']) & (data['SMA_short'].shift(1) >= data['SMA_long'].shift(1)), 'Signal'] = -1

        return data

    def position_sizing(self, data):
        """
        Define how much to allocate per trade.
        Default is equal sizing (1 unit).
        
        Args:
            data (pd.DataFrame): Strategy data.
        
        Returns:
            pd.Series: Position sizes per timestamp.
        """
        # Calculate position size based on percent risk
        risk_pct = self.position_sizing_config['params']['risk_pct']
        position_size = (risk_pct * self.capital['initial_capital']) / (data['close'] * self.lot_size)
        return pd.Series(position_size, index=data.index)

    def risk_management(self, data):
        """
        Apply stop-loss, take-profit, or max drawdown rules.
        Override for custom risk logic.
        
        Args:
            data (pd.DataFrame): Strategy data.
        
        Returns:
            pd.DataFrame: Adjusted data after applying risk management.
        """
        # Apply stop-loss and take-profit
        stoploss_pct = float(self.stoploss.strip('%')) / 100
        take_profit_pct = float(self.profit_target.strip('%')) / 100
        data['StopLoss'] = data['close'] * (1 - stoploss_pct)
        data['TakeProfit'] = data['close'] * (1 + take_profit_pct)
        return data

    def load_data(self):
        """
        Load dataset based on the data_config settings.
        Supports CSV, Parquet, and Excel formats.
        """
        path = f"data/{self.assets}.csv"
        fmt = "csv"
        data = pd.read_csv(path)
        date_col = "Date"
        data[date_col] = pd.to_datetime(data[date_col])
        data = data.sort_values(by=date_col)
        self.data = data
        return data

    def validate_data(self, data):
        """
        Validate dataset integrity and required columns.
        """
        required_cols = ["Open", "High", "Low", "Close"]
        missing = [c for c in required_cols if c not in data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        return True

    def preprocess_data(self, data, context=None):
        """
        Preprocess input data before signal generation.
        Can handle missing values, normalization, resampling, 
        feature engineering, etc.
        
        Args:
            data (pd.DataFrame): Input OHLCV or feature data.
            context (dict, optional): Extra datasets or metadata.
        
        Returns:
            pd.DataFrame: Preprocessed data.
        """
        data = data.drop_duplicates()
        data = data.ffill().bfill()
        return data

# Example usage
if __name__ == "__main__":
    strategy = ModelAStrategy()
    data = strategy.load_data()
    data = strategy.preprocess_data(data)
    signals = strategy.generate_signals(data)
    positions = strategy.position_sizing(data)
    risk_managed_data = strategy.risk_management(data)
    print(signals.head())
    print(positions.head())
    print(risk_managed_data.head())