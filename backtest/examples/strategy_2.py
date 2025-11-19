import pandas as pd
import numpy as np

class ModelAStratgy(Strategy):
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
            pd.Series: Series of entry signals (1, -1, or 0).
        """
        return data["Signal"]

    def exit_rules(self, data):
        """
        Define conditions for exiting trades.
        Supports holding periods, trailing stops, custom exit logic.
        
        Args:
            data (pd.DataFrame): Strategy data.
        
        Returns:
            pd.Series: Series of exit signals (1=exit, 0=hold).
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

class HighBreakoutHoldStrategy(Strategy):
    """
    Strategy that buys stocks when they close above 52-week high,
    holds for 20 days or exits with 5% stop loss.
    """
    
    def __init__(self, params=None, data_config=None):
        super().__init__(params, data_config)
        # Set default parameters
        self.params = {
            "lookback_period": 252,  # 52 weeks for 52-week high
            "holding_period": 20,
            "stop_loss_pct": 0.05,
            "start_date": "2024-10-28",
            "end_date": "2025-10-28"
        }
        if params:
            self.params.update(params)
    
    def description(self):
        return "Buy stocks when they close above 52-week high, hold for 20 days or exit with 5% stop loss"
    
    def parameter_schema(self):
        return {
            "lookback_period": {"type": "int", "min": 50, "max": 500, "default": 252, 
                               "description": "Lookback period for calculating high (trading days)"},
            "holding_period": {"type": "int", "min": 1, "max": 100, "default": 20,
                              "description": "Maximum holding period in days"},
            "stop_loss_pct": {"type": "float", "min": 0.01, "max": 0.20, "default": 0.05,
                             "description": "Stop loss percentage from entry price"},
            "start_date": {"type": "string", "default": "2024-10-28",
                          "description": "Strategy start date"},
            "end_date": {"type": "string", "default": "2025-10-28",
                        "description": "Strategy end date"}
        }
    
    def generate_signals(self, data, context=None):
        """
        Generate signals based on 52-week high breakout strategy.
        """
        # Make a copy to avoid modifying original data
        data = data.copy()
        
        # Filter data for backtest period
        start_date = pd.to_datetime(self.params["start_date"])
        end_date = pd.to_datetime(self.params["end_date"])
        
        if "Date" in data.columns:
            mask = (data["Date"] >= start_date) & (data["Date"] <= end_date)
            data = data[mask].copy()
        
        # Calculate 52-week high (rolling maximum of High)
        lookback = self.params["lookback_period"]
        data['52_week_high'] = data['High'].rolling(window=lookback, min_periods=1).max()
        
        # Initialize signal column
        data['Signal'] = 0
        
        # Identify breakout signals (close above 52-week high)
        breakout_condition = data['Close'] > data['52_week_high'].shift(1)
        
        # Buy on next day after breakout
        data['Breakout_Signal'] = breakout_condition.shift(1).fillna(False)
        
        # Initialize tracking columns for position management
        data['Entry_Price'] = np.nan
        data['Days_Held'] = 0
        data['Active_Position'] = False
        data['Stop_Price'] = np.nan
        
        current_position = False
        entry_price = 0
        days_held = 0
        stop_price = 0
        
        # Iterate through data to manage positions
        for i in range(len(data)):
            current_price = data['Close'].iloc[i]
            
            if not current_position and data['Breakout_Signal'].iloc[i]:
                # Enter new position
                data.loc[data.index[i], 'Signal'] = 1
                data.loc[data.index[i], 'Entry_Price'] = current_price
                data.loc[data.index[i], 'Active_Position'] = True
                data.loc[data.index[i], 'Stop_Price'] = current_price * (1 - self.params["stop_loss_pct"])
                
                current_position = True
                entry_price = current_price
                days_held = 1
                stop_price = entry_price * (1 - self.params["stop_loss_pct"])
                
            elif current_position:
                # Check exit conditions
                stop_loss_hit = current_price <= stop_price
                holding_period_over = days_held >= self.params["holding_period"]
                
                if stop_loss_hit or holding_period_over:
                    # Exit position
                    data.loc[data.index[i], 'Signal'] = -1
                    current_position = False
                    days_held = 0
                else:
                    # Continue holding
                    data.loc[data.index[i], 'Signal'] = 0
                    data.loc[data.index[i], 'Active_Position'] = True
                    data.loc[data.index[i], 'Days_Held'] = days_held
                    data.loc[data.index[i], 'Entry_Price'] = entry_price
                    data.loc[data.index[i], 'Stop_Price'] = stop_price
                    days_held += 1
            else:
                # No position
                data.loc[data.index[i], 'Signal'] = 0
        
        # Fill NaN values in signal column
        data['Signal'] = data['Signal'].fillna(0)
        
        self.signals = data
        return data
    
    def position_sizing(self, data):
        """
        Use equal position sizing for each trade.
        """
        return pd.Series(1, index=data.index)
    
    def risk_management(self, data):
        """
        Apply stop loss logic - already implemented in generate_signals.
        """
        return data
    
    def exit_rules(self, data):
        """
        Exit rules are handled in generate_signals.
        Returns exit signals (1 for exit, 0 for hold).
        """
        if 'Signal' not in data.columns:
            return pd.Series(0, index=data.index)
        
        # Exit signals are where Signal == -1
        exit_signals = (data['Signal'] == -1).astype(int)
        return exit_signals