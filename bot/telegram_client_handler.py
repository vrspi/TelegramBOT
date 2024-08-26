import logging
import asyncio
from telethon import TelegramClient, events
from PySide6.QtCore import QObject, Signal, Slot
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
import json5
import traceback
import threading

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
        self.opened_trades = []
        self.loop = None
        self.thread = None

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
            logging.info(f"Starting to process message: {message_content}")
            analysis = await self.analyze_message(message_content)
            
            logging.info(f"Analysis result: {analysis}")
            
            if analysis['action'] is None:
                logging.info(f"Non-actionable message received and processed: {message_content}")
                logging.info("Waiting for next message...")
                return

            logging.info(f"Proceeding with action: {analysis['action']}")

            if analysis['action'] == 'open_trade':
                await self.synchronize_trades(analysis['symbol'])
                if self.opened_trades:
                    await self.adjust_existing_trades(analysis)
                else:
                    await self.open_trades(analysis)
            elif analysis['action'] == 'update_trade':
                await self.update_trades(analysis)
            elif analysis['action'] == 'breakeven':
                await self.handle_breakeven()
            elif analysis['action'] == 'close_trade':
                await self.close_trades(analysis)
            else:
                logging.info(f"Unrecognized action in message: {message_content}")
        except Exception as e:
            logging.error(f"Error processing message: {e}", exc_info=True)
        finally:
            logging.info("Message processing complete. Waiting for next message...")

    async def adjust_existing_trades(self, analysis):
        if not self.opened_trades:
            logging.info("No trades to adjust.")
            return

        logging.info(f"Adjusting existing trades with fixed 300 pips SL and 1100 pips TP")

        for trade_ticket in self.opened_trades:
            trade = self.mt5_service.get_open_position(trade_ticket)
            if trade is None:
                logging.error(f"Failed to retrieve trade information for ticket {trade_ticket}")
                continue

            current_price = self.mt5_service.get_current_price(trade.symbol)
            logging.info(f"Attempting to adjust trade {trade_ticket}. Current price: {current_price}, Current SL: {trade.sl}, Current TP: {trade.tp}")
            result = self.mt5_service.modify_position(trade_ticket)

            if result is None:
                logging.error(f"Failed to adjust trade {trade_ticket}: No result returned")
            elif result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                # Get the updated position to log the new SL and TP
                updated_trade = self.mt5_service.get_open_position(trade_ticket)
                if updated_trade:
                    logging.info(f"Trade {trade_ticket} adjusted successfully. New SL: {updated_trade.sl}, New TP: {updated_trade.tp}")
                else:
                    logging.info(f"Trade {trade_ticket} adjusted successfully, but couldn't retrieve updated values.")
            else:
                logging.error(f"Failed to adjust trade {trade_ticket}: {result.comment}")

    async def analyze_message(self, message_content):
            max_retries = 3
            retry_delay = 5  # seconds

            for attempt in range(max_retries):
                try:
                    prompt = self.generate_analysis_prompt(message_content)
                    logging.info(f"Sending prompt to Together API: {prompt}")
                    
                    response = self.together_client.chat_completion(prompt)
                    logging.info(f"Received raw response from Together API: {response}")
                    
                    if response is None:
                        logging.info("Failed to get a valid response from Together API.")
                        return {'action': None}

                    logging.info(f"Response object type: {type(response)}")
                    logging.info(f"Response attributes: {dir(response)}")

                    if not hasattr(response, 'choices') or not response.choices:
                        logging.error("Response does not have 'choices' attribute or it's empty")
                        return {'action': None}

                    raw_response = response.choices[0].message.content.strip()
                    logging.info(f"Raw response content: {raw_response}")
                    
                    clean_response = raw_response.strip().strip('```')
                    logging.info(f"Cleaned AI Response: {clean_response}")

                    try:
                        parsed_response = json5.loads(clean_response)
                        logging.info(f"Parsed JSON response: {parsed_response}")
                        # Ensure that 'action' is always present in the response
                        if 'action' not in parsed_response:
                            parsed_response['action'] = None
                        return parsed_response
                    except ValueError as e:
                        logging.error(f"Failed to decode JSON5: {e} - Cleaned Response: {clean_response}")
                        return {'action': None}
                except Exception as e:
                    logging.error(f"Error in analyze_message (attempt {attempt + 1}/{max_retries}): {e}", exc_info=True)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        logging.error("Max retries reached. Returning None.")
                        return {'action': None}

    def generate_analysis_prompt(self, message_content):
        return (
            "(YOU SPEAK ONLY JSON) You are an expert trading assistant. Analyze the following message and extract key information. "
            "Respond with a JSON object containing the following fields:\n"
            "- action: 'open_trade', 'update_trade', 'breakeven', 'close_trade', or 'After Trade'\n"
                "- symbol: the trading symbol (XAUUSD.sml)\n"
                "- direction: 'buy' or 'sell'\n"
                "- entry: entry price or price range (can be a single number or an object with 'min' and 'max')\n"
                "- stop_loss: stop loss price\n"
                "- take_profit: take profit price(s) (can be a single number, an array, or an object with 'tp1', 'tp2', etc.)\n"
                "- comment: any additional information\n\n"
                f"Message:\n{message_content}\n"
            )

    async def open_trades(self, analysis):
        if self.opened_trades:
            logging.info("Trades are already open. New trades will not be executed.")
            return

        symbol_info = self.get_symbol_info(analysis['symbol'])
        if not symbol_info:
            logging.error(f"Failed to get symbol info for {analysis['symbol']}")
            return

        current_price = symbol_info.ask if analysis['direction'] == "buy" else symbol_info.bid

        logging.info(f"Attempting to open {analysis['direction']} trade for {symbol_info.name} at {current_price}")

        for i in range(4):
            result = self.execute_trade(analysis['direction'], symbol_info.name, current_price)
            if result:
                self.opened_trades.append(result.order)  # Store the trade ticket
                logging.info(f"Trade {i+1}/4: {analysis['direction']} {symbol_info.name} executed successfully at {current_price}.")
            else:
                logging.warning(f"Trade {i+1}/4: Failed to execute trade. Check if auto-trading is enabled in MetaTrader 5.")

        if not self.opened_trades:
            logging.error("No trades were opened. Please check your MetaTrader 5 settings and ensure auto-trading is enabled.")
        else:
            logging.info(f"Successfully opened {len(self.opened_trades)} out of 4 attempted trades.")

    def get_symbol_info(self, symbol):
        possible_symbols = [symbol, f"{symbol}.sml", symbol.upper()]
        symbol_info = next((self.mt5_service.get_symbol_info(s) for s in possible_symbols if self.mt5_service.get_symbol_info(s)), None)

        if not symbol_info:
            logging.info(f"Failed to get symbol info for {symbol}. Tried symbols: {', '.join(possible_symbols)}")
        return symbol_info

    def execute_trade(self, action, symbol, price):
        request = {
            "action": self.mt5_service.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": 0.02,
            "type": self.mt5_service.ORDER_TYPE_BUY if action == "buy" else self.mt5_service.ORDER_TYPE_SELL,
            "price": price,
            "magic": 234000,
            "comment": f"Auto trade: {action}",
            "type_time": self.mt5_service.ORDER_TIME_GTC
        }
        result = self.mt5_service.send_order(request)
        if result is None:
            logging.error("Failed to execute trade: No result returned")
            return None
        if result.retcode != self.mt5_service.TRADE_RETCODE_DONE:
            logging.error(f"Failed to execute trade: {result.comment} (retcode: {result.retcode})")
            return None
        return result

    async def update_trades(self, analysis):
        if not self.opened_trades:
            logging.info("No trades to update.")
            return

        trade_data = await self.parse_trade_data(analysis)
        if not trade_data:
            return

        sl = trade_data.get("stop_loss")
        tp = trade_data.get("take_profit")
        tp1, tp2 = self.parse_take_profit(tp)

        for trade in self.opened_trades:
            self.update_trade_sl_tp(trade, sl, tp1, tp2)

    async def parse_trade_data(self, analysis):
        prompt = self.generate_ai_prompt(analysis)
        response = self.together_client.chat_completion(prompt)
        if response is None:
            logging.info("Failed to get a valid response from Together API.")
            return None

        raw_response = response.choices[0].message.content.strip()
        clean_response = raw_response.strip().strip('```')
        logging.info(f"Cleaned AI Response: {clean_response}")

        try:
            return json5.loads(clean_response)
        except ValueError as e:
            logging.info(f"Failed to decode JSON5: {e} - Cleaned Response: {clean_response}")
            return None

    def generate_ai_prompt(self, analysis):
        return (
            "You are a JSON writer expert. You will receive messages about trading and your role is to extract the key information and "
            "structure it into a JSON format (YOU SPEAK ONLY JSON).\n\n"
            "Here's how the JSON structure should look:\n\n"
            "{\n"
            "  \"action\": [\"buy\", \"sell\", \"close\", \"hold\", \"comment\"],\n"
            "  \"symbol\": \"string\",\n"
            "  \"entry\": {\n"
            "    \"price\": [\"float\", \"null\"],\n"
            "    \"range_start\": [\"float\", \"null\"],\n"
            "    \"range_end\": [\"float\", \"null\"]\n"
            "  },\n"
            "  \"take_profit\": [\"float\", \"null\"],\n"
            "  \"stop_loss\": [\"float\", \"null\"],\n"
            "  \"comment\": \"string\"\n"
            "}\n\n"
            f"Message:\n{analysis}\n"
        )

    def parse_take_profit(self, tp):
        if isinstance(tp, list):
            return tp if len(tp) >= 2 else (tp[0], None)
        return tp, None

    def update_trade_sl_tp(self, trade, sl, tp1, tp2):
        request = {
            "action": self.mt5_service.TRADE_ACTION_SLTP,
            "symbol": trade.symbol,
            "volume": trade.volume,
            "type": trade.type,
            "position": trade.ticket,
            "sl": sl,
            "tp": tp1 if trade.volume == 0.02 else tp2,
            "deviation": 20,
            "magic": 234000,
            "comment": "Update SL/TP",
        }

        result = self.mt5_service.send_order(request)

        if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
            logging.info(f"Trade updated successfully with SL/TP for {trade.symbol}.")
        else:
            logging.info(f"Failed to update trade: {result.comment}")

    async def handle_breakeven(self):
        if not self.opened_trades:
            logging.info("No trades to adjust for breakeven.")
            return

        logging.info("Handling breakeven...")
        
        # If there are 2 or fewer trades, close all of them
        if len(self.opened_trades) <= 2:
            logging.info(f"Only {len(self.opened_trades)} trade(s) open. Closing all trades.")
            for trade_ticket in self.opened_trades.copy():  # Use copy to avoid modifying list while iterating
                trade = self.mt5_service.get_open_position(trade_ticket)
                if trade is None:
                    logging.error(f"Failed to retrieve trade information for ticket {trade_ticket}")
                    continue

                result = self.mt5_service.close_position(trade_ticket, trade.volume)

                if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                    self.opened_trades.remove(trade_ticket)
                    logging.info(f"Trade closed successfully for breakeven: {trade.symbol}.")
                else:
                    logging.error(f"Failed to close trade for breakeven: {result.comment if result else 'Unknown error'}")
            return  # Exit the method after closing all trades

        # If more than 2 trades are open, proceed with the breakeven logic
        half_trades_to_close = self.opened_trades[:len(self.opened_trades) // 2]
        half_trades_to_update = self.opened_trades[len(self.opened_trades) // 2:]

        # Close half of the trades
        for trade_ticket in half_trades_to_close:
            trade = self.mt5_service.get_open_position(trade_ticket)
            if trade is None:
                logging.error(f"Failed to retrieve trade information for ticket {trade_ticket}")
                continue

            result = self.mt5_service.close_position(trade_ticket, trade.volume)

            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                self.opened_trades.remove(trade_ticket)
                logging.info(f"Trade closed successfully for breakeven: {trade.symbol}.")
            else:
                logging.error(f"Failed to close trade for breakeven: {result.comment if result else 'Unknown error'}")

        # Calculate breakeven price for remaining trades
        remaining_trades = [self.mt5_service.get_open_position(ticket) for ticket in half_trades_to_update]
        remaining_trades = [trade for trade in remaining_trades if trade is not None]
        
        if not remaining_trades:
            logging.error("No remaining trades to set breakeven.")
            return

        total_volume = sum(trade.volume for trade in remaining_trades)
        weighted_price_sum = sum(trade.price_open * trade.volume for trade in remaining_trades)
        breakeven_price = weighted_price_sum / total_volume

        logging.info(f"Calculated breakeven price: {breakeven_price}")

        # Update remaining trades with breakeven stop loss
        for trade in remaining_trades:
            current_price = self.mt5_service.get_current_price(trade.symbol)
            if current_price is None:
                logging.error(f"Failed to get current price for {trade.symbol}")
                continue

            symbol_info = self.mt5_service.get_symbol_info(trade.symbol)
            if symbol_info is None:
                logging.error(f"Failed to get symbol info for {trade.symbol}")
                continue

            # Add a small buffer to the breakeven price to avoid immediate stop-out
            buffer_pips = 5  # You can adjust this value
            buffer_price = buffer_pips * symbol_info.point

            if trade.type == self.mt5_service.ORDER_TYPE_BUY:
                breakeven_sl = breakeven_price - buffer_price
            else:  # SELL order
                breakeven_sl = breakeven_price + buffer_price

            result = self.mt5_service.modify_position(trade.ticket, sl=breakeven_sl)

            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                logging.info(f"Trade {trade.ticket} updated to breakeven. New SL: {breakeven_sl}")
            else:
                logging.error(f"Failed to set breakeven for trade {trade.ticket}: {result.comment if result else 'Unknown error'}")

            logging.info(f"Trade {trade.ticket} - Current price: {current_price}, Breakeven price: {breakeven_price}, New SL: {breakeven_sl}")

    async def close_trades(self, analysis):
        if not self.opened_trades:
            logging.info("No trades to close.")
            return

        for trade in self.opened_trades:
            request = {
                "action": self.mt5_service.TRADE_ACTION_DEAL,
                "symbol": trade.symbol,
                "volume": trade.volume,
                "type": self.mt5_service.ORDER_TYPE_SELL if trade.type == self.mt5_service.ORDER_TYPE_BUY else self.mt5_service.ORDER_TYPE_BUY,
                "position": trade.ticket,
                "deviation": 20,
                "magic": 234000,
                "comment": "Close trade",
            }

            result = self.mt5_service.send_order(request)

            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                self.opened_trades.remove(trade)
                logging.info(f"Trade closed successfully: {trade.symbol}.")
            else:
                logging.info(f"Failed to close trade: {result.comment}")

    async def synchronize_trades(self, symbol):
        mt5_open_trades = self.mt5_service.get_open_positions(symbol)
        self.opened_trades = [trade for trade in self.opened_trades if trade in mt5_open_trades]
        logging.info(f"Synchronized trades for {symbol}. Current open trades: {self.opened_trades}")