from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLabel,
    QProgressBar,
    QTabWidget,
)
from PySide6.QtCore import Qt, Slot, QTimer
import logging

class MainApp(QMainWindow):
    def __init__(self, mt5_service=None, telegram_handler=None):
        super().__init__()
        self.mt5_service = mt5_service
        self.telegram_handler = telegram_handler

        self.setWindowTitle("Trading Bot")
        self.setGeometry(100, 100, 900, 700)

        # Apply basic styling
        self.setup_styles()

        # Central tab widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # ----------------------- Dashboard Tab -----------------------
        dashboard = QWidget()
        dash_layout = QVBoxLayout(dashboard)

        self.status_label = QLabel("Bot Status: Stopped")
        dash_layout.addWidget(self.status_label)

        # Account info labels
        self.account_labels = {
            "balance": QLabel("Balance: --"),
            "equity": QLabel("Equity: --"),
            "margin": QLabel("Margin: --"),
            "free_margin": QLabel("Free Margin: --"),
            "margin_level": QLabel("Margin Level: --"),
        }
        for label in self.account_labels.values():
            dash_layout.addWidget(label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        dash_layout.addWidget(self.progress_bar)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Bot")
        self.start_button.clicked.connect(self.start_bot)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Bot")
        self.stop_button.clicked.connect(self.stop_bot)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)

        dash_layout.addLayout(button_layout)
        self.tabs.addTab(dashboard, "Dashboard")

        # ----------------------- Trading Journey Tab -----------------------
        self.journal_viewer = QTextEdit()
        self.journal_viewer.setReadOnly(True)
        self.tabs.addTab(self.journal_viewer, "Journey")

        # ----------------------- Logs Tab -----------------------
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.tabs.addTab(self.log_viewer, "Logs")

        # ----------------------- Statistics Tab -----------------------
        self.stats_viewer = QTextEdit()
        self.stats_viewer.setReadOnly(True)
        self.tabs.addTab(self.stats_viewer, "Statistics")

        # Initialize logger
        self.setup_logger()
        self.update_account_info()
        
    def setup_logger(self):
        """Set up logging to GUI."""
        class QTextEditLogger(logging.Handler):
            def __init__(self, widget):
                super().__init__()
                self.widget = widget
                self.widget.setReadOnly(True)
                
            def emit(self, record):
                msg = self.format(record)
                self.widget.append(msg)
                
        # Create logger
        self.logger = logging.getLogger("GUI")
        self.logger.setLevel(logging.INFO)
        
        # Create handler
        log_handler = QTextEditLogger(self.log_viewer)
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Add handler to logger
        self.logger.addHandler(log_handler)

    def update_account_info(self):
        """Refresh account information labels."""
        if not self.mt5_service:
            return
        info = self.mt5_service.get_account_info()
        self.account_labels["balance"].setText(f"Balance: {info['balance']}")
        self.account_labels["equity"].setText(f"Equity: {info['equity']}")
        self.account_labels["margin"].setText(f"Margin: {info['margin']}")
        self.account_labels["free_margin"].setText(f"Free Margin: {info['free_margin']}")
        self.account_labels["margin_level"].setText(f"Margin Level: {info['margin_level']}")

    def setup_styles(self):
        """Apply a simple dark theme to the window."""
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #282c34;
                color: #ffffff;
            }
            QLabel {
                font-size: 16px;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
            }
            QPushButton {
                background-color: #007acc;
                color: #ffffff;
                padding: 6px;
                border-radius: 3px;
            }
            QPushButton:disabled {
                background-color: #555555;
            }
            """
        )
        
    @Slot(str)
    def log_message(self, message: str):
        """Slot for receiving log messages from other components."""
        self.logger.info(message)
        self.journal_viewer.append(message)
        
    @Slot()
    def start_bot(self):
        """Start the bot."""
        self.logger.info("Starting bot...")
        self.status_label.setText("Bot Status: Running")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(50)
        self.update_account_info()
        
    @Slot()
    def stop_bot(self):
        """Stop the bot."""
        self.logger.info("Stopping bot...")
        self.status_label.setText("Bot Status: Stopped")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        
    def update_progress(self):
        """Update progress bar during startup."""
        value = self.progress_bar.value() + 5
        if value >= 100:
            value = 100
            self.timer.stop()
            self.progress_bar.setVisible(False)
            self.update_account_info()
        self.progress_bar.setValue(value)

    def closeEvent(self, event):
        """Handle application close event."""
        self.logger.info("Shutting down application...")
        event.accept()
