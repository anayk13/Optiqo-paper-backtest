import polars as pl
from .logger import get_logger 
from typing import Dict, Any, List
from abc import ABC, abstractmethod
import asyncio
import uuid
import time
import random

class BaseBroker(ABC):
    """
    BaseBroker: Abstract base class for all brokers.
    Shared functionality and common interface for broker implementations.
    """
    def __init__(self, account_name: str) -> None:
        self.account_name = account_name
        self.logger = get_logger(main_folder_name="broker", broker_name="BaseBroker", account_name=account_name)
    
    @abstractmethod
    async def initialize(self):
        """Initialize the broker-specific configuration or connection."""
        pass

    @abstractmethod
    async def master_scrip(self, mode:str):
        """" Download the masterscrip file for the broker """
        pass

    @abstractmethod
    async def place_order(self, **kwargs) -> Dict[str, Any]:
        """Place an order."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        pass

    @abstractmethod
    async def modify_order(self, **kwargs) -> Dict[str, Any]:
        """Modify an existing order."""
        pass

    @abstractmethod
    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Get details of an order."""
        pass

    @abstractmethod
    async def get_orderbook(self) -> List[Dict[str, Any]]:
        """Get orderbook"""
        pass

    @abstractmethod
    async def historical_data(self, **kwargs) -> pl.DataFrame:
        """Fetch historical data."""
        pass

    @abstractmethod
    async def get_funds_and_margin(self, segment: str = None) -> float:
        """Fetch available balance in the account"""
        pass

    @abstractmethod
    async def expiry_dates(self, exchange_token: str) -> List:
        ''' Gets the expiry dates for the given exchange token'''
        pass

    @abstractmethod
    async def option_chain(self, exchange_token:str, expiry_date: str = None) -> dict:
        """ Fetch the option chain for the given exchange token"""
        pass

    @abstractmethod
    async def ltp_quote(self, exchange_token: str) -> float:
        """Fetch LTP quote."""
        pass

    @abstractmethod
    async def ohlc_quote(self, exchange_token: str, interval: str) -> dict:
        """Fetch OHLC quote."""
        pass

    @abstractmethod
    async def full_market_quote(self, exchange_token: str) -> dict:
        """Fetch full market quote."""
        pass
    
    @abstractmethod
    async def calculate_margin(self, instrument_dict: Dict[str, Any]) -> float:
        """Fetch required margin for the trade"""
        pass

    @abstractmethod
    async def calculate_brokerage(self, instrument_dict: Dict[str, Any]) -> float:
        """Fetch required brokerage for the trade"""
        pass

    @abstractmethod
    async def market_holidays(self) -> pl.DataFrame:
        """Fetch market holidays"""
        pass

    @abstractmethod
    async def get_trade_book(self) -> Dict:
        """Fetch array of all trades executed for the day"""
        pass

