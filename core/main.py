import sys
import os

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
import logging
from PySide6.QtWidgets import QApplication
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
from bot.telegram_client_handler import TelegramClientHandler
from config.config import load_config
from gui.main_app import MainApp

def main():
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting application...")

    # Load configuration
    config = load_config()

    # Initialize services
    mt5_service = MT5Service()
    together_client = TogetherClient(api_key=config['TOGETHER_API_KEY'])

    # Initialize Telegram client handler
    api_id = config['TELEGRAM_API_ID']
    api_hash = config['TELEGRAM_API_HASH']
    phone_number = config['TELEGRAM_PHONE_NUMBER']
    source_channel_id = config['TELEGRAM_SOURCE_CHANNEL_ID']
    telegram_handler = TelegramClientHandler(api_id, api_hash, phone_number, source_channel_id, mt5_service, together_client)

    # Create and start the PySide6 application
    app = QApplication(sys.argv)
    main_window = MainApp()
    # main_window.show()

    # Start the Telegram client handler
    telegram_handler.start()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()