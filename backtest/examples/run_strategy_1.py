#!/usr/bin/env python3
"""
Standalone runner for strategy_1.py (ModelAStrategy)
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path
from datetime import datetime

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))

# Import strategy and engine
from strategy_1 import ModelAStrategy
from backtest_engine import BacktestEngine

def main():
    print("="*70)
    print("🚀 RUNNING MODEL A STRATEGY (Strategy_1)")
    print("="*70)
    
    # Load INFY data
    print("\n📊 Loading INFY data...")
    data_path = Path(__file__).parent.parent.parent / 'data' / '2018_1daydata' / 'INFY.parquet'
    df = pd.read_parquet(data_path)
    
    # Normalize column names
    col_map = {
        'datetime': 'date',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume'
    }
    for old, new in col_map.items():
        if old in df.columns:
            df[new] = df[old]
    
    # Sort by date
    if 'date' in df.columns:
        df = df.sort_values('date').reset_index(drop=True)
    
    # Add symbol if not present
    if 'symbol' not in df.columns:
        df['symbol'] = 'INFY'
    
    print(f"✅ Loaded {len(df):,} rows from INFY.parquet")
    print(f"   Date range: {df['date'].min()} to {df['date'].max()}")
    
    # Initialize strategy
    print("\n🤖 Initializing ModelAStrategy...")
    strategy = ModelAStrategy()
    
    # Initialize engine
    engine = BacktestEngine(initial_capital=100000)
    
    # Create output directory
    output_dir = Path(__file__).parent.parent.parent / 'output' / f'MODELA_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n🔄 Running backtest...")
    
    # Run backtest
    result = engine.run_backtest(
        strategy_class=ModelAStrategy,
        strategy_name="ModelAStrategy",
        data=df,
        params=None,
        save_outputs={'output_dir': str(output_dir), 'symbol': 'INFY'}
    )
    
    # Display results
    print("\n" + "="*70)
    print("📈 RESULTS")
    print("="*70)
    
    if result.get('status') == 'PASSED':
        print(f"✅ Total Signals: {result['total_signals']}")
        print(f"📈 Win Rate: {result['win_rate']:.2%}")
        print(f"💰 Total Return: {result['total_return']:.2%}")
        print(f"📉 Max Drawdown: {result['max_drawdown']:.2%}")
        print(f"📊 Sharpe Ratio: {result['sharpe_ratio']:.2f}")
        if 'cagr' in result:
            print(f"📅 CAGR: {result['cagr']:.2%}")
        print(f"\n📁 Output saved to: {output_dir}")
    else:
        print(f"❌ Error: {result.get('error')}")
    
    print("="*70)

if __name__ == "__main__":
    main()

