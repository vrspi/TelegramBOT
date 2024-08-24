import logging
import asyncio
from telethon import TelegramClient, events
from PySide6.QtCore import QThread, Signal
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
import json5

class TelegramClientHandler(QThread):
    log_signal = Signal(str)

    def __init__(self, api_id, api_hash, source_channel_id, destination_chat_id, mt5_service: MT5Service, together_client: TogetherClient):
        super().__init__()
        self.api_id = api_id
        self.api_hash = api_hash
        self.source_channel_id = source_channel_id
        self.destination_chat_id = destination_chat_id
        self.mt5_service = mt5_service
        self.together_client = together_client
        self.client = None
        self.opened_trades = []  # To handle multiple trades

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.client = TelegramClient('session_name', self.api_id, self.api_hash)
        loop.run_until_complete(self.start_client())

    async def start_client(self):
        await self.client.start()
        logging.info(f"Listening for messages in channel ID: {self.source_channel_id}")
        self.client.add_event_handler(self.handler, events.NewMessage(chats=int(self.source_channel_id)))
        logging.info("Telegram client started. Listening for new messages...")
        await self.client.run_until_disconnected()

    async def handler(self, event):
        message_content = event.message.message
        if not message_content:
            return
        logging.info(f"Received message: {message_content}")

        try:
            if "sell" in message_content.lower() or "buy" in message_content.lower():
                await self.handle_trade(message_content)
            elif any(keyword in message_content.lower() for keyword in ["breakeven", "set breakeven", "secure"]):
                await self.handle_breakeven()
            else:
                logging.info(f"General message received: {message_content}")
        except Exception as e:
            logging.error(f"Failed to process message: {e}")

    async def handle_trade(self, message_content):
        if "now" in message_content.lower():
            await self.open_trades(message_content)
        elif any(keyword in message_content.lower() for keyword in ["tp", "sl", "take profit"]):
            await self.update_trades(message_content)

    async def open_trades(self, message_content):
        if self.opened_trades:
            logging.info("Trades are already open. New trades will not be executed.")
            return

        # Here, we open four trades each with 0.02 lot size.
        action = "sell" if "sell" in message_content.lower() else "buy"
        symbol = "XAUUSD"  # Assuming "Gold" corresponds to "XAUUSD"
        volume = 0.02
        possible_symbols = ["GOLD", "XAUUSD", "GC", "GOLDUSD", "XAUUSD.sml", "Gold", "XAUUSD.sml"]
        symbol_info = next((self.mt5_service.get_symbol_info(s) for s in possible_symbols if self.mt5_service.get_symbol_info(s)), None)

        if not symbol_info:
            logging.info(f"Failed to get symbol info for Gold. Tried symbols: {', '.join(possible_symbols)}")
            return

        current_price = symbol_info.ask if action == "buy" else symbol_info.bid

        for _ in range(4):
            request = {
                "action": self.mt5_service.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": self.mt5_service.ORDER_TYPE_BUY if action == "buy" else self.mt5_service.ORDER_TYPE_SELL,
                "price": current_price,
                "magic": 234000,
                "comment": f"Auto trade: {action}",
                "type_time": self.mt5_service.ORDER_TIME_GTC
            }

            result = self.mt5_service.send_order(request)

            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                self.opened_trades.append(result.order)
                logging.info(f"Trade {action} {symbol} executed successfully at {current_price}.")
            else:
                logging.info(f"Failed to execute trade: {result.comment}")

    async def update_trades(self, message_content):
        if not self.opened_trades:
            logging.info("No trades to update.")
            return

        # Parse the incoming message for SL and TP updates
        prompt = (
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
            "Message:\n"
            f"{message_content}\n"
        )

        response = self.together_client.chat_completion(prompt)
        if response is None:
            logging.info("Failed to get a valid response from Together API.")
            return

        raw_response = response.choices[0].message.content.strip()
        logging.info(f"Raw AI Response: `{raw_response}`")

        if not raw_response:
            logging.info("The AI response was empty. Skipping JSON5 parsing.")
            return

        clean_response = raw_response.strip().strip('```')
        logging.info(f"Cleaned AI Response: {clean_response}")

        try:
            trade_data = json5.loads(clean_response)
            sl = trade_data.get("stop_loss")
            tp = trade_data.get("take_profit")

            if isinstance(tp, list):
                tp1, tp2 = tp if len(tp) >= 2 else (tp[0], None)
            else:
                tp1, tp2 = tp, None

            for trade in self.opened_trades:
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

        except ValueError as e:
            logging.info(f"Failed to decode JSON5: {e} - Cleaned Response: {clean_response}")

    async def handle_breakeven(self):
        if not self.opened_trades:
            logging.info("No trades to adjust for breakeven.")
            return

        half_trades_to_close = self.opened_trades[:len(self.opened_trades) // 2]
        half_trades_to_update = self.opened_trades[len(self.opened_trades) // 2:]

        # Close half of the trades
        for trade in half_trades_to_close:
            request = {
                "action": self.mt5_service.TRADE_ACTION_DEAL,
                "symbol": trade.symbol,
                "volume": trade.volume,
                "type": trade.type,
                "position": trade.ticket,
                "deviation": 20,
                "magic": 234000,
                "comment": "Breakeven close half",
            }

            result = self.mt5_service.send_order(request)

            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                self.opened_trades.remove(trade)
                logging.info(f"Trade closed successfully for breakeven: {trade.symbol}.")
            else:
                logging.info(f"Failed to close trade for breakeven: {result.comment}")

        # Set breakeven (adjust stop loss) for the remaining trades
        for trade in half_trades_to_update:
            request = {
                "action": self.mt5_service.TRADE_ACTION_SLTP,
                "symbol": trade.symbol,
                "volume": trade.volume,
                "type": trade.type,
                "position": trade.ticket,
                "sl": trade.price_open,  # Set stop loss to breakeven (entry price)
                "deviation": 20,
                "magic": 234000,
                "comment": "Set breakeven",
            }

            result = self.mt5_service.send_order(request)

            if result and result.retcode == self.mt5_service.TRADE_RETCODE_DONE:
                logging.info(f"Trade updated to breakeven for {trade.symbol}.")
            else:
                logging.info(f"Failed to set breakeven for trade: {result.comment}")