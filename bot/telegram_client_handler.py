import logging
import asyncio
from telethon import TelegramClient, events
from PySide6.QtCore import QObject, Signal, Slot
import sys
import os
# Add the project root directory to Python's module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
import json5
import traceback
import threading
import re
from enum import Enum
from typing import Dict, List, Optional, Any
from bot.agents.trading_agent import TradingAgent, AccountInfo, MarketContext, TradingDecision
import MetaTrader5 as mt5

class MessageType(Enum):
    TRADE_OPEN = 1
    TRADE_UPDATE = 2
    TRADE_CLOSE = 3
    GENERAL_INFO = 4
    UNKNOWN = 5

class TradeState(Enum):
    WAITING = 0
    OPEN = 1
    PARTIAL_CLOSE = 2
    BREAKEVEN = 3
    CLOSED = 4

class Trade:
    def __init__(self, symbol: str, direction: str, entry: float, stop_loss: float, take_profit: List[float]):
        self.symbol = symbol
        self.direction = direction
        self.entry = entry
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.state = TradeState.WAITING
        self.tickets: List[int] = []

class TelegramClientHandler(QObject):
    log_signal = Signal(str)

    def __init__(self, api_id, api_hash, phone_number, source_channel_id, mt5_service: MT5Service, together_client: TogetherClient):
        super().__init__()
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.source_channel_id = source_channel_id
        self.mt5_service = mt5_service
        self.together_client = together_client
        self.client = None
        self.trades: Dict[str, Trade] = {}
        self.loop = None
        self.thread = None
        self.trading_agent = None  # Will be initialized in process_message

        # Regex patterns for quick message classification
        self.patterns = {
            'open_trade': re.compile(r'(Gold|XAUUSD)\s+(buy|sell)\s*(?:now|:)', re.IGNORECASE),
            'update_trade': re.compile(r'(secure|close)\s+half|set\s+breakeven', re.IGNORECASE),
            'close_trade': re.compile(r'close\s+(?:all|trade)', re.IGNORECASE),
        }

    @Slot()
    def start(self):
        self.thread = threading.Thread(target=self.run_async_loop, daemon=True)
        self.thread.start()

    def run_async_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.run())

    async def run(self):
        while True:
            try:
                self.client = TelegramClient('session', self.api_id, self.api_hash, loop=self.loop)
                await self.start_client()
                
                # Start the periodic cleanup task
                asyncio.create_task(self.periodic_cleanup())
                
            except Exception as e:
                logging.error(f"Unexpected error in run method: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying
            finally:
                logging.info("Restarting Telegram client handler...")

    async def start_client(self):
        await self.client.start(phone=self.phone_number)
        logging.info(f"Listening for messages in channel ID: {self.source_channel_id}")
        self.client.add_event_handler(self.handler, events.NewMessage(chats=int(self.source_channel_id)))
        logging.info("Telegram client started. Listening for new messages...")
        await self.client.run_until_disconnected()

    async def handler(self, event):
        try:
            message_content = event.message.message
            if not message_content:
                return
            logging.info(f"Received message: {message_content}")

            await self.process_message(message_content)
        except Exception as e:
            logging.error(f"Error in handler: {e}", exc_info=True)

    async def process_message(self, message_content):
        """Process a new message from Telegram."""
        try:
            # Handle case where message_content is already a string
            if isinstance(message_content, str):
                message_text = message_content
            else:
                # Handle Telegram message object
                if not message_content or not hasattr(message_content, 'text'):
                    return
                message_text = message_content.text
                
                # Get channel ID if available
                channel_id = None
                if hasattr(message_content, 'peer_id') and hasattr(message_content.peer_id, 'channel_id'):
                    channel_id = message_content.peer_id.channel_id
            
            logging.info(f"Processing message: {message_text}")
            
            # Initialize trading agent if not exists
            if not self.trading_agent:
                logging.info("Initializing trading agent")
                self.trading_agent = TradingAgent(self.together_client, self.mt5_service)
            
            # Send to AI for analysis
            logging.info("Sending message to AI for analysis")
            
            # Check for direct trade signals using simple pattern matching first
            action = self._detect_direct_signal(message_text)
            
            # Send to trading agent for full analysis
            decision = await self.trading_agent.analyze_and_decide(message_text, action)
            if not decision:
                logging.error("Failed to get decision from trading agent")
                self.log_signal.emit("Analysis failed")
                return
                
            # Update GUI with analysis
            risk_assessment = decision.get("risk_assessment", "No risk assessment available")
            self.log_signal.emit(f"AI Analysis: {decision.get('reasoning', 'No reasoning available')}")
            self.log_signal.emit(f"Risk Assessment: {risk_assessment}")
            
            # Only execute if a trade action is required
            if decision.get("action") in ["buy", "sell"]:
                # Execute the trade
                execution_result = self.trading_agent.execute_decision(decision)
                
                # Update GUI with execution result
                if execution_result and execution_result.get("success"):
                    self.log_signal.emit(f"Trade executed: {execution_result.get('message', '')}")
                else:
                    error_msg = execution_result.get("message", "Unknown error") if execution_result else "Failed to execute trade"
                    self.log_signal.emit(f"Trade failed: {error_msg}")
            else:
                # No trade action required
                self.log_signal.emit(f"No trade action taken: {decision.get('action', 'no action')}")
                
        except Exception as e:
            logging.error(f"Error processing message: {e}", exc_info=True)
            self.log_signal.emit("Error")
            self.log_signal.emit(f"Failed to process message: {str(e)}")

    def _detect_direct_signal(self, message_text):
        """Detect direct trading signals from message text using simple pattern matching."""
        message_lower = message_text.lower()
        
        # Check for buy/sell signals
        if "buy now" in message_lower or "buy" in message_lower and "gold" in message_lower:
            return "buy"
        elif "sell now" in message_lower or "sell" in message_lower and "gold" in message_lower:
            return "sell"
            
        return None

    async def execute_agent_decision(self, decision):
        try:
            if decision["decision"] == TradingDecision.EXECUTE_TRADE:
                await self.handle_execute_trade(decision)
            elif decision["decision"] == TradingDecision.MODIFY_TRADE:
                await self.handle_modify_trade(decision)
            elif decision["decision"] == TradingDecision.CLOSE_TRADE:
                await self.handle_close_trade(decision)
            elif decision["decision"] == TradingDecision.SET_BREAKEVEN:
                await self.handle_breakeven(decision)
            else:
                logging.info(f"No action taken. Reasoning: {decision.get('reasoning')}")
                
            logging.info(f"Risk Assessment: {decision.get('risk_assessment')}")
            
        except Exception as e:
            logging.error(f"Error executing agent decision: {e}", exc_info=True)

    async def handle_execute_trade(self, decision):
        """Handle opening a new trade."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol", "XAUUSD")  # Default to XAUUSD if not specified
            direction = params.get("direction")
            entry_price = params.get("entry")
            stop_loss = params.get("stop_loss")
            take_profit = params.get("take_profit", [])

            if not direction:
                logging.error("Missing direction parameter for trade execution")
                return

            # Ensure symbol name is standardized
            symbol = self.mt5_service.standardize_symbol(symbol)
            
            # Log trade intent
            logging.info(f"Attempting to execute {direction} trade on {symbol}")
            logging.info(f"Entry: {entry_price}, SL: {stop_loss}, TP: {take_profit}")
            
            # Calculate default position size (1% risk or minimum allowed)
            account_info = self.mt5_service.get_account_info()
            risk_amount = account_info['balance'] * 0.01  # 1% risk
            
            # Calculate position size based on stop loss
            volume = 0.01  # Default minimum volume
            if stop_loss and entry_price:
                price_difference = abs(entry_price - stop_loss)
                if price_difference > 0:
                    # For XAUUSD on IC Markets, typically 1 pip = $0.10 for 0.01 lot
                    # So for $1 risk, we need 10 pips with 0.01 lot
                    volume = round(risk_amount / (price_difference * 10), 2)
                    volume = max(0.01, min(volume, 1.0))  # Limit between 0.01 and 1.0 lots
            
            logging.info(f"Calculated position size: {volume} lots with risk amount: ${risk_amount}")

            # Verify margin requirements before executing
            order_type_enum = mt5.ORDER_TYPE_BUY if direction.lower() == "buy" else mt5.ORDER_TYPE_SELL
            margin_check = self.mt5_service.check_margin_for_trade(symbol, volume, order_type_enum)
            if not margin_check["result"]:
                logging.error(f"Cannot execute trade: {margin_check['message']}")
                self.log_signal.emit(f"Trade rejected - Insufficient margin: {margin_check['message']}")
                return
            
            logging.info(f"Margin check passed: {margin_check['message']}")

            # Execute the trade
            result = self.mt5_service.open_position(
                symbol=symbol,
                order_type=direction,
                volume=volume,
                price=entry_price,
                sl=stop_loss,
                tp=take_profit[0] if take_profit else None
            )

            if result:
                logging.info(f"Successfully opened {direction} position on {symbol}")
                logging.info(f"Entry: {entry_price}, SL: {stop_loss}, TP: {take_profit[0] if take_profit else None}")
                logging.info(f"Volume: {volume} lots (1% risk)")
                
                self.log_signal.emit(f"Trade executed: {direction} {symbol} at {entry_price}")
                
                # Store trade information
                self.trades[symbol] = Trade(
                    symbol=symbol,
                    direction=direction,
                    entry=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                self.trades[symbol].tickets.append(result["ticket"])
                self.trades[symbol].state = TradeState.OPEN
            else:
                logging.error("Failed to open position")
                self.log_signal.emit(f"Trade failed: Could not execute {direction} {symbol}")
                
                # Try to get the last error from MT5
                try:
                    error_code = mt5.last_error()
                    if error_code:
                        logging.error(f"MT5 error code: {error_code}")
                        self.log_signal.emit(f"MT5 error: {error_code}")
                except Exception as e:
                    logging.error(f"Could not get MT5 error: {e}")

        except Exception as e:
            logging.error(f"Error in handle_execute_trade: {e}", exc_info=True)
            self.log_signal.emit(f"Trade error: {str(e)}")

    async def handle_modify_trade(self, decision):
        """Handle modifying an existing trade."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol", "XAUUSD")
            stop_loss = params.get("stop_loss")
            take_profit = params.get("take_profit", [])

            # Ensure symbol name is standardized
            symbol = self.mt5_service.standardize_symbol(symbol) 

            if symbol not in self.trades:
                logging.error(f"No active trade found for {symbol}")
                return

            trade = self.trades[symbol]
            
            # Clean up closed positions first
            await self.clean_closed_positions(trade)
            
            if not trade.tickets:
                logging.info(f"No active positions left for {symbol}")
                return

            for ticket in trade.tickets:
                result = self.mt5_service.modify_position(
                    ticket=ticket,
                    sl=stop_loss,
                    tp=take_profit[0] if take_profit else None
                )
                
                if result:
                    logging.info(f"Successfully modified position {ticket}")
                    trade.stop_loss = stop_loss if stop_loss is not None else trade.stop_loss
                    trade.take_profit = take_profit if take_profit else trade.take_profit
                else:
                    logging.error(f"Failed to modify position {ticket}")

        except Exception as e:
            logging.error(f"Error in handle_modify_trade: {e}", exc_info=True)

    async def handle_close_trade(self, decision):
        """Handle closing a trade."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol", "XAUUSD")

            # Ensure symbol name is standardized
            symbol = self.mt5_service.standardize_symbol(symbol)

            if symbol not in self.trades:
                logging.error(f"No active trade found for {symbol}")
                return

            trade = self.trades[symbol]
            success_count = 0
            
            for ticket in list(trade.tickets):  # Use a copy of the list since we'll modify it
                position = self.mt5_service.get_position(ticket)
                if not position:
                    logging.info(f"Position {ticket} not found, may already be closed")
                    trade.tickets.remove(ticket)
                    success_count += 1
                    continue
                    
                result = self.mt5_service.close_position(ticket)
                if result:
                    logging.info(f"Successfully closed position {ticket}")
                    trade.tickets.remove(ticket)
                    success_count += 1
                else:
                    logging.error(f"Failed to close position {ticket}")

            if success_count > 0 and not trade.tickets:
                logging.info(f"All positions for {symbol} closed successfully")
                trade.state = TradeState.CLOSED
                del self.trades[symbol]

        except Exception as e:
            logging.error(f"Error in handle_close_trade: {e}", exc_info=True)

    async def handle_breakeven(self, decision):
        """Handle setting a trade to breakeven."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol", "XAUUSD")

            # Ensure symbol name is standardized
            symbol = self.mt5_service.standardize_symbol(symbol)

            if symbol not in self.trades:
                logging.error(f"No active trade found for {symbol}")
                return

            trade = self.trades[symbol]
            
            # Clean up closed positions first
            await self.clean_closed_positions(trade)
            
            if not trade.tickets:
                logging.info(f"No active positions left for {symbol}")
                return

            success_count = 0
            for ticket in trade.tickets:
                position = self.mt5_service.get_position(ticket)
                if not position:
                    logging.warning(f"Position {ticket} not found, removing from tracking")
                    trade.tickets.remove(ticket)
                    continue
                    
                # Set stop loss to entry price (breakeven)
                result = self.mt5_service.modify_position(
                    ticket=ticket,
                    sl=trade.entry
                )
                
                if result:
                    logging.info(f"Successfully set position {ticket} to breakeven")
                    success_count += 1
                else:
                    logging.error(f"Failed to set position {ticket} to breakeven")

            if success_count > 0:
                trade.state = TradeState.BREAKEVEN
                trade.stop_loss = trade.entry
                logging.info(f"Set {success_count}/{len(trade.tickets)} positions to breakeven for {symbol}")

        except Exception as e:
            logging.error(f"Error in handle_breakeven: {e}", exc_info=True)

    async def clean_closed_positions(self, trade: Trade):
        """Remove closed position tickets from the trade."""
        open_tickets = []
        for ticket in trade.tickets:
            position = self.mt5_service.get_position(ticket)
            if position:
                open_tickets.append(ticket)
            else:
                logging.info(f"Position {ticket} for {trade.symbol} has been closed or not found.")
        
        closed_tickets = set(trade.tickets) - set(open_tickets)
        if closed_tickets:
            logging.info(f"Removing closed tickets for {trade.symbol}: {closed_tickets}")
        
        trade.tickets = open_tickets
        
        if not trade.tickets:
            trade.state = TradeState.CLOSED

    async def clean_closed_trades(self):
        """Clean up trades with all closed positions."""
        closed_symbols = []
        for symbol, trade in list(self.trades.items()):
            await self.clean_closed_positions(trade)
            if trade.state == TradeState.CLOSED or not trade.tickets:
                closed_symbols.append(symbol)
        
        for symbol in closed_symbols:
            if symbol in self.trades:
                del self.trades[symbol]
                logging.info(f"Removed closed trade for {symbol}")

    async def periodic_cleanup(self):
        """Periodically clean up closed trades."""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                logging.info("Performing periodic cleanup of closed trades")
                await self.clean_closed_trades()
            except Exception as e:
                logging.error(f"Error in periodic cleanup: {e}")