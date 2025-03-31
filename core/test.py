import sys
import os
import logging
import time
import MetaTrader5 as mt5
from datetime import datetime

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import project components for testing
from services.mt5_service import MT5Service
from config.config import load_config
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mt5_test.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def test_mt5_connection():
    """Test basic MT5 connection and capabilities"""
    # Initialize MT5
    if not mt5.initialize():
        logging.error("Failed to initialize MT5")
        return False
    
    # Log MT5 version
    logging.info(f"MetaTrader5 package version: {mt5.__version__}")
    logging.info(f"MetaTrader5 terminal version: {mt5.version()}")
    
    # Get account info
    account_info = mt5.account_info()
    if account_info:
        logging.info(f"Account number: {account_info.login}")
        logging.info(f"Server: {account_info.server}")
        logging.info(f"Account balance: {account_info.balance}")
        logging.info(f"Account equity: {account_info.equity}")
        logging.info(f"Account margin: {account_info.margin}")
        logging.info(f"Account free margin: {account_info.margin_free}")
        logging.info(f"Account leverage: 1:{account_info.leverage}")
        logging.info(f"Account currency: {account_info.currency}")
        logging.info(f"Trade allowed: {account_info.trade_allowed}")
    else:
        logging.error("Failed to get account info")
        return False
    
    # Check if autotrading is enabled
    terminal_info = mt5.terminal_info()
    if terminal_info:
        logging.info(f"Trade allowed: {terminal_info.trade_allowed}")
        if not terminal_info.trade_allowed:
            logging.warning("AutoTrading is disabled in MT5. Enable it to trade.")
            logging.warning("Go to Tools > Options > Expert Advisors and enable 'Allow automated trading'")
            logging.warning("Also ensure the Algo Trading button on toolbar is enabled (green)")
    
    # Test symbol availability (both XAUUSD and GOLD with variants)
    symbols_to_test = ["XAUUSD", "XAUUSD.a", "GOLD", "GOLD.a"]
    working_symbols = []
    
    for symbol in symbols_to_test:
        # Try to select the symbol first
        selected = mt5.symbol_select(symbol, True)
        if not selected:
            logging.warning(f"Could not select {symbol} in Market Watch")
            continue
            
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            logging.info(f"Symbol {symbol} found and selected")
            logging.info(f"Symbol properties: spread={symbol_info.spread}, digits={symbol_info.digits}")
            logging.info(f"Symbol trade mode: {symbol_info.trade_mode}")
            
            # Log filling modes
            filling_mode = symbol_info.filling_mode
            filling_modes = []
            if filling_mode & mt5.ORDER_FILLING_FOK:
                filling_modes.append("FOK")
            if filling_mode & mt5.ORDER_FILLING_IOC:
                filling_modes.append("IOC")
            if filling_mode & mt5.ORDER_FILLING_RETURN:
                filling_modes.append("RETURN")
            logging.info(f"Symbol filling modes: {', '.join(filling_modes)}")
            
            # Log stop levels
            logging.info(f"Symbol stop level: {symbol_info.trade_stops_level} points")
            logging.info(f"Symbol volume step: {symbol_info.volume_step}")
            logging.info(f"Symbol minimum volume: {symbol_info.volume_min}")
            
            working_symbols.append(symbol)
            
            # Test getting current price
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                logging.info(f"Current {symbol} price: bid={tick.bid}, ask={tick.ask}, spread={tick.ask - tick.bid}")
            else:
                logging.error(f"Failed to get tick for {symbol}")
        else:
            logging.warning(f"Symbol {symbol} not found")
    
    if not working_symbols:
        logging.error("No gold symbols found")
        return False
        
    logging.info(f"Working symbols: {', '.join(working_symbols)}")
    
    # Try all available gold symbols
    for symbol in working_symbols:
        test_order_check(symbol)
        test_margin_calculation(symbol)
    
    # Clean up
    mt5.shutdown()
    return True