class SimulatedBroker(BaseBroker):
    """
    SimulatedBroker: Implements the BaseBroker for paper trading simulation.
    It simulates order placement, cancellation, modification, and fill based on
    predefined slippage and fill chances.
    """
    def __init__(self, account_name: str, slippage_percent: float = 0.0, fill_chance: float = 1.0):
        super().__init__(account_name)
        self.broker_name = 'Simulated'
        self.orders: Dict[str, Dict[str, Any]] = {}  # Stores active orders
        self.trades: List[Dict[str, Any]] = []    # Stores filled trades
        self.slippage_percent = slippage_percent
        self.fill_chance = fill_chance
        self.logger = get_logger(main_folder_name="broker", broker_name="SimulatedBroker", account_name=account_name)
        self.initial_funds = 1000000.0
        self.current_funds = self.initial_funds
        self.logger.info(f"SimulatedBroker initialized for {account_name} with {self.initial_funds} funds, slippage: {slippage_percent}%, fill chance: {fill_chance*100}%")

    async def initialize(self):
        """Simulated initialization, does nothing for paper trading."""
        self.logger.info("SimulatedBroker: Initialized connection.")
        return self

    async def master_scrip(self, mode: str):
        """Simulated master scrip download."""
        self.logger.info("SimulatedBroker: Master scrip downloaded (simulated).")
        # Return dummy data or an empty DataFrame for simulation
        return pl.DataFrame({
            "instrument_token": ["NSE_FO_5210_1", "NSE_EQ_INFY"],
            "symbol": ["NIFTY25FEB", "INFY"],
            "name": ["NIFTY FUTURES", "INFOSYS LTD"],
            "exchange": ["NSE", "NSE"],
            "instrument_type": ["FUT", "EQ"]
        })

    async def place_order(self,
                          instrument_token: str,
                          transaction_type: str,
                          quantity: int,
                          product: str,
                          validity: str,
                          order_type: str = 'MARKET',
                          price: float = 0,
                          trigger_price: float = 0,
                          disclosed_quantity: int = 0,
                          is_amo: bool = False,
                          tag: str = '') -> Dict[str, Any]:
        """
        Simulates placing an order.
        For MARKET orders, it simulates an immediate fill.
        For LIMIT orders, it logs the order but doesn't fill immediately.
        """
        order_id = str(uuid.uuid4())
        order_details = {
            "order_id": order_id,
            "instrument_token": instrument_token,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "product": product,
            "validity": validity,
            "order_type": order_type,
            "price": price,
            "trigger_price": trigger_price,
            "disclosed_quantity": disclosed_quantity,
            "is_amo": is_amo,
            "tag": tag,
            "status": "PENDING", # Could be PENDING, FILLED, CANCELLED, REJECTED
            "timestamp": time.time(),
            "exchange_order_id": None,
            "filled_quantity": 0,
            "filled_price": 0.0
        }
        self.orders[order_id] = order_details
        self.logger.info(f"Simulated order placed: {order_details}")

        # Simulate immediate fill for MARKET orders (or with a chance for LIMIT if matched)
        if order_type.upper() == 'MARKET' and random.random() <= self.fill_chance:
            fill_price = price if price > 0 else (random.uniform(99, 101) / 100 * order_details["price"] if order_details["price"] > 0 else 100) # Simple fill price logic
            
            # Apply slippage
            slippage_amount = fill_price * (self.slippage_percent / 100)
            if transaction_type.upper() == 'BUY':
                fill_price += slippage_amount
            else: # SELL
                fill_price -= slippage_amount
            fill_price = round(fill_price, 2)

            brokerage = await self.calculate_brokerage(order_details)
            trade_value = fill_price * quantity
            
            if transaction_type.upper() == 'BUY':
                cost = trade_value + brokerage
                if self.current_funds >= cost:
                    self.current_funds -= cost
                    order_details["status"] = "FILLED"
                    order_details["filled_quantity"] = quantity
                    order_details["filled_price"] = fill_price
                    order_details["exchange_order_id"] = str(uuid.uuid4())
                    fill_event = {
                        "order_id": order_id,
                        "instrument_token": instrument_token,
                        "exchange_order_id": order_details["exchange_order_id"],
                        "transaction_type": transaction_type,
                        "quantity": quantity,
                        "price": fill_price,
                        "brokerage": brokerage,
                        "fill_timestamp": time.time()
                    }
                    self.trades.append(fill_event)
                    self.logger.info(f"Simulated order {order_id} filled. Fill Price: {fill_price}, Brokerage: {brokerage}, Remaining Funds: {self.current_funds}")
                else:
                    order_details["status"] = "REJECTED"
                    self.logger.warning(f"Simulated order {order_id} rejected due to insufficient funds. Funds: {self.current_funds}, Cost: {cost}")
            elif transaction_type.upper() == 'SELL':
                revenue = trade_value - brokerage
                self.current_funds += revenue
                order_details["status"] = "FILLED"
                order_details["filled_quantity"] = quantity
                order_details["filled_price"] = fill_price
                order_details["exchange_order_id"] = str(uuid.uuid4())
                fill_event = {
                    "order_id": order_id,
                    "instrument_token": instrument_token,
                    "exchange_order_id": order_details["exchange_order_id"],
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "price": fill_price,
                    "brokerage": brokerage,
                    "fill_timestamp": time.time()
                }
                self.trades.append(fill_event)
                self.logger.info(f"Simulated order {order_id} filled. Fill Price: {fill_price}, Brokerage: {brokerage}, Remaining Funds: {self.current_funds}")
        elif order_type.upper() == 'LIMIT':
            self.logger.info(f"Simulated LIMIT order {order_id} placed. Awaiting fill conditions.")
        else:
            order_details["status"] = "REJECTED"
            self.logger.warning(f"Simulated order {order_id} rejected (fill chance missed or unsupported order type).")


        return order_details

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Simulates cancelling an order."""
        if order_id in self.orders and self.orders[order_id]["status"] == "PENDING":
            self.orders[order_id]["status"] = "CANCELLED"
            self.logger.info(f"Simulated order {order_id} cancelled.")
            return {"status": "success", "order_id": order_id}
        self.logger.warning(f"Simulated order {order_id} not found or not in PENDING state for cancellation.")
        return {"status": "failed", "message": "Order not found or cannot be cancelled"}

    async def modify_order(self, **kwargs) -> Dict[str, Any]:
        """Simulates modifying an order."""
        order_id = kwargs.get("order_id")
        if order_id in self.orders and self.orders[order_id]["status"] == "PENDING":
            self.orders[order_id].update(kwargs) 
            self.logger.info(f"Simulated order {order_id} modified: {kwargs}")
            return {"status": "success", "order_id": order_id}
        self.logger.warning(f"Simulated order {order_id} not found or not in PENDING state for modification.")
        return {"status": "failed", "message": "Order not found or cannot be modified"}

    async def get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Retrieves simulated order details."""
        return self.orders.get(order_id, {})

    async def get_orderbook(self) -> List[Dict[str, Any]]:
        """Retrieves the simulated order book."""
        return list(self.orders.values())

    async def historical_data(self, **kwargs) -> pl.DataFrame:
        """Simulated historical data fetching."""
        self.logger.info(f"Simulated historical data fetch for {kwargs.get('exchange_token')}.")
        return pl.DataFrame({
            "datetime": [
                datetime.datetime.now() - datetime.timedelta(days=1),
                datetime.datetime.now()
            ],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1200]
        })

    async def get_funds_and_margin(self, segment: str = None) -> float:
        """Returns simulated available funds."""
        self.logger.info(f"SimulatedBroker: Current funds: {self.current_funds}")
        return self.current_funds

    async def expiry_dates(self, exchange_token: str) -> List:
        """Simulated expiry dates."""
        return [str(datetime.date.today() + datetime.timedelta(days=30))]

    async def option_chain(self, exchange_token: str, expiry_date: str = None) -> dict:
        """Simulated option chain."""
        return {"calls": [], "puts": []}

    async def ltp_quote(self, exchange_token: str) -> float:
        """Simulated LTP quote."""
        return 100.0 

    async def ohlc_quote(self, exchange_token: str, interval: str) -> dict:
        """Simulated OHLC quote."""
        return {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0}

    async def full_market_quote(self, exchange_token: str) -> dict:
        """Simulated full market quote."""
        return {"ltp": 100.0, "bid": 99.9, "ask": 100.1, "volume": 10000}
    
    async def calculate_margin(self, instrument_dict: Dict[str, Any]) -> float:
        """Simulated margin calculation."""
        price = instrument_dict.get('price', 0)
        quantity = instrument_dict.get('quantity', 0)
        return (price * quantity) * 0.1

    async def calculate_brokerage(self, instrument_dict: Dict[str, Any]) -> float:
        """Simulated brokerage calculation (flat fee)."""
        return 20.0 

    async def market_holidays(self) -> pl.DataFrame:
        """Simulated market holidays."""
        return pl.DataFrame({"date": [], "description": []})

    async def get_trade_book(self) -> Dict:
        """Returns simulated trade book."""
        return {"trades": self.trades}