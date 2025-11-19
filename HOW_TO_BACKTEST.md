# 🚀 How to Backtest Your Strategy (strat2_base.py Format)

This guide shows you how to backtest any trading strategy written in the `strat2_base.py` format.

## 📋 **Prerequisites**

1. Strategy code in `strat2_base.py` format
2. Market data (parquet files with OHLCV columns)
3. Python packages installed (see `requirements.txt`)

## 🎯 **Quick Start**

### **Step 1: Prepare Your Strategy**

Your strategy must inherit from `Strategy` class and implement these methods:

```python
from strat2_base import Strategy
import pandas as pd

class YourStrategy(Strategy):
    def generate_signals(self, data):
        """
        Your trading logic here.
        Must return DataFrame with 'Signal' column.
        
        Signal values:
        - 1  = Buy/Enter position
        - -1 = Sell/Exit position
        - 0  = Hold/Do nothing
        """
        # Example: Simple SMA crossover
        data = data.copy()
        data['SMA_short'] = data['close'].rolling(20).mean()
        data['SMA_long'] = data['close'].rolling(50).mean()
        
        # Generate signals
        data['Signal'] = 0
        # Buy when short crosses above long
        data.loc[data['SMA_short'] > data['SMA_long'], 'Signal'] = 1
        # Sell when short crosses below long
        data.loc[data['SMA_short'] < data['SMA_long'], 'Signal'] = -1
        
        return data[['Signal']]
    
    def preprocess_data(self, data):
        """Optional: Clean and prepare your data"""
        # Normalize column names if needed
        if 'Close' in data.columns:
            data['close'] = data['Close']
        return data
    
    def description(self):
        return "Your strategy description"
    
    def parameter_schema(self):
        return {
            "param1": {"type": "int", "min": 5, "max": 100, "default": 20}
        }
```

### **Step 2: Save Your Strategy**

Save your strategy to: `backtest/examples/your_strategy.py`

### **Step 3: Update the Import**

Edit `backtest/run_backtest.py` line 20:

```python
# Change this:
from examples.example_strategy import ModelAStrategy

# To this:
from examples.your_strategy import YourStrategy
```

Also update line 70:

```python
strategy_class = YourStrategy  # Your strategy class
```

### **Step 4: Configure Data Path**

Edit `backtest/run_backtest.py` line 33:

```python
# Update this path to your data location
data_path = Path(__file__).parent.parent / 'data' / '2018_1daydata'
```

Your data should be organized as:
```
data/
└── 2018_1daydata/
    ├── 1/
    │   ├── file1.parquet
    │   └── file2.parquet
    ├── 2/
    │   └── ...
    └── ...
```

### **Step 5: Run the Backtest**

```bash
cd backtest
python run_backtest.py
```

## 📊 **What You'll See**

### **Console Output**
```
======================================================================
🚀 LLM STRATEGY PLUG-AND-PLAY BACKTESTING DEMO
======================================================================

1️⃣ Load LLM Strategy
----------------------------------------------------------------------
✅ Loaded: Your Strategy Description
📊 Parameters: ['param1', 'param2']

2️⃣ Load Market Data
----------------------------------------------------------------------
Loading data: 100%|██████████| 6/6 [00:01<00:00]
✅ Loaded 165,328 rows
   Date range: 2018-01-01 to 2018-06-29
   Symbols: 1370
   Selected: SYMBOL with 248 trading days

3️⃣ Run Backtest
----------------------------------------------------------------------
✅ Strategy initialized successfully
✅ Signal generation completed

4️⃣ Results
----------------------------------------------------------------------
✅ Signals: 10
📈 Win Rate: 60.0%
💰 Return: 15.5%
📉 Max Drawdown: 3.2%
📊 Sharpe: 1.8

📁 Output saved to: output/SYMBOL_20251027_184150
```

### **Output Files**

Results are saved to: `output/{symbol}_{timestamp}/`

