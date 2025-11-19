#!/usr/bin/env python3
"""
Simple Demo: How to backtest an LLM-generated strategy with MBVC data

This demonstrates plug-and-play backtesting with any strat2.py format strategy
"""

import pandas as pd
import numpy as np
import sys
import os
import importlib.util
from pathlib import Path
from datetime import datetime

# Try to import tqdm for progress bars
try:
    from tqdm import tqdm as _tqdm
    TQDM_AVAILABLE = True
    tqdm = _tqdm
except ImportError:
    TQDM_AVAILABLE = False
    # Create a dummy tqdm function that just returns the iterable
    tqdm = lambda *args, **kwargs: args[0] if args else iter

# Add paths
backtest_dir = Path(__file__).parent
sys.path.insert(0, str(backtest_dir))

# Import
# Change this to import your strategy:
from examples.strat7 import ModelAStrategy
from core.backtest_engine import BacktestEngine

def load_mbvc_sample():
    """Load sample MBVC 2018 data"""
    # Load data from project root
    data_path = Path(__file__).parent.parent / 'data' / '2018_1daydata' / 'INFY.parquet'
    
    # Load INFY parquet file directly
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    print(f"Loading data from: {data_path}")
    df = pd.read_parquet(data_path)
    
    # Combine
    combined = df.copy()
    
    # Normalize column names
    col_map = {}
    for old, new in [('Date', 'date'), ('Datetime', 'date'), ('datetime', 'date'),
                     ('StockName', 'symbol'), 
                     ('Open', 'open'), ('High', 'high'), ('Low', 'low'), 
                     ('Close', 'close'), ('Volume', 'volume')]:
        if old in combined.columns:
            col_map[old] = new
    
    combined = combined.rename(columns=col_map)
    
    # Add symbol column if it doesn't exist
    if 'symbol' not in combined.columns:
        combined['symbol'] = 'INFY'
    
    # Sort by date if exists
    if 'date' in combined.columns:
        combined = combined.sort_values('date').reset_index(drop=True)
    
    return combined

def demo():
    print("="*70)
    print("🚀 LLM STRATEGY PLUG-AND-PLAY BACKTESTING DEMO")
    print("="*70)
    
    
    print("-" * 70)
    strategy_class = ModelAStrategy
    strategy = strategy_class()
    #print(f"✅ Loaded: {strategy.description()}")
    print(f"📊 Parameters: {list(strategy.parameter_schema().keys())}")
    
    print("\n2️⃣ Load MBVC 2018 daily data")
    print("-" * 70)
    market_data = load_mbvc_sample()
    print(f"✅ Loaded {len(market_data):,} rows from MBVC")
    print(f"   Columns: {list(market_data.columns)}")
    
    # Find date column
    date_col = None
    for col in ['date', 'Date', 'Datetime']:
        if col in market_data.columns:
            date_col = col
            break
    
    if date_col:
        print(f"   Date range: {market_data[date_col].min()} to {market_data[date_col].max()}")
    
    # Find symbol column
    symbol_col = None
    for col in ['symbol', 'StockName', 'Symbol']:
        if col in market_data.columns:
            symbol_col = col
            break
    
    if symbol_col:
        print(f"   Symbols: {market_data[symbol_col].nunique()}")
    
    # Pick a symbol
    symbol = 'INFY'
    symbol_data = market_data[market_data['symbol'] == symbol].copy()
    print(f"\n   Selected: {symbol} with {len(symbol_data)} trading days")
    
    print("\n3️⃣ Run Backtest")
    print("-" * 70)
    
    engine = BacktestEngine(initial_capital=100000)
    
    # Create output directory
    output_dir = Path(__file__).parent.parent / 'output' / f'{symbol}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    result = engine.run_backtest(
        strategy_class=strategy_class,
        strategy_name="ModelAStrategy",
        data=symbol_data.copy(),
        params=None,
        save_outputs={'output_dir': str(output_dir), 'symbol': symbol}
    )
    
    print("\n4️⃣ Results")
    print("-" * 70)
    if result.get('status') == 'PASSED':
        print(f"✅ Signals: {result['total_signals']}")
        print(f"📈 Win Rate: {result['win_rate']:.1%}")
        print(f"💰 Return: {result['total_return']:.1%}")
        print(f"📉 Max Drawdown: {result['max_drawdown']:.1%}")
        print(f"📊 Sharpe: {result['sharpe_ratio']:.2f}")
        if 'cagr' in result:
            print(f"📅 CAGR: {result['cagr']:.1%}")
        print(f"\n📁 Output saved to: {output_dir}")
    else:
        print(f"❌ Error: {result.get('error')}")
    
    print("\n" + "="*70)
    
    return result

if __name__ == "__main__":
    demo()
