from PySide6.QtWidgets import QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl


class MainApp(QMainWindow):
    """Main window wrapping the web-based UI."""

    def __init__(self, frontend_url="http://localhost:3000", frontend_server=None, api_server=None):
        super().__init__()
        self.frontend_server = frontend_server
        self.api_server = api_server

        self.setWindowTitle("Trading Bot")
        self.setGeometry(100, 100, 1024, 768)

        self.web_view = QWebEngineView()
        self.web_view.load(QUrl(frontend_url))
        self.setCentralWidget(self.web_view)

    def closeEvent(self, event):
        if self.frontend_server:
            self.frontend_server.stop()
        if self.api_server:
            self.api_server.stop()
        super().closeEvent(event)
