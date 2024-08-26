import sys
import os
import requests
from PySide6.QtWidgets import QTextBrowser
from PySide6.QtCore import QRunnable, Slot, Signal, QObject, QThreadPool

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.telegram_client_handler import TelegramClientHandler
from config.config import load_config
from services.mt5_service import MT5Service
from services.together_client import TogetherClient
import threading
import json
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QPlainTextEdit, QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QHBoxLayout, QStackedWidget, QRadioButton, QFrame
from PySide6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor, QPalette
import asyncio
from concurrent.futures import ThreadPoolExecutor
import traceback


class QTextEditLogger(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)
        self.widget.verticalScrollBar().setValue(self.widget.verticalScrollBar().maximum())


class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(int)

class BotWorker(QRunnable):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.main_app.run_bot()
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit((type(e), str(e), e.__traceback__))


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set up the main window with a modern title and geometry
        self.setWindowTitle("Telegram Bot Monitor")
        self.setGeometry(200, 100, 1400, 800)

        # Central widget setup
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)

        # Left side layout for the three panels
        left_layout = QVBoxLayout()

        # First panel: Real-time account information and news
        self.account_info_panel = QWidget()
        self.account_info_layout = QVBoxLayout(self.account_info_panel)

        # Account Information Elements
        self.balance_label = QLabel("Balance: Loading...")
        self.equity_label = QLabel("Equity: Loading...")
        self.margin_label = QLabel("Margin: Loading...")
        self.free_margin_label = QLabel("Free Margin: Loading...")

        # Apply a modern color scheme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F0F3F4;
            }
            QLabel {
                color: #2C3E50;
            }
            QPushButton {
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                opacity: 0.8;
            }
            QLineEdit {
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                padding: 8px;
            }
        """)

        # Enhance label styling
        label_style = """
            font-size: 16px;
            font-weight: bold;
            color: #34495E;
            background-color: #ECF0F1;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 5px;
            border: 1px solid #BDC3C7;
        """
        for label in [self.balance_label, self.equity_label, self.margin_label, self.free_margin_label]:
            label.setStyleSheet(label_style)
            self.account_info_layout.addWidget(label)

        self.panel_switcher = QRadioButton("Show News")
        self.panel_switcher.setChecked(False)
        self.panel_switcher.toggled.connect(self.switch_panels)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.account_info_panel)
        self.stacked_widget.addWidget(QLabel("Today's News: Loading..."))

        left_layout.addWidget(self.stacked_widget)
        left_layout.addWidget(self.panel_switcher)

        # Second panel: Chat placeholder
        self.chat_panel = QLabel("Chat: Coming soon...")
        self.chat_panel.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.chat_panel.setAlignment(Qt.AlignTop)
        left_layout.addWidget(self.chat_panel)

        # Trades monitoring table with a modern design (Third panel)
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(5)
        self.trades_table.setHorizontalHeaderLabels(["Symbol", "Type", "Volume", "Price", "Profit"])
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.trades_table.setStyleSheet("""
            QHeaderView::section {
                background-color: #2E86C1;
                color: white;
                font-weight: bold;
                height: 30px;
            }
            QTableWidget {
                background-color: #F4F6F7;
                border-radius: 5px;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)
        left_layout.addWidget(self.trades_table)

        main_layout.addLayout(left_layout)

        # Log output area with a custom stylesheet for a modern look (Right side)
        right_layout = QVBoxLayout()

        self.status_label = QLabel("Status: Stopped")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2E86C1;")
        right_layout.addWidget(self.status_label)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("""
            background-color: #1E1E1E;
            color: #FFFFFF;
            font-family: Consolas, monospace;
            font-size: 14px;
            padding: 10px;
            border-radius: 5px;
        """)
        right_layout.addWidget(self.log_output)

        input_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter API Key")
        self.api_key_input.setStyleSheet("padding: 8px; font-size: 14px;")
        input_layout.addWidget(QLabel("API Key:"))
        input_layout.addWidget(self.api_key_input)

        self.channel_id_input = QLineEdit()
        self.channel_id_input.setPlaceholderText("Enter Channel ID")
        self.channel_id_input.setStyleSheet("padding: 8px; font-size: 14px;")
        input_layout.addWidget(QLabel("Channel ID:"))
        input_layout.addWidget(self.channel_id_input)

        right_layout.addLayout(input_layout)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Bot")
        self.start_button.setStyleSheet("color: white; padding: 10px; font-size: 16px; border-radius: 5px; background-color: #27AE60;")
        self.start_button.clicked.connect(self.on_start_button_clicked)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Bot")
        self.stop_button.setStyleSheet("color: white; padding: 10px; font-size: 16px; border-radius: 5px; background-color: #E74C3C;")
        self.stop_button.clicked.connect(self.on_stop_button_clicked)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)

        right_layout.addLayout(button_layout)

        main_layout.addLayout(right_layout)
        self.setCentralWidget(central_widget)

        # Load previous configurations
        self.load_config()

        # Set up logging to display in the QTextEdit widget
        self.setup_logging()

        # Set up a timer for updating the trades table and account info
        self.trade_update_timer = QTimer(self)
        self.trade_update_timer.timeout.connect(self.update_trades_table)
        # self.trade_update_timer.start(5000)  # Update every 5 seconds

        self.account_update_timer = QTimer(self)
        self.account_update_timer.timeout.connect(self.update_account_info)
        # self.account_update_timer.start(5000)  # Update every 5 seconds

        # Add animations
        self.start_animation = QPropertyAnimation(self.start_button, b"geometry")
        self.start_animation.setEasingCurve(QEasingCurve.OutBounce)
        self.start_animation.setDuration(1000)

        self.stop_animation = QPropertyAnimation(self.stop_button, b"geometry")
        self.stop_animation.setEasingCurve(QEasingCurve.OutBounce)
        self.stop_animation.setDuration(1000)

        # Modify the news panel
        self.news_panel = QTextBrowser()
        self.news_panel.setOpenExternalLinks(True)
        self.stacked_widget.addWidget(self.news_panel)

        # Add a timer to update news periodically
        self.news_update_timer = QTimer(self)
        self.news_update_timer.timeout.connect(self.update_news)
        # self.news_update_timer.start(600000)  # Update every 10 minutes

        # Call update_news immediately to load news on startup
        # self.update_news()

        # Initialize mt5_service
        self.mt5_service = None

        self.threadpool = QThreadPool()

    def switch_panels(self):
        if self.panel_switcher.isChecked():
            self.stacked_widget.setCurrentIndex(1)  # Show news panel
            # self.update_news()  # Fetch news when switching to the news panel
        else:
            self.stacked_widget.setCurrentIndex(0)  # Show account info panel

    def update_account_info(self):
        if self.mt5_service is not None:
            account_info = self.mt5_service.get_account_info()
            if account_info:
                self.balance_label.setText(f"Balance: {account_info['balance']}")
                self.equity_label.setText(f"Equity: {account_info['equity']}")
                self.margin_label.setText(f"Margin: {account_info['margin']}")
                self.free_margin_label.setText(f"Free Margin: {account_info['free_margin']}")
            else:
                logging.error("Failed to update account info.")

    def setup_logging(self):
        log_handler = QTextEditLogger(self.log_output)
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)

    def on_start_button_clicked(self):
        self.status_label.setText("Status: Running")
        self.status_label.setStyleSheet("color: #28B463;")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        logging.info("Bot started.")

        worker = BotWorker(self)
        worker.signals.finished.connect(self.bot_finished)
        worker.signals.error.connect(self.bot_error)
        self.threadpool.start(worker)

        self.animate_button(self.start_button)

    def bot_finished(self):
        logging.info("Bot finished execution.")
        self.status_label.setText("Status: Finished")
        self.status_label.setStyleSheet("color: #2E86C1;")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def bot_error(self, error_tuple):
        error_type, error_value, error_traceback = error_tuple
        logging.error(f"Bot error: {error_type.__name__}: {error_value}")
        self.status_label.setText("Status: Error")
        self.status_label.setStyleSheet("color: #CB4335;")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def on_stop_button_clicked(self):
        self.status_label.setText("Status: Stopping")
        self.status_label.setStyleSheet("color: #F39C12;")
        self.stop_button.setEnabled(False)
        logging.info("Stopping bot...")
        # Add logic to stop the bot (e.g., set a flag to stop execution)
        # You may need to implement a way to interrupt the bot's execution

    def run_bot(self):
        try:
            logging.info("Loading configuration...")
            config = load_config()
            logging.info("Configuration loaded successfully.")

            logging.info(f"Configuration keys: {', '.join(config.keys())}")

            logging.info("Initializing MT5 service...")
            self.mt5_service = MT5Service()
            logging.info("MT5 service initialized.")

            logging.info("Initializing Together client...")
            try:
                together_client = TogetherClient(api_key=config.get('TOGETHER_API_KEY'))
                logging.info("Together client initialized.")
            except Exception as e:
                logging.error(f"Error initializing Together client: {e}", exc_info=True)
                raise

            logging.info("Initializing Telegram client handler...")
            try:
                client_handler = TelegramClientHandler(
                    api_id=config.get('TELEGRAM_API_ID'),
                    api_hash=config.get('TELEGRAM_API_HASH'),
                    source_channel_id=config.get('TELEGRAM_SOURCE_CHANNEL_ID'),
                    destination_chat_id=config.get('TELEGRAM_DESTINATION_CHAT_ID'),
                    mt5_service=self.mt5_service,
                    together_client=together_client
                )
                logging.info("Telegram client handler initialized.")
            except Exception as e:
                logging.error(f"Error initializing Telegram client handler: {e}", exc_info=True)
                raise

            logging.info("Starting Telegram client handler...")
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(client_handler.run())
            except Exception as e:
                logging.error(f"Error running Telegram client handler: {e}", exc_info=True)
                raise
            finally:
                loop.close()

        except Exception as e:
            logging.error(f"Error in run_bot: {e}", exc_info=True)
            self.status_label.setText("Status: Error")
            self.status_label.setStyleSheet("color: #CB4335;")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")

    def update_trades_table(self):
        if self.mt5_service is not None:
            trades = self.mt5_service.get_open_positions()
            self.trades_table.setRowCount(len(trades))
            for i, trade in enumerate(trades):
                self.trades_table.setItem(i, 0, QTableWidgetItem(trade['symbol']))
                self.trades_table.setItem(i, 1, QTableWidgetItem(trade['type']))
                self.trades_table.setItem(i, 2, QTableWidgetItem(str(trade['volume'])))
                self.trades_table.setItem(i, 3, QTableWidgetItem(str(trade['price'])))
                self.trades_table.setItem(i, 4, QTableWidgetItem(str(trade['profit'])))

    def save_config(self):
        config = {
            'api_key': self.api_key_input.text(),
            'channel_id': self.channel_id_input.text()
        }
        with open('config.json', 'w') as f:
            json.dump(config, f)

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.api_key_input.setText(config['api_key'])
                self.channel_id_input.setText(config['channel_id'])
        except FileNotFoundError:
            pass

    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Exit',
                                     "Are you sure you want to exit?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.save_config()  # Save config before exiting
            event.accept()
        else:
            event.ignore()

    def animate_button(self, button):
        geometry = button.geometry()
        self.start_animation.setStartValue(geometry)
        self.start_animation.setEndValue(geometry.adjusted(-5, -5, 5, 5))
        self.start_animation.start()

        QTimer.singleShot(200, lambda: self.start_animation.setDirection(QPropertyAnimation.Backward))
        QTimer.singleShot(200, self.start_animation.start)

    def update_news(self):
        logging.info("Updating news...")
        try:
            url = 'https://newsapi.org/v2/top-headlines?country=us&category=business&apiKey=8575387f43dd4527bc2a9a0c3201bf68'
            logging.info(f"Fetching news from URL: {url}")
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes
            news_data = response.json()

            # logging.info(f"Received response: {news_data}")

            if news_data['status'] == 'ok':
                news_html = "<h2>Today's Business News:</h2>"
                for article in news_data['articles'][:5]:  # Display top 5 articles
                    news_html += f"<h3><a href='{article['url']}'>{article['title']}</a></h3>"
                    if article['description']:
                        news_html += f"<p>{article['description']}</p>"
                    news_html += "<hr>"

                self.news_panel.setHtml(news_html)
                logging.info("News updated successfully")
                # logging.info(f"News HTML: {news_html}")  # Log the HTML content
            else:
                error_message = f"Failed to fetch news. Status: {news_data['status']}"
                logging.error(error_message)
                self.news_panel.setPlainText(error_message)
        except requests.RequestException as e:
            error_message = f"Error fetching news: {e}"
            logging.error(error_message)
            self.news_panel.setPlainText(error_message)
        except Exception as e:
            error_message = f"Unexpected error updating news: {e}"
            logging.error(error_message)
            self.news_panel.setPlainText(error_message)

        # Force update of the news panel
        self.news_panel.update()

if __name__ == '__main__':
    try:
        logging.basicConfig(level=logging.INFO)
        logging.info("Starting application...")
        app = QApplication(sys.argv)
        app.setStyle('Fusion')  # Set Fusion style for a modern look
        main_window = MainApp()
        main_window.show()
        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"Main application error: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        QMessageBox.critical(None, "Critical Error", f"A critical error occurred: {str(e)}\n\nPlease check the logs for more details.")