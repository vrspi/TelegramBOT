import sys
import os

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import logging
from PySide6.QtWidgets import QApplication, QSplashScreen
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from pathlib import Path
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
from bot.telegram_client_handler import TelegramClientHandler
from config.config import load_config
from gui.main_app import MainApp
from services.api_server import APIServer
from services.frontend_server import FrontendServer
from dotenv import load_dotenv

def setup_logging():
    """Set up logging configuration."""
    # Create a custom formatter that can handle Unicode
    class UnicodeFormatter(logging.Formatter):
        def format(self, record):
            # Ensure the message is a string
            if isinstance(record.msg, bytes):
                record.msg = record.msg.decode('utf-8', errors='replace')
            elif not isinstance(record.msg, str):
                record.msg = str(record.msg)
            return super().format(record)

    formatter = UnicodeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # File handler with UTF-8 encoding
    file_handler = logging.FileHandler('trading_bot.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

def initialize_services(config):
    """Initialize all required services."""
    # Initialize MT5 Service
    mt5_service = MT5Service()
    if not mt5_service.initialize_mt5():
        logging.error("Failed to initialize MT5. Please make sure MetaTrader 5 is running.")
        return None, None, None

    # Initialize Together AI Client
    together_client = TogetherClient(api_key=config['TOGETHER_API_KEY'])
    if not together_client:
        logging.error("Failed to initialize Together AI client.")
        return None, None, None

    # Initialize Telegram Handler
    try:
        telegram_handler = TelegramClientHandler(
            api_id=config['TELEGRAM_API_ID'],
            api_hash=config['TELEGRAM_API_HASH'],
            phone_number=config['TELEGRAM_PHONE_NUMBER'],
            source_channel_id=config['TELEGRAM_SOURCE_CHANNEL_ID'],
            mt5_service=mt5_service,
            together_client=together_client
        )
    except Exception as e:
        logging.error(f"Failed to initialize Telegram handler: {e}")
        return None, None, None

    return mt5_service, together_client, telegram_handler

def main():
    """Main application entry point."""
    # Set up logging
    setup_logging()
    logging.info("Starting Trading Bot application...")

    # Create the Qt application and splash screen
    app = QApplication(sys.argv)
    pixmap = QPixmap(400, 300)
    pixmap.fill(Qt.darkGray)
    splash = QSplashScreen(pixmap)
    splash.showMessage("Initializing...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
    splash.show()
    app.processEvents()

    # Load environment variables and configuration
    load_dotenv()
    config = load_config()
    if not config:
        logging.error("Failed to load configuration. Please check your config files.")
        splash.finish(None)
        return

    # Initialize services
    mt5_service, together_client, telegram_handler = initialize_services(config)
    if not all([mt5_service, together_client, telegram_handler]):
        logging.error("Failed to initialize one or more required services. Exiting...")
        splash.finish(None)
        return

    # Start backend API server
    api_server = APIServer(mt5_service=mt5_service)
    api_server.start()

    # Start Next.js frontend
    frontend_dir = Path(project_root) / "frontend"
    frontend_server = FrontendServer(frontend_dir)
    frontend_server.start()

    try:
        main_window = MainApp(frontend_server=frontend_server, api_server=api_server)
        splash.showMessage("Starting application...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        app.processEvents()

        # Start the Telegram client handler
        telegram_handler.start()

        splash.finish(main_window)
        main_window.show()

        # Start the application event loop
        sys.exit(app.exec())

    except Exception as e:
        logging.error(f"Unexpected error in main application: {e}", exc_info=True)
    finally:
        # Cleanup
        if mt5_service:
            del mt5_service
        if together_client:
            del together_client
        logging.info("Application shutdown complete.")

if __name__ == '__main__':
    main()