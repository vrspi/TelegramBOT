import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import json5
from services.together_client import TogetherClient
import MetaTrader5 as mt5

class TradingDecision(Enum):
    EXECUTE_TRADE = "execute_trade"
    MODIFY_TRADE = "modify_trade"
    CLOSE_TRADE = "close_trade"
    SET_BREAKEVEN = "set_breakeven"
    NO_ACTION = "no_action"
    NEED_CLARIFICATION = "need_clarification"

@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float

@dataclass
class MarketContext:
    symbol: str
    bid: float
    ask: float
    spread: float
    volume: float
    time: str

class TradingAgent:
    def __init__(self, together_client: TogetherClient, mt5_service=None, max_history: int = 10):
        self.together_client = together_client
        self.mt5_service = mt5_service
        self.message_history: List[Dict] = []
        self.max_history = max_history
        
    def add_to_history(self, message: str, decision: Dict):
        """Add message and its analysis to history."""
        self.message_history.append({
            "message": message,
            "decision": decision,
            "timestamp": self.get_current_timestamp()
        })
        
        # Keep only recent history
        if len(self.message_history) > self.max_history:
            self.message_history.pop(0)

    def get_current_timestamp(self) -> str:
        """Get current timestamp in a readable format."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def format_trade_history(self, trades: Dict) -> str:
        """Format current trades into a readable string."""
        if not trades:
            return "No active trades."
        
        trade_strings = []
        for symbol, trade in trades.items():
            trade_strings.append(
                f"{symbol}: {trade.direction.upper()} at {trade.entry}, "
                f"SL={trade.stop_loss}, TP={trade.take_profit}, "
                f"State={trade.state.name}"
            )
        return "\n".join(trade_strings)

    def format_message_history(self) -> str:
        """Format recent message history into a readable string."""
        if not self.message_history:
            return "No message history."
        
        history_strings = []
        for entry in self.message_history[-5:]:  # Last 5 messages
            history_strings.append(
                f"[{entry['timestamp']}] {entry['message']}\n"
                f"Decision: {entry['decision'].get('decision', 'Unknown')}"
            )
        return "\n\n".join(history_strings)

    def generate_analysis_prompt(self, message: str, account_info: AccountInfo, 
                               market_context: MarketContext, trades: Dict) -> str:
        """Generate a comprehensive prompt for the LLM."""
        prompt_template = '''You are an expert trading assistant specializing in XAUUSD (Gold) trading signals.
Your role is to analyze trading messages and make informed decisions. IMPORTANT: When a clear trading signal is given (like "Gold buy/sell now"), you should EXECUTE the trade immediately at market price, even if stop loss and take profit levels are not specified.

Current Market Context:
- Symbol: {symbol}
- Current Bid: {bid}
- Current Ask: {ask}
- Spread: {spread}
- Time: {time}

Account Status:
- Balance: ${balance:,.2f}
- Equity: ${equity:,.2f}
- Free Margin: ${free_margin:,.2f}
- Margin Level: {margin_level}%

Active Trades:
{trades}

Recent Message History:
{history}

New Message to Analyze:
"{message}"

Analyze this message carefully and provide:
1. A detailed analysis of the message intent
2. Risk assessment considering current market and account conditions
3. A clear trading decision

IMPORTANT RULES:
1. For "buy/sell now" messages, ALWAYS execute the trade immediately at market price
2. If stop loss and take profit are not specified, execute the trade anyway with default risk management
3. Default risk management will be 1% of account balance
4. Do not ask for clarification on direct trading signals
5. Be very specific about price levels - provide exact values, not just "above X" or "near Y"
6. IC Markets may use a different symbol name like XAUUSD.a instead of XAUUSD - be aware

Return your response in this JSON format:
{{
    "analysis": "Your step-by-step reasoning about the message",
    "risk_assessment": "Your evaluation of the risk",
    "decision": "EXECUTE_TRADE/MODIFY_TRADE/CLOSE_TRADE/SET_BREAKEVEN/NO_ACTION/NEED_CLARIFICATION",
    "action_params": {{
        "symbol": "XAUUSD",
        "direction": "buy/sell",
        "entry": float or null,
        "stop_loss": float or null,
        "take_profit": [float] or null, // Extract all TP values EXACTLY as they appear in the message text and provide them as a list of floats. Do not validate or select. If no TPs are mentioned, provide null.// Example: if message has TP1: 2345, TP2: 2340, then provide [2345.0, 2340.0]
        "reason": "Brief explanation of the decision"
    }}
}}'''

        return prompt_template.format(
            symbol=market_context.symbol,
            bid=market_context.bid,
            ask=market_context.ask,
            spread=market_context.spread,
            time=market_context.time,
            balance=account_info.balance,
            equity=account_info.equity,
            free_margin=account_info.free_margin,
            margin_level=account_info.margin_level,
            trades=self.format_trade_history(trades),
            history=self.format_message_history(),
            message=message
        )

    async def analyze_and_decide(self, message: str, suggested_action=None) -> Dict:
        """Analyze message and make a trading decision using direct pattern matching."""
        try:
            logging.info(f"Analyzing message with direct pattern matching: {message}")
            lower_msg = message.lower()
            
            # Get market context if available
            market_context = None
            if self.mt5_service:
                try:
                    market_context = self.mt5_service.get_market_context("XAUUSD")
                except Exception as e:
                    logging.error(f"Failed to get market context: {e}")
            
            # Emergency direct pattern matching for trading signals
            decision = None
            
            # Detect breakeven command
            if "break even" in lower_msg or "breakeven" in lower_msg:
                logging.warning("Using direct pattern matching for breakeven command")
                return {
                    "action": "set_breakeven",
                    "symbol": "XAUUSD",  # Default to gold
                    "reasoning": "Direct pattern matching detected breakeven command",
                    "risk_assessment": "Moving stop loss to breakeven to eliminate risk"
                }
            
            # Detect close half command
            if "close half" in lower_msg or "secure half" in lower_msg or "secure profits" in lower_msg:
                logging.warning("Using direct pattern matching for close half command")
                return {
                    "action": "close_half",
                    "symbol": "XAUUSD",  # Default to gold
                    "reasoning": "Direct pattern matching detected close half command",
                    "risk_assessment": "Securing partial profits while keeping remaining position open"
                }
            
            # Try to detect direct buy signal
            if ("xauusd buy" in lower_msg or "gold buy" in lower_msg) and ("now" in lower_msg or ":" in lower_msg):
                action = "buy"
                entry_price = market_context["ask"] if market_context else None
                logging.warning("Using direct pattern matching for buy signal")
            # Try to detect direct sell signal
            elif ("xauusd sell" in lower_msg or "gold sell" in lower_msg) and ("now" in lower_msg or ":" in lower_msg):
                action = "sell"
                entry_price = market_context["bid"] if market_context else None
                logging.warning("Using direct pattern matching for sell signal")
            # If suggested action provided, use it
            elif suggested_action:
                action = suggested_action
                entry_price = market_context["ask"] if action == "buy" and market_context else None
                entry_price = market_context["bid"] if action == "sell" and market_context else None
            else:
                # No clear action found
                return {
                    "action": "no_action",
                    "reasoning": "No clear trading signal detected in message",
                    "risk_assessment": "No risk assessment needed"
                }
            
            # Extract stop loss and take profit from message
            lines = message.split('\n')
            import re
            
            stop_loss = None
            raw_take_profit_values = [] # To store all TPs found before validation/selection
            
            # First try to extract price points from the first line
            price_points = re.findall(r'\d+\.?\d*', lines[0])
            price_points = [float(p) for p in price_points]
            
            # Extract stop loss
            for line in lines:
                if "sl" in line.lower() or "stop" in line.lower():
                    sl_matches = re.findall(r'\d+\.?\d*', line)
                    if sl_matches:
                        stop_loss = float(sl_matches[0])
                        break
            
            # Extract take profit levels
            for line in lines:
                if "tp" in line.lower() or "target" in line.lower() or "profit" in line.lower():
                    tp_matches = re.findall(r'\d+\.?\d*', line)
                    if tp_matches:
                        for tp_str in tp_matches:
                            try:
                                raw_take_profit_values.append(float(tp_str))
                            except ValueError:
                                logging.warning(f"Could not convert TP value '{tp_str}' to float.")
            
            # Keep a copy of all TPs found before filtering and selection for logging purposes
            original_tps_from_signal = list(raw_take_profit_values) # Make a copy
            take_profit = list(raw_take_profit_values) # Work with a copy for filtering
            
            # Validate stop loss direction
            if stop_loss and entry_price:
                if action == "buy" and stop_loss >= entry_price:
                    logging.warning(f"Invalid SL for BUY: {stop_loss} >= {entry_price}, adjusting to 1% below entry")
                    stop_loss = round(entry_price * 0.99, 2)  # 1% below entry price
                elif action == "sell" and stop_loss <= entry_price:
                    logging.warning(f"Invalid SL for SELL: {stop_loss} <= {entry_price}, adjusting to 1% above entry")
                    stop_loss = round(entry_price * 1.01, 2)  # 1% above entry price
            elif entry_price:  # No SL provided, create default
                if action == "buy":
                    stop_loss = round(entry_price * 0.99, 2)  # 1% below entry
                    logging.info(f"No SL provided, using default 1% below entry: {stop_loss}")
                else:  # sell
                    stop_loss = round(entry_price * 1.01, 2)  # 1% above entry
                    logging.info(f"No SL provided, using default 1% above entry: {stop_loss}")
            
            # Validate take profit direction
            if take_profit and entry_price:
                valid_tps = []
                for tp in take_profit:
                    if action == "buy" and tp > entry_price:
                        valid_tps.append(tp)
                    elif action == "sell" and tp < entry_price:
                        valid_tps.append(tp)
                    else:
                        logging.warning(f"Invalid TP for {action.upper()}: {tp}, skipping")
                
                if not valid_tps and entry_price:  # No valid TPs, create default
                    if action == "buy":
                        default_tp = round(entry_price * 1.02, 2)  # 2% above entry
                        valid_tps.append(default_tp)
                        logging.info(f"No valid TP provided, using default 2% above entry: {default_tp}")
                    else:  # sell
                        default_tp = round(entry_price * 0.98, 2)  # 2% below entry
                        valid_tps.append(default_tp) 
                        logging.info(f"No valid TP provided, using default 2% below entry: {default_tp}")
                
                # If multiple valid TPs, select the most aggressive one
                if len(valid_tps) > 1:
                    if action == "buy":
                        take_profit = [max(valid_tps)] # Largest TP for buy
                        logging.info(f"Multiple valid TPs for BUY, selected most aggressive: {take_profit[0]}")
                    elif action == "sell":
                        take_profit = [min(valid_tps)] # Smallest TP for sell
                        logging.info(f"Multiple valid TPs for SELL, selected most aggressive: {take_profit[0]}")
                elif len(valid_tps) == 1:
                    take_profit = valid_tps
                else: # No valid TPs found after filtering, or original take_profit was empty
                    take_profit = [] # Ensure it's an empty list not None, if no TPs

            # Ensure take_profit is a list for consistency, even if it's empty or has one element
            if not isinstance(take_profit, list):
                if take_profit is not None: # If it's a single valid TP value from default logic
                    take_profit = [take_profit]
                else:
                    take_profit = []
            
            # Build response
            decision = {
                "action": action,
                "symbol": "XAUUSD",
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,  # This is now a list with the single most aggressive TP or empty
                "original_take_profit_list": original_tps_from_signal, # Full list of TPs from signal
                "reasoning": f"Direct pattern matching for {action} signal",
                "risk_assessment": "Risk managed by SL/TP levels"
            }
            
            logging.info(f"Direct pattern matching decision: {decision}")
            return decision
            
        except Exception as e:
            logging.error(f"Error in analyze_and_decide: {e}", exc_info=True)
            return {
                "action": "no_action",
                "reasoning": f"Error during analysis: {str(e)}",
                "risk_assessment": "Error during analysis"
            }

    def create_error_decision(self, error_message: str) -> Dict:
        """Create an error decision object."""
        return {
            "decision": TradingDecision.NO_ACTION,
            "params": {},
            "reasoning": f"Error: {error_message}",
            "risk_assessment": "Unable to assess risk due to error"
        }

    def execute_decision(self, decision):
        """Execute a trading decision."""
        try:
            # Extract decision components
            action = decision.get("action", "")
            symbol = decision.get("symbol", "")
            entry_price = decision.get("entry_price")
            stop_loss = decision.get("stop_loss")
            # raw_take_profit_from_decision is a list from analyze_and_decide, e.g., [3308.0] or []
            raw_take_profit_from_decision = decision.get("take_profit") 
            # original_take_profit_list would be the full list from the signal, e.g., [3312.0, 3310.0, 3308.0]
            # This needs to be populated by analyze_and_decide if detailed logging of other TPs is desired.
            original_take_profit_list = decision.get("original_take_profit_list", [])

            risk_percent = decision.get("risk_percent", 1.0)  # Default to 1%
            position_size = decision.get("position_size")
            reasoning = decision.get("reasoning", "No reasoning provided")

            # Extract the single most aggressive TP for use in this method
            take_profit = None # This will be the single float TP value or None
            if isinstance(raw_take_profit_from_decision, list) and raw_take_profit_from_decision:
                take_profit = raw_take_profit_from_decision[0] # Should be the single most aggressive
            elif isinstance(raw_take_profit_from_decision, (float, int)):
                 take_profit = float(raw_take_profit_from_decision) # Fallback, though analyze_and_decide should provide list

            logging.info(f"Extracted TP for execution: {take_profit} (from decision's raw TP: {raw_take_profit_from_decision})")
            
            # Flag if the original signal contained multiple distinct TPs
            multiple_tp_levels = len(original_take_profit_list) > 1

            # Handle breakeven action
            if action.lower() == "set_breakeven":
                if not self.mt5_service:
                    logging.error("MT5 service not available for breakeven operation")
                    return {"success": False, "message": "MT5 service not available"}
                
                # Get all open positions for the given symbol
                positions = self.mt5_service.get_all_positions()
                if not positions:
                    logging.warning(f"No open positions found for setting breakeven")
                    return {"success": False, "message": "No open positions found"}
                
                # Filter positions for the specified symbol
                symbol_positions = [pos for pos in positions if pos["symbol"] == symbol]
                if not symbol_positions:
                    logging.warning(f"No open positions found for {symbol}")
                    return {"success": False, "message": f"No open positions found for {symbol}"}
                
                success_count = 0
                total_positions = len(symbol_positions)
                
                for position in symbol_positions:
                    # Set SL to entry price (breakeven)
                    result = self.mt5_service.modify_position(
                        ticket=position["ticket"],
                        sl=position["price"]  # Entry price
                    )
                    
                    if result:
                        logging.info(f"Set position {position['ticket']} to breakeven (SL = {position['price']})")
                        success_count += 1
                    else:
                        logging.error(f"Failed to set position {position['ticket']} to breakeven")
                
                if success_count > 0:
                    return {
                        "success": True,
                        "message": f"Set {success_count}/{total_positions} positions to breakeven for {symbol}"
                    }
                else:
                    return {
                        "success": False, 
                        "message": f"Failed to set any positions to breakeven for {symbol}"
                    }
            
            # Handle close half action
            if action.lower() == "close_half":
                if not self.mt5_service:
                    logging.error("MT5 service not available for close half operation")
                    return {"success": False, "message": "MT5 service not available"}
                
                # Get all open positions for the given symbol
                positions = self.mt5_service.get_all_positions()
                if not positions:
                    logging.warning(f"No open positions found for closing half")
                    return {"success": False, "message": "No open positions found"}
                
                # Filter positions for the specified symbol
                symbol_positions = [pos for pos in positions if pos["symbol"] == symbol]
                if not symbol_positions:
                    logging.warning(f"No open positions found for {symbol}")
                    return {"success": False, "message": f"No open positions found for {symbol}"}
                
                success_count = 0
                total_positions = len(symbol_positions)
                
                for position in symbol_positions:
                    # Calculate half volume (minimum 0.01)
                    half_volume = max(position["volume"] / 2, 0.01)
                    half_volume = round(half_volume, 2)  # Round to 2 decimal places for lots
                    
                    # Only proceed if we can close at least some volume
                    if half_volume >= 0.01:
                        # Close half position by ticket
                        try:
                            # Check if we're closing exactly half or full position
                            is_full_close = abs(half_volume - position["volume"]) < 0.001
                            
                            if is_full_close:
                                # If difference is negligible, close the entire position
                                result = self.mt5_service.close_position(position["ticket"])
                                logging.info(f"Volume too small to divide, closing entire position {position['ticket']}")
                            else:
                                # Partial close with half volume
                                result = self.mt5_service.close_position(position["ticket"], volume=half_volume)
                                logging.info(f"Closing {half_volume} lots out of {position['volume']} for position {position['ticket']}")
                            
                            if result:
                                success_count += 1
                                logging.info(f"Successfully closed half of position {position['ticket']}")
                            else:
                                logging.error(f"Failed to close half of position {position['ticket']}")
                        except Exception as e:
                            logging.error(f"Error closing half position: {e}")
                    else:
                        logging.warning(f"Position {position['ticket']} volume too small to close half ({position['volume']})")
                
                if success_count > 0:
                    return {
                        "success": True,
                        "message": f"Closed half of {success_count}/{total_positions} positions for {symbol}"
                    }
                else:
                    return {
                        "success": False, 
                        "message": f"Failed to close half of any positions for {symbol}"
                    }
                
            # 'take_profit' (float or None) is now set based on raw_take_profit_from_decision.
            # 'multiple_tp_levels' (boolean) is set based on original_take_profit_list.

            # Skip if no action or invalid symbol
            if not action or not symbol:
                logging.warning("No action or symbol specified in decision")
                return {"success": False, "message": "No action or symbol specified"}
                
            # Normalize action to buy/sell
            action = action.lower()
            if action in ["buy", "long"]:
                action = "buy"
            elif action in ["sell", "short"]:
                action = "sell"
            else:
                logging.warning(f"Invalid action: {action}")
                return {"success": False, "message": f"Invalid action: {action}"}
            
            # Get current market data
            market_context = self.mt5_service.get_market_context(symbol)
            if not market_context:
                logging.error(f"Could not get market context for {symbol}")
                return {"success": False, "message": f"Could not get market context for {symbol}"}
                
            # Use current price if entry price is not specified
            current_price = market_context["ask"] if action == "buy" else market_context["bid"]
            if entry_price is None:
                entry_price = current_price
                logging.info(f"No entry price specified, using current market price: {entry_price}")
                
            # Calculate position size if not specified
            if position_size is None:
                # Get account info for position sizing
                account_info = self.mt5_service.get_account_info()
                if not account_info:
                    logging.error("Could not get account info for position sizing")
                    return {"success": False, "message": "Could not get account info for position sizing"}
                    
                balance = account_info['balance']
                if risk_percent <= 0:
                    risk_percent = 1.0  # Default to 1%
                    logging.warning(f"Invalid risk percent ({risk_percent}), using default: 1%")
                    
                risk_amount = balance * (risk_percent / 100)
                
                # Calculate SL pips for position sizing
                if stop_loss:
                    sl_points = abs(entry_price - stop_loss)
                else:
                    # Default SL to 1% of entry price if not specified
                    sl_points = entry_price * 0.01
                    logging.warning(f"No SL specified, using default: {sl_points} points")
                    
                # Calculate position size in lots
                # Formula: Risk amount / (SL points * Value per point)
                # For XAU/USD, 1 point is typically worth $1 per 0.01 lot
                value_per_point_per_lot = 1.0  # $1 per 0.01 lot per point for gold
                position_size = round(risk_amount / (sl_points * value_per_point_per_lot * 100), 2)
                
                # Minimum position size 0.01 lots
                position_size = max(0.01, position_size)
                logging.info(f"Calculated position size: {position_size} lots with risk amount: ${risk_amount}")
                
            # Check margin before executing trade
            order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
            margin_check = self.mt5_service.check_margin_for_trade(symbol, position_size, order_type)
            if not margin_check["result"]:
                logging.error(f"Margin check failed: {margin_check['message']}")
                return {"success": False, "message": margin_check['message']}
                
            logging.info(f"Margin check passed: {margin_check['message']}")
            
            # Re-assign take_profit to the single selected TP for the order
            # The original list of TPs is still in decision.get('take_profit')
            take_profit_for_order = selected_tp_for_order
            
            # Skip if no action or invalid symbol
            if not action or not symbol:
                logging.warning("No action or symbol specified in decision")
                return {"success": False, "message": "No action or symbol specified"}
                
            # Normalize action to buy/sell
            action = action.lower()
            if action in ["buy", "long"]:
                action = "buy"
            elif action in ["sell", "short"]:
                action = "sell"
            else:
                logging.warning(f"Invalid action: {action}")
                return {"success": False, "message": f"Invalid action: {action}"}
            
            # Get current market data
            market_context = self.mt5_service.get_market_context(symbol)
            if not market_context:
                logging.error(f"Could not get market context for {symbol}")
                return {"success": False, "message": f"Could not get market context for {symbol}"}
                
            # Use current price if entry price is not specified
            current_price = market_context["ask"] if action == "buy" else market_context["bid"]
            if entry_price is None:
                entry_price = current_price
                logging.info(f"No entry price specified, using current market price: {entry_price}")
                
            # Calculate position size if not specified
            if position_size is None:
                # Get account info for position sizing
                # account_info = self.mt5_service.get_account_info()
                # if not account_info:
                #     logging.error("Could not get account info for position sizing")
                #     return {"success": False, "message": "Could not get account info for position sizing"}
                    
                # balance = account_info['balance']
                # if risk_percent <= 0:
                #     risk_percent = 1.0  # Default to 1%
                #     logging.warning(f"Invalid risk percent ({risk_percent}), using default: 1%")
                    
                # risk_amount = balance * (risk_percent / 100)
                
                # # Calculate SL pips for position sizing
                # if stop_loss:
                #     sl_points = abs(entry_price - stop_loss)
                # else:
                #     # Default SL to 1% of entry price if not specified
                #     sl_points = entry_price * 0.01
                #     logging.warning(f"No SL specified, using default: {sl_points} points")
                    
                # # Calculate position size in lots
                # # Formula: Risk amount / (SL points * Value per point)
                # # For XAU/USD, 1 point is typically worth $1 per 0.01 lot
                # value_per_point_per_lot = 1.0  # $1 per 0.01 lot per point for gold
                # position_size = round(risk_amount / (sl_points * value_per_point_per_lot * 100), 2)
                
                # # Minimum position size 0.01 lots
                # position_size = max(0.01, position_size)
                # logging.info(f"Calculated position size: {position_size} lots with risk amount: ${risk_amount}")
                position_size = 0.05  # Set fixed position size
                logging.info(f"Using fixed position size: {position_size} lots")
                
            # Check margin before executing trade
            order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
            margin_check = self.mt5_service.check_margin_for_trade(symbol, position_size, order_type)
            if not margin_check["result"]:
                logging.error(f"Margin check failed: {margin_check['message']}")
                return {"success": False, "message": margin_check["message"]}
                
            logging.info(f"Margin check passed: {margin_check['message']}")
            
            # Check for existing open positions for the same symbol and action
            existing_positions = self.mt5_service.get_all_positions()
            open_trade_for_symbol_and_action = None
            if existing_positions:
                for pos in existing_positions:
                    if pos['symbol'] == symbol:
                        pos_action = "buy" if pos['type'] == mt5.ORDER_TYPE_BUY else "sell"
                        if pos_action == action:
                            open_trade_for_symbol_and_action = pos
                            break

            if open_trade_for_symbol_and_action:
                logging.info(f"Existing {action} trade found for {symbol} (Ticket: {open_trade_for_symbol_and_action['ticket']}). Modifying TP if necessary.")
                current_tp = open_trade_for_symbol_and_action.get('tp', 0.0) # Assuming 0.0 if TP is not set
                # 'take_profit' (derived from decision['take_profit']) is the single most aggressive TP (float or None) from the new signal.
                new_signal_tp = take_profit 

                single_new_tp = float(new_signal_tp) if new_signal_tp is not None else 0.0
                logging.info(f"For existing trade modification: current_tp={current_tp}, new_signal_tp (most aggressive)={single_new_tp}")
                
                final_tp = 0.0
                # single_new_tp should hold the most aggressive TP from the new signal
                if action == "buy":
                    # If current_tp is 0, use single_new_tp if valid, else 0
                    # If single_new_tp is 0, use current_tp if valid, else 0
                    # Otherwise, take the max of valid TPs
                    if current_tp > 0 and single_new_tp > 0:
                        final_tp = max(current_tp, single_new_tp)
                    elif single_new_tp > 0:
                        final_tp = single_new_tp
                    else:
                        final_tp = current_tp # current_tp could be 0 here, which is fine if no valid new TP
                elif action == "sell":
                    # For sell, the 'most ambitious' is the numerically smallest valid TP
                    if current_tp > 0 and single_new_tp > 0:
                        final_tp = min(current_tp, single_new_tp)
                    elif single_new_tp > 0: # current_tp is not valid or 0, use new one if valid
                        final_tp = single_new_tp
                    else: # single_new_tp is not valid or 0, use current one
                        final_tp = current_tp # current_tp could be 0 here

                # Ensure final_tp is not 0 if one of them was valid and resulted in a 0 final_tp (e.g. if one was 0 and other was negative)
                # This secondary check might be redundant if single_new_tp and current_tp are always positive or 0
                if final_tp == 0.0:
                    if single_new_tp > 0 and current_tp > 0:
                        # This case should have been handled above, but as a safeguard
                        if action == "buy": final_tp = max(current_tp, single_new_tp)
                        if action == "sell": final_tp = min(current_tp, single_new_tp)
                    elif single_new_tp > 0:
                        final_tp = single_new_tp
                    elif current_tp > 0:
                        final_tp = current_tp
                # Logging the decision for TP update
                logging.info(f"TP Update Check: Current TP: {current_tp}, New Signal TP (most aggressive): {single_new_tp}, Chosen Final TP: {final_tp}")

                if final_tp != current_tp and final_tp > 0:
                    logging.info(f"Updating TP for ticket {open_trade_for_symbol_and_action['ticket']} from {current_tp} to {final_tp}")
                    modify_result = self.mt5_service.modify_position(
                        ticket=open_trade_for_symbol_and_action['ticket'],
                        tp=final_tp
                    )
                    if modify_result:
                        return {"success": True, "message": f"Modified TP for existing {action} {symbol} trade (Ticket: {open_trade_for_symbol_and_action['ticket']}) to {final_tp}"}
                    else:
                        return {"success": False, "message": f"Failed to modify TP for existing {action} {symbol} trade (Ticket: {open_trade_for_symbol_and_action['ticket']})"}
                else:
                    return {"success": True, "message": f"Existing {action} {symbol} trade (Ticket: {open_trade_for_symbol_and_action['ticket']}) found. TP not changed as new TP ({new_tp_value}) is not greater or no valid new TP."}
            else:
                # Execute the trade as no existing one was found
                logging.info(f"Attempting to execute {action} trade on {symbol}")
                logging.info(f"Entry: {entry_price}, SL: {stop_loss}, TP: {take_profit}")
                
                result = self.mt5_service.open_position(
                    symbol=symbol,
                    order_type=action,
                    volume=position_size,
                    price=entry_price,
                    sl=stop_loss,
                    tp=take_profit
                )
                
                if not result:
                    logging.error("Failed to open position")
                    return {"success": False, "message": f"Could not execute {action} {symbol}"}
                    
                # Log success and multiple TP information if applicable
                actual_tp_logged = take_profit # This is now a single float or None

                if multiple_tp_levels and actual_tp_logged is not None:
                    # Filter out the TP that was actually used for the order from the original list for the message
                    remaining_tps = [tp for tp in original_take_profit_list if tp != actual_tp_logged]
                    logging.info(f"Trade executed with TP: {actual_tp_logged}. Original signal had multiple TPs: {original_take_profit_list}. Remaining TPs for manual management: {remaining_tps}")
                    result["message"] = f"Position opened with SL at {stop_loss}, TP at {actual_tp_logged}. Original signal had multiple TPs. Other TPs ({remaining_tps}) need manual management."
                else:
                    result["message"] = f"Successfully executed {action} {symbol} at {entry_price} with SL at {stop_loss}" + (f", TP at {actual_tp_logged}" if actual_tp_logged else "")
                    
                result["success"] = True
                logging.info(f"Trade executed: {result['message']}")
                logging.info(f"Trade reasoning: {reasoning}")
                
                return result
                
                
            
        except Exception as e:
            logging.error(f"Error executing decision: {e}", exc_info=True)
            return {"success": False, "message": f"Error executing decision: {str(e)}"}