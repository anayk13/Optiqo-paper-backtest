"""
MBVC Data Adapter for Paper Trading Engine
Converts MBVC parquet data format to the paper trading engine's expected format.
Supports both daily and minute-level data from MBVC project.
"""

import pandas as pd
import numpy as np
import asyncio
import os
import glob
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from .event_engine import EventEngine, MarketEvent
from .logger import get_logger


class MBVCDataAdapter:
    """
    Adapter to convert MBVC parquet data format to paper trading engine format.
    Handles both daily and minute-level data from MBVC project structure.
    """
    
    def __init__(self, 
                 day_data_root: str,
                 minute_data_root: str = None,
                 event_engine: EventEngine = None,
                 logger=None):
        self.day_data_root = Path(day_data_root)
        self.minute_data_root = Path(minute_data_root) if minute_data_root else None
        self.event_engine = event_engine
        self.logger = logger or get_logger("mbvc_data_adapter")
        
        # Data caches
        self.day_data_cache: Dict[str, pd.DataFrame] = {}
        self.minute_data_cache: Dict[str, pd.DataFrame] = {}
        self.symbol_mapping: Dict[str, str] = {}  # Maps StockName to instrument_token
        
        # Configuration
        self.start_date = None
        self.end_date = None
        self.current_date = None
        self.tick_delay = 0.1  # Delay between ticks in seconds
        
        self.logger.info(f"MBVCDataAdapter initialized with day_data_root: {self.day_data_root}")
        if self.minute_data_root:
            self.logger.info(f"Minute data root: {self.minute_data_root}")
    
    def set_date_range(self, start_date: str, end_date: str):
        """Set the date range for data processing"""
        self.start_date = pd.to_datetime(start_date).date()
        self.end_date = pd.to_datetime(end_date).date()
        self.current_date = self.start_date
        self.logger.info(f"Date range set: {self.start_date} to {self.end_date}")
    
    def load_symbol_mapping(self) -> Dict[str, str]:
        """Load symbol mapping from MBVC data structure"""
        if not self.day_data_root.exists():
            self.logger.error(f"Day data root does not exist: {self.day_data_root}")
            return {}
        
        # Find all parquet files to extract symbols
        parquet_files = list(self.day_data_root.glob("**/*.parquet"))
        
        if not parquet_files:
            self.logger.error("No parquet files found in day data root")
            return {}
        
        # Load first file to get symbol list
        try:
            sample_df = pd.read_parquet(parquet_files[0])
            if 'StockName' in sample_df.columns:
                symbols = sample_df['StockName'].unique()
                # Create mapping: StockName -> instrument_token (using index)
                for i, symbol in enumerate(symbols):
                    self.symbol_mapping[symbol] = f"MBVC_{i:06d}"
                
                self.logger.info(f"Loaded {len(self.symbol_mapping)} symbols from MBVC data")
                return self.symbol_mapping
            else:
                self.logger.error("StockName column not found in MBVC data")
                return {}
                
        except Exception as e:
            self.logger.error(f"Error loading symbol mapping: {e}")
            return {}
    
    def load_day_data(self, date: datetime.date) -> pd.DataFrame:
        """Load daily data for a specific date"""
        if date in self.day_data_cache:
            return self.day_data_cache[date]
        
        # Find parquet file for this date
        month_folder = str(date.month)
        day_file = f"{date.day}.parquet"
        file_path = self.day_data_root / month_folder / day_file
        
        if not file_path.exists():
            self.logger.warning(f"No data file found for {date}: {file_path}")
            return pd.DataFrame()
        
        try:
            df = pd.read_parquet(file_path)
            
            # Convert MBVC format to paper trading engine format
            df = self._convert_day_data_format(df)
            
            # Filter by date range if set
            if self.start_date and self.end_date:
                df = df[(df['date'] >= self.start_date) & (df['date'] <= self.end_date)]
            
            self.day_data_cache[date] = df
            self.logger.info(f"Loaded day data for {date}: {len(df)} rows")
            return df
            
        except Exception as e:
            self.logger.error(f"Error loading day data for {date}: {e}")
            return pd.DataFrame()
    
    def load_minute_data(self, date: datetime.date) -> pd.DataFrame:
        """Load minute-level data for a specific date"""
        if not self.minute_data_root or not self.minute_data_root.exists():
            return pd.DataFrame()
        
        if date in self.minute_data_cache:
            return self.minute_data_cache[date]
        
        # Find parquet file for this date
        month_folder = str(date.month)
        day_file = f"{date.day}.parquet"
        file_path = self.minute_data_root / month_folder / day_file
        
        if not file_path.exists():
            self.logger.warning(f"No minute data file found for {date}: {file_path}")
            return pd.DataFrame()
        
        try:
            df = pd.read_parquet(file_path)
            
            # Convert MBVC format to paper trading engine format
            df = self._convert_minute_data_format(df)
            
            # Filter by date range if set
            if self.start_date and self.end_date:
                df = df[(df['date'] >= self.start_date) & (df['date'] <= self.end_date)]
            
            self.minute_data_cache[date] = df
            self.logger.info(f"Loaded minute data for {date}: {len(df)} rows")
            return df
            
        except Exception as e:
            self.logger.error(f"Error loading minute data for {date}: {e}")
            return pd.DataFrame()
    
    def _convert_day_data_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert MBVC day data format to paper trading engine format"""
        if df.empty:
            return df
        
        # MBVC format: Date, Open, High, Low, Close, Volume, OI, StockName, security_id
        # Paper trading engine expects: timestamp, open, high, low, close, volume, symbol
        
        converted_df = pd.DataFrame()
        
        # Convert date column
        if 'Date' in df.columns:
            converted_df['timestamp'] = pd.to_datetime(df['Date'])
            converted_df['date'] = converted_df['timestamp'].dt.date
        else:
            self.logger.error("Date column not found in MBVC day data")
            return pd.DataFrame()
        
        # Convert OHLCV data
        column_mapping = {
            'Open': 'open',
            'High': 'high', 
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume'
        }
        
        for mbvc_col, engine_col in column_mapping.items():
            if mbvc_col in df.columns:
                converted_df[engine_col] = df[mbvc_col]
            else:
                self.logger.warning(f"Column {mbvc_col} not found in MBVC day data")
                converted_df[engine_col] = 0.0
        
        # Convert symbol
        if 'StockName' in df.columns:
            converted_df['symbol'] = df['StockName']
            # Add instrument_token mapping
            converted_df['instrument_token'] = converted_df['symbol'].map(self.symbol_mapping)
        else:
            self.logger.error("StockName column not found in MBVC day data")
            return pd.DataFrame()
        
        # Add additional fields
        converted_df['oi'] = df.get('OI', 0)
        converted_df['security_id'] = df.get('security_id', '')
        
        return converted_df
    
    def _convert_minute_data_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert MBVC minute data format to paper trading engine format"""
        if df.empty:
            return df
        
        # MBVC format: datetime, instrument_token, StockName, open, high, low, close, volume
        # Paper trading engine expects: timestamp, open, high, low, close, volume, symbol
        
        converted_df = pd.DataFrame()
        
        # Convert datetime
        if 'datetime' in df.columns:
            converted_df['timestamp'] = pd.to_datetime(df['datetime'])
            converted_df['date'] = converted_df['timestamp'].dt.date
        else:
            self.logger.error("datetime column not found in MBVC minute data")
            return pd.DataFrame()
        
        # Convert OHLCV data
        column_mapping = {
            'open': 'open',
            'high': 'high',
            'low': 'low', 
            'close': 'close',
            'volume': 'volume'
        }
        
        for mbvc_col, engine_col in column_mapping.items():
            if mbvc_col in df.columns:
                converted_df[engine_col] = df[mbvc_col]
            else:
                self.logger.warning(f"Column {mbvc_col} not found in MBVC minute data")
                converted_df[engine_col] = 0.0
        
        # Convert symbol
        if 'StockName' in df.columns:
            converted_df['symbol'] = df['StockName']
            # Use existing instrument_token or create mapping
            if 'instrument_token' in df.columns:
                converted_df['instrument_token'] = df['instrument_token']
            else:
                converted_df['instrument_token'] = converted_df['symbol'].map(self.symbol_mapping)
        else:
            self.logger.error("StockName column not found in MBVC minute data")
            return pd.DataFrame()
        
        return converted_df
    
    async def generate_ticks_from_day_data(self, date: datetime.date):
        """Generate ticks from daily data for a specific date"""
        day_data = self.load_day_data(date)
        
        if day_data.empty:
            self.logger.warning(f"No day data available for {date}")
            return
        
        # Group by symbol and generate ticks
        for symbol, group in day_data.groupby('symbol'):
            if symbol not in self.symbol_mapping:
                continue
            
            instrument_token = self.symbol_mapping[symbol]
            
            # Create market events for each symbol
            for _, row in group.iterrows():
                timestamp = row['timestamp']
                if pd.isna(timestamp):
                    continue
                
                # Convert to epoch seconds
                if hasattr(timestamp, 'timestamp'):
                    timestamp_seconds = timestamp.timestamp()
                else:
                    timestamp_seconds = pd.to_datetime(timestamp).timestamp()
                
                # Create market event
                market_event = MarketEvent(
                    instrument_token=instrument_token,
                    ltp=float(row['close']),
                    timestamp=timestamp_seconds
                )
                
                if self.event_engine:
                    await self.event_engine.put(market_event)
                
                self.logger.debug(f"Generated tick for {symbol} ({instrument_token}): LTP={row['close']}")
                await asyncio.sleep(self.tick_delay)
    
    async def generate_ticks_from_minute_data(self, date: datetime.date):
        """Generate ticks from minute-level data for a specific date"""
        minute_data = self.load_minute_data(date)
        
        if minute_data.empty:
            self.logger.warning(f"No minute data available for {date}")
            return
        
        # Sort by timestamp
        minute_data = minute_data.sort_values('timestamp')
        
        # Group by symbol and generate ticks
        for symbol, group in minute_data.groupby('symbol'):
            if symbol not in self.symbol_mapping:
                continue
            
            instrument_token = self.symbol_mapping[symbol]
            
            # Create market events for each minute
            for _, row in group.iterrows():
                timestamp = row['timestamp']
                if pd.isna(timestamp):
                    continue
                
                # Convert to epoch seconds
                if hasattr(timestamp, 'timestamp'):
                    timestamp_seconds = timestamp.timestamp()
                else:
                    timestamp_seconds = pd.to_datetime(timestamp).timestamp()
                
                # Create market event
                market_event = MarketEvent(
                    instrument_token=instrument_token,
                    ltp=float(row['close']),
                    timestamp=timestamp_seconds
                )
                
                if self.event_engine:
                    await self.event_engine.put(market_event)
                
                self.logger.debug(f"Generated minute tick for {symbol} ({instrument_token}): LTP={row['close']}")
                await asyncio.sleep(self.tick_delay)
    
    async def generate_ticks_for_date_range(self, use_minute_data: bool = True):
        """Generate ticks for the entire date range"""
        if not self.start_date or not self.end_date:
            self.logger.error("Date range not set. Call set_date_range() first.")
            return
        
        current_date = self.start_date
        while current_date <= self.end_date:
            # Skip weekends
            if current_date.weekday() < 5:  # Monday = 0, Sunday = 6
                self.logger.info(f"Generating ticks for {current_date}")
                
                if use_minute_data and self.minute_data_root:
                    await self.generate_ticks_from_minute_data(current_date)
                else:
                    await self.generate_ticks_from_day_data(current_date)
            
            current_date += timedelta(days=1)
        
        self.logger.info("Finished generating ticks for date range")
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols from MBVC data"""
        return list(self.symbol_mapping.keys())
    
    def get_symbol_instrument_token(self, symbol: str) -> Optional[str]:
        """Get instrument token for a symbol"""
        return self.symbol_mapping.get(symbol)
    
    def get_data_summary(self) -> Dict[str, Any]:
        """Get summary of available data"""
        summary = {
            'day_data_root': str(self.day_data_root),
            'minute_data_root': str(self.minute_data_root) if self.minute_data_root else None,
            'symbols_count': len(self.symbol_mapping),
            'symbols': list(self.symbol_mapping.keys()),
            'date_range': {
                'start': self.start_date.isoformat() if self.start_date else None,
                'end': self.end_date.isoformat() if self.end_date else None
            },
            'cached_dates': {
                'day_data': list(self.day_data_cache.keys()),
                'minute_data': list(self.minute_data_cache.keys())
            }
        }
        return summary
