import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from strat2_base import Strategy

class ModelAStrategy(Strategy):
    
    def __init__(self, params=None, data_config=None):
        self.params = params or {}
        self.data_config = data_config or {}
        self.signals = None
        self.trades = None
        self.data = None
        self.context = None

    def load_data(self):
        path = self.data_config["path"]
        format_type = self.data_config.get("format", "csv")
        date_col = self.data_config.get("date_column", "date")
        
        if format_type == "csv":
            data = pd.read_csv(path)
        elif format_type == "parquet":
            data = pd.read_parquet(path)
        elif format_type == "excel":
            data = pd.read_excel(path)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
        
        data[date_col] = pd.to_datetime(data[date_col])
        data = data.sort_values(date_col)
        self.data = data
        return data

    def validate_data(self, data):
        required = ["open", "high", "low", "close"]
        missing = [col for col in required if col not in data.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        return True

    def data_summary(self):
        if self.data is None:
            return "No data loaded."
        
        date_col = self.data_config.get("date_column", "date")
        return {
            "rows": len(self.data),
            "columns": len(self.data.columns),
            "start_date": self.data[date_col].min(),
            "end_date": self.data[date_col].max(),
            "format": self.data_config.get("format", "csv")
        }

    def attach_context(self, context_dict):
        self.context = context_dict

    def preprocess_data(self, data, context=None):
        data = data.drop_duplicates()
        data = data.ffill().bfill()
        data["returns"] = data["close"].pct_change()
        if "volume" in data.columns:
            data["volume_norm"] = (data["volume"] - data["volume"].mean()) / data["volume"].std()
        return data

    def generate_signals(self, data, context=None):
        sma_fast = self.params.get('sma_fast', 20)
        sma_slow = self.params.get('sma_slow', 50)
        data['sma_fast'] = data['close'].rolling(sma_fast).mean()
        data['sma_slow'] = data['close'].rolling(sma_slow).mean()
        data['signal'] = 0
        crossover_above = (data['sma_fast'] > data['sma_slow']) & (data['sma_fast'].shift(1) <= data['sma_slow'].shift(1))
        data.loc[crossover_above, 'signal'] = 1
        data['signal'] = data['signal'].fillna(0)
        return data

    def entry_rules(self, data):
        entry = data['signal'].copy()
        time_filter = data.index.time == pd.to_datetime('09:15').time()
        entry = entry.where(time_filter, 0)
        return entry

    def exit_rules(self, data):
        sma_fast = data['close'].rolling(20).mean()
        sma_slow = data['close'].rolling(50).mean()
        exit_signal = (sma_fast < sma_slow) & (sma_fast.shift(1) >= sma_slow.shift(1))
        return exit_signal.astype(int)

    def position_sizing(self, data):
        sizing_type = self.params['position_sizing']['type']
        if sizing_type == 'equal_weight':
            return pd.Series(1.0, index=data.index)
        elif sizing_type == 'percent_risk':
            capital = self.params['capital']['initial_capital']
            risk_pct = self.params['position_sizing']['params']['risk_pct']
            stop_pct = self.params.get('stop_loss_pct', 0.02)
            return (capital * risk_pct) / stop_pct / data['close']
        elif sizing_type == 'volatility_scaled':
            base_size = self.params['position_sizing']['params'].get('base_size', 1.0)
            avg_atr = data['atr'].mean()
            return base_size * (avg_atr / data['atr'])
        elif sizing_type == 'kelly':
            p = self.params['position_sizing']['params']['win_prob']
            b = self.params['position_sizing']['params']['win_loss_ratio']
            q = 1 - p
            return (p * b - q) / b
        elif sizing_type == 'fixed_capital':
            fixed_amount = self.params['position_sizing']['params']['fixed_amount']
            return fixed_amount / data['close']
        return pd.Series(1.0, index=data.index)

    def risk_management(self, data):
        stop_loss_pct = self.params.get('stop_loss_pct')
        take_profit_pct = self.params.get('take_profit_pct')
        if stop_loss_pct is None and take_profit_pct is None:
            return data
        entry_price = None
        for i in range(len(data)):
            if data['signal'].iloc[i] != 0 and entry_price is None:
                entry_price = data['close'].iloc[i]
            if entry_price is not None:
                current_price = data['close'].iloc[i]
                if stop_loss_pct and current_price <= entry_price * (1 - stop_loss_pct):
                    data.loc[data.index[i], 'signal'] = 0
                    entry_price = None
                elif take_profit_pct and current_price >= entry_price * (1 + take_profit_pct):
                    data.loc[data.index[i], 'signal'] = 0
                    entry_price = None
        return data

    def description(self):
        return "Long-only SMA Crossover strategy for Infosys using SMA(20) crossing above SMA(50) for entry and SMA(20) crossing below SMA(50) for exit"

    def parameter_schema(self):
        return {
            "sma_fast": {"type": "int", "min": 5, "max": 50, "default": 20},
            "sma_slow": {"type": "int", "min": 20, "max": 200, "default": 50}
        }

    def parameters(self):
        return self.params

    def run_backtest(self, signals):
        return signals