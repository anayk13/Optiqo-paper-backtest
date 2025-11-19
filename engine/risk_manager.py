from typing import Dict, Any
from .broker import BaseBroker 
from .logger import get_logger 

class RiskManager:
    """
    Manages risk assessment before placing orders.
    Validates orders based on available funds, required margins, and other risk rules.
    """

    def __init__(self, broker: BaseBroker):
        self.broker = broker
        self.logger = get_logger(
            main_folder_name="risk_manager",
            broker_name=self.broker.broker_name,
            account_name=self.broker.account_name
        )
    
    async def validate_order(self,
                             exchange_token: str,
                             quantity: int,
                             product: str,
                             transaction_type: str,
                             trade_type: str, # "entry" or "exit"
                             price: float = 0) -> tuple[bool, float, float]:
        """
        Validates an order against available funds, margin requirements, and brokerage.

        Args:
            exchange_token (str): The unique identifier for the instrument.
            quantity (int): The quantity of the instrument.
            product (str): The product type (e.g., 'MIS', 'CNC').
            transaction_type (str): 'BUY' or 'SELL'.
            trade_type (str): 'entry' for opening a new position, 'exit' for closing.
            price (float): The price at which the order is intended to be placed (0 for market).

        Returns:
            tuple[bool, float, float]: A tuple indicating (is_valid, margin_required, brokerage_required).
        """
        self.logger.debug(f"Validating order for {exchange_token}: Qty={quantity}, Type={transaction_type}, Price={price}, TradeType={trade_type}")
        instrument_dict = {
            'exchange_token': exchange_token,
            'quantity': quantity,
            'product': product,
            'transaction_type': transaction_type,
            'price': price
        }
        try:
            margin_required = await self.broker.calculate_margin(instrument_dict=instrument_dict)
            brokerage_required = await self.broker.calculate_brokerage(instrument_dict=instrument_dict)
            available_margin = await self.broker.get_funds_and_margin()

            if trade_type.lower() == 'entry': 
                total_cost = margin_required + brokerage_required
                self.logger.debug(f"Entry validation: Margin={margin_required:.2f}, Brokerage={brokerage_required:.2f}, Total Cost={total_cost:.2f}, Available Funds={available_margin:.2f}")
                if available_margin >= total_cost: # Use >= to allow exact matches
                    self.logger.info(f'Order for {instrument_dict["exchange_token"]} (Entry): Validated. Margin: {margin_required}, Brokerage: {brokerage_required}. Available Funds: {available_margin}')
                    return True, margin_required, brokerage_required
                else:
                    self.logger.warning(f'Order for {instrument_dict["exchange_token"]} (Entry): Validation FAILED. Insufficient funds. Required: {total_cost}, Available: {available_margin}')
                    return False, margin_required, brokerage_required
            elif trade_type.lower() == 'exit':
                # For exit, typically only brokerage and minor charges are needed,
                # assuming the position covers any margin initially blocked.
                if available_margin >= brokerage_required: # Use >= to allow exact matches
                    self.logger.info(f'Order for {instrument_dict["exchange_token"]} (Exit): Validated. Brokerage: {brokerage_required}. Available Funds: {available_margin}')
                    return True, margin_required, brokerage_required # margin_required might be 0 for exit
                else:
                    self.logger.warning(f'Order for {instrument_dict["exchange_token"]} (Exit): Validation FAILED. Insufficient funds for brokerage. Required: {brokerage_required}, Available: {available_margin}')
                    return False, margin_required, brokerage_required
            else:
                self.logger.error(f'Order Validation failed due to incorrect trade_type: {trade_type}. Must be "entry" or "exit".')
                return False, 0.0, 0.0

        except Exception as e:
            error_msg = f"Error occurred while validating order for {instrument_dict.get('exchange_token')}: {e}"
            self.logger.error(error_msg, exc_info=True)
            return False, 0.0, 0.0