import logging
from PySide6.QtCore import QObject, Signal

class QTextEditLogger(logging.Handler, QObject):
    log_signal = Signal(str)  # Signal to send log messages to the QTextEdit

    def __init__(self, parent):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.widget = parent

        # Connect the signal to the append method of the QTextEdit widget
        self.log_signal.connect(self.widget.appendPlainText)

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)  # Emit the signal to update the QTextEdit
