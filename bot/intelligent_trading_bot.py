import logging
from services.mt5_service import MT5Service
from services.sma_strategy import SMAStrategy

class IntelligentTradingBot:
    """Automatically trade based on a simple moving average strategy."""

    def __init__(self, mt5_service: MT5Service, symbol: str = "XAUUSD.sml"):
        self.mt5_service = mt5_service
        self.strategy = SMAStrategy(mt5_service, symbol=symbol)
        self.symbol = symbol

    def run(self):
        signal = self.strategy.check_signal()
        if signal is None:
            logging.info("No trading signal from SMA strategy")
            return

        positions = self.mt5_service.get_all_positions()
        # Close opposite positions
        for pos in positions:
            if pos["symbol"] == self.symbol:
                if signal == "buy" and pos["type"] == "sell":
                    self.mt5_service.close_position(pos["ticket"])
                elif signal == "sell" and pos["type"] == "buy":
                    self.mt5_service.close_position(pos["ticket"])

        # Check if we already have a position in the direction of the signal
        positions = self.mt5_service.get_all_positions()
        if any(p["symbol"] == self.symbol and p["type"] == signal for p in positions):
            logging.info("Position already open in direction %s", signal)
            return

        result = self.mt5_service.open_position(self.symbol, signal, volume=0.01)
        if result:
            logging.info("Opened %s position based on SMA signal", signal)
        else:
            logging.error("Failed to open position for SMA signal")
