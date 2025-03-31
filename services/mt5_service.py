import MetaTrader5 as mt5
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any

class MT5Service:
    TRADE_RETCODE_DONE = 10009
    
    def __init__(self):
        self.initialize_mt5()
        # Add symbol standardization mapping for IC Markets
        # IC Markets may use suffix for metals like XAUUSD.a
        self.symbol_map = {
            "XAUUSD": "XAUUSD",
            "Gold": "XAUUSD"
        }
        self.detect_gold_symbol()
        
    def initialize_mt5(self) -> bool:
        """Initialize connection to MetaTrader 5."""
        if not mt5.initialize():
            logging.error("Failed to initialize MT5")
            return False
            
        # Verify we can trade
        terminal_info = mt5.terminal_info()
        if not terminal_info.trade_allowed:
            logging.warning("AutoTrading is disabled in MT5 terminal. Enable it to trade.")
            logging.warning("Go to Tools > Options > Expert Advisors and enable 'Allow automated trading'")
            logging.warning("Also ensure the Algo Trading button on toolbar is enabled (green)")
            
        # Log account information
        account_info = mt5.account_info()
        if account_info:
            logging.info(f"Connected to account: {account_info.login} ({account_info.server})")
            logging.info(f"Account balance: {account_info.balance}, Leverage: 1:{account_info.leverage}")
            logging.info(f"Trade allowed: {account_info.trade_allowed}")
        else:
            logging.error("Could not retrieve account information")
            
        return True
    
    def detect_gold_symbol(self):
        """Detect the correct symbol name for gold on this broker."""
        # Try different possible symbol names for gold
        possible_symbols = ["XAUUSD", "XAUUSD.a", "GOLD", "GOLD.a"]
        
        for symbol in possible_symbols:
            if mt5.symbol_select(symbol, True):
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info and symbol_info.visible:
                    logging.info(f"Found working gold symbol: {symbol}")
                    # Update the symbol map with the correct symbol
                    self.symbol_map = {
                        "XAUUSD": symbol,
                        "Gold": symbol
                    }
                    
                    # Log symbol details
                    logging.info(f"Symbol properties: spread={symbol_info.spread}, digits={symbol_info.digits}")
                    logging.info(f"Symbol trade mode: {symbol_info.trade_mode}")
                    logging.info(f"Symbol filling modes: {symbol_info.filling_mode}")
                    logging.info(f"Symbol stop level: {symbol_info.trade_stops_level} points")
                    
                    # Test getting current price
                    tick = mt5.symbol_info_tick(symbol)
                    if tick:
                        logging.info(f"Current {symbol} price: bid={tick.bid}, ask={tick.ask}")
                    
                    return
        
        logging.warning("Could not find a valid gold symbol. Please check Market Watch.")
        
    def standardize_symbol(self, symbol: str) -> str:
        """Standardize symbol name to match broker requirements."""
        return self.symbol_map.get(symbol, symbol)
        
    def get_account_info(self) -> Dict:
        """Get current account information."""
        account_info = mt5.account_info()
        if not account_info:
            logging.error("Failed to get account info")
            return {
                "balance": 0.0,
                "equity": 0.0,
                "margin": 0.0,
                "free_margin": 0.0,
                "margin_level": 0.0
            }
            
        return {
            "balance": account_info.balance,
            "equity": account_info.equity,
            "margin": account_info.margin,
            "free_margin": account_info.margin_free,
            "margin_level": account_info.margin_level if account_info.margin_level else 0.0
        }
        
    def get_market_context(self, symbol: str) -> Dict:
        """Get current market context for a symbol."""
        # Apply symbol standardization
        symbol = self.standardize_symbol(symbol)
        
        # Ensure the symbol is selected
        if not mt5.symbol_select(symbol, True):
            logging.warning(f"Failed to select {symbol}, trying alternatives...")
            # Try detect_gold_symbol again
            self.detect_gold_symbol()
            symbol = self.standardize_symbol(symbol)
            if not mt5.symbol_select(symbol, True):
                logging.error(f"Could not select {symbol} or any alternative")
                return {}
        
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
        
    def check_margin_for_trade(self, symbol: str, volume: float, order_type: int) -> Dict:
        """Check if there's enough margin for the specified trade."""
        symbol = self.standardize_symbol(symbol)
        
        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            return {"result": False, "message": f"Failed to select {symbol} in Market Watch"}
            
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {"result": False, "message": f"Failed to get price for {symbol}"}
            
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        
        # Calculate required margin
        margin = mt5.order_calc_margin(order_type, symbol, volume, price)
        if margin is None:
            return {"result": False, "message": "Failed to calculate margin requirement"}
            
        # Get account free margin
        account_info = mt5.account_info()
        if not account_info:
            return {"result": False, "message": "Failed to get account information"}
            
        free_margin = account_info.margin_free
        
        # Check if we have enough margin (with 10% buffer)
        if margin * 1.1 > free_margin:
            return {
                "result": False,
                "message": f"Insufficient margin: {margin:.2f} required (plus buffer), {free_margin:.2f} available",
                "margin_required": margin,
                "free_margin": free_margin
            }
            
        return {
            "result": True,
            "message": f"Margin check passed: {margin:.2f} required, {free_margin:.2f} available",
            "margin_required": margin,
            "free_margin": free_margin
        }
        
    def get_supported_filling_modes(self, symbol: str) -> List[int]:
        """Get supported filling modes for a symbol."""
        symbol = self.standardize_symbol(symbol)
        
        # Ensure symbol is selected
        if not mt5.symbol_select(symbol, True):
            logging.error(f"Failed to select {symbol} in Market Watch")
            return [mt5.ORDER_FILLING_IOC]  # Default to IOC as fallback
            
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {symbol}")
            return [mt5.ORDER_FILLING_IOC]
            
        filling_mode = symbol_info.filling_mode
        
        result = []
        if filling_mode & mt5.ORDER_FILLING_FOK:
            result.append(mt5.ORDER_FILLING_FOK)
        if filling_mode & mt5.ORDER_FILLING_IOC:
            result.append(mt5.ORDER_FILLING_IOC)
        if filling_mode & mt5.ORDER_FILLING_RETURN:
            result.append(mt5.ORDER_FILLING_RETURN)
            
        # If no filling modes were detected, default to IOC which works on most brokers
        if not result:
            logging.warning(f"No filling modes detected for {symbol}, defaulting to IOC")
            result.append(mt5.ORDER_FILLING_IOC)
            
        return result
        
    def open_position(self, symbol: str, order_type: str, volume: float,
                     price: Optional[float] = None, sl: Optional[float] = None,
                     tp: Optional[float] = None) -> Optional[Dict]:
        """Open a new position with proper filling mode handling."""
        try:
            if not mt5.initialize():
                logging.error("Failed to initialize MT5")
                return None
                
            # Check account permissions
            account_info = mt5.account_info()
            if not account_info or not account_info.trade_allowed:
                logging.error("Trading not allowed. Check if you're using investor password or autotrading is disabled")
                return None
                
            # Check terminal permissions
            terminal_info = mt5.terminal_info()
            if not terminal_info.trade_allowed:
                logging.error("AutoTrading is disabled in MT5 terminal. Enable it to trade.")
                return None
                
            # Standardize symbol name
            symbol = self.standardize_symbol(symbol)
            
            # Select the symbol in the Market Watch
            if not mt5.symbol_select(symbol, True):
                logging.error(f"Failed to select {symbol} in Market Watch")
                # Try with detect_gold_symbol again
                self.detect_gold_symbol()
                symbol = self.standardize_symbol(symbol)
                if not mt5.symbol_select(symbol, True):
                    logging.error(f"Could not select {symbol} or any alternative")
                    return None

            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                logging.error(f"Failed to get symbol info for {symbol}")
                return None

            # Get current price if not specified
            if price is None:
                tick = mt5.symbol_info_tick(symbol)
                if not tick:
                    logging.error(f"Failed to get tick for {symbol}")
                    return None
                price = tick.ask if order_type.lower() == "buy" else tick.bid
            
            # Determine order type enum
            order_type_enum = mt5.ORDER_TYPE_BUY if order_type.lower() == "buy" else mt5.ORDER_TYPE_SELL

            # Check margin before placing trade
            margin_check = self.check_margin_for_trade(symbol, volume, order_type_enum)
            if not margin_check["result"]:
                logging.error(f"Margin check failed: {margin_check['message']}")
                return None
            
            # CRITICAL: Validate SL and TP are in correct relation to price based on order type
            # For BUY orders: SL must be below entry, TP must be above entry
            # For SELL orders: SL must be above entry, TP must be below entry
            if order_type.lower() == "buy":
                if sl is not None and sl >= price:
                    logging.error(f"Invalid SL {sl} for BUY order - must be below entry price {price}")
                    sl = None
                if tp is not None and tp <= price:
                    logging.error(f"Invalid TP {tp} for BUY order - must be above entry price {price}")
                    tp = None
            else:  # sell
                if sl is not None and sl <= price:
                    logging.error(f"Invalid SL {sl} for SELL order - must be above entry price {price}")
                    sl = None
                if tp is not None and tp >= price:
                    logging.error(f"Invalid TP {tp} for SELL order - must be below entry price {price}")
                    tp = None

            # Check minimum stop levels and adjust if needed
            if sl is not None or tp is not None:
                stops_level = symbol_info.trade_stops_level
                if stops_level > 0:
                    logging.info(f"Minimum stop level for {symbol}: {stops_level} points")
                    tick = mt5.symbol_info_tick(symbol)
                    
                    # Adjust stop loss if needed
                    if sl is not None:
                        if order_type.lower() == "buy":
                            min_sl = tick.bid - (stops_level + 5) * symbol_info.point
                            if sl > min_sl:
                                logging.warning(f"Adjusting stop loss from {sl} to {min_sl} to meet minimum distance")
                                sl = min_sl
                        else:  # sell
                            min_sl = tick.ask + (stops_level + 5) * symbol_info.point
                            if sl < min_sl:
                                logging.warning(f"Adjusting stop loss from {sl} to {min_sl} to meet minimum distance")
                                sl = min_sl
                    
                    # Adjust take profit if needed
                    if tp is not None:
                        if order_type.lower() == "buy":
                            min_tp = tick.bid + (stops_level + 5) * symbol_info.point
                            if tp < min_tp:
                                logging.warning(f"Adjusting take profit from {tp} to {min_tp} to meet minimum distance")
                                tp = min_tp
                        else:  # sell
                            min_tp = tick.ask - (stops_level + 5) * symbol_info.point
                            if tp > min_tp:
                                logging.warning(f"Adjusting take profit from {tp} to {min_tp} to meet minimum distance")
                                tp = min_tp

            # For IC Markets, directly use IOC filling mode (2)
            # Prepare the trade request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type_enum,
                "price": price,
                "deviation": 50,  # Increased deviation for higher chance of execution
                "magic": 234000,
                "comment": "python script open",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC  # Use IOC for IC Markets
            }

            # Only add SL/TP if they are valid
            if sl is not None:
                request["sl"] = sl
                logging.info(f"Setting stop loss at {sl}")
            
            if tp is not None:
                request["tp"] = tp
                logging.info(f"Setting take profit at {tp}")

            # Log the full request for debugging
            logging.info(f"Prepared order request: {request}")

            # Check the order first
            check_result = mt5.order_check(request)
            if check_result is None:
                logging.error("Order check failed - no result returned")
                error_code = mt5.last_error()
                logging.error(f"Last error: {error_code}")
                return None
                
            if check_result.retcode != 0:
                logging.error(f"Order check failed: {check_result.comment}, code: {check_result.retcode}")
                self._log_detailed_error(check_result.retcode)
                return None

            # Try to send the order
            result = mt5.order_send(request)
            if result is None:
                logging.error("order_send() failed, no result returned")
                error_code = mt5.last_error()
                logging.error(f"Last error: {error_code}")
                return None
                
            if result.retcode == self.TRADE_RETCODE_DONE:
                logging.info(f"Trade executed successfully: {result.comment}")
                logging.info(f"Position details: Ticket #{result.order}, {order_type.upper()} {volume} lots at {result.price}")
                logging.info(f"SL set at: {sl if sl is not None else 'None'}, TP set at: {tp if tp is not None else 'None'}")
                return {
                    "ticket": result.order,
                    "volume": volume,
                    "price": result.price,
                    "sl": sl,
                    "tp": tp,
                    "comment": "Position opened successfully"
                }
            elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                # Try one more time with updated price
                tick = mt5.symbol_info_tick(symbol)
                new_price = tick.ask if order_type.lower() == "buy" else tick.bid
                request["price"] = new_price
                logging.info(f"Requote received, retrying with new price: {new_price}")
                
                # Send the order again
                result = mt5.order_send(request)
                if result and result.retcode == self.TRADE_RETCODE_DONE:
                    logging.info(f"Trade executed successfully on second attempt: {result.comment}")
                    logging.info(f"Position details: Ticket #{result.order}, {order_type.upper()} {volume} lots at {result.price}")
                    logging.info(f"SL set at: {sl if sl is not None else 'None'}, TP set at: {tp if tp is not None else 'None'}")
                    return {
                        "ticket": result.order,
                        "volume": volume,
                        "price": result.price,
                        "sl": sl,
                        "tp": tp,
                        "comment": "Position opened successfully on retry"
                    }
            
            # If we reached here, the order failed
            if result:
                logging.error(f"Failed to open position: {result.comment}, code: {result.retcode}")
                self._log_detailed_error(result.retcode)
            
            return None
            
        except Exception as e:
            logging.error(f"Exception in open_position: {e}", exc_info=True)
            return None

    def _log_detailed_error(self, error_code: int):
        """Log detailed information about MT5 error codes."""
        error_descriptions = {
            10004: "Requote",
            10006: "Order rejected",
            10007: "Order canceled by trader",
            10008: "Order already complete",
            10009: "Order done",
            10010: "Only part of the order was completed",
            10011: "Error in order processing",
            10012: "Error while generating orders",
            10013: "Order locked",
            10014: "Invalid volume",
            10015: "Invalid price",
            10016: "Invalid stops",
            10017: "Trade disabled",
            10018: "Market closed",
            10019: "Not enough money",
            10020: "Prices changed",
            10021: "No quotes to process request",
            10022: "Invalid expiration date in order",
            10023: "Order state changed",
            10024: "Too many orders",
            10025: "No changes in order",
            10026: "Autotrading disabled by server",
            10027: "Autotrading disabled by client",
            10028: "Request locked for processing",
            10029: "Order or position frozen",
            10030: "Invalid order filling type",
            10031: "No connection with trade server",
            10032: "Operation is allowed only for live accounts",
            10033: "Maximum number of pending orders reached",
            10034: "Maximum pending order volume limit reached",
            10035: "Maximum pending order count limit reached",
            10036: "Maximum position and pending order count limit reached",
            10038: "Close only order placed incorrectly",
            10039: "Close only position exists already",
            10040: "The pending order will be executed at the next stop",
            10041: "The pending order is not allowed before the start of pending order activation time",
            10042: "Symbol is in status 'Close Only'",
            10043: "Position exceeds margin limit"
        }
        
        description = error_descriptions.get(error_code, "Unknown error code")
        logging.error(f"MT5 Error {error_code}: {description}")
        
        if error_code == 10014:
            logging.error("Invalid volume: Check minimum trade size and volume step")
        elif error_code == 10016:
            logging.error("Invalid stops: Check stop loss and take profit levels")
        elif error_code == 10019:
            logging.error("Not enough money: Insufficient margin for this trade")
        elif error_code == 10027:
            logging.error("Autotrading disabled: Enable it in MT5 (Tools > Options > Expert Advisors)")
        elif error_code == 10030:
            logging.error("Invalid filling type: Broker doesn't support this filling mode")

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
        
    def close_position(self, ticket: int, volume: Optional[float] = None) -> bool:
        """Close a specific position with proper filling mode handling.
        
        Args:
            ticket: The position ticket to close
            volume: Optional volume to close (for partial closing). If None, close entire position.
        """
        position = mt5.positions_get(ticket=ticket)
        if not position:
            logging.error(f"Position {ticket} not found")
            return False
            
        position = position[0]
        
        # Determine if we're closing the entire position or just a part
        is_partial_close = False
        if volume is None or abs(volume - position.volume) < 0.001:
            # Close entire position
            close_volume = position.volume
        else:
            # Partial close
            is_partial_close = True
            close_volume = min(volume, position.volume)
            logging.info(f"Partial close requested: {close_volume} out of {position.volume} lots")
        
        # Select the symbol in the Market Watch
        if not mt5.symbol_select(position.symbol, True):
            logging.error(f"Failed to select {position.symbol} in Market Watch")
            return False

        # Prepare close request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": close_volume,
            "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,
            "deviation": 50,  # Increased deviation
            "magic": 234000,
            "comment": "python script close" + (" partial" if is_partial_close else ""),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC  # Default to IOC for IC Markets
        }
        
        # Log the request
        logging.info(f"Prepared close request: {request}")
        
        # Try to send the order with IOC filling type
        result = mt5.order_send(request)
        
        # If fails, try with explicit filling types
        if result is None or result.retcode != self.TRADE_RETCODE_DONE:
            # Try various filling modes
            for filling_type in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
                try:
                    request["type_filling"] = filling_type
                    logging.info(f"Trying close with filling type: {filling_type}")
                    result = mt5.order_send(request)
                    if result is not None and result.retcode == self.TRADE_RETCODE_DONE:
                        logging.info(f"Close successful with filling type: {filling_type}")
                        return True
                except Exception as e:
                    logging.error(f"Error with filling type {filling_type}: {e}")
            
            # If still failed, log the error
            if result is not None:
                logging.error(f"Failed to close position: {result.comment}, code: {result.retcode}")
                self._log_detailed_error(result.retcode)
            else:
                logging.error("Failed to close position: No result returned")
            
            return False
        else:
            if is_partial_close:
                logging.info(f"Successfully closed {close_volume} lots of position {ticket}")
            else:
                logging.info(f"Successfully closed entire position {ticket}")
        
        return True
        
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
            
        # Check minimum stop levels and adjust if needed
        if sl is not None or tp is not None:
            stops_level = symbol_info.trade_stops_level
            if stops_level > 0:
                logging.info(f"Minimum stop level for {position.symbol}: {stops_level} points")
                tick = mt5.symbol_info_tick(position.symbol)
                
                # Adjust stop loss if needed
                if sl is not None:
                    if position.type == mt5.ORDER_TYPE_BUY:
                        min_sl = tick.bid - (stops_level + 5) * symbol_info.point
                        if sl > min_sl:
                            logging.warning(f"Adjusting stop loss from {sl} to {min_sl} to meet minimum distance")
                            sl = min_sl
                    else:  # sell
                        min_sl = tick.ask + (stops_level + 5) * symbol_info.point
                        if sl < min_sl:
                            logging.warning(f"Adjusting stop loss from {sl} to {min_sl} to meet minimum distance")
                            sl = min_sl
                
                # Adjust take profit if needed
                if tp is not None:
                    if position.type == mt5.ORDER_TYPE_BUY:
                        min_tp = tick.bid + (stops_level + 5) * symbol_info.point
                        if tp < min_tp:
                            logging.warning(f"Adjusting take profit from {tp} to {min_tp} to meet minimum distance")
                            tp = min_tp
                    else:  # sell
                        min_tp = tick.ask - (stops_level + 5) * symbol_info.point
                        if tp > min_tp:
                            logging.warning(f"Adjusting take profit from {tp} to {min_tp} to meet minimum distance")
                            tp = min_tp
            
        # Prepare modification request
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "magic": 234000,
            "sl": sl if sl is not None else position.sl,
            "tp": tp if tp is not None else position.tp
        }
        
        # Log the request
        logging.info(f"Prepared modify request: {request}")
        
        # Check if the modification would be valid
        check_result = mt5.order_check(request)
        if check_result is None:
            logging.error("Order check failed for position modification")
            return None
            
        if check_result.retcode != 0:
            logging.error(f"Position modification check failed: {check_result.comment}, code: {check_result.retcode}")
            self._log_detailed_error(check_result.retcode)
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
            else:
                error_message = f"Failed to modify position: {result.comment}, code: {result.retcode}"
                logging.error(error_message)
                self._log_detailed_error(result.retcode)
                break
                
        return None
        
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