# 📊 Backtest Output Flow & Structure

## 🔄 **Complete Flow: Input → Process → Output**

### **1️⃣ INPUT**
- **Strategy File**: `backtest/examples/your_strategy.py`
- **Market Data**: `data/2018_1daydata/` (parquet files)
- **Configuration**: `backtest/config/backtest_config.yaml`

### **2️⃣ PROCESS (Step-by-Step)**

#### **Step 1: Load Data**
- Reads parquet files from `data/2018_1daydata/`
- Normalizes column names (Close→close, Date→date)
- Filters data for selected symbol
- Combines all monthly data

#### **Step 2: Preprocess Data** (Your strategy)
- Calls `strategy.preprocess_data(data)`
- You can normalize columns, handle missing data
- Returns cleaned data

#### **Step 3: Generate Signals** (Your strategy)
- Calls `strategy.generate_signals(data)`
- You implement your trading logic
- Returns DataFrame with 'Signal' column:
  - `1` = Buy signal
  - `-1` = Sell signal
  - `0` = Hold/No action

#### **Step 4: Calculate Metrics**
- Counts total signals
- Calculates win rate (if trades executed)
- Computes total return, max drawdown, Sharpe ratio
- Calculates CAGR (Compound Annual Growth Rate)

#### **Step 5: Save Outputs**
- Creates unique output folder: `output/{symbol}_{timestamp}/`
- Saves all files (see below)

### **3️⃣ OUTPUT - Files Generated**

After running `python backtest/run_backtest.py`, results are saved to:

```
output/
└── {symbol}_{timestamp}/     ← e.g., ARE&M_20251027_184150
    ├── signals_full.csv      ← All signals (including 0s)
    ├── signals_nonzero.csv   ← Only buy/sell events (1/-1)
    ├── signals_enriched.csv  ← Signals + technical indicators
    ├── signals.parquet       ← All signals (Parquet format)
    ├── prepared_data.parquet ← Cleaned market data
    └── metrics.json          ← Performance metrics
```

#### **File Contents:**

**1. signals_full.csv**
```
date,Signal
2018-01-01,0
2018-01-02,0
2018-01-03,1    ← Buy signal
2018-01-04,0
2018-01-05,-1   ← Sell signal
```

**2. signals_nonzero.csv** (Only events)
```
date,Signal
2018-01-03,1
2018-01-05,-1
```

**3. signals_enriched.csv** (Includes indicators)
```
date,open,high,low,close,volume,rsi,ema20,ema50,macd_hist,vol_ratio,52w_high,Signal
2018-01-03,100,105,99,103,1000000,65.5,101.2,99.8,0.5,1.2,110,1
```

**4. metrics.json**
```json
{
  "total_signals": 10,
  "win_rate": 0.75,
  "total_return": 0.15,
  "max_drawdown": 0.05,
  "sharpe_ratio": 1.2,
  "buy_signals": 5,
  "sell_signals": 5,
  "hold_signals": 238
}
```

## 📍 **Where to Find Results**

**Output Location**: 
```bash
output/{symbol}_{timestamp}/
```

**Example**: 
```bash
output/ARE&M_20251027_184150/
```

**View Files**:
```bash
# View signals
cat output/*/signals_nonzero.csv

# View metrics
cat output/*/metrics.json

# List all outputs
ls -lh output/
```

## 🔍 **Understanding the Flow**

1. **Signals Generated First** - Your strategy's `generate_signals()` runs
2. **Metrics Calculated Next** - Engine analyzes signals vs price data
3. **Files Saved Last** - All outputs written to timestamped folder

## 💡 **Signal Meanings**

- **Signal = 1**: Buy/Enter position
- **Signal = -1**: Sell/Exit position  
- **Signal = 0**: Hold current position or do nothing

Most strategies only generate signals when conditions are met, so you'll typically see many 0s and a few 1s/-1s.

