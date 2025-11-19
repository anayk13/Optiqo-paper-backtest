# ➕ How to Add Your Strategy

## 📝 **Step-by-Step Guide**

### **Option 1: Copy Template (Easiest)**

1. **Copy the template:**
   ```bash
   cp backtest/examples/template_strategy.py backtest/examples/my_strategy.py
   ```

2. **Edit `my_strategy.py`:**
   - Change class name: `YourStrategy` → `MyStrategy`
   - Update `description()` method
   - Update `parameter_schema()` with your parameters
   - **Most importantly:** Implement `generate_signals()` with your logic

3. **Update `run_backtest.py`:**
   ```python
   # Line 20: Change import
   from examples.my_strategy import MyStrategy
   
   # Line 70: Change class
   strategy_class = MyStrategy
   ```

4. **Run:**
   ```bash
   cd backtest
   python run_backtest.py
   ```

---

### **Option 2: Create New File Manually**

1. **Create new file:**
   ```bash
   touch backtest/examples/your_strategy.py
   ```

2. **Write your strategy:**
   ```python
   from strat2_base import Strategy
   import pandas as pd
   
   class YourStrategy(Strategy):
       def generate_signals(self, data):
           # Your logic here
           data['Signal'] = 0
           # ... your conditions ...
           return data[['Signal']]
   
       def description(self):
           return "Your strategy description"
   
       def parameter_schema(self):
           return {
               "param1": {"type": "int", "min": 5, "max": 200, "default": 20}
           }
   ```

3. **Import in `run_backtest.py`:**
   ```python
   from examples.your_strategy import YourStrategy
   strategy_class = YourStrategy
   ```

---

## 🎯 **Where Files Go**

```
backtest/
├── examples/
│   ├── template_strategy.py   ← Copy this
│   ├── example_strategy.py     ← SMA example
│   └── your_strategy.py        ← Your strategy here
├── core/
│   ├── backtest_engine.py     ← Engine (don't touch)
│   └── strat2_base.py          ← Base class (don't touch)
└── run_backtest.py             ← Main script (edit imports)
```

---

## ⚠️ **Important Notes**

### **DO NOT use `llm_strategy_example.py`**
- It’s for the old paper trading engine (`main.py`)
- It uses `EnhancedBaseStrategy`
- Not compatible with backtesting

### **DO use `template_strategy.py`**
- Starts from `Strategy` (strat2_base)
- Backtesting compatible
- Simple and plug-and-play

---

## 🔍 **What is `llm_strategy_example.py`?**

This file is for the production paper trading engine, not for backtesting.

- **Purpose:** Run strategies live with real portfolio tracking
- **Uses:** `EnhancedBaseStrategy` (event-driven)
- **Used by:** `main.py` and `production_main.py`
- **Not for:** Backtesting

### **When to use each:**

| File | Purpose | When to Use |
|------|---------|-------------|
| `template_strategy.py` | Backtesting template | ✅ Use for backtesting |
| `example_strategy.py` | Backtesting example | ✅ Use for reference |
| `llm_strategy_example.py` | Live trading | ❌ Not for backtesting |

---

## 📝 **Quick Comparison**

### **Template Strategy (for backtesting):**
```python
from strat2_base import Strategy  # ← Correct for backtesting

class YourStrategy(Strategy):
    def generate_signals(self, data):
        # Return DataFrame with Signal column
        return data[['Signal']]
```

### **LLM Example (for live trading):**
```python
from strategies.enhanced_base_strategy import EnhancedBaseStrategy  # ← Wrong for backtesting

class LLMMomentumStrategy(EnhancedBaseStrategy):
    def generate_signals(self, data, context=None):
        # Different format
```

---

## 🚀 **Example: Adding a Simple Momentum Strategy**

1. **Create file:** `backtest/examples/momentum_strategy.py`

```python
from strat2_base import Strategy
import pandas as pd
import numpy as np

class MomentumStrategy(Strategy):
    def __init__(self, params=None):
        super().__init__(params)
        self.params = params or {
            "lookback": 20,
            "momentum_threshold": 0.02
        }
    
    def description(self):
        return "Simple momentum strategy - buy when price momentum is strong"
    
    def parameter_schema(self):
        return {
            "lookback": {"type": "int", "min": 5, "max": 50, "default": 20},
            "momentum_threshold": {"type": "float", "min": 0.01, "max": 0.1, "default": 0.02}
        }
    
    def generate_signals(self, data):
        data = data.copy()
        lookback = self.params["lookback"]
        threshold = self.params["momentum_threshold"]
        
        # Calculate momentum
        momentum = (data["close"] / data["close"].shift(lookback) - 1)
        
        # Generate signals
        data["Signal"] = 0
        data.loc[momentum > threshold, "Signal"] = 1  # Buy
        data.loc[momentum < -threshold, "Signal"] = -1  # Sell
        
        return data[["Signal"]]
```

2. **Update `run_backtest.py` line 20:**
```python
from examples.momentum_strategy import MomentumStrategy
```

3. **Update line 70:**
```python
strategy_class = MomentumStrategy
```

4. **Run:**
```bash
cd backtest && python run_backtest.py
```

---

## ✅ **Summary**

- ❌ **Don't** add strategies to `llm_strategy_example.py`
- ✅ **Do** create new files in `backtest/examples/`
- ✅ **Do** copy `template_strategy.py` as a starting point
- ✅ **Do** update imports in `run_backtest.py`

**Simple flow:**
1. Copy template → `your_strategy.py`
2. Edit `generate_signals()`
3. Update `run_backtest.py` imports
4. Run!

