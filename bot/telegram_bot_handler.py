from utils import logger
import logging 
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from services.mt5_service import MT5Service
from services.together_client import TogetherClient

class TelegramBotHandler:
    def __init__(self, token, channel_id, mt5_service: MT5Service, together_client: TogetherClient):
        self.token = token
        self.channel_id = channel_id
        self.mt5_service = mt5_service
        self.together_client = together_client
        self.application = ApplicationBuilder().token(self.token).build()

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Chat(self.channel_id), self.handle_channel_post))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Received start command")
        await update.message.reply_text('Bot is running and listening to the channel.')

    async def handle_channel_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.channel_post
        if message:
            logger.info(f"New message in channel: {message.text}")
            print(f"New message: {message.text}")

    def run(self):
        logging.info("Starting Telegram bot...")
        self.application.run_polling()
