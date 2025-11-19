#!/usr/bin/env python3
"""
Dedicated Backtesting Engine for strat2.py Format Strategies
"""

import pandas as pd
import numpy as np
import os
import sys
import importlib
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path
import warnings
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = lambda x, **kwargs: x
warnings.filterwarnings('ignore')

class BacktestEngine:
    """
    Backtesting engine specifically designed for strat2.py format strategies
    """
    
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.results = {}
        
    def generate_test_data(self, days=500, start_price=100, trend='uptrend', volatility=0.02, symbol='TEST'):
        """Generate synthetic test data with various patterns"""
        np.random.seed(42)  # For reproducible results
        
        dates = pd.date_range(start='2023-01-01', periods=days, freq='D')
        
        if trend == 'uptrend':
            # Create uptrend with some pullbacks
            trend_component = np.linspace(0, 0.3, days)  # 30% uptrend over period
        elif trend == 'downtrend':
            # Create downtrend with some rallies
            trend_component = np.linspace(0, -0.2, days)  # 20% downtrend over period
        else:  # sideways
            # Create sideways movement
            trend_component = np.linspace(0, 0.05, days)  # 5% slight uptrend
        
        # Add some cyclical patterns
        cycle1 = 0.1 * np.sin(2 * np.pi * np.arange(days) / 50)  # 50-day cycle
        cycle2 = 0.05 * np.sin(2 * np.pi * np.arange(days) / 20)  # 20-day cycle
        
        # Generate random noise
        noise = np.random.normal(0, volatility, days)
        
        # Combine all components
        log_returns = trend_component/days + cycle1/days + cycle2/days + noise
        
        # Convert to prices
        prices = start_price * np.exp(np.cumsum(log_returns))
        
        # Generate OHLCV data
        data = pd.DataFrame({
            'date': dates,
            'symbol': symbol,
            'open': prices * (1 + np.random.normal(0, 0.005, days)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.01, days))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.01, days))),
            'close': prices,
            'volume': np.random.randint(100000, 1000000, days)
        })
        
        # Ensure high >= max(open, close) and low <= min(open, close)
        data['high'] = np.maximum(data['high'], np.maximum(data['open'], data['close']))
        data['low'] = np.minimum(data['low'], np.minimum(data['open'], data['close']))
        
        return data
    
    def generate_pairs_data(self, days=500):
        """Generate synthetic pairs data for pairs trading strategy"""
        np.random.seed(42)
        
        dates = pd.date_range(start='2023-01-01', periods=days, freq='D')
        
        # Create two correlated but mean-reverting series
        base_trend = np.linspace(0, 0.2, days)
        common_factor = np.random.normal(0, 0.02, days)
        
        # Stock A
        stock_a_trend = base_trend + 0.3 * common_factor + np.random.normal(0, 0.015, days)
        stock_a_prices = 100 * np.exp(np.cumsum(stock_a_trend))
        
        # Stock B (correlated but with some divergence)
        stock_b_trend = base_trend + 0.7 * common_factor + np.random.normal(0, 0.012, days)
        stock_b_prices = 95 * np.exp(np.cumsum(stock_b_trend))
        
        data = pd.DataFrame({
            'date': dates,
            'stock_a_close': stock_a_prices,
            'stock_b_close': stock_b_prices,
            'stock_a_volume': np.random.randint(50000, 500000, days),
            'stock_b_volume': np.random.randint(40000, 400000, days)
        })
        
        return data
    
    def run_backtest(self, strategy_class, strategy_name, data, params=None, save_outputs=None):
        """
        Run backtest on a single strategy
        
        Args:
            strategy_class: The strategy class to test
            strategy_name: Name of the strategy
            data: Test data
            params: Strategy parameters
            
        Returns:
            dict: Backtest results
        """
        print(f"\n{'='*60}")
        print(f"BACKTESTING: {strategy_name}")
        print(f"{'='*60}")
        
        try:
            # Initialize strategy
            strategy = strategy_class(params)
            print(f"✅ Strategy initialized successfully")

            # Attempt preprocessing with robust column normalization
            processed_data = None
            preprocess_errors = []

            # 1) Try as-is
            try:
                processed_data = strategy.preprocess_data(data.copy())
            except Exception as e1:
                preprocess_errors.append(e1)
            
            # 2) Try lowercase-normalized schema
            if processed_data is None:
                try:
                    normalized_lower = self._normalize_columns(data.copy(), variant="lower")
                    processed_data = strategy.preprocess_data(normalized_lower)
                except Exception as e2:
                    preprocess_errors.append(e2)

            # 3) Try capitalized-normalized schema (for strategies expecting 'Datetime','Open',...)
            if processed_data is None:
                try:
                    normalized_caps = self._normalize_columns(data.copy(), variant="capitalized")
                    processed_data = strategy.preprocess_data(normalized_caps)
                except Exception as e3:
                    preprocess_errors.append(e3)

            if processed_data is None:
                raise RuntimeError(f"Preprocess failed under all normalization attempts: {[str(e) for e in preprocess_errors][:2]} ...")

            print(f"✅ Data preprocessing completed. Shape: {processed_data.shape}")

            # Generate signals with safety net
            signals_df = None
            try:
                signals_df = strategy.generate_signals(processed_data)
            except Exception as e4:
                # As a fallback, if the strategy still relies on a different naming, try alternate normalization once more
                try:
                    alt_processed = self._normalize_columns(processed_data.copy(), variant="lower")
                    signals_df = strategy.generate_signals(alt_processed)
                    processed_data = alt_processed
                except Exception:
                    raise e4

            # Normalize Signal column name (handle both 'Signal' and 'signal')
            if 'Signal' not in signals_df.columns:
                if 'signal' in signals_df.columns:
                    signals_df = signals_df.rename(columns={'signal': 'Signal'})
                    print(f"ℹ️  Normalized 'signal' → 'Signal' column")
                else:
                    print(f"❌ Strategy did not generate 'Signal' or 'signal' column")
                    print(f"   Available columns: {list(signals_df.columns)}")
                    return {'status': 'FAILED', 'error': 'No Signal column generated'}

            signals = signals_df['Signal']
            print(f"✅ Signal generation completed. Shape: {signals_df.shape}")

            # Calculate performance metrics (signal-based)
            results = self.calculate_performance_metrics(signals, processed_data)

            # Optionally persist outputs (signals, prepared data, metrics)
            if save_outputs and isinstance(save_outputs, dict):
                try:
                    out_dir = save_outputs.get('output_dir')
                    symbol = save_outputs.get('symbol')
                    if out_dir:
                        Path(out_dir).mkdir(parents=True, exist_ok=True)
                        # Save signals - keep ALL columns from signals_df (including SMA indicators, etc.)
                        if 'date' in signals_df.columns:
                            sig_df = signals_df.copy()
                        else:
                            # Fallback if no date column in signals_df
                            sig_df = pd.DataFrame({'date': processed_data.get('date', pd.RangeIndex(len(signals))), 'Signal': signals}).reset_index(drop=True)
                        sig_path = Path(out_dir) / 'signals.parquet'
                        sig_df.to_parquet(sig_path, index=False)
                        # Also save CSVs for easy viewing
                        (Path(out_dir) / 'signals_full.csv').write_text(sig_df.to_csv(index=False))
                        nonzero = sig_df[sig_df['Signal'] != 0]
                        (Path(out_dir) / 'signals_nonzero.csv').write_text(nonzero.to_csv(index=False))
                        # Save prepared data (raw OHLCV only, no MBVC enrichment)
                        data_cols = [c for c in ['date','symbol','open','high','low','close','volume'] if c in processed_data.columns]
                        prep = processed_data[data_cols].copy()
                        prep_path = Path(out_dir) / 'prepared_data.parquet'
                        prep.to_parquet(prep_path, index=False)

                        # Create enriched CSV with JUST the strategy's own indicators
                        # Merge signals_df (which contains strategy's own columns like SMA_short, SMA_long)
                        # with prepared data
                        enriched_with_signal = pd.merge(prep, sig_df, on='date', how='left', suffixes=('', '_y'))
                        
                        # Event-only export for convenience (only non-zero signals)
                        events_only = enriched_with_signal[enriched_with_signal['Signal'] != 0].copy()
                        
                        # Remove duplicate columns from merge (keep only non-suffixed version)
                        events_only = events_only[[c for c in events_only.columns if not c.endswith('_y')]]
                        
                        enr_path = Path(out_dir) / 'signals_enriched.csv'
                        events_only.to_csv(enr_path, index=False)
                        
                        # Generate paired trades (one row per complete buy/sell trade)
                        paired_trades = self._pair_signals_into_trades(enriched_with_signal)
                        if len(paired_trades) > 0:
                            paired_path = Path(out_dir) / 'paired_trades.csv'
                            paired_trades.to_csv(paired_path, index=False)

                        # Portfolio simulation with sizing (next-bar execution)
                        try:
                            trades_with_size, portfolio_transactions_df, equity_curve, portfolio_metrics = self._simulate_portfolio_with_sizing(
                                prepared_df=prep,
                                signals_df=sig_df,
                                strategy=strategy,
                                initial_capital=self.initial_capital
                            )

                            # Save sized trades and equity curve
                            (Path(out_dir) / 'trades_with_size.csv').write_text(trades_with_size.to_csv(index=False))
                            equity_curve_path = Path(out_dir) / 'equity_curve.parquet'
                            equity_curve.to_parquet(equity_curve_path, index=False)
                            
                            # Save detailed portfolio transactions
                            if len(portfolio_transactions_df) > 0:
                                trans_path = Path(out_dir) / 'portfolio_transactions.csv'
                                portfolio_transactions_df.to_csv(trans_path, index=False)
                            
                            # Generate portfolio summary
                            final_cash = equity_curve['cash'].iloc[-1] if len(equity_curve) > 0 else self.initial_capital
                            final_shares = equity_curve['shares'].iloc[-1] if len(equity_curve) > 0 else 0
                            final_equity = equity_curve['equity'].iloc[-1] if len(equity_curve) > 0 else self.initial_capital
                            total_pnl = final_equity - self.initial_capital
                            
                            portfolio_summary = {
                                'initial_capital': float(self.initial_capital),
                                'final_cash': float(final_cash),
                                'final_shares': int(final_shares),
                                'final_equity': float(final_equity),
                                'total_pnl': float(total_pnl),
                                'total_return_pct': float((total_pnl / self.initial_capital) * 100) if self.initial_capital > 0 else 0,
                                'total_trades': len(trades_with_size),
                                'winning_trades': len(trades_with_size[trades_with_size['pnl'] > 0]) if len(trades_with_size) > 0 and 'pnl' in trades_with_size.columns else 0,
                                'losing_trades': len(trades_with_size[trades_with_size['pnl'] < 0]) if len(trades_with_size) > 0 and 'pnl' in trades_with_size.columns else 0
                            }
                            
                            summary_path = Path(out_dir) / 'portfolio_summary.json'
                            with open(summary_path, 'w') as f:
                                json.dump(portfolio_summary, f, indent=2)

                            # Merge portfolio metrics into results (prefixed)
                            for k, v in portfolio_metrics.items():
                                results[f'portfolio_{k}'] = v
                        except Exception as sim_err:
                            print(f"⚠️ Portfolio simulator failed: {sim_err}")
                            print(traceback.format_exc())
                        
                        # Save metrics
                        met_path = Path(out_dir) / 'metrics.json'
                        # Convert numpy types to native
                        serializable = {k: (float(v) if hasattr(v, 'item') else v) for k,v in results.items() if k not in ('strategy_description','parameter_schema')}
                        with open(met_path, 'w') as f:
                            json.dump({**serializable, 'strategy_name': strategy_name, 'symbol': symbol}, f, indent=2)
                except Exception as _:
                    # Do not fail run on save errors
                    pass

            # Add strategy-specific information
            results['strategy_name'] = strategy_name
            results['strategy_description'] = strategy.description()
            results['parameter_schema'] = strategy.parameter_schema()
            results['status'] = 'PASSED'

            print(f"✅ Backtest completed successfully!")
            print(f"   Total Signals: {results['total_signals']}")
            print(f"   Win Rate: {results['win_rate']:.2%}")
            print(f"   Total Return: {results['total_return']:.2%}")
            print(f"   Max Drawdown: {results['max_drawdown']:.2%}")
            print(f"   Sharpe Ratio: {results['sharpe_ratio']:.2f}")

            return results

        except Exception as e:
            error_msg = f"Error in {strategy_name}: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")
            return {
                'status': 'FAILED',
                'error': error_msg,
                'strategy_name': strategy_name
            }
    
    def calculate_performance_metrics(self, signals, data):
        """Calculate comprehensive performance metrics"""
        # Check if there are any nonzero signals (1 or -1)
        nonzero_signals = (signals != 0).sum()
        if len(signals) == 0 or nonzero_signals == 0:
            return {
                'total_signals': 0,
                'win_rate': 0,
                'total_return': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'avg_trade_duration': 0,
                'buy_signals': 0,
                'sell_signals': 0
            }
        
        # Get price data
        if 'close' in data.columns:
            prices = data['close']
        else:
            # Try to find a price column
            price_cols = [col for col in data.columns if 'close' in col.lower() or 'price' in col.lower()]
            if price_cols:
                prices = data[price_cols[0]]
            else:
                prices = data.iloc[:, 1]  # Assume second column is price
        
        # Calculate returns (assume daily)
        returns = prices.pct_change().fillna(0)
        
        # Calculate strategy returns
        strategy_returns = signals.shift(1) * returns
        
        # Basic metrics
        total_signals = int(abs(signals).sum())
        total_return = strategy_returns.sum()
        
        # Win rate
        winning_trades = (strategy_returns > 0).sum()
        win_rate = winning_trades / total_signals if total_signals > 0 else 0
        
        # Drawdown
        cumulative_returns = (1 + strategy_returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Annualization helpers (daily assumption ~252 days)
        trading_days = 252
        ann_factor = np.sqrt(trading_days)
        # Sharpe ratio (annualized)
        sharpe_ratio = 0
        if strategy_returns.std() > 0:
            sharpe_ratio = (strategy_returns.mean() * trading_days) / (strategy_returns.std() * ann_factor)

        # CAGR (approx from cumulative returns over period length)
        n_days = max(len(strategy_returns), 1)
        if n_days > 0:
            ending = (1 + strategy_returns).prod()
            years = max(n_days / trading_days, 1e-9)
            cagr = ending ** (1/years) - 1
        else:
            cagr = 0

        # Annualized volatility
        ann_vol = strategy_returns.std() * ann_factor if strategy_returns.std() > 0 else 0
        
        # Average trade duration
        trade_durations = []
        in_trade = False
        trade_start = 0
        
        for i, signal in enumerate(signals):
            if signal == 1 and not in_trade:  # Enter trade
                in_trade = True
                trade_start = i
            elif signal == -1 and in_trade:  # Exit trade
                trade_durations.append(i - trade_start)
                in_trade = False
        
        avg_trade_duration = np.mean(trade_durations) if trade_durations else 0
        
        return {
            'total_signals': total_signals,
            'win_rate': win_rate,
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'cagr': cagr,
            'annualized_volatility': ann_vol,
            'avg_trade_duration': avg_trade_duration,
            'buy_signals': int((signals == 1).sum()),
            'sell_signals': int((signals == -1).sum())
        }
    
    def test_strategy_with_scenarios(self, strategy_class, strategy_name, params=None):
        """Test a strategy with multiple market scenarios"""
        print(f"\n🔍 Testing {strategy_name} with multiple scenarios")
        print("-" * 50)
        
        # Define test scenarios - using more data points for strategies with long lookback periods
        scenarios = {
            'Uptrend Market': self.generate_test_data(1000, 100, 'uptrend', 0.02),
            'Downtrend Market': self.generate_test_data(1000, 100, 'downtrend', 0.02),
            'Sideways Market': self.generate_test_data(1000, 100, 'sideways', 0.015),
            'High Volatility': self.generate_test_data(1000, 100, 'uptrend', 0.04),
            'Low Volatility': self.generate_test_data(1000, 100, 'uptrend', 0.01)
        }
        
        scenario_results = {}
        
        for scenario_name, data in scenarios.items():
            print(f"\n  📊 Testing scenario: {scenario_name}")
            result = self.run_backtest(strategy_class, f"{strategy_name} - {scenario_name}", data, params)
            scenario_results[scenario_name] = result
        
        return scenario_results
    
    def generate_report(self, strategy_name, results):
        """Generate a detailed backtest report"""
        report = f"""# {strategy_name} - Backtest Report

## Test Date: {datetime.now().strftime('%Y-%m-%d')}

---

## 📊 **Strategy Overview**
- **Strategy Name**: {strategy_name}
- **Test Scenarios**: {len(results)}
- **Overall Status**: {'PASSED' if all(r.get('status') == 'PASSED' for r in results.values()) else 'MIXED'}

---

## 🧪 **Test Scenarios**

"""
        
        for scenario_name, result in results.items():
            report += f"### {scenario_name}\n\n"
            
            if result.get('status') == 'PASSED':
                report += f"✅ **PASSED** - Strategy executed successfully\n\n"
                report += f"**Performance Metrics:**\n"
                report += f"- Total Signals: {result.get('total_signals', 0)}\n"
                report += f"- Win Rate: {result.get('win_rate', 0):.2%}\n"
                report += f"- Total Return: {result.get('total_return', 0):.2%}\n"
                report += f"- Max Drawdown: {result.get('max_drawdown', 0):.2%}\n"
                report += f"- Sharpe Ratio: {result.get('sharpe_ratio', 0):.2f}\n"
                report += f"- Avg Trade Duration: {result.get('avg_trade_duration', 0):.1f} days\n\n"
                
                report += f"**Signal Breakdown:**\n"
                report += f"- Buy Signals: {result.get('buy_signals', 0)}\n"
                report += f"- Sell Signals: {result.get('sell_signals', 0)}\n"
                report += f"- Hold Signals: {result.get('hold_signals', 0)}\n\n"
                
            else:
                report += f"❌ **FAILED** - {result.get('error', 'Unknown error')}\n\n"
            
            report += "---\n\n"
        
        # Add summary
        passed_scenarios = sum(1 for r in results.values() if r.get('status') == 'PASSED')
        total_scenarios = len(results)
        
        report += f"""## 📈 **Test Summary**

### Overall Results
- **Scenarios Passed**: {passed_scenarios}/{total_scenarios} ({passed_scenarios/total_scenarios:.1%})
- **Strategy Status**: {'✅ READY' if passed_scenarios == total_scenarios else '⚠️ NEEDS ATTENTION'}

### Key Findings
"""
        
        if passed_scenarios == total_scenarios:
            report += "- All test scenarios passed successfully\n"
            report += "- Strategy is ready for live trading\n"
            report += "- Risk management features working correctly\n"
        else:
            report += "- Some test scenarios failed\n"
            report += "- Review error messages and fix issues\n"
            report += "- Re-test before live trading\n"
        
        report += f"""
### Recommendations
1. **Monitor Performance**: Track key metrics in live trading
2. **Risk Management**: Ensure proper position sizing
3. **Market Conditions**: Adapt to changing market regimes
4. **Regular Testing**: Re-test periodically with new data

---

*Backtest completed on {datetime.now().strftime('%Y-%m-%d')} by Backtesting Engine*
"""
        
        return report

    def _normalize_columns(self, df: pd.DataFrame, variant: str = "lower") -> pd.DataFrame:
        """Normalize common OHLCV/symbol/date columns to desired variant.

        variant:
          - "lower": date, open, high, low, close, volume, symbol
          - "capitalized": Datetime, Open, High, Low, Close, Volume, StockName
        """
        if variant == "lower":
            mapping = {
                'Date': 'date', 'Datetime': 'date',
                'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume',
                'StockName': 'symbol', 'Symbol': 'symbol'
            }
            df = df.rename(columns={c: mapping.get(c, c) for c in df.columns})
            if 'symbol' not in df.columns:
                # fallback if original had lowercase already
                if 'StockName' in df.columns:
                    df = df.rename(columns={'StockName': 'symbol'})
            return df
        elif variant == "capitalized":
            mapping = {
                'date': 'Datetime',
                'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
                'symbol': 'StockName'
            }
            df = df.rename(columns={c: mapping.get(c, c) for c in df.columns})
            return df
        else:
            return df

    def _pair_signals_into_trades(self, enriched_df: pd.DataFrame) -> pd.DataFrame:
        """Pair buy/sell signals into complete trades.
        
        Args:
            enriched_df: DataFrame containing signals and price data
            
        Returns:
            DataFrame with columns: buy_date, sell_date, buy_price, sell_price, pnl, pnl_pct
        """
        # Normalize Signal column (handle both 'Signal' and 'signal')
        if 'Signal' not in enriched_df.columns and 'signal' in enriched_df.columns:
            enriched_df = enriched_df.rename(columns={'signal': 'Signal'})
        
        trades = []
        buy_price = None
        buy_date = None
        
        for _, row in enriched_df.iterrows():
            signal = row.get('Signal', 0)
            
            if signal == 1:  # BUY signal
                buy_date = row.get('date')
                buy_price = row.get('close')
                
            elif signal == -1 and buy_price is not None:  # SELL with active position
                sell_date = row.get('date')
                sell_price = row.get('close')
                
                if buy_price is not None and sell_price is not None:
                    pnl = sell_price - buy_price
                    pnl_pct = (pnl / buy_price) * 100 if buy_price != 0 else 0
                    
                    trades.append({
                        'buy_date': buy_date,
                        'sell_date': sell_date,
                        'buy_price': round(buy_price, 2),
                        'sell_price': round(sell_price, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round(pnl_pct, 2)
                    })
                    buy_price = None  # Reset after closing position
        
        return pd.DataFrame(trades)

    def _simulate_portfolio_with_sizing(self, prepared_df: pd.DataFrame, signals_df: pd.DataFrame, strategy, initial_capital: float):
        """Simulate portfolio using strategy-defined sizing with next-bar execution.

        Assumptions:
          - Long-only, single position at a time.
          - Execute buys/sells on next bar's 'open' if available, else next 'close'.
          - Ignores fees/slippage (can be added later).

        Returns:
          - trades_with_size (pd.DataFrame)
          - portfolio_transactions_df (pd.DataFrame)
          - equity_curve (pd.DataFrame)
          - portfolio_metrics (dict)
        """
        # Normalize Signal column in signals_df (handle both 'Signal' and 'signal')
        if 'Signal' not in signals_df.columns and 'signal' in signals_df.columns:
            signals_df = signals_df.rename(columns={'signal': 'Signal'})
        
        # Merge to align dates and price columns
        if 'date' in signals_df.columns:
            df = pd.merge(prepared_df.copy(), signals_df.copy(), on='date', how='left')
        else:
            # If signals_df lacks date, align by index
            df = prepared_df.copy()
            df['Signal'] = signals_df['Signal'].values

        df = df.sort_values('date') if 'date' in df.columns else df
        
        # Normalize Signal column in merged df (handle both cases)
        if 'Signal' not in df.columns and 'signal' in df.columns:
            df = df.rename(columns={'signal': 'Signal'})

        # Ensure canonical 'open'/'close' columns exist after merge (handle _x/_y cases)
        if 'close' not in df.columns:
            for alt in ['close_x', 'close_y']:
                if alt in df.columns:
                    df['close'] = df[alt]
                    break
        if 'open' not in df.columns:
            for alt in ['open_x', 'open_y']:
                if alt in df.columns:
                    df['open'] = df[alt]
                    break

        # Compute per-row target size from strategy (can be fractional); handle method/dict name collision safely
        target_sizes = None
        sizing_attr = getattr(strategy, 'position_sizing', None)
        if callable(sizing_attr):
            try:
                target_sizes = sizing_attr(df)
            except Exception:
                target_sizes = None
        if target_sizes is None:
            # If a dict named 'position_sizing' exists (common in examples), derive simple risk-based size
            sizing_conf = sizing_attr if isinstance(sizing_attr, dict) else getattr(strategy, 'position_sizing_config', None)
            try:
                risk_pct = 0.0
                if isinstance(sizing_conf, dict):
                    risk_pct = float(sizing_conf.get('params', {}).get('risk_pct', 0.0))
                capital_conf = getattr(strategy, 'capital', {}) or {}
                init_cap = float(capital_conf.get('initial_capital', initial_capital))
                lot_size = float(getattr(strategy, 'lot_size', 1) or 1)
                close_px = df['close'] if 'close' in df.columns else df.iloc[:, 1]
                with np.errstate(divide='ignore', invalid='ignore'):
                    raw_size = (risk_pct * init_cap) / (close_px * lot_size)
                raw_size = raw_size.replace([np.inf, -np.inf], 0).fillna(0)
                target_sizes = pd.Series(raw_size, index=df.index)
            except Exception:
                target_sizes = pd.Series(1, index=df.index)

        # Get entry/exit signals and execution prices from strategy methods
        # entry_rules() and exit_rules() control both WHEN and WHICH PRICE
        entry_signals = None
        exit_signals = None
        entry_config = None
        exit_config = None
        
        # Get entry signals and config
        if hasattr(strategy, 'entry_rules') and callable(getattr(strategy, 'entry_rules')):
            try:
                entry_result = strategy.entry_rules(df)
                if isinstance(entry_result, dict):
                    # Dict format: {'signals': Series, 'price_col': str, 'shift': int}
                    entry_signals = entry_result.get('signals', df.get('Signal', pd.Series(0, index=df.index)))
                    entry_config = entry_result
                else:
                    # Series format: just signals, use default prices
                    entry_signals = entry_result
            except Exception:
                pass
        
        # Get exit signals and config
        if hasattr(strategy, 'exit_rules') and callable(getattr(strategy, 'exit_rules')):
            try:
                exit_result = strategy.exit_rules(df)
                if isinstance(exit_result, dict):
                    # Dict format: {'signals': Series, 'price_col': str, 'shift': int}
                    exit_signals = exit_result.get('signals', pd.Series(0, index=df.index))
                    exit_config = exit_result
                else:
                    # Series format: just signals, use default prices
                    exit_signals = exit_result
            except Exception:
                pass
        
        # Fallback to Signal column if entry_rules/exit_rules not used (backward compatible)
        if entry_signals is None:
            entry_signals = df.get('Signal', pd.Series(0, index=df.index))
        if exit_signals is None:
            # For exit, check Signal == -1 if no exit_rules provided
            exit_signals = (df.get('Signal', pd.Series(0, index=df.index)) == -1).astype(int)
        
        # Ensure signals are Series with same index as df
        if not isinstance(entry_signals, pd.Series):
            entry_signals = pd.Series(entry_signals, index=df.index) if hasattr(entry_signals, '__iter__') else pd.Series(0, index=df.index)
        if not isinstance(exit_signals, pd.Series):
            exit_signals = pd.Series(exit_signals, index=df.index) if hasattr(exit_signals, '__iter__') else pd.Series(0, index=df.index)
        
        # Align signals with df index
        entry_signals = entry_signals.reindex(df.index, fill_value=0)
        exit_signals = exit_signals.reindex(df.index, fill_value=0)
        
        # Get execution prices from config (or defaults)
        entry_price_col = entry_config.get('price_col', 'open') if entry_config else 'open'
        entry_shift = entry_config.get('shift', -1) if entry_config else -1
        if entry_price_col not in df.columns:
            entry_price_col = 'open' if 'open' in df.columns else 'close'
        entry_exec_price = df[entry_price_col].shift(entry_shift) if entry_shift != 0 else df[entry_price_col]
        
        exit_price_col = exit_config.get('price_col', 'open') if exit_config else 'open'
        exit_shift = exit_config.get('shift', -1) if exit_config else -1
        if exit_price_col not in df.columns:
            exit_price_col = 'open' if 'open' in df.columns else 'close'
        exit_exec_price = df[exit_price_col].shift(exit_shift) if exit_shift != 0 else df[exit_price_col]
        
        # Get execution dates (always use next bar for dates)
        next_exec_date = df['date'].shift(-1) if 'date' in df.columns else pd.Series(index=df.index)

        cash = float(initial_capital)
        shares = 0
        in_position = False
        cost_basis = 0.0
        entry_info = {}  # Store entry details until exit

        trades = []
        portfolio_transactions = []  # Detailed transaction log
        equity_rows = []

        for idx, row in df.iterrows():
            date_val = row.get('date', idx)
            price_today_close = row.get('close', np.nan)
            
            # Get entry/exit signals from strategy methods (not hardcoded Signal column)
            entry_signal = entry_signals.loc[idx] if idx in entry_signals.index else 0
            exit_signal = exit_signals.loc[idx] if idx in exit_signals.index else 0

            # Mark-to-market at today's close
            equity_value = cash + shares * (price_today_close if not np.isnan(price_today_close) else 0.0)
            equity_rows.append({'date': date_val, 'cash': cash, 'shares': shares, 'close': price_today_close, 'equity': equity_value})

            # Entry logic: use entry_signals from entry_rules()
            # entry_signal > 0 means enter long, < 0 means enter short
            if entry_signal > 0 and not in_position:
                # Determine entry execution price
                px = entry_exec_price.loc[idx] if idx in entry_exec_price.index else np.nan
                if np.isnan(px):
                    continue
                # Determine intended size at current row
                intended_shares = int(np.floor(max(target_sizes.loc[idx], 0))) if idx in target_sizes.index else 0
                if intended_shares <= 0:
                    continue
                # Constrain by available cash
                affordable_shares = int(np.floor(cash / px))
                qty = max(min(intended_shares, affordable_shares), 0)
                if qty <= 0:
                    continue
                cost = qty * px
                cash_before = cash
                shares_before = shares
                cash -= cost
                shares += qty
                in_position = True
                # Store entry info for later trade completion
                entry_info = {
                    'entry_signal_date': date_val,
                    'entry_date': next_exec_date.loc[idx] if idx in next_exec_date.index else date_val,
                    'entry_price': round(px, 6),
                    'quantity': qty,
                    'cost': round(cost, 6)
                }
                # Log transaction
                portfolio_transactions.append({
                    'date': entry_info['entry_date'],
                    'transaction_type': 'BUY',
                    'price': round(px, 6),
                    'quantity': qty,
                    'amount': round(cost, 6),
                    'cash_before': round(cash_before, 2),
                    'cash_after': round(cash, 2),
                    'shares_before': shares_before,
                    'shares_after': shares,
                    'equity_before': round(cash_before + shares_before * (row.get('close', px)), 2),
                    'equity_after': round(cash + shares * (row.get('close', px)), 2)
                })
            # Exit logic: use exit_signals from exit_rules()
            elif exit_signal != 0 and in_position and shares > 0:
                # Determine exit execution price
                px = exit_exec_price.loc[idx] if idx in exit_exec_price.index else np.nan
                if np.isnan(px):
                    continue
                proceeds = shares * px
                exit_price = round(px, 6)
                exit_date = next_exec_date.loc[idx] if idx in next_exec_date.index else date_val
                pnl = proceeds - (shares * entry_info['entry_price'])
                return_pct = ((exit_price / entry_info['entry_price']) - 1.0) * 100.0
                
                cash_before = cash
                shares_before = shares
                
                # Create complete trade row (MBVC format: single row per trade)
                trades.append({
                    'entry_date': entry_info['entry_date'],
                    'entry_price': entry_info['entry_price'],
                    'quantity': shares,
                    'exit_date': exit_date,
                    'exit_price': exit_price,
                    'exit_reason': 'signal',
                    'pnl': round(pnl, 6),
                    'return_pct': round(return_pct, 6)
                })
                
                cash += proceeds
                shares = 0
                in_position = False
                entry_info = {}
                
                # Log transaction
                portfolio_transactions.append({
                    'date': exit_date,
                    'transaction_type': 'SELL',
                    'price': round(px, 6),
                    'quantity': shares_before,
                    'amount': round(proceeds, 6),
                    'cash_before': round(cash_before, 2),
                    'cash_after': round(cash, 2),
                    'shares_before': shares_before,
                    'shares_after': shares,
                    'equity_before': round(cash_before + shares_before * (row.get('close', px)), 2),
                    'equity_after': round(cash + shares * (row.get('close', px)), 2),
                    'pnl': round(pnl, 6),
                    'return_pct': round(return_pct, 6)
                })

        trades_with_size = pd.DataFrame(trades)
        portfolio_transactions_df = pd.DataFrame(portfolio_transactions)
        equity_curve = pd.DataFrame(equity_rows)

        # Portfolio metrics from equity curve
        portfolio_metrics = {}
        if len(equity_curve) > 1:
            equity_curve = equity_curve.dropna(subset=['equity']).copy()
            if not equity_curve.empty and len(equity_curve) > 1:
                # Ensure equity is numeric and positive
                equity_curve['equity'] = pd.to_numeric(equity_curve['equity'], errors='coerce')
                equity_curve = equity_curve[equity_curve['equity'] > 0]
                
                if len(equity_curve) > 1:
                    initial_equity = float(equity_curve['equity'].iloc[0])
                    final_equity = float(equity_curve['equity'].iloc[-1])
                    
                    # Calculate returns
                    returns = equity_curve['equity'].pct_change().fillna(0)
                    # Remove infinite and NaN values
                    returns = returns.replace([np.inf, -np.inf], 0).fillna(0)
                    
                    trading_days = 252
                    ann_factor = np.sqrt(trading_days)
                    
                    # Total return
                    total_return = (final_equity / max(initial_equity, 1e-9)) - 1
                    
                    # Annualized volatility (only if we have meaningful returns)
                    vol = returns.std() * ann_factor if len(returns) > 1 and returns.std() > 0 else 0
                    
                    # Sharpe ratio (annualized)
                    if vol > 0 and len(returns) > 1:
                        mean_return = returns.mean()
                        sharpe = (mean_return * trading_days) / vol
                    else:
                        sharpe = 0.0
                    
                    # Drawdown calculation using equity values directly (more accurate)
                    running_max = equity_curve['equity'].expanding().max()
                    dd = (equity_curve['equity'] - running_max) / running_max
                    max_dd = float(dd.min()) if len(dd) > 0 else 0.0
                    
                    # CAGR calculation
                    years = max(len(returns) / trading_days, 1e-9)
                    if initial_equity > 0 and final_equity > 0:
                        cagr = (final_equity / initial_equity) ** (1/years) - 1
                    else:
                        cagr = 0.0
                    
                    portfolio_metrics = {
                        'total_return': float(total_return),
                        'sharpe_ratio': float(sharpe),
                        'max_drawdown': float(max_dd),
                        'cagr': float(cagr),
                        'annualized_volatility': float(vol)
                    }

        return trades_with_size, portfolio_transactions_df, equity_curve, portfolio_metrics

    def _enrich_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute lightweight indicator features to mirror MBVC-style exports.
        Adds: rsi(14), ema20, ema50, macd_hist (12-26, sig9), vol_ratio(10),
        52w_high(252), swing_low_10d(min low 10), swing_high_10d(max high 10).
        """
        out = df.copy()
        # Ensure needed cols exist
        for col in ['close','high','low','volume']:
            if col not in out.columns:
                return out
        # EMA
        out['ema20'] = out['close'].ewm(span=20, adjust=False).mean()
        out['ema50'] = out['close'].ewm(span=50, adjust=False).mean()
        # MACD histogram
        ema12 = out['close'].ewm(span=12, adjust=False).mean()
        ema26 = out['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_sig = macd.ewm(span=9, adjust=False).mean()
        out['macd_hist'] = macd - macd_sig
        # RSI 14 (simple Wilder-like approximation)
        delta = out['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        roll_up = gain.ewm(alpha=1/14, adjust=False).mean()
        roll_down = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = (roll_up / (roll_down.replace(0, 1e-12)))
        out['rsi'] = 100 - (100 / (1 + rs))
        # Volume ratio 10
        out['vol_ratio'] = out['volume'] / (out['volume'].rolling(10).mean().replace(0, 1e-12))
        # 52w high (252 trading days)
        out['52w_high'] = out['close'].rolling(252, min_periods=1).max()
        # Swings 10d
        out['swing_low_10d'] = out['low'].rolling(10, min_periods=1).min()
        out['swing_high_10d'] = out['high'].rolling(10, min_periods=1).max()
        return out

def load_strategy_from_file(file_path, strategy_name):
    """Load a strategy class from a file"""
    try:
        # Add the directory to Python path
        strategy_dir = os.path.dirname(file_path)
        if strategy_dir not in sys.path:
            sys.path.insert(0, strategy_dir)
        
        # Import the module
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find the strategy class
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                hasattr(attr, 'generate_signals') and 
                attr_name != 'Strategy'):
                return attr
        
        raise ValueError(f"No strategy class found in {file_path}")
        
    except Exception as e:
        print(f"Error loading strategy from {file_path}: {e}")
        return None

if __name__ == "__main__":
    # Example usage
    engine = BacktestEngine()
    
    # Generate test data
    test_data = engine.generate_test_data(500, 100, 'uptrend', 0.02)
    print(f"Generated test data with {len(test_data)} periods")
    print(f"Date range: {test_data['date'].min()} to {test_data['date'].max()}")
    print(f"Price range: ${test_data['close'].min():.2f} to ${test_data['close'].max():.2f}")
