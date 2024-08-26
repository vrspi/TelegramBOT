import MetaTrader5 as mt5
import logging

class MT5Service:
    # Add these constants at the beginning of the class
    TRADE_ACTION_DEAL = mt5.TRADE_ACTION_DEAL
    TRADE_ACTION_SLTP = mt5.TRADE_ACTION_SLTP
    ORDER_TYPE_BUY = mt5.ORDER_TYPE_BUY
    ORDER_TYPE_SELL = mt5.ORDER_TYPE_SELL
    ORDER_TIME_GTC = mt5.ORDER_TIME_GTC
    TRADE_RETCODE_DONE = mt5.TRADE_RETCODE_DONE

    def __init__(self):
        self.is_initialized = mt5.initialize()
        if not self.is_initialized:
            logging.error("Failed to initialize MT5.")
        else:
            logging.info("MT5 initialized successfully.")

    def send_order(self, request):
        if not self.is_initialized:
            logging.error("Cannot send order: MT5 is not initialized.")
            return None

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Failed to send order: {result}")
            return None
        else:
            logging.info(f"Order executed successfully: {result}")
        return result

    def close_order(self, ticket):
        if not self.is_initialized:
            logging.error("Cannot close order: MT5 is not initialized.")
            return None

        trade = mt5.positions_get(ticket=ticket)
        if not trade:
            logging.error(f"Failed to retrieve the open trade details for ticket {ticket}.")
            return None
        
        trade = trade[0]  # Assuming only one trade for the given ticket
        symbol = trade.symbol
        trade_type = mt5.ORDER_TYPE_SELL if trade.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": trade.volume,
            "type": trade_type,
            "position": trade.ticket,
            "deviation": 20,
            "magic": 234000,
            "comment": "Auto-close trade",
        }
        
        result = self.send_order(request)
        if result:
            logging.info(f"Trade on {symbol} closed successfully.")
        else:
            logging.error(f"Failed to close trade on {symbol}.")
        return result
    
    def get_open_positions(self):
        positions = mt5.positions_get()
        open_positions = []
        if positions:
            for pos in positions:
                open_positions.append({
                    "symbol": pos.symbol,
                    "type": "Buy" if pos.type == mt5.ORDER_TYPE_BUY else "Sell",
                    "volume": pos.volume,
                    "price": pos.price_open,
                    "profit": pos.profit
                })
        return open_positions
    
    def get_symbol_info(self, symbol):
        if not self.is_initialized:
            logging.error("Cannot get symbol info: MT5 is not initialized.")
            return None

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Failed to get symbol info for {symbol}.")
        return symbol_info

    def get_open_position(self, ticket):
        if not self.is_initialized:
            logging.error("Cannot get open position: MT5 is not initialized.")
            return None

        positions = mt5.positions_get(ticket=ticket)
        if positions:
            return positions[0]
        else:
            logging.error(f"Failed to retrieve open position for ticket {ticket}.")
            return None

    def get_account_info(self):
        if not self.is_initialized:
            logging.error("Cannot get account info: MT5 is not initialized.")
            return None

        account_info = mt5.account_info()
        if account_info is None:
            logging.error("Failed to retrieve account information.")
            return None

        return {
            "balance": account_info.balance,
            "equity": account_info.equity,
            "margin": account_info.margin,
            "free_margin": account_info.margin_free
        }

    def close_position(self, ticket, volume):
        if not self.is_initialized:
            logging.error("Cannot close position: MT5 is not initialized.")
            return None

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logging.error(f"Failed to retrieve position for ticket {ticket}.")
            return None

        position = position[0]
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,
            "deviation": 20,
            "magic": 234000,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        result = mt5.order_send(request)
        if result is None:
            logging.error("Failed to close position: No result returned")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Failed to close position: {result.comment}")
        return result

    def modify_position(self, ticket):
        if not self.is_initialized:
            logging.error("Cannot modify position: MT5 is not initialized.")
            return None

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logging.error(f"Failed to retrieve position for ticket {ticket}.")
            return None

        position = position[0]
        symbol_info = mt5.symbol_info(position.symbol)
        if symbol_info is None:
            logging.error(f"Failed to retrieve symbol info for {position.symbol}")
            return None

        point = symbol_info.point
        digits = symbol_info.digits

        current_price = mt5.symbol_info_tick(position.symbol).ask if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).bid

        # Set SL and TP distances (300 pips for SL, 1100 pips for TP)
        sl_distance = 3000 * point  # 300 pips
        tp_distance = 11000 * point  # 1100 pips

        if position.type == mt5.ORDER_TYPE_BUY:
            sl = current_price - sl_distance
            tp = current_price + tp_distance
        else:  # SELL
            sl = current_price + sl_distance
            tp = current_price - tp_distance

        sl = round(sl, digits)
        tp = round(tp, digits)

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "sl": sl,
            "tp": tp,
        }

        logging.info(f"Sending modify position request: {request}")
        result = mt5.order_send(request)
        
        if result is None:
            last_error = mt5.last_error()
            logging.error(f"Failed to modify position: No result returned. Last error: {last_error}")
            return None
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Failed to modify position: {result.comment}. Retcode: {result.retcode}")
        else:
            logging.info(f"Position modified successfully: {result}")
        
        return result

    def get_current_price(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logging.error(f"Failed to get current price for {symbol}")
            return None
        return (tick.bid + tick.ask) / 2

    def get_open_positions(self, symbol):
        if not self.is_initialized:
            logging.error("Cannot get open positions: MT5 is not initialized.")
            return []
        
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            logging.error(f"Failed to retrieve open positions for {symbol}")
            return []
        
        return [position.ticket for position in positions]