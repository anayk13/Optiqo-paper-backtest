import os
import json
import asyncio
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime 
from pathlib import Path 
import uuid 

from .logger import get_logger
from .broker import BaseBroker
from .event_engine import OrderEvent, FillEvent, EventEngine 



class TradeExecutor:
    """
    Executes trades by interacting with the broker and dispatches FillEvents.
    Also maintains a log of all orders processed for historical reporting.
    """
    def __init__(self,
                 broker_name: str,
                 account_name: str,
                 strategy_name: str,
                 broker: BaseBroker,
                 event_engine: EventEngine): 
        self.broker_name = broker_name
        self.account_name = account_name
        self.strategy_name = strategy_name
        self.broker = broker
        self.event_engine = event_engine 
        self.logger = get_logger(
            main_folder_name="trade_executor",
            broker_name=broker_name,
            account_name=account_name,
            strategy_name=strategy_name
        )
        self.logger.info("TradeExecutor initialized.")
        
        # To store a history of all orders handled by the executor
        # This will be saved to a Parquet file at shutdown.
        self.all_orders: List[Dict[str, Any]] = [] 

    async def on_order_event(self, event: OrderEvent):
        """
        Processes an OrderEvent, sends the order to the broker, and dispatches a FillEvent if successful.
        """
        self.logger.info(f"[{self.strategy_name}] TradeExecutor received OrderEvent: {event.instrument_token} {event.order_type} {event.transaction_type} {event.quantity}@{event.price}")
        
        order_record = event.__dict__.copy() # Copy event attributes
        order_record['timestamp_processed'] = datetime.now() # When TradeExecutor processes it
        order_record['status'] = "PENDING" # Initial status before broker response
        order_record['order_id'] = order_record.get('order_id', str(uuid.uuid4())) 

        try:
            # Send order to the broker 
            # The broker's place_order method is expected to return a dictionary
            # with details including 'status', 'filled_quantity', 'filled_price', 'brokerage', 'timestamp', 'exchange_order_id'.
            broker_order_response = await self.broker.place_order(
                instrument_token=event.instrument_token,
                order_type=event.order_type,
                transaction_type=event.transaction_type,
                quantity=event.quantity,
                price=event.price,
                product=event.product, 
                validity=event.validity,
                trigger_price=event.trigger_price,
                disclosed_quantity=event.disclosed_quantity,
                is_amo=event.is_amo,
                tag=event.tag
            )

            if broker_order_response:
                order_record.update(broker_order_response) # Update record with broker's response
                self.logger.info(f"[{self.strategy_name}] Order placed via broker. Order ID: {order_record['order_id']}, Status: {order_record.get('status')}")
                
                # If the simulated order was filled, generate and dispatch a FillEvent
                if order_record.get("status") == "FILLED":
                    fill_event = FillEvent(
                        order_id=order_record['order_id'],
                        instrument_token=order_record["instrument_token"],
                        exchange_order_id=order_record.get("exchange_order_id", "N/A"),
                        transaction_type=order_record["transaction_type"],
                        quantity=order_record["filled_quantity"],
                        price=order_record["filled_price"],
                        brokerage=order_record.get("brokerage", 0.0), # Assuming brokerage is returned by simulated broker
                        fill_timestamp=order_record.get("timestamp", datetime.now().timestamp()) # Use broker's timestamp or current time
                    )
                    await self.event_engine.put(fill_event)
                    self.logger.info(f"[{self.strategy_name}] FillEvent dispatched for {fill_event.instrument_token}.")
                else:
                    self.logger.warning(f"[{self.strategy_name}] Order {order_record['order_id']} was not filled. Status: {order_record.get('status')}")
            else:
                order_record['status'] = "FAILED"
                self.logger.warning(f"[{self.strategy_name}] Broker did not return a valid response for order {order_record.get('order_id')}.")

        except Exception as e:
            order_record['status'] = "ERROR"
            self.logger.error(f"[{self.strategy_name}] Failed to place order for {event.instrument_token}. Error: {e}", exc_info=True)
        finally:
            self.all_orders.append(order_record)


    async def save_trade_history(self, file_path: str):
        """
        Saves the complete history of all orders processed by the TradeExecutor to a Parquet file.
        """
        if not self.all_orders:
            self.logger.warning("No order history to save for TradeExecutor.")
            return

        try:
            df = pd.DataFrame(self.all_orders)
            
            if 'timestamp_processed' in df.columns:
                df['timestamp_processed'] = pd.to_datetime(df['timestamp_processed'])
            # Convert fill_timestamp to datetime if it's a float timestamp
            if 'fill_timestamp' in df.columns:
                df['fill_timestamp'] = pd.to_datetime(df['fill_timestamp'], unit='s')
            
            current_timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file_path = Path(file_path).parent / f"{Path(file_path).stem}_{current_timestamp_str}.parquet"
            
            output_dir = output_file_path.parent
            output_dir.mkdir(parents=True, exist_ok=True)

            df.to_parquet(output_file_path, index=False)
            self.logger.info(f"TradeExecutor order history saved to {output_file_path}")
        except ImportError:
            self.logger.error("Pandas or PyArrow not installed. Cannot write to Parquet. Please install them: pip install pandas pyarrow")
        except Exception as e:
            self.logger.error(f"Error saving TradeExecutor order history: {e}", exc_info=True)

    async def get_broker_orderbook(self) -> list:
        """Retrieves the broker's current order book."""
        return await self.broker.get_orderbook()