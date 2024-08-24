import MetaTrader5 as mt5
import logging

class MT5Service:
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

        trade = mt5.positions_get(ticket=ticket)
        if not trade:
            logging.error(f"Failed to retrieve open position for ticket {ticket}.")
            return None
        return trade[0]  # Assuming only one position per ticket

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
