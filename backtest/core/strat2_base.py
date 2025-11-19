import pandas as pd
import numpy as np

class Strategy:
    """
    Base class for all strategies.
    Every custom strategy should inherit from this and override
    specific methods where necessary.
    """

    def __init__(self, params=None, data_config=None):
        """
        Initialize the strategy with parameters and data configuration.
        Args:
            params (dict): Dictionary of strategy parameters.
            data_config (dict): Dictionary containing dataset info.
                Example:
                    {
                        "path": "data/stock_data.csv",
                        "format": "csv",
                        "columns": ["Date", "Open", "High", "Low", "Close", "Volume"],
                        "date_col": "Date",
                        "symbol_col": "Symbol",
                        "freq": "1D"
                    }
        """
        self.params = params or {}
        self.data_config = data_config or {}
        self.signals = None
        self.trades = None
        self.data = None
        self.context = None

    # ----------------------------------------------------------------------
    # DATA HANDLING SECTION
    # ----------------------------------------------------------------------
    def load_data(self):
        """
        Load dataset based on the data_config settings.
        Supports CSV, Parquet, and Excel formats.
        """
        path = self.data_config.get("path")
        fmt = self.data_config.get("format", "csv").lower()

        if path is None:
            raise ValueError("Dataset path not provided in data_config.")

        if fmt == "csv":
            data = pd.read_csv(path)
        elif fmt == "parquet":
            data = pd.read_parquet(path)
        elif fmt == "excel":
            data = pd.read_excel(path)
        else:
            raise ValueError(f"Unsupported file format: {fmt}")

        # Convert date column
        date_col = self.data_config.get("date_col", "Date")
        if date_col in data.columns:
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

        if "Volume" in data.columns:
            data["Volume_norm"] = (data["Volume"] - data["Volume"].mean()) / data["Volume"].std()

        if "Close" in data.columns:
            data["Returns"] = data["Close"].pct_change()

        return data

    def data_summary(self):
        """
        Summarize loaded data for debugging or logging.
        """
        if self.data is None:
            return "No data loaded."

        date_col = self.data_config.get("date_col", "Date")
        return {
            "rows": len(self.data),
            "columns": list(self.data.columns),
            "start_date": str(self.data[date_col].min()) if date_col in self.data.columns else "N/A",
            "end_date": str(self.data[date_col].max()) if date_col in self.data.columns else "N/A",
            "format": self.data_config.get("format", "csv")
        }

    def attach_context(self, context_dict):
        """
        Attach additional contextual datasets (e.g., macro, sentiment, predictions).
        """
        self.context = context_dict

    # ----------------------------------------------------------------------
    # STRATEGY SECTION
    # ----------------------------------------------------------------------
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
        raise NotImplementedError

    def description(self):
        """
        Text description of what the strategy does.
        Useful for UI or LLM explanations.
        """
        raise NotImplementedError

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
        return {}

    def entry_rules(self, data):
        """
        Define conditions for entering trades.
        By default, uses 'Signal' values directly.
        
        Args:
            data (pd.DataFrame): Data with 'Signal' column.
        
        Returns:
            pd.Series OR dict: 
                - If Series: Entry signals (1, -1, or 0). Uses default execution prices.
                - If dict: {
                    'signals': pd.Series of entry signals,
                    'price_col': str, column name for execution price (default: 'open'),
                    'shift': int, bars to shift (-1=next bar, 0=current bar, default: -1)
                  }
        """
        return data["Signal"]

    def exit_rules(self, data):
        """
        Define conditions for exiting trades.
        Supports holding periods, trailing stops, custom exit logic.
        
        Args:
            data (pd.DataFrame): Strategy data.
        
        Returns:
            pd.Series OR dict:
                - If Series: Exit signals (1=exit, 0=hold). Uses default execution prices.
                - If dict: {
                    'signals': pd.Series of exit signals,
                    'price_col': str, column name for execution price (default: 'open'),
                    'shift': int, bars to shift (-1=next bar, 0=current bar, default: -1)
                  }
        """
        return pd.Series(0, index=data.index)

    def position_sizing(self, data):
        """
        Define how much to allocate per trade.
        Default is equal sizing (1 unit).
        
        Args:
            data (pd.DataFrame): Strategy data.
        
        Returns:
            pd.Series: Position sizes per timestamp.
        """
        return pd.Series(1, index=data.index)

    def risk_management(self, data):
        """
        Apply stop-loss, take-profit, or max drawdown rules.
        Override for custom risk logic.
        
        Args:
            data (pd.DataFrame): Strategy data.
        
        Returns:
            pd.DataFrame: Adjusted data after applying risk management.
        """
        return data

    def parameters(self):
        """
        Return the current parameter dictionary.
        
        Returns:
            dict: Strategy parameters.
        """
        return self.params
    
    def run_backtest(self, signals):
        """
        Run backtest on generated signals.
        Must call generate_signals() first.
        
        Returns:
            pd.DataFrame: Portfolio performance over time.
        """
        return signals
