import pandas as pd
import numpy as np

class VolatilityRegimeAdaptiveMeanReversionStrategy(Strategy):
    """
    Mean reversion strategy adapting to volatility regimes with dynamic position sizing.
    """

    def __init__(self, params=None, data_config=None):
        """
        Initialize the strategy with parameters and data configuration.
        Args:
            params (dict): Dictionary of strategy parameters.
            data_config (dict): Dictionary containing dataset info.
        """
        super().__init__(params, data_config)
        self.params = {
            "window": 10,
            "threshold_low_vol": -1.5,
            "threshold_high_vol": -2.5,
            "threshold_low": -2,
            "threshold_high": 2,
            "holding_period_low_vol": 5,
            "holding_period_high_vol": 2,
            "ATR_window": 14,
            "position_size_low_vol": 1,
            "position_size_high_vol": 0.5,
            "risk_pct": 0.05,
        }
        self.params.update(params or {})

    def description(self):
        """
        Text description of what the strategy does.
        """
        return "Mean reversion strategy adapting to volatility regimes with dynamic position sizing."

    def parameter_schema(self):
        """
        Define the parameters with metadata (for no-code UI).
        """
        return {
            "window": {"type": "int", "min": 5, "max": 200, "default": 10},
            "threshold_low_vol": {"type": "float", "min": -5, "max": 0, "default": -1.5},
            "threshold_high_vol": {"type": "float", "min": -5, "max": 0, "default": -2.5},
            "threshold_low": {"type": "float", "min": -5, "max": 5, "default": -2},
            "threshold_high": {"type": "float", "min": -5, "max": 5, "default": 2},
            "holding_period_low_vol": {"type": "int", "min": 1, "max": 30, "default": 5},
            "holding_period_high_vol": {"type": "int", "min": 1, "max": 30, "default": 2},
            "ATR_window": {"type": "int", "min": 5, "max": 200, "default": 14},
            "position_size_low_vol": {"type": "float", "min": 0.1, "max": 2, "default": 1},
            "position_size_high_vol": {"type": "float", "min": 0.1, "max": 2, "default": 0.5},
            "risk_pct": {"type": "float", "min": 0.01, "max": 0.1, "default": 0.05},
        }

    def generate_signals(self, data, context=None):
        """
        Core strategy logic: generate trading signals.
        """
        # Calculate z-score of price deviation from 10-day SMA
        data["SMA"] = data["Close"].rolling(window=self.params["window"]).mean()
        data["Price_Deviation"] = data["Close"] - data["SMA"]
        data["Z_Score"] = data["Price_Deviation"] / data["Price_Deviation"].rolling(window=self.params["window"]).std()

        # Generate signals based on z-score
        data["Signal"] = 0
        data.loc[data["Z_Score"] < self.params["threshold_low_vol"], "Signal"] = 1
        data.loc[data["Z_Score"] > self.params["threshold_high_vol"], "Signal"] = -1

        # Apply holding period
        data["Holding_Period"] = 0
        data.loc[data["Signal"] == 1, "Holding_Period"] = self.params["holding_period_low_vol"]
        data.loc[data["Signal"] == -1, "Holding_Period"] = self.params["holding_period_high_vol"]

        # Apply exit rules
        data["Exit_Signal"] = 0
        data.loc[data["Z_Score"].crossing(0), "Exit_Signal"] = 1
        data.loc[data["Holding_Period"] == 0, "Exit_Signal"] = 1

        return data

    def position_sizing(self, data):
        """
        Define how much to allocate per trade.
        """
        # Calculate ATR
        data["High_Low"] = data["High"] - data["Low"]
        data["High_Close"] = np.abs(data["High"] - data["Close"].shift(1))
        data["Low_Close"] = np.abs(data["Low"] - data["Close"].shift(1))
        data["TR"] = data[["High_Low", "High_Close", "Low_Close"]].max(axis=1)
        data["ATR"] = data["TR"].rolling(window=self.params["ATR_window"]).mean()

        # Calculate position size
        data["Position_Size"] = 0
        data.loc[data["Signal"] == 1, "Position_Size"] = self.params["position_size_low_vol"]
        data.loc[data["Signal"] == -1, "Position_Size"] = self.params["position_size_high_vol"]

        # Apply risk management
        data["Risk"] = data["ATR"] * self.params["risk_pct"]
        data["Position_Size"] = data["Position_Size"] * data["Risk"]

        return data

    def risk_management(self, data):
        """
        Apply stop-loss, take-profit, or max drawdown rules.
        """
        # Apply stop-loss
        data["Stop_Loss"] = data["Close"] - data["ATR"] * 1.5

        return data

# Example usage
if __name__ == "__main__":
    strategy = VolatilityRegimeAdaptiveMeanReversionStrategy()
    data_config = {
        "path": "data/INFY.csv",
        "format": "csv",
        "columns": ["Date", "Open", "High", "Low", "Close", "Volume"],
        "date_col": "Date",
        "freq": "1D"
    }
    strategy.data_config = data_config
    data = strategy.load_data()
    data = strategy.preprocess_data(data)
    signals = strategy.generate_signals(data)
    positions = strategy.position_sizing(signals)
    risk_managed = strategy.risk_management(positions)
    print(risk_managed.head())