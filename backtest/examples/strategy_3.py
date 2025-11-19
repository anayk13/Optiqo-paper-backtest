import pandas as pd
import numpy as np

class BollingerBandSMA_CrossoverStrategy(Strategy):
    """
    Buy stock on gap up after closing above weekly Bollinger Band, 
    sell on close below daily SMA 200.
    """

    def __init__(self, params=None, data_config=None):
        super().__init__(params, data_config)
        self.params = {
            "bollinger_band_length": 50,
            "bollinger_band_timeframe": "weekly",
            "sma_length": 200,
            "sma_timeframe": "daily"
        }

    def description(self):
        """
        Text description of what the strategy does.
        """
        return "Buy stock on gap up after closing above weekly Bollinger Band, sell on close below daily SMA 200."

    def parameter_schema(self):
        """
        Define the parameters with metadata (for no-code UI).
        """
        return {
            "bollinger_band_length": {"type": "int", "min": 10, "max": 200, "default": 50},
            "bollinger_band_timeframe": {"type": "str", "options": ["daily", "weekly"], "default": "weekly"},
            "sma_length": {"type": "int", "min": 10, "max": 200, "default": 200},
            "sma_timeframe": {"type": "str", "options": ["daily", "weekly"], "default": "daily"}
        }

    def generate_signals(self, data, context=None):
        """
        Core strategy logic: generate trading signals.
        """
        # Calculate weekly Bollinger Band
        data["weekly_close"] = data["Close"].resample("W").last()
        data["weekly_bollinger_band"] = data["weekly_close"].rolling(window=self.params["bollinger_band_length"]).mean() + 2 * data["weekly_close"].rolling(window=self.params["bollinger_band_length"]).std()

        # Calculate daily SMA
        data["daily_sma"] = data["Close"].rolling(window=self.params["sma_length"]).mean()

        # Generate entry signals
        data["entry_signal"] = 0
        data.loc[(data["Close"] > data["weekly_bollinger_band"]) & (data["Open"] > data["Close"].shift(1)), "entry_signal"] = 1

        # Generate exit signals
        data["exit_signal"] = 0
        data.loc[data["Close"] < data["daily_sma"], "exit_signal"] = -1

        # Combine entry and exit signals
        data["Signal"] = data["entry_signal"] - data["exit_signal"]

        return data

    def position_sizing(self, data):
        """
        Define how much to allocate per trade.
        """
        return pd.Series(1, index=data.index)

    def risk_management(self, data):
        """
        Apply stop-loss, take-profit, or max drawdown rules.
        """
        return data

# Example usage
if __name__ == "__main__":
    strategy = BollingerBandSMA_CrossoverStrategy()
    data_config = {
        "path": "data/stock_data.csv",
        "format": "csv",
        "columns": ["Date", "Open", "High", "Low", "Close", "Volume"],
        "date_col": "Date"
    }
    strategy.data_config = data_config
    data = strategy.load_data()
    data = strategy.preprocess_data(data)
    signals = strategy.generate_signals(data)
    print(signals.head())