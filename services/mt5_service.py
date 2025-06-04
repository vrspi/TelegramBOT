import MetaTrader5 as mt5
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any
import pandas as pd

class MT5Service:
    TRADE_RETCODE_DONE = 10009
    
    def __init__(self):
        self.initialize_mt5()
        
    def initialize_mt5(self) -> bool:
        """Initialize connection to MetaTrader 5."""
        if not mt5.initialize():
            logging.error("Failed to initialize MT5")
            return False
        return True
        
    def get_account_info(self) -> Dict:
        """Get current account information."""
        account_info = mt5.account_info()
        if not account_info:
            logging.error("Failed to get account info")
            return {}
            
        return {
            "balance": account_info.balance,
            "equity": account_info.equity,
            "margin": account_info.margin,
            "free_margin": account_info.margin_free,
            "margin_level": account_info.margin_level if account_info.margin_level else 0.0
        }
        
    def get_market_context(self, symbol: str) -> Dict:
        """Get current market context for a symbol."""
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {symbol}")
            return {}
            
        last_tick = mt5.symbol_info_tick(symbol)
        if not last_tick:
            logging.error(f"Failed to get last tick for {symbol}")
            return {}
            
        return {
            "symbol": symbol,
            "bid": last_tick.bid,
            "ask": last_tick.ask,
            "spread": (last_tick.ask - last_tick.bid) / symbol_info.point,
            "volume": last_tick.volume,
            "time": datetime.fromtimestamp(last_tick.time).strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_rates(self, symbol: str, timeframe: int, num_bars: int):
        """Retrieve recent price bars for a symbol."""
        if not mt5.initialize():
            logging.error("Failed to initialize MT5")
            return []

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
        if rates is None:
            logging.error(f"Failed to copy rates for {symbol}")
            return []

        return pd.DataFrame(rates)
        
    def open_position(self, symbol: str, order_type: str, volume: float,
                     price: Optional[float] = None, sl: Optional[float] = None,
                     tp: Optional[float] = None) -> Optional[Dict]:
        """Open a new position with proper filling mode handling."""
        if not mt5.initialize():
            logging.error("Failed to initialize MT5")
            return None
            
        # Select the symbol in the Market Watch
        if not mt5.symbol_select(symbol, True):
            logging.error(f"Failed to select {symbol} in Market Watch")
            return None

        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {symbol}")
            return None

        # Get current price if not specified
        if price is None:
            tick = mt5.symbol_info_tick(symbol)
            price = tick.ask if order_type.lower() == "buy" else tick.bid

        # Get appropriate filling mode
        filling_type = self._get_filling_type(symbol)
        if filling_type is None:
            logging.error(f"Failed to determine filling type for {symbol}")
            return None

        # Prepare the trade request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if order_type.lower() == "buy" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "python script open",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp

        # Check the order before sending
        check_result = mt5.order_check(request)
        if check_result is None:
            logging.error("Order check failed")
            return None
            
        if check_result.retcode != 0:
            logging.error(f"Order check failed: {check_result.comment}, code: {check_result.retcode}")
            return None

        # Try to send the order
        max_retries = 3
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result is None:
                logging.error("order_send() failed, no result returned")
                continue
                
            if result.retcode == self.TRADE_RETCODE_DONE:
                logging.info(f"Trade executed successfully: {result.comment}")
                return {
                    "ticket": result.order,
                    "volume": volume,
                    "price": result.price,
                    "comment": "Position opened successfully"
                }
            elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                # Update price and retry
                tick = mt5.symbol_info_tick(symbol)
                new_price = tick.ask if order_type.lower() == "buy" else tick.bid
                request["price"] = new_price
                logging.info(f"Requote received, retrying with new price: {new_price}")
                continue
            else:
                logging.error(f"Failed to open position: {result.comment}, code: {result.retcode}")
                break
                
        return None

    def _get_filling_type(self, symbol: str) -> Optional[int]:
        """Determine the appropriate filling type for the symbol."""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None
            
        # Get the filling mode flags
        filling_mode = symbol_info.filling_mode
        logging.info(f"Symbol {symbol} filling mode flags: {filling_mode}")
        
        # Try all possible filling modes
        if filling_mode & mt5.ORDER_FILLING_FOK:
            logging.info(f"Using FOK filling mode for {symbol}")
            return mt5.ORDER_FILLING_FOK
        elif filling_mode & mt5.ORDER_FILLING_IOC:
            logging.info(f"Using IOC filling mode for {symbol}")
            return mt5.ORDER_FILLING_IOC
        elif filling_mode & mt5.ORDER_FILLING_RETURN:
            logging.info(f"Using RETURN filling mode for {symbol}")
            return mt5.ORDER_FILLING_RETURN
        else:
            # If no specific filling mode is supported, try each one
            for mode in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": 0.01,  # Minimum volume for testing
                    "type": mt5.ORDER_TYPE_BUY,
                    "price": mt5.symbol_info_tick(symbol).ask,
                    "type_time": mt5.ORDER_TIME_GTC
                }
                
                result = mt5.order_check(request)
                if result and result.retcode == 0:
                    logging.info(f"Found working filling mode for {symbol}: {mode}")
                    return mode
                    
            logging.error(f"No supported filling mode found for {symbol}")
            return mt5.ORDER_FILLING_RETURN  # Last resort default
            
    def close_position(self, ticket: int) -> bool:
        """Close a specific position with proper filling mode handling."""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logging.error(f"Position {ticket} not found")
            return False
            
        position = position[0]
        
        # Select the symbol in the Market Watch
        if not mt5.symbol_select(position.symbol, True):
            logging.error(f"Failed to select {position.symbol} in Market Watch")
            return False

        # Get appropriate filling mode
        filling_type = self._get_filling_type(position.symbol)
        if filling_type is None:
            logging.error(f"Failed to determine filling type for {position.symbol}")
            return False

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,
            "deviation": 20,
            "magic": 234000,
            "comment": "python script close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }
        
        # Try to send the order with retries
        max_retries = 3
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result is None:
                logging.error("order_send() failed, no result returned")
                continue
                
            if result.retcode == self.TRADE_RETCODE_DONE:
                return True
            elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                # Update price and retry
                new_price = mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask
                request["price"] = new_price
                continue
            else:
                logging.error(f"Failed to close position: {result.comment}, code: {result.retcode}")
                break
                
        return False
        
    def modify_position(self, ticket: int, sl: Optional[float] = None,
                       tp: Optional[float] = None) -> Optional[Dict]:
        """Modify an existing position's stop loss and/or take profit with proper error handling."""
        if not mt5.initialize():
            logging.error("Failed to initialize MT5")
            return None
            
        # Get position information
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logging.error(f"Position {ticket} not found")
            return None
            
        position = position[0]
        
        # Select the symbol in Market Watch
        if not mt5.symbol_select(position.symbol, True):
            logging.error(f"Failed to select {position.symbol} in Market Watch")
            return None
            
        # Get symbol information
        symbol_info = mt5.symbol_info(position.symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {position.symbol}")
            return None
            
        # Prepare modification request
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "magic": 234000,
            "sl": sl if sl is not None else position.sl,
            "tp": tp if tp is not None else position.tp
        }
        
        # Check if the modification would be valid
        check_result = mt5.order_check(request)
        if check_result is None:
            logging.error("Order check failed for position modification")
            return None
            
        if check_result.retcode != 0:
            logging.error(f"Position modification check failed: {check_result.comment}, code: {check_result.retcode}")
            return None
            
        # Try to modify the position
        max_retries = 3
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result is None:
                logging.error("order_send() failed for position modification, no result returned")
                continue
                
            if result.retcode == self.TRADE_RETCODE_DONE:
                logging.info(f"Successfully modified position {ticket}")
                return {
                    "ticket": ticket,
                    "new_sl": sl if sl is not None else position.sl,
                    "new_tp": tp if tp is not None else position.tp,
                    "comment": "Position modified successfully"
                }
            elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                # For SL/TP modifications, we don't need to handle requotes
                continue
            else:
                error_message = f"Failed to modify position: {result.comment}, code: {result.retcode}"
                logging.error(error_message)
                
                # Check for specific error codes and provide more detailed information
                if result.retcode == mt5.TRADE_RETCODE_INVALID_STOPS:
                    current_price = mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask
                    min_stop_level = symbol_info.trade_stops_level * symbol_info.point
                    logging.error(f"Invalid stop levels. Current price: {current_price}, Min stop level: {min_stop_level} points")
                elif result.retcode == mt5.TRADE_RETCODE_INVALID:
                    logging.error("Invalid parameters for position modification")
                elif result.retcode == mt5.TRADE_RETCODE_FROZEN:
                    logging.error("Position is frozen and cannot be modified")
                    
                break
                
        return None
            
    def get_position(self, ticket: int) -> Optional[Dict]:
        """Get information about a specific position."""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return None
            
        position = position[0]
        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "price": position.price_open,
            "sl": position.sl,
            "tp": position.tp,
            "profit": position.profit,
            "type": "buy" if position.type == mt5.ORDER_TYPE_BUY else "sell"
        }
        
    def get_all_positions(self) -> List[Dict]:
        """Get all open positions."""
        positions = mt5.positions_get()
        if not positions:
            return []
            
        return [{
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "price": pos.price_open,
            "sl": pos.sl,
            "tp": pos.tp,
            "profit": pos.profit,
            "type": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell"
        } for pos in positions]
        
    def __del__(self):
        """Cleanup when the service is destroyed."""
        mt5.shutdown()