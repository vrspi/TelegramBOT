import logging
import asyncio
from telethon import TelegramClient, events
from PySide6.QtCore import QObject, Signal, Slot
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
import json5
import traceback
import threading
import re
from enum import Enum
from typing import Dict, List, Optional
from bot.agents.trading_agent import TradingAgent, AccountInfo, MarketContext, TradingDecision

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
        try:
            # Get current account and market context
            account_info = AccountInfo(**self.mt5_service.get_account_info())
            market_context = MarketContext(**self.mt5_service.get_market_context("XAUUSD.sml"))
            
            # Create trading agent if not exists
            if not hasattr(self, 'trading_agent'):
                self.trading_agent = TradingAgent(self.together_client)
            
            # Get agent's decision
            decision = await self.trading_agent.analyze_and_decide(
                message_content,
                account_info,
                market_context,
                self.trades
            )
            
            # Execute the decision
            await self.execute_agent_decision(decision)
            
        except Exception as e:
            logging.error(f"Error processing message: {e}", exc_info=True)

    async def execute_agent_decision(self, decision):
        try:
            if decision["decision"] == TradingDecision.EXECUTE_TRADE:
                await self.handle_open_trade_decision(decision)
            elif decision["decision"] == TradingDecision.MODIFY_TRADE:
                await self.handle_modify_trade_decision(decision)
            elif decision["decision"] == TradingDecision.CLOSE_TRADE:
                await self.handle_close_trade_decision(decision)
            elif decision["decision"] == TradingDecision.SET_BREAKEVEN:
                await self.handle_breakeven_decision(decision)
            else:
                logging.info(f"No action taken. Reasoning: {decision.get('reasoning')}")
                
            logging.info(f"Risk Assessment: {decision.get('risk_assessment')}")
            
        except Exception as e:
            logging.error(f"Error executing agent decision: {e}", exc_info=True)

    async def handle_open_trade_decision(self, decision):
        """Handle opening a new trade."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol")
            direction = params.get("direction")
            entry_price = params.get("entry")
            stop_loss = params.get("stop_loss")
            take_profit = params.get("take_profit", [])

            if not all([symbol, direction]):
                logging.error("Missing required parameters for trade execution")
                return

            # Get current market price if entry price is not specified
            if not entry_price:
                symbol_info = self.mt5_service.get_symbol_info(symbol)
                if not symbol_info:
                    logging.error("Failed to get symbol info")
                    return
                entry_price = symbol_info.ask if direction.lower() == "buy" else symbol_info.bid

            # Calculate default stop loss and take profit if not provided
            if not stop_loss or not take_profit:
                # Default to 100 pips SL and 200 pips TP
                pip_value = 0.1  # For XAUUSD
                if direction.lower() == "buy":
                    stop_loss = entry_price - (100 * pip_value)
                    take_profit = [entry_price + (200 * pip_value)]
                else:
                    stop_loss = entry_price + (100 * pip_value)
                    take_profit = [entry_price - (200 * pip_value)]

            # Calculate position size (1% risk)
            account_info = self.mt5_service.get_account_info()
            risk_amount = account_info['balance'] * 0.01  # 1% risk
            price_difference = abs(entry_price - stop_loss)
            if price_difference > 0:
                volume = round(risk_amount / (price_difference * 10), 2)  # 10 USD per pip for 0.01 lot
                volume = max(0.01, min(volume, 1.0))  # Limit between 0.01 and 1.0 lots
            else:
                volume = 0.01  # Default to minimum volume

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
                # Store trade information
                self.trades[symbol] = Trade(
                    symbol=symbol,
                    direction=direction,
                    entry=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                self.trades[symbol].tickets.append(result["ticket"])
            else:
                logging.error("Failed to open position")

        except Exception as e:
            logging.error(f"Error in handle_open_trade_decision: {e}", exc_info=True)

    async def handle_modify_trade_decision(self, decision):
        """Handle modifying an existing trade."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol")
            stop_loss = params.get("stop_loss")
            take_profit = params.get("take_profit", [])

            if not symbol or symbol not in self.trades:
                logging.error(f"No active trade found for {symbol}")
                return

            trade = self.trades[symbol]
            for ticket in trade.tickets:
                result = self.mt5_service.modify_position(
                    ticket=ticket,
                    sl=stop_loss,
                    tp=take_profit[0] if take_profit else None
                )
                if result:
                    logging.info(f"Successfully modified position {ticket}")
                    trade.stop_loss = stop_loss
                    trade.take_profit = take_profit
                else:
                    logging.error(f"Failed to modify position {ticket}")

        except Exception as e:
            logging.error(f"Error in handle_modify_trade_decision: {e}", exc_info=True)

    async def handle_close_trade_decision(self, decision):
        """Handle closing a trade."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol")

            if not symbol or symbol not in self.trades:
                logging.error(f"No active trade found for {symbol}")
                return

            trade = self.trades[symbol]
            for ticket in trade.tickets:
                result = self.mt5_service.close_position(ticket)
                if result:
                    logging.info(f"Successfully closed position {ticket}")
                else:
                    logging.error(f"Failed to close position {ticket}")

            if all(result):
                del self.trades[symbol]

        except Exception as e:
            logging.error(f"Error in handle_close_trade_decision: {e}", exc_info=True)

    async def handle_breakeven_decision(self, decision):
        """Handle setting a trade to breakeven."""
        try:
            params = decision.get("params", {})
            symbol = params.get("symbol")

            if not symbol or symbol not in self.trades:
                logging.error(f"No active trade found for {symbol}")
                return

            trade = self.trades[symbol]
            for ticket in trade.tickets:
                position = self.mt5_service.get_position(ticket)
                if position:
                    result = self.mt5_service.modify_position(
                        ticket=ticket,
                        sl=position["price"]  # Set stop loss to entry price
                    )
                    if result:
                        logging.info(f"Successfully set position {ticket} to breakeven")
                        trade.stop_loss = position["price"]
                    else:
                        logging.error(f"Failed to set position {ticket} to breakeven")

        except Exception as e:
            logging.error(f"Error in handle_breakeven_decision: {e}", exc_info=True)

    def classify_message(self, message_content):
        if self.patterns['open_trade'].search(message_content):
            return MessageType.TRADE_OPEN
        elif self.patterns['update_trade'].search(message_content):
            return MessageType.TRADE_UPDATE
        elif self.patterns['close_trade'].search(message_content):
            return MessageType.TRADE_CLOSE
        elif any(keyword in message_content.lower() for keyword in ['ready', 'alert', 'setup', 'running']):
            return MessageType.GENERAL_INFO
        else:
            return MessageType.UNKNOWN

    async def handle_open_trade(self, message_content):
        trade_info = self.parse_trade_info(message_content)
        if not trade_info:
            logging.warning(f"Failed to parse detailed trade info. Attempting simple trade execution.")
            trade_info = self.parse_simple_trade_command(message_content)

        if not trade_info:
            logging.error(f"Failed to parse trade info from message: {message_content}")
            return

        symbol = trade_info['symbol']
        existing_trade = self.trades.get(symbol)

        if existing_trade:
            logging.info(f"Trade for {symbol} already exists. Adjusting SL and TP.")
            await self.adjust_existing_trade(existing_trade, trade_info)
        else:
            logging.info(f"Opening new trade for {symbol}.")
            self.trades[symbol] = Trade(**trade_info)
            await self.execute_trade(self.trades[symbol])

        # Clean up closed trades after each operation
        await self.clean_closed_trades()

    def parse_trade_info(self, message_content) -> Optional[Dict]:
        # Parse detailed trade info
        match = re.search(r'(Gold|XAUUSD)\s+(buy|sell)\s*:\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)', message_content, re.IGNORECASE)
        if not match:
            return None

        symbol, direction, entry_min, entry_max = match.groups()
        sl_match = re.search(r'Sl\s*:\s*(\d+(?:\.\d+)?)', message_content, re.IGNORECASE)
        tp_matches = re.findall(r'Tp\d*\s*:\s*(\d+(?:\.\d+)?)', message_content, re.IGNORECASE)

        return {
            'symbol': 'XAUUSD.sml',
            'direction': direction.lower(),
            'entry': (float(entry_min) + float(entry_max)) / 2,
            'stop_loss': float(sl_match.group(1)) if sl_match else None,
            'take_profit': [float(tp) for tp in tp_matches] if tp_matches else None
        }

    def parse_simple_trade_command(self, message_content) -> Optional[Dict]:
        # Parse simple trade command
        match = re.search(r'(Gold|XAUUSD)\s+(buy|sell)', message_content, re.IGNORECASE)
        if not match:
            return None

        symbol, direction = match.groups()
        return {
            'symbol': 'XAUUSD.sml',
            'direction': direction.lower(),
            'entry': None,  # Will use current market price
            'stop_loss': None,
            'take_profit': None
        }

    async def adjust_existing_trade(self, existing_trade: Trade, new_trade_info: Dict):
        symbol_info = self.mt5_service.get_symbol_info(existing_trade.symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {existing_trade.symbol}")
            return

        # Clean up closed positions
        await self.clean_closed_positions(existing_trade)

        if not existing_trade.tickets:
            logging.info(f"All positions for {existing_trade.symbol} have been closed. Removing trade.")
            del self.trades[existing_trade.symbol]
            return

        current_price = self.mt5_service.get_current_price(existing_trade.symbol)
        if not current_price:
            logging.error(f"Failed to get current price for {existing_trade.symbol}")
            return

        new_sl = new_trade_info.get('stop_loss') or self.calculate_default_sl(current_price, existing_trade.direction, symbol_info.point, existing_trade.symbol)
        new_tp = new_trade_info.get('take_profit', [None])[0] or self.calculate_default_tp(current_price, existing_trade.direction, symbol_info.point, existing_trade.symbol)

        for ticket in existing_trade.tickets:
            result = self.mt5_service.modify_position(ticket, sl=new_sl, tp=new_tp)
            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                logging.info(f"Successfully adjusted SL/TP for trade ticket {ticket}")
            else:
                logging.error(f"Failed to adjust SL/TP for trade ticket {ticket}")

        existing_trade.stop_loss = new_sl
        existing_trade.take_profit = [new_tp]

    async def clean_closed_positions(self, trade: Trade):
        open_tickets = []
        for ticket in trade.tickets:
            position = self.mt5_service.get_position(ticket)
            if position:
                open_tickets.append(ticket)
            else:
                logging.info(f"Position {ticket} for {trade.symbol} has been closed.")
        
        closed_tickets = set(trade.tickets) - set(open_tickets)
        if closed_tickets:
            logging.info(f"Removing closed tickets for {trade.symbol}: {closed_tickets}")
        
        trade.tickets = open_tickets
        
        if not trade.tickets:
            trade.state = TradeState.CLOSED

    async def clean_closed_trades(self):
        closed_symbols = []
        for symbol, trade in self.trades.items():
            await self.clean_closed_positions(trade)
            if trade.state == TradeState.CLOSED:
                closed_symbols.append(symbol)
        
        for symbol in closed_symbols:
            del self.trades[symbol]
            logging.info(f"Removed closed trade for {symbol}")

    async def periodic_cleanup(self):
        while True:
            await asyncio.sleep(300)  # 5 minutes
            await self.clean_closed_trades()

    async def execute_trade(self, trade: Trade):
        symbol_info = self.mt5_service.get_symbol_info(trade.symbol)
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {trade.symbol}")
            return

        current_price = self.mt5_service.get_current_price(trade.symbol)
        if not current_price:
            logging.error(f"Failed to get current price for {trade.symbol}")
            return

        # Calculate default SL and TP if not provided
        if trade.stop_loss is None:
            trade.stop_loss = self.calculate_default_sl(current_price, trade.direction, symbol_info.point, trade.symbol)
        if not trade.take_profit:
            trade.take_profit = [self.calculate_default_tp(current_price, trade.direction, symbol_info.point, trade.symbol)]

        logging.info(f"Calculated SL: {trade.stop_loss}, TP: {trade.take_profit[0]}")

        for i in range(4):
            result = self.mt5_service.open_trade(
                symbol=trade.symbol,
                trade_type=self.mt5_service.TRADE_ACTION_DEAL,
                order_type=self.mt5_service.ORDER_TYPE_SELL if trade.direction == 'sell' else self.mt5_service.ORDER_TYPE_BUY,
                price=current_price,
                volume=0.02,
                sl=trade.stop_loss,
                tp=trade.take_profit[0]
            )
            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                trade.tickets.append(result.order)
                logging.info(f"Trade {i+1}/4: {trade.direction} {trade.symbol} executed successfully.")
            else:
                logging.warning(f"Trade {i+1}/4: Failed to execute trade. {result.comment if result else 'Unknown error'}")

        if trade.tickets:
            trade.state = TradeState.OPEN
            logging.info(f"Successfully opened {len(trade.tickets)} out of 4 attempted trades for {trade.symbol}.")
        else:
            logging.error(f"No trades were opened for {trade.symbol}. Please check your MetaTrader 5 settings.")

    def calculate_default_sl(self, current_price, direction, point, symbol):
        # Calculate a default SL 100 pips away from the current price
        sl_distance = max(100 * point, self.get_min_stop_level(symbol) * point)
        return current_price + sl_distance if direction == 'sell' else current_price - sl_distance

    def calculate_default_tp(self, current_price, direction, point, symbol):
        # Calculate a default TP 200 pips away from the current price
        tp_distance = max(200 * point, self.get_min_stop_level(symbol) * point)
        return current_price - tp_distance if direction == 'sell' else current_price + tp_distance

    def get_min_stop_level(self, symbol):
        symbol_info = self.mt5_service.get_symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Failed to get symbol info for {symbol}")
            return 100  # Default to 100 pips if unable to get symbol info
        return symbol_info.trade_stops_level

    async def handle_update_trade(self, message_content):
        self.log_current_trades()
        keywords = ["pips", "wow", "fly", "breakeven", "secure", "boom", "running", "hit"]
        close_all_keywords = ["hit all takeprofit", "hit takeprofit", "hit first takeprofit"]

        logging.info(f"Checking message: {message_content}")
        
        if any(keyword in message_content.lower() for keyword in keywords):
            logging.info("Keyword found in message")
            for symbol, trade in self.trades.items():
                logging.info(f"Checking trade for symbol: {symbol}")
                if trade.state in [TradeState.OPEN, TradeState.BREAKEVEN, TradeState.PARTIAL_CLOSE]:
                    logging.info(f"Trade is in a valid state for updates: {symbol}")
                    total_volume = sum(self.mt5_service.get_position(ticket).volume for ticket in trade.tickets if self.mt5_service.get_position(ticket))
                    logging.info(f"Total volume for {symbol}: {total_volume}")
                    
                    if total_volume == 0.02 and any(keyword in message_content.lower() for keyword in close_all_keywords):
                        logging.info(f"Closing all trades for {symbol}")
                        await self.close_existing_trade(symbol)
                    else:
                        if "secure" in message_content.lower() or "close half" in message_content.lower():
                            logging.info(f"Closing partial trades for {symbol}")
                            await self.close_partial(trade)
                        if "breakeven" in message_content.lower() and trade.state != TradeState.BREAKEVEN:
                            logging.info(f"Setting breakeven for {symbol}")
                            await self.set_breakeven(trade)
                else:
                    logging.info(f"Trade is not in a valid state for updates: {symbol}")
        else:
            logging.info("No relevant keywords found in message")

    def log_current_trades(self):
        logging.info("Current trades:")
        for symbol, trade in self.trades.items():
            logging.info(f"Symbol: {symbol}, State: {trade.state}, Tickets: {trade.tickets}")

    async def close_partial(self, trade: Trade):
        if not trade.tickets:
            logging.info(f"No open trades for {trade.symbol} to close partially.")
            return

        positions = [self.mt5_service.get_position(ticket) for ticket in trade.tickets]
        open_positions = [pos for pos in positions if pos is not None]
        
        if not open_positions:
            logging.info(f"No open positions found for {trade.symbol}.")
            return

        for position in open_positions[:len(open_positions)//2]:
            volume_to_close = position.volume
            result = self.mt5_service.close_position(position.ticket, volume_to_close)
            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                trade.tickets.remove(position.ticket)
                logging.info(f"Closed trade {position.ticket} on {trade.symbol}, volume: {volume_to_close}.")
            else:
                logging.error(f"Failed to close trade {position.ticket} on {trade.symbol}. {result.comment if result else 'Unknown error'}")

        if trade.tickets:
            trade.state = TradeState.PARTIAL_CLOSE
        else:
            trade.state = TradeState.CLOSED

    async def set_breakeven(self, trade: Trade):
        if not trade.tickets:
            logging.info(f"No open trades for {trade.symbol} to set breakeven.")
            return

        for ticket in trade.tickets:
            position = self.mt5_service.get_position(ticket)
            if position is None:
                logging.error(f"Failed to get position info for ticket {ticket}")
                continue
            
            result = self.mt5_service.modify_position(ticket, sl=trade.entry, tp=position.tp)
            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                logging.info(f"Set breakeven for trade {ticket} on {trade.symbol}.")
            else:
                logging.error(f"Failed to set breakeven for trade {ticket} on {trade.symbol}. {result.comment if result else 'Unknown error'}")

        trade.state = TradeState.BREAKEVEN

    async def close_existing_trade(self, symbol: str):
        trade = self.trades.get(symbol)
        if not trade or not trade.tickets:
            logging.info(f"No open trades for {symbol} to close.")
            return

        for ticket in trade.tickets:
            result = self.mt5_service.close_position(ticket)
            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                logging.info(f"Closed trade {ticket} on {symbol}.")
            else:
                logging.error(f"Failed to close trade {ticket} on {symbol}. {result.comment if result else 'Unknown error'}")

        del self.trades[symbol]

    async def handle_close_trade(self, message_content):
        for symbol, trade in list(self.trades.items()):
            await self.close_existing_trade(symbol)

    async def handle_general_info(self, message_content):
        logging.info(f"General info message: {message_content}")
        # You can add additional logic here if needed

    async def handle_unknown_message(self, message_content):
        logging.info(f"Processing unknown message with LLM: {message_content}")
        analysis = await self.analyze_message_with_llm(message_content)
        logging.info(f"LLM analysis result: {analysis}")
        
        if analysis.get('action') == 'open_trade':
            await self.handle_open_trade(message_content)
        elif analysis.get('action') in ['update_trade', 'breakeven']:
            await self.handle_update_trade(message_content)
        elif analysis.get('action') == 'close_trade':
            await self.handle_close_trade(message_content)
        else:
            logging.info(f"No action taken for message: {message_content}")

    async def analyze_message_with_llm(self, message_content):
        prompt = self.generate_analysis_prompt(message_content)
        response = self.together_client.chat_completion(prompt)
        
        if response is None:
            logging.info("Failed to get a valid response from Together API.")
            return {'action': None}

        try:
            raw_response = response.choices[0].message.content.strip()
            clean_response = raw_response.strip().strip('```')
            parsed_response = json5.loads(clean_response)
            logging.info(f"Parsed LLM response: {parsed_response}")
            return parsed_response
        except Exception as e:
            logging.error(f"Error parsing LLM response: {e}")
            return {'action': None}

    def generate_analysis_prompt(self, message_content):
        return (
            "(YOU SPEAK ONLY JSON) You are an expert trading assistant. Analyze the following message and extract key information. "
            "Respond with a JSON object containing the following fields:\n"
            "- action: 'open_trade', 'update_trade', 'breakeven', 'close_trade', or null if no action\n"
            "- symbol: the trading symbol (XAUUSD.sml)\n"
            "- direction: 'buy' or 'sell'\n"
            "- entry: entry price or price range (can be a single number or an object with 'min' and 'max')\n"
            "- stop_loss: stop loss price\n"
            "- take_profit: take profit price(s) (can be a single number, an array, or an object with 'tp1', 'tp2', etc.)\n"
            "- comment: any additional information\n\n"
            f"Message:\n{message_content}\n"
        )