```
output/SYMBOL_20251027_184150/
├── signals_full.csv       ← All signals (0s, 1s, -1s)
├── signals_nonzero.csv    ← Only buy/sell events
├── signals_enriched.csv   ← Signals + technical indicators
├── signals.parquet        ← Signals (Parquet format)
├── prepared_data.parquet  ← Cleaned market data
└── metrics.json           ← Performance metrics
```

## 📁 **Required File Structure**

### **Strategy Format**

Your strategy file must have:

1. **Import the base class:**
   ```python
   from strat2_base import Strategy
   ```

2. **Create your strategy class:**
   ```python
   class YourStrategy(Strategy):
       def __init__(self, params=None):
           super().__init__(params)
           self.params = params or {
               "param1": 20,
               "param2": 50
           }
   ```

3. **Required methods:**
   - `generate_signals(data)` - Must return DataFrame with 'Signal' column
   - `description()` - Returns string description
   - `parameter_schema()` - Returns dict of parameters

4. **Optional methods:**
   - `preprocess_data(data)` - Clean data before signal generation
   - `position_sizing(data)` - Define position sizes
   - `risk_management(data)` - Stop-loss, take-profit rules

### **Data Format**

Your market data must have these columns:

```python
# Required
- date (or Date, Datetime)
- open (or Open)
- high (or High)
- low (or Low)
- close (or Close)
- volume (or Volume)

# Optional
- symbol (or StockName, Symbol)
```

## ⚙️ **Advanced Configuration**

### **Backtest Multiple Symbols**

Edit `backtest/run_backtest.py` line 103:

```python
# Single symbol
symbol = 'RELIANCE'

# Or loop through multiple
symbols = ['RELIANCE', 'TCS', 'INFY']
for symbol in symbols:
    symbol_data = market_data[market_data['symbol'] == symbol].copy()
    # Run backtest for each symbol
```

### **Override Parameters**

Edit the run_backtest call:

```python
result = engine.run_backtest(
    strategy_class=YourStrategy,
    strategy_name="Your Strategy Name",
    data=symbol_data,
    params={
        'param1': 30,  # Override default
        'param2': 60
    }
)
```

### **Change Output Directory**

Edit `backtest/run_backtest.py` line 112:

```python
output_dir = Path('/path/to/your/output') / f'{symbol}_{timestamp}'
```

## 🔍 **Understanding Signals**

### **Signal Values**

- **`1`** (Buy): Enter long position
- **`-1`** (Sell): Exit position / Enter short
- **`0`** (Hold): No action

### **Example Signal Generation**

```python
def generate_signals(self, data):
    # Simple moving average crossover
    data['SMA20'] = data['close'].rolling(20).mean()
    data['SMA50'] = data['close'].rolling(50).mean()
    
    data['Signal'] = 0  # Initialize
    
    # Buy when 20-day crosses above 50-day
    data.loc[data['SMA20'] > data['SMA50'], 'Signal'] = 1
    
    # Sell when 20-day crosses below 50-day
    data.loc[data['SMA20'] < data['SMA50'], 'Signal'] = -1
    
    return data[['Signal']]
```

## 🐛 **Troubleshooting**

### **No Signals Generated**

- Check if you have enough data points (some strategies need 50-200 days)
- Verify your logic conditions are being met
- Look at `signals_full.csv` - are all values 0?

### **Import Error**

```python
# Make sure you update the import path
from examples.your_strategy import YourStrategy
```

### **Data Format Issues**

The engine auto-normalizes these column names:
- `Close` → `close`
- `Date` → `date`
- `StockName` → `symbol`

### **Module Not Found Error**

Make sure your strategy file is in:
```
backtest/examples/your_strategy.py
```

## 📚 **Example: Complete Strategy**

See `backtest/examples/example_strategy.py` for a working example with:
- Preprocessing (column normalization)
- Signal generation (SMA crossover)
- Risk management (stop-loss, take-profit)
- Position sizing

## 🎯 **Summary**

1. Write your strategy inheriting from `Strategy`
2. Save to `backtest/examples/`
3. Update imports in `run_backtest.py`
4. Run: `cd backtest && python run_backtest.py`
5. Check results in `output/` folder

That's it! Your strategy is now backtesting. 🚀