def test_order_check(symbol):
    """Test order check functionality for a symbol"""
    logging.info(f"Testing order check for {symbol}")
    
    # Get symbol info and current price
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logging.error(f"Failed to get symbol info for {symbol}")
        return
        
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logging.error(f"Failed to get tick for {symbol}")
        return
    
    # Use minimum volume for test
    volume = symbol_info.volume_min
    price = tick.ask
    
    logging.info(f"Testing BUY order: {volume} lots at {price}")
    
    # First try without filling mode
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "deviation": 50,
        "magic": 123456,
        "comment": "test check",
        "type_time": mt5.ORDER_TIME_GTC,
    }
    
    # Check order without filling type
    logging.info(f"Testing order check without filling type")
    result = mt5.order_check(request)
    log_check_result(result)
    
    # Try different filling modes
    for filling_type, name in [
        (mt5.ORDER_FILLING_FOK, "FOK"),
        (mt5.ORDER_FILLING_IOC, "IOC"),
        (mt5.ORDER_FILLING_RETURN, "RETURN")
    ]:
        request["type_filling"] = filling_type
        logging.info(f"Testing with filling mode: {name}")
        result = mt5.order_check(request)
        log_check_result(result)

def log_check_result(result):
    """Log the result of an order check"""
    if result is None:
        error_code = mt5.last_error()
        logging.error(f"Order check returned None, error code: {error_code}")
        return
        
    if result.retcode == 0:
        logging.info(f"Order check successful: {result.comment}")
        logging.info(f"Margin required: {result.margin}")
    else:
        logging.warning(f"Order check failed: {result.comment}, code: {result.retcode}")

def test_margin_calculation(symbol):
    """Test margin calculation for a symbol"""
    logging.info(f"Testing margin calculation for {symbol}")
    
    # Get current price
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logging.error(f"Failed to get tick for {symbol}")
        return
        
    # Get symbol info for minimum volume
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        logging.error(f"Failed to get symbol info for {symbol}")
        return
        
    volume = symbol_info.volume_min
    
    # Test margin for various volumes
    volumes_to_test = [volume, volume*2, volume*5, 0.01, 0.02, 0.05, 0.1]
    
    account_info = mt5.account_info()
    if not account_info:
        logging.error("Failed to get account info")
        return
        
    logging.info(f"Account free margin: {account_info.margin_free}")
    
    for test_volume in volumes_to_test:
        # Calculate margin for BUY
        buy_margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, test_volume, tick.ask)
        if buy_margin is not None:
            viable = "VIABLE" if buy_margin <= account_info.margin_free else "NOT VIABLE"
            logging.info(f"BUY {test_volume} lots of {symbol} requires {buy_margin} margin ({viable})")
        else:
            logging.error(f"Failed to calculate buy margin for {test_volume} lots")
            
        # Calculate margin for SELL
        sell_margin = mt5.order_calc_margin(mt5.ORDER_TYPE_SELL, symbol, test_volume, tick.bid)
        if sell_margin is not None:
            viable = "VIABLE" if sell_margin <= account_info.margin_free else "NOT VIABLE"
            logging.info(f"SELL {test_volume} lots of {symbol} requires {sell_margin} margin ({viable})")
        else:
            logging.error(f"Failed to calculate sell margin for {test_volume} lots")

def test_with_mt5_service():
    """Test the MT5Service class"""
    logging.info("Testing MT5Service class")
    
    # Initialize MT5Service
    mt5_service = MT5Service()
    
    # Test symbol detection
    logging.info("Testing symbol detection")
    mt5_service.detect_gold_symbol()
    
    # Get account info
    logging.info("Testing account info")
    account_info = mt5_service.get_account_info()
    logging.info(f"Account info: {account_info}")
    
    # Get market context
    logging.info("Testing market context")
    market_context = mt5_service.get_market_context("XAUUSD")
    logging.info(f"Market context: {market_context}")
    
    symbol = market_context.get("symbol", "XAUUSD")
    
    # Test margin check
    logging.info("Testing margin check")
    margin_check = mt5_service.check_margin_for_trade(symbol, 0.01, mt5.ORDER_TYPE_BUY)
    logging.info(f"Margin check result: {margin_check}")
    
    # Test supported filling modes
    logging.info("Testing supported filling modes")
    filling_modes = mt5_service.get_supported_filling_modes(symbol)
    logging.info(f"Supported filling modes: {filling_modes}")
    
    return True

if __name__ == "__main__":
    logging.info("Starting MT5 test")
    logging.info("-" * 50)
    
    # Load configuration if needed
    load_dotenv()
    config = load_config()
    
    # Test basic MT5 connection
    test_result = test_mt5_connection()
    logging.info(f"Basic MT5 test {'passed' if test_result else 'failed'}")
    logging.info("-" * 50)
    
    # Test MT5Service
    service_test_result = test_with_mt5_service()
    logging.info(f"MT5Service test {'passed' if service_test_result else 'failed'}")
    
    logging.info("Test completed")