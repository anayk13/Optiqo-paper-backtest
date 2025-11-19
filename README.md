# Optiqo Paper Trading & Backtesting Engine

A comprehensive event-driven paper trading and backtesting engine for algorithmic trading strategies.

## 🚀 Features

### Backtesting System
- **Offline Strategy Testing**: Test strategies on historical data before going live
- **Signal Normalization**: Automatically handles both uppercase `Signal` and lowercase `signal` columns
- **Portfolio Simulation**: Realistic trading simulation with position sizing, cash management, and execution delays
- **Comprehensive Metrics**: Total return, CAGR, Sharpe ratio, max drawdown, win rate, and more
- **Multiple Output Formats**: Parquet, CSV, and JSON outputs for analysis

### Live Trading Engine
- **Event-Driven Architecture**: MarketEvent, SignalEvent, OrderEvent, FillEvent
- **Simulated Broker**: Paper trading with realistic order execution
- **Portfolio Management**: Real-time position tracking, P&L calculation
- **Risk Management**: Pre-trade risk checks and position limits
- **Multi-Strategy Support**: Run multiple strategies simultaneously
- **Live Data Feed**: Real-time market data integration

## 📁 Project Structure

```
├── backtest/               # Backtesting system
│   ├── core/              # Backtest engine
│   ├── examples/          # Example strategies
│   └── run_backtest.py    # Main backtest runner
├── engine/                # Live trading engine
│   ├── broker.py          # Simulated broker
│   ├── event_engine.py    # Event-driven core
│   ├── portfolio.py       # Portfolio manager
│   ├── risk_manager.py    # Risk management
│   └── trade_executor.py  # Order execution
├── strategies/            # Production strategies
├── config/               # Configuration files
├── data/                 # Historical data
└── output/              # Backtest results
```

## 🔧 Quick Start

### Backtesting

```bash
# Run a backtest
python backtest/run_backtest.py
```

### Live Trading (Paper)

```bash
# Run live paper trading
python production_main.py
```

## 📊 Current Status

**Backtest System**: ✅ Active and tested
- Signal normalization: Fixed
- Portfolio simulation: Working
- Metrics calculation: Verified

**Live Trading System**: 🟡 Ready but not running
- All components implemented
- Configuration files ready
- Last tested: June 2025

## 🔍 Recent Improvements

1. **Signal Column Normalization** (Nov 2024)
   - Automatically handles both `Signal` and `signal` column names
   - No more case-sensitivity errors
   - Backward compatible with existing strategies

2. **Enhanced Backtesting**
   - Portfolio-based metrics (not just signal-based)
   - Realistic position sizing
   - Next-bar execution simulation

## 📖 Documentation

- [HOW_TO_BACKTEST.md](HOW_TO_BACKTEST.md) - Complete backtesting guide
- [ADD_YOUR_STRATEGY.md](ADD_YOUR_STRATEGY.md) - How to create strategies
- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) - System design details
- [OUTPUT_FLOW.md](OUTPUT_FLOW.md) - Understanding outputs

## 🛠️ Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## ⚙️ Configuration

- `config/production_config.yaml` - Live trading settings
- `config/strategy_config.yaml` - Strategy parameters
- `backtest/config/backtest_config.yaml` - Backtest settings

## 📈 Data

Historical data in `data/2018_1daydata/` includes:
- 252 stocks
- Daily OHLCV data
- 2003-2025 date range

## 🤝 Contributing

Strategies should follow the `strat2_base.Strategy` interface with:
- `generate_signals()` - Generate buy/sell signals
- `entry_rules()` - Entry timing/filters
- `exit_rules()` - Exit conditions
- `position_sizing()` - Position size calculation

## 📝 License

See repository license file.

## 🔗 Repository

https://github.com/anayk13/Optiqo-paper-backtest.git

