import logging
import pandas as pd
import MetaTrader5 as mt5
from services.mt5_service import MT5Service

class SMAStrategy:
    """Simple moving average crossover strategy."""
    def __init__(self, mt5_service: MT5Service, symbol: str = "XAUUSD.sml", timeframe: int = mt5.TIMEFRAME_M5,
                 fast_period: int = 20, slow_period: int = 50):
        self.mt5_service = mt5_service
        self.symbol = symbol
        self.timeframe = timeframe
        self.fast_period = fast_period
        self.slow_period = slow_period

    def check_signal(self):
        bars = self.mt5_service.get_rates(self.symbol, self.timeframe, self.slow_period + 5)
        if bars is None or bars.empty:
            return None

        bars["fast"] = bars["close"].rolling(self.fast_period).mean()
        bars["slow"] = bars["close"].rolling(self.slow_period).mean()

        if len(bars.dropna()) < 2:
            return None

        if bars["fast"].iloc[-1] > bars["slow"].iloc[-1] and bars["fast"].iloc[-2] <= bars["slow"].iloc[-2]:
            return "buy"
        if bars["fast"].iloc[-1] < bars["slow"].iloc[-1] and bars["fast"].iloc[-2] >= bars["slow"].iloc[-2]:
            return "sell"
        return None
