"""
Strategy Loader for Dynamic Loading of LLM-Generated Strategies
Supports loading strategies from files, databases, or API endpoints.
"""

import os
import sys
import importlib
import inspect
import json
import logging
from typing import Dict, List, Any, Optional, Type, Union
from pathlib import Path
from datetime import datetime
import tempfile
import ast

from .logger import get_logger
from strategies.enhanced_base_strategy import EnhancedBaseStrategy


class StrategyLoader:
    """
    Dynamic strategy loader that can load LLM-generated strategies
    and integrate them with the production trading engine.
    """
    
    def __init__(self, strategies_dir: str = "strategies", temp_dir: str = None):
        self.strategies_dir = Path(strategies_dir)
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "trading_strategies"
        self.temp_dir.mkdir(exist_ok=True)
        
        self.logger = get_logger(
            main_folder_name="strategy_loader",
            broker_name="SYSTEM",
            account_name="LOADER",
            strategy_name="LOADER"
        )
        
        # Strategy registry
        self.loaded_strategies: Dict[str, Type[EnhancedBaseStrategy]] = {}
        self.strategy_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Validation rules
        self.required_methods = ['generate_signals', 'description', 'parameter_schema']
        self.optional_methods = ['preprocess_data', 'entry_rules', 'exit_rules', 'position_sizing', 'risk_management']
        
        self.logger.info(f"StrategyLoader initialized with strategies_dir: {self.strategies_dir}")

    def load_strategy_from_code(self, 
                               strategy_code: str, 
                               strategy_name: str,
                               strategy_class_name: str = None) -> Type[EnhancedBaseStrategy]:
        """
        Load a strategy from Python code string (LLM-generated).
        
        Args:
            strategy_code: Python code string containing the strategy
            strategy_name: Unique name for the strategy
            strategy_class_name: Name of the strategy class (auto-detected if None)
        
        Returns:
            Strategy class that can be instantiated
        """
        try:
            # Create temporary file
            temp_file = self.temp_dir / f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
            
            # Write code to file
            with open(temp_file, 'w') as f:
                f.write(strategy_code)
            
            # Load strategy from file
            strategy_class = self._load_strategy_from_file(
                str(temp_file), 
                strategy_name, 
                strategy_class_name
            )
            
            # Clean up temp file
            temp_file.unlink()
            
            self.logger.info(f"Strategy '{strategy_name}' loaded from code successfully")
            return strategy_class
            
        except Exception as e:
            self.logger.error(f"Failed to load strategy from code: {e}", exc_info=True)
            raise

    def load_strategy_from_file(self, 
                               file_path: str, 
                               strategy_name: str = None,
                               strategy_class_name: str = None) -> Type[EnhancedBaseStrategy]:
        """
        Load a strategy from a Python file.
        
        Args:
            file_path: Path to the Python file
            strategy_name: Unique name for the strategy (defaults to filename)
            strategy_class_name: Name of the strategy class (auto-detected if None)
        
        Returns:
            Strategy class that can be instantiated
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Strategy file not found: {file_path}")
            
            if strategy_name is None:
                strategy_name = file_path.stem
            
            strategy_class = self._load_strategy_from_file(
                str(file_path), 
                strategy_name, 
                strategy_class_name
            )
            
            self.logger.info(f"Strategy '{strategy_name}' loaded from file: {file_path}")
            return strategy_class
            
        except Exception as e:
            self.logger.error(f"Failed to load strategy from file {file_path}: {e}", exc_info=True)
            raise

    def load_strategy_from_json(self, 
                               json_path: str,
                               strategy_name: str = None) -> Type[EnhancedBaseStrategy]:
        """
        Load a strategy from JSON configuration (for no-code strategies).
        
        Args:
            json_path: Path to JSON file containing strategy definition
            strategy_name: Unique name for the strategy
        
        Returns:
            Strategy class that can be instantiated
        """
        try:
            with open(json_path, 'r') as f:
                strategy_config = json.load(f)
            
            if strategy_name is None:
                strategy_name = strategy_config.get('name', 'json_strategy')
            
            # Generate Python code from JSON
            strategy_code = self._generate_code_from_json(strategy_config)
            
            # Load the generated code
            strategy_class = self.load_strategy_from_code(
                strategy_code, 
                strategy_name,
                strategy_config.get('class_name', 'GeneratedStrategy')
            )
            
            self.logger.info(f"Strategy '{strategy_name}' loaded from JSON: {json_path}")
            return strategy_class
            
        except Exception as e:
            self.logger.error(f"Failed to load strategy from JSON {json_path}: {e}", exc_info=True)
            raise

    def load_all_strategies_from_directory(self, 
                                         directory: str = None) -> Dict[str, Type[EnhancedBaseStrategy]]:
        """
        Load all strategies from a directory.
        
        Args:
            directory: Directory to scan for strategies (defaults to strategies_dir)
        
        Returns:
            Dictionary mapping strategy names to strategy classes
        """
        try:
            if directory is None:
                directory = self.strategies_dir
            else:
                directory = Path(directory)
            
            strategies = {}
            
            # Scan for Python files
            for py_file in directory.glob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                
                try:
                    strategy_name = py_file.stem
                    strategy_class = self.load_strategy_from_file(str(py_file), strategy_name)
                    strategies[strategy_name] = strategy_class
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load strategy from {py_file}: {e}")
                    continue
            
            # Scan for JSON files
            for json_file in directory.glob("*.json"):
                try:
                    strategy_name = json_file.stem
                    strategy_class = self.load_strategy_from_json(str(json_file), strategy_name)
                    strategies[strategy_name] = strategy_class
                    
                except Exception as e:
                    self.logger.warning(f"Failed to load strategy from {json_file}: {e}")
                    continue
            
            self.logger.info(f"Loaded {len(strategies)} strategies from {directory}")
            return strategies
            
        except Exception as e:
            self.logger.error(f"Failed to load strategies from directory {directory}: {e}", exc_info=True)
            return {}

    def _load_strategy_from_file(self, 
                                file_path: str, 
                                strategy_name: str,
                                strategy_class_name: str = None) -> Type[EnhancedBaseStrategy]:
        """Internal method to load strategy from file"""
        try:
            # Add directory to Python path
            file_dir = Path(file_path).parent
            if str(file_dir) not in sys.path:
                sys.path.insert(0, str(file_dir))
            
            # Import the module
            module_name = Path(file_path).stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find strategy class
            if strategy_class_name:
                strategy_class = getattr(module, strategy_class_name, None)
            else:
                # Auto-detect strategy class
                strategy_class = self._find_strategy_class(module)
            
            if strategy_class is None:
                raise ValueError(f"No valid strategy class found in {file_path}")
            
            # Validate strategy class
            self._validate_strategy_class(strategy_class, strategy_name)
            
            # Register strategy
            self.loaded_strategies[strategy_name] = strategy_class
            self.strategy_metadata[strategy_name] = {
                'file_path': file_path,
                'class_name': strategy_class.__name__,
                'loaded_at': datetime.now().isoformat(),
                'description': getattr(strategy_class, 'description', lambda: 'No description')(),
                'parameter_schema': getattr(strategy_class, 'parameter_schema', lambda: {})(),
            }
            
        return strategy_class
            
        except Exception as e:
            self.logger.error(f"Error loading strategy from file {file_path}: {e}", exc_info=True)
            raise

    def _find_strategy_class(self, module) -> Optional[Type[EnhancedBaseStrategy]]:
        """Find the strategy class in a module"""
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Check if it's a strategy class (inherits from EnhancedBaseStrategy or has required methods)
            if (issubclass(obj, EnhancedBaseStrategy) or 
                self._has_required_methods(obj)):
                return obj
        return None

    def _has_required_methods(self, cls) -> bool:
        """Check if a class has the required strategy methods"""
        for method_name in self.required_methods:
            if not hasattr(cls, method_name):
                return False
        return True

    def _validate_strategy_class(self, strategy_class: Type, strategy_name: str):
        """Validate that a strategy class meets requirements"""
        try:
            # Check required methods
            for method_name in self.required_methods:
                if not hasattr(strategy_class, method_name):
                    raise ValueError(f"Strategy class missing required method: {method_name}")
            
            # Check if it can be instantiated with required parameters
            try:
                # Try to create an instance (this will fail if __init__ signature is wrong)
                inspect.signature(strategy_class.__init__)
            except Exception as e:
                raise ValueError(f"Strategy class has invalid __init__ signature: {e}")
            
            # Check if generate_signals returns a DataFrame
            generate_signals_method = getattr(strategy_class, 'generate_signals')
            sig = inspect.signature(generate_signals_method)
            if len(sig.parameters) < 2:  # Should have at least data and context parameters
                raise ValueError("generate_signals method must accept at least 'data' and 'context' parameters")
            
            self.logger.info(f"Strategy class '{strategy_class.__name__}' validated successfully")
            
        except Exception as e:
            self.logger.error(f"Strategy validation failed for {strategy_name}: {e}")
            raise

    def _generate_code_from_json(self, strategy_config: Dict[str, Any]) -> str:
        """Generate Python code from JSON strategy configuration"""
        try:
            strategy_name = strategy_config.get('name', 'GeneratedStrategy')
            class_name = strategy_config.get('class_name', 'GeneratedStrategy')
            description = strategy_config.get('description', 'Generated strategy')
            parameters = strategy_config.get('parameters', {})
            
            # Generate the strategy code
            code_template = f'''
import pandas as pd
import numpy as np
from strategies.enhanced_base_strategy import EnhancedBaseStrategy

class {class_name}(EnhancedBaseStrategy):
    """
    {description}
    Generated from JSON configuration.
    """
    
    def __init__(self, event_engine, logger, executor_account_name, strategy_id=None, strategy_manager=None, **kwargs):
        super().__init__(event_engine, logger, executor_account_name, strategy_id, strategy_manager, **kwargs)
        
        # Set parameters from configuration
        self.params.update({parameters})
    
    def generate_signals(self, data, context=None):
        """
        Generate trading signals based on the strategy logic.
        """
        # This is a template - implement your strategy logic here
        signals = pd.DataFrame(index=data.index)
        signals['Signal'] = 0  # Default: no signal
        
        # Add your strategy logic here
        # Example: Simple moving average crossover
        if len(data) >= 20:
            short_ma = data['close'].rolling(window=5).mean()
            long_ma = data['close'].rolling(window=20).mean()
            
            # Generate signals
            signals['Signal'] = 0
            signals.loc[short_ma > long_ma, 'Signal'] = 1  # Buy signal
            signals.loc[short_ma < long_ma, 'Signal'] = -1  # Sell signal
        
        return signals
    
    def description(self):
        """Return strategy description"""
        return "{description}"
    
    def parameter_schema(self):
        """Return parameter schema for UI"""
        return {parameters}
'''
            
            return code_template
            
        except Exception as e:
            self.logger.error(f"Failed to generate code from JSON: {e}", exc_info=True)
            raise

    def get_loaded_strategies(self) -> Dict[str, Type[EnhancedBaseStrategy]]:
        """Get all loaded strategies"""
        return self.loaded_strategies.copy()

    def get_strategy_metadata(self, strategy_name: str = None) -> Union[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """Get metadata for a specific strategy or all strategies"""
        if strategy_name:
            return self.strategy_metadata.get(strategy_name, {})
        return self.strategy_metadata.copy()

    def unload_strategy(self, strategy_name: str):
        """Unload a strategy from memory"""
        if strategy_name in self.loaded_strategies:
            del self.loaded_strategies[strategy_name]
            del self.strategy_metadata[strategy_name]
            self.logger.info(f"Strategy '{strategy_name}' unloaded")
        else:
            self.logger.warning(f"Strategy '{strategy_name}' not found for unloading")

    def reload_strategy(self, strategy_name: str) -> Type[EnhancedBaseStrategy]:
        """Reload a strategy from its source"""
        if strategy_name not in self.strategy_metadata:
            raise ValueError(f"Strategy '{strategy_name}' not found for reloading")
        
        metadata = self.strategy_metadata[strategy_name]
        file_path = metadata['file_path']
        
        # Unload current version
        self.unload_strategy(strategy_name)
        
        # Reload from file
        return self.load_strategy_from_file(file_path, strategy_name, metadata['class_name'])

    def create_strategy_from_template(self, 
                                    strategy_name: str,
                                    strategy_type: str = "basic",
                                    parameters: Dict[str, Any] = None) -> str:
        """Create a new strategy from a template"""
        try:
            templates = {
                "basic": self._get_basic_strategy_template(),
                "momentum": self._get_momentum_strategy_template(),
                "mean_reversion": self._get_mean_reversion_strategy_template(),
                "arbitrage": self._get_arbitrage_strategy_template(),
                "ml_based": self._get_ml_strategy_template()
            }
            
            if strategy_type not in templates:
                raise ValueError(f"Unknown strategy type: {strategy_type}")
            
            template = templates[strategy_type]
            strategy_code = template.format(
                strategy_name=strategy_name,
                class_name=f"{strategy_name}Strategy",
                parameters=parameters or {}
            )
            
            # Save to file
            strategy_file = self.strategies_dir / f"{strategy_name}.py"
            with open(strategy_file, 'w') as f:
                f.write(strategy_code)
            
            self.logger.info(f"Strategy template '{strategy_name}' created: {strategy_file}")
            return str(strategy_file)
            
    except Exception as e:
            self.logger.error(f"Failed to create strategy template: {e}", exc_info=True)
            raise

    def _get_basic_strategy_template(self) -> str:
        """Get basic strategy template"""
        return '''
import pandas as pd
import numpy as np
from strategies.enhanced_base_strategy import EnhancedBaseStrategy

class {class_name}(EnhancedBaseStrategy):
    """
    Basic strategy template.
    """
    
    def __init__(self, event_engine, logger, executor_account_name, strategy_id=None, strategy_manager=None, **kwargs):
        super().__init__(event_engine, logger, executor_account_name, strategy_id, strategy_manager, **kwargs)
        
        # Set parameters
        self.params.update({parameters})
    
    def generate_signals(self, data, context=None):
        """Generate trading signals"""
        signals = pd.DataFrame(index=data.index)
        signals['Signal'] = 0
        
        # Implement your strategy logic here
        # Example: Simple price-based signals
        if len(data) >= 2:
            price_change = data['close'].pct_change()
            signals['Signal'] = np.where(price_change > 0.01, 1, 
                                       np.where(price_change < -0.01, -1, 0))
        
        return signals
    
    def description(self):
        return "Basic strategy template"
    
    def parameter_schema(self):
        return {parameters}
'''

    def _get_momentum_strategy_template(self) -> str:
        """Get momentum strategy template"""
        return '''
import pandas as pd
import numpy as np
from strategies.enhanced_base_strategy import EnhancedBaseStrategy

class {class_name}(EnhancedBaseStrategy):
    """
    Momentum strategy template.
    """
    
    def __init__(self, event_engine, logger, executor_account_name, strategy_id=None, strategy_manager=None, **kwargs):
        super().__init__(event_engine, logger, executor_account_name, strategy_id, strategy_manager, **kwargs)
        
        self.lookback_period = self.params.get('lookback_period', 20)
        self.momentum_threshold = self.params.get('momentum_threshold', 0.02)
    
    def generate_signals(self, data, context=None):
        """Generate momentum-based signals"""
        signals = pd.DataFrame(index=data.index)
        signals['Signal'] = 0
        
        if len(data) >= self.lookback_period:
            # Calculate momentum
            momentum = (data['close'] / data['close'].shift(self.lookback_period) - 1)
            
            # Generate signals based on momentum
            signals['Signal'] = np.where(momentum > self.momentum_threshold, 1,
                                       np.where(momentum < -self.momentum_threshold, -1, 0))
        
        return signals
    
    def description(self):
        return "Momentum strategy based on price momentum"
    
    def parameter_schema(self):
        return {{
            "lookback_period": {{"type": "int", "min": 5, "max": 100, "default": 20}},
            "momentum_threshold": {{"type": "float", "min": 0.001, "max": 0.1, "default": 0.02}}
        }}
'''

    def _get_mean_reversion_strategy_template(self) -> str:
        """Get mean reversion strategy template"""
        return '''
import pandas as pd
import numpy as np
from strategies.enhanced_base_strategy import EnhancedBaseStrategy

class {class_name}(EnhancedBaseStrategy):
    """
    Mean reversion strategy template.
    """
    
    def __init__(self, event_engine, logger, executor_account_name, strategy_id=None, strategy_manager=None, **kwargs):
        super().__init__(event_engine, logger, executor_account_name, strategy_id, strategy_manager, **kwargs)
        
        self.lookback_period = self.params.get('lookback_period', 20)
        self.zscore_threshold = self.params.get('zscore_threshold', 2.0)
    
    def generate_signals(self, data, context=None):
        """Generate mean reversion signals"""
        signals = pd.DataFrame(index=data.index)
        signals['Signal'] = 0
        
        if len(data) >= self.lookback_period:
            # Calculate z-score
            rolling_mean = data['close'].rolling(window=self.lookback_period).mean()
            rolling_std = data['close'].rolling(window=self.lookback_period).std()
            zscore = (data['close'] - rolling_mean) / rolling_std
            
            # Generate signals based on z-score
            signals['Signal'] = np.where(zscore > self.zscore_threshold, -1,  # Sell when overbought
                                       np.where(zscore < -self.zscore_threshold, 1, 0))  # Buy when oversold
        
        return signals
    
    def description(self):
        return "Mean reversion strategy based on z-score"
    
    def parameter_schema(self):
        return {{
            "lookback_period": {{"type": "int", "min": 10, "max": 100, "default": 20}},
            "zscore_threshold": {{"type": "float", "min": 1.0, "max": 5.0, "default": 2.0}}
        }}
'''

    def _get_arbitrage_strategy_template(self) -> str:
        """Get arbitrage strategy template"""
        return '''
import pandas as pd
import numpy as np
from strategies.enhanced_base_strategy import EnhancedBaseStrategy

class {class_name}(EnhancedBaseStrategy):
    """
    Arbitrage strategy template.
    """
    
    def __init__(self, event_engine, logger, executor_account_name, strategy_id=None, strategy_manager=None, **kwargs):
        super().__init__(event_engine, logger, executor_account_name, strategy_id, strategy_manager, **kwargs)
        
        self.price_threshold = self.params.get('price_threshold', 0.01)
        self.min_spread = self.params.get('min_spread', 0.005)
    
    def generate_signals(self, data, context=None):
        """Generate arbitrage signals"""
        signals = pd.DataFrame(index=data.index)
        signals['Signal'] = 0
        
        # This is a simplified example - real arbitrage would need multiple instruments
        if len(data) >= 2:
            price_spread = data['close'].diff()
            signals['Signal'] = np.where(price_spread > self.price_threshold, 1,
                                       np.where(price_spread < -self.price_threshold, -1, 0))
        
        return signals
    
    def description(self):
        return "Arbitrage strategy for price discrepancies"
    
    def parameter_schema(self):
        return {{
            "price_threshold": {{"type": "float", "min": 0.001, "max": 0.1, "default": 0.01}},
            "min_spread": {{"type": "float", "min": 0.001, "max": 0.05, "default": 0.005}}
        }}
'''

    def _get_ml_strategy_template(self) -> str:
        """Get ML-based strategy template"""
        return '''
import pandas as pd
import numpy as np
from strategies.enhanced_base_strategy import EnhancedBaseStrategy

class {class_name}(EnhancedBaseStrategy):
    """
    ML-based strategy template.
    """
    
    def __init__(self, event_engine, logger, executor_account_name, strategy_id=None, strategy_manager=None, **kwargs):
        super().__init__(event_engine, logger, executor_account_name, strategy_id, strategy_manager, **kwargs)
        
        self.model_path = self.params.get('model_path', None)
        self.feature_window = self.params.get('feature_window', 20)
        self.prediction_threshold = self.params.get('prediction_threshold', 0.6)
        
        # Load ML model if path provided
        self.model = None
        if self.model_path:
            self._load_model()
    
    def _load_model(self):
        """Load ML model"""
        # Implement model loading logic here
        pass
    
    def generate_signals(self, data, context=None):
        """Generate ML-based signals"""
        signals = pd.DataFrame(index=data.index)
        signals['Signal'] = 0
        
        if len(data) >= self.feature_window and self.model is not None:
            # Extract features
            features = self._extract_features(data)
            
            # Make predictions
            predictions = self.model.predict(features)
            
            # Generate signals based on predictions
            signals['Signal'] = np.where(predictions > self.prediction_threshold, 1,
                                       np.where(predictions < -self.prediction_threshold, -1, 0))
        
        return signals
    
    def _extract_features(self, data):
        """Extract features for ML model"""
        # Implement feature extraction logic here
        features = pd.DataFrame(index=data.index)
        features['returns'] = data['close'].pct_change()
        features['volatility'] = data['close'].rolling(window=10).std()
        features['volume_ratio'] = data['volume'] / data['volume'].rolling(window=20).mean()
        
        return features.fillna(0)
    
    def description(self):
        return "ML-based strategy using machine learning predictions"
    
    def parameter_schema(self):
        return {{
            "model_path": {{"type": "string", "default": ""}},
            "feature_window": {{"type": "int", "min": 10, "max": 100, "default": 20}},
            "prediction_threshold": {{"type": "float", "min": 0.1, "max": 0.9, "default": 0.6}}
        }}
'''