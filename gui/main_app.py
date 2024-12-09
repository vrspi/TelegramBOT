from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel
from PySide6.QtCore import Qt, Slot
import logging

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trading Bot")
        self.setGeometry(100, 100, 800, 600)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Status label
        self.status_label = QLabel("Bot Status: Starting...")
        layout.addWidget(self.status_label)
        
        # Log viewer
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        layout.addWidget(self.log_viewer)
        
        # Control buttons
        button_layout = QVBoxLayout()
        
        self.start_button = QPushButton("Start Bot")
        self.start_button.clicked.connect(self.start_bot)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Bot")
        self.stop_button.clicked.connect(self.stop_bot)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        
        layout.addLayout(button_layout)
        
        # Initialize logger
        self.setup_logger()
        
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
        
    @Slot(str)
    def log_message(self, message: str):
        """Slot for receiving log messages from other components."""
        self.logger.info(message)
        
    @Slot()
    def start_bot(self):
        """Start the bot."""
        self.logger.info("Starting bot...")
        self.status_label.setText("Bot Status: Running")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
    @Slot()
    def stop_bot(self):
        """Stop the bot."""
        self.logger.info("Stopping bot...")
        self.status_label.setText("Bot Status: Stopped")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
    def closeEvent(self, event):
        """Handle application close event."""
        self.logger.info("Shutting down application...")
        event.accept()