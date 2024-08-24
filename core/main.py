
import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
import logging
import threading
from PySide6.QtWidgets import QApplication
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
from bot.telegram_client_handler import TelegramClientHandler
from config.config import load_config
from gui.main_app import MainApp  # Make sure this import is correct

def start_telegram_client():
    # Load configuration
    config = load_config()

    # Initialize services
    mt5_service = MT5Service()
    together_client = TogetherClient(api_key=config['TOGETHER_API_KEY'])

    # Initialize and run Telegram client handler
    client_handler = TelegramClientHandler(
        api_id=config['TELEGRAM_API_ID'],
        api_hash=config['TELEGRAM_API_HASH'],
        source_channel_id=config['TELEGRAM_SOURCE_CHANNEL_ID'],
        destination_chat_id=config['TELEGRAM_DESTINATION_CHAT_ID'],
        mt5_service=mt5_service,
        together_client=together_client
    )

    client_handler.run()

def main():
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting application...")

    # Start the Telegram client in a separate thread
    telegram_thread = threading.Thread(target=start_telegram_client, daemon=True)
    telegram_thread.start()

    # Create and start the PySide6 application
    app = QApplication(sys.argv)
    # main_window = MainApp()  # Removed bot_handler and client_handler
    # # main_window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
