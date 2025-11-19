import asyncio
from db.models import Event, EventType 

def create_signal_handler(strategy, broker, portfolio, logger, market_prices, event_engine):
    async def handle_signal_event(event: Event):
        try:
            signal = event.data
            tick = signal.pop("tick", {}) # Extract tick data passed with signal
            
            # For simplicity, assuming a signal directly implies a market order
            order_details = await broker.place_order(signal=signal, tick=tick)
            
            if order_details and order_details.get("status") == "FILLED":
                # Fire an ORDER_FILLED event
                await event_engine.put(Event(EventType.ORDER_FILLED, {
                    "order": order_details,
                    "tick": tick # Pass the original tick data for context
                }))
            else:
                # Log rejected or error orders
                logger.log_order({"type": "ORDER_REJECTED", "signal": signal, "response": order_details})
                print(f"⚠️ Order Rejected/Error: {order_details.get('message', 'Unknown error')}")

        except Exception as e:
            print(f" Error in Signal Handler: {e}")
            import traceback
            traceback.print_exc()

    return handle_signal_